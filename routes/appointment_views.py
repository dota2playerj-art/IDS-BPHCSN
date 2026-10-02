"""Shared context builders for the appointment / consultation queue screen.

Screen 08 is rendered by two blueprints -- once for the Administrator and once
for Health Center Staff -- from the same template with the same data. The queries
live here so the two role variants cannot drift apart; the routes stay thin and
each keeps its own role_required guard and its own redirect target.

This mirrors routes/patient_views.py and routes/inventory_views.py exactly.
"""
from models.appointments import (
    attach_leave_flags,
    attach_visit_reasons,
    change_visit_service,
    check_in_patient,
    complete_consultation,
    get_active_consultation,
    get_appointment_by_id,
    get_calendar_month,
    get_earlier_waiting,
    get_queue_entry,
    get_queue_stats,
    get_todays_appointments,
    mark_left,
    send_to_doctor,
    parse_month,
    queue_display_name,
    start_consultation,
    undo_left,
)
from models.consultations import RESTRICTED_PLACEHOLDER
from models.doctor_worklist import VISIT_SERVICES, clean_service
from models.immunizations import get_immunization_alert, get_immunization_status
from models.patients import get_all_patients, get_patient_by_id
from models.service_schedule import get_entries as get_schedule_entries, services_on
from routes.audit_entries import (
    consultation_completed, consultation_started, left_before_seen, left_undone,
    patient_checked_in, visit_sent_to_doctor, visit_service_changed,
)
from utils.dates import today
from utils.roles import is_care_team
from utils.security import current_role

# Only a living, active record may be checked in. An Inactive or Deceased patient
# appearing in the Check In picker is a data-entry accident waiting to happen, and
# the roster is small enough that the filter costs nothing.
SCHEDULABLE_PATIENT_STATUS = "Active"


def appointment_scheduling_context(month=None):
    """Everything Screen 08 renders.

    Two things, and they are kept visibly apart because they answer different
    questions:

        today's queue      who is here, who is next
        the calendar       which days carried what load

    `month` selects which month the calendar shows ('YYYY-MM'); anything
    unusable falls back to the current one. The queue below it is always
    today's and is unaffected by it.
    """
    # The room is resolved once, here, and handed to both the queue and its stat
    # cards. get_active_consultation() is not scoped to a date -- a visit left
    # open on an earlier day still holds the clinician, and start_consultation()
    # refuses on exactly that basis -- so this is the fact the Start Consultation
    # button has to be offered on if the screen is not to advertise an action the
    # server will reject. One lookup, one answer, both consumers.
    active = get_active_consultation()
    entries = get_todays_appointments(active=active)
    # The check-in reason is added here, for this reader (Task 5b, D4). The
    # Administrator gets no reason on any row; it is decided on the server, so it
    # is in neither the page nor the export.
    role = current_role()
    entries = attach_visit_reasons(entries, role, queue_view=True)

    # Which children in today's queue are due or overdue for a dose. Read once
    # for the whole roster rather than per row -- get_immunization_alert() reads
    # every dose in one query -- and matched onto the queue by patient id, so the
    # badge on a row and the count on the dashboard are the same calculation.
    # Which child is due for which dose is an immunization record, and the
    # Check In dialog's picker is a patient write: both are the care team's
    # (Task 5c). For the Administrator neither is read.
    care_team = is_care_team(role)
    # The buttons for Left before being seen, and the visits still Waiting from earlier
    # days (Task 6). Only the care team gets either: the Administrator's queue is
    # read-only and the server refuses his POST anyway.
    if care_team:
        entries = attach_leave_flags(entries)
    immunization_alert = (get_immunization_alert() if care_team
                          else {"children": [], "child_count": 0,
                                "overdue_child_count": 0})
    due_by_patient = {
        child["patient"]["id"]: child for child in immunization_alert["children"]
    }
    for entry in entries:
        child = due_by_patient.get(entry["patient_id"])
        entry["immunization_due"] = child is not None
        entry["immunization_overdue"] = bool(child and child["overdue_count"])
        entry["immunization_count"] = child["attention_count"] if child else 0
        entry["immunization_next"] = child["next_label"] if child else None

    # What today already holds for each patient, so the Check In dialog can say
    # "already waiting" or "Completed today" beside a name instead of letting the
    # operator find out only after submitting. Keyed by patient row id.
    today_by_patient = {}
    for entry in entries:
        # First wins: entries arrive in queue order, so an active queue row is
        # seen before a later Completed one for the same person.
        today_by_patient.setdefault(entry["patient_id"], entry)

    patients = []
    for patient in (get_all_patients() if care_team else []):
        if patient.get("status") != SCHEDULABLE_PATIENT_STATUS:
            continue
        patient = dict(patient)
        entry = today_by_patient.get(patient["id"])
        patient["today_status"] = entry["status"] if entry else None
        patient["today_in_queue"] = bool(entry and entry["in_queue"])
        patients.append(patient)

    reference = today()

    return {
        "queue": entries,
        "earlier_waiting": get_earlier_waiting() if care_team else [],
        # False for the Administrator: the screen and the exports leave the reason
        # column out altogether.
        "show_visit_reason": is_care_team(role),
        "restricted_placeholder": RESTRICTED_PLACEHOLDER,
        "queue_stats": get_queue_stats(entries, active=active),
        # The filter panel's two dropdowns, built from the rows in today's queue
        # rather than from APPOINTMENT_TYPES and the status vocabulary. Those
        # list everything that can be booked or reached; offering a service
        # nobody is here for today would be an option that can only empty the
        # table. Screen 12's module filter is built the same way.
        "queue_filter_options": {
            # The service names a clinical fact, so the Administrator's queue has
            # no service filter and no service column (Task 6b).
            "services": sorted({
                entry["appointment_type"] or "Consultation" for entry in entries
            }) if care_team else [],
            "statuses": sorted({
                entry["display_status"] for entry in entries if entry["display_status"]
            }),
        },
        "checkin_patients": patients,
        # The one fixed list Staff choose from at check-in and when correcting a visit.
        "visit_services": VISIT_SERVICES,
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
        "services_today": _services_today(reference),
    }


def _services_today(reference):
    """What the Service Schedule says runs on `reference`, for the strip at the top.

    Asked about the SAME date the queue below it is built for, rather than
    reading the clock a second time, so the strip and the queue cannot describe
    two different days across midnight.

    `total` travels with the list because the two empty answers are different
    facts and the strip words them differently: a schedule nobody has filled in
    yet cannot say what runs today at all, while a filled schedule with nothing
    on today is a real answer about today.

    INFORMATION ONLY. Nothing in this module reads the result: check-in, the
    queue order and Start Consultation are decided exactly as they were before
    the schedule existed. A walk-in who is unwell is seen on any day.
    """
    entries = get_schedule_entries()
    return {
        "date": reference,
        "services": services_on(reference, entries),
        "total": len(entries),
    }


def process_check_in(form_data, user_id, ip_address=None):
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

    # A required choice with no default, checked here and again in check_in_patient().
    service = clean_service(form_data.get("service"))
    if service is None:
        return "Choose the service before checking the patient in."

    appointment_id, outcome = check_in_patient(
        patient_id, reason, user_id, audit=patient_checked_in(user_id, ip_address),
        service=service,
    )
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


def process_new_patient_check_in(patient_id, reason, user_id, ip_address=None, *, service):
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

    appointment_id, outcome = check_in_patient(
        patient_id, reason, user_id, audit=patient_checked_in(user_id, ip_address),
        service=service,
    )
    return (
        f"{patient['full_name']} registered as patient {patient['patient_id']}. "
        + _check_in_message(patient["full_name"], appointment_id, outcome, patient)
    )


def process_start_consultation(form_data, user_id=None, ip_address=None):
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
    outcome = start_consultation(
        appointment_id, audit=consultation_started(appointment_id, user_id, ip_address)
    )

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


def process_mark_left(form_data, user_id=None, ip_address=None):
    """Mark one visit as left before being seen. Returns the message to flash.

    The rules are mark_left()'s, which settles them in SQL. This only turns its
    outcome into a sentence a person at the desk can act on.
    """
    raw_id = (form_data.get("appointment_id") or "").strip()
    if not raw_id.isdigit():
        return "Choose a patient from the queue."
    appointment_id = int(raw_id)
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "That queue entry could not be found."
    name = queue_display_name(appointment)
    outcome = mark_left(
        appointment_id, user_id, audit=left_before_seen(appointment_id, user_id, ip_address))
    if outcome == "marked":
        return (f"{name} is marked as left before being seen. "
                "You can undo this today.")
    if outcome == "already":
        return f"{name} is already marked as left before being seen."
    return (f"{name} cannot be marked as left before being seen. "
            "A visit with a diagnosis, or one that is finished, cannot be changed here.")


def process_undo_left(form_data, user_id=None, ip_address=None):
    """Undo "left before being seen" on the day it was set. Returns the message."""
    raw_id = (form_data.get("appointment_id") or "").strip()
    if not raw_id.isdigit():
        return "Choose a patient from the queue."
    appointment_id = int(raw_id)
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "That queue entry could not be found."
    name = queue_display_name(appointment)
    outcome = undo_left(appointment_id, audit=left_undone(appointment_id, user_id, ip_address))
    if outcome == "undone":
        return f"{name} is back to {appointment['status_before_left']}."
    if outcome == "too-late":
        return (f"{name} was marked on an earlier day. It can only be undone "
                "on the same day.")
    if outcome == "busy":
        return (f"Another patient is in consultation, so {name} cannot go back in "
                "yet. Try again when that visit is complete.")
    return f"{name} is not marked as left before being seen."


def process_change_service(form_data, user_id=None, ip_address=None):
    """Correct the service of a visit that is not finished. Returns the message.

    The rules are change_visit_service()'s, which settles them in SQL: only a visit
    that is Waiting, In Consultation or Waiting for the Doctor, and only to a service
    in VISIT_SERVICES. This turns its outcome into a sentence.
    """
    raw_id = (form_data.get("appointment_id") or "").strip()
    if not raw_id.isdigit():
        return "Choose a patient from the queue."
    appointment_id = int(raw_id)
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "That queue entry could not be found."
    name = queue_display_name(appointment)
    outcome = change_visit_service(
        appointment_id, form_data.get("service"),
        audit=visit_service_changed(appointment_id, user_id, ip_address),
    )
    if outcome in ("changed", "changed-completed"):
        message = f"The service of {name}'s visit is changed to {clean_service(form_data.get('service'))}."
        if outcome == "changed-completed":
            message += " This service does not need the Doctor, so the visit is now Completed."
        return message
    if outcome == "same":
        return f"{name}'s visit already has that service."
    if outcome == "invalid":
        return "Choose a service from the list."
    return (f"The service of {name}'s visit cannot be changed. "
            "A visit that is finished or marked as left cannot be changed.")


def process_send_to_doctor(form_data, user_id=None, ip_address=None):
    """Send the visit in progress to the Doctor. Returns the message to flash."""
    raw_id = (form_data.get("appointment_id") or "").strip()
    if not raw_id.isdigit():
        return "Choose the consultation to send to the Doctor."
    appointment_id = int(raw_id)
    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return "That queue entry could not be found."
    name = queue_display_name(appointment)
    outcome = send_to_doctor(
        appointment_id, audit=visit_sent_to_doctor(appointment_id, user_id, ip_address))
    if outcome == "sent":
        return f"{name}'s visit is now Waiting for the Doctor."
    if outcome == "already":
        return f"{name}'s visit is already Waiting for the Doctor."
    if outcome == "not-needed":
        return f"{name}'s visit does not need the Doctor. Use Mark Completed."
    return f"{name} is marked {appointment['status']}, not In Consultation."


def process_complete_consultation(form_data, user_id=None, ip_address=None):
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
    outcome = complete_consultation(
        appointment_id, audit=consultation_completed(appointment_id, user_id, ip_address)
    )

    if outcome == "needs-doctor":
        return "This visit needs the Doctor first."
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
