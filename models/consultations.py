"""Consultation record queries -- what happened during a visit.

A consultation is the clinical write-up of one appointment: what the patient came
in with, what was measured, what it was judged to be, and what was done about it.
The queue (models/appointments.py) tracks a patient through the building; this
tracks what the health worker recorded once they were in the room.
"""
from datetime import datetime

from database.connection import db_connection
from models.patients import calculate_age, format_age
from utils import sealed_crypto
from utils.dates import recent_months, resolve_range, today
from utils.roles import holds_clinical_authority
from utils.small_counts import fold_small_counts, shown_count

# Growth monitoring cohort -- DOH Operation Timbang Plus / WHO 0-59 months.
PEDIATRIC_AGE_YEARS = 5
# Head circumference is an infant measurement; matches format_age()'s boundary.
INFANT_AGE_YEARS = 1

# WHERE IMMUNISATIONS ATTACH, AND WHY HERE
#
# The DOH EPI schedule is tracked in models/immunizations.py and recorded from
# the paediatric section of this module's form. Everything an EPI schedule needs
# is already resolved by the time that section renders: the patient, their age
# (consultation_age_context), the visit date and the health worker. A dose is
# administered *during* a consultation, so it belongs as a further section of
# this same record -- not as a parallel screen that would have to rediscover all
# four for itself and could then disagree with this one about any of them.
#
# get_immunization_status() reads PEDIATRIC_AGE_YEARS from here rather than
# defining its own boundary, so the growth measurements and the immunisation
# schedule are offered to exactly the same children.

# Every column the Record Consultation form writes, in one place so the INSERT,
# the UPDATE and the redisplay cannot fall out of step. patient_id, recorded_by,
# appointment_id, consultation_date and created_at are absent on purpose: they
# are set once, when the record is created, and an edit must not move them.
CLINICAL_TEXT_FIELDS = ("chief_complaint", "diagnosis", "treatment_plan", "remarks")
VITAL_FIELDS = ("temperature", "blood_pressure", "pulse_rate", "respiratory_rate", "weight")
GROWTH_FIELDS = ("height", "head_circumference")
CONSULTATION_FIELDS = (
    *CLINICAL_TEXT_FIELDS, *VITAL_FIELDS, *GROWTH_FIELDS, "follow_up_date",
)

# What the operator must fill in. The clinical judgement is the point of the
# record, so those three are required.
#
# The vitals are deliberately NOT required. A barangay health station does not
# always have a working thermometer, and paediatric BP cuffs are frequently
# absent; a form that refuses to save without a number teaches staff to type one
# in. A blank that means "not measured" is worth more than a plausible invention,
# so each vital is optional but strictly range-checked when it is given.
REQUIRED_FIELDS = {
    "chief_complaint": "Chief complaint is required — what the patient came in for.",
    "diagnosis": "Diagnosis is required.",
    "treatment_plan": "Treatment plan is required — including any medicines given.",
}

# (field, label, unit, low, high, whole_number). The ranges are wide on purpose:
# they exist to catch a slipped decimal point or a transposed digit, not to
# second-guess a clinician. Anything genuinely outside them is a typo.
NUMERIC_LIMITS = (
    ("temperature", "Temperature", "°C", 25.0, 45.0, False),
    ("pulse_rate", "Pulse rate", "bpm", 20, 250, True),
    ("respiratory_rate", "Respiratory rate", "breaths/min", 5, 100, True),
    ("weight", "Weight", "kg", 0.5, 400.0, False),
    ("height", "Height", "cm", 20.0, 250.0, False),
    ("head_circumference", "Head circumference", "cm", 20.0, 70.0, False),
)
_LIMITS_BY_FIELD = {entry[0]: entry for entry in NUMERIC_LIMITS}

# Blood pressure is read as one value and validated as two halves.
BP_SYSTOLIC_RANGE = (50, 300)
BP_DIASTOLIC_RANGE = (20, 200)

# Human labels, in display order. Used by the profile screen, the form, and the
# audit trail -- so a field is called the same thing wherever it is named.
FIELD_LABELS = {
    "chief_complaint": "Chief complaint",
    "temperature": "Temperature",
    "blood_pressure": "Blood pressure",
    "pulse_rate": "Pulse rate",
    "respiratory_rate": "Respiratory rate",
    "weight": "Weight",
    "height": "Height",
    "head_circumference": "Head circumference",
    "diagnosis": "Diagnosis",
    "treatment_plan": "Treatment plan / medicines given",
    "remarks": "Additional notes",
    "follow_up_date": "Follow-up date",
}

MISSING_TEXT = "Not recorded"

# ---------------------------------------------------------------------------
# CLINICAL AUTHORITY AND THE CONFIDENTIALITY SEAL
#
# THE TWO FIELDS ONLY A LICENSED CLINICIAN MAY WRITE.
# Diagnosing a patient and deciding their treatment is a licensed act. Health
# Center Staff and Barangay Health Workers take the intake -- the complaint, the
# vitals, the growth measurements -- give the vaccinations and hand over the
# medicine the doctor prescribed; they do not decide what the patient has, and
# neither does the Administrator, who is a barangay Kagawad running the system
# rather than a physician. These two fields are the Doctor's.
#
# This tuple is the single authority on that, in the same way
# allowed_growth_fields() is the single authority on which measurements an age
# admits. The form renders these fields only for a role that may write them, the
# validator stops requiring them of a role that may not, and
# routes/consultation_views.py drops them from any submission by such a role --
# so a POST that never touched the page cannot put a diagnosis on a record.
DOCTOR_ONLY_FIELDS = ("diagnosis", "treatment_plan")

# THE FREE TEXT THAT IS SEALED WITH THEM (Task 5b, D1).
# These two are the intake: Health Center Staff write them on an unsealed record,
# so they are not Doctor-only to WRITE. Once the Doctor seals the visit they are
# stored encrypted and read only by the Doctor, like the two above. A save by any
# other role on a sealed record keeps them exactly as stored.
SEALED_WITH_RECORD_FIELDS = ("chief_complaint", "remarks")

# Every consultation column that is encrypted while the record is sealed. This
# tuple, and nothing else, decides what the seal encrypts, opens and redacts.
SEALED_FIELDS = DOCTOR_ONLY_FIELDS + SEALED_WITH_RECORD_FIELDS

# The check-in reason lives on the linked queue visit: appointments.notes. It is
# encrypted with the record and bound to the appointments row, not to the
# consultation. See _seal_visit_reason().
VISIT_REASON_TABLE = "appointments"
VISIT_REASON_FIELD = "notes"

# WHAT A SEALED ENTRY SHOWS INSTEAD, AND WHY IT SHOWS ANYTHING AT ALL.
# A withheld field is never silently blanked and never quietly dropped from the
# page. A health worker who opens a record and finds an empty Diagnosis cell has
# been told something false -- that nothing was written -- and the next thing
# they do is write one, or ask the patient a question the record already answers.
# The placeholder says the field exists, holds something, and is not theirs to
# read. That is the whole of the honest answer, and it is the same principle
# utils/unavailable.py applies to every deliberately disabled control here.
#
# It names the role that CAN read it rather than the reason it is sealed. The
# reason would be the disclosure: "Restricted — HIV" protects nothing.
RESTRICTED_PLACEHOLDER = "Restricted — Doctor access only"


def can_diagnose(role):
    """Whether this role may enter a diagnosis and a treatment plan.

    The Doctor is the licensed clinician and is the only role that may. The
    Administrator and Health Center Staff both reach the consultation form and
    both record the intake on it; neither writes these two fields. A Barangay
    Official reaches no consultation screen at all.

    It was the Administrator's until the RHU's field data showed the
    Administrator is a Kagawad, not the doctor. The answer now comes from
    utils.roles.holds_clinical_authority(), the one definition every clinical
    permission in this system shares.

    Asked of the SIGNED-IN ACCOUNT'S stored role, never of anything a request
    carried. That is what makes it a permission rather than a preference -- see
    routes/consultation_views.py, where the answer comes from
    utils.security.current_role() and cannot be reached by a form field.
    """
    return holds_clinical_authority(role)


def can_view_restricted(role):
    """Whether this role may read a consultation the clinician has sealed.

    Deliberately the same answer as can_diagnose(), and deliberately a separate
    function rather than the same one called twice. They are one rule read from
    each end: the seal withholds the free text of the visit (SEALED_FIELDS), which
    includes the fields DOCTOR_ONLY_FIELDS names, so the role that may write
    those is the role that may read them all back once sealed.
    Written as a delegation so that stays true by construction -- if the write
    rule ever moves, the read rule moves with it rather than being a second copy
    that quietly disagrees.

    So the Administrator, who administers the system and can open every patient
    profile, is shown the placeholder on a sealed record exactly as Health
    Center Staff are. Under RA 11166 the treating clinician is the reader who
    needs privileged information, and a system administrator is not one.
    """
    return can_diagnose(role)


def redact(consultation, viewer_can_view):
    """A copy of one consultation with its sealed fields withheld, if they are.

    Returns a NEW dict every time. The row it is given is never mutated, because
    the same row is read by the audit trail and by the write path, and a
    redaction that leaked into either would either censor an audit entry or
    write the placeholder into the database as though it were a diagnosis.

    Both the raw field and its `<field>_display` twin are replaced, not just the
    twin. The profile prints the raw value in two places and the twin in a third,
    and a template added later will reach for whichever is nearer -- so the value
    that is present is the placeholder whichever one it takes. That is the
    difference between a rule and a habit: there is no spelling of
    `consultation.diagnosis` that yields the sealed text to a viewer who may not
    read it.

    `withheld` says whether anything was actually taken out, which is what the
    profile reads to decide whether to explain itself, and what
    routes/patient_views.py counts to decide whether the view is worth an audit
    entry. It is False for an unsealed record and False for the Doctor, who had
    nothing withheld from them.
    """
    values = dict(consultation)
    if viewer_can_view or not values.get("is_restricted"):
        values["withheld"] = False
        return values

    for field in SEALED_FIELDS:
        values[field] = RESTRICTED_PLACEHOLDER
        values[f"{field}_display"] = RESTRICTED_PLACEHOLDER
    values["withheld"] = True
    return values


# What the Doctor sees when a sealed field cannot be decrypted on this computer:
# the key in .env is missing, wrong, or the stored value is damaged.
UNOPENABLE_TEXT = "This sealed record cannot be opened on this computer."


def open_sealed_value(value, row_id, field, role, table="consultations"):
    """Decrypt one sealed field for the Doctor. Returns (text, opened).

    THE ONLY PLACE IN THE APP THAT DECRYPTS. Every other role is refused here,
    whatever the caller asked, so a new screen cannot leak a sealed field by
    forgetting a check. A value that cannot be opened returns
    (UNOPENABLE_TEXT, False) instead of raising, so the page still renders.
    """
    if not can_view_restricted(role):
        raise PermissionError("Only the Doctor may open a sealed record.")
    if not sealed_crypto.is_encrypted(value):
        return value, True
    try:
        return sealed_crypto.decrypt(value, row_id, field, table), True
    except sealed_crypto.SealedDataError:
        return UNOPENABLE_TEXT, False


def open_sealed(consultation, role):
    """A copy of one consultation with its sealed fields decrypted, for the Doctor.

    `unopenable` is True when a field could not be decrypted. The caller then
    writes one audit entry (routes/sealed_access.py) and must not save the
    shown text back as a diagnosis.
    """
    values = dict(consultation)
    values["withheld"] = False
    values["unopenable"] = False
    if not values.get("is_restricted"):
        return values
    for field in SEALED_FIELDS:
        text, opened = open_sealed_value(values.get(field), values["id"], field, role)
        values[field] = text
        values[f"{field}_display"] = _rendered(field, text, MISSING_TEXT)
        if not opened:
            values["unopenable"] = True
    return values


def for_viewer(consultation, role):
    """One consultation as this role may see it: opened for the Doctor, redacted for others."""
    if can_view_restricted(role):
        return open_sealed(consultation, role)
    return redact(consultation, False)


def _encrypt_sealed_fields(conn, consultation_id):
    """Encrypt the sealed fields of one row, and its visit's check-in reason, on
    the caller's connection. No commit.

    Values already encrypted are left alone, so running it twice is safe.
    """
    row = conn.execute(
        f"SELECT appointment_id, {', '.join(SEALED_FIELDS)} FROM consultations WHERE id = ?",
        (consultation_id,),
    ).fetchone()
    if row is None:
        return
    conn.execute(
        f"UPDATE consultations SET {', '.join(f'{f} = ?' for f in SEALED_FIELDS)} "
        "WHERE id = ?",
        [row[f] if sealed_crypto.is_encrypted(row[f])
         else sealed_crypto.encrypt(row[f], consultation_id, f)
         for f in SEALED_FIELDS]
        + [consultation_id],
    )
    _seal_visit_reason(conn, row["appointment_id"])


def _seal_visit_reason(conn, appointment_id):
    """Encrypt the check-in reason of one queue visit. No commit. Safe to repeat."""
    if not appointment_id:
        return
    row = conn.execute(
        f"SELECT {VISIT_REASON_FIELD} FROM {VISIT_REASON_TABLE} WHERE id = ?",
        (appointment_id,),
    ).fetchone()
    if row is None or sealed_crypto.is_encrypted(row[VISIT_REASON_FIELD]):
        return
    conn.execute(
        f"UPDATE {VISIT_REASON_TABLE} SET {VISIT_REASON_FIELD} = ? WHERE id = ?",
        (sealed_crypto.encrypt(row[VISIT_REASON_FIELD], appointment_id,
                               VISIT_REASON_FIELD, VISIT_REASON_TABLE),
         appointment_id),
    )


def _open_visit_reason(conn, appointment_id, role):
    """The decrypted check-in reason of one queue visit, as (text, ok, row_exists).

    Used when a seal is lifted, so the reason goes back to plain text. Reads
    through open_sealed_value(), so only the Doctor can get anything.
    """
    if not appointment_id:
        return None, True, False
    row = conn.execute(
        f"SELECT {VISIT_REASON_FIELD} FROM {VISIT_REASON_TABLE} WHERE id = ?",
        (appointment_id,),
    ).fetchone()
    if row is None:
        return None, True, False
    text, ok = open_sealed_value(row[VISIT_REASON_FIELD], appointment_id,
                                 VISIT_REASON_FIELD, role, VISIT_REASON_TABLE)
    return text, ok, True


def as_date(value):
    """A date, a stored 'YYYY-MM-DD[ HH:MM:SS]' string, or None -> a date.

    Falls back to today for anything absent or unparseable.

    consultation_date comes back from SQLite as text, and every age calculation
    downstream needs a real date object. Normalising here rather than at each
    call site means a caller cannot forget: passing the stored string straight
    through reaches calculate_age() and fails on `reference.year`.
    """
    if value is None or value == "":
        return today()
    if hasattr(value, "year") and not hasattr(value, "hour"):
        return value
    if hasattr(value, "date"):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return today()


def consultation_age_context(patient, on_date=None):
    """What the patient's age means for this consultation's form.

    `on_date` is the consultation's own date -- as a date or as the text SQLite
    stores -- so an old record is always judged by how old the patient was at the
    time. Defaults to today for a new one.

    Returns the age as the screens print it, the whole-year number, and the two
    eligibility flags the form and the validator both read -- one computation,
    so the fields that are offered are exactly the fields that will be accepted.
    """
    reference = as_date(on_date)
    birth_date = patient.get("birth_date") if patient else None
    years = calculate_age(birth_date, on_date=reference)

    return {
        "age_display": format_age(birth_date, on_date=reference),
        "age_years": years,
        # An unknown birthdate yields neither: inventing a cohort for a patient
        # whose age nobody recorded would put a head circumference on a record
        # that cannot justify one.
        "is_pediatric": years is not None and 0 <= years < PEDIATRIC_AGE_YEARS,
        "is_infant": years is not None and 0 <= years < INFANT_AGE_YEARS,
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "infant_age_years": INFANT_AGE_YEARS,
    }


def allowed_growth_fields(age_context):
    """The growth measurements this patient's age admits, as a set.

    The single authority on the question. The form renders these, the validator
    accepts only these, and store_values() drops everything else -- so a POST
    that never touched the page cannot put a head circumference on an adult.
    """
    allowed = set()
    if age_context["is_pediatric"]:
        allowed.add("height")
    if age_context["is_infant"]:
        allowed.add("head_circumference")
    return allowed


def _with_unit(field, value):
    """A measurement rendered with its unit: 37.2 -> '37.2 °C'. None -> None.

    `:g` rather than str() so a REAL round-tripped through SQLite prints as 37.2
    and 12 rather than 37.2 and 12.0 -- the second reads as a precision the
    instrument does not have.
    """
    if value is None or value == "":
        return None
    unit = _LIMITS_BY_FIELD[field][2]
    text = f"{value:g}" if isinstance(value, float) else str(value)
    return f"{text} {unit}".strip()


def _rendered(field, value, absent):
    """One stored value as text, or `absent` when there is nothing there.

    The single renderer behind both the profile screen and the audit trail. They
    differ only in how they word an empty field -- a table cell says "Not
    recorded", a sentence in a log says "not recorded" -- so that word is the
    parameter and everything else is shared. Two renderers would eventually
    disagree about a unit.
    """
    if value is None or value == "":
        return absent
    if field == "follow_up_date":
        from utils.dates import display_date

        return display_date(value, fallback=str(value))
    if field in _LIMITS_BY_FIELD:
        return _with_unit(field, value)
    return value


def describe_consultation_changes(before, after):
    """The audit text for one consultation edit. Returns (summary, changed fields).

    NO AUDIT ENTRY QUOTES A CLINICAL VALUE (D5, Task 5c).
    Audit Logs are read and exported by the Administrator, who is not part of
    the patient's care. Every field is only named, in form order: "Changed:
    Temperature, Chief complaint". That covers the vitals and the follow-up date
    too, which Task 5b still quoted.

    On a sealed record both sides are ciphertext. A field the Doctor did not
    change keeps its stored ciphertext, so it does not read as changed.
    """
    from models.audit import describe_changes

    _, changed = describe_changes(before, after, FIELD_LABELS)
    if not changed:
        return "", []
    return "Changed: " + ", ".join(FIELD_LABELS[f] for f in changed), list(changed)


def _to_consultation(row):
    """Copy a consultations row into a dict and add the derived display fields.

    Every clinical field gains a `<field>_display` twin holding either the value
    with its unit or "Not recorded". The five seeded rows predate the vitals
    columns entirely, so the profile screen would otherwise print blanks where a
    reader cannot tell "measured 0" from "never measured" -- the two readings a
    medical record must never confuse.
    """
    consultation = dict(row)
    for field in CONSULTATION_FIELDS:
        consultation[f"{field}_display"] = _rendered(
            field, consultation.get(field), MISSING_TEXT
        )

    consultation["has_vitals"] = any(
        consultation.get(field) not in (None, "") for field in VITAL_FIELDS
    )
    consultation["has_growth"] = any(
        consultation.get(field) not in (None, "") for field in GROWTH_FIELDS
    )
    # A record that has been changed since it was written. updated_at is
    # backfilled from created_at by the migration, so equality means untouched.
    consultation["was_edited"] = bool(
        consultation.get("updated_at")
        and consultation.get("created_at")
        and consultation["updated_at"] != consultation["created_at"]
    )
    # A plain bool rather than the stored 0/1, because every reader of this is a
    # condition -- a template branch, redact()'s guard, an audit decision -- and
    # SQLite hands integers back. Kept alongside the raw column rather than
    # replacing it so nothing that reads `is_restricted` has to know which.
    consultation["is_restricted"] = bool(consultation.get("is_restricted"))
    return consultation


# restricted_by is LEFT joined, unlike recorded_by above it, because it is null
# on every consultation nobody has sealed -- which is nearly all of them. An
# inner join here would have silently dropped every unsealed record from the
# patient's history, which is the kind of failure that looks like data loss.
_CONSULTATION_SELECT = """
    SELECT c.*, u.full_name AS recorded_by_name, u.role AS recorded_by_role,
           r.full_name AS restricted_by_name,
           p.patient_id AS patient_reference, p.first_name, p.middle_name,
           p.last_name, p.birth_date, p.sex
    FROM consultations c
    JOIN users u ON u.id = c.recorded_by
    LEFT JOIN users r ON r.id = c.restricted_by
    JOIN patients p ON p.id = c.patient_id
"""


def get_consultation_report(viewer_role, limit=None):
    """Every consultation with its patient and author, newest first.

    Written for Screen 10, which does not use it: that screen wants counts and
    rankings, and get_consultation_stats() below answers those in SQL instead of
    pulling every row into memory for the template to total up.

    Its caller today is the Administrator dashboard's "Recent Patient
    Consultations" panel, which wants the opposite thing -- the actual latest
    visits, named. `limit` is for that panel; left off, the function still
    returns the whole set, which is what a future spreadsheet export wants.

    birth_date and created_at come back so the panel can print an age and a time
    without a second query per row. Age is derived through calculate_age() by the
    caller, the same function every other screen ages a patient with.

    Ordered by consultation_date then id so two visits recorded on the same date
    -- which is normal, the column is a date for anything entered on Screen 21 --
    come back newest-first rather than in whatever order SQLite happens to scan.
    """
    # No diagnosis or treatment plan: the dashboard panel shows neither, and a
    # column nobody prints is a column that can leak a sealed field later. The
    # chief complaint is sealed with the record (Task 5b), so it is shaped for
    # `viewer_role` here: opened for the Doctor, the placeholder for everyone
    # else. `viewer_role` has no default, for the reason
    # get_consultations_for_patient() gives.
    with db_connection() as conn:
        rows = conn.execute(
            f"""
        SELECT c.id, c.consultation_date, c.chief_complaint, c.is_restricted,
               c.created_at, c.appointment_id,
               p.id AS patient_row_id, p.patient_id, p.first_name, p.last_name,
               p.birth_date, u.full_name AS recorded_by
        FROM consultations c
        JOIN patients p ON p.id = c.patient_id
        JOIN users u ON u.id = c.recorded_by
        ORDER BY c.consultation_date DESC, c.id DESC
        {"LIMIT ?" if limit else ""}
        """,
            (limit,) if limit else (),
        ).fetchall()

    entries = []
    for row in rows:
        entry = dict(row)
        if entry["is_restricted"]:
            if can_view_restricted(viewer_role):
                entry["chief_complaint"], _ = open_sealed_value(
                    entry["chief_complaint"], entry["id"], "chief_complaint",
                    viewer_role)
            else:
                entry["chief_complaint"] = RESTRICTED_PLACEHOLDER
        entries.append(entry)
    return {
        "entries": entries,
        "total_entries": len(rows),
    }


# ---------------------------------------------------------------------------
# REPORTING
#
# WHY consultation_date IS GROUPED WITH substr(), NOT date()
# ----------------------------------------------------------
# The column holds two shapes. A consultation written up through Screen 09
# stores the visit date the form supplied ('2026-08-03'); the column's DEFAULT
# CURRENT_TIMESTAMP writes a full UTC stamp ('2026-08-03 14:22:01') for anything
# inserted without one. Taking the leading 7 characters treats both as the
# clinic-local month they were recorded under, which is what a monthly report is
# asking for, and avoids re-interpreting a plain date as a UTC instant -- which
# date() would do, moving an early-morning visit into the previous month.
# ---------------------------------------------------------------------------

# How many rows the "most common diagnoses" list shows. A barangay health centre
# report is read at a glance; beyond about five the tail is noise.
TOP_DIAGNOSIS_LIMIT = 5

# ---------------------------------------------------------------------------
# A SEALED DIAGNOSIS IS NOT RANKED, AT ANY COUNT
#
# The seal on a consultation withholds its diagnosis from everyone but the
# Doctor on the screens that show that record. This module builds
# something different -- a ranking of diagnosis TEXT across many records -- and
# an aggregate looked like a safe place for a sealed value to go, because no
# patient is named in it.
#
# It is not, and the reason is the size of the count rather than the absence of a
# name. A ranking prints the words a clinician typed. A common diagnosis appears
# there with a count in double figures and tells a reader nothing about anybody;
# a rare one appears with a count of 1, and a count of 1 is not a statistic, it is
# a record with the name filed off. Reports & Analytics carries a date range, and
# a reader who can set that range to a single day has narrowed one sealed
# diagnosis to the visits of that day. RA 11166 attaches criminal penalties to
# disclosing HIV status without consent, and it does not stop applying because
# the disclosure arrived as a row in a table.
#
# So the rule is not "exclude it when the count is low". Any threshold is a
# promise about re-identification that this system is in no position to make, and
# it would have to be re-argued every time a report gained a filter. Sealed
# diagnoses are excluded from the ranking entirely, at every count, and the
# exclusion lives HERE -- in the one function every reader of these figures goes
# through -- rather than in the screens. There are nine surfaces printing this
# ranking (the Administrator's Reports & Analytics and the Barangay Official's,
# each as a screen, an Excel workbook and a PDF, plus the Official's Community
# Reports as the same three), and a rule applied at nine call sites is a rule
# with nine chances to be forgotten.
#
# WHAT IS STILL COUNTED. The visit, in `total`, in `patients_seen` and in the
# trend; and its chief complaint, in the complaints ranking beside this one. Only
# the diagnosis text is held back, which is exactly what the seal covers on every
# other screen -- see DOCTOR_ONLY_FIELDS.
#
# TASK 5d (D1) ADDS A SECOND RULE ON TOP OF THIS ONE, FOR UNSEALED TEXT. Sealed
# text is still never ranked, at any count. Separately, the Administrator and the
# Barangay Official see any row with a count of 1 to 4 -- the Confidential row
# included -- as one "Other (each fewer than 5)" row, because a small count over a
# short range can point at one visit. utils/small_counts.py holds the rule.
#
# SINCE TASK 5 (D3) SEALED VISITS ARE ONE "Confidential" ROW IN THE RANKING,
# for every role, so the ranking accounts for every consultation and still
# shows no sealed text. `diagnoses_withheld` is that row's count. A count
# discloses nothing: it names no patient, no date and no condition.
# ---------------------------------------------------------------------------


def _rank_free_text(rows, limit):
    """Group free-text clinical entries case-insensitively, most common first.

    diagnosis and chief_complaint are prose typed by a health worker, not a
    controlled vocabulary, so 'Acute bronchitis' and 'acute bronchitis' are one
    diagnosis and must not be two bars on a chart. The label shown is the first
    spelling encountered, so the report prints something a person actually wrote
    rather than a lower-cased normalisation of it.

    Ties are broken alphabetically so the same data always renders in the same
    order -- a chart that reshuffles between page loads reads as changing data.
    """
    grouped = {}
    for row in rows:
        text = (row or "").strip()
        if not text:
            continue
        key = " ".join(text.lower().split())
        entry = grouped.setdefault(key, {"label": text, "count": 0})
        entry["count"] += 1

    ranked = sorted(grouped.values(), key=lambda item: (-item["count"], item["label"].lower()))
    return ranked[:limit] if limit else ranked


# The one category every sealed consultation is counted under in a breakdown by
# diagnosis (D3), for every role. Its text is never ranked, at any count.
CONFIDENTIAL_LABEL = "Confidential"


def _rank_diagnoses(diagnoses, sealed_count, limit, viewer_role):
    """The diagnosis ranking, with sealed consultations as one Confidential row.

    The Confidential row is ranked by its count like any other. If it would
    fall outside the top `limit`, it is added at the end anyway, so the
    breakdown always accounts for every sealed visit.

    For the Administrator and the Barangay Official, every row with a count of 1
    to 4, the Confidential row included, is then folded into one Other row (Task
    5d, D1; see utils/small_counts.py). The fold is made on the whole ranking, so
    the Other row adds up every small group, not only those inside the top
    `limit`. The Other row comes last and is not counted against the limit.
    """
    ranked = _rank_free_text(diagnoses, None)
    if sealed_count:
        ranked.append({"label": CONFIDENTIAL_LABEL, "count": sealed_count,
                       "confidential": True})
        ranked.sort(key=lambda item: (-item["count"], item["label"].lower()))
    ranked = fold_small_counts(ranked, viewer_role, label_key="label",
                               sum_keys=("count",))
    named = [entry for entry in ranked if not entry.get("other")]
    other = [entry for entry in ranked if entry.get("other")]
    if limit and len(named) > limit:
        top = named[:limit]
        top.extend(entry for entry in named[limit:]
                   if entry.get("confidential") and entry not in top)
        named = top
    return named + other


def get_consultation_stats(months=6, limit=TOP_DIAGNOSIS_LIMIT, on_date=None,
                           start=None, end=None, *, viewer_role):
    """The consultation figures Screen 10 reports.

    Returns totals, a month-by-month trend over the same window the other trend
    charts use, and the most common diagnoses and presenting complaints.

    `recorded_this_month` counts by the month the visit is dated to, which is the
    same basis the trend's last bar uses -- so the KPI card and the right-hand
    end of the chart cannot print different numbers for the same period.

    THE `window` BLOCK
    ------------------
    `start`/`end` ask for a specific range. Everything above stays exactly as it
    was -- `total` is still every consultation ever recorded, and every existing
    caller reads unchanged numbers -- and the range-scoped answers arrive in
    their own `window` block. Two rules follow from that split and are worth
    stating, because both were ways this could have gone quietly wrong:

    * The window's totals and its trend are counted from one pass over the same
      rows, so the cards a generated report prints and the chart beneath them
      cannot disagree about the range they both describe.
    * The diagnoses and complaints in `window` are ranked from the window's rows
      only. Leaving them at all-time would have been the subtle failure here: a
      report headed "March to June" would have listed the year's top complaints
      underneath it and read as though those were March-to-June's.

    SEALED CONSULTATIONS
    --------------------
    A consultation the clinician has marked Restricted counts in every figure
    here. In the diagnosis and complaint rankings it is counted under one
    Confidential row, never by its text (D3, Task 5b). `diagnoses_withheld` is
    that row's count, and it is the same for both rankings.

    `viewer_role` HAS NO DEFAULT, for the reason get_consultations_for_patient()
    gives. It decides the small-count rule (Task 5d, D1): for the Administrator and
    the Barangay Official a ranking row with a count of 1 to 4 is folded into one
    Other row. `diagnoses_withheld_shown` is the restricted-visit count as that
    viewer may read it: the number, or "Fewer than 5". Totals are never changed.
    """
    reference = on_date or today()
    window = resolve_range(start=start, end=end, months=months, on_date=reference)
    current_month = reference.strftime("%Y-%m")
    lo, hi = window["start"].isoformat(), window["end"].isoformat()

    with db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
        by_month = {
            row["month"]: row["count"]
            for row in conn.execute(
                """
            SELECT substr(consultation_date, 1, 7) AS month, COUNT(*) AS count
            FROM consultations
            GROUP BY month
            """
            ).fetchall()
        }
        patients_seen = conn.execute(
            "SELECT COUNT(DISTINCT patient_id) FROM consultations"
        ).fetchone()[0]
        # A SEALED CONSULTATION'S DIAGNOSIS IS NOT RANKED HERE. See the block above
        # _rank_free_text() for why an aggregate is not a safe place for one.
        diagnoses = [
            row[0] for row in conn.execute(
                "SELECT diagnosis FROM consultations WHERE is_restricted = 0"
            )
        ]
        withheld_total = conn.execute(
            "SELECT COUNT(*) FROM consultations WHERE is_restricted = 1"
        ).fetchone()[0]
        # THE COMPLAINTS ARE RANKED THE SAME WAY (Task 5b). The chief complaint is
        # sealed with the record, and a complaint such as "for HIV testing" is
        # itself the disclosure RA 11166 Section 44 forbids. A sealed visit is
        # counted under the one Confidential row and its text is never ranked.
        complaints = [
            row[0] for row in conn.execute(
                "SELECT chief_complaint FROM consultations WHERE is_restricted = 0"
            )
        ]

        # The window's own rows. consultation_date is stored as clinic-local date
        # text (it is the day of the visit, not a UTC instant), so the range compares
        # against its leading ten characters directly -- no timezone conversion, and
        # a row carrying a time still lands on its own day.
        #
        # is_restricted comes along so the diagnosis ranking can drop the sealed rows
        # WITHOUT the visit itself vanishing. The filter is applied where the ranking
        # is built, a few lines below, and deliberately not in this WHERE clause: a
        # sealed consultation still happened, was still attended, and still belongs
        # in the total, in patients_seen and in the month it falls in. Filtering here
        # would have made a sealed visit disappear from the barangay's activity
        # figures altogether, which is a second, quieter falsehood -- and one that
        # would have moved the trend line under a card that no longer matched it.
        scoped = conn.execute(
            """
        SELECT diagnosis, chief_complaint, patient_id, is_restricted,
               substr(consultation_date, 1, 7) AS month
        FROM consultations
        WHERE substr(consultation_date, 1, 10) BETWEEN ? AND ?
        """,
            (lo, hi),
        ).fetchall()

    # THE TREND IS CLIPPED TO THE RANGE, NOT TO WHOLE MONTHS.
    # A report for 1-10 August whose August bar showed the whole month would put
    # 11 on the chart directly under a card reading 6, and the reader has no way
    # to tell which of the two answers the range they asked for. Counting the
    # trend from the window's own rows makes the bars sum to the card by
    # construction; a part-month is a part-month on the chart as well.
    scoped_by_month = {}
    for row in scoped:
        scoped_by_month[row["month"]] = scoped_by_month.get(row["month"], 0) + 1

    trend = [
        {
            "month": start_day.strftime("%Y-%m"),
            "label": label,
            "count": scoped_by_month.get(start_day.strftime("%Y-%m"), 0),
        }
        for start_day, _, label in window["months"]
    ]

    # The window's rankable diagnoses, and how many were held back from them.
    # Counted rather than merely dropped, because every screen and export that
    # prints this ranking also prints the number of consultations it was ranked
    # from, and that sentence would otherwise be making a claim the ranking no
    # longer meets. What is published is a count and never a hint of content.
    scoped_diagnoses = [row["diagnosis"] for row in scoped if not row["is_restricted"]]
    scoped_complaints = [row["chief_complaint"] for row in scoped
                         if not row["is_restricted"]]
    scoped_withheld = sum(1 for row in scoped if row["is_restricted"])

    return {
        "total": total,
        "recorded_this_month": by_month.get(current_month, 0),
        "patients_seen": patients_seen,
        "months": months,
        "trend": trend,
        "top_diagnoses": _rank_diagnoses(diagnoses, withheld_total, limit, viewer_role),
        "top_complaints": _rank_diagnoses(complaints, withheld_total, limit, viewer_role),
        "diagnoses_withheld": withheld_total,
        "diagnoses_withheld_shown": shown_count(withheld_total, viewer_role),
        "window": {
            "start": window["start"],
            "end": window["end"],
            "custom": window["custom"],
            "total": len(scoped),
            "patients_seen": len({row["patient_id"] for row in scoped}),
            "trend": trend,
            "top_diagnoses": _rank_diagnoses(
                scoped_diagnoses, scoped_withheld, limit, viewer_role),
            "top_complaints": _rank_diagnoses(
                scoped_complaints, scoped_withheld, limit, viewer_role),
            # How many of this range's `total` consultations are counted under the
            # Confidential row of the two rankings above. The total,
            # patients_seen and the trend all still count every one of them.
            "diagnoses_withheld": scoped_withheld,
            "diagnoses_withheld_shown": shown_count(scoped_withheld, viewer_role),
        },
    }


def get_consultations_for_patient(patient_id, viewer_role):
    """Consultation History tab on Screen 04, most recent first, redacted to fit.

    Returns the whole row, not the four columns it used to: the tab now shows the
    vitals and growth measurements alongside the clinical text, and each entry
    carries its own edit link.

    recorded_by keeps its original meaning -- the health worker's name -- so the
    template that already prints it is unaffected.

    `viewer_role` HAS NO DEFAULT, AND THAT IS THE POINT.
    A default would be a decision about confidentiality made by whichever value
    seemed harmless when this signature was written, inherited silently by every
    caller added afterwards. Defaulting to the Administrator would leak a sealed
    diagnosis to any future caller that forgot to pass a role; defaulting the
    other way would blank the doctor's own screen. So the question is compulsory,
    it is answered from the signed-in account (utils.security.current_role()),
    and a caller that cannot answer it cannot call this function.

    The redaction happens HERE, at the read, rather than in the template. What is
    withheld is not in the returned dictionaries at all, so it is not in the
    render context, so it is not in the bytes sent to the browser -- there is
    nothing for a View Source, a saved page or a disabled stylesheet to recover.
    """
    with db_connection() as conn:
        rows = conn.execute(
            _CONSULTATION_SELECT
            + " WHERE c.patient_id = ? ORDER BY c.consultation_date DESC, c.id DESC",
            (patient_id,),
        ).fetchall()

    consultations = []
    for row in rows:
        consultation = _to_consultation(row)
        # The name under its historical key, so patient_profile.html's existing
        # "Attending: {{ consultation.recorded_by }}" keeps working unchanged.
        consultation["recorded_by"] = consultation["recorded_by_name"]
        # Decrypted for the Doctor, redacted for everyone else.
        consultations.append(for_viewer(consultation, viewer_role))
    return consultations


def get_consultation_by_id(consultation_id):
    """One consultation with its patient and author, or None.

    DELIBERATELY UNREDACTED, unlike get_consultations_for_patient() above. This
    is the write path's reader: process_edit_consultation() calls it for the
    before-and-after that the audit entry is composed from, and an audit trail
    that had been shown a placeholder instead of the stored value would record
    the seal as though it were the diagnosis. The two callers that put this on a
    screen redact it themselves, at the point they know who is looking -- see
    routes/consultation_views.py consultation_form_context().
    """
    with db_connection() as conn:
        row = conn.execute(
            _CONSULTATION_SELECT + " WHERE c.id = ?", (consultation_id,)
        ).fetchone()
    if row is None:
        return None
    consultation = _to_consultation(row)
    consultation["recorded_by"] = consultation["recorded_by_name"]
    consultation["patient_name"] = " ".join(
        part for part in (row["first_name"], row["middle_name"], row["last_name"]) if part
    )
    return consultation


def get_consultation_for_appointment(appointment_id):
    """The consultation already written up for one queue entry, or None.

    What stops the same visit being recorded twice: the form refuses to open a
    second time for an appointment that already has a record, and offers the
    existing one to edit instead.
    """
    if not appointment_id:
        return None
    with db_connection() as conn:
        row = conn.execute(
            _CONSULTATION_SELECT + " WHERE c.appointment_id = ? ORDER BY c.id LIMIT 1",
            (appointment_id,),
        ).fetchone()
    return _to_consultation(row) if row else None


def _clean_number(raw, whole_number):
    """Parse a submitted measurement. Returns (value, ok). Blank is (None, True)."""
    text = str(raw or "").strip()
    if not text:
        return None, True
    try:
        value = float(text)
    except ValueError:
        return None, False
    if whole_number:
        if value != int(value):
            return None, False
        return int(value), True
    # Two decimals is finer than any instrument in the building reads.
    return round(value, 2), True


def parse_blood_pressure(raw):
    """'120/80' -> (120, 80), or (None, None) when it is blank or unusable."""
    text = str(raw or "").strip()
    if not text:
        return None, None
    parts = text.replace("\\", "/").split("/")
    if len(parts) != 2:
        return None, None
    try:
        systolic, diastolic = (int(part.strip()) for part in parts)
    except ValueError:
        return None, None
    return systolic, diastolic


def validate_consultation_form(values, age_context, require_diagnosis=True):
    """Server-side validation. Returns {field: message}; empty means valid.

    Runs independently of the browser: the form carries `novalidate`, and a POST
    can arrive without ever touching the page.

    Growth fields are checked against `age_context`, so submitting a head
    circumference for an adult is an error rather than something quietly stored.

    `require_diagnosis` False drops the two DOCTOR_ONLY_FIELDS from the required
    set, and it is what a save by Health Center Staff passes. Without it the
    intake they are allowed to record could never be saved: the form would refuse
    it for missing two fields the person filling it in is not licensed to write
    and cannot see. It narrows what is REQUIRED and nothing else -- the same
    submission's growth, vital and date rules are unchanged, and whether those
    two fields may be WRITTEN is not decided here at all but in
    routes/consultation_views.py, which strips them before this runs.
    """
    errors = {}

    required = dict(REQUIRED_FIELDS)
    if not require_diagnosis:
        for field in DOCTOR_ONLY_FIELDS:
            required.pop(field, None)

    for field, message in required.items():
        if not str(values.get(field) or "").strip():
            errors[field] = message

    allowed = allowed_growth_fields(age_context)
    for field, label, unit, low, high, whole in NUMERIC_LIMITS:
        raw = str(values.get(field) or "").strip()
        if not raw:
            continue
        if field in GROWTH_FIELDS and field not in allowed:
            errors[field] = (
                f"{label} is only recorded for "
                + (
                    f"infants under {INFANT_AGE_YEARS} year"
                    if field == "head_circumference"
                    else f"children under {PEDIATRIC_AGE_YEARS}"
                )
                + ". This patient is outside that age."
            )
            continue
        value, ok = _clean_number(raw, whole)
        if not ok:
            errors[field] = (
                f"Enter {label.lower()} as a whole number in {unit}."
                if whole
                else f"Enter {label.lower()} as a number in {unit}."
            )
        elif value is not None and not (low <= value <= high):
            errors[field] = (
                f"{label} must be between {low:g} and {high:g} {unit}. "
                "Check the reading before saving."
            )

    raw_bp = str(values.get("blood_pressure") or "").strip()
    if raw_bp:
        systolic, diastolic = parse_blood_pressure(raw_bp)
        if systolic is None:
            errors["blood_pressure"] = "Enter blood pressure as systolic/diastolic, e.g. 120/80."
        elif not (BP_SYSTOLIC_RANGE[0] <= systolic <= BP_SYSTOLIC_RANGE[1]):
            errors["blood_pressure"] = (
                f"Systolic must be between {BP_SYSTOLIC_RANGE[0]} and {BP_SYSTOLIC_RANGE[1]}."
            )
        elif not (BP_DIASTOLIC_RANGE[0] <= diastolic <= BP_DIASTOLIC_RANGE[1]):
            errors["blood_pressure"] = (
                f"Diastolic must be between {BP_DIASTOLIC_RANGE[0]} and {BP_DIASTOLIC_RANGE[1]}."
            )
        elif systolic <= diastolic:
            errors["blood_pressure"] = (
                "Systolic must be higher than diastolic — check the two numbers "
                "are the right way round."
            )

    follow_up = str(values.get("follow_up_date") or "").strip()
    if follow_up:
        try:
            parsed = datetime.strptime(follow_up, "%Y-%m-%d").date()
        except ValueError:
            errors["follow_up_date"] = "Enter a valid date in YYYY-MM-DD format."
        else:
            # A follow-up is an instruction to come back, so it cannot fall
            # before the visit. Judged against the visit's own date rather than
            # today, so editing last month's record does not suddenly invalidate
            # a follow-up that was perfectly future when it was written.
            if parsed < as_date(values.get("_consultation_date")):
                errors["follow_up_date"] = (
                    "The follow-up date cannot be before the consultation date."
                )

    return errors


def store_values(values, age_context):
    """Normalise submitted form values into the column values to store.

    Shared by create_consultation() and update_consultation() so an insert and an
    edit can never normalise the same field differently.

    Growth fields outside the patient's cohort are dropped to NULL rather than
    stored. validate_consultation_form() already rejects them, so this is the
    second of two independent refusals -- the one that holds even if a future
    caller forgets to validate.
    """
    record = {}
    for field in CLINICAL_TEXT_FIELDS:
        record[field] = str(values.get(field) or "").strip() or None

    allowed = allowed_growth_fields(age_context)
    for field, _label, _unit, _low, _high, whole in NUMERIC_LIMITS:
        if field in GROWTH_FIELDS and field not in allowed:
            record[field] = None
            continue
        record[field], _ok = _clean_number(values.get(field), whole)

    systolic, diastolic = parse_blood_pressure(values.get("blood_pressure"))
    # Re-composed from the parsed halves rather than stored as typed, so
    # "120 / 80" and "120/80" cannot end up as two different-looking readings.
    record["blood_pressure"] = f"{systolic}/{diastolic}" if systolic is not None else None

    record["follow_up_date"] = str(values.get("follow_up_date") or "").strip() or None
    return record


def create_consultation(patient_id, recorded_by, values, age_context,
                        appointment_id=None, consultation_date=None, audit=None,
                        sealed_by=None):
    """Insert a consultation and return its new primary key.

    `sealed_by` is the Doctor's user id when the record is sealed as it is
    written. The seal and the encryption then commit with the record, and the
    check-in reason of the linked queue visit is encrypted with them.

    consultation_date is the clinic-local calendar date, matching the format the
    five seeded rows already use, so the history table sorts and prints one way.
    created_at keeps the precise instant, from the column's own default.

    `audit(conn, new_id)` is called before the commit, so "Recorded
    consultation" commits with the record (Task 4, H3). The entry names the
    consultation and the patient only, never what the consultation says.
    """
    record = store_values(values, age_context)
    day = as_date(consultation_date).isoformat()

    columns = ["patient_id", "recorded_by", "appointment_id", "consultation_date",
               *CONSULTATION_FIELDS, "updated_at"]
    placeholders = ", ".join("?" for _ in columns)
    parameters = [patient_id, recorded_by, appointment_id, day]
    # A record sealed as it is written never holds its sealed fields as plain
    # text: they go in empty, and the encrypted values follow once the id (which
    # each value is bound to) exists. Same transaction.
    parameters += [None if (sealed_by and field in SEALED_FIELDS) else record[field]
                   for field in CONSULTATION_FIELDS]
    # Equal to created_at on an unedited record, which is what was_edited reads.
    parameters += [None]

    with db_connection() as conn:
        cursor = conn.execute(
            f"INSERT INTO consultations ({', '.join(columns)}) VALUES ({placeholders})",
            parameters,
        )
        conn.execute(
            "UPDATE consultations SET updated_at = created_at WHERE id = ?",
            (cursor.lastrowid,),
        )
        new_id = cursor.lastrowid
        if sealed_by:
            conn.execute(
                "UPDATE consultations SET "
                + ", ".join(f"{f} = ?" for f in SEALED_FIELDS)
                + ", is_restricted = 1, restricted_by = ?, "
                "restricted_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ?",
                [sealed_crypto.encrypt(record[f], new_id, f) for f in SEALED_FIELDS]
                + [sealed_by, new_id],
            )
            _seal_visit_reason(conn, appointment_id)
        if audit:
            audit(conn, new_id)
        conn.commit()
    return new_id


def update_consultation(consultation_id, values, age_context):
    """Overwrite one consultation's clinical fields. Returns rows affected.

    Deliberately leaves patient_id, recorded_by, appointment_id,
    consultation_date and created_at alone. Which patient a record belongs to and
    when the visit happened are historical fact; an edit corrects what was
    written about that visit, it does not move the visit. Letting patient_id
    change would silently transplant a diagnosis onto another person's chart.

    The audit entry is written by the caller, which is the only place that knows
    who is acting and from where.

    A SAVE THAT CHANGES NOTHING WRITES NOTHING, and returns 0.
    It used to run the UPDATE regardless, which stamped updated_at on a save that
    moved no field -- so the profile then labelled the visit "edited" while the
    flash beside it said "No changes". It mattered more once only the Doctor may
    diagnose: a forged submission from another role carrying a diagnosis has
    that field put back to the stored value by _apply_clinical_authority(), and
    what remains is exactly such a save. The refusal must leave the record
    byte-identical, not with a fresh timestamp and an "edited" label that point
    at an edit nobody was allowed to make. The comparison is `IS`, which treats
    two NULLs as equal, in the same statement as the write, so there is no gap
    between checking and writing for another save to land in.
    """
    record = store_values(values, age_context)
    assignments = ", ".join(f"{field} = ?" for field in CONSULTATION_FIELDS)
    unchanged = " AND ".join(f"{field} IS ?" for field in CONSULTATION_FIELDS)

    # strftime(...'%f') rather than CURRENT_TIMESTAMP, which is only accurate to
    # the second. created_at is second-precision and an unedited row copies it
    # verbatim into updated_at, so a second-precision edit landing inside the
    # same second as the original save would write back a byte-identical value --
    # and the record would go on claiming it had never been touched. The
    # fractional part makes "has this been edited?" exact rather than usually
    # right. display_date() still reads it: it falls back to the date prefix.
    with db_connection() as conn:
        # ON A SEALED RECORD THE SEALED FIELDS ARE STORED ENCRYPTED. A value equal
        # to what is stored (the ciphertext, handed back unchanged) is kept as it
        # is. Anything else is new text from the Doctor and is encrypted here, in
        # the same transaction, so it is never stored as plain text.
        stored = conn.execute(
            f"SELECT is_restricted, {', '.join(SEALED_FIELDS)} "
            "FROM consultations WHERE id = ?",
            (consultation_id,),
        ).fetchone()
        if stored is not None and stored["is_restricted"]:
            for field in SEALED_FIELDS:
                if record[field] != stored[field]:
                    record[field] = sealed_crypto.encrypt(record[field], consultation_id, field)
        parameters = (
            [record[field] for field in CONSULTATION_FIELDS]
            + [consultation_id]
            + [record[field] for field in CONSULTATION_FIELDS]
        )
        cursor = conn.execute(
            f"UPDATE consultations SET {assignments}, "
        "updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') "
        f"WHERE id = ? AND NOT ({unchanged})",
            parameters,
        )
        conn.commit()
        affected = cursor.rowcount
    return affected


def set_consultation_restriction(consultation_id, restricted, user_id, role=None, audit=None):
    """Seal or unseal one consultation. Returns what actually happened.

    One of "missing", "unchanged", "restricted" or "lifted". The caller decides
    what to say about each; nothing here flashes or logs, for the reason
    update_consultation() gives -- only the caller knows who is acting and from
    where.

    IT DOES NOT TOUCH updated_at, AND THAT IS DELIBERATE.
    Every other write to this table stamps updated_at, which is what
    was_edited reads and what the profile prints as "edited" beside the visit
    date. Sealing a record changes who may read it; it changes nothing the record
    says about the patient. Stamping it would put "edited" on a consultation
    whose clinical content is exactly what the clinician wrote, and would send
    anyone chasing that word to an audit trail with no content change in it.
    The seal has its own entry in that trail and its own two columns here.

    THE THREE COLUMNS ARE WRITTEN AS A SET, ALWAYS.
    Lifting a restriction clears restricted_by and restricted_at rather than
    leaving them behind as a fossil of the last seal. A row saying "not
    restricted, sealed by the Doctor on the 3rd" is a record making two claims
    at once, and the profile would have to choose which to print. The migration
    asserts the three agree, on every run.

    A no-op returns "unchanged" and writes nothing, which is the same rule
    process_edit_consultation() follows: a save that moved nothing is not an
    event, and an audit entry for it would bury the ones that matter.

    SEALING ENCRYPTS, LIFTING DECRYPTS, IN THE SAME TRANSACTION AS THE FLAG.
    That is every free-text field of the visit and the check-in reason of its
    queue visit (Task 5b, D1).
    Lifting needs `role`, because only the Doctor may decrypt. If the key on this
    computer cannot open the record, nothing changes and "cannot_open" is
    returned: the record stays sealed rather than losing its text.
    """
    flag = 1 if restricted else 0

    with db_connection() as conn:
        row = conn.execute(
            f"SELECT is_restricted, appointment_id, {', '.join(SEALED_FIELDS)} "
            "FROM consultations WHERE id = ?",
            (consultation_id,),
        ).fetchone()
        if row is None:
            return "missing"

        if bool(row["is_restricted"]) == bool(flag):
            return "unchanged"

        if flag:
            _encrypt_sealed_fields(conn, consultation_id)
        else:
            # Everything is opened before anything is written, so a key that cannot
            # open one value leaves the whole record sealed and untouched.
            opened = []
            for field in SEALED_FIELDS:
                text, ok = open_sealed_value(row[field], consultation_id, field, role)
                if not ok:
                    return "cannot_open"
                opened.append(text)
            reason, ok, has_reason = _open_visit_reason(
                conn, row["appointment_id"], role)
            if not ok:
                return "cannot_open"
            conn.execute(
                "UPDATE consultations SET "
                + ", ".join(f"{f} = ?" for f in SEALED_FIELDS) + " WHERE id = ?",
                opened + [consultation_id],
            )
            if has_reason:
                conn.execute(
                    f"UPDATE {VISIT_REASON_TABLE} SET {VISIT_REASON_FIELD} = ? "
                    "WHERE id = ?",
                    (reason, row["appointment_id"]),
                )

        conn.execute(
            """
        UPDATE consultations
           SET is_restricted = ?,
               restricted_by = ?,
               restricted_at = ?
         WHERE id = ?
        """,
            (
                flag,
                user_id if flag else None,
                # NULL here for both directions. Lifting a seal wants NULL and keeps
                # it; setting one has its stamp written by the statement below, from
                # SQLite's own clock rather than from Python's -- created_at and
                # updated_at on this table both come from that clock, and a third
                # date taken from a different one would disagree with them by
                # however far the application's idea of now has drifted.
                None,
                consultation_id,
            ),
        )
        # Same shape and same precision as the stamp update_consultation() writes, so
        # the dates on a record read alike and sort together.
        if flag:
            conn.execute(
                "UPDATE consultations "
            "SET restricted_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ?",
                (consultation_id,),
            )
        # The entry commits with the change, or neither does.
        if audit:
            audit(conn, consultation_id, "restricted" if flag else "lifted")
        conn.commit()
    return "restricted" if flag else "lifted"
