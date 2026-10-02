"""Export Excel and Export PDF, for both report screens."""
import config
from io import BytesIO

from flask import send_file

from models.settings import health_center_name
from utils.dates import display_date, long_date, now, today
from utils.document import PDF_MIMETYPE, render
from utils.security import get_current_user
from utils.small_counts import ranking_note, small_count_note
from utils.workbook import (
    XLSX_MIMETYPE, build, figures, safe_filename, sheet, table,
)

# The order sections appear in as sheets. One list for both screens, so a
# section common to the two -- consultations, registrations, appointments -- sits
# in the same relative place in either workbook and a reader who has seen one
# knows where to look in the other.
SECTION_ORDER = (
    "registrations",
    "consultations",
    "diagnoses",
    "concerns",
    "appointments",
    "services",
    "vaccination",
    "demographics",
    "seniors",
    "programs",
    "inventory",
    # Directly after inventory and never before it: the stock sheet is the shelf
    # as it stands and this one is what left it, and a reader who has just seen
    # a low figure is a reader about to ask why.
    "dispensing",
    "sms",
    "notifications",
)

# Sheet name per section. Kept inside Excel's 31-character limit here rather
# than being truncated by the writer, so the names are chosen rather than
# chopped.
SHEET_TITLES = {
    "registrations": "Registrations",
    "consultations": "Consultations",
    "diagnoses": "Diagnoses",
    "concerns": "Health Concerns",
    "appointments": "Appointments",
    "services": "Health Services",
    "vaccination": "Immunisation",
    "demographics": "Demographics",
    "seniors": "Senior Citizens",
    "programs": "Health Programmes",
    "inventory": "Medicine Inventory",
    "dispensing": "Items Dispensed",
    "sms": "SMS Activity",
    "notifications": "Notifications",
}

# One line saying what each sheet holds, for the index on the cover.
SHEET_SUMMARIES = {
    "registrations": "New patient registrations per month, and the range's total.",
    "consultations": "Consultations written up per month, and who was seen.",
    "diagnoses": "The most common diagnoses recorded inside the range.",
    "concerns": "Chronic conditions on the register, and the range's diagnoses.",
    "appointments": "Appointment outcomes per month, and the attendance rate.",
    "services": "Which services the range's visits were recorded against.",
    "vaccination": "Immunisation coverage on the closing date, and doses given.",
    "demographics": "Age, sex and chronic-condition breakdowns of the register.",
    "seniors": "The senior cohort and the conditions recorded against it.",
    "programs": "Programme membership the stored data can establish.",
    "inventory": "Stock condition today, and every item below its reorder level.",
    "dispensing": "Medicine issued to patients inside the range, and which medicines moved most.",
    "sms": "SMS broadcast activity inside the range, and all time.",
    "notifications": "SMS broadcast activity inside the range, and all time.",
}

# Which "not yet tracked" reasons a section is responsible for stating. The
# reason texts themselves are never written here -- they are looked up from the
# context's own `untracked` dict, which is routes/report_views.UNTRACKED and
# official_views.LOCAL_UNTRACKED merged. One wording, quoted by the screen and
# by the file it exports.
SECTION_UNTRACKED = {
    "vaccination": ("population", "campaigns"),
    "seniors": ("prenatal",),
    "programs": ("programs",),
    # "inventory" used to be responsible for stating ("dispensing",) here -- that
    # medicine leaving the shelf was not recorded and units dispensed could not be
    # recovered. It is recorded now, on its own sheet, so the reason is gone from
    # routes/report_views.UNTRACKED and the mapping to it goes with it. A key
    # listed here that the context no longer holds would be dropped silently by
    # _not_tracked_sheet()'s `if key in untracked` guard, which is exactly the
    # kind of quiet nothing worth removing deliberately instead.
    "sms": ("sms",),
    "notifications": ("delivery",),
}

# Stated on every workbook, whichever sections it holds. Exporting a report is
# still not recorded anywhere -- this feature did not change that -- and the
# screens both say so, so the file says so too.
ALWAYS_UNTRACKED = ("generated_reports",)


# ---------------------------------------------------------------------------
# The two entry points
# ---------------------------------------------------------------------------

def _download(built, mimetype):
    """A (bytes, filename) pair as the download itself.

    Every export route -- the Administrator's, the Barangay Official's and the
    Doctor's views of Screen 10, and Community Reports, each in both formats --
    returns through here,
    so the attachment header and the filename are decided once. A route that
    assembled its own response is how one of them would end up serving a file the
    browser offers to open as text.
    """
    payload, filename = built
    return send_file(
        BytesIO(payload),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


def excel_response(built):
    """A built workbook (bytes, filename) as an .xlsx download."""
    return _download(built, XLSX_MIMETYPE)


def pdf_response(built):
    """A built document (bytes, filename) as a .pdf download."""
    return _download(built, PDF_MIMETYPE)


def exported_by():
    """The signed-in account's own name, for the cover sheet.

    Read the way utils/context.py reads it for the sidebar and the print
    letterhead, so the name on an exported workbook is the name on the printed
    sheet of the same report. get_current_user() hands back a sqlite3.Row, which
    indexes but has no .get().
    """
    user = get_current_user()
    if user is not None and "full_name" in user.keys():
        return (user["full_name"] or "").strip()
    return ""


def analytics_workbook(context, produced_by=""):
    """Reports & Analytics (Screen 10) as a workbook: bytes and a filename."""
    sheets, stem = _assemble(context, "Reports & Analytics", produced_by)
    return build(sheets), safe_filename(stem + ".xlsx")


def community_workbook(context, produced_by=""):
    """Community Reports (Screen 18) as a workbook: bytes and a filename."""
    sheets, stem = _assemble(context, "Community Reports", produced_by)
    return build(sheets), safe_filename(stem + ".xlsx")


def analytics_pdf(context, produced_by=""):
    """Reports & Analytics (Screen 10) as a PDF document: bytes and a filename."""
    return _document(context, "Reports & Analytics", produced_by)


def community_pdf(context, produced_by=""):
    """Community Reports (Screen 18) as a PDF document: bytes and a filename."""
    return _document(context, "Community Reports", produced_by)


def _document(context, screen, produced_by):
    """Both screens' PDF, from the same sheets the workbook is built from.

    The renderer is handed the report's identity for the running letterhead and
    footer -- which report, over which days, taken off by whom -- because a PDF can
    be split and a loose page still has to say what it is. The figures themselves
    are in the sheets, which are the workbook's sheets.
    """
    sheets, stem = _assemble(context, screen, produced_by)
    selection = context["selection"]
    window = context["report_window"]
    stamped = now()
    exported = stamped.strftime("%B %d, %Y at %I:%M %p")
    footer_left = f"{config.SYSTEM_SHORT_NAME} · Exported {exported}"
    if produced_by:
        footer_left += f" by {produced_by}"
    payload = render(
        sheets,
        org=health_center_name(),
        org_sub=f"{config.SYSTEM_NAME} ({config.SYSTEM_SHORT_NAME})",
        doc_title=f"{screen} — {selection['type_label']}",
        range_label=f"{long_date(window['start'])} to {long_date(window['end'])}",
        footer_left=footer_left,
    )
    return payload, safe_filename(stem + ".pdf")


def _assemble(context, screen, produced_by):
    """The report as a list of sheet dicts, and a filename stem, for either file.

    The screen name is the only thing that differs structurally, and it differs
    only on the cover sheet and in the stem. Everything else is decided by which
    sections the selected report type keeps -- the same `selection.sections` set
    the template branches on -- so the two screens cannot grow different ideas of
    what a consultation section contains, and the .xlsx and the .pdf of one report
    cannot grow different ideas either: they are this one structure, rendered twice.
    """
    selection = context["selection"]
    window = context["report_window"]
    sections = [
        name for name in SECTION_ORDER
        if name in selection["sections"] and name in _SECTION_BUILDERS
    ]

    sheets = [_cover_sheet(context, screen, sections, produced_by)]
    summary = _summary_sheet(context, sections)
    if summary:
        sheets.append(summary)
    for name in sections:
        built = _SECTION_BUILDERS[name](context)
        if built:
            sheets.append(
                sheet(SHEET_TITLES[name], built, heading=_heading(name, window))
            )
    sheets.append(_not_tracked_sheet(context, sections))

    stem = (
        f"{config.SYSTEM_SHORT_NAME} {screen} - {selection['type_label']} - "
        f"{window['start'].isoformat()} to {window['end'].isoformat()}"
    )
    return sheets, stem


def _heading(name, window):
    return (
        f"{SHEET_TITLES[name]} — {display_date(window['start'])} to "
        f"{display_date(window['end'])}"
    )


# ---------------------------------------------------------------------------
# Cover, summary and notes
# ---------------------------------------------------------------------------

def _cover_sheet(context, screen, sections, produced_by):
    """What this file is, what it covers, and what is in it.

    A workbook of figures with no provenance is the spreadsheet version of the
    unlabelled printout _print.html's letterhead exists to prevent. This names
    the health center, the report, the exact days counted, who took it off the
    system and when -- and then, because a spreadsheet hides its other sheets
    behind tabs, indexes them.
    """
    selection = context["selection"]
    window = context["report_window"]
    stamped = now()

    detail = [
        ("Report", selection["type_label"]),
        ("Screen", screen),
        ("Covers", f"{long_date(window['start'])} to {long_date(window['end'])}"),
        (
            "Range",
            "Custom range, generated on the screen"
            if window["custom"] else
            f"Default window — the last {len(window['months'])} clinic months",
        ),
        ("Exported", stamped.strftime("%B %d, %Y at %I:%M %p")),
        ("Exported by", produced_by or "—"),
        ("Source", f"{health_center_name()} records, via {config.SYSTEM_SHORT_NAME}"),
    ]

    index = [
        [SHEET_TITLES[name], SHEET_SUMMARIES[name]] for name in sections
    ]
    if index:
        index.insert(0, ["Summary", "The headline figures from every sheet below."])
    index.append(["Not Tracked", "Figures this system has no source for, and why."])

    blocks = [
        table("This report", ("Item", "Detail"), detail, empty="—"),
        table("Sheets in this workbook", ("Sheet", "What it holds"), index),
    ]

    if selection["errors"]:
        # The screen refuses a range it cannot read and falls back to the default
        # window with the reason printed above the figures. The export carries
        # that refusal rather than quietly presenting the fallback as though it
        # were what was asked for.
        blocks.append(table(
            "Date range",
            ("Problem",),
            [[problem] for problem in selection["errors"]],
            note=("That range was not used. The report covers the default window "
                  "instead. The problems with it are listed below."),
        ))

    return sheet(
        "Report",
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
            f"{config.SYSTEM_NAME} ({config.SYSTEM_SHORT_NAME}).\n"
            + context["snapshot_note"]
            + "\nEvery sheet says, under its own heading, whether its figures "
            "were counted inside the range or describe the position today."
        ),
    )


def _summary_sheet(context, sections):
    """The stat cards, as rows. One place a reader can check the headline totals.

    Each row carries the basis it was counted on, because half of these are
    ranged and half are not, and a column of numbers with no basis beside them is
    exactly how a snapshot figure ends up quoted as a period one.
    """
    window = context["report_window"]
    ranged = f"{display_date(window['start'])} to {display_date(window['end'])}"
    standing = f"Position as of {display_date(today())}, not narrowed by the range"
    rows = []

    if "registrations" in sections:
        patients = context["patient_report"]
        rows.append(("Total registered patients", patients["stats"]["total_patients"], standing))
        rows.append(("Registered in this range", patients["window"]["registered"], ranged))
    if "consultations" in sections:
        consultations = context["consultation_report_stats"]
        rows.append(("Consultations recorded", consultations["window"]["total"], ranged))
        rows.append(("Patients seen", consultations["window"]["patients_seen"], ranged))
        rows.append(("Consultations on record, all time", consultations["total"],
                     "Every consultation ever recorded"))
    if "appointments" in sections:
        appointments = context["appointment_report"]["window"]
        rows.append(("Appointments", appointments["total"], ranged))
        rows.append(("Attendance rate (%)", appointments["attendance_pct"],
                     f"Of the {appointments['resolved']} that have resolved, {ranged}"))
    if "vaccination" in sections:
        coverage = context["immunization_coverage"]
        rows.append(("Children up to date on the DOH schedule (%)",
                     coverage["up_to_date_pct"],
                     f"{coverage['up_to_date_children']} of "
                     f"{coverage['eligible_children']} registered children, as of "
                     f"{display_date(window['end'])}"))
        # Split rather than totalled. This sheet is the summary somebody quotes
        # from, and "doses given" has to mean doses this health center gave.
        rows.append(("Immunisation doses given here",
                     coverage["window"]["doses_administered"], ranged))
        rows.append(("Doses reported as given elsewhere",
                     coverage["window"]["doses_reported"],
                     f"{ranged}, by the date reported. Recorded at a consultation "
                     "here; administered at another facility"))
    if "inventory" in sections:
        inventory = context["inventory_report"]
        rows.append(("Inventory items in service", inventory["total_items"], standing))
        rows.append(("Items below reorder level", inventory["low_stock_count"], standing))
    if "dispensing" in sections:
        dispensed = context["dispensing_stats"]["window"]
        rows.append(("Medicine units dispensed", dispensed["units"], ranged))
        rows.append(("Dispensing events", dispensed["events"], ranged))
    if "programs" in sections:
        for program in context["programs"]:
            rows.append((f"{program['name']} — members", program["count"],
                         f"{program['basis']}. {standing}"))
    if "concerns" in sections:
        conditions = context["conditions"]
        rows.append(("Patients with a recorded chronic condition",
                     conditions["with_any_shown"], standing))
    for key in ("sms", "notifications"):
        if key in sections:
            broadcasts = context["broadcast_stats"]
            rows.append(("SMS broadcasts published", broadcasts["window"]["broadcasts"], ranged))
            rows.append(("Messages handed to the gateway",
                         broadcasts["window"]["messages_sent"], ranged))
            break

    if not rows:
        return None
    return sheet(
        "Summary",
        [figures("Headline figures", rows)],
        heading=f"Summary — {ranged}",
    )


def _not_tracked_sheet(context, sections):
    """Everything the barangay's records cannot answer, in the screen's words."""
    untracked = context["untracked"]
    keys = []
    for name in sections:
        for key in SECTION_UNTRACKED.get(name, ()):
            if key not in keys:
                keys.append(key)
    for key in ALWAYS_UNTRACKED:
        if key not in keys:
            keys.append(key)

    rows = [[key.replace("_", " ").capitalize(), untracked[key]]
            for key in keys if key in untracked]
    return sheet(
        "Not Tracked",
        [table("What this system has no source for", ("Subject", "Why"), rows,
               empty="Nothing in this report has an untracked figure.")],
        heading="Not Tracked",
        intro=(
            "These gaps are stated on the screens and carried into the export. "
            "A figure with no data is shown as absent, never filled in."),
    )


# ---------------------------------------------------------------------------
# Shared block builders
#
# The pieces both screens are made of. A section that appears on Screen 10 and
# Screen 18 -- registrations, consultations, appointments -- is built by the same
# function from the same context keys, which is what stops the two exports from
# drifting into two answers.
# ---------------------------------------------------------------------------

def _trend_block(title, trend, series, note=None):
    """A month-by-month chart's own numbers.

    `series` is a list of (column heading, key) taken off each trend row. With
    more than one it adds a Total column, which is what the stacked
    appointment-outcome chart needs -- the same shape _chart_table.html renders
    for the printer.
    """
    columns = ["Month"] + [heading for heading, _ in series]
    multi = len(series) > 1
    if multi:
        columns.append("Total")
    rows = []
    for point in trend:
        values = [point[key] for _, key in series]
        rows.append([point["label"]] + values + ([sum(values)] if multi else []))
    return table(title, columns, rows, note=note)


def _ranked_block(title, entries, label_key, count_key, heads, note=None,
                  empty="Nothing recorded in this range."):
    """A ranked or fixed-order list -- diagnoses, services, conditions, bands."""
    return table(
        title, heads,
        [[entry[label_key], entry[count_key]] for entry in entries],
        note=note, empty=empty,
    )


# ---------------------------------------------------------------------------
# WHAT A DIAGNOSIS RANKING IN AN EXPORT MAY SAY ABOUT WHAT IT LEFT OUT
#
# A consultation the clinician has sealed is counted in this range's totals and
# its trend, and appears in the diagnosis ranking only as one "Confidential" row
# -- the rule is in models/consultations.py, _rank_diagnoses(). These three
# helpers exist so the two blocks below state that consistently.
#
# THEY ARE SHARED BECAUSE THE WORKBOOK AND THE PDF ARE THE SAME ASSEMBLY. Both
# export routes for all three roles -- six of them, plus Screen 18's three -- build
# from the identical context through the identical functions, which is what stops
# an Administrator's workbook and a Barangay Official's PDF disagreeing about
# what the barangay recorded. A sentence typed into one of the two ranking blocks
# and not the other would reintroduce exactly that split.
#
# None of the three ever emits a diagnosis, a date or a patient. A count is the
# whole of what they publish.
# ---------------------------------------------------------------------------
def _ranked_count(consultations):
    """How many of the range's consultations the diagnosis ranking covers: all
    of them. Restricted ones are counted under Confidential (D3)."""
    return consultations["window"]["total"]


def _ranking_note(consultations, which, what):
    """The sentences added to a ranking's note: sealed visits, and folded rows.

    `which` is "top_diagnoses" or "top_complaints"; `what` is the word for what is
    not shown. The wording is utils.small_counts.ranking_note(), which the screens
    use too. Empty when the range has neither, which is the ordinary case.
    """
    window = consultations["window"]
    return ranking_note(window[which], window["diagnoses_withheld"], what)


def _ranking_empty(consultations):
    """The empty state. Sealed visits always appear as Confidential, so an empty
    ranking means nothing was written up."""
    return "No consultation was written up in this range."


def _month_change_rows(change, subject):
    """The "vs last month" figure Screen 18's cards print, as rows.

    Read off the trend the card sits above, exactly as _month_over_month() reads
    it -- not recounted here. `change_pct` is None when the previous month is
    zero, and stays absent rather than being rendered as a percentage change from
    nothing.
    """
    if not change:
        return []
    rows = [(f"{subject} in {change['label']}", change["count"], "The trend's last month")]
    if change["previous_label"]:
        rows.append((f"{subject} in {change['previous_label']}",
                     change["previous_count"], "The month before it"))
        rows.append(("Change", change["change"], f"Against {change['previous_label']}"))
        if change["change_pct"] is not None:
            rows.append(("Change (%)", change["change_pct"],
                         f"Against {change['previous_label']}"))
        else:
            rows.append(("Change (%)", None,
                         f"{change['previous_label']} recorded none, so a "
                         f"percentage change is undefined"))
    return rows


def _condition_rows(counts):
    return [[entry["condition"], entry["count"]] for entry in counts]


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _registrations(context):
    patients = context["patient_report"]
    window = context["report_window"]
    trend = patients["registration_trend"]

    rows = [
        ("Registered in this range", patients["window"]["registered"],
         f"patients.created_at between {display_date(window['start'])} and "
         f"{display_date(window['end'])}"),
        ("Total registered patients", patients["stats"]["total_patients"],
         "The whole register, today"),
        ("Registered this calendar month", patients["stats"]["new_this_month"],
         "The clinic month to date, not narrowed by the range"),
    ]
    rows.extend(_month_change_rows(context.get("registration_month"), "Registrations"))

    return [
        _trend_block("New patient registrations, by month", trend,
                     [("Registrations", "count")],
                     note="The first and last months are clipped to the range, so the bars add up to the range total."),
        figures("Registration totals", rows),
    ]


def _consultations(context):
    consultations = context["consultation_report_stats"]
    window = context["report_window"]

    rows = [
        ("Consultations recorded in this range", consultations["window"]["total"],
         f"consultations.consultation_date between "
         f"{display_date(window['start'])} and {display_date(window['end'])}"),
        ("Patients seen in this range", consultations["window"]["patients_seen"],
         "Distinct patients, so a patient seen twice counts once"),
        ("Consultations on record, all time", consultations["total"],
         "Every consultation ever recorded"),
        ("Patients seen, all time", consultations["patients_seen"],
         "Distinct patients across the whole record"),
    ]
    rows.extend(_month_change_rows(context.get("consultation_month"), "Consultations"))

    return [
        _trend_block("Consultations written up, by month", consultations["trend"],
                     [("Consultations", "count")],
                     note=("Counted from the range's own rows, clipped to it, so the "
                           "months sum to the range total below.")),
        figures("Consultation totals", rows),
    ]


def _diagnoses(context):
    consultations = context["consultation_report_stats"]
    window = context["report_window"]
    return [
        _ranked_block(
            "Most common diagnoses recorded in this range",
            consultations["window"]["top_diagnoses"], "label", "count",
            ("Diagnosis", "Consultations"),
            note=("Ranked from this range's consultations. Diagnoses are typed text, so two "
                  "spellings of one condition count separately."
                  + _ranking_note(consultations, "top_diagnoses", "diagnoses")),
            empty=_ranking_empty(consultations),
        ),
        _ranked_block(
            "Most common presenting complaints in this range",
            consultations["window"]["top_complaints"], "label", "count",
            ("Complaint", "Consultations"),
            note=(("Ranked from this range's consultations. Diagnoses are typed text, so two "
                   "spellings of one condition count separately.")
                  + _ranking_note(consultations, "top_complaints", "complaints")),
            empty="No consultation was written up in this range.",
        ),
        figures("Basis", [
            ("Consultations these are ranked from", _ranked_count(consultations),
             f"{display_date(window['start'])} to {display_date(window['end'])}"),
            ("Restricted consultations, counted under Confidential",
             consultations["window"]["diagnoses_withheld_shown"],
             "Counted in the totals. Their diagnoses are not shown"),
        ]),
    ]


def _concerns(context):
    """Screen 18's "Top Community Health Concerns", both halves of it.

    The question has two answers over a date range and they are different
    questions: what the register records as chronic conditions, which describes
    who is registered today, and what was diagnosed during the range. Both are
    here, each labelled with which it is, exactly as the screen shows them --
    presenting one alone would let a reader take the standing register for the
    period's illness.
    """
    conditions = context["conditions"]
    ranked = context["top_conditions"]
    consultations = context["consultation_report_stats"]
    window = context["report_window"]

    other_only = conditions["other_only"]
    other_only_shown = conditions["other_only_shown"]
    basis = (
        "Counted from the registration form's condition list. A patient with two "
        "conditions is counted under each, so these do not add up to the "
        f"{conditions['cohort_size']} patients."
    )
    if other_only:
        basis += (
            f" {other_only_shown} patient{'' if other_only_shown == 1 else 's'} recorded only "
            f"free-text conditions and {'is' if other_only_shown == 1 else 'are'} not "
            "counted here."
        )

    return [
        table("Chronic conditions recorded at registration, whole register",
              ("Condition", "Patients"), _condition_rows(ranked),
              note=(context["snapshot_note"] + " " + basis
                    + small_count_note(ranked)),
              empty="No patient has a recorded chronic condition yet."),
        _ranked_block(
            "Diagnoses recorded in this range",
            consultations["window"]["top_diagnoses"], "label", "count",
            ("Diagnosis", "Consultations"),
            note=(f"From {_ranked_count(consultations)} consultation"
                  f"{'' if _ranked_count(consultations) == 1 else 's'} written up "
                  f"between {display_date(window['start'])} and "
                  f"{display_date(window['end'])}. Grouped by the text entered, "
                  "ignoring case."
                  + _ranking_note(consultations, "top_diagnoses", "diagnoses")),
            empty=_ranking_empty(consultations),
        ),
        figures("Register totals", [
            ("Patients on the register", conditions["cohort_size"], "Today"),
            ("Patients with any recorded condition", conditions["with_any_shown"], "Today"),
            ("Patients with free-text conditions only", other_only_shown,
             "Not counted in the table above"),
        ]),
    ]


def _appointments(context):
    appointments = context["appointment_report"]
    window = appointments["window"]
    return [
        _trend_block(
            "Appointment outcomes, by month", appointments["trend"],
            [("Attended", "attended"), ("Waiting for the Doctor", "awaiting"),
             ("Still expected", "expected"),
             ("Cancelled / no-show", "missed"),
             ("Left before being seen", "left")],
            note=("The five outcomes partition every status an appointment can "
                  "hold, so a month's row totals that month's appointments."),
        ),
        figures("Appointment outcomes in this range", [
            ("Appointments", window["total"], "Dated into the range, walk-ins included"),
            ("Attended", window["attended"],
             "Completed visits, plus those in the clinic right now"),
            ("Waiting for the Doctor", window["awaiting"],
             "Intake saved; the Doctor has not written the diagnosis yet"),
            ("Cancelled or no-show", window["missed"], ""),
            ("Left before being seen", window["left"],
             "Checked in, then went home before the Doctor saw them"),
            ("Still expected", window["expected"],
             "From the earlier booking system, never closed. Zero since September "
             "2026, when booking ended"),
            ("Resolved", window["resolved"],
             "Attended, waiting for the Doctor, cancelled/no-show and left before being seen — a visit still to happen has "
             "neither succeeded nor failed"),
            ("Attendance rate (%)", window["attendance_pct"],
             "Of the resolved appointments only"),
            ("Missed rate (%)", window["missed_pct"],
             "Of the resolved appointments only"),
            ("Walk-ins", window["walk_ins"], ""),
            ("From the earlier booking system", window["booked"],
             "Visits booked ahead before September 2026"),
        ]),
    ]


def _services(context):
    window = context["appointment_report"]["window"]
    return [
        _ranked_block(
            "Appointments by service requested", window["services"],
            "service", "count", ("Service", "Appointments"),
            note=("What was actually asked for, walk-ins included. This is a record "
                  "of visits, not of who is enrolled in a programme -- nothing in "
                  "this system stores an enrolment."
                  + small_count_note(window["services"])),
            empty="No appointment falls in this range, so there is nothing to rank.",
        ),
        figures("Basis", [
            ("Appointments in this range", window["total"], "Walk-ins included"),
        ]),
    ]


def _vaccination(context):
    coverage = context["immunization_coverage"]
    window = context["report_window"]
    closing = display_date(window["end"])
    return [
        figures("Immunisation coverage", [
            ("Registered children the schedule applies to",
             coverage["eligible_children"], f"As of {closing}"),
            ("Children up to date on the DOH schedule",
             coverage["up_to_date_children"], f"As of {closing}"),
            ("Children up to date (%)", coverage["up_to_date_pct"],
             "Against registered children, not against the barangay"),
            ("Children needing attention", coverage["needing_attention"],
             f"Due or overdue a dose as of {closing}"),
            ("Children overdue a dose", coverage["overdue_children"], f"As of {closing}"),
            ("Children awaiting a first dose", coverage["awaiting_first_dose"],
             "Due a dose and with nothing on record yet"),
        ], note=("Coverage is a judgement about a child made on one day, so it is "
                 f"reported as of the range's closing date, {closing}. There is no "
                 "such thing as a child being up to date \"during\" a period.")),
        figures("Doses", [
            ("Doses given here in this range",
             coverage["window"]["doses_administered"],
             f"{display_date(window['start'])} to {closing}"),
            ("Doses reported as given elsewhere, in this range",
             coverage["window"]["doses_reported"],
             "Administered at another facility and reported to this health "
             "center at a consultation. A dose whose date is not known appears "
             "in no range"),
            ("Children dosed in this range", coverage["window"]["children_dosed"],
             "Distinct children"),
            ("Doses on record, all time", coverage["doses_given"],
             f"{coverage['doses_administered']} given here, "
             f"{coverage['doses_reported']} reported as given elsewhere"),
            ("Patients with at least one dose", coverage["enrolled"],
             "The only reading of programme membership the data supports"),
        ], note=("Coverage counts every dose a child has had, wherever it was given. "
                 "These dose counts are this health center's own work, so the two are never added together.")),
    ]


def _demographics(context):
    patients = context["patient_report"]
    ages = patients["age_distribution"]
    sexes = patients["sex_distribution"]
    conditions = patients["conditions"]

    return [
        table("Registered patients by age group, whole register",
              ("Age group", "Patients"),
              [[band["label"], band["count"]] for band in ages["bands"]],
              note=(context["snapshot_note"] + " Ages are calculated from each stored "
                    "birthdate on the day of export.")),
        figures("Age basis", [
            ("Patients with a usable birthdate", ages["known"], "Plotted above"),
            ("Patients with no usable birthdate", ages["unknown"],
             "Counted here rather than dropped into a band"),
        ]),
        table("Registered patients by sex, whole register",
              ("Sex", "Patients", "Share of roster (%)"),
              [["Female", sexes["female"], sexes["female_pct"]],
               ["Male", sexes["male"], sexes["male_pct"]],
               ["Not recorded", sexes["unrecorded"], sexes["unrecorded_pct"]]],
              note="Shares are of the whole roster, so they sum to 100%."),
        table("Chronic conditions recorded at registration, whole register",
              ("Condition", "Patients"), _condition_rows(conditions["counts"]),
              note=("A patient with two conditions is counted under each, so these do "
                    f"not sum to the {conditions['cohort_size']} patients on the "
                    "register." + small_count_note(conditions["counts"]))),
    ]


def _seniors(context):
    patients = context["patient_report"]
    seniors = patients["senior_conditions"]
    age = patients["senior_age"]
    return [
        table(f"Senior patients ({age}+) by recorded chronic condition",
              ("Condition", "Seniors"), _condition_rows(seniors["counts"]),
              note=(context["snapshot_note"] + " A senior with two conditions is "
                    f"counted under each, so these do not sum to "
                    f"{seniors['cohort_size']}." + small_count_note(seniors["counts"]))),
        figures("The senior cohort", [
            (f"Patients aged {age} and above", patients["senior_count"], "By birthdate"),
            ("Share of the roster (%)", patients["senior_share_pct"], ""),
            ("Seniors with free-text conditions only", seniors["other_only_shown"],
             "Not counted in the table above"),
        ]),
    ]


def _programs(context):
    return [
        table("Programme membership the stored data can establish",
              ("Programme", "Patients", "Counted from"),
              [[program["name"], program["count"], program["basis"]]
               for program in context["programs"]],
              note=(context["snapshot_note"] + " Both memberships are derived from the "
                    "register and the whole dose history, not read from an enrolment "
                    "somebody recorded.")),
    ]


def _inventory(context):
    inventory = context["inventory_report"]
    distribution = inventory["status_distribution"]
    return [
        table("Inventory items by stock condition, today",
              ("Condition", "Items"),
              [["In Stock", distribution["in_stock"]],
               ["Low Stock", distribution["low_stock"]],
               ["Near Expiry", distribution["near_expiry"]],
               ["Expired", distribution["expired"]]],
              note=(context["snapshot_note"] + " Each item is counted once, under the "
                    "most urgent condition that applies to it, so these sum to the "
                    "total below.")),
        figures("Inventory totals", [
            ("Items tracked", inventory["total_items"],
             "Items in service today; retired items are excluded, as they are "
             "from the reorder figure below"),
            ("Items below reorder level", inventory["low_stock_count"], "Today"),
            ("Items out of stock", inventory["out_of_stock_count"], "Today"),
        ]),
        table("Items below their reorder level, today",
              ("Item", "Dosage", "Stock", "Reorder level", "Unit",
               "% of reorder level", "Status"),
              [[item["name"], item.get("display_dosage") or "",
                item.get("stock_quantity") or 0,
                item.get("low_stock_threshold") or 0,
                item.get("unit") or "", item.get("threshold_pct"),
                item.get("stock_status") or ""]
               for item in inventory["low_stock_items"]],
              note="Most urgent first: stock as a fraction of the item's own reorder level.",
              empty="Every item is above its reorder level."),
    ]


def _dispensing(context):
    """What actually left the shelf inside the range.

    The sheet that could not exist before medicine_dispensing did. Everything on
    it is ranged -- unlike the inventory sheet directly before it, which reports
    the shelf as it stands today and says so -- because every row behind these
    figures carries the date it happened on.

    The ranking is by units rather than by number of issues, and both are
    printed. They answer different questions: an antibiotic given to forty
    patients in tens is a different supply problem from a maintenance drug given
    to two patients in hundreds, and a sheet that showed only one of the two
    would let a reader draw the wrong conclusion about which shelf to restock.

    Covers all three inventory categories, as the dispensing form does. The
    stats dict still keys its ranking "medicines" -- that is an internal name
    predating the widening, and renaming it would touch every reader of
    get_dispensing_stats() for nothing a reader of this sheet ever sees.
    """
    dispensing = context["dispensing_stats"]
    window = context["report_window"]
    scoped = dispensing["window"]
    span = "{} to {}".format(
        display_date(window["start"]), display_date(window["end"]))

    return [
        figures("Items dispensed in this range", [
            ("Units dispensed", scoped["units"], span),
            ("Dispensing events", scoped["events"],
             "One event is one item issued to one patient at one visit"),
            ("Patients supplied", scoped["patients"], ""),
            ("Different items dispensed", scoped["medicines"], ""),
        ]),
        _trend_block("Units dispensed, by month", scoped["trend"],
                     [("Units", "units")],
                     note="Clipped to the range, not rounded out to whole "
                          "months, so the bars sum to the figure above."),
        _trend_block("Dispensing events, by month", scoped["trend"],
                     [("Events", "events")]),
        table("Most dispensed items in this range",
              ("Item", "Units", "Unit", "Issues"),
              [[entry["medicine_name"], entry["units"], entry["unit"] or "",
                entry["events"]]
               for entry in scoped["all_medicines"]],
              note="Ranked by units dispensed in the range, most first. An item renamed in the "
                   "range appears under both names."
                   + (" Items dispensed at Restricted consultations are counted "
                      "under Confidential and not named."
                      if any(e.get("confidential") for e in scoped["all_medicines"])
                      else "")
                   + small_count_note(scoped["all_medicines"]),
              empty="Nothing was dispensed inside this range."),
        figures("All time", [
            ("Units dispensed", dispensing["total_units"], ""),
            ("Dispensing events", dispensing["total_events"], ""),
            ("Patients supplied at least once", dispensing["patients_supplied"], ""),
        ]),
    ]


def _broadcasts(context):
    broadcasts = context["broadcast_stats"]
    window = context["report_window"]
    scoped = broadcasts["window"]
    return [
        figures("SMS activity in this range", [
            ("Broadcasts published", scoped["broadcasts"],
             f"{display_date(window['start'])} to {display_date(window['end'])}"),
            ("Messages handed to the gateway", scoped["messages_sent"], ""),
            ("Messages that failed to send", scoped["messages_failed"], ""),
            ("Broadcasts sent through the simulated gateway", scoped["simulated"],
             "recorded in full, but never handed to the messaging service"),
        ]),
        figures("All time", [
            ("Broadcasts on record", broadcasts["total_broadcasts"], ""),
            ("Messages handed to the gateway", broadcasts["messages_sent"], ""),
            ("Messages that failed to send", broadcasts["messages_failed"], ""),
            ("Contacts reachable by SMS", broadcasts["reachable_contacts"],
             "Patients with a usable mobile number on file, today — not narrowed "
             "by the range, because no history of who was reachable is kept"),
        ]),
    ]


_SECTION_BUILDERS = {
    "registrations": _registrations,
    "consultations": _consultations,
    "diagnoses": _diagnoses,
    "concerns": _concerns,
    "appointments": _appointments,
    "services": _services,
    "vaccination": _vaccination,
    "demographics": _demographics,
    "seniors": _seniors,
    "programs": _programs,
    "inventory": _inventory,
    "dispensing": _dispensing,
    # One builder, two section names. Screen 10 calls this section "sms" and
    # Screen 18 calls it "notifications"; they are the same figures from
    # get_broadcast_stats() and are deliberately not built twice.
    "sms": _broadcasts,
    "notifications": _broadcasts,
}
