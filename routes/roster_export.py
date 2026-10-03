"""Export Excel and Export PDF, for the four working lists -- and for one selection.

Patient Records (Screen 03), Medicine Inventory (Screen 06), Appointment
Scheduling (Screen 08) and User Management (Screen 11) each carried a disabled
Export button quoting one shared reason. This module is what all four press now.
"""
import config
from models.consultations import RESTRICTED_PLACEHOLDER
from models.settings import health_center_name
from routes.report_export import _download  # noqa: F401  (re-exported below)
from utils.dates import display_date, display_timestamp, long_date, now, today
from utils.document import LANDSCAPE, render
from utils.workbook import XLSX_MIMETYPE, build, figures, safe_filename, sheet, table

# Rendered on every cover, above the per-screen list of controls that were not
# applied. One sentence, one file, four screens -- see the module docstring for
# why it is not four sentences.
FILTER_SCOPE_NOTE = (
    "This file holds the complete list. The search box and filters work in the browser only, so "
    "this download cannot follow them. Narrow it in the spreadsheet."
)

# What "not tracked" means on these four screens, as opposed to on a report.
# Stated once at the head of every Not Tracked sheet.
UNTRACKED_INTRO = (
    "None of these is a gap in this file. The system does not record them, so no export can "
    "contain them."
)

# Screen 03. Registration, edits and status changes to a patient are recorded in
# the audit trail (Task 4, H3); the entry that said otherwise is removed. What is
# still genuinely absent from the system is listed below.
PATIENT_UNTRACKED = (
    (
        "Prenatal enrolment",
        "Pregnancy is not recorded, so this file has no prenatal column.",
    ),
    (
        "Purok or zone",
        "Address is one free-text line, so the roster cannot be grouped by area. It is shown as "
        "stored.",
    ),
    (
        "That this export happened",
        "Exports are not recorded. The cover sheet names who took this copy and when.",
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
#
# "Who changed a stock level, and when" is removed outright, not corrected: Task
# 4 (H3) added an audit entry to every inventory write -- add, edit, stock
# adjustment, archive and restore -- so the absence it named no longer exists.
INVENTORY_UNTRACKED = (
    (
        "Stock movement, in this file",
        "Dispensing is recorded; see Items Dispensed on Reports & Analytics. This file shows the "
        "shelf as it is today, with no movement column.",
    ),
    (
        "Batch history",
        "A row holds one batch number and one expiry date. There is no table of "
        "earlier batches, so an item that has been restocked shows only its "
        "current one.",
    ),
    (
        "That this export happened",
        "Exports are not recorded. The cover sheet names who took this copy and when.",
    ),
)

# Screen 08. Rewritten on 2026-09-05, when advance booking was retired: two of
# the four reasons here were about booking writes that no longer happen, and a
# file that keeps explaining what it does not record about a feature the system
# does not have is exactly the drift utils/unavailable.py exists to prevent.
# What replaced them is not filler -- the removal made one genuinely new gap, and
# it is named here as well as on the screen.
#
# "Who checked a patient in" is removed in turn: Task 4 (H3) added an audit entry
# for check-in, for starting a consultation and for completing one, so the queue
# writes this row used to say nothing recorded are recorded now.
APPOINTMENT_UNTRACKED = (
    (
        "How long anybody waited",
        "Arrival time is stored, but the time a consultation starts is not, so waiting time "
        "cannot be counted.",
    ),
    (
        "That this export happened",
        "Exports are not recorded. The cover sheet names who took this copy and when.",
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
# three was built; two of them were, from this screen, so the label and the
# reason were both false.
#
# Its two successors have now gone the same way, for the same reason and one step
# further on. "Editing an existing account" and "Password reset" quoted the
# `edit_account` and `reset_password` reasons, and both of those said the feature
# did not exist. Both exist -- Edit User changes a full name and a role, Reset
# Password sets a new one -- so the reasons were deleted from the screen and
# these two rows go with them.
#
# The rows are removed rather than left to be dropped by the `if key in
# untracked` filter further down. That filter would have made this file quietly
# correct while this tuple went on naming two absences the system does not have,
# and the next person to read it would have believed the tuple.
#
# What replaced those reasons is not an absence at all. A username cannot be
# changed and a stored password cannot be read back; both are rules the system
# enforces on purpose, worded beside the controls that enforce them, and this
# sheet lists what the system CANNOT do rather than what it refuses to.
USER_STATED_UNTRACKED = (
    ("Station and zone assignment", "assignment"),
    ("Invitation and lock-out states", "invitations"),
    ("Contact details", "contact"),
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
    """The Patient Queue (Screen 08) as a workbook: bytes and a filename."""
    return _workbook(_appointment_export(context, produced_by))


def appointment_document(context, produced_by=""):
    """The Patient Queue (Screen 08) as a PDF document: bytes and a filename."""
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
    footer_left = f"{config.SYSTEM_SHORT_NAME} · Exported {stamped.strftime('%B %d, %Y at %I:%M %p')}"
    if produced_by:
        footer_left += f" by {produced_by}"
    payload = render(
        export["sheets"],
        org=health_center_name(),
        org_sub=f"{config.SYSTEM_NAME} ({config.SYSTEM_SHORT_NAME})",
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
        ("Source", f"{health_center_name()} records, via {config.SYSTEM_SHORT_NAME}"),
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
        heading=health_center_name(),
        intro=(
            # NOT SWITCHED TO THE STORED NAME, AND THAT IS THE DELIBERATE HALF OF
            # THIS CHANGE. Every letterhead line above now reads the health
            # center's stored name, but this one is the SYSTEM's own title -- the
            # words IDS-BPHCSN is an acronym of. Renaming the facility does not
            # rename the software, and rewriting this from a setting would
            # produce an expansion whose initials no longer spell the acronym
            # printed beside it.
            f"{config.SYSTEM_NAME} ({config.SYSTEM_SHORT_NAME}).\n" + intro
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
    return f"{config.SYSTEM_SHORT_NAME} {screen} - {scope} - {today().isoformat()}"


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
    "Sorted by surname, A to Z. Age is the age today. Last Visit is the most recent recorded "
    "consultation."
)


# The Administrator's patient export is demographics only (Task 5c). His roster
# is read through get_all_patients_demographics(), so there is no contact number
# or visit date in it to write; these columns say so rather than leave blanks.
DEMOGRAPHIC_COLUMNS = (
    "Patient ID",
    "Full Name",
    "Age",
    "Sex",
    "Address",
    "Status",
    "Registered",
)

DEMOGRAPHIC_ROW_NOTE = (
    "Sorted by surname, A to Z. Demographics only: clinical details and contact numbers are for "
    "the Doctor and Health Center Staff."
)


def _patient_table(context):
    """(columns, rows, note) for a patient export, as this reader may have it."""
    patients = context["patients"]
    if context.get("demographics_only"):
        rows = [
            [
                _value(patient.get("patient_id")),
                _value(patient.get("full_name")),
                _value(patient.get("age")),
                _value(patient.get("sex")),
                _value(patient.get("display_address")),
                _value(patient.get("status")),
                display_date(patient.get("created_at"), "—"),
            ]
            for patient in patients
        ]
        return DEMOGRAPHIC_COLUMNS, rows, DEMOGRAPHIC_ROW_NOTE
    return PATIENT_COLUMNS, _patient_rows(patients), PATIENT_ROW_NOTE


def _roster_scope(context, care_team_text):
    """The Not Tracked sheet's opening sentence, true for the file it is in."""
    if context.get("demographics_only"):
        return ("This file holds demographics only. Clinical details and contact numbers are for "
                "the Doctor and Health Center Staff. The items below are not stored.")
    return care_team_text


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

    columns, rows, row_note = _patient_table(context)

    roster = sheet(
        "Patient Roster",
        [table(
            f"Every registered patient — {_count_label(total, 'record')}",
            columns,
            rows,
            note=row_note,
            empty="No patients are registered.",
        )],
        heading="Patient Roster",
        intro=(
            f"{_count_label(total, 'patient')} on the register as of "
            f"{long_date(today())}. Inactive and Deceased records are listed "
            "under that status."
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
            note=("Counted over the whole register, not over any filter on the screen."),
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
        _roster_scope(context, "The roster holds identity, contact and status. It is not a "
                               "medical record. The items below are not stored."),
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
        "The selection was made by ticking rows, and nothing stores it. If the reason matters, "
        "write it down beside the file.",
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
            *_patient_table(context)[:2],
            note=_patient_table(context)[2],
            empty="No selected record could be found.",
        )],
        heading="Selected Patients",
        intro=(
            f"{_count_label(total, 'patient')} selected from the "
            f"{_count_label(registered, 'patient')} on the register, as of "
            f"{long_date(today())}. Only the records ticked on Patient Records."
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
        "The search box and filters decide which rows can be ticked. This file is the ticked "
        "rows, and it cannot say what was on screen.",
    ]]
    if missing:
        controls.append([
            "Some selected records were not found",
            f"{requested} records were selected and {total} were found. "
            f"{missing} could not be included. Reload Patient Records and select again.",
        ])

    cover = _cover_sheet(
        "Patient Records",
        "Selected patients",
        produced_by,
        detail=detail,
        scope=(
            "A selection, not the register",
            "This file holds only the records ticked on Patient Records. It is not the full "
            "roster: Export Excel and Export PDF are.",
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
        _roster_scope(context, "These records hold identity, contact and status, as in the full "
                               "roster. They are not medical records. The items below are not "
                               "stored."),
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
            note=("Sorted by medicine name, A to Z. Status shows a retired item's status, or its "
                  "stock condition."),
            empty="The inventory holds nothing.",
        )],
        heading="Medicine Inventory",
        intro=(
            f"{_count_label(total, 'item')} on the shelf as of "
            f"{long_date(today())}"
            + (f", of which {retired} {'is' if retired == 1 else 'are'} retired."
               if retired else ".")
            + " Retired items are listed under that status. They are not counted "
            "in the figures on the next sheet."
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
            note=("The position today, over the whole shelf, not over any filter on the screen."),
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
        "This list holds the columns the screen shows. The other stored fields appear only on the"
        " Add / Edit Medicine form. The items below are not stored.",
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
# Screen 08 -- Patient Queue
# ---------------------------------------------------------------------------

# The Notes column holds the check-in reason. It is in the file only for the
# Doctor and Health Center Staff; the Administrator's file has no such column
# (Task 5b, D4). See _appointment_export().
QUEUE_COLUMNS = (
    "#",
    "Appointment ID",
    "Patient",
    "Patient ID",
    "Service / Reason",
    "Notes",
    "Arrived",
    "Status",
    "Assigned to",
)

CALENDAR_COLUMNS = (
    "Date",
    "Day",
    "Visits",
    "In the queue",
    "Waiting for the Doctor",
    "Completed",
)


def _patient_name(entry):
    """The queue's own rendering of a patient's name, first and last."""
    parts = [entry.get("first_name"), entry.get("last_name")]
    return " ".join(str(part).strip() for part in parts if part)


def _appointment_export(context, produced_by):
    """Screen 08 as a cover, its three panels, its figures, and the notes.

    WHAT "THE FULL LIST" MEANS ON THIS SCREEN
    -----------------------------------------
    Screen 08 is not one table. It shows two lists, and they answer two different
    questions: today's queue (who is here now) and the calendar (what each day of
    the month held). Both are in the file, on sheets of their own, in the order
    the screen has them, and the cover names each one's scope.

    The queue is today only, because that is what a queue is. The calendar sheet
    is the month the screen's calendar was showing, day by day -- the one part of
    this file a control on the screen does change, because ?month= is a real
    server-side parameter and the export route reads the same one the screen's
    arrows submit.

    There was a third sheet, Upcoming, holding every pending booking after today.
    It went with advance booking on 2026-09-05: nothing books a future day, so the
    sheet could only ever have been empty, and an empty sheet headed "Upcoming
    Appointments" reads as a query that failed rather than as a feature that was
    retired. The summary figures that counted those bookings went with it. See
    utils/unavailable.py `advance_booking`.
    """
    queue = context["queue"]
    queue_stats = context["queue_stats"]
    calendar = context["calendar"]
    queue_date = context["queue_date"]

    # No check-in reason for a role outside the care team. The column is left out
    # of the file rather than blanked, so the file does not suggest one was given.
    # The service names a clinical fact (a prenatal visit, an immunization), so the
    # Administrator's file has no service either (Task 6b).
    show_reason = bool(context.get("show_visit_reason"))
    queue_columns = [name for name in QUEUE_COLUMNS
                     if show_reason or name not in ("Notes", "Service / Reason")]
    queue_rows = [
        [
            _value(entry.get("line_position")),
            _value(entry.get("reference")),
            _value(_patient_name(entry)),
            _value(entry.get("patient_reference")),
            *([_value(entry.get("appointment_type") or "Consultation")] if show_reason else []),
            # A sealed visit's reason never goes into a file, even for the Doctor
            # who can read it on screen.
            *([_value(RESTRICTED_PLACEHOLDER if entry.get("reason_sealed")
                      else entry.get("notes"))] if show_reason else []),
            _value(entry.get("arrival_time")),
            _value(entry.get("display_status")),
            _value(entry.get("assigned_staff")),
        ]
        for entry in queue
    ]

    queue_sheet = sheet(
        "Today's Queue",
        [table(
            f"{display_date(queue_date)} — {_count_label(len(queue), 'patient')}",
            queue_columns,
            queue_rows,
            note=("In arrival order, patients in consultation first. The # column is the place in"
                  " the waiting line."),
            empty="Nobody has checked in today.",
        )],
        heading=f"Today's Queue — {long_date(queue_date)}",
        intro=(
            "Everyone checked in today, whatever has since happened to them: "
            "completed rows stay on the queue for the rest of the day, exactly as "
            "they do on the screen."
        ),
    )

    calendar_rows = [
        [
            display_date(cell["date"]),
            cell["date"].strftime("%A"),
            cell["total"],
            cell["in_queue"],
            cell["waiting_doctor"],
            cell["completed"],
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
            note=("One row per day that had a visit. The count columns add up to the day's total."),
            empty=f"Nothing was recorded in {calendar['label']}.",
        )],
        heading=f"Calendar — {calendar['label']}",
        intro=(
            "The month the calendar was showing, day by day. The month exported is the month "
            "displayed."
        ),
    )

    summary = sheet(
        "Summary",
        [figures(
            "The figures on the Patient Queue's stat cards and panel headers",
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
                ("Waiting for the Doctor today", queue_stats["waiting_doctor"],
                 "Intake saved; the Doctor has not written the diagnosis yet"),
                ("Completed today", queue_stats["completed"],
                 f"Finished visits, of the {queue_stats['total_today']} checked in today"),
                (f"Visits in {calendar['label']}", calendar["month_total"], ""),
            ],
            note=("The queue figures are today's, at the health center; the month "
                  "figure covers the calendar month on the sheet before this one. "
                  "Each row says which."),
        )],
        heading="Summary",
    )

    cover = _cover_sheet(
        "Patient Queue",
        "Today's queue and the calendar month",
        produced_by,
        detail=[
            ("Queue date", long_date(queue_date)),
            ("In today's queue", len(queue)),
            ("Calendar month", calendar["label"]),
        ],
        controls=[
            [
                "The controls that were not applied",
                "The queue's search box and its Advanced Filter service and "
                "status controls. All three narrow the table in the browser only.",
            ],
            [
                "The one control that was carried",
                "The calendar's month. The Calendar sheet holds the month that was on screen.",
            ],
        ],
        index=[
            ["Today's Queue", "Everyone checked in today, in queue order."],
            ["Calendar", "The month's load, one row per day that had visits."],
            ["Summary", "The figures the screen's stat cards and headers show."],
        ],
        intro=(
            "The Patient Queue shows two lists, and both are in this file on "
            "sheets of their own. Taken off the system on "
            f"{now().strftime('%B %d, %Y')}."
        ),
    )

    notes = _untracked_sheet(
        APPOINTMENT_UNTRACKED,
        "Both lists hold every visit as it stands now. The items below are not stored.",
    )

    return _assemble(
        "Patient Queue — Today's Queue and Calendar",
        f"{display_date(queue_date)} queue · {calendar['label']}",
        _stem("Patient Queue", "Queue and calendar"),
        cover,
        [queue_sheet, calendar_sheet, summary],
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
            note=("Ordered by role, then name. Contact is blank because the system does not "
                  "record it. Last Login comes from the audit trail."),
            empty="No accounts exist.",
        )],
        heading="System Accounts",
        intro=(
            f"{_count_label(total, 'account')} — {context['active_users']} active, "
            f"{context['inactive_users']} deactivated — across "
            f"{_count_label(context['roles_represented'], 'role')}. This is the "
            "complete list. A deactivated account cannot sign in."
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
            note=("Read from the access rule each screen enforces. An account appears once for "
                  "each screen its role can open."),
            empty="No screen is role-restricted.",
        )],
        heading="Access By Account",
        intro=(
            "The permissions panel of User Management, for every account. A screen not listed is "
            "refused for that role."
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
            note=("The same figures as the four cards above the table."),
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
            f"Every account is on one page ({_count_label(total, 'account')} today), "
            "so this file is the complete roster.",
        ]],
        index=[
            ["System Accounts",
             "Every account that can sign in, by role then name."],
            ["Access By Account", "Which screens each account's role can open."],
            ["Account Summary", "The figures the screen's stat cards show."],
        ],
        intro=(
            f"Every account that can sign in to {config.SYSTEM_SHORT_NAME}, with its role and "
            f"access, taken on {now().strftime('%B %d, %Y')}. No password is in this file."
        ),
    )

    notes = _untracked_sheet(
        [
            [label, untracked[key]]
            for label, key in USER_STATED_UNTRACKED
            if key in untracked
        ] + [[
            "That this export happened",
            "Exports are not recorded. The cover sheet names who took this copy and when.",
        ]],
        "The roster is complete. The reasons below are the screen's own words.",
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
