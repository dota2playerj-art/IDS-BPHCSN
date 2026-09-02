"""Context for Screen 11, User Management.

Built here rather than inline in routes/admin.py for the same reason every other
screen in this project has a `*_views.py`: the route stays a guard plus a
render, and the shape of the screen is one readable thing in one place.


WHAT THIS SCREEN CAN AND CANNOT SHOW
------------------------------------
The users table holds exactly the accounts that can sign in, and this table is
the whole of it. There were three for the project's whole life -- seeded by
models/users.py::seed_demo_users(), one per role the schema's CHECK constraint
allows -- and there are now as many as an Administrator has created, because
this screen creates them.


THE SCREEN WRITES NOW, AND THAT IS THE CHANGE THIS FILE'S NOTES TURN ON
------------------------------------------------------------------------
Everything below used to describe a screen that could only look. Add User is a
real form, and Deactivate and Reactivate are real buttons over the flag
routes/auth.py and utils/security.py have enforced since before either control
existed -- which is why wiring them was a matter of connecting a trigger to a
mechanism that was already proven rather than of building a mechanism.

Three properties of that write path are worth having in one place, because each
of them is a decision rather than an implementation detail:

* The administrator sets the new account's password directly, on the form. It is
  not emailed, because there is no email in this project to send it through and
  because a raw password sitting in an inbox is a credential in a place nobody
  controls. It is not auto-generated, because the person who has to tell the new
  holder what it is has to be able to read it. What follows from that is the
  sentence on the form: the value is never stored anywhere it can be read back,
  so nobody -- including the administrator who set it -- can look it up later.

* Password strength is enforced for the first time anywhere in this project. The
  rule and the reasoning behind every clause of it are in models/users.py; the
  exact rule is printed on the form itself, in the same words, so an
  administrator meets it before being rejected by it rather than after.

* The last active Administrator cannot be deactivated. The refusal lives in
  models.users.deactivate_user(), inside the transaction that does the write,
  and this file only words it. See the section note further down.

The screen was drawn as a staff directory for a much larger centre: eighteen
users across five roles (Nurse, Midwife, Pharmacist, Barangay Health Worker),
each with a station assignment, a mobile number, an invitation status and a
last-login time. None of those exist. Three of the five roles would be rejected
by the CHECK constraint if anyone tried to insert them, and the columns behind
assignment, invitation status and last login are simply not in the table.

So the invented roster is gone rather than trimmed. Every absence it papered
over is named in UNTRACKED below and printed next to the thing it explains,
following the rule Screen 03's Prenatal card set and Screens 10 and 12 follow:
a figure with no source reports its own absence, because an invented one gets
believed.

email and phone are the one middle case. Those columns do exist, but nothing in
the application ever writes them -- Add User does not ask for either, so an
account created here has them NULL exactly as the seeded ones do -- and the cell
says the detail was never recorded rather than showing a number no one entered.


LAST LOGIN IS REAL NOW, AND IT DOES NOT COME FROM A COLUMN
-----------------------------------------------------------
The note above used to list last login among the columns that "are simply not in
the table", and that half is still true -- users has no last_login column and has
not gained one. What changed is that it no longer needs one. routes/auth.py now
writes an audit entry for every successful sign-in, so the most recent one per
account is a MAX() over rows that already exist
(models/audit.py::get_last_logins()).

Deriving it rather than storing it is the better answer here and not merely the
cheaper one. A last_login column is a single value that can be overwritten, and
by the time anyone asks "when did this account last sign in, and from where"
there is nothing left to read. The audit trail keeps every sign-in, so the same
question is answerable in arbitrary depth, and the roster's column is simply the
newest of them. It also cannot disagree with Audit Logs' Login Events card: both
are counting the same rows.

An account that has never signed in is absent from that map, and the cell says so
rather than falling back to a date. That distinction matters on this screen more
than anywhere: an account with no sign-in in its history is either newly created
or unused, and both are things an administrator should be able to see at a
glance.


ACCESS PERMISSIONS ARE READ OFF THE GUARDS
------------------------------------------
The permissions list under each account is not a description of the roles kept
in sync by hand. accessible_screens() walks the url_map and reads the roles each
view's role_required() decorator actually admits (utils/security.py leaves them
on the wrapper). The list is therefore the access rule itself, and it cannot
drift from the enforcement the way a hand-written list would.
"""
from flask import current_app, session

from models.audit import (
    ACTION_USER_CREATED,
    ACTION_USER_DEACTIVATED,
    ACTION_USER_REACTIVATED,
    MODULE_USERS,
    get_last_logins,
    log_action,
)
from models.users import (
    ADMIN_ROLE,
    ALREADY_IN_THAT_STATE,
    LAST_ADMINISTRATOR,
    PASSWORD_RULE_TEXT,
    ROLE_CHOICES,
    count_active_admins,
    create_user,
    deactivate_user,
    get_all_users,
    get_user_by_id,
    reactivate_user,
    validate_new_user_form,
)
from utils.dates import day_start_utc, days_ago, display_timestamp, today
from utils.roles import normalize_role

# How recent "recently" is on the Signed In Recently card, in days, counting
# today. Seven so the card answers "has this account been used this week", which
# is the question a roster of a health center's staff is actually asked -- a
# figure over a longer window would report a team that has left as present.
RECENT_SIGN_IN_DAYS = 7

# The parts of this screen with no data source, and why. Keyed by the slot on
# the page so the template can look one up next to the thing it explains.
UNTRACKED = {
    # THERE IS NO "last_login" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said sign-ins are not recorded, and that routes/auth.py never writes a
    # row for one. That route writes one for every sign-in now, so the column and
    # the card that quoted this both read real timestamps, and a reason with
    # nothing quoting it is exactly the drift utils/unavailable.py exists to
    # prevent. It goes rather than sitting here describing a state the
    # application has left.
    #
    # What replaces it is not a reason at all but a cell that says "Never signed
    # in" -- which is a fact about the account rather than a gap in the system,
    # and is why it is written in the template rather than kept here.
    "assignment": (
        "Station and zone assignment is not stored. There is nowhere to record "
        "it, so an account cannot be placed at the main health center, a purok "
        "zone or the dispensary."
    ),
    # CORRECTED TWICE, AND THE SECOND TIME BECAUSE THE FIX MADE IT FALSE.
    # It first read "no account is ever locked out -- there is no failed-login
    # counter to lock one"; refused sign-ins started being recorded, so the
    # second half went, and the sentence became "nothing acts on that count".
    #
    # Then the login route learned to check is_active, and the opening claim went
    # too: "an account exists and can sign in, or it does not exist" was the
    # sentence this screen used to describe a two-state world, and there are
    # three states now. A deactivated account exists and cannot sign in. Leaving
    # that line would have been this file's own Deactivated card all over again --
    # a confident description of an access rule the application had stopped
    # following, on the very screen that shows the flag.
    # The screen number went, and so did the second half: that nothing acts on a
    # rising count of refused sign-ins is now said once, on the card that shows
    # the count, in audit_views.UNTRACKED["login_scope"]. It was being said in
    # three places.
    # STILL TRUE AFTER Add User, AND NOW SAYING WHY RATHER THAN ONLY WHAT.
    # A screen that creates accounts is exactly where a reader starts wondering
    # whether one of them might be sitting unactivated, so the reason names the
    # decision that rules it out: the administrator sets the password at
    # creation, which is the step an invitation would otherwise carry, so an
    # account is usable the moment it exists and there is no in-between state to
    # record.
    "invitations": (
        "There is no invitation or activation flow, and no account is ever "
        "waiting for one. The administrator sets the password when the account "
        "is created, so it can be signed in to immediately; an account is either "
        "allowed to sign in or deactivated, with nothing in between."
    ),
    "contact": (
        "An email address and a phone number can be held for an account, but "
        "nothing in this system ever fills them in and both are empty for every "
        "account. Contact details were never captured, so there is none to show."
    ),
    # THERE IS NO "search" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said searching and filtering are not wired, and that three accounts on
    # one screen leave nothing to narrow down. Both halves were true, and the
    # second is why the controls themselves went: the search box, the five-role
    # Advanced Filter and the "Showing 1-7 of 18 users" pager were removed from
    # user_management.html rather than left disabled with this sentence hung off
    # them, because a control that would filter an already-complete list is not
    # a gap to explain but a control that should not be drawn. What stands in
    # their place is a Jinja comment recording what the mockup carried and why
    # none of it survived.
    #
    # With nothing rendering it, the reason is drift waiting to happen -- the
    # same call made for "last_login" above -- so it goes with them.
    # "export" used to be here, then moved out, and is now gone from where it
    # moved to. It was a screen-specific sentence; it was replaced by a pointer
    # at utils/unavailable.py's shared `export`, because two near-identical
    # descriptions of one missing library is exactly the drift that file exists
    # to prevent. That shared reason has since been deleted as well -- Export on
    # this screen is two working links now (routes/roster_export.py), and this
    # screen's Export button carries no reason at all, because a control that
    # works does not need one.
    # THERE IS NO "write" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said "creating, editing and deactivating accounts is not built", that
    # the three accounts here are set up by the system itself, and that
    # deactivation "is set by hand in the database, not from this screen". It
    # hung off three controls: Add User, Edit User and Deactivate Account.
    #
    # Two of its three clauses are now false. Add User creates a real account
    # with a real hashed password, and Deactivate and Reactivate are working
    # buttons over the flag the login route and the per-request check already
    # enforced. A reason that denies a working control is the worst kind this
    # project keeps -- worse than a missing one, because it is read as a
    # description of the system by somebody who has no other way to check.
    #
    # So it goes the way "last_login", "search" and "export" went before it,
    # rather than being narrowed until it is a sentence about something else.
    # What survives is the one clause that is still true, and it is a different
    # claim about a different control, so it gets its own key and its own
    # wording below rather than inheriting the old one's.
    "edit_account": (
        "Editing an existing account is not built. A name, a username and a role "
        "are set when the account is created, and nothing can change them "
        "afterwards. Deactivating the account and creating a replacement is the "
        "only way round it today; the old account stays in the roster and keeps "
        "its history."
    ),
    # STILL TRUE, AND NOW SAYING WHERE THE ONE PASSWORD-SETTING MOMENT IS.
    # It said each password "is set once when the account is first created", and
    # that was written when nothing in the application could create one -- so the
    # sentence described a moment that had only ever happened at first boot. It
    # is a moment an administrator now lives through on this screen, so the
    # reason points at it: a reader who has just been told the password cannot be
    # reset is owed the fact that the one chance to set it has already gone by.
    "reset_password": (
        "Password reset is not built. A password is set once, by the "
        "administrator who creates the account, and nothing afterwards can "
        "change it -- not this screen, and not the account's own holder. It is "
        "stored only as a hash, so it cannot be looked up or recovered either, "
        "and there is no email channel to send a reset through. An account whose "
        "password has been forgotten has to be deactivated and replaced."
    ),
}

# Endpoint stems whose underscores do not title-case into anything a reader
# would recognise. Presentation only -- the set of screens itself is derived.
LABEL_OVERRIDES = {
    "dashboard": "Dashboard",
    "admin_dashboard": "Dashboard",
    "official_dashboard": "Dashboard",
    "sms_notifications": "SMS Notifications",
    "add_edit_medicine": "Add / Edit Medicine",
    "reports_analytics": "Reports & Analytics",
}

# Stripped before labelling, so the admin, staff and official spellings of one
# screen collapse to a single entry instead of listing three times.
_BLUEPRINT_PREFIXES = ("staff_", "official_")

ROLE_STYLES = {
    "admin": ("role-admin", "shield_person"),
    "health staff": ("role-staff", "medical_services"),
    "barangay official": ("role-official", "account_balance"),
}


def _screen_label(endpoint):
    stem = endpoint.split(".", 1)[-1]
    for prefix in _BLUEPRINT_PREFIXES:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    if stem in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[stem]
    return stem.replace("_", " ").title()


def accessible_screens(role):
    """The screens this role's own guards admit it to, read off the url_map.

    Only GET rules carry a screen a person opens, and only views wearing
    role_required() are role-scoped -- an unguarded view is reachable by
    everyone signed in and says nothing about this role, so it is left out.
    """
    normalized = normalize_role(role)
    labels = set()

    for rule in current_app.url_map.iter_rules():
        if rule.endpoint == "static" or "GET" not in rule.methods:
            continue
        view = current_app.view_functions.get(rule.endpoint)
        allowed = getattr(view, "allowed_roles", None)
        if not allowed:
            continue
        if normalized in {normalize_role(item) for item in allowed}:
            labels.add(_screen_label(rule.endpoint))

    return sorted(labels)


def _initials(full_name):
    parts = [word for word in str(full_name).replace(".", " ").split() if word]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _decorate(user, last_logins, active_admins, signed_in_id):
    """One account, plus the presentation the template would otherwise compute.

    `last_logins` is passed in rather than looked up per account: one grouped
    query for the whole roster, so adding a fourth account costs no extra round
    trip. A user_id absent from it has never signed in, and both the stored value
    and its rendering are set to None so the template tests one thing.

    The timestamp is rendered through display_timestamp(), the same filter
    Account Created two rows above it already uses, so the two cells in one panel
    cannot disagree about what time it is at the health center. audit_logs
    .created_at is a UTC CURRENT_TIMESTAMP exactly as users.created_at is.

    `active_admins` is passed in for the same reason `last_logins` is: it is one
    number for the whole roster, and asking models.users.is_last_active_admin()
    once per row would be one COUNT query per account to answer a question that
    has a single answer. `is_last_admin` below is derived from it rather than
    from a second query, so every row on one render agrees about how many
    administrators there are -- which matters, because that number decides which
    Deactivate button is offered and which is disabled.

    WHAT `is_last_admin` IS FOR, AND WHAT IT IS NOT.
    It disables a button and writes the sentence beside it. It is not the guard.
    The guard is in models.users.deactivate_user(), inside the transaction that
    performs the write, and it re-asks this question there -- because this answer
    was computed when the page was rendered and the page may have been sitting
    open while somebody else changed the roster. A screen that disabled the
    button and stopped there would be enforcing an access rule with a `disabled`
    attribute, which is enforcing nothing at all.
    """
    role_class, role_icon = ROLE_STYLES.get(
        normalize_role(user["role"]), ("role-staff", "person")
    )
    contact = user.get("email") or user.get("phone")
    last_login = last_logins.get(user["id"])
    is_active = bool(user["is_active"])
    return {
        **user,
        "initials": _initials(user["full_name"]),
        "role_class": role_class,
        "role_icon": role_icon,
        "is_active": is_active,
        "contact": contact,
        "screens": accessible_screens(user["role"]),
        "last_login": last_login,
        "last_login_display": display_timestamp(last_login) if last_login else None,
        "is_last_admin": (
            is_active and user["role"] == ADMIN_ROLE and active_admins <= 1
        ),
        # Whether this row is the account reading the screen. The dialog says so
        # before a signed-in administrator switches their own access off -- which
        # is allowed whenever another administrator remains, and which ends their
        # session on their next click (utils/security.py). A confirmation that did
        # not mention it would be a confirmation of the wrong thing.
        "is_self": signed_in_id is not None and user["id"] == signed_in_id,
    }


def user_management_context(add_form=None, add_errors=None, add_open=False):
    """Everything Screen 11 renders.

    The three `add_*` arguments carry the Add User dialog's state back after a
    submit that did not save -- its values and its field errors -- so the
    operator's entry survives the round trip exactly as Register Patient's and
    the booking dialog's do. `add_open` is what reopens the dialog on the next
    render; the template reads it and nothing else decides.

    The password fields are deliberately not among the values that come back.
    See _extract_add_user_form() below for why re-rendering a password into an
    HTML attribute is the one case where keeping what was typed is the wrong
    call.
    """
    last_logins = get_last_logins()
    # One count for the whole render. Every row's "is this the last
    # administrator" answer is derived from this single number, so no two rows on
    # one page can disagree about it.
    active_admins = count_active_admins()
    signed_in_id = session.get("user_id")
    users = [
        _decorate(user, last_logins, active_admins, signed_in_id)
        for user in get_all_users()
    ]
    active = [user for user in users if user["is_active"]]

    # The boundary for "recently", as the UTC text audit_logs.created_at holds,
    # so the comparison happens between two values in the same representation --
    # the same trick every clinic-local date filter in this project uses. Six
    # days back rather than seven: the window is the start of that day through
    # now, which is RECENT_SIGN_IN_DAYS calendar days counting today.
    recent_boundary = day_start_utc(days_ago(RECENT_SIGN_IN_DAYS - 1, today()))
    recent = [
        user for user in users
        if user["last_login"] and str(user["last_login"]) >= recent_boundary
    ]
    ever = [user for user in users if user["last_login"]]

    return {
        "users": users,
        "total_users": len(users),
        "active_users": len(active),
        "inactive_users": len(users) - len(active),
        "roles_represented": len({user["role"] for user in users}),
        "recent_sign_ins": len(recent),
        "recent_sign_in_days": RECENT_SIGN_IN_DAYS,
        "accounts_ever_signed_in": len(ever),
        "untracked": UNTRACKED,
        # How many accounts could still open this screen if every deactivation
        # offered below were carried out. Printed on the screen rather than only
        # used to disable a button, because "you cannot switch this one off" is a
        # rule an operator should be able to see the reason for before they meet
        # it -- and because the number is the whole of the reason.
        "active_admins": active_admins,
        # The Add User dialog: what to offer, what was typed, what was wrong with
        # it, and whether to reopen it.
        "role_choices": ROLE_CHOICES,
        "password_rule": PASSWORD_RULE_TEXT,
        "add_form": add_form or {},
        "add_errors": add_errors or {},
        "add_open": bool(add_open),
        # The two values the status form posts, named here so the template's
        # buttons and process_account_status() below read the same two strings
        # and cannot drift out of agreement.
        "deactivate_action": DEACTIVATE,
        "reactivate_action": REACTIVATE,
    }


# ---------------------------------------------------------------------------
# ADD USER, DEACTIVATE, REACTIVATE
# ---------------------------------------------------------------------------
# WHERE THE DECISIONS ARE, AND WHERE THE SENTENCES ARE.
# models/users.py decides. It holds the password rule, the username rule, the
# duplicate check and the refusal to switch off the last administrator, and it
# returns machine-readable outcomes -- an errors dict, or a (changed, code) pair.
# This file turns those outcomes into what a person reads: the flash text, the
# audit entry, and the state the reopened dialog comes back in.
#
# That split is the same one routes/auth.py makes between deciding a sign-in is
# refused and deciding what the login form says about it, and it is what lets the
# last-administrator guard be enforced in one place and explained in two -- on the
# disabled button before it is pressed, and in the refusal if a POST arrives that
# never saw the button.
#
# WHAT THE AUDIT ENTRIES SAY, AND WHY THEY NAME THE ADMINISTRATOR IN THE TEXT.
# Every other entry in this project names its subject in `details` and leaves the
# author to audit_logs.user_id, because on those entries the author and the
# subject are the same person. Here they are not: an account was changed BY
# somebody, and "who decided this account should exist" is the first question a
# reviewer asks. The acting administrator's own name, username and role are
# therefore spelled into the sentence as well as carried in user_id -- so a role
# changed later cannot rewrite the history of who held the power to do this.
#
# AND WHAT THEY NEVER SAY: THE PASSWORD.
# This is the one place in the application where a plaintext password is
# legitimately in hand, having just been typed by an administrator. Nothing about
# it reaches the audit table -- not the value, not a hash, not its length, not
# which rules it passed. process_create_user() below is not even passed the value
# separately from the form dict it hands straight to the model, and the details
# string it builds is composed from the STORED account row that comes back after
# the insert. The rule is routes/auth.py's, and it binds here for the same reason.

# The two things the status form can ask for. Constants rather than literals so
# the template's button values and the branch below cannot drift apart.
DEACTIVATE = "deactivate"
REACTIVATE = "reactivate"
STATUS_ACTIONS = (DEACTIVATE, REACTIVATE)

# The fields Add User submits, read into one dict the model validates and the
# template re-renders. The password pair is deliberately absent from this list --
# see _extract_add_user_form().
_ADD_USER_TEXT_FIELDS = ("full_name", "username", "role")


def _extract_add_user_form(form_data):
    """The submitted values, in the shape the model and the template share.

    THE TWO PASSWORD FIELDS ARE PULLED OUT SEPARATELY AND ARE NEVER PUT BACK.
    `values` is what the model validates; `redisplay` is what the reopened dialog
    is re-rendered from, and it carries the three text fields and nothing else. A
    form that bounces on a validation error therefore comes back with the name,
    the username and the role still filled in -- which is the whole point of
    keeping what was typed -- and with both password boxes empty.

    That is a deliberate exception to this project's "never throw away what the
    operator typed" rule, and it is the one place the rule should not hold. Every
    other field is re-rendered into a `value=` attribute, which puts it in the
    page source, in the browser's back/forward cache and in anything that scrapes
    the DOM. A password re-rendered that way would be a plaintext credential
    sitting in an HTML document, and it would be there because a validation error
    happened -- which is exactly when an administrator is most likely to leave the
    tab open and walk away. Retyping twelve characters is the cost, and it is
    small next to that.
    """
    values = {key: (form_data.get(key) or "").strip() for key in _ADD_USER_TEXT_FIELDS}
    redisplay = dict(values)
    values["password"] = form_data.get("password") or ""
    values["confirm_password"] = form_data.get("confirm_password") or ""
    return values, redisplay


def _account_phrase(user):
    """How an account is named in a flash message and in an audit entry.

    One function, so the sentence a person reads and the sentence the trail keeps
    identify the account the same way. `user` is a row or a dict; both index.
    """
    return f'"{user["username"]}" ({user["full_name"]}, {user["role"]})'


def _actor_phrase(actor):
    """The acting administrator, named in the entry rather than only in user_id.

    Falls back to a plain statement when the account row cannot be read, rather
    than to a name that was guessed at. log_action() will refuse the entry
    outright if there is no user_id at all, so this only covers the narrow case of
    an id that no longer resolves.
    """
    if actor is None:
        return "an administrator whose account row could not be read"
    return f'{actor["full_name"]} ("{actor["username"]}", {actor["role"]})'


def process_create_user(form_data, actor_id, ip_address=None):
    """Validate and create one account. Returns (new_user_id, context, message).

    The id and the context are mutually exclusive, the same contract
    process_add_edit_medicine() uses: an id means the caller should redirect and
    flash `message`, a context means it should re-render User Management with the
    dialog reopened on what was typed and the errors beside the fields.

    A duplicate username lands in the errors dict like any other field problem.
    That is the whole of the fix for it: before this existed the INSERT would have
    raised sqlite3.IntegrityError on the UNIQUE constraint and the operator would
    have been shown a 500 page for what is an ordinary, expected mistake.
    """
    values, redisplay = _extract_add_user_form(form_data)

    errors = validate_new_user_form(values)
    if errors:
        return None, user_management_context(
            add_form=redisplay, add_errors=errors, add_open=True
        ), None

    new_id = create_user(values)

    # Read back rather than reused from the form: the entry then describes the
    # row as it actually exists, and the role it names is the one the CHECK
    # constraint accepted rather than the one that was posted.
    created = get_user_by_id(new_id)
    actor = get_user_by_id(actor_id) if actor_id else None

    log_action(
        actor_id,
        ACTION_USER_CREATED,
        module=MODULE_USERS,
        details=(
            f"Account {_account_phrase(created)} created by {_actor_phrase(actor)}"
            "; the account is active and can sign in immediately, and the screens "
            f'its role opens are those listed for {created["role"]} on User '
            "Management; its password was set directly by the administrator at "
            "creation and is stored only as a salted hash -- the value itself is "
            "not recorded here, in this entry, or anywhere else in the system, by "
            "design; no email address or phone number was captured, because this "
            "form does not ask for either"
        ),
        ip_address=ip_address,
    )

    return new_id, None, (
        f'Account "{created["username"]}" created for {created["full_name"]} as '
        f'{created["role"]}. They can sign in now with the password you set. '
        "That password is not stored anywhere it can be read back — tell them "
        "what it is; nobody, including you, can look it up later."
    )


def process_account_status(form_data, actor_id, ip_address=None):
    """Deactivate or reactivate one account. Returns the message to flash.

    Everything is re-checked here because a POST can be made without ever loading
    the page: the requested action is validated against STATUS_ACTIONS, the id is
    validated as a number, and the account is read back out of the database rather
    than trusted from the form. The last-administrator refusal is not re-checked
    here at all -- models.users.deactivate_user() does it inside the transaction
    that performs the write, and this function only words the answer it gives.
    """
    action = (form_data.get("action") or "").strip()
    if action not in STATUS_ACTIONS:
        return "Choose whether to deactivate or reactivate the account."

    raw_id = (form_data.get("user_id") or "").strip()
    if not raw_id.isdigit():
        return "Select an account to change."

    user_id = int(raw_id)
    user = get_user_by_id(user_id)
    if user is None:
        return "That account could not be found."

    # Captured before the write, so the sentence describes the account as it was
    # named at the moment it was changed.
    phrase = _account_phrase(user)
    actor = get_user_by_id(actor_id) if actor_id else None
    acting_on_self = actor_id is not None and user_id == actor_id

    if action == DEACTIVATE:
        changed, refusal = deactivate_user(user_id)
        if not changed:
            if refusal == LAST_ADMINISTRATOR:
                # The specific refusal, stated as the reason rather than as a
                # rule. An operator who is told "not allowed" goes looking for a
                # way round it; one who is told what would break does not.
                return (
                    f'{user["full_name"]} cannot be deactivated: this is the last '
                    "Administrator account that can still sign in. Only an "
                    "Administrator can open User Management, so switching this one "
                    "off would leave nobody able to create an account, restore "
                    "one, or undo the change — the system could only be recovered "
                    "by editing the database file by hand. Create or reactivate "
                    "another Administrator first, and this account can then be "
                    "deactivated."
                )
            if refusal == ALREADY_IN_THAT_STATE:
                return f'No change. {user["full_name"]}’s account is already deactivated.'
            return "That account could not be found."

        log_action(
            actor_id,
            ACTION_USER_DEACTIVATED,
            module=MODULE_USERS,
            details=(
                f"Account {phrase} deactivated by {_actor_phrase(actor)}"
                + ("; the administrator deactivated their own account" if acting_on_self else "")
                + "; the account is refused at the login form from now on even "
                "when the password presented is correct, and a session it already "
                "had open is ended on its next guarded request rather than being "
                "left to run; nothing was deleted -- the account row, its stored "
                "password hash and every record it created are unchanged, and "
                "reactivating it restores the same credential; "
                f"{count_active_admins()} Administrator account"
                f"{'' if count_active_admins() == 1 else 's'} can still sign in"
            ),
            ip_address=ip_address,
        )

        message = (
            f'{user["full_name"]}’s account is deactivated. They are refused at '
            "the login form from now on, even with the correct password, and any "
            "session they already had open ends on their next click. Nothing was "
            "deleted — reactivating the account restores the same password."
        )
        if acting_on_self:
            message += (
                " You deactivated your own account, so you will be signed out on "
                "your next action and will not be able to sign back in."
            )
        return message

    changed, refusal = reactivate_user(user_id)
    if not changed:
        if refusal == ALREADY_IN_THAT_STATE:
            return f'No change. {user["full_name"]}’s account is already active.'
        return "That account could not be found."

    log_action(
        actor_id,
        ACTION_USER_REACTIVATED,
        module=MODULE_USERS,
        details=(
            f"Account {phrase} reactivated by {_actor_phrase(actor)}"
            "; it can sign in again from now on, using the password it held "
            "before it was deactivated -- no new password was set and none was "
            "needed, because deactivation never touched the stored hash; "
            f"{count_active_admins()} Administrator account"
            f"{'' if count_active_admins() == 1 else 's'} can now sign in"
        ),
        ip_address=ip_address,
    )

    return (
        f'{user["full_name"]}’s account is active again. They can sign in with '
        "the same password they had before it was deactivated — no new password "
        "was set, so if they have forgotten it there is no way to look it up or "
        "reset it from this screen."
    )
