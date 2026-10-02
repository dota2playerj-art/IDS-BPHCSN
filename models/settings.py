"""The health center's own identity and opening hours, stored and read back."""
import re

from flask import g, has_request_context

from database.connection import db_connection

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
# for a change that reaches into SMS messages and every printed letterhead.
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
        "Enter the health center's name. It is printed on every export and at "
        "the front of every SMS the barangay sends."
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
    with db_connection() as conn:
        placeholders = ", ".join("?" for _ in STORED_KEYS)
        rows = conn.execute(
            f"SELECT setting_key, setting_value FROM settings "
        f"WHERE setting_key IN ({placeholders})",
            STORED_KEYS,
        ).fetchall()

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

    with db_connection() as conn:
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
    with db_connection() as conn:
        row = conn.execute(
            """
        SELECT s.updated_at, u.full_name
          FROM settings s
          LEFT JOIN users u ON u.id = s.updated_by
         WHERE s.setting_key = ?
        """,
            (KEY_MAINTENANCE,),
        ).fetchone()
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
    own and the pair being nonsense. The pair is refused on the closing time,
    because that is the box that was almost certainly the one typed wrong.

    This paragraph used to say the nonsense was not harmless because the bookable
    slots were generated between the two times, so an inverted pair emptied the
    time dropdown on Appointment Scheduling. That stopped being true on
    2026-09-05, when advance booking was retired: nothing generates slots and
    nothing is booked. The rule stays, and so does the SLOT_MINUTES floor below,
    because these two times are still what the health center publishes as its own
    hours on every export and every printed record -- and a facility that closes
    before it opens, or is open for twenty minutes, is not a fact worth printing.
    """
    # Imported inside the function, which is now belt and braces rather than
    # necessary. models/appointments.py used to import clinic_hours() from this
    # module to build its time slots, and a top-level import here would have
    # closed that loop; the slots went with advance booking and so did
    # clinic_hours(), so there is no cycle left to break. The deferral costs
    # nothing and is left rather than churned.
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
                f"{display_time(closing_raw)} would leave no day at all."
            )
        elif closing - opening < SLOT_MINUTES:
            # Refused rather than accepted-and-empty. SLOT_MINUTES is the
            # granularity this system reasons about a clinic day in, and a window
            # shorter than one of them is not a day the health center could
            # publish -- it would print on the letterhead as a facility open for
            # twenty minutes.
            errors[KEY_CLOSING] = (
                f"That leaves less than one {SLOT_MINUTES}-minute session. A "
                f"clinic day is measured in {SLOT_MINUTES}-minute steps, so it "
                "has to be at least that long."
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

    with db_connection() as conn:
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
    with db_connection() as conn:
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
    if row is None:
        return None, None
    return row["updated_at"], row["full_name"]
