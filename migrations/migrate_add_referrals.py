"""Migration: the visit outcome "Referred" (Task 18, D1).

Adds 'Referred' to the appointments.status CHECK and six columns for the referral (destination,
facility name, reason, who, when, the status before). SQLite cannot change a CHECK, so the table
is rebuilt with every row, value and id kept.

Run: python migrations/migrate_add_referrals.py (project root). The database defaults to app.db.
Safe to run twice: it backs the database up first, does nothing when the status is already
there, and writes one audit entry.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config  # loads .env into the environment

PROJECT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "referrals"

NEW_STATUS = "Referred"
# Written out here on purpose: a migration must keep working when the application's lists
# change later.
STATUSES = ("Scheduled", "Confirmed", "Waiting", "In Consultation", "Waiting for the Doctor",
            "Completed", "Cancelled", "No-show", "Left before being seen", NEW_STATUS)
_CHECK = ", ".join(f"'{s}'" for s in STATUSES)

ACTION = "Added referrals to the Patient Queue"
MODULE = "Appointment Scheduling"

OLD_COLUMNS = (
    "id", "patient_id", "scheduled_by", "appointment_type", "appointment_date",
    "appointment_time", "assigned_staff_id", "status", "notes", "is_walkin",
    "checked_in_at", "created_at", "updated_at", "left_by", "left_at",
    "status_before_left",
)

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
    referral_destination TEXT,
    referral_facility TEXT,
    referral_reason TEXT,
    referred_by INTEGER,
    referred_at TEXT,
    status_before_referred TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (scheduled_by) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (assigned_staff_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (left_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (referred_by) REFERENCES users(id) ON DELETE SET NULL
)
"""
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


def needs_work(conn):
    return f"'{NEW_STATUS}'" not in _table_sql(conn)


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
        audit_before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        actor = conn.execute(
            "SELECT id FROM users WHERE role = 'Admin' AND is_active = 1 "
            "ORDER BY id LIMIT 1").fetchone()
        if actor is None:
            raise SystemExit("Stopped. No active Administrator account to file the entry under.")
        problems = result["problems"]
        present = {r["name"] for r in conn.execute("PRAGMA table_info(appointments)")}
        copy_columns = ", ".join(c for c in OLD_COLUMNS if c in present)

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

            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_add_referrals.py, not by this account. "
                 f"The appointments table was rebuilt with {len(before)} "
                 f"row{'' if len(before) == 1 else 's'} kept as they were. Staff and the Doctor "
                 "can now refer a patient to the RHU or a hospital from the Patient Queue."))

            # Checks, before anything is committed.
            after = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM appointments")}
            if len(after) != len(before):
                problems.append("the row count changed")
            for row_id, old in before.items():
                new = after.get(row_id)
                if new is None:
                    problems.append("a row went missing")
                    break
                if any(new[c] != v for c, v in old.items() if c in new):
                    problems.append("a value changed")
                    break
                if any(new[c] is not None for c in new if c not in old):
                    problems.append("a new column was not empty")
                    break
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                problems.append("foreign_key_check found a violation")
            have = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='appointments'")}
            if not {"idx_appointments_date", "idx_appointments_queue"} <= have:
                problems.append("an index is missing")
            if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] != audit_before + 1:
                problems.append("the audit table did not gain exactly one row")
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
        print("Nothing to do. The status is already there.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"appointments rebuilt: {result['rows']} rows")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
