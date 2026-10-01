"""Patient record queries.

Functions here return plain dicts rather than sqlite3.Row objects, because the
Patient Records and Patient Profile screens need derived values (age, full name,
composed address) that do not exist as columns. sqlite3.Row is read-only, so the
row is copied into a dict and the derived keys are added alongside.
"""
import calendar
import json
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
# migrate_correct_patient_location.py, which repaired the eleven it reached.
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


def format_age(birth_date, on_date=None):
    """Age as every screen prints it, or None when birth_date is unusable.

    The one place patient age is turned into text. Screens 03 and 04 render this
    string directly, so their Age column, header meta grid and Personal
    Information grid cannot drift apart.

    One year and over returns the same whole-year count those screens have
    always shown ("63"), so no existing record's display changes. Under one year
    returns months with the leftover days ("4 months, 6 days"), and under one
    month returns days alone ("21 days") so a newborn never reads as "0 months".

    The days are carried alongside the months on purpose. The instructor's point
    was vaccination scheduling, and the Philippine EPI schedule places doses at
    6, 10 and 14 weeks -- month-only precision cannot tell those apart, and all
    three would otherwise read as "1 month" or "2 months".

    A birthdate in the future keeps its existing negative-year rendering rather
    than being reinterpreted as an infant; validate_patient_form() already
    refuses to store one, so this only concerns hand-edited rows.
    """
    years = calculate_age(birth_date, on_date)
    if years is None:
        return None
    if years != 0:
        return str(years)

    born = _parse_birth_date(birth_date)
    reference = on_date or today()

    months = (reference.year - born.year) * 12 + (reference.month - born.month)
    if reference.day < born.day:
        months -= 1
    days = (reference - add_months(born, months)).days

    if months == 0:
        return f"{days} day{'' if days == 1 else 's'}"

    text = f"{months} month{'' if months == 1 else 's'}"
    if days:
        text += f", {days} day{'' if days == 1 else 's'}"
    return text


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


def get_condition_counts(patients=None, conditions=CONDITION_OPTIONS, min_age=None):
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

    return {
        "cohort_size": len(patients),
        "counts": [
            {"condition": condition, "count": counts[condition]}
            for condition in conditions
        ],
        "other_only": other_only,
        "with_any": sum(
            1 for patient in patients if patient.get("medical_conditions_list")
        ),
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


def get_patient_report(months=6, start=None, end=None):
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
        "conditions": get_condition_counts(patients),
        "senior_conditions": get_condition_counts(patients, min_age=SENIOR_AGE),
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


def find_possible_duplicates(first_name, last_name, birth_date):
    """Existing patients sharing a name and birthdate, matched case-insensitively.

    Used for a non-blocking warning: two residents genuinely can share a name and
    birthday, so this informs the operator rather than refusing the record.
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT id, patient_id, first_name, last_name, birth_date
        FROM patients
        WHERE LOWER(TRIM(first_name)) = LOWER(TRIM(?))
          AND LOWER(TRIM(last_name))  = LOWER(TRIM(?))
          AND birth_date = ?
        ORDER BY patient_id
        """,
            (first_name or "", last_name or "", birth_date or ""),
        ).fetchall()
    return [dict(row) for row in rows]


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
