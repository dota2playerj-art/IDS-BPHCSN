"""Migration: add the service_schedule table, and put nothing in it.

Run: python migrations/migrate_add_service_schedule.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

TABLE = "service_schedule"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS service_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL CHECK (length(trim(service)) > 0),
    weekdays TEXT NOT NULL CHECK (
        weekdays <> '' AND weekdays NOT GLOB '*[^1-7,]*'
    ),
    weeks_of_month TEXT CHECK (
        weeks_of_month IS NULL
        OR (weeks_of_month <> '' AND weeks_of_month NOT GLOB '*[^1-4,]*')
    ),
    note TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER,
    updated_at TEXT,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
)
"""

COLUMNS = [
    "id", "service", "weekdays", "weeks_of_month", "note",
    "created_by", "created_at", "updated_by", "updated_at",
]


def table_names(conn):
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def snapshot(conn, table):
    """Every row of one table, in rowid order."""
    return [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else config.DATABASE
    print(f"database: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    already = TABLE in table_names(conn)
    print(f"{TABLE} before migration: {'present' if already else 'absent'}")

    # Every table that exists now, whatever it is called, must come out of this
    # exactly as it went in. Read from sqlite_master rather than a hand-kept
    # list, so a table added after this script was written is still compared.
    # sqlite_sequence is left out: creating an AUTOINCREMENT table does not
    # touch it, but the probes below do insert-and-roll-back, and the check is
    # about user data rather than SQLite's own bookkeeping.
    existing = sorted(
        name for name in table_names(conn)
        if name not in (TABLE, "sqlite_sequence")
    )
    before = {table: snapshot(conn, table) for table in existing}
    for table in existing:
        print(f"  {table:<26} {len(before[table])} rows")

    conn.execute(TABLE_SQL)
    conn.commit()

    problems = []

    if TABLE not in table_names(conn):
        problems.append(f"{TABLE} was not created")
    else:
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")]
        if columns != COLUMNS:
            problems.append(f"{TABLE} columns are {columns}, expected {COLUMNS}")

    # --- nothing that already existed may have moved ------------------------
    for table in existing:
        after = snapshot(conn, table)
        if after != before[table]:
            problems.append(
                f"{table} changed: {len(before[table])} rows before, {len(after)} after"
            )

    # --- the constraints have to actually refuse, not merely be written -----
    def refuses(label, service, weekdays, weeks):
        try:
            conn.execute("SAVEPOINT probe")
            conn.execute(
                "INSERT INTO service_schedule (service, weekdays, weeks_of_month) "
                "VALUES (?, ?, ?)",
                (service, weekdays, weeks),
            )
            conn.execute("ROLLBACK TO probe")
            conn.execute("RELEASE probe")
            problems.append(f"CHECK did not refuse {label}")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK TO probe")
            conn.execute("RELEASE probe")
            if "CHECK constraint failed" not in str(exc) and "NOT NULL" not in str(exc):
                problems.append(f"{label} refused by {exc}, not by its constraint")
            else:
                print(f"refuses {label}")

    refuses("a blank service", "   ", "1", None)
    refuses("a service with no day", "__PROBE__", "", None)
    refuses("a day written as a name", "__PROBE__", "Wed", None)
    refuses("a day number outside 1-7", "__PROBE__", "8", None)
    refuses("a 5th week of the month", "__PROBE__", "3", "2,5")
    refuses("an empty weeks value", "__PROBE__", "3", "")

    # And it must still ACCEPT the three shapes the interviews described.
    for label, weekdays, weeks in (
        ("every weekday", "1,2,3,4,5", None),
        ("specific weekdays", "1,4", None),
        ("2nd and 4th Wednesday", "3", "2,4"),
    ):
        conn.execute("SAVEPOINT probe")
        try:
            conn.execute(
                "INSERT INTO service_schedule (service, weekdays, weeks_of_month) "
                "VALUES ('__PROBE__', ?, ?)",
                (weekdays, weeks),
            )
            print(f"accepts {label}")
        except sqlite3.IntegrityError as exc:
            problems.append(f"refused a valid row ({label}): {exc}")
        conn.execute("ROLLBACK TO probe")
        conn.execute("RELEASE probe")

    # --- it ships empty ------------------------------------------------------
    rows = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    print(f"{TABLE} after migration: {rows} rows")
    if not already and rows:
        problems.append(f"{TABLE} was created holding {rows} rows; it must ship empty")
    probes = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE service = '__PROBE__'"
    ).fetchone()[0]
    if probes:
        problems.append(f"{probes} probe rows survived their rollback")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print(f"\n{TABLE} present with working constraints and no rows; every "
          "pre-existing table unchanged row for row.")


if __name__ == "__main__":
    main()
