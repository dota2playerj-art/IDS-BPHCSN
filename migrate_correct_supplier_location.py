"""Migration: repair the three inventory rows naming the wrong province.

Companion to migrate_correct_patient_location.py, which fixed the same error in
the patients table. Three stock items record their supplier as "Provincial
Health Office - Agusan del Sur". The health center is in San Francisco (formerly
Anao-Aon), Surigao del Norte, so the provincial health office that supplies it is
Surigao del Norte's. Agusan del Sur was the invented location this project was
built around; see that script's header for where it came from.

populate_records.py seeds these three strings and has been corrected alongside
this script, so a database rebuilt from scratch comes out right. This exists for
the database that is already here, which a reseed would not touch -- the seeder
uses INSERT OR IGNORE on rows that already exist.

Only inventory_items.supplier is written, and only on the three item codes named
in CORRECTIONS. Every other column of those rows, and every other row in the
table, is verified byte-for-byte unchanged.

Idempotent -- re-running is a no-op. A row already carrying the corrected string
is skipped; a row matching neither the expected before-state nor the after-state
is reported and left alone rather than overwritten.

Run:  python migrate_correct_supplier_location.py
"""
import sqlite3
import sys

import config

WRONG = "Provincial Health Office - Agusan del Sur"
RIGHT = "Provincial Health Office - Surigao del Norte"

# item_code -> (name, expected before, intended after). Spelled out per row, as
# in the patient migration, so the change to each item is reviewable here and in
# the commit without running anything.
CORRECTIONS = {
    "MED-0003": ("Cotrimoxazole", WRONG, RIGHT),
    "MED-0007": ("Metformin", WRONG, RIGHT),
    "MED-0012": ("Salbutamol Nebule", WRONG, RIGHT),
}


def snapshot(conn):
    return {
        row["item_code"]: dict(row)
        for row in conn.execute("SELECT * FROM inventory_items ORDER BY id")
    }


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before = snapshot(conn)
    print(f"inventory items before migration: {len(before)}")

    applied, already, mismatched, missing = [], [], [], []

    for item_code, (name, expected, corrected) in CORRECTIONS.items():
        row = before.get(item_code)
        if row is None:
            missing.append(item_code)
            continue
        current = row["supplier"]
        if current == corrected:
            already.append(item_code)
            continue
        if current != expected:
            mismatched.append((item_code, current, expected))
            continue
        conn.execute(
            "UPDATE inventory_items SET supplier = ? WHERE item_code = ?",
            (corrected, item_code),
        )
        applied.append((item_code, name, current, corrected))

    conn.commit()

    print(f"records corrected:  {len(applied)}")
    for item_code, name, was, now in applied:
        print(f"  {item_code} {name}:")
        print(f"      {was!r}")
        print(f"   -> {now!r}")
    if already:
        print(f"already correct:    {len(already)} ({', '.join(already)})")
    if mismatched:
        print(f"left alone:         {len(mismatched)}")
        for item_code, current, expected in mismatched:
            print(f"  {item_code}: holds {current!r}, expected {expected!r} -- not touched")
    if missing:
        print(f"not in database:    {', '.join(missing)}")

    after = snapshot(conn)
    problems = []

    if len(before) != len(after):
        problems.append(f"row count changed: {len(before)} -> {len(after)}")

    untouched = 0
    for item_code, old in before.items():
        new = after.get(item_code)
        if new is None:
            problems.append(f"{item_code} disappeared")
            continue
        changed = [c for c, v in old.items() if new[c] != v]
        if not changed:
            untouched += 1
            continue
        if item_code not in CORRECTIONS:
            problems.append(f"{item_code} was not in scope but changed: {changed}")
            continue
        for column in changed:
            if column != "supplier":
                problems.append(
                    f"{item_code}.{column}: {old[column]!r} -> {new[column]!r} "
                    "(outside this migration's remit)"
                )

    # The point of the exercise: no supplier anywhere may still name the wrong
    # province. This catches a fourth row the audit did not find as well as an
    # incomplete run of this script.
    for item_code, row in after.items():
        if row["supplier"] and "Agusan" in row["supplier"]:
            problems.append(
                f"{item_code}.supplier still names Agusan: {row['supplier']!r}"
            )

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print(f"\ninventory items after migration:  {len(after)}")
    print(f"rows untouched:                   {untouched}")
    print("No supplier in the inventory names the wrong province.")


if __name__ == "__main__":
    main()
