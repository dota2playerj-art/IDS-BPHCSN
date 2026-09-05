"""Shared context builders for the appointment / consultation queue screen.

Screen 08 is rendered by two blueprints -- once for the Administrator and once
for Health Center Staff -- from the same template with the same data. The queries
live here so the two role variants cannot drift apart; the routes stay thin and
each keeps its own role_required guard and its own redirect target.

This mirrors routes/patient_views.py and routes/inventory_views.py exactly.
"""
from datetime import timedelta

from models.appointments import (
    APPOINTMENT_TYPES,
    BOOKING_HORIZON_DAYS,
    BOOKING_NOTES_MAX,
    CLOSURE_STATUSES,
    booking_time_slots,
    check_in_patient,
    complete_consultation,
    get_active_consultation,
    get_appointment_by_id,
    get_calendar_month,
    get_queue_entry,
    get_queue_stats,
    get_slot_load,
    get_todays_appointments,
    get_upcoming_appointments,
    get_upcoming_stats,
    parse_month,
    queue_display_name,
    start_consultation,
)
from models.immunizations import get_immunization_alert, get_immunization_status
from models.patients import get_all_patients, get_patient_by_id
from models.users import get_clinical_staff
from utils.dates import today

# Only a living, active record may be checked in or booked. An Inactive or
# Deceased patient appearing in either picker is a data-entry accident waiting to
# happen, and the roster is small enough that the filter costs nothing.
SCHEDULABLE_PATIENT_STATUS = "Active"


def _booking_for_patient(patient_id):
    """Open the New Appointment dialog on a named patient, or None.

    The counterpart of _open_booking() for the other direction: ?book=<id> is
    how the Patient Profile offers "Schedule Appointment" without holding a
    second copy of the booking dialog, exactly as ?reschedule= and ?cancel=
    already work for that screen's Appointment History.

    Nothing is booked here -- this only decides which patient the dialog opens
    on. The submit still goes through process_book_appointment() and is
    validated there, because a POST need not come from this page.

    A patient the dialog cannot offer is not preselected: the picker lists
    Active records only, so an Inactive or Deceased id would open a dialog with
    nothing chosen and no reason given. The link lands on the screen instead,
    where the queue and the calendar are.
    """
    raw = (str(patient_id) if patient_id is not None else "").strip()
    if not raw.isdigit():
        return None
    patient = get_patient_by_id(int(raw))
    if patient is None or patient["status"] != SCHEDULABLE_PATIENT_STATUS:
        return None
    return {"open": True, "mode": "existing", "form": {"patient_id": raw}}


def appointment_scheduling_context(month=None, booking=None, reschedule=None,
                                   reschedule_id=None, cancel_id=None,
                                   return_to="", book_patient_id=None):
    """Everything Screen 08 renders.

    Three things now, and they are kept visibly apart because they answer
    different questions:

        today's queue      who is here, who is next    (unchanged by this pass)
        the calendar       which days carry what load
        upcoming bookings  who is expected, and when

    `month` selects which month the calendar shows ('YYYY-MM'); anything
    unusable falls back to the current one. `booking` carries the New
    Appointment dialog's state back after a submit that did not save -- its
    values, its field errors and any scheduling conflict awaiting
    acknowledgement -- so the operator's entry survives the round trip exactly
    as Register Patient's does. `reschedule` does the same for the Reschedule
    dialog.

    `reschedule_id` / `cancel_id` open one of those dialogs on a named
    appointment, and `return_to` says where the action should land afterwards.
    Together they are how the Patient Profile's Appointment History offers these
    actions without holding a second copy of either dialog: it links here, the
    dialog it asked for opens on the right row, and the operator is put back on
    the profile when it is done.
    """
    # The room is resolved once, here, and handed to both the queue and its stat
    # cards. get_active_consultation() is not scoped to a date -- a visit left
    # open on an earlier day still holds the clinician, and start_consultation()
    # refuses on exactly that basis -- so this is the fact the Start Consultation
    # button has to be offered on if the screen is not to advertise an action the
    # server will reject. One lookup, one answer, both consumers.
    active = get_active_consultation()
    entries = get_todays_appointments(active=active)

    # Which children in today's queue are due or overdue for a dose. Read once
    # for the whole roster rather than per row -- get_immunization_alert() reads
    # every dose in one query -- and matched onto the queue by patient id, so the
    # badge on a row and the count on the dashboard are the same calculation.
    immunization_alert = get_immunization_alert()
    due_by_patient = {
        child["patient"]["id"]: child for child in immunization_alert["children"]
    }
    for entry in entries:
        child = due_by_patient.get(entry["patient_id"])
        entry["immunization_due"] = child is not None
        entry["immunization_overdue"] = bool(child and child["overdue_count"])
        entry["immunization_count"] = child["attention_count"] if child else 0
        entry["immunization_next"] = child["next_label"] if child else None

    # What today already holds for each patient, so the dialog can say "booked
    # 09:15" or "already waiting" beside a name instead of letting the operator
    # find out only after submitting. Keyed by patient row id.
    today_by_patient = {}
    for entry in entries:
        # First wins: entries arrive in queue order, so an active queue row is
        # seen before a later Completed one for the same person.
        today_by_patient.setdefault(entry["patient_id"], entry)

    patients = []
    for patient in get_all_patients():
        if patient.get("status") != SCHEDULABLE_PATIENT_STATUS:
            continue
        patient = dict(patient)
        entry = today_by_patient.get(patient["id"])
        patient["today_status"] = entry["status"] if entry else None
        patient["today_booked_time"] = entry["booked_time"] if entry else None
        patient["today_in_queue"] = bool(entry and entry["in_queue"])
        patients.append(patient)

    reference = today()
    upcoming = get_upcoming_appointments(from_date=reference)

    return {
        "queue": entries,
        "queue_stats": get_queue_stats(entries, active=active),
        # The filter panel's two dropdowns, built from the rows in today's queue
        # rather than from APPOINTMENT_TYPES and the status vocabulary. Those
        # list everything that can be booked or reached; offering a service
        # nobody is here for today would be an option that can only empty the
        # table. Screen 12's module filter is built the same way.
        "queue_filter_options": {
            "services": sorted({
                entry["appointment_type"] or "Consultation" for entry in entries
            }),
            "statuses": sorted({
                entry["display_status"] for entry in entries if entry["display_status"]
            }),
        },
        "checkin_patients": patients,
        "queue_date": reference,
        "immunization_alert": immunization_alert,
        # How many of the children needing a dose are actually in the building
        # today -- the ones staff can act on before the parent leaves.
        "immunization_in_queue": sum(
            1 for entry in entries
            if entry["immunization_due"] and entry["in_queue"]
        ),
        # The calendar panel, which until now was a hand-written July 2026 grid.
        "calendar": get_calendar_month(parse_month(month, reference), reference),
        # Future bookings, listed apart from the queue above -- see the panel's
        # own note in the template for why they are not merged.
        "upcoming": upcoming,
        "upcoming_stats": get_upcoming_stats(upcoming, reference),
        # A booking bounced back from a failed submit wins over ?book=<id>: the
        # operator's own entry must never be discarded in favour of a dialog
        # reopened blank on a patient.
        **booking_context(booking or _booking_for_patient(book_patient_id)),
        **reschedule_context(reschedule, reschedule_id),
        **cancel_context(cancel_id),
        # Rendered as a hidden field in both dialogs, so wherever the operator
        # opened them from is where the completed action puts them back.
        "return_to": (return_to or "").strip(),
    }


def _open_booking(appointment_id):
    """The named appointment if it can still be moved or called off, else None.

    A link naming an appointment that has since been checked in, cancelled or
    completed simply lands on the page with its dialog shut, rather than opening
    one on a refusal. The screen behind it already shows what happened instead.
    """
    if not str(appointment_id or "").strip().isdigit():
        return None
    appointment = get_appointment_by_id(int(appointment_id))
    if appointment is None or not appointment["is_open_booking"]:
        return None
    return appointment


def reschedule_context(reschedule=None, reschedule_id=None):
    """The Reschedule dialog's state.

    It shares every vocabulary and bound with the New Appointment dialog -- they
    are both choosing a slot for the same clinic -- so nothing is redefined here;
    booking_context() supplies the slots, the date bounds and the slot load, and
    this only carries which appointment is being moved and what has been entered
    for it.
    """
    reschedule = dict(reschedule or {})
    appointment = reschedule.get("appointment") or _open_booking(reschedule_id)

    return {
        "reschedule": {
            "open": bool(reschedule.get("open")) or appointment is not None,
            "appointment": appointment,
            "form": reschedule.get("form") or {},
            "errors": reschedule.get("errors") or {},
            "conflicts": reschedule.get("conflicts") or {"slot": [], "patient_day": []},
            "acknowledge_conflict": bool(reschedule.get("acknowledge_conflict")),
        },
    }


def cancel_context(cancel_id=None):
    """The Cancel dialog's state when a link opened it on a named appointment.

    Every other way into that dialog is a button on this page, which tells it
    which appointment through data-* attributes; this is the one path where the
    server has to render the target, because the request arrived without one.
    """
    appointment = _open_booking(cancel_id)
    return {
        "cancel": {
            "open": appointment is not None,
            "appointment": appointment,
            "closures": (
                appointment["closures"] if appointment else CLOSURE_STATUSES
            ),
        },
    }


def booking_context(booking=None):
    """The New Appointment dialog's own context, whether or not it is reopening.

    Built here rather than inside the template so the vocabularies the form
    offers are the same tuples validate_booking_form() checks against, and the
    dialog cannot present a service or a slot the server would then reject.
    """
    booking = dict(booking or {})
    reference = today()
    return {
        "booking": {
            "open": bool(booking.get("open")),
            "mode": booking.get("mode") or "existing",
            "form": booking.get("form") or {},
            "errors": booking.get("errors") or {},
            "conflicts": booking.get("conflicts") or {"slot": [], "patient_day": []},
            "acknowledge_conflict": bool(booking.get("acknowledge_conflict")),
        },
        "appointment_types": APPOINTMENT_TYPES,
        # Read per render rather than from a module constant: the clinic day is
        # a stored setting now, so the dropdown has to be built from whatever
        # Screen 13 currently holds -- and from the same call validate_booking()
        # makes, so the times offered and the times accepted cannot diverge.
        "booking_time_slots": booking_time_slots(),
        "booking_notes_max": BOOKING_NOTES_MAX,
        "clinical_staff": get_clinical_staff(),
        # The date input's own bounds, so the picker refuses out-of-range days
        # before the server has to. The server still checks -- see
        # validate_booking_form() -- because a POST need not come from this page.
        "booking_min_date": (reference + timedelta(days=1)).isoformat(),
        "booking_max_date": (reference + timedelta(days=BOOKING_HORIZON_DAYS)).isoformat(),
        # {date: {time: [names]}} so the time dropdown can mark the slots a
        # chosen day already has somebody in.
        "booking_slot_load": get_slot_load(reference),
    }


def process_check_in(form_data, user_id):
    """Apply the Check In Patient action. Returns the message to flash.

    Validated here rather than trusted from the page: the dialog only lists
    Active patients, but a POST can be made without ever loading it.
    """
    raw_id = (form_data.get("patient_id") or "").strip()
    if not raw_id.isdigit():
        return "Choose a patient to check in."

    patient_id = int(raw_id)
    patient = next(
        (
            candidate
            for candidate in get_all_patients()
            if candidate["id"] == patient_id
        ),
        None,
    )
    if patient is None:
        return "That patient record could not be found."
    if patient.get("status") != SCHEDULABLE_PATIENT_STATUS:
        return (
            f"{patient['full_name']} is marked {patient.get('status')}. "
            "Only active patient records can be checked in."
        )

    reason = (form_data.get("reason") or "").strip()
    if not reason:
        return "Enter a reason for the visit before checking the patient in."

    appointment_id, outcome = check_in_patient(patient_id, reason, user_id)
    return _check_in_message(patient["full_name"], appointment_id, outcome, patient)


def _queue_placement(appointment_id):
    """How the queue now reads for one just-checked-in patient.

    Read back through get_queue_entry() -- the same computation the screen runs --
    so the message and the row the operator is about to look at cannot disagree
    about whether the patient can go straight in.
    """
    entry = get_queue_entry(appointment_id) or get_appointment_by_id(appointment_id)
    if entry is None:
        return None, None, ""

    arrival = entry.get("arrival_time")
    if entry.get("is_ready"):
        placement = "The clinician is free — they can be seen now."
    elif entry.get("is_waiting"):
        active = get_active_consultation()
        position = entry.get("line_position")
        place = f" ({_ordinal(position)} in line)" if position else ""
        if active:
            placement = (
                f"They are Waiting{place} while "
                f"{queue_display_name(active)} is in consultation."
            )
        else:
            placement = f"They are Waiting{place}."
    else:
        placement = f"They are marked {entry.get('status')}."

    return entry, arrival, placement


def _ordinal(number):
    """1 -> '1st'. Used for the operator-facing 'Nth in line'."""
    if number is None:
        return ""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _immunization_note(patient):
    """The immunisation sentence a check-in adds, or "" when there is nothing due.

    Said at check-in rather than left for whoever opens the profile: the whole
    value of tracking defaulters is catching them while the parent is still at
    the desk. A child who is overdue and walks in for a cough is the one chance
    that month to give the dose, and it is missed if the information only appears
    somewhere nobody has a reason to look.
    """
    if not patient:
        return ""
    status = get_immunization_status(patient)
    if not status["needs_attention"]:
        return ""

    doses = ", ".join(item["label"] for item in status["attention_items"][:3])
    more = len(status["attention_items"]) - 3
    if more > 0:
        doses += f" and {more} more"
    lead = "OVERDUE for" if status["overdue_count"] else "due for"
    return (
        f" IMMUNISATION: {patient['first_name']} is {lead} {doses} — "
        "record it during today's consultation."
    )


def _check_in_message(full_name, appointment_id, outcome, patient=None):
    """The flash text for a completed check-in, whichever path produced it.

    Shared by the existing-patient dialog and the new-patient registration path
    so a first-time walk-in is told the same things, in the same words, as
    everybody else.
    """
    entry, arrival, placement = _queue_placement(appointment_id)
    at = f" at {arrival}" if arrival else ""
    note = _immunization_note(patient)

    if outcome == "already":
        status = entry.get("display_status") if entry else "in today's queue"
        return f"{full_name} is already in today's queue ({status})." + note
    if outcome == "updated":
        return (
            f"{full_name} checked in for their scheduled appointment{at}. {placement}"
            + note
        )
    return f"{full_name} checked in as a walk-in{at}. {placement}" + note


def process_new_patient_check_in(patient_id, reason, user_id):
    """Queue a patient who was registered from the Check In dialog.

    The second half of the "New Patient (first visit)" path: Register Patient has
    just created the record, and this puts that same person into today's queue
    without the operator having to come back and check them in separately.

    Nothing about the queueing differs from an existing patient's walk-in -- it
    is the same check_in_patient() call and the same message builder -- so the
    two paths cannot produce differently-shaped queue rows.
    """
    patient = get_patient_by_id(patient_id)
    if patient is None:
        return "That patient record could not be found, so nobody was checked in."

    appointment_id, outcome = check_in_patient(patient_id, reason, user_id)
    return (
        f"{patient['full_name']} registered as patient {patient['patient_id']}. "
        + _check_in_message(patient["full_name"], appointment_id, outcome, patient)
    )


# ---------------------------------------------------------------------------
# NEW APPOINTMENT (advance booking)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CANCELLING AND RESCHEDULING
#
# Neither of these introduces a rule of its own. Cancelling is the appointment
# equivalent of Screen 03's status change -- a guarded UPDATE to a status the
# CHECK already admits, with the row kept -- and rescheduling reuses the booking
# form's validator and its conflict check unchanged, because moving a visit to
# Thursday 10:00 has to be judged by exactly the standard that booking it for
# Thursday 10:00 in the first place would have been.
# ---------------------------------------------------------------------------


def process_start_consultation(form_data):
    """Move one Waiting patient to In Consultation. Returns the message to flash.

    The decision itself belongs to start_consultation(), which settles it inside
    one atomic UPDATE; this only turns its outcome into something a person at the
    desk can act on. Re-deciding it here would reintroduce exactly the read-then-
    write window that let several patients be In Consultation at once.
    """
    raw_id = (form_data.get("appointment_id") or "").strip()
    if not raw_id.isdigit():
        return "Choose a patient from the queue to start a consultation."

    appointment_id = int(raw_id)
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "That queue entry could not be found."

    name = queue_display_name(appointment)
    outcome = start_consultation(appointment_id)

    if outcome == "started":
        return f"{name} is now In Consultation."
    if outcome == "already":
        return f"{name} is already in consultation."
    if outcome == "missing":
        return "That queue entry could not be found."
    if outcome == "busy":
        # The page the button was clicked on had already gone stale. Name who
        # actually holds the room, and what has to happen before this patient
        # can go in, rather than just refusing.
        active = get_active_consultation()
        holder = queue_display_name(active) or "Another patient"
        return (
            f"{holder} is still in consultation. Only one patient can be seen at a "
            f"time here, so {name} stays in the queue — mark {holder}'s "
            "consultation completed first."
        )
    return (
        f"{name} is marked {appointment['status']}, not Waiting. "
        "Only a waiting patient can be brought in."
    )


def process_complete_consultation(form_data):
    """Close the consultation in progress. Returns the message to flash.

    Completing is what frees the clinician, so the message says who that makes
    available next -- read back from the queue after the write, so it names
    whoever the screen is about to show as ready rather than who was next before.
    """
    raw_id = (form_data.get("appointment_id") or "").strip()
    if not raw_id.isdigit():
        return "Choose the consultation to mark completed."

    appointment_id = int(raw_id)
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "That queue entry could not be found."

    name = queue_display_name(appointment)
    outcome = complete_consultation(appointment_id)

    if outcome == "already":
        return f"{name}'s consultation is already marked completed."
    if outcome == "missing":
        return "That queue entry could not be found."
    if outcome == "not-in-consultation":
        return (
            f"{name} is marked {appointment['status']}, not In Consultation. "
            "Only the consultation currently in progress can be completed."
        )

    stats = get_queue_stats()
    if stats["next_up_name"]:
        return (
            f"{name}'s consultation is complete. {stats['next_up_name']} is next "
            f"and can be started now"
            + (
                f" — {stats['still_waiting']} other{'' if stats['still_waiting'] == 1 else 's'} waiting."
                if stats["still_waiting"]
                else "."
            )
        )
    return f"{name}'s consultation is complete. Nobody else is waiting."
