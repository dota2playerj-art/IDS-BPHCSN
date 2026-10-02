"""Authentication and the role-dispatch entry points.

Mounted at the site root, so these keep their original URLs: /, /login,
/logout, /dashboard.
"""
from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from models.audit import (
    ACTION_LOGIN_BLOCKED,
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    MODULE_AUTH,
    log_action,
)
from models.settings import maintenance_mode
from models.users import get_user_by_id, get_user_by_username, needs_password_change
from routes.account_views import my_account_context, process_password_change
from utils.login_throttle import (
    THROTTLED_KEY, THROTTLED_MESSAGE, clear as clear_failures, is_throttled, record_failure,
)
from utils.roles import normalize_role
from utils.security import (
    INVALID_CREDENTIALS_KEY,
    INVALID_CREDENTIALS_MESSAGE,
    SESSION_EXPIRED_KEY,
    SESSION_EXPIRED_MESSAGE,
    SESSION_IDLE_KEY,
    SESSION_IDLE_MESSAGE,
    get_current_user,
    login_required,
    refuse_credentials,
    start_session_clock,
)

auth_bp = Blueprint("auth", __name__)

# What an entry says when the request carried no address -- behind a proxy that
# strips it, or from a test client. Spelled out rather than left blank, so a
# reader can tell the address was absent from the request instead of wondering
# whether the logger dropped it.
_NO_ADDRESS = "an address the request did not carry"


def _address_phrase(ip_address):
    return ip_address or _NO_ADDRESS


def _log_sign_in(user, ip_address):
    """Record that this account was let in.

    Self-contained on the same rule every other entry in this project follows:
    read months later, on its own, it must say who signed in and as what without
    anyone having to open the users table to find out. So the account's full name
    and role are spelled into the sentence rather than left implicit in the
    user_id -- a role that is later changed must not silently rewrite the history
    of what access an old sign-in actually granted.
    """
    return log_action(
        user_id=user["id"],
        action=ACTION_LOGIN_SUCCESS,
        module=MODULE_AUTH,
        details=(
            f'{user["full_name"]} signed in to account "{user["username"]}" '
            f'as {user["role"]}, from {_address_phrase(ip_address)}; '
            "password verified against the stored hash; session started"
        ),
        ip_address=ip_address,
    )


def _log_blocked_sign_in(user, ip_address, password_verified):
    """Record that a deactivated account was refused, and say whether its
    password still works.

    Its own entry rather than a variant of the refusal below, because an
    administrator reading the trail is asking two different questions of the two
    rows. A wrong password on a live account is a typo or a guess. A sign-in
    attempt on a deactivated one is somebody still holding a credential that was
    supposed to have been withdrawn -- and if `password_verified` is true, still
    holding a WORKING one, which is the single most actionable line this trail
    can produce. That clause is why the password is checked before the flag: the
    answer is worth having.

    Recording the outcome of the check is not the same as recording the value
    checked, and the value is not a parameter of this function any more than it
    is of the one below. `password_verified` is a boolean the caller has already
    computed.
    """
    if user is None:
        return None

    credential = (
        "the password was correct"
        if password_verified else
        "the password was also wrong"
    )
    return log_action(
        user_id=user["id"],
        action=ACTION_LOGIN_BLOCKED,
        module=MODULE_AUTH,
        details=(
            f'Sign-in blocked for account "{user["username"]}" '
            f'({user["full_name"]}, {user["role"]}), from '
            f'{_address_phrase(ip_address)}; the account is deactivated; '
            f'{credential}'
        ),
        ip_address=ip_address,
    )


def _log_refused_sign_in(user, ip_address):
    """Record that a sign-in was refused, and record nothing that was typed.

    `user` is the matched account row, or None when the username matched no
    account. None writes nothing: see the module note -- there is no account to
    attribute the row to, and an audit trail must not invent one.

    EVERY VALUE BELOW COMES FROM THE STORED ACCOUNT ROW.
    The username written is user["username"] -- the one on file -- and not the
    string the form submitted, even though a matched lookup means the two are
    equal. That is deliberate: it means no caller-supplied text is on any path
    into this table, so the question "could something a stranger typed end up in
    the audit log" has one answer and it does not depend on reading the lookup.
    The submitted password is not a parameter of this function and cannot be.
    """
    if user is None:
        return None

    return log_action(
        user_id=user["id"],
        action=ACTION_LOGIN_FAILED,
        module=MODULE_AUTH,
        details=(
            f'Sign-in refused for account "{user["username"]}" '
            f'({user["full_name"]}, {user["role"]}), from '
            f'{_address_phrase(ip_address)}; the password was wrong'
        ),
        ip_address=ip_address,
    )


# THE ONE RESPONSE EVERY REFUSAL RETURNS -- AND IT NOW LIVES IN utils/security.py.
# One function rather than the same two lines at each refusal site, because the
# security property here is that the outcomes are INDISTINGUISHABLE from the
# outside -- no such account, wrong password, deactivated account -- and a
# property that depends on copies of a string staying equal is a property waiting
# to be broken by an edit to one of them. This comment used to end "a fourth
# outcome added later gets the identical response by construction rather than by
# remembering to", and that outcome has now arrived: a session revoked
# mid-visit, because the per-request check in utils/security.py found the account
# deactivated after the session had already started.
#
# That refusal cannot be raised from this module -- utils/security.py is imported
# BY routes, not the other way round -- so the function moved down to where both
# callers can reach it, and this name is now an alias for the moved one. Nothing
# about the response changed. What changed is that "by construction" is now
# literally true: the second caller returns the same response because it calls
# the same function, not because somebody copied the string correctly.
#
# In particular there is still no "this account has been deactivated" message,
# and there must never be one. It would be helpful to the one person who deserves
# it and a free account-enumeration oracle for everybody else: anyone could sort
# a list of guessed usernames into real-and-disabled, real-and-live, and
# fictional, without ever knowing a password. The distinction is recorded in the
# audit trail, where only a signed-in Admin can read it.
#
# The one person it would be helpful to is now told, and not by this form: an
# Administrator who deactivates their own account is signed out by the route that
# did it, and sees a notice saying so here on the next page. It arrives as a
# flash in their own signed session cookie, never as a response to anything
# posted to this form -- utils/security.py end_session_after_self_deactivation().
_refuse = refuse_credentials

# The maintenance window's own refusal at the login form. Built the same shape
# _refuse is -- flash, then redirect to the form with a key on the query string
# -- so it renders in the same alert box login.html already draws and no
# template change is needed to show it.
MAINTENANCE_SIGN_IN_MESSAGE = (
    "The system is temporarily in maintenance mode and is open to "
    "Administrators only. Your username and password are correct. Please try "
    "again shortly."
)
MAINTENANCE_SIGN_IN_KEY = "maintenance"


def _refuse_maintenance():
    flash(MAINTENANCE_SIGN_IN_MESSAGE)
    return redirect(url_for("auth.login", error=MAINTENANCE_SIGN_IN_KEY))


# EVERY SENTENCE THE LOGIN FORM WILL SHOW FROM ITS QUERY STRING, AND NO OTHER.
# login() looks ?error= up here and hands the template the sentence it finds --
# never the value that arrived. It used to hand over the value, so
# /login?error=<anything> printed <anything> under the health center's name: a
# link anyone could craft to put their own words on this page. A key missing
# from this table shows no message at all -- not a fallback sentence, and not
# the text supplied.
#
# Both sentences are safe for anyone to summon by typing the key, because both
# were already the answer any visitor could get by submitting the form: neither
# names an account or says anything about one. A new entry must meet the same
# test. The self-deactivation notice is deliberately NOT here -- it travels
# only as a flash in the signed session cookie of the browser that earned it
# (utils/security.py end_session_after_self_deactivation()), and a key for it
# would let anybody display it.
LOGIN_FORM_MESSAGES = {
    INVALID_CREDENTIALS_KEY: INVALID_CREDENTIALS_MESSAGE,
    MAINTENANCE_SIGN_IN_KEY: MAINTENANCE_SIGN_IN_MESSAGE,
    # Five failures in five minutes (utils/login_throttle.py). Same text for everyone.
    THROTTLED_KEY: THROTTLED_MESSAGE,
    # The two session limits (utils/security.py). Safe for anyone to summon:
    # they name no account and state a rule that is the same for everyone.
    SESSION_IDLE_KEY: SESSION_IDLE_MESSAGE,
    SESSION_EXPIRED_KEY: SESSION_EXPIRED_MESSAGE,
}


@auth_bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("auth.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = LOGIN_FORM_MESSAGES.get(request.args.get("error", ""))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # After repeated failures the form is closed for a short time, before any
        # account is looked up, so the answer is the same for every username.
        if is_throttled(username, request.remote_addr):
            return redirect(url_for("auth.login", error=THROTTLED_KEY))

        user = get_user_by_username(username)

        # Only a stored hash is ever compared. An account with no hash cannot
        # sign in.
        password_verified = False
        if user is not None and user["password_hash"]:
            password_verified = check_password_hash(user["password_hash"], password)

        # Read once, before any branch, so entries written by different outcomes
        # cannot end up describing the address differently.
        ip_address = request.remote_addr

        # Deactivation is checked AFTER the password comparison above and BEFORE
        # the sign-in below -- see the module note for why that order is load
        # bearing in both directions. NOT NULL DEFAULT 1 in the schema, so the
        # bool() is about SQLite handing back an integer rather than about the
        # value ever being absent.
        account_deactivated = user is not None and not bool(user["is_active"])

        if account_deactivated:
            # The correct password is deliberately not enough to get past this.
            # That is the entire point of the fix: User Management's Deactivated
            # card says "Access revoked", and until this branch existed the
            # application did not keep that promise.
            _log_blocked_sign_in(user, ip_address, password_verified)
            record_failure(username, ip_address)
            return _refuse()

        # MAINTENANCE MODE, CHECKED AFTER THE PASSWORD AND AFTER DEACTIVATION.
        #
        # The order is the same one the deactivation branch above is placed by,
        # and for the same reason in both directions. It is AFTER the password
        # comparison so that a wrong password during a maintenance window is
        # still a wrong password -- telling somebody the system is closed would
        # otherwise confirm that the credentials they guessed were right. It is
        # AFTER the deactivation branch so a revoked account is refused as
        # revoked whatever the switch says; that is a security decision about
        # one account and must not be masked by a message about the whole
        # system.
        #
        # AN ADMINISTRATOR IS NEVER STOPPED HERE. The condition is "not admin",
        # so there is no branch for them to fall down -- the same structural
        # property utils/security.py's guard has, and the reason an
        # administrator can always sign in and switch the system back on even
        # if their session expired while it was closed.
        #
        # IT DOES NOT REUSE refuse_credentials(). That function says "Invalid
        # security credentials", which is deliberately vague because at the
        # login form the truth would be an account-enumeration oracle. Here the
        # credentials were correct and vagueness would be a lie -- it would send
        # a health worker to find an administrator to reset a password that
        # works. This is the one refusal at this form that can safely say what
        # actually happened, because it reveals nothing about the account: the
        # answer is the same for every non-Administrator username, existing or
        # not... which is exactly why it is asked only after the password check,
        # where an unknown username has already been turned away.
        #
        # NOTHING IS LOGGED. _log_refused_sign_in() means "these credentials
        # were wrong" and writing it here would put a false statement in the
        # trail; ACTION_LOGIN_BLOCKED means "this account is deactivated" and is
        # equally untrue. The fact a reviewer needs is already recorded exactly
        # once -- who closed the system and when -- and every refusal in the
        # window follows from that single entry.
        maintenance_blocked = (
            user is not None
            and password_verified
            and maintenance_mode()
            and normalize_role(user["role"]) != "admin"
        )
        if maintenance_blocked:
            return _refuse_maintenance()

        if user is not None and password_verified:
            clear_failures(username, ip_address)
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            # The start of both session limits. See utils/security.py.
            start_session_clock()

            # Written once here rather than in each of the dispatch
            # branches below: the entry records that this account was admitted,
            # which is true identically whichever dashboard it then lands on.
            _log_sign_in(user, ip_address)

            normalized_role = normalize_role(user["role"])
            if normalized_role == "admin":
                session["role"] = "Admin"
                destination = url_for("admin.admin_dashboard")
            elif normalized_role == "health staff":
                session["role"] = "Health Staff"
                destination = url_for("staff.staff_dashboard")
            elif normalized_role == "doctor":
                # The Doctor works the clinical floor's screens, so lands on
                # its dashboard. routes/staff.py says why the two roles share
                # one blueprint.
                session["role"] = "Doctor"
                destination = url_for("staff.staff_dashboard")
            elif normalized_role == "barangay official":
                session["role"] = "Barangay Official"
                destination = url_for("official.official_dashboard")
            else:
                session["role"] = user["role"]
                destination = url_for("auth.dashboard")

            # A password someone else set must be replaced before anything
            # else. utils/security.py enforces it on every request; this only
            # saves one redirect. Read with SELECT *, so a database without the
            # column (not yet migrated) still signs in.
            if needs_password_change(get_user_by_id(user["id"])):
                destination = url_for("auth.my_account")
            return redirect(destination)

        # Everything below this point is a refusal: either the username matched
        # no account, or it matched an active one and the password did not.
        _log_refused_sign_in(user, ip_address)
        record_failure(username, ip_address)
        return _refuse()

    return render_template("login.html", error=error)


# Signing out is a POST with the form token like every other POST (utils/csrf.py). A GET
# (an old bookmark) does not sign anyone out: it goes to the person's own dashboard, or to
# the sign-in page when nobody is signed in, with no message. No guard, so signing out
# works during maintenance and while a password change is required.
@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "GET":
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return redirect(url_for("auth.dashboard"))
    session.clear()
    return redirect(url_for("auth.login"))


# MY ACCOUNT. Every signed-in person, whatever their role, reading their own
# account and changing their own password. See the module note above for why the
# pair is mounted here rather than under a role prefix, and
# routes/account_views.py for everything they decide.
@auth_bp.route("/account")
@login_required
def my_account():
    return render_template("my_account.html", **my_account_context())


# POST only, and no GET, for the reason routes/admin.py's write endpoints have
# none: this changes a credential, so there is no URL to navigate to and none a
# link, a bookmark or a prefetch could reach.
#
# IT IS NOT role_required ANYTHING, AND THAT IS NOT AN OVERSIGHT. Every other
# password-writing endpoint in this project is Admin-only because an endpoint any
# role could reach would let that role set a password on the Administrator
# account and sign in as it. That argument does not apply here and cannot: this
# route reads no account from the request. It changes the password of whoever
# sent it, and only after verifying the password that account already has, so the
# most a forged post can achieve is what its own sender could achieve by typing
# it on the form -- changing their own password, which is the feature.
#
# A REFUSED SUBMIT RE-RENDERS THIS SCREEN AT 200 rather than redirecting, the
# same shape add_user() and reset_user_password() use. Three password boxes are
# cleared by a refusal whatever happens, so what survives the round trip is the
# error beside the box it belongs to -- which is the whole of what redisplay can
# preserve on a form made entirely of passwords, and exactly why it must not be
# thrown away into a flash on another page.
@auth_bp.route("/account/password", methods=["POST"])
@login_required
def change_own_password():
    changed, context, message = process_password_change(
        request.form, request.remote_addr
    )
    if changed:
        flash(message)
        return redirect(url_for("auth.my_account"))
    if context is None:
        # The signed-in row could not be read -- unreachable behind the guard,
        # which refuses a session naming a row that is not there. Answered with a
        # sentence rather than a traceback.
        flash(message)
        return redirect(url_for("auth.my_account"))
    return render_template("my_account.html", **context)


# KEEP-ALIVE. static/js/session.js calls this while the person is active, at
# most once every config.KEEPALIVE_INTERVAL. The guard does the work: a request
# that passes it counts as activity. It never changes the sign-in time, so it
# cannot stretch the 12-hour limit. When the session has ended, the guard
# answers with a 401 and JSON (the script sends X-Requested-With: fetch), and
# the script goes to the login page.
@auth_bp.route("/session/keep-alive", methods=["POST"])
@login_required
def keep_alive():
    return "", 204


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    normalized_role = normalize_role(user["role"])
    if normalized_role == "admin":
        return redirect(url_for("admin.admin_dashboard"))
    if normalized_role in {"health staff", "doctor"}:
        return redirect(url_for("staff.staff_dashboard"))
    return redirect(url_for("official.official_dashboard"))
