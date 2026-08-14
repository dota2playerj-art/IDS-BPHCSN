"""Context for Screen 12, Audit Logs.

Built here rather than inline in routes/admin.py for the same reason every other
screen in this project has a `*_views.py`: the route stays a guard plus a render,
and the shape of the screen is one readable thing in one place.

WHAT THIS SCREEN CAN AND CANNOT SHOW
------------------------------------
audit_logs has exactly two writers today -- the consultation edit path in
routes/consultation_views.py and the broadcast send path in
routes/broadcast_views.py. Everything they write is shown here in full.

Nothing else writes to it. In particular routes/auth.py logs neither logins nor
logout nor failed attempts, and no patient, inventory or appointment write calls
log_action() yet. The screen was drawn with cards for "Login Events" and
"Security Events" and with User / Activity Type / Status filters, none of which
have anything behind them. Rather than let those render plausible-looking
numbers, UNTRACKED below names each absence and the template prints the reason.

That is the rule Screen 03's Prenatal card set and Screen 10 follows: a figure
with no source reports its own absence, because an invented one gets believed.
"""
from models.audit import (
    MODULE_SMS,
    count_audit_logs,
    get_audit_logs,
    get_audit_stats,
)
from utils.dates import to_clinic_time

# How many entries one page of the trail shows. The screen has no paging
# controls behind it yet, so this doubles as the honest ceiling the footer
# reports against -- see the "showing" line in the template.
PAGE_SIZE = 100

# The parts of this screen with no data source, and why. Keyed by the slot on the
# page so the template can look one up next to the thing it explains.
UNTRACKED = {
    "logins": (
        "Login and logout are not recorded. routes/auth.py authenticates and "
        "starts the session but never calls log_action(), so there is no row to "
        "count sign-ins, sign-outs or failed attempts against."
    ),
    "security": (
        "Security events are not recorded. There is no failed-login counter and "
        "no account lockout in the system, so nothing writes the events this "
        "card was drawn to summarise."
    ),
    "filters": (
        "Filtering by user, activity type or status is not wired. The stored "
        "query supports a module filter only, which is the one offered above; "
        "the rest would need columns audit_logs does not have."
    ),
    "export": (
        "Exporting the trail is not implemented. The entries below are the "
        "complete record and can be read on screen."
    ),
}


def _initials(name):
    """'Dr. Joshua Reyes' -> 'JR'. Titles are skipped so the avatar reads as a person."""
    skip = {"dr.", "dr", "mr.", "mrs.", "ms.", "engr."}
    parts = [p for p in str(name or "").split() if p.lower() not in skip]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _split_details(details):
    """One `details` string -> (lead sentence, field changes, remaining notes).

    models/audit.py writes two shapes into this column and both are handled
    without the parser having to know which one it has:

      consultation edit  "<context>. N fields changed — Label: a → b; Label: c → d"
      broadcast sent     "<reference> to <audience> (...); <clause>; <clause>"

    A clause reading "Label: before → after" becomes a before/after pair the
    template can render side by side; anything else is kept verbatim as a note,
    so a clause this parser does not recognise is still shown rather than lost.
    """
    text = (details or "").strip()
    if not text:
        return "", [], []

    lead = ""
    if " — " in text:
        lead, text = text.split(" — ", 1)

    clauses = [c.strip() for c in text.split("; ") if c.strip()]
    if not lead and clauses:
        lead = clauses.pop(0)

    changes, notes = [], []
    for clause in clauses:
        if " → " in clause and ": " in clause.split(" → ", 1)[0]:
            label, rest = clause.split(": ", 1)
            before, after = rest.split(" → ", 1)
            changes.append({
                "field": label.strip(),
                "before": before.strip(),
                "after": after.strip(),
            })
        else:
            notes.append(clause)
    return lead.strip(), changes, notes


def _decorate(entry):
    """One stored row -> the row the table draws, with nothing invented.

    The timestamp is split into its clinic-local time and date halves through
    utils.dates.to_clinic_time(), the same conversion display_timestamp() uses,
    so the two cells cannot disagree with each other or with any other screen.
    """
    local = to_clinic_time(entry.get("created_at"))
    lead, changes, notes = _split_details(entry.get("details"))

    return {
        **entry,
        "time_text": local.strftime("%I:%M %p").lstrip("0") if local else "—",
        "date_text": local.strftime("%b %d, %Y") if local else "—",
        "full_text": (
            f"{local.strftime('%b %d, %Y')}, {local.strftime('%I:%M:%S %p').lstrip('0')}"
            if local else "—"
        ),
        "initials": _initials(entry.get("user_name")),
        "summary": lead,
        "changes": changes,
        "notes": notes,
        "is_sms": entry.get("module") == MODULE_SMS,
    }


def audit_logs_context(module=None):
    """Everything Screen 12 renders.

    `module` is the one filter the stored query supports, so it is the one the
    screen offers. An unknown value is treated as no filter rather than as an
    empty result, so a hand-edited URL cannot make the trail look empty.
    """
    stats = get_audit_stats()
    modules = [row["module"] for row in stats["by_module"]]

    selected = module if module in modules else None
    entries = [_decorate(e) for e in get_audit_logs(module=selected, limit=PAGE_SIZE)]
    matching = count_audit_logs(module=selected)

    return {
        "entries": entries,
        # The entry the detail panel opens on. The table marks the same row
        # selected, so the two always start in step.
        "selected_entry": entries[0] if entries else None,
        "stats": stats,
        "module_options": modules,
        "selected_module": selected,
        "showing": len(entries),
        "matching": matching,
        "page_size": PAGE_SIZE,
        "truncated": matching > len(entries),
        "untracked": UNTRACKED,
    }
