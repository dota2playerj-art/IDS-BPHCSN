"""Migration: repair the eleven patient records that stored the wrong location.

WHY THIS MIGRATION EXISTS
-------------------------
This system was built around "San Francisco, Agusan del Sur". That is the wrong
place. The health center is in Barangay Poblacion, San Francisco (formerly
Anao-Aon), **Surigao del Norte** -- a different municipality in a different
province, about 12 km from Surigao City.

The wrong value was never sourced from anything. The approved Capstone Proposal
names no province at all (its only geographic string is "Surigao City", the
college's own address); 06_DESIGN_CONTENT_LIBRARY.md left Province and
Municipality as "(Use the ... stated in the approved capstone proposal.)" -- a
placeholder that was never resolved. "Agusan del Sur" was invented downstream in
models/patients.py, and from there it reached real records.

It reached them through models.patients.MUNICIPALITIES / PROVINCES, which
validate_patient_form() enforces as a closed list. Whoever registered these
patients could only choose from what that list offered, so the stored values are
not data-entry mistakes -- they are the closest each operator could get:

* Seven records hold province "Surigao del Sur". Surigao del Norte was not on
  offer, so "Surigao" was reached for and the only Surigao available was taken.
  These are the strongest evidence of intent in the whole database, and they are
  a rename, not a re-survey.
* Two hold municipality "Bunawan" with province "Agusan del Sur" -- an Agusan del
  Sur municipality that exists nowhere near this health center. Nothing about
  those two rows says the patient is non-local; the list simply offered no
  correct answer. They are corrected to San Francisco on the same assumption
  every other record makes. See CAVEAT below.
* Two are the seeded infants from populate_records.py, written directly with the
  wrong province.

Zip codes went the same way: 8506 is Bunawan (Agusan del Sur), 8400 is Surigao
*City*, and 8765 belongs to nowhere in play. The correct code for San Francisco,
Surigao del Norte is 8401.

CAVEAT, recorded deliberately
-----------------------------
For PAT-016 and PAT-017 the true municipality is not recoverable from the data.
Their stored "Bunawan" was picked from a list that could not express the truth,
and their street addresses ("Purok 5, Sitio Bagong Buhay", "Purok 2, Sitio
Maligaya") name no municipality. This migration assumes they are local, like
every other patient in the register. If either turns out to live elsewhere, that
is a correction to make from the patient's own record, not from this script.

WHY NO AUDIT_LOGS ROW
---------------------
audit_logs.user_id is NOT NULL and FK-constrained to a real account, and
models.audit.log_action() refuses to write an entry it cannot attribute --
"an audit row that cannot say who acted is worse than none". A migration is not
a user action, and filing it under the admin account would name an author who did
not do it. No patient write anywhere in the application calls log_action() today
(routes/audit_views.py:42 says so), so a row here would also be the only patient
entry in the trail and would read as though this were the only patient edit ever
made. This script, committed and re-runnable, is the traceable record instead.

WHAT IT CHANGES
---------------
Only municipality, province and zip_code, and only on the eleven rows named in
CORRECTIONS below. Every other column of those rows, and every other row, is
verified byte-for-byte unchanged. The fifteen patients carrying NULL
municipality/province (PAT-001..PAT-015) are not touched -- NULL is incomplete,
not wrong, and inventing an address for them would be fabricating clinical data.

Idempotent -- re-running is a no-op. A row already in its corrected state is
skipped; a row matching neither the expected before-state nor the after-state is
reported and left alone rather than overwritten.

Run:  python migrate_correct_patient_location.py
"""
import sqlite3
import sys

import config
from models.patients import MUNICIPALITIES, PROVINCES

# The fields this migration is allowed to write. Anything else differing between
# the before and after snapshots is a bug in this script, and is checked for.
FIELDS = ("municipality", "province", "zip_code")

# patient_id -> (expected before, intended after), each as (municipality,
# province, zip_code). Written out per record rather than derived from a rule so
# that the change to every individual patient is reviewable here, in the commit,
# without running anything. A row whose stored values match neither tuple is left
# untouched: this script corrects a known, audited set, and silently rewriting
# something it does not recognise is exactly the failure it exists to undo.
CORRECTIONS = {
    # Two records that named an Agusan del Sur municipality. See CAVEAT above.
    "PAT-016": (("Bunawan", "Agusan del Sur", None),
                ("San Francisco", "Surigao del Norte", None)),
    "PAT-017": (("Bunawan", "Agusan del Sur", "8506"),
                ("San Francisco", "Surigao del Norte", "8401")),
    # Seven records that reached for "Surigao" and got the only one on offer.
    "PAT-018": (("San Francisco", "Surigao del Sur", "8400"),
                ("San Francisco", "Surigao del Norte", "8401")),
    "PAT-019": (("San Francisco", "Surigao del Sur", "8400"),
                ("San Francisco", "Surigao del Norte", "8401")),
    "PAT-020": (("San Francisco", "Surigao del Sur", "8765"),
                ("San Francisco", "Surigao del Norte", "8401")),
    "PAT-023": (("San Francisco", "Surigao del Sur", "8400"),
                ("San Francisco", "Surigao del Norte", "8401")),
    "PAT-024": (("San Francisco", "Surigao del Sur", "8400"),
                ("San Francisco", "Surigao del Norte", "8401")),
    "PAT-025": (("San Francisco", "Surigao del Sur", "8400"),
                ("San Francisco", "Surigao del Norte", "8401")),
    "PAT-026": (("San Francisco", "Surigao del Sur", "8400"),
                ("San Francisco", "Surigao del Norte", "8401")),
    # The two seeded infants, written with the wrong province by
    # populate_records.py. Their zip was never set and stays unset -- this
    # migration corrects wrong values, it does not invent missing ones.
    "PAT-021": (("San Francisco", "Agusan del Sur", None),
                ("San Francisco", "Surigao del Norte", None)),
    "PAT-022": (("San Francisco", "Agusan del Sur", None),
                ("San Francisco", "Surigao del Norte", None)),
}


def snapshot(conn):
    return {
        row["patient_id"]: dict(row)
        for row in conn.execute("SELECT * FROM patients ORDER BY id")
    }


def state(row):
    return tuple(row[field] for field in FIELDS)


def render(values):
    return ", ".join("NULL" if v is None else repr(v) for v in values)


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before = snapshot(conn)
    print(f"patients before migration: {len(before)}")

    applied, already, mismatched, missing = [], [], [], []

    for patient_id, (expected, corrected) in CORRECTIONS.items():
        row = before.get(patient_id)
        if row is None:
            missing.append(patient_id)
            continue
        current = state(row)
        if current == corrected:
            already.append(patient_id)
            continue
        if current != expected:
            mismatched.append((patient_id, current, expected))
            continue
        conn.execute(
            "UPDATE patients SET municipality = ?, province = ?, zip_code = ? "
            "WHERE patient_id = ?",
            (*corrected, patient_id),
        )
        applied.append((patient_id, current, corrected))

    conn.commit()

    print(f"records corrected:  {len(applied)}")
    for patient_id, was, now in applied:
        print(f"  {patient_id}:  {render(was)}  ->  {render(now)}")
    if already:
        print(f"already correct:    {len(already)} ({', '.join(already)})")
    if mismatched:
        print(f"left alone:         {len(mismatched)}")
        for patient_id, current, expected in mismatched:
            print(f"  {patient_id}: holds {render(current)}, "
                  f"expected {render(expected)} -- not touched")
    if missing:
        print(f"not in database:    {', '.join(missing)}")

    after = snapshot(conn)
    problems = []

    if len(before) != len(after):
        problems.append(f"row count changed: {len(before)} -> {len(after)}")

    # Nothing outside FIELDS may move, and nothing outside CORRECTIONS may move
    # at all. This is the check that protects the fifteen NULL-address records
    # and every clinical column on the eleven.
    untouched_rows = 0
    for patient_id, old in before.items():
        new = after.get(patient_id)
        if new is None:
            problems.append(f"{patient_id} disappeared")
            continue
        changed = [c for c, v in old.items() if new[c] != v]
        if not changed:
            untouched_rows += 1
            continue
        if patient_id not in CORRECTIONS:
            problems.append(f"{patient_id} was not in scope but changed: {changed}")
            continue
        for column in changed:
            if column not in FIELDS:
                problems.append(
                    f"{patient_id}.{column}: {old[column]!r} -> {new[column]!r} "
                    "(outside this migration's remit)"
                )

    # The point of the whole exercise: what is stored must be something the
    # Register Patient form can offer and validate_patient_form() will accept.
    # A row that fails this is one an operator could no longer save from the
    # Edit screen without re-picking the address.
    for patient_id, row in after.items():
        if row["municipality"] is not None and row["municipality"] not in MUNICIPALITIES:
            problems.append(
                f"{patient_id}.municipality {row['municipality']!r} is not in "
                f"MUNICIPALITIES {MUNICIPALITIES}"
            )
        if row["province"] is not None and row["province"] not in PROVINCES:
            problems.append(
                f"{patient_id}.province {row['province']!r} is not in "
                f"PROVINCES {PROVINCES}"
            )

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    nulls = sum(
        1 for row in after.values()
        if row["municipality"] is None and row["province"] is None
    )
    print(f"\npatients after migration:  {len(after)}")
    print(f"rows untouched:            {untouched_rows} "
          f"(of which {nulls} carry no municipality or province at all)")
    print("Every stored municipality and province is now one the Register "
          "Patient form offers and the validator accepts.")


if __name__ == "__main__":
    main()
