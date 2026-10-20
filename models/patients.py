"""Patient record queries.

Functions here return plain dicts rather than sqlite3.Row objects, because the
Patient Records and Patient Profile screens need derived values (age, full name,
composed address) that do not exist as columns. sqlite3.Row is read-only, so the
row is copied into a dict and the derived keys are added alongside.
"""
import calendar
import difflib
import json
import re
import unicodedata
from datetime import date, datetime

from database.connection import db_connection
from utils.dates import (
    day_start_utc,
    days_ago,
    month_bounds,
    range_bounds_utc,
    recent_months,
    resolve_range,
    today,
)
from utils.phone import is_valid_ph_mobile, to_local_ph_mobile
from utils.roles import holds_clinical_authority
from utils.small_counts import fold_small_counts, shown_count

# The vocabularies the Register Patient form offers. The template renders its
# <select>/radio/chip options from these same tuples, so a constrained field
# cannot accept a value the form never offered, and the two cannot drift apart.
CIVIL_STATUSES = ("Single", "Married", "Widowed", "Separated", "Minor")
SEXES = ("Female", "Male")
# The health center is in Barangay Poblacion, San Francisco (formerly Anao-Aon),
# Surigao del Norte -- a coastal municipality of 11 barangays, Surigao City about
# 12 km to the east. San Francisco is listed first because it is where nearly
# every patient lives; the other three are the LGUs it actually shares a land
# border with (Surigao City east, Malimono and Sison south -- the Bohol Sea is
# north and the Surigao Strait west, so there are no others). A patient who
# walked in from farther away than that is rare enough to belong in a
# conversation about the record, not in a list that invites a wrong pick.
#
# These previously read ("San Francisco", "Bunawan", "Rosario") and
# ("Agusan del Sur", "Surigao del Sur", "Davao de Oro") -- Agusan del Sur
# municipalities and provinces around a *different* San Francisco, ~150 km away
# in the wrong province. Nothing in the approved Capstone Proposal ever named a
# province; the value was invented here and then spread into real records. See
# a repair script (since deleted) that fixed the eleven records it reached.
MUNICIPALITIES = ("San Francisco", "Surigao City", "Malimono", "Sison")
# Surigao del Norte is the province the health center is in. Surigao del Sur is
# kept because it genuinely adjoins Surigao del Norte to the south, so a patient
# really can live there -- unlike Agusan del Sur and Davao de Oro, which border
# neither and were only ever artefacts of the wrong municipality.
PROVINCES = ("Surigao del Norte", "Surigao del Sur")
EMERGENCY_RELATIONSHIPS = (
    "Mother", "Father", "Spouse", "Son/Daughter", "Sibling", "Grandchild",
    "Guardian", "Other",
)
# "Unknown" is the form's placeholder choice and is stored as NULL, not as text.
# The "(Rh unknown)" entries record a patient who knows their ABO group but was
# never told their Rh factor. A bare "O" is deliberately absent: every person is
# either O+ or O-, so storing "O" would assert a blood type that does not exist.
BLOOD_TYPES = (
    "Unknown",
    "O+", "O-", "O (Rh unknown)",
    "A+", "A-", "A (Rh unknown)",
    "B+", "B-", "B (Rh unknown)",
    "AB+", "AB-", "AB (Rh unknown)",
)
CONDITION_OPTIONS = ("Hypertension", "Diabetes", "Asthma", "Tuberculosis")
ALLERGY_OPTIONS = ("Penicillin", "Sulfa Drugs", "Seafood")

# Fields marked with * on the form; the confirmed required set.
REQUIRED_FIELDS = {
    "first_name": "First name is required.",
    "last_name": "Last name is required.",
    "birth_date": "Birthdate is required.",
    "civil_status": "Civil status is required.",
    "sex": "Gender is required.",
    "address": "House No. / Street / Purok is required.",
    "municipality": "Municipality / City is required.",
    "province": "Province is required.",
    "emergency_contact_name": "Emergency contact name is required.",
    "emergency_contact_relationship": "Emergency contact relationship is required.",
    "emergency_contact_number": "Emergency contact number is required.",
}

# Every column the form writes, in one place so the INSERT and the redisplay
# cannot fall out of step. created_at is absent on purpose -- it comes from the
# column's DEFAULT CURRENT_TIMESTAMP.
PATIENT_FIELDS = (
    "first_name", "middle_name", "last_name", "birth_date", "sex", "civil_status",
    "blood_type", "address", "municipality", "province", "zip_code",
    "contact_number", "emergency_contact_name", "emergency_contact_relationship",
    "emergency_contact_number", "emergency_contact_address",
    "medical_conditions", "allergies",
)

# The two list-valued columns arrive as Python lists and are JSON-encoded, so
# they are handled apart from the plain text ones.
LIST_FIELDS = ("medical_conditions", "allergies")
SCALAR_FIELDS = tuple(field for field in PATIENT_FIELDS if field not in LIST_FIELDS)

EARLIEST_BIRTH_YEAR = 1900

# Republic Act 9994 defines a Philippine senior citizen as 60 years and over.
# The "Senior Citizen Patients" stat card on Screen 03 counts against this.
SENIOR_AGE = 60

# Lifecycle values permitted by the patients.status CHECK constraint. Records are
# never hard-deleted. Health Center Staff, the Doctor and the Administrator may
# move a record between Active and Inactive; only the Doctor may move one to or
# from Deceased -- see DOCTOR_ONLY_STATUS.
PATIENT_STATUSES = ("Active", "Inactive", "Deceased")

# THE ONE STATUS ONLY THE DOCTOR MAY SET, OR TAKE AWAY.
# Declaring a death is a clinical act, and at the RHU it is the doctor's: the
# field data gathered there is explicit that nurses and midwives do not declare
# death, and the Administrator is a barangay Kagawad, not a physician. So
# marking a patient Deceased needs clinical authority, and so does reversing it
# -- a record wrongly marked Deceased drops out of the broadcast audiences and
# the queue, and bringing a patient "back" is the same judgement made the other
# way. Active <-> Inactive is clerical and stays open to every role that holds
# Patient Records.
DOCTOR_ONLY_STATUS = "Deceased"

# status -> the badge class Screen 03/04 already define in their stylesheets.
STATUS_BADGE_CLASS = {
    "Active": "badge-active",
    "Inactive": "badge-inactive",
    "Deceased": "badge-archived",
}


def allowed_status_transitions(current_status):
    """The statuses a record currently in current_status may be moved to.

    Every status except the one it already holds, in PATIENT_STATUSES order --
    which yields exactly the three cases the status dialog offers:

        Active   -> Inactive, Deceased
        Inactive -> Active,   Deceased
        Deceased -> Active,   Inactive

    Reactivation is deliberately included. Marking a record Inactive or Deceased
    used to be a one-way door, so a mis-click on the wrong row left no way back
    through the UI; correcting an erroneous status is a normal clerical fix, not
    an exceptional one.

    An unrecognised status (a hand-edited row) yields all three, so the dialog
    still offers a way out rather than presenting no options at all.

    These are the transitions the lifecycle allows. Which of them a given person
    may make is status_change_needs_doctor()'s question, asked separately: a
    move to or from Deceased is legal and is still refused to everyone but the
    Doctor.
    """
    return tuple(status for status in PATIENT_STATUSES if status != current_status)


def can_declare_death(role):
    """Whether this role may mark a patient Deceased or reverse that status.

    Only the Doctor. Delegates to utils.roles.holds_clinical_authority(), the one
    definition every clinical permission in this system shares, so the rule for
    declaring death and the rule for diagnosing cannot come to name different
    roles. Asked of the signed-in account's STORED role, never of the request.
    """
    return holds_clinical_authority(role)


def status_change_needs_doctor(current_status, target_status):
    """Whether moving a record from one status to another is the Doctor's to make.

    True whenever either end is DOCTOR_ONLY_STATUS: setting Deceased, and taking
    it away again. False for Active <-> Inactive.
    """
    return DOCTOR_ONLY_STATUS in (current_status, target_status)


def get_patient_statuses(patient_ids):
    """{id: status} for the given ids. Ids with no row are simply absent.

    The status dialog decides what to offer from the page, but the page can be
    stale and a POST can be forged, so the server re-reads the current statuses
    before deciding whether a requested transition is legal.
    """
    ids = [int(patient_id) for patient_id in patient_ids]
    if not ids:
        return {}

    placeholders = ", ".join("?" for _ in ids)
    with db_connection() as conn:
        rows = conn.execute(
            f"SELECT id, status FROM patients WHERE id IN ({placeholders})", ids
        ).fetchall()
    return {row["id"]: row["status"] for row in rows}


def _parse_birth_date(birth_date):
    """A stored birth_date as a date, or None if it is absent or malformed."""
    if not birth_date:
        return None
    try:
        return datetime.strptime(str(birth_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def add_months(value, months):
    """value shifted forward by whole months, clamped to the month's last day.

    Needed to find an infant's month-anniversary before counting the leftover
    days: 31 January plus one month is 28 February, not an invalid 31 February.

    Public because models/immunizations.py needs exactly this to turn "due at 9
    months" into a date. Calendar months are not 4-week blocks, and a second
    implementation over there would drift from this one on precisely the dates
    that are hardest to notice -- a baby born on the 31st.
    """
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def calculate_age(birth_date, on_date=None):
    """Whole years between birth_date and on_date (default today), or None.

    The numeric age, used wherever age drives logic rather than display -- the
    "Senior Citizen Patients" card counts against SENIOR_AGE through this. For
    what a screen actually prints, see format_age(): under a year old this
    returns 0, which is exactly the reading that function exists to replace.
    """
    born = _parse_birth_date(birth_date)
    if born is None:
        return None

    reference = on_date or today()
    return (
        reference.year
        - born.year
        - ((reference.month, reference.day) < (born.month, born.day))
    )


def _unit(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def format_age(birth_date, on_date=None):
    """Age as every screen prints it, or None when birth_date is unusable (Task 15, D3).

    The ONE place patient age is turned into text: the profile, the patient list, the queue,
    the consultation form, the prints and the exports all read it. The vaccine schedule works
    in weeks, so a baby's age shows in weeks and days, exactly counted from the birth date:

        under 28 days               "12 days"
        28 days to under 16 weeks   "4 weeks 2 days"      ("0 days" is dropped)
        16 weeks to under 24 months "5 months 3 days"
        24 months to under 5 years  "2 years 6 months"    ("0 months" is dropped)
        5 years and over            "7 years"

    Months are calendar months (add_months(), the same helper the vaccine due dates use), not
    30-day blocks, so a baby born on the 31st is counted correctly. A birth date in the
    future keeps its negative-year rendering rather than being read as an infant;
    validate_patient_form() already refuses to store one.
    """
    years = calculate_age(birth_date, on_date)
    if years is None:
        return None
    if years < 0:
        return str(years)

    born = _parse_birth_date(birth_date)
    reference = on_date or today()
    total_days = (reference - born).days
    if total_days < 28:
        return _unit(total_days, "day")
    if total_days < 16 * 7:
        weeks, days = divmod(total_days, 7)
        return _unit(weeks, "week") + (f" {_unit(days, 'day')}" if days else "")

    months = (reference.year - born.year) * 12 + (reference.month - born.month)
    if reference.day < born.day:
        months -= 1
    if months < 24:
        days = (reference - add_months(born, months)).days
        return _unit(months, "month") + (f" {_unit(days, 'day')}" if days else "")
    if months < 60:
        rest = months % 12
        return _unit(months // 12, "year") + (f" {_unit(rest, 'month')}" if rest else "")
    return _unit(years, "year")


def parse_list_field(raw):
    """Read a medical_conditions / allergies value into a list of strings.

    Stored as a JSON array. Tolerates a plain string (returned as a single-item
    list) so a hand-edited row does not break the profile page.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [part.strip() for part in str(raw).split(",") if part.strip()]

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


def _full_name(row):
    parts = [row["first_name"], row["middle_name"], row["last_name"]]
    return " ".join(part for part in parts if part)


def _initials(row):
    first = (row["first_name"] or "").strip()
    last = (row["last_name"] or "").strip()
    return ((first[:1] or "") + (last[:1] or "")).upper() or "?"


def _display_address(row, keys=("address", "municipality", "province", "zip_code")):
    return ", ".join(str(row[key]).strip() for key in keys if row[key])


def _to_patient(row):
    """Copy a patients row into a dict and add the derived display fields."""
    patient = dict(row)
    patient["full_name"] = _full_name(row)
    patient["initials"] = _initials(row)
    # "age" is the display string, because that is all the three screens do with
    # it -- keeping the number here under that name is what let an infant print
    # as "0". The number is still available as age_years for anything that needs
    # to compare rather than print.
    patient["age"] = format_age(row["birth_date"])
    patient["age_years"] = calculate_age(row["birth_date"])
    patient["display_address"] = _display_address(row)
    patient["status_badge_class"] = STATUS_BADGE_CLASS.get(
        patient.get("status"), "badge-inactive"
    )
    # Where this status sits in PATIENT_STATUSES, for Screen 03's Sort control.
    # Sorting the Status column alphabetically would read Active, Deceased,
    # Inactive -- which is not an order anybody thinks of these three in, and puts
    # the most final of them in the middle. PATIENT_STATUSES is already the order
    # the rest of the system lists them in (the status dialog offers transitions
    # in it, allowed_status_transitions() walks it), so the sort reuses that one
    # declared order instead of inventing a second one in a template.
    patient["status_rank"] = (
        PATIENT_STATUSES.index(patient["status"])
        if patient.get("status") in PATIENT_STATUSES else None
    )
    patient["medical_conditions_list"] = parse_list_field(patient.get("medical_conditions"))
    patient["allergies_list"] = parse_list_field(patient.get("allergies"))
    return patient


# Screen 03's table carries a Last Visit column, which is the most recent
# consultation rather than a stored field -- hence the correlated subquery.
_LAST_VISIT = (
    "(SELECT MAX(c.consultation_date) FROM consultations c "
    "WHERE c.patient_id = p.id) AS last_visit"
)


def get_all_patients():
    """Every patient, ordered by surname then given name."""
    with db_connection() as conn:
        rows = conn.execute(
            f"""
        SELECT p.*, {_LAST_VISIT}
        FROM patients p
        ORDER BY p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE
        """
        ).fetchall()
    return [_to_patient(row) for row in rows]


def get_patient_by_id(patient_id):
    """One patient by primary key, or None if no such row exists."""
    with db_connection() as conn:
        row = conn.execute(
            f"SELECT p.*, {_LAST_VISIT} FROM patients p WHERE p.id = ?",
            (patient_id,),
        ).fetchone()
    return _to_patient(row) if row else None


# ---------------------------------------------------------------------------
# THE ADMINISTRATOR'S VIEW OF A PATIENT (Task 5c)
#
# Clinical data is for the care team only. The Administrator runs the system and
# is not part of anyone's care (RA 11166; RA 10173's "adequate, relevant and not
# excessive"; the minimum-necessary standard). So his screens read patients
# through these two functions, which select the demographic columns and nothing
# else: no contact numbers, no conditions or allergies, no blood type, no
# emergency contact, and no last-visit date. What is not selected cannot reach a
# page, an export or a print.
# ---------------------------------------------------------------------------
DEMOGRAPHIC_COLUMNS = (
    "id", "patient_id", "first_name", "middle_name", "last_name", "sex",
    "birth_date", "address", "status", "created_at",
)
_DEMOGRAPHIC_SELECT = "SELECT " + ", ".join(DEMOGRAPHIC_COLUMNS) + " FROM patients"


def _to_demographics(row):
    patient = dict(row)
    patient["full_name"] = _full_name(row)
    patient["initials"] = _initials(row)
    patient["age"] = format_age(row["birth_date"])
    patient["age_years"] = calculate_age(row["birth_date"])
    patient["display_address"] = (row["address"] or "").strip()
    patient["status_badge_class"] = STATUS_BADGE_CLASS.get(
        patient.get("status"), "badge-inactive"
    )
    patient["status_rank"] = (
        PATIENT_STATUSES.index(patient["status"])
        if patient.get("status") in PATIENT_STATUSES else None
    )
    return patient


def get_all_patients_demographics():
    """Every patient's demographic fields only, ordered as get_all_patients()."""
    with db_connection() as conn:
        rows = conn.execute(
            _DEMOGRAPHIC_SELECT
            + " ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE"
        ).fetchall()
    return [_to_demographics(row) for row in rows]


def get_patient_demographics(patient_id):
    """One patient's demographic fields only, or None."""
    with db_connection() as conn:
        row = conn.execute(_DEMOGRAPHIC_SELECT + " WHERE id = ?", (patient_id,)).fetchone()
    return _to_demographics(row) if row else None


def get_patient_stats():
    """Counts behind the four stat cards on Screen 03.

    The windows are clinic-local: "this month" means the month it is in San
    Francisco, Surigao del Norte, not wherever the server happens to be. They are
    built in Python via utils.dates and converted to UTC instants before being
    compared, because created_at is written by SQLite's CURRENT_TIMESTAMP and is
    therefore UTC. Both sides of every comparison are then the same instant
    expressed the same way -- previously SQLite's own date('now') supplied the
    boundary, which pinned these counts to UTC midnight rather than Manila's.
    """
    with db_connection() as conn:

        total = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]

        month_start, next_month_start = month_bounds()
        new_this_month = conn.execute(
            "SELECT COUNT(*) FROM patients WHERE created_at >= ? AND created_at < ?",
            (day_start_utc(month_start), day_start_utc(next_month_start)),
        ).fetchone()[0]

        # Registered since midnight, clinic time. The Staff dashboard's "New Patient
        # Registrations / Today" card reads this; same boundary treatment as the
        # month window above, so the two cannot disagree about which day a record
        # written late in the evening belongs to.
        new_today = conn.execute(
            "SELECT COUNT(*) FROM patients WHERE created_at >= ?",
            (day_start_utc(today()),),
        ).fetchone()[0]

        new_last_30 = conn.execute(
            "SELECT COUNT(*) FROM patients WHERE created_at >= ?",
            (day_start_utc(days_ago(30)),),
        ).fetchone()[0]

        previous_30 = conn.execute(
            "SELECT COUNT(*) FROM patients WHERE created_at >= ? AND created_at < ?",
            (day_start_utc(days_ago(60)), day_start_utc(days_ago(30))),
        ).fetchone()[0]

        birth_dates = [row[0] for row in conn.execute("SELECT birth_date FROM patients")]

    senior_count = sum(
        1
        for birth_date in birth_dates
        if (calculate_age(birth_date) or 0) >= SENIOR_AGE
    )

    change_pct = None
    if previous_30:
        change_pct = round((new_last_30 - previous_30) / previous_30 * 100)

    return {
        "total_patients": total,
        "new_today": new_today,
        "new_this_month": new_this_month,
        "new_last_30_days": new_last_30,
        "previous_30_days": previous_30,
        "new_30_day_change_pct": change_pct,
        "senior_count": senior_count,
        "senior_share_pct": round(senior_count / total * 100) if total else 0,
        # Screen 03 shows a "Prenatal Patients" card, but nothing in the schema
        # records a pregnancy. Reported as 0 rather than invented; it needs a
        # real data source (a prenatal flag or an appointment type) before it
        # can show anything else.
        "prenatal_count": 0,
    }


# ---------------------------------------------------------------------------
# REPORTING
#
# Screen 10's patient charts. Everything below reads the roster through
# get_all_patients() and the derived fields already on it -- age_years from
# calculate_age(), the parsed condition list -- rather than issuing its own SQL.
#
# That is the point: a second query that counted seniors with its own `WHERE
# birth_date <= ...` would eventually disagree with the "Senior Citizen Patients"
# card on Screen 03, and the two would both look right in isolation. Reading the
# same rows the rest of the project reads makes agreement structural.
# ---------------------------------------------------------------------------

# The bands Screen 10's Age Distribution chart plots. Upper bound None means
# open-ended, so every patient with a usable birthdate lands in exactly one band
# and the bars sum to the number of patients whose age is known.
AGE_BANDS = (
    ("0-9", 0, 9), ("10-19", 10, 19), ("20-29", 20, 29), ("30-39", 30, 39),
    ("40-49", 40, 49), ("50-59", 50, 59), ("60-69", 60, 69), ("70+", 70, None),
)


def get_age_distribution(patients=None):
    """Patients per age band, plus how many have no usable birthdate.

    A patient with an unparseable or missing birth_date is counted in `unknown`
    rather than dropped into a band -- a chart whose bars silently omit rows
    misreports the population it claims to describe.
    """
    if patients is None:
        patients = get_all_patients()

    counts = {label: 0 for label, _, _ in AGE_BANDS}
    unknown = 0
    for patient in patients:
        age = patient.get("age_years")
        if age is None or age < 0:
            unknown += 1
            continue
        for label, low, high in AGE_BANDS:
            if age >= low and (high is None or age <= high):
                counts[label] += 1
                break

    return {
        "bands": [
            {"label": label, "count": counts[label]} for label, _, _ in AGE_BANDS
        ],
        "unknown": unknown,
        "known": sum(counts.values()),
    }


def get_sex_distribution(patients=None):
    """Female / male / unrecorded counts with their shares of the roster.

    Percentages are of the whole roster, not of the two named sexes, so the
    figures on the chart's legend add up to the total the panel prints above it.
    """
    if patients is None:
        patients = get_all_patients()

    total = len(patients)
    counts = {"Female": 0, "Male": 0}
    unrecorded = 0
    for patient in patients:
        sex = (patient.get("sex") or "").strip()
        if sex in counts:
            counts[sex] += 1
        else:
            unrecorded += 1

    def share(value):
        return round(value / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "female": counts["Female"],
        "male": counts["Male"],
        "unrecorded": unrecorded,
        "female_pct": share(counts["Female"]),
        "male_pct": share(counts["Male"]),
        "unrecorded_pct": share(unrecorded),
    }


def get_condition_counts(patients=None, conditions=CONDITION_OPTIONS, min_age=None,
                         *, viewer_role):
    """How many patients have each recorded chronic condition.

    Counted from the parsed medical_conditions list, so a patient with both
    Hypertension and Diabetes is counted under each -- these are not segments of
    a pie and are not expected to sum to the roster.

    Only the form's own CONDITION_OPTIONS vocabulary is counted by default.
    The field also accepts free text (the "other" note), and that text is
    deliberately left out: 'High blood' and 'Hypertension' are the same illness
    written two ways, and a chart that treated them as two conditions would be
    reporting the data-entry habit rather than the population. The count of
    patients carrying only free-text conditions is reported separately as
    `other_only` so the omission is visible instead of silent.

    `min_age` narrows to a cohort -- the Senior Citizen panel passes SENIOR_AGE.

    `viewer_role` HAS NO DEFAULT. For the Administrator and the Barangay Official a
    condition with 1 to 4 patients is folded into one Other row (Task 5d, D1; see
    utils/small_counts.py). A condition with none stays named at 0. `cohort_size`,
    `other_only` and `with_any` are totals and are never changed.
    """
    if patients is None:
        patients = get_all_patients()

    if min_age is not None:
        patients = [
            patient for patient in patients
            if (patient.get("age_years") is not None and patient["age_years"] >= min_age)
        ]

    counts = {condition: 0 for condition in conditions}
    other_only = 0
    for patient in patients:
        recorded = patient.get("medical_conditions_list") or []
        matched = False
        for condition in conditions:
            if condition in recorded:
                counts[condition] += 1
                matched = True
        if recorded and not matched:
            other_only += 1

    with_any = sum(1 for patient in patients if patient.get("medical_conditions_list"))
    return {
        "cohort_size": len(patients),
        "counts": fold_small_counts(
            [{"condition": condition, "count": counts[condition]}
             for condition in conditions],
            viewer_role, label_key="condition", sum_keys=("count",),
        ),
        "other_only": other_only,
        "with_any": with_any,
        # Task 5e (D2): the same two counts as a viewer may read them. Under 5 and
        # above 0 they read "Fewer than 5" for the Administrator and the Official.
        "other_only_shown": shown_count(other_only, viewer_role),
        "with_any_shown": shown_count(with_any, viewer_role),
    }


def get_registration_trend(months=6, end=None, start=None):
    """New patient registrations per clinic month, oldest first.

    The window boundaries are built in Python and converted to UTC instants
    before being compared, for the reason get_patient_stats() spells out:
    created_at is written by SQLite's CURRENT_TIMESTAMP and is therefore UTC,
    while "August" means August in San Francisco, Surigao del Norte.

    Months with no registrations are returned as zeros rather than omitted --
    a trend line that skipped its empty months would compress the gap and read
    as steady activity through a period when nobody registered at all.

    `start` alongside `end` asks for a specific range instead of the last
    `months`. The two parameters keep the meaning they already had -- `end` was
    always the day whose month the window finishes on -- so resolve_range() reads
    an existing call and a ranged one the same way and no caller had to change.
    """
    window = resolve_range(start=start, end=end, months=months)
    # Each month's bar is clipped to the range, so the first and last may be part
    # months. A report for 1-10 August whose August bar counted the whole month
    # would put a figure on the chart that is not in the report -- see the same
    # note in get_consultation_stats(). The clamp is a no-op on the default
    # window, whose bounds are month boundaries already.
    lo_text, hi_text = range_bounds_utc(window)
    with db_connection() as conn:
        trend = []
        for month_start, next_start, label in window["months"]:
            bar_lo = max(day_start_utc(month_start), lo_text)
            bar_hi = min(day_start_utc(next_start), hi_text)
            count = conn.execute(
                "SELECT COUNT(*) FROM patients WHERE created_at >= ? AND created_at < ?",
                (bar_lo, bar_hi),
            ).fetchone()[0] if bar_lo < bar_hi else 0
            trend.append(
                {"month": month_start.strftime("%Y-%m"), "label": label, "count": count}
            )
    return trend


def count_registered_in(window):
    """Patients registered inside a resolved range.

    Counted against the range's own day boundaries rather than by summing the
    trend above: the trend counts whole months, and a range that starts on the
    12th would otherwise report the registrations from the 1st to the 11th as
    though the operator had asked for them.
    """
    lo, hi = range_bounds_utc(window)
    with db_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM patients WHERE created_at >= ? AND created_at < ?",
            (lo, hi),
        ).fetchone()[0]
    return count


def get_patient_report(months=6, start=None, end=None, *, viewer_role):
    """Everything Screen 10 shows about patients, from one read of the roster.

    get_all_patients() is called once and handed to each breakdown, so the age
    bands, the sex split and the condition counts all describe the same roster --
    and the headline totals come straight from get_patient_stats(), the function
    Screen 03's own stat cards use.

    WHAT A DATE RANGE CAN AND CANNOT NARROW HERE
    --------------------------------------------
    Registrations are an event and are ranged: `registration_trend` and the
    `window` block below both answer "who joined the register between these
    dates".

    The age bands, the sex split and the condition counts are not, and are
    deliberately left describing the whole roster. They answer "who is registered
    here", which is a standing fact about today and not something that happened
    during a period. Narrowing them to a range would silently turn them into
    "the age profile of patients who happened to register in June" -- a real but
    completely different figure, and one nobody reading a chart headed "Patient
    Age Distribution" would take it for. The screens label these as whole-roster
    for that reason; see `window["roster_is_ranged"]`, which is always False and
    exists so a template can state it rather than assume it.
    """
    patients = get_all_patients()
    stats = get_patient_stats()
    window = resolve_range(start=start, end=end, months=months)
    return {
        "stats": stats,
        "total": len(patients),
        "age_distribution": get_age_distribution(patients),
        "sex_distribution": get_sex_distribution(patients),
        "conditions": get_condition_counts(patients, viewer_role=viewer_role),
        "senior_conditions": get_condition_counts(
            patients, min_age=SENIOR_AGE, viewer_role=viewer_role),
        "senior_count": stats["senior_count"],
        "senior_share_pct": stats["senior_share_pct"],
        "registration_trend": get_registration_trend(months, end=end, start=start),
        "senior_age": SENIOR_AGE,
        "window": {
            "start": window["start"],
            "end": window["end"],
            "custom": window["custom"],
            "registered": count_registered_in(window),
            "roster_is_ranged": False,
        },
    }


def collect_list_field(selected, note):
    """Turn the checkbox chips plus the free-text note into a JSON-ready list.

    The form's "None" chip is a UI affordance, not a value: choosing it means
    the list is empty, so it is dropped rather than stored as the string "None".
    """
    items = [str(item).strip() for item in selected if str(item).strip() and str(item).strip() != "None"]
    note = (note or "").strip()
    if note:
        items.append(note)
    return items


def validate_patient_form(values):
    """Server-side validation. Returns {field: message}; empty means valid.

    Runs independently of the browser -- the form carries `novalidate`, and a
    POST can arrive without ever touching the page.
    """
    errors = {}

    for field, message in REQUIRED_FIELDS.items():
        if not (values.get(field) or "").strip():
            errors[field] = message

    birth_date = (values.get("birth_date") or "").strip()
    if birth_date and "birth_date" not in errors:
        try:
            parsed = datetime.strptime(birth_date, "%Y-%m-%d").date()
        except ValueError:
            errors["birth_date"] = "Enter a valid date in YYYY-MM-DD format."
        else:
            if parsed > today():
                errors["birth_date"] = "Birthdate cannot be in the future."
            elif parsed.year < EARLIEST_BIRTH_YEAR:
                errors["birth_date"] = f"Birthdate cannot be earlier than {EARLIEST_BIRTH_YEAR}."

    # Constrained fields: reject anything the form does not itself offer.
    for field, allowed, label in (
        ("civil_status", CIVIL_STATUSES, "civil status"),
        ("sex", SEXES, "gender"),
        ("municipality", MUNICIPALITIES, "municipality"),
        ("province", PROVINCES, "province"),
        ("emergency_contact_relationship", EMERGENCY_RELATIONSHIPS, "relationship"),
    ):
        value = (values.get(field) or "").strip()
        if value and field not in errors and value not in allowed:
            errors[field] = f"Choose a {label} from the list."

    blood_type = (values.get("blood_type") or "").strip()
    if blood_type and blood_type not in BLOOD_TYPES:
        errors["blood_type"] = "Choose a blood type from the list."

    emergency_number = (values.get("emergency_contact_number") or "").strip()
    if emergency_number and "emergency_contact_number" not in errors:
        if not is_valid_ph_mobile(emergency_number):
            errors["emergency_contact_number"] = (
                "Enter a valid Philippine mobile number, e.g. 0917-123-4567."
            )

    contact_number = (values.get("contact_number") or "").strip()
    if contact_number and not is_valid_ph_mobile(contact_number):
        errors["contact_number"] = (
            "Enter a valid Philippine mobile number, e.g. 0917-123-4567."
        )

    zip_code = (values.get("zip_code") or "").strip()
    if zip_code and not (zip_code.isdigit() and len(zip_code) == 4):
        errors["zip_code"] = "Zip code must be 4 digits, e.g. 8401."

    return errors


# ---------------------------------------------------------------------------
# THE POSSIBLE-DUPLICATE CHECK (Task 20)
#
# The one duplicate check in the system. Register Patient runs it before a new
# record is saved, and Edit Patient runs it when a name or the birth date
# changes (routes/patient_views.py). It only warns: two residents really can
# share a name and a birthday, so the operator decides, and nothing is merged.
#
# Names are compared after normalize_name(), so "De la Cruz", "Dela Cruz" and
# "Delacruz" are one name, as are "Ma. Cristina" and "Maria Cristina", and
# "Peña" and "Pena". The three rules are in _match_rule().
# ---------------------------------------------------------------------------

# Suffixes typed inside a name field ("Juan Jr.", "Dela Cruz III"). There is no
# suffix column, so these are dropped before names are compared.
NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv"})
# What separates the parts of a name: spaces, hyphens, periods, apostrophes, commas.
_NAME_SEPARATORS = re.compile(r"[\s.\-'‘’`,]+")

# Rule B's thresholds, for difflib.SequenceMatcher().ratio() on normalized names.
LAST_NAME_SIMILARITY = 0.85
FIRST_NAME_SIMILARITY = 0.80
# "juan" and "juancarlos": one first name starting with the other counts as
# similar when the shorter one has at least this many letters.
FIRST_NAME_PREFIX_MIN = 3

# The most matches the warning lists.
MAX_DUPLICATE_MATCHES = 5

# Rule -> (order, the reason the warning prints). Lower order is the stronger match.
DUPLICATE_RULES = {
    "A": (0, "Same name and birth date"),
    "B": (1, "Similar name, same birth date"),
    "C": (2, "Same name, birth date may be mistyped"),
}


def normalize_name(value, first_name=False):
    """A name as the duplicate check compares it.

    Lowercase, accents removed (ñ -> n, é -> e), suffixes dropped, and spaces,
    hyphens, periods and apostrophes removed: "De la Cruz Jr." -> "delacruz".
    With first_name=True a leading "Ma." or "Ma" is read as "Maria", the common
    Filipino abbreviation: "Ma. Cristina" -> "mariacristina".

    A name that is nothing but a suffix keeps it, so it is never emptied.
    """
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    parts = [part for part in _NAME_SEPARATORS.split(text.strip().lower()) if part]
    without_suffixes = [part for part in parts if part not in NAME_SUFFIXES]
    if without_suffixes:
        parts = without_suffixes
    if first_name and parts and parts[0] == "ma":
        parts[0] = "maria"
    return "".join(parts)


def _similarity(first, second):
    return difflib.SequenceMatcher(None, first, second).ratio()


def _is_neighbour_swap(first, second):
    """True when the two differ only by two neighbouring letters swapped ("jhon", "john")."""
    if len(first) != len(second) or first == second:
        return False
    differ = [index for index, (a, b) in enumerate(zip(first, second)) if a != b]
    return (len(differ) == 2 and differ[1] == differ[0] + 1
            and first[differ[0]] == second[differ[1]]
            and first[differ[1]] == second[differ[0]])


def _first_names_similar(first, second):
    """Rule B's first-name test, on normalized first names."""
    if _similarity(first, second) >= FIRST_NAME_SIMILARITY:
        return True
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= FIRST_NAME_PREFIX_MIN and longer.startswith(shorter):
        return True
    # A common typing slip that the ratio scores at 0.75 for a four-letter name.
    return _is_neighbour_swap(first, second)


def _birth_date_mistyped(typed, stored):
    """Rule C's date test: the same year, and the day and month swapped, or one
    digit different in the day or the month. Both are dates; equal dates are not."""
    if typed == stored or typed.year != stored.year:
        return False
    if (typed.month, typed.day) == (stored.day, stored.month):
        return True
    typed_digits = f"{typed.month:02d}{typed.day:02d}"
    stored_digits = f"{stored.month:02d}{stored.day:02d}"
    return sum(a != b for a, b in zip(typed_digits, stored_digits)) == 1


def _match_rule(typed, stored):
    """'A', 'B', 'C' or None for one stored patient, strongest rule first.

    A  same normalized first name, same normalized last name, same birth date.
    B  same birth date, last names >= LAST_NAME_SIMILARITY alike, and first names
       similar (>= FIRST_NAME_SIMILARITY, one starts with the other, or two
       neighbouring letters swapped).
    C  same normalized first and last name, and the birth date has the day and
       month swapped or one digit different in the day or the month, same year.
    """
    same_names = typed["first"] == stored["first"] and typed["last"] == stored["last"]
    same_date = typed["birth_date"] == stored["birth_date"]
    if same_names and same_date:
        return "A"
    if same_date and _similarity(typed["last"], stored["last"]) >= LAST_NAME_SIMILARITY \
            and _first_names_similar(typed["first"], stored["first"]):
        return "B"
    if same_names and _birth_date_mistyped(typed["birth_date"], stored["birth_date"]):
        return "C"
    return None


def find_possible_duplicates(first_name, middle_name, last_name, birth_date,
                             exclude_patient_id=None):
    """Patients who may be the same person as the one typed, strongest first.

    Records of every status are searched, Deceased and Inactive included: a
    duplicate of either is still a duplicate. `exclude_patient_id` is the row id
    of the record being edited, so it never matches itself.

    The database narrows the search to the birth year, which every rule needs,
    and the names are compared here. Only demographic columns are read.

    At most MAX_DUPLICATE_MATCHES, ordered by rule (A, B, then C), then a
    matching middle name first, then the closer name, then the patient ID. Each
    is a dict: id, patient_id, full_name, birth_date, sex, address, status,
    status_badge_class, rule and reason (the plain words the warning prints).
    The middle name is not one of the rules: it only orders the list.
    """
    born = _parse_birth_date(birth_date)
    typed = {
        "first": normalize_name(first_name, first_name=True),
        "middle": normalize_name(middle_name),
        "last": normalize_name(last_name),
        "birth_date": born,
    }
    if born is None or not typed["first"] or not typed["last"]:
        return []

    sql = (
        "SELECT id, patient_id, first_name, middle_name, last_name, birth_date, "
        "sex, address, status FROM patients WHERE substr(birth_date, 1, 4) = ?"
    )
    parameters = [f"{born.year:04d}"]
    if exclude_patient_id is not None:
        sql += " AND id != ?"
        parameters.append(int(exclude_patient_id))
    with db_connection() as conn:
        rows = conn.execute(sql, parameters).fetchall()

    found = []
    for row in rows:
        stored = {
            "first": normalize_name(row["first_name"], first_name=True),
            "middle": normalize_name(row["middle_name"]),
            "last": normalize_name(row["last_name"]),
            "birth_date": _parse_birth_date(row["birth_date"]),
        }
        if stored["birth_date"] is None:
            continue
        rule = _match_rule(typed, stored)
        if rule is None:
            continue
        order, reason = DUPLICATE_RULES[rule]
        middle_matches = bool(typed["middle"]) and typed["middle"] == stored["middle"]
        closeness = (_similarity(typed["first"], stored["first"])
                     + _similarity(typed["last"], stored["last"]))
        found.append(((order, not middle_matches, -closeness, row["patient_id"]), {
            "id": row["id"],
            "patient_id": row["patient_id"],
            "full_name": _full_name(row),
            "birth_date": row["birth_date"],
            "sex": row["sex"],
            "address": (row["address"] or "").strip(),
            "status": row["status"],
            "status_badge_class": STATUS_BADGE_CLASS.get(row["status"], "badge-inactive"),
            "rule": rule,
            "reason": reason,
        }))

    found.sort(key=lambda pair: pair[0])
    return [match for _, match in found[:MAX_DUPLICATE_MATCHES]]


def _build_record(values):
    """Normalise submitted form values into the column values to store.

    Shared by create_patient() and update_patient() so an insert and an edit can
    never normalise the same field differently.
    """
    record = {field: (values.get(field) or "").strip() or None for field in SCALAR_FIELDS}

    # "Unknown" blood type is the absence of a value.
    if record["blood_type"] == "Unknown":
        record["blood_type"] = None

    # Store phone numbers in the same 09XXXXXXXXX shape as the existing rows.
    for field in ("contact_number", "emergency_contact_number"):
        if record[field]:
            record[field] = to_local_ph_mobile(record[field]) or record[field]

    # These two arrive as Python lists from the form handler.
    record["medical_conditions"] = json.dumps(values.get("medical_conditions") or [])
    record["allergies"] = json.dumps(values.get("allergies") or [])
    return record


def update_patient(patient_id, values, audit=None):
    """Overwrite one patient's form-collected fields. Returns rows affected.

    Deliberately leaves patient_id, created_at and status alone: the identifier
    and the registration date are historical fact, and the lifecycle status is
    changed through the separate deactivate/deceased flow, not by editing.

    `audit(conn, changed_fields)` is called before the commit when at least one
    field changed, so the audit entry commits with the edit.
    """
    record = _build_record(values)
    assignments = ", ".join(f"{field} = ?" for field in PATIENT_FIELDS)
    parameters = [record[field] for field in PATIENT_FIELDS] + [patient_id]

    with db_connection() as conn:
        before = conn.execute(
            "SELECT * FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()
        cursor = conn.execute(
            f"UPDATE patients SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            parameters,
        )
        affected = cursor.rowcount
        if audit and before is not None:
            changed = [field for field in PATIENT_FIELDS
                       if (before[field] or None) != (record[field] or None)]
            if changed:
                audit(conn, changed)
        conn.commit()
    return affected


def set_patient_status(patient_ids, status, audit=None):
    """Move one or more patients to a lifecycle status. Returns rows changed.

    This is the whole of the Archive action on Screen 03. Records are never
    hard-deleted -- medical records are retained even after a patient dies -- so
    archiving is this UPDATE and nothing else: no row is removed, patient_id and
    created_at are untouched, and only updated_at moves alongside the status.

    The row-level icon and the bulk bar both arrive here as a list of ids, so a
    single archive is just the one-element case of the bulk one; there is no
    second code path that could drift.

    `AND status != ?` makes the count honest. SQLite's rowcount reports rows
    matched, not rows changed, so without it re-archiving an already-Inactive
    patient would claim an update that did not happen -- and would bump
    updated_at for a write that changed nothing.

    `audit(conn, [(patient_id, old_status), ...])` is called before the commit
    with the rows that actually changed.
    """
    if status not in PATIENT_STATUSES:
        raise ValueError(
            f"{status!r} is not a patient status; expected one of {PATIENT_STATUSES}."
        )

    ids = [int(patient_id) for patient_id in patient_ids]
    if not ids:
        return 0

    placeholders = ", ".join("?" for _ in ids)
    with db_connection() as conn:
        # Which rows will change, and from what, read inside the same
        # transaction so the audit entries name exactly the rows updated.
        moving = conn.execute(
            f"SELECT id, status FROM patients WHERE id IN ({placeholders}) AND status != ?",
            ids + [status],
        ).fetchall()
        cursor = conn.execute(
            f"""
        UPDATE patients
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id IN ({placeholders}) AND status != ?
        """,
            [status] + ids + [status],
        )
        affected = cursor.rowcount
        if audit and moving:
            audit(conn, [(row["id"], row["status"]) for row in moving])
        conn.commit()
    return affected


def create_patient(values, audit=None):
    """Insert a patient and return its new primary key.

    created_at is left to the column's DEFAULT CURRENT_TIMESTAMP, and status is
    set explicitly to 'Active' -- new records always start active.

    `audit(conn, new_id)` is called before the commit.
    """
    record = _build_record(values)

    columns = ["patient_id"] + list(PATIENT_FIELDS) + ["status"]
    placeholders = ", ".join("?" for _ in columns)
    parameters = [generate_next_patient_id()] + [record[f] for f in PATIENT_FIELDS] + ["Active"]

    with db_connection() as conn:
        cursor = conn.execute(
            f"INSERT INTO patients ({', '.join(columns)}) VALUES ({placeholders})",
            parameters,
        )
        new_id = cursor.lastrowid
        if audit:
            audit(conn, new_id)
        conn.commit()
    return new_id


def generate_next_patient_id():
    """Next free identifier in the existing PAT-### series.

    Reads the highest number currently in use rather than counting rows, so a
    gap left by an earlier record cannot cause a UNIQUE collision. Zero-padded
    to three digits; a series past PAT-999 simply grows wider.
    """
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT patient_id FROM patients WHERE patient_id LIKE 'PAT-%'"
        ).fetchall()

    highest = 0
    for row in rows:
        suffix = str(row["patient_id"]).split("-", 1)[1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))

    return f"PAT-{highest + 1:03d}"
