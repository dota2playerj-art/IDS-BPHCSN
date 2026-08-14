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

    non_active = conn.execute(
        "SELECT COUNT(*) FROM patients WHERE status <> 'Active'"
    ).fetchone()[0]
    if non_active:
        problems.append(f"{non_active} rows did not take the 'Active' default")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print("\nAll pre-existing column values preserved byte-for-byte; "
          "every row defaulted to status='Active'.")


if __name__ == "__main__":
    main()
