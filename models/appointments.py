"""Appointment queries, including the live consultation queue on Screen 08.

Every visit is a walk-in: an appointment row created at the moment the patient
arrives at the desk. This system booked visits ahead until 2026-09-05 and the
older rows in the table still carry the date and the time they were booked for,
so both shapes read out of one table and one query rather than a union of two
sources that could disagree about who is next. See utils/unavailable.py
`advance_booking` for why the booking half went.
"""
import calendar as _calendar
from datetime import date, datetime

from database.connection import db_connection
from models.doctor_worklist import (
    VISIT_SERVICES, WAITING_FOR_DOCTOR, clean_service, has_diagnosis, needs_doctor,
    waiting_text,
)
from models.queue_actions import (
    CHANGE_SERVICE, MARK_COMPLETED, MARK_LEFT, REFER, REFERRED, SEND_TO_DOCTOR, START,
    UNDO_LEFT, UNDO_REFERRAL, allowed_actions, is_today, statuses_allowing,
)
from models.referrals import REFERRABLE_STATUSES, count_by_destination, referral_allowed
from utils.dates import format_time, now, recent_months, resolve_range, today
from utils.roles import is_care_team
from utils.small_counts import fold_small_counts, shown_count

# Statuses that still represent a commitment the patient is expected to keep.
PENDING_STATUSES = ("Scheduled", "Confirmed")

# The full vocabulary the appointments.status CHECK admits, in queue order.
APPOINTMENT_STATUSES = (
    "Scheduled", "Confirmed", "Waiting", "In Consultation",
    "Waiting for the Doctor", "Completed", "Cancelled", "No-show", "Left before being seen",
    "Referred",
)

# The patient has arrived and has not yet been dealt with. These two are what the
# queue is made of.
WAITING = "Waiting"
IN_CONSULTATION = "In Consultation"
COMPLETED = "Completed"

# The intake is saved and the visit needs a diagnosis the Doctor has not written yet
# (Task 6b, D3). Defined in models/doctor_worklist.py, which decides who is on his list.
# "Completed" now means finished: nothing is left for anyone to do on the visit.
WAITING_DOCTOR = WAITING_FOR_DOCTOR

# The patient checked in and went home before the Doctor saw them (Task 6, M5). Set
# by Staff or the Doctor from the queue, undone the same day. It is not "No-show"
# (never came) and not "Cancelled" (a booking withdrawn): they were here.
LEFT = "Left before being seen"
# The statuses a visit can be marked as left from, and the statuses its service can still
# be corrected in (Task 6b, D2). Both are read off the one status x role mapping in
# models/queue_actions.py (Task 6d), so the SQL rules and the buttons cannot disagree.
LEAVABLE_STATUSES = statuses_allowing(MARK_LEFT)
CORRECTABLE_STATUSES = statuses_allowing(CHANGE_SERVICE)
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
READY_LABEL = "Next in line"
READY_BADGE_CLASS = "badge-ready"

# Checking in is only meaningful for a visit that has not already been resolved.
# Re-checking in someone already Waiting or In Consultation is a no-op, not a
# second visit, and a Completed/Cancelled/No-show row is closed -- a patient who
# genuinely returns the same day gets a fresh walk-in record instead.
CHECK_IN_FROM_STATUSES = PENDING_STATUSES

# What every visit was called before the service was chosen at check-in (Task 6b).
# Old rows still carry it. A new visit always carries one of VISIT_SERVICES.
WALK_IN_TYPE = "Walk-in Consultation"

# The granularity a clinic day is measured in. It was the size of a bookable
# slot; advance booking is gone and nothing generates slots any more, but the
# constant is NOT dead -- models/settings.py imports it to refuse a clinic day
# shorter than one of these, which is what stops Screen 13 storing a facility
# open for twenty minutes. It stays here, where the clinic day is described,
# rather than moving to the one module that now reads it.
SLOT_MINUTES = 30


# appointments.status -> the badge class the screens' stylesheets define.
STATUS_BADGE_CLASS = {
    "Scheduled": "badge-scheduled",
    "Confirmed": "badge-scheduled",
    "Waiting": "badge-waiting",
    "In Consultation": "badge-inconsult",
    "Waiting for the Doctor": "badge-waiting-doctor",
    "Completed": "badge-completed",
    "Cancelled": "badge-cancelled",
    "No-show": "badge-noshow",
    "Left before being seen": "badge-noshow",
    "Referred": "badge-referred",
}

# The colour of each status's dot in the calendar and its legend (Task 6d), matching the
# badge the queue row shows for it.
STATUS_DOT_CLASS = {
    "Waiting": "dot-waiting",
    "In Consultation": "dot-inconsult",
    "Waiting for the Doctor": "dot-waiting-doctor",
    "Completed": "dot-completed",
    "Left before being seen": "dot-left",
    "Referred": "dot-referred",
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
    "Waiting for the Doctor": 3,
    "Completed": 4,
    "Cancelled": 5,
    "No-show": 5,
    "Left before being seen": 5,
    "Referred": 5,
}


def _to_appointment(row):
    appointment = dict(row)
    appointment["status_badge_class"] = STATUS_BADGE_CLASS.get(
        appointment.get("status"), "badge-scheduled"
    )
    return appointment


def _to_queue_entry(row):
    """A queue row plus the derived display fields Screen 08 renders."""
    entry = _to_appointment(row)
    entry["is_waiting"] = entry["status"] == WAITING
    entry["is_in_consultation"] = entry["status"] == IN_CONSULTATION
    entry["in_queue"] = entry["status"] in QUEUE_STATUSES
    # A visit of a service that needs the Doctor is sent to him, not closed (Task 6c).
    entry["needs_doctor"] = needs_doctor(entry.get("appointment_type"))
    entry["walk_in"] = bool(entry.get("is_walkin"))
    # The reference the table's first column shows. appointments has no external
    # identifier column of its own, so it is composed from the row id -- stable,
    # unique, and it cannot drift from the record it names.
    entry["reference"] = f"APT-{entry['id']:05d}"
    entry["arrival_time"] = _clock(entry.get("checked_in_at"))
    entry["booked_time"] = _clock(entry.get("appointment_time"))
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
    """A stored timestamp or time rendered as '2:21 PM', or None.

    Accepts both what checked_in_at holds ('YYYY-MM-DD HH:MM:SS', clinic-local)
    and what appointment_time holds ('HH:MM'), because the queue shows the two
    side by side and neither should need its own formatting rule at the call
    site. The 12-hour rule itself is utils.dates.format_time(). The queue is
    ordered by the stored values, never by this text.
    """
    return format_time(value) or None


def get_appointments_for_patient(patient_id, viewer_role):
    """Appointment History tab on Screen 04, most recent first.

    `viewer_role` has no default: the check-in reason (`notes`) of a sealed visit
    is encrypted, and what a reader gets depends on who they are. See
    attach_visit_reasons().
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT a.id, a.appointment_date, a.appointment_time, a.appointment_type,
               a.status, u.full_name AS assigned_staff
        FROM appointments a
        LEFT JOIN users u ON u.id = a.assigned_staff_id
        WHERE a.patient_id = ?
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
        """,
            (patient_id,),
        ).fetchall()
    return attach_visit_reasons([_to_appointment(row) for row in rows], viewer_role)


_QUEUE_SELECT = """
    SELECT a.id, a.patient_id, a.appointment_type, a.appointment_date,
           a.appointment_time, a.status, a.is_walkin, a.checked_in_at,
           a.created_at, a.left_at, a.status_before_left,
           a.referred_at, a.status_before_referred,
           p.patient_id AS patient_reference,
           p.first_name, p.middle_name, p.last_name, p.sex, p.birth_date,
           u.full_name AS assigned_staff,
           b.full_name AS booked_by
    FROM appointments a
    JOIN patients p ON p.id = a.patient_id
    LEFT JOIN users u ON u.id = a.assigned_staff_id
    LEFT JOIN users b ON b.id = a.scheduled_by
"""


# WHO READS THE CHECK-IN REASON (Task 5b, D1, D4).
# The reason given at the desk ("for HIV testing") can itself disclose that a
# person has been tested, which RA 11166 Section 44 forbids without consent. So
# the queries above do NOT select it, and a row never carries it unless it went
# through attach_visit_reasons(), which decides per reader:
#
#   Patient Queue (queue_view=True)
#       Doctor and Health Center Staff see it. Everyone else sees no reason at
#       all, for any visit: the Administrator needs to see who is waiting, not why.
#   Appointment History on a profile
#       The reason is shown as it was recorded, except on a visit the Doctor has
#       sealed. That reason is encrypted, so only the Doctor reads it; everyone
#       else sees the placeholder.
#
# The decryption goes through models.consultations.open_sealed_value(), the one
# function that may decrypt, and it is refused to every role but the Doctor.
def attach_visit_reasons(entries, viewer_role, queue_view=False):
    """Add `notes` (the check-in reason) and `reason_hidden` to appointment rows.

    Mutates and returns the list it is given. A row whose reason this reader may
    not see gets `notes` None. `reason_hidden` is True when the reader may not see
    reasons on this screen at all, so a template can leave the column out.
    `reason_sealed` is True when the visit is sealed, so a page can keep the
    reason off a printout even for the Doctor, who reads it on screen.
    """
    from models.consultations import (
        RESTRICTED_PLACEHOLDER, can_view_restricted,
        open_sealed_value,
    )
    from utils import sealed_crypto

    entries = list(entries)
    if queue_view and not is_care_team(viewer_role):
        for entry in entries:
            entry["notes"] = None
            entry["reason_hidden"] = True
        return entries

    ids = [entry["id"] for entry in entries]
    stored = {}
    if ids:
        placeholders = ", ".join("?" for _ in ids)
        with db_connection() as conn:
            stored = {
                row["id"]: row
                for row in conn.execute(
                    f"""
                SELECT a.id, a.notes,
                       EXISTS (SELECT 1 FROM consultations c
                                WHERE c.appointment_id = a.id
                                  AND c.is_restricted = 1) AS is_sealed
                  FROM appointments a WHERE a.id IN ({placeholders})
                """,
                    ids,
                ).fetchall()
            }

    for entry in entries:
        entry["reason_hidden"] = False
        entry["reason_sealed"] = False
        row = stored.get(entry["id"])
        text = row["notes"] if row else None
        if text and (row["is_sealed"] or sealed_crypto.is_encrypted(text)):
            entry["reason_sealed"] = True
            if can_view_restricted(viewer_role):
                text, _ = open_sealed_value(text, entry["id"], "notes",
                                            viewer_role, "appointments")
            else:
                text = RESTRICTED_PLACEHOLDER
        entry["notes"] = text or None
    return entries


def _apply_queue_flow(entries, active=None):
    """Add the single-active-consultation fields to an ordered queue.

    The clinic sees one patient at a time, so the whole of that rule is decided
    here, once -- and every screen, message and stat card reads the answer off
    these fields rather than working it out again:

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

    WHY "WHO HOLDS THE ROOM" IS ASKED OF THE DATABASE, NOT OF `entries`
    ------------------------------------------------------------------
    This used to read the active consultation out of the day's own rows:

        active = next(e for e in entries if e["is_in_consultation"])

    which is the same question start_consultation() asks, but asked of a
    strictly smaller set. The UPDATE's guard there is
    `NOT EXISTS (... status = 'In Consultation')` over the whole table, with no
    date filter, deliberately -- see get_active_consultation(). So the two
    disagreed for exactly one case, and it was not a hypothetical one: a visit
    started and never written up stops being in *today's* rows at midnight while
    still occupying the clinician. On 2026-08-29 the queue showed the room free
    and offered Start Consultation for a waiting patient, and the server refused
    the click, because a consultation opened at 23:36 the previous night was
    still open. The screen was reading one fact and the server another.

    Asking get_active_consultation() closes that by construction: the button is
    offered on the same fact the UPDATE tests, so the screen cannot advertise an
    action the server will reject. `active` may be passed in when the caller has
    already looked it up, so one render resolves the room exactly once and the
    queue and its stat cards cannot disagree with each other either.
    """
    entries = list(entries)
    if active is None:
        active = get_active_consultation()
    # Prefer this day's own row for the holder when there is one, so the object
    # the flow fields were computed against is the same object the table renders.
    active = next(
        (entry for entry in entries if entry["is_in_consultation"]), active
    )
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
        # "Next in line" replaces the stored "Waiting" only for display. The
        # row is still Waiting in the database -- see READY_LABEL.
        entry["display_status"] = READY_LABEL if entry["is_ready"] else entry["status"]
        entry["display_badge_class"] = (
            READY_BADGE_CLASS if entry["is_ready"] else entry["status_badge_class"]
        )

    return entries


def get_todays_appointments(on_date=None, active=None):
    """Every appointment for the clinic-local day, in queue order.

    Ordering is done in Python rather than SQL because the status ranking is a
    presentation rule, not a property of the data -- putting it in a CASE inside
    the query would hide it from anything else that needs the same order.

    `active` is passed straight to _apply_queue_flow(): a caller that also wants
    get_queue_stats() should look the room up once and hand it to both, so the
    table and the cards above it are answering from one reading.
    """
    day = (on_date or today()).isoformat()
    with db_connection() as conn:
        rows = conn.execute(
            _QUEUE_SELECT + " WHERE date(a.appointment_date) = ?",
            (day,),
        ).fetchall()

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
    return _apply_queue_flow(entries, active=active)


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


def get_queue_stats(entries=None, active=None):
    """The figures Screen 08's stat cards and footer show for today.

    Accepts an already-fetched list, and the already-resolved room, so one render
    queries each once. Pass the same `active` given to get_todays_appointments()
    and the cards cannot disagree with the table under them.

    TWO DIFFERENT QUESTIONS, KEPT APART
    -----------------------------------
    "How many of today's rows are In Consultation" and "is the clinician free"
    read like the same question and were answered by one figure until the
    2026-08-29 stuck-consultation bug showed they are not. A visit started
    yesterday and never written up is not in today's rows and still holds the
    room. So:

        in_consultation_today   today's rows only. Disjoint from ready and
                                still_waiting, which is what lets the table
                                footer print the three side by side and have
                                them add up to the people in the building.
        in_consultation         the room itself, whole-database, 0 or 1. This is
                                what the stat card shows, because a card headed
                                "In Consultation" reading 0 while the server
                                refuses every Start Consultation is the lie this
                                pair of keys exists to stop telling.

    active_is_stale marks the case that pulled them apart: the room is held by a
    visit from a day other than the one on screen. The queue screen renders that
    as a banner naming the patient and offering the two ways to resolve it,
    rather than leaving it to be inferred from a card.
    """
    if entries is None:
        entries = get_todays_appointments(active=active)
    if active is None:
        active = get_active_consultation()
    # The same preference _apply_queue_flow() makes: this day's own row for the
    # holder when there is one, so the stats and the table share an object.
    active = next(
        (entry for entry in entries if entry["is_in_consultation"]), active
    )

    waiting = [entry for entry in entries if entry["is_waiting"]]
    ready = [entry for entry in waiting if entry["is_ready"]]
    next_up = next((entry for entry in waiting if entry["is_next_up"]), None)

    reference = today()
    active_date = _as_date(active["appointment_date"]) if active else None
    stale = bool(active_date and active_date != reference)

    return {
        "total_today": len(entries),
        "walk_ins": sum(1 for entry in entries if entry["walk_in"]),
        # Everyone checked in and not yet with the clinician -- the waiting room.
        "waiting": len(waiting),
        # At most 1: the patient who may be brought in now.
        "ready": len(ready),
        # The waiting room minus that one, so the two never double-count.
        "still_waiting": len(waiting) - len(ready),
        # The room, whole-database. At most 1, enforced by start_consultation().
        "in_consultation": 1 if active else 0,
        # Today's rows only -- the footer's tally. Equal to the above except
        # while the room is held by another day's visit.
        "in_consultation_today": sum(
            1 for entry in entries if entry["is_in_consultation"]
        ),
        # Only finished visits. A visit whose intake is saved and that still needs the
        # Doctor is counted under waiting_doctor, not here (Task 6b, D6).
        "completed": sum(1 for entry in entries if entry["status"] == COMPLETED),
        "waiting_doctor": sum(1 for entry in entries if entry["status"] == WAITING_DOCTOR),
        "left": sum(1 for entry in entries if entry["status"] == LEFT),
        "referred": sum(1 for entry in entries if entry["status"] == REFERRED),
        "not_arrived": sum(
            1 for entry in entries if entry["status"] in PENDING_STATUSES
        ),
        "room_free": active is None,
        "active_name": queue_display_name(active),
        "next_up_name": queue_display_name(next_up),
        # The stuck-consultation case, for the banner on Screen 08.
        "active": active,
        "active_is_stale": stale,
        "active_date": active_date,
        "active_days_open": (reference - active_date).days if stale else 0,
    }


def _as_date(value):
    """'YYYY-MM-DD' (or a date) as a date, or None if it is neither.

    Tolerant on purpose: appointment_date is TEXT, so a row written by hand or by
    an older migration could hold something this cannot parse, and a stat card
    must not be the thing that raises on it.
    """
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def get_appointment_by_id(appointment_id):
    """One appointment with its patient, or None.

    Carries the display fields but not the flow fields -- those only exist
    relative to a whole day's queue. Use get_queue_entry() when the answer
    depends on who else is in the room.
    """
    with db_connection() as conn:
        row = conn.execute(_QUEUE_SELECT + " WHERE a.id = ?", (appointment_id,)).fetchone()
    return _to_queue_entry(row) if row else None


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
    with db_connection() as conn:
        row = conn.execute(
            _QUEUE_SELECT
            + " WHERE a.status = ? ORDER BY a.checked_in_at DESC, a.id DESC LIMIT 1",
            (IN_CONSULTATION,),
        ).fetchone()
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
    with db_connection() as conn:
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
    return dict(row) if row else None


def find_active_queue_entry(patient_id, on_date=None):
    """This patient's row for today that is already in the queue, or None."""
    day = (on_date or today()).isoformat()
    placeholders = ", ".join("?" for _ in QUEUE_STATUSES)
    with db_connection() as conn:
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
    return dict(row) if row else None


def check_in_patient(patient_id, reason, user_id, on_date=None, audit=None, *, service):
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
    patient can go straight in. "Next in line" is not stored -- the queue
    derives it in _apply_queue_flow(), so a patient who arrives to an empty room
    is shown as ready without ever being written as Waiting-and-then-something-
    else, and cannot be left stranded on a stale ready flag if someone else is
    brought in first. See READY_LABEL.

    `service` is the service Staff chose from VISIT_SERVICES (Task 6b, D1). It is a
    required choice with no default: anything not in the list is refused here, so a
    forged POST cannot store a made-up service. It is stored as appointment_type.

    `audit(conn, appointment_id, outcome)` is called before the commit when a
    row was created or updated. "already" writes nothing, so no entry.
    """
    chosen = clean_service(service)
    if chosen is None:
        raise ValueError("A service from VISIT_SERVICES is required to check a patient in.")
    day = (on_date or today()).isoformat()
    stamp = now().strftime("%Y-%m-%d %H:%M:%S")
    reason = (reason or "").strip() or None

    existing = find_active_queue_entry(patient_id, on_date=on_date)
    if existing:
        return existing["id"], "already"

    booked = find_todays_appointment(patient_id, on_date=on_date)
    with db_connection() as conn:
        if booked:
            conn.execute(
                """
            UPDATE appointments
               SET status = ?,
                   appointment_type = ?,
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
                (WAITING, chosen, stamp, reason, reason, reason, booked["id"]),
            )
            appointment_id = booked["id"]
            outcome = "updated"
            if audit:
                audit(conn, appointment_id, outcome)
            conn.commit()
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
                    chosen,
                    day,
                    # A walk-in has no booked slot; the arrival time is the only time
                    # that means anything, and it is kept in checked_in_at.
                    None,
                    WAITING,
                    reason,
                    stamp,
                ),
            )
            appointment_id = cursor.lastrowid
            outcome = "created"
            if audit:
                audit(conn, appointment_id, outcome)
            conn.commit()

    return appointment_id, outcome


def start_consultation(appointment_id, audit=None):
    """Bring one Waiting patient in. Returns the outcome:

        "started"      they are now In Consultation
        "busy"         someone else is In Consultation; nothing changed
        "already"      this row is already In Consultation
        "not-waiting"  the row is Scheduled/Completed/... , so it cannot start
        "earlier-day"  the visit was checked in on an earlier day (Task 11, L49)
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

    `audit(conn)` is called before the commit, only when the patient started.
    """
    with db_connection() as conn:
        cursor = conn.execute(
            """
        UPDATE appointments
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
           AND status = ?
           AND date(appointment_date) = ?
           AND NOT EXISTS (
                 SELECT 1 FROM appointments busy WHERE busy.status = ?
               )
        """,
            (IN_CONSULTATION, appointment_id, WAITING, today().isoformat(), IN_CONSULTATION),
        )
        # The audit entry commits with the move, and only when the move happened.
        if cursor.rowcount == 1 and audit:
            audit(conn)
        conn.commit()

        if cursor.rowcount == 1:
            return "started"

        # Nothing was written, so say which of the WHERE's conditions refused.
        row = conn.execute(
            "SELECT status, appointment_date FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()

    if row is None:
        return "missing"
    if row["status"] == IN_CONSULTATION:
        return "already"
    if row["status"] == WAITING and not is_today(row["appointment_date"], today()):
        return "earlier-day"
    if row["status"] != WAITING:
        return "not-waiting"
    # Still Waiting and still not started: the only remaining refusal is the
    # NOT EXISTS, i.e. the clinician is with someone else.
    return "busy"


def _completion_blocked(conn, appointment_id):
    """True when the visit needs the Doctor and has no diagnosis (Task 6c, D1).

    THE ONE PLACE that decides it for the routes that close a visit. A visit of a
    service in SERVICES_NEEDING_DOCTOR with no diagnosis is never Completed:
    complete_consultation() (the queue's Mark Completed) refuses it and
    send_to_doctor() sends it on. The other ways to Completed cannot reach it:
    finish_intake() gives Waiting for the Doctor for exactly this case,
    complete_after_diagnosis() requires a diagnosis in its SQL, change_visit_service()
    sets Completed only for a service that does not need him, and undo_left() restores
    a stored status that is only Waiting, In Consultation or Waiting for the Doctor.
    """
    row = conn.execute(
        "SELECT a.appointment_type, "
        "EXISTS (SELECT 1 FROM consultations c WHERE c.appointment_id = a.id "
        "AND TRIM(COALESCE(c.diagnosis, '')) != '') AS diagnosed "
        "FROM appointments a WHERE a.id = ?", (appointment_id,)).fetchone()
    return bool(row) and needs_doctor(row["appointment_type"]) and not row["diagnosed"]


def send_to_doctor(appointment_id, audit=None):
    """Send the visit in progress to the Doctor. Returns the outcome:

        "sent"                the visit is now Waiting for the Doctor
        "already"             it was already Waiting for the Doctor
        "not-needed"          its service does not need the Doctor, or it has a diagnosis
        "not-in-consultation" it is not the visit currently in progress
        "missing"             no such appointment

    `audit(conn)` is called before the commit, only when the visit moved.
    """
    with db_connection() as conn:
        row = conn.execute("SELECT status FROM appointments WHERE id = ?",
                           (appointment_id,)).fetchone()
        if row is None:
            return "missing"
        if row["status"] == WAITING_DOCTOR:
            return "already"
        if row["status"] != IN_CONSULTATION:
            return "not-in-consultation"
        if not _completion_blocked(conn, appointment_id):
            return "not-needed"
        cursor = conn.execute(
            "UPDATE appointments SET status = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = ?", (WAITING_DOCTOR, appointment_id, IN_CONSULTATION))
        if cursor.rowcount != 1:
            conn.rollback()
            return "not-in-consultation"
        if audit:
            audit(conn)
        conn.commit()
    return "sent"


def complete_consultation(appointment_id, audit=None):
    """Close the consultation in progress. Returns the outcome:

        "completed"           the visit is now Completed
        "already"             it was already Completed
        "needs-doctor"        its service needs the Doctor and it has no diagnosis: refused
        "not-in-consultation" it is not the visit currently in progress
        "missing"             no such appointment

    This is the transition that releases the room: the next Waiting patient
    becomes startable the moment it lands, which the queue picks up on its next
    render through _apply_queue_flow(). Recording *what happened* in the
    consultation is a separate concern and is not touched here.

    Guarded in the WHERE for the same reason as start_consultation(): only the
    visit actually in progress may be completed, so a stale page cannot close a
    patient who never went in.

    `audit(conn)` is called before the commit, only when the visit completed.
    """
    with db_connection() as conn:
        current = conn.execute("SELECT status FROM appointments WHERE id = ?",
                               (appointment_id,)).fetchone()
        if current and current["status"] == IN_CONSULTATION and _completion_blocked(
                conn, appointment_id):
            return "needs-doctor"
        cursor = conn.execute(
            """
        UPDATE appointments
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status = ?
        """,
            (COMPLETED, appointment_id, IN_CONSULTATION),
        )
        # The audit entry commits with the move, and only when the move happened.
        if cursor.rowcount == 1 and audit:
            audit(conn)
        conn.commit()

        if cursor.rowcount == 1:
            return "completed"

        row = conn.execute(
            "SELECT status FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()

    if row is None:
        return "missing"
    if row["status"] == COMPLETED:
        return "already"
    return "not-in-consultation"


def finish_intake(appointment_id, diagnosis_written, audit=None):
    """Close the intake of the visit in progress. Returns the outcome:

        "completed"           the visit is Completed: nothing is left for the Doctor
        "waiting-for-doctor"  the intake is saved and the Doctor still has to diagnose
        "already"             the visit had already moved on
        "not-in-consultation" it is not the visit currently in progress
        "missing"             no such appointment

    THE RULE (Task 6b, D3). Saving the intake makes the visit "Waiting for the Doctor"
    when its service is in SERVICES_NEEDING_DOCTOR and no diagnosis was written.
    Otherwise it is Completed: an immunization or a prenatal check-up is finished by
    Staff, and a visit the Doctor recorded himself, with a diagnosis, is finished.

    Guarded in the WHERE like complete_consultation(): only the visit in progress may
    move, so a stale page cannot close a patient who never went in. Either way the
    room is freed, because neither status is In Consultation.

    `audit(conn, new_status)` is called before the commit, only when the visit moved.
    """
    with db_connection() as conn:
        row = conn.execute(
            "SELECT status, appointment_type FROM appointments WHERE id = ?",
            (appointment_id,),
        ).fetchone()
        if row is None:
            return "missing"
        if row["status"] != IN_CONSULTATION:
            return "already" if row["status"] in (COMPLETED, WAITING_DOCTOR) else "not-in-consultation"
        new_status = (
            WAITING_DOCTOR
            if needs_doctor(row["appointment_type"]) and not diagnosis_written
            else COMPLETED
        )
        cursor = conn.execute(
            "UPDATE appointments SET status = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = ?",
            (new_status, appointment_id, IN_CONSULTATION),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return "not-in-consultation"
        if audit:
            audit(conn, new_status)
        conn.commit()
    return "completed" if new_status == COMPLETED else "waiting-for-doctor"


def complete_after_diagnosis(appointment_id, audit=None):
    """The Doctor saved a diagnosis: a visit Waiting for the Doctor becomes Completed.

    Returns True when it moved. Any other visit is left as it is: the Doctor may write
    a diagnosis on any visit, and a visit that is already Completed stays Completed.
    `audit(conn)` is called before the commit, only when it moved.
    """
    if appointment_id is None:
        return False
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE appointments SET status = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = ? AND EXISTS (SELECT 1 FROM consultations c "
            "WHERE c.appointment_id = appointments.id AND TRIM(COALESCE(c.diagnosis, '')) != '')",
            (COMPLETED, appointment_id, WAITING_DOCTOR),
        )
        if cursor.rowcount == 1 and audit:
            audit(conn)
        conn.commit()
        return cursor.rowcount == 1


def change_visit_service(appointment_id, service, audit=None):
    """Correct the service of a visit that is not finished (Task 6b, D2).

    Returns the outcome:

        "changed"            the service was changed
        "changed-in-consultation"  changed, and the visit was Waiting for the Doctor but
                             the new service does not need him, so it is now In
                             Consultation: a correction never completes a visit, the
                             service is recorded first
        "busy"               that move needs the room and someone else is in it; nothing
                             changed
        "same"               it already has that service
        "invalid"            not a service in VISIT_SERVICES
        "not-allowed"        the visit is Completed, Left before being seen, or not in
                             the queue
        "missing"            no such appointment

    Enforced here, in SQL, not by the buttons: a stale page or a forged POST gets the
    same answer. `audit(conn, old, new, moved)` runs before the commit, only
    when the service changed.
    """
    chosen = clean_service(service)
    if chosen is None:
        return "invalid"
    with db_connection() as conn:
        row = conn.execute(
            "SELECT status, appointment_type, appointment_date FROM appointments WHERE id = ?",
            (appointment_id,),
        ).fetchone()
        if row is None:
            return "missing"
        if row["status"] not in CORRECTABLE_STATUSES:
            return "not-allowed"
        # An earlier day's Waiting visit offers only Left before being seen (Task 13, D6).
        if row["status"] == WAITING and not is_today(row["appointment_date"], today()):
            return "not-allowed"
        old = (row["appointment_type"] or "").strip() or WALK_IN_TYPE
        if old == chosen:
            return "same"
        # A correction never completes a visit (Task 6e). Waiting for the Doctor with a
        # service that no longer needs him goes back to In Consultation, so the service
        # is actually recorded first; the room rule of start_consultation() applies.
        moved = row["status"] == WAITING_DOCTOR and not needs_doctor(chosen)
        cursor = conn.execute(
            "UPDATE appointments SET appointment_type = ?, "
            "status = CASE WHEN ? THEN ? ELSE status END, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = ? AND (? = 0 OR NOT EXISTS "
            "(SELECT 1 FROM appointments busy WHERE busy.status = ?))",
            (chosen, 1 if moved else 0, IN_CONSULTATION, appointment_id, row["status"],
             1 if moved else 0, IN_CONSULTATION),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return "busy" if moved else "not-allowed"
        if audit:
            audit(conn, old, chosen, moved)
        conn.commit()
    return "changed-in-consultation" if moved else "changed"


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


# ---------------------------------------------------------------------------
# LEFT BEFORE BEING SEEN (Task 6, M5)
# ---------------------------------------------------------------------------
# A patient who checks in and goes home before the Doctor sees them could not be
# closed: the visit stayed Waiting for ever and the queue figures were wrong. Staff
# and the Doctor can now mark it, and undo it the same day. Nothing closes a visit
# automatically.
#
# WHEN IT CAN BE SET. The visit is Waiting, In Consultation, or Waiting for the Doctor
# (the intake is saved and the Doctor has not diagnosed), and it has no diagnosis. A
# Completed visit is finished and cannot be marked.
#
# WHEN IT CAN BE UNDONE. The same day it was marked, back to the status it had.
# Putting a visit back In Consultation is refused while someone else holds the room.
#
# THE RULES ARE ENFORCED HERE, IN SQL, not by the buttons: a stale page or a forged
# POST gets the same answer. The Administrator has no route to either function.

def leave_allowed(status, diagnosis=None):
    """Whether a visit in this state may be marked as left before being seen.

    Waiting, In Consultation and Waiting for the Doctor, and never one that has a
    diagnosis. A Completed visit is finished and cannot be marked.
    """
    return status in LEAVABLE_STATUSES and not has_diagnosis(diagnosis)


def _leave_row(conn, appointment_id):
    return conn.execute(
        """
    SELECT a.id, a.status, a.appointment_type, a.appointment_date, a.left_at,
           a.status_before_left, c.id AS consultation_id, c.diagnosis
      FROM appointments a
      LEFT JOIN consultations c ON c.appointment_id = a.id
     WHERE a.id = ?
    """,
        (appointment_id,),
    ).fetchone()


def mark_left(appointment_id, user_id, audit=None):
    """Mark one visit as left before being seen. Returns the outcome:

        "marked"       done; who and when are stored
        "already"      it is already marked
        "not-allowed"  it has a diagnosis, or is finished, or is not in the queue
        "missing"      no such appointment

    `audit(conn)` is called before the commit, only when the visit was marked.
    """
    stamp = now().strftime("%Y-%m-%d %H:%M:%S")
    with db_connection() as conn:
        row = _leave_row(conn, appointment_id)
        if row is None:
            return "missing"
        if row["status"] == LEFT:
            return "already"
        if not leave_allowed(row["status"], row["diagnosis"]):
            return "not-allowed"
        # The guard is repeated in the UPDATE, so a diagnosis written a moment ago, or a
        # status that moved, loses the race instead of being overwritten.
        cursor = conn.execute(
            """
        UPDATE appointments
           SET status_before_left = status, status = ?, left_by = ?, left_at = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status = ?
           AND NOT EXISTS (
                 SELECT 1 FROM consultations c
                  WHERE c.appointment_id = appointments.id
                    AND TRIM(COALESCE(c.diagnosis, '')) != ''
               )
        """,
            (LEFT, user_id, stamp, appointment_id, row["status"]),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return "not-allowed"
        if audit:
            audit(conn)
        conn.commit()
    return "marked"


def undo_left(appointment_id, audit=None):
    """Put a visit marked as left back to the status it had. Returns the outcome:

        "undone"     done
        "not-left"   it is not marked as left
        "too-late"   it was marked on an earlier day; it stays closed
        "busy"       it was In Consultation and someone else is in the room now
        "missing"    no such appointment

    `audit(conn)` is called before the commit, only when it was undone.
    """
    with db_connection() as conn:
        row = _leave_row(conn, appointment_id)
        if row is None:
            return "missing"
        if row["status"] != LEFT:
            return "not-left"
        if (row["left_at"] or "")[:10] != today().isoformat():
            return "too-late"
        before = row["status_before_left"]
        if before not in LEAVABLE_STATUSES:
            return "not-left"
        cursor = conn.execute(
            """
        UPDATE appointments
           SET status = status_before_left, status_before_left = NULL,
               left_by = NULL, left_at = NULL, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status = ?
           AND (status_before_left != ?
                OR NOT EXISTS (SELECT 1 FROM appointments busy WHERE busy.status = ?))
        """,
            (appointment_id, LEFT, IN_CONSULTATION, IN_CONSULTATION),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return "busy"
        if audit:
            audit(conn)
        conn.commit()
    return "undone"


def attach_leave_flags(entries):
    """Add `can_leave` and `can_undo_left` to queue rows, for the buttons.

    Mutates and returns the list. The buttons are offered where mark_left() and
    undo_left() would accept; those two decide, so a stale page changes nothing.
    """
    entries = list(entries)
    ids = [entry["id"] for entry in entries]
    found = {}
    if ids:
        marks = ", ".join("?" for _ in ids)
        with db_connection() as conn:
            found = {
                row["appointment_id"]: row
                for row in conn.execute(
                    f"SELECT appointment_id, id, diagnosis FROM consultations "
                    f"WHERE appointment_id IN ({marks})", ids)
            }
    day = today().isoformat()
    for entry in entries:
        consultation = found.get(entry["id"])
        entry["can_leave"] = leave_allowed(
            entry["status"], consultation["diagnosis"] if consultation else None,
        )
        entry["can_undo_left"] = (
            entry["status"] == LEFT and (entry.get("left_at") or "")[:10] == day
            and entry.get("status_before_left") in LEAVABLE_STATUSES
        )
        # The same two questions for a referral (Task 19): referral_allowed() and
        # undo_referral() decide, these only decide which buttons are drawn.
        entry["can_refer"] = referral_allowed(
            entry["status"], consultation["diagnosis"] if consultation else None)
        entry["can_undo_referral"] = (
            entry["status"] == REFERRED and (entry.get("referred_at") or "")[:10] == day
            and entry.get("status_before_referred") in REFERRABLE_STATUSES
        )
    return entries


def attach_actions(entries, role):
    """Add `actions` and `shown` to queue rows, for the buttons (Task 6d, D3).

    `actions` is the mapping's answer for this role and the row's status
    (models/queue_actions.py). `shown` is what the row offers: those actions, less the
    ones that make no sense for this one visit right now -- a service that needs the
    Doctor is sent to him and not completed, one that does not is completed and not
    sent, a visit with a diagnosis cannot be marked as left, and Undo is for the day it
    was set. Start is always shown when allowed; `can_start` says whether the room is
    free. The template draws exactly `shown`. Needs attach_leave_flags() first.
    """
    entries = list(entries)
    for entry in entries:
        actions = allowed_actions(role, entry["status"],
                                  is_today(entry.get("appointment_date"), today()))
        entry["actions"] = actions
        entry["shown"] = tuple(
            action for action in actions
            if not (
                (action == SEND_TO_DOCTOR and not entry["needs_doctor"])
                or (action == MARK_COMPLETED and entry["needs_doctor"])
                or (action == MARK_LEFT and not entry["can_leave"])
                or (action == UNDO_LEFT and not entry["can_undo_left"])
                or (action == REFER and not entry["can_refer"])
                or (action == UNDO_REFERRAL and not entry["can_undo_referral"])
            )
        )
    return entries


# The statuses of a visit that is still open: nobody has finished it. A visit from an
# earlier day in one of these is listed on the Patient Queue (Task 10), whatever its status.
OPEN_STATUSES = (WAITING, IN_CONSULTATION, WAITING_DOCTOR)


def get_open_earlier_visits(active=None):
    """Every visit from an earlier day that is still open, oldest first (Task 10, D1).

    Waiting, In Consultation or Waiting for the Doctor. Today's table shows only today, so
    these used to be invisible on the queue. Nothing closes them automatically. The queue
    lists them for Staff, the Doctor and (read-only) the Administrator, with the same
    actions as a row of today's table, drawn from models/queue_actions.py. `active` is the
    visit holding the room, which decides whether Start can be offered.
    """
    marks = ", ".join("?" for _ in OPEN_STATUSES)
    with db_connection() as conn:
        rows = conn.execute(
            _QUEUE_SELECT
            + f" WHERE a.status IN ({marks}) AND date(a.appointment_date) < ? "
              "ORDER BY a.appointment_date, a.checked_in_at, a.id",
            (*OPEN_STATUSES, today().isoformat()),
        ).fetchall()
    if active is None:
        active = get_active_consultation()
    moment = now().replace(tzinfo=None)
    entries = []
    for row in rows:
        entry = _to_queue_entry(row)
        try:
            since = datetime.strptime((entry["checked_in_at"] or "")[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            since = None
        entry["waiting_text"] = waiting_text(since, moment)
        entry["checked_in_date"] = _as_date(entry["appointment_date"])
        # Start is offered on the same fact the server tests: nobody holds the room.
        entry["can_start"] = entry["is_waiting"] and active is None
        entry["is_ready"] = False
        entry["display_status"] = entry["status"]
        entry["display_badge_class"] = entry["status_badge_class"]
        entries.append(entry)
    return entries


def count_open_by_status(entries):
    """{status: how many} for the three open statuses, in the legend's order."""
    return {status: sum(1 for entry in entries if entry["status"] == status)
            for status in OPEN_STATUSES}


def get_appointment_day_summary(start_date, end_date):
    """{ISO date: counts} over an inclusive range, for the calendar grid.

    One grouped query for the whole month rather than one per cell. The three
    buckets match the legend the calendar already prints: still to happen,
    finished, and called off.
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT date(appointment_date) AS day, status, COUNT(*) AS count
        FROM appointments
        WHERE date(appointment_date) BETWEEN ? AND ?
        GROUP BY day, status
        """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

    summary = {}
    for row in rows:
        bucket = summary.setdefault(
            row["day"],
            {"total": 0, "pending": 0, "in_queue": 0, "completed": 0, "cancelled": 0,
             "left": 0, "referred": 0, "waiting_doctor": 0, "waiting": 0, "in_consultation": 0},
        )
        bucket["total"] += row["count"]
        if row["status"] in PENDING_STATUSES:
            bucket["pending"] += row["count"]
        elif row["status"] in QUEUE_STATUSES:
            bucket["in_queue"] += row["count"]
            # The two real statuses behind in_queue, for the calendar's own dots (Task 6d).
            bucket["waiting" if row["status"] == WAITING else "in_consultation"] += row["count"]
        elif row["status"] == COMPLETED:
            bucket["completed"] += row["count"]
        elif row["status"] == WAITING_DOCTOR:
            bucket["waiting_doctor"] += row["count"]
        elif row["status"] == LEFT:
            bucket["left"] += row["count"]
        elif row["status"] == REFERRED:
            bucket["referred"] += row["count"]
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

# The four outcomes Screen 10's Appointment Statistics chart stacks. Every
# status the CHECK admits maps into exactly one of them, so the bars sum to the
# month's total appointments and nothing is quietly dropped.
OUTCOME_EXPECTED = "Expected"       # Scheduled / Confirmed -- still to happen
OUTCOME_ATTENDED = "Attended"       # Waiting / In Consultation / Completed
OUTCOME_AWAITING = "Awaiting"       # Waiting for the Doctor (Task 6b, D6): came, intake saved
OUTCOME_MISSED = "Missed"           # Cancelled / No-show
OUTCOME_LEFT = "Left"               # Left before being seen (Task 6, D6)
OUTCOME_REFERRED = "Referred"       # Sent on to the RHU or a hospital (Task 19, D3)

_OUTCOME_BY_STATUS = {
    "Scheduled": OUTCOME_EXPECTED,
    "Confirmed": OUTCOME_EXPECTED,
    "Waiting": OUTCOME_ATTENDED,
    "In Consultation": OUTCOME_ATTENDED,
    "Waiting for the Doctor": OUTCOME_AWAITING,
    "Completed": OUTCOME_ATTENDED,
    "Cancelled": OUTCOME_MISSED,
    "No-show": OUTCOME_MISSED,
    "Left before being seen": OUTCOME_LEFT,
    "Referred": OUTCOME_REFERRED,
}

OUTCOMES = (OUTCOME_EXPECTED, OUTCOME_ATTENDED, OUTCOME_AWAITING, OUTCOME_MISSED, OUTCOME_LEFT,
            OUTCOME_REFERRED)


def _outcome_summary(counts, walk_ins, total, services, viewer_role, referrals=None):
    """One period's appointment outcomes, however that period was chosen.

    Shared by the year-to-date block and the ranged `window` block below so the
    two cannot compute an attendance rate differently. The rate is of *resolved*
    appointments for the reason get_appointment_report() gives.
    """
    # A patient who left before being seen is resolved (the visit is over) and is
    # neither attended nor missed: it is its own figure (Task 6, D6).
    #
    # "Waiting for the Doctor" (Task 6b, D6) is its own figure, so "Attended" counts
    # only finished visits and the people in the clinic right now. The patient did
    # come, so the attendance rate still counts them as attended: it does not move.
    #
    # "Referred" (Task 19, D3) is its own figure too. The patient came and the visit is over,
    # so it is resolved and counts as having come: the attendance rate counts it as attended.
    came = counts[OUTCOME_ATTENDED] + counts[OUTCOME_AWAITING] + counts[OUTCOME_REFERRED]
    resolved = came + counts[OUTCOME_MISSED] + counts[OUTCOME_LEFT]
    return {
        "total": total,
        "expected": counts[OUTCOME_EXPECTED],
        # Records from the old booking system (Scheduled, Confirmed, Cancelled, No-show).
        # No screen or file shows them as figures; one line says how many there are, and
        # only when there are some (Task 11, L48).
        "older": counts[OUTCOME_EXPECTED] + counts[OUTCOME_MISSED],
        "attended": counts[OUTCOME_ATTENDED],
        "awaiting": counts[OUTCOME_AWAITING],
        "missed": counts[OUTCOME_MISSED],
        "left": counts[OUTCOME_LEFT],
        "referred": counts[OUTCOME_REFERRED],
        # The referrals by where they went, in the order of REFERRAL_DESTINATIONS. The small-count
        # rule folds a destination with 1 to 4 referrals for the Administrator and the Official;
        # the total above is exact.
        "referral_destinations": fold_small_counts(
            [{"destination": name, "count": count}
             for name, count in (referrals or {}).items() if count],
            viewer_role, label_key="destination", sum_keys=("count",),
        ),
        "walk_ins": walk_ins,
        "booked": total - walk_ins,
        "resolved": resolved,
        "attendance_pct": (
            round(came / resolved * 100, 1) if resolved else None
        ),
        "missed_pct": (
            round(counts[OUTCOME_MISSED] / resolved * 100, 1) if resolved else None
        ),
        # Task 5e (D1): a service with 1 to 4 appointments folds into one Other
        # row for the Administrator and the Official. The total above is exact.
        "services": fold_small_counts(
            sorted(
                ({"service": name, "count": count} for name, count in services.items()),
                key=lambda item: (-item["count"], item["service"].lower()),
            ),
            viewer_role, label_key="service", sum_keys=("count",),
        ),
    }


def get_appointment_report(months=6, on_date=None, start=None, end=None, *, viewer_role):
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

    with db_connection() as conn:
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
        referrals = count_by_destination(conn, lo, hi)

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
            "older": bucket[OUTCOME_EXPECTED] + bucket[OUTCOME_MISSED],
            "attended": bucket[OUTCOME_ATTENDED],
            "awaiting": bucket[OUTCOME_AWAITING],
            "missed": bucket[OUTCOME_MISSED],
            "left": bucket[OUTCOME_LEFT],
            "referred": bucket[OUTCOME_REFERRED],
            "total": bucket["total"],
        })

    ytd_summary = _outcome_summary(ytd, ytd_walk_ins, ytd_total, services, viewer_role)
    return {
        "year": year,
        "ytd_total": ytd_total,
        "ytd_expected": ytd[OUTCOME_EXPECTED],
        "ytd_attended": ytd[OUTCOME_ATTENDED],
        "ytd_awaiting": ytd[OUTCOME_AWAITING],
        "ytd_missed": ytd[OUTCOME_MISSED],
        "ytd_left": ytd[OUTCOME_LEFT],
        "ytd_referred": ytd[OUTCOME_REFERRED],
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
                scoped_counts, scoped_walk_ins, scoped_total, scoped_services,
                viewer_role, referrals,
            ),
            # The Prenatal Check-up count printed beside the prenatal note. It is
            # tied to a service, so it reads "Fewer than 5" for those two roles.
            "prenatal_visits": shown_count(
                scoped_services.get("Prenatal Check-up", 0), viewer_role),
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
                "waiting_doctor": counts["waiting_doctor"] if counts else 0,
                "waiting": counts["waiting"] if counts else 0,
                "in_consultation": counts["in_consultation"] if counts else 0,
                "left": counts["left"] if counts else 0,
                "referred": counts["referred"] if counts else 0,
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
