"""Migration: add the "Left before being seen" queue status (Task 6, M5).

usage:
    python migrate_add_left_before_seen.py [database]

The database defaults to app.db (config.DATABASE).

WHY
---
A patient who checks in and leaves before being seen could not be closed: the visit
stayed Waiting. The queue now has a status for it, "Left before being seen". Staff or
the Doctor set it, and can undo it the same day.

WHAT IT CHANGES IN `appointments`
---------------------------------
* The status CHECK admits 'Left before being seen'. SQLite cannot widen a CHECK in
  place, so the table is rebuilt the way sqlite.org documents (create, copy, drop,
  rename, with foreign keys off for the swap), as migrate_add_appointment_queue.py did.
* Three new columns: left_by (who), left_at (when, clinic time) and
  status_before_left (what the status was, so an undo can put it back).

WHAT IT DOES, IN ORDER
----------------------
1. Looks for work. When the CHECK and the columns are already there, it makes no copy
   and writes nothing.
2. Copies the database into IDS-BPHCSN-backups next to the project, with a timestamped
   name, before it changes anything.
3. Rebuilds the table and copies every row.
4. Checks before it finishes: every row and every column value is the same as before,
   foreign keys are clean, both indexes exist, the CHECK admits the new status and
   still refuses a made-up one. Any problem rolls the rebuild back.

Safe to run twice. It prints counts only.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import config  # loads .env into the environment

PROJECT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "left-before-seen"

NEW_STATUS = "Left before being seen"
STATUSES = ("Scheduled", "Confirmed", "Waiting", "In Consultation", "Completed",
            "Cancelled", "No-show", NEW_STATUS)
NEW_COLUMNS = ("left_by", "left_at", "status_before_left")
_CHECK = ", ".join(f"'{s}'" for s in STATUSES)

NEW_TABLE_SQL = f"""
CREATE TABLE appointments_migrated (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    scheduled_by INTEGER NOT NULL,
    appointment_type TEXT,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT,
    assigned_staff_id INTEGER,
    status TEXT NOT NULL DEFAULT 'Scheduled' CHECK (status IN ({_CHECK})),
    notes TEXT,
    is_walkin INTEGER NOT NULL DEFAULT 0,
    checked_in_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    left_by INTEGER,
    left_at TEXT,
    status_before_left TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (scheduled_by) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (assigned_staff_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (left_by) REFERENCES users(id) ON DELETE SET NULL
)
"""
OLD_COLUMNS = (
    "id", "patient_id", "scheduled_by", "appointment_type", "appointment_date",
    "appointment_time", "assigned_staff_id", "status", "notes", "is_walkin",
    "checked_in_at", "created_at", "updated_at",
)
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_appointments_date "
    "ON appointments(appointment_date, status)",
    "CREATE INDEX IF NOT EXISTS idx_appointments_queue "
    "ON appointments(appointment_date, status, checked_in_at)",
)


def _table_sql(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'appointments'"
    ).fetchone()
    return row[0] if row else ""


def _columns(conn, table="appointments"):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def needs_work(conn):
    return (f"'{NEW_STATUS}'" not in _table_sql(conn)
            or not set(NEW_COLUMNS) <= _columns(conn))


def _backup(db_path, backup_dir):
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{Path(db_path).name}.PRETASK_BACKUP_{TASK}_{stamp}"
    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def _probe_check(conn, problems):
    """The CHECK must admit the new status and still refuse a made-up one."""
    anchor = conn.execute(
        "SELECT (SELECT id FROM patients LIMIT 1), (SELECT id FROM users LIMIT 1)"
    ).fetchone()
    if anchor[0] is None or anchor[1] is None:
        return  # an empty database has nothing to point the probe row at
    for status, should_pass in ((NEW_STATUS, True), ("Bogus", False)):
        conn.execute("SAVEPOINT probe")
        try:
            conn.execute(
                "INSERT INTO appointments (patient_id, scheduled_by, appointment_date, "
                "status) VALUES (?, ?, '2026-01-01', ?)", (anchor[0], anchor[1], status))
            if not should_pass:
                problems.append("the CHECK accepted a made-up status")
        except sqlite3.IntegrityError:
            if should_pass:
                problems.append("the CHECK refused the new status")
        conn.execute("ROLLBACK TO probe")
        conn.execute("RELEASE probe")


def run(db_path, backup_dir=BACKUP_DIR):
    """Apply the migration. Returns a dict describing what happened."""
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise SystemExit(f"No database at {db_path}")
    result = {"database": db_path, "backup": None, "rows": 0, "problems": []}
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        if not needs_work(conn):
            return result
        result["backup"] = str(_backup(db_path, backup_dir))
        before = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM appointments")}
        result["rows"] = len(before)
        problems = result["problems"]
        copy_columns = ", ".join(c for c in OLD_COLUMNS if c in _columns(conn))

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            conn.execute(NEW_TABLE_SQL)
            conn.execute(f"INSERT INTO appointments_migrated ({copy_columns}) "
                         f"SELECT {copy_columns} FROM appointments")
            conn.execute("DROP TABLE appointments")
            conn.execute("ALTER TABLE appointments_migrated RENAME TO appointments")
            for statement in INDEXES:
                conn.execute(statement)

            after = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM appointments")}
            if len(after) != len(before):
                problems.append("the row count changed")
            for row_id, old in before.items():
                new = after.get(row_id)
                if new is None or any(new[c] != v for c, v in old.items() if c in new):
                    problems.append("a row's values changed")
                    break
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                problems.append("foreign_key_check found a violation")
            have = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='appointments'")}
            if not {"idx_appointments_date", "idx_appointments_queue"} <= have:
                problems.append("an index is missing")
            _probe_check(conn, problems)
            conn.execute("ROLLBACK" if problems else "COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
        return result
    finally:
        conn.close()


def main(argv):
    db_path = argv[0] if argv else config.DATABASE
    print(f"database: {db_path}")
    result = run(db_path)
    if result["problems"]:
        print("STOPPED. Nothing was changed:")
        for problem in result["problems"]:
            print(f"  - {problem}")
        return 1
    if not result["backup"]:
        print("Nothing to do. The status and its columns are already there.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"appointments rebuilt: {result['rows']} rows, every value unchanged")
    print("status 'Left before being seen' and columns left_by, left_at, "
          "status_before_left added.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
