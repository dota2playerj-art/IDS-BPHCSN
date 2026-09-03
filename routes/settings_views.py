"""Context and form handling for Screen 13, Settings.

WHAT CHANGED, AND WHY THE OLD NOTE AT THE TOP OF THIS FILE IS GONE
-------------------------------------------------------------------
Everything this file used to say about itself opened on the same premise:
"nothing on this screen is stored -- the settings table is still empty and no
route writes it". That premise is what has just stopped being true, so the note
that rested on it is replaced rather than amended. It said, correctly for its
time, that turning any field on the screen into a stored value "is a different
and much larger task than the one that closed the sign-in gap". This is that
task, done for the fields that had somewhere to be read.

THE SCREEN NOW HAS FOUR KINDS OF PANE, AND THE DIFFERENCE BETWEEN THEM IS THE
WHOLE DESIGN.

1. STORED AND READ BACK -- General Settings.
   Six values in the settings table (models/settings.py), written by
   process_general_settings() below and read by the SMS composer, all three
   export modules, the booking slot generator and every template's header. This
   is the only pane with a live control on it.

2. READ FROM WHAT THE SYSTEM ACTUALLY DOES -- Security Settings' sign-in
   figures, Password Policy, Backup's size and last-download rows, About
   System's database version.
   Nothing here is typed and nothing here is stored. Each is read from the thing
   it describes, on every load, which is the property that makes it impossible
   for the display to drift from the fact. Password Policy is the sharpest case
   and the reason it is worth stating as a category: it reports the rule
   check_password_strength() enforces by reading the constants that function
   branches on, so a change to the rule changes this screen in the same edit.
   The five controls it replaced described a different policy entirely -- eight
   characters, a 90-day expiry, a reuse history -- none of which this system has
   ever applied.

3. DISABLED, WITH A REASON -- Health Center Information, SMS Gateway, the rest
   of Security Settings, Backup's frequency and retention, System Maintenance.
   Real features that are not built. Each pane carries its own `disabled`
   fieldset now rather than the single one that used to wrap all ten, because a
   fieldset around everything cannot admit one live form inside it.

4. GONE -- User Preferences and Notification Settings.
   Removed outright rather than left disabled. See the note in settings.html.

WHY THE GENERAL FORM IS THE ONLY LIVE ONE, AND WHY THAT IS NOT ARBITRARY
--------------------------------------------------------------------------
The line is not "which fields would be nice to store". It is "which fields does
some other part of the running system already read". Six do -- the facility name
is at the front of every appointment SMS and on every export letterhead, the
three place names make up the address those letterheads print, and the two times
are what the bookable slots are built from. Storing the contact number or the
DOH licence number would produce a control that accepts input and changes
nothing, which is the exact defect utils/unavailable.py exists to keep off this
project's screens.

WHERE THE FIGURES COME FROM
---------------------------
The sign-in counts are models/audit.py's, the same two functions Audit Logs and
User Management read, so this screen cannot report a different number of
sign-ins from the screen whose job it is to report them. The password rule is
models/users.py's. The database size is models/backup.py's, measured off the
file the backup would be taken from. Nothing is counted locally here.
"""
import sqlite3

from models.appointments import get_active_consultation
from models.audit import (
    ACTION_BACKUP_DOWNLOADED,
    ACTION_MAINTENANCE_DISABLED,
    ACTION_MAINTENANCE_ENABLED,
    ACTION_SETTINGS_UPDATED,
    MODULE_SETTINGS,
    get_audit_stats,
    get_last_logins,
    get_latest_entry,
    log_action,
)
from models.backup import create_backup_bytes, database_size_bytes, format_size
from models.settings import (
    GENERAL_KEYS,
    KEY_CLOSING,
    KEY_NAME,
    KEY_OPENING,
    address_line,
    describe_changes,
    display_time,
    get_settings,
    last_updated,
    maintenance_changed_at,
    maintenance_mode,
    save_general_settings,
    set_maintenance_mode,
    validate_general_settings,
)
from models.users import get_all_users, get_user_by_id, password_policy
from routes.report_export import _download
from utils.dates import display_timestamp, now
from utils.workbook import safe_filename


def _most_recent_sign_in(last_logins, users):
    """(account name, rendered timestamp) for the newest sign-in, or (None, None).

    Derived from the same per-account map User Management's Last Login column
    uses rather than from a fresh query, so the two cannot name different
    moments. An empty map means no account has ever signed in, which is a real
    state on a freshly seeded database and is reported as itself.
    """
    if not last_logins:
        return None, None

    by_id = {user["id"]: user for user in users}
    # Ties are real: CURRENT_TIMESTAMP has one-second granularity, and two
    # accounts signing in within the same second is ordinary at shift change.
    # The rendered string cannot tell them apart either way -- display_timestamp()
    # stops at the minute -- so the only thing at stake is which name is printed,
    # and user_id breaks the tie so it is at least the same name on every reload
    # rather than whichever row the map happened to yield first.
    user_id, stamp = max(last_logins.items(), key=lambda item: (str(item[1]), item[0]))
    account = by_id.get(user_id)
    name = account["full_name"] if account else None
    return name, display_timestamp(stamp)


def _last_backup():
    """(rendered timestamp, who) for the last backup taken FROM THIS SCREEN.

    Read out of the audit trail, because the trail is the only record that one
    was taken -- models/backup.py writes no file anywhere and keeps no history of
    its own, by design: what it produces goes straight to the browser that asked
    for it.

    THE LABEL ON THE SCREEN SAYS "FROM THIS SCREEN", AND THAT QUALIFIER IS LOAD-
    BEARING. The practice at this health center has been to copy app.db by hand
    with the date in the filename, and this system cannot see that those copies
    exist. A row reading "Last backup" with a date beside it would claim to be
    the answer to "when was this system last backed up", which it is not and
    cannot be. It answers the narrower question it is labelled with.
    """
    entry = get_latest_entry(MODULE_SETTINGS, ACTION_BACKUP_DOWNLOADED)
    if entry is None:
        return None, None
    return display_timestamp(entry["created_at"]), entry["user_name"]


# ---------------------------------------------------------------------------
# WHICH PANE THE SCREEN OPENS ON
# ---------------------------------------------------------------------------
# WHY THIS EXISTS AT ALL. Screen 13 is eight panes behind one URL. Bootstrap
# switches between them in the browser, so which one is showing was never part
# of anything the server knew -- settings.html simply hardcoded `active` on the
# General nav button and `show active` on #pane-general, and every load started
# there.
#
# That was invisible until a pane other than General grew a control that saves.
# Maintenance Mode did. An administrator pressing "Turn on maintenance mode" was
# redirected back to /admin/settings and landed on General Settings, several
# panes away from the switch they had just thrown and with no sight of whether
# it had worked. The flash message said it had; the screen showed them somewhere
# else.
#
# GENERAL SETTINGS WAS NEVER RIGHT EITHER -- IT WAS LUCKY. Saving it also
# redirects to a screen that always opens on General, and that looked correct
# only because General happened to be the hardcoded default. Nothing preserved
# the tab; the destination and the default coincided. Reordering the panes, or
# making a different one the default, would have broken it exactly as
# Maintenance Mode was broken. So the fix is one shared mechanism used by both
# rather than a redirect patched onto the one that was noticed.
#
# WHY A QUERY PARAMETER AND NOT A #FRAGMENT. The obvious alternative is to
# redirect to /admin/settings#pane-maint. A fragment is never sent to the
# server, so the page would still be RENDERED with General active and a script
# would have to switch panes after paint -- a visible flash of the wrong tab,
# and nothing at all with JavaScript unavailable. A query parameter is resolved
# before the HTML is built, so the correct pane is active in the first byte the
# browser receives, and /admin/settings?tab=maint is a real address that can be
# linked and bookmarked.
TAB_GENERAL = "general"
TAB_MAINTENANCE = "maint"

# Slug -> the pane id it activates. The slugs are the pane ids minus their
# "pane-" prefix, so the URL reads as the thing it selects, and this dict is the
# only place the two vocabularies meet.
SETTINGS_TABS = {
    TAB_GENERAL: "pane-general",
    "hc": "pane-hc",
    "sms": "pane-sms",
    "security": "pane-security",
    "pwd": "pane-pwd",
    "backup": "pane-backup",
    TAB_MAINTENANCE: "pane-maint",
    "about": "pane-about",
}


def resolve_tab(value):
    """A ?tab= value -> the slug to open on. Anything unrecognised gives General.

    THE FALLBACK IS NOT POLITENESS, IT IS THE DIFFERENCE BETWEEN A WRONG TAB AND
    AN EMPTY SCREEN. The template marks exactly the pane this names as `show
    active`; a value matching no pane would mark none of them, and Bootstrap
    hides every .tab-pane that is not active -- so a hand-typed ?tab=nonsense
    would render the nav on the left and a blank panel on the right, which reads
    as the screen being broken rather than as a bad URL.
    """
    return value if value in SETTINGS_TABS else TAB_GENERAL


def _maintenance_state():
    """What the Maintenance Mode row shows: the switch, its history, the warning.

    `in_consultation` is the one thing on this screen that is about clinical
    work rather than configuration, and it is here because it is the only real
    cost of closing the system. A visit that is In Consultation can only be
    written up by the person holding it, and that person is Health Center Staff
    -- so switching the system off mid-consultation leaves the appointment open
    until the window ends. Nothing is corrupted and nothing is lost, but the
    record stays In Consultation meanwhile, and models/appointments.py's
    single-active-consultation guard is not date-scoped, so nobody else can be
    brought in either.

    It is shown as a warning and NOT as a refusal. Closing the system is an
    administrator's decision and there are good reasons to make it during a
    consultation -- that is what an emergency is. What the screen owes them is
    the fact, before they press it, rather than a veto.

    get_active_consultation() is the same call Appointment Scheduling asks "is
    the room free?" with, so this cannot report a consultation the queue screen
    does not show, or miss one it does.
    """
    changed_at, changed_by = maintenance_changed_at()
    active = get_active_consultation()
    return {
        "on": maintenance_mode(),
        "changed_at": display_timestamp(changed_at) if changed_at else None,
        "changed_by": changed_by,
        # first + last, the same pair Appointment Scheduling's queue prints on
        # its rows. There is no full_name on a queue entry -- the appointment
        # join carries the patient's three name columns separately -- so the
        # middle name is left out here for the same reason that screen leaves it
        # out of its own heading: one line naming who is in the room.
        "in_consultation": (
            f'{active["first_name"]} {active["last_name"]}' if active else None
        ),
        "in_consultation_reference": active["patient_reference"] if active else None,
    }


def _general_form(values):
    """The six stored values in the shape the form re-renders from.

    Used when the page is loaded normally. A failed submit passes what was typed
    instead -- see process_general_settings() -- so the two paths hand the
    template the same dict shape and it needs no conditional of its own.
    """
    return {key: values[key] for key in GENERAL_KEYS}


def settings_context(general_form=None, general_errors=None, active_tab=None):
    """Everything Screen 13 renders beyond the shared role context.

    `general_form` and `general_errors` are the form-redisplay pair every other
    form in this project uses (`add_form`/`add_errors` on User Management,
    `form`/`errors` on Register Patient). Both absent means an ordinary load, and
    the form renders from what is stored; both present means a submit was
    refused, and the form renders from what was typed with the messages beside
    the fields that earned them.

    `active_tab` is which of the eight panes opens. It is resolved here rather
    than trusted, so no caller can hand the template a pane that does not exist
    -- see resolve_tab(). A refused General Settings submit does not have to pass
    it: the default is General, which is the pane that submit came from.
    """
    stats = get_audit_stats()
    users = get_all_users()
    last_logins = get_last_logins()
    recent_name, recent_stamp = _most_recent_sign_in(last_logins, users)

    stored = get_settings()
    saved_at, saved_by = last_updated()
    backup_at, backup_by = _last_backup()
    size = database_size_bytes()

    return {
        # The pane that opens. Every render goes through resolve_tab(), so this
        # is always the id of a pane that exists.
        "active_pane": SETTINGS_TABS[resolve_tab(active_tab)],
        "general": {
            # What the form draws. Typed values on a refused submit, stored
            # values otherwise -- so nothing an administrator wrote is thrown
            # away by a validation error.
            "form": general_form if general_form is not None else _general_form(stored),
            "errors": general_errors or {},
            # The address the three place names make. Derived, not stored, so it
            # cannot disagree with the fields above it -- see address_line().
            "address": address_line(),
            # Rendered 12-hour, for the sentence under the two time inputs that
            # says what the clinic day currently is.
            "opening_label": display_time(stored[KEY_OPENING]),
            "closing_label": display_time(stored[KEY_CLOSING]),
            "name": stored[KEY_NAME],
            # None until the first save. An untouched installation is running on
            # the defaults in models/settings.py, and saying "never saved" is the
            # true answer rather than a date invented for the row.
            "saved_at": display_timestamp(saved_at) if saved_at else None,
            "saved_by": saved_by,
        },
        "security": {
            "sign_ins": stats["logins"],
            "sign_ins_today": stats["logins_today"],
            "refused": stats["refused_logins"],
            "refused_today": stats["refused_logins_today"],
            # Broken out because this pane is where an administrator is already
            # reading about access control. A refusal aimed at an account that
            # has been switched off belongs beside the switch, not only in the
            # trail.
            "blocked": stats["blocked_logins"],
            "accounts_signed_in": len(last_logins),
            "total_accounts": len(users),
            "most_recent_name": recent_name,
            "most_recent_at": recent_stamp,
        },
        # The password rule as the validator actually holds it. Not a description
        # maintained here -- every figure in this dict is read from the constants
        # check_password_strength() branches on, so the pane cannot state a rule
        # the system does not enforce. See models/users.password_policy().
        "password_policy": password_policy(),
        "backup": {
            "size": format_size(size),
            "size_bytes": size,
            "last_at": backup_at,
            "last_by": backup_by,
        },
        # The one live control outside General Settings. Read from the same
        # settings row utils/security.py's guard reads on every request, so the
        # switch on the screen cannot show one state while the system enforces
        # the other.
        "maintenance": _maintenance_state(),
        "system": {
            # Not the sqlite3 module's own version: this is the SQLite library
            # the interpreter is linked against, which is what actually stores
            # the rows every other figure on this screen was counted from.
            "sqlite_version": sqlite3.sqlite_version,
        },
    }


# ---------------------------------------------------------------------------
# SAVING GENERAL SETTINGS
# ---------------------------------------------------------------------------

def process_general_settings(form_data, actor_id, ip_address=None):
    """Validate and save the six General Settings. Returns (context, message).

    The two are mutually exclusive, the same contract process_create_user() and
    process_add_edit_medicine() use: a context means the caller should re-render
    Settings with the errors beside the fields and what was typed still in them,
    a message means it should redirect and flash.

    EVERY VALUE IS RE-VALIDATED HERE REGARDLESS OF WHAT THE BROWSER DID.
    The form carries `novalidate` like every other form in this project, and a
    POST can arrive without the page ever having been loaded -- so the required
    fields, the lengths and the ordering of the two times are all decided by
    validate_general_settings() and not by the input types on the page.

    THE AUDIT ENTRY NAMES WHAT MOVED, NOT WHAT WAS SUBMITTED.
    save_general_settings() returns the list of values that actually changed, and
    the entry is written from that -- so a save that confirmed the existing
    values reads as having confirmed them rather than as six changes. Both cases
    are recorded: "this was reviewed and left alone" is a fact worth being able
    to see in the trail, and it is also the honest thing to write when somebody
    pressed Save.
    """
    values = {key: (form_data.get(key) or "").strip() for key in GENERAL_KEYS}

    errors = validate_general_settings(values)
    if errors:
        return settings_context(general_form=values, general_errors=errors), None

    changed = save_general_settings(values, actor_id)

    actor = get_user_by_id(actor_id) if actor_id else None
    actor_phrase = (
        f'{actor["full_name"]} ("{actor["username"]}", {actor["role"]})'
        if actor is not None else
        "an administrator whose account row could not be read"
    )

    log_action(
        actor_id,
        ACTION_SETTINGS_UPDATED,
        module=MODULE_SETTINGS,
        details=(
            f"General Settings saved by {actor_phrase}: {describe_changes(changed)}"
            ". These six values are read by the rest of the system rather than "
            "only displayed: the health center's name is the first thing in "
            "every appointment SMS and the heading on every PDF and Excel "
            "export, the barangay, municipality and province make up the "
            "address those exports and the sign-in page print, and the opening "
            "and closing times are what the bookable appointment slots are "
            "generated from — so a change to the times changes which times "
            "Appointment Scheduling will accept. Messages already sent and files "
            "already downloaded are unaffected; they carry the values that were "
            "in force when they were produced"
        ),
        ip_address=ip_address,
    )

    if not changed:
        return None, (
            "General Settings saved. Nothing was different from what was already "
            "stored, so no value changed."
        )

    if len(changed) == 1:
        key, _was, _now = changed[0]
        if key in (KEY_OPENING, KEY_CLOSING):
            return None, (
                "General Settings saved. The clinic day is now "
                f"{display_time(values[KEY_OPENING])} to "
                f"{display_time(values[KEY_CLOSING])}, and Appointment "
                "Scheduling offers and accepts times inside it."
            )

    return None, (
        f"General Settings saved. The health center is now named "
        f'"{values[KEY_NAME]}" on every screen, on every export, and in every '
        "appointment SMS sent from now on."
    )


# ---------------------------------------------------------------------------
# RECORDING A BACKUP DOWNLOAD
# ---------------------------------------------------------------------------

def log_backup_download(actor_id, size, filename, ip_address=None):
    """Record that a complete copy of the database left the system.

    Written AFTER the copy has been made and verified, so the entry describes a
    file that exists and passed its integrity check rather than an attempt that
    may have failed -- an audit row saying a backup was taken, when it was not,
    would be worse than no row at all.

    The entry says what the file contains in plain terms rather than naming
    tables, because the question it answers months later is "what did somebody
    walk away with", and the answer is: everything.
    """
    actor = get_user_by_id(actor_id) if actor_id else None
    actor_phrase = (
        f'{actor["full_name"]} ("{actor["username"]}", {actor["role"]})'
        if actor is not None else
        "an administrator whose account row could not be read"
    )

    return log_action(
        actor_id,
        ACTION_BACKUP_DOWNLOADED,
        module=MODULE_SETTINGS,
        details=(
            f"{actor_phrase} downloaded a backup of the database as "
            f'"{filename}" ({format_size(size)}). The file is a complete copy of '
            "every record this system holds — every patient, consultation, "
            "immunisation, appointment, stock movement, SMS broadcast, audit "
            "entry and user account — taken with SQLite's own online backup "
            "interface while the system was running, and checked with PRAGMA "
            "integrity_check before it was sent. Account passwords are in it "
            "only as the salted hashes they are stored as; nothing in the file "
            "reveals a password. The copy now exists outside this system and "
            "cannot be recalled or tracked from here, which is why the download "
            "is recorded even though it changed no record"
        ),
        ip_address=ip_address,
    )


# The MIME type for a SQLite database file. Registered with IANA in 2021, and
# the correct answer for what this download is -- not application/octet-stream,
# which is what a server says when it does not know. A browser has no viewer for
# either, so both produce a save; the difference is what the file is labelled as
# when it lands, and one of the two is true.
SQLITE_MIMETYPE = "application/vnd.sqlite3"


def backup_download_response(actor_id, ip_address=None):
    """Make a verified copy of the database and serve it as a download.

    ORDER MATTERS AND IS THE POINT OF THIS FUNCTION.
    The copy is taken and passes PRAGMA integrity_check (models/backup.py) BEFORE
    the audit entry is written and before any response is built. A failed backup
    therefore raises, writes no entry, and serves nothing -- rather than leaving
    a trail claiming a backup exists and a browser holding a file that will not
    open. The trail is the only record this system keeps that a backup was ever
    taken, so an entry for one that failed would corrupt the one figure the
    Backup pane reports.

    The filename carries the date and time to the minute, matching the practice
    the `backup` reason on this screen describes -- a copy of the file with the
    date in its name -- so a folder of these sorts chronologically and two taken
    on the same day do not overwrite each other.

    Routed through report_export._download(), the same helper the eleven export
    routes use, so the attachment header and the filename are decided in one
    place for every file this application hands out.
    """
    payload = create_backup_bytes()
    stamped = now()
    filename = safe_filename(
        f"IDS-BPHCSN backup {stamped.strftime('%Y-%m-%d %H%M')}.db"
    )

    log_backup_download(actor_id, len(payload), filename, ip_address)

    return _download((payload, filename), SQLITE_MIMETYPE)


# ---------------------------------------------------------------------------
# MAINTENANCE MODE
# ---------------------------------------------------------------------------
# The two things the switch can be asked for. Constants rather than literals so
# the template's button values and the branch below cannot drift apart -- the
# same arrangement DEACTIVATE / REACTIVATE have in routes/user_views.py, and for
# the same reason: these are the other pair of controls in this project that
# decide who can use the system.
MAINTENANCE_ENABLE = "enable"
MAINTENANCE_DISABLE = "disable"
MAINTENANCE_ACTIONS = (MAINTENANCE_ENABLE, MAINTENANCE_DISABLE)


def process_maintenance_mode(form_data, actor_id, ip_address=None):
    """Open or close the system. Returns the message to flash.

    A message and never a context, unlike process_general_settings(): there is
    nothing typed here to preserve on a refusal. A switch has two positions and
    the form carries which one was asked for, so every failure is "that was not
    a valid request" rather than "fix this field".

    THE REQUESTED ACTION IS VALIDATED AGAINST MAINTENANCE_ACTIONS RATHER THAN
    TRUSTED. A POST can be made without ever loading the page, and this is the
    one form in the project whose payload could close the system to every health
    worker in the barangay -- so an unrecognised value is refused outright
    rather than being read as falsy and quietly interpreted as "disable".

    NOTHING HERE HAS TO PROTECT THE ADMINISTRATOR FROM LOCKING THEMSELVES OUT,
    and that is worth stating because it is the first thing anybody asks of this
    feature. The guard in utils/security.py admits every Administrator whatever
    the switch says -- the condition it tests is "not an Administrator", which
    for them is not a branch that exists. Compare the last-administrator rule in
    models/users.py, which genuinely needs a count inside a transaction to be
    sure of its answer. This needs neither, and the two together are what make
    the lockout unrecoverable-proof: an Administrator can always sign in, and
    there is always at least one active Administrator account to sign in as,
    because deactivate_user() and update_user() refuse to remove the last one.
    """
    action = (form_data.get("action") or "").strip()
    if action not in MAINTENANCE_ACTIONS:
        return "Choose whether to turn maintenance mode on or off."

    enabling = action == MAINTENANCE_ENABLE

    # Captured BEFORE the write, so the entry describes the room as it stood at
    # the moment the system was closed rather than as it stands afterwards.
    active = get_active_consultation() if enabling else None

    changed = set_maintenance_mode(enabling, actor_id)
    if not changed:
        # Pressed twice, or two administrators pressed it at once. Not an error
        # and not worth an audit entry -- nothing moved -- but saying "saved"
        # would imply something did.
        return (
            "Maintenance mode was already on; nothing changed."
            if enabling else
            "Maintenance mode was already off; nothing changed."
        )

    actor = get_user_by_id(actor_id) if actor_id else None
    actor_phrase = (
        f'{actor["full_name"]} ("{actor["username"]}", {actor["role"]})'
        if actor is not None else
        "an administrator whose account row could not be read"
    )

    if enabling:
        consultation_note = (
            f'; a consultation was in progress at the time -- '
            f'{active["first_name"]} {active["last_name"]} '
            f'({active["patient_reference"]}), appointment '
            f'{active["reference"]} -- and the staff member holding it cannot '
            "write it up until the system is reopened, so the appointment stays "
            "In Consultation and no other patient can be brought in meanwhile"
            if active is not None else
            "; no consultation was in progress at the time"
        )
        log_action(
            actor_id,
            ACTION_MAINTENANCE_ENABLED,
            module=MODULE_SETTINGS,
            details=(
                f"Maintenance mode turned ON by {actor_phrase}. Health Center "
                "Staff and Barangay Official accounts are refused on every "
                "screen and at the sign-in form for as long as it stays on, and "
                "are shown a page saying the system is temporarily closed rather "
                "than being signed out — their sessions are left intact, so they "
                "resume where they were when it is turned off. Administrator "
                "access is unaffected, which is what guarantees the system can "
                "be reopened. Nothing is recorded when a blocked person is "
                "turned away; this entry and the matching one that reopens the "
                f"system are the whole record of the window{consultation_note}"
            ),
            ip_address=ip_address,
        )
        if active is not None:
            return (
                "Maintenance mode is ON. Only Administrators can use the system "
                f'now. Note that {active["first_name"]} {active["last_name"]} is '
                "still In Consultation — the staff member with them cannot "
                "complete that record until you turn this off."
            )
        return (
            "Maintenance mode is ON. Only Administrators can use the system now. "
            "Everyone else sees a page saying it is temporarily closed; they stay "
            "signed in and resume where they were when you turn it off. Your own "
            "access is unaffected."
        )

    log_action(
        actor_id,
        ACTION_MAINTENANCE_DISABLED,
        module=MODULE_SETTINGS,
        details=(
            f"Maintenance mode turned OFF by {actor_phrase}. Health Center Staff "
            "and Barangay Official accounts can sign in and use every screen "
            "their role admits them to again, with immediate effect: the check "
            "runs on each request rather than at sign-in, so anyone who was "
            "sitting on the maintenance page is back at work on their next "
            "click without signing in again"
        ),
        ip_address=ip_address,
    )
    return (
        "Maintenance mode is OFF. Health Center Staff and Barangay Officials can "
        "use the system again — anyone still holding the maintenance page is back "
        "at work on their next click, without signing in again."
    )
