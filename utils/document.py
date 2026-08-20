"""Writing a .pdf report, with no knowledge of what is in it.

The mechanics only: a paginated document with a running letterhead and footer, a
section per part, headed tables, wrapped explanatory notes, and the one house
style they are drawn in. What the numbers *are* belongs to the modules that
assemble them -- routes/report_export.py, routes/audit_export.py and
routes/roster_export.py; this module would lay out a document of anything.

WHY THIS IS THE TWIN OF utils/workbook.py
-----------------------------------------
workbook.py turns a list of sheet dictionaries into a .xlsx file. This turns the
*same* list of sheet dictionaries into a .pdf file. An export module assembles
those dictionaries once -- a cover, the sheets that screen is made of, and a "not
tracked" sheet -- and hands the identical structure to either writer. A figure
cannot read one way in the spreadsheet and another on the printout, because there
is one assembly and two renderers, not two assemblies. That is the same rule the
rest of the project reports under, carried up one level: not "one query, every
screen" but "one report, every file".

A `sheet` is {"title", "heading", "intro", "blocks"}. A `block` is the dict
`table()`/`figures()` build: {"kind", "title", "columns", "rows", "note",
"empty"}. This file reads those keys and knows nothing else about them.

WHY fpdf2
---------
It writes a real PDF offline -- nothing in it reaches the network, the constraint
this project is built under -- and its whole dependency set installs from
prebuilt wheels, so there is no compiler to run on a health center PC. Its API
maps almost one-to-one onto the document this needs: header() and footer() are
methods the library calls on every page, which is exactly where a letterhead and
a page number belong, and table() paginates a long table and repeats its heading
row on the next page on its own. The alternatives were weighed:

  * WeasyPrint would render the print stylesheet straight to PDF, which is
    tempting because templates/_print.html already exists. It is rejected for the
    same reason openpyxl was chosen over its heavier rivals: it needs the native
    GTK / Cairo / Pango stack, and getting that onto a Windows clinic machine is
    precisely the "wheel-for-your-platform problem" this project avoids.
  * reportlab is the other serious candidate and would also do the job, but it is
    a heavier dependency that bundles a compiled accelerator, and this report
    needs nothing its Platypus flowables provide that fpdf2's table() and
    multi_cell() do not.

fpdf2 itself is pure Python, though it declares Pillow -- which is compiled -- for
image handling. This report embeds no images, but the dependency is still pulled
in, so the honest claim is "installs from wheels, runs offline", not "pure
Python all the way down". That is a weaker claim than openpyxl's and is stated as
the weaker one.

CHARTS ARE ALREADY TABLES
-------------------------
There is no charting here and none is wanted. Every chart on the two report
screens already carries a table of its own numbers for the printer
(templates/_chart_table.html), and report_export.py turned those same series into
`table` blocks for the workbook. The PDF renders those blocks, so the reader gets
the numbers behind every chart -- the same numbers the screen plots and the
spreadsheet lists.
"""
from datetime import date, datetime

from fpdf import FPDF
from fpdf.enums import TableCellFillMode
from fpdf.fonts import FontFace

# application/pdf is what a browser needs to hand the file to a PDF reader rather
# than showing it as a download of unknown type.
PDF_MIMETYPE = "application/pdf"

# 02_UI_DESIGN_SYSTEM's teal, so an exported document is recognisably from the
# same system as the screen it was taken off -- and the same teal utils/workbook.py
# fills a header row with, so the PDF and the spreadsheet of one report match.
# A PDF always paints its fills, so unlike the print stylesheet (which redraws
# headers as underlined text because browsers drop backgrounds from a printout)
# this can use the fill directly.
_TEAL = (22, 155, 146)
_TEAL_DARK = (15, 110, 86)
_MUTED = (107, 114, 128)
_RULE = (17, 24, 39)
_HAIRLINE = (209, 213, 219)
_INK = (0, 0, 0)
_WHITE = (255, 255, 255)

# What an absent figure is written as -- the em dash utils/workbook.py and
# utils/dates.py use, so a blank reads the same in the document as on the screen
# and in the spreadsheet, and is never written as 0, which would be a claim.
MISSING = "—"

# A4, matching templates/_print.html's @page. Margins wide enough to punch and
# file.
#
# PORTRAIT IS THE DEFAULT AND LANDSCAPE IS AN ARGUMENT, NOT A SECOND RENDERER.
# A report is a page of prose and two- or three-column tables and belongs on a
# portrait sheet, which is what _print.html puts it on. A roster does not: a
# patient row is eight columns and a stock item is eleven, and eight columns
# inside A4 portrait's 182mm of usable width leaves each one about 22mm, which is
# narrow enough to break "PAT-016" across two lines inside its own cell. That is
# not a table anybody would file.
#
# utils/workbook.py already made this exact decision and made it unconditionally:
# every sheet it writes is set to landscape, fitToWidth 1, "so a sheet sent to a
# printer from Excel comes out on one page across rather than with its last
# column on a sheet of its own". This is the same judgement, exposed as a choice
# rather than forced, because unlike a spreadsheet a PDF has one shape and the
# report documents genuinely want the other one.
PORTRAIT = "portrait"
LANDSCAPE = "landscape"

_MARGIN = 14  # mm
_BOTTOM_MARGIN = 16  # mm, room for the footer

# Column-width bounds, as relative weights before fpdf2 scales them to the page.
_MIN_WEIGHT, _MAX_WEIGHT = 6, 42

# The core PDF fonts encode text as cp1252 (WinAnsi). That covers the Latin script
# these records are in -- including the em dash, the typographic quotes the notes
# use, and the accented letters a Filipino or Spanish name carries -- but a stray
# character outside it would raise mid-render. Rather than embed a Unicode font
# file (an asset to ship and keep) the few characters that do not survive are
# folded to a plain equivalent, so a document is produced rather than an
# exception, and a name is at worst approximated rather than lost.
_FOLD = {
    "–": "-", "—": "—", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "•": "·",
    " ": " ",
}


def _text(value):
    """A string the core-font encoder will accept, folding what it will not."""
    folded = "".join(_FOLD.get(character, character) for character in str(value))
    try:
        folded.encode("cp1252")
    except UnicodeEncodeError:
        folded = folded.encode("cp1252", "replace").decode("cp1252")
    return folded


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _cell(value):
    """What actually goes in a table cell.

    None becomes the em dash rather than a blank or a zero: an absent figure and a
    figure of nought are different claims, and this project states the difference
    everywhere else it reports one. Numbers get a thousands separator, matching the
    spreadsheet's cell format, so the two files read the same figure the same way.
    """
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.1f}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return _text(value)


class _Report(FPDF):
    """One report document. The letterhead and footer ride every page.

    A printed report leaves the building, so each page identifies where it came
    from, which report it is, who took it off the system and when -- the same
    provenance templates/_print.html puts on a printout, made per-page here
    because a PDF can be split and a loose page still has to say what it is.
    """

    def __init__(self, org, org_sub, doc_title, range_label, footer_left,
                 orientation=PORTRAIT):
        super().__init__(orientation=orientation, unit="mm", format="A4")
        # The core fonts are written with WinAnsi (cp1252), not the library's
        # default latin-1. cp1252 is the difference between an em dash, a
        # typographic quote and an ellipsis rendering and raising -- the note prose
        # uses all three, and the em dash is the mark this project writes for an
        # absent figure. Everything _text() lets through is cp1252, so the two
        # agree and nothing reaches the encoder that it cannot write.
        self.core_fonts_encoding = "cp1252"
        self.org = _text(org)
        self.org_sub = _text(org_sub)
        self.doc_title = _text(doc_title)
        self.range_label = _text(range_label)
        self.footer_left = _text(footer_left)
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        self.set_auto_page_break(True, margin=_BOTTOM_MARGIN)
        self.set_title(_text(f"{doc_title} - {org}"))

    def header(self):
        top = self.get_y()
        inner = self.epw  # effective page width, between the margins
        right_w = inner * 0.5
        # Left: the clinic. Right: which report, and the days it counts.
        self.set_xy(_MARGIN, top)
        self.set_text_color(*_INK)
        self.set_font("Helvetica", "B", 12.5)
        self.cell(inner - right_w, 6, self.org)
        self.set_xy(_MARGIN + inner - right_w, top)
        self.set_font("Helvetica", "B", 10.5)
        self.multi_cell(right_w, 5, self.doc_title, align="R")
        left_after = top + 6
        self.set_xy(_MARGIN, left_after)
        self.set_text_color(*_MUTED)
        self.set_font("Helvetica", "", 7.5)
        self.cell(inner - right_w, 4, self.org_sub)
        self.set_xy(_MARGIN + inner - right_w, self.get_y())
        self.multi_cell(right_w, 4, self.range_label, align="R")
        # A rule under the letterhead, like _print.html's 2px border-bottom.
        bottom = max(left_after + 4, self.get_y()) + 1.5
        self.set_draw_color(*_RULE)
        self.set_line_width(0.5)
        self.line(_MARGIN, bottom, self.w - _MARGIN, bottom)
        # Back to the left margin: the right-aligned multi_cell above leaves the
        # cursor at the right edge, and the body writes full-width from here.
        self.set_xy(_MARGIN, bottom + 4)
        self.set_text_color(*_INK)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*_HAIRLINE)
        self.set_line_width(0.2)
        self.line(_MARGIN, self.get_y(), self.w - _MARGIN, self.get_y())
        self.ln(1)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*_MUTED)
        half = self.epw / 2
        self.cell(half, 6, self.footer_left)
        self.cell(half, 6, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_color(*_INK)


# ---------------------------------------------------------------------------
# Rendering the shared sheet/block structure
# ---------------------------------------------------------------------------

def render(sheets, org, org_sub, doc_title, range_label, footer_left,
           orientation=PORTRAIT):
    """The list of sheet dicts, as the bytes of a real .pdf file.

    The first sheet is the cover: its heading is the clinic's name, which already
    rides the page as the letterhead, so it is not repeated as a section title --
    its intro is set as the document's opening paragraph and its blocks follow.
    Every later sheet is a section with its own ruled title. This is the one place
    the renderer treats a sheet by its position, and it is the same convention
    workbook.py follows: the first sheet is the cover.

    `orientation` is PORTRAIT unless a caller asks otherwise. It changes the page
    and nothing else -- the same sheets, the same blocks, the same styling, laid
    out across a wider line -- so a document does not become a different document
    by being turned sideways. See the constant's own note above for when a caller
    should ask.
    """
    pdf = _Report(org, org_sub, doc_title, range_label, footer_left, orientation)
    pdf.set_auto_page_break(True, margin=_BOTTOM_MARGIN)
    pdf.add_page()

    for index, spec in enumerate(sheets):
        if not spec:
            continue
        if index == 0:
            _intro(pdf, spec.get("intro"), lead=True)
        else:
            _section_title(pdf, spec["heading"])
            _intro(pdf, spec.get("intro"))
        for block in spec["blocks"]:
            if block:
                _block(pdf, block)

    return bytes(pdf.output())


def _section_title(pdf, text):
    # A section starts its own page when little of this one is left, so a heading
    # is never stranded at the foot of a page above the table it introduces.
    if pdf.will_page_break(22):
        pdf.add_page()
    else:
        pdf.ln(3)
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_TEAL_DARK)
    pdf.cell(0, 7, _text(text))
    pdf.ln(8)
    y = pdf.get_y() - 2
    pdf.set_draw_color(*_RULE)
    pdf.set_line_width(0.4)
    pdf.line(_MARGIN, y, pdf.w - _MARGIN, y)
    pdf.set_text_color(*_INK)
    pdf.ln(1)


def _intro(pdf, text, lead=False):
    if not text:
        return
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "" if lead else "I", 9 if lead else 8.5)
    pdf.set_text_color(*(_INK if lead else _MUTED))
    for paragraph in str(text).split("\n"):
        pdf.set_x(_MARGIN)
        pdf.multi_cell(0, 4.6, _text(paragraph), align="L")
    pdf.set_text_color(*_INK)
    pdf.ln(2)


def _block(pdf, block):
    if block.get("kind") == "note":
        _note(pdf, block.get("text"))
        return

    columns = block["columns"]
    rows = block["rows"]

    # Reserve enough room that a block's title and note do not print at the foot of
    # a page with the table pushed to the next -- keep the label with what it labels.
    if pdf.will_page_break(26):
        pdf.add_page()

    if block.get("title"):
        pdf.set_x(_MARGIN)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(0, 5.5, _text(block["title"]), align="L")
        pdf.ln(0.5)

    if block.get("note"):
        _note(pdf, block["note"])

    if not rows:
        pdf.set_x(_MARGIN)
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(0, 4.6, _text(block.get("empty") or ""), align="L")
        pdf.set_text_color(*_INK)
        pdf.ln(2)
        return

    numeric = _numeric_columns(columns, rows)
    aligns = tuple("RIGHT" if flag else "LEFT" for flag in numeric)
    weights = _weights(columns, rows)

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*_INK)
    headings_style = FontFace(emphasis="BOLD", color=_WHITE, fill_color=_TEAL)
    with pdf.table(
        borders_layout="HORIZONTAL_LINES",
        headings_style=headings_style,
        cell_fill_color=(247, 249, 249),
        cell_fill_mode=TableCellFillMode.ROWS,
        col_widths=weights,
        text_align=aligns,
        first_row_as_headings=True,
        repeat_headings=1,
        line_height=5.2,
        width=pdf.epw,
    ) as table:
        head = table.row()
        for name in columns:
            head.cell(_text(name))
        for data in rows:
            line = table.row()
            for index in range(len(columns)):
                value = data[index] if index < len(data) else None
                line.cell(_cell(value))
    pdf.ln(3)


def _note(pdf, text):
    if not text:
        return
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(*_MUTED)
    for paragraph in str(text).split("\n"):
        pdf.set_x(_MARGIN)
        pdf.multi_cell(0, 4.4, _text(paragraph), align="L")
    pdf.set_text_color(*_INK)
    pdf.ln(1)


def _numeric_columns(columns, rows):
    """A column is a number column when its first filled cell is a number.

    The same test workbook.py makes, so a column that is right-aligned in the
    spreadsheet is right-aligned in the document.
    """
    numeric = []
    for index in range(len(columns)):
        first = None
        for data in rows:
            if index < len(data) and data[index] is not None:
                first = data[index]
                break
        numeric.append(_is_number(first))
    return numeric


def _weights(columns, rows):
    """Relative column widths from the longest cell in each column.

    Mirrors workbook.py's autosize: a label column earns more width than a column
    of short counts, bounded so one long entry cannot starve the rest. fpdf2 scales
    these to the page width.
    """
    weights = []
    for index in range(len(columns)):
        longest = len(str(columns[index]))
        for data in rows:
            if index < len(data):
                longest = max(longest, len(_cell(data[index])))
        weights.append(min(_MAX_WEIGHT, max(_MIN_WEIGHT, longest)))
    return tuple(weights)
