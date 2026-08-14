"""Migration: reduce the queue to one consultation at a time.

Barangay Poblacion Health Center has a single health worker consulting at any
given moment. Until now "Start Consultation" only wrote a status label -- there
was no rule behind it -- so every patient it was pressed on stayed In
Consultation, and the live database ended up holding six of them at once. That
is not a state the clinic can be in, and it is not a state the repaired code can
produce; this migration brings the existing rows into line with the invariant
start_consultation() now enforces.

WHY THE OTHERS GO BACK TO WAITING, NOT COMPLETED
------------------------------------------------
The one with the latest arrival is the only one that can still plausibly be in
the room, so it keeps its status. For the rest, what actually happened is
unknown: the button was pressed, and nothing recorded whether the patient was
seen, went home, or was never called at all.

'Completed' would assert a consultation took place. On a medical record that is
a claim, not a tidy-up -- it would show in the day's completed count and in the
patient's appointment history as a visit that was carried out, when no
consultation record exists to back it up.

'Waiting' asserts only that the patient arrived, which the checked_in_at column
already proves. They return to the queue where the desk can look at them and
resolve each one properly -- start it, complete it, or mark it No-show. That
leaves the correction visible to staff rather than silently absorbed, which is
the right default for data nobody can reconstruct.

Nothing is deleted, and checked_in_at is untouched, so arrival order survives and
the returned patients queue in the order they actually turned up.

Idempotent -- re-running is a no-op once at most one row is In Consultation.
Run:  python migrate_enforce_single_consultation.py
"""
import sqlite3
import sys

import config

IN_CONSULTATION = "In Consultation"
WAITING = "Waiting"


def active_rows(conn):
    """Every appointment currently In Consultation, newest arrival first.

    Ordered the same way models.appointments.get_active_consultation() orders it,
    so the row this migration keeps is the row that function would have named.
    """
    return conn.execute(
        """
        SELECT a.id, a.patient_id, a.appointment_date, a.checked_in_at,
               p.patient_id AS patient_reference,
               p.first_name, p.last_name
          FROM appointments a
          LEFT JOIN patients p ON p.id = a.patient_id
         WHERE a.status = ?
         ORDER BY a.checked_in_at DESC, a.id DESC
        """,
        (IN_CONSULTATION,),
    ).fetchall()


def describe(row):
    name = " ".join(part for part in (row["first_name"], row["last_name"]) if part)
    return (
        f"id={row['id']:<4} {name or '(patient row missing)':<28} "
        f"{row['patient_reference'] or '—':<9} arrived {row['checked_in_at'] or '—'}"
    )


def main():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row

    before = active_rows(conn)
    before_total = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    print(f"appointments in table:        {before_total}")
    print(f"rows currently In Consultation: {len(before)}")
    for row in before:
        print("  ", describe(row))

    if len(before) <= 1:
        print("\nAt most one consultation is in progress — nothing to repair.")
        conn.close()
        return

    keep = before[0]
    demote = before[1:]
    print(f"\nkeeping In Consultation: {describe(keep)}")
    print(f"returning to Waiting:    {len(demote)} row(s)")
    for row in demote:
        print("  ", describe(row))

    # Everything except the kept row, decided in SQL from the same ordering
    # rather than from the id list, so the write cannot disagree with the report
    # above if a row changed underneath it.
    demote_ids = [row["id"] for row in demote]
    placeholders = ", ".join("?" for _ in demote_ids)
    cursor = conn.execute(
        f"""
        UPDATE appointments
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id IN ({placeholders}) AND status = ?
        """,
        [WAITING] + demote_ids + [IN_CONSULTATION],
    )
    conn.commit()
    changed = cursor.rowcount
    print(f"\nrows changed: {changed}")

    # --- verification ------------------------------------------------------
    problems = []
    if changed != len(demote):
        problems.append(f"expected to change {len(demote)} rows, changed {changed}")

    after = active_rows(conn)
    if len(after) != 1:
        problems.append(f"{len(after)} rows still In Consultation; expected exactly 1")
    elif after[0]["id"] != keep["id"]:
        problems.append(
            f"the remaining consultation is id={after[0]['id']}, expected id={keep['id']}"
        )

    after_total = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    if after_total != before_total:
        problems.append(f"row count changed: {before_total} -> {after_total}")

    # The demoted rows must be Waiting, and must have kept their arrival time --
    # queue order depends on it, and nothing here had any business touching it.
    for row in demote:
        now_row = conn.execute(
            "SELECT status, checked_in_at, patient_id FROM appointments WHERE id = ?",
            (row["id"],),
        ).fetchone()
        if now_row is None:
            problems.append(f"id={row['id']} disappeared")
            continue
        if now_row["status"] != WAITING:
            problems.append(f"id={row['id']} is {now_row['status']!r}, expected {WAITING!r}")
        if now_row["checked_in_at"] != row["checked_in_at"]:
            problems.append(
                f"id={row['id']}.checked_in_at changed: "
                f"{row['checked_in_at']!r} -> {now_row['checked_in_at']!r}"
            )
        if now_row["patient_id"] != row["patient_id"]:
            problems.append(f"id={row['id']}.patient_id changed")

    # Nothing was completed or cancelled on the way through.
    for status in ("Completed", "Cancelled", "No-show"):
        count = conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE status = ?", (status,)
        ).fetchone()[0]
        print(f"{status:<12} rows after migration: {count}")

    conn.close()

    if problems:
        print("\nMIGRATION PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)

    print(
        "\nExactly one consultation in progress; the rest returned to the queue "
        "with their arrival times intact. No row was deleted or completed."
    )


if __name__ == "__main__":
    main()
