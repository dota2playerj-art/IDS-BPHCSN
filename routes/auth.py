"""Authentication and the role-dispatch entry points.

Mounted at the site root, so these keep their original URLs: /, /login,
/logout, /dashboard.


WHY THIS FILE WRITES TO THE AUDIT TRAIL
---------------------------------------
It did not, for most of the project's life, and that single omission was the
reason three separate screens printed "Not tracked": Audit Logs' Login Events
card, User Management's Last Login column, and the security half of Settings.
None of them was missing a query -- audit_logs and its reader existed all along.
What was missing was a writer, and this is the file that owed them one.

Both outcomes are recorded, not just the successful one. In a system holding
patient records, "somebody tried five times to get into the administrator
account this afternoon and failed" is the more urgent of the two facts, and it
is the one a trail of successes alone can never tell anybody.

WHAT A FAILED ATTEMPT RECORDS, AND WHAT IT MUST NEVER RECORD
-------------------------------------------------------------
An entry for a refusal names the account that was aimed at, the moment, and the
address it came from. It does not record the password that was supplied, and the
prohibition is absolute -- not "hashed first", not "truncated", not "only the
length". A password typed into the wrong account is very often the right
password for another one, so an audit trail that captured failed passwords would
be a plaintext credential store that every administrator is invited to read, and
it would be built out of exactly the passwords most worth stealing.

The rule is enforced structurally rather than by care. _log_refused_sign_in()
below is never passed the submitted password: it receives the matched user row
and the address, and it builds its sentence from the *stored* account fields
(username, full name, role). Nothing an anonymous caller typed reaches the
audit row at all.

DEACTIVATION IS ENFORCED HERE, AND NOWHERE ELSE IT COULD BE
------------------------------------------------------------
users.is_active has existed since the first schema and every other reader in the
project honoured it -- a deactivated account is kept off the booking dropdown, is
not texted by a broadcast, and is badged "Deactivated" on User Management under a
card that reads "Access revoked". This route never asked, so that card was making
a promise the application did not keep: a revoked account could still sign in with
its old password and reach every screen its role admits. It is checked now, and
the check is the difference between a status flag and a revocation.

The order of the three questions below is deliberate. The password is verified
BEFORE the active flag is consulted, even though a deactivated account is refused
either way, for two independent reasons:

* Timing. Skipping the hash comparison for deactivated accounts would make those
  requests measurably faster than every other refusal, which turns the login form
  into an oracle for which accounts have been switched off. The work is done in
  both cases so the two look alike from outside.
* Because the answer is worth recording. "A deactivated account was presented
  with the CORRECT password" and "a deactivated account was presented with a
  wrong one" are different events -- the first says a credential someone believed
  was withdrawn is still live and still in somebody's hands, which may mean that
  password needs changing wherever else it is used. The entry says which it was.
  It still never says what the password was.

WHAT IS STILL NOT RECORDED HERE, AND WHY
-----------------------------------------
An attempt against a username that does not exist writes nothing. The column
audit_logs.user_id is NOT NULL and foreign-keyed to a real account (schema.sql),
so there is no row such an attempt could be attributed to, and log_action()
returns None rather than fabricating an author. What is recorded is therefore
every refusal aimed at an account that exists -- which is every attempt that
could ever have succeeded, and the whole of what a repeated-guessing alert would
need.

Signing out is also not recorded. logout() clears the session and writes nothing,
so the figures these entries feed are sign-in counts and not session counts. Both
absences are stated on the screens that report the counts rather than left to be
inferred from a number.

One more boundary used to be stated here, and it has since been closed rather
than narrowed. The active flag was checked when a session STARTED and not on any
request afterwards, so an account deactivated while it was already signed in kept
that session until its holder chose to log out. This note said closing it "would
mean a lookup on every guarded request rather than a change to this file", and
that is exactly where the fix went: utils/security.py now re-reads the account on
every guarded request and clears the session the moment the flag reads false, at
no extra database cost -- see that module's header for why it is cheaper than
what it replaced. This file is unchanged by it apart from the note you are
reading and the refusal function below, which moved so both callers could share
one copy of it.

What that leaves is a much smaller boundary, and it is a property of sessions
rather than of this file: a revocation takes effect on the deactivated holder's
NEXT guarded request, not at the instant an administrator sets the flag. There is
no push, and a browser sitting on an already-rendered page has already been sent
that page. The window is one click long.
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
from models.users import get_user_by_username
from utils.roles import normalize_role
from utils.security import get_current_user, login_required, refuse_credentials

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
        "the password supplied was correct, so this credential still works and "
        "only the account's deactivation stopped it"
        if password_verified else
        "the password supplied was also wrong"
    )
    return log_action(
        user_id=user["id"],
        action=ACTION_LOGIN_BLOCKED,
        module=MODULE_AUTH,
        details=(
            f'Sign-in blocked for account "{user["username"]}" '
            f'({user["full_name"]}, {user["role"]}), from '
            f'{_address_phrase(ip_address)}; the account is marked deactivated, '
            f'so no session was started -- {credential}. The person at the form '
            "was told only that the credentials were invalid, the same wording a "
            "wrong password receives, so the refusal reveals nothing about the "
            "account's status. The value supplied is not recorded anywhere, by "
            "design"
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
            f'{_address_phrase(ip_address)}; the password supplied did not match '
            "the stored hash, and no session was started. The value supplied is "
            "not recorded anywhere, by design"
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
_refuse = refuse_credentials

# The maintenance window's own refusal at the login form. Built the same shape
# _refuse is -- flash, then redirect to the form with the message on the query
# string -- so it renders in the same alert box login.html already draws and no
# template change is needed to show it.
MAINTENANCE_SIGN_IN_MESSAGE = (
    "The system is temporarily in maintenance mode and is open to "
    "Administrators only. Your username and password are correct. Please try "
    "again shortly."
)


def _refuse_maintenance():
    flash(MAINTENANCE_SIGN_IN_MESSAGE)
    return redirect(url_for("auth.login", error=MAINTENANCE_SIGN_IN_MESSAGE))


@auth_bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("auth.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = request.args.get("error")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_username(username)

        password_verified = False
        if user is not None:
            user_dict = dict(user)
            password_hash = user_dict.get("password_hash")
            if password_hash:
                password_verified = check_password_hash(password_hash, password)
            elif user_dict.get("password"):
                password_verified = user_dict["password"] == password

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
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]

            # Written once here rather than in each of the four dispatch
            # branches below: the entry records that this account was admitted,
            # which is true identically whichever dashboard it then lands on.
            _log_sign_in(user, ip_address)

            normalized_role = normalize_role(user["role"])
            if normalized_role == "admin":
                session["role"] = "Admin"
                return redirect(url_for("admin.admin_dashboard"))
            elif normalized_role == "health staff":
                session["role"] = "Health Staff"
                return redirect(url_for("staff.staff_dashboard"))
            elif normalized_role == "barangay official":
                session["role"] = "Barangay Official"
                return redirect(url_for("official.official_dashboard"))
            else:
                session["role"] = user["role"]
                return redirect(url_for("auth.dashboard"))

        # Everything below this point is a refusal: either the username matched
        # no account, or it matched an active one and the password did not.
        _log_refused_sign_in(user, ip_address)
        return _refuse()

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    normalized_role = normalize_role(user["role"])
    if normalized_role == "admin":
        return redirect(url_for("admin.admin_dashboard"))
    if normalized_role == "health staff":
        return redirect(url_for("staff.staff_dashboard"))
    return redirect(url_for("official.official_dashboard"))
