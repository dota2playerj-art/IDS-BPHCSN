"""Migration: give the Administrator account its real persona.

The `admin` account has carried "Dr. Joshua Reyes" since the database was first
seeded. That name was a placeholder invented in `06_DESIGN_CONTENT_LIBRARY.md`
and copied from there into `models/users.py`. The person who actually holds this
account is **Antonio Acido**, a Kagawad -- an elected barangay councilor --
chairing the barangay's Health Committee, confirmed by the project team's
technical adviser. He is not a physician, so the honorific is "Kagawad".

`models/users.py` seeds the corrected name and has been changed alongside this
script, so a database built from scratch comes out right. This exists for the
database that is already here, which a reseed would not touch -- seed_demo_users()
only runs into an empty users table.

WHAT THIS DOES NOT TOUCH, ON PURPOSE
------------------------------------
* **The username.** `admin` is unchanged. `models/users.py` states the rule at
  length: a username is permanently fixed, because past audit rows are
  attributable to it.
* **The password.** password_hash is verified byte-for-byte unchanged, so the
  existing credentials keep working exactly as they did.
* **The role.** The stored value stays "Admin". That is what the schema's CHECK
  constraint allows and what role_required() compares; nothing about this
  account's permissions changes. Only the person filling the role changed.
* **The audit trail.** 506 entries in audit_logs.details name "Dr. Joshua Reyes"
  in sentences already written. They are left exactly as they are. An audit trail
  records what the system knew at the time, and rewriting old entries to look
  tidy is the one thing it must never do. The rows will read a little oddly next
  to the corrected name in the User column, which is joined live from users --
  that is the honest result, not a defect.

  That figure is counted, not remembered: this docstring said 508 until the
  count was actually run against the database as it stood before the migration,
  which is 506. The number is printed by the script itself on every run, before
  and after, so what a reader is told is what the file holds rather than what a
  comment claims about it.

Only users.full_name is written, and only on the one row named below. Every
other column of that row, and every other row in the table, is verified
byte-for-byte unchanged.

Idempotent -- re-running is a no-op. A row already carrying the corrected name is
skipped; a row matching neither the expected before-state nor the after-state is
reported and left alone rather than overwritten.

Run:  python migrate_correct_admin_persona.py
"""
import sqlite3
import sys

import config

USERNAME = "admin"
WRONG = "Dr. Joshua Reyes"
RIGHT = "Kagawad Antonio Acido"


def snapshot(conn):
    return {row["username"]: dict(row) for row in conn.execute("SELECT * FROM users ORDER BY id")}


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before = snapshot(conn)
    print(f"user accounts before migration: {len(before)}")

    audit_before = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE details LIKE ?", (f"%{WRONG}%",)
    ).fetchone()[0]
    print(f'audit entries naming "{WRONG}" in their details: {audit_before} (left as written)')

    row = before.get(USERNAME)
    if row is None:
        print(f'  MISSING  account "{USERNAME}" is not in this database; nothing to correct.')
        conn.close()
        return 1

    current = row["full_name"]
    if current == RIGHT:
        print(f'  already  "{USERNAME}" already reads "{RIGHT}"; nothing to do.')
    elif current != WRONG:
        print(
            f'  MISMATCH "{USERNAME}" reads "{current}", which is neither the expected '
            f'"{WRONG}" nor the corrected "{RIGHT}". Left untouched.'
        )
        conn.close()
        return 1
    else:
        conn.execute(
            "UPDATE users SET full_name = ? WHERE username = ? AND full_name = ?",
            (RIGHT, USERNAME, WRONG),
        )
        conn.commit()
        print(f'  applied  "{USERNAME}": "{current}" -> "{RIGHT}"')

    # Verification: the one field moved, and nothing else in the table did.
    after = snapshot(conn)
    failures = []

    if set(after) != set(before):
        failures.append("the set of accounts changed")

    for username, before_row in before.items():
        after_row = after.get(username, {})
        for column, value in before_row.items():
            expected = RIGHT if (username == USERNAME and column == "full_name") else value
            if after_row.get(column) != expected:
                failures.append(
                    f'{username}.{column}: expected {expected!r}, found {after_row.get(column)!r}'
                )

    audit_after = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE details LIKE ?", (f"%{WRONG}%",)
    ).fetchone()[0]
    if audit_after != audit_before:
        failures.append(
            f"audit history was altered: {audit_before} entries named the old persona "
            f"before, {audit_after} after"
        )

    conn.close()

    print()
    if failures:
        print("VERIFICATION FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("VERIFICATION PASSED")
    print(f'  users.full_name for "{USERNAME}" is "{after[USERNAME]["full_name"]}"')
    print(f'  username unchanged: "{after[USERNAME]["username"]}"')
    print(f'  role unchanged: "{after[USERNAME]["role"]}"')
    print("  password_hash unchanged, so the existing credentials still work")
    print(f"  audit_logs untouched: {audit_after} entries still name the old persona, as written")
    print(f"  every other column of every account byte-for-byte unchanged ({len(after)} accounts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
