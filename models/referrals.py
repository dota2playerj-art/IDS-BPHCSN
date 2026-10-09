"""Referring a patient to the RHU or a hospital (Task 18, D1 and D2).

"Referred" is a visit outcome, like "Left before being seen". Staff and the Doctor set it on a
visit that is Waiting, In Consultation or Waiting for the Doctor, and undo it the same day. The
rules are in SQL here, so a stale page or a forged POST gets the same answer as the button; who
may do it is the status x role mapping in models/queue_actions.py.

The reason is clinical free text: care team only, encrypted while the visit is sealed (the seal
in models/consultations.py covers it), never in an audit entry, an export or a count. The
Administrator sees the status only: no queue query selects the destination or the reason.

The RHU doctor visits barangay health centers on no fixed day, so a patient the health center
cannot handle is referred to the RHU on any day; the RHU refers hospital cases to Caraga
Regional Hospital in Surigao City.
"""
from database.connection import db_connection
from models.doctor_worklist import has_diagnosis
from models.queue_actions import REFER, REFERRED, statuses_allowing
from utils import sealed_crypto
from utils.dates import now, today

# THE ONE LIST OF DESTINATIONS. The form offers exactly these, the server accepts exactly
# these, and the reports break the referrals down by them.
RHU = "Rural Health Unit (RHU)"
CARAGA = "Caraga Regional Hospital"
OTHER = "Other hospital or facility"
REFERRAL_DESTINATIONS = (RHU, CARAGA, OTHER)

# How a destination reads inside a sentence of the audit trail. The facility's typed name
# is not written there (a facility's name can itself say what a patient has); the list entry is.
DESTINATION_PHRASE = {
    RHU: "the RHU",
    CARAGA: "Caraga Regional Hospital",
    OTHER: "another hospital or facility",
}

FACILITY_MAX_LENGTH = 80
REASON_MAX_LENGTH = 500

REFERRABLE_STATUSES = statuses_allowing(REFER)

# What a sealed field prints as on the referral slip.
SLIP_CONFIDENTIAL = "Confidential — discuss directly with the receiving doctor."

REASON_FIELD = "referral_reason"
REASON_TABLE = "appointments"


def clean_destination(value):
    """The chosen destination if it is in REFERRAL_DESTINATIONS, else None."""
    value = (value or "").strip()
    return value if value in REFERRAL_DESTINATIONS else None


def extract_form(form_data):
    """What was submitted, trimmed and with runs of spaces folded in the facility name."""
    return {
        "destination": (form_data.get("destination") or "").strip(),
        "facility": " ".join((form_data.get("facility") or "").split()),
        "reason": (form_data.get("reason") or "").strip(),
    }


def validate_referral(values):
    """{field: message} for a referral form. Empty means valid. Server-side, plain words."""
    errors = {}
    destination = clean_destination(values.get("destination"))
    if destination is None:
        errors["destination"] = "Choose where the patient is referred to."
    facility = values.get("facility") or ""
    if destination == OTHER and not facility:
        errors["facility"] = "Write the name of the hospital or facility."
    if len(facility) > FACILITY_MAX_LENGTH:
        errors["facility"] = f"Use {FACILITY_MAX_LENGTH} characters or fewer for the name."
    if len(values.get("reason") or "") > REASON_MAX_LENGTH:
        errors["reason"] = f"Use {REASON_MAX_LENGTH} characters or fewer for the reason."
    return errors


def referral_allowed(status, diagnosis=None):
    """Whether a visit in this state may be referred.

    Waiting, In Consultation and Waiting for the Doctor, and never one that has a diagnosis.
    A Completed visit is finished and cannot be referred.
    """
    return status in REFERRABLE_STATUSES and not has_diagnosis(diagnosis)


def _row(conn, appointment_id):
    return conn.execute(
        """
    SELECT a.id, a.status, a.appointment_date, a.referred_at, a.status_before_referred,
           c.id AS consultation_id, c.diagnosis, COALESCE(c.is_restricted, 0) AS is_sealed
      FROM appointments a
      LEFT JOIN consultations c ON c.appointment_id = a.id
     WHERE a.id = ?
    """,
        (appointment_id,),
    ).fetchone()


def refer_visit(appointment_id, user_id, destination, facility="", reason="", audit=None):
    """Refer one visit. Returns the outcome:

        "referred"      done; who and when are stored
        "already"       it is already referred
        "invalid"       the destination is not in the list, or "Other" has no facility name
        "not-allowed"   it has a diagnosis, is finished, is not in the queue, or is an
                        earlier day's Waiting visit
        "cannot-seal"   the visit is sealed and the key on this computer cannot encrypt
        "missing"       no such appointment

    The reason is encrypted when the visit is sealed. `audit(conn)` is called before the
    commit, only when the visit was referred.
    """
    chosen = clean_destination(destination)
    facility = " ".join((facility or "").split())
    reason = (reason or "").strip()
    if validate_referral({"destination": chosen or "", "facility": facility, "reason": reason}):
        return "invalid"
    if chosen != OTHER:
        facility = ""
    stamp = now().strftime("%Y-%m-%d %H:%M:%S")
    with db_connection() as conn:
        row = _row(conn, appointment_id)
        if row is None:
            return "missing"
        if row["status"] == REFERRED:
            return "already"
        if not referral_allowed(row["status"], row["diagnosis"]):
            return "not-allowed"
        # An earlier day's Waiting visit offers only Left before being seen (the day rule).
        if row["status"] == "Waiting" and (row["appointment_date"] or "")[:10] != today().isoformat():
            return "not-allowed"
        stored = reason or None
        if stored and row["is_sealed"]:
            try:
                stored = sealed_crypto.encrypt(stored, appointment_id, REASON_FIELD, REASON_TABLE)
            except sealed_crypto.SealedDataError:
                return "cannot-seal"
        # The guard is repeated in the UPDATE, so a diagnosis written a moment ago, or a status
        # that moved, loses the race instead of being overwritten.
        cursor = conn.execute(
            """
        UPDATE appointments
           SET status_before_referred = status, status = ?, referral_destination = ?,
               referral_facility = ?, referral_reason = ?, referred_by = ?, referred_at = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status = ?
           AND NOT EXISTS (
                 SELECT 1 FROM consultations c
                  WHERE c.appointment_id = appointments.id
                    AND TRIM(COALESCE(c.diagnosis, '')) != ''
               )
        """,
            (REFERRED, chosen, facility or None, stored, user_id, stamp,
             appointment_id, row["status"]),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return "not-allowed"
        if audit:
            audit(conn, chosen)
        conn.commit()
    return "referred"


def undo_referral(appointment_id, audit=None):
    """Put a referred visit back to the status it had. Returns the outcome:

        "undone"       done; the destination, facility, reason, who and when are cleared
        "not-referred" it is not referred
        "too-late"     it was referred on an earlier day; it stays referred
        "busy"         it was In Consultation and someone else is in the room now
        "missing"      no such appointment

    `audit(conn)` is called before the commit, only when it was undone.
    """
    with db_connection() as conn:
        row = _row(conn, appointment_id)
        if row is None:
            return "missing"
        if row["status"] != REFERRED:
            return "not-referred"
        if (row["referred_at"] or "")[:10] != today().isoformat():
            return "too-late"
        before = row["status_before_referred"]
        if before not in REFERRABLE_STATUSES:
            return "not-referred"
        cursor = conn.execute(
            """
        UPDATE appointments
           SET status = status_before_referred, status_before_referred = NULL,
               referral_destination = NULL, referral_facility = NULL, referral_reason = NULL,
               referred_by = NULL, referred_at = NULL, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status = ?
           AND (status_before_referred != 'In Consultation'
                OR NOT EXISTS (SELECT 1 FROM appointments busy WHERE busy.status = 'In Consultation'))
        """,
            (appointment_id, REFERRED),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return "busy"
        if audit:
            audit(conn)
        conn.commit()
    return "undone"


def attach_referrals(entries, viewer_role):
    """Add `referral_destination` and `referral_facility` to queue rows.

    The care team gets the destination of a referred visit; every other role gets None, so the
    Administrator's queue shows the status only. The reason is never added here.
    """
    from utils.roles import is_care_team

    entries = list(entries)
    found = {}
    ids = [entry["id"] for entry in entries if entry.get("status") == REFERRED]
    if ids and is_care_team(viewer_role):
        marks = ", ".join("?" for _ in ids)
        with db_connection() as conn:
            found = {
                row["id"]: row
                for row in conn.execute(
                    "SELECT id, referral_destination, referral_facility "
                    f"FROM appointments WHERE id IN ({marks})", ids)
            }
    for entry in entries:
        row = found.get(entry["id"])
        entry["referral_destination"] = row["referral_destination"] if row else None
        entry["referral_facility"] = row["referral_facility"] if row else None
    return entries


def destination_text(destination, facility=None):
    """'Caraga Regional Hospital', or 'Other hospital or facility: <name>'."""
    if destination == OTHER and facility:
        return f"{OTHER}: {facility}"
    return destination or ""


def get_referral_slip(appointment_id):
    """Everything the referral slip prints for one referred visit, or None.

    The sealed fields are never decrypted here: the slip leaves the building, so for a sealed
    visit the chief complaint and the reason are the SLIP_CONFIDENTIAL line, whoever prints it.
    Vitals are not sealed fields and print as recorded. For the care team's route only; the
    Administrator has no route to it.
    """
    from models.patients import format_age

    with db_connection() as conn:
        row = conn.execute(
            """
        SELECT a.id, a.status, a.appointment_date, a.referral_destination, a.referral_facility,
               a.referral_reason, a.referred_at, p.patient_id AS patient_reference,
               p.first_name, p.middle_name, p.last_name, p.sex, p.birth_date,
               u.full_name AS referred_by_name
          FROM appointments a
          JOIN patients p ON p.id = a.patient_id
          LEFT JOIN users u ON u.id = a.referred_by
         WHERE a.id = ?
        """,
            (appointment_id,),
        ).fetchone()
        if row is None or row["status"] != REFERRED:
            return None
        intake = conn.execute(
            """
        SELECT chief_complaint, temperature, blood_pressure, pulse_rate, respiratory_rate,
               weight, height, head_circumference, is_restricted
          FROM consultations WHERE appointment_id = ? ORDER BY id LIMIT 1
        """,
            (appointment_id,),
        ).fetchone()

    sealed = bool(intake and intake["is_restricted"]) or sealed_crypto.is_encrypted(
        row["referral_reason"])
    vitals = []
    if intake:
        for label, key, unit in (
            ("Temperature", "temperature", "°C"), ("Blood pressure", "blood_pressure", "mmHg"),
            ("Pulse", "pulse_rate", "/min"), ("Breathing", "respiratory_rate", "/min"),
            ("Weight", "weight", "kg"), ("Height", "height", "cm"),
            ("Head size", "head_circumference", "cm"),
        ):
            value = intake[key]
            if value is not None and str(value).strip() != "":
                vitals.append({"label": label, "value": f"{value:g}" if isinstance(value, float)
                               else str(value), "unit": unit})
    complaint = (intake["chief_complaint"] or "").strip() if intake else ""
    reason = (row["referral_reason"] or "").strip()
    name = " ".join(part for part in (row["first_name"], row["middle_name"], row["last_name"])
                    if part)
    referred_at = (row["referred_at"] or "")[:16]
    return {
        "reference": f"APT-{row['id']:05d}",
        "patient_name": name,
        "patient_reference": row["patient_reference"],
        "age": format_age(row["birth_date"]) or "",
        "sex": row["sex"] or "",
        "destination": destination_text(row["referral_destination"], row["referral_facility"]),
        "referred_on": referred_at[:10],
        "referred_time": referred_at[11:16],
        "referred_by": row["referred_by_name"] or "",
        "vitals": vitals,
        "has_intake": intake is not None,
        "sealed": sealed,
        "complaint": SLIP_CONFIDENTIAL if (sealed and complaint) else complaint,
        "reason": SLIP_CONFIDENTIAL if (sealed and reason) else reason,
    }


def count_by_destination(conn, start, end):
    """{destination: how many} for visits Referred and dated start..end (ISO dates)."""
    counts = {destination: 0 for destination in REFERRAL_DESTINATIONS}
    for row in conn.execute(
        "SELECT referral_destination AS destination, COUNT(*) AS n FROM appointments "
        "WHERE status = ? AND substr(appointment_date, 1, 10) BETWEEN ? AND ? "
        "GROUP BY referral_destination", (REFERRED, start, end)):
        counts[row["destination"] if row["destination"] in counts else OTHER] += row["n"]
    return counts
