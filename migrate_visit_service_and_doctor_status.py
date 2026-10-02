"""Migration: the queue status "Waiting for the Doctor" (Task 6b, M33 and L31).

usage:
    python migrate_visit_service_and_doctor_status.py [database]

The database defaults to app.db (config.DATABASE).

WHY
---
Saving the intake used to set a visit to "Completed" even when the Doctor had not seen
the patient, so "Completed" counts were wrong, and every visit was saved as a
"Walk-in Consultation", so immunization and prenatal visits landed on the Doctor's
list. Staff now choose the service at check-in, and a visit whose service needs a
diagnosis waits in its own status, "Waiting for the Doctor", until the Doctor writes it.

WHAT IT DOES, IN ORDER
----------------------
1. Looks for work. When the status CHECK already admits "Waiting for the Doctor", it
   makes no copy and writes nothing.
2. Copies the database into IDS-BPHCSN-backups next to the project, with a timestamped
   name, before it changes anything.
3. Rebuilds `appointments` with the wider status CHECK. SQLite cannot widen a CHECK in
   place, so the table is rebuilt the way sqlite.org documents (create, copy, drop,
   rename, with foreign keys off for the swap), as migrate_add_left_before_seen.py did.
4. Converts the visits the Doctor still owes a diagnosis to "Waiting for the Doctor":
   those that are Completed, whose service needs the Doctor (a Walk-in Consultation, or
   no service at all, needs him), that have a consultation record and no diagnosis. A
   Completed visit with no consultation record at all was closed from the queue with
   nothing written; the Doctor has nothing to open, so it stays Completed. A sealed
   diagnosis is stored encrypted, which is not blank, so it counts as a diagnosis.
5. Does the same for a visit that was marked "Left before being seen" from Completed:
   its `status_before_left` becomes "Waiting for the Doctor", so the same-day undo puts
   it back where it belongs.
6. Writes ONE audit entry recording the run, with the counts. audit_logs.user_id must
   name an account, and no "system" account exists, so it is filed under the first
   active Administrator. The entry says the migration did it, not that person.
7. Checks before it finishes: every other column of every row is unchanged, only the
   converted rows moved and only in `status` (and `status_before_left`), foreign keys are
   clean, both indexes exist, the CHECK admits the new status and still refuses a
   made-up one, and the audit table gained exactly one row. Any problem rolls it all back.

Safe to run twice: the second run finds the CHECK already wide and does nothing.
It prints counts only.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import config  # loads .env into the environment

PROJECT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "visit-service-and-doctor-status"

NEW_STATUS = "Waiting for the Doctor"
STATUSES = ("Scheduled", "Confirmed", "Waiting", "In Consultation", NEW_STATUS,
            "Completed", "Cancelled", "No-show", "Left before being seen")
_CHECK = ", ".join(f"'{s}'" for s in STATUSES)

# The services whose visits need the Doctor. The same list as
# models/doctor_worklist.py SERVICES_NEEDING_DOCTOR, written out here on purpose: a
# migration must keep working when the application's list changes later.
NEEDS_DOCTOR = ("Consultation", "Follow-up Consultation",
                "Hypertension / Diabetes Monitoring", "Walk-in Consultation")

ACTION = "Moved visits to Waiting for the Doctor"
MODULE = "Appointment Scheduling"

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
COLUMNS = (
    "id", "patient_id", "scheduled_by", "appointment_type", "appointment_date",
    "appointment_time", "assigned_staff_id", "status", "notes", "is_walkin",
    "checked_in_at", "created_at", "updated_at", "left_by", "left_at",
    "status_before_left",
)
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_appointments_date "
    "ON appointments(appointment_date, status)",
    "CREATE INDEX IF NOT EXISTS idx_appointments_queue "
    "ON appointments(appointment_date, status, checked_in_at)",
)
_MARKS = ", ".join("?" for _ in NEEDS_DOCTOR)
# A visit with a consultation record, no diagnosis, and a service that needs the Doctor.
_OWED = (
    "(a.appointment_type IS NULL OR TRIM(a.appointment_type) = '' "
    f"OR a.appointment_type IN ({_MARKS})) "
    "AND EXISTS (SELECT 1 FROM consultations c WHERE c.appointment_id = a.id "
    "AND TRIM(COALESCE(c.diagnosis, '')) = '')"
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
    result = {"database": db_path, "backup": None, "rows": 0, "converted": 0,
              "converted_left": 0, "closed_without_record": 0, "problems": []}
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
        copy_columns = ", ".join(c for c in COLUMNS if c in before[next(iter(before))]) \
            if before else ", ".join(COLUMNS)

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

            # Which visits the Doctor still owes a diagnosis.
            owed = [r["id"] for r in conn.execute(
                f"SELECT a.id FROM appointments a WHERE a.status = 'Completed' AND {_OWED}",
                NEEDS_DOCTOR)]
            owed_left = [r["id"] for r in conn.execute(
                "SELECT a.id FROM appointments a WHERE a.status = 'Left before being seen' "
                f"AND a.status_before_left = 'Completed' AND {_OWED}", NEEDS_DOCTOR)]
            result["closed_without_record"] = conn.execute(
                "SELECT COUNT(*) FROM appointments a WHERE a.status = 'Completed' "
                "AND NOT EXISTS (SELECT 1 FROM consultations c WHERE c.appointment_id = a.id)"
            ).fetchone()[0]
            if owed:
                conn.execute(
                    "UPDATE appointments SET status = ? WHERE id IN (%s)"
                    % ", ".join("?" for _ in owed), (NEW_STATUS, *owed))
            if owed_left:
                conn.execute(
                    "UPDATE appointments SET status_before_left = ? WHERE id IN (%s)"
                    % ", ".join("?" for _ in owed_left), (NEW_STATUS, *owed_left))
            result["converted"], result["converted_left"] = len(owed), len(owed_left)

            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_visit_service_and_doctor_status.py, "
                 f"not by this account. {len(owed)} completed visit"
                 f"{'' if len(owed) == 1 else 's'} with intake and no diagnosis "
                 f"{'was' if len(owed) == 1 else 'were'} moved to Waiting for the Doctor, "
                 f"and {len(owed_left)} marked as left before being seen "
                 f"{'was' if len(owed_left) == 1 else 'were'} set to return there on undo. "
                 "Staff now choose the service at check-in; a visit whose service needs "
                 "the Doctor waits in this status until the Doctor writes the diagnosis."))

            # Checks, before anything is committed.
            after = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM appointments")}
            if len(after) != len(before):
                problems.append("the row count changed")
            for row_id, old in before.items():
                new = after.get(row_id)
                if new is None:
                    problems.append("a row went missing")
                    break
                allowed = set()
                if row_id in owed:
                    allowed.add("status")
                if row_id in owed_left:
                    allowed.add("status_before_left")
                if any(new[c] != v for c, v in old.items() if c in new and c not in allowed):
                    problems.append("a value other than the converted ones changed")
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
    print(f"moved to Waiting for the Doctor: {result['converted']} completed visits")
    print(f"marked as left, set to return there on undo: {result['converted_left']}")
    print(f"left as Completed (closed with no record written): {result['closed_without_record']}")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
