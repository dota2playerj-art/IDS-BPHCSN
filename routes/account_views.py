"""My Account: the signed-in person's own details, and their own password.

WHY THIS EXISTS AT ALL
----------------------
Until now the only way any password in this system could change was an
Administrator opening User Management and resetting it. That is the right tool
for the situation it was built for -- somebody has forgotten theirs, or an
account is being handed over -- and it is the wrong and only tool for the
ordinary one: a health worker who wants to change a password they still know.
With no self-service path they have to ask the Administrator, tell them the new
password out loud or over the phone so it can be typed in for them, and end up
with a credential a second person has seen. The feature that is supposed to
protect the account is the thing that leaks it.

So this screen asks for the current password and the administrator's reset does
not, and those two facts are the same decision seen from both ends. See
models/users.py's section note: a reset exists precisely BECAUSE the old password
is unavailable, and a change exists precisely because it is available and is the
only thing that proves the person at the keyboard is the account holder rather
than whoever found the machine still signed in.

WHAT IS DELIBERATELY NOT ON THIS SCREEN
----------------------------------------
The name and the role are printed and are not editable, and neither is the
username. That is the same boundary User Management already draws, kept from the
other side: full_name and role are EDITABLE_USER_FIELDS and belong to the
Administrator, because a role a person can raise on themselves is not a role, and
a name the trail attributes actions to should not be changeable by the person the
trail is about. The username is not editable by anybody at all -- see
models/users.py on why it is fixed for the life of the account.

There is no photograph, no contact detail and no preference of any kind. Nothing
in this application stores or reads any of those (users.email and users.phone are
never written -- User Management says so on its own face), so a box for one would
be a control for a feature that does not exist, which is the thing this project
keeps deleting rather than adding.

NEITHER FUNCTION BELOW TAKES AN ACCOUNT TO ACT ON, AND THAT IS THE GUARD
-------------------------------------------------------------------------
routes/user_views.py has _resolve_target(), which reads a user_id out of the form
and looks the row up, because those dialogs are rendered per row and genuinely
act on somebody else. Nothing here does. Both functions call get_current_user()
and act on whatever comes back, so there is no parameter, no hidden field and no
path of any kind by which a request could name a different account. A posted
`user_id` is not rejected here -- it is never read, which is the stronger answer,
and it is the same answer validate_user_edit_form() gives a posted username.

That is also why this needs no role check. It is available to the Administrator,
to Health Center Staff and to the Barangay Official identically, because what it
can reach is not a role's worth of screens -- it is one row, the caller's own.
@login_required is the whole of the requirement: be somebody, and this acts on
you.

WHAT A REFUSED SUBMIT DOES
--------------------------
It re-renders this same screen with the error beside the box it belongs to, at
200, exactly as Add User and Register Patient do -- the project's form-redisplay
standard, and this feature is built to it from the start rather than corrected
into it later. Nothing typed is written back into the page, and here that costs
nothing to explain: all three boxes hold a password, and re-rendering a password
into a `value=` attribute is the one case this project refuses outright. See
routes/user_views.py::_reset_state(). All three come back empty, and the banner
at the top says so, so an empty box after a refusal reads as intended rather than
as the screen having lost what was typed.
"""
from models.audit import ACTION_PASSWORD_CHANGED_SELF, MODULE_AUTH, log_action
from models.users import (
    PASSWORD_RULE_TEXT,
    ROLE_LABELS,
    set_user_password,
    validate_password_change_form,
    verify_user_password,
)
from utils.security import get_current_user

# What an entry says when the request carried no address. The same sentence
# routes/auth.py writes for the same absence, so a reader meeting it under
# Authentication does not have to work out whether two differently-worded
# blanks mean two different things.
_NO_ADDRESS = "an address the request did not carry"

# The message that goes on the current-password box when what was typed is not
# the account's password. Named because two things have to agree about it: the
# refusal itself, and the fact -- asserted in the verification suite -- that a
# wrong current password produces a FIELD error on this screen rather than a
# flash on another one.
#
# IT SAYS WHAT WENT WRONG, AND THAT IS SAFE HERE IN A WAY IT IS NOT AT THE LOGIN
# FORM. utils/security.py::refuse_credentials() is deliberately vague ("Invalid
# security credentials") because at the login form a precise answer is an
# account-enumeration oracle -- it would sort guessed usernames into real and
# fictional. Nothing is revealed here. The account is already known: the reader
# is signed in as it, its username and role are printed above this very box, and
# the only thing the message confirms is something the person can see on the
# screen in front of them.
WRONG_CURRENT_PASSWORD = (
    "That is not the password this account signs in with. Type your current "
    "password, not the new one you want."
)


def _address_phrase(ip_address):
    return ip_address or _NO_ADDRESS


def _role_label(role):
    """A stored role string in the words the rest of the system shows it in."""
    return ROLE_LABELS.get(role, role)


def my_account_context(change_errors=None):
    """Everything the My Account screen renders.

    `change_errors` is the Change Password form's state after a submit that did
    not save -- a dict keyed by field, the same shape every other form in this
    project hands back. There is no companion `form` dict holding what was typed,
    and its absence is the point rather than an omission: all three boxes hold a
    password. routes/user_views.py::_reset_state() states the reason in full.

    The three account details are read from the signed-in row on every render
    rather than from the session, so a name or a role an Administrator changed
    while this person was signed in shows here on their next click rather than
    at their next sign-in. The session holds a copy of both, written once at
    login; this screen is specifically the place someone comes to read what their
    account actually says, so it reads the account.
    """
    user = get_current_user()

    return {
        # None only if the account vanished between the guard and here, which
        # nothing in this application can do -- there is no delete. The template
        # is written so it renders as blanks rather than raising if it ever does.
        "account": None if user is None else {
            "full_name": user["full_name"],
            "username": user["username"],
            "role": user["role"],
            "role_label": _role_label(user["role"]),
        },
        # The same sentence the Add User and Reset Password forms print, from the
        # same constant, because it is the same rule -- one
        # check_password_strength() serves all three, so a password refused on
        # one of those screens is refused on this one.
        "password_rule": PASSWORD_RULE_TEXT,
        "change_errors": change_errors or {},
    }


def process_password_change(form_data, ip_address=None):
    """Change the signed-in account's own password. Returns (changed, context, message).

    The three-way contract routes/user_views.py uses: `changed` true means the
    caller flashes `message` and redirects, a `context` means it re-renders this
    screen with the errors on the form, and neither means the caller flashes
    `message` above a fresh render.

    THE CURRENT PASSWORD IS VERIFIED BEFORE ANYTHING IS WRITTEN, AND A WRONG ONE
    WRITES NOTHING AT ALL. Not the password, and not an audit entry either -- see
    the note below the verification. verify_user_password() compares against the
    stored hash with the same check_password_hash() the login form uses, so
    "the password you sign in with" is literally what that box is asking for.

    THE STRENGTH RULE READS THE STORED USERNAME AND NAME, not anything the form
    carried, for the reason process_reset_password() gives: the two clauses that
    refuse a password for containing the username or a part of the person's own
    name have to be compared against the real account.

    NEITHER PASSWORD REACHES THE AUDIT TRAIL. The current one is passed to
    verify_user_password() and to one string comparison; the new one is passed to
    check_password_strength() and to set_user_password(). Both are local to this
    function and neither is an argument to log_action(): the entry is composed
    from the stored account row, exactly as every other credential entry in this
    project is.
    """
    user = get_current_user()
    if user is None:
        # Unreachable behind @login_required, which refuses a session naming a
        # row that is not there before a view runs. Answered rather than left to
        # raise, because a self-service screen that 500s is worse than one that
        # says it could not read the account.
        return False, None, "Your account could not be read. Sign in again."

    # NOT STRIPPED. A password may legitimately begin or end with a space -- the
    # strength rule counts "a symbol or a space" as one of its four character
    # kinds and says so on the form -- so trimming here would quietly refuse a
    # password the rule allows, and would refuse it at the CURRENT box as well,
    # where the failure would read as the person having forgotten their own
    # password. Emptiness is still judged on the stripped value, inside
    # validate_password_change_form(), so a box holding only spaces is empty.
    values = {
        "current_password": form_data.get("current_password") or "",
        "new_password": form_data.get("new_password") or "",
        "confirm_new_password": form_data.get("confirm_new_password") or "",
    }

    errors = validate_password_change_form(
        values, user["username"], user["full_name"]
    )

    # Asked only when the box holds something -- an empty one already carries its
    # own "type the password you sign in with now", and replacing that with "that
    # is not the password" would tell somebody who typed nothing that what they
    # typed was wrong.
    #
    # Asked ALONGSIDE the other errors rather than instead of them, which is the
    # same choice validate_new_user_form() makes about its own fields: a submit
    # with a mistyped current password AND a weak new one reports both at once.
    # It costs nothing to do so -- the account is already known, so unlike the
    # login form there is nothing here that a fuller answer could reveal -- and
    # the alternative makes somebody retype three passwords to discover the
    # second problem.
    if values["current_password"] and "current_password" not in errors:
        if not verify_user_password(user["id"], values["current_password"]):
            errors["current_password"] = WRONG_CURRENT_PASSWORD

    if errors:
        return False, my_account_context(change_errors=errors), None

    # Knowable only because the holder typed both, and NOT a rule. Nothing in
    # this system remembers a previous password -- Settings' Password Policy pane
    # says so out loud, in models/users.py::password_policy()'s `not_enforced` --
    # so refusing this would be a reuse check the rest of the application does
    # not have and could not perform on any other path. What it changes is what
    # the outcome SAYS: re-saving the same password is not a lie to correct, but
    # reporting "the old one stopped working" about a password that is still the
    # one in use would be.
    unchanged_value = values["new_password"] == values["current_password"]

    changed, _refusal = set_user_password(user["id"], values["new_password"])
    if not changed:
        return False, None, "Your account could not be read. Sign in again."

    # WHY THE ENTRY SPELLS OUT THAT THE HOLDER DID THIS THEMSELVES.
    # The row it most needs to be told apart from is ACTION_PASSWORD_RESET, which
    # is written when an administrator sets a password on an account without its
    # holder taking part. Both leave a new hash in the same column, and a
    # reviewer asking "was this account taken over, or did its holder simply
    # change their password" is asking which of the two happened. So the phrase
    # differs, the module differs (see models/audit.py), and the sentence itself
    # names the verification that only this path can perform.
    log_action(
        user["id"],
        ACTION_PASSWORD_CHANGED_SELF,
        module=MODULE_AUTH,
        details=(
            f'{user["full_name"]} changed the password on their own account '
            f'"{user["username"]}" ({user["role"]}), from '
            f"{_address_phrase(ip_address)}; the password the account was already "
            "signing in with was typed on the form and verified against the "
            "stored hash before anything was written, so this was done by the "
            "account holder and not on their behalf -- an administrator "
            "replacing this account's password is a different entry, which names "
            "the administrator who did it"
            + (
                "; the new password submitted was the same value the account was "
                "already using, so the stored hash was replaced but the "
                "credential itself is unchanged and the account signs in with "
                "exactly what it did before"
                if unchanged_value else
                "; the previous password stopped working the moment this was "
                "saved and the account signs in with the new one from now on"
            )
            + "; the new value met the same strength rule a new account's "
            "password must meet and is stored only as a salted hash -- neither "
            "it nor the current password typed to prove identity is recorded "
            "here, in this entry, or anywhere else in the system, by design; "
            "nothing else about the account changed -- its username, name, role "
            "and whether it may sign in are exactly as they were; the session "
            "this was changed from stays open, because a Flask session names an "
            "account rather than carrying its credential"
        ),
        ip_address=ip_address,
    )

    if unchanged_value:
        message = (
            "Your password has been saved, and it is the same password you were "
            "already using — the new one you typed matched your current one. "
            "Nothing about signing in has changed. This system does not remember "
            "previous passwords, so re-setting one is allowed; if you meant to "
            "change it, do it again with a different new password."
        )
    else:
        message = (
            "Your password has been changed. You sign in with the new one from "
            "now on — the old one stopped working the moment you saved this. You "
            "are still signed in on this device, and nothing else about your "
            "account changed. The new password is not stored anywhere it can be "
            "read back, so nobody, including the Administrator, can look it up "
            "for you later."
        )
    return True, None, message
