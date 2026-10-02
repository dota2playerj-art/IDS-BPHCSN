"""Export Excel and Export PDF, for Screen 12's audit trail.

The Export control on Audit Logs presses this. It reads routes/audit_views'
audit_export_context(), which decorates rows through the same _decorate() the
screen renders from, so an entry cannot read one way in the table and another in
the file.
"""
import config
from models.settings import health_center_name
from routes.audit_views import PAGE_SIZE
from routes.report_export import _download  # noqa: F401  (re-exported below)
from utils.dates import now
from utils.document import PDF_MIMETYPE, render
from utils.workbook import XLSX_MIMETYPE, build, safe_filename, sheet, table

# The trail is written as two blocks rather than one seven-column table, and the
# reason is a hard limit rather than a preference.
#
# `details` is prose, and the longest entry in the seeded trail is over 2,300
# characters. In a seven-column portrait table that column is capped at about
# 48mm by utils/document._weights() -- deliberately, so one long entry cannot
# starve the other columns -- and 2,300 characters wrapped into 48mm is several
# pages of text inside a single cell. fpdf2 refuses a row taller than one page,
# and it is right to: there is no sensible way to draw one.
#
# The alternatives were both worse. Truncating would put an ellipsis in the
# middle of the one field that records what actually changed, in the file whose
# whole claim is that it is the record. Giving the PDF a different table from the
# spreadsheet would mean two assemblies, which is the thing this module and
# report_export.py both exist to avoid.
#
# So the identifying fields -- all short, all sortable -- stay a grid, and the
# prose gets a block of its own with most of the page width to wrap into. An
# entry number ties the two together, and it is the same number in both files.
#
# One tuple each, so the .xlsx and the .pdf cannot grow different ideas of what an
# entry consists of, and so a column cannot be added to one file and forgotten in
# the other.
TRAIL_COLUMNS = (
    "#",
    "Date & time",
    "User",
    "Role",
    "Module",
    "Action",
    "IP address",
)

DETAIL_COLUMNS = ("#", "When & who", "What was recorded")

# Which UNTRACKED reasons the file states. Every one of them, because each names
# something the trail does not hold, and that is the set a reader of a *complete
# record* most needs. Named explicitly rather than iterating the dict so a reason
# added for a screen slot does not silently start appearing in exports.
STATED_UNTRACKED = (
    ("The edge of the two sign-in figures", "login_scope"),
    ("Filtering by user, activity type or status", "filters"),
)


def audit_workbook(context, produced_by=""):
    """The audit trail as a workbook: bytes and a filename."""
    sheets, stem = _assemble(context, produced_by)
    return build(sheets), safe_filename(stem + ".xlsx")


def audit_document(context, produced_by=""):
    """The audit trail as a PDF: bytes and a filename.

    Handed the trail's identity for the running letterhead and footer, because a
    PDF can be split and a loose page still has to say which system it came off,
    over what scope, taken by whom.
    """
    sheets, stem = _assemble(context, produced_by)
    stamped = now()
    exported = stamped.strftime("%B %d, %Y at %I:%M %p")
    footer_left = f"{config.SYSTEM_SHORT_NAME} · Exported {exported}"
    if produced_by:
        footer_left += f" by {produced_by}"

    payload = render(
        sheets,
        org=health_center_name(),
        org_sub=f"{config.SYSTEM_NAME} ({config.SYSTEM_SHORT_NAME})",
        doc_title="Audit Logs — System Activity Trail",
        range_label=_scope_label(context),
        footer_left=footer_left,
    )
    return payload, safe_filename(stem + ".pdf")


def _scope_label(context):
    """'All modules' or the one module filtered to. The file's subtitle."""
    return context["selected_module"] or "All modules"


def _assemble(context, produced_by):
    """The trail as a list of sheet dicts, and a filename stem, for either file.

    Three sheets, always the same three: what this file is, the entries, and what
    the trail does not record. There is no per-section branching the way
    report_export has, because there are no sections -- the audit trail is one
    table, which is why this was the simplest export in the project to build.
    """
    sheets = [
        _cover_sheet(context, produced_by),
        _trail_sheet(context),
        _untracked_sheet(context),
    ]

    scope = context["selected_module"] or "All modules"
    stem = f"{config.SYSTEM_SHORT_NAME} Audit Logs {scope} {now().strftime('%Y-%m-%d')}"
    return sheets, stem


def _cover_sheet(context, produced_by):
    """What this file is, what it covers, and what it deliberately does not.

    A trail of entries with no provenance is the spreadsheet version of the
    unlabelled printout _print.html's letterhead exists to prevent. This names the
    health centre, the filter in force, how many entries are in the file, who took
    it off the system and when -- and then states the two scope facts a reader
    would otherwise have to guess at.
    """
    total = context["total"]
    stamped = now()

    detail = [
        ("Document", "System activity trail"),
        ("Screen", "Audit Logs"),
        ("Module filter", _scope_label(context)),
        ("Entries in this file", total),
        ("Exported", stamped.strftime("%B %d, %Y at %I:%M %p")),
        ("Exported by", produced_by or "—"),
        ("Source", f"{health_center_name()} records, via {config.SYSTEM_SHORT_NAME}"),
    ]

    scope = [
        [
            "Every entry, not one page of them",
            f"Audit Logs shows {PAGE_SIZE} entries at a time. This file holds all "
            f"{total} entries that match the module filter.",
        ],
        [
            "A search typed on the screen was not applied",
            "The search box works in the browser only. This file is filtered by "
            "module only. To cover less, set the module filter and export again.",
        ],
    ]

    return sheet(
        "About This File",
        [
            table("This export", ("Item", "Detail"), detail, empty="—"),
            table("What it covers", ("Point", "What it means"), scope),
            table(
                "Sheets in this workbook",
                ("Sheet", "What it holds"),
                [
                    ["Audit Trail", "Every recorded entry, newest first."],
                    ["Not Tracked", "What the trail does not record, and why."],
                ],
            ),
        ],
        heading=health_center_name(),
        intro=(
            "The recorded history of who changed what in this system, taken off "
            f"on {stamped.strftime('%B %d, %Y')}. Entries are listed newest first, "
            "in clinic-local time."
        ),
    )


def _trail_sheet(context):
    """The entries themselves, in the order the screen lists them.

    `details` is written verbatim rather than split into the before/after pairs
    the screen renders. The screen splits it because a table cell has room to show
    a change side by side; the file's job is to be the record, and the stored
    sentence is the record. Nothing is dropped and nothing is reinterpreted.
    """
    entries = context["entries"]

    rows = [
        [
            number,
            entry.get("full_text") or "—",
            entry.get("user_name") or "—",
            entry.get("user_role") or "—",
            entry.get("module") or "—",
            entry.get("action") or "—",
            entry.get("ip_address") or "—",
        ]
        for number, entry in enumerate(entries, start=1)
    ]

    details = [
        [
            number,
            f"{entry.get('full_text') or '—'} · {entry.get('user_name') or '—'}",
            entry.get("details") or "—",
        ]
        for number, entry in enumerate(entries, start=1)
    ]

    return sheet(
        "Audit Trail",
        [
            table(
                f"Recorded activity — {_scope_label(context)}",
                TRAIL_COLUMNS,
                rows,
                note=("Newest first. Times are clinic-local, converted from the "
                      "stored UTC timestamps the same way every screen converts "
                      "them."),
                empty="No activity has been recorded for this module.",
            ),
            table(
                "What each entry recorded",
                DETAIL_COLUMNS,
                details,
                note=("The # column is the entry's number in the table above. Each "
                      "entry is written here in full, as stored."),
                empty="No activity has been recorded for this module.",
            ),
        ],
        intro=(
            f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}. Each one is a "
            "write that happened, named by the account that made it."
        ),
    )


def _untracked_sheet(context):
    """What the trail does not record, in the screen's own words.

    The last sheet on purpose, and never omitted. A reader who has just been told
    this file is the complete record needs, in the same breath, to know the two
    places that record still has an edge -- otherwise a figure's boundary reads as
    a gap in what was written down.

    Sign-ins used to head this sheet, as the largest thing the trail did not
    hold. They are in the file now, so what is left of that row is the boundary
    of what the sign-in entries cover, which is a narrower and more useful
    sentence. See UNTRACKED in routes/audit_views.py.
    """
    untracked = context["untracked"]
    rows = [
        [label, untracked[key]]
        for label, key in STATED_UNTRACKED
        if key in untracked
    ]

    return sheet(
        "Not Tracked",
        [table(
            "What this trail does not record, and why",
            ("Not recorded", "Why"),
            rows,
            note=("These are not gaps in this file. They are things nothing in the "
                  "system writes, so no export could contain them."),
            empty="Everything this screen can show is in this file.",
        )],
        intro=(
            "This file holds everything the system records. The things below are "
            "not recorded, so their absence does not mean they did not happen."
        ),
    )


# Re-exported so routes import their response helpers from the module they are
# exporting, the way the report routes do. The plumbing itself stays single.
from routes.report_export import (  # noqa: E402
    excel_response,
    exported_by,
    pdf_response,
)

__all__ = [
    "audit_document",
    "audit_workbook",
    "excel_response",
    "exported_by",
    "pdf_response",
    "PDF_MIMETYPE",
    "XLSX_MIMETYPE",
]
