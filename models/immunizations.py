"""Immunisation records, and the child's standing against the DOH EPI schedule.

Doses are administered during a consultation -- that is where a health worker
actually holds the syringe -- so this module is written up from the consultation
form and read back by the Patient Profile, the queue and the dashboards. It is
the Pass 3b half of the hook models/consultations.py describes.


WHY THE SCHEDULE IS A CODE CONSTANT AND THE DOSES ARE A TABLE
-------------------------------------------------------------
Two different kinds of fact, stored two different ways on purpose:

* EPI_SCHEDULE is *national policy*. It is the Department of Health's Expanded
  Program on Immunization infant schedule -- the same for every barangay in the
  country, changed by DOH circular every few years, and never by anything a user
  of this system does. There is no screen to edit it and there must not be: a
  health worker who could redefine the national schedule from the UI could make
  a defaulting child look up to date. Putting it in a table would mean seeding
  it, migrating it to change it, and *still* keeping the vocabulary in code so
  the form and the validator could name a vaccine -- two sources that can
  disagree, for a list that does not vary between installations.

  It is also exactly how every other controlled vocabulary in this project is
  already held: CIVIL_STATUSES, BLOOD_TYPES, APPOINTMENT_STATUSES and
  NUMERIC_LIMITS are all module constants that the template renders from and the
  validator checks against. One tuple, one place to correct, one place to extend
  when the team learns the health center also gives Rotavirus or Vitamin A.

* The `immunizations` table is *this child's history* -- a per-patient clinical
  fact that only exists because someone recorded it. That has to be stored, and
  it carries who gave it, when, and during which consultation.

A dose recorded against a code that a later schedule revision drops is not lost:
get_immunization_status() reports it under "extra_records" rather than silently
dropping it, because a vaccination that happened, happened.


ONE CALCULATION, READ EVERYWHERE
--------------------------------
get_immunization_status() is the only place that decides whether a dose is
Completed, Due Now, Upcoming or Overdue. The profile tab, the queue badge, the
check-in message and the dashboard card all read its output; none of them works
it out again. This is the same arrangement get_low_stock_alert() has for stock
and _apply_queue_flow() has for the queue, and for the same reason -- a second
implementation would eventually disagree with the first about a real child.


A DOSE GIVEN SOMEWHERE ELSE IS STILL A DOSE
-------------------------------------------
Capstone testing found an infant sitting at Overdue for doses the child had
already been given -- at another hospital, in another barangay. The parent said
so at the counter and there was nowhere to put it. The only way to clear the
Overdue reading was to tick "given today", which would have recorded another
facility's vaccination as this health center's own work, on the wrong date, under
the name of a health worker who never gave it.

So every dose now carries a `source`, and it holds one of exactly two values:

    SOURCE_ADMINISTERED   this health center gave it
    SOURCE_REPORTED       it was reported to us, at a real consultation, as
                          already given somewhere else

Two rules follow from that, and they pull in opposite directions on purpose.

    IT COUNTS.   _dose_status() asks only whether a dose is on file, not where it
                 came from. A reported dose is Completed, the child stops showing
                 as Overdue, and the coverage figures count them as protected --
                 which they are. Grading the two differently would put this
                 module back to calling a vaccinated child a defaulter, which is
                 the defect it was changed to fix.

    IT IS SAID.  Every screen that prints a dose says which kind it is, and none
                 of them may blend the two. dose_source_label() is the one place
                 those words are written, so the profile row, the consultation
                 form, the visit panel and the audit line cannot each invent a
                 different phrase for the same fact.

The date follows the same honesty rule the rest of this project keeps. A reported
dose may have no date at all -- a parent who remembers the hospital may not
remember the day -- and the column is nullable for exactly that case. A dose this
health center administered still must say when: the table's CHECK enforces that
half, so the nullability is one-sided rather than a general loosening. Anything
reading date_administered therefore has to cope with None, and `date_known` on
each schedule entry is what a screen asks rather than testing the date itself.

This is the split HL7 FHIR draws with Immunization.primarySource, and it is the
same instinct the separation from models/general_vaccinations.py comes from: say
what is actually known, and never let a record claim more than that.
"""
from datetime import datetime, timedelta

from database.connection import get_db
from models.consultations import PEDIATRIC_AGE_YEARS, as_date
from models.patients import add_months, calculate_age
from utils.dates import display_date, resolve_range, today

# ---------------------------------------------------------------------------
# The Department of Health Expanded Program on Immunization infant schedule.
#
# (code, vaccine, protects_against, dose_number, total_doses, due_value,
#  due_unit, timing_note)
#
# `code` is the stable identity stored in the immunizations table; `vaccine` is
# what the screens print. They are kept apart so renaming a vaccine for display
# -- "Measles-Rubella" to "MR", say -- does not orphan every record already
# written, and so a stored row is never a display string that someone edited.
#
# Weeks and months are both real units here rather than everything being
# normalised to days: the DOH schedule itself says "6 weeks" and "9 months", and
# 9 calendar months is not 39 weeks. due_date_for() resolves each against the
# child's actual birthday using the same add_months() the age display uses.
#
# Ordered by due age, then by the order a health worker gives them at one visit,
# so every screen that iterates this shows the schedule the way it is worked.
# ---------------------------------------------------------------------------
EPI_SCHEDULE = (
    ("BCG",   "BCG",          "Tuberculosis",                  1, 1,  0, "weeks",  "At birth"),
    ("HEPB",  "Hepatitis B",  "Hepatitis B",                   1, 1,  0, "weeks",  "At birth, ideally within 24 hours"),

    ("PENTA", "Pentavalent",  "Diphtheria, tetanus, pertussis, hepatitis B, Hib", 1, 3,  6, "weeks", "6 weeks"),
    ("OPV",   "OPV",          "Poliomyelitis (oral)",          1, 3,  6, "weeks",  "6 weeks"),
    ("PCV",   "PCV",          "Pneumococcal disease",          1, 3,  6, "weeks",  "6 weeks"),

    ("PENTA", "Pentavalent",  "Diphtheria, tetanus, pertussis, hepatitis B, Hib", 2, 3, 10, "weeks", "10 weeks"),
    ("OPV",   "OPV",          "Poliomyelitis (oral)",          2, 3, 10, "weeks",  "10 weeks"),
    ("PCV",   "PCV",          "Pneumococcal disease",          2, 3, 10, "weeks",  "10 weeks"),

    ("PENTA", "Pentavalent",  "Diphtheria, tetanus, pertussis, hepatitis B, Hib", 3, 3, 14, "weeks", "14 weeks"),
    ("OPV",   "OPV",          "Poliomyelitis (oral)",          3, 3, 14, "weeks",  "14 weeks"),
    ("PCV",   "PCV",          "Pneumococcal disease",          3, 3, 14, "weeks",  "14 weeks"),
    ("IPV",   "IPV",          "Poliomyelitis (injectable)",    1, 1, 14, "weeks",  "14 weeks"),

    # The measles series is two doses, but they are two different products: MR at
    # 9 months and MMR at 12-15 months. They are stored as separate codes, each a
    # single dose, because the record has to say what was actually put in the
    # child -- calling the MMR "MR dose 2" would file a vial of one vaccine under
    # the name of another. The series relationship is carried in the timing note,
    # which is where a health worker reads it.
    ("MR",    "MR",           "Measles, rubella",              1, 1,  9, "months", "9 months — 1st measles dose"),
    ("MMR",   "MMR",          "Measles, mumps, rubella",       1, 1, 12, "months", "12 to 15 months — 2nd measles dose"),
)

# Every distinct vaccine in the schedule, in first-appearance order. Used by the
# profile tab to group the doses of one vaccine together.
VACCINE_ORDER = tuple(dict.fromkeys(row[0] for row in EPI_SCHEDULE))
VACCINE_NAMES = {row[0]: row[1] for row in EPI_SCHEDULE}
VACCINE_PROTECTS = {row[0]: row[2] for row in EPI_SCHEDULE}

# Valid (code, dose_number) pairs. What the form is allowed to submit and the
# model is allowed to store -- so a POST cannot invent "Pentavalent dose 7".
SCHEDULE_KEYS = frozenset((row[0], row[3]) for row in EPI_SCHEDULE)
TOTAL_SCHEDULED_DOSES = len(EPI_SCHEDULE)

# How long after the recommended age a dose is still "due" rather than "overdue".
#
# The EPI schedule gives target ages, not deadlines: a child seen a fortnight
# after their 6-week visit is not a defaulter, they are simply being caught up at
# the next available session, which is how a barangay health station runs. Four
# weeks is the point past which the delay is worth chasing rather than absorbing
# -- roughly one missed monthly immunisation session. One constant rather than a
# per-vaccine grace, because a per-vaccine number would be invented precision.
GRACE_PERIOD_DAYS = 28

# Statuses, most urgent first. This order is also the sort order the profile tab
# and the alert list use, so whatever needs attention soonest is read first.
OVERDUE = "Overdue"
DUE_NOW = "Due Now"
UPCOMING = "Upcoming"
COMPLETED = "Completed"
STATUS_ORDER = (OVERDUE, DUE_NOW, UPCOMING, COMPLETED)
_STATUS_RANK = {status: index for index, status in enumerate(STATUS_ORDER)}

# Reuses the badge classes the profile, queue and dashboard stylesheets already
# define -- no new visual vocabulary. Red for a defaulter, amber for something
# needing action today, blue for planned, green for done: exactly the readings
# those four colours already carry on the inventory and queue screens.
STATUS_BADGE_CLASS = {
    OVERDUE: "badge-cancelled",
    DUE_NOW: "badge-waiting",
    UPCOMING: "badge-scheduled",
    COMPLETED: "badge-completed",
}

# The two statuses that mean somebody should act. Named once so the queue badge,
# the check-in message and the dashboard card cannot each pick a different pair.
NEEDS_ATTENTION = (OVERDUE, DUE_NOW)

# Where a dose on file came from. Exactly the two values the table's CHECK
# permits, spelled here so no caller writes the string itself. See the module
# header, and migrate_add_immunization_source.py for the case that produced them.
SOURCE_ADMINISTERED = "administered"
SOURCE_REPORTED = "reported"
SOURCES = (SOURCE_ADMINISTERED, SOURCE_REPORTED)

# THE ONE PLACE THE DISTINCTION IS PUT INTO WORDS.
#
# Every screen that shows a dose reads these, so the Patient Profile, the
# consultation form, the visit panel on a history row, the coverage report and
# the audit line all say the same thing about the same record. A second wording
# invented on one screen is how "reported" quietly becomes indistinguishable from
# "administered" on that screen and nowhere else.
#
# The reported label names the health center's position rather than the parent's
# claim: the system knows the dose was not given here, and it does not know that
# the account of where it was given is true. "Given elsewhere" would assert the
# second; "Reported -- given elsewhere" asserts only the first, and says out loud
# that the record rests on a report.
SOURCE_LABELS = {
    SOURCE_ADMINISTERED: "Given at this health center",
    SOURCE_REPORTED: "Reported — given elsewhere",
}

# The short form, for a badge with a column of table beside it.
SOURCE_SHORT_LABELS = {
    SOURCE_ADMINISTERED: "Given here",
    SOURCE_REPORTED: "Reported — elsewhere",
}

# The consultation form's second column of tick boxes posts under this name, each
# valued "CODE:DOSE" exactly as the "given today" boxes are. It lives here rather
# than beside IMMUNIZATION_FIELD in routes/consultation_views.py because
# parse_reported_doses() below is what reads it, and the name a parser reads
# belongs next to the parser -- the arrangement models/general_vaccinations.py
# already uses for VACCINE_FIELD.
IMMUNIZATION_ELSEWHERE_FIELD = "immunizations_elsewhere"

# Printed wherever a reported dose's date would go and there is none. Not a dash:
# a dash reads as "this field is empty", and what is true here is that the dose
# happened and nobody at this health center knows the day. Saying so is the whole
# reason the column is nullable.
UNKNOWN_DATE_TEXT = "Date not known"

# How far back a reported dose may be dated when the patient has no birth date on
# file to check it against. The same limit, for the same reason, that the
# correction dialog applies in routes/vaccination_correction_views.py: without a
# birthday there is no real floor, and a typo in the year is the error worth
# catching.
MAX_BACKDATE_YEARS = 10


def dose_source_label(source, short=False):
    """'Reported — given elsewhere' for a stored source value.

    Falls back to the stored value itself for anything the vocabulary does not
    contain, rather than to the administered label. A row holding an unexpected
    source is a row whose provenance is unknown, and the one thing a screen must
    not do with it is print "Given at this health center".
    """
    table = SOURCE_SHORT_LABELS if short else SOURCE_LABELS
    return table.get(source, str(source or ""))


def due_date_for(birth_date, due_value, due_unit):
    """When one scheduled dose falls due for a child born on birth_date.

    Weeks are exact multiples of seven days; months are calendar months resolved
    through add_months(), the same helper format_age() uses -- so "9 months" for
    a baby born on 31 May is 28 February in a non-leap year, not an invalid date
    and not 39 weeks later.
    """
    if birth_date is None:
        return None
    if due_unit == "weeks":
        return birth_date + timedelta(weeks=due_value)
    return add_months(birth_date, due_value)


def _dose_status(given, due_date, reference):
    """Completed / Overdue / Due Now / Upcoming for one scheduled dose."""
    if given is not None:
        return COMPLETED
    if due_date is None:
        # No birthdate on record, so no due date can be computed. Reported as
        # Upcoming rather than Overdue: an unknown age is a data gap, and calling
        # it a defaulter would put a child on the follow-up list on no evidence.
        return UPCOMING
    if reference < due_date:
        return UPCOMING
    if reference <= due_date + timedelta(days=GRACE_PERIOD_DAYS):
        return DUE_NOW
    return OVERDUE


def get_immunizations_for_patient(patient_id):
    """Every dose recorded for one patient, oldest first."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT i.id, i.patient_id, i.consultation_id, i.vaccine_code, i.dose_number,
               i.source, i.date_administered, i.administered_by, i.notes, i.created_at,
               u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        WHERE i.patient_id = ?
        ORDER BY i.date_administered, i.id
        """,
        (patient_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_immunizations_for_consultation(consultation_id):
    """The doses given during one consultation, in schedule order."""
    if not consultation_id:
        return []
    conn = get_db()
    rows = conn.execute(
        """
        SELECT i.id, i.vaccine_code, i.dose_number, i.source, i.date_administered,
               i.notes, u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        WHERE i.consultation_id = ?
        """,
        (consultation_id,),
    ).fetchall()
    conn.close()
    given = [dict(row) for row in rows]
    order = {(row[0], row[3]): index for index, row in enumerate(EPI_SCHEDULE)}
    given.sort(key=lambda dose: order.get((dose["vaccine_code"], dose["dose_number"]), 99))
    for dose in given:
        dose["vaccine"] = VACCINE_NAMES.get(dose["vaccine_code"], dose["vaccine_code"])
        dose["label"] = dose_label(dose["vaccine_code"], dose["dose_number"])
        annotate_source(dose)
    return given


def annotate_source(record):
    """Add the three provenance keys a screen reads, in place. Returns the record.

    `reported`, `source_label` and `date_known` are derived from `source` and
    `date_administered` here rather than in each template, so a screen asks one
    boolean instead of comparing a stored string it could compare wrongly --
    `record.source == 'Reported'` is silently False for every row, and would
    print a dose given at another hospital as this health center's own work.

    Every list of doses this module hands out goes through it: the patient's
    history, one consultation's doses, and each entry in the schedule.
    """
    source = record.get("source") or SOURCE_ADMINISTERED
    record["source"] = source
    record["reported"] = source == SOURCE_REPORTED
    record["source_label"] = dose_source_label(source)
    record["source_short_label"] = dose_source_label(source, short=True)
    record["date_known"] = record.get("date_administered") is not None
    return record


def dose_label(code, dose_number):
    """'Pentavalent dose 2', or 'Pentavalent' when the vaccine is a single dose.

    The one place a dose is turned into words, so the form's checkbox, the
    profile row, the queue tooltip and the audit entry all name it identically.
    """
    name = VACCINE_NAMES.get(code, code)
    total = next(
        (row[4] for row in EPI_SCHEDULE if row[0] == code and row[3] == dose_number),
        None,
    )
    if total == 1:
        return name
    return f"{name} dose {dose_number}"


def get_immunization_status(patient, on_date=None, records=None):
    """Where one child stands against the DOH EPI schedule.

    The single authority behind every immunisation figure in the system. Returns:

        applicable      the EPI infant schedule still applies (under 5)
        schedule        one entry per scheduled dose, in schedule order, each
                        carrying its status, badge class, administered detail and
                        -- where a dose is on file -- where that dose came from
        attention_items the Overdue and Due Now entries, most urgent first
        extra_records   doses on file that the current schedule does not list
        counts          completed / due_now / overdue / upcoming / total, plus
                        how many of the completed ones were reported rather than
                        given here
        next_due        the soonest dose not yet given, or None
        summary         one line a screen can print without composing it itself

    The dose list is keyed "schedule" rather than the more obvious "items"
    because this dict is handed to Jinja, where `immunization.items` resolves to
    dict.items -- the built-in method -- and blows up on iteration. Same trap,
    and same fix, as get_low_stock_alert()'s "low_stock_items".

    `records` lets a caller that has already fetched a whole roster's doses hand
    them in, so the dashboard alert does not issue one query per child.
    """
    # on_date arrives as a real date from the queue and the dashboards, and as
    # the text SQLite stores it when the consultation form asks "how old was this
    # child at the visit this record describes?". Normalised once, here, because
    # everything below -- the age, every due date, every comparison -- needs a
    # date object and a string reaches calculate_age() and fails on .year.
    reference = as_date(on_date) if on_date is not None else today()
    birth_date = as_date(patient["birth_date"]) if patient and patient.get("birth_date") else None

    age_years = calculate_age(patient.get("birth_date") if patient else None,
                              on_date=reference)
    applicable = age_years is not None and 0 <= age_years < PEDIATRIC_AGE_YEARS

    if records is None:
        records = get_immunizations_for_patient(patient["id"]) if patient else []

    # Keyed by (code, dose) so a scheduled dose can find its record in one look.
    # Annotated on the way in, so a caller that handed `records` in -- the roster
    # readers below do, to avoid a query per child -- gets provenance on those
    # rows too rather than only on the schedule built from them.
    given_by_key = {
        (record["vaccine_code"], record["dose_number"]): annotate_source(record)
        for record in records
    }

    schedule = []
    for code, vaccine, protects, dose_number, total, value, unit, note in EPI_SCHEDULE:
        given = given_by_key.get((code, dose_number))
        due_date = due_date_for(birth_date, value, unit)
        status = _dose_status(given, due_date, reference)
        # Past the cohort the schedule describes, "Overdue" and "Due Now" stop
        # being useful readings -- the infant programme's window has closed, and
        # flagging a 30-year-old as a defaulter would be noise on every screen
        # that counts them. What is on file is still reported.
        if not applicable and status in NEEDS_ATTENTION:
            status = UPCOMING
        schedule.append({
            "code": code,
            "vaccine": vaccine,
            "protects": protects,
            "dose_number": dose_number,
            "total_doses": total,
            "label": dose_label(code, dose_number),
            "timing": note,
            "due_date": due_date,
            "status": status,
            "badge_class": STATUS_BADGE_CLASS[status],
            "needs_attention": status in NEEDS_ATTENTION,
            "given": given is not None,
            # The immunizations row behind this scheduled dose, when one exists.
            # Carried so the Patient Profile's Correct action can name the record
            # it means -- the (code, dose) pair identifies the dose in the
            # schedule, but the correction endpoint has to be handed the row's
            # own id, because correcting a dose may change that very pair.
            "record_id": given["id"] if given else None,
            "date_administered": given["date_administered"] if given else None,
            "administered_by_name": given["administered_by_name"] if given else None,
            "consultation_id": given["consultation_id"] if given else None,
            # Where this dose came from, for the row that has one. None on a dose
            # not yet given -- there is no provenance to report about something
            # that has not happened, and a default of "administered" there would
            # be a claim about a dose nobody has given.
            "source": given["source"] if given else None,
            "reported": bool(given and given["reported"]),
            "source_label": given["source_label"] if given else None,
            "source_short_label": given["source_short_label"] if given else None,
            # False for a reported dose whose date nobody knows, and for a dose
            # not yet given. A screen asks this rather than testing the date,
            # because those two cases print different sentences.
            "date_known": bool(given and given["date_known"]),
            # What the form's checkboxes post back -- both of them, the one that
            # records a dose as given today and the one that records it as
            # reported from elsewhere.
            "key": f"{code}:{dose_number}",
            "reported_date_field": reported_date_field(f"{code}:{dose_number}"),
        })

    extra_records = [
        annotate_source(record) for record in records
        if (record["vaccine_code"], record["dose_number"]) not in SCHEDULE_KEYS
    ]
    for record in extra_records:
        record["label"] = dose_label(record["vaccine_code"], record["dose_number"])

    counts = {status: sum(1 for item in schedule if item["status"] == status)
              for status in STATUS_ORDER}
    # How many of the completed doses this health center did not give. Counted
    # here rather than by each screen filtering the schedule itself, so the
    # profile's summary line, the report card and the flash message all report
    # the same number.
    reported_count = sum(1 for item in schedule if item["reported"])
    attention_items = sorted(
        (item for item in schedule if item["needs_attention"]),
        key=lambda item: (_STATUS_RANK[item["status"]], item["due_date"] or reference),
    )
    next_due = next(
        (item for item in schedule if not item["given"]
         and item["due_date"] is not None),
        None,
    )

    return {
        "applicable": applicable,
        "age_years": age_years,
        "schedule": schedule,
        "attention_items": attention_items,
        "extra_records": extra_records,
        "records": records,
        "completed_count": counts[COMPLETED],
        "due_count": counts[DUE_NOW],
        "overdue_count": counts[OVERDUE],
        "upcoming_count": counts[UPCOMING],
        "reported_count": reported_count,
        "administered_count": counts[COMPLETED] - reported_count,
        "total_doses": TOTAL_SCHEDULED_DOSES,
        "attention_count": counts[OVERDUE] + counts[DUE_NOW],
        "needs_attention": bool(counts[OVERDUE] + counts[DUE_NOW]) and applicable,
        "next_due": next_due,
        "summary": _summarise(counts, applicable, reported_count),
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "grace_period_days": GRACE_PERIOD_DAYS,
    }


def _summarise(counts, applicable, reported_count=0):
    """The one-line reading every screen prints rather than composing its own.

    The reported clause is printed only when there is one to print. A standing
    "0 reported as given elsewhere" on every child's summary would be noise, and
    the sentence has to stay readable on the queue tooltip as well as the profile
    -- but where a dose did come from somewhere else, the headline figure says so
    rather than leaving the distinction to be discovered further down the page.
    """
    given = counts[COMPLETED]
    parts = [f"{given} of {TOTAL_SCHEDULED_DOSES} scheduled doses given"]
    if reported_count:
        parts.append(
            f"{reported_count} reported as given elsewhere"
        )
    if not applicable:
        parts.append("EPI infant schedule no longer applies at this age")
        return " · ".join(parts)
    if counts[OVERDUE]:
        parts.append(f"{counts[OVERDUE]} overdue")
    if counts[DUE_NOW]:
        parts.append(f"{counts[DUE_NOW]} due now")
    if not counts[OVERDUE] and not counts[DUE_NOW]:
        parts.append("nothing due today" if given < TOTAL_SCHEDULED_DOSES
                     else "schedule complete")
    return " · ".join(parts)


def _roster_statuses(on_date=None):
    """Every active patient's standing against the schedule. (roster, reference).

    The shared root of get_immunization_alert() and get_dose_coverage(). Both
    need the same thing -- one get_immunization_status() per active patient, on
    one date -- and computing it twice is how the follow-up list and the coverage
    table would eventually come to disagree about the same child. It is the same
    reason get_immunization_status() itself is the only place a dose's status is
    decided; this just extends that rule one level up.

    Only living, active records: chasing a deceased or archived child for a
    missed dose is exactly the kind of thing a follow-up list must not do, and a
    coverage denominator that counted them would be reporting on children the
    health center is no longer responsible for.

    Every dose for every patient is read in one query and grouped in Python,
    rather than one query per child: the roster is small, but a per-child query
    inside a dashboard render is the shape that stops being small quietly.
    """
    from models.patients import get_all_patients

    reference = on_date or today()

    conn = get_db()
    rows = conn.execute(
        """
        SELECT i.id, i.patient_id, i.consultation_id, i.vaccine_code, i.dose_number,
               i.source, i.date_administered, i.administered_by, i.notes, i.created_at,
               u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        ORDER BY i.date_administered, i.id
        """
    ).fetchall()
    conn.close()

    by_patient = {}
    for row in rows:
        by_patient.setdefault(row["patient_id"], []).append(dict(row))

    roster = [
        (patient, get_immunization_status(
            patient, on_date=reference, records=by_patient.get(patient["id"], [])))
        for patient in get_all_patients()
        if patient.get("status") == "Active"
    ]
    return roster, reference


def get_immunization_alert(limit=None, on_date=None):
    """Children due or overdue for a dose. Same role as get_low_stock_alert().

    The dashboards' figure and list, and the set the queue reads to decide which
    rows carry a badge. Everything derives from get_immunization_status(), so the
    dashboard card, the queue badge and the child's own profile cannot disagree.

    `limit` caps only the returned list, never the counts -- a panel with room
    for five rows still reports the true total above them, exactly as the
    low-stock panel does.
    """
    roster, reference = _roster_statuses(on_date)

    children = []
    # How many children the DOH schedule applies to at all -- the denominator a
    # coverage figure needs. Counted in this loop rather than by a second query,
    # because "applicable" is get_immunization_status()'s own judgement and a
    # separate SELECT on birth_date would be a second, quietly different rule.
    eligible = 0
    for patient, status in roster:
        if status["applicable"]:
            eligible += 1
        if not status["needs_attention"]:
            continue
        children.append({
            "patient": patient,
            "status": status,
            # Lifted out so the templates read one level shallower.
            "overdue_count": status["overdue_count"],
            "due_count": status["due_count"],
            "attention_count": status["attention_count"],
            "next_label": status["attention_items"][0]["label"],
            "next_status": status["attention_items"][0]["status"],
            "next_badge_class": status["attention_items"][0]["badge_class"],
        })

    # Most overdue doses first, then most due, then youngest -- the order a
    # health worker would work the follow-up list in.
    children.sort(key=lambda child: (
        -child["overdue_count"], -child["due_count"],
        child["patient"].get("birth_date") or "",
    ))

    return {
        "children": children if limit is None else children[:limit],
        "child_count": len(children),
        "overdue_child_count": sum(1 for child in children if child["overdue_count"]),
        "due_dose_count": sum(child["attention_count"] for child in children),
        "patient_ids": {child["patient"]["id"] for child in children},
        # The two figures a coverage percentage is built from. up_to_date is the
        # complement of child_count within the eligible set by construction, so
        # the follow-up list and the coverage card cannot disagree about how many
        # children are behind.
        "eligible_child_count": eligible,
        "up_to_date_child_count": eligible - len(children),
    }


def get_immunization_coverage(on_date=None, start=None, end=None, months=6):
    """Programme-level immunisation figures for Screen 10.

    `enrolled` is the number of distinct patients with at least one dose on
    record -- the only defensible reading of "how many are in the immunisation
    programme" from what is stored, because nothing anywhere records an
    enrolment. A child who is due a dose but has never had one is therefore not
    counted here; `awaiting_first_dose` says how many those are, so the gap is
    stated rather than hidden.

    The due/overdue figures come from get_immunization_alert(), the same call
    behind both dashboards and the queue badges, so this panel cannot report a
    different number of defaulters from the rest of the project.

    WHY ONLY DOSES ARE RANGED
    -------------------------
    Doses are events and the `window` block counts them between two dates.
    Coverage is not: "up to date on the schedule" is a judgement about a child
    made on one day, and the only honest way to range it is to ask it as of the
    range's closing date -- which is what passing `end` does, through the
    existing `on_date`. There is no such thing as a child being up to date
    "during March", and a report that offered one would be inventing a reading
    the DOH schedule does not have.
    """
    window = resolve_range(start=start, end=end, months=months, on_date=on_date)
    conn = get_db()
    enrolled = conn.execute(
        "SELECT COUNT(DISTINCT patient_id) FROM immunizations"
    ).fetchone()[0]
    # Split by source, all time and in the window, because "doses given" and
    # "doses this health center gave" stopped being the same number the day a
    # dose could be recorded as given elsewhere. A single total would credit
    # another hospital's work to this one on the Barangay Official's dashboard,
    # which is the one screen in the project a figure leaves the building from.
    #
    # Both halves are returned rather than one being chosen here. Coverage is
    # about the child and counts every dose; activity is about the health center
    # and counts only its own -- and the screens that print each say which they
    # mean.
    by_source = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT source, COUNT(*) FROM immunizations GROUP BY source"
        )
    }
    doses_given = sum(by_source.values())
    # A dose with no date is in no window. That is arithmetic rather than a
    # decision -- substr(NULL) is NULL and NULL BETWEEN anything is not true --
    # but it is also the right answer: a dose whose date nobody knows cannot
    # honestly be counted into a particular month.
    scoped = conn.execute(
        """
        SELECT COUNT(*) AS doses,
               COUNT(DISTINCT patient_id) AS children,
               SUM(CASE WHEN source = ? THEN 1 ELSE 0 END) AS reported
        FROM immunizations
        WHERE substr(date_administered, 1, 10) BETWEEN ? AND ?
        """,
        (SOURCE_REPORTED, window["start"].isoformat(), window["end"].isoformat()),
    ).fetchone()
    conn.close()

    scoped_reported = scoped["reported"] or 0
    reported = by_source.get(SOURCE_REPORTED, 0)

    alert = get_immunization_alert(on_date=on_date)
    return {
        "window": {
            "start": window["start"],
            "end": window["end"],
            "custom": window["custom"],
            "doses_given": scoped["doses"],
            "doses_administered": scoped["doses"] - scoped_reported,
            "doses_reported": scoped_reported,
            "children_dosed": scoped["children"],
        },
        "enrolled": enrolled,
        "doses_given": doses_given,
        "doses_administered": doses_given - reported,
        "doses_reported": reported,
        "needing_attention": alert["child_count"],
        "overdue_children": alert["overdue_child_count"],
        "awaiting_first_dose": len(alert["patient_ids"] - _patients_with_doses()),
        # Carried through so Screen 10 and the Barangay Official dashboard read
        # coverage from this one call rather than each dividing for themselves.
        "eligible_children": alert["eligible_child_count"],
        "up_to_date_children": alert["up_to_date_child_count"],
        "up_to_date_pct": (
            round(alert["up_to_date_child_count"] * 100 / alert["eligible_child_count"])
            if alert["eligible_child_count"] else None
        ),
    }


def get_dose_coverage(on_date=None):
    """Coverage of each scheduled dose across the children the schedule applies to.

    What Screen 17 (Vaccination Campaigns) can honestly report. That screen was
    drawn as a list of named vaccination drives -- "Anti-Measles Vaccination
    Drive, 6-10 July, 343 target, 91% coverage" -- and nothing in the schema
    stores a campaign, its target group, its date range or its goal. See
    official_views.LOCAL_UNTRACKED["campaigns"].

    What *is* stored is every dose given to every child, and the DOH schedule
    says which doses each child should have had by now. So the real unit here is
    the scheduled dose, not the campaign: for each of the EPI schedule's entries,
    how many of the eligible children have had it, and how many are overdue, due
    now or not yet due. That is a coverage report a barangay can act on, and
    every figure in it traces to a row in `immunizations`.

    The denominator is the eligible cohort -- active patients get_immunization_status()
    judges the infant schedule still applies to -- which is the same denominator
    get_immunization_alert() reports as eligible_child_count, because both come
    from _roster_statuses(). A dose's coverage here can therefore be read
    directly against the up-to-date percentage the dashboards print.

    Returns `doses` (one row per EPI_SCHEDULE entry, in schedule order) and
    `by_vaccine` (those rows rolled up per vaccine, for the coverage cards).
    """
    roster, reference = _roster_statuses(on_date)
    eligible = [status for _, status in roster if status["applicable"]]
    cohort = len(eligible)

    doses = []
    for index, entry in enumerate(EPI_SCHEDULE):
        code, vaccine, protects, dose_number, total, value, unit, note = entry
        # Positional lookup is safe: get_immunization_status() builds its
        # "schedule" list by iterating EPI_SCHEDULE in this same order, one entry
        # per row, so index i here is index i there for every child.
        counts = {status_name: 0 for status_name in STATUS_ORDER}
        # Of the children counted Completed for this dose, how many had it
        # somewhere else. Counted alongside the statuses rather than derived
        # afterwards, so the two figures come from one pass over one list and
        # cannot describe different cohorts.
        reported = 0
        for status in eligible:
            entry = status["schedule"][index]
            counts[entry["status"]] += 1
            if entry["reported"]:
                reported += 1
        doses.append({
            "code": code,
            "vaccine": vaccine,
            "protects": protects,
            "dose_number": dose_number,
            "total_doses": total,
            "label": dose_label(code, dose_number),
            "timing": note,
            "given": counts[COMPLETED],
            # `given` is the coverage figure and counts every child who has had
            # this dose, wherever they had it -- that is what protection means.
            # These two say how that figure is made up, so a coverage percentage
            # can be read without it being mistaken for a count of what this
            # health center administered.
            "administered": counts[COMPLETED] - reported,
            "reported": reported,
            "overdue": counts[OVERDUE],
            "due_now": counts[DUE_NOW],
            "upcoming": counts[UPCOMING],
            "eligible": cohort,
            # None rather than 0 when there is nobody to count, so a screen can
            # tell "no eligible children" apart from "nobody has had it".
            "coverage_pct": round(counts[COMPLETED] * 100 / cohort) if cohort else None,
        })

    by_vaccine = []
    for code in VACCINE_ORDER:
        entries = [dose for dose in doses if dose["code"] == code]
        given = sum(dose["given"] for dose in entries)
        # Every dose of this vaccine that every eligible child should have had.
        scheduled = len(entries) * cohort
        by_vaccine.append({
            "code": code,
            "vaccine": VACCINE_NAMES[code],
            "protects": VACCINE_PROTECTS[code],
            "dose_count": len(entries),
            "given": given,
            "administered": sum(dose["administered"] for dose in entries),
            "reported": sum(dose["reported"] for dose in entries),
            "scheduled": scheduled,
            "coverage_pct": round(given * 100 / scheduled) if scheduled else None,
            "overdue": sum(dose["overdue"] for dose in entries),
            "due_now": sum(dose["due_now"] for dose in entries),
        })

    return {
        "reference_date": reference,
        "eligible_children": cohort,
        "doses": doses,
        "by_vaccine": by_vaccine,
        "total_given": sum(dose["given"] for dose in doses),
        "total_administered": sum(dose["administered"] for dose in doses),
        "total_reported": sum(dose["reported"] for dose in doses),
        "total_scheduled": TOTAL_SCHEDULED_DOSES * cohort,
        "total_overdue": sum(dose["overdue"] for dose in doses),
        "total_due_now": sum(dose["due_now"] for dose in doses),
    }


def _patients_with_doses():
    conn = get_db()
    ids = {row[0] for row in conn.execute("SELECT DISTINCT patient_id FROM immunizations")}
    conn.close()
    return ids


def parse_dose_keys(raw_keys):
    """['BCG:1', 'PENTA:2'] -> [('BCG', 1), ...], dropping anything not scheduled.

    The gate between the form and the table. Only pairs the DOH schedule actually
    lists survive, so a hand-made POST cannot record a dose that does not exist --
    and the UNIQUE constraint on the table then stops a real one being given twice.
    """
    keys = []
    for raw in raw_keys or []:
        text = str(raw or "").strip()
        if ":" not in text:
            continue
        code, _, dose = text.partition(":")
        code = code.strip().upper()
        if not dose.strip().isdigit():
            continue
        pair = (code, int(dose.strip()))
        if pair in SCHEDULE_KEYS and pair not in keys:
            keys.append(pair)
    # Returned in schedule order regardless of the order the form posted them, so
    # an audit entry lists a visit's doses the way the schedule reads.
    order = {(row[0], row[3]): index for index, row in enumerate(EPI_SCHEDULE)}
    keys.sort(key=lambda pair: order[pair])
    return keys


def reported_date_field(key):
    """'PENTA:2' -> 'elsewhere_date_PENTA_2'. The per-row date box's field name.

    Built here rather than spelled in the template, for the reason
    models/general_vaccinations.dose_field() exists: the form that prints the box
    and the parser that reads it back have to agree about the name, and two
    string literals in two files agree only until one of them is edited.

    The colon becomes an underscore because the key is going into an HTML `name`
    and a JavaScript selector, where a colon has to be escaped and eventually
    will not be.
    """
    return "elsewhere_date_" + str(key or "").replace(":", "_")


# What the consultation form's error summary calls each of those date boxes.
#
# The summary at the top of the page prints field_labels.get(field, field), so
# without this a mistyped date would be reported as "elsewhere_date_PENTA_2" --
# a field name, to a health worker, at the moment they are being told something
# is wrong. Built from EPI_SCHEDULE through the same two functions the form and
# the parser use, so a schedule revision cannot leave a label behind.
REPORTED_DATE_LABELS = {
    reported_date_field(f"{row[0]}:{row[3]}"):
        f"{dose_label(row[0], row[3])} — date given elsewhere"
    for row in EPI_SCHEDULE
}


def validate_reported_date(raw, patient, visit_date=None):
    """Read one 'given elsewhere' date box. Returns (iso_text_or_None, error).

    BLANK IS A VALID ANSWER, and it is the one thing this validator does that the
    correction dialog's date check in routes/vaccination_correction_views.py
    deliberately does not. There the date is a fact the health center holds about
    its own work and its absence is a defect; here it belongs to another
    facility's records, and a parent who remembers their child was vaccinated at
    the hospital where they were born may genuinely not remember the day. Forcing
    a date would mean forcing an invented one, and an invented date in a clinical
    record is worse than an absent one -- which is why the column is nullable and
    why this returns (None, None) rather than an error.

    What it does hold a date to, once one is typed:

        a real date            anything else is a typo, not a record
        not in the future      a dose cannot have been given after today
        not after this visit   "previously given" means before the encounter that
                               is recording it. A date later than the visit
                               describes something that has not happened yet from
                               this record's point of view.
        not before birth       the child did not exist to be vaccinated
        within living memory   where no birth date is on file to check against,
                               MAX_BACKDATE_YEARS catches a mistyped year, which
                               is the error a free date box actually produces
    """
    text = str(raw or "").strip()
    if not text:
        return None, None

    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None, (
            "Enter a valid date in YYYY-MM-DD format, or leave it blank if the "
            "date it was given is not known."
        )

    now = today()
    if parsed > now:
        return None, (
            "The date cannot be in the future — a dose reported for "
            f"{display_date(parsed)} has not been given yet."
        )

    visit = as_date(visit_date) if visit_date is not None else now
    if parsed > visit:
        return None, (
            "A dose given elsewhere must have been given before this visit. "
            f"{display_date(parsed)} is after {display_date(visit)}."
        )

    birth_text = patient.get("birth_date") if patient else None
    if birth_text:
        birth = as_date(birth_text)
        if parsed < birth:
            first_name = (patient or {}).get("first_name") or "this patient"
            return None, (
                f"The date cannot be before {first_name} was born "
                f"({display_date(birth)})."
            )
    elif parsed.year < now.year - MAX_BACKDATE_YEARS:
        return None, (
            f"The date cannot be more than {MAX_BACKDATE_YEARS} years ago. This "
            "patient has no birth date on file to check it against."
        )

    return parsed.isoformat(), None


def parse_reported_doses(form_data, patient, visit_date=None, given_today=()):
    """Read the "previously given elsewhere" ticks. Returns (entries, errors).

    `entries` is [{'code', 'dose_number', 'date', 'key', 'label'}] in schedule
    order, ready for record_reported_immunizations(). `errors` is {field:
    message}, which the caller merges into the consultation form's own errors so
    one refusal summary covers the whole page -- the shape
    parse_general_vaccinations() already uses.

    The tick boxes go through parse_dose_keys(), the same gate the "given today"
    boxes do, so a hand-made POST cannot report a dose the DOH schedule does not
    list any more than it can record one.

    A DOSE TICKED IN BOTH COLUMNS IS REFUSED, NOT RESOLVED. The two claims are
    incompatible -- this health center either gave the dose today or it did not
    -- and picking one silently would store a clinical fact nobody asserted. So
    the save stops and says which dose is contradicting itself, and the operator
    decides. That is the same treatment a vaccine name typed into the free-text
    row with the box left unticked gets, and for the same reason: a save about to
    discard or invent what somebody entered says so instead.
    """
    raw_keys = (form_data.getlist(IMMUNIZATION_ELSEWHERE_FIELD)
                if hasattr(form_data, "getlist")
                else (form_data.get(IMMUNIZATION_ELSEWHERE_FIELD) or []))
    keys = parse_dose_keys(raw_keys)
    conflicting = set(given_today or ())

    entries, errors = [], {}
    for code, dose_number in keys:
        key = f"{code}:{dose_number}"
        field = reported_date_field(key)

        if (code, dose_number) in conflicting:
            errors[field] = (
                f"{dose_label(code, dose_number)} is ticked both as given today "
                "and as previously given elsewhere. Choose one."
            )
            continue

        date_text, date_error = validate_reported_date(
            form_data.get(field), patient, visit_date
        )
        if date_error:
            errors[field] = date_error
            continue

        entries.append({
            "code": code,
            "dose_number": dose_number,
            "date": date_text,
            "key": key,
            "label": dose_label(code, dose_number),
        })

    # A date typed against a row whose box was never ticked is a save about to
    # discard what somebody entered. Say so rather than drop it silently --
    # exactly what parse_general_vaccinations() does with an unticked free-text
    # name. Only rows whose box is genuinely absent are checked, so a row already
    # refused above is not told off twice.
    ticked = {f"{code}:{dose_number}" for code, dose_number in keys}
    for row in EPI_SCHEDULE:
        key = f"{row[0]}:{row[3]}"
        if key in ticked:
            continue
        field = reported_date_field(key)
        if field in errors or not str(form_data.get(field) or "").strip():
            continue
        errors[field] = (
            f"Tick “previously given elsewhere” for {dose_label(row[0], row[3])} "
            "to record this date, or clear the date."
        )

    return entries, errors


def record_immunizations(patient_id, dose_keys, administered_by, date_administered,
                         consultation_id=None):
    """Write the doses THIS HEALTH CENTER gave at one visit. Returns the pairs stored.

    INSERT OR IGNORE against the table's UNIQUE (patient_id, vaccine_code,
    dose_number): a dose already on file is left exactly as it was rather than
    being re-dated to today. Double-clicking Save must not rewrite the history of
    when a child was actually vaccinated, and a dose recorded earlier as given at
    another facility is not superseded by a tick box -- that constraint is now
    doing two jobs, and the second one is new.

    `source` is written explicitly rather than left to the column default. The
    default exists for rows migrated from before the distinction existed; a row
    this function writes is a positive claim that a health worker here
    administered the dose, and a claim that large should be made in the INSERT
    where it can be read.
    """
    if not dose_keys:
        return []

    day = date_administered
    day = day.isoformat() if hasattr(day, "isoformat") else str(day)

    stored = []
    conn = get_db()
    for code, dose_number in dose_keys:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO immunizations
                (patient_id, consultation_id, vaccine_code, dose_number,
                 source, date_administered, administered_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (patient_id, consultation_id, code, dose_number,
             SOURCE_ADMINISTERED, day, administered_by),
        )
        if cursor.rowcount:
            stored.append((code, dose_number))
    conn.commit()
    conn.close()
    return stored


def record_reported_immunizations(patient_id, entries, recorded_by,
                                  consultation_id=None):
    """Write doses reported at one visit as already given elsewhere.

    `entries` is [{'code', 'dose_number', 'date'}], where `date` is an ISO string
    or None -- None being the honest answer when the parent remembers the
    hospital but not the day. Returns the (code, dose_number, date) triples
    actually stored, so the caller can name them in a flash message and an audit
    line without re-reading the table.

    THE CONSULTATION IS REQUIRED HERE, NOT IN THE SCHEMA.
    Nothing is written without a consultation_id, and that is the rule this
    project applies to every clinical fact: a record exists because a health
    worker learned something at a real encounter, not because a screen offered a
    field. The column cannot enforce it -- consultation_id is nullable because a
    deleted consultation sets it NULL and the vaccination still happened -- so
    the refusal lives here, at the only place that writes SOURCE_REPORTED.

    Everything else is deliberately identical to record_immunizations() above:
    the same INSERT OR IGNORE against the same UNIQUE constraint, so a dose
    already on file is left exactly as it is. A child who really was given
    Pentavalent 1 here last month does not have that record overwritten by a
    parent's recollection that it happened somewhere else, and a double-submitted
    form adds nothing twice.

    `recorded_by` goes into administered_by, and that is the one column whose
    name now reads slightly wide of what it holds. It is not renamed: it is a
    foreign key on every dose ever recorded, and renaming it would rewrite
    seventeen rows of history to fix a word. What matters is that no screen
    prints it as "administered by" for a reported dose -- SOURCE_LABELS is what
    keeps that true, and the Patient Profile prints "Recorded by" instead.
    """
    if not entries or not consultation_id:
        return []

    stored = []
    conn = get_db()
    for entry in entries:
        day = entry.get("date")
        if day is not None and hasattr(day, "isoformat"):
            day = day.isoformat()
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO immunizations
                (patient_id, consultation_id, vaccine_code, dose_number,
                 source, date_administered, administered_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (patient_id, consultation_id, entry["code"], entry["dose_number"],
             SOURCE_REPORTED, day, recorded_by),
        )
        if cursor.rowcount:
            stored.append((entry["code"], entry["dose_number"], day))
    conn.commit()
    conn.close()
    return stored


def remove_immunizations(patient_id, dose_keys, consultation_id):
    """Un-record doses entered against one consultation. Returns what was removed.

    Scoped to the consultation that recorded them, deliberately. Correcting a
    mis-ticked box on the visit you are editing is a clerical fix; reaching
    across into a dose recorded at some other visit is not something a
    consultation edit should be able to do, and the WHERE clause is what makes
    that true rather than the UI merely not offering it.
    """
    if not dose_keys or not consultation_id:
        return []

    removed = []
    conn = get_db()
    for code, dose_number in dose_keys:
        cursor = conn.execute(
            """
            DELETE FROM immunizations
             WHERE patient_id = ? AND consultation_id = ?
               AND vaccine_code = ? AND dose_number = ?
            """,
            (patient_id, consultation_id, code, dose_number),
        )
        if cursor.rowcount:
            removed.append((code, dose_number))
    conn.commit()
    conn.close()
    return removed


def get_immunization_by_id(record_id):
    """One recorded dose by primary key, or None. The correction path's first read.

    Returns the stored row plus the name of whoever administered it, because a
    correction's audit entry has to say who recorded the dose originally --
    exactly as a consultation edit names who wrote the visit up. The patient is
    deliberately NOT joined here: the caller resolves them through
    models.patients.get_patient_by_id() so a corrected record is named by the
    same full_name builder every other screen uses, rather than by a second
    concatenation in SQL that could spell the same person differently.
    """
    conn = get_db()
    row = conn.execute(
        """
        SELECT i.id, i.patient_id, i.consultation_id, i.vaccine_code, i.dose_number,
               i.source, i.date_administered, i.administered_by, i.notes, i.created_at,
               u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        WHERE i.id = ?
        """,
        (record_id,),
    ).fetchone()
    conn.close()
    # Annotated like every other dose this module hands out, so the correction
    # dialog reads `record["reported"]` rather than comparing the stored string
    # itself -- and so it knows whether this record may be left without a date.
    return annotate_source(dict(row)) if row else None


def correct_immunization(record_id, vaccine_code, dose_number, date_administered):
    """Correct one recorded dose's vaccine, dose number and date. Deliberate path.

    Returns "corrected", "missing", "duplicate" or "date_required". Never
    removes the row: this
    is the correction capability routes/consultation_views.py's
    _apply_immunization_edit() says belongs on a path of its own, and a
    correction moves a record's field values rather than making the record go
    away.

    THE DUPLICATE CHECK AND THE UPDATE SHARE ONE CONNECTION ON PURPOSE.
    The table's UNIQUE (patient_id, vaccine_code, dose_number) means correcting
    a dose onto a (vaccine, dose) the same child already has on file is a
    collision, and it is a collision worth naming rather than letting SQLite
    raise: "Pentavalent dose 2 is already recorded for this child" tells the
    operator what to do next, and IntegrityError does not. Checking in the same
    connection that then writes is what keeps the answer true at the moment the
    write happens rather than a moment before it.

    The patient is never moved. A record that was filed against the wrong
    *patient* is not a field-value correction -- it is one child's record
    claiming another child's vaccination, and undoing that means removing a row
    from one history and adding it to another. That is a different, larger
    action than this one and it is not offered here; what this fixes is the
    wrong vaccine, the wrong dose number or the wrong date on a record that is
    on the right patient.
    """
    day = date_administered
    if day is not None:
        day = day.isoformat() if hasattr(day, "isoformat") else str(day)

    conn = get_db()
    row = conn.execute(
        "SELECT patient_id, source FROM immunizations WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return "missing"

    # A correction may not turn a dose this health center administered into an
    # undated one. The table's CHECK would refuse the UPDATE anyway and raise an
    # IntegrityError up through the route; naming the outcome here is what lets
    # the dialog say something a person can act on, exactly as "duplicate" does
    # for the UNIQUE constraint below. The correction dialog does not offer a
    # blank date on such a record, so this is the server's own refusal rather
    # than the form's -- the distinction routes/consultation_views.py draws
    # between a field a screen does not offer and a field the server refuses.
    if day is None and row["source"] != SOURCE_REPORTED:
        conn.close()
        return "date_required"

    clash = conn.execute(
        """
        SELECT id FROM immunizations
         WHERE patient_id = ? AND vaccine_code = ? AND dose_number = ? AND id <> ?
        """,
        (row["patient_id"], vaccine_code, dose_number, record_id),
    ).fetchone()
    if clash is not None:
        conn.close()
        return "duplicate"

    conn.execute(
        """
        UPDATE immunizations
           SET vaccine_code = ?, dose_number = ?, date_administered = ?
         WHERE id = ?
        """,
        (vaccine_code, dose_number, day, record_id),
    )
    conn.commit()
    conn.close()
    return "corrected"
