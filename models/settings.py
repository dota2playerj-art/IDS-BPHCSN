"""The health center's own identity and opening hours, stored and read back.

WHAT THIS MODULE IS FOR, AND WHAT IT DELIBERATELY IS NOT
--------------------------------------------------------
schema.sql has defined a `settings` table since the first schema -- setting_key,
setting_value, updated_by, updated_at -- and until now nothing wrote a row into
it and nothing read one out. utils/unavailable.py's `settings` reason had been
rewritten twice to say exactly that, because a reason denying an existing
structure sends the next session off to build something already there. This is
the wiring that reason was describing the absence of.

It stores seven values and no others. Six describe the health center:

    health_center_name   what the facility calls itself
    barangay             the barangay it stands in
    municipality         the municipality
    province             the province
    opening_time         when the clinic opens, "HH:MM"
    closing_time         when it closes, "HH:MM"

and one is a switch that decides who may use the system at all:

    maintenance_mode     "on" closes it to everyone but an Administrator

The switch is described where it is defined below, including why it is kept out
of GENERAL_KEYS and why it fails open. The rest of this note is about the six.

Six rather than the twenty-odd fields Screen 13 draws, and the line between them
is not taste. Each of these six is a value some OTHER part of the running system
already reads: the name is at the front of every appointment SMS and on every
export letterhead, the three place names make up the address those letterheads
and the login page print, and the two times are what the bookable time slots are
built from. They were constants in five different files, which is the actual
problem this module solves -- one of them was `HEALTH_CENTER` in
models/appointment_sms.py, three more were string literals repeated across the
three export modules, and two were CLINIC_OPEN_HOUR and CLINIC_CLOSE_HOUR in
models/appointments.py. Changing the health center's name meant editing five
files and hoping none had been missed.

Everything else on that screen -- the contact number, the DOH licence, the
session timeout, the backup retention period -- has no reader anywhere in the
project. Storing those would produce exactly the thing this project keeps
removing: a control that accepts input and changes nothing.

WHY DEFAULTS LIVE HERE AND NOT IN THE DATABASE
-----------------------------------------------
No migration seeds these rows. An empty settings table is a valid, expected
state -- it is the state every existing copy of app.db is in right now -- and on
that database every value below is the value the application already used as a
hard-coded constant. So a fresh install and an untouched install behave
identically to how the system behaved before this module existed, and the first
save is what starts overriding a default rather than what starts the feature
working.

That also means a row is only ever written for a value an administrator actually
set. Reading the table tells you what was decided, not what was defaulted.

HOW READS ARE CACHED, AND WHY ONLY FOR ONE REQUEST
---------------------------------------------------
get_settings() is called several times in a single render -- once by
utils/context.py for the page header, again by whichever export or SMS composer
the request is running -- and each call would otherwise be a connect / query /
close cycle, which utils/security.py measured at ~0.54-0.64 ms against ~0.027 ms
for the query itself. So the resolved dict is cached on flask.g, the same place
and for the same reason get_current_user() caches the account row: one request,
one read, and no invalidation rule to get wrong. A cache that outlived the
request would have to be invalidated on every save, and getting that wrong is
how a screen comes to show the value that was replaced.

Outside a request context there is nowhere to cache and nothing to save, so
scripts read the database directly.
"""
import re

from flask import g, has_request_context

from database.connection import get_db

# ---------------------------------------------------------------------------
# THE KEYS, AND WHAT THE SYSTEM DOES WITHOUT THEM
# ---------------------------------------------------------------------------
KEY_NAME = "health_center_name"
KEY_BARANGAY = "barangay"
KEY_MUNICIPALITY = "municipality"
KEY_PROVINCE = "province"
KEY_OPENING = "opening_time"
KEY_CLOSING = "closing_time"

GENERAL_KEYS = (
    KEY_NAME,
    KEY_BARANGAY,
    KEY_MUNICIPALITY,
    KEY_PROVINCE,
    KEY_OPENING,
    KEY_CLOSING,
)

# MAINTENANCE MODE, AND WHY IT IS DELIBERATELY NOT ONE OF THE SIX ABOVE.
# It is stored in the same table by the same mechanism, but it is not a General
# Setting and must never be written by that form. GENERAL_KEYS is what
# save_general_settings() writes -- all six, every time, so `updated_by` on each
# row means "who last confirmed this value". Folding a switch into that set
# would mean every save of the health center's name also re-asserted whether the
# system is open, and a validation error on the barangay would sit on a form
# that had a live lockout toggle in it.
#
# It is its own key, its own route, and its own writer for the same reason
# deactivating an account is not part of Edit User: one changes a detail, the
# other changes who can get in.
KEY_MAINTENANCE = "maintenance_mode"

# Everything with a row in the settings table, which is the six plus the switch.
# _read_stored() selects on this; GENERAL_KEYS stays the form's set.
STORED_KEYS = GENERAL_KEYS + (KEY_MAINTENANCE,)

# The two values maintenance mode is ever stored as. Explicit strings rather
# than "1"/"0" or a bare truth test, because the column is TEXT and a truth test
# over TEXT is how "0" comes to be true.
MAINTENANCE_ON = "on"
MAINTENANCE_OFF = "off"

# Every one of these is the literal the application used before it could store
# anything, copied from the file that held it:
#
#   KEY_NAME        models/appointment_sms.py's HEALTH_CENTER, and the `org` and
#                   `heading` arguments in all three export modules
#   KEY_BARANGAY    the eyebrow line on every screen, and Screen 13's own field
#   KEY_MUNICIPALITY, KEY_PROVINCE
#                   templates/login.html's location line
#   KEY_OPENING     models/appointments.py's CLINIC_OPEN_HOUR = 8
#   KEY_CLOSING     models/appointments.py's CLINIC_CLOSE_HOUR = 17
#
# So an administrator who never opens Settings gets the system exactly as it
# behaved before this module was written, which is the only acceptable default
# for a change that reaches into SMS messages and booking validation.
DEFAULTS = {
    KEY_NAME: "Barangay Poblacion Health Center",
    KEY_BARANGAY: "Barangay Poblacion",
    KEY_MUNICIPALITY: "San Francisco",
    KEY_PROVINCE: "Surigao del Norte",
    KEY_OPENING: "08:00",
    KEY_CLOSING: "17:00",
    # OFF, AND THE DIRECTION OF THIS DEFAULT IS THE SAFETY PROPERTY.
    # Every existing copy of app.db has no row under this key, and so does a
    # fresh install -- so the system is open until an administrator deliberately
    # closes it, and a database that has never seen this feature behaves exactly
    # as it did before the feature existed.
    KEY_MAINTENANCE: MAINTENANCE_OFF,
}

# What each field is called on the form, used in its own error messages so the
# message names the box the operator is looking at.
FIELD_LABELS = {
    KEY_NAME: "Health center name",
    KEY_BARANGAY: "Barangay",
    KEY_MUNICIPALITY: "Municipality / City",
    KEY_PROVINCE: "Province",
    KEY_OPENING: "Opening time",
    KEY_CLOSING: "Closing time",
}

# What each empty field is told, in the same voice REQUIRED_NEW_USER_FIELDS uses
# on Add User: what to do, not what went wrong. The health center's name says
# more than the other three because it is read by more of the system than
# anything else on the screen -- a blank would reach a patient's phone.
REQUIRED_MESSAGES = {
    KEY_NAME: (
        "Enter the health center's name. It is printed on every export and is "
        "the first thing in every appointment SMS."
    ),
    KEY_BARANGAY: "Enter the barangay the health center stands in.",
    KEY_MUNICIPALITY: "Enter the municipality or city.",
    KEY_PROVINCE: "Enter the province.",
}

# Long enough for the longest real facility name in the region and short enough
# that the value cannot break a PDF letterhead or push an SMS into a second
# segment on its own. The name in particular is checked against a tighter figure
# below, for that second reason.
TEXT_MAX_LENGTH = 100

# THE NAME IS CAPPED SHORTER THAN THE OTHER THREE, AND THE REASON IS THE COST OF
# A TEXT MESSAGE. models/appointment_sms.py puts this string at the front of
# every confirmation, and 160 characters is what one message credit buys. The
# default is 32 characters and the shortest of the three messages is 96 with it
# in place, so 60 leaves headroom for a long patient name and a long service
# without silently doubling what every confirmation costs the barangay. It is a
# limit on a field, not a truncation -- nothing here shortens what was typed.
NAME_MAX_LENGTH = 60

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# The cache key on flask.g. Named with a leading underscore like
# utils/security.py's, so it reads as machinery rather than as something a
# template might be meant to reach.
_CACHE_ATTRIBUTE = "_general_settings"


# ---------------------------------------------------------------------------
# READING
# ---------------------------------------------------------------------------

def _read_stored():
    """{key: value} for the keys that have a stored row. Missing keys absent.

    Only the keys this module owns are selected. A row under any other key --
    there are none today, and nothing in this module writes one -- is left alone
    rather than being read into a dict the rest of the application would then be
    able to see.
    """
    conn = get_db()
    placeholders = ", ".join("?" for _ in STORED_KEYS)
    rows = conn.execute(
        f"SELECT setting_key, setting_value FROM settings "
        f"WHERE setting_key IN ({placeholders})",
        STORED_KEYS,
    ).fetchall()
    conn.close()

    stored = {}
    for row in rows:
        value = (row["setting_value"] or "").strip()
        # A row holding an empty string is treated as no row at all. Nothing
        # writes one -- save_general_settings() refuses a blank -- but a value
        # that fell back to "" would put an empty health center name at the front
        # of an SMS, and the default is a better answer than a message beginning
        # with a colon.
        if value:
            stored[row["setting_key"]] = value
    return stored


def get_settings():
    """Every stored value in force, defaults filled in. Never returns a partial dict.

    Every caller can index any key without checking, which is why no consumer in
    this project has a fallback of its own -- a second fallback is a second place
    for the default to be written down and to go stale.
    """
    if not has_request_context():
        return {**DEFAULTS, **_read_stored()}

    cached = getattr(g, _CACHE_ATTRIBUTE, None)
    if cached is not None:
        return cached

    resolved = {**DEFAULTS, **_read_stored()}
    setattr(g, _CACHE_ATTRIBUTE, resolved)
    return resolved


def clear_cache():
    """Forget this request's cached copy. Called after a save.

    A save is followed by a redirect, so the next request would re-read anyway.
    This exists so that anything running after the write inside the SAME request
    -- an audit entry quoting the new name, a re-render -- cannot be handed the
    values that were just replaced.
    """
    if has_request_context():
        setattr(g, _CACHE_ATTRIBUTE, None)


def health_center_name():
    """The facility as it names itself. One call for the commonest read."""
    return get_settings()[KEY_NAME]


def address_line():
    """'Barangay Poblacion, San Francisco, Surigao del Norte'.

    Derived from the three stored place names rather than stored as a fourth
    value. Screen 13 used to carry a "Complete Address" field holding its own
    copy of the same three names plus a purok and a postcode; a stored address
    would be a fourth string that could disagree with the three it is made of,
    and the first time somebody corrected the municipality in one place and not
    the other, the letterhead and the address line would name two municipalities.

    Blank parts are dropped rather than leaving a stray comma, which cannot
    happen from a saved value -- all three are required -- but can from a
    hand-edited database row.
    """
    values = get_settings()
    parts = [
        values[KEY_BARANGAY],
        values[KEY_MUNICIPALITY],
        values[KEY_PROVINCE],
    ]
    return ", ".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# MAINTENANCE MODE
# ---------------------------------------------------------------------------

def maintenance_mode():
    """True when the system is closed to everyone but an Administrator.

    IT FAILS OPEN, AND THAT DIRECTION IS A DECISION RATHER THAN AN OVERSIGHT.
    Anything that is not exactly the stored word "on" reads as off: a missing
    row, an empty string, a hand-edited "1", "true", "yes", or a value nobody
    anticipated. So the only way this returns True is a row that says so
    exactly, written by the one route that writes it.

    The alternative -- treating anything unrecognised as "on" -- would mean a
    single malformed row in a settings table locking every health worker and
    barangay official out of the patient register until an administrator noticed
    and could sign in to fix it. In a clinic that is a far worse failure than a
    maintenance window that quietly did not engage, and the one an operator has
    no way to diagnose from the screen they are looking at. A lockout must be
    something somebody chose, never something a database fell into.
    """
    return get_settings()[KEY_MAINTENANCE] == MAINTENANCE_ON


def set_maintenance_mode(enabled, actor_id):
    """Turn the switch on or off. Returns True if the stored value actually moved.

    Written on its own rather than through save_general_settings(), for the
    reason KEY_MAINTENANCE is not in GENERAL_KEYS: this is the one stored value
    that decides who may use the system at all, and it must not be reachable by
    a form whose subject is the health center's postal address.

    Returns whether anything changed so the caller can word an honest message
    and decide whether an audit entry is worth writing -- pressing "enable" on a
    system that is already closed is not a second closure.
    """
    desired = MAINTENANCE_ON if enabled else MAINTENANCE_OFF
    if get_settings()[KEY_MAINTENANCE] == desired:
        return False

    conn = get_db()
    conn.execute(
        """
        INSERT INTO settings (setting_key, setting_value, updated_by, updated_at)
             VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(setting_key) DO UPDATE SET
             setting_value = excluded.setting_value,
                updated_by = excluded.updated_by,
                updated_at = CURRENT_TIMESTAMP
        """,
        (KEY_MAINTENANCE, desired, actor_id),
    )
    conn.commit()
    conn.close()

    # The guard in utils/security.py reads this on the very next request, and
    # the redirect that follows this call IS the next request. Without this the
    # administrator who just closed the system would be shown a screen still
    # saying it was open.
    clear_cache()
    return True


def maintenance_changed_at():
    """(when, who) for the last time the switch moved, or (None, None).

    Read off the settings row itself rather than the audit trail, so the screen
    reports the state of the stored value even if the entry that should
    accompany it was never written -- log_action() declines an entry it cannot
    attribute to a real account, and a switch whose history disagreed with its
    own row would be the more misleading of the two.
    """
    conn = get_db()
    row = conn.execute(
        """
        SELECT s.updated_at, u.full_name
          FROM settings s
          LEFT JOIN users u ON u.id = s.updated_by
         WHERE s.setting_key = ?
        """,
        (KEY_MAINTENANCE,),
    ).fetchone()
    conn.close()
    if row is None:
        return None, None
    return row["updated_at"], row["full_name"]


# ---------------------------------------------------------------------------
# THE CLINIC DAY
# ---------------------------------------------------------------------------

def to_minutes(value):
    """'08:30' -> 510. None for anything that is not a valid 24-hour time."""
    match = _TIME_PATTERN.match((value or "").strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def display_time(value):
    """'08:00' -> '8:00 AM'. The form stores 24-hour; people read 12-hour.

    Falls back to the stored string when it cannot be parsed, so a hand-edited
    row shows what it actually holds instead of a blank.
    """
    minutes = to_minutes(value)
    if minutes is None:
        return value or ""
    hour, minute = divmod(minutes, 60)
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {suffix}"


def clinic_hours():
    """(opening minutes, closing minutes) as integers past midnight.

    Both are guaranteed parseable: validate_general_settings() refuses anything
    else, and DEFAULTS holds valid strings, so the only way to a bad value is a
    hand-edited row -- which falls back to the default rather than raising, since
    an unparseable opening time must not take the booking screen down.
    """
    values = get_settings()
    opening = to_minutes(values[KEY_OPENING])
    closing = to_minutes(values[KEY_CLOSING])
    if opening is None:
        opening = to_minutes(DEFAULTS[KEY_OPENING])
    if closing is None:
        closing = to_minutes(DEFAULTS[KEY_CLOSING])
    return opening, closing


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def validate_general_settings(values):
    """Server-side validation. Returns {field: message}; empty means valid.

    Same contract as validate_new_user_form(), validate_patient_form() and
    validate_inventory_form(), and it exists for the same reason all three do:
    the form carries `novalidate` and a POST can arrive without the page ever
    having been loaded, so every rule is enforced here regardless of what the
    browser did or did not check.

    THE TWO TIMES ARE CHECKED AGAINST EACH OTHER AS WELL AS INDIVIDUALLY.
    A closing time at or before the opening time is each field being valid on its
    own and the pair being nonsense, and it is not a harmless nonsense: the
    bookable slots are generated between them, so it would empty the time
    dropdown on Appointment Scheduling and leave every booking refusable with no
    time an operator could pick. The pair is refused on the closing time, because
    that is the box that was almost certainly the one typed wrong.
    """
    # Imported inside the function on purpose. models/appointments.py imports
    # clinic_hours() from this module to build its time slots, so a top-level
    # import here would close the loop; deferring it to call time breaks the
    # cycle without either module having to know about the other's ordering.
    from models.appointments import SLOT_MINUTES

    errors = {}

    for key in (KEY_NAME, KEY_BARANGAY, KEY_MUNICIPALITY, KEY_PROVINCE):
        value = (values.get(key) or "").strip()
        limit = NAME_MAX_LENGTH if key == KEY_NAME else TEXT_MAX_LENGTH
        if not value:
            errors[key] = REQUIRED_MESSAGES[key]
        elif len(value) > limit:
            errors[key] = (
                f"{FIELD_LABELS[key]} can be at most {limit} characters; this one "
                f"is {len(value)}."
            )

    opening_raw = (values.get(KEY_OPENING) or "").strip()
    closing_raw = (values.get(KEY_CLOSING) or "").strip()
    opening = to_minutes(opening_raw)
    closing = to_minutes(closing_raw)

    if not opening_raw:
        errors[KEY_OPENING] = "Enter the time the clinic opens."
    elif opening is None:
        errors[KEY_OPENING] = "Enter the opening time as a 24-hour time, such as 08:00."

    if not closing_raw:
        errors[KEY_CLOSING] = "Enter the time the clinic closes."
    elif closing is None:
        errors[KEY_CLOSING] = "Enter the closing time as a 24-hour time, such as 17:00."

    if opening is not None and closing is not None and KEY_CLOSING not in errors:
        if closing <= opening:
            errors[KEY_CLOSING] = (
                "The clinic must close after it opens. Closing at "
                f"{display_time(closing_raw)} would leave no time to book in."
            )
        elif closing - opening < SLOT_MINUTES:
            # Refused rather than accepted-and-empty. A window shorter than one
            # slot generates no slots at all, which reaches the operator as a
            # booking form with an empty time dropdown and no explanation.
            errors[KEY_CLOSING] = (
                f"That leaves less than one {SLOT_MINUTES}-minute appointment "
                f"slot. Appointments are booked in {SLOT_MINUTES}-minute slots, "
                "so the clinic day has to be at least that long."
            )

    return errors


# ---------------------------------------------------------------------------
# WRITING
# ---------------------------------------------------------------------------

def _changes(values, current):
    """[(key, was, now)] for the values this submit actually alters.

    Only what moved, so the audit entry says "the province was corrected" rather
    than reciting all six fields on every save. Compared against what was IN
    FORCE, defaults included -- a first save that types the default back in
    changes nothing anybody can observe, and is recorded as changing nothing.
    """
    moved = []
    for key in GENERAL_KEYS:
        was = current[key]
        now = (values.get(key) or "").strip()
        if now != was:
            moved.append((key, was, now))
    return moved


def save_general_settings(values, actor_id):
    """Write the six values. Returns [(key, was, now)] for what changed.

    Assumes validate_general_settings() has already passed -- the caller in
    routes/settings_views.py runs it and returns the form for redisplay on any
    error, so nothing unvalidated reaches this function.

    ALL SIX ROWS ARE WRITTEN, NOT ONLY THE CHANGED ONES, AND THAT IS DELIBERATE.
    A key with no row falls back to DEFAULTS, so writing only the changed keys
    would leave an unchanged field still defaulting -- and a default is a value
    the application chose, not one an administrator decided. After a save all six
    rows exist and say what was submitted, so `updated_by` and `updated_at` on
    each of them answer "who last confirmed this value" rather than "who last
    happened to change it".

    ONE CONNECTION AND ONE COMMIT for all six, so a save cannot land half-applied
    -- a settings table holding the new name beside the old barangay would put a
    place that does not exist on the next export.
    """
    changed = _changes(values, get_settings())

    conn = get_db()
    conn.executemany(
        """
        INSERT INTO settings (setting_key, setting_value, updated_by, updated_at)
             VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(setting_key) DO UPDATE SET
             setting_value = excluded.setting_value,
                updated_by = excluded.updated_by,
                updated_at = CURRENT_TIMESTAMP
        """,
        [
            (key, (values.get(key) or "").strip(), actor_id)
            for key in GENERAL_KEYS
        ],
    )
    conn.commit()
    conn.close()

    # Anything reading settings later in THIS request -- the audit entry below,
    # the flash message, a re-render -- must see what was just written.
    clear_cache()
    return changed


def describe_changes(changed):
    """The change list as one sentence fragment for an audit entry.

    Values are quoted so a change to or from a name with a comma in it can still
    be read, and times are rendered the way the screen shows them rather than as
    the stored 24-hour string, so the entry and the screen agree.
    """
    if not changed:
        return "no value was altered; every field was saved as it already stood"

    parts = []
    for key, was, now in changed:
        if key in (KEY_OPENING, KEY_CLOSING):
            was, now = display_time(was), display_time(now)
        parts.append(f'{FIELD_LABELS[key]} changed from "{was}" to "{now}"')
    return "; ".join(parts)


def last_updated():
    """(when, who) for the most recently saved of the six rows, or (None, None).

    Read from the table itself rather than from the audit trail, so the answer is
    about the stored values -- if a row is ever changed by any route other than
    the one on Screen 13, this still reports it.
    """
    conn = get_db()
    placeholders = ", ".join("?" for _ in GENERAL_KEYS)
    row = conn.execute(
        f"""
        SELECT s.updated_at, u.full_name
          FROM settings s
          LEFT JOIN users u ON u.id = s.updated_by
         WHERE s.setting_key IN ({placeholders})
      ORDER BY s.updated_at DESC, s.id DESC
         LIMIT 1
        """,
        GENERAL_KEYS,
    ).fetchone()
    conn.close()
    if row is None:
        return None, None
    return row["updated_at"], row["full_name"]
