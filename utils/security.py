"""Session lookup, the RBAC decorators, and the per-request account check.

WHAT A GUARDED REQUEST ASKS, AND WHEN THAT LIST GREW
-----------------------------------------------------
Until now a guarded request asked two questions: is there a session, and does its
role admit this route. Neither of them re-reads the account, so `users.is_active`
was consulted exactly once in an account's whole life -- at the login form. An
account deactivated while its holder was signed in kept working until they chose
to log out, which could be days. routes/auth.py's own module note named this and
said closing it "would mean a lookup on every guarded request rather than a
change to this file". This is that change, and the lookup turned out to be one
the request was already making twice.

A guarded request now asks four questions, in this order:

    1. is there a session at all           session["user_id"]
    2. does the account still exist        get_current_user()
    3. is the account still active         user["is_active"]
    4. is the system open to this role     maintenance_mode()

Failing 2 or 3 clears the session and returns the same refusal the login form
gives, so the next request arrives as an anonymous one and the holder has to
sign in again -- where routes/auth.py's existing deactivation branch refuses
them properly. The revocation therefore takes effect at the holder's next click.

Failing 4 does NOT clear the session, and that difference is the whole of what
separates the two. A revoked account has had its access taken away and should
arrive at the next request as a stranger. A health worker during a maintenance
window has done nothing wrong and is not losing anything -- the system is
briefly closed and will open again -- so they keep their session, are shown a
page that says so, and are back where they were on their next click once it is
lifted. Clearing it would also be self-defeating: they would land on the login
form, sign in with correct credentials, and be turned away again by the branch
in routes/auth.py, which reads as the password having stopped working.

QUESTION 4 IS LAST ON PURPOSE. A deactivated account must still be revoked
during a maintenance window: the revocation is a security action and must not be
masked by a message saying the system is temporarily closed. Asking 3 before 4
means an account that has lost its access is told so, in the same words as
always, whatever the switch says.

WHY THIS COSTS LESS THAN IT DID BEFORE, NOT MORE
-------------------------------------------------
The obvious worry about a per-request account check is the query it adds to all
76 guarded routes. It adds none. It removes one.

Before this change a single guarded render already read the account row TWICE
from two different places, neither aware of the other:

    role_required()        -> get_current_user() -> SELECT * FROM users WHERE id = ?
    inject_role_context()  -> get_current_user() -> SELECT * FROM users WHERE id = ?

and database.connection.get_db() opens a NEW sqlite3 connection per call and
closes it after, so those were two full connect / query / close cycles. Measured
over 9 rounds of 400 calls, one cycle costs ~0.54-0.64 ms on this database while
the SELECT alone on an already-open connection costs ~0.027 ms -- so roughly 95%
of a lookup is the connection, not the read. The read itself is the cheapest in
the schema: the users table holds three rows and the plan is
`SEARCH users USING INTEGER PRIMARY KEY (rowid=?)`, a primary-key hit, not a scan.

get_current_user() now caches the row on flask.g for the life of the request, so
those two calls become one lookup and one dictionary read. The is_active check
reads a column on a row the request had already fetched: it issues no query of
its own and can issue none.

So a guarded request does strictly less database work after this change than
before it -- one connect/query/close cycle less, around half a millisecond. That
figure is deliberately stated as the saved lookup rather than as a faster page:
end-to-end request timing on a laptop is dominated by noise, and repeated runs of
the same nine screens disagreed by tens of milliseconds in both directions. The
lookup count is exact and reproducible; the wall clock is not, so no claim is
made from it.

Caching on `g` and not for longer is deliberate. A cache that outlived the
request would be a cache that has to be invalidated when an account changes, and
getting that wrong is how a deactivation check comes to pass a stale row -- the
exact defect this file exists to close. One request, one read, no invalidation
rule to get wrong.

WHY get_current_user() STILL RETURNS DEACTIVATED ACCOUNTS
----------------------------------------------------------
It would be tidy to have it return None for a deactivated account and let every
caller inherit the check. It would also be wrong twice over. inject_role_context()
would silently lose the sidebar name and role, so the refusal would render as a
logged-out-looking page instead of a redirect; and routes/report_export.py stamps
"produced by" on every workbook from this same call, which must name whoever
actually produced the file. This function stays a plain lookup. Deciding what a
deactivated account may do belongs to the guards below, where it can be seen.
"""
from functools import wraps

from flask import (
    flash, g, has_request_context, redirect, render_template, request, session,
    url_for,
)

from models.audit import ACTION_SESSION_REVOKED, MODULE_AUTH, log_action
from models.settings import maintenance_mode
from models.users import get_user_by_id
from utils.roles import normalize_role

# Sentinel for "this request has not looked the account up yet", kept distinct
# from None because None is a real answer -- it means the account row is gone,
# and that must be cached too rather than re-queried on every caller.
_UNSET = object()


def get_current_user():
    """The signed-in account row, read at most once per request.

    Returns a sqlite3.Row (which indexes but has no .get()), or None when there
    is no session or the account it names no longer exists.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None

    # Outside a request there is nowhere to cache and nothing to save; scripts
    # and shell sessions go straight to the database.
    if not has_request_context():
        return get_user_by_id(user_id)

    # Keyed on the id as well as cached, so a request that changes who is signed
    # in cannot be served the previous account. Nothing does that today -- the
    # login route clears the session and is not guarded -- but a cache whose
    # correctness rests on that staying true is a cache waiting to be wrong.
    cached = getattr(g, "_current_user", _UNSET)
    if cached is not _UNSET and getattr(g, "_current_user_id", None) == user_id:
        return cached

    user = get_user_by_id(user_id)
    g._current_user = user
    g._current_user_id = user_id
    return user


def current_role():
    """The signed-in account's canonical role, or "" when nobody is signed in.

    THE POINT OF THIS FUNCTION IS WHERE IT DOES NOT READ FROM.
    The role comes from the STORED account row, through get_current_user(), and
    falls back to the session's own copy only when there is no row to read -- the
    same order and the same reason inject_role_context() uses. Nothing a request
    carried is on any path into the answer: not a form field, not a query string,
    not a header. That is what lets it be the authority behind a permission
    rather than a convenience.

    It exists because clinical decisions have to be made per request from the
    role, away from the decorators that were previously the only thing asking:
    whether this person may write a diagnosis, whether they may read one that has
    been sealed (models/consultations.py can_diagnose / can_view_restricted), and
    whether they may declare a patient deceased (models/patients.py
    can_declare_death). All three are the Doctor's, and all are asked inside the
    shared view builders -- which serve two blueprints each, and the clinical
    floor's blueprint admits Health Center Staff and the Doctor alike -- so none
    of them can be read off the route's own guard.

    It costs no query. get_current_user() caches the row on flask.g for the life
    of the request, and every guarded request has already fetched it.
    """
    user = get_current_user()
    if user is not None:
        return normalize_role(user["role"])
    return normalize_role(session.get("role"))


# THE ONE RESPONSE EVERY REFUSAL RETURNS.
# Moved here from routes/auth.py, which still imports it, because a second caller
# appeared and the whole point of the function is that there is only one of it.
# Its own comment there said so: "A fourth outcome added later gets the identical
# response by construction rather than by remembering to." A session revoked
# mid-visit is that fourth outcome, and this is what "by construction" means --
# it returns the same response because it calls the same function, not because
# somebody copied the string correctly.
#
# So there is still no "your account has been deactivated" anywhere, and there
# must not be. At the login form that wording is an account-enumeration oracle;
# here it would be the same sentence reachable by anyone holding a stolen session
# cookie, and it would be the only place in the application where the deactivated
# state is stated out loud. The distinction is recorded in the audit trail, where
# only a signed-in Admin can read it.
#
# One sentence does say it, to one person, and it is not a refusal: an
# Administrator who deactivates their OWN account is told so on the login form
# after being signed out. end_session_after_self_deactivation() below says why
# that is not an oracle -- nobody can be shown it without having done it.
def refuse_credentials():
    flash("Invalid security credentials.")
    return redirect(url_for("auth.login", error="Invalid security credentials."))


def _log_revoked_session(user, ip_address):
    """Record that a live session was ended because its account is deactivated.

    Built to the shape routes/auth.py's three sign-in entries already use, and
    for the same reasons: read months later on its own, the sentence must say
    whose session ended and what access it had been carrying, without anyone
    having to open the users table -- a role changed afterwards must not rewrite
    the history of what this session could reach.

    Every value written comes from the STORED account row. Nothing the request
    carried, beyond its address, is on any path into this table.

    `user` None writes nothing. That is the same rule _log_refused_sign_in()
    follows for an unmatched username: audit_logs.user_id is NOT NULL and
    foreign-keyed to a real account, so a session naming an account that has been
    deleted outright has no row to be attributed to, and an audit trail must not
    invent one.

    ONE ENTRY PER REVOCATION, NOT ONE PER CLICK.
    Worth stating because a per-request check is exactly the shape of thing that
    fills a table. It does not, and the reason is structural rather than a rate
    limit: the caller clears the session in the same breath, so the request after
    this one carries no user_id, fails question 1 above and never reaches here.
    A revoked holder writes one row and then looks like an anonymous visitor.
    """
    if user is None:
        return None

    return log_action(
        user_id=user["id"],
        action=ACTION_SESSION_REVOKED,
        module=MODULE_AUTH,
        details=(
            f'Session ended for account "{user["username"]}" '
            f'({user["full_name"]}, {user["role"]}), from '
            f'{ip_address or "an address the request did not carry"}; the '
            "account was deactivated after this session had already started, so "
            "the session was cleared on its next guarded request rather than "
            "being left to run until the holder signed out. The person was told "
            "only that the credentials were invalid, the same wording the login "
            "form gives, so nothing was revealed about the account's status. "
            "Signing in again will be refused while the account stays deactivated"
        ),
        ip_address=ip_address,
    )


def _end_revoked_session(user):
    """Log the revocation, clear the session, and return the standard refusal.

    Order matters: the entry is written while the session is still readable and
    the account row is still in hand, and the session is cleared before the
    response is returned so nothing downstream can act on it.
    """
    _log_revoked_session(user, request.remote_addr if has_request_context() else None)
    session.clear()
    return refuse_credentials()


def _log_self_ended_session(user, ip_address):
    """Record that a session was ended because its holder deactivated themselves.

    The same action as _log_revoked_session(), because it is the same event --
    a session ended on a deactivated account -- and a reviewer filtering for it
    must find both. The sentence is different because two of that one's clauses
    would be false here: this session was not ended "on its next guarded
    request" but in the request that deactivated it, and the person was not told
    "only that the credentials were invalid".
    """
    if user is None:
        return None

    return log_action(
        user_id=user["id"],
        action=ACTION_SESSION_REVOKED,
        module=MODULE_AUTH,
        details=(
            f'Session ended for account "{user["username"]}" '
            f'({user["full_name"]}, {user["role"]}), from '
            f'{ip_address or "an address the request did not carry"}; the '
            "account holder deactivated their own account from User Management, "
            "so the session they did it from was ended in that same request. They "
            "were told on the login form that they had deactivated their own "
            "account and been signed out. That notice is carried only in this "
            "browser's signed session and is never shown in answer to a sign-in "
            "attempt. Signing in again will be refused while the account stays "
            "deactivated"
        ),
        ip_address=ip_address,
    )


def end_session_after_self_deactivation(notice):
    """Sign out an Administrator who has just deactivated their own account.

    THE ONE PLACE A SIGNED-OUT PERSON IS TOLD AN ACCOUNT IS DEACTIVATED, AND WHY
    THAT DOES NOT BREAK THE RULE ABOVE.
    refuse_credentials() is vague because the people who meet it have not proved
    who they are: a visitor at the login form, or a request carrying a session
    the account behind it no longer backs. The holder who switched their own
    account off has proved it -- the deactivation arrived in their live,
    Administrator session, through role_required("Admin") -- and the only thing
    the notice tells them is what they just did. It is not a response the login
    form can give to anyone:

    * it is flashed into the session cookie AFTER the session is cleared, so the
      cookie carries the notice and no identity, and it is signed with the
      application's secret key, so it cannot be written by anybody else;
    * the redirect carries no ?error=, because login.html prints that parameter
      as given and anyone could type it into the address bar;
    * it names no account.

    The session is cleared here, in the request that did the deactivation,
    rather than left for the guard to find on the next one. That is sooner than
    before, not later; and the guard still ends every other session this account
    has open, on each one's next click, with the generic refusal.
    """
    _log_self_ended_session(
        get_current_user(), request.remote_addr if has_request_context() else None
    )
    session.clear()
    flash(notice)
    return redirect(url_for("auth.login"))


def _maintenance_response(user):
    """The page a signed-in non-Administrator sees while the system is closed.

    NOTHING IS WRITTEN TO THE AUDIT TRAIL HERE, AND THAT IS DELIBERATE.
    _log_revoked_session() above writes one entry per revocation and can do so
    safely because the session is cleared in the same breath -- the holder's next
    request is anonymous and never reaches that code again. This branch clears
    nothing, so a blocked health worker clicking around a closed system would
    write a row per click and bury the trail under an event that is not news.

    The fact a reviewer actually needs is already recorded exactly once: who
    closed the system and when (ACTION_MAINTENANCE_ENABLED, in models/audit.py).
    Every refusal in the window follows from that one entry, and a row per click
    would add no information to it.

    503 rather than 200 or 403. From this person's side the service genuinely is
    temporarily unavailable, which is what 503 means and what 403 does not -- 403
    says "not for you", and this is "not now". It also stops any intermediary
    storing the page as though it were the screen that was asked for, which
    matters because the request that produced it is one the operator will repeat
    the moment the window ends. Retry-After is deliberately absent: nothing in
    this system knows when an administrator will switch it back, and a guessed
    number would be the sort of invented figure this project keeps deleting.
    """
    return render_template(
        "maintenance.html",
        blocked_name=(user["full_name"] if user is not None else ""),
        blocked_role=(user["role"] if user is not None else ""),
    ), 503


def _signed_in_account():
    """The account this request may act as, or the response refusing it.

    Returns (user_row, None) when the request may proceed and (None, response)
    when it may not. One function rather than a check in each decorator, so
    login_required and role_required cannot come to disagree about what counts as
    a valid session -- which they would, the first time one of them was edited.
    """
    if not session.get("user_id"):
        return None, redirect(url_for("auth.login"))

    user = get_current_user()

    # The account row is gone entirely. Rare -- nothing in the application
    # deletes an account -- but a session naming a row that no longer exists is
    # not a session that should keep working, and the old code let it through to
    # login_required's session-only check. Treated exactly as a deactivation,
    # minus the audit entry it cannot attribute.
    if user is None:
        return None, _end_revoked_session(None)

    # NOT NULL DEFAULT 1 in the schema, so the bool() is about SQLite handing
    # back an integer rather than about the value ever being absent. This is the
    # same expression routes/auth.py's login branch uses, asked of the same
    # column, at the other end of the session's life.
    if not bool(user["is_active"]):
        return None, _end_revoked_session(user)

    # MAINTENANCE MODE, ASKED ONCE HERE AND THEREFORE ASKED ON EVERY GUARDED
    # ROUTE IN THE APPLICATION.
    #
    # This is the reason the feature is four lines rather than a project. There
    # are 95 guarded routes and this function is the only way any of them is
    # reached, so the switch covers all of them by construction -- not because
    # somebody remembered to decorate them, and not by a list that a route added
    # next month could be left off. A new route inherits the restriction by
    # carrying @login_required or @role_required, which it must carry anyway.
    #
    # THE ADMINISTRATOR CANNOT BE LOCKED OUT BY THIS, AND NOT BECAUSE A GUARD
    # PREVENTS IT.
    # The condition below is `role is not admin`. For an Administrator it is
    # false, so there is no branch for them to fall down -- the lockout is not
    # something they are exempted from, it is something that cannot be expressed
    # about them. That is a stronger property than the last-administrator check
    # in models/users.py, which has to count rows inside a transaction to be
    # sure of its answer; this one needs no count and no transaction.
    #
    # And there is always somebody who can turn it off, which is the other half
    # of "no self-lockout". deactivate_user() and update_user() both refuse to
    # remove the last Administrator that can sign in, so an active Administrator
    # account always exists -- the account that could reopen the system cannot be
    # the one that was switched off or demoted while the system was closed.
    #
    # It costs no query. models/settings.py resolves the settings dict once per
    # request onto flask.g, and utils/context.py has already asked for it to draw
    # the page header, so by the time a guarded view runs this is a dict lookup.
    if maintenance_mode() and normalize_role(user["role"]) != "admin":
        return None, _maintenance_response(user)

    return user, None


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        _user, refusal = _signed_in_account()
        if refusal is not None:
            return refusal
        return view_func(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            user, refusal = _signed_in_account()
            if refusal is not None:
                return refusal
            normalized_user_role = normalize_role(user["role"])
            allowed = {normalize_role(item) for item in allowed_roles}
            if normalized_user_role not in allowed:
                return redirect(url_for("auth.dashboard"))
            return view_func(*args, **kwargs)

        # Left on the wrapper so the guard can be read as well as enforced.
        # User Management lists what each role may open (routes/user_views.py);
        # reading it off the decorator means that list is the access rule
        # itself rather than a second copy of it that could quietly disagree.
        wrapper.allowed_roles = tuple(allowed_roles)
        return wrapper

    return decorator
