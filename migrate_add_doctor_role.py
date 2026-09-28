"""Migration: add the Doctor role, and the demo account that holds it.

WHY THERE IS A FOURTH ROLE
--------------------------
Clinical authority -- entering a diagnosis and a treatment plan, sealing a
consultation as Restricted, reading one that is sealed, declaring a patient
deceased -- was given to the Administrator account, on the assumption that the
Administrator was the health center's licensed doctor. That assumption stopped
being true when the Administrator's persona was corrected to Kagawad Antonio
Acido, chair of the barangay Health Committee (migrate_correct_admin_persona.py):
an elected barangay official, not a physician. Field data gathered from the RHU
of San Francisco, Surigao del Norte then showed the two jobs are genuinely
separate there -- the Kagawad administers, the RHU doctor diagnoses -- so the
only account this system allowed to diagnose was held by someone not licensed to.

The fix is a separate Doctor role. This script does the database half of it:

  1. The users.role CHECK constraint admits exactly three strings, so a Doctor
     account cannot be stored at all. It is widened to four.
  2. One demo Doctor account, "doctor", is created, because a live database was
     seeded long before the role existed and seed_demo_users() only ever runs
     into an empty users table. Its values are read from models/users.py
     DEMO_USERS -- the same list a fresh database is seeded from -- so the two
     cannot come to disagree about the account.

The display name is "RHU Physician (demo)", a placeholder on purpose: the real
doctor's name is not yet confirmed, and an invented person's name would read as
a real one. The team renames it through Edit User when it is.

Idempotent -- re-running is a no-op and writes nothing.

    python migrate_add_doctor_role.py              the project database
    python migrate_add_doctor_role.py <path>       a copy, to rehearse on first

WHY THE CHECK NEEDS A TABLE REBUILD
-----------------------------------
SQLite has no ALTER TABLE ... DROP CONSTRAINT. The supported way to change a
CHECK is the rebuild documented at sqlite.org/lang_altertable.html#otheralter,
which migrate_add_appointment_queue.py already uses for the appointments status
CHECK: create the replacement, copy every row, drop the original, rename -- in
one transaction, with foreign keys off for the swap and a foreign_key_check
after it.

users is the table every other table points at (audit_logs, consultations,
appointments and seven more reference users(id)), so this is done with more
care than that script needed rather than less:

* The replacement's definition is the LIVE table's own CREATE statement with
  only the CHECK clause substituted, not a retyped copy. A retyped copy is a
  second definition that could differ in a column default nobody noticed. If
  the live CHECK is not exactly the three-role clause this script expects, it
  stops without writing anything.
* The AUTOINCREMENT high-water mark is carried across, so an id that was ever
  issued is never issued again -- audit_logs.user_id rows must never come to
  point at a different person.
* Every pre-existing account row is compared column by column afterwards,
  password_hash included, and so is every row of every OTHER table: the only
  permitted difference anywhere in the database is the one new account.

WHAT THIS DOES NOT TOUCH, ON PURPOSE
------------------------------------
* No existing account changes. The Administrator keeps the "Admin" role; this
  moves no permission by itself. Which role may diagnose is decided in code
  (models/consultations.py can_diagnose), not in the users table.
* No consultation, seal or audit entry changes. A diagnosis written under the
  Administrator account stays exactly as written and attributed; a seal set
  under it stays set.
* No audit entry is written for the new account. seed_demo_users() writes none
  for the accounts it creates either: audit_logs.user_id is NOT NULL and names
  the account that acted, and no signed-in account acted here. The account's
  existence is recorded where every account's is -- in users, with created_at.
"""
import os
import sqlite3
import sys

from werkzeug.security import generate_password_hash

import config
from models.users import (
    DEMO_USERS,
    DOCTOR_ROLE,
    generate_initial_password,
    print_first_passwords,
)

OLD_CHECK = "CHECK (role IN ('Admin', 'Health Center Staff', 'Barangay Official'))"
NEW_CHECK = (
    "CHECK (role IN ('Admin', 'Doctor', 'Health Center Staff', "
    "'Barangay Official'))"
)
ALL_ROLES = ("Admin", "Doctor", "Health Center Staff", "Barangay Official")

USER_COLUMNS = (
    "id", "username", "password_hash", "full_name", "role", "email", "phone",
    "is_active", "created_at",
)

# (username, full name, role). DEMO_USERS holds no password: one is made at
# random when the account is created, and printed once.
DOCTOR_ACCOUNT = next(entry for entry in DEMO_USERS if entry[2] == DOCTOR_ROLE)


def users_sql(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    return row[0] if row else ""


def check_admits_doctor(conn):
    return "'Doctor'" in users_sql(conn)


def users_sequence(conn):
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'users'"
    ).fetchone()
    return row[0] if row else None


def snapshot(conn):
    """Every row of every table, keyed by table, as sorted tuples.

    sqlite_sequence is left out and checked on its own: its users row is the one
    value in it this migration is expected to move, by exactly one account.
    """
    tables = [
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    data = {}
    for table in tables:
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        data[table] = sorted(tuple(row) for row in rows)
    return data


def rebuild_with_doctor(conn):
    """Replace users with an identical table whose CHECK also admits Doctor."""
    live_sql = users_sql(conn)
    if live_sql.count(OLD_CHECK) != 1:
        raise SystemExit(
            "users.role CHECK is not the three-role clause this migration was "
            f"written against, so nothing was changed.\n  expected: {OLD_CHECK}\n"
            f"  live table: {live_sql}"
        )
    new_sql = live_sql.replace(OLD_CHECK, NEW_CHECK)
    # The table name appears once, straight after CREATE TABLE.
    head = "CREATE TABLE users ("
    if not new_sql.startswith(head):
        raise SystemExit(f"Unexpected users definition, nothing changed:\n{live_sql}")
    new_sql = "CREATE TABLE users_migrated (" + new_sql[len(head):]

    sequence_before = users_sequence(conn)
    columns = ", ".join(USER_COLUMNS)

    # PRAGMA foreign_keys is ignored inside a transaction, so it is set first.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        conn.execute(new_sql)
        conn.execute(
            f"INSERT INTO users_migrated ({columns}) SELECT {columns} FROM users"
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_migrated RENAME TO users")
        # Carry the AUTOINCREMENT high-water mark across. The copy leaves it at
        # the highest id present, which is lower than the old mark if the
        # highest-numbered account was ever removed -- and an id reissued to a
        # different person would re-attribute that account's audit history.
        if sequence_before is not None:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'users'",
                (sequence_before,),
            )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"foreign_key_check reported {violations}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        conn.execute("PRAGMA foreign_keys = ON")
        raise
    conn.execute("PRAGMA foreign_keys = ON")


def add_demo_doctor(conn):
    """Create the demo Doctor account unless one by that username exists.

    Returns "created", "present" (already there, as a Doctor), or raises when the
    username is held by an account of another role -- that is somebody's real
    account and this script has no business deciding what it should be.
    """
    username, full_name, role = DOCTOR_ACCOUNT
    existing = conn.execute(
        "SELECT id, role FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    if existing is not None:
        if existing["role"] != role:
            raise SystemExit(
                f'The username "{username}" already belongs to account '
                f'#{existing["id"]} with role {existing["role"]!r}. Nothing was '
                "created; choose what to do about that account by hand."
            )
        return "present"

    # A random first password that passes the password rule, the same way
    # seed_demo_users() makes one. It is printed once below and kept nowhere.
    password = generate_initial_password(username, full_name)

    # generate_password_hash() with no arguments, exactly as seed_demo_users()
    # and create_user() call it, so this credential is verified by the same
    # code path as every other one in the table. If the must_change_password
    # column already exists, the account is marked so the person must set their
    # own password; if not, migrate_add_must_change_password.py adds it later.
    columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
    conn.execute("BEGIN")
    if "must_change_password" in columns:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, "
            "must_change_password) VALUES (?, ?, ?, ?, 1)",
            (username, generate_password_hash(password), full_name, role),
        )
    else:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) "
            "VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), full_name, role),
        )
    conn.execute("COMMIT")
    print_first_passwords([(username, password)])
    return "created"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else config.DATABASE
    if not os.path.exists(path):
        raise SystemExit(f"No database at {path}")
    print(f"database: {path}")

    # isolation_level=None: this script issues its own BEGIN/COMMIT, and the
    # PRAGMA around the rebuild must not land inside an implicit transaction.
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row

    before = snapshot(conn)
    sequence_before = users_sequence(conn)
    users_before = {
        row["id"]: dict(row) for row in conn.execute("SELECT * FROM users")
    }
    print(f"accounts before: {len(users_before)}")

    if check_admits_doctor(conn):
        print("role CHECK: already admits Doctor -- rebuild skipped")
    else:
        print("role CHECK: rebuilding users to admit Doctor")
        rebuild_with_doctor(conn)
        print("foreign_key_check: clean")

    outcome = add_demo_doctor(conn)
    print(f'demo Doctor account "{DOCTOR_ACCOUNT[0]}": '
          f"{'created' if outcome == 'created' else 'already present -- nothing written'}")

    # ---- verification ---------------------------------------------------
    problems = []

    if not all(f"'{role}'" in users_sql(conn) for role in ALL_ROLES):
        problems.append("users CHECK does not list all four roles")

    after = snapshot(conn)
    for table, rows in before.items():
        if table == "users":
            continue
        if after.get(table) != rows:
            problems.append(f"table {table} changed")
    if set(after) != set(before):
        problems.append(f"table set changed: {sorted(set(after) ^ set(before))}")

    users_after = {
        row["id"]: dict(row) for row in conn.execute("SELECT * FROM users")
    }
    for user_id, old in users_before.items():
        new = users_after.get(user_id)
        if new is None:
            problems.append(f"account id={user_id} disappeared")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(f"account id={user_id}.{column} changed")

    added = [u for i, u in users_after.items() if i not in users_before]
    expected_added = 1 if outcome == "created" else 0
    if len(added) != expected_added:
        problems.append(f"{len(added)} accounts added, expected {expected_added}")
    for account in added:
        if (account["username"], account["full_name"], account["role"]) != (
            DOCTOR_ACCOUNT[0], DOCTOR_ACCOUNT[1], DOCTOR_ACCOUNT[2]
        ) or account["is_active"] != 1:
            problems.append(f"added account is not the demo Doctor: {account}")

    sequence_after = users_sequence(conn)
    if sequence_before is not None and sequence_after != sequence_before + expected_added:
        problems.append(
            f"users AUTOINCREMENT mark moved {sequence_before} -> {sequence_after}"
        )

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        problems.append(f"foreign_key_check reported {len(violations)} violation(s)")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        problems.append(f"integrity_check: {integrity}")

    # The constraint must actually refuse a role outside the vocabulary, not
    # merely list the good ones. Probed inside a transaction that is always
    # rolled back, so the probe itself can never leave a row behind.
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) "
            "VALUES ('__probe__', 'x', 'probe', 'Nurse')"
        )
        problems.append("CHECK accepted a role outside the vocabulary")
    except sqlite3.IntegrityError as exc:
        if "CHECK constraint failed" not in str(exc):
            problems.append(f"bad role refused, but by {exc} rather than the CHECK")
        else:
            print("role CHECK: refuses a role outside the four")
    finally:
        conn.execute("ROLLBACK")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print(f"accounts after:  {len(users_after)}")
    print("\nEvery pre-existing account and every row of every other table is "
          "unchanged; the only difference is the demo Doctor account.")


if __name__ == "__main__":
    main()
