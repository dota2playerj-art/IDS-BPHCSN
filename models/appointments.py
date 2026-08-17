"""Appointment queries, including the live consultation queue on Screen 08.

A walk-in and a booked visit are the same kind of record here: a walk-in is an
appointment created at the moment the patient arrives. Everything the queue shows
therefore comes from one table and one query, rather than a union of two sources
that could disagree about who is next.

ONE CONSULTATION AT A TIME
--------------------------
Barangay Poblacion Health Center is a small facility with a single health worker
consulting at any given moment -- the nearby Rural Health Unit is what handles
larger capacity. So the queue is not a set of parallel rooms: at most one
appointment in the whole system is In Consultation, and everyone else who has
arrived is waiting for that one person to finish.

That rule is held in two places, and both are needed:

* start_consultation() refuses in SQL, inside the UPDATE's own WHERE clause, so
  two requests racing each other cannot both find the room empty.
* _apply_queue_flow() derives, for a whole day at once, who may be brought in and
  who is next -- so the screen offers the action only where the model would
  accept it, and the two cannot drift.
"""
import calendar as _calendar
from datetime import date, datetime, timedelta

from database.connection import get_db
from utils.dates import now, recent_months, resolve_range, today

# Statuses that still represent a commitment the patient is expected to keep.
PENDING_STATUSES = ("Scheduled", "Confirmed")

# The full vocabulary the appointments.status CHECK admits, in queue order.
APPOINTMENT_STATUSES = (
    "Scheduled", "Confirmed", "Waiting", "In Consultation",
    "Completed", "Cancelled", "No-show",
)

# The patient has arrived and has not yet been dealt with. These two are what the
# queue is made of.
WAITING = "Waiting"
IN_CONSULTATION = "In Consultation"
COMPLETED = "Completed"
QUEUE_STATUSES = (WAITING, IN_CONSULTATION)

# The label the queue prints for the one patient who may be brought in right now.
#
# WHY THIS IS NOT A STORED STATUS
# -------------------------------
# Barangay Poblacion has one health worker consulting at a time, so "ready to be
# seen" is not an independent fact about a visit -- it is entirely determined by
# two things the database already knows: whether anyone is In Consultation, and
# who arrived first among those Waiting. Storing it would create a second source
# of truth that has to be maintained by every transition that touches the queue,
# and any missed one leaves a row claiming to be ready while somebody else is in
# the room. Deriving it in _apply_queue_flow() makes "at most one ready patient,
# and never while the room is busy" true by construction rather than by upkeep.
#
# This is the same reasoning _STATUS_RANK below already rests on: queue position
# is a presentation rule, not a column.
READY_LABEL = "Ready to Consult"
READY_BADGE_CLASS = "badge-ready"

# Checking in is only meaningful for a visit that has not already been resolved.
# Re-checking in someone already Waiting or In Consultation is a no-op, not a
# second visit, and a Completed/Cancelled/No-show row is closed -- a patient who
# genuinely returns the same day gets a fresh walk-in record instead.
CHECK_IN_FROM_STATUSES = PENDING_STATUSES

# appointment_type recorded when the patient had no prior booking.
WALK_IN_TYPE = "Walk-in Consultation"

# The status an advance booking is created with. Deliberately not Waiting: that
# one means the patient is physically in the building, and _apply_queue_flow()
# will put anyone holding it into the line. A booking made for next Tuesday must
# not appear in a queue until Tuesday, and then only once they arrive -- which is
# what check_in_patient() converts it for.
BOOKED_STATUS = "Scheduled"

# The services that can be booked in advance. Same list the screen's Service
# filter already offers, so the two cannot drift; WALK_IN_TYPE is absent on
# purpose -- a walk-in is by definition not booked ahead, and offering it here
# would let a future appointment claim it had no prior booking.
APPOINTMENT_TYPES = (
    "Consultation",
    "Prenatal Check-up",
    "Immunization",
    "DM / Hypertension Monitoring",
    "Dental",
    "Follow-up Consultation",
)

# Clinic hours and the granularity bookings are taken at. Half-hour slots rather
# than a free-text time for two reasons: the operator cannot mistype 0930 as
# 09:3, and "another patient already has this slot" becomes an exact comparison
# instead of a fuzzy one about how near two times have to be to collide.
CLINIC_OPEN_HOUR = 8
CLINIC_CLOSE_HOUR = 17
SLOT_MINUTES = 30


def _build_time_slots():
    """('08:00', '08:30', ... '16:30') -- every bookable slot in a clinic day.

    The last slot starts one interval before closing, so nothing is booked to
    begin at the moment the doors shut.
    """
    slots = []
    minute = CLINIC_OPEN_HOUR * 60
    end = CLINIC_CLOSE_HOUR * 60
    while minute + SLOT_MINUTES <= end:
        slots.append(f"{minute // 60:02d}:{minute % 60:02d}")
        minute += SLOT_MINUTES
    return tuple(slots)


BOOKING_TIME_SLOTS = _build_time_slots()

# How far ahead a booking may be made. A year covers the longest thing this
# center schedules (an annual maintenance review); beyond that a date is far more
# likely to be a mistyped year than an intention.
BOOKING_HORIZON_DAYS = 365

# Matches the reason/notes length the Check In dialog already allows, so the two
# ways a note reaches appointments.notes agree about how long it may be.
BOOKING_NOTES_MAX = 200

# appointments.status -> the badge class the screens' stylesheets define.
STATUS_BADGE_CLASS = {
    "Scheduled": "badge-scheduled",
    "Confirmed": "badge-scheduled",
    "Waiting": "badge-waiting",
    "In Consultation": "badge-inconsult",
    "Completed": "badge-completed",
    "Cancelled": "badge-cancelled",
    "No-show": "badge-noshow",
}

# Where each status sorts in the queue. In Consultation first because that is who
# the clinician is with right now, then whoever is next, then the not-yet-arrived,
# then everything already resolved. Within a group the ORDER BY breaks ties by
# arrival, then booked time.
_STATUS_RANK = {
    "In Consultation": 0,
    "Waiting": 1,
    "Scheduled": 2,
    "Confirmed": 2,
    "Completed": 3,
    "Cancelled": 4,
    "No-show": 4,
}


def _to_appointment(row):
    appointment = dict(row)
    appointment["status_badge_class"] = STATUS_BADGE_CLASS.get(
        appointment.get("status"), "badge-scheduled"
    )
    # Whether this row is still a plan rather than a visit under way, and
    # therefore whether it can be moved or called off. Derived here, alongside
    # the badge, so the queue, the upcoming list and the profile's Appointment
    # History all decide it the same way -- and so the buttons a screen offers
    # are exactly the ones close_appointment() and reschedule_appointment()
    # would accept.
    appointment["is_open_booking"] = appointment.get("status") in PENDING_STATUSES
    appointment["closures"] = allowed_appointment_closures(appointment)
    return appointment


def _to_queue_entry(row):
    """A queue row plus the derived display fields Screen 08 renders."""
    entry = _to_appointment(row)
    entry["is_waiting"] = entry["status"] == WAITING
    entry["is_in_consultation"] = entry["status"] == IN_CONSULTATION
    entry["in_queue"] = entry["status"] in QUEUE_STATUSES
    entry["walk_in"] = bool(entry.get("is_walkin"))
    # The reference the table's first column shows. appointments has no external
    # identifier column of its own, so it is composed from the row id -- stable,
    # unique, and it cannot drift from the record it names.
    entry["reference"] = f"APT-{entry['id']:05d}"
    entry["arrival_time"] = _clock(entry.get("checked_in_at"))
    entry["booked_time"] = _clock(entry.get("appointment_time"))
    # Whether this row is still a plan rather than a visit in progress, and
    # therefore whether it can be moved or called off. Derived here, next to the
    # other display fields, so the queue, the upcoming list and the profile all
    # decide it the same way -- and so the buttons a screen offers are exactly
    # the ones close_appointment() and reschedule_appointment() would accept.
    return entry


def queue_display_name(entry):
    """A queue row rendered as the name a flash message or stat card should use.

    One helper rather than the same first/last join written out at each call
    site, so the queue, the messages and the stat cards cannot name the same
    patient three different ways.
    """
    if not entry:
        return ""
    return " ".join(
        part for part in (entry.get("first_name"), entry.get("last_name")) if part
    )


def _clock(value):
    """A stored timestamp or time rendered as 'HH:MM', or None.

    Accepts both what checked_in_at holds ('YYYY-MM-DD HH:MM:SS') and what
    appointment_time holds ('HH:MM'), because the queue shows the two side by
    side and neither should need its own formatting rule at the call site.
    """
    if not value:
        return None
    text = str(value).strip()
    if " " in text:
        text = text.split(" ", 1)[1]
    parts = text.split(":")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return None
    return f"{int(parts[0]):02d}:{parts[1][:2]}"


def get_appointments_for_patient(patient_id):
    """Appointment History tab on Screen 04, most recent first."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT a.id, a.appointment_date, a.appointment_time, a.appointment_type,
               a.status, a.notes, u.full_name AS assigned_staff
        FROM appointments a
        LEFT JOIN users u ON u.id = a.assigned_staff_id
        WHERE a.patient_id = ?
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
        """,
        (patient_id,),
    ).fetchall()
    conn.close()
    return [_to_appointment(row) for row in rows]


def get_next_appointment_for_patient(patient_id):
    """Soonest still-upcoming appointment, or None."""
    placeholders = ", ".join("?" for _ in PENDING_STATUSES)
    conn = get_db()
    row = conn.execute(
        f"""
        SELECT a.appointment_date, a.appointment_time, a.appointment_type, a.status
        FROM appointments a
        WHERE a.patient_id = ?
          AND a.status IN ({placeholders})
          AND date(a.appointment_date) >= ?
        ORDER BY a.appointment_date ASC, a.appointment_time ASC
        LIMIT 1
        """,
        # Clinic-local today, not SQLite's date('now'), which is UTC: an
        # appointment booked for today would otherwise drop off this list eight
        # hours early -- mid-afternoon, while the patient is still expected.
        (patient_id, *PENDING_STATUSES, today().isoformat()),
    ).fetchone()
    conn.close()
    return row


_QUEUE_SELECT = """
    SELECT a.id, a.patient_id, a.appointment_type, a.appointment_date,
           a.appointment_time, a.status, a.notes, a.is_walkin, a.checked_in_at,
           a.created_at,
           p.patient_id AS patient_reference,
           p.first_name, p.middle_name, p.last_name, p.sex, p.birth_date,
           u.full_name AS assigned_staff,
           b.full_name AS booked_by
    FROM appointments a
    JOIN patients p ON p.id = a.patient_id
    LEFT JOIN users u ON u.id = a.assigned_staff_id
    LEFT JOIN users b ON b.id = a.scheduled_by
"""


def _apply_queue_flow(entries):
    """Add the single-active-consultation fields to an ordered queue.

    The clinic sees one patient at a time, so the whole of that rule is decided
    here, once, from the day's rows -- and every screen, message and stat card
    reads the answer off these fields rather than working it out again:

        line_position   place in the waiting line, 1-based; None once seen
        can_start       this patient may be brought in now
        is_ready        ... and is the one who should be, being first in line
        is_next_up      first in line, whether or not the room is free yet
        can_complete    this is the consultation currently in progress

    can_start is granted to every waiting patient while the room is free, not
    only the first: the desk can legitimately take an urgent case out of turn,
    and refusing that would put the software's ordering above the clinician's
    judgement. is_ready still points at whoever arrived first, so the queue says
    who is *due* next even when it permits an exception.

    The moment anyone is In Consultation, can_start is false for everyone else --
    that is the enforcement Gap 1 was about. It is re-checked in SQL inside
    start_consultation() as well, because a page can go stale between render and
    click.
    """
    entries = list(entries)
    active = next((entry for entry in entries if entry["is_in_consultation"]), None)
    room_free = active is None

    for entry in entries:
        entry["line_position"] = None
        entry["can_start"] = False
        entry["is_ready"] = False
        entry["is_next_up"] = False
        entry["can_complete"] = entry["is_in_consultation"]

    # entries arrive sorted by _STATUS_RANK then arrival, so the Waiting rows are
    # already in first-come order and index 0 is whoever has queued longest.
    for index, entry in enumerate(entry for entry in entries if entry["is_waiting"]):
        entry["line_position"] = index + 1
        entry["can_start"] = room_free
        entry["is_next_up"] = index == 0
        entry["is_ready"] = room_free and index == 0

    for entry in entries:
        # "Ready to Consult" replaces the stored "Waiting" only for display. The
        # row is still Waiting in the database -- see READY_LABEL.
        entry["display_status"] = READY_LABEL if entry["is_ready"] else entry["status"]
        entry["display_badge_class"] = (
            READY_BADGE_CLASS if entry["is_ready"] else entry["status_badge_class"]
        )

    return entries


def get_todays_appointments(on_date=None):
    """Every appointment for the clinic-local day, in queue order.

    Ordering is done in Python rather than SQL because the status ranking is a
    presentation rule, not a property of the data -- putting it in a CASE inside
    the query would hide it from anything else that needs the same order.
    """
    day = (on_date or today()).isoformat()
    conn = get_db()
    rows = conn.execute(
        _QUEUE_SELECT + " WHERE date(a.appointment_date) = ?",
        (day,),
    ).fetchall()
    conn.close()

    entries = [_to_queue_entry(row) for row in rows]
    entries.sort(
        key=lambda entry: (
            _STATUS_RANK.get(entry["status"], 9),
            # Arrival first, so the queue is first-come first-served; the booked
            # time only breaks ties among people who have not arrived yet.
            entry["checked_in_at"] or "",
            entry["appointment_time"] or "",
            entry["id"],
        )
    )
    return _apply_queue_flow(entries)


def get_queue_entry(appointment_id, on_date=None):
    """One appointment as today's queue sees it -- flow fields included -- or None.

    Deliberately routed through get_todays_appointments() rather than fetching
    the row alone: is_ready and can_start only mean anything relative to the rest
    of the day, so answering "is this patient ready?" has to be the same
    computation the screen ran, not a second one that could disagree with it.
    """
    for entry in get_todays_appointments(on_date):
        if entry["id"] == appointment_id:
            return entry
    return None


def get_queue_stats(entries=None):
    """The figures Screen 08's stat cards and footer show for today.

    Accepts an already-fetched list so the screen does not query twice for the
    same day.

    ready / still_waiting / in_consultation are disjoint by construction, so the
    footer can print them side by side and have them add up to the number of
    people actually in the building.
    """
    if entries is None:
        entries = get_todays_appointments()

    waiting = [entry for entry in entries if entry["is_waiting"]]
    ready = [entry for entry in waiting if entry["is_ready"]]
    active = next((entry for entry in entries if entry["is_in_consultation"]), None)
    next_up = next((entry for entry in waiting if entry["is_next_up"]), None)

    return {
        "total_today": len(entries),
        "walk_ins": sum(1 for entry in entries if entry["walk_in"]),
        # Everyone checked in and not yet with the clinician -- the waiting room.
        "waiting": len(waiting),
        # At most 1: the patient who may be brought in now.
        "ready": len(ready),
        # The waiting room minus that one, so the two never double-count.
        "still_waiting": len(waiting) - len(ready),
        # At most 1 as well, and enforced as such by start_consultation().
        "in_consultation": sum(1 for entry in entries if entry["is_in_consultation"]),
        "completed": sum(1 for entry in entries if entry["status"] == COMPLETED),
        "not_arrived": sum(
            1 for entry in entries if entry["status"] in PENDING_STATUSES
        ),
        "room_free": active is None,
        "active_name": queue_display_name(active),
        "next_up_name": queue_display_name(next_up),
    }


def get_appointment_by_id(appointment_id):
    """One appointment with its patient, or None.

    Carries the display fields but not the flow fields -- those only exist
    relative to a whole day's queue. Use get_queue_entry() when the answer
    depends on who else is in the room.
    """
    conn = get_db()
    row = conn.execute(_QUEUE_SELECT + " WHERE a.id = ?", (appointment_id,)).fetchone()
    conn.close()
    return _to_queue_entry(row) if row else None


def count_active_consultations():
    """How many appointments are In Consultation anywhere in the system.

    The invariant this whole module exists to hold is that this is 0 or 1. Kept
    as a plain count over the raw table -- no join, no date filter -- so it can
    be trusted as the check on that invariant rather than reporting only what the
    queue screen happens to render.
    """
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM appointments WHERE status = ?", (IN_CONSULTATION,)
    ).fetchone()[0]
    conn.close()
    return count


def get_active_consultation():
    """The appointment currently In Consultation, or None.

    Not scoped to a date. The health center has one worker consulting at a time,
    so "is the room free?" is a question about the room, not about today's page:
    a consultation left open when the clinic closed still occupies the clinician
    as far as this system is concerned, and hiding it behind a date filter would
    let a second one be started beside it.

    Ordered newest-arrival-first so that if a legacy database still holds several
    (which is exactly what migrate_enforce_single_consultation.py repairs) this
    names the most recently started one rather than an arbitrary row.
    """
    conn = get_db()
    row = conn.execute(
        _QUEUE_SELECT
        + " WHERE a.status = ? ORDER BY a.checked_in_at DESC, a.id DESC LIMIT 1",
        (IN_CONSULTATION,),
    ).fetchone()
    conn.close()
    return _to_queue_entry(row) if row else None


def find_todays_appointment(patient_id, on_date=None):
    """This patient's still-open booking for today, or None.

    "Still open" means Scheduled or Confirmed: the booking they are turning up
    for. A row already Waiting or In Consultation is deliberately not returned --
    check_in_patient() treats that as an already-checked-in patient, which is a
    different outcome from having a booking to convert.
    """
    day = (on_date or today()).isoformat()
    placeholders = ", ".join("?" for _ in CHECK_IN_FROM_STATUSES)
    conn = get_db()
    row = conn.execute(
        f"""
        SELECT * FROM appointments
        WHERE patient_id = ?
          AND date(appointment_date) = ?
          AND status IN ({placeholders})
        ORDER BY appointment_time IS NULL, appointment_time, id
        LIMIT 1
        """,
        (patient_id, day, *CHECK_IN_FROM_STATUSES),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def find_active_queue_entry(patient_id, on_date=None):
    """This patient's row for today that is already in the queue, or None."""
    day = (on_date or today()).isoformat()
    placeholders = ", ".join("?" for _ in QUEUE_STATUSES)
    conn = get_db()
    row = conn.execute(
        f"""
        SELECT * FROM appointments
        WHERE patient_id = ?
          AND date(appointment_date) = ?
          AND status IN ({placeholders})
        ORDER BY id
        LIMIT 1
        """,
        (patient_id, day, *QUEUE_STATUSES),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def check_in_patient(patient_id, reason, user_id, on_date=None):
    """Put a patient in today's queue. Returns (appointment_id, outcome).

    outcome is one of:

        "updated"        they had a booking for today; that row became Waiting
        "created"        no booking, so a walk-in record was created
        "already"        they are already Waiting or In Consultation

    Converting an existing booking rather than inserting alongside it is the
    whole point of the lookup: a patient who booked and then arrived must not end
    up as two rows in the queue, which is what a plain INSERT would produce.

    is_walkin is set only on the created path, and never cleared on the updated
    one, so the flag keeps saying whether there was a prior booking.

    Both paths store WAITING, including when the clinician is free and the
    patient can go straight in. "Ready to Consult" is not stored -- the queue
    derives it in _apply_queue_flow(), so a patient who arrives to an empty room
    is shown as ready without ever being written as Waiting-and-then-something-
    else, and cannot be left stranded on a stale ready flag if someone else is
    brought in first. See READY_LABEL.
    """
    day = (on_date or today()).isoformat()
    stamp = now().strftime("%Y-%m-%d %H:%M:%S")
    reason = (reason or "").strip() or None

    existing = find_active_queue_entry(patient_id, on_date=on_date)
    if existing:
        return existing["id"], "already"

    booked = find_todays_appointment(patient_id, on_date=on_date)
    conn = get_db()
    if booked:
        conn.execute(
            """
            UPDATE appointments
               SET status = ?,
                   checked_in_at = ?,
                   -- The reason given at the desk is appended rather than
                   -- overwriting whatever the booking already said.
                   notes = CASE
                             WHEN ? IS NULL THEN notes
                             WHEN notes IS NULL OR TRIM(notes) = '' THEN ?
                             ELSE notes || ' — ' || ?
                           END,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (WAITING, stamp, reason, reason, reason, booked["id"]),
        )
        conn.commit()
        appointment_id = booked["id"]
        outcome = "updated"
    else:
        cursor = conn.execute(
            """
            INSERT INTO appointments
                (patient_id, scheduled_by, appointment_type, appointment_date,
                 appointment_time, status, notes, is_walkin, checked_in_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                patient_id,
                user_id,
                WALK_IN_TYPE,
                day,
                # A walk-in has no booked slot; the arrival time is the only time
                # that means anything, and it is kept in checked_in_at.
                None,
                WAITING,
                reason,
                stamp,
            ),
        )
        conn.commit()
        appointment_id = cursor.lastrowid
        outcome = "created"

    conn.close()
    return appointment_id, outcome


def start_consultation(appointment_id):
    """Bring one Waiting patient in. Returns the outcome:

        "started"      they are now In Consultation
        "busy"         someone else is In Consultation; nothing changed
        "already"      this row is already In Consultation
        "not-waiting"  the row is Scheduled/Completed/... , so it cannot start
        "missing"      no such appointment

    WHY THE GUARD IS IN THE SQL
    ---------------------------
    The obvious shape -- read whether anyone is In Consultation, decide, then
    UPDATE -- has a window between the read and the write. Two check-in desks,
    or one operator double-clicking, or a page left open while a colleague
    starts someone else, all land two writes inside that window and both see an
    empty room. That is precisely how the six simultaneous "In Consultation"
    rows in the existing database came about.

    Putting `NOT EXISTS (... In Consultation ...)` in the UPDATE's WHERE makes
    the check and the write one statement, which SQLite evaluates atomically.
    The loser of a race changes nothing and its rowcount is 0, so it is reported
    honestly rather than silently overwriting the winner.

    `AND status = ?` in the same WHERE keeps the other half of the rule: only a
    waiting patient can be brought in, so a Completed visit cannot be quietly
    reopened and lose the record of it having ended.
    """
    conn = get_db()
    cursor = conn.execute(
        """
        UPDATE appointments
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
           AND status = ?
           AND NOT EXISTS (
                 SELECT 1 FROM appointments busy WHERE busy.status = ?
               )
        """,
        (IN_CONSULTATION, appointment_id, WAITING, IN_CONSULTATION),
    )
    conn.commit()

    if cursor.rowcount == 1:
        conn.close()
        return "started"

    # Nothing was written, so say which of the WHERE's conditions refused.
    row = conn.execute(
        "SELECT status FROM appointments WHERE id = ?", (appointment_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return "missing"
    if row["status"] == IN_CONSULTATION:
        return "already"
    if row["status"] != WAITING:
        return "not-waiting"
    # Still Waiting and still not started: the only remaining refusal is the
    # NOT EXISTS, i.e. the clinician is with someone else.
    return "busy"


def complete_consultation(appointment_id):
    """Close the consultation in progress. Returns the outcome:

        "completed"           the visit is now Completed
        "already"             it was already Completed
        "not-in-consultation" it is not the visit currently in progress
        "missing"             no such appointment

    This is the transition that releases the room: the next Waiting patient
    becomes startable the moment it lands, which the queue picks up on its next
    render through _apply_queue_flow(). Recording *what happened* in the
    consultation is a separate concern and is not touched here.

    Guarded in the WHERE for the same reason as start_consultation(): only the
    visit actually in progress may be completed, so a stale page cannot close a
    patient who never went in.
    """
    conn = get_db()
    cursor = conn.execute(
        """
        UPDATE appointments
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status = ?
        """,
        (COMPLETED, appointment_id, IN_CONSULTATION),
    )
    conn.commit()

    if cursor.rowcount == 1:
        conn.close()
        return "completed"

    row = conn.execute(
        "SELECT status FROM appointments WHERE id = ?", (appointment_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return "missing"
    if row["status"] == COMPLETED:
        return "already"
    return "not-in-consultation"


# ---------------------------------------------------------------------------
# ADVANCE BOOKING
#
# Everything above this line is about today: who has arrived, who is with the
# clinician, who is next. Everything below is about a day that has not happened
# yet -- creating the commitment, and showing it -- and the join between the two
# is deliberately narrow: a booking is an ordinary appointments row with status
# Scheduled and is_walkin = 0, so when its date becomes today it is picked up by
# find_todays_appointment() and converted by check_in_patient() with no separate
# "arrivals" mechanism to keep in step.
# ---------------------------------------------------------------------------


def parse_iso_date(value):
    """'2026-08-20' -> date, or None if it is absent or malformed."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def validate_booking_form(values, staff_ids=()):
    """Server-side validation for an advance booking. Returns {field: message}.

    Same contract as validate_patient_form(): an empty dict means valid, and the
    caller redisplays the form with these messages against their fields. Run on
    the server rather than trusted from the dialog, because a POST can be made
    without ever opening it.

    What is refused here is only what is certainly wrong -- a missing patient, a
    date that is not in the future, a service or slot the form never offered.
    Whether the slot is *busy* is a different question and is deliberately not
    answered here; see find_scheduling_conflicts(), which warns rather than
    refuses.
    """
    errors = {}

    raw_patient = str(values.get("patient_id") or "").strip()
    if not raw_patient.isdigit():
        errors["patient_id"] = "Choose the patient this appointment is for."

    raw_date = (values.get("appointment_date") or "").strip()
    booking_date = parse_iso_date(raw_date)
    if not raw_date:
        errors["appointment_date"] = "Choose the date of the appointment."
    elif booking_date is None:
        errors["appointment_date"] = "Enter a valid date in YYYY-MM-DD format."
    else:
        current = today()
        if booking_date <= current:
            # Same-day arrivals are the Check In Patient action, which puts the
            # patient straight into the queue. Booking one here would create a
            # Scheduled row for a person already standing at the desk.
            errors["appointment_date"] = (
                "Advance bookings are for a future date. To record someone who is "
                "here today, use Check In Patient instead."
            )
        elif booking_date > current + timedelta(days=BOOKING_HORIZON_DAYS):
            errors["appointment_date"] = (
                f"Appointments can be booked up to {BOOKING_HORIZON_DAYS} days ahead "
                f"(no later than {(current + timedelta(days=BOOKING_HORIZON_DAYS)).isoformat()})."
            )

    appointment_time = (values.get("appointment_time") or "").strip()
    if not appointment_time:
        errors["appointment_time"] = "Choose a time slot."
    elif appointment_time not in BOOKING_TIME_SLOTS:
        errors["appointment_time"] = (
            f"Choose a time from the list — the clinic books "
            f"{BOOKING_TIME_SLOTS[0]} to {BOOKING_TIME_SLOTS[-1]} in "
            f"{SLOT_MINUTES}-minute slots."
        )

    appointment_type = (values.get("appointment_type") or "").strip()
    if not appointment_type:
        errors["appointment_type"] = "Choose what the appointment is for."
    elif appointment_type not in APPOINTMENT_TYPES:
        errors["appointment_type"] = "Choose a service from the list."

    raw_staff = str(values.get("assigned_staff_id") or "").strip()
    if raw_staff:
        allowed = {str(staff_id) for staff_id in staff_ids}
        if raw_staff not in allowed:
            errors["assigned_staff_id"] = "Choose a staff member from the list."

    notes = (values.get("notes") or "").strip()
    if len(notes) > BOOKING_NOTES_MAX:
        errors["notes"] = f"Keep the note to {BOOKING_NOTES_MAX} characters or fewer."

    return errors


def find_scheduling_conflicts(patient_id, appointment_date, appointment_time,
                              exclude_appointment_id=None):
    """What is already booked that a proposed booking would run into.

    `exclude_appointment_id` leaves one row out of the comparison. Rescheduling
    needs it: an appointment moved to another time on its own day would
    otherwise find itself sitting there and report the patient as clashing with
    themselves.

    Returns {"slot": [...], "patient_day": [...]} -- two different problems, kept
    apart because they mean different things to whoever is at the desk:

        slot         other patients already booked for that exact date and time.
                     One clinician sees one patient at a time, so a second name
                     in a slot means somebody waits. Common and often deliberate
                     (a mother bringing two children, a slot known to run short),
                     which is why it warns rather than refuses.

        patient_day  this same patient already has a booking on that date. Much
                     more likely to be a double entry than an intention, and it
                     matters more: check_in_patient() converts the earliest
                     pending booking of the day, so the second row would be left
                     behind as a Scheduled appointment nobody ever closes.

    Only pending rows count. A Completed, Cancelled or No-show appointment in the
    slot is history, not a clash.
    """
    booking_date = parse_iso_date(appointment_date)
    if booking_date is None:
        return {"slot": [], "patient_day": []}

    day = booking_date.isoformat()
    placeholders = ", ".join("?" for _ in PENDING_STATUSES)
    conn = get_db()
    rows = conn.execute(
        _QUEUE_SELECT
        + f"""
        WHERE date(a.appointment_date) = ?
          AND a.status IN ({placeholders})
        ORDER BY a.appointment_time IS NULL, a.appointment_time, a.id
        """,
        (day, *PENDING_STATUSES),
    ).fetchall()
    conn.close()

    entries = [
        _to_queue_entry(row) for row in rows
        if exclude_appointment_id is None or row["id"] != int(exclude_appointment_id)
    ]
    wanted_time = (appointment_time or "").strip()
    patient_id = int(patient_id) if str(patient_id).isdigit() else None

    return {
        "slot": [
            entry for entry in entries
            if entry["patient_id"] != patient_id
            and wanted_time
            and (entry["appointment_time"] or "").strip() == wanted_time
        ],
        "patient_day": [
            entry for entry in entries if entry["patient_id"] == patient_id
        ],
    }


def create_appointment(patient_id, user_id, appointment_date, appointment_time,
                       appointment_type, notes=None, assigned_staff_id=None):
    """Book a future visit. Returns the new appointment's id.

    status is BOOKED_STATUS and is_walkin is 0, both written explicitly rather
    than left to the column defaults, because they are the two facts that make
    this row a booking: nobody has arrived, and there *was* a prior booking when
    they eventually do.

    checked_in_at is left NULL -- it is arrival time, and nobody has arrived.
    """
    notes = (notes or "").strip() or None
    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO appointments
            (patient_id, scheduled_by, appointment_type, appointment_date,
             appointment_time, assigned_staff_id, status, notes, is_walkin)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            patient_id,
            user_id,
            appointment_type,
            appointment_date,
            appointment_time,
            assigned_staff_id,
            BOOKED_STATUS,
            notes,
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


# ---------------------------------------------------------------------------
# CHANGING A BOOKING THAT HAS ALREADY BEEN MADE
#
# Both actions below are guarded on PENDING_STATUSES, and that one condition is
# doing all the work. A booking may be called off or moved only while nobody has
# arrived for it: the moment check_in_patient() converts it to Waiting the row
# stops being a plan and becomes a patient in the building, and neither cancelling
# them nor moving them to next Tuesday describes anything that could happen.
#
# Note that this is a status rule, not a date rule -- which is what makes the
# awkward case fall out for free. A booking made for today that the patient rings
# to call off is still Scheduled, so it can be cancelled; and once cancelled it
# leaves PENDING_STATUSES, so find_todays_appointment() stops offering it to
# check-in and get_queue_stats() stops counting it as not-yet-arrived. Nothing in
# the queue needed a special case for it.
# ---------------------------------------------------------------------------

# The two ways a booking ends without the patient ever being seen. Both are
# closures, not deletions: the row stays, exactly as an Inactive patient record
# stays -- see set_patient_status() for the same principle on Screen 03.
CANCELLED = "Cancelled"
NO_SHOW = "No-show"
CLOSURE_STATUSES = (CANCELLED, NO_SHOW)

# Only a booking nobody has turned up for can be cancelled, moved or written off.
OPEN_BOOKING_STATUSES = PENDING_STATUSES


def allowed_appointment_closures(appointment, on_date=None):
    """Which of Cancelled / No-show this appointment may be moved to.

    The direct counterpart of models/patients.py allowed_status_transitions(),
    and the dialog that offers these is the same dialog shape Screen 03 uses --
    a record's current state decides what it is offered, so no button is ever
    present that the server would then refuse.

    Cancelled is always available on an open booking: calling off a visit is
    something that can be decided at any point before it happens.

    No-show is not, because it is a statement about a day that has already run
    its course. Offering it on next Tuesday's appointment would invite the desk
    to record an absence from a day nobody has lived through yet.
    """
    if not appointment or appointment.get("status") not in OPEN_BOOKING_STATUSES:
        return ()

    reference = on_date or today()
    booking_date = parse_iso_date(appointment.get("appointment_date"))
    if booking_date is not None and booking_date <= reference:
        return CLOSURE_STATUSES
    return (CANCELLED,)


def close_appointment(appointment_id, status, on_date=None):
    """Cancel a booking or write it off as a no-show. Returns the outcome:

        "closed"       the booking now holds `status`
        "already"      it already held it
        "arrived"      the patient is in the queue, so it is not ours to close
        "resolved"     it is already Completed/Cancelled/No-show
        "too-early"    No-show asked for a day that has not happened yet
        "missing"      no such appointment

    GUARDED IN THE SQL, for the reason start_consultation() is
    ------------------------------------------------------------
    The status is re-checked inside the UPDATE's own WHERE rather than read
    first and decided in Python. A queue screen can sit open on somebody's desk
    for an hour; in that time the patient can walk in and be checked in by a
    colleague. Cancelling from that stale page must not reach past the check-in
    and close a visit that is now in progress, and putting the condition in the
    WHERE is what makes the check and the write one indivisible step.

    The row is never deleted. A cancelled appointment is part of the patient's
    history -- it says the clinic held a slot and the visit did not happen, which
    is exactly the thing a defaulter follow-up needs to know.
    """
    if status not in CLOSURE_STATUSES:
        raise ValueError(
            f"{status!r} is not a way of closing a booking; expected one of "
            f"{CLOSURE_STATUSES}."
        )

    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "missing"
    if appointment["status"] == status:
        return "already"
    if status not in allowed_appointment_closures(appointment, on_date):
        # Either it is not an open booking at all, or it is No-show on a future
        # date. Say which, so the message can explain rather than just refuse.
        if appointment["status"] in QUEUE_STATUSES:
            return "arrived"
        if appointment["status"] not in OPEN_BOOKING_STATUSES:
            return "resolved"
        return "too-early"

    placeholders = ", ".join("?" for _ in OPEN_BOOKING_STATUSES)
    conn = get_db()
    cursor = conn.execute(
        f"""
        UPDATE appointments
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status IN ({placeholders})
        """,
        (status, appointment_id, *OPEN_BOOKING_STATUSES),
    )
    conn.commit()
    changed = cursor.rowcount
    conn.close()

    if changed == 1:
        return "closed"

    # Nothing was written, so the row moved between the read above and the write.
    current = get_appointment_by_id(appointment_id)
    if current is None:
        return "missing"
    if current["status"] == status:
        return "already"
    if current["status"] in QUEUE_STATUSES:
        return "arrived"
    return "resolved"


def reschedule_appointment(appointment_id, appointment_date, appointment_time):
    """Move an open booking to a new date and time. Returns the outcome:

        "moved"      the booking now sits at the new slot
        "unchanged"  the new slot is the one it already had
        "arrived"    the patient is in the queue; the visit is happening
        "resolved"   already Completed/Cancelled/No-show
        "missing"    no such appointment

    Deliberately an UPDATE of the existing row rather than a cancel-and-rebook.
    The commitment is the same commitment -- same patient, same reason, same
    person who booked it -- and splitting it in two would leave a Cancelled row
    that reads as a visit called off, next to a new booking that looks like it
    was arranged from scratch. The patient's history would then describe
    something that never happened.

    Only appointment_date and appointment_time move. patient_id,
    appointment_type, notes, assigned_staff_id and scheduled_by are all left
    untouched by this statement, so what the visit is *for* survives being moved.

    Guarded on the open statuses in the WHERE, for the reason close_appointment()
    explains at length.
    """
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "missing"
    if appointment["status"] in QUEUE_STATUSES:
        return "arrived"
    if appointment["status"] not in OPEN_BOOKING_STATUSES:
        return "resolved"
    if (
        (appointment["appointment_date"] or "")[:10] == appointment_date
        and (appointment["appointment_time"] or "") == appointment_time
    ):
        return "unchanged"

    placeholders = ", ".join("?" for _ in OPEN_BOOKING_STATUSES)
    conn = get_db()
    cursor = conn.execute(
        f"""
        UPDATE appointments
           SET appointment_date = ?, appointment_time = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status IN ({placeholders})
        """,
        (appointment_date, appointment_time, appointment_id, *OPEN_BOOKING_STATUSES),
    )
    conn.commit()
    changed = cursor.rowcount
    conn.close()

    if changed == 1:
        return "moved"

    current = get_appointment_by_id(appointment_id)
    if current is None:
        return "missing"
    if current["status"] in QUEUE_STATUSES:
        return "arrived"
    return "resolved"


def _to_upcoming_entry(row, reference=None):
    """A future booking with the fields the upcoming list and calendar print."""
    entry = _to_queue_entry(row)
    reference = reference or today()
    booking_date = parse_iso_date(entry.get("appointment_date"))
    entry["days_away"] = (booking_date - reference).days if booking_date else None
    if entry["days_away"] == 1:
        entry["when_label"] = "Tomorrow"
    elif entry["days_away"] is not None and entry["days_away"] < 7:
        entry["when_label"] = booking_date.strftime("%A")
    elif booking_date:
        entry["when_label"] = booking_date.strftime("%b %d")
    else:
        entry["when_label"] = ""
    return entry


def get_upcoming_appointments(limit=None, from_date=None):
    """Bookings still to come, soonest first.

    Strictly after the clinic-local today: everything dated today already appears
    in the queue below, and a screen that listed it twice would leave the desk
    unsure which of the two entries to act on.
    """
    reference = from_date or today()
    placeholders = ", ".join("?" for _ in PENDING_STATUSES)
    sql = (
        _QUEUE_SELECT
        + f"""
        WHERE date(a.appointment_date) > ?
          AND a.status IN ({placeholders})
        ORDER BY a.appointment_date ASC, a.appointment_time IS NULL,
                 a.appointment_time ASC, a.id ASC
        """
    )
    parameters = [reference.isoformat(), *PENDING_STATUSES]
    if limit:
        sql += " LIMIT ?"
        parameters.append(int(limit))

    conn = get_db()
    rows = conn.execute(sql, parameters).fetchall()
    conn.close()
    return [_to_upcoming_entry(row, reference) for row in rows]


def get_upcoming_stats(entries=None, from_date=None):
    """The figures the Upcoming Appointments panel prints above its list."""
    reference = from_date or today()
    if entries is None:
        entries = get_upcoming_appointments(from_date=reference)

    days = {entry["appointment_date"][:10] for entry in entries}
    return {
        "total": len(entries),
        "next_seven_days": sum(
            1 for entry in entries
            if entry["days_away"] is not None and entry["days_away"] <= 7
        ),
        "tomorrow": sum(1 for entry in entries if entry["days_away"] == 1),
        "days_with_bookings": len(days),
    }


def get_slot_load(from_date=None):
    """{date: {time: [patient names]}} for every pending future booking.

    Handed to the booking dialog so the time dropdown can say which slots the
    chosen day already has somebody in, before the operator picks one. The same
    rows find_scheduling_conflicts() would warn about afterwards -- shown early
    so the usual case is a clash avoided rather than a warning acknowledged.
    """
    load = {}
    for entry in get_upcoming_appointments(from_date=from_date):
        slot_time = (entry.get("appointment_time") or "").strip()
        if not slot_time:
            continue
        day = entry["appointment_date"][:10]
        load.setdefault(day, {}).setdefault(slot_time, []).append(
            queue_display_name(entry)
        )
    return load


def get_appointment_day_summary(start_date, end_date):
    """{ISO date: counts} over an inclusive range, for the calendar grid.

    One grouped query for the whole month rather than one per cell. The three
    buckets match the legend the calendar already prints: still to happen,
    finished, and called off.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT date(appointment_date) AS day, status, COUNT(*) AS count
        FROM appointments
        WHERE date(appointment_date) BETWEEN ? AND ?
        GROUP BY day, status
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    conn.close()

    summary = {}
    for row in rows:
        bucket = summary.setdefault(
            row["day"],
            {"total": 0, "pending": 0, "in_queue": 0, "completed": 0, "cancelled": 0},
        )
        bucket["total"] += row["count"]
        if row["status"] in PENDING_STATUSES:
            bucket["pending"] += row["count"]
        elif row["status"] in QUEUE_STATUSES:
            bucket["in_queue"] += row["count"]
        elif row["status"] == COMPLETED:
            bucket["completed"] += row["count"]
        else:
            bucket["cancelled"] += row["count"]
    return summary


# ---------------------------------------------------------------------------
# REPORTING
#
# Screen 10's appointment figures. appointment_date is a plain clinic-local date
# ('2026-08-13'), never a UTC stamp, so these group on substr() of it directly --
# no timezone conversion is needed or wanted here, unlike the patients.created_at
# windows which do have to cross from UTC.
# ---------------------------------------------------------------------------

# The three outcomes Screen 10's Appointment Statistics chart stacks. Every
# status the CHECK admits maps into exactly one of them, so the bars sum to the
# month's total appointments and nothing is quietly dropped.
OUTCOME_EXPECTED = "Expected"       # Scheduled / Confirmed -- still to happen
OUTCOME_ATTENDED = "Attended"       # Waiting / In Consultation / Completed
OUTCOME_MISSED = "Missed"           # Cancelled / No-show

_OUTCOME_BY_STATUS = {
    "Scheduled": OUTCOME_EXPECTED,
    "Confirmed": OUTCOME_EXPECTED,
    "Waiting": OUTCOME_ATTENDED,
    "In Consultation": OUTCOME_ATTENDED,
    "Completed": OUTCOME_ATTENDED,
    "Cancelled": OUTCOME_MISSED,
    "No-show": OUTCOME_MISSED,
}

OUTCOMES = (OUTCOME_EXPECTED, OUTCOME_ATTENDED, OUTCOME_MISSED)


def _outcome_summary(counts, walk_ins, total, services):
    """One period's appointment outcomes, however that period was chosen.

    Shared by the year-to-date block and the ranged `window` block below so the
    two cannot compute an attendance rate differently. The rate is of *resolved*
    appointments for the reason get_appointment_report() gives.
    """
    resolved = counts[OUTCOME_ATTENDED] + counts[OUTCOME_MISSED]
    return {
        "total": total,
        "expected": counts[OUTCOME_EXPECTED],
        "attended": counts[OUTCOME_ATTENDED],
        "missed": counts[OUTCOME_MISSED],
        "walk_ins": walk_ins,
        "booked": total - walk_ins,
        "resolved": resolved,
        "attendance_pct": (
            round(counts[OUTCOME_ATTENDED] / resolved * 100, 1) if resolved else None
        ),
        "missed_pct": (
            round(counts[OUTCOME_MISSED] / resolved * 100, 1) if resolved else None
        ),
        "services": sorted(
            ({"service": name, "count": count} for name, count in services.items()),
            key=lambda item: (-item["count"], item["service"].lower()),
        ),
    }


def get_appointment_report(months=6, on_date=None, start=None, end=None):
    """The appointment figures Screen 10 reports.

    Three things: how the year's appointments have turned out, how that breaks
    down month by month, and which services were actually asked for.

    WHY 'ATTENDED' AND NOT 'COMPLETED'
    ----------------------------------
    A visit that is Waiting or In Consultation right now is a patient who turned
    up; it is only not Completed because the day has not finished. Bucketing it
    with Completed keeps the attendance rate from dipping every afternoon and
    recovering overnight, which would be an artefact of when the report is read
    rather than anything about the clinic.

    The rates are of *resolved* appointments -- Attended plus Missed -- because
    an appointment still to happen has not yet succeeded or failed at anything,
    and counting it as neither is what stops next month's bookings from dragging
    the attendance rate down.
    """
    reference = on_date or today()
    window = resolve_range(start=start, end=end, months=months, on_date=reference)
    year = reference.strftime("%Y")
    lo, hi = window["start"].isoformat(), window["end"].isoformat()

    conn = get_db()
    rows = conn.execute(
        """
        SELECT substr(appointment_date, 1, 7) AS month, status, is_walkin,
               appointment_type, COUNT(*) AS count
        FROM appointments
        GROUP BY month, status, is_walkin, appointment_type
        """
    ).fetchall()
    # The window's own rows, by day rather than by month: a range starting on the
    # 12th must not be handed the whole of that month. appointment_date is stored
    # as clinic-local date text, so it compares directly.
    scoped = conn.execute(
        """
        SELECT substr(appointment_date, 1, 7) AS month, status, is_walkin,
               appointment_type, COUNT(*) AS count
        FROM appointments
        WHERE substr(appointment_date, 1, 10) BETWEEN ? AND ?
        GROUP BY month, status, is_walkin, appointment_type
        """,
        (lo, hi),
    ).fetchall()
    conn.close()

    by_month = {}
    ytd = {outcome: 0 for outcome in OUTCOMES}
    ytd_total = 0
    ytd_walk_ins = 0
    services = {}

    for row in rows:
        outcome = _OUTCOME_BY_STATUS.get(row["status"], OUTCOME_EXPECTED)
        bucket = by_month.setdefault(
            row["month"], {name: 0 for name in OUTCOMES} | {"total": 0}
        )
        bucket[outcome] += row["count"]
        bucket["total"] += row["count"]

        if (row["month"] or "").startswith(year):
            ytd[outcome] += row["count"]
            ytd_total += row["count"]
            if row["is_walkin"]:
                ytd_walk_ins += row["count"]
            service = (row["appointment_type"] or "").strip() or "Unspecified"
            services[service] = services.get(service, 0) + row["count"]

    scoped_counts = {outcome: 0 for outcome in OUTCOMES}
    scoped_total = 0
    scoped_walk_ins = 0
    scoped_services = {}
    scoped_by_month = {}
    for row in scoped:
        outcome = _OUTCOME_BY_STATUS.get(row["status"], OUTCOME_EXPECTED)
        scoped_counts[outcome] += row["count"]
        scoped_total += row["count"]
        if row["is_walkin"]:
            scoped_walk_ins += row["count"]
        service = (row["appointment_type"] or "").strip() or "Unspecified"
        scoped_services[service] = scoped_services.get(service, 0) + row["count"]
        bucket = scoped_by_month.setdefault(
            row["month"], {name: 0 for name in OUTCOMES} | {"total": 0}
        )
        bucket[outcome] += row["count"]
        bucket["total"] += row["count"]

    # Clipped to the range, not rounded out to whole months -- see the same note
    # in get_consultation_stats(). The stacked bars therefore sum to the totals
    # the cards beside them print.
    trend = []
    for month_start, _, label in window["months"]:
        bucket = scoped_by_month.get(
            month_start.strftime("%Y-%m"), {name: 0 for name in OUTCOMES} | {"total": 0}
        )
        trend.append({
            "month": month_start.strftime("%Y-%m"),
            "label": label,
            "expected": bucket[OUTCOME_EXPECTED],
            "attended": bucket[OUTCOME_ATTENDED],
            "missed": bucket[OUTCOME_MISSED],
            "total": bucket["total"],
        })

    ytd_summary = _outcome_summary(ytd, ytd_walk_ins, ytd_total, services)
    return {
        "year": year,
        "ytd_total": ytd_total,
        "ytd_expected": ytd[OUTCOME_EXPECTED],
        "ytd_attended": ytd[OUTCOME_ATTENDED],
        "ytd_missed": ytd[OUTCOME_MISSED],
        "ytd_walk_ins": ytd_walk_ins,
        "ytd_booked": ytd_total - ytd_walk_ins,
        "resolved": ytd_summary["resolved"],
        "attendance_pct": ytd_summary["attendance_pct"],
        "missed_pct": ytd_summary["missed_pct"],
        "trend": trend,
        # Most-requested first. Ties break alphabetically so the chart does not
        # reshuffle between page loads on equal counts.
        "services": ytd_summary["services"],
        # The same outcomes over the requested range. Every key above keeps its
        # year-to-date meaning untouched, so the four screens already reading
        # them are unaffected; only the two report screens read this block.
        "window": {
            "start": window["start"],
            "end": window["end"],
            "custom": window["custom"],
            **_outcome_summary(
                scoped_counts, scoped_walk_ins, scoped_total, scoped_services
            ),
        },
    }


def parse_month(value, fallback=None):
    """'2026-09' -> date(2026, 9, 1). Anything unusable -> the current month."""
    fallback = (fallback or today()).replace(day=1)
    text = (value or "").strip()
    if not text:
        return fallback
    try:
        return datetime.strptime(text[:7], "%Y-%m").date().replace(day=1)
    except ValueError:
        return fallback


def shift_month(first_of_month, months):
    """The first of the month `months` away. Negative goes back."""
    index = first_of_month.month - 1 + months
    year = first_of_month.year + index // 12
    return date(year, index % 12 + 1, 1)


def get_calendar_month(month_start=None, on_date=None):
    """The month grid the calendar panel renders, with real counts per day.

    Weeks start on Sunday to match the column headings the screen already has.
    Leading and trailing cells belong to the neighbouring months and are marked
    `muted`; they still carry their counts, because a booking on the 1st of next
    month is no less real for being shown in the last row of this one.
    """
    reference = on_date or today()
    month_start = (month_start or reference).replace(day=1)
    weeks = _calendar.Calendar(firstweekday=6).monthdatescalendar(
        month_start.year, month_start.month
    )
    summary = get_appointment_day_summary(weeks[0][0], weeks[-1][-1])

    grid = []
    for week in weeks:
        cells = []
        for day in week:
            counts = summary.get(day.isoformat())
            cells.append({
                "date": day,
                "day": day.day,
                "iso": day.isoformat(),
                "in_month": day.month == month_start.month,
                "is_today": day == reference,
                "is_past": day < reference,
                "counts": counts,
                "total": counts["total"] if counts else 0,
                "pending": counts["pending"] if counts else 0,
                "in_queue": counts["in_queue"] if counts else 0,
                "completed": counts["completed"] if counts else 0,
                "cancelled": counts["cancelled"] if counts else 0,
            })
        grid.append(cells)

    return {
        "month_start": month_start,
        "label": month_start.strftime("%B %Y"),
        "weeks": grid,
        "previous": shift_month(month_start, -1).strftime("%Y-%m"),
        "next": shift_month(month_start, 1).strftime("%Y-%m"),
        "current": reference.replace(day=1).strftime("%Y-%m"),
        "is_current_month": month_start == reference.replace(day=1),
        "month_total": sum(
            cell["total"] for week in grid for cell in week if cell["in_month"]
        ),
        "month_pending": sum(
            cell["pending"] for week in grid for cell in week if cell["in_month"]
        ),
    }


def set_appointment_status(appointment_id, status):
    """Move one appointment to a status. Returns rows actually changed.

    NOT THE WAY TO CANCEL OR CLOSE A BOOKING -- use close_appointment().
    ---------------------------------------------------------------------
    This was written as the unguarded primitive for Cancelled and No-show, back
    when nothing performed those two transitions. Something does now, and it does
    not go through here: close_appointment() re-checks the status inside its own
    UPDATE, so a page that went stale while the patient walked in and was checked
    in cannot reach past the check-in and cancel a visit already under way. This
    function has no such guard and would write straight over it.

    It is kept because it is still the honest general primitive -- a caller with
    a genuinely new transition and its own guard can build on it -- but it has no
    callers today, and a new one should be sure it does not want one of the four
    guarded transitions instead: start_consultation(), complete_consultation(),
    close_appointment(), reschedule_appointment().

    Entering and leaving the consultation room in particular must go through
    start_consultation() and complete_consultation(): those hold the
    one-patient-at-a-time invariant in the WHERE clause, and this would let a
    caller write 'In Consultation' straight past it.

    `AND status != ?` keeps the count honest, the same way set_patient_status()
    does: SQLite reports rows matched, not rows changed, so without it a repeated
    click would claim an update that did not happen and bump updated_at for a
    write that changed nothing.
    """
    if status not in APPOINTMENT_STATUSES:
        raise ValueError(
            f"{status!r} is not an appointment status; expected one of "
            f"{APPOINTMENT_STATUSES}."
        )

    conn = get_db()
    cursor = conn.execute(
        """
        UPDATE appointments
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status != ?
        """,
        (status, appointment_id, status),
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected
