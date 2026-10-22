"""Migration: patients get a barangay column (Task 22).

The address is now chosen Province -> City/Municipality -> Barangay. The barangay used to be a
fixed, disabled box on the form that was never stored, so there was no column to keep it in.
This adds one nullable TEXT column, patients.barangay, and nothing else: no stored address is
changed or filled in. Records saved before it have no barangay; Edit Patient asks for one.

Run: python migrations/migrate_add_patient_barangay.py [database] (project root). The database
defaults to app.db. Safe to run twice: it backs the database up first, does nothing when the
column is already there, and writes one audit entry.
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
TASK = "patient_barangay"

COLUMN = "barangay"
ACTION = "Added the barangay to patient addresses"
MODULE = "Patient Records"


def _columns(conn):
    return [r[1] for r in conn.execute("PRAGMA table_info(patients)")]


def needs_work(conn):
    return COLUMN not in _columns(conn)


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
        before = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM patients")}
        result["rows"] = len(before)
        audit_before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        actor = conn.execute(
            "SELECT id FROM users WHERE role = 'Admin' AND is_active = 1 "
            "ORDER BY id LIMIT 1").fetchone()
        if actor is None:
            raise SystemExit("Stopped. No active Administrator account to file the entry under.")
        problems = result["problems"]

        conn.execute("BEGIN")
        try:
            conn.execute(f"ALTER TABLE patients ADD COLUMN {COLUMN} TEXT")
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_add_patient_barangay.py, not by this "
                 "account. Patient records can now store the barangay. No stored address was "
                 f"changed: the {len(before)} existing record{'' if len(before) == 1 else 's'} "
                 "have no barangay until someone edits them."))

            # Checks, before anything is committed.
            after = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM patients")}
            if set(after) != set(before):
                problems.append("the set of patient rows changed")
            for row_id, old in before.items():
                new = after[row_id]
                if any(new[c] != v for c, v in old.items()) or new[COLUMN] is not None:
                    problems.append("a stored value changed")
                    break
            if _columns(conn)[-1] != COLUMN:
                problems.append("the column is not there")
            if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] != audit_before + 1:
                problems.append("the audit table did not gain exactly one row")
            conn.execute("ROLLBACK" if problems else "COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
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
        print("Nothing to do. The barangay column is already there.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"barangay column added; {result['rows']} patient rows kept as they were (barangay empty).")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
