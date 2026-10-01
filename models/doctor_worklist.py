"""Visits waiting for the Doctor (Task 6, M4).

At a barangay health station the Doctor comes only on certain days. Staff take the
intake every day, so a visit that needs a diagnosis can wait days for the Doctor.
This module answers one question: which visits need a diagnosis and do not have one
yet? It is the one place that decides it. The Doctor's dashboard lists them, the
Staff dashboard and the Administrator's dashboard show the count, and all three call
the functions below, so they cannot disagree.

WHAT "WAITING FOR THE DOCTOR" MEANS
-----------------------------------
A visit is on the list when ALL of these are true:

* its queue status is Waiting, In Consultation or Completed. (Cancelled, No-show and
  "Left before being seen" are over. Scheduled and Confirmed have not arrived.)
* it has no diagnosis. "Has a diagnosis" is decided here: the consultation's
  `diagnosis` is not blank. A sealed diagnosis is stored encrypted, which is not
  blank, so a sealed visit counts as diagnosed.
* if it is Completed, it has a consultation. Saving the intake form completes the
  queue entry, so a Completed visit with intake and no diagnosis is exactly the case
  this list exists for. A visit closed with nothing written at all is not a visit
  waiting for a diagnosis, and is not listed.
* its service needs the Doctor (SERVICES_NEEDING_DOCTOR).

ACROSS ALL DAYS. A visit from three days ago is on the list until it has a diagnosis
or is marked "Left before being seen".

THE COUNT NEVER READS A NAME. count_waiting_for_doctor() selects ids and the service
only, so the Administrator's dashboard is built without any patient's name.

NO SEALED TEXT. Nothing here reads a complaint, a check-in reason or any consultation
text. A row carries the name, the patient ID, the service and the times.
"""
from datetime import datetime

from database.connection import db_connection
from utils.dates import now, today

# The services (appointment_type) whose visits need a diagnosis from the Doctor.
#
# Consultations and clinical follow-ups need one. Prenatal Check-up and Immunization
# are done by midwives and health workers, and Dental is a dentist's service, so they
# are not here and are never listed.
#
# TODAY EVERY NEW VISIT IS A "Walk-in Consultation": the service is the typed check-in
# reason and is not stored as a type. So in practice every visit without a diagnosis is
# on the list, and this constant separates services only when a visit carries one of
# the other types. A visit with no type is treated as a consultation.
SERVICES_NEEDING_DOCTOR = (
    "Walk-in Consultation",
    "Consultation",
    "Follow-up Consultation",
    "DM / Hypertension Monitoring",
)

# The queue statuses a visit can be in while it still needs a diagnosis.
_OPEN_STATUSES = ("Waiting", "In Consultation", "Completed")

_FROM_SQL = """
    FROM appointments a
    LEFT JOIN consultations c ON c.appointment_id = a.id
"""
_WHERE_SQL = """
    WHERE a.status IN ('Waiting', 'In Consultation', 'Completed')
      AND (c.id IS NULL OR TRIM(COALESCE(c.diagnosis, '')) = '')
      AND (a.status != 'Completed' OR c.id IS NOT NULL)
"""


def needs_doctor(appointment_type):
    """Whether a visit of this service needs a diagnosis. A blank type does."""
    kind = (appointment_type or "").strip()
    return not kind or kind in SERVICES_NEEDING_DOCTOR


def has_diagnosis(diagnosis):
    """The one definition of "has a diagnosis": the stored text is not blank."""
    return bool((diagnosis or "").strip())


def count_waiting_for_doctor():
    """How many visits are waiting for the Doctor. Reads no name and no text."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT a.id, a.appointment_type " + _FROM_SQL + _WHERE_SQL).fetchall()
    return sum(1 for row in rows if needs_doctor(row["appointment_type"]))


def _checked_in(row):
    """When the patient arrived, as a naive clinic-local datetime."""
    for value in (row["checked_in_at"], row["appointment_date"]):
        text = (value or "").strip()
        for pattern, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
            try:
                return datetime.strptime(text[:size], pattern)
            except ValueError:
                continue
    return None


def waiting_text(since, moment=None):
    """How long, in plain words: '5 minutes', '3 hours', '1 day', '2 days'."""
    if since is None:
        return ""
    moment = moment or now().replace(tzinfo=None)
    minutes = max(0, int((moment - since).total_seconds() // 60))
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes} minute{'' if minutes == 1 else 's'}"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'' if hours == 1 else 's'}"
    days = hours // 24
    return f"{days} day{'' if days == 1 else 's'}"


def get_waiting_for_doctor():
    """The visits waiting for the Doctor, oldest first, across all days.

    Each row: id, reference (APT-00081), patient_id, patient_reference (PAT-005),
    name, service, checked_in (a datetime), appointment_date, waiting (plain text),
    from_earlier_day, status, consultation_id, and `action`: where the button goes.

    * "edit"   the intake exists: open it to write the diagnosis
    * "record" the patient is In Consultation and nothing is recorded yet
    * "queue"  still Waiting: the visit has to be started from the Patient Queue

    For the Doctor only. The dashboard builder calls this for the Doctor and
    count_waiting_for_doctor() for everyone else.
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT a.id, a.patient_id, a.appointment_type, a.appointment_date,
               a.checked_in_at, a.status, c.id AS consultation_id,
               p.patient_id AS patient_reference, p.first_name, p.last_name
        """ + _FROM_SQL + " JOIN patients p ON p.id = a.patient_id " + _WHERE_SQL
        ).fetchall()

    moment = now().replace(tzinfo=None)
    day = today().isoformat()
    visits = []
    for row in rows:
        if not needs_doctor(row["appointment_type"]):
            continue
        since = _checked_in(row)
        if row["consultation_id"]:
            action = "edit"
        elif row["status"] == "In Consultation":
            action = "record"
        else:
            action = "queue"
        visits.append({
            "id": row["id"],
            "reference": f"APT-{row['id']:05d}",
            "patient_id": row["patient_id"],
            "patient_reference": row["patient_reference"],
            "name": f"{row['first_name']} {row['last_name']}".strip(),
            "service": (row["appointment_type"] or "").strip() or "Consultation",
            "checked_in": since,
            "appointment_date": (row["appointment_date"] or "")[:10],
            "waiting": waiting_text(since, moment),
            "from_earlier_day": (row["appointment_date"] or "")[:10] < day,
            "status": row["status"],
            "consultation_id": row["consultation_id"],
            "action": action,
        })
    visits.sort(key=lambda v: (v["checked_in"] or datetime.max, v["id"]))
    return visits
