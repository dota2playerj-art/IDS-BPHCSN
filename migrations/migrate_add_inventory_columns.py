"""Migration: extend inventory_items with the fields Add/Edit Medicine collects.

Screen 07's form collects nineteen values; `inventory_items` as first written held
nine of them. The eleven added here close that gap, so the form can round-trip a
record instead of silently dropping most of what the operator typed.

Run: python migrations/migrate_add_inventory_columns.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
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
# The two values schema.sql's CHECK constraint permits -- the same set the
# status definition above declares. Named here so the verification below can
# tell "a status this schema does not allow" from "a status the clinic chose".
# Two, not three: an item is in service or retired. Patients have a third.
VALID_STATUSES = ("Active", "Inactive")


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

    # Two different questions, and this check used to conflate them. This is
    # the same split migrate_add_patient_columns.py makes, for the same reason.
    #
    # On the run that ADDS the column, SQLite backfills every existing row
    # from the DEFAULT, so all of them must come out 'Active'. That is a real
    # invariant about this migration's own work, and it is still asserted --
    # but only on the run that does the adding.
    #
    # On a re-run the column is already there and Add / Edit Medicine has been
    # live in between. Its Status field offers both values, models.inventory
    # names 'Inactive' RETIRED_STATUS, and an item set to it is badged Retired
    # and taken out of every operating figure. schema.sql calls status "a soft
    # lifecycle flag, as on patients: inventory rows are not hard-deleted", so
    # a retired medicine is the feature working, not damage. The patient copy
    # of this check exited 1 against a perfectly correct database for exactly
    # this reason; here it has stayed quiet only because nothing has been
    # retired yet.
    #
    # What is worth catching on every run is a status the schema does not
    # permit. The CHECK constraint refuses one on write, but a CHECK is only
    # consulted on write: a value that predates the constraint, or one written
    # by a tool that went around it, would sit there unnoticed. NULL too.
    status_counts = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT status, COUNT(*) FROM inventory_items GROUP BY status"
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
