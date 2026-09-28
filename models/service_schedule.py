"""Which services the health center runs on which days.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
The successor to advance booking. A barangay health center does not let a
patient choose an hour: the facility decides which services run on which days,
and people walk in. This module stores that decision, one service per row, as
the Administrator enters it, and answers the one question the floor asks of it
every morning -- what is running today.

It is INFORMATION, and nothing else reads it as a rule. The Patient Queue shows
today's services at the top; it does not refuse a check-in, reorder the line or
hide a patient because of them. The RHU's own account of these facilities is
that a walk-in with a fever is seen on prenatal day, and a schedule that could
turn them away would be modelling the booking system that was just retired.
Nothing here sends an SMS either.

IT STARTS EMPTY
---------------
No row is seeded and no default schedule exists anywhere in the code. The
health center's real days have not been confirmed, and this project has already
been damaged once by a placeholder being read as a fact (the province that was
written down as "Agusan del Sur"). An empty schedule is the true state until the
Administrator fills it in, and every screen that reads it says so in words
rather than drawing a blank. See migrate_add_service_schedule.py.

THE SERVICE NAME IS FREE TEXT, AND NOT FROM A LIST
--------------------------------------------------
There is no service vocabulary in this system to choose from. The Patient
Queue's "Reason for visit" is typed, every queue row's appointment_type is the
one constant "Walk-in Consultation", and Record Consultation has a typed chief
complaint. The only controlled list there ever was, APPOINTMENT_TYPES, went with
advance booking -- and it held "Dental" and "DM / Hypertension Monitoring",
which nobody had confirmed this facility offers. Reviving it would put a
guessed list of services back in front of the person entering the real ones.

So the name is typed. What keeps one service from being spelled three ways is
the schedule itself: the form suggests every name already on it
(service_names()), and a name typed with different capitals or spacing from one
already there is stored in the spelling already there (_canonical_service()).
The list of suggestions is therefore exactly the list of services the
Administrator has entered, and nothing else.

HOW A ROW STORES ITS DAYS
-------------------------
Two columns, described in full in migrate_add_service_schedule.py:

    weekdays        (1, 4)   ISO weekday numbers -- Monday is 1, Sunday 7
    weeks_of_month  (2, 4)   which occurrences in the month; () for every week

The three patterns the interviews described are what those two say, not a third
stored field:

    every weekday                weekdays 1-5,  every week
    specific weekdays            any weekdays,  every week
    Nth weekday of the month     any weekdays,  weeks (2, 4)

The Nth occurrence of a weekday in a month is (day - 1) // 7 + 1: days 1-7 hold
the 1st of every weekday, 8-14 the 2nd, and so on. That is the whole of the
calendar arithmetic here, and week_of_month() is the only place it is written.
"""
from database.connection import db_connection
from utils.dates import today

# ---------------------------------------------------------------------------
# THE VOCABULARY OF A DAY
# ---------------------------------------------------------------------------

WEEKDAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

# The days "every weekday" means, and the only set given a name of its own when
# a row is worded. Saturday and Sunday can still be ticked -- nobody has said
# this facility is closed at weekends, and the form does not decide it.
WORKING_WEEK = (1, 2, 3, 4, 5)

# 1st to 4th, and deliberately no 5th. Every month has at least four of each
# weekday and only some have a fifth, so a service on "the 5th Wednesday" would
# quietly not run in most months. No interview described one.
WEEK_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

# Long enough for "Maternal and Child Health -- Prenatal Check-up" and short
# enough to sit on one line of the Patient Queue's panel.
SERVICE_MAX_LENGTH = 80

# Room for the RHU's own kind of condition -- "everyday as long as there's a
# request from the doctor, and if there's no medtech then no laboratory" is 88
# characters -- with space to spare, and short enough to read at the desk.
NOTE_MAX_LENGTH = 300

# What each field is called, for the audit entry's before/after pairs and the
# form's own messages.
FIELD_LABELS = {
    "service": "Service",
    "days": "Days",
    "note": "Note",
}


def week_of_month(day):
    """Which occurrence of its weekday `day` is in its month: 1 for the 1st.

    The 8th to the 14th of any month hold the 2nd Monday, the 2nd Tuesday and so
    on, whichever day of the week the month started on -- so this needs no
    calendar, only the day of the month.
    """
    return (day.day - 1) // 7 + 1


# ---------------------------------------------------------------------------
# READING A STORED ROW
# ---------------------------------------------------------------------------

def _parse_numbers(text, allowed):
    """'1,4' -> (1, 4). Sorted, de-duplicated, and anything unrecognised dropped.

    Tolerant on the way in because a row can be edited by hand in a database
    browser; the CHECK constraints keep letters out, but not a repeated digit or
    a stray comma. What cannot be read is left out rather than guessed at.
    """
    numbers = set()
    for part in (text or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) in allowed:
            numbers.add(int(part))
    return tuple(sorted(numbers))


def _join(words):
    """['Monday', 'Thursday'] -> 'Monday and Thursday'; three or more take commas."""
    words = list(words)
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def _day_names(weekdays):
    """(1, 2, 3, 4, 5) -> 'Monday to Friday'; (1, 4) -> 'Monday and Thursday'.

    A run of three or more consecutive days is worded as a range, which is how
    people say it at a desk. Two consecutive days stay as a pair -- "Monday to
    Tuesday" is not how anyone describes two days.
    """
    days = list(weekdays)
    if len(days) >= 3 and days == list(range(days[0], days[-1] + 1)):
        return f"{WEEKDAY_NAMES[days[0]]} to {WEEKDAY_NAMES[days[-1]]}"
    return _join(WEEKDAY_NAMES[d] for d in days)


def describe_days(weekdays, weeks):
    """The row's days as a sentence fragment a person would say.

        (1, 2, 3, 4, 5), ()   'Every weekday, Monday to Friday'
        (1..7), ()            'Every day'
        (1, 4), ()            'Every Monday and Thursday'
        (3,), (2, 4)          '2nd and 4th Wednesday of the month'

    One function, used by the screen, the Patient Queue and the audit entry, so
    the three cannot word one schedule differently.
    """
    if not weekdays:
        return "No day recorded"
    if weeks:
        ordinals = _join(WEEK_ORDINALS[w] for w in weeks)
        return f"{ordinals} {_join(WEEKDAY_NAMES[d] for d in weekdays)} of the month"
    if tuple(weekdays) == WORKING_WEEK:
        return "Every weekday, Monday to Friday"
    if len(weekdays) == 7:
        return "Every day"
    return f"Every {_day_names(weekdays)}"


def _decorate(row):
    entry = dict(row)
    entry["weekdays"] = _parse_numbers(row["weekdays"], WEEKDAY_NAMES)
    entry["weeks"] = _parse_numbers(row["weeks_of_month"], WEEK_ORDINALS)
    entry["days_text"] = describe_days(entry["weekdays"], entry["weeks"])
    # "2nd & 4th", for the chip beside a service in the week view. Empty for a
    # service that runs every week.
    entry["weeks_short"] = " & ".join(WEEK_ORDINALS[w] for w in entry["weeks"])
    entry["note"] = (row["note"] or "").strip()
    return entry


def get_entries():
    """Every entry, alphabetically by service, then oldest first."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM service_schedule ORDER BY service COLLATE NOCASE, id"
        ).fetchall()
    return [_decorate(row) for row in rows]


def get_entry(entry_id):
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM service_schedule WHERE id = ?", (entry_id,)
        ).fetchone()
    return _decorate(row) if row else None


def service_names(entries=None):
    """Every distinct service already on the schedule, for the form's suggestions.

    This is the only list of services this system offers anybody, and it is
    made of what the Administrator typed. It is empty until they type one.
    """
    entries = get_entries() if entries is None else entries
    seen = {}
    for entry in entries:
        seen.setdefault(entry["service"].casefold(), entry["service"])
    return sorted(seen.values(), key=str.casefold)


# ---------------------------------------------------------------------------
# WHICH DAYS AN ENTRY RUNS ON
# ---------------------------------------------------------------------------

def runs_on(entry, day):
    """Whether this entry's service runs on the date `day`."""
    if day.isoweekday() not in entry["weekdays"]:
        return False
    if entry["weeks"] and week_of_month(day) not in entry["weeks"]:
        return False
    return True


def services_on(day, entries=None):
    """The entries that run on `day`, in the schedule's own order.

    Takes the date as an argument rather than reading the clock, so the Patient
    Queue asks it about today and a test can ask it about any date at all.
    """
    entries = get_entries() if entries is None else entries
    return [entry for entry in entries if runs_on(entry, day)]


def todays_services():
    """(today, the entries running today, how many entries exist at all).

    The total is returned alongside because the two empty answers mean different
    things and the screen must not say the same sentence for both: an empty
    schedule has not been filled in yet, while a filled schedule with nothing on
    today is a real answer about today.
    """
    entries = get_entries()
    day = today()
    return day, services_on(day, entries), len(entries)


def next_dates(entry, from_day=None, count=2):
    """The next `count` dates this entry runs, from `from_day` inclusive.

    Shown on the schedule screen for an entry tied to weeks of the month, where
    "2nd and 4th Wednesday" is exactly the sort of rule people have to count on a
    calendar to apply. Looks at most 62 days ahead, which always contains at
    least one of every 1st-to-4th weekday occurrence.
    """
    from datetime import timedelta

    start = from_day or today()
    found = []
    for offset in range(62):
        day = start + timedelta(days=offset)
        if runs_on(entry, day):
            found.append(day)
            if len(found) == count:
                break
    return found


def by_weekday(entries=None):
    """Monday to Sunday, each with the entries that run on it.

    An entry that runs on several days appears under each of them -- that is
    what reading a week by its days means -- and carries `every_week` so the
    screen can say "2nd and 4th only" beside one that does not run every week.
    Days with nothing on them are included, so an empty Thursday reads as empty
    rather than as missing.
    """
    entries = get_entries() if entries is None else entries
    week = []
    for number, name in WEEKDAY_NAMES.items():
        on_day = [
            {**entry, "every_week": not entry["weeks"]}
            for entry in entries
            if number in entry["weekdays"]
        ]
        week.append({"number": number, "name": name, "entries": on_day})
    return week


# ---------------------------------------------------------------------------
# THE FORM
# ---------------------------------------------------------------------------

def extract_form(form_data):
    """What was submitted, as the values the form redisplays and validation reads.

    Checkbox groups arrive as lists; they are kept as the submitted strings so a
    refused submit redisplays exactly the boxes that were ticked, including one
    whose value a forged request made up.
    """
    getlist = getattr(form_data, "getlist", None)
    if getlist is None:
        def getlist(key):
            value = form_data.get(key)
            if value is None:
                return []
            return list(value) if isinstance(value, (list, tuple)) else [value]

    return {
        "service": (form_data.get("service") or "").strip(),
        "weekdays": [str(v).strip() for v in getlist("weekdays")],
        "weeks": [str(v).strip() for v in getlist("weeks")],
        "note": (form_data.get("note") or "").strip(),
    }


def form_values(entry):
    """A stored entry, in the shape extract_form() produces, to prefill Edit."""
    return {
        "service": entry["service"],
        "weekdays": [str(d) for d in entry["weekdays"]],
        "weeks": [str(w) for w in entry["weeks"]],
        "note": entry["note"],
    }


def _canonical_service(service, entries, editing_id=None):
    """The spelling already on the schedule, if this is the same name retyped.

    "family planning" typed beside an existing "Family Planning" is the same
    service, and storing both spellings would split it in two on every screen
    that groups by name. Only case and runs of spaces are folded; anything else
    is a different name and is stored as typed.
    """
    folded = " ".join(service.split()).casefold()
    for entry in entries:
        if entry["id"] == editing_id:
            continue
        if " ".join(entry["service"].split()).casefold() == folded:
            return entry["service"]
    return " ".join(service.split())


def validate_entry(values, entries=None, editing_id=None):
    """Server-side validation. Returns {field: message}; empty means valid.

    Same contract as validate_general_settings() and validate_new_user_form(),
    and for the same reason: a POST can arrive without the page ever having been
    loaded, so nothing the browser checked counts.

    Messages say what to do, in the voice the other forms use.
    """
    entries = get_entries() if entries is None else entries
    errors = {}

    service = values.get("service") or ""
    if not service:
        errors["service"] = "Enter the service, such as the name the health center uses for it."
    elif len(service) > SERVICE_MAX_LENGTH:
        errors["service"] = (
            f"Keep the service name to {SERVICE_MAX_LENGTH} characters; this one is "
            f"{len(service)}. Anything longer belongs in the note."
        )

    raw_days = values.get("weekdays") or []
    if not raw_days:
        errors["weekdays"] = "Tick at least one day the service runs."
    elif any(
        not d.isdigit() or int(d) not in WEEKDAY_NAMES for d in raw_days
    ):
        errors["weekdays"] = "Choose the days from the boxes shown."

    raw_weeks = values.get("weeks") or []
    if any(not w.isdigit() or int(w) not in WEEK_ORDINALS for w in raw_weeks):
        errors["weeks"] = (
            "Choose the weeks from the 1st to the 4th. A 5th occurrence only "
            "happens in some months, so the schedule does not offer it."
        )
    elif raw_weeks and len(set(raw_weeks)) == len(WEEK_ORDINALS):
        # All four ticked is not the same as every week -- a 5th Wednesday would
        # be left out -- and the person almost certainly meant every week.
        errors["weeks"] = (
            "All four weeks are ticked. If the service runs every week, leave the "
            "weeks blank; ticking all four would leave out a 5th occurrence in "
            "the months that have one."
        )

    note = values.get("note") or ""
    if len(note) > NOTE_MAX_LENGTH:
        errors["note"] = (
            f"Keep the note to {NOTE_MAX_LENGTH} characters; this one is {len(note)}."
        )

    # The same service on exactly the same days is the same entry twice. Checked
    # only once the parts are valid, so the message is about the duplicate and
    # not about a day that could not be read.
    if not errors:
        service_key = " ".join(service.split()).casefold()
        weekdays = _parse_numbers(",".join(raw_days), WEEKDAY_NAMES)
        weeks = _parse_numbers(",".join(raw_weeks), WEEK_ORDINALS)
        for entry in entries:
            if entry["id"] == editing_id:
                continue
            if (
                " ".join(entry["service"].split()).casefold() == service_key
                and entry["weekdays"] == weekdays
                and entry["weeks"] == weeks
            ):
                errors["service"] = (
                    f'"{entry["service"]}" is already on the schedule on exactly '
                    f'these days ({entry["days_text"]}). Edit that entry instead '
                    "of adding it twice."
                )
                break

    return errors


def _stored(values, entries, editing_id=None):
    """Validated form values -> the four columns, in canonical form."""
    weekdays = _parse_numbers(",".join(values["weekdays"]), WEEKDAY_NAMES)
    weeks = _parse_numbers(",".join(values["weeks"]), WEEK_ORDINALS)
    return {
        "service": _canonical_service(values["service"], entries, editing_id),
        "weekdays": ",".join(str(d) for d in weekdays),
        "weeks_of_month": ",".join(str(w) for w in weeks) or None,
        "note": values["note"] or None,
    }


# ---------------------------------------------------------------------------
# WRITING
# ---------------------------------------------------------------------------

def create_entry(values, actor_id, entries=None):
    """Insert one validated entry. Returns the stored row, decorated."""
    entries = get_entries() if entries is None else entries
    stored = _stored(values, entries)
    with db_connection() as conn:
        cursor = conn.execute(
            """
        INSERT INTO service_schedule
            (service, weekdays, weeks_of_month, note, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
            (stored["service"], stored["weekdays"], stored["weeks_of_month"],
             stored["note"], actor_id),
        )
        conn.commit()
        new_id = cursor.lastrowid
    return get_entry(new_id)


def update_entry(entry_id, values, actor_id, entries=None):
    """Rewrite one validated entry. Returns the stored row after, or None if gone.

    Returns None rather than raising when the row has disappeared since the form
    was opened -- deleted by another administrator in between -- so the caller
    can say so instead of claiming an edit that touched nothing.
    """
    entries = get_entries() if entries is None else entries
    stored = _stored(values, entries, editing_id=entry_id)
    with db_connection() as conn:
        cursor = conn.execute(
            """
        UPDATE service_schedule
           SET service = ?, weekdays = ?, weeks_of_month = ?, note = ?,
               updated_by = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
            (stored["service"], stored["weekdays"], stored["weeks_of_month"],
             stored["note"], actor_id, entry_id),
        )
        conn.commit()
        changed = cursor.rowcount
    return get_entry(entry_id) if changed else None


def would_change(entry, values, entries=None):
    """Whether saving `values` over `entry` would alter anything a reader sees.

    Asked before writing, so an Edit saved unchanged writes nothing -- no row
    update, no audit entry -- and says so, the rule every other edit form here
    follows: a save that altered nothing is not an event.
    """
    entries = get_entries() if entries is None else entries
    stored = _stored(values, entries, editing_id=entry["id"])
    return (
        stored["service"] != entry["service"]
        or stored["weekdays"] != ",".join(str(d) for d in entry["weekdays"])
        or (stored["weeks_of_month"] or None)
        != (",".join(str(w) for w in entry["weeks"]) or None)
        or (stored["note"] or "") != entry["note"]
    )


def delete_entry(entry_id):
    """Remove one entry. Returns what it said, decorated, or None if already gone.

    Read first and returned so the audit entry can record everything the row
    held: once it is deleted, that entry is the only copy of what it said.
    """
    entry = get_entry(entry_id)
    if entry is None:
        return None
    with db_connection() as conn:
        cursor = conn.execute("DELETE FROM service_schedule WHERE id = ?", (entry_id,))
        conn.commit()
        removed = cursor.rowcount
    return entry if removed else None
