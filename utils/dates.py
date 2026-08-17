"""Date handling: the clinic's time reference, and presentation helpers.

Dates are stored as ISO text ('2026-07-07', or '2026-07-07 09:15:00' for the
CURRENT_TIMESTAMP columns). The screens display them as 'Jul 07, 2026' or
'July 7, 2026', so the conversion lives here rather than in the models.


WHY THE TIMEZONE IS HARDCODED
-----------------------------
01_PROJECT_BIBLE.md scopes this system to one barangay health center in San
Francisco, Agusan del Sur. There is one site, one set of opening hours, and one
answer to "what is today" -- so "today" is deliberately fixed to Asia/Manila
here rather than being made configurable or derived from the server clock.

That is a decision, not an oversight:

* Reading the server clock (`date.today()`) silently makes correctness depend on
  where the application happens to be hosted. Deployed to a UTC host, "today"
  would roll over at 08:00 Manila time, so a medicine expiring today would read
  as already expired for the first eight hours of every working day.
* SQLite's `CURRENT_TIMESTAMP` is always UTC. Storage keeps that -- it is an
  unambiguous instant and nothing needs to change -- but any *business* question
  ("is this expired?", "how many registered this month?") is answered in the
  timezone the health center actually works in.
* ZoneInfo("Asia/Manila") rather than a fixed +08:00 offset, so the answer stays
  right on its own if the Philippines ever revisits daylight saving, which it has
  observed before.

Every module that needs the current date calls today() or now() from here. There
should be no other source of "now" in the application.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MISSING = "—"

# Asia/Manila has been a flat +08:00 since 1978, when the Philippines last
# observed daylight saving. Used only when the named zone cannot be resolved.
_PHT = timezone(timedelta(hours=8), "PHT")


def _clinic_timezone():
    """Asia/Manila from the IANA database, or a fixed +08:00 if it is missing.

    Windows ships no system copy of the IANA database, so `zoneinfo` -- stdlib
    though it is -- can only resolve "Asia/Manila" when the `tzdata` package is
    installed. requirements.txt lists it for that reason, but the application
    must not refuse to start on a machine that lacks it, so this falls back to
    the fixed offset rather than raising.

    The two agree exactly today; the named zone is still preferred because it
    would pick up any future rule change without a code edit, which is the whole
    reason for not hardcoding the offset in the first place.
    """
    try:
        return ZoneInfo("Asia/Manila")
    except (ZoneInfoNotFoundError, OSError):
        return _PHT


# The single reference timezone for the whole application. See the module note.
CLINIC_TIMEZONE = _clinic_timezone()

# How SQLite writes its CURRENT_TIMESTAMP columns, and therefore the shape any
# value compared against created_at / updated_at has to take.
SQLITE_TIMESTAMP = "%Y-%m-%d %H:%M:%S"


def now():
    """The current moment at the health center, as an aware datetime."""
    return datetime.now(CLINIC_TIMEZONE)


def today():
    """Today's date at the health center.

    The one source of "today" for business logic -- expiry status, age, and the
    future-date validation checks all resolve through this.
    """
    return now().date()


def utc_timestamp(moment):
    """An aware datetime -> the UTC text SQLite stores in a timestamp column.

    Lets a query compare a clinic-local boundary against created_at without
    either side being reinterpreted: the boundary is converted to the same UTC
    instant the column already holds.
    """
    return moment.astimezone(timezone.utc).strftime(SQLITE_TIMESTAMP)


def day_start_utc(day):
    """Midnight at the start of a clinic calendar day, as stored-UTC text."""
    return utc_timestamp(datetime.combine(day, time.min, tzinfo=CLINIC_TIMEZONE))


def days_ago(count, from_day=None):
    """The clinic date `count` days before today (or before `from_day`)."""
    return (from_day or today()) - timedelta(days=count)


def month_bounds(day=None):
    """(first day of that clinic month, first day of the next one).

    Half-open, so a row is in the month when start <= created_at < next_start --
    which avoids the "last day of the month" edge case a BETWEEN would carry.
    """
    day = day or today()
    start = day.replace(day=1)
    # Day 28 plus four days always lands in the next month, whatever its length.
    next_start = (start + timedelta(days=32)).replace(day=1)
    return start, next_start


def recent_months(count, end=None):
    """The last `count` clinic months, oldest first, ending with end's month.

    Each entry is (first_day, next_first_day, short_label) -- the same half-open
    pair month_bounds() returns, plus the 'Jan'/'Feb' label the trend charts use
    for their x axis.

    Lives here rather than in a model because three of them need exactly this
    window (registrations, consultations, appointment outcomes) and a trend
    stitched from three different ideas of "the last six months" would put the
    same month under different labels on the same screen.
    """
    end_month = (end or today()).replace(day=1)
    months = []
    cursor = end_month
    for _ in range(count):
        months.append(cursor)
        # Step back into the previous month, then to its first day.
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()

    windows = []
    for start in months:
        next_start = (start + timedelta(days=32)).replace(day=1)
        windows.append((start, next_start, start.strftime("%b")))
    return windows


def month_span(start, end):
    """Every clinic month the inclusive [start, end] range touches, oldest first.

    The same (first_day, next_first_day, label) shape recent_months() returns, so
    a chart plots a custom range through exactly the code that already plots the
    default one.

    The label carries the year only when the range crosses one. "Jan" appearing
    twice on a single axis would be two different months wearing one name, and a
    reader counting bars would have no way to tell which year a figure belonged
    to; within one year the bare month is what every existing chart already
    prints and is left alone.
    """
    fmt = "%b" if start.year == end.year else "%b %Y"
    windows = []
    cursor = start.replace(day=1)
    last = end.replace(day=1)
    while cursor <= last:
        next_start = (cursor + timedelta(days=32)).replace(day=1)
        windows.append((cursor, next_start, cursor.strftime(fmt)))
        cursor = next_start
    return windows


def resolve_range(start=None, end=None, months=6, on_date=None):
    """The one window a report covers, however it was asked for.

    Every ranged figure in this project resolves its window here, so a report's
    cards, its trend charts and its letterhead cannot disagree about which days
    they cover. Returns:

        start   first day counted, inclusive
        end     last day counted, inclusive
        months  the (first, next_first, label) triples the trend plots
        custom  True when the caller asked for a specific range

    With no explicit range this reproduces the fixed window the screens have
    always used -- recent_months() itself, not a re-derivation of it -- so the
    default view is byte-identical to what it was before ranges existed.
    """
    reference = on_date or today()
    if start and end:
        return {
            "start": start,
            "end": end,
            "months": month_span(start, end),
            "custom": True,
        }
    windows = recent_months(months, reference)
    return {
        "start": windows[0][0],
        "end": reference,
        "months": windows,
        "custom": False,
    }


def range_bounds_utc(window):
    """A resolved range -> the half-open UTC text pair the timestamp columns want.

    created_at and sent_at are written by SQLite's CURRENT_TIMESTAMP and are
    therefore UTC, while the range the operator typed means clinic-local days.
    The end is exclusive and one day past the last day counted, so a row written
    at 23:30 on the closing date is inside the report rather than a day past it.
    """
    return (
        day_start_utc(window["start"]),
        day_start_utc(window["end"] + timedelta(days=1)),
    )


def _parse(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # Last resort: keep the leading date of anything else ISO-ish.
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def display_date(value, fallback=MISSING):
    """'2026-07-07' -> 'Jul 07, 2026'. Unparseable or empty -> fallback."""
    parsed = _parse(value)
    return parsed.strftime("%b %d, %Y") if parsed else fallback


def long_date(value, fallback=MISSING):
    """'1968-03-02' -> 'March 2, 1968'.

    Built by hand because the no-pad day directive differs between platforms
    ('%-d' on Linux, '%#d' on Windows).
    """
    parsed = _parse(value)
    if not parsed:
        return fallback
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"


def to_clinic_time(value):
    """A stored UTC timestamp -> the same instant as clinic-local, or None.

    The one place the UTC-to-Manila conversion happens. display_timestamp()
    below formats the result; a caller that needs the date and the time in
    separate cells -- the Audit Logs table does -- takes the datetime from here
    rather than re-deriving the offset and risking a second answer.

    A value carrying no time (a plain date) is returned unshifted: moving a bare
    date across a timezone would land it on the wrong day.
    """
    parsed = _parse(value)
    if not parsed:
        return None
    if len(str(value).strip()) <= 10:
        return parsed
    return parsed.replace(tzinfo=timezone.utc).astimezone(CLINIC_TIMEZONE)


def full_date(value, fallback=MISSING):
    """'2026-08-13' -> 'Thursday, August 13, 2026'.

    long_date() with the weekday in front. It exists because the dashboards and
    the four Barangay Official screens all print today in exactly this shape in
    their page subtitle, and each of them used to carry its own frozen copy of
    the string. One filter means one format and one source for all of them.

    Built by hand for the same reason long_date() is: '%-d' is not portable.
    """
    parsed = _parse(value)
    if not parsed:
        return fallback
    return (f"{parsed.strftime('%A')}, {parsed.strftime('%B')} "
            f"{parsed.day}, {parsed.year}")


def display_timestamp(value, fallback=MISSING):
    """A stored UTC timestamp -> 'Jul 07, 2026 · 6:00 AM' at the health center.

    The CURRENT_TIMESTAMP columns hold UTC (see the module note), so a screen that
    printed them as written would say a broadcast sent at 3 PM went out at 7 AM.

    A value carrying no time -- a plain date -- is returned as display_date()
    would render it rather than gaining a fabricated midnight.
    """
    local = to_clinic_time(value)
    if not local:
        return fallback
    if len(str(value).strip()) <= 10:
        return local.strftime("%b %d, %Y")

    # %I zero-pads the hour on every platform; the lstrip is what turns 06 into 6.
    return f"{local.strftime('%b %d, %Y')} · {local.strftime('%I:%M %p').lstrip('0')}"


def register_date_filters(app):
    app.jinja_env.filters["display_date"] = display_date
    app.jinja_env.filters["long_date"] = long_date
    app.jinja_env.filters["full_date"] = full_date
    app.jinja_env.filters["display_timestamp"] = display_timestamp
