"""Shared context builders and write handlers for the Service Schedule screen.

One screen, four roles, three blueprints -- the same arrangement Reports &
Analytics has. The Administrator reads it at /admin/service_schedule and is the
only role that can change it; Health Center Staff and the Doctor read it at
/staff/service_schedule; the Barangay Official reads it at
/official/service_schedule. Every one of them is built here, from the same
entries, so no two roles can be shown different days for the same service.

WHO MAY WRITE, AND WHERE THAT IS DECIDED
----------------------------------------
Only the Administrator. That is enforced by the three POST routes existing
under /admin and nowhere else, each guarded role_required("Admin") -- there is
no /staff/... or /official/... URL a forged form could be posted to, which is
the same "enforced by absence" arrangement SMS Notifications uses for Health
Center Staff. `can_edit` below decides only whether the form and the Edit and
Delete buttons are drawn, and it is read from the stored account role, so a
query string cannot switch it on.

WHAT THE SCHEDULE DOES NOT DO
-----------------------------
It restricts nothing. The Patient Queue shows today's services; check-in, the
queue order and Record Consultation are exactly as they were. A walk-in with a
fever is seen on prenatal day, which is the RHU's own account of how these
facilities work. It sends no SMS.

THE FORM AND ITS REDISPLAY
--------------------------
Add, Edit and Delete happen on the screen itself rather than in dialogs: the
form sits in a side panel, ?edit=<id> fills it with one entry, ?delete=<id>
turns it into a confirmation. A refused submit re-renders the screen with the
panel holding exactly what was typed and each message beside its field -- the
standard Add User, Edit User and General Settings set -- and needs no script
to reopen anything, because the panel is never closed.
"""
from models.audit import (
    ACTION_SCHEDULE_ENTRY_ADDED,
    ACTION_SCHEDULE_ENTRY_DELETED,
    ACTION_SCHEDULE_ENTRY_EDITED,
    MODULE_SERVICE_SCHEDULE,
    describe_changes,
    log_action,
)
from models.service_schedule import (
    FIELD_LABELS,
    NOTE_MAX_LENGTH,
    SERVICE_MAX_LENGTH,
    WEEK_ORDINALS,
    WEEKDAY_NAMES,
    by_weekday,
    create_entry,
    delete_entry,
    extract_form,
    form_values,
    get_entries,
    get_entry,
    next_dates,
    service_names,
    services_on,
    update_entry,
    validate_entry,
    would_change,
)
from models.users import get_user_by_id
from utils.dates import today
from utils.security import current_role

MODE_ADD = "add"
MODE_EDIT = "edit"
MODE_DELETE = "delete"

_BLANK_FORM = {"service": "", "weekdays": [], "weeks": [], "note": ""}


def _can_edit():
    """Whether this request may be SHOWN the controls. Not the permission.

    The permission is the Admin-only guard on the three POST routes. This only
    stops the other three roles being drawn a form they could not submit.
    """
    return current_role() == "admin"


def service_schedule_context(mode=None, target=None, form=None, errors=None):
    """Everything the Service Schedule screen renders, for any of the four roles.

    `mode`, `target`, `form` and `errors` describe the Administrator's side
    panel: which of Add / Edit / Delete it shows, which entry it is about, what
    is in the fields, and what was wrong with them. For the other three roles
    they are ignored and no panel is drawn.
    """
    can_edit = _can_edit()
    entries = get_entries()
    day = today()

    for entry in entries:
        # Only for entries tied to weeks of the month. "Every Monday" needs no
        # calendar to apply; "2nd and 4th Wednesday" does, and the next two dates
        # beside it are what saves somebody counting.
        entry["upcoming"] = next_dates(entry, day) if entry["weeks"] else []

    panel = None
    if can_edit:
        mode = mode if mode in (MODE_ADD, MODE_EDIT, MODE_DELETE) else MODE_ADD
        if mode != MODE_ADD and target is None:
            mode = MODE_ADD
        if form is None:
            form = form_values(target) if mode == MODE_EDIT else dict(_BLANK_FORM)
        panel = {
            "mode": mode,
            "target": target,
            "form": form,
            "errors": errors or {},
        }

    return {
        "entries": entries,
        "total_entries": len(entries),
        "week": by_weekday(entries),
        "schedule_today": day,
        "todays_services": services_on(day, entries),
        "can_edit": can_edit,
        "panel": panel,
        "service_suggestions": service_names(entries),
        "weekday_names": WEEKDAY_NAMES,
        "week_ordinals": WEEK_ORDINALS,
        "service_max_length": SERVICE_MAX_LENGTH,
        "note_max_length": NOTE_MAX_LENGTH,
    }


def service_schedule_request(args):
    """The screen as a GET asked for it. Returns (context, message).

    `?edit=<id>` and `?delete=<id>` open the side panel on one entry. A context
    of None with a message means the entry asked for is not on the schedule --
    deleted by somebody else since the page was loaded -- and the caller
    flashes the message and shows the plain screen.

    Only an Administrator's request looks at either parameter. For every other
    role they are ignored, so /staff/service_schedule?edit=1 is simply the
    screen.
    """
    if not _can_edit():
        return service_schedule_context(), None

    for mode in (MODE_EDIT, MODE_DELETE):
        raw = (args.get(mode) or "").strip()
        if not raw:
            continue
        target = get_entry(int(raw)) if raw.isdigit() else None
        if target is None:
            return None, (
                "That schedule entry is not on the schedule any more. It may "
                "already have been deleted."
            )
        return service_schedule_context(mode=mode, target=target), None

    return service_schedule_context(), None


# ---------------------------------------------------------------------------
# AUDIT ENTRIES
# ---------------------------------------------------------------------------

def _actor_phrase(actor_id):
    """The acting administrator, named in the entry as well as in user_id.

    The same shape routes/user_views.py uses, so an entry here and an account
    entry name the same person the same way.
    """
    actor = get_user_by_id(actor_id) if actor_id else None
    if actor is None:
        return "an administrator whose account row could not be read"
    return actor["full_name"]


def _audit_view(entry):
    """The three things a reader sees about an entry, for describe_changes()."""
    return {
        "service": entry["service"],
        "days": entry["days_text"],
        "note": entry["note"] or None,
    }


def _note_clause(entry):
    return f'note: "{entry["note"]}"' if entry["note"] else "no note"


# ---------------------------------------------------------------------------
# WRITES -- reached only through the Administrator's three POST routes
# ---------------------------------------------------------------------------

def _spelling_sentence(typed, stored):
    """Said when a retyped name was stored in the spelling already on the schedule."""
    if " ".join(typed.split()) == stored:
        return ""
    return (
        f' It was saved as "{stored}", the spelling already on the schedule, so '
        "the service is listed once."
    )


def process_add_entry(form_data, actor_id, ip_address=None):
    """Validate and add one entry. Returns (entry, context, message).

    An entry means the caller flashes `message` and redirects. A context means
    the submit was refused and the caller re-renders it: the panel holds what
    was typed and each message sits beside its field.
    """
    values = extract_form(form_data)
    entries = get_entries()
    errors = validate_entry(values, entries)
    if errors:
        return None, service_schedule_context(
            mode=MODE_ADD, form=values, errors=errors
        ), None

    entry = create_entry(values, actor_id, entries)

    log_action(
        actor_id,
        ACTION_SCHEDULE_ENTRY_ADDED,
        module=MODULE_SERVICE_SCHEDULE,
        details=(
            f'Service schedule entry #{entry["id"]} added by '
            f"{_actor_phrase(actor_id)}; service: \"{entry['service']}\"; "
            f'days: {entry["days_text"]}; {_note_clause(entry)}'
        ),
        ip_address=ip_address,
    )

    return entry, None, (
        f'"{entry["service"]}" added to the service schedule: {entry["days_text"]}. '
        "It will be listed on the Patient Queue on those days."
        + _spelling_sentence(values["service"], entry["service"])
    )


def process_edit_entry(entry_id, form_data, actor_id, ip_address=None):
    """Validate and save changes to one entry. Returns (entry, context, message).

    Three outcomes: an entry (saved, or saved unchanged -- the message says
    which), a context (refused, redisplay what was typed), or neither with a
    message (the entry is gone, so there is nothing to redisplay the edit on).
    """
    before = get_entry(entry_id)
    if before is None:
        return None, None, (
            "That schedule entry is not on the schedule any more, so the edit "
            "was not saved. It may have been deleted since the page was opened."
        )

    values = extract_form(form_data)
    entries = get_entries()
    errors = validate_entry(values, entries, editing_id=entry_id)
    if errors:
        return None, service_schedule_context(
            mode=MODE_EDIT, target=before, form=values, errors=errors
        ), None

    # A save that alters nothing is not an event: no row update, no audit entry,
    # and a message that says so rather than claiming an edit.
    if not would_change(before, values, entries):
        return before, None, (
            f'Nothing was changed. "{before["service"]}" was saved exactly as it '
            "stood, so nothing was recorded."
        )

    after = update_entry(entry_id, values, actor_id, entries)
    if after is None:
        return None, None, (
            "That schedule entry was deleted while you were editing it, so the "
            "edit was not saved."
        )

    summary, changed = describe_changes(
        _audit_view(before), _audit_view(after), FIELD_LABELS
    )
    count = len(changed)
    log_action(
        actor_id,
        ACTION_SCHEDULE_ENTRY_EDITED,
        module=MODULE_SERVICE_SCHEDULE,
        details=(
            f'Schedule entry #{entry_id} ("{after["service"]}") edited by '
            f"{_actor_phrase(actor_id)}. {count} field{'' if count == 1 else 's'} "
            f"changed — {summary}"
        ),
        ip_address=ip_address,
    )

    return after, None, (
        f'"{after["service"]}" updated. {summary}.'
        + _spelling_sentence(values["service"], after["service"])
    )


def process_delete_entry(entry_id, actor_id, ip_address=None):
    """Remove one entry. Returns the message to flash.

    Every outcome is a message and a redirect: there is nothing typed to keep.
    """
    removed = delete_entry(entry_id)
    if removed is None:
        return (
            "That schedule entry is not on the schedule any more. It may already "
            "have been deleted; nothing was removed."
        )

    log_action(
        actor_id,
        ACTION_SCHEDULE_ENTRY_DELETED,
        module=MODULE_SERVICE_SCHEDULE,
        details=(
            f'Service schedule entry #{removed["id"]} deleted by '
            f"{_actor_phrase(actor_id)}; it said: service \"{removed['service']}\"; "
            f'days: {removed["days_text"]}; {_note_clause(removed)}'
        ),
        ip_address=ip_address,
    )

    return (
        f'"{removed["service"]}" ({removed["days_text"]}) was removed from the '
        "service schedule."
    )
