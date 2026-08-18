"""Why a control on a screen cannot do its job.

Every entry here is the tooltip on a control that is rendered `disabled`. The
rule this file serves is the one User Management set for Add / Edit User and
that the rest of the system now follows:

    a control either works, or it is visibly disabled and says why.
    It is never left looking live while silently doing nothing when clicked.

A dead button is worse than a missing one. It teaches an operator that the
system is unreliable, and in a defence it is the first thing a panel finds by
clicking. Naming the specific missing piece -- a library, a table, a route --
also tells the next session what building it would actually take, which
"Coming soon" does not.

WHY THESE LIVE HERE AND NOT IN EACH TEMPLATE
--------------------------------------------
Export is unavailable for one reason across the four screens that still offer
it, and print for one reason across the screens that have no print layout.
Written into each template, that is a dozen copies of two sentences, and the
copies drift -- one screen would end up claiming export was "not yet built"
while another said it was "planned for a later phase", for the same absent
library.
inject_role_context() puts this dict on every render as `unavailable`, so a
screen states the reason by naming it.

Collecting them also means a reason can be corrected in one place when the
world changes. When printing was built for Patient Profile and Patient Records,
the print sentence had to stop saying the project had no print stylesheet; had
that claim been copied into eight templates, some of them would still be
saying it. The same thing has now happened to export: Export Excel is real on
the two report screens, so the shared sentence claiming the project had no
file-generation library had to go before the screens still quoting it started
lying about a dependency that is now installed.

A REASON CAN SPLIT, AND THEN GO
-------------------------------
"export" used to cover Export Excel and Export PDF together, which was correct
while neither existed. Excel became real on the report screens and PDF did not,
so one sentence would have had to be false about one of the two. It split into
"export" -- the screens that have no export of any kind -- and "export_pdf",
which the two report screens quoted beside a working Export Excel.

"export_pdf" is now gone as well. Export PDF became real on both report screens --
fpdf2 is a dependency and each screen has its own export.pdf route beside its
export.xlsx one -- so the two templates that quoted the reason stopped quoting it,
and a reason with nothing quoting it is exactly the drift this file exists to
prevent. It went the way "community_reports" did below: deleted once true of
nothing, rather than left sitting here describing a state the application has
left. This is the whole life of a shared reason -- born when the gap is real,
split when the gap is real for one control and not another, deleted when the gap
closes -- and one file is where all three happen so none of them is missed.

A reason can also split because it is aimed at the wrong *scope* rather than
because it became false. "print" is a sentence about a screen, and it was being
quoted by the print icon on a Medicine Inventory row -- a control offering to
print one item, answered by a paragraph about the sidebar. "medicine_print" now
says what actually stops that button, and "print" keeps the screens it was
written for. Nothing about it had gone false; it was simply answering a question
the control was not asking.

Kept apart from the per-screen UNTRACKED dicts in routes/*_views.py on purpose.
Those answer a different question -- why a *figure* has no source -- and are
specific to one screen's data. This answers why an *action* cannot be taken,
and the answers are shared.
"""

UNAVAILABLE = {
    # ---- File output --------------------------------------------------------
    # THIS SENTENCE HAS BEEN REWRITTEN BECAUSE THE WORLD CHANGED, WHICH IS THE
    # WHOLE REASON THE REASONS LIVE IN ONE FILE.
    # It used to say export needed two things the project did not have, "a
    # file-generation library in requirements.txt, and a download route to serve
    # what it writes". Both now exist -- openpyxl is a dependency and the two
    # report screens each have an export.xlsx route -- so that claim would be
    # false on the six screens still quoting it. What is actually missing on
    # those six is different and is what this now names: nobody has decided what
    # a spreadsheet of a *roster* should contain.
    #
    # The two report screens do not quote this any more. Their Export Excel is a
    # working link, and a control that works carries no reason at all.
    "export": (
        "Export is not built for this screen. The machinery exists -- openpyxl "
        "and fpdf2 are dependencies, and Reports & Analytics and Community "
        "Reports each download a real spreadsheet and a real PDF of their "
        "figures -- so what is missing here is not a library or a route. It is "
        "the decision about what an export of this screen's rows should hold: "
        "which columns, which rows when the table is filtered, and what a reader "
        "is meant to do with the file. A report has one obvious answer to that "
        "and a working list does not, which is why the report screens were taken "
        "first."
    ),
    # THERE IS NO "export_pdf" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said Export PDF was not built while it was not. Export PDF is now real on
    # both report screens -- fpdf2 is a dependency and each screen has its own
    # export.pdf route -- so the two templates that quoted it stopped, and a reason
    # with nothing quoting it is the drift this file exists to prevent. It goes,
    # exactly as "community_reports" went below. See the module docstring.
    # Printing is real on four screens now -- Patient Profile, Patient Records,
    # Reports & Analytics and Community Reports -- each opting in by including
    # templates/_print.html. This reason is what the screens that have NOT been
    # given a print layout still say, and it has now been rewritten twice: it
    # opened "There is no print stylesheet" until the first one was built, and
    # named only the two patient screens until the two report screens joined
    # them. A shared sentence is only worth having while it is accurate.
    "print": (
        "This screen has no print layout. Printing is built where a printed "
        "page is a document somebody keeps or sends -- a patient's record and "
        "the patient list on Patient Profile and Patient Records, and a dated, "
        "ranged report on Reports & Analytics and Community Reports -- and "
        "those four screens hide their navigation and controls for the printer "
        "and put a letterhead on top. This one does not, so sending it to a "
        "printer would produce the sidebar, the header and the screen "
        "furniture along with the content. Giving it a usable printout means "
        "deciding what on it is worth keeping on paper, which is a design "
        "question, not a switch."
    ),
    # A SHARED REASON CAN ALSO BE THE WRONG *SCOPE*, NOT MERELY WRONG.
    # The print icon on a Medicine Inventory row used to quote "print" above, and
    # that sentence is true -- Screen 06 has no print layout -- but it answers a
    # question about the whole screen while sitting on a control that offers to
    # print one item. Patient Records' row-level print icon does not print its
    # row; it opens that patient's own page with ?print=1, because the record is
    # the page. Medicine Inventory has no per-item page for the equivalent link to
    # point at, and that -- not the missing screen stylesheet -- is what actually
    # stops this button. So it says so itself.
    "medicine_print": (
        "There is nothing to print one item from. Where printing a single record "
        "is built, the row does not print itself: the print icon on a Patient "
        "Records row opens that patient's own page and sends that to the "
        "printer, because the patient's record is a page that already exists. A "
        "stock item has no page of its own -- Edit is a form, not a record -- so "
        "there is no equivalent to link to here, and a printed copy of one table "
        "row is not a document anybody would keep. This waits on the same "
        "decision the View action does."
    ),

    # ---- Table controls -----------------------------------------------------
    "sort": (
        "Column sorting is not implemented. The rows arrive in the order the "
        "query returns them, which each screen states beside its table. A "
        "sort control also has to say what it sorts by, and this one never "
        "did -- it is a menu that was never built, not a setting that was lost."
    ),
    "pagination": (
        "Paging is not implemented. Every row the query returns is already on "
        "this page, so there is no second page to turn to. The page numbers "
        "that used to sit here were markup -- they counted a roster this "
        "system does not hold."
    ),

    # ---- Records ------------------------------------------------------------
    # REWRITTEN: the old sentence claimed "everything recorded about it is in
    # this row", which was false. Eight stored fields -- item code, brand name,
    # date received, batch number, manufacturer, unit cost, storage location and
    # notes -- appear in no template but add_edit_medicine.html. Reading any of
    # them means opening the editable form, which is the exact complaint the
    # read-only View on Consultation History was built to answer.
    "medicine_detail": (
        "There is no read-only detail screen for a stock item, and no route that "
        "would serve one. The row beside this button does not show everything "
        "the record holds either: its item code, brand name, date received, "
        "batch number, manufacturer, unit cost, storage location and notes are "
        "stored, but appear nowhere except the Add / Edit Medicine form. So "
        "reading those means opening the form that can also change them. What is "
        "undecided is whether a stock item should get its own screen, or the "
        "treatment Consultation History uses -- a read-only panel that expands "
        "in place, needing no new route or template."
    ),
    "save_and_another": (
        "Save & Register Another is not implemented. Saving already redirects "
        "to the new patient's profile, which is where the duplicate check and "
        "the check-in and booking hand-offs land; returning to a blank form "
        "instead is a second outcome for the registration POST, and that write "
        "path is not being changed for a convenience shortcut. Use Register "
        "Patient again from the sidebar."
    ),
    "appointment_detail": (
        "There is no separate view for one appointment. Everything the booking "
        "records -- its date, time, service, assigned staff, status and notes "
        "-- is already in this row, so opening it would repeat the row."
    ),
    # REWRITTEN, AND IT WAS THE FALSEST SENTENCE IN THIS FILE.
    # It said "retiring a stock item is not implemented" while inventory_items
    # has carried a status flag since the first schema, and the Add / Edit
    # Medicine form has offered Active / Inactive on it all along. It also said
    # patients are archived with "its own confirmation and audit entry" -- the
    # confirmation dialog is real, but no audit entry is written for a patient
    # archive either; log_action() is called from two places in this project and
    # neither is that one. Holding medicines to a bar the feature it cites does
    # not clear is how a reason ends up arguing against building something for a
    # standard nothing meets.
    # And "would take its batch and expiry history with it" described a loss that
    # could not happen: retiring is an UPDATE, nothing is deleted, and there is no
    # batch or expiry history to lose -- inventory_items holds one batch number
    # and one expiry date per row and there is no history table.
    "medicine_archive": (
        "The status this would set already exists, and this button is not what "
        "sets it. An item is Active or Inactive, the Add / Edit Medicine form "
        "offers both, and an Inactive item is badged Retired in the table below, "
        "left out of all four cards above it, and left out of every low-stock "
        "figure in the system. What is missing is only the shortcut: patients "
        "have a dedicated archive endpoint and a confirmation dialog that names "
        "the record and offers just the statuses it can legally move to, and "
        "medicines have neither, so retiring one means opening Edit and changing "
        "the status there. Nothing is lost by that route -- it is the same "
        "single field either way."
    ),

    # ---- Whole screens with no data source ---------------------------------
    "settings": (
        "Settings are not stored. There is no settings table and no route that "
        "reads or writes one, so nothing typed on this screen is saved and "
        "nothing on it is read by the running system. The values shown are the "
        "defaults the application is actually built with."
    ),
    "backup": (
        "Backup and restore are not implemented. The database is a single "
        "SQLite file and the project's real backup practice is a dated copy of "
        "it taken outside the application; doing it from this screen needs a "
        "job that can safely quiesce and copy an open database."
    ),
    "sms_gateway": (
        "The SMS gateway is simulated. utils/sms.py records a broadcast and "
        "its recipients without contacting a provider, so there is no "
        "connection to test and no credential in use. Screen 09 states the "
        "same thing beside the composer."
    ),
    "notifications": (
        "There is no notifications table. Nothing in this system writes, "
        "stores or clears a notification, so marking one read or dismissing it "
        "would change only what this browser is showing until the next reload. "
        "Recorded activity lives on Audit Logs, and community messages on "
        "SMS Notifications."
    ),
    # THERE IS NO "community_reports" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It has been deleted twice over. It first said Community Reports had no
    # data source, which stopped being true when the screen was wired to real
    # queries; it was rewritten to say report generation was not implemented,
    # and that stopped being true when Generate was built. Nothing on that
    # screen is disabled for a screen-specific reason now -- its Print works,
    # its Generate works, and its two Export buttons quote the shared `export`
    # reason above like every other screen's do.
    #
    # A reason with nothing quoting it is exactly the drift this file exists to
    # prevent, so it goes rather than sitting here describing a state the
    # application has left. If some future control needs a Community Reports
    # reason, it writes a true one.
}
