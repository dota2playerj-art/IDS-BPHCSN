"""Context for Screen 11, User Management.

Built here rather than inline in routes/admin.py for the same reason every other
screen in this project has a `*_views.py`: the route stays a guard plus a
render, and the shape of the screen is one readable thing in one place.
"""
from flask import current_app, session

from models.audit import (
    ACTION_PASSWORD_RESET,
    ACTION_USER_CREATED,
    ACTION_USER_DEACTIVATED,
    ACTION_USER_EDITED,
    ACTION_USER_REACTIVATED,
    ACTION_USER_ROLE_CHANGED,
    MODULE_USERS,
    describe_changes,
    get_last_logins,
    log_action,
)
from models.users import (
    ADMIN_ROLE,
    ALREADY_IN_THAT_STATE,
    EDITABLE_USER_FIELDS,
    LAST_ADMINISTRATOR,
    PASSWORD_RULE_TEXT,
    ROLE_CHOICES,
    ROLE_LABELS,
    USER_EDIT_LABELS,
    count_active_admins,
    create_user,
    deactivate_user,
    get_all_users,
    get_user_by_id,
    reactivate_user,
    set_user_password,
    update_user,
    validate_new_user_form,
    validate_password_reset_form,
    validate_user_edit_form,
)
from utils.dates import day_start_utc, days_ago, display_timestamp, today
from utils.names import initials
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
        "Station and zone assignment is not stored, so an account cannot be placed at a purok "
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
        "There is no invitation flow. The administrator sets the password when the account is "
        "created, and it can sign in at once."
    ),
    "contact": (
        "Email and phone are not stored for accounts. Contact details were never captured."
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
    # THERE IS NO "edit_account" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said "editing an existing account is not built", that a name, a username
    # and a role are fixed at creation, and that deactivating the account and
    # creating a replacement was "the only way round it today". Two of those
    # three clauses are false now: Edit User changes a full name and a role, and
    # the replacement dance is no longer anybody's only option.
    #
    # The surviving clause -- that a username cannot be changed -- is not a gap
    # and does not belong in this dict at all. UNTRACKED collects the things this
    # system CANNOT do; a fixed username is a thing it REFUSES to do, for a
    # stated reason, exactly as the last-administrator rule is. Those are worded
    # beside the control that enforces them, which is where the field's own
    # helper text now says it, so a reader meets the rule at the box it governs
    # rather than in a tooltip on a button.
    #
    # So it goes the way "last_login", "search", "export" and "write" went before
    # it, rather than being narrowed until it describes something else. A reason
    # that denies a working control is the worst kind this project keeps.
    #
    # THERE IS NO "reset_password" ENTRY EITHER, FOR THE SAME REASON.
    # It said password reset "is not built", that nothing after creation could
    # change a password -- "not this screen, and not the account's own holder" --
    # and that a forgotten password meant deactivating the account and replacing
    # it. This screen does it now. Half of the old sentence is still true and is
    # still said: the holder cannot change their own, and a stored password
    # cannot be looked up or recovered. Both of those are printed inside the
    # Reset Password dialog, where they are answers to what an administrator is
    # about to do, rather than kept here as an explanation for a control that no
    # longer needs one.
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
    "doctor": ("role-doctor", "stethoscope"),
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


# THIS USED TO BE ITS OWN COPY OF THE RULE, AND IT DISAGREED WITH THE OTHER TWO.
# It skipped no honorifics at all, so the roster drew "KA" for the account the
# header and the audit trail both drew "JD" for -- one person, two answers, on
# screens an administrator reads side by side. It had disagreed before the
# persona was corrected too ("DR" here against "JR" there); the correction only
# made it visible. The rule is now utils/names.py, once, for all three.
def _initials(full_name):
    return initials(full_name, "?")


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


def user_management_context(
    add_form=None, add_errors=None, add_open=False,
    edit_state=None, reset_state=None,
):
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

    `edit_state` and `reset_state` are the same idea for the two per-account
    dialogs, and they are single objects rather than three arguments each because
    each of them has to say WHICH account it belongs to. Add User has one dialog
    on the page; Edit User and Reset Password have one per row, so the state must
    carry a user_id or the wrong person's dialog would spring open holding
    somebody else's correction. Their shape is built by _edit_state() and
    _reset_state() below and is the same shape
    routes/vaccination_correction_views.py::_reopen() returns.

    Only one of the three can be set on any render, because a POST arrives from
    one form.
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
        # The two per-account dialogs' state after a submit that did not save.
        # None on an ordinary render, which is what keeps every dialog closed.
        "edit_state": edit_state,
        "reset_state": reset_state,
        # The stored role strings mapped to the words the form shows, so a
        # refusal can name a role in the same language the dropdown offered it
        # in rather than in the value the database holds.
        "role_labels": ROLE_LABELS,
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

# What the login form says to an Administrator who has just deactivated their
# own account. It is the one sentence in the application that says an account is
# deactivated to someone who is no longer signed in, and it is safe for exactly
# one reason: nobody can see it without having done it. It is not a response the
# login form can give. It travels only as a flash in the signed session cookie of
# the browser that sent the deactivation, set by the route after it clears that
# session (utils/security.py end_session_after_self_deactivation), and never on
# the query string, where anyone could type it into the address bar. It names no
# account, so even on a shared screen it says nothing a visitor could not
# already see.
#
# Every clause is true at the moment it is shown. "Another Administrator" is
# guaranteed: deactivate_user() refuses the last one, so this can only be
# reached while a second active Administrator exists. "The same password" is
# what reactivate_user() restores, because deactivation never touches the hash.
SELF_DEACTIVATION_NOTICE = (
    "You deactivated your own account and have been signed out. Another "
    "Administrator must reactivate it before you can sign in again."
)

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
    return f'"{user["username"]}" ({user["full_name"]})'


def _actor_phrase(actor):
    """The acting administrator, named in the entry rather than only in user_id.

    Falls back to a plain statement when the account row cannot be read, rather
    than to a name that was guessed at. log_action() will refuse the entry
    outright if there is no user_id at all, so this only covers the narrow case of
    an id that no longer resolves.
    """
    if actor is None:
        return "an administrator whose account row could not be read"
    return actor["full_name"]


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
            f'; role {created["role"]}; the password is not recorded'
        ),
        ip_address=ip_address,
    )

    return new_id, None, (
        f'Account "{created["username"]}" created for {created["full_name"]} as '
        f'{created["role"]}. The password cannot be looked up later. '
        "The user must change this password the first time they sign in."
    )


def process_account_status(form_data, actor_id, ip_address=None):
    """Deactivate or reactivate one account. Returns (message, deactivated_self).

    `deactivated_self` is True in one case only: the acting Administrator has
    just deactivated their own account, and the write succeeded. The message is
    then SELF_DEACTIVATION_NOTICE, which is meant for the login form, and the
    caller must end the session it is running in rather than flash it over User
    Management -- a page the person can no longer open. Every other outcome,
    refusals included, is False with a sentence for User Management.

    Everything is re-checked here because a POST can be made without ever loading
    the page: the requested action is validated against STATUS_ACTIONS, the id is
    validated as a number, and the account is read back out of the database rather
    than trusted from the form. The last-administrator refusal is not re-checked
    here at all -- models.users.deactivate_user() does it inside the transaction
    that performs the write, and this function only words the answer it gives.
    """
    action = (form_data.get("action") or "").strip()
    if action not in STATUS_ACTIONS:
        return "Choose whether to deactivate or reactivate the account.", False

    raw_id = (form_data.get("user_id") or "").strip()
    if not raw_id.isdigit():
        return "Select an account to change.", False

    user_id = int(raw_id)
    user = get_user_by_id(user_id)
    if user is None:
        return "That account could not be found.", False

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
                    "Administrator who can sign in. Create or reactivate another "
                    "Administrator first.",
                    False,
                )
            if refusal == ALREADY_IN_THAT_STATE:
                return f'No change. {user["full_name"]}’s account is already deactivated.', False
            return "That account could not be found.", False

        log_action(
            actor_id,
            ACTION_USER_DEACTIVATED,
            module=MODULE_USERS,
            details=(
                f"Account {phrase} deactivated by {_actor_phrase(actor)}"
                + (
                    "; their own account, so their session ended"
                    if acting_on_self else ""
                )
                + "; sign-in is now refused; "
                f"{count_active_admins()} Administrator account"
                f"{'' if count_active_admins() == 1 else 's'} can still sign in"
            ),
            ip_address=ip_address,
        )

        # Their own account: the sentence below would be flashed over User
        # Management, which this person can no longer open. It used to be, with a
        # clause saying they would be signed out "on your next action" -- and the
        # redirect was that action, so the guard cleared the session, the flash
        # went with it, and the login form said "Invalid security credentials."
        # instead. The caller now ends the session itself and shows this notice.
        if acting_on_self:
            return SELF_DEACTIVATION_NOTICE, True

        return (
            f'{user["full_name"]}’s account is deactivated. They cannot sign in, '
            "and any open session ends at their next click. Nothing was deleted.",
            False,
        )

    changed, refusal = reactivate_user(user_id)
    if not changed:
        if refusal == ALREADY_IN_THAT_STATE:
            return f'No change. {user["full_name"]}’s account is already active.', False
        return "That account could not be found.", False

    log_action(
        actor_id,
        ACTION_USER_REACTIVATED,
        module=MODULE_USERS,
        details=(
            f"Account {phrase} reactivated by {_actor_phrase(actor)}"
            "; it keeps its old password; "
            f"{count_active_admins()} Administrator account"
            f"{'' if count_active_admins() == 1 else 's'} can now sign in"
        ),
        ip_address=ip_address,
    )

    return (
        f'{user["full_name"]}’s account is active again, with its old password. '
        "If they forgot it, use Reset Password.",
        False,
    )


# ---------------------------------------------------------------------------
# EDIT USER, AND RESET PASSWORD
# ---------------------------------------------------------------------------
# THE SPLIT IS THE SAME SPLIT. models/users.py decides -- what a name and a role
# may be, and whether demoting this particular account would lock everybody out
# -- and returns an errors dict or a (before, after, refusal) triple. This file
# turns that into what a person reads and what the trail keeps.
#
# WHY BOTH OF THESE REOPEN A DIALOG WHERE DEACTIVATE FLASHES.
# process_account_status() answers every outcome, refusals included, with a
# sentence above a closed page, and that is right for it: a deactivation is a
# button press carrying no typing, so there is nothing to preserve and nothing
# to correct in place. These two carry typing. An edit refused because it would
# demote the last Administrator may also hold a name correction that was
# perfectly good, and a reset refused for a weak password has had twelve
# characters entered twice. Throwing either away and explaining it from the top
# of the page is the failure the whole form-redisplay pass in this project
# existed to remove, so neither is built that way.
#
# WHAT THE ENTRIES SAY, AND WHAT THEY STILL NEVER SAY.
# A role change spells out the role held before and the role held after, in one
# sentence, so the pair can be read without joining this entry to an earlier one
# -- which is the whole of what makes "elevate, act, revert" visible in a list.
# The acting administrator is named in the text as well as carried in user_id,
# for the reason ACTION_USER_CREATED's entries name them: the author and the
# subject are two different people here.
#
# And the password is not in any of it. Not the value, not a hash, not its
# length, not which rules it passed or failed. process_reset_password() below
# does not pass the plaintext to anything except the validator and the model,
# and the entry it writes is composed from the account row rather than from the
# form.

# The two fields Edit User posts besides the account it names.
_EDIT_USER_FIELDS = EDITABLE_USER_FIELDS


def _resolve_target(form_data):
    """The account a per-account dialog was submitted against. Returns (id, row).

    (None, None) means the form did not name an account this system holds. Both
    dialogs are rendered per row with the id in a hidden field, so reaching that
    branch means a POST that did not come from this page -- which is exactly the
    request that must not be trusted, and is why the row is read back out of the
    database rather than taken from the form.
    """
    raw_id = (form_data.get("user_id") or "").strip()
    if not raw_id.isdigit():
        return None, None
    user_id = int(raw_id)
    return user_id, get_user_by_id(user_id)


def _edit_state(user_id, values, errors, banner=None):
    """The Edit User dialog's state after a submit that did not save.

    `banner` is the sentence at the top of the reopened dialog when the refusal
    is about the edit as a whole rather than about one box -- the
    last-administrator refusal is the only one, and it needs the room to explain
    what would have broken. Field errors carry their own wording next to the
    field and leave this None.
    """
    return {
        "open": True,
        "user_id": user_id,
        "errors": errors,
        "banner": banner,
        "form": {field: values.get(field, "") for field in _EDIT_USER_FIELDS},
    }


def _reset_state(user_id, errors):
    """The Reset Password dialog's state after a submit that did not save.

    There is no `form` on this one, and its absence is the point. Both boxes hold
    a password, and _extract_add_user_form() states in full why a password is the
    one value this project does not re-render into a `value=` attribute: it would
    put a working credential into the page source and the browser's history cache,
    at the exact moment -- a rejected submit -- when the tab is most likely to be
    left open. The dialog comes back naming the account and carrying the error;
    both boxes are empty.
    """
    return {
        "open": True,
        "user_id": user_id,
        "errors": errors,
    }


def _role_phrase(role):
    """A stored role string, in the words the form offered it in."""
    return ROLE_LABELS.get(role, role)


def process_edit_user(form_data, actor_id, ip_address=None):
    """Change one account's full name and role. Returns (user_id, context, message).

    The same three-way contract process_create_user() uses: a user_id means the
    caller redirects and flashes `message`, a context means it re-renders User
    Management with this account's dialog reopened on what was typed.

    NOTHING ABOUT THE USERNAME IS READ FROM THIS FORM. `values` is built from
    EDITABLE_USER_FIELDS, which does not contain it, so a posted username is not
    validated, not rejected and not written -- there is simply no path from the
    request to that column. The template renders the box read-only; this is why
    that is a statement of the rule rather than the whole of it.

    A SAVE THAT CHANGED NOTHING IS NOT AN EVENT. describe_changes() reports which
    of the two fields actually moved, and when neither did the answer is a flash
    saying so, with no audit entry written. The alternative -- an entry reading
    "Full name: 'Arnel Manalastas' -> 'Arnel Manalastas'" -- is the kind of row that
    makes a trail harder to read rather than more complete.
    """
    user_id, user = _resolve_target(form_data)
    if user is None:
        return None, None, "That account could not be found."

    values = {
        field: (form_data.get(field) or "").strip() for field in _EDIT_USER_FIELDS
    }

    errors = validate_user_edit_form(values)
    if errors:
        return None, user_management_context(
            edit_state=_edit_state(user_id, values, errors)
        ), None

    before, after, refusal = update_user(user_id, values)

    if before is None:
        if refusal == LAST_ADMINISTRATOR:
            # The refusal is about the role box, so it is worded on the role box,
            # and the reason it would matter is in the banner above -- the same
            # division the deactivation refusal makes between "this is not
            # allowed" and "here is what it would break". Everything typed comes
            # back, including a name correction that was never the problem.
            return None, user_management_context(edit_state=_edit_state(
                user_id,
                values,
                {"role": (
                    f'{user["full_name"]} must stay an Administrator for now. '
                    "Leave the role as Administrator to save the rest of this "
                    "edit."
                )},
                banner=(
                    f'{user["full_name"]}’s role cannot be changed: this is the '
                    "last Administrator who can sign in. Create another "
                    "Administrator first."
                ),
            )), None
        return None, None, "That account could not be found."

    summary, changed = describe_changes(before, after, USER_EDIT_LABELS)
    if not changed:
        return user_id, None, (
            f'No change. {after["full_name"]}’s name and role are already what '
            "you entered."
        )

    actor = get_user_by_id(actor_id) if actor_id else None
    role_changed = "role" in changed
    acting_on_self = actor_id is not None and user_id == actor_id

    # A role change names the entry even when the name moved in the same submit.
    # The more serious of the two facts is the one a reviewer scans for; both are
    # in `details` either way.
    if role_changed:
        role_sentence = (
            "; ROLE CHANGED"
            + (
                "; their own access moved"
                if acting_on_self
                else ""
            )
            + f'; {count_active_admins()} Administrator account'
            f'{"" if count_active_admins() == 1 else "s"} can sign in'
        )
    else:
        role_sentence = ""

    log_action(
        actor_id,
        ACTION_USER_ROLE_CHANGED if role_changed else ACTION_USER_EDITED,
        module=MODULE_USERS,
        details=(
            f'Account "{after["username"]}" edited by {_actor_phrase(actor)}; '
            f"{summary}"
            + role_sentence
        ),
        ip_address=ip_address,
    )

    message = f'{after["full_name"]}’s account has been updated. {summary}.'
    if role_changed:
        message += (
            f' The role change takes effect now: "{after["username"]}" can open '
            f'only the screens listed for {_role_phrase(after["role"])}. It is '
            "recorded in the audit trail."
        )
        if acting_on_self:
            message += (
                " You changed your own role, so your own access has changed with "
                "it and this screen may no longer be open to you."
            )
    else:
        message += " Their role, username and password are unchanged."
    return user_id, None, message


def process_reset_password(form_data, actor_id, ip_address=None):
    """Set a new password on one account. Returns (user_id, context, message).

    The same three-way contract as process_edit_user() above.

    THE ACCOUNT'S OWN STORED NAME AND USERNAME ARE WHAT THE STRENGTH RULE READS.
    They are taken from the row this function looked up, not from the request, so
    the two clauses that refuse a password for containing the username or a part
    of the person's name are checked against the real account. A form that could
    supply its own name alongside the password would let "bhwmanalastas2026!!" through
    for the account named bhwmanalastas by claiming the person is called something
    else.

    THE OLD PASSWORD IS NOT ASKED FOR AND IS NOT CHECKED. models/users.py's module
    note gives the reasoning in full: an administrator resetting an account does
    not know it, cannot be made to know it -- it is a one-way hash -- and
    demanding it would refuse every legitimate reset while stopping nothing. What
    stands in its place is the route's role_required("Admin") guard and this
    function's audit entry.
    """
    user_id, user = _resolve_target(form_data)
    if user is None:
        return None, None, "That account could not be found."

    values = {
        "password": form_data.get("password") or "",
        "confirm_password": form_data.get("confirm_password") or "",
    }

    errors = validate_password_reset_form(
        values, user["username"], user["full_name"]
    )
    if errors:
        return None, user_management_context(
            reset_state=_reset_state(user_id, errors)
        ), None

    # must_change=True: the person must set their own at the next sign-in.
    changed, refusal = set_user_password(user_id, values["password"], must_change=True)
    if not changed:
        return None, None, "That account could not be found."

    actor = get_user_by_id(actor_id) if actor_id else None
    acting_on_self = actor_id is not None and user_id == actor_id

    # Composed from the stored account row. The plaintext was handed to the
    # validator and the model and reaches nothing else -- see the section note.
    log_action(
        actor_id,
        ACTION_PASSWORD_RESET,
        module=MODULE_USERS,
        details=(
            f"Password for account {_account_phrase(user)} reset by "
            f"{_actor_phrase(actor)}"
            + (
                "; the administrator reset the password on their own account"
                if acting_on_self
                else ""
            )
            + "; old password stopped working; new value not recorded"
        ),
        ip_address=ip_address,
    )

    message = (
        f'{user["full_name"]}’s password has been reset. The new password '
        "cannot be looked up later. "
        "The user must change this password the first time they sign in."
    )
    if acting_on_self:
        message += (
            " This is the account you are signed in as. Your current session "
            "stays open, but the new password is what you will need next time."
        )
    return user_id, None, message
