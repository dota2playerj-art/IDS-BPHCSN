"""Context for Screen 12, Audit Logs.

Built here rather than inline in routes/admin.py for the same reason every other
screen in this project has a `*_views.py`: the route stays a guard plus a render,
and the shape of the screen is one readable thing in one place.

WHAT THIS SCREEN CAN AND CANNOT SHOW
------------------------------------
audit_logs has three writers today: the consultation edit path in
routes/consultation_views.py, the broadcast send path in
routes/broadcast_views.py, and the login route in routes/auth.py. Everything
they write is shown here in full.

THE THIRD WRITER IS NEW, AND IT CHANGED WHAT THIS SCREEN CAN SAY
-----------------------------------------------------------------
This note used to read "exactly two writers", and went on to say that
routes/auth.py logged neither logins nor logout nor failed attempts -- which is
why the screen's "Login Events" and "Security Events" cards both printed a dash
and named their own absence. That is no longer the state of the system. The login
route now writes one entry per successful sign-in and one per sign-in refused
against an account that exists, so both cards report counts of real rows, and
"Authentication" is a module the filter above the table can select.

A refusal is written under one of two activity phrases, and the difference is the
point of keeping them apart. "Refused sign-in attempt" is a credential that did
not match. "Blocked sign-in to deactivated account" is an account that has been
switched off, refused whether or not the password was right -- and its entry says
which, because a correct password against a revoked account is the one line here
that tells an administrator a withdrawn credential is still live. The Security
Events card adds the two; the trail keeps them separate. The person at the login
form is told neither: all three outcomes return one identical message, so the
form cannot be used to sort guessed usernames into real, disabled and fictional.

What is left absent is narrower, and precise enough to be worth stating rather
than glossing: an attempt against a username that does not exist writes nothing
at all (audit_logs.user_id is NOT NULL and foreign-keyed to a real account, so
there is no row to attribute one to), and signing out is not recorded. Those two
are what UNTRACKED["login_scope"] below says, and the Security Events card
carries it as its own tooltip -- a real figure with its boundary stated beside
it, rather than a figure left to be read as more than it is.

No patient, inventory or appointment write calls log_action() yet, and the User /
Activity Type / Status filters the screen was drawn with still have nothing
behind them.

That is the rule Screen 03's Prenatal card set and Screen 10 follows: a figure
with no source reports its own absence, because an invented one gets believed --
and its corollary, which this screen is now the clearest example of, that a
reason is deleted the moment the gap it describes is closed.
"""
from models.audit import (
    ACTION_LOGIN_BLOCKED,
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    ACTION_SESSION_REVOKED,
    MODULE_AUTH,
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
    # THERE IS NO "logins" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said login and logout are not recorded, and that routes/auth.py never
    # calls log_action() -- true when it was written, and the direct cause of the
    # dash on the Login Events card. That route now writes an entry for every
    # sign-in, so the card counts rows instead of quoting this, and a reason with
    # nothing quoting it is exactly the drift utils/unavailable.py exists to
    # prevent. It goes rather than sitting here describing a state the
    # application has left.
    #
    # "security" went the same way and was replaced rather than simply deleted.
    # It claimed security events are not recorded at all; refused sign-ins are
    # now recorded, so the claim is false. But the card that quoted it would be
    # overstated if it were left with no caveat at all, because two real gaps
    # remain inside it. So the reason narrowed to exactly those two, under a name
    # that says what it now is: not "this figure has no source" but "this figure
    # has a source and here is its edge".
    "login_scope": (
        "Both sign-in figures count real rows, and every one of them is in the "
        "trail below. Two things sit outside them. An attempt against a username "
        "that does not exist writes nothing: audit_logs.user_id is NOT NULL and "
        "foreign-keyed to a real account, so there is no row such an attempt "
        "could be attributed to -- what is counted is every refusal aimed at an "
        "account that exists, which is every attempt that could ever have "
        "succeeded. And signing out is not recorded, so these are sign-in counts "
        "rather than session counts. Nothing here locks an account either: a "
        "rising number is something for a person to notice, because repeated "
        "failures against an account never close it on their own. An account can "
        "be shut off, but only by being marked deactivated -- those refusals are "
        "counted here too, under their own activity phrase, and a deactivated "
        "account is refused even when the password presented is correct."
    ),
    "filters": (
        "Filtering by user, activity type or status is not wired. The stored "
        "query supports a module filter only, which is the one offered above; "
        "the rest would need columns audit_logs does not have."
    ),
    # THERE IS NO "export" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said exporting the trail is not implemented. Export Excel and Export PDF
    # are now real on this screen -- routes/audit_export.py assembles the trail
    # once and renders it as either file -- so nothing quotes this, and a reason
    # with nothing quoting it is the drift utils/unavailable.py exists to prevent.
    # It goes the way "print" and "export_pdf" went, rather than sitting here
    # describing a state the screen has left.
    #
    # This screen also never quoted the shared `export` reason, which was its own
    # small drift: it was the only Export button in the project explaining itself
    # in different words from the rest. That is moot now that the button works.
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

    models/audit.py writes three shapes into this column and all are handled
    without the parser having to know which one it has:

      consultation edit  "<context>. N fields changed — Label: a → b; Label: c → d"
      broadcast sent     "<reference> to <audience> (...); <clause>; <clause>"
      sign-in / refusal  "<who, as what, from where>; <clause>; <clause>"

    The authentication shape needs no special case: it carries no " → " in any
    clause, so every one of its clauses falls through to `notes` and is shown
    verbatim, which is exactly right for a sentence that describes an event
    rather than an edit.

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


# The two authentication outcomes deserve different glyphs from each other, not
# merely a shared one: a refusal and an admission are the entries most likely to
# be scanned for rather than read, and they must not look alike in a list.
_ICONS = {
    ACTION_LOGIN_SUCCESS: "login",
    ACTION_LOGIN_FAILED: "gpp_bad",
    # Distinct from the refusal above for the same reason the action phrase is:
    # scanning the trail, a revoked credential still being presented must not
    # look like somebody mistyping their password.
    ACTION_LOGIN_BLOCKED: "person_off",
    # And distinct again from that one. `person_off` is somebody being turned
    # away at the door; this is a session that was already inside being cut off,
    # so the glyph is a severed link rather than a barred person. Verified
    # present in static/fonts/material-symbols-outlined.woff2 -- that file is a
    # fixed subset and a ligature it does not carry renders as its own literal
    # name, which is the failure mode medicine_inventory.html documents.
    ACTION_SESSION_REVOKED: "link_off",
}
_MODULE_ICONS = {
    MODULE_SMS: "campaign",
    MODULE_AUTH: "shield_person",
}


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
        # The glyph the detail panel puts at the top of the entry. Chosen here
        # rather than in the template so the panel does not have to grow a
        # conditional per module: an authentication entry showed the edit_note
        # pencil before this, which read as though signing in had changed a
        # record.
        "icon": _ICONS.get(entry.get("action"), _MODULE_ICONS.get(
            entry.get("module"), "edit_note"
        )),
    }


def audit_export_context(module=None):
    """Every entry the export writes, for the module filter in force.

    Separate from audit_logs_context() for one reason: that one caps at PAGE_SIZE
    because a screen is a page, and this one must not, because a file is the
    record. Both resolve `module` the same way and decorate rows through the same
    _decorate(), so the file and the screen cannot describe the same entry
    differently -- they differ only in how many entries they carry.
    """
    modules = [row["module"] for row in get_audit_stats()["by_module"]]
    selected = module if module in modules else None
    entries = [_decorate(e) for e in get_audit_logs(module=selected, limit=None)]

    return {
        "entries": entries,
        "selected_module": selected,
        "module_options": modules,
        "total": len(entries),
        "page_size": PAGE_SIZE,
        "untracked": UNTRACKED,
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
