"""Migration: remove the test run an interrupted session left in the database.

WHAT WAS WRONG
--------------
On 2026-08-29 a verification session ran an end-to-end Health Center Staff
workflow against the LIVE database rather than a copy, and lost its connection
before it could restore anything. Its test data is still here:

    patients              id 94  PAT-029 "Verify Role Testcase", Inactive
    consultations         id 38  "Acute upper respiratory infection (revised)"
    appointments          id 69  patient 94, 2026-08-29, Completed  (walk-in)
    appointments          id 70  patient 7,  2026-08-29, Completed  (walk-in)
    appointments          id 71  patient 94, 2026-09-10, Scheduled
    medicine_dispensing   id 19  Paracetamol x4 against consultation 38
    general_vaccinations  id 5   Influenza dose 1 for patient 94
    inventory_items       id 1   Paracetamol stock 745 -> 741

None of it describes anything that happened. A fictional patient sits in the
roster, a real patient (id 7) carries a visit they never made, four units of
Paracetamol are missing from the shelf count, and a future appointment is booked
for 10 September for somebody who does not exist.

WHERE THE "CORRECT PRIOR STATE" COMES FROM
------------------------------------------
Not from reasoning about it. That session took a backup immediately before it
started -- app.db.PRETASK_BACKUP_role-verification_20260829_213138 -- so the
database as it stood before the test run is on disk. This script reads it, and
every id below was established by diffing the two files rather than by reading
the test script and guessing what it wrote. The backup is opened READ-ONLY and is
never written to.

WHY DELETE, WHEN NOTHING ELSE IN THIS PROJECT DELETES
-----------------------------------------------------
Every other data path here archives rather than deletes: a patient goes Inactive,
a medicine goes Inactive, a cancelled appointment keeps its row. That rule exists
because those records describe real events, and a health center does not get to
un-happen a visit.

These rows describe no event. They are an artefact of a test harness, and marking
them Inactive would leave a fictional patient permanently in the roster with a
fictional visit attached -- exactly the outcome the archive rule exists to
prevent for real records. So they go, and the audit trail is where that decision
is written down.

WHAT HAPPENS TO THE AUDIT TRAIL
-------------------------------
The test run also wrote two audit_logs entries (951, a sign-in; 952, describing
its edit to consultation 38). Neither is deleted, for two reasons: audit_logs is
foreign-keyed only to `users`, so removing the clinical rows orphans nothing; and
an audit trail is not rewritten to match a tidier version of the past. Entry 951
records a sign-in that genuinely happened, and entry 952 records an edit that
genuinely was made.

What entry 952 will no longer have is a consultation to point at. So this script
writes one further entry saying so, in the shape
migrate_close_stuck_consultation.py established: read months later on its own, it
has to explain why an earlier entry names a record that is not there.

ORDER, AND WHY IT IS THIS ORDER
-------------------------------
Children before parents, so no statement ever runs against a row whose referent
has already gone:

    medicine_dispensing (-> consultations, patients, inventory_items)
    general_vaccinations (-> consultations, patients)
    consultations (-> appointments, patients)
    appointments (-> patients)
    patients

PRAGMA foreign_keys is ON for the whole run, and a foreign_key_check is made
before the commit, so a missed reference aborts rather than being written.

WHAT THIS TOUCHES
-----------------
The eight rows named above and one INSERT into audit_logs. Every other row in
every table is verified against the backup, byte for byte, before anything is
committed. The whole thing is one transaction: if verification fails, nothing is
committed.

Idempotent -- re-running is a no-op. Rows already gone are reported as already
gone, the stock is only moved if it is still at the reduced figure, and the audit
entry is written only when this run actually removed something.

Run:  python migrate_remove_test_residue.py
"""
import os
import sqlite3
import sys

import config

BACKUP = os.path.join(
    os.path.dirname(os.path.abspath(config.DATABASE)),
    "app.db.PRETASK_BACKUP_role-verification_20260829_213138",
)

# (table, id, what it is) in deletion order -- children first. Spelled out per
# row so the scope is reviewable here and in the commit without running anything.
RESIDUE = [
    ("medicine_dispensing", 19, "Paracetamol x4 against consultation 38"),
    ("general_vaccinations", 5, "Influenza dose 1 for patient 94"),
    ("consultations", 38, '"Acute upper respiratory infection (revised)"'),
    ("appointments", 69, "patient 94, 2026-08-29, Completed walk-in"),
    ("appointments", 70, "patient 7, 2026-08-29, Completed walk-in"),
    ("appointments", 71, "patient 94, 2026-09-10, Scheduled"),
    ("patients", 94, 'PAT-029 "Verify Role Testcase", Inactive'),
]

STOCK_ITEM_ID = 1
STOCK_REDUCED = 741
STOCK_CORRECT = 745

# Deducting the stock also stamped the row's updated_at, so restoring only the
# quantity would leave inventory_items.1 still carrying the moment a test touched
# it -- and Medicine Inventory sorts and reports on that column. The correct
# value is read from the backup rather than written here, for the same reason
# every other figure in this script is.
STOCK_TOUCHED_COLUMNS = ("stock_quantity", "updated_at")

# The one place this database is deliberately ALLOWED to differ from the backup.
# migrate_clear_seeded_remarks.py runs first and sets these five rows' remarks to
# NULL on purpose; the backup predates that and still holds the seeded filename.
# Declared here, per row and per column, so the diff below can tell a change that
# was intended from one that was not -- and so a sixth row quietly changing would
# still abort the run.
INTENDED_DIVERGENCE = {
    ("consultations", 1, "remarks"),
    ("consultations", 2, "remarks"),
    ("consultations", 3, "remarks"),
    ("consultations", 4, "remarks"),
    ("consultations", 5, "remarks"),
}
SEEDED_REMARK = "Mock consultation entry generated by populate_records.py"

# The acting account. The test run signed in as user 2 (Health Center Staff) and
# wrote every row below under it, so the entry recording their removal is
# attributed to the same account rather than to an administrator who was not
# involved. Matches migrate_close_stuck_consultation.py's reasoning.
ACTING_USER_ID = 2

ALL_TABLES = (
    "patients", "consultations", "appointments", "inventory_items",
    "medicine_dispensing", "immunizations", "general_vaccinations",
    "sms_broadcasts", "sms_broadcast_recipients", "users", "settings",
)


def snapshot(conn, tables=ALL_TABLES):
    """Every row of every table, keyed by table and id, for a byte-level diff."""
    out = {}
    for table in tables:
        out[table] = {
            row["id"]: dict(row)
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")
        }
    return out


def main():
    if not os.path.exists(BACKUP):
        print(f"The reference backup is missing:\n  {BACKUP}\n"
              "This migration establishes the correct prior state from that file "
              "and will not guess at it. Nothing has been changed.")
        sys.exit(1)

    # Read-only: the reference must not be writable by this script even by
    # accident, so it is opened through a URI with mode=ro.
    reference = sqlite3.connect(f"file:{BACKUP}?mode=ro", uri=True)
    reference.row_factory = sqlite3.Row
    expected = snapshot(reference)
    reference.close()

    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    before = snapshot(conn)
    print("rows before migration:")
    for table in ALL_TABLES:
        print(f"  {table:26} {len(before[table]):4}   "
              f"(backup holds {len(expected[table])})")

    # -- 1. the residue rows ------------------------------------------------
    removed, absent, unexpected = [], [], []
    for table, row_id, description in RESIDUE:
        row = before[table].get(row_id)
        if row is None:
            absent.append((table, row_id))
            continue
        if row_id in expected[table]:
            # It is in the backup too, so it predates the test run and is real.
            unexpected.append((table, row_id, description))
            continue
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        removed.append((table, row_id, description))

    print(f"\nrows removed:       {len(removed)}")
    for table, row_id, description in removed:
        print(f"  {table}.{row_id}  {description}")
    if absent:
        print(f"already gone:       {len(absent)} "
              f"({', '.join(f'{t}.{i}' for t, i in absent)})")
    if unexpected:
        print(f"REFUSED:            {len(unexpected)}")
        for table, row_id, description in unexpected:
            print(f"  {table}.{row_id} is in the backup, so it predates the test "
                  f"run and is real -- not touched ({description})")

    # -- 2. the stock the test run took off the shelf -----------------------
    stock_row = before["inventory_items"].get(STOCK_ITEM_ID)
    reference_row = expected["inventory_items"].get(STOCK_ITEM_ID)
    stock_note = None
    if stock_row is None or reference_row is None:
        stock_note = f"inventory item {STOCK_ITEM_ID} is not in both files"
    elif stock_row["stock_quantity"] == STOCK_CORRECT:
        stock_note = f"already {STOCK_CORRECT}"
    elif stock_row["stock_quantity"] != STOCK_REDUCED:
        stock_note = (f"holds {stock_row['stock_quantity']}, expected "
                      f"{STOCK_REDUCED} -- not touched")
    elif reference_row["stock_quantity"] != STOCK_CORRECT:
        stock_note = (f"the backup holds {reference_row['stock_quantity']}, not "
                      f"{STOCK_CORRECT} -- not touched")
    else:
        conn.execute(
            "UPDATE inventory_items SET stock_quantity = ?, updated_at = ? "
            "WHERE id = ?",
            (reference_row["stock_quantity"], reference_row["updated_at"],
             STOCK_ITEM_ID),
        )
    if stock_note:
        print(f"\nstock restored:     {stock_row['name'] if stock_row else '?'} "
              f"{stock_note}")
    else:
        print(f"\nstock restored:     {stock_row['name']} "
              f"{STOCK_REDUCED} -> {STOCK_CORRECT}")
        print(f"                    updated_at {stock_row['updated_at']!r} "
              f"-> {reference_row['updated_at']!r}")

    # -- 3. say so in the audit trail ---------------------------------------
    wrote_audit = False
    if removed:
        conn.execute(
            """
            INSERT INTO audit_logs (user_id, action, module, details, ip_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ACTING_USER_ID,
                "Removed test data",
                "Consultation Records",
                (
                    "Removed the end-to-end test data an interrupted verification "
                    "session wrote into this database on Aug 29, 2026: patient "
                    'PAT-029 "Verify Role Testcase" and the visit built around '
                    "them -- consultation #38, appointments #69, #70 and #71, one "
                    "medicine issue (Paracetamol x4) and one vaccination "
                    "(Influenza dose 1). Paracetamol stock was returned from 741 "
                    "to 745, the figure it held before that run. None of those "
                    "rows described a real patient, visit or issue; they were "
                    "written by a test harness against the live database instead "
                    "of a copy. The correct prior state was read from the backup "
                    "that session took before it began, not inferred. Two earlier "
                    "entries from that run are deliberately left in place: the "
                    'sign-in at 13:39:49, and "Updated consultation record" '
                    "naming consultation #38, which is why that entry now refers "
                    "to a record no longer in the database"
                ),
                "127.0.0.1",
            ),
        )
        wrote_audit = True

    # -- 4. verify against the backup before committing ----------------------
    after = snapshot(conn)
    problems, intended = [], []

    for table in ALL_TABLES:
        want, got = expected[table], after[table]
        # audit_logs is excluded from ALL_TABLES on purpose: it legitimately
        # grew, both during the test run and just now, and is checked separately.
        for row_id, old in want.items():
            new = got.get(row_id)
            if new is None:
                problems.append(f"{table}.{row_id} is in the backup but was removed")
                continue
            changed = [c for c, v in old.items() if new[c] != v]
            for column in changed:
                if (table, row_id, column) in INTENDED_DIVERGENCE:
                    # Allowed, but only in the one direction that is actually
                    # the other migration's work: the backup still holds the
                    # seeded filename and this database now holds NULL. Any
                    # other pair of values here is something else entirely.
                    if old[column] == SEEDED_REMARK and new[column] is None:
                        intended.append(f"{table}.{row_id}.{column}")
                        continue
                    problems.append(
                        f"{table}.{row_id}.{column} was expected to be the "
                        f"cleared seeded remark, but reads {old[column]!r} -> "
                        f"{new[column]!r}"
                    )
                    continue
                problems.append(
                    f"{table}.{row_id} differs from the backup on {column}: "
                    f"{old[column]!r} -> {new[column]!r}"
                )
        for row_id in got:
            if row_id not in want:
                problems.append(
                    f"{table}.{row_id} is still here but is not in the backup")

    # Foreign keys, asked of the database rather than assumed from the order.
    violations = list(conn.execute("PRAGMA foreign_key_check"))
    for violation in violations:
        problems.append(f"foreign key violation: {tuple(violation)}")

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        problems.append(f"integrity_check said {integrity!r}")

    audit_now = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]

    if problems:
        conn.rollback()
        conn.close()
        print("\nMIGRATION PROBLEMS -- nothing was committed:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    conn.commit()

    print("\nverified against the backup: every remaining row in every table is "
          "byte-for-byte identical to its pre-test state,")
    if intended:
        print(f"  except {len(intended)} declared field(s) cleared by "
              "migrate_clear_seeded_remarks.py:")
        print("  " + ", ".join(intended))
    else:
        print("  with no declared exceptions outstanding.")
    print(f"foreign_key_check:   {len(violations)} violations")
    print(f"integrity_check:     {integrity}")
    print(f"audit_logs:          {audit_now} entries"
          + (" (+1 recording this cleanup)" if wrote_audit else ""))
    print("\nrows after migration:")
    for table in ALL_TABLES:
        mark = "" if len(after[table]) == len(expected[table]) else "   MISMATCH"
        print(f"  {table:26} {len(after[table]):4}{mark}")

    conn.close()


if __name__ == "__main__":
    main()
