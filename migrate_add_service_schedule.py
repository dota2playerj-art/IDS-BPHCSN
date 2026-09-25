"""Migration: add the service_schedule table, and put nothing in it.

WHAT THIS IS FOR
----------------
Advance booking was retired on 2026-09-05 because a barangay health center does
not let a patient choose an hour: the facility decides which services run on
which days, and people walk in. utils/unavailable.py's `advance_booking` has
said since then that a fixed schedule of service days was "the honest
successor", and nothing could record one. This is the table that records one:
each row is one service and the days it runs, entered by the Administrator.

IT SHIPS EMPTY, AND THAT IS THE POINT RATHER THAN AN OMISSION
-------------------------------------------------------------
Barangay Poblacion Health Center has not been interviewed yet. Two facts are
confirmed, from the RHU interview: family planning runs daily at the barangay
health center, and vaccination there is scheduled on a day that is not known,
because immunisation rotates between barangays. Neither is a complete row -- one
has no service name the center itself uses, the other has no day -- and the
RHU's own days (prenatal on Tuesday, immunisation on Wednesday) describe the RHU
building, not this facility.

So no row is seeded, not even the confirmed half-facts. This project has already
been damaged once by an unconfirmed guess hardening into apparent fact -- the
health center's province, which was written down as "Agusan del Sur" and read
back as though somebody had checked (09_UI_Architecture §17). A plausible
timetable sitting in this table would be read the same way. The screens that
read it say plainly that it is empty, and the Administrator fills it in once the
days are known.

HOW A ROW DESCRIBES ITS DAYS
----------------------------
Two columns, and no "pattern type" column:

    weekdays        which days of the week, as ISO weekday numbers, ascending
                    and comma-separated: "1" is Monday, "7" is Sunday -- the
                    numbering Python's date.isoweekday() returns, so the check
                    against a date is a membership test with no translation
    weeks_of_month  NULL for every week; otherwise which occurrences of those
                    days within the month, "2,4" for the 2nd and 4th

That covers every pattern the interviews described, each as one row:

    daily, Monday to Friday         weekdays "1,2,3,4,5"   weeks NULL
    every Monday and Thursday       weekdays "1,4"         weeks NULL
    every 2nd and 4th Wednesday     weekdays "3"           weeks "2,4"

"Every weekday", "specific weekdays" and "the Nth weekday of the month" are then
things the two columns SAY, not a third column that could disagree with them. A
stored type of "every weekday" beside weekdays "1,4" would be a row that states
two different schedules, and every reader would have to decide which one to
believe. See models/service_schedule.py for how a row is read and worded.

The Nth occurrence runs 1st to 4th. Every month has at least four of each
weekday and only some have a fifth, so a "5th Wednesday" service would silently
not run in most months; no interview described one, and a "last Wednesday"
rule was not described either. Both are refused rather than guessed at.

WHY THE CONSTRAINTS ARE WHAT THEY ARE
-------------------------------------
service is NOT NULL and CHECKed non-blank: a row that does not name a service
says nothing. weekdays is NOT NULL and CHECKed to digits 1-7 and commas: a row
that runs on no day is not a schedule entry. weeks_of_month is NULL or digits
1-4 and commas, for the reason above. The model writes the canonical sorted form
and validates everything first; the CHECKs are what stop a hand-edited row from
putting "Wed" or "5" where a reader cannot interpret it.

created_by and updated_by are ON DELETE SET NULL, matching settings.updated_by:
this is configuration of the facility, not a clinical record naming its author,
and nothing in the application deletes an account anyway. The full history of
who added, changed and removed each entry is in audit_logs.

A deleted entry is deleted, not flagged. The audit entry for the deletion
records everything the row said, so nothing is lost, and a "deleted" flag would
be one more condition every reader of the schedule had to remember.

Idempotent -- re-running is a no-op and writes nothing.

    python migrate_add_service_schedule.py              the project database
    python migrate_add_service_schedule.py <path>       a copy, to rehearse on first
"""
import sqlite3
import sys

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
