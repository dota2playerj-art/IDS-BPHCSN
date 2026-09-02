"""Export Excel and Export PDF, for the four working lists -- and for one selection.

Patient Records (Screen 03), Medicine Inventory (Screen 06), Appointment
Scheduling (Screen 08) and User Management (Screen 11) each carried a disabled
Export button quoting one shared reason. This module is what all four press now.

Each export reads the same context builder the screen itself rendered from --
patient_records_context(), medicine_inventory_context(),
appointment_scheduling_context() and user_management_context() -- so a row in the
downloaded file cannot disagree with the row the operator was looking at when
they clicked. There is no SQL in this file and nothing here derives a figure the
model functions do not already derive. That is the project's "one query, every
screen" rule, applied to a file instead of a screen.

ONE ASSEMBLY, TWO FILES
-----------------------
The arrangement routes/report_export.py established and routes/audit_export.py
followed, for the third time and for the same reason: _assemble() builds one list
of sheet dictionaries and hands the identical structure to either renderer --
utils/workbook.build() writes it as .xlsx, utils/document.render() writes it as
.pdf. A value cannot read one way in the spreadsheet and another on the printout,
because there is one assembly and two renderers. The response plumbing --
_download(), and the attachment header and filename it decides -- is imported
from report_export rather than repeated, so every download this project serves is
still served in one place.

WHY FOUR SCREENS IN ONE MODULE AND NOT FOUR MODULES
---------------------------------------------------
Because the hard part is identical for all four and is worth having exactly one
copy of. Every one of these screens filters in the browser, so every one of these
files holds the whole list rather than the narrowed one, and every one of them
has to say so on its cover in words a reader will actually believe. That
paragraph, and the cover that carries it, is _cover_sheet() below. Written into
four modules it would be four copies of the most important sentence in the file,
and the copies would drift -- which is the argument utils/unavailable.py makes
about tooltips, applied to the one statement that decides whether a reader trusts
the numbers.

What differs between the four is only which rows go in and what they are called,
and that is a builder function each.

THE FULL LIST, NOT THE FILTERED ONE
-----------------------------------
This is the constraint the whole feature is shaped around, and it is not a new
one. All four screens narrow their tables in the browser: applyFilters() sets
`hidden` on the rows it excludes and the search box tests a data-search string,
so the server is never told what was typed or chosen. templates/_print.html
documents exactly this for Patient Records and resolves it by printing the DOM,
which a download cannot do -- a download is a fresh request, and the fresh request
arrives without the narrowing.

The resolutions available were three, and two of them are worse:

  * Re-implement every screen's filter server-side, so the export could honour
    it. That is a second implementation of a matching rule this project already
    has one of, for four screens, and the two copies drift the moment either is
    touched. It is also explicitly out of scope for this task.
  * Post the visible row ids up with the request. That works, and it is what a
    selection export has to do, but for a *filter* it means the file's contents
    are decided by a list of primary keys rather than by the rule that chose
    them -- unbookmarkable, and silently wrong the moment the page is stale.
  * Export the whole list and say so plainly, in the one place a reader of the
    file will see before they read a number.

The third is what Screen 12's audit export already does about its own search box,
and it is what these four do. Every cover sheet carries a "What this file covers"
block naming the controls that were not applied, by name, per screen -- Patient
Records has five, Medicine Inventory three, Appointment Scheduling five -- and
states the row count so a reader can check the file against the screen's own
footer.

AND THE ONE FILE THAT IS NOT A WHOLE LIST
-----------------------------------------
There is a sixth export here, and it breaks the rule above on purpose: Patient
Records' bulk bar downloads the records that were ticked. The second bullet
rejects deciding a file by a list of primary keys, and that rejection was about a
*filter* -- a rule that has a better representation than the ids it matched. A
selection has no rule behind it. The ids are the request rather than a stale copy
of its answer, so posting them is the only faithful thing to do with one, and the
POST that carries them is the same one Change Status already makes from the same
checkboxes.

So the two live side by side and the covers keep them apart. Five files say "the
complete list, not the filtered view" in the first row of "What this file
covers"; the sixth says "a selection, not the register" in the same row of the
same block, names the toolbar's exports as the ones that hold everything, and
states how many records were ticked beside how many were found. _cover_sheet()
takes that row as a parameter for exactly this reason -- see FULL_LIST_SCOPE.

WHAT IS DELIBERATELY IN EVERY FILE
----------------------------------
A "Not Tracked" sheet, last, exactly as report_export.py and audit_export.py put
one on theirs. A roster leaving the building is the copy where an unexplained
blank does the most damage, and each of these four screens has real absences: no
patient write is recorded in the audit trail, a stock level carries no movement
column beside it, no appointment write is recorded either, and User Management's
own UNTRACKED dict names five more. Where the screen already holds the wording -- User
Management's does -- it is quoted rather than rewritten, so the file and the
screen say the same thing in the same words.
"""
from routes.report_export import _download  # noqa: F401  (re-exported below)
from utils.dates import display_date, display_timestamp, long_date, now, today
from utils.document import LANDSCAPE, render
from utils.workbook import XLSX_MIMETYPE, build, figures, safe_filename, sheet, table

# Rendered on every cover, above the per-screen list of controls that were not
# applied. One sentence, one file, four screens -- see the module docstring for
# why it is not four sentences.
FILTER_SCOPE_NOTE = (
    "This file holds the complete list. The search box and filter controls on the "
    "screen narrow rows inside the browser, so the server is never told what was "
    "typed or chosen and a download cannot honour them. Print has the same limit "
    "and resolves it the same way. If the file should "
    "cover less, narrow it after opening it: that is what a spreadsheet is for."
)

# What "not tracked" means on these four screens, as opposed to on a report.
# Stated once at the head of every Not Tracked sheet.
UNTRACKED_INTRO = (
    "None of the following is a gap in this file. They are things nothing in the "
    "system records, so no export could contain them, and their absence here is "
    "not evidence that they did not happen."
)

# Screen 03. Every write path on this screen is unaudited, which is a fact about
# the system rather than about this file, and the file is where a reader is most
# likely to assume otherwise.
PATIENT_UNTRACKED = (
    (
        "Who changed a patient record, and when",
        "The audit trail records consultation edits, SMS broadcasts and sign-ins. "
        "It does not record registrations, edits or status changes to a patient, "
        "so this roster shows the position now with no history of how it got "
        "here.",
    ),
    (
        "Prenatal enrolment",
        "Nothing marks a patient as pregnant or stores an expected delivery "
        "date. The Prenatal Patients card on the screen reports its own absence "
        "for the same reason, and there is no column for it here.",
    ),
    (
        "Purok or zone",
        "Address is stored as one free-text line with no purok in it, so the "
        "roster cannot be grouped or filtered by area -- on the screen or in this "
        "file. Address is reproduced here exactly as it is stored.",
    ),
    (
        "That this export happened",
        "Nothing writes a row when a file is exported, so there is no history of "
        "downloads. The cover sheet names who took this copy off the system and "
        "when, and that name is the only record of it that exists.",
    ),
)

# Screen 06. The first entry here used to be "Medicine dispensing", saying that
# inventory_items holds a stock level with no per-issue history and that units
# dispensed could not be recovered -- the same absence
# routes/report_views.UNTRACKED named, worded to match it because it was one fact
# about one table.
#
# That fact changed. medicine_dispensing records every issue, and Reports &
# Analytics reports units dispensed over a range from it. So the entry could not
# stay as written; a "Not Tracked" sheet claiming an absence that has been filled
# is worse than one that says nothing, because it is the copy that leaves the
# building and it would be believed.
#
# It is corrected rather than deleted, because what it was warning the reader
# about is still true of *this file*: a stock export is a position, not a
# movement record, and restocking in particular is still not recorded as a
# movement anywhere at all.
INVENTORY_UNTRACKED = (
    (
        "Stock movement, in this file",
        "Stock dispensed at a consultation is recorded -- see Items Dispensed on "
        "Reports & Analytics, which reports units issued over a date range. This "
        "file is not that report: the Current Stock column is the shelf as it "
        "stands today, with no movement column beside it. Restocking is not "
        "recorded as a movement at all; an item's stock figure is raised by "
        "editing it through Add / Edit Medicine, which overwrites the number.",
    ),
    (
        "Who changed a stock level, and when",
        "The audit trail does not record inventory writes. An item's stock figure "
        "can be corrected through Add / Edit Medicine and nothing keeps a note of "
        "it, so this file is the position now with no history behind it. "
        "Dispensing is the one exception and is not in this file: it moves stock "
        "down through a recorded, dated row of its own.",
    ),
    (
        "Batch history",
        "A row holds one batch number and one expiry date. There is no table of "
        "earlier batches, so an item that has been restocked shows only its "
        "current one.",
    ),
    (
        "That this export happened",
        "Nothing writes a row when a file is exported, so there is no history of "
        "downloads. The cover sheet names who took this copy off the system and "
        "when, and that name is the only record of it that exists.",
    ),
)

# Screen 08.
APPOINTMENT_UNTRACKED = (
    (
        "Who booked, moved or called off an appointment",
        "The audit trail does not record appointment writes. Every row here "
        "carries the staff member it is assigned to, because that is a stored "
        "column -- but a reschedule or a cancellation overwrites the row and "
        "leaves no trace of what it held before.",
    ),
    (
        "Why an appointment was cancelled, or a patient did not attend",
        "Cancelled and No-show are statuses with no reason field behind them. The "
        "booking's notes are the operator's own text about the visit and are "
        "reproduced in full here; they are not a cancellation reason.",
    ),
    (
        "How long anybody waited",
        "Arrival time is stored when a patient is checked in, and the moment a "
        "consultation starts is not, so the queue can say who is waiting but "
        "nothing can say how long they waited before being seen.",
    ),
    (
        "That this export happened",
        "Nothing writes a row when a file is exported, so there is no history of "
        "downloads. The cover sheet names who took this copy off the system and "
        "when, and that name is the only record of it that exists.",
    ),
)

# Screen 11 is the one screen of the four that already keeps its own reasons, in
# routes/user_views.UNTRACKED. They are looked up from the context by key rather
# than restated here, so the file and the screen state them in one wording -- the
# same arrangement audit_export.STATED_UNTRACKED uses. Named explicitly rather
# than iterated so a reason added for a screen slot does not silently start
# appearing in exports.
# The "write" key is gone from that dict and so is the row that quoted it. It
# was labelled "Creating, editing and deactivating accounts" and said none of the
# three was built; two of them are, from this screen, so the label and the reason
# were both false. What is left of it is the one clause that is still true --
# editing an existing account -- under its own key and its own label.
USER_STATED_UNTRACKED = (
    ("Station and zone assignment", "assignment"),
    ("Invitation and lock-out states", "invitations"),
    ("Contact details", "contact"),
    ("Editing an existing account", "edit_account"),
    ("Password reset", "reset_password"),
)


# ---------------------------------------------------------------------------
# The ten entry points -- two formats each, for four rosters and one selection
# ---------------------------------------------------------------------------

def patient_roster_workbook(context, produced_by=""):
    """Patient Records (Screen 03) as a workbook: bytes and a filename."""
    return _workbook(_patient_export(context, produced_by))


def patient_roster_document(context, produced_by=""):
    """Patient Records (Screen 03) as a PDF document: bytes and a filename."""
    return _document(_patient_export(context, produced_by), produced_by)


def patient_selection_workbook(context, produced_by=""):
    """The ticked patient records (Screen 03's bulk bar) as a workbook."""
    return _workbook(_patient_selection_export(context, produced_by))


def patient_selection_document(context, produced_by=""):
    """The same ticked records as a PDF document: bytes and a filename."""
    return _document(_patient_selection_export(context, produced_by), produced_by)


def inventory_workbook(context, produced_by=""):
    """Medicine Inventory (Screen 06) as a workbook: bytes and a filename."""
    return _workbook(_inventory_export(context, produced_by))


def inventory_document(context, produced_by=""):
    """Medicine Inventory (Screen 06) as a PDF document: bytes and a filename."""
    return _document(_inventory_export(context, produced_by), produced_by)


def appointment_workbook(context, produced_by=""):
    """Appointment Scheduling (Screen 08) as a workbook: bytes and a filename."""
    return _workbook(_appointment_export(context, produced_by))


def appointment_document(context, produced_by=""):
    """Appointment Scheduling (Screen 08) as a PDF document: bytes and a filename."""
    return _document(_appointment_export(context, produced_by), produced_by)


def user_roster_workbook(context, produced_by=""):
    """User Management (Screen 11) as a workbook: bytes and a filename."""
    return _workbook(_user_export(context, produced_by))


def user_roster_document(context, produced_by=""):
    """User Management (Screen 11) as a PDF document: bytes and a filename."""
    return _document(_user_export(context, produced_by), produced_by)


# ---------------------------------------------------------------------------
# The two renderers, over one assembly
# ---------------------------------------------------------------------------

def _workbook(export):
    """An assembled export as .xlsx bytes and a filename."""
    return build(export["sheets"]), safe_filename(export["stem"] + ".xlsx")


def _document(export, produced_by):
    """The same assembled export as .pdf bytes and a filename.

    The renderer is handed the file's identity for the running letterhead and
    footer -- which list, over what scope, taken off by whom -- because a PDF can
    be split and a loose page still has to say what it is. The rows themselves are
    the sheets, which are the workbook's sheets.

    Landscape, unlike the two report documents, and for a reason that is visible
    the moment it is not: these are wide tables. A patient row is eight columns
    and a stock item eleven, and eight columns inside A4 portrait leaves the
    Patient ID cell narrow enough to break "PAT-016" across two lines. The report
    PDFs stay portrait because their tables are two and three columns of prose and
    figures, which is what a portrait sheet is for. utils/workbook.py sets every
    sheet it writes to landscape for exactly this reason; this is the same
    judgement, made per document because a PDF has one shape and a spreadsheet
    does not.
    """
    stamped = now()
    footer_left = f"IDS-BPHCSN · Exported {stamped.strftime('%B %d, %Y at %I:%M %p')}"
    if produced_by:
        footer_left += f" by {produced_by}"
    payload = render(
        export["sheets"],
        org="Barangay Poblacion Health Center",
        org_sub="Integrated Data System (IDS-BPHCSN)",
        doc_title=export["doc_title"],
        range_label=export["scope_label"],
        footer_left=footer_left,
        orientation=LANDSCAPE,
    )
    return payload, safe_filename(export["stem"] + ".pdf")


def _assemble(doc_title, scope_label, stem, cover, sheets, untracked):
    """One export: a cover, the screen's sheets, and a Not Tracked sheet, in order.

    The cover is always first and the Not Tracked sheet always last, on purpose
    and in both files. utils/document.render() treats the first sheet as the
    document's cover -- that is the one place it reads a sheet by position -- and a
    reader who has just been told a file is the complete list needs, in the same
    breath, to know what the list does not hold.
    """
    return {
        "doc_title": doc_title,
        "scope_label": scope_label,
        "stem": stem,
        "sheets": [cover, *[block for block in sheets if block], untracked],
    }


# ---------------------------------------------------------------------------
# The cover and the notes, shared by every export in this file
# ---------------------------------------------------------------------------

# The first line of every cover's "What this file covers" block: what decided
# which rows are in the file. Five of the six exports this module builds are the
# whole of a list and say so; the sixth is a selection and says that instead.
# Both are one row in one table on one cover, so a reader looks in the same place
# either way and cannot mistake one file for the other.
FULL_LIST_SCOPE = ("The complete list, not the filtered view", FILTER_SCOPE_NOTE)


def _cover_sheet(screen, subtitle, produced_by, detail, controls, index, intro,
                 scope=FULL_LIST_SCOPE):
    """What this file is, what it covers, and what narrowing it did not carry.

    A list of records with no provenance is the spreadsheet version of the
    unlabelled printout templates/_print.html's letterhead exists to prevent. This
    names the health center, the screen, how many rows are in the file, who took
    it off the system and when -- and then, because this is the point on which a
    reader is most likely to be misled, states in a block of its own what decided
    the file's contents, and names the controls on the screen that were not
    applied to it.

    `scope` is that statement, as a (point, meaning) pair. It defaults to the
    full-list claim every roster export makes; the selection export overrides it,
    because for that one file the default sentence would be false in every clause
    -- and a cover whose most important paragraph is wrong is worse than a file
    with no cover at all.
    """
    stamped = now()
    rows = [
        ("Screen", screen),
        ("Document", subtitle),
        *detail,
        ("Exported", stamped.strftime("%B %d, %Y at %I:%M %p")),
        ("Exported by", produced_by or "—"),
        ("Source", "Barangay Poblacion Health Center records, via IDS-BPHCSN"),
    ]

    blocks = [
        table("This export", ("Item", "Detail"), rows, empty="—"),
        table(
            "What this file covers",
            ("Point", "What it means"),
            [
                list(scope),
                *controls,
            ],
        ),
        table(
            "Sheets in this file",
            ("Sheet", "What it holds"),
            [*index,
             ["Not Tracked", "What this screen has no source for, and why."]],
        ),
    ]

    return sheet(
        "About This File",
        blocks,
        heading="Barangay Poblacion Health Center",
        intro=(
            "Integrated Data System for Barangay Poblacion Health Center "
            "Networking (IDS-BPHCSN).\n" + intro
        ),
    )


def _untracked_sheet(rows, intro):
    """What the screen has no source for, in its own words. Always last."""
    return sheet(
        "Not Tracked",
        [table(
            "What this screen does not record, and why",
            ("Not recorded", "Why"),
            [list(row) for row in rows],
            note=UNTRACKED_INTRO,
            empty="Everything this screen can show is in this file.",
        )],
        intro=intro,
    )


def _stem(screen, scope):
    """The download's filename stem: system, screen, scope, and the day taken."""
    return f"IDS-BPHCSN {screen} - {scope} - {today().isoformat()}"


def _count_label(count, singular, plural=None):
    """'1 patient' / '25 patients'. Used in headings a reader checks against."""
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _value(value):
    """A cell value, with "nothing recorded" written the one way this project writes it.

    A field the screen falls back to an em dash for can reach here as None or as
    an empty string -- _display_dosage() joins what it has and returns "" when it
    has nothing, and a stored TEXT column that was never filled comes back as "".
    Both renderers already turn None into the shared MISSING em dash and neither
    turns "" into anything, so an untouched empty string would print as a blank
    cell in the file beside an em dash on the screen. Folded here, once, rather
    than at each of the thirty-odd call sites that could hit it.
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


# ---------------------------------------------------------------------------
# Screen 03 -- Patient Records
# ---------------------------------------------------------------------------

# The roster's columns, in the order Screen 03's table has them. One tuple, so the
# .xlsx and the .pdf cannot grow different ideas of what a patient row is, and so
# a column cannot be added to one file and forgotten in the other.
PATIENT_COLUMNS = (
    "Patient ID",
    "Full Name",
    "Age",
    "Sex",
    "Address",
    "Contact Number",
    "Last Visit",
    "Status",
)


# What a patient row means, stated wherever one is tabulated. Both patient
# exports write the same eight columns from the same records, so they say the
# same thing about them -- the argument _cover_sheet() makes about the scope
# note, applied to the columns underneath it.
PATIENT_ROW_NOTE = (
    "Sorted by surname, A–Z, the order the Patient Records table states in its "
    "footer. Age is the age today, computed from the stored birth date; Last "
    "Visit is the most recent recorded consultation, not a stored field."
)


def _patient_rows(patients):
    """Patient records as PATIENT_COLUMNS rows.

    One function, because the full roster and a ticked selection are the same
    eight columns read off the same dictionaries. Two copies of this would be two
    chances for a column to be added to one file and forgotten in the other,
    which is the reason PATIENT_COLUMNS is a single tuple in the first place.
    """
    return [
        [
            _value(patient.get("patient_id")),
            _value(patient.get("full_name")),
            # The display string, which is what the screen's Age column holds --
            # "8 months" for an infant, not 0. models/patients.py keeps the number
            # separately as age_years for anything that compares rather than
            # prints.
            _value(patient.get("age")),
            _value(patient.get("sex")),
            _value(patient.get("display_address")),
            _value(patient.get("contact_number")),
            display_date(patient.get("last_visit"), "No visits yet"),
            _value(patient.get("status")),
        ]
        for patient in patients
    ]


def _patient_export(context, produced_by):
    """Screen 03 as a cover, the roster, its four figures, and the notes."""
    patients = context["patients"]
    stats = context["stats"]
    total = len(patients)

    rows = _patient_rows(patients)

    roster = sheet(
        "Patient Roster",
        [table(
            f"Every registered patient — {_count_label(total, 'record')}",
            PATIENT_COLUMNS,
            rows,
            note=PATIENT_ROW_NOTE,
            empty="No patients are registered.",
        )],
        heading="Patient Roster",
        intro=(
            f"{_count_label(total, 'patient')} on the register as of "
            f"{long_date(today())}. Every registered patient is here whatever "
            "their status — Inactive and Deceased records are listed under that "
            "status rather than left out, exactly as the screen lists them."
        ),
    )

    summary = sheet(
        "Roster Summary",
        [figures(
            "The figures on the Patient Records stat cards",
            [
                ("Total registered patients", stats["total_patients"],
                 "Every record, whatever its status"),
                ("Registered this month", stats["new_this_month"],
                 f"Clinic-local calendar month to {display_date(today())}"),
                ("Registered in the last 30 days", stats["new_last_30_days"],
                 f"Against {stats['previous_30_days']} in the 30 days before that"),
                ("Senior citizen patients", stats["senior_count"],
                 f"{stats['senior_share_pct']}% of the register, aged 60 and over "
                 "today"),
                ("Prenatal patients", None,
                 "Not tracked — see the Not Tracked sheet"),
            ],
            note=("Counted over the whole register, not over any narrowing done "
                  "on the screen. These are the same figures the four cards above "
                  "the table show, read from the same call."),
        )],
        heading="Roster Summary",
    )

    cover = _cover_sheet(
        "Patient Records",
        "Full patient roster",
        produced_by,
        detail=[("Patients in this file", total)],
        controls=[[
            "The controls that were not applied",
            "The search box, and the Advanced Filter panel's age range, sex, "
            "status and last-visit controls. All five narrow the table in the "
            "browser only.",
        ]],
        index=[
            ["Patient Roster", "Every registered patient, surname order."],
            ["Roster Summary", "The four figures the screen's stat cards show."],
        ],
        intro=(
            "The complete patient register, taken off the system on "
            f"{now().strftime('%B %d, %Y')}. It is a snapshot of the position "
            "today, not a record of a period."
        ),
    )

    notes = _untracked_sheet(
        PATIENT_UNTRACKED,
        "The roster is complete for what the system stores about a patient's "
        "identity, contact and status. It is not a medical record — a patient's "
        "consultations, immunisations and appointments are on their own profile "
        "screen — and the following are not stored at all.",
    )

    return _assemble(
        "Patient Records — Full Roster",
        f"Complete register · {_count_label(total, 'patient')}",
        _stem("Patient Records", "Full roster"),
        cover,
        [roster, summary],
        notes,
    )


# ---------------------------------------------------------------------------
# Screen 03 -- the bulk bar's selection
# ---------------------------------------------------------------------------

# WHY THIS EXPORT EXISTS BESIDE THE ROSTER ONE
# --------------------------------------------
# The module docstring above argues that a *filter* must not decide a file's
# contents through a list of primary keys, and that argument still stands. A
# selection is the opposite case, and the difference is the whole justification
# for this builder.
#
# A filter is a rule -- "everyone over 60" -- and the honest way to carry a rule
# to the server is to send the rule. Sending the ids it happened to match instead
# is a copy of the answer that goes stale the moment the register changes, which
# is why the roster export refuses to do it and says so on its cover.
#
# A selection is not a rule. It is a set of records a person picked one at a time
# and there is nothing else it could be sent as: "the four patients due for
# follow-up that the desk ticked on Tuesday" has no query behind it. The ids ARE
# the request, so posting them is exact rather than approximate, and the file is
# complete by definition -- it holds every record that was asked for, or names on
# its cover the ones that had gone.
#
# What it costs is the property the roster exports keep: the request is not a
# bookmarkable URL, because there is nothing stable to bookmark. That is stated
# on the cover rather than glossed, in the same block the roster exports use to
# say they hold the whole list.

# The one thing this file cannot tell a reader, and one the roster export's notes
# do not cover: why these records and not others. It goes first on the Not
# Tracked sheet, ahead of the four the roster shares, because it is the question
# somebody holding a list of eleven patients will actually ask.
SELECTION_UNTRACKED = (
    (
        "Why these records were selected",
        "The selection was made by ticking rows on Patient Records and nothing "
        "stores "
        "it. There is no saved cohort, no shared list and no reason field behind "
        "it, so this file is a snapshot of one operator's choice at one moment "
        "and cannot be reproduced from the system afterwards. If the grounds "
        "matter -- follow-up due, a campaign, a barangay request -- they have to "
        "be written down beside the file.",
    ),
    *PATIENT_UNTRACKED,
)


def _patient_selection_export(context, produced_by):
    """The ticked records as a cover, one sheet of rows, and the notes.

    Deliberately three sheets rather than the roster export's four: there is no
    Roster Summary here. Those four figures are counts over the whole register --
    total registered, new this month, new in 30 days, senior share -- and not one
    of them is a fact about a selection. Reproducing them beside eleven rows
    would put "Total registered patients: 118" on a file that holds eleven, which
    is the single most likely way a reader of this file could be misled. The
    register's size is on the cover instead, where it reads as context for the
    selection rather than as a figure about it.

    Everything else is the roster export's, unchanged: the same eight columns
    from _patient_rows(), the same note under them, the same cover builder, the
    same Not Tracked sheet and the same two renderers.
    """
    patients = context["patients"]
    total = len(patients)
    requested = context["requested"]
    registered = context["total_registered"]

    # Selected on a page that has since gone stale. Nothing in this system
    # deletes a patient, so this is close to unreachable -- but "close to" is not
    # "never", and a file quietly holding four rows for a five-record selection
    # is exactly what a cover sheet is for.
    missing = requested - total

    listing = sheet(
        "Selected Patients",
        [table(
            f"The records selected on Patient Records — {_count_label(total, 'record')}",
            PATIENT_COLUMNS,
            _patient_rows(patients),
            note=PATIENT_ROW_NOTE,
            empty="No selected record could be found.",
        )],
        heading="Selected Patients",
        intro=(
            f"{_count_label(total, 'patient')} selected from the "
            f"{_count_label(registered, 'patient')} on the register, as of "
            f"{long_date(today())}. These are the records that were ticked on "
            "Patient Records and no others; a patient missing from this list was not "
            "selected, rather than filtered out."
        ),
    )

    detail = [
        ("Patients in this file", total),
        ("Selected on screen", requested),
        ("On the register at the time", registered),
    ]
    if missing:
        detail.append((
            "Selected but not found",
            f"{missing} — see 'What this file covers'",
        ))

    controls = [[
        "It is a selection, so no filter applies to it",
        "The search box and the Advanced Filter panel decide which rows are on "
        "screen to be ticked, and this file is the ticked rows. Whatever was "
        "typed or chosen before the selection was made is therefore already "
        "reflected in it; it is neither applied again here nor recorded "
        "anywhere, so this file cannot say what was on screen at the time.",
    ]]
    if missing:
        controls.append([
            "Some selected records were not found",
            f"{requested} records were selected and {total} were found, so "
            f"{missing} could not be included: the register has no row for them. "
            "Retiring a patient does not do this -- an Inactive or Deceased "
            "record is still on the roster and would still be in this file -- so "
            "reload Patient Records and select again if the full set is needed.",
        ])

    cover = _cover_sheet(
        "Patient Records",
        "Selected patients",
        produced_by,
        detail=detail,
        scope=(
            "A selection, not the register",
            "This file holds only the patient records that were ticked on Patient "
            "Records before Export was pressed. It is NOT the full roster -- the "
            "toolbar's own Export Excel and Export PDF are, and they download "
            "every registered patient. It is not the result of a saved search "
            "either: the selection was made by hand, one row at a time, and "
            "nothing stores it, so this file cannot be regenerated by re-running "
            "anything. The count above is the whole of what is here.",
        ),
        controls=controls,
        index=[
            ["Selected Patients", "The ticked records, surname order."],
        ],
        intro=(
            f"{_count_label(total, 'selected patient record')}, taken off the "
            f"system on {now().strftime('%B %d, %Y')}. It is a snapshot of those "
            "records as they stand today, not a record of a period, and not the "
            "register."
        ),
    )

    notes = _untracked_sheet(
        SELECTION_UNTRACKED,
        "These records are complete for what the system stores about a patient's "
        "identity, contact and status -- the same eight columns the full roster "
        "export carries. They are not medical records: a patient's "
        "consultations, immunisations and appointments are on their own profile "
        "screen. The following are not stored at all.",
    )

    return _assemble(
        "Patient Records — Selected Patients",
        f"Selection · {_count_label(total, 'patient')} of {registered} registered",
        _stem("Patient Records", f"Selected patients ({total})"),
        cover,
        [listing],
        notes,
    )


# ---------------------------------------------------------------------------
# Screen 06 -- Medicine Inventory
# ---------------------------------------------------------------------------

# Screen 06's columns, plus the two the screen renders as a second line inside a
# cell rather than as columns of their own: the generic name under the item name,
# and the stock condition printed under "Retired" on a retired row. A spreadsheet
# has no second line, so they become columns. Nothing is added that the screen
# does not show, and nothing it shows is dropped.
INVENTORY_COLUMNS = (
    "Medicine Name",
    "Generic Name",
    "Category",
    "Dosage / Form",
    "Current Stock",
    "Unit",
    "Reorder Level",
    "Expiration Date",
    "Supplier",
    "Status",
    "Stock condition",
)


def _inventory_export(context, produced_by):
    """Screen 06 as a cover, the item list, its four figures, and the notes."""
    items = context["items"]
    stats = context["stats"]
    total = len(items)
    retired = stats["retired_count"]

    rows = [
        [
            _value(item.get("name")),
            _value(item.get("generic_name")),
            _value(item.get("drug_class") or item.get("category")),
            _value(item.get("display_dosage")),
            _value(item.get("stock_quantity")),
            _value(item.get("unit")),
            _value(item.get("low_stock_threshold")),
            display_date(item.get("expiry_date"), "No expiry"),
            _value(item.get("supplier")),
            # What the screen's Status cell prints: "Retired" for an item taken out
            # of service, and the stock condition otherwise. The lifecycle status
            # replaces the stock condition in that cell rather than sitting beside
            # it -- see models/inventory.py -- so the stock condition gets a column
            # of its own here instead of being lost.
            _value(item.get("display_status")),
            _value(item.get("stock_status")),
        ]
        for item in items
    ]

    listing = sheet(
        "Inventory",
        [table(
            f"Every item on the shelf — {_count_label(total, 'item')}",
            INVENTORY_COLUMNS,
            rows,
            note=("Sorted by medicine name, A–Z, the order the Medicine Inventory table "
                  "states in its own footer. Status is what the screen's badge "
                  "shows: the item's lifecycle status where it has been retired, "
                  "and its stock condition otherwise. Stock condition is always "
                  "the stock condition, so a retired item still reports whether "
                  "it is short or expired — which is why the two columns read the "
                  "same on every item that is still in service. They are kept "
                  "apart rather than merged because a column that means one thing "
                  "on every row can be sorted and filtered, and one that changes "
                  "meaning halfway down cannot."),
            empty="The inventory holds nothing.",
        )],
        heading="Medicine Inventory",
        intro=(
            f"{_count_label(total, 'item')} on the shelf as of "
            f"{long_date(today())}"
            + (f", of which {retired} {'is' if retired == 1 else 'are'} retired."
               if retired else ".")
            + " Retired items are listed here rather than left out, under that "
            "status, exactly as the screen lists them — but they are counted in "
            "none of the figures on the next sheet, because an item nobody is "
            "restocking is not short of stock in any sense that asks somebody to "
            "reorder it."
        ),
    )

    summary = sheet(
        "Stock Summary",
        [figures(
            "The figures on the Medicine Inventory stat cards",
            [
                ("Items in service", stats["total_items"],
                 f"{stats['medicine_count']} medicines, "
                 f"{stats['total_items'] - stats['medicine_count']} supply and "
                 "equipment. Retired items excluded"),
                ("Retired items", retired,
                 "Listed on the sheet before this one, counted in none of these "
                 "figures"),
                ("Items below reorder level", stats["low_stock_count"],
                 f"Of which {stats['out_of_stock_count']} at zero stock"),
                (f"Near expiry (within {stats['near_expiry_days']} days)",
                 stats["near_expiry_count"],
                 f"Of which {stats['expires_today_count']} "
                 f"{'expires' if stats['expires_today_count'] == 1 else 'expire'} "
                 "today"),
                ("Already expired", stats["expired_count"],
                 f"On the shelf and past their expiry date on "
                 f"{display_date(today())}"),
            ],
            note=("The position today, over the whole shelf, not over any "
                  "narrowing done on the screen. These are the same figures the "
                  "four cards above the table show, read from the same call — and "
                  "the same low-stock count the sidebar badge and both dashboards "
                  "report."),
        )],
        heading="Stock Summary",
    )

    cover = _cover_sheet(
        "Medicine Inventory",
        "Full inventory list",
        produced_by,
        detail=[
            ("Items in this file", total),
            ("Of which retired", retired),
        ],
        controls=[[
            "The controls that were not applied",
            "The search box, and the Advanced Filter panel's category, stock "
            "status and expiry-date controls. All three narrow the table in the "
            "browser only.",
        ]],
        index=[
            ["Inventory", "Every stock item, name order, retired items included."],
            ["Stock Summary", "The figures the screen's stat cards show."],
        ],
        intro=(
            "The complete inventory list, taken off the system on "
            f"{now().strftime('%B %d, %Y')}. Stock levels and expiry judgements "
            "are the position today, not a record of a period."
        ),
    )

    notes = _untracked_sheet(
        INVENTORY_UNTRACKED,
        "The list is complete for what the screen shows about an item as it stands "
        "today. Eight further stored fields — item code, brand name, date received, "
        "batch number, manufacturer, unit cost, storage location and notes — appear "
        "nowhere except the Add / Edit Medicine form, and so are not in this file "
        "either: it holds the columns the screen holds. The following are not "
        "stored at all.",
    )

    return _assemble(
        "Medicine Inventory — Full Item List",
        f"Complete shelf · {_count_label(total, 'item')}",
        _stem("Medicine Inventory", "Full item list"),
        cover,
        [listing, summary],
        notes,
    )


# ---------------------------------------------------------------------------
# Screen 08 -- Appointment Scheduling
# ---------------------------------------------------------------------------

QUEUE_COLUMNS = (
    "#",
    "Appointment ID",
    "Patient",
    "Patient ID",
    "Service / Reason",
    "Notes",
    "Arrived",
    "Booked for",
    "Status",
    "Assigned to",
)

UPCOMING_COLUMNS = (
    "Appointment ID",
    "Patient",
    "Patient ID",
    "Service / Reason",
    "Notes",
    "Date",
    "Day",
    "Time",
    "Assigned to",
    "Status",
)

CALENDAR_COLUMNS = (
    "Date",
    "Day",
    "Booked",
    "Still to happen",
    "In the queue",
    "Completed",
    "Cancelled or no-show",
)


def _patient_name(entry):
    """The queue's own rendering of a patient's name, first and last."""
    parts = [entry.get("first_name"), entry.get("last_name")]
    return " ".join(str(part).strip() for part in parts if part)


def _appointment_export(context, produced_by):
    """Screen 08 as a cover, its three panels, its figures, and the notes.

    WHAT "THE FULL LIST" MEANS ON THIS SCREEN
    -----------------------------------------
    Screen 08 is not one table. It shows three lists by default and they answer
    three different questions: today's queue (who is here now), the calendar
    (which days carry what load), and upcoming bookings (who is expected, and
    when). The template says outright why the first and third are not merged -- a
    booking for next Tuesday has no arrival time, no queue position and no action
    available -- so a file holding only one of them would be an export of a third
    of the screen.

    All three are in the file, on sheets of their own, in the order the screen has
    them, and the cover names each one's scope. The queue is today only, because
    that is what a queue is. Upcoming is every pending booking after today, which
    is the whole of what that panel lists rather than the five the reminder strip
    above it shows. And the calendar sheet is the month the screen's calendar was
    showing, day by day -- the one part of this file a control on the screen does
    change, because ?month= is a real server-side parameter and the export route
    reads the same one the screen's arrows submit.
    """
    queue = context["queue"]
    queue_stats = context["queue_stats"]
    upcoming = context["upcoming"]
    upcoming_stats = context["upcoming_stats"]
    calendar = context["calendar"]
    queue_date = context["queue_date"]

    queue_rows = [
        [
            _value(entry.get("line_position")),
            _value(entry.get("reference")),
            _value(_patient_name(entry)),
            _value(entry.get("patient_reference")),
            _value(entry.get("appointment_type") or "Consultation"),
            _value(entry.get("notes")),
            _value(entry.get("arrival_time")),
            _value(entry.get("booked_time")),
            _value(entry.get("display_status")),
            _value(entry.get("assigned_staff")),
        ]
        for entry in queue
    ]

    queue_sheet = sheet(
        "Today's Queue",
        [table(
            f"{display_date(queue_date)} — {_count_label(len(queue), 'patient')}",
            QUEUE_COLUMNS,
            queue_rows,
            note=("In arrival order, patients in consultation first — the order "
                  "the screen states above its table. The # column is the place in "
                  "the waiting line, and is blank for anyone already seen or not "
                  "yet arrived. Status is what the screen's badge prints, so the "
                  "patient who may be brought in now reads 'Ready' rather than "
                  "'Waiting'."),
            empty="Nobody is booked for today and nobody has checked in.",
        )],
        heading=f"Today's Queue — {long_date(queue_date)}",
        intro=(
            "Everyone booked for today or checked in today, whatever has since "
            "happened to them: completed and cancelled rows stay on the queue for "
            "the rest of the day, exactly as they do on the screen."
        ),
    )

    upcoming_rows = [
        [
            _value(entry.get("reference")),
            _value(_patient_name(entry)),
            _value(entry.get("patient_reference")),
            _value(entry.get("appointment_type") or "Consultation"),
            _value(entry.get("notes")),
            display_date(entry.get("appointment_date")),
            _value(entry.get("when_label")),
            _value(entry.get("booked_time")),
            _value(entry.get("assigned_staff")),
            _value(entry.get("status")),
        ]
        for entry in upcoming
    ]

    upcoming_sheet = sheet(
        "Upcoming",
        [table(
            f"Booked after today — {_count_label(len(upcoming), 'appointment')}",
            UPCOMING_COLUMNS,
            upcoming_rows,
            note=("Soonest first. Every pending booking dated after today, not the "
                  "five the reminder strip on the screen shows. Anything dated "
                  "today is on the previous sheet instead, so no appointment "
                  "appears twice in this file."),
            empty="Nothing is booked beyond today.",
        )],
        heading="Upcoming Appointments",
        intro=(
            "Future bookings, kept apart from today's queue for the reason the "
            "screen keeps them apart: a booking for next week has no arrival time, "
            "no queue position and no action available except waiting for the day."
        ),
    )

    calendar_rows = [
        [
            display_date(cell["date"]),
            cell["date"].strftime("%A"),
            cell["total"],
            cell["pending"],
            cell["in_queue"],
            cell["completed"],
            cell["cancelled"],
        ]
        for week in calendar["weeks"]
        for cell in week
        if cell["in_month"] and cell["total"]
    ]

    calendar_sheet = sheet(
        "Calendar",
        [table(
            f"{calendar['label']} — "
            f"{_count_label(calendar['month_total'], 'appointment')}",
            CALENDAR_COLUMNS,
            calendar_rows,
            note=("One row per day that has something booked; days with nothing on "
                  "them are left out rather than listed as zeroes. The four count "
                  "columns are the buckets the screen's calendar legend uses, and "
                  "they add up to Booked."),
            empty=f"Nothing is booked in {calendar['label']}.",
        )],
        heading=f"Calendar — {calendar['label']}",
        intro=(
            "The month the screen's calendar panel was showing when this file was "
            "taken, day by day. This is the one part of the file a control on the "
            "screen does change: the calendar's month arrows are a real "
            "server-side parameter, so the month exported is the month displayed."
        ),
    )

    summary = sheet(
        "Summary",
        [figures(
            "The figures on the Appointment Scheduling stat cards and panel headers",
            [
                ("Appointments today", queue_stats["total_today"],
                 f"{queue_stats['walk_ins']} walk-in"
                 f"{'' if queue_stats['walk_ins'] == 1 else 's'}"),
                ("In the waiting room", queue_stats["waiting"],
                 f"{queue_stats['ready']} ready to be seen, "
                 f"{queue_stats['still_waiting']} still waiting"),
                # The room, not this day's rows -- see get_queue_stats(). When
                # the visit holding it was started on another day the note says
                # so, rather than letting a report headed with today's date
                # imply the patient it names arrived today.
                ("In consultation now", queue_stats["in_consultation"],
                 (f"{queue_stats['active_name']} — started "
                  f"{display_date(queue_stats['active_date'])} and still open"
                  if queue_stats["active_is_stale"]
                  else queue_stats["active_name"] or "The clinician is free")),
                ("Completed today", queue_stats["completed"],
                 f"Of the {queue_stats['total_today']} booked or checked in today"),
                ("Booked but not yet arrived", queue_stats["not_arrived"],
                 f"Still expected on {display_date(queue_date)}"),
                ("Upcoming appointments", upcoming_stats["total"],
                 "Across "
                 f"{_count_label(upcoming_stats['days_with_bookings'], 'day')}, "
                 f"{upcoming_stats['next_seven_days']} inside the next 7 days"),
                (f"Booked in {calendar['label']}", calendar["month_total"],
                 f"Of which {calendar['month_pending']} have still to happen"),
            ],
            note=("The queue figures are today's, at the health center; the "
                  "upcoming figures cover every pending booking after today; the "
                  "month figure covers the calendar month on the sheet before this "
                  "one. Each row says which."),
        )],
        heading="Summary",
    )

    cover = _cover_sheet(
        "Appointment Scheduling",
        "Today's queue, upcoming bookings and the calendar month",
        produced_by,
        detail=[
            ("Queue date", long_date(queue_date)),
            ("In today's queue", len(queue)),
            ("Upcoming after today", len(upcoming)),
            ("Calendar month", calendar["label"]),
        ],
        controls=[
            [
                "The controls that were not applied",
                "The queue's search box and its Advanced Filter service and status "
                "controls, and the Upcoming panel's own search box and day chip. "
                "All five narrow their tables in the browser only.",
            ],
            [
                "The one control that was carried",
                "The calendar's month. It is a real server-side parameter — the "
                "screen's arrows submit it as ?month= and this export reads the "
                "same one — so the Calendar sheet holds the month that was on "
                "screen rather than always the current one.",
            ],
        ],
        index=[
            ["Today's Queue",
             "Everyone booked for or checked in today, in queue order."],
            ["Upcoming", "Every pending booking dated after today, soonest first."],
            ["Calendar", "The calendar month's load, one row per day with bookings."],
            ["Summary", "The figures the screen's stat cards and headers show."],
        ],
        intro=(
            "Appointment Scheduling shows three lists side by side, and all "
            "three are in this file on sheets of their own. Taken off the system on "
            f"{now().strftime('%B %d, %Y')}."
        ),
    )

    notes = _untracked_sheet(
        APPOINTMENT_UNTRACKED,
        "The three lists are complete for what the system stores about a booking as "
        "it stands. An appointment row is overwritten in place as it moves through "
        "its statuses, so what this file holds is where every booking stands now. "
        "The following are not stored at all.",
    )

    return _assemble(
        "Appointment Scheduling — Queue, Upcoming and Calendar",
        (f"{display_date(queue_date)} queue · {len(upcoming)} upcoming · "
         f"{calendar['label']}"),
        _stem("Appointment Scheduling", "Queue and upcoming"),
        cover,
        [queue_sheet, upcoming_sheet, calendar_sheet, summary],
        notes,
    )


# ---------------------------------------------------------------------------
# Screen 11 -- User Management
# ---------------------------------------------------------------------------

USER_COLUMNS = (
    "Username",
    "Full Name",
    "Role",
    "Status",
    "Contact",
    "Account Created",
    "Last Login",
)

ACCESS_COLUMNS = ("Account", "Role", "Screen")


def _user_export(context, produced_by):
    """Screen 11 as a cover, the roster, the access each role carries, and notes.

    WHY THE ACCESS SHEET IS IN IT
    -----------------------------
    Because it is the half of this screen a roster alone would lose. Screen 11's
    right-hand panel lists, for the selected account, every screen that account's
    role can open -- and that list is not a description kept in step by hand. It is
    read at request time off the role_required() guards themselves
    (routes/user_views.py::accessible_screens), so it is the access rule rather
    than a copy of it. A roster naming accounts with no statement of what those
    accounts can reach would be the least useful possible export of an
    access-control screen, and this is the one place the rule can be read whole.

    It matters more now than when it was written. The roster was three fixed
    accounts then; User Management creates them, so this file is also the record
    of how many ways into the system exist and what each of them opens.
    """
    users = context["users"]
    untracked = context["untracked"]
    total = context["total_users"]

    rows = [
        [
            _value(user.get("username")),
            _value(user.get("full_name")),
            _value(user.get("role")),
            "Active" if user.get("is_active") else "Deactivated",
            _value(user.get("contact")),
            display_timestamp(user.get("created_at")),
            user.get("last_login_display") or "Never signed in",
        ]
        for user in users
    ]

    roster = sheet(
        "System Accounts",
        [table(
            f"Every account that can sign in — {_count_label(total, 'account')}",
            USER_COLUMNS,
            rows,
            note=("Ordered by role then name, the order the screen lists them in. "
                  "Contact is blank for every account because nothing in the "
                  "application writes the email or phone column. Last Login is the "
                  "most recent successful sign-in in the audit trail, not a stored "
                  "column — an account with none has never been signed into, and "
                  "says so rather than showing a date. Both timestamps are "
                  "clinic-local, converted from the stored UTC the same way every "
                  "screen converts them."),
            empty="No accounts exist.",
        )],
        heading="System Accounts",
        intro=(
            f"{_count_label(total, 'account')} — {context['active_users']} active, "
            f"{context['inactive_users']} deactivated — across "
            f"{_count_label(context['roles_represented'], 'role')}. This is the "
            "complete list: the accounts are set up by the system itself, one for "
            "each role the database allows, and nothing on the screen creates "
            "another. A deactivated account is refused at the login form even when "
            "the password presented is correct, and the refusal is recorded in the "
            "audit trail."
        ),
    )

    access_rows = [
        [user.get("full_name"), user.get("role"), screen]
        for user in users
        for screen in user.get("screens") or []
    ]

    access = sheet(
        "Access By Account",
        [table(
            "Which screens each account's role can open",
            ACCESS_COLUMNS,
            access_rows,
            note=("Read at export time from the access rule each screen enforces, "
                  "so this is the access rule that is enforced rather than a "
                  "description of it kept in step by hand. An account appears once "
                  "per screen its role admits it to."),
            empty="No screen is role-restricted.",
        )],
        heading="Access By Account",
        intro=(
            "The permissions panel on the right of User Management, for every account at "
            "once. A screen absent from an account's rows is a screen that "
            "account's role is refused."
        ),
    )

    summary = sheet(
        "Account Summary",
        [figures(
            "The figures on the User Management stat cards",
            [
                ("Total accounts", total,
                 f"Across {_count_label(context['roles_represented'], 'role')}"),
                ("Active accounts", context["active_users"],
                 f"{context['active_users']} of {total} can sign in"),
                ("Deactivated accounts", context["inactive_users"],
                 "Refused at the login form, and the refusal recorded"),
                (f"Signed in within {context['recent_sign_in_days']} days",
                 context["recent_sign_ins"],
                 f"{context['accounts_ever_signed_in']} of {total} have ever "
                 "signed in. Counted from the audit trail"),
            ],
            note=("The same figures the four cards above the table show, read from "
                  "the same source. The sign-in counts are the rows the Audit Logs "
                  "Login Events card counts, so the two cannot disagree."),
        )],
        heading="Account Summary",
    )

    cover = _cover_sheet(
        "User Management",
        "All system accounts and the access each one carries",
        produced_by,
        detail=[
            ("Accounts in this file", total),
            ("Active", context["active_users"]),
            ("Deactivated", context["inactive_users"]),
        ],
        # "with three accounts on one page" was true of a system that could not
        # create a fourth. User Management creates accounts now, so the count is
        # read from the roster this file was built from rather than asserted --
        # a sentence that names a number the screen can change is a sentence
        # that goes false the first time somebody uses the feature.
        controls=[[
            "There is nothing on this screen to narrow",
            "User Management has no search box and no filter panel — every "
            f"account is on one page ({_count_label(total, 'account')} today), so "
            "there is nothing to narrow, and the screen says so. This "
            "file is the complete roster for the same reason the screen is: it is "
            "all there is.",
        ]],
        index=[
            ["System Accounts",
             "Every account that can sign in, by role then name."],
            ["Access By Account", "Which screens each account's role can open."],
            ["Account Summary", "The figures the screen's stat cards show."],
        ],
        intro=(
            "Every account that can sign in to IDS-BPHCSN, with the role and the "
            "access each one carries, taken off the system on "
            f"{now().strftime('%B %d, %Y')}. This file names accounts and their "
            "privileges; no password is in it, and none can be — this file never "
            "reads one."
        ),
    )

    notes = _untracked_sheet(
        [
            [label, untracked[key]]
            for label, key in USER_STATED_UNTRACKED
            if key in untracked
        ] + [[
            "That this export happened",
            "Nothing writes a row when a file is exported, so there is no history "
            "of downloads — not even of this one, which lists every account on the "
            "system. The cover sheet names who took it off and when, and that name "
            "is the only record of it that exists.",
        ]],
        "The roster is complete for everything held about an account. The reasons "
        "below are the screen's own, quoted word for word so this file and "
        "User Management state them in one wording.",
    )

    return _assemble(
        "User Management — System Accounts",
        f"All accounts · {_count_label(total, 'account')}",
        _stem("User Management", "All accounts"),
        cover,
        [roster, access, summary],
        notes,
    )


# Re-exported so each route imports its response helpers from the module it is
# exporting, the way the report and audit routes do. The plumbing itself stays
# single -- one place decides the attachment header and the download name.
from routes.report_export import (  # noqa: E402
    PDF_MIMETYPE,
    excel_response,
    exported_by,
    pdf_response,
)

__all__ = [
    "appointment_document",
    "appointment_workbook",
    "excel_response",
    "exported_by",
    "inventory_document",
    "inventory_workbook",
    "patient_roster_document",
    "patient_roster_workbook",
    "patient_selection_document",
    "patient_selection_workbook",
    "pdf_response",
    "user_roster_document",
    "user_roster_workbook",
    "PDF_MIMETYPE",
    "XLSX_MIMETYPE",
]
