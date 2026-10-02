"""Migration: drop the schedule_logs table.

Run: python migrations/migrate_drop_schedule_logs.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

DOOMED_TABLE = "schedule_logs"

# Every table whose contents must be exactly what they were.
EXISTING_TABLES = (
    "users", "patients", "consultations", "inventory_items", "appointments",
    "immunizations", "audit_logs", "settings", "sms_broadcasts",
    "sms_broadcast_recipients",
)


def table_names(conn):
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def snapshot(conn, table):
    """Every row of one table, keyed by id, or None if the table is absent."""
    if table not in table_names(conn):
        return None
    return {
        row["id"]: dict(row)
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")
    }


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    present = DOOMED_TABLE in table_names(conn)
    print(f"{DOOMED_TABLE} before migration: {'present' if present else 'absent'}")
    if present:
        rows = conn.execute(f"SELECT COUNT(*) FROM {DOOMED_TABLE}").fetchone()[0]
        by_type = conn.execute(
            f"SELECT log_type, COUNT(*) FROM {DOOMED_TABLE} GROUP BY log_type"
        ).fetchall()
        print(f"  {rows} rows: " + ", ".join(f"{t}={n}" for t, n in by_type))

    before = {table: snapshot(conn, table) for table in EXISTING_TABLES}
    for table, rows in before.items():
        print(f"  {table:<26} {len(rows) if rows is not None else '(missing)'} rows")

    problems = []

    # Nothing may hold a foreign key into the table being dropped. Checked rather
    # than assumed: dropping a referenced table is exactly the mistake this
    # migration must not make.
    for table in table_names(conn):
        if table == DOOMED_TABLE or table.startswith("sqlite_"):
            continue
        for fk in conn.execute(f"PRAGMA foreign_key_list({table})"):
            if fk["table"] == DOOMED_TABLE:
                problems.append(
                    f"{table}.{fk['from']} references {DOOMED_TABLE}; not dropping"
                )

    if problems:
        print("\nMIGRATION ABORTED -- something depends on the table:")
        for problem in problems:
            print("  -", problem)
        conn.close()
        sys.exit(1)

    conn.execute(f"DROP TABLE IF EXISTS {DOOMED_TABLE}")
    conn.commit()

    print()
    still_there = DOOMED_TABLE in table_names(conn)
    print(f"{DOOMED_TABLE} after migration: {'STILL PRESENT' if still_there else 'gone'}")
    if still_there:
        problems.append(f"{DOOMED_TABLE} survived the drop")

    leftover_indexes = [
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
            (DOOMED_TABLE,),
        )
    ]
    if leftover_indexes:
        problems.append(f"indexes left behind: {leftover_indexes}")
    else:
        print("its index went with it")

    # --- nothing else may have moved --------------------------------------
    for table, old in before.items():
        new = snapshot(conn, table)
        if old is None:
            continue
        if new is None:
            problems.append(f"table {table} disappeared")
            continue
        if len(old) != len(new):
            problems.append(f"{table}: row count changed {len(old)} -> {len(new)}")
            continue
        for row_id, old_row in old.items():
            new_row = new.get(row_id)
            if new_row is None:
                problems.append(f"{table} id={row_id} disappeared")
                continue
            for column, value in old_row.items():
                if new_row[column] != value:
                    problems.append(
                        f"{table} id={row_id}.{column}: {value!r} -> {new_row[column]!r}"
                    )

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        problems.append(f"integrity_check returned {integrity!r}")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        problems.append(f"{len(violations)} foreign key violations after the drop")
    print(f"integrity_check: {integrity}; foreign key violations: {len(violations)}")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\nschedule_logs is gone with its index; every other table unchanged "
          "row for row, and the database still checks out clean.")


if __name__ == "__main__":
    main()
