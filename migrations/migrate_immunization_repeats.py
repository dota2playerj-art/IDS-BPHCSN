"""Migration: a dose may have more than one record, so a dose given too early can be repeated
(Task 14, L54).

The immunizations table used to refuse a second record of the same dose (UNIQUE on patient,
vaccine and dose number). A dose given before its minimum age or interval does not count and
must be repeated, and the repeat is a new record beside the early one. The constraint is
dropped; a partial unique index keeps one parent's report per dose. Every record is carried
across with its id and checked.

The database defaults to app.db (config.DATABASE). A copy is saved first in the
IDS-BPHCSN-backups folder next to the project.

Run: python migrations/migrate_immunization_repeats.py (project root). Safe to run twice.
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
TASK = "immunization-repeats"

ACTION = "Changed how repeated immunisation doses are stored"
MODULE = "Immunization Records"

# The table as schema.sql declares it. Written out here on purpose: a migration must keep
# working when the application's constants change later.
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
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""
COLUMNS = ("id", "patient_id", "consultation_id", "vaccine_code", "dose_number", "evidence",
           "date_administered", "place_given", "administered_by", "notes", "created_at")
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_immunizations_patient "
    "ON immunizations(patient_id, date_administered)",
    "CREATE INDEX IF NOT EXISTS idx_immunizations_consultation "
    "ON immunizations(consultation_id)",
    "CREATE INDEX IF NOT EXISTS idx_immunizations_dose "
    "ON immunizations(patient_id, vaccine_code, dose_number)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_immunizations_one_parent_report "
    "ON immunizations(patient_id, vaccine_code, dose_number) WHERE evidence = 'parent_report'",
)
INDEX_NAMES = ("idx_immunizations_patient", "idx_immunizations_consultation",
               "idx_immunizations_dose", "idx_immunizations_one_parent_report")


def needs_work(conn):
    """True while the table still carries the one-record-per-dose constraint: a unique index
    made by the table itself over exactly patient, vaccine and dose number."""
    for index in conn.execute("PRAGMA index_list(immunizations)").fetchall():
        # columns: seq, name, unique, origin, partial
        if index[2] and index[3] == "u":
            columns = [row[2] for row in conn.execute(f"PRAGMA index_info('{index[1]}')")]
            if columns == ["patient_id", "vaccine_code", "dose_number"]:
                return True
    return False


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


def _probe(conn, problems):
    """The new table must take two records of one dose, refuse two parent's reports of one
    dose, and still refuse a made-up evidence value and an undated dose given here."""
    anchor = conn.execute(
        "SELECT (SELECT id FROM patients LIMIT 1), (SELECT id FROM users LIMIT 1)").fetchone()
    if anchor[0] is None or anchor[1] is None:
        return  # an empty database has nothing to point a probe row at
    insert = ("INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, "
              "date_administered, administered_by) VALUES (?, 'ZZPROBE', 1, ?, ?, ?)")
    cases = (
        ((("given_here", "2026-01-01"), ("given_here", "2026-03-01")), True,
         "the table still refuses two records of one dose"),
        ((("parent_report", None), ("parent_report", None)), False,
         "the table accepted two parent's reports of one dose"),
        ((("guessed", "2026-01-01"),), False, "the CHECK accepted a made-up evidence value"),
        ((("given_here", None),), False, "the CHECK accepted a dose given here with no date"),
    )
    for rows, should_pass, message in cases:
        conn.execute("SAVEPOINT probe")
        try:
            for evidence, day in rows:
                conn.execute(insert, (anchor[0], evidence, day, anchor[1]))
            if not should_pass:
                problems.append(message)
        except sqlite3.IntegrityError:
            if should_pass:
                problems.append(message)
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
        before = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM immunizations")}
        result["rows"] = len(before)
        old_sequence = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'immunizations'").fetchone()
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
            conn.execute(f"INSERT INTO immunizations_migrated ({columns}) "
                         f"SELECT {columns} FROM immunizations")
            conn.execute("DROP TABLE immunizations")
            conn.execute("ALTER TABLE immunizations_migrated RENAME TO immunizations")
            for statement in INDEXES:
                conn.execute(statement)
            # New ids must carry on from where the old table stopped, even if its last
            # rows had been removed.
            if old_sequence is not None:
                conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'immunizations'",
                             (old_sequence[0],))
            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_immunization_repeats.py, not by this "
                 f"account. {len(before)} dose record{'' if len(before) == 1 else 's'} kept. A dose "
                 "can now have more than one record, so a dose given too early can be repeated "
                 "and the early record stays as history."))

            # Checks, before anything is committed.
            after = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM immunizations")}
            if len(after) != len(before):
                problems.append("the row count changed")
            for row_id, old in before.items():
                if after.get(row_id) != old:
                    problems.append("a row went missing or a value changed")
                    break
            if needs_work(conn):
                problems.append("the one-record-per-dose constraint is still there")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                problems.append("foreign_key_check found a violation")
            have = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='immunizations'")}
            if not set(INDEX_NAMES) <= have:
                problems.append("an index is missing")
            if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] != audit_before + 1:
                problems.append("the audit table did not gain exactly one row")
            _probe(conn, problems)
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
        print("Nothing to do. A dose can already have more than one record.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"immunizations rebuilt: {result['rows']} rows, every value unchanged")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
