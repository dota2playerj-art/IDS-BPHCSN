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
Export is unavailable for one reason across six screens, and print for one
reason across the four that still have no print layout. Written into each
template, that is ten copies of two sentences, and the copies drift -- one
screen would end up claiming export was "not yet built" while another said it
was "planned for a later phase", for the same absent library.
inject_role_context() puts this dict on every render as `unavailable`, so a
screen states the reason by naming it.

Collecting them also means a reason can be corrected in one place when the
world changes. When printing was built for Patient Profile and Patient Records,
the print sentence had to stop saying the project had no print stylesheet; had
that claim been copied into eight templates, some of them would still be
saying it.

Kept apart from the per-screen UNTRACKED dicts in routes/*_views.py on purpose.
Those answer a different question -- why a *figure* has no source -- and are
specific to one screen's data. This answers why an *action* cannot be taken,
and the answers are shared.
"""

UNAVAILABLE = {
    # ---- File output --------------------------------------------------------
    "export": (
        "Export is not implemented. No screen in this project writes a CSV, "
        "Excel or PDF file: there is no file-generation library in "
        "requirements.txt and no download route to serve one. The figures on "
        "this screen are read from the database on each load, so exporting "
        "them is a reporting feature to be built, not a button to re-enable."
    ),
    # Printing is now real on Patient Profile and Patient Records, which opt in
    # by including templates/_print.html. This reason is what the screens that
    # have NOT been given a print layout still say, and it had to be rewritten
    # the day the first one was built: it used to open "There is no print
    # stylesheet", which stopped being true of the project the moment one
    # existed. A shared sentence is only worth having while it is accurate.
    "print": (
        "This screen has no print layout. Printing is built where a printed "
        "page is a document somebody keeps -- a patient's record and the "
        "patient list, both on Patient Records and Patient Profile -- and "
        "those two screens hide their navigation and controls for the printer. "
        "This one does not, so sending it to a printer would produce the "
        "sidebar, the header and the screen furniture along with the content. "
        "Giving it a usable printout means deciding what on it is worth "
        "keeping on paper, which is a design question, not a switch."
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
    "medicine_detail": (
        "There is no read-only detail screen for a stock item. Everything "
        "recorded about it is in this row and on the Add / Edit Medicine form, "
        "so a view action would open the same fields the Edit action already "
        "opens."
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
    "medicine_archive": (
        "Retiring a stock item is not implemented. Patients are archived "
        "through a dedicated endpoint with its own confirmation and audit "
        "entry; medicines have no such path yet, and a stock item that "
        "disappeared without one would take its batch and expiry history with "
        "it."
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
    "community_reports": (
        "This screen is not connected to a data source. Its figures and report "
        "list are written into the markup, so generating, opening or "
        "downloading one of them would produce nothing. The reporting that is "
        "real lives on Reports & Analytics, Health Programs and Vaccination "
        "Campaigns."
    ),
}
