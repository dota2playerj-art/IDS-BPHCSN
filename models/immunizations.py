"""Immunisation records, and the child's standing against the DOH EPI schedule.

Doses given here are recorded during a consultation -- that is where a health worker
actually holds the syringe. Doses given elsewhere are recorded with their EVIDENCE
(Task 9): a vaccination card that was seen counts as given, a parent's word does not.
This module is read back by the Patient Profile, the queue, the dashboards and the
reports, and is the one place a dose's status is decided.
"""
from collections import namedtuple
from datetime import datetime, timedelta

from database.connection import db_connection
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

# WHEN A DOSE MAY BE GIVEN (Task 13). The recommended ages above say when a dose is DUE; this
# table says when it is VALID. A dose given before its minimum age, before the previous dose
# of its series, or too soon after it does not count and must be repeated, so the child
# gets an extra injection. WHO routine immunization tables: Pentavalent, OPV and PCV start
# at a minimum age of 6 weeks with at least 4 weeks between doses; measles-containing
# vaccine dose 1 at 9 months and at least 4 weeks between MCV1 and MCV2. The values sit
# here, next to the schedule, as named fields, one rule per scheduled dose.
#
#   min_age_value, min_age_unit   the child must have reached this age
#   previous                      the dose of the same series that must be on file first
#                                 ((code, dose) or None)
#   min_interval_weeks            at least this long after that previous dose
#
# Pentavalent, OPV and PCV doses 2 and 3 keep the 6-week minimum age too: they inherit it
# from dose 1 plus the interval. MR and MMR are two products, so MMR names MR as its
# previous dose (the measles series). IPV has one dose, at 14 weeks, as the schedule lists it.
DoseRule = namedtuple("DoseRule", "min_age_value min_age_unit previous min_interval_weeks")
MIN_INTERVAL_WEEKS = 4
MIN_AGE_PRIMARY_WEEKS = 6
DOSE_RULES = {
    ("BCG", 1): DoseRule(0, "weeks", None, 0),
    ("HEPB", 1): DoseRule(0, "weeks", None, 0),
    ("PENTA", 1): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", None, 0),
    ("PENTA", 2): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", ("PENTA", 1), MIN_INTERVAL_WEEKS),
    ("PENTA", 3): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", ("PENTA", 2), MIN_INTERVAL_WEEKS),
    ("OPV", 1): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", None, 0),
    ("OPV", 2): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", ("OPV", 1), MIN_INTERVAL_WEEKS),
    ("OPV", 3): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", ("OPV", 2), MIN_INTERVAL_WEEKS),
    ("PCV", 1): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", None, 0),
    ("PCV", 2): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", ("PCV", 1), MIN_INTERVAL_WEEKS),
    ("PCV", 3): DoseRule(MIN_AGE_PRIMARY_WEEKS, "weeks", ("PCV", 2), MIN_INTERVAL_WEEKS),
    ("IPV", 1): DoseRule(14, "weeks", None, 0),
    ("MR", 1): DoseRule(9, "months", None, 0),
    ("MMR", 1): DoseRule(12, "months", ("MR", 1), MIN_INTERVAL_WEEKS),
}
# When judging any RECORDED dose, a dose within this many days of the minimum age or
# interval still counts (ACIP's 4-day grace period). It is the same for a dose given here
# and one seen on a card (Task 14, D1). The form itself still offers a dose only from its
# date: the grace is for judging records, not for scheduling.
RECORD_GRACE_DAYS = 4

# Every distinct vaccine in the schedule, in first-appearance order. Used by the
# profile tab to group the doses of one vaccine together.
VACCINE_ORDER = tuple(dict.fromkeys(row[0] for row in EPI_SCHEDULE))
# After a dose that did not count, the same dose may be repeated at least this long later
# (Task 14, D2): the series' own minimum interval, or 4 weeks when the series has none.
REPEAT_INTERVAL_WEEKS = {
    code: max((rule.min_interval_weeks for (c, _), rule in DOSE_RULES.items() if c == code),
              default=0) or MIN_INTERVAL_WEEKS
    for code in VACCINE_ORDER
}
VACCINE_NAMES = {row[0]: row[1] for row in EPI_SCHEDULE}
VACCINE_PROTECTS = {row[0]: row[2] for row in EPI_SCHEDULE}

# Valid (code, dose_number) pairs. What the form is allowed to submit and the
# model is allowed to store -- so a POST cannot invent "Pentavalent dose 7".
SCHEDULE_KEYS = frozenset((row[0], row[3]) for row in EPI_SCHEDULE)
TOTAL_SCHEDULED_DOSES = len(EPI_SCHEDULE)
# Every scheduled dose has exactly one rule, and every rule names a scheduled dose.
assert set(DOSE_RULES) == set(SCHEDULE_KEYS), "DOSE_RULES must cover the schedule exactly"
assert all(rule.previous is None or rule.previous in SCHEDULE_KEYS for rule in DOSE_RULES.values())

# How long after the recommended age a dose is still "due" rather than "no record".
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
#
# "No record" is what used to be called "Overdue" (Task 9). The health center cannot
# know what happened elsewhere: a child may have had BCG and Hepatitis B at the hospital
# of birth. A dose with no evidence on file is a gap in OUR record, not proof the child
# missed it, so the word says exactly that. Each such dose still shows its due date.
NO_RECORD = "No record"
TOO_EARLY = "Given too early — ask the Doctor about a repeat"
DUE_NOW = "Due Now"
PARENT_REPORT = "Parent says given — no card"
UPCOMING = "Upcoming"
GIVEN_ELSEWHERE = "Given elsewhere"
COMPLETED = "Completed"
STATUS_ORDER = (NO_RECORD, TOO_EARLY, DUE_NOW, PARENT_REPORT, UPCOMING, GIVEN_ELSEWHERE, COMPLETED)
_STATUS_RANK = {status: index for index, status in enumerate(STATUS_ORDER)}

# The two statuses that count as given: a dose given here, and a dose given elsewhere
# whose card was seen. Completion and coverage count exactly these (CDC: only written,
# dated records are evidence of vaccination).
GIVEN_STATUSES = (COMPLETED, GIVEN_ELSEWHERE)

# Reuses the badge classes the profile, queue and dashboard stylesheets already
# define -- no new visual vocabulary. Amber for no record or something needing
# action today or a report nobody has seen written down, blue for planned, green for
# a dose with evidence. Amber for every reminder, never red: "No record" means "check the
# vaccination card", not an emergency (Task 10).
STATUS_BADGE_CLASS = {
    NO_RECORD: "badge-waiting",
    TOO_EARLY: "badge-waiting",
    DUE_NOW: "badge-waiting",
    PARENT_REPORT: "badge-waiting",
    UPCOMING: "badge-scheduled",
    GIVEN_ELSEWHERE: "badge-completed",
    COMPLETED: "badge-completed",
}

# The statuses that mean somebody should act. Named once so the queue badge, the
# check-in message and the dashboard card cannot each pick a different set. A parent's
# report only needs action once the dose is due: ask for the card.
NEEDS_ATTENTION = (NO_RECORD, TOO_EARLY, DUE_NOW, PARENT_REPORT)

# WHAT A DOSE RECORD RESTS ON (Task 9, D2). The values the table's CHECK permits,
# spelled here so no caller writes the string itself. FHIR Immunization mapping:
#   given_here     primarySource = true
#   card           primarySource = false, reportOrigin = "record"
#   parent_report  primarySource = false, reportOrigin = "recall"
EVIDENCE_GIVEN_HERE = "given_here"
EVIDENCE_CARD = "card"
EVIDENCE_PARENT = "parent_report"
EVIDENCE_TYPES = (EVIDENCE_GIVEN_HERE, EVIDENCE_CARD, EVIDENCE_PARENT)
# What can be recorded without a consultation, from the Immunization Record tab.
ELSEWHERE_EVIDENCE = (EVIDENCE_CARD, EVIDENCE_PARENT)
# The evidence that counts as given for completion and coverage.
COUNTS_AS_GIVEN = (EVIDENCE_GIVEN_HERE, EVIDENCE_CARD)

# THE ONE PLACE THE DISTINCTION IS PUT INTO WORDS.
#
# Every screen that shows a dose reads these, so the Patient Profile, the
# consultation form, the visit panel on a history row, the coverage report and
# the audit line all say the same thing about the same record.
EVIDENCE_LABELS = {
    EVIDENCE_GIVEN_HERE: "Given at this health center",
    EVIDENCE_CARD: "Given elsewhere — card seen",
    EVIDENCE_PARENT: "Parent says given — no card",
}

# The short form, for a badge with a column of table beside it.
EVIDENCE_SHORT_LABELS = {
    EVIDENCE_GIVEN_HERE: "Given here",
    EVIDENCE_CARD: "Given elsewhere",
    EVIDENCE_PARENT: "Parent says given — no card",
}

# What the person recording a dose chooses between, in plain words (D3).
PROOF_CHOICES = (
    (EVIDENCE_CARD, "I saw it on the vaccination card or record book"),
    (EVIDENCE_PARENT, "The parent or guardian says it was given, but has no card"),
)
PROOF_FIELD = "evidence"
DATE_FIELD = "date_given"
PLACE_FIELD = "place_given"
DOSE_FIELD = "dose_key"
MAX_PLACE_LENGTH = 120

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


def dose_evidence_label(evidence, short=False):
    """'Given elsewhere — card seen' for a stored evidence value.

    Falls back to the stored value itself for anything the vocabulary does not
    contain, rather than to the given-here label. A row holding an unexpected value
    is a row whose provenance is unknown, and the one thing a screen must not do with
    it is print "Given at this health center".
    """
    table = EVIDENCE_SHORT_LABELS if short else EVIDENCE_LABELS
    return table.get(evidence, str(evidence or ""))


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


def minimum_age_date(birth_date, code, dose_number):
    """The first day a child born on birth_date may be given this dose, or None."""
    rule = DOSE_RULES[(code, dose_number)]
    return due_date_for(birth_date, rule.min_age_value, rule.min_age_unit)


def _counts_as_given_row(record):
    return bool(record) and record.get("evidence") in COUNTS_AS_GIVEN


def _record_day(record):
    return as_date(record["date_administered"]) if record and record.get("date_administered") else None


# THE ONE VALIDITY RULE (Task 14, D1). Every recorded dose is judged here, whatever its
# evidence (given here or seen on a card), and every screen, report and write path reads
# the answer from this module. A dose is INVALID ("given too early") when its date is more
# than RECORD_GRACE_DAYS before
#   - the child's minimum age for it,
#   - the minimum interval after the previous VALID dose of its series, or
#   - (for a repeat) the series' interval after an earlier invalid record of the same dose.
# An invalid dose stays on file as history. It does not count for completion, coverage or
# eligibility. A dose whose previous dose is on file but does not count is also invalid:
# it was not spaced from a valid dose. A dose with no previous dose on file at all is not
# judged against one: nothing shows it was early. A parent's report is never judged: it
# never counts. Only one valid record per dose counts; any other is "extra".
VERDICT_VALID = "valid"
VERDICT_EARLY = "too_early"
VERDICT_EXTRA = "extra"
VERDICT_REPORT = "parent_report"


def judge_records(birth_date, records):
    """Judge every record of ONE child. Returns a list of verdicts, aligned with `records`.

    `records` are dicts with vaccine_code, dose_number, evidence, date_administered and
    (for a stable order of same-day records) id. The verdicts are VERDICT_VALID,
    VERDICT_EARLY, VERDICT_EXTRA (a second valid record of a dose that already counts) and
    VERDICT_REPORT (a parent's report, which is not judged and never counts).
    """
    grace = timedelta(days=RECORD_GRACE_DAYS)
    verdicts = [None] * len(records)
    by_key = {}
    for index, record in enumerate(records):
        if (record.get("evidence") or EVIDENCE_GIVEN_HERE) not in COUNTS_AS_GIVEN:
            verdicts[index] = VERDICT_REPORT
            continue
        by_key.setdefault((record["vaccine_code"], record["dose_number"]), []).append(index)

    # Schedule order puts every previous dose before the dose that needs it.
    order = [(row[0], row[3]) for row in EPI_SCHEDULE]
    order += [key for key in by_key if key not in DOSE_RULES]
    valid_day = {}   # key -> the date of its valid record (None when the record has no date)
    for key in order:
        rule = DOSE_RULES.get(key)
        invalid_days = []
        indexes = sorted(by_key.get(key, ()), key=lambda i: (
            _record_day(records[i]) or datetime.min.date(), records[i].get("id") or 0))
        for index in indexes:
            if key in valid_day:
                verdicts[index] = VERDICT_EXTRA
                continue
            day = _record_day(records[index])
            valid = True
            if rule is not None and day is not None:
                gate = minimum_age_date(birth_date, *key) if birth_date is not None else None
                if rule.previous in valid_day:
                    previous_day = valid_day[rule.previous]
                    if previous_day is not None:
                        after = previous_day + timedelta(weeks=rule.min_interval_weeks)
                        gate = after if gate is None else max(gate, after)
                elif rule.previous in by_key:
                    valid = False   # the previous dose is on file, but it does not count
                for earlier in invalid_days:
                    after = earlier + timedelta(weeks=REPEAT_INTERVAL_WEEKS[key[0]])
                    gate = after if gate is None else max(gate, after)
                if valid and gate is not None and day < gate - grace:
                    valid = False
            if valid:
                verdicts[index] = VERDICT_VALID
                valid_day[key] = day
            else:
                verdicts[index] = VERDICT_EARLY
                if day is not None:
                    invalid_days.append(day)
    return verdicts


def dose_groups(birth_date, records):
    """The records of one child, grouped by dose: {(code, dose): group}, each group
    {"counting", "invalid", "parent", "extra"}. `counting` is the one valid record (or None),
    `invalid` the records given too early (oldest first), `parent` a parent's report, `extra`
    any other valid record of the same dose. Each record gets its verdict as `record["verdict"]`.
    """
    verdicts = judge_records(birth_date, records)
    groups = {}
    for record, verdict in zip(records, verdicts):
        record["verdict"] = verdict
        group = groups.setdefault((record["vaccine_code"], record["dose_number"]),
                                  {"counting": None, "invalid": [], "parent": None, "extra": []})
        if verdict == VERDICT_VALID:
            group["counting"] = record
        elif verdict == VERDICT_EARLY:
            group["invalid"].append(record)
        elif verdict == VERDICT_EXTRA:
            group["extra"].append(record)
        else:
            group["parent"] = record
    return groups


def too_early_keys(birth_date, records):
    """The (code, dose) pairs that are on file only as doses given too early: no valid record,
    so the dose must be repeated. `records` is a list, as judge_records() takes."""
    groups = dose_groups(birth_date, [dict(r) for r in records])
    return {key for key, group in groups.items() if group["counting"] is None and group["invalid"]}


_NO_RECORDS = {"counting": None, "invalid": [], "parent": None, "extra": []}


def dose_eligibility(code, dose_number, birth_date, groups, on_date):
    """THE ONE RULE for whether a scheduled dose may be given on on_date (Task 13, D1).

    `groups` is dose_groups() for the child. Returns {"eligible", "earliest", "reason"}. A dose
    is eligible only if (a) the child has reached its minimum age, (b) the previous dose of the
    same series is on file and counts, (c) at least the minimum interval has passed since that
    dose, and (d) if the dose was given before and did not count, the series' interval has
    passed since the last such dose (Task 14, D2). A dose that already has a valid record is
    never eligible again. A dose that has only a parent's report on file is still eligible: it
    does not count as given.

    `earliest` is the first day it can be given (None when it first needs another dose),
    and `reason` is the plain sentence the form prints: "From Nov 14, 2026" or "Needs
    Pentavalent dose 1 first". The consultation form, the server and every screen call
    this, so they cannot disagree.
    """
    key = (code, dose_number)
    rule = DOSE_RULES[key]
    on_date = as_date(on_date)
    group = groups.get(key, _NO_RECORDS)

    if group["counting"] is not None:
        return {"eligible": False, "earliest": None, "reason": "Already recorded"}
    if birth_date is None:
        return {"eligible": False, "earliest": None, "reason": "Birth date needed"}

    earliest = minimum_age_date(birth_date, code, dose_number)
    if rule.previous:
        previous = groups.get(rule.previous, _NO_RECORDS)["counting"]
        if previous is None:
            return {"eligible": False, "earliest": None,
                    "reason": f"Needs {dose_label(*rule.previous)} first"}
        previous_day = _record_day(previous)
        if previous_day is not None:
            earliest = max(earliest, previous_day + timedelta(weeks=rule.min_interval_weeks))
    for early in group["invalid"]:
        early_day = _record_day(early)
        if early_day is not None:
            earliest = max(earliest, early_day + timedelta(weeks=REPEAT_INTERVAL_WEEKS[code]))
    if on_date < earliest:
        return {"eligible": False, "earliest": earliest, "reason": f"From {display_date(earliest)}"}
    return {"eligible": True, "earliest": earliest, "reason": None}


def _due_parts(key, birth_date, groups, today_date):
    """(earliest date, None), or (None, the dose that must come first), for one dose that does
    not count yet. Shared by dose_due(); it follows a chain of repeats forward."""
    group = groups.get(key, _NO_RECORDS)
    if group["counting"] is not None or birth_date is None:
        return None, None
    rule = DOSE_RULES[key]
    earliest = minimum_age_date(birth_date, *key)
    if rule.previous:
        previous = groups.get(rule.previous, _NO_RECORDS)
        if previous["counting"] is not None:
            previous_day = _record_day(previous["counting"])
            if previous_day is not None:
                earliest = max(earliest, previous_day + timedelta(weeks=rule.min_interval_weeks))
        elif previous["invalid"]:
            # The previous dose will be repeated. This one follows the repeat, which cannot
            # be given before its own earliest date, nor before today.
            previous_date, missing = _due_parts(rule.previous, birth_date, groups, today_date)
            if previous_date is None:
                return None, missing or rule.previous
            earliest = max(earliest, max(previous_date, today_date)
                           + timedelta(weeks=rule.min_interval_weeks))
        else:
            return None, rule.previous
    for early in group["invalid"]:
        early_day = _record_day(early)
        if early_day is not None:
            earliest = max(earliest, early_day + timedelta(weeks=REPEAT_INTERVAL_WEEKS[key[0]]))
    return earliest, None


def dose_due(code, dose_number, birth_date, groups, on_date):
    """What a screen prints as a dose's DUE date (Task 15, D2): the earliest date the dose can
    actually be given, never a date counted from birth that the child cannot reach.

    Returns {"date", "text"}. `date` is the later of the dose's minimum age date, the previous
    valid dose + the minimum interval, and (for a repeat) the last invalid dose + the series'
    interval. When the previous dose will be repeated, the date follows the repeat. When a
    previous dose has no record at all, there is no date and `text` reads "After <that dose>".
    A dose that already counts has nothing due ("—"). The recommended age is a different
    column and is not touched.
    """
    on_date = as_date(on_date)
    due, missing = _due_parts((code, dose_number), birth_date, groups, on_date)
    if due is not None:
        return {"date": due, "text": display_date(due)}
    if missing is not None:
        return {"date": None, "text": f"After {dose_label(*missing)}"}
    return {"date": None, "text": "—"}


def too_young_message(patient, code, dose_number, birth_date):
    """The one sentence a dose given elsewhere is refused with when the child is too young."""
    name = (patient or {}).get("first_name") or "This child"
    opens = elsewhere_opens_on(birth_date, code, dose_number)
    return (f"{name} is not old enough for {dose_label(code, dose_number)} yet. "
            f"It can be recorded from {display_date(opens)}.")


def elsewhere_opens_on(birth_date, code, dose_number):
    """The first day a dose can be recorded as given elsewhere (Task 15, D1): its minimum age
    date minus the 4-day grace. None when the child has no birth date on file."""
    if birth_date is None:
        return None
    return minimum_age_date(birth_date, code, dose_number) - timedelta(days=RECORD_GRACE_DAYS)


def may_record_elsewhere(birth_date, group, code, dose_number, on_date):
    """May this dose be recorded as given elsewhere on on_date? (Task 15, D1.) Not before the
    child is old enough for it. A dose that has a parent's report (to upgrade it to a card) or
    needs a repeat is always open."""
    opens = elsewhere_opens_on(birth_date, code, dose_number)
    if opens is None or group["parent"] is not None or group["invalid"]:
        return True
    return as_date(on_date) >= opens


def dose_today_field(key):
    """'PENTA:2' -> 'dose_today_PENTA_2'. The key a refusal of a dose ticked as given today
    is reported under, so the form can print it under that row."""
    return "dose_today_" + str(key or "").replace(":", "_")


def check_given_today(patient, dose_keys, visit_date, reported_entries=()):
    """Refuse every ticked "given today" dose that is not eligible (Task 13, D3).

    Returns {field: message}, empty when every dose may be given. The server runs this on
    every save, so a forged POST for a dose that is not due is refused the same way the form
    greys it out. Several eligible doses in one visit are fine (co-administration is normal).
    A dose reported at this same visit on a card, with its date, counts as on file for the
    doses after it in its series, so a child can have the card dose and the next dose in one
    visit when the interval allows.
    """
    birth = as_date(patient["birth_date"]) if patient.get("birth_date") else None
    records = [annotate_evidence(r) for r in get_immunizations_for_patient(patient["id"])]
    on_file = dose_groups(birth, [dict(r) for r in records])
    for entry in reported_entries or ():
        key = (entry["code"], entry["dose_number"])
        if entry.get("evidence") == EVIDENCE_CARD and entry.get("date") and (
                on_file.get(key, _NO_RECORDS)["counting"] is None):
            records.append({"vaccine_code": entry["code"], "dose_number": entry["dose_number"],
                            "evidence": EVIDENCE_CARD, "date_administered": entry["date"]})
    groups = dose_groups(birth, records)
    errors = {}
    for code, dose_number in dose_keys:
        message = not_due_message(code, dose_number, birth, groups, visit_date)
        if message:
            errors[dose_today_field(f"{code}:{dose_number}")] = message
    return errors


def not_due_message(code, dose_number, birth_date, groups, on_date):
    """The one sentence the server refuses a non-eligible dose with, or None if eligible."""
    verdict = dose_eligibility(code, dose_number, birth_date, groups, on_date)
    if verdict["eligible"]:
        return None
    if verdict["reason"] == "Already recorded":
        return f"{dose_label(code, dose_number)} is already recorded. It cannot be given again."
    if verdict["earliest"] is not None:
        return f"This dose is not due yet. Earliest date: {display_date(verdict['earliest'])}."
    return f"This dose is not due yet. {verdict['reason']}."


def _dose_status(record, due_date, reference, too_early=False):
    """Completed / Given elsewhere / Parent says given / Given too early / No record / Due Now / Upcoming.

    A record counts only when its evidence does: given here is Completed, a card is
    Given elsewhere, and a parent's report is its own status and does NOT count as
    given. A dose on file only as doses given too early reads Given too early, whatever
    its evidence (Task 14). Without any record, the status comes from the due date.
    """
    if too_early:
        return TOO_EARLY
    if record is not None:
        evidence = record.get("evidence")
        if evidence == EVIDENCE_GIVEN_HERE:
            return COMPLETED
        if evidence == EVIDENCE_CARD:
            return GIVEN_ELSEWHERE
        return PARENT_REPORT
    if due_date is None:
        # No birthdate on record, so no due date can be computed. Reported as
        # Upcoming rather than No record: an unknown age is a data gap, and putting a
        # child on the follow-up list would be on no evidence.
        return UPCOMING
    if reference < due_date:
        return UPCOMING
    if reference <= due_date + timedelta(days=GRACE_PERIOD_DAYS):
        return DUE_NOW
    return NO_RECORD


def get_immunizations_for_patient(patient_id):
    """Every dose recorded for one patient, oldest first."""
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT i.id, i.patient_id, i.consultation_id, i.vaccine_code, i.dose_number,
               i.evidence, i.place_given, i.date_administered, i.administered_by, i.notes, i.created_at,
               u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        WHERE i.patient_id = ?
        ORDER BY i.date_administered, i.id
        """,
            (patient_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_immunizations_for_consultation(consultation_id):
    """The doses given during one consultation, in schedule order."""
    if not consultation_id:
        return []
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT i.id, i.vaccine_code, i.dose_number, i.evidence, i.place_given, i.date_administered,
               i.notes, u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        WHERE i.consultation_id = ?
        """,
            (consultation_id,),
        ).fetchall()
    given = [dict(row) for row in rows]
    order = {(row[0], row[3]): index for index, row in enumerate(EPI_SCHEDULE)}
    given.sort(key=lambda dose: order.get((dose["vaccine_code"], dose["dose_number"]), 99))
    for dose in given:
        dose["vaccine"] = VACCINE_NAMES.get(dose["vaccine_code"], dose["vaccine_code"])
        dose["label"] = dose_label(dose["vaccine_code"], dose["dose_number"])
        annotate_evidence(dose)
    return given


def annotate_evidence(record):
    """Add the provenance keys a screen reads, in place. Returns the record.

    `evidence` is defaulted, `reported` (the dose was not given here), `counts` (the
    evidence counts as given), `parent_report`, the two labels and `date_known` are
    derived here rather than in each template, so a screen asks one boolean instead of
    comparing a stored string it could compare wrongly.

    Every list of doses this module hands out goes through it: the patient's
    history, one consultation's doses, and each entry in the schedule.
    """
    evidence = record.get("evidence") or EVIDENCE_GIVEN_HERE
    record["evidence"] = evidence
    record["reported"] = evidence != EVIDENCE_GIVEN_HERE
    record["counts"] = evidence in COUNTS_AS_GIVEN
    record["parent_report"] = evidence == EVIDENCE_PARENT
    record["evidence_label"] = dose_evidence_label(evidence)
    record["evidence_short_label"] = dose_evidence_label(evidence, short=True)
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


def _dose_history(group, shown):
    """The records of one dose that are not the one its row shows, as screen-ready lines.

    A dose given too early reads "Earlier dose on <date> was too early" (Task 14, D2). A
    parent's report beside a record that counts, or any other valid record, is named too,
    so nothing on file is hidden. Each line carries its record, for the Change or Correct
    button.
    """
    lines = []
    for record in group["invalid"]:
        if record is not shown:
            lines.append({"record": record, "kind": "too_early", "text": (
                f"Earlier dose on {display_date(record['date_administered'])} was too early")})
    if group["parent"] is not None and group["parent"] is not shown:
        lines.append({"record": group["parent"], "kind": "parent_report",
                      "text": EVIDENCE_LABELS[EVIDENCE_PARENT]})
    for record in group["extra"]:
        lines.append({"record": record, "kind": "extra", "text": (
            f"Another dose on {display_date(record['date_administered'])} is on file")})
    return lines


def get_immunization_status(patient, on_date=None, records=None):
    """Where one child stands against the DOH EPI schedule.

    The single authority behind every immunisation figure in the system. Returns:

        applicable      the EPI infant schedule still applies (under 5)
        schedule        one entry per scheduled dose, in schedule order, each
                        carrying its status, badge class, administered detail and
                        -- where a dose is on file -- where that dose came from
        attention_items the No record, Due Now and parent-report entries, most urgent first
        extra_records   doses on file that the current schedule does not list
        counts          given / given here / given elsewhere / parent report /
                        due_now / no_record / upcoming / total
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

    # Annotated on the way in, so a caller that handed `records` in -- the roster
    # readers below do, to avoid a query per child -- gets provenance on those
    # rows too rather than only on the schedule built from them.
    for record in records:
        annotate_evidence(record)
    # Every recorded dose judged once for the whole child (Task 14, D1), then grouped by dose.
    groups = dose_groups(birth_date, records)

    schedule = []
    for code, vaccine, protects, dose_number, total, value, unit, note in EPI_SCHEDULE:
        group = groups.get((code, dose_number), _NO_RECORDS)
        counting = group["counting"]
        # A dose on file only as doses given too early must be repeated (D2).
        too_early = counting is None and bool(group["invalid"])
        # The row shows the record that counts; with none, the latest dose given too early,
        # then a parent's report. Every other record of the dose is history under it.
        record = counting or (group["invalid"][-1] if group["invalid"] else None) or group["parent"]
        history = _dose_history(group, record)
        recommended = due_date_for(birth_date, value, unit)
        due = dose_due(code, dose_number, birth_date, groups, reference)
        # A dose is "due" only from the day it can actually be given, so one that must wait for
        # another dose does not read Due Now or No record before then (Task 15, D2).
        due_date = max(recommended, due["date"]) if (recommended and due["date"]) else recommended
        status = _dose_status(record, due_date, reference, too_early)
        verdict = dose_eligibility(code, dose_number, birth_date, groups, reference)
        # Past the cohort the schedule describes, "No record" and "Due Now" stop being
        # useful readings -- the infant programme's window has closed, and flagging a
        # 30-year-old would be noise on every screen that counts them. What is on file
        # is still reported.
        if not applicable and status in (NO_RECORD, DUE_NOW):
            status = UPCOMING
        # A parent's report is only chased once the dose is due: ask for the card.
        needs_attention = status in (NO_RECORD, DUE_NOW) or (
            status == TOO_EARLY and applicable) or (
            status == PARENT_REPORT and applicable
            and due_date is not None and reference >= due_date)
        counts_as_given = counting is not None
        elsewhere_ok = may_record_elsewhere(birth_date, group, code, dose_number, reference)
        schedule.append({
            "code": code,
            "vaccine": vaccine,
            "protects": protects,
            "dose_number": dose_number,
            "total_doses": total,
            "label": dose_label(code, dose_number),
            "timing": note,
            # What the screens print as Due: the earliest date the dose can actually be given
            # (None with "After <dose>" when a previous dose has no record, "—" when it counts).
            "due_date": due["date"],
            "due_text": due["text"],
            # The date the schedule recommends, counted from birth. Kept for the status.
            "recommended_date": recommended,
            "status": status,
            "badge_class": STATUS_BADGE_CLASS[status],
            "needs_attention": needs_attention,
            # Counts as given for completion and coverage: a valid dose given here, or seen
            # on a card. A parent's report is on file but is NOT given; a dose given too
            # early is on file and does not count.
            "given": counts_as_given,
            # A record exists for this dose, of any evidence.
            "on_file": record is not None,
            # The "Record dose given elsewhere" button is offered on exactly these:
            # nothing that counts on file (a repeat can be recorded after a dose given too
            # early, and a card can upgrade a parent's report).
            "can_record_elsewhere": not counts_as_given and elsewhere_ok,
            # May a dose given elsewhere be recorded for it today (Task 15, D1)? The child must
            # be old enough, unless the dose has a parent's report or needs a repeat.
            "elsewhere_ok": elsewhere_ok,
            # The one rule (D1): may this dose be given today? The form ticks only these.
            "eligible": verdict["eligible"],
            "earliest_date": verdict["earliest"],
            "eligibility_reason": verdict["reason"],
            "too_early": too_early,
            # The other records of this dose, shown under its row: doses given too early
            # and a parent's report, each {"record", "kind", "text"}.
            "history": history,
            # The immunizations row behind this scheduled dose, when one exists.
            # Carried so the Patient Profile's Correct action can name the record
            # it means -- the (code, dose) pair identifies the dose in the
            # schedule, but the correction endpoint has to be handed the row's
            # own id, because correcting a dose may change that very pair.
            "record_id": record["id"] if record else None,
            "date_administered": record["date_administered"] if record else None,
            "administered_by_name": record["administered_by_name"] if record else None,
            "consultation_id": record["consultation_id"] if record else None,
            "place_given": record.get("place_given") if record else None,
            # What the record rests on, for the row that has one. None on a dose with
            # no record -- a default of "given here" there would be a claim about a
            # dose nobody has recorded.
            "evidence": record["evidence"] if record else None,
            "reported": bool(record and record["reported"]),
            "parent_report": bool(record and record["parent_report"]),
            "evidence_label": record["evidence_label"] if record else None,
            "evidence_short_label": record["evidence_short_label"] if record else None,
            # False for a dose whose date nobody knows, and for a dose with no record.
            # A screen asks this rather than testing the date, because those two cases
            # print different sentences.
            "date_known": bool(record and record["date_known"]),
            # What the form's checkboxes post back -- both of them, the one that
            # records a dose as given today and the one that records it as
            # given elsewhere.
            "key": f"{code}:{dose_number}",
            "reported_date_field": reported_date_field(f"{code}:{dose_number}"),
            "reported_proof_field": reported_proof_field(f"{code}:{dose_number}"),
        })

    extra_records = [
        annotate_evidence(record) for record in records
        if (record["vaccine_code"], record["dose_number"]) not in SCHEDULE_KEYS
    ]
    for record in extra_records:
        record["label"] = dose_label(record["vaccine_code"], record["dose_number"])

    counts = {status: sum(1 for item in schedule if item["status"] == status)
              for status in STATUS_ORDER}
    # How the given doses divide, counted here rather than by each screen filtering
    # the schedule itself, so the profile's summary line, the report card and the
    # flash message all report the same number.
    given_count = counts[COMPLETED] + counts[GIVEN_ELSEWHERE]
    attention_items = sorted(
        (item for item in schedule if item["needs_attention"]),
        key=lambda item: (_STATUS_RANK[item["status"]], item["due_date"] or item["recommended_date"] or reference),
    )
    next_due = next(
        (item for item in schedule if not item["given"]
         and item["due_date"] is not None),
        None,
    ) or next((item for item in schedule if not item["given"]), None)

    follow_up_title, follow_up_line = follow_up_text(attention_items, reference)
    return {
        "applicable": applicable,
        "age_years": age_years,
        "follow_up_title": follow_up_title,
        "follow_up_line": follow_up_line,
        "schedule": schedule,
        "attention_items": attention_items,
        "extra_records": extra_records,
        "records": records,
        # Doses that count as given: given here plus given elsewhere with a card.
        "completed_count": given_count,
        "given_here_count": counts[COMPLETED],
        "elsewhere_count": counts[GIVEN_ELSEWHERE],
        "parent_report_count": counts[PARENT_REPORT],
        "due_count": counts[DUE_NOW],
        "no_record_count": counts[NO_RECORD],
        "too_early_count": counts[TOO_EARLY],
        "upcoming_count": counts[UPCOMING],
        "total_doses": TOTAL_SCHEDULED_DOSES,
        "attention_count": len(attention_items),
        "needs_attention": bool(attention_items) and applicable,
        "next_due": next_due,
        "summary": _summarise(counts, applicable),
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "grace_period_days": GRACE_PERIOD_DAYS,
    }


def _join_names(names):
    """'A', 'A and B', 'A, B and C'."""
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def follow_up_text(attention_items, reference):
    """The short alert the profile and the consultation form print (Task 15, D4).

    Returns (title, line). The title is "<N> doses to follow up". The line lists the doses,
    grouped by what is wrong with them, for example "Pentavalent dose 1 (repeat from Oct 31,
    2026); BCG and Hepatitis B (parent says given, no card). Ask for the vaccination card."
    """
    reference = as_date(reference)
    groups = {}
    for item in attention_items:
        status = item["status"]
        if status == TOO_EARLY:
            if item["due_date"] is None:
                phrase = "repeat needed"
            elif item["due_date"] > reference:
                phrase = f"repeat from {display_date(item['due_date'])}"
            else:
                phrase = "repeat due now"
        elif status == NO_RECORD:
            phrase = "no record"
        elif status == DUE_NOW:
            phrase = "due now"
        else:
            phrase = "parent says given, no card"
        groups.setdefault(phrase, []).append(item["label"])
    line = "; ".join(f"{_join_names(names)} ({phrase})" for phrase, names in groups.items()) + "."
    if any(item["status"] in (NO_RECORD, PARENT_REPORT) for item in attention_items):
        line += " Ask for the vaccination card."
    count = len(attention_items)
    return f"{count} dose{'' if count == 1 else 's'} to follow up", line


def _summarise(counts, applicable):
    """The one-line reading every screen prints rather than composing its own.

    A clause is printed only when there is something to say: a standing "0 parent
    reports" on every child's summary would be noise.
    """
    given = counts[COMPLETED] + counts[GIVEN_ELSEWHERE]
    parts = [f"{given} of {TOTAL_SCHEDULED_DOSES} scheduled doses given"]
    if counts[GIVEN_ELSEWHERE]:
        parts.append(f"{counts[GIVEN_ELSEWHERE]} given elsewhere (card seen)")
    if counts[PARENT_REPORT]:
        parts.append(f"{counts[PARENT_REPORT]} parent says given, no card")
    if not applicable:
        parts.append("EPI infant schedule no longer applies at this age")
        return " · ".join(parts)
    if counts[TOO_EARLY]:
        parts.append(f"{counts[TOO_EARLY]} given too early, not counted")
    if counts[NO_RECORD]:
        parts.append(f"{counts[NO_RECORD]} with no record")
    if counts[DUE_NOW]:
        parts.append(f"{counts[DUE_NOW]} due now")
    if not counts[NO_RECORD] and not counts[DUE_NOW] and not counts[TOO_EARLY]:
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

    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT i.id, i.patient_id, i.consultation_id, i.vaccine_code, i.dose_number,
               i.evidence, i.place_given, i.date_administered, i.administered_by, i.notes, i.created_at,
               u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        ORDER BY i.date_administered, i.id
        """
        ).fetchall()

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
    """Children with a dose due, with no record, or with only a parent's report.

    Same role as get_low_stock_alert(). The dashboards' figure and list, and the set
    the queue reads to decide which rows carry a badge. Everything derives from
    get_immunization_status(), so the dashboard card, the queue badge and the child's
    own profile cannot disagree.

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
            "no_record_count": status["no_record_count"],
            "due_count": status["due_count"],
            "parent_report_count": sum(
                1 for item in status["attention_items"] if item["status"] == PARENT_REPORT),
            "attention_count": status["attention_count"],
            "next_label": status["attention_items"][0]["label"],
            "next_status": status["attention_items"][0]["status"],
            "next_badge_class": status["attention_items"][0]["badge_class"],
        })

    # Most doses with no record first, then most due, then youngest -- the order a
    # health worker would work the follow-up list in.
    children.sort(key=lambda child: (
        -child["no_record_count"], -child["due_count"],
        child["patient"].get("birth_date") or "",
    ))

    return {
        "children": children if limit is None else children[:limit],
        "child_count": len(children),
        "no_record_child_count": sum(1 for child in children if child["no_record_count"]),
        # Doses to follow up across those children: no record, due now, or only a parent's word.
        "due_dose_count": sum(child["attention_count"] for child in children),
        "no_record_dose_count": sum(child["no_record_count"] for child in children),
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

    `enrolled` is the number of distinct patients with at least one dose that COUNTS
    (given here, or given elsewhere with a card) -- the only defensible reading of "how
    many are in the immunisation programme" from what is stored, because nothing
    anywhere records an enrolment. A child who is due a dose but has never had one is
    therefore not counted here; `awaiting_first_dose` says how many those are, so the
    gap is stated rather than hidden.

    A parent's report counts toward nothing here (CDC: without a written, dated record
    the child is treated as unvaccinated). It is shown as its own figure,
    `doses_parent_report`.

    The no-record figures come from get_immunization_alert(), the same call behind
    both dashboards and the queue badges, so this panel cannot report a different
    number from the rest of the project.

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
    # A card dose given too early does not count (Task 13, D4), so it is left out of every
    # figure below except the parent-report one, which never counted anyway.
    rows = _valid_dose_rows()
    lo, hi = window["start"].isoformat(), window["end"].isoformat()

    def in_window(row):
        day = (row["date_administered"] or "")[:10]
        return bool(day) and lo <= day <= hi

    # Split by evidence, all time and in the window, because "doses given" and "doses this
    # health center gave" are not the same number. A single total would credit another
    # hospital's work to this one on the Barangay Official's dashboard, which is the one
    # screen in the project a figure leaves the building from. Coverage is about the child
    # and counts every dose that has written evidence; activity is about the health center
    # and counts only its own. A dose with no date is in no window.
    by_evidence, scoped_by_evidence = {}, {}
    for row in rows:
        by_evidence[row["evidence"]] = by_evidence.get(row["evidence"], 0) + 1
        if in_window(row):
            scoped_by_evidence[row["evidence"]] = scoped_by_evidence.get(row["evidence"], 0) + 1
    enrolled = len({row["patient_id"] for row in rows if row["evidence"] != EVIDENCE_PARENT})
    scoped_children = len({row["patient_id"] for row in rows
                           if row["evidence"] != EVIDENCE_PARENT and in_window(row)})

    here = by_evidence.get(EVIDENCE_GIVEN_HERE, 0)
    card = by_evidence.get(EVIDENCE_CARD, 0)
    scoped_here = scoped_by_evidence.get(EVIDENCE_GIVEN_HERE, 0)
    scoped_card = scoped_by_evidence.get(EVIDENCE_CARD, 0)

    alert = get_immunization_alert(on_date=on_date)
    return {
        "window": {
            "start": window["start"],
            "end": window["end"],
            "custom": window["custom"],
            "doses_given": scoped_here + scoped_card,
            "doses_administered": scoped_here,
            "doses_elsewhere": scoped_card,
            "doses_parent_report": scoped_by_evidence.get(EVIDENCE_PARENT, 0),
            "children_dosed": scoped_children,
        },
        "enrolled": enrolled,
        "doses_given": here + card,
        "doses_administered": here,
        "doses_elsewhere": card,
        "doses_parent_report": by_evidence.get(EVIDENCE_PARENT, 0),
        "needing_attention": alert["child_count"],
        "no_record_children": alert["no_record_child_count"],
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
    how many of the eligible children have had it, and how many have no record, are due
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
        for status in eligible:
            counts[status["schedule"][index]["status"]] += 1
        given = counts[COMPLETED] + counts[GIVEN_ELSEWHERE]
        doses.append({
            "code": code,
            "vaccine": vaccine,
            "protects": protects,
            "dose_number": dose_number,
            "total_doses": total,
            "label": dose_label(code, dose_number),
            "timing": note,
            # `given` is the coverage figure: children with written evidence of this
            # dose, given here or seen on a card. A parent's report is NOT in it.
            "given": given,
            "administered": counts[COMPLETED],
            "elsewhere": counts[GIVEN_ELSEWHERE],
            "parent_report": counts[PARENT_REPORT],
            "no_record": counts[NO_RECORD],
            "due_now": counts[DUE_NOW],
            "upcoming": counts[UPCOMING],
            "eligible": cohort,
            # None rather than 0 when there is nobody to count, so a screen can
            # tell "no eligible children" apart from "nobody has had it".
            "coverage_pct": round(given * 100 / cohort) if cohort else None,
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
            "elsewhere": sum(dose["elsewhere"] for dose in entries),
            "parent_report": sum(dose["parent_report"] for dose in entries),
            "scheduled": scheduled,
            "coverage_pct": round(given * 100 / scheduled) if scheduled else None,
            "no_record": sum(dose["no_record"] for dose in entries),
            "due_now": sum(dose["due_now"] for dose in entries),
        })

    return {
        "reference_date": reference,
        "eligible_children": cohort,
        "doses": doses,
        "by_vaccine": by_vaccine,
        "total_given": sum(dose["given"] for dose in doses),
        "total_administered": sum(dose["administered"] for dose in doses),
        "total_elsewhere": sum(dose["elsewhere"] for dose in doses),
        "total_parent_report": sum(dose["parent_report"] for dose in doses),
        "total_scheduled": TOTAL_SCHEDULED_DOSES * cohort,
        "total_no_record": sum(dose["no_record"] for dose in doses),
        "total_due_now": sum(dose["due_now"] for dose in doses),
    }


def _valid_dose_rows():
    """Every dose row that counts toward a figure (Task 14, D1), as dicts: valid doses and
    parent's reports. A dose given too early, whatever its evidence, is left out.

    The reports count doses in SQL-shaped questions; whether a dose was early depends on the
    child's birth date and the other doses of the series, so the rows are read once and
    judged here with the same rule the profile uses.
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT i.id, i.patient_id, i.vaccine_code, i.dose_number, i.evidence,
               i.date_administered, p.birth_date
        FROM immunizations i JOIN patients p ON p.id = i.patient_id
        """
        ).fetchall()
    by_patient = {}
    for row in rows:
        by_patient.setdefault(row["patient_id"], []).append(dict(row))
    valid = []
    for records in by_patient.values():
        birth = as_date(records[0]["birth_date"]) if records[0]["birth_date"] else None
        verdicts = judge_records(birth, records)
        valid.extend(r for r, v in zip(records, verdicts) if v in (VERDICT_VALID, VERDICT_REPORT))
    return valid


def _patients_with_doses():
    """Patients with at least one dose that counts as given (not a parent's report, not
    a card dose given too early)."""
    return {row["patient_id"] for row in _valid_dose_rows() if row["evidence"] != EVIDENCE_PARENT}


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


def reported_proof_field(key):
    """'PENTA:2' -> 'elsewhere_proof_PENTA_2'. The per-row proof choice's field name."""
    return "elsewhere_proof_" + str(key or "").replace(":", "_")


# What the consultation form's error summary calls each of those boxes.
#
# The summary at the top of the page prints field_labels.get(field, field), so
# without this a mistyped date would be reported as "elsewhere_date_PENTA_2" --
# a field name, to a health worker, at the moment they are being told something
# is wrong. Built from EPI_SCHEDULE through the same functions the form and
# the parser use, so a schedule revision cannot leave a label behind.
REPORTED_DATE_LABELS = {
    reported_date_field(f"{row[0]}:{row[3]}"):
        f"{dose_label(row[0], row[3])} — date given elsewhere"
    for row in EPI_SCHEDULE
}
REPORTED_DATE_LABELS.update({
    dose_today_field(f"{row[0]}:{row[3]}"): f"{dose_label(row[0], row[3])} — given today"
    for row in EPI_SCHEDULE
})
REPORTED_DATE_LABELS.update({
    reported_proof_field(f"{row[0]}:{row[3]}"):
        f"{dose_label(row[0], row[3])} — proof of the dose given elsewhere"
    for row in EPI_SCHEDULE
})


def validate_reported_date(raw, patient, visit_date=None, required=False):
    """Read one 'given elsewhere' date box. Returns (iso_text_or_None, error).

    BLANK IS VALID unless `required`. The date is required when the dose was seen on
    a card (written, dated evidence) and optional for a parent's report: a parent who
    remembers their child had BCG at the hospital where they were born may not
    remember the day, and forcing one would mean an invented date in a clinical record.

    What it holds a date to, once one is typed:

        a real date            anything else is a typo, not a record
        not in the future      a dose cannot have been given after today
        not after this visit   "previously given" means before the encounter that
                               is recording it (only when a visit date is given)
        not before birth       the child did not exist to be vaccinated
        within living memory   where no birth date is on file to check against,
                               MAX_BACKDATE_YEARS catches a mistyped year
    """
    text = str(raw or "").strip()
    if not text:
        if required:
            return None, "Enter the date shown on the card."
        return None, None

    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None, (
            "Enter a valid date in YYYY-MM-DD format"
            + ("." if required else ", or leave it blank if the date it was given is not known.")
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


def clean_place(raw):
    """The place a dose was given, trimmed and capped. Blank is allowed (None)."""
    text = " ".join(str(raw or "").split())
    return text[:MAX_PLACE_LENGTH] or None


def validate_evidence(raw_evidence):
    """The proof the person chose: 'card' or 'parent_report'. Returns (value, error)."""
    value = str(raw_evidence or "").strip()
    if value not in ELSEWHERE_EVIDENCE:
        return None, "Choose how you know: the vaccination card, or the parent's word."
    return value, None


def parse_reported_doses(form_data, patient, visit_date=None, given_today=()):
    """Read the "previously given elsewhere" ticks. Returns (entries, errors).

    `entries` is [{'code', 'dose_number', 'evidence', 'date', 'key', 'label'}] in
    schedule order, ready for record_reported_immunizations(). `errors` is {field:
    message}, which the caller merges into the consultation form's own errors so
    one refusal summary covers the whole page.

    Each ticked row must say what it rests on: the card was seen (a date is
    required) or the parent says so (the date is optional).

    The tick boxes go through parse_dose_keys(), the same gate the "given today"
    boxes do, so a hand-made POST cannot report a dose the DOH schedule does not
    list any more than it can record one.

    A DOSE TICKED IN BOTH COLUMNS IS REFUSED, NOT RESOLVED: the two claims are
    incompatible, and picking one silently would store a clinical fact nobody
    asserted.
    """
    raw_keys = (form_data.getlist(IMMUNIZATION_ELSEWHERE_FIELD)
                if hasattr(form_data, "getlist")
                else (form_data.get(IMMUNIZATION_ELSEWHERE_FIELD) or []))
    keys = parse_dose_keys(raw_keys)
    conflicting = set(given_today or ())
    on_file = None
    if keys and patient and patient.get("id"):
        birth = as_date(patient["birth_date"]) if patient.get("birth_date") else None
        on_file = (birth, dose_groups(birth, [dict(r) for r in get_immunizations_for_patient(patient["id"])]))
    reference = as_date(visit_date) if visit_date is not None else today()

    entries, errors = [], {}
    for code, dose_number in keys:
        key = f"{code}:{dose_number}"
        field = reported_date_field(key)
        proof_field = reported_proof_field(key)

        # Not before the child is old enough for the dose (Task 15, D1).
        if on_file is not None and not may_record_elsewhere(
                on_file[0], on_file[1].get((code, dose_number), _NO_RECORDS), code, dose_number, reference):
            errors[field] = too_young_message(patient, code, dose_number, on_file[0])
            continue

        if (code, dose_number) in conflicting:
            errors[field] = (
                f"{dose_label(code, dose_number)} is ticked both as given today "
                "and as previously given elsewhere. Choose one."
            )
            continue

        evidence, proof_error = validate_evidence(form_data.get(proof_field))
        if proof_error:
            errors[proof_field] = proof_error
            continue

        date_text, date_error = validate_reported_date(
            form_data.get(field), patient, visit_date,
            required=evidence == EVIDENCE_CARD,
        )
        if date_error:
            errors[field] = date_error
            continue

        entries.append({
            "code": code,
            "dose_number": dose_number,
            "evidence": evidence,
            "date": date_text,
            "key": key,
            "label": dose_label(code, dose_number),
        })

    # A date typed against a row whose box was never ticked is a save about to
    # discard what somebody entered. Say so rather than drop it silently.
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


def _records_in(conn, patient_id):
    """Every dose record of one child, read through `conn`, plus the child's birth date."""
    rows = conn.execute(
        "SELECT id, patient_id, vaccine_code, dose_number, evidence, date_administered, "
        "place_given FROM immunizations WHERE patient_id = ? ORDER BY date_administered, id",
        (patient_id,)).fetchall()
    birth = conn.execute("SELECT birth_date FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return [dict(row) for row in rows], (
        as_date(birth["birth_date"]) if birth and birth["birth_date"] else None)


def _groups_in(conn, patient_id):
    """dose_groups() for one child, read through `conn` so the answer is true at the moment
    the write happens (the same reason correct_immunization() checks inside its transaction)."""
    records, birth = _records_in(conn, patient_id)
    return dose_groups(birth, records)


def _same_record_on_file(group, evidence, day):
    """True when the dose already has a record with this evidence and this date."""
    others = group["invalid"] + group["extra"] + ([group["parent"]] if group["parent"] else [])
    return any(r["evidence"] == evidence and r["date_administered"] == day for r in others)


def record_immunizations(patient_id, dose_keys, administered_by, date_administered,
                         consultation_id=None, audit=None):
    """Write the doses THIS HEALTH CENTER gave at one visit. Returns the pairs stored.

    A dose that already counts (a valid record on file) is left exactly as it was rather than
    being re-dated to today, and a second valid record is refused: double-clicking Save must
    not rewrite the history of when a child was actually vaccinated. A dose that is on file
    only as a record given too early gets a NEW record: the repeat (Task 14, D2). The earlier
    record stays as history.

    ONE EXCEPTION: a dose on file only as a parent's report (no card) is not given as
    far as the schedule is concerned, and the child now really did get it here. That row
    is changed to 'given_here', dated today, against this consultation.

    `evidence` is written explicitly rather than left to the column default: a row
    this function writes is a positive claim that a health worker here administered
    the dose, and a claim that large should be made in the INSERT where it can be read.
    `audit(conn, stored)` is called before the commit when something was stored.
    """
    if not dose_keys:
        return []

    day = date_administered
    day = day.isoformat() if hasattr(day, "isoformat") else str(day)

    stored = []
    with db_connection() as conn:
        for code, dose_number in dose_keys:
            group = _groups_in(conn, patient_id).get((code, dose_number), _NO_RECORDS)
            if group["counting"] is not None:
                continue
            if group["parent"] is not None:
                conn.execute(
                    """
                UPDATE immunizations
                   SET evidence = ?, consultation_id = ?, date_administered = ?,
                       administered_by = ?, place_given = NULL
                 WHERE id = ? AND evidence = ?
                """,
                    (EVIDENCE_GIVEN_HERE, consultation_id, day, administered_by,
                     group["parent"]["id"], EVIDENCE_PARENT),
                )
            else:
                conn.execute(
                    """
                INSERT INTO immunizations
                    (patient_id, consultation_id, vaccine_code, dose_number,
                     evidence, date_administered, administered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (patient_id, consultation_id, code, dose_number,
                     EVIDENCE_GIVEN_HERE, day, administered_by),
                )
            stored.append((code, dose_number))
        if audit and stored:
            audit(conn, stored)
        conn.commit()
    return stored


def record_reported_immunizations(patient_id, entries, recorded_by,
                                  consultation_id=None, audit=None):
    """Write doses reported at one visit as already given elsewhere.

    `entries` is [{'code', 'dose_number', 'evidence', 'date'}], where `evidence` is
    'card' or 'parent_report' and `date` is an ISO string or None (None only for a
    parent's report). Returns the (code, dose_number, date) triples actually stored, so
    the caller can name them in a flash message and an audit line.

    THE CONSULTATION IS REQUIRED HERE, NOT IN THE SCHEMA: this is the consultation
    form's path. Doses given elsewhere are also recorded with no consultation, from the
    Immunization Record tab (record_elsewhere_dose() below).

    A dose that already counts is left exactly as it is, with one exception: a parent's
    report is upgraded when this visit sees the card. A child who really was given
    Pentavalent 1 here last month does not have that record overwritten by a recollection.
    A dose on file only as a record given too early takes the card as a new record (a
    repeat given elsewhere, Task 14), unless the same card record is already on file.

    `recorded_by` goes into administered_by, the one column whose name reads slightly
    wide of what it holds. It is not renamed: it is a foreign key on every dose ever
    recorded. No screen prints it as "administered by" for a dose given elsewhere.
    `audit(conn, stored)` is called before the commit when something was stored.
    """
    if not entries or not consultation_id:
        return []

    stored = []
    with db_connection() as conn:
        for entry in entries:
            day = entry.get("date")
            if day is not None and hasattr(day, "isoformat"):
                day = day.isoformat()
            evidence = entry.get("evidence") or EVIDENCE_CARD
            group = _groups_in(conn, patient_id).get((entry["code"], entry["dose_number"]),
                                                     _NO_RECORDS)
            if group["counting"] is not None or _same_record_on_file(group, evidence, day):
                continue
            if evidence == EVIDENCE_CARD and group["parent"] is not None:
                conn.execute(
                    "UPDATE immunizations SET evidence = ?, date_administered = ?, "
                    "administered_by = ? WHERE id = ? AND evidence = ?",
                    (EVIDENCE_CARD, day, recorded_by, group["parent"]["id"], EVIDENCE_PARENT))
            elif evidence == EVIDENCE_PARENT and group["parent"] is not None:
                continue
            else:
                conn.execute(
                    """
                INSERT INTO immunizations
                    (patient_id, consultation_id, vaccine_code, dose_number,
                     evidence, date_administered, administered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (patient_id, consultation_id, entry["code"], entry["dose_number"],
                     evidence, day, recorded_by),
                )
            stored.append((entry["code"], entry["dose_number"], day))
        if audit and stored:
            audit(conn, stored)
        conn.commit()
    return stored


def _valid_evidence_row(evidence, day):
    """The model's own refusal of what the form should never send."""
    if evidence not in ELSEWHERE_EVIDENCE:
        return False
    return not (evidence == EVIDENCE_CARD and not day)


def _would_double_count(records, birth, record_id, new_values, key):
    """True if changing record `record_id` to `new_values` would leave the dose `key` with
    two valid records. Only one valid record per dose can exist (Task 14, D2)."""
    changed = [dict(r, **new_values) if r["id"] == record_id else dict(r) for r in records]
    groups = dose_groups(birth, changed)
    group = groups.get(key)
    return bool(group and group["extra"])


def record_elsewhere_dose(patient_id, code, dose_number, evidence, date_given, place,
                          recorded_by, audit=None):
    """Record one dose given elsewhere, outside a consultation (Task 9, D3).

    Returns the outcome:

        "recorded"       a new record was written
        "upgraded"       a parent's report is now a card record (the card was shown)
        "unchanged"      the same record was already on file; nothing changed
        "already-given"  the dose already counts as given (here, or a card): refused
        "too-young"      the child is not yet old enough for this dose (Task 15, D1): refused
        "invalid"        not a dose of the schedule, bad evidence, or a card with no date

    A dose on file only as a record given too early takes the new record beside it: the
    repeat (Task 14, D2). `audit(conn, outcome, evidence)` is called before the commit when
    something was written. The caller has already validated the date against the patient;
    this re-checks only what the table's rules need.
    """
    day = date_given.isoformat() if hasattr(date_given, "isoformat") else (date_given or None)
    if (code, dose_number) not in SCHEDULE_KEYS or not _valid_evidence_row(evidence, day):
        return "invalid"
    place = clean_place(place)
    with db_connection() as conn:
        records, birth = _records_in(conn, patient_id)
        group = dose_groups(birth, records).get((code, dose_number), _NO_RECORDS)
        if group["counting"] is not None:
            return "already-given"
        if not may_record_elsewhere(birth, group, code, dose_number, today()):
            return "too-young"
        if _same_record_on_file(group, evidence, day):
            return "unchanged"
        parent = group["parent"]
        if parent is None:
            conn.execute(
                """
            INSERT INTO immunizations
                (patient_id, consultation_id, vaccine_code, dose_number, evidence,
                 date_administered, place_given, administered_by)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
            """,
                (patient_id, code, dose_number, evidence, day, place, recorded_by))
            outcome = "recorded"
        elif evidence == EVIDENCE_PARENT:
            return "unchanged"
        else:
            conn.execute(
                "UPDATE immunizations SET evidence = ?, date_administered = ?, "
                "place_given = ?, administered_by = ? WHERE id = ? AND evidence = ?",
                (EVIDENCE_CARD, day, place, recorded_by, parent["id"], EVIDENCE_PARENT))
            outcome = "upgraded"
        if audit:
            audit(conn, outcome, evidence)
        conn.commit()
    return outcome


def update_elsewhere_dose(record_id, evidence, date_given, place, audit=None):
    """Change a card or parent's-report record (Task 9, D5). Returns the outcome:

        "updated"      evidence, date or place changed
        "upgraded"     a parent's report became a card record
        "unchanged"    nothing differed
        "duplicate"    the change would leave the dose with two valid records
        "not-allowed"  the record was given here: it is corrected on its own path
        "invalid"      bad evidence, or a card with no date
        "missing"      no such record

    `audit(conn, outcome)` is called before the commit, only when something changed.
    """
    day = date_given.isoformat() if hasattr(date_given, "isoformat") else (date_given or None)
    if not _valid_evidence_row(evidence, day):
        return "invalid"
    place = clean_place(place)
    with db_connection() as conn:
        row = conn.execute(
            "SELECT patient_id, vaccine_code, dose_number, evidence, date_administered, "
            "place_given FROM immunizations WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return "missing"
        if row["evidence"] == EVIDENCE_GIVEN_HERE:
            return "not-allowed"
        if (row["evidence"], row["date_administered"], row["place_given"]) == (evidence, day, place):
            return "unchanged"
        records, birth = _records_in(conn, row["patient_id"])
        key = (row["vaccine_code"], row["dose_number"])
        if _would_double_count(records, birth, record_id,
                               {"evidence": evidence, "date_administered": day}, key):
            return "duplicate"
        conn.execute(
            "UPDATE immunizations SET evidence = ?, date_administered = ?, place_given = ? "
            "WHERE id = ? AND evidence <> ?",
            (evidence, day, place, record_id, EVIDENCE_GIVEN_HERE))
        outcome = ("upgraded" if row["evidence"] == EVIDENCE_PARENT and evidence == EVIDENCE_CARD
                   else "updated")
        if audit:
            audit(conn, outcome)
        conn.commit()
    return outcome


def remove_elsewhere_dose(record_id, audit=None):
    """Remove a card or parent's-report record. Returns "removed", "not-allowed" or "missing".

    A dose given here is never removed (a vaccination that happened, happened); only a
    record that rests on a card or a parent's word can be taken back. `audit(conn)` is
    called before the commit, only when a record was removed.
    """
    with db_connection() as conn:
        row = conn.execute(
            "SELECT evidence FROM immunizations WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return "missing"
        if row["evidence"] == EVIDENCE_GIVEN_HERE:
            return "not-allowed"
        conn.execute("DELETE FROM immunizations WHERE id = ? AND evidence <> ?",
                     (record_id, EVIDENCE_GIVEN_HERE))
        if audit:
            audit(conn)
        conn.commit()
    return "removed"


def get_immunization_by_id(record_id):
    """One recorded dose by primary key, or None. The correction path's first read.

    Returns the stored row plus the name of whoever recorded it, because a correction's
    audit entry has to say who recorded the dose originally -- exactly as a consultation
    edit names who wrote the visit up. The patient is deliberately NOT joined here: the
    caller resolves them through models.patients.get_patient_by_id() so a corrected
    record is named by the same full_name builder every other screen uses.
    """
    with db_connection() as conn:
        row = conn.execute(
            """
        SELECT i.id, i.patient_id, i.consultation_id, i.vaccine_code, i.dose_number,
               i.evidence, i.place_given, i.date_administered, i.administered_by, i.notes,
               i.created_at, u.full_name AS administered_by_name
        FROM immunizations i
        JOIN users u ON u.id = i.administered_by
        WHERE i.id = ?
        """,
            (record_id,),
        ).fetchone()
    if row is None:
        return None
    # Annotated like every other dose this module hands out, so the correction
    # dialog reads `record["reported"]` rather than comparing the stored string.
    record = annotate_evidence(dict(row))
    # And judged like every other dose (Task 14): the correction says what its result was.
    record["verdict"] = record_verdict(record["id"])
    return record


def record_verdict(record_id):
    """How the one validity rule judges one record: a VERDICT_* value, or None if missing."""
    with db_connection() as conn:
        row = conn.execute("SELECT patient_id FROM immunizations WHERE id = ?",
                           (record_id,)).fetchone()
        if row is None:
            return None
        records, birth = _records_in(conn, row["patient_id"])
    verdicts = judge_records(birth, records)
    return next(v for r, v in zip(records, verdicts) if r["id"] == record_id)


def correct_immunization(record_id, vaccine_code, dose_number, date_administered):
    """Correct one recorded dose's vaccine, dose number and date. Deliberate path.

    Returns "corrected", "missing", "duplicate", "date_required" or "bad_date". Never removes
    the row: a correction moves a record's field values rather than making the record go
    away (removing a card or parent's-report record is remove_elsewhere_dose()).

    A date is checked for basic sense (not in the future, not before the child was born:
    "bad_date") and then judged by the one validity rule like any other dose (Task 14, D3):
    a correction to a too-early date makes the dose invalid, and that shows from then on.

    THE DUPLICATE CHECK AND THE UPDATE SHARE ONE CONNECTION ON PURPOSE. Only one VALID
    record per dose can exist, so correcting a dose onto a (vaccine, dose) that already has a
    valid record is a collision, and it is a collision worth naming rather than letting SQLite
    raise. A dose that has only records given too early can take the corrected record (it is
    a repeat). Checking in the same connection that then writes is what keeps the answer
    true at the moment the write happens rather than a moment before it.

    The patient is never moved. A record that was filed against the wrong *patient* is
    a different, larger action than this one.
    """
    day = date_administered
    if day is not None:
        day = day.isoformat() if hasattr(day, "isoformat") else str(day)

    with db_connection() as conn:
        row = conn.execute(
            "SELECT patient_id, evidence FROM immunizations WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            return "missing"

        # A dose given here, or seen on a card, must say when. Only a parent's report may
        # be undated. The table's CHECK would refuse a given-here row with no date anyway
        # and raise an IntegrityError up through the route; naming the outcome here is
        # what lets the dialog say something a person can act on.
        if day is None and row["evidence"] != EVIDENCE_PARENT:
            return "date_required"

        records, birth = _records_in(conn, row["patient_id"])
        if day is not None:
            if as_date(day) > today() or (birth is not None and as_date(day) < birth):
                return "bad_date"

        key = (vaccine_code, dose_number)
        new_values = {"vaccine_code": vaccine_code, "dose_number": dose_number,
                      "date_administered": day}
        if _would_double_count(records, birth, record_id, new_values, key):
            return "duplicate"
        if row["evidence"] == EVIDENCE_PARENT and any(
                r["id"] != record_id and r["evidence"] == EVIDENCE_PARENT
                and (r["vaccine_code"], r["dose_number"]) == key for r in records):
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
    return "corrected"
