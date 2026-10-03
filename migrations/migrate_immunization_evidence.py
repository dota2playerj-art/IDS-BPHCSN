"""Migration: what each immunisation record rests on (Task 9, honest immunization status).

`source` ('administered' / 'reported') becomes `evidence` ('given_here' / 'card' /
'parent_report'), and a dose gets an optional `place_given`. Every dose given here
becomes 'given_here'; every dose that was reported as given elsewhere becomes 'card'
(the decision of the Task 9 brief). The rows are carried across by name and checked.

The database defaults to app.db (config.DATABASE). A copy is saved first in the
IDS-BPHCSN-backups folder next to the project.

Run: python migrations/migrate_immunization_evidence.py (project root). Safe to run twice.
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
TASK = "immunization-evidence"

ACTION = "Changed how immunisation records are classified"
MODULE = "Immunization Records"

# The table as schema.sql declares it. The vocabulary is written out here on purpose: a
# migration must keep working when the application's constants change later.
NEW_TABLE_SQL = """
CREATE TABLE immunizations_migrated (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    vaccine_code TEXT NOT NULL,
    dose_number INTEGER NOT NULL,
    evidence TEXT NOT NULL DEFAULT 'given_here'
        CHECK (evidence IN ('given_here', 'card', 'parent_report')),
    date_administered TEXT,
    place_given TEXT,
    administered_by INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (evidence <> 'given_here' OR date_administered IS NOT NULL),
    UNIQUE (patient_id, vaccine_code, dose_number),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""
COLUMNS = ("id", "patient_id", "consultation_id", "vaccine_code", "dose_number",
           "date_administered", "administered_by", "notes", "created_at")
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_immunizations_patient "
    "ON immunizations(patient_id, date_administered)",
    "CREATE INDEX IF NOT EXISTS idx_immunizations_consultation "
    "ON immunizations(consultation_id)",
)


def needs_work(conn):
    return "evidence" not in {row[1] for row in conn.execute("PRAGMA table_info(immunizations)")}


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


def _probe_checks(conn, problems):
    """The CHECKs must admit the new values and refuse a made-up one and an undated dose here."""
    anchor = conn.execute(
        "SELECT (SELECT id FROM patients LIMIT 1), (SELECT id FROM users LIMIT 1)").fetchone()
    if anchor[0] is None or anchor[1] is None:
        return  # an empty database has nothing to point a probe row at
    probes = (("card", "2026-01-01", True), ("parent_report", None, True),
              ("given_here", None, False), ("guessed", "2026-01-01", False))
    for evidence, day, should_pass in probes:
        conn.execute("SAVEPOINT probe")
        try:
            conn.execute(
                "INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, "
                "date_administered, administered_by) VALUES (?, 'ZZPROBE', 1, ?, ?, ?)",
                (anchor[0], evidence, day, anchor[1]))
            if not should_pass:
                problems.append(f"the CHECK accepted {evidence} with date {day}")
        except sqlite3.IntegrityError:
            if should_pass:
                problems.append(f"the CHECK refused {evidence} with date {day}")
        conn.execute("ROLLBACK TO probe")
        conn.execute("RELEASE probe")


def run(db_path, backup_dir=BACKUP_DIR):
    """Apply the migration. Returns a dict describing what happened."""
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise SystemExit(f"No database at {db_path}")
    result = {"database": db_path, "backup": None, "rows": 0, "given_here": 0, "card": 0,
              "card_without_date": 0, "problems": []}
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        if not needs_work(conn):
            return result
        result["backup"] = str(_backup(db_path, backup_dir))
        before = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM immunizations")}
        result["rows"] = len(before)
        audit_before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        actor = conn.execute(
            "SELECT id FROM users WHERE role = 'Admin' AND is_active = 1 "
            "ORDER BY id LIMIT 1").fetchone()
        if actor is None:
            raise SystemExit("Stopped. No active Administrator account to file the entry under.")
        problems = result["problems"]
        columns = ", ".join(COLUMNS)

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            conn.execute(NEW_TABLE_SQL)
            # The evidence is set in the INSERT itself: a reported dose with no date is a
            # valid card row, and it would break the given-here CHECK if it were copied
            # first with the default and changed afterwards.
            conn.execute(
                f"INSERT INTO immunizations_migrated ({columns}, evidence) "
                f"SELECT {columns}, CASE source WHEN 'reported' THEN 'card' ELSE 'given_here' END "
                "FROM immunizations")
            conn.execute("DROP TABLE immunizations")
            conn.execute("ALTER TABLE immunizations_migrated RENAME TO immunizations")
            for statement in INDEXES:
                conn.execute(statement)

            result["given_here"] = conn.execute(
                "SELECT COUNT(*) FROM immunizations WHERE evidence = 'given_here'").fetchone()[0]
            result["card"] = conn.execute(
                "SELECT COUNT(*) FROM immunizations WHERE evidence = 'card'").fetchone()[0]
            result["card_without_date"] = conn.execute(
                "SELECT COUNT(*) FROM immunizations WHERE evidence = 'card' "
                "AND date_administered IS NULL").fetchone()[0]
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_immunization_evidence.py, not by this "
                 f"account. {result['given_here']} dose{'' if result['given_here'] == 1 else 's'} "
                 "marked given here and "
                 f"{result['card']} dose{'' if result['card'] == 1 else 's'} reported as given "
                 "elsewhere marked as seen on a card. A dose now says what its record rests on: "
                 "given here, a vaccination card, or a parent's report."))

            # Checks, before anything is committed.
            after = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM immunizations")}
            if len(after) != len(before):
                problems.append("the row count changed")
            for row_id, old in before.items():
                new = after.get(row_id)
                if new is None:
                    problems.append("a row went missing")
                    break
                expected = "card" if old["source"] == "reported" else "given_here"
                if new["evidence"] != expected:
                    problems.append("a row got the wrong evidence")
                    break
                if any(new[c] != old[c] for c in COLUMNS):
                    problems.append("a value other than the evidence changed")
                    break
            if result["given_here"] + result["card"] != len(before):
                problems.append("the two evidence counts do not add up to the rows")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                problems.append("foreign_key_check found a violation")
            have = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='immunizations'")}
            if not {"idx_immunizations_patient", "idx_immunizations_consultation"} <= have:
                problems.append("an index is missing")
            if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] != audit_before + 1:
                problems.append("the audit table did not gain exactly one row")
            _probe_checks(conn, problems)
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
        print("Nothing to do. The evidence column is already there.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"immunizations rebuilt: {result['rows']} rows")
    print(f"given here: {result['given_here']}")
    print(f"card (was reported as given elsewhere): {result['card']}"
          f" ({result['card_without_date']} without a date)")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
