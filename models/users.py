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

There is also no password change and no reset. A password is set once, at
creation, by the administrator creating the account. Changing one later is a
separate feature with its own decisions to make (does the holder change their
own? does an administrator overwrite it? is the old one required?) and User
Management states the absence rather than implying it.
"""
import re
import sqlite3

from werkzeug.security import generate_password_hash

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
    ("admin", "(retired demo password)", "Dr. Joshua Reyes", "Admin"),
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
# excluded for the same reason they cannot open Appointment Scheduling at all --
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
PASSWORD_RULE_TEXT = (
    f"At least {PASSWORD_MIN_LENGTH} characters, using at least "
    f"{PASSWORD_MIN_CHARACTER_KINDS} of these four: a small letter, a capital "
    "letter, a number, and a symbol. It must not contain the username or the "
    "person's name, and must not be a commonly-used password."
)

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


def _character_kinds(password):
    """How many of the four kinds of character the password uses."""
    kinds = 0
    if any(c.islower() for c in password):
        kinds += 1
    if any(c.isupper() for c in password):
        kinds += 1
    if any(c.isdigit() for c in password):
        kinds += 1
    if any(not c.isalnum() for c in password):
        kinds += 1
    return kinds


def _name_words(full_name):
    """The parts of a person's name long enough to be worth banning.

    Two letters or fewer are skipped: an initial, or a Filipino particle such as
    "de" or "y", appears inside far too many ordinary words to refuse a password
    over -- banning "de" would reject "the blue jeepney" for containing it.
    """
    return [
        word.lower()
        for word in re.split(r"[^A-Za-z0-9]+", full_name or "")
        if len(word) > 2
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
            f"Use at least {PASSWORD_MIN_CHARACTER_KINDS} of these four: a small "
            "letter, a capital letter, a number, and a symbol."
        )

    lowered = password.lower()

    username = (username or "").strip().lower()
    if username and len(username) > 2 and username in lowered:
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
