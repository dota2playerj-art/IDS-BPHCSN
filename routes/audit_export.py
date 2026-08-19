"""Export Excel and Export PDF, for Screen 12's audit trail.

The Export control on Audit Logs presses this. It reads routes/audit_views'
audit_export_context(), which decorates rows through the same _decorate() the
screen renders from, so an entry cannot read one way in the table and another in
the file.

ONE ASSEMBLY, TWO FILES
-----------------------
The same arrangement routes/report_export.py uses, and for the same reason:
_assemble() builds one list of sheet dicts and hands the identical structure to
either renderer -- utils/workbook.build() writes it as .xlsx,
utils/document.render() writes it as .pdf. The two files cannot disagree about an
entry because there is one assembly and two renderers. The response plumbing is
imported from report_export rather than repeated, so every download this project
serves gets its attachment header and its filename decided in one place.

WHY BOTH FORMATS, ON A SCREEN THAT IS ONE FLAT TABLE
----------------------------------------------------
They answer different questions and both get asked of an audit trail. The PDF is
the artifact somebody files or submits: a paginated document with the health
centre on every page and a footer saying who took it off the system and when, so
a loose sheet still says what it is. The spreadsheet is what somebody sorts,
filters and hands to a reviewer who wants to look down the User column. Neither
substitutes for the other, and because the assembly is shared, the second format
costs one route rather than a second implementation. Both report screens already
offer both, so offering one here would be the odd screen out for no reason a
reader could infer.

WHAT THE FILE COVERS, AND THE ONE THING IT CANNOT
-------------------------------------------------
Every entry matching the module filter, not the page of them the screen shows.
Screen 12 caps its table at PAGE_SIZE and says so in its footer; a downloaded
audit trail that silently stopped at the hundredth entry would be the worst place
in this system for a quiet omission, because the file's whole claim is that it is
the complete record. get_audit_logs(limit=None) is what that cap being absent
looks like, and the cover sheet states the count so a reader can check it against
the screen.

The module filter is honoured because it is a real server-side filter: Screen 12
submits it as ?module= and the export route reads the same query string, so the
button exports the trail the operator is looking at.

The search box is not, and cannot be. It narrows rows in the browser -- the same
constraint templates/_print.html documents for Patient Records -- so the server
never learns what was typed. Rather than invent a way to smuggle it across, the
cover sheet says plainly that the file holds every entry for the module filter
and that any search typed on the screen was not applied. That is the resolution
this project already uses for the same problem, not a new one.

WHAT IS DELIBERATELY IN IT
--------------------------
The "not tracked" notes, on their own final sheet, exactly as report_export.py
puts them on its own. The trail's most important property is what it does *not*
record -- no logins, no failed attempts, no patient or stock writes -- and a file
that left that out would let a reader take the entries it holds for the whole of
what the system does. Those reasons are looked up from audit_views.UNTRACKED, so
the file and the screen state them in one wording.
"""
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
    footer_left = f"IDS-BPHCSN · Exported {exported}"
    if produced_by:
        footer_left += f" by {produced_by}"

    payload = render(
        sheets,
        org="Barangay Poblacion Health Center",
        org_sub="Integrated Data System (IDS-BPHCSN)",
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
    stem = f"IDS-BPHCSN Audit Logs {scope} {now().strftime('%Y-%m-%d')}"
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
        ("Source", "Barangay Poblacion Health Center records, via IDS-BPHCSN"),
    ]

    scope = [
        [
            "Every entry, not one page of them",
            f"Audit Logs shows the {PAGE_SIZE} most recent entries at a time. This "
            f"file holds all {total} matching the module filter above, so it is the "
            "complete record rather than the page that was on screen.",
        ],
        [
            "A search typed on the screen was not applied",
            "The search box on Audit Logs narrows rows in the browser, so the "
            "server is never told what was typed. This file is filtered by module "
            "only. If it should cover less, set the module filter and export again.",
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
        heading="Barangay Poblacion Health Center",
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
                note=("The # column is the entry's number in the table above. What "
                      "each entry recorded is written here in full, exactly as it "
                      "is stored — nothing is shortened, because this column "
                      "is the record of what actually changed."),
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
    this file is the complete record needs, in the same breath, to know that the
    record covers three write paths and not the whole system -- otherwise the
    absence of a patient-archive entry reads as nobody having archived a patient.

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
            "The entries in this file are complete for what the system records, "
            "which is the consultation edit path, the SMS broadcast path and the "
            "login route. It does not record the following, so their absence from "
            "the trail is not evidence that they did not happen."
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
