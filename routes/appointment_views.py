"""Shared context builders for the appointment / consultation queue screen.

Screen 08 is rendered by two blueprints -- once for the Administrator and once
for Health Center Staff -- from the same template with the same data. The queries
live here so the two role variants cannot drift apart; the routes stay thin and
each keeps its own role_required guard and its own redirect target.

This mirrors routes/patient_views.py and routes/inventory_views.py exactly.
"""
from datetime import timedelta

from flask import url_for

from models.appointments import (
    APPOINTMENT_TYPES,
    BOOKING_HORIZON_DAYS,
    BOOKING_NOTES_MAX,
    BOOKING_TIME_SLOTS,
    CLOSURE_STATUSES,
    check_in_patient,
    close_appointment,
    complete_consultation,
    create_appointment,
    find_scheduling_conflicts,
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
    reschedule_appointment,
    start_consultation,
    validate_booking_form,
)
from models.immunizations import get_immunization_alert, get_immunization_status
from models.patients import get_all_patients, get_patient_by_id
from models.users import get_clinical_staff
from utils.dates import display_date, today

# Only a living, active record may be checked in or booked. An Inactive or
# Deceased patient appearing in either picker is a data-entry accident waiting to
# happen, and the roster is small enough that the filter costs nothing.
SCHEDULABLE_PATIENT_STATUS = "Active"

# The submit that opened the dialog's "New patient" pane rather than its picker.
BOOKING_MODE_FIELD = "booking_mode"
NEW_PATIENT_MODE = "new"

# Cancelling and rescheduling are offered on two screens -- Appointment
# Scheduling and the Patient Profile's Appointment History -- but there is one
# endpoint for each action rather than a pair per screen, because the write is
# identical and a second copy could only ever drift from the first. This field is
# how the operator gets put back where they were working.
RETURN_TO_FIELD = "return_to"
RETURN_TO_PROFILE = "profile:"


def booking_mode(source):
    """'new' when the booking came from the dialog's new-patient pane."""
    return (source.get(BOOKING_MODE_FIELD) or "").strip().lower()


def appointment_return_url(form_data, scheduling_endpoint, profile_endpoint):
    """Where a cancel or reschedule should land, given where it came from.

    The two endpoint names are passed in rather than looked up here: they differ
    per role, and each blueprint already owns its own URL space. Anything the
    field does not recognise falls back to Appointment Scheduling, so a hand-made
    POST cannot redirect anywhere of its choosing.
    """
    raw = (form_data.get(RETURN_TO_FIELD) or "").strip()
    if raw.startswith(RETURN_TO_PROFILE):
        patient_id = raw[len(RETURN_TO_PROFILE):]
        if patient_id.isdigit():
            return url_for(profile_endpoint, patient_id=int(patient_id))
    return url_for(scheduling_endpoint)


def appointment_scheduling_context(month=None, booking=None, reschedule=None,
                                   reschedule_id=None, cancel_id=None,
                                   return_to=""):
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
    entries = get_todays_appointments()

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
        "queue_stats": get_queue_stats(entries),
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
        **booking_context(booking),
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
        "booking_time_slots": BOOKING_TIME_SLOTS,
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


def _extract_booking_form(form_data):
    """The dialog's submitted values, in the shape the model and template share."""
    values = {
        key: (form_data.get(key) or "").strip()
        for key in (
            "patient_id", "appointment_date", "appointment_time",
            "appointment_type", "assigned_staff_id", "notes",
        )
    }
    return values


def _booking_failure(values, errors=None, conflicts=None,
                     acknowledge_conflict=False, mode="existing"):
    """Rebuild the whole screen with the dialog reopened on what was entered."""
    return appointment_scheduling_context(
        booking={
            "open": True,
            "mode": mode,
            "form": values,
            "errors": errors,
            "conflicts": conflicts,
            "acknowledge_conflict": acknowledge_conflict,
        }
    )


def _conflict_sentences(conflicts):
    """The clashes a saved booking should mention, as finished sentences.

    Used on the paths where the booking has already been created, so the desk is
    told what it now shares a day with rather than being asked about it.
    """
    lines = []
    for entry in conflicts.get("patient_day") or []:
        lines.append(
            f"Note: they were already booked that day at "
            f"{entry.get('booked_time') or 'an unspecified time'} "
            f"({entry.get('appointment_type') or 'Consultation'}) — check whether "
            "one of the two should be cancelled."
        )
    others = conflicts.get("slot") or []
    if others:
        names = ", ".join(queue_display_name(entry) for entry in others)
        lines.append(
            f"Note: {names} {'is' if len(others) == 1 else 'are'} also booked for "
            "that slot, so one of them will wait."
        )
    return lines


def _booked_message(patient, values, conflicts=None):
    """The flash text for a booking that saved, whichever path created it."""
    staff_name = ""
    if values.get("assigned_staff_id"):
        staff_name = next(
            (
                member["full_name"]
                for member in get_clinical_staff()
                if str(member["id"]) == str(values["assigned_staff_id"])
            ),
            "",
        )

    message = (
        f"{patient['full_name']} is booked for {values['appointment_type']} on "
        f"{display_date(values['appointment_date'])} at {values['appointment_time']}"
        + (f" with {staff_name}" if staff_name else "")
        + ". Status is Scheduled — check them in from this screen when they arrive "
        "on the day."
    )
    for sentence in _conflict_sentences(conflicts or {}):
        message += " " + sentence
    return message


def _bookable_patient(patient_id):
    """(patient, error message). Exactly one of the two is set."""
    patient = get_patient_by_id(patient_id)
    if patient is None:
        return None, "That patient record could not be found."
    if patient.get("status") != SCHEDULABLE_PATIENT_STATUS:
        return None, (
            f"{patient['full_name']} is marked {patient.get('status')}. "
            "Only active patient records can be given an appointment."
        )
    return patient, ""


def process_book_appointment(form_data, user_id):
    """Book a future visit for an existing patient.

    Returns (appointment_id, context, message). Exactly one of the first two is
    meaningful, the same contract process_add_edit_medicine() uses: an id means
    redirect and flash, a context means re-render the screen with the dialog
    reopened.

    Two rounds are possible, and only the second can save:

      1. Anything certainly wrong -- no patient, a date that is not in the
         future, a service the form never offered -- comes back as field errors.
      2. Anything merely *questionable* -- the slot is taken, or this patient is
         already booked that day -- comes back as a warning with the entry
         preserved. Pressing Book again carries confirm_conflict and saves. See
         find_scheduling_conflicts() for why those two are warnings and not
         refusals.
    """
    values = _extract_booking_form(form_data)
    staff = get_clinical_staff()
    errors = validate_booking_form(values, staff_ids=[member["id"] for member in staff])

    patient = None
    if "patient_id" not in errors:
        patient, message = _bookable_patient(int(values["patient_id"]))
        if patient is None:
            errors["patient_id"] = message

    if errors:
        return None, _booking_failure(
            values,
            errors=errors,
            # An acknowledgement already given survives a later validation
            # failure, so the same clash is not raised twice.
            acknowledge_conflict=form_data.get("confirm_conflict") == "yes",
        ), ""

    conflicts = find_scheduling_conflicts(
        patient["id"], values["appointment_date"], values["appointment_time"]
    )
    has_conflict = bool(conflicts["slot"] or conflicts["patient_day"])
    if has_conflict and form_data.get("confirm_conflict") != "yes":
        return None, _booking_failure(
            values, conflicts=conflicts, acknowledge_conflict=True
        ), ""

    appointment_id = create_appointment(
        patient_id=patient["id"],
        user_id=user_id,
        appointment_date=values["appointment_date"],
        appointment_time=values["appointment_time"],
        appointment_type=values["appointment_type"],
        notes=values["notes"],
        assigned_staff_id=(
            int(values["assigned_staff_id"]) if values["assigned_staff_id"] else None
        ),
    )
    return appointment_id, None, _booked_message(patient, values, conflicts)


def process_new_patient_booking_request(form_data):
    """Check a booking made for somebody not yet registered.

    Returns (details, context). `details` set means the booking is sound and the
    caller should send the operator to Register Patient carrying it; a context
    means the dialog reopens with what is wrong.

    The details are validated *before* the registration form opens rather than
    after it saves, so a mistyped date is corrected while it is still only a
    dialog -- not after a permanent patient record has been created against it.

    No conflict check happens here, and none is needed: a patient who does not
    exist yet cannot already be booked that day, and the only remaining clash --
    somebody else in the slot -- never blocks a booking anyway. It is reported in
    the message once the record is saved. See process_new_patient_booking().
    """
    values = _extract_booking_form(form_data)
    # There is no patient to choose on this path; the record is made next.
    values["patient_id"] = ""
    staff = get_clinical_staff()
    errors = validate_booking_form(values, staff_ids=[member["id"] for member in staff])
    errors.pop("patient_id", None)

    if errors:
        return None, _booking_failure(
            values, errors=errors, mode=NEW_PATIENT_MODE
        )
    return values, None


def process_new_patient_booking(patient_id, values, user_id):
    """Book the future visit for a patient who was just registered.

    The second half of the dialog's "New patient" path, and the exact mirror of
    process_new_patient_check_in(): Register Patient has created the record, and
    this creates the appointment that registration was opened for, so the
    operator never has to come back and book it separately.

    The booking details were already validated in
    process_new_patient_booking_request() before the registration form opened.
    They are validated again here because they travelled through that form as
    hidden fields, and a form's hidden fields are only ever a claim.
    """
    patient, message = _bookable_patient(patient_id)
    if patient is None:
        return f"{message} No appointment was booked."

    staff_ids = [member["id"] for member in get_clinical_staff()]
    values = dict(values)
    values["patient_id"] = str(patient["id"])
    errors = validate_booking_form(values, staff_ids=staff_ids)
    if errors:
        return (
            f"{patient['full_name']} was registered as patient "
            f"{patient['patient_id']}, but the appointment was not booked: "
            + " ".join(errors.values())
            + " Use New Appointment to book it."
        )

    conflicts = find_scheduling_conflicts(
        patient["id"], values["appointment_date"], values["appointment_time"]
    )
    create_appointment(
        patient_id=patient["id"],
        user_id=user_id,
        appointment_date=values["appointment_date"],
        appointment_time=values["appointment_time"],
        appointment_type=values["appointment_type"],
        notes=values["notes"],
        assigned_staff_id=(
            int(values["assigned_staff_id"]) if values["assigned_staff_id"] else None
        ),
    )
    return (
        f"{patient['full_name']} registered as patient {patient['patient_id']}. "
        + _booked_message(patient, values, conflicts)
    )


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


def _appointment_from(form_data, field="appointment_id"):
    """(appointment, error message). Exactly one of the two is set."""
    raw_id = (form_data.get(field) or "").strip()
    if not raw_id.isdigit():
        return None, "Choose an appointment first."
    appointment = get_appointment_by_id(int(raw_id))
    if appointment is None:
        return None, "That appointment could not be found."
    return appointment, ""


def _appointment_label(appointment):
    """'Grace Ilagan's Prenatal Check-up on Aug 13, 2026 at 09:00'."""
    name = queue_display_name(appointment)
    what = appointment.get("appointment_type") or "appointment"
    when = display_date(appointment.get("appointment_date"))
    at = f" at {appointment['booked_time']}" if appointment.get("booked_time") else ""
    return f"{name}'s {what} on {when}{at}"


def process_cancel_appointment(form_data):
    """Cancel a booking, or write it off as a no-show. Returns the message to flash.

    The status arrives as the value of whichever submit button was pressed, the
    same way Screen 03's status dialog works, and is re-checked here against
    CLOSURE_STATUSES before it reaches the model -- a POST can be made without
    ever opening the dialog, and the schema's CHECK is not a place to find that
    out.

    Everything else is settled by close_appointment(), inside its UPDATE. This
    only turns the outcome into something a person at the desk can act on.
    """
    appointment, message = _appointment_from(form_data)
    if appointment is None:
        return message

    status = (form_data.get("status") or "").strip()
    if status not in CLOSURE_STATUSES:
        return "Choose how to close this appointment: Cancel it, or mark it a No-show."

    label = _appointment_label(appointment)
    outcome = close_appointment(appointment["id"], status)

    if outcome == "closed":
        kept = (
            " The booking is kept in the patient's appointment history — nothing "
            "was deleted."
        )
        if status == "Cancelled":
            return f"{label} is cancelled. It has left the upcoming list.{kept}"
        return f"{label} is marked No-show.{kept}"
    if outcome == "already":
        return f"{label} is already marked {status}."
    if outcome == "arrived":
        return (
            f"{queue_display_name(appointment)} has already been checked in and is "
            f"in today's queue, so that visit is under way and cannot be "
            f"{'cancelled' if status == 'Cancelled' else 'marked a no-show'}. "
            "Complete the consultation instead, or mark it completed from the queue."
        )
    if outcome == "resolved":
        return (
            f"{label} is already marked {appointment['status']}, so there is "
            "nothing left to close."
        )
    if outcome == "too-early":
        return (
            f"{label} has not happened yet, so it cannot be a no-show. Cancel it "
            "instead if the patient has called it off."
        )
    return "That appointment could not be found."


def process_reschedule_appointment(form_data):
    """Move a booking to a new date and time.

    Returns (appointment_id, context, message) -- the same contract
    process_book_appointment() uses, and for the same reason: an id means
    redirect and flash, a context means re-render the screen with the dialog
    reopened on what was entered.

    The two rounds are the booking dialog's two rounds, unchanged. Field errors
    come from validate_booking_form(); a taken slot or a second booking that day
    comes back as a warning that the next submit acknowledges. What is different
    is only the one argument: find_scheduling_conflicts() is told to leave this
    appointment out of the comparison, so a visit moved from 09:00 to 10:00 on
    its own day does not report the patient as clashing with themselves.
    """
    appointment, message = _appointment_from(form_data)
    if appointment is None:
        return None, None, message

    if not appointment["is_open_booking"]:
        if appointment["status"] in ("Waiting", "In Consultation"):
            return None, None, (
                f"{queue_display_name(appointment)} has already been checked in "
                "and is in today's queue, so that visit cannot be moved."
            )
        return None, None, (
            f"{_appointment_label(appointment)} is marked {appointment['status']} "
            "and can no longer be moved. Book a new appointment instead."
        )

    # Validated as a whole booking, not as two loose fields: the stored patient,
    # service and staff are put back alongside the new date and time so
    # validate_booking_form() judges the moved appointment by exactly the
    # standard it would judge a new one by.
    values = {
        "patient_id": str(appointment["patient_id"]),
        "appointment_date": (form_data.get("appointment_date") or "").strip(),
        "appointment_time": (form_data.get("appointment_time") or "").strip(),
        "appointment_type": appointment.get("appointment_type") or "",
        "assigned_staff_id": "",
        "notes": appointment.get("notes") or "",
    }
    staff = get_clinical_staff()
    errors = validate_booking_form(values, staff_ids=[m["id"] for m in staff])
    # The service and the note came off the stored row rather than from this
    # form, so a complaint about either belongs on the booking that created them,
    # not on the operator moving it. A walk-in converted long ago can carry a
    # service this vocabulary no longer lists; that must not make it immovable.
    errors.pop("appointment_type", None)
    errors.pop("notes", None)

    return_to = form_data.get(RETURN_TO_FIELD) or ""
    if errors:
        return None, _reschedule_failure(
            appointment, values, errors=errors,
            acknowledge_conflict=form_data.get("confirm_conflict") == "yes",
            return_to=return_to,
        ), ""

    conflicts = find_scheduling_conflicts(
        appointment["patient_id"], values["appointment_date"],
        values["appointment_time"], exclude_appointment_id=appointment["id"],
    )
    if (conflicts["slot"] or conflicts["patient_day"]) and \
            form_data.get("confirm_conflict") != "yes":
        return None, _reschedule_failure(
            appointment, values, conflicts=conflicts, acknowledge_conflict=True,
            return_to=return_to,
        ), ""

    was = _appointment_label(appointment)
    outcome = reschedule_appointment(
        appointment["id"], values["appointment_date"], values["appointment_time"]
    )

    if outcome == "moved":
        message = (
            f"{was} has been moved to {display_date(values['appointment_date'])} "
            f"at {values['appointment_time']}. It is the same appointment — the "
            "reason and any notes were kept, and it is still Scheduled."
        )
        for sentence in _conflict_sentences(conflicts):
            message += " " + sentence
        return appointment["id"], None, message
    if outcome == "unchanged":
        return None, None, (
            f"{was} is already booked for that date and time, so nothing changed."
        )
    if outcome == "arrived":
        return None, None, (
            f"{queue_display_name(appointment)} was checked in while this page was "
            "open, so that visit is under way and was not moved."
        )
    if outcome == "resolved":
        return None, None, (
            f"{was} was closed while this page was open, so it was not moved."
        )
    return None, None, "That appointment could not be found."


def _reschedule_failure(appointment, values, errors=None, conflicts=None,
                        acknowledge_conflict=False, return_to=""):
    """Rebuild the screen with the Reschedule dialog reopened on what was entered."""
    return appointment_scheduling_context(
        reschedule={
            "open": True,
            "appointment": appointment,
            "form": values,
            "errors": errors,
            "conflicts": conflicts,
            "acknowledge_conflict": acknowledge_conflict,
        },
        # Carried through the failed round so a move begun from a patient's
        # profile still lands back there when it finally saves.
        return_to=return_to,
    )


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
