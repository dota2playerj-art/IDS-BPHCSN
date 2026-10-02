"""Visits waiting for the Doctor (Task 6, M4; Task 6b).

At a barangay health station the Doctor comes only on certain days. Staff take the
intake every day, so a visit that needs a diagnosis can wait days for the Doctor.
This module answers one question: which visits are waiting for the Doctor? It is the
one place that decides it. The Doctor's dashboard lists them, the Staff dashboard and
the Administrator's dashboard show the count, and all three call the functions below,
so they cannot disagree.
"""
from datetime import datetime

from database.connection import db_connection
from utils.dates import now, today

# The queue status a visit holds from the moment its intake is saved until the Doctor
# writes the diagnosis.
WAITING_FOR_DOCTOR = "Waiting for the Doctor"

# THE SERVICES STAFF CHOOSE FROM WHEN THEY CHECK A PATIENT IN (Task 6b, D1).
#
# One fixed list, a required choice with no default. It is built from the services
# the code and the reports already name: Prenatal Check-up and Immunization are
# counted in Reports & Analytics, and the retired booking list held Consultation,
# Follow-up Consultation, DM / Hypertension Monitoring and Dental. Labels are plain.
VISIT_SERVICES = (
    "Consultation",
    "Follow-up Consultation",
    "Hypertension / Diabetes Monitoring",
    "Prenatal Check-up",
    "Immunization",
    "Dental",
)

# The services whose visits need a diagnosis from the Doctor: a subset of
# VISIT_SERVICES. Prenatal Check-up and Immunization are done by midwives and health
# workers, and Dental is a dentist's service, so they are not here.
#
# "Walk-in Consultation" is what every visit was called before the service was
# chosen at check-in. Old rows still carry it, and it needs the Doctor like a
# Consultation. It is not offered for a new visit. A visit with no service is treated
# as a consultation.
SERVICES_NEEDING_DOCTOR = (
    "Consultation",
    "Follow-up Consultation",
    "Hypertension / Diabetes Monitoring",
    "Walk-in Consultation",
)

_FROM_SQL = """
    FROM appointments a
    LEFT JOIN consultations c ON c.appointment_id = a.id
"""
_WHERE_SQL = " WHERE a.status = '" + WAITING_FOR_DOCTOR + "'"


def needs_doctor(appointment_type):
    """Whether a visit of this service needs a diagnosis. A blank type does."""
    kind = (appointment_type or "").strip()
    return not kind or kind in SERVICES_NEEDING_DOCTOR


def clean_service(value):
    """The chosen service if it is in VISIT_SERVICES, else None. No default."""
    value = (value or "").strip()
    return value if value in VISIT_SERVICES else None


def has_diagnosis(diagnosis):
    """The one definition of "has a diagnosis": the stored text is not blank."""
    return bool((diagnosis or "").strip())


def count_waiting_for_doctor():
    """How many visits are waiting for the Doctor. Reads no name and no text."""
    with db_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM appointments a" + _WHERE_SQL).fetchone()[0]


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
    from_earlier_day, status, consultation_id (None when Staff did no intake), and
    `action`: always "see_patient" (Task 6d). One button for every visit, with or without an
    intake record: it opens the record when there is one, a new consultation when not.

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
        since = _checked_in(row)
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
            "action": "see_patient",
        })
    visits.sort(key=lambda v: (v["checked_in"] or datetime.max, v["id"]))
    return visits
