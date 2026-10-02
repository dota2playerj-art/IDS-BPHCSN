"""One text message, to one patient, about one of their own appointments."""
from database.connection import db_connection
from utils.dates import display_timestamp
from utils.phone import mask_phone
from utils.sms import LIVE, SIMULATED

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

# The three things this system used to tell one patient about one appointment.
# Nothing composes them now; they survive because EVENT_LABELS below turns the
# stored `event` column into the words the history panel prints.
#
# A no-show was deliberately absent, and the absence was a decision rather than
# an oversight: somebody who did not attend already knows they did not attend,
# and a text saying so would have been a reprimand sent at the barangay's
# expense. No stored row carries one, which is why there is no label for it.
BOOKED = "booked"
RESCHEDULED = "rescheduled"
CANCELLED_EVENT = "cancelled"

# What each event is called on screen.
EVENT_LABELS = {
    BOOKED: "New appointment",
    RESCHEDULED: "Appointment moved",
    CANCELLED_EVENT: "Appointment cancelled",
}


# Row-level outcome, matching sms_broadcast_recipients.status exactly. There is
# no 'Delivered' member here for the same reason there is none there.
STATUS_SENT = "Sent"
STATUS_FAILED = "Failed"


# ---------------------------------------------------------------------------
# WHAT THE PATIENT ACTUALLY READS
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# WHETHER A MESSAGE CAN BE SENT AT ALL
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SENDING AND HISTORY
# ---------------------------------------------------------------------------

def _to_message(row):
    """A stored row plus the fields the screens render."""
    record = dict(row)
    # Masked for every role (Task 5d, D3). The stored row keeps the full number.
    record["mobile_number"] = mask_phone(record.get("mobile_number"))
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
    with db_connection() as conn:
        row = conn.execute(_HISTORY_SELECT + " WHERE m.id = ?", (message_id,)).fetchone()
    return _to_message(row) if row else None


def get_appointment_sms_history(limit=25):
    """Individual confirmations, newest first, with the sender's name resolved."""
    with db_connection() as conn:
        rows = conn.execute(
            _HISTORY_SELECT + " ORDER BY m.sent_at DESC, m.id DESC LIMIT ?", (limit,)
        ).fetchall()
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
