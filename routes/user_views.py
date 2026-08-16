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


ACCESS PERMISSIONS ARE READ OFF THE GUARDS
------------------------------------------
The permissions list under each account is not a description of the roles kept
in sync by hand. accessible_screens() walks the url_map and reads the roles each
view's role_required() decorator actually admits (utils/security.py leaves them
on the wrapper). The list is therefore the access rule itself, and it cannot
drift from the enforcement the way a hand-written list would.
"""
from flask import current_app

from models.users import get_all_users
from utils.roles import normalize_role

# The parts of this screen with no data source, and why. Keyed by the slot on
# the page so the template can look one up next to the thing it explains.
UNTRACKED = {
    "last_login": (
        "Sign-ins are not recorded. routes/auth.py checks the password and "
        "starts the session but never writes a row for it, so no account has a "
        "last-login time to show. Screen 12's Login Events card says the same."
    ),
    "assignment": (
        "Station and zone assignment is not stored. The users table has no "
        "column for it, so an account cannot be placed at the main health "
        "center, a purok zone or the dispensary."
    ),
    "invitations": (
        "There is no invitation or activation flow. An account exists and can "
        "sign in, or it does not exist. Nothing records an account awaiting "
        "activation, and no account is ever locked out -- there is no "
        "failed-login counter to lock one."
    ),
    "contact": (
        "The users table has email and phone columns, but nothing in the "
        "application writes to them and they are empty for every account. "
        "Contact details were never captured, so there is none to show."
    ),
    "search": (
        "Searching and filtering are not wired. With three accounts on one "
        "screen there is nothing to narrow down, so the controls the mockup "
        "drew would have filtered a list that is already complete."
    ),
    # "export" used to be here. Export is absent for one reason on every screen
    # that offers it, so the sentence moved to utils/unavailable.py and this
    # screen quotes the shared one -- two near-identical descriptions of one
    # missing library is exactly the drift that file exists to prevent.
    # Task 4 of the brief: flagged for a decision, deliberately not built.
    "write": (
        "Creating, editing and deactivating accounts is not implemented. "
        "Every write here touches authentication -- password hashing, role "
        "assignment, and the ability to revoke a sign-in -- so it is a "
        "deliberate decision rather than a missing button. The three seeded "
        "accounts are managed in models/users.py."
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


def _decorate(user):
    """One account, plus the presentation the template would otherwise compute."""
    role_class, role_icon = ROLE_STYLES.get(
        normalize_role(user["role"]), ("role-staff", "person")
    )
    contact = user.get("email") or user.get("phone")
    return {
        **user,
        "initials": _initials(user["full_name"]),
        "role_class": role_class,
        "role_icon": role_icon,
        "is_active": bool(user["is_active"]),
        "contact": contact,
        "screens": accessible_screens(user["role"]),
    }


def user_management_context():
    users = [_decorate(user) for user in get_all_users()]
    active = [user for user in users if user["is_active"]]

    return {
        "users": users,
        "total_users": len(users),
        "active_users": len(active),
        "inactive_users": len(users) - len(active),
        "roles_represented": len({user["role"] for user in users}),
        "untracked": UNTRACKED,
    }
