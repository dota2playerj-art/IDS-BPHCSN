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
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from models.audit import (
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    MODULE_AUTH,
    log_action,
)
from models.users import get_user_by_username
from utils.roles import normalize_role
from utils.security import get_current_user, login_required

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

        # Read once, before either branch, so the successful entry and the
        # refused one cannot end up describing the address differently.
        ip_address = request.remote_addr

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
        # no account, or it matched one and the password did not.
        _log_refused_sign_in(user, ip_address)

        # The message stays identical for both, and deliberately says nothing
        # about which half failed. Distinguishing "no such account" from "wrong
        # password" would let anyone enumerate the valid usernames from the login
        # form -- the trail records the difference, the stranger at the form is
        # not told it.
        flash("Invalid security credentials.")
        return redirect(url_for("auth.login", error="Invalid security credentials."))

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
