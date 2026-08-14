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
"""
from datetime import timedelta

from database.connection import get_db
from models.consultations import PEDIATRIC_AGE_YEARS, as_date
from models.patients import add_months, calculate_age
from utils.dates import today

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
               i.date_administered, i.administered_by, i.notes, i.created_at,
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
        SELECT i.id, i.vaccine_code, i.dose_number, i.date_administered, i.notes,
               u.full_name AS administered_by_name
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
    return given


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
                        carrying its status, badge class and administered detail
        attention_items the Overdue and Due Now entries, most urgent first
        extra_records   doses on file that the current schedule does not list
        counts          completed / due_now / overdue / upcoming / total
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
    given_by_key = {
        (record["vaccine_code"], record["dose_number"]): record for record in records
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
            "date_administered": given["date_administered"] if given else None,
            "administered_by_name": given["administered_by_name"] if given else None,
            "consultation_id": given["consultation_id"] if given else None,
            # What the form's checkbox posts back.
            "key": f"{code}:{dose_number}",
        })

    extra_records = [
        record for record in records
        if (record["vaccine_code"], record["dose_number"]) not in SCHEDULE_KEYS
    ]
    for record in extra_records:
        record["label"] = dose_label(record["vaccine_code"], record["dose_number"])

    counts = {status: sum(1 for item in schedule if item["status"] == status)
              for status in STATUS_ORDER}
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
        "total_doses": TOTAL_SCHEDULED_DOSES,
        "attention_count": counts[OVERDUE] + counts[DUE_NOW],
        "needs_attention": bool(counts[OVERDUE] + counts[DUE_NOW]) and applicable,
        "next_due": next_due,
        "summary": _summarise(counts, applicable),
        "pediatric_age_years": PEDIATRIC_AGE_YEARS,
        "grace_period_days": GRACE_PERIOD_DAYS,
    }


def _summarise(counts, applicable):
    """The one-line reading every screen prints rather than composing its own."""
    given = counts[COMPLETED]
    parts = [f"{given} of {TOTAL_SCHEDULED_DOSES} scheduled doses given"]
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


def get_immunization_alert(limit=None, on_date=None):
    """Children due or overdue for a dose. Same role as get_low_stock_alert().

    The dashboards' figure and list, and the set the queue reads to decide which
    rows carry a badge. Everything derives from get_immunization_status(), so the
    dashboard card, the queue badge and the child's own profile cannot disagree.

    `limit` caps only the returned list, never the counts -- a panel with room
    for five rows still reports the true total above them, exactly as the
    low-stock panel does.

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
               i.date_administered, i.administered_by, i.notes, i.created_at,
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

    children = []
    # How many children the DOH schedule applies to at all -- the denominator a
    # coverage figure needs. Counted in this loop rather than by a second query,
    # because "applicable" is get_immunization_status()'s own judgement and a
    # separate SELECT on birth_date would be a second, quietly different rule.
    eligible = 0
    for patient in get_all_patients():
        # Only living, active records: chasing a deceased or archived child for a
        # missed dose is exactly the kind of thing a follow-up list must not do.
        if patient.get("status") != "Active":
            continue
        status = get_immunization_status(
            patient, on_date=reference, records=by_patient.get(patient["id"], [])
        )
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


def get_immunization_coverage(on_date=None):
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
    """
    conn = get_db()
    enrolled = conn.execute(
        "SELECT COUNT(DISTINCT patient_id) FROM immunizations"
    ).fetchone()[0]
    doses_given = conn.execute("SELECT COUNT(*) FROM immunizations").fetchone()[0]
    conn.close()

    alert = get_immunization_alert(on_date=on_date)
    return {
        "enrolled": enrolled,
        "doses_given": doses_given,
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


def record_immunizations(patient_id, dose_keys, administered_by, date_administered,
                         consultation_id=None):
    """Write the doses given at one visit. Returns the (code, dose) pairs stored.

    INSERT OR IGNORE against the table's UNIQUE (patient_id, vaccine_code,
    dose_number): a dose already on file is left exactly as it was rather than
    being re-dated to today. Double-clicking Save must not rewrite the history of
    when a child was actually vaccinated, and a dose given at another facility
    and recorded earlier is not superseded by a tick box.
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
                 date_administered, administered_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (patient_id, consultation_id, code, dose_number, day, administered_by),
        )
        if cursor.rowcount:
            stored.append((code, dose_number))
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
