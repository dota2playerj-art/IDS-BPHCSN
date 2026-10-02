"""Migration: close the visit left In Consultation on 2026-08-28.

Run: python migrations/migrate_close_stuck_consultation.py (project root). Safe to run twice.
"""
import sqlite3
import sys

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config

APPOINTMENT_ID = 67
EXPECTED_STATUS = "In Consultation"
CORRECTED_STATUS = "Completed"

# The acting account. Appointment 67 was created and started by user 2 (the
# Health Center Staff account, appointments.scheduled_by = 2), and this closes
# that account's own unfinished visit, so the audit entry is attributed there
# rather than to an administrator who was not involved.
ACTING_USER_ID = 2

NOTE = (
    "Visit started 2026-08-28 23:36 and never written up or closed. "
    "Closed 2026-08-29 as a data correction; no consultation was recorded "
    "for it, and none has been invented."
)

AUDIT_ACTION = "Closed a consultation left open"
AUDIT_MODULE = "Appointment Scheduling"
AUDIT_DETAILS = (
    "Appointment APT-00067 (PAT-026, walk-in on "
    "2026-08-28) was moved from 'In Consultation' to 'Completed'. It was "
    "checked in at 23:36:30 and started at 23:36:36 on 2026-08-28 and was "
    "never completed, so it still held the clinician a day later and refused "
    "every new consultation across the whole system -- only one consultation "
    "may be open at a time, and that rule does not reset overnight. No "
    "consultation record was written for this visit and none was created here: "
    "the appointment is closed, and what was not recorded stays not recorded. "
    "Applied by a one-off correction run against the records."
)


def appointment(conn, appointment_id=APPOINTMENT_ID):
    row = conn.execute(
        "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
    ).fetchone()
    return dict(row) if row else None


def snapshot(conn):
    return {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM appointments ORDER BY id")
    }


def active_ids(conn):
    return [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM appointments WHERE status = ? ORDER BY id",
            (EXPECTED_STATUS,),
        )
    ]


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before = snapshot(conn)
    audit_before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    consultations_before = conn.execute(
        "SELECT COUNT(*) FROM consultations"
    ).fetchone()[0]

    print(f"appointments in table:          {len(before)}")
    print(f"rows In Consultation before:    {active_ids(conn)}")

    row = before.get(APPOINTMENT_ID)
    if row is None:
        print(f"\nAppointment {APPOINTMENT_ID} is not in this database. Nothing to do.")
        conn.close()
        return

    print(f"\nappointment {APPOINTMENT_ID}:")
    for column in ("patient_id", "appointment_date", "status", "notes",
                   "checked_in_at", "created_at", "updated_at"):
        print(f"  {column:<18} {row[column]!r}")

    linked = conn.execute(
        "SELECT COUNT(*) FROM consultations WHERE appointment_id = ?",
        (APPOINTMENT_ID,),
    ).fetchone()[0]
    print(f"  consultations linked to it: {linked}")

    if row["status"] == CORRECTED_STATUS:
        print(f"\nAlready {CORRECTED_STATUS} -- nothing to repair.")
        conn.close()
        return

    if row["status"] != EXPECTED_STATUS:
        print(
            f"\nLeft alone: status is {row['status']!r}, expected "
            f"{EXPECTED_STATUS!r}. This script corrects one known row in one "
            "known state and will not overwrite anything else."
        )
        conn.close()
        sys.exit(1)

    if linked:
        print(
            "\nLeft alone: a consultation record already exists for this "
            "appointment, so it was written up after all and this is not the "
            "abandoned visit this script was written for."
        )
        conn.close()
        sys.exit(1)

    existing_note = (row["notes"] or "").strip()
    corrected_note = f"{existing_note} — {NOTE}" if existing_note else NOTE

    print(f"\napplying:")
    print(f"  status  {row['status']!r} -> {CORRECTED_STATUS!r}")
    print(f"  notes   {row['notes']!r}")
    print(f"       -> {corrected_note!r}")

    conn.execute(
        """
        UPDATE appointments
           SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status = ?
        """,
        (CORRECTED_STATUS, corrected_note, APPOINTMENT_ID, EXPECTED_STATUS),
    )
    conn.execute(
        """
        INSERT INTO audit_logs (user_id, action, module, details)
        VALUES (?, ?, ?, ?)
        """,
        (ACTING_USER_ID, AUDIT_ACTION, AUDIT_MODULE, AUDIT_DETAILS),
    )

    # --- verification, before anything is committed -------------------------
    after = snapshot(conn)
    problems = []

    if len(before) != len(after):
        problems.append(f"row count changed: {len(before)} -> {len(after)}")

    untouched = 0
    for appointment_id, old in before.items():
        new = after.get(appointment_id)
        if new is None:
            problems.append(f"appointment {appointment_id} disappeared")
            continue
        changed = [c for c, v in old.items() if new[c] != v]
        if not changed:
            untouched += 1
            continue
        if appointment_id != APPOINTMENT_ID:
            problems.append(
                f"appointment {appointment_id} was not in scope but changed: {changed}"
            )
            continue
        for column in changed:
            if column not in ("status", "notes", "updated_at"):
                problems.append(
                    f"{column}: {old[column]!r} -> {new[column]!r} "
                    "(outside this migration's remit)"
                )

    corrected = after[APPOINTMENT_ID]
    if corrected["status"] != CORRECTED_STATUS:
        problems.append(f"status is {corrected['status']!r} after the write")
    if NOTE not in (corrected["notes"] or ""):
        problems.append("the note explaining the closure is not on the row")

    # The point of the exercise: the room must be free, and it must be free
    # because this row was closed rather than because something else moved.
    remaining = active_ids(conn)
    if remaining:
        problems.append(
            f"appointments still In Consultation: {remaining} -- expected none"
        )

    # Nothing clinical may have been invented to make the closure look tidy.
    consultations_after = conn.execute(
        "SELECT COUNT(*) FROM consultations"
    ).fetchone()[0]
    if consultations_after != consultations_before:
        problems.append(
            f"consultations changed: {consultations_before} -> "
            f"{consultations_after}. This migration must create none."
        )
    if conn.execute(
        "SELECT COUNT(*) FROM consultations WHERE appointment_id = ?",
        (APPOINTMENT_ID,),
    ).fetchone()[0]:
        problems.append("a consultation record was created for the closed visit")

    audit_after = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    if audit_after != audit_before + 1:
        problems.append(
            f"audit_logs went {audit_before} -> {audit_after}, expected one entry"
        )

    if problems:
        conn.rollback()
        conn.close()
        print("\nMIGRATION PROBLEMS -- nothing was committed:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    conn.commit()

    print(f"\nrows untouched:                 {untouched}")
    print(f"rows In Consultation after:     {active_ids(conn)}")
    print(f"consultations before / after:   {consultations_before} / {consultations_after}")
    print(f"audit_logs before / after:      {audit_before} / {audit_after}")
    conn.close()
    print("\nThe clinician is free. No consultation record was invented.")


if __name__ == "__main__":
    main()
