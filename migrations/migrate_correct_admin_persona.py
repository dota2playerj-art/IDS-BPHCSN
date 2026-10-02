"""Migration: give the Administrator account its real persona.

Run: python migrations/migrate_correct_admin_persona.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
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
