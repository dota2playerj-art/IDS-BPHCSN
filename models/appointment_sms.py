"""One text message, to one patient, about one of their own appointments.

This is the individual counterpart of models/broadcasts.py, and the two are
deliberately different things rather than one thing with a switch:

    a broadcast    one message, composed by hand, sent to an audience. It
                   belongs to no patient record and says what the barangay told
                   the community.
    a confirmation one message, composed by this module, sent to the single
                   patient a booking belongs to. It belongs to that appointment
                   and says what the health center told that person about it.

What they share is the wire. Nothing here talks to Semaphore: every send goes
through utils.sms.deliver_announcement_sms(), the same call send_broadcast()
makes, so this feature is live or simulated by exactly the same decision and on
exactly the same day -- the moment SEMAPHORE_API_KEY is set, with no code change
here or there. See the activation note at the top of utils/sms.py.


IT IS SENT BY HAND, AND THAT IS THE DESIGN
------------------------------------------
Nothing in this module is called from create_appointment(), reschedule_appointment()
or close_appointment(). A booking saves; then the operator is offered a button,
and the message goes only if they press it. Two reasons, and neither is
laziness:

* A text costs money per segment and cannot be recalled. A booking corrected
  twice in a minute at the desk would send three messages automatically, two of
  them wrong, and the patient would have no way to tell which to believe.
* Half the roster is a walk-in queue. Automatic confirmation would mean texting
  people who are standing at the counter having just been told the same thing.

So the send is an act, it is attributed to whoever performed it, and it is
recorded. What is NOT claimed anywhere is that a patient was notified: only that
a message was sent, or -- while there is no API key -- recorded as simulated.


WHAT IS RECORDED, AND WHAT IS NOT
---------------------------------
appointment_sms_messages holds one row per attempt, with the exact text, the
number it was addressed to, the segment cost, and whether the gateway was live.
It has no 'Delivered' status, for the reason sms_broadcast_recipients has none:
Semaphore reports delivery through a callback URL this application does not
expose, so nothing here could ever learn that a message arrived. 'Sent' means
the gateway accepted it, which is all a POST to the messages endpoint tells you.

The recipient's name and number are copied into the row rather than joined, the
same as a broadcast recipient's: they record who was texted and on what number
at the time. A patient who later changes their number must not retroactively
change the history of what was sent to them.


THE OFFER IS MADE ONCE, BESIDE THE CONFIRMATION OF THE SAVE
-----------------------------------------------------------
build_offer() below produces what the screen renders after a booking, a move or
a cancellation: either a real send control, or -- when the patient has no usable
mobile number -- a plain statement that no message can be sent and what would
have to change for one to be. Not a disabled button: a control that looks
clickable and refuses teaches the operator the system is unreliable, and this
project's rule (utils/unavailable.py) is that a control either works or is
visibly not a control at all. Here there is genuinely nothing to click, so
nothing clickable is drawn.
"""
from database.connection import get_db
from models.appointments import (
    CANCELLED,
    OPEN_BOOKING_STATUSES,
    get_appointment_by_id,
)
from models.patients import get_patient_by_id
from models.settings import health_center_name
from utils.dates import display_date, display_timestamp, today
from utils.phone import is_valid_ph_mobile, to_local_ph_mobile
from utils.sms import (
    LIVE,
    SIMULATED,
    deliver_announcement_sms,
    gateway_configured,
    message_metrics,
)

# THE FACILITY AS IT NAMES ITSELF TO A PATIENT, AND IT IS NO LONGER A CONSTANT.
# This was HEALTH_CENTER = "Barangay Poblacion Health Center", written out here
# on the reasoning that 06_DESIGN_CONTENT_LIBRARY.md was the authority on the
# string. It is now read from the settings table through models/settings.py,
# where an administrator sets it on Screen 13 -- one value, and the same one
# every export letterhead prints, rather than the five separate copies of the
# same words this project used to hold in five files.
#
# It is still not assembled from barangay + "Health Center". The stored name is
# a name, typed as a whole, so a message cannot end up announcing a facility
# that does not exist because two fields were concatenated.
#
# READ AT COMPOSE TIME, NOT AT IMPORT. A module constant would be fixed for the
# life of the process, so a name corrected at 10am would keep going out wrong on
# every message until a restart. compose_message() asks for it per message.

# The three things worth telling one patient about one appointment.
#
# A no-show is deliberately absent, and its absence is a decision rather than an
# oversight. close_appointment() admits two closures -- Cancelled and No-show --
# and only the first is news to the patient: somebody who did not attend already
# knows they did not attend, and a text saying so would be a reprimand sent at
# the barangay's expense. Nothing is offered for that closure, which is not the
# same as offering something that refuses.
BOOKED = "booked"
RESCHEDULED = "rescheduled"
CANCELLED_EVENT = "cancelled"

EVENTS = (BOOKED, RESCHEDULED, CANCELLED_EVENT)

# What each event is called on screen, and the label its send button carries.
EVENT_LABELS = {
    BOOKED: "New appointment",
    RESCHEDULED: "Appointment moved",
    CANCELLED_EVENT: "Appointment cancelled",
}

EVENT_BUTTON_LABELS = {
    BOOKED: "Send SMS Confirmation",
    RESCHEDULED: "Send SMS Notice of Change",
    CANCELLED_EVENT: "Send SMS Cancellation Notice",
}

# Which appointment statuses each event may be composed against. Checked on the
# submit as well as when the offer is built, because a POST need not come from
# the page that offered it -- and an event claimed against the wrong status would
# text a patient that a live booking was cancelled, or that a cancelled one is
# confirmed. The message has to agree with the record it describes.
EVENT_STATUSES = {
    BOOKED: OPEN_BOOKING_STATUSES,
    RESCHEDULED: OPEN_BOOKING_STATUSES,
    CANCELLED_EVENT: (CANCELLED,),
}

# Row-level outcome, matching sms_broadcast_recipients.status exactly. There is
# no 'Delivered' member here for the same reason there is none there.
STATUS_SENT = "Sent"
STATUS_FAILED = "Failed"


# ---------------------------------------------------------------------------
# WHAT THE PATIENT ACTUALLY READS
# ---------------------------------------------------------------------------

def _appointment_when(appointment):
    """'Sep 08, 2026 at 09:00', or just the date when no time was booked.

    A walk-in converted into a record has no appointment_time, so a message
    composed from one must not invent an hour. Saying the date alone is the
    honest reading of a row that holds only a date.
    """
    when = display_date(appointment.get("appointment_date"), fallback="")
    booked_time = appointment.get("booked_time")
    return f"{when} at {booked_time}" if (when and booked_time) else when


def _service(appointment):
    """The service as a patient would recognise it, lower-cased mid-sentence."""
    return (appointment.get("appointment_type") or "appointment").strip()


def compose_message(event, patient, appointment):
    """The exact text one confirmation carries. Returns "" for an unknown event.

    Written to the plain-language standard the rest of this project's operator
    text follows, and kept inside one GSM-7 segment wherever the appointment's
    own details allow it -- 160 characters is what one message credit buys, and
    every character past it doubles or triples the cost of the same sentence. The
    caller is told the real segment count either way (see build_offer); nothing
    here truncates a message to hit a number, because a confirmation missing its
    date would be worse than a confirmation costing two credits.

    Every value in the text is read off the stored appointment, the stored
    patient and the stored settings. Nothing is passed in by the screen, so a
    message cannot state a date the record does not hold, and the facility it
    names is the one Screen 13 currently holds rather than one typed into this
    file.
    """
    center = health_center_name()
    first_name = (patient.get("first_name") or "").strip()
    greeting = f"Hi {first_name}, " if first_name else ""
    when = _appointment_when(appointment)
    service = _service(appointment)

    if event == BOOKED:
        return (
            f"{center}: {greeting}your {service} is booked for {when}. "
            "Please arrive on time. Thank you."
        )
    if event == RESCHEDULED:
        return (
            f"{center}: {greeting}your {service} has moved to {when}. "
            "Please note the new schedule. Thank you."
        )
    if event == CANCELLED_EVENT:
        return (
            f"{center}: {greeting}your {service} on {when} is cancelled. "
            "Visit the health center to book again. Thank you."
        )
    return ""


# ---------------------------------------------------------------------------
# WHETHER A MESSAGE CAN BE SENT AT ALL
# ---------------------------------------------------------------------------

def _reachable(patient):
    """(mobile in 09XX form, reason it cannot be texted). One of the two is set.

    "Reachable" is is_valid_ph_mobile() and not "has something in the column",
    which is the same funnel deliver_announcement_sms() applies before it will
    record a send. Deciding it any other way here would let the screen offer a
    button the send would then refuse -- exactly the dead control this feature
    was asked not to draw.
    """
    number = (patient.get("contact_number") or "").strip()
    if not number:
        return "", "no-number"
    if not is_valid_ph_mobile(number):
        return "", "unusable-number"
    return to_local_ph_mobile(number), ""


def _reason_sentence(problem, patient):
    """Why no message can go out, said to the person at the desk.

    Names the specific missing piece and the screen that fixes it, per the rule
    in utils/unavailable.py: "Coming soon" tells nobody what to do, and neither
    does "invalid".
    """
    name = (patient.get("full_name") or "This patient").strip()
    if problem == "no-number":
        return (
            f"No contact number on file for {name}, so no text message can be "
            "sent about this appointment. Add a mobile number through Edit "
            "Profile on their patient record."
        )
    return (
        f"The contact number on file for {name} is not a Philippine mobile "
        "number, so the messaging service cannot reach it. Correct it through "
        "Edit Profile on their patient record."
    )


def build_offer(appointment_id, event):
    """What the screen shows after a booking, a move or a cancellation.

    Returns None when there is nothing honest to offer -- an unknown event, a
    vanished appointment, or a record whose status no longer matches what the
    event claims about it. Otherwise a dict the template renders directly:

        can_send   whether a real send control is drawn at all
        reason     when it is not, the sentence saying why and what fixes it
        message    the exact text that would be sent, shown before it is
        metrics    utils.sms.message_metrics() on that text -- the real cost
        gateway_live / simulated  whether anything would leave the building

    The message is shown to the operator in full rather than summarised. A text
    to a patient cannot be recalled, so the last look at it belongs before the
    button, not in the history afterwards.
    """
    if event not in EVENTS:
        return None

    appointment = get_appointment_by_id(appointment_id)
    if appointment is None:
        return None
    if appointment.get("status") not in EVENT_STATUSES[event]:
        return None

    patient = get_patient_by_id(appointment["patient_id"])
    if patient is None:
        return None

    mobile, problem = _reachable(patient)
    message = compose_message(event, patient, appointment)
    live = gateway_configured()

    return {
        "event": event,
        "event_label": EVENT_LABELS[event],
        "button_label": EVENT_BUTTON_LABELS[event],
        "appointment_id": appointment["id"],
        "appointment_reference": appointment["reference"],
        "appointment_when": _appointment_when(appointment),
        "appointment_type": _service(appointment),
        "patient_id": patient["id"],
        "patient_name": patient.get("full_name") or "",
        "patient_reference": patient.get("patient_id") or "",
        "mobile": mobile,
        "can_send": bool(mobile and message),
        "reason": _reason_sentence(problem, patient) if problem else "",
        "message": message,
        "metrics": message_metrics(message),
        "gateway_live": live,
        "simulated": not live,
    }


# ---------------------------------------------------------------------------
# SENDING AND HISTORY
# ---------------------------------------------------------------------------

def generate_next_reference(conn=None):
    """Next free APT-SMS-YYYY-NNNN reference for the current clinic year.

    Reads the highest number already issued this year rather than counting rows,
    so a deleted message cannot cause a UNIQUE collision -- the same reasoning as
    models/broadcasts.py generate_next_reference() and generate_next_patient_id().
    """
    owns_connection = conn is None
    conn = conn or get_db()
    year = today().year
    rows = conn.execute(
        "SELECT reference FROM appointment_sms_messages WHERE reference LIKE ?",
        (f"APT-SMS-{year}-%",),
    ).fetchall()
    if owns_connection:
        conn.close()

    highest = 0
    for row in rows:
        suffix = str(row["reference"]).rsplit("-", 1)[-1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"APT-SMS-{year}-{highest + 1:04d}"


def send_appointment_sms(appointment_id, event, sent_by):
    """Send one confirmation and record it. Returns (record, error sentence).

    Exactly one of the two is set. The record is the stored row read back, so
    everything the caller then reports -- the reference, the number, the mode --
    is what was written rather than what was intended.

    The offer is rebuilt here from the database rather than trusted from the
    form, so a submit that arrived without the page, or after the appointment
    changed underneath it, is judged on the record as it stands now.
    """
    offer = build_offer(appointment_id, event)
    if offer is None:
        return None, (
            "That appointment could not be found, or it is no longer in the state "
            "this message describes, so nothing was sent."
        )
    if not offer["can_send"]:
        return None, offer["reason"] + " Nothing was sent."

    outcome = deliver_announcement_sms(offer["message"], offer["mobile"])
    metrics = offer["metrics"]

    conn = get_db()
    reference = generate_next_reference(conn)
    cursor = conn.execute(
        """
        INSERT INTO appointment_sms_messages
            (reference, appointment_id, patient_id, event, recipient_name,
             mobile_number, message, segments, encoding, status, delivery_mode,
             gateway_response, sent_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reference,
            offer["appointment_id"],
            offer["patient_id"],
            event,
            offer["patient_name"],
            offer["mobile"],
            offer["message"],
            metrics["segments"],
            metrics["encoding"],
            STATUS_SENT if outcome["status"] == "sent" else STATUS_FAILED,
            outcome["mode"],
            outcome.get("response") or outcome.get("error"),
            sent_by,
        ),
    )
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return get_appointment_sms_by_id(message_id), ""


def _to_message(row):
    """A stored row plus the fields the screens render."""
    record = dict(row)
    record["event_label"] = EVENT_LABELS.get(record.get("event"), record.get("event"))
    record["is_simulated"] = record.get("delivery_mode") == SIMULATED
    record["is_live"] = record.get("delivery_mode") == LIVE
    record["status_badge_class"] = (
        "badge-sent" if record.get("status") == STATUS_SENT else "badge-failed"
    )
    # sent_at is stored as UTC by CURRENT_TIMESTAMP; the screens show clinic time.
    record["sent_at_display"] = display_timestamp(record.get("sent_at"))
    return record


_HISTORY_SELECT = """
    SELECT m.*, u.full_name AS sent_by_name, u.role AS sent_by_role,
           p.patient_id AS patient_reference
    FROM appointment_sms_messages m
    JOIN users u ON u.id = m.sent_by
    LEFT JOIN patients p ON p.id = m.patient_id
"""


def get_appointment_sms_by_id(message_id):
    conn = get_db()
    row = conn.execute(_HISTORY_SELECT + " WHERE m.id = ?", (message_id,)).fetchone()
    conn.close()
    return _to_message(row) if row else None


def get_appointment_sms_history(limit=25):
    """Individual confirmations, newest first, with the sender's name resolved."""
    conn = get_db()
    rows = conn.execute(
        _HISTORY_SELECT + " ORDER BY m.sent_at DESC, m.id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_to_message(row) for row in rows]


def get_appointment_sms_stats(history=None):
    """The figures the history panel prints above its table.

    Counted from stored rows only. There is no delivery figure here for the
    reason get_broadcast_stats() gives: nothing in this system is ever told that
    a message arrived.
    """
    if history is None:
        history = get_appointment_sms_history(limit=1000)
    return {
        "total": len(history),
        "sent": sum(1 for record in history if record["status"] == STATUS_SENT),
        "failed": sum(1 for record in history if record["status"] == STATUS_FAILED),
        "simulated": sum(1 for record in history if record["is_simulated"]),
        "live": sum(1 for record in history if record["is_live"]),
    }
