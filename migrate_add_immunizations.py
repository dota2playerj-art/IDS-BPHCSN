"""Migration: add the immunizations table.

Pass 3b records which DOH EPI doses a child has actually received. That is a
per-patient clinical fact with an author and a date, so it needs a table; the
schedule it is measured against does not, and lives as EPI_SCHEDULE in
models/immunizations.py -- see the note at the top of that module for why.

Idempotent -- re-running is a no-op. This is the first migration in the project
to add a whole table rather than columns, so it uses CREATE TABLE IF NOT EXISTS
where the three ALTER TABLE ... ADD COLUMN migrations used a column check. The
verification half follows them exactly: snapshot every existing table before,
compare after, and prove the new constraints actually refuse bad data rather than
merely being spelled out in the DDL.

WHAT THE CONSTRAINTS ARE FOR
----------------------------
UNIQUE (patient_id, vaccine_code, dose_number) is the clinically important one:
a child cannot be given the same dose of the same vaccine twice, and a schema
that allows it will eventually hold it. With the constraint, a double-submitted
form is absorbed by INSERT OR IGNORE instead of quietly duplicating a dose and
making a defaulting child look up to date.

consultation_id is ON DELETE SET NULL rather than CASCADE. If a consultation
record were ever removed, the vaccination still happened -- the dose must survive
losing its paperwork. patient_id is ON DELETE CASCADE, matching consultations:
patients are never hard-deleted in this system, so that path is theoretical, and
where it is used elsewhere it means the same thing.

administered_by is ON DELETE RESTRICT, matching consultations.recorded_by: a user
account cannot be deleted out from under a clinical record that names them.

Run:  python migrate_add_immunizations.py
"""
import sqlite3
import sys

import config

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS immunizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    consultation_id INTEGER,
    vaccine_code TEXT NOT NULL,
    dose_number INTEGER NOT NULL,
    date_administered TEXT NOT NULL,
    administered_by INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (patient_id, vaccine_code, dose_number),
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (consultation_id) REFERENCES consultations(id) ON DELETE SET NULL,
    FOREIGN KEY (administered_by) REFERENCES users(id) ON DELETE RESTRICT
)
"""

INDEXES = (
    # The profile tab and the schedule calculation both read one child's doses.
    "CREATE INDEX IF NOT EXISTS idx_immunizations_patient "
    "ON immunizations(patient_id, date_administered)",
    # The consultation form reads back what was given during one visit.
    "CREATE INDEX IF NOT EXISTS idx_immunizations_consultation "
    "ON immunizations(consultation_id)",
)

# Every table whose contents must be exactly what they were. Adding a table can
# only damage the others through a mistake, but "can only" is what verification
# is for.
EXISTING_TABLES = (
    "users", "patients", "consultations", "inventory_items", "appointments",
    "audit_logs", "schedule_logs", "settings",
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

    before = {table: snapshot(conn, table) for table in EXISTING_TABLES}
    existed = "immunizations" in table_names(conn)
    print(f"immunizations table before migration: {'present' if existed else 'absent'}")
    for table, rows in before.items():
        print(f"  {table:<16} {len(rows) if rows is not None else '(missing)'} rows")

    conn.execute(TABLE_SQL)
    for statement in INDEXES:
        conn.execute(statement)
    conn.commit()

    print(f"\nimmunizations table after migration: "
          f"{'present' if 'immunizations' in table_names(conn) else 'MISSING'}")
    print(f"immunization rows: {conn.execute('SELECT COUNT(*) FROM immunizations').fetchone()[0]}")

    problems = []

    if "immunizations" not in table_names(conn):
        problems.append("immunizations table was not created")

    # --- nothing that already existed may have moved ------------------------
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
                    problems.append(f"{table} id={row_id}.{column}: {value!r} -> {new_row[column]!r}")

    columns = [row[1] for row in conn.execute("PRAGMA table_info(immunizations)")]
    expected = ["id", "patient_id", "consultation_id", "vaccine_code", "dose_number",
                "date_administered", "administered_by", "notes", "created_at"]
    if columns != expected:
        problems.append(f"columns are {columns}, expected {expected}")

    live_indexes = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='immunizations'"
        )
    }
    for name in ("idx_immunizations_patient", "idx_immunizations_consultation"):
        if name not in live_indexes:
            problems.append(f"index {name} missing after migration")

    # --- the constraints have to actually refuse, not merely be written -----
    #
    # Probes need a real patient and a real user to point at, so a database
    # migrated before anyone is registered simply skips them rather than
    # reporting a failure -- the same allowance migrate_add_appointment_queue.py
    # makes for its CHECK probe.
    anchor = conn.execute(
        "SELECT (SELECT id FROM patients LIMIT 1) AS patient_id, "
        "       (SELECT id FROM users LIMIT 1) AS user_id"
    ).fetchone()

    if anchor["patient_id"] is None or anchor["user_id"] is None:
        print("constraints: not probed (no patient/user row to reference); DDL verified above")
    else:
        # UNIQUE must reject the same dose twice for the same child.
        try:
            conn.execute("BEGIN")
            for _ in range(2):
                conn.execute(
                    "INSERT INTO immunizations "
                    "(patient_id, vaccine_code, dose_number, date_administered, administered_by) "
                    "VALUES (?, '__PROBE__', 1, '2026-01-01', ?)",
                    (anchor["patient_id"], anchor["user_id"]),
                )
            conn.execute("ROLLBACK")
            problems.append("UNIQUE did not reject a duplicate dose")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "UNIQUE constraint failed" not in str(exc):
                problems.append(f"duplicate dose was rejected, but by {exc} rather than UNIQUE")
            else:
                print("UNIQUE (patient, vaccine, dose): rejects a repeated dose")

        # NOT NULL must reject a dose with no date.
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO immunizations "
                "(patient_id, vaccine_code, dose_number, date_administered, administered_by) "
                "VALUES (?, '__PROBE__', 2, NULL, ?)",
                (anchor["patient_id"], anchor["user_id"]),
            )
            conn.execute("ROLLBACK")
            problems.append("NOT NULL did not reject a dose with no date")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            if "NOT NULL constraint failed" not in str(exc):
                problems.append(f"undated dose rejected by {exc} rather than NOT NULL")
            else:
                print("NOT NULL (date_administered): rejects an undated dose")

        left_behind = conn.execute(
            "SELECT COUNT(*) FROM immunizations WHERE vaccine_code = '__PROBE__'"
        ).fetchone()[0]
        if left_behind:
            problems.append(f"{left_behind} probe rows survived their rollback")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\nimmunizations table present with its indexes and working constraints; "
          "every pre-existing table unchanged row for row.")


if __name__ == "__main__":
    main()
