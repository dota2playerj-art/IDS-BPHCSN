"""Context for Screen 11, User Management.

Built here rather than inline in routes/admin.py for the same reason every other
screen in this project has a `*_views.py`: the route stays a guard plus a
render, and the shape of the screen is one readable thing in one place.


WHAT THIS SCREEN CAN AND CANNOT SHOW
------------------------------------
The users table holds exactly the accounts that can sign in -- three of them,
seeded by models/users.py::seed_demo_users(), one per role the schema's CHECK
constraint allows. That is the whole roster, and it is what the table now shows.

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
the application ever writes them and they are NULL for all three accounts, so
the cell says the detail was never recorded rather than showing a number no one
entered.


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
from flask import current_app

from models.audit import get_last_logins
from models.users import get_all_users
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
        "Station and zone assignment is not stored. The users table has no "
        "column for it, so an account cannot be placed at the main health "
        "center, a purok zone or the dispensary."
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
    "invitations": (
        "There is no invitation or activation flow. An account is either allowed "
        "to sign in or deactivated; nothing records one waiting to be activated."
    ),
    "contact": (
        "The users table has email and phone columns, but nothing in the "
        "application writes to them and they are empty for every account. "
        "Contact details were never captured, so there is none to show."
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
    # Task 4 of the brief: flagged for a decision, deliberately not built.
    # Still true, and worth one added sentence now that the flag it names is
    # enforced. What is missing here is the button, not the mechanism -- and a
    # reader who has just been told access is revoked deserves to know where the
    # revoking currently happens.
    # "A deliberate decision rather than a missing button" is the argument for
    # not building it, and it is worth keeping where a maintainer will read it:
    # every write on this screen touches authentication -- password hashing, role
    # assignment, and the power to revoke a sign-in -- which is why it was left
    # out rather than left unfinished. The filename went with the argument.
    "write": (
        "Creating, editing and deactivating accounts is not built. The three "
        "accounts here are set up in the application's own code. Deactivation "
        "does work and is enforced at sign-in, but it is set by hand in the "
        "database, not from this screen."
    ),
    "reset_password": (
        "Password reset is not implemented. Hashes are written once by "
        "seed_demo_users(); nothing else in the project sets a password, and "
        "there is no email channel to send a reset through."
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


def _decorate(user, last_logins):
    """One account, plus the presentation the template would otherwise compute.

    `last_logins` is passed in rather than looked up per account: one grouped
    query for the whole roster, so adding a fourth account costs no extra round
    trip. A user_id absent from it has never signed in, and both the stored value
    and its rendering are set to None so the template tests one thing.

    The timestamp is rendered through display_timestamp(), the same filter
    Account Created two rows above it already uses, so the two cells in one panel
    cannot disagree about what time it is at the health center. audit_logs
    .created_at is a UTC CURRENT_TIMESTAMP exactly as users.created_at is.
    """
    role_class, role_icon = ROLE_STYLES.get(
        normalize_role(user["role"]), ("role-staff", "person")
    )
    contact = user.get("email") or user.get("phone")
    last_login = last_logins.get(user["id"])
    return {
        **user,
        "initials": _initials(user["full_name"]),
        "role_class": role_class,
        "role_icon": role_icon,
        "is_active": bool(user["is_active"]),
        "contact": contact,
        "screens": accessible_screens(user["role"]),
        "last_login": last_login,
        "last_login_display": display_timestamp(last_login) if last_login else None,
    }


def user_management_context():
    last_logins = get_last_logins()
    users = [_decorate(user, last_logins) for user in get_all_users()]
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
    }
