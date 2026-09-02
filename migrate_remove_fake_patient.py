"""Migration: remove the fake patient a form-testing session left in the roster.

WHAT IS WRONG
-------------
Two rows written on 2026-09-02 at 06:25:57 describe nobody and nothing:

    patients      id 95  PAT-029 "JOhn asc asdas", Inactive
    appointments  id 78  patient 95, 2026-09-03 12:30, Consultation, Scheduled

They are somebody trying the Register Patient form and then the booking dialog,
and the record says so in every field rather than in only one:

* The name is keyboard mash. "JOhn asc asdas", with the emergency contact
  "asd asc asdas" beside it.
* The birth date is 2026-07-01, which makes the patient a two-month-old infant.
  Their civil status is "Married".
* The province is "Surigao del Sur" and the ZIP is "8765" -- the exact pair
  migrate_correct_patient_location.py went through this database to remove. This
  health center is in San Francisco, **Surigao del Norte**, 8401. A record
  created after that correction, carrying the values the correction existed to
  fix, was typed rather than lived.

Any one of those could be a clerical slip. Together they are a test.

WHY THIS IS URGENT RATHER THAN UNTIDY
-------------------------------------
Somebody had already noticed and set the patient to Inactive. That closed the
roster entry and nothing else: appointment 78 is still **Scheduled**, for
**2026-09-03**, which is tomorrow. Deactivating a patient in this system does not
touch their bookings, so the fictional visit still sits on the queue, on the
Appointment Scheduling calendar, and in tomorrow's counts on the dashboards. That
is what a demo opens on.

WHY THESE ROWS ARE DELETED, WHEN THIS PROJECT ARCHIVES
------------------------------------------------------
The rule everywhere else here is that records are archived, not deleted: a
patient goes Inactive, a medicine goes Inactive, a cancelled appointment keeps
its row. That rule exists because those records describe real events, and a
health center does not get to un-happen a visit.

These rows describe no event, and migrate_remove_test_residue.py already settled
the same question on the same ground five days ago. Marking them Inactive --
which has been tried -- leaves a fictional patient permanently in the roster with
a fictional appointment attached, which is precisely the outcome the archive rule
protects real records from.

AND WHY THE APPOINTMENT IS DELETED RATHER THAN CANCELLED
--------------------------------------------------------
Cancelling it is the wrong shape twice over. `Cancelled` is a statement that a
real booking was called off, which would leave the demo queue showing a
cancellation nobody made; and the row would still be foreign-keyed to patient 95,
so it cannot survive the patient's removal without orphaning. The appointment
goes with the patient it belongs to, children first, which is the same order and
the same reasoning migrate_remove_test_residue.py used for appointments 69, 70
and 71.

WHAT ELSE POINTS AT THEM: NOTHING, AND THAT WAS CHECKED
-------------------------------------------------------
Every table with a foreign key to `patients` or `appointments` was queried for
these two ids before this script was written, and the check is repeated below at
run time rather than trusted from that pass:

    consultations.patient_id            0 rows    consultations.appointment_id  0
    immunizations.patient_id            0 rows
    general_vaccinations.patient_id     0 rows
    medicine_dispensing.patient_id      0 rows
    sms_broadcast_recipients.patient_id 0 rows
    appointment_sms_messages.patient_id 0 rows    .appointment_id               0

The session got as far as registering and booking and no further. Nothing was
consulted, dispensed, vaccinated or texted, so no stock moved and no message was
composed -- which is why this migration has no counterpart to the stock
restoration migrate_remove_test_residue.py had to make.

WHAT HAPPENS TO THE AUDIT TRAIL
-------------------------------
Nothing is removed from it. Registering a patient and booking an appointment are
not audited actions in this system -- the trail holds no entry for either of
these rows -- so their removal orphans no entry and rewrites no history.

One entry is added, in the shape migrate_close_stuck_consultation.py established
and migrate_remove_test_residue.py followed: the removal is a decision, and a
decision that leaves no trace is indistinguishable from data quietly going
missing.

THE ONE THING THAT ENTRY HAS TO SAY, THAT THE LAST ONE DID NOT
--------------------------------------------------------------
"PAT-029" has now been two different fictional people. It was
"Verify Role Testcase" until entry 953 removed them on 2026-08-31, and
generate_next_patient_id() hands out highest-plus-one, so the identifier came
free and the next registration took it. Entry 952 still names PAT-029, and means
the first one.

Removing this patient frees PAT-029 a second time, and the next real registration
will be given it. So the entry written here names the patient by their full fake
name rather than by the identifier alone, and says which PAT-029 it means --
otherwise the trail ends up with three uses of one label and no way to tell them
apart.

WHAT THIS TOUCHES
-----------------
The two rows named above and one INSERT into audit_logs. Nothing else, and that
is not asserted -- it is checked. Every other row of every table is compared
column by column against the backup taken immediately before this run, and any
difference at all aborts the transaction before it commits.

HOW THE BACKUP IS USED HERE, WHICH IS THE OPPOSITE OF LAST TIME
---------------------------------------------------------------
migrate_remove_test_residue.py read a backup that predated the damage, so its
backup was the *target* state and the residue rows were the ones missing from it.
Patient 95 was created after every backup on disk, so no such file exists. The
backup this script reads was taken minutes before it ran and therefore *contains*
the two rows: it is the state to preserve everywhere except at the two ids named
below. The verification is the same idea run the other way -- identical to the
backup, except exactly the declared deletions and the one appended audit entry.

Idempotent. Re-running reports rows already gone and writes no second audit
entry.

Run:  python migrate_remove_fake_patient.py
"""
import os
import sqlite3
import sys

import config

BACKUP = os.path.join(
    os.path.dirname(os.path.abspath(config.DATABASE)),
    "app.db.PRETASK_BACKUP_fake-patient-pat029_20260902_174847",
)

# (table, id, what it is) in deletion order -- children first, so no statement
# ever runs against a row whose referent has already gone. Spelled out per row so
# the scope is reviewable here and in the commit without running anything.
REMOVE = [
    ("appointments", 78, "patient 95, 2026-09-03 12:30, Consultation, Scheduled"),
    ("patients", 95, 'PAT-029 "JOhn asc asdas", Inactive'),
]

# The rows above are only removable if they really are the rows described. A
# migration that deletes by id alone deletes whatever has since moved into that
# id. Each is matched on the fields that make it identifiable before anything is
# written; a mismatch refuses that row rather than guessing.
IDENTITY = {
    ("patients", 95): {
        "patient_id": "PAT-029",
        "first_name": "JOhn",
        "middle_name": "asc",
        "last_name": "asdas",
        "birth_date": "2026-07-01",
        "created_at": "2026-09-02 06:25:57",
    },
    ("appointments", 78): {
        "patient_id": 95,
        "appointment_date": "2026-09-03",
        "appointment_time": "12:30",
        "appointment_type": "Consultation",
        "status": "Scheduled",
        "created_at": "2026-09-02 06:25:57",
    },
}

# Every table with a foreign key to patients or appointments, and the column that
# holds it. Asked of the database at run time rather than taken from the survey
# in the docstring, so a reference created between then and now stops this run
# instead of being deleted out from under.
REFERENCES = [
    ("consultations", "patient_id", "patients", 95),
    ("consultations", "appointment_id", "appointments", 78),
    ("immunizations", "patient_id", "patients", 95),
    ("general_vaccinations", "patient_id", "patients", 95),
    ("medicine_dispensing", "patient_id", "patients", 95),
    ("sms_broadcast_recipients", "patient_id", "patients", 95),
    ("appointment_sms_messages", "patient_id", "patients", 95),
    ("appointment_sms_messages", "appointment_id", "appointments", 78),
]

# The acting account. Both rows were written under user 2 -- appointments.78
# carries scheduled_by = 2 -- so the entry recording their removal is attributed
# to the same account rather than to an administrator who was not involved.
# Matches migrate_remove_test_residue.py and migrate_close_stuck_consultation.py.
ACTING_USER_ID = 2

ALL_TABLES = (
    "patients", "consultations", "appointments", "inventory_items",
    "medicine_dispensing", "immunizations", "general_vaccinations",
    "sms_broadcasts", "sms_broadcast_recipients", "appointment_sms_messages",
    "settings", "users",
)

AUDIT_DETAILS = (
    'Removed the fake patient record PAT-029 "JOhn asc asdas" (patient id 95) '
    "and the appointment booked for them, #78 -- a Consultation Scheduled for "
    "Sep 03, 2026 at 12:30. Both rows were written on Sep 02, 2026 at 06:25:57 "
    "by somebody trying the Register Patient form and the booking dialog: the "
    "name and emergency contact are keyboard mash, the birth date of Jul 01, "
    "2026 makes the patient a two-month-old infant recorded as Married, and the "
    'province and ZIP read "Surigao del Sur" / 8765 -- the pair the patient '
    "location correction went through this database to remove. The patient had "
    "already been set to Inactive, which does not close a booking, so the "
    "appointment was still Scheduled for the following day and still appeared on "
    "the queue, the calendar and the day's counts. Nothing else referred to "
    "either row: no consultation, immunisation, vaccination, medicine issue, "
    "broadcast recipient or SMS message, so no stock or history was affected. "
    "The rows were deleted rather than archived because they describe no event, "
    "which is the same ground on which the Aug 31, 2026 test-data removal was "
    "made. Note for anyone reading the older entries: this is the SECOND "
    'fictional PAT-029. The first was "Verify Role Testcase", removed on Aug 31, '
    "2026, and it is that one the earlier consultation entry names. Identifiers "
    "are reissued as highest-plus-one, so PAT-029 is free again and the next "
    "real registration will be given it"
)


def snapshot(conn, tables=ALL_TABLES):
    """Every row of every table, keyed by table and id, for a column-level diff."""
    return {
        table: {
            row["id"]: dict(row)
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")
        }
        for table in tables
    }


def main():
    if not os.path.exists(BACKUP):
        print(f"The reference backup is missing:\n  {BACKUP}\n"
              "This migration proves it changed only what it says it changed by "
              "diffing against that file, and will not run without it. Nothing "
              "has been changed.")
        sys.exit(1)

    # Read-only: the reference must not be writable by this script even by
    # accident, so it is opened through a URI with mode=ro.
    reference = sqlite3.connect(f"file:{BACKUP}?mode=ro", uri=True)
    reference.row_factory = sqlite3.Row
    expected = snapshot(reference)
    expected_audit = {
        row["id"]: dict(row)
        for row in reference.execute("SELECT * FROM audit_logs ORDER BY id")
    }
    reference.close()

    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    before = snapshot(conn)
    # Separate from the backup on purpose. The backup answers "what has changed
    # on disk since it was taken"; this answers "what did THIS RUN change", and
    # they are different questions the moment this script is run twice or the
    # application records a sign-in in between. audit_logs needs both.
    before_audit = {
        row["id"] for row in conn.execute("SELECT id FROM audit_logs")
    }
    print("rows before migration:")
    for table in ALL_TABLES:
        print(f"  {table:26} {len(before[table]):4}   "
              f"(backup holds {len(expected[table])})")

    # -- 1. is anything pointing at these rows? ------------------------------
    print("\nreferences to patient 95 / appointment 78:")
    blocking = []
    for table, column, parent, row_id in REFERENCES:
        found = [r["id"] for r in conn.execute(
            f"SELECT id FROM {table} WHERE {column} = ?", (row_id,))]
        print(f"  {table + '.' + column:38} = {row_id:<4} {len(found)} row(s)"
              + (f"  {found}" if found else ""))
        if found:
            blocking.append(f"{table}.{column} still names {parent}.{row_id}: "
                            f"rows {found}")
    if blocking:
        conn.rollback()
        conn.close()
        print("\nREFUSED -- something refers to these rows, so removing them "
              "would orphan it. Nothing has been changed:")
        for problem in blocking:
            print("  -", problem)
        sys.exit(1)

    # -- 2. the two rows -----------------------------------------------------
    removed, absent, refused = [], [], []
    for table, row_id, description in REMOVE:
        row = before[table].get(row_id)
        if row is None:
            absent.append((table, row_id, description))
            continue
        mismatched = [
            f"{column}: {row[column]!r} (expected {value!r})"
            for column, value in IDENTITY[(table, row_id)].items()
            if row[column] != value
        ]
        if mismatched:
            refused.append((table, row_id, mismatched))
            continue
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        removed.append((table, row_id, description))

    print(f"\nrows removed:       {len(removed)}")
    for table, row_id, description in removed:
        print(f"  {table}.{row_id}  {description}")
    for table, row_id, description in absent:
        print(f"  already gone:     {table}.{row_id}  {description}")
    if refused:
        print(f"REFUSED:            {len(refused)}")
        for table, row_id, mismatched in refused:
            print(f"  {table}.{row_id} is not the row this migration describes, "
                  "so it is a different record now and is not touched:")
            for detail in mismatched:
                print(f"      {detail}")

    # -- 3. say so in the audit trail ----------------------------------------
    wrote_audit = False
    if removed:
        conn.execute(
            """
            INSERT INTO audit_logs (user_id, action, module, details, ip_address)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ACTING_USER_ID, "Removed test data", "Patient Records",
             AUDIT_DETAILS, "127.0.0.1"),
        )
        wrote_audit = True

    # -- 4. verify against the backup before committing ----------------------
    after = snapshot(conn)
    intended = {(table, row_id) for table, row_id, _ in REMOVE}
    gone = {(table, row_id) for table, row_id, _ in removed}
    problems = []

    for table in ALL_TABLES:
        want, got = expected[table], after[table]
        for row_id, old in want.items():
            new = got.get(row_id)
            if new is None:
                if (table, row_id) not in intended:
                    problems.append(
                        f"{table}.{row_id} was in the backup and is now gone, "
                        "and it is not one of the two rows this migration "
                        "removes")
                continue
            if (table, row_id) in gone:
                problems.append(
                    f"{table}.{row_id} was deleted by this run and is still here")
                continue
            for column, value in old.items():
                if new[column] != value:
                    problems.append(
                        f"{table}.{row_id} differs from the backup on {column}: "
                        f"{value!r} -> {new[column]!r}")
        for row_id in got:
            if row_id not in want:
                problems.append(
                    f"{table}.{row_id} is here but is not in the backup")

    # audit_logs is checked separately because it is the one table this
    # migration is allowed to ADD to, and it is checked against both references.
    #
    # Against the backup: every entry that was in it must still be there,
    # unchanged. A trail is not rewritten to match a tidier past, and that half
    # is an absolute -- any edit or deletion here aborts.
    #
    # Against the start of this run: this run must have appended exactly one
    # entry, or none if it removed nothing. Entries that appeared between the
    # backup and now are reported rather than refused, because a trail that grows
    # is the trail working -- a re-run of this script, or a sign-in recorded
    # while it was being read, both land there and neither is this run's doing.
    audit_after = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM audit_logs ORDER BY id")
    }
    for row_id, old in expected_audit.items():
        new = audit_after.get(row_id)
        if new is None:
            problems.append(f"audit_logs.{row_id} was removed")
            continue
        for column, value in old.items():
            if new[column] != value:
                problems.append(
                    f"audit_logs.{row_id} differs from the backup on {column}")
    added = [i for i in audit_after if i not in before_audit]
    if len(added) != (1 if wrote_audit else 0):
        problems.append(f"this run appended {len(added)} audit entries, expected "
                        f"{1 if wrote_audit else 0}")
    since_backup = [i for i in audit_after
                    if i not in expected_audit and i not in added]

    # Foreign keys, asked of the database rather than assumed from the order.
    violations = list(conn.execute("PRAGMA foreign_key_check"))
    for violation in violations:
        problems.append(f"foreign key violation: {tuple(violation)}")

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        problems.append(f"integrity_check said {integrity!r}")

    if problems:
        conn.rollback()
        conn.close()
        print("\nMIGRATION PROBLEMS -- nothing was committed:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    conn.commit()

    print("\nverified against the backup: every row of every table is "
          "column-for-column identical to the state before this run,")
    print(f"  except the {len(removed)} declared removal(s) above"
          + (f" and 1 appended audit entry (#{added[0]})" if added else ""))
    if since_backup:
        print(f"  {len(since_backup)} audit entr(ies) appeared between the backup "
              f"and this run and were left alone: {since_backup}")
    print(f"foreign_key_check:   {len(violations)} violations")
    print(f"integrity_check:     {integrity}")
    print("\nrows after migration:")
    for table in ALL_TABLES:
        delta = len(after[table]) - len(expected[table])
        print(f"  {table:26} {len(after[table]):4}"
              + ("" if delta == 0 else f"   {delta:+d}"))
    print(f"  {'audit_logs':26} {len(audit_after):4}"
          + (f"   +{len(added)}" if added else ""))

    conn.close()


if __name__ == "__main__":
    main()
