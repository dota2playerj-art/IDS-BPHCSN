"""Migration: extend consultations with vitals, growth measures and follow-up.

`consultations` as first written held four clinical text fields -- chief
complaint, diagnosis, treatment plan and remarks. The Record Consultation form
captures what a barangay health worker actually writes down at the end of a
visit, which is those four plus the vital signs taken on the way in, the growth
measurements taken for young children, and the date the patient is told to come
back. The ten columns added here close that gap.

Idempotent -- re-running is a no-op. Uses ALTER TABLE ... ADD COLUMN so the five
existing consultation rows are preserved in place; the table is never dropped or
recreated. Same pattern as migrate_add_patient_columns.py and
migrate_add_inventory_columns.py, including the byte-for-byte verification at the
end. SQLite appends new columns, so the live column order differs from the
grouped order in schema.sql -- cosmetic, since all access is by name.

Run:  python migrate_add_consultation_columns.py


UNITS ARE FIXED, NOT STORED
---------------------------
temperature is degrees Celsius, weight kilograms, height and head_circumference
centimetres, pulse_rate beats per minute, respiratory_rate breaths per minute.
One health center, one set of instruments, one convention -- storing a unit
alongside each number would invite two rows in different units and no way to
compare them. The form labels every field with its unit so nothing is implied.

blood_pressure is TEXT, not two numbers. It is read and written as one reading
("120/80"); splitting it into systolic and diastolic columns would let a row hold
one without the other, which is not a blood pressure. The form validates the
shape and the plausible range of both halves before it gets here.

THE TWO PEDIATRIC COLUMNS
-------------------------
height is recorded for children under five and head_circumference for infants
under one -- see PEDIATRIC_AGE_YEARS in models/consultations.py for why those
boundaries. They are plain nullable columns like the rest: the age rule is a
property of the patient on the day of the visit, not of the column, and freezing
it into the schema would mean a CHECK that has to be rebuilt if the programme's
cohort ever changes.

appointment_id ties a consultation back to the queue entry it documents. Without
it there is no way to tell which visit a record belongs to, and nothing stops the
same queue entry being written up twice. Nullable, because the five seeded rows
predate the queue and a consultation can legitimately be recorded outside it.

updated_at cannot take DEFAULT CURRENT_TIMESTAMP here: SQLite rejects a
non-constant default in ADD COLUMN. It is therefore added plain and backfilled
from each row's created_at, so no row is left NULL, and every write sets it
explicitly. schema.sql gives fresh installs the NOT NULL DEFAULT that patients
and inventory_items already carry; that constraint difference between a migrated
and a fresh database is deliberate and is the only one.
"""
import sqlite3
import sys

import config

# (column_name, column_definition) in the order they are added.
NEW_COLUMNS = [
    # Vital signs, taken at the start of every consultation.
    ("temperature", "REAL"),
    ("blood_pressure", "TEXT"),
    ("pulse_rate", "INTEGER"),
    ("respiratory_rate", "INTEGER"),
    ("weight", "REAL"),
    # Growth measurements, for the paediatric cohort only.
    ("height", "REAL"),
    ("head_circumference", "REAL"),
    # When the patient was told to come back, if they were.
    ("follow_up_date", "TEXT"),
    # The queue entry this consultation documents.
    ("appointment_id", "INTEGER REFERENCES appointments(id) ON DELETE SET NULL"),
    # Last edit. See the module note on why this cannot be NOT NULL here.
    ("updated_at", "TEXT"),
]


def existing_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(consultations)")}


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before_count = conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    before_rows = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM consultations ORDER BY id")
    }
    print(f"consultations before migration: {before_count}")

    present = existing_columns(conn)
    added, skipped = [], []
    for name, definition in NEW_COLUMNS:
        if name in present:
            skipped.append(name)
            continue
        conn.execute(f"ALTER TABLE consultations ADD COLUMN {name} {definition}")
        added.append(name)
    conn.commit()

    print(f"columns added:   {added if added else '(none)'}")
    print(f"already present: {skipped if skipped else '(none)'}")

    # Kept in step with schema.sql so a migrated database and a fresh one carry
    # the same indexes. IF NOT EXISTS makes the second run a no-op.
    #
    # Both are asserted, not just the new one: idx_consultations_patient_date
    # predates this migration, but asserting an index the script does not also
    # ensure would fail on any database that reached here by a route other than
    # the current schema.sql -- which is exactly the situation a migration is for.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_consultations_patient_date "
        "ON consultations(patient_id, consultation_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_consultations_appointment "
        "ON consultations(appointment_id)"
    )
    conn.commit()

    # Backfill updated_at from created_at: an unedited record was last changed
    # when it was written. Only touches rows where it is still NULL, so a second
    # run cannot overwrite a real edit timestamp.
    backfilled = conn.execute(
        "UPDATE consultations SET updated_at = created_at WHERE updated_at IS NULL"
    ).rowcount
    conn.commit()
    print(f"updated_at backfilled from created_at on {backfilled} row(s)")

    after_count = conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    after_rows = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM consultations ORDER BY id")
    }
    print(f"consultations after migration:  {after_count}")

    problems = []
    if before_count != after_count:
        problems.append(f"row count changed: {before_count} -> {after_count}")

    # Every value that existed before must still be exactly what it was. The
    # backfilled updated_at is the one column allowed to appear, and only where
    # it was absent entirely.
    for consultation_id, old in before_rows.items():
        new = after_rows.get(consultation_id)
        if new is None:
            problems.append(f"consultation id={consultation_id} disappeared")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(f"id={consultation_id}.{column}: {value!r} -> {new[column]!r}")

    # The clinical columns the seeded rows carry must be intact, not merely equal
    # to a blank they were silently reset to.
    populated = conn.execute(
        "SELECT COUNT(*) FROM consultations "
        "WHERE chief_complaint IS NOT NULL AND diagnosis IS NOT NULL"
    ).fetchone()[0]
    if populated != before_count:
        problems.append(
            f"{before_count - populated} pre-existing rows lost their clinical text"
        )

    null_updated = conn.execute(
        "SELECT COUNT(*) FROM consultations WHERE updated_at IS NULL"
    ).fetchone()[0]
    if null_updated:
        problems.append(f"{null_updated} rows still have a NULL updated_at")

    # The new columns must exist on the table.
    live = existing_columns(conn)
    for name, _ in NEW_COLUMNS:
        if name not in live:
            problems.append(f"column {name} missing after migration")
    live_indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='consultations'"
        )
    }
    for expected in ("idx_consultations_patient_date", "idx_consultations_appointment"):
        if expected not in live_indexes:
            problems.append(f"index {expected} missing after migration")

    # A migration that invented a vital sign would be worse than one that failed,
    # so the rows that existed beforehand must come out of it with the new
    # columns still empty.
    #
    # Scoped to the run that actually adds the columns. On a re-run they are
    # already there, and by then the health center has been using the form -- a
    # consultation recorded through the UI legitimately holds a temperature, and
    # counting those as "invented" would turn every later run into a false
    # failure. The byte-for-byte comparison above is what protects those rows
    # once the columns exist: it proves this run changed none of them.
    if added:
        fabricated = conn.execute(
            "SELECT COUNT(*) FROM consultations WHERE temperature IS NOT NULL "
            "OR blood_pressure IS NOT NULL OR pulse_rate IS NOT NULL "
            "OR respiratory_rate IS NOT NULL OR weight IS NOT NULL OR height IS NOT NULL "
            "OR head_circumference IS NOT NULL OR follow_up_date IS NOT NULL"
        ).fetchone()[0]
        if fabricated:
            problems.append(
                f"{fabricated} pre-existing rows came out with clinical values invented"
            )
    else:
        print("clinical columns already present — pre-existing values verified "
              "byte-for-byte above rather than re-checked as empty")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print(
        f"\nAll {before_count} pre-existing consultations preserved byte-for-byte; "
        + ("new clinical columns present and empty; "
           if added else "clinical columns already present and unchanged; ")
        + "updated_at populated on every row."
    )


if __name__ == "__main__":
    main()
