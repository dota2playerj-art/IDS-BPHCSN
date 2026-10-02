"""Context for Screen 12, Audit Logs.

Built here rather than inline in routes/admin.py for the same reason every other
screen in this project has a `*_views.py`: the route stays a guard plus a render,
and the shape of the screen is one readable thing in one place.

WHAT THIS SCREEN CAN AND CANNOT SHOW
------------------------------------
Every path that changes a record or an account writes to audit_logs, and
everything written is shown here in full. Since Task 4 (H3) that includes
patient registration, edits and status changes (a death declaration and its
reversal have their own phrases), new consultations, doses recorded at a visit,
dispensing, inventory changes and the Patient Queue. Those entries are written
by routes/audit_entries.py, in the same transaction as the change.
tests/verify_audit_coverage.py fails if a write path has no audit entry.

THE FOURTH WRITER IS THE FIRST THAT IS NOT AN EDIT, A MESSAGE OR AN ACCESS
--------------------------------------------------------------------------
It is a correction, and the trail says so in its own word. Both places a
vaccination can be entered are deliberately add-only -- a recorded dose is shown
as locked fact rather than as a checkbox, because an absent checkbox is not
evidence a child was never vaccinated -- so a wrongly recorded vaccine, dose or
date is put right on a separate, confirmed path reached from the Patient Profile
and nowhere else. Every correction writes one entry here under
"Immunization Records", naming the record, the patient, who recorded it
originally, and each field that moved with both of its values. The two activity
phrases stay apart because an EPI dose is graded against the national schedule
and a vaccination outside it is graded against nothing: moving an EPI date moves
who reads as Due Now or Overdue, and a reader scanning for that must not have to
open each entry to tell the two apart.

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

The User / Activity Type / Status filters the screen was drawn with still have
nothing behind them.

That is the rule Screen 03's Prenatal card set and Screen 10 follows: a figure
with no source reports its own absence, because an invented one gets believed --
and its corollary, which this screen is now the clearest example of, that a
reason is deleted the moment the gap it describes is closed.
"""
from models.audit import (
    ACTION_CONSULTATION_COMPLETED,
    ACTION_LEFT_BEFORE_SEEN,
    ACTION_LEFT_UNDONE,
    ACTION_SENT_TO_DOCTOR,
    ACTION_SERVICE_CHANGED,
    ACTION_CONSULTATION_RECORDED,
    ACTION_CONSULTATION_STARTED,
    ACTION_INVENTORY_ADDED,
    ACTION_INVENTORY_ARCHIVED,
    ACTION_INVENTORY_EDITED,
    ACTION_INVENTORY_RESTORED,
    ACTION_MEDICINE_DISPENSED,
    ACTION_PATIENT_CHECKED_IN,
    ACTION_PATIENT_DEATH_REVERSED,
    ACTION_PATIENT_DECLARED_DECEASED,
    ACTION_PATIENT_REGISTERED,
    ACTION_PATIENT_STATUS_CHANGED,
    ACTION_PATIENT_UPDATED,
    ACTION_STOCK_ADJUSTED,
    ACTION_LOGIN_BLOCKED,
    ACTION_LOGIN_FAILED,
    ACTION_PASSWORD_CHANGE_FAILED_SELF,
    ACTION_BACKUP_DOWNLOADED,
    ACTION_LOGIN_SUCCESS,
    ACTION_MAINTENANCE_DISABLED,
    ACTION_MAINTENANCE_ENABLED,
    ACTION_REQUEST_REFUSED,
    ACTION_SESSION_ABSOLUTE_TIMEOUT,
    ACTION_SESSION_IDLE_TIMEOUT,
    ACTION_SESSION_REVOKED,
    ACTION_SETTINGS_UPDATED,
    ACTION_PASSWORD_RESET,
    ACTION_USER_CREATED,
    ACTION_USER_DEACTIVATED,
    ACTION_USER_EDITED,
    ACTION_USER_ROLE_CHANGED,
    ACTION_USER_REACTIVATED,
    ACTION_CONSULTATION_RESTRICTED,
    ACTION_CONSULTATION_UNRESTRICTED,
    ACTION_DIAGNOSIS_REFUSED,
    ACTION_RESTRICTED_WITHHELD,
    ACTION_SCHEDULE_ENTRY_ADDED,
    ACTION_SCHEDULE_ENTRY_DELETED,
    ACTION_SCHEDULE_ENTRY_EDITED,
    MODULE_AUTH,
    MODULE_CONFIDENTIALITY,
    MODULE_IMMUNIZATIONS,
    MODULE_SERVICE_SCHEDULE,
    MODULE_SETTINGS,
    MODULE_SMS,
    MODULE_USERS,
    count_audit_logs,
    get_audit_logs,
    get_audit_stats,
)
from utils.dates import to_clinic_time
from utils.names import initials

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
    # SHORTENED, AND PUT IN STEP WITH SCREEN 13.
    # At 901 characters this was the longest string in the project's UI, and it
    # quoted a NOT NULL constraint and a foreign key under a card a barangay
    # official reads. It also stated the same five facts about signing in that
    # Settings stated in its own words at its own length, so one system had two
    # vocabularies for one subject.
    #
    # The first five sentences below are now word for word the ones in
    # templates/settings.html under "What is actually recorded". What is added
    # here is only what is about this card rather than about signing in: that the
    # figures count rows in the trail below, and that nothing acts on a rising
    # count. Edit the two together or they drift apart again.
    #
    # The schema reason is kept here rather than on screen: an attempt on an
    # unknown username writes nothing because audit_logs.user_id is NOT NULL and
    # foreign-keyed to a real account, so what is counted is every refusal aimed
    # at an account that exists -- which is every attempt that could ever have
    # succeeded.
    "login_scope": (
        "Both figures count rows in the trail below. "
        "A refused sign-in records the account, the time and the address. "
        "The password is never recorded. "
        "An attempt on a username that does not exist is not recorded at all. "
        "Signing out is not recorded either, so these are sign-in counts, not "
        "sessions. "
        "A deactivated account is refused even when the password is correct, and "
        "the entry says so -- those refusals are counted here too. "
        "Nothing locks an account: a rising count is for someone to notice."
    ),
    "filters": (
        "The module filter above is the only one that works. Filtering by user, "
        "activity type or status is not built."
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


# "?" rather than a blank when there is no name: every row here names an account
# that definitely exists, so an empty circle would read as the name having gone
# missing rather than as there being nobody. utils/names.py holds the rule.
def _initials(name):
    return initials(name, "?")


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
    # Sessions the server ended because a session limit passed. Both glyphs are
    # already drawn elsewhere in this project, so the font subset carries them.
    ACTION_SESSION_IDLE_TIMEOUT: "hourglass_top",
    ACTION_SESSION_ABSOLUTE_TIMEOUT: "lock_clock",
    # A request refused for a missing or wrong form token (utils/csrf.py).
    # `gpp_maybe` is drawn on this screen's own stat cards, so the font has it.
    ACTION_REQUEST_REFUSED: "gpp_maybe",
    # A refused own-password change. It needs a glyph of its own for the reason
    # the three above do: it is a refusal, and the successful self-change beside
    # it in the trail carries no entry in this map at all, so without one an
    # admission and a refusal on the same screen would render the identical
    # Authentication module icon -- the precise thing this map exists to
    # prevent. `password` rather than another shield: `gpp_bad` is the login
    # form's refusal and this one is not a sign-in, so the two must not read as
    # the same event happening twice. Drawn already in this project's templates,
    # which is the available check that the fixed font subset in static/fonts
    # carries it; one it does not hold renders as its own literal name.
    ACTION_PASSWORD_CHANGE_FAILED_SELF: "password",
    # The three account-management entries. Each gets its own glyph for the
    # reason the three phrases are separate constants: these are the rows a
    # reviewer scans a list for rather than reads in order, and an account being
    # created, revoked and restored must not look alike at a glance.
    #
    # `block` rather than the `person_off` above it, deliberately. That one
    # already means "a deactivated account was refused at the login form" -- a
    # thing that happened TO the account -- and this means "an administrator
    # switched the account off". Sharing a glyph would make the cause and its
    # consequence indistinguishable in exactly the list where telling them apart
    # is the point.
    #
    # All three ligatures are already drawn literally in this project's own
    # templates -- `person_add` on User Management's own Add User button,
    # `how_to_reg` on its Active Accounts card, `block` on Medicine Inventory --
    # which is the only available check that the font subset in static/fonts
    # carries them: it is a fixed subset, and a ligature it does not hold renders
    # as its own literal name, the failure mode medicine_inventory.html
    # documents. The same holds for `manage_accounts` below, drawn in base.html.
    ACTION_USER_CREATED: "person_add",
    ACTION_USER_DEACTIVATED: "block",
    ACTION_USER_REACTIVATED: "how_to_reg",
    # The three later account-management entries, on the same principle: a
    # reviewer scans this list rather than reading it in order, so no two of the
    # six may look alike at a glance.
    #
    # `edit` and `lock_reset` are the glyphs User Management draws on the two
    # buttons that produce these entries -- the trail and the control that wrote
    # it read as one thing, which is the same reasoning MODULE_IMMUNIZATIONS'
    # `vaccines` above is chosen on.
    #
    # `shield` for a role change, and it is deliberately not `shield_person`:
    # that one is MODULE_AUTH's pill and means somebody presenting credentials at
    # the door. This means somebody's set of doors was changed, which is the row
    # in this table that most needs to stand out on its own.
    #
    # All three ligatures are already drawn in this project's templates --
    # `edit` and `lock_reset` on User Management's own buttons, `shield` on
    # Settings' Security Settings tab -- which is the available check that the fixed font subset in
    # static/fonts carries them; one it does not hold renders as its own literal
    # name.
    ACTION_USER_EDITED: "edit",
    ACTION_USER_ROLE_CHANGED: "shield",
    ACTION_PASSWORD_RESET: "lock_reset",
    # The two Settings entries, given separate glyphs rather than sharing the
    # module's, because they are opposite kinds of event under one pill: one
    # changed how the system is configured, the other took a complete copy of
    # everything in it away. A reviewer scanning for the second must not have to
    # read the text of the first to tell them apart -- the same reasoning that
    # keeps deactivation and reactivation on separate phrases above.
    #
    # `tune` is the glyph Settings' own General pane carries in its left-hand
    # nav and `backup` the one on the download button, so each entry and the
    # control that wrote it read as one place. Both are already drawn in this
    # project's templates, which is the available check that the fixed font
    # subset in static/fonts carries them; one it does not hold renders as its
    # own literal name.
    ACTION_SETTINGS_UPDATED: "tune",
    ACTION_BACKUP_DOWNLOADED: "backup",
    # The two maintenance entries, and they are given OPPOSITE glyphs rather
    # than one shared "maintenance" one. These are the only entries in the trail
    # that describe the whole system being shut to most of the people who use
    # it, and the pair reads as a window -- a reviewer scanning for "when could
    # nobody work" is looking for the closing and the opening, and a padlock
    # against an open padlock says which is which without reading either row.
    #
    # `lock` is already drawn on the sign-in form. `lock_open` is not drawn
    # anywhere else in this project, so the usual check -- "it renders somewhere
    # already" -- was not available for it and the font subset was read directly
    # instead: static/fonts/material-symbols-outlined.woff2 carries 4010 glyphs
    # and both of these are among them. That matters because the subset is fixed
    # and a ligature it does not hold renders as its own literal name, so an
    # unverified glyph would have put the word "lock_open" in the trail.
    ACTION_MAINTENANCE_ENABLED: "lock",
    ACTION_MAINTENANCE_DISABLED: "lock_open",
    # The four confidentiality entries. Each gets its own glyph for the reason
    # the four phrases are separate constants: two of them are a clinician
    # deciding who may read a record, and two are somebody being kept out of one.
    # A reviewer scans this list rather than reading it in order, and those are
    # the rows they are scanning FOR.
    #
    # `shield_lock` for the seal and `no_encryption` for its lifting: opposite
    # glyphs rather than one shared padlock, on the same argument the maintenance
    # pair above rests on -- these describe a window during which a record was
    # privileged, and a reviewer looking for "was this ever opened back up" wants
    # the closing and the opening to be distinguishable without reading either
    # row. The plain `lock` / `lock_open` pair is taken, by that maintenance pair,
    # and reusing it would make a record being sealed look like the whole system
    # being shut.
    #
    # `visibility_off` for a withheld view, which is the only entry in this trail
    # that means somebody LOOKED and was shown less than the record holds -- and
    # is deliberately the eye that Patient Profile's own View control uses,
    # negated, so the entry and the act read as one place.
    #
    # `gpp_bad` for a refused field. It is the login form's refusal glyph and
    # that is the intended echo: both mean a request was turned away rather than
    # served, and this is the only other place in the system where that happens
    # to somebody already inside. It is distinct from ACTION_SESSION_REVOKED's
    # `link_off` and from ACTION_PASSWORD_CHANGE_FAILED_SELF's `password`, which
    # are the two other refusals aimed at a live session.
    #
    # All four were checked against static/fonts/material-symbols-outlined.woff2
    # directly rather than by the usual "it renders somewhere already" test,
    # because none of the three new ones is drawn anywhere else in this project.
    # That file is a fixed subset and a ligature it does not carry renders as its
    # own literal name -- an unverified glyph would have put the word
    # "shield_lock" into the audit trail.
    ACTION_CONSULTATION_RESTRICTED: "shield_lock",
    ACTION_CONSULTATION_UNRESTRICTED: "no_encryption",
    ACTION_RESTRICTED_WITHHELD: "visibility_off",
    ACTION_DIAGNOSIS_REFUSED: "gpp_bad",
    # The three service-schedule entries, one glyph each for the reason the
    # three phrases are separate: a reviewer looking for "when was prenatal day
    # dropped" is scanning for a removal and must not have to read an edit to
    # rule it out. `event_available` for an entry going on and `event_busy` for
    # one coming off, an opposite pair on the maintenance pair's argument;
    # `date_range` for an edit, the glyph the Service Schedule carries in the
    # sidebar, so the entry and the screen that wrote it read as one place.
    # All three were already drawn in this project's templates before this -- the
    # Patient Queue draws `event_busy`, the Patient Profile `event_available`,
    # and Community Reports `date_range` -- which is the available check that
    # the fixed font subset in static/fonts carries them.
    ACTION_SCHEDULE_ENTRY_ADDED: "event_available",
    ACTION_SCHEDULE_ENTRY_EDITED: "date_range",
    ACTION_SCHEDULE_ENTRY_DELETED: "event_busy",
    # Task 4 (H3): the health-record entries. Every glyph is already drawn in
    # this project's templates, so the fixed font subset carries it. A death
    # declaration gets a warning glyph: it is the entry a reviewer looks for.
    ACTION_PATIENT_REGISTERED: "badge",
    ACTION_PATIENT_UPDATED: "contacts",
    ACTION_PATIENT_STATUS_CHANGED: "person",
    ACTION_PATIENT_DECLARED_DECEASED: "warning",
    ACTION_PATIENT_DEATH_REVERSED: "restore",
    ACTION_CONSULTATION_RECORDED: "clinical_notes",
    ACTION_MEDICINE_DISPENSED: "pill",
    ACTION_INVENTORY_ADDED: "add",
    ACTION_INVENTORY_EDITED: "edit_note",
    ACTION_STOCK_ADJUSTED: "fact_check",
    ACTION_INVENTORY_ARCHIVED: "archive",
    ACTION_INVENTORY_RESTORED: "restart_alt",
    ACTION_PATIENT_CHECKED_IN: "event_upcoming",
    ACTION_CONSULTATION_STARTED: "play_arrow",
    ACTION_CONSULTATION_COMPLETED: "task_alt",
    ACTION_LEFT_BEFORE_SEEN: "directions_walk",
    ACTION_LEFT_UNDONE: "undo",
    ACTION_SENT_TO_DOCTOR: "stethoscope",
    ACTION_SERVICE_CHANGED: "edit",
}
_MODULE_ICONS = {
    MODULE_SMS: "campaign",
    MODULE_AUTH: "shield_person",
    # Distinct from MODULE_AUTH's shield above, because the two modules answer
    # different questions and the pill is what a reader filters on. The shield is
    # somebody presenting credentials at the door; this is somebody deciding
    # which doors exist. Only reached by an entry whose action is not one of the
    # three above -- so in practice this is the fallback that keeps a future
    # account action looking like account management rather than like an edit.
    MODULE_USERS: "manage_accounts",
    # A correction to a vaccination record. The default edit_note pencil would
    # be true but uninformative here -- these entries are the ones a reviewer
    # goes looking for, and the tab they came from is labelled with this same
    # glyph on the Patient Profile, so the two read as one place. Verified
    # present in static/fonts/material-symbols-outlined.woff2: that file is a
    # fixed subset and a ligature it does not carry renders as its own literal
    # name, and `vaccines` is already drawn on the profile's tab strip.
    MODULE_IMMUNIZATIONS: "vaccines",
    # Reached only by a future Settings action that is not one of the two above.
    # `settings` rather than either of their glyphs, so a third kind of entry
    # arrives looking like configuration rather than like a save or a download it
    # is not.
    MODULE_SETTINGS: "settings",
    # Reached only by a future confidentiality action that is not one of the four
    # above. `shield_lock` rather than any of their glyphs, so a fifth kind of
    # entry arrives looking like confidentiality rather than like one of the four
    # specific events it is not.
    MODULE_CONFIDENTIALITY: "shield_lock",
    # Reached only by a future schedule action that is not one of the three
    # above.
    MODULE_SERVICE_SCHEDULE: "date_range",
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
