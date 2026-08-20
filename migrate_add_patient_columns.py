"""Migration: extend the patients table with the fields Register Patient collects.

Idempotent -- re-running is a no-op. Uses ALTER TABLE ... ADD COLUMN so the 15
existing patient records are preserved in place; the table is never dropped or
recreated.

SQLite appends new columns at the end of the table, so the live column order
differs from the grouped order in schema.sql. That difference is cosmetic --
same names, same types, same constraints -- and all access is by column name.

List-valued fields (medical_conditions, allergies) are stored as a JSON array of
strings, e.g. '["Hypertension", "Diabetes"]'. JSON rather than comma-separated
because the Register Patient form pairs fixed checkbox chips with a free-text
"other conditions" note, and that free text can itself contain commas.

Run:  python migrate_add_patient_columns.py
"""
import sqlite3
import sys

import config

# (column_name, column_definition) in the order they are added.
NEW_COLUMNS = [
    ("civil_status", "TEXT"),
    ("blood_type", "TEXT"),
    ("municipality", "TEXT"),
    ("province", "TEXT"),
    ("zip_code", "TEXT"),
    ("emergency_contact_relationship", "TEXT"),
    ("emergency_contact_address", "TEXT"),
    ("medical_conditions", "TEXT"),
    ("allergies", "TEXT"),
    (
        "status",
        "TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive', 'Deceased'))",
    ),
]
# The three values schema.sql's CHECK constraint permits -- the same set the
# status definition above declares. Named here so the verification below can
# tell "a status this schema does not allow" from "a status the clinic chose".
VALID_STATUSES = ("Active", "Inactive", "Deceased")


def existing_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(patients)")}


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    before_rows = {
        row["patient_id"]: dict(row)
        for row in conn.execute("SELECT * FROM patients ORDER BY id")
    }
    print(f"patients before migration: {before_count}")

    present = existing_columns(conn)
    added, skipped = [], []
    for name, definition in NEW_COLUMNS:
        if name in present:
            skipped.append(name)
            continue
        conn.execute(f"ALTER TABLE patients ADD COLUMN {name} {definition}")
        added.append(name)
    conn.commit()

    print(f"columns added:   {added if added else '(none)'}")
    print(f"already present: {skipped if skipped else '(none)'}")

    after_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    after_rows = {
        row["patient_id"]: dict(row)
        for row in conn.execute("SELECT * FROM patients ORDER BY id")
    }

    print(f"patients after migration:  {after_count}")

    problems = []
    if before_count != after_count:
        problems.append(f"row count changed: {before_count} -> {after_count}")

    for pid, old in before_rows.items():
        new = after_rows.get(pid)
        if new is None:
            problems.append(f"{pid} disappeared")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(f"{pid}.{column}: {value!r} -> {new[column]!r}")

    # Two different questions, and this check used to conflate them.
    #
    # On the run that ADDS the column, SQLite backfills every existing row
    # from the DEFAULT, so all of them must come out 'Active'. That is a real
    # invariant about this migration's own work, and it is still asserted --
    # but only on the run that does the adding.
    #
    # On a re-run the column is already there and the Patient Status feature
    # has been live in between. Health Center Staff and the Administrator can
    # move a record to Inactive or Deceased; schema.sql calls status "a soft
    # lifecycle flag: patient records are never hard-deleted", so those rows
    # are the feature working, not damage. Asserting they must all be 'Active'
    # made this script exit 1 against a database that was perfectly correct.
    #
    # What is worth catching on every run is a status the schema does not
    # permit. The CHECK constraint refuses one on write, but a CHECK is only
    # consulted on write: a value that predates the constraint, or one written
    # by a tool that went around it, would sit there unnoticed. NULL too.
    status_counts = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT status, COUNT(*) FROM patients GROUP BY status"
        )
    }

    for status, count in sorted(status_counts.items(), key=lambda kv: str(kv[0])):
        if status not in VALID_STATUSES:
            problems.append(
                f"{count} rows have status {status!r}, which the schema does "
                f"not permit (allowed: {', '.join(VALID_STATUSES)})"
            )

    if "status" in added:
        not_defaulted = sum(
            count for status, count in status_counts.items() if status != "Active"
        )
        if not_defaulted:
            problems.append(
                f"{not_defaulted} rows did not take the 'Active' default on "
                "the run that added the column"
            )

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    spread = ", ".join(
        f"{status}={status_counts.get(status, 0)}" for status in VALID_STATUSES
    )
    print("\nAll pre-existing column values preserved byte-for-byte; "
          f"every status is one the schema permits ({spread}).")


if __name__ == "__main__":
    main()
