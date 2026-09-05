"""User accounts, authentication lookups, and the writes that create or revoke one.

WHAT THIS MODULE GAINED, AND WHY THE WRITES LIVE HERE RATHER THAN IN A ROUTE
-----------------------------------------------------------------------------
It was read-only for the project's whole life apart from seed_demo_users(): the
three accounts were written once at first boot and nothing else could add,
disable or restore one. User Management said so on its own face, and the login
route enforced a flag no screen could set. This module is now the writer as well,
and everything that decides whether a write is allowed is in it -- the password
rules, the username rules, and the refusal to switch off the last administrator.

That placement is the point rather than a filing preference. A guard that lives
in a route protects that route; a guard that lives here protects the table. The
last-administrator check in particular is inside deactivate_user() and reads its
count on the same connection and inside the same transaction as the UPDATE it is
guarding, so a second entry point added later -- another blueprint, a management
command, a future bulk action -- inherits the refusal by calling the function
rather than by its author remembering the rule exists.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
There is no delete. Accounts are revoked, never removed, for the reason patients
are archived rather than deleted: audit_logs.user_id is NOT NULL and foreign-keyed
ON DELETE RESTRICT, so every entry an account ever wrote is anchored to a row that
has to keep existing. Deleting an account would either be refused by the database
or, if that constraint were ever relaxed, would orphan the history of everything
that account did -- which is the one outcome an audit trail exists to prevent.

PASSWORD RESET AND ACCOUNT EDITING ARE HERE NOW, AND WHAT THEY DECIDED
----------------------------------------------------------------------
The paragraph that used to stand here said there was no password change and no
reset, and listed the three questions such a feature would have to answer first.
They are answered, and the answers are the shape of set_user_password() and
update_user() below:

* An administrator overwrites the password on somebody else's account. THIS IS
  NO LONGER THE ONLY WAY A PASSWORD CHANGES -- see the section below -- but it
  is still the only way one changes without its holder taking part, and that is
  what the entry in the audit trail has to say.
* The old password is NOT required, and asking for it would be theatre. An
  administrator resetting an account does not know its password -- that is the
  situation the reset exists for -- and could not be made to know it, because
  the stored value is a one-way hash. A prompt for something nobody can supply
  would refuse every legitimate reset and stop nothing else.
* The new password meets the same rule a new account's does, through the same
  check_password_strength(). One rule, one implementation; a reset that could
  set a weaker password than creation allows would make the rule advisory.

Hashing is unchanged and is not negotiable. generate_password_hash() with no
arguments, exactly as create_user() and seed_demo_users() call it, so every
credential in the table is verified by one code path. Nothing anywhere stores,
logs or can read back a password -- not the administrator who set it, not this
module, and not the audit trail.

update_user() edits a full name and a role, and nothing else. THE USERNAME IS
FIXED FOR THE LIFE OF THE ACCOUNT and is not in its UPDATE at all. It is the
stable identity every audit entry is attributed to: audit_logs.user_id points at
the row, and the entries themselves spell the username into their text, so
renaming one would leave the trail saying that "mdelacruz" performed an action
that the roster now attributes to somebody else's name. An account that needs a
different username is a different account -- create it, and deactivate the old
one, which keeps its history intact and attributable.

The role is the security-sensitive half of that edit, and it carries the
last-administrator guard for the same reason deactivation does: demoting the only
Administrator who can sign in is the same unrecoverable lockout as switching them
off, reached by a different button.

AND THE HOLDER CAN NOW CHANGE THEIR OWN PASSWORD, WHICH THE NOTE ABOVE USED TO
SAY WAS IMPOSSIBLE
-----------------------------------------------------------------------------
It said "the holder does not change their own. There is no self-service screen".
There is one now -- My Account, reached from the profile chip in the header by
every role -- and the two paths are deliberately not the same function with a
flag on it. What separates them is the one question each can ask:

    reset   an administrator, on someone else's account, WITHOUT the old
            password, because they do not have it and cannot be given it
    change  the holder, on their own account, ONLY with the old password,
            because they do have it and it is the only thing that proves the
            person at the keyboard is them and not somebody who walked up to a
            signed-in machine

verify_user_password() is what makes the second sentence true, and it is a real
comparison against the stored hash -- the same check_password_hash() call the
login form makes, against the same column. A change whose current-password box
is wrong writes nothing at all.

Everything else about the two is deliberately identical. The new password goes
through check_password_strength(), the same function, with the account's own
stored username and full name -- so a password a holder may set on themselves is
exactly a password an administrator could have set on them and exactly one that
creating the account would have allowed. And the write is set_user_password(),
the same function, so there is one UPDATE and one hashing call in this module
and no second way for a credential to enter the table.

THERE IS STILL NO REUSE HISTORY, AND THIS DID NOT ADD ONE. A change may set the
password back to what it already was: nothing stores what it was before, the
current one is knowable here only because the holder just typed it, and
password_policy() says out loud on Settings that previous passwords are not
remembered. That statement is left true. What the change path does instead is
notice the case and say so -- see routes/account_views.py -- rather than refuse
it with a rule the rest of the system does not have.
"""
import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from database.connection import get_db

# The single source of truth for the three SEEDED login accounts (audit item 21
# -- seed_users.py was removed so these were the only credentials in the
# project). full_name matches the personas rendered in the sidebar by
# inject_role_context().
#
# They are no longer the only accounts that can exist: create_user() below adds
# them from User Management. They are still the only ones written from source,
# and seed_demo_users() still runs only into an empty table, so nothing here
# touches an account an administrator created.
#
# Their passwords would not pass the strength rule further down this file, and
# they are not re-checked against it. That is stated in full beside the rule.
DEMO_USERS = [
    ("admin", "(retired demo password)", "Kagawad Antonio Acido", "Admin"),
    ("staff", "(retired demo password)", "Health Center Staff", "Health Center Staff"),
    ("official", "(retired demo password)", "Barangay Official", "Barangay Official"),
]


def seed_demo_users():
    conn = get_db()
    user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count == 0:
        for username, password, full_name, role in DEMO_USERS:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), full_name, role),
            )
        conn.commit()
    conn.close()


# Whose names may appear in "Assign to" on a booking. The Barangay Official is
# excluded for the same reason they cannot open the Patient Queue at all --
# they hold no clinical role, so a visit cannot be assigned to them.
CLINICAL_ROLES = ("Admin", "Health Center Staff")


def get_clinical_staff():
    """Active users a future appointment can be assigned to, by name.

    Read from the users table rather than hardcoded in the form, so the dropdown
    cannot offer somebody the assigned_staff_id foreign key would reject -- and
    so a deactivated account stops being offered without a template edit.
    """
    placeholders = ", ".join("?" for _ in CLINICAL_ROLES)
    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT id, full_name, role
        FROM users
        WHERE is_active = 1 AND role IN ({placeholders})
        ORDER BY full_name COLLATE NOCASE
        """,
        CLINICAL_ROLES,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_users():
    """Every account on the system, for the User Management roster.

    Deliberately not get_clinical_staff(): that one answers a different
    question -- who a visit may be assigned to -- so it drops the Barangay
    Official and hides deactivated accounts. A roster that did either would be
    an incomplete list of who can sign in, which is the one thing this screen
    exists to show. password_hash is the only column left out.

    Ordered by role then name so the roster always reads in the same order,
    rather than in whatever order the rows happen to come back in. That was
    cosmetic when there were three fixed accounts; with accounts created from
    the screen it is what keeps a newly added one from appearing at whatever
    position its row id happens to fall in.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, username, full_name, role, email, phone, is_active, created_at
        FROM users
        ORDER BY
            CASE role
                WHEN 'Admin' THEN 0
                WHEN 'Health Center Staff' THEN 1
                WHEN 'Barangay Official' THEN 2
                ELSE 3
            END,
            full_name COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def get_user_by_username(username):
    """Fetch the row the login form needs.

    Swallows OperationalError so a request that arrives before the schema exists
    is treated as a failed login rather than a 500.

    WHY is_active IS IN THIS SELECT LIST
    ------------------------------------
    It was not, and that omission was a real hole rather than an untidy query.
    The column has existed since the first schema (NOT NULL DEFAULT 1), and every
    other reader in the project honours it: get_clinical_staff() above will not
    offer a deactivated account on a booking, resolve_recipients() will not text
    one, and User Management badges it "Deactivated" under a card that says
    "Access revoked". Login was the one place that never asked -- so the flag
    meant something everywhere except the single screen where it mattered, and a
    revoked account could still sign in with its old password and reach every
    screen its role admits.

    The fix is deliberately split in two. This function's only job is to hand the
    login route the whole truth about the account; the decision about what to do
    with it belongs to routes/auth.py, next to the password check and the audit
    entry, where the refusal is worded and recorded. A model function that
    silently returned None for a deactivated account would have "fixed" the hole
    by making the account indistinguishable from one that does not exist -- and
    the audit trail would then have had nothing to attribute the refusal to,
    which is exactly the entry an administrator most needs to see.
    """
    conn = get_db()
    user = None

    try:
        user = conn.execute(
            "SELECT id, username, role, full_name, password_hash, is_active "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    except sqlite3.OperationalError:
        user = None
    finally:
        conn.close()

    return user


# ---------------------------------------------------------------------------
# Creating an account
# ---------------------------------------------------------------------------

# The three role strings the schema's CHECK constraint allows, paired with the
# label the form shows. The stored value is the left half and it is exactly what
# schema.sql permits -- so a role that would be rejected by the database cannot
# be offered by the form, and validate_new_user_form() below rejects anything
# that is not one of these before an INSERT is attempted.
#
# The middle label is spelled "Health Center Staff" rather than the sidebar's
# shorter "Health Staff" because this screen is where a role is CHOSEN, and the
# name chosen here is the one that goes into the row. utils/roles.py already
# treats the two spellings as one role for every comparison; this list is the
# stored form, and showing the stored form is what makes the audit entry, the
# roster and the database read the same word.
ROLE_CHOICES = (
    ("Admin", "Administrator"),
    ("Health Center Staff", "Health Center Staff"),
    ("Barangay Official", "Barangay Official"),
)
USER_ROLES = tuple(value for value, _label in ROLE_CHOICES)
ROLE_LABELS = dict(ROLE_CHOICES)

# The role string an Administrator is stored as. Named rather than repeated,
# because the last-administrator guard below and the roster's ordering both
# select on it and must not come to disagree about its spelling.
ADMIN_ROLE = "Admin"

# WHAT A USERNAME MAY BE.
# Narrow on purpose. A username is typed at a login form by someone who may have
# been told it over the phone, so anything that cannot be read aloud unambiguously
# or that survives a copy-paste differently from how it was typed is a support
# call waiting to happen. Letters, digits, dot, underscore and hyphen; it must
# start with a letter, so a name is never confused with a row id.
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")

FULL_NAME_MAX_LENGTH = 100

# ---------------------------------------------------------------------------
# THE PASSWORD RULE
# ---------------------------------------------------------------------------
# Nothing in this project validated password strength anywhere before this, so
# this is the rule rather than a tightening of one. It is stated in full on the
# form, in the same words, because a rule an administrator has to discover by
# being rejected four times is a rule that produces "Password1234!".
#
# THE RULE, EXACTLY:
#
#   1. at least 12 characters;
#   2. at least three of the four kinds of character -- a lower-case letter, an
#      upper-case letter, a digit, and anything else (a symbol or a space);
#   3. it must not contain the username, and must not contain a word from the
#      person's own full name, in either case;
#   4. it must not be one of the widely-used passwords listed below, and must
#      not be one of those with digits or punctuation stuck on the end.
#
# WHY 12 AND NOT 8.
# Length is the only one of these that actually costs an attacker anything.
# NIST SP 800-63B's own guidance is that length is the primary factor and that
# composition rules should not be imposed at all -- so rule 2 is the one part of
# this that is a concession rather than a defence, and it is here deliberately
# and with its limits understood. It is kept because the accounts on this system
# are created BY an administrator FOR somebody else, who will be told the password
# once; in that situation the failure mode is not a user picking something weak
# for themselves but an administrator picking the same short thing for every
# account they create, and a class requirement is a cheap brake on exactly that.
# Three of four rather than all four so a long passphrase -- "the blue jeepney
# leaves at six" -- is not rejected for lacking a symbol, which is the classic way
# composition rules push people towards shorter, worse passwords.
#
# WHY RULES 3 AND 4 MATTER MORE THAN RULE 2.
# They are the ones that catch what a real guess would try first. Rule 3 stops
# "staff_marivic2026" for the account named marivic; rule 4 stops the handful of
# strings that top every breach corpus. The blocklist below is short and is not
# pretending to be more: a real deployment would check against a downloaded
# corpus of the most common few hundred thousand, and that is a dependency this
# project does not have and has not invented one to look like it has. What is
# here is the shape of the check, working, with its scope stated.
#
# THE THREE SEEDED ACCOUNTS WOULD FAIL THIS RULE, AND THEY ARE NOT RE-CHECKED.
# "(retired demo password)" is nine characters. That is a true and slightly awkward fact, and
# it is left true rather than papered over: this rule governs passwords set from
# now on, seed_demo_users() is unchanged, and nothing re-validates a stored hash
# because a hash cannot be re-validated -- the password is not recoverable from
# it, which is the entire reason it is stored that way.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MIN_CHARACTER_KINDS = 3

# The one-sentence version, shown on the form and repeated in the field error so
# an administrator never has to look in two places for the rule they just broke.
#
# BUILT AT THE BOTTOM OF THIS FILE, NOT HERE, because it now names the four
# character kinds by reading PASSWORD_CHARACTER_KINDS -- which is defined below
# this line, beside the function that tests them. See password_policy().

# Widely-used passwords, refused outright. Compared after lower-casing and after
# stripping trailing digits and punctuation, so "password2026" and "qwerty123!"
# are caught by the same entry as the bare word.
COMMON_PASSWORDS = frozenset({
    "password", "passw0rd", "p@ssword", "p@ssw0rd", "welcome", "letmein",
    "qwerty", "qwertyuiop", "asdfghjkl", "zxcvbnm", "abc", "abcd", "abcdef",
    "iloveyou", "monkey", "dragon", "sunshine", "princess", "football",
    "baseball", "master", "shadow", "superman", "trustno", "admin",
    "administrator", "root", "login", "user", "guest", "test", "demo",
    "changeme", "secret", "default", "healthcenter", "barangay", "bphcsn",
    "idsbphcsn", "poblacion", "philippines", "pilipinas",
})

_TRAILING_NOISE = re.compile(r"""[0-9!@#$%^&*()_+\-=\[\]{};:'",.<>/?\\|`~ ]+$""")

REQUIRED_NEW_USER_FIELDS = {
    "full_name": "Enter the person's full name.",
    "username": "Enter a username for this account.",
    "role": "Choose the role this account holds.",
    "password": "Set a password for this account.",
    "confirm_password": "Type the password a second time to confirm it.",
}


# THE FOUR KINDS, AS DATA, BECAUSE TWO THINGS NOW READ THEM.
# This used to be four `if` statements inside _character_kinds() and a separate
# English sentence in PASSWORD_RULE_TEXT listing the same four in the same order.
# Settings' Password Policy pane now displays them as well, which would have made
# three copies of one list -- and a rule displayed from a second copy is a rule
# that can be displayed wrongly. The test and the label it is shown under are one
# entry here, so the pane cannot describe a kind the validator does not count and
# cannot miss one it does.
#
# `not c.isalnum()` covers a space as well as punctuation, which is why the label
# says so: a passphrase is meant to satisfy this kind without a symbol in it.
PASSWORD_CHARACTER_KINDS = (
    ("a small letter", str.islower),
    ("a capital letter", str.isupper),
    ("a number", str.isdigit),
    ("a symbol or a space", lambda c: not c.isalnum()),
)


def _character_kinds(password):
    """How many of the four kinds of character the password uses."""
    return sum(
        1 for _label, matches in PASSWORD_CHARACTER_KINDS
        if any(matches(c) for c in password)
    )


def _kinds_phrase():
    """'a small letter, a capital letter, a number, and a symbol or a space'.

    One function so the sentence on the Add User form, the sentence in the field
    error a rejected password gets, and the list Settings displays are the same
    words in the same order -- read off PASSWORD_CHARACTER_KINDS, which is what
    _character_kinds() actually tests.
    """
    labels = [label for label, _matches in PASSWORD_CHARACTER_KINDS]
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


# The shortest word from a name or a username that rules 3 and 4 will refuse a
# password for containing. A named constant because check_password_strength()
# applies it to the username, _name_words() applies it to each part of the full
# name, and Settings' Password Policy pane states it -- three readers of one
# number, which is two too many for a literal 2 sitting in a comparison.
MIN_BANNED_WORD_LENGTH = 3


def _name_words(full_name):
    """The parts of a person's name long enough to be worth banning.

    Anything shorter than MIN_BANNED_WORD_LENGTH is skipped: an initial, or a
    Filipino particle such as "de" or "y", appears inside far too many ordinary
    words to refuse a password over -- banning "de" would reject "the blue
    jeepney" for containing it.
    """
    return [
        word.lower()
        for word in re.split(r"[^A-Za-z0-9]+", full_name or "")
        if len(word) >= MIN_BANNED_WORD_LENGTH
    ]


def check_password_strength(password, username="", full_name=""):
    """The password rule, as one function. Returns a message, or None if it passes.

    Its own function rather than a block inside validate_new_user_form() so the
    rule has one implementation for any future caller -- a password change screen,
    a reset -- to reuse rather than restate. The rule is documented in full above.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return (
            f"Too short. A password must be at least {PASSWORD_MIN_LENGTH} "
            f"characters; this one is {len(password)}."
        )

    if _character_kinds(password) < PASSWORD_MIN_CHARACTER_KINDS:
        return (
            f"Use at least {PASSWORD_MIN_CHARACTER_KINDS} of these "
            f"{len(PASSWORD_CHARACTER_KINDS)}: {_kinds_phrase()}."
        )

    lowered = password.lower()

    username = (username or "").strip().lower()
    if len(username) >= MIN_BANNED_WORD_LENGTH and username in lowered:
        return (
            "A password must not contain the username. Someone guessing at this "
            "account already knows that word."
        )

    for word in _name_words(full_name):
        if word in lowered:
            return (
                "A password must not contain a part of the person's own name "
                f'("{word}"). It is the first thing anyone guessing would try.'
            )

    # Stripped of trailing digits and punctuation before the comparison, so the
    # near-misses people reach for when a rule rejects the bare word -- adding a
    # year, adding an exclamation mark -- are caught by the same entry.
    stem = _TRAILING_NOISE.sub("", lowered)
    if lowered in COMMON_PASSWORDS or (stem and stem in COMMON_PASSWORDS):
        return (
            "That is one of the most commonly guessed passwords, with or without "
            "numbers on the end. Choose something else."
        )

    return None


# ---------------------------------------------------------------------------
# THE RULE, STATED RATHER THAN ENFORCED
# ---------------------------------------------------------------------------
# WHY THIS FUNCTION EXISTS, AND WHY IT IS IN THIS FILE AND NOT ON THE SCREEN.
#
# Settings' Password Policy pane used to be five controls describing a policy
# that was not this one and was not enforced by anything: "Minimum Length 8" in a
# number box, a 90-day expiry, three complexity toggles, and a switch promising
# the last three passwords could not be reused. The real rule was twelve
# characters, three character kinds of four, no username, no name, no common
# password -- so the screen understated the length, named requirements the
# validator does not apply one at a time, and offered two features (expiry,
# reuse history) that do not exist anywhere in this system.
#
# The obvious repair is to retype the correct numbers into the same boxes. That
# is the repair this function exists to refuse. A description typed on a screen
# is a SECOND copy of the rule, and the whole failure above is what a second copy
# does over time: somebody changed the validator, or wrote it, and the screen
# went on describing something else. Every figure below is read from the
# constants check_password_strength() itself branches on and from the very list
# _character_kinds() iterates -- so raising PASSWORD_MIN_LENGTH to 14, or adding
# a fifth character kind, changes what this screen says in the same edit. There
# is no path by which the pane can be wrong while the validator is right.
#
# What it does NOT do is enforce anything. It is a read of the rule, and the pane
# that renders it is labelled as informational for that reason: the enforcement
# is check_password_strength(), called by validate_new_user_form() and by
# validate_password_reset(), and nothing an administrator can type on Screen 13
# changes it.
def password_policy():
    """The live password rule, as facts a screen can render. Nothing is typed here.

    Returns a dict:

        min_length        the length the validator refuses below
        min_kinds         how many character kinds it requires
        kinds             every kind it counts, labelled, in the order counted
        min_banned_word   shortest username or name-word that is refused
        blocklist_size    how many common passwords are refused outright
        rule_text         the one-sentence version shown on the Add User form
        not_enforced      rules this system does NOT apply, said out loud

    `not_enforced` is part of the answer rather than an omission from it. The
    pane it feeds replaced controls for an expiry period and a reuse history, and
    a pane that simply stopped mentioning them would leave an administrator to
    assume they are handled somewhere else. They are not handled anywhere.
    """
    return {
        "min_length": PASSWORD_MIN_LENGTH,
        "min_kinds": PASSWORD_MIN_CHARACTER_KINDS,
        "kinds": [label for label, _matches in PASSWORD_CHARACTER_KINDS],
        "min_banned_word": MIN_BANNED_WORD_LENGTH,
        "blocklist_size": len(COMMON_PASSWORDS),
        "rule_text": PASSWORD_RULE_TEXT,
        "not_enforced": [
            (
                "Passwords do not expire",
                "No password has an age recorded against it and nothing checks "
                "one, so no account is ever asked to change its password on a "
                "schedule.",
            ),
            (
                "Previous passwords are not remembered",
                "Only the current hash is stored. There is no history to compare "
                "against, so a password can be re-set to what it was before.",
            ),
            (
                "Each character kind is not required on its own",
                f"The rule counts how many of the {len(PASSWORD_CHARACTER_KINDS)} "
                f"kinds appear and asks for {PASSWORD_MIN_CHARACTER_KINDS} of "
                "them. A long passphrase with no symbol passes; so does one with "
                "no capital letter.",
            ),
            (
                "The three seeded demo accounts were never checked against this",
                "This rule governs passwords set from now on. A stored hash "
                "cannot be re-validated, because the password is not recoverable "
                "from it -- which is the entire reason it is stored that way.",
            ),
        ],
    }


# Assembled from the same constants and the same kinds list password_policy()
# reports and _character_kinds() counts, so the sentence on the Add User form,
# the sentence in the field error, and the pane on Settings are one sentence.
PASSWORD_RULE_TEXT = (
    f"At least {PASSWORD_MIN_LENGTH} characters, using at least "
    f"{PASSWORD_MIN_CHARACTER_KINDS} of these {len(PASSWORD_CHARACTER_KINDS)}: "
    f"{_kinds_phrase()}. It must not contain the username or the person's name, "
    "and must not be a commonly-used password."
)


def username_taken(username):
    """Whether an account already holds this username, compared case-insensitively.

    THE COMPARISON IS DELIBERATELY WIDER THAN THE DATABASE'S OWN.
    users.username is UNIQUE, but SQLite compares TEXT case-sensitively by
    default, so the constraint alone would happily accept "Admin" alongside
    "admin" -- two separate accounts, two separate password hashes, and no way to
    tell them apart when the name is read aloud or written on a handover note.
    routes/auth.py looks an account up with `WHERE username = ?`, which is
    case-sensitive too, so whichever spelling the holder typed would decide which
    of the two accounts they signed in to.

    That is not a duplicate the database would catch and it is not a cosmetic
    tidy-up: it is two credentials for what everybody involved believes is one
    account. So this is the check that runs, and the UNIQUE constraint stays as
    the backstop underneath it for the exact-match case.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(?)",
        ((username or "").strip(),),
    ).fetchone()
    conn.close()
    return row is not None


def validate_new_user_form(values):
    """Server-side validation for Add User. Returns {field: message}; empty is valid.

    Same contract as validate_patient_form() and validate_inventory_form(), and
    the same reason for existing: the form carries `novalidate` and a POST can
    arrive without the page ever having been loaded. Every rule below is enforced
    here regardless of what the browser did or did not check.

    THE DUPLICATE USERNAME IS A VALIDATION ERROR HERE AND NOT A DATABASE ERROR
    LATER. Without this the INSERT would raise sqlite3.IntegrityError on the
    UNIQUE constraint, which reaches the operator as a 500 page -- the account is
    not created, so nothing is corrupted, but the screen says the system broke
    when what actually happened is that a name was already in use. Every other
    form in this project catches its own conflicts, and this one now does too.
    """
    errors = {}

    for field, message in REQUIRED_NEW_USER_FIELDS.items():
        if not (values.get(field) or "").strip():
            errors[field] = message

    full_name = (values.get("full_name") or "").strip()
    if full_name and len(full_name) > FULL_NAME_MAX_LENGTH:
        errors["full_name"] = (
            f"Keep the name to {FULL_NAME_MAX_LENGTH} characters or fewer."
        )

    username = (values.get("username") or "").strip()
    if username and "username" not in errors:
        if len(username) < USERNAME_MIN_LENGTH:
            errors["username"] = (
                f"A username must be at least {USERNAME_MIN_LENGTH} characters."
            )
        elif len(username) > USERNAME_MAX_LENGTH:
            errors["username"] = (
                f"Keep the username to {USERNAME_MAX_LENGTH} characters or fewer."
            )
        elif not _USERNAME_PATTERN.match(username):
            errors["username"] = (
                "A username may use letters, numbers, a dot, an underscore or a "
                "hyphen, and must start with a letter. No spaces."
            )
        elif username_taken(username):
            errors["username"] = (
                f'The username "{username}" is already taken by another account. '
                "Choose a different one. Usernames are compared without regard to "
                "capitals, so a different capitalisation of the same word counts "
                "as the same username."
            )

    role = (values.get("role") or "").strip()
    if role and role not in USER_ROLES:
        errors["role"] = "Choose a role from the list."

    password = values.get("password") or ""
    confirm = values.get("confirm_password") or ""
    if password and "password" not in errors:
        problem = check_password_strength(password, username, full_name)
        if problem:
            errors["password"] = problem

    # Checked even when the password itself failed a rule above: an administrator
    # who mistyped it twice differently needs to be told both things at once, not
    # to fix the strength, resubmit, and only then discover the confirmation never
    # matched. The two errors are about different fields and both are shown.
    if password and confirm and password != confirm:
        errors["confirm_password"] = (
            "The two passwords do not match. Type the same one in both boxes."
        )

    return errors


def create_user(values):
    """Insert one account. Returns the new row id.

    Assumes validate_new_user_form() has already passed -- the same contract
    create_patient() has with validate_patient_form(). It hashes the password
    here rather than accepting a hash from the caller, so there is exactly one
    place in this project where a plaintext password becomes a stored one and no
    route can accidentally write an unhashed column.

    THE HASH IS generate_password_hash() WITH NO ARGUMENTS, WHICH IS THE SAME
    CALL seed_demo_users() ABOVE MAKES. That is deliberate to the point of being
    the requirement: routes/auth.py verifies with check_password_hash() against
    whatever scheme the stored string names, so an account created here and one
    seeded at first boot are verified by the identical code path. Werkzeug's
    default (scrypt, salted per password) is what both get; naming a different
    method here would work but would leave two kinds of credential in one table
    for no reason anybody could later reconstruct.

    email and phone are left NULL. This form does not ask for them -- see User
    Management's `contact` reason, which says contact details are never captured
    and remains true of accounts created here.
    """
    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO users (username, password_hash, full_name, role)
        VALUES (?, ?, ?, ?)
        """,
        (
            (values.get("username") or "").strip(),
            generate_password_hash(values.get("password") or ""),
            (values.get("full_name") or "").strip(),
            (values.get("role") or "").strip(),
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


# ---------------------------------------------------------------------------
# Revoking and restoring access, and the one account that cannot be revoked
# ---------------------------------------------------------------------------

# Why a deactivation was refused. A code rather than a sentence, so the model
# stays out of the business of wording a screen and the route stays the only
# place the operator's sentence is written -- the same split routes/auth.py makes
# between deciding a sign-in is refused and deciding what the form says about it.
LAST_ADMINISTRATOR = "last_administrator"
ACCOUNT_NOT_FOUND = "account_not_found"
ALREADY_IN_THAT_STATE = "already_in_that_state"


def count_active_admins():
    """How many Administrator accounts can currently sign in.

    Read on the `role` column exactly as stored. utils/roles.py's normalize_role()
    is not used and must not be: it maps several spellings onto one, which is
    right for comparing a session's role against a guard, and wrong here, because
    the schema's CHECK constraint means the only spelling that can be in this
    column is ADMIN_ROLE. Counting through the normaliser would be a loop over
    every row to answer what one COUNT already answers.
    """
    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) FROM users WHERE is_active = 1 AND role = ?",
        (ADMIN_ROLE,),
    ).fetchone()[0]
    conn.close()
    return total


def is_last_active_admin(user_id):
    """Whether deactivating this account would leave nobody able to manage accounts.

    True only when the account is itself an active Administrator and is the only
    one. Used by the screen to explain the refusal BEFORE it is attempted -- the
    button is disabled and says why -- while deactivate_user() below re-asks the
    same question at the moment of the write. Both, deliberately: the screen's
    answer is what an operator sees, the write's answer is what is true.
    """
    user = get_user_by_id(user_id)
    if user is None:
        return False
    if user["role"] != ADMIN_ROLE or not bool(user["is_active"]):
        return False
    return count_active_admins() <= 1


def _set_active(conn, user_id, is_active):
    cursor = conn.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, user_id),
    )
    return cursor.rowcount


def deactivate_user(user_id):
    """Revoke an account's access. Returns (changed, refusal_code).

    `changed` True means the account is now deactivated and was not before.
    False comes with a code saying why nothing happened.

    THE LAST-ADMINISTRATOR GUARD, AND WHY IT IS IN HERE
    ---------------------------------------------------
    Only an Administrator can open User Management -- the route carries
    role_required("Admin") -- so an Administrator is the only kind of account
    that can create accounts, revoke them, or restore one. Deactivating the last
    active Administrator would therefore not merely disable an account: it would
    remove the ability to ever enable one again, from inside the application, for
    anybody. The recovery is editing app.db by hand with a SQLite client, which
    is exactly the thing a health center running this system has nobody to do. It
    is a one-click, irreversible lockout, and it is refused.

    It is refused HERE, in the same function that does the write, rather than in
    the route that calls it. A route-level check protects one route; this
    protects the table, so a second entry point added later inherits the refusal
    by construction. The screen checks too, so the button can be disabled and can
    explain itself in advance -- but that check is an explanation, and this one is
    the rule.

    THE COUNT AND THE UPDATE SHARE ONE TRANSACTION, AND THAT IS NOT DECORATION.
    Two administrators, each deactivating the other at the same moment, is the
    textbook way a check-then-write guard is beaten: both count two, both are
    allowed, both write, and the system ends with zero. BEGIN IMMEDIATE takes the
    write lock before the count is read, so the second transaction waits for the
    first to commit and then counts one, not two, and is refused. The guard holds
    under concurrency because the count it reads cannot change under it.
    """
    conn = get_db()
    try:
        # Write lock first, then read. The order is the guarantee -- see above.
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            "SELECT id, role, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            conn.rollback()
            return False, ACCOUNT_NOT_FOUND
        if not bool(user["is_active"]):
            conn.rollback()
            return False, ALREADY_IN_THAT_STATE

        if user["role"] == ADMIN_ROLE:
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE is_active = 1 AND role = ?",
                (ADMIN_ROLE,),
            ).fetchone()[0]
            if active_admins <= 1:
                conn.rollback()
                return False, LAST_ADMINISTRATOR

        _set_active(conn, user_id, False)
        conn.commit()
        return True, None
    finally:
        conn.close()


def reactivate_user(user_id):
    """Restore an account's access. Returns (changed, refusal_code).

    No guard of its own, and there is nothing missing. Every argument in
    deactivate_user() above is about not being able to get back IN; letting an
    account back in cannot cause that. The two refusals here are the two ways
    there is nothing to do: the account is gone, or it was never switched off.

    Restoring is not the same act as creating and does not set a password. The
    stored hash was never touched by the deactivation -- is_active is a separate
    column -- so the credential the holder had before the account was switched
    off is the credential that works again now. That is stated on the screen,
    because an administrator restoring an account needs to know they are handing
    back the old password rather than issuing a new one.
    """
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute(
            "SELECT id, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            conn.rollback()
            return False, ACCOUNT_NOT_FOUND
        if bool(user["is_active"]):
            conn.rollback()
            return False, ALREADY_IN_THAT_STATE

        _set_active(conn, user_id, True)
        conn.commit()
        return True, None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Editing an account, and resetting its password
# ---------------------------------------------------------------------------
# WHAT AN EDIT MAY TOUCH, AND THE ONE FIELD IT MAY NOT.
# A full name and a role. Not the username, and not by omission -- it is absent
# from EDITABLE_USER_FIELDS, absent from the UPDATE statement, and rendered
# read-only on the form, so there are three separate places a change would have
# to be made before one could happen. The module note at the top of this file
# gives the reason in full: the username is what the audit trail attributes every
# action to, and a trail whose subject can be renamed is a trail that cannot
# answer "who did this".
#
# email and phone are not editable either, and for a different reason: nothing in
# this application ever writes them, so an edit form offering them would be the
# only place in the system where contact details exist. User Management's
# `contact` reason says they were never captured, and it stays true.
EDITABLE_USER_FIELDS = ("full_name", "role")

# The labels describe_changes() prints for the two editable fields, in the order
# an edit is reported. Kept beside the fields themselves so the audit entry and
# the form cannot come to disagree about what either one is called.
USER_EDIT_LABELS = {
    "full_name": "Full name",
    "role": "Role",
}

REQUIRED_USER_EDIT_FIELDS = {
    "full_name": "Enter the person's full name.",
    "role": "Choose the role this account holds.",
}

REQUIRED_PASSWORD_RESET_FIELDS = {
    "password": "Set a new password for this account.",
    "confirm_password": "Type the new password a second time to confirm it.",
}


def validate_user_edit_form(values):
    """Server-side validation for Edit User. Returns {field: message}.

    Same contract as validate_new_user_form() above, and deliberately narrower:
    it validates the two fields an edit may change and says nothing about the
    username, because the username is not one of the values update_user() writes.
    A posted `username` is not rejected here -- it is simply never read, which is
    the stronger answer. There is nothing to reject when there is no code path
    that could act on it.
    """
    errors = {}

    for field, message in REQUIRED_USER_EDIT_FIELDS.items():
        if not (values.get(field) or "").strip():
            errors[field] = message

    full_name = (values.get("full_name") or "").strip()
    if full_name and len(full_name) > FULL_NAME_MAX_LENGTH:
        errors["full_name"] = (
            f"Keep the name to {FULL_NAME_MAX_LENGTH} characters or fewer."
        )

    role = (values.get("role") or "").strip()
    if role and role not in USER_ROLES:
        errors["role"] = "Choose a role from the list."

    return errors


def validate_password_reset_form(values, username="", full_name=""):
    """Server-side validation for Reset Password. Returns {field: message}.

    `username` and `full_name` are the STORED values of the account being reset,
    passed in by the caller rather than read from the form, so the two rules that
    compare a password against the person it belongs to are compared against the
    real account. A form-supplied name would let the same weak password through by
    posting a different one alongside it.

    The strength rule is check_password_strength() -- the same function, not a
    copy of it -- so a password an administrator may set on a reset is exactly a
    password they could have set at creation.

    THE OLD PASSWORD IS NOT AMONG THESE FIELDS AND IS NOT ASKED FOR. See the
    module note: an administrator resetting an account does not know it, cannot
    be made to know it because the stored value is a one-way hash, and requiring
    it would refuse every legitimate reset while stopping nothing. What stands in
    its place is the guard on the route -- only an Administrator can reach it at
    all -- and an audit entry naming who did it.
    """
    errors = {}

    for field, message in REQUIRED_PASSWORD_RESET_FIELDS.items():
        if not (values.get(field) or "").strip():
            errors[field] = message

    password = values.get("password") or ""
    confirm = values.get("confirm_password") or ""

    if password and "password" not in errors:
        problem = check_password_strength(password, username, full_name)
        if problem:
            errors["password"] = problem

    # Checked even when the strength rule already failed, for the reason
    # validate_new_user_form() gives: two mistakes about two different boxes are
    # both shown at once rather than discovered one submit at a time.
    if password and confirm and password != confirm:
        errors["confirm_password"] = (
            "The two passwords do not match. Type the same one in both boxes."
        )

    return errors


def update_user(user_id, values):
    """Change one account's full name and role. Returns (before, after, refusal).

    `before` and `after` are the row as it was and as it now is, both as plain
    dicts, so the caller can describe the change without re-reading the table and
    without risking a description of a row somebody else edited in between. A
    refusal comes back as (None, None, code) and nothing was written.

    THE LAST-ADMINISTRATOR GUARD IS HERE TOO, AND IT IS THE SAME RULE
    -----------------------------------------------------------------
    deactivate_user() refuses to switch off the only Administrator who can sign
    in, because only an Administrator can open User Management and the result
    would be a system nobody can ever administer again, recoverable only by
    editing app.db by hand. Changing that same account's role to anything else
    produces the identical outcome by a different route: the account still signs
    in, and it still cannot reach a single screen that could put an Administrator
    back. Guarding one and not the other would have left the lock on the front
    door and the back door open.

    So the check is the same check, on the same terms. It fires only when the
    account is an ACTIVE Administrator, is the only one, and the edit moves its
    role away from Admin -- an inactive Administrator is not counted by
    count_active_admins() and demoting one takes nothing away that is currently
    there, exactly as deactivate_user() does not fire on an account that is
    already off.

    THE COUNT AND THE UPDATE SHARE ONE TRANSACTION, for the reason spelled out on
    deactivate_user(): BEGIN IMMEDIATE takes the write lock before the count is
    read, so two administrators demoting each other at the same moment cannot both
    be told there are two of them. The second waits, counts one, and is refused.

    An edit that changes nothing is not refused here. It writes the same two
    values back and returns a `before` and an `after` that are equal, and the
    caller compares them -- describe_changes() reports no changed fields, and
    routes/user_views.py declines to flash a change or write an audit entry for a
    save that saved nothing. That decision is about wording and about what belongs
    in a trail, so it is made where the wording is.
    """
    full_name = (values.get("full_name") or "").strip()
    role = (values.get("role") or "").strip()

    conn = get_db()
    try:
        # Write lock first, then read -- see above.
        conn.execute("BEGIN IMMEDIATE")

        columns = "id, username, full_name, role, is_active"
        user = conn.execute(
            f"SELECT {columns} FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            conn.rollback()
            return None, None, ACCOUNT_NOT_FOUND

        if (
            user["role"] == ADMIN_ROLE
            and role != ADMIN_ROLE
            and bool(user["is_active"])
        ):
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE is_active = 1 AND role = ?",
                (ADMIN_ROLE,),
            ).fetchone()[0]
            if active_admins <= 1:
                conn.rollback()
                return None, None, LAST_ADMINISTRATOR

        # username is not in this statement, and that absence is the rule rather
        # than an oversight. See EDITABLE_USER_FIELDS above.
        conn.execute(
            "UPDATE users SET full_name = ?, role = ? WHERE id = ?",
            (full_name, role, user_id),
        )
        after = conn.execute(
            f"SELECT {columns} FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        conn.commit()
        return dict(user), dict(after), None
    finally:
        conn.close()


def set_user_password(user_id, password):
    """Replace one account's stored password. Returns (changed, refusal).

    Assumes validate_password_reset_form() has already passed, the same contract
    create_user() has with validate_new_user_form().

    THE HASH IS THE SAME HASH, AND THAT IS THE REQUIREMENT.
    generate_password_hash() with no arguments, exactly as create_user() and
    seed_demo_users() call it. routes/auth.py verifies with check_password_hash()
    against whatever scheme the stored string names, so an account whose password
    was reset here and one created last week are verified by one code path and
    are indistinguishable afterwards. Naming a different method here would work
    and would quietly leave two kinds of credential in one table.

    The plaintext is used to compute a hash and is not held, returned, logged, or
    passed on. What comes back is a boolean.

    NO LAST-ADMINISTRATOR GUARD, AND NOTHING IS MISSING. Every argument in
    deactivate_user() is about removing the ability to sign in. A reset replaces
    one working credential with another working credential; the account is as
    able to sign in afterwards as before, with a password the administrator
    performing the reset knows and can hand over. The one account this could
    strand is one whose new password is then forgotten before it is written down,
    and the answer to that is another reset.
    """
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute(
            "SELECT id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            conn.rollback()
            return False, ACCOUNT_NOT_FOUND

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        conn.commit()
        return True, None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Changing your own password
# ---------------------------------------------------------------------------
# WHAT THIS SECTION ADDS TO THE ONE ABOVE, AND WHAT IT REUSES UNCHANGED.
# It adds exactly two things: a way to ask whether a supplied password is this
# account's real one, and a validator that asks for three boxes instead of two.
# It adds no way to write a password. The write is set_user_password() above --
# the same function the administrator's reset calls, with the same
# generate_password_hash() and the same UPDATE -- so a credential set from My
# Account and one set from User Management are indistinguishable in the table
# and are verified by one code path at the login form.
#
# That reuse is the reason this section is short, and it is worth saying why it
# is not shorter still. validate_password_reset_form() could have grown an
# optional current-password field and served both screens. It is not extended,
# because the two forms disagree about the one field that matters: the reset
# MUST NOT ask for the old password (an administrator does not have it) and the
# change MUST (it is the only proof the holder is present). A single validator
# with a flag would put both rules in one function where a caller passing the
# flag wrongly gets the wrong security property and no error -- and the wrong
# direction is silent, because a change that skipped the check would look like a
# change that worked.


REQUIRED_PASSWORD_CHANGE_FIELDS = {
    "current_password": "Type the password you sign in with now.",
    "new_password": "Set the new password you want to use.",
    "confirm_new_password": "Type the new password a second time to confirm it.",
}


def verify_user_password(user_id, password):
    """Whether this password is the one the account actually signs in with.

    Returns True only for the stored credential. False for a wrong password, for
    an id that names no account, and for an empty submission -- an account whose
    stored hash is somehow blank does not thereby accept every password.

    THE COMPARISON IS check_password_hash() AGAINST users.password_hash, WHICH IS
    THE SAME COMPARISON THE LOGIN FORM MAKES. Not a similar one: routes/auth.py
    verifies a sign-in against that column with that function, and so does this,
    which is what makes "the password you sign in with" a true description of
    what the field is asking for. A second scheme here would let the two answers
    diverge for the same typed string, and the divergence would show up as a
    correct password being refused on one screen and accepted on the other.

    The legacy plaintext branch mirrors routes/auth.py's for the same defensive
    reason it has one -- the live schema has no `password` column, and if a row
    ever carried one it must be honoured identically by both readers rather than
    by whichever of them happened to be written first.

    The value is used for one comparison and is not held, returned or logged.
    What comes back is a boolean, and the callers of this function pass it
    nothing that reaches the audit trail.
    """
    if not password:
        return False

    user = get_user_by_id(user_id)
    if user is None:
        return False

    values = dict(user)
    stored_hash = values.get("password_hash")
    if stored_hash:
        return check_password_hash(stored_hash, password)
    if values.get("password"):
        return values["password"] == password
    return False


def validate_password_change_form(values, username="", full_name=""):
    """Server-side validation for My Account's Change Password. Returns {field: message}.

    Same contract as validate_password_reset_form() above -- a dict keyed by the
    field the message belongs beside, empty when the submission is acceptable --
    and the same rule applied to the new password, through the same
    check_password_strength(). A holder cannot set themselves a password an
    administrator could not have set them, and neither could set one that
    creating the account would have refused.

    `username` and `full_name` are the STORED values of the signed-in account,
    passed in by the caller rather than read from the form, for the reason
    validate_password_reset_form() gives: the two clauses that refuse a password
    for containing the username or a part of the person's own name have to be
    compared against the real account, or a form could post a different name
    alongside the password and let the weak one through.

    WHAT THIS FUNCTION DOES NOT DO IS CHECK THE CURRENT PASSWORD. It cannot: the
    check needs the stored hash, this validator is handed a form. It reports only
    that the box is EMPTY, which is a fact about the form. Whether what was typed
    is right is verify_user_password()'s answer, asked by the caller, and the
    caller places the refusal on this same `current_password` key so the two
    kinds of problem with that one box read identically on the screen.

    Every box is checked even after another has failed, for the reason
    validate_new_user_form() gives: three mistakes about three different boxes
    are shown at once rather than discovered one submit at a time -- which
    matters more here than anywhere, because every box on this form is a password
    and a rejected submit clears all three.
    """
    errors = {}

    for field, message in REQUIRED_PASSWORD_CHANGE_FIELDS.items():
        if not (values.get(field) or "").strip():
            errors[field] = message

    new_password = values.get("new_password") or ""
    confirm = values.get("confirm_new_password") or ""

    if new_password and "new_password" not in errors:
        problem = check_password_strength(new_password, username, full_name)
        if problem:
            errors["new_password"] = problem

    if new_password and confirm and new_password != confirm:
        errors["confirm_new_password"] = (
            "The two new passwords do not match. Type the same one in both boxes."
        )

    return errors
