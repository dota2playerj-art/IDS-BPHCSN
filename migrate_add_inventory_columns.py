"""Migration: extend inventory_items with the fields Add/Edit Medicine collects.

Screen 07's form collects nineteen values; `inventory_items` as first written held
nine of them. The eleven added here close that gap, so the form can round-trip a
record instead of silently dropping most of what the operator typed.

Idempotent -- re-running is a no-op. Uses ALTER TABLE ... ADD COLUMN so existing
inventory rows are preserved in place; the table is never dropped or recreated.
SQLite appends new columns at the end, so the live column order differs from the
grouped order in schema.sql. That difference is cosmetic -- same names, same
types, same constraints -- and all access is by column name.

Two columns deserve a note:

* `category` already existed and keeps its CHECK of Medicine/Supply/Equipment --
  that is the *item type*. The Add/Edit form's "Category" dropdown offers a
  different axis entirely (Antibiotic, Antihypertensive, ...), which is a
  therapeutic classification, so it gets its own `drug_class` column rather than
  being forced through a CHECK it does not satisfy.
* `status` mirrors patients.status: a soft Active/Inactive flag. Inventory rows
  are not hard-deleted here either.

Run:  python migrate_add_inventory_columns.py
"""
import sqlite3
import sys

import config

# (column_name, column_definition) in the order they are added.
NEW_COLUMNS = [
    ("generic_name", "TEXT"),
    ("brand_name", "TEXT"),
    ("drug_class", "TEXT"),
    ("dosage_strength", "TEXT"),
    ("dosage_form", "TEXT"),
    ("manufacturer", "TEXT"),
    ("batch_number", "TEXT"),
    ("date_received", "TEXT"),
    ("unit_cost", "REAL"),
    ("storage_location", "TEXT"),
    (
        "status",
        "TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive'))",
    ),
]


def existing_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(inventory_items)")}


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before_count = conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0]
    before_rows = {
        row["item_code"]: dict(row)
        for row in conn.execute("SELECT * FROM inventory_items ORDER BY id")
    }
    print(f"inventory_items before migration: {before_count}")

    present = existing_columns(conn)
    added, skipped = [], []
    for name, definition in NEW_COLUMNS:
        if name in present:
            skipped.append(name)
            continue
        conn.execute(f"ALTER TABLE inventory_items ADD COLUMN {name} {definition}")
        added.append(name)
    conn.commit()

    print(f"columns added:   {added if added else '(none)'}")
    print(f"already present: {skipped if skipped else '(none)'}")

    after_count = conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0]
    after_rows = {
        row["item_code"]: dict(row)
        for row in conn.execute("SELECT * FROM inventory_items ORDER BY id")
    }

    print(f"inventory_items after migration:  {after_count}")

    problems = []
    if before_count != after_count:
        problems.append(f"row count changed: {before_count} -> {after_count}")

    for code, old in before_rows.items():
        new = after_rows.get(code)
        if new is None:
            problems.append(f"{code} disappeared")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(f"{code}.{column}: {value!r} -> {new[column]!r}")

    non_active = conn.execute(
        "SELECT COUNT(*) FROM inventory_items WHERE status <> 'Active'"
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
