"""Migration: the stored civil status "Minor" becomes "Single" (Task 22).

"Minor" is an age, not a civil status, and a child saved as "Minor" stayed "Minor" after turning
18. Under Republic Act No. 11596 a person under 18 cannot marry, so "Single" is what such a record
should always have said. Only patients.civil_status changes, and only where it is "Minor": no
other column of those rows (not even updated_at) and no other row is touched.

Run: python migrations/migrate_civil_status_minor_to_single.py [database] (project root). The
database defaults to app.db. Safe to run twice: it backs the database up first, does nothing when
no "Minor" is left, and writes one audit entry giving the count (no names).
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
TASK = "civil_status_minor"

# Written out here on purpose: a migration must keep working when the application's lists change.
OLD_VALUE = "Minor"
NEW_VALUE = "Single"

ACTION = "Changed civil status Minor to Single"
MODULE = "Patient Records"


def needs_work(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM patients WHERE civil_status = ?", (OLD_VALUE,)).fetchone()[0] > 0


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
    result = {"database": db_path, "backup": None, "changed": 0, "problems": []}
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        if not needs_work(conn):
            return result
        result["backup"] = str(_backup(db_path, backup_dir))
        before = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM patients")}
        targets = {row_id for row_id, row in before.items() if row["civil_status"] == OLD_VALUE}
        audit_before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        actor = conn.execute(
            "SELECT id FROM users WHERE role = 'Admin' AND is_active = 1 "
            "ORDER BY id LIMIT 1").fetchone()
        if actor is None:
            raise SystemExit("Stopped. No active Administrator account to file the entry under.")
        problems = result["problems"]

        conn.execute("BEGIN")
        try:
            changed = conn.execute(
                "UPDATE patients SET civil_status = ? WHERE civil_status = ?",
                (NEW_VALUE, OLD_VALUE)).rowcount
            result["changed"] = changed
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_civil_status_minor_to_single.py, not by "
                 f"this account. {changed} patient record{'' if changed == 1 else 's'} had the "
                 "civil status \"Minor\", which is an age, not a civil status; each is now "
                 "\"Single\" (a person under 18 cannot marry, RA 11596). No other value changed."))

            # Checks, before anything is committed.
            after = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM patients")}
            if set(after) != set(before):
                problems.append("the set of patient rows changed")
            for row_id, old in before.items():
                new = after.get(row_id, {})
                for column, value in old.items():
                    expected = NEW_VALUE if (row_id in targets and column == "civil_status") else value
                    if new.get(column) != expected:
                        problems.append(f"patient row {row_id}: {column} is not what it should be")
                        break
            if changed != len(targets):
                problems.append("the number of rows changed is not the number holding Minor")
            if conn.execute("SELECT COUNT(*) FROM patients WHERE civil_status = ?",
                            (OLD_VALUE,)).fetchone()[0]:
                problems.append("a Minor is left")
            if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] != audit_before + 1:
                problems.append("the audit table did not gain exactly one row")
            conn.execute("ROLLBACK" if problems else "COMMIT")
            if problems:
                result["changed"] = 0
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
        print("Nothing to do. No patient has the civil status Minor.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"patient records changed from Minor to Single: {result['changed']}")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
