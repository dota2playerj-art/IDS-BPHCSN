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
    # Export is planned, not impossible, and this now says which. It is held
    # back deliberately rather than being missing: the team took printing and
    # report generation first because those close the loop -- a health worker can
    # produce a dated, ranged sheet for the RHU today -- and a file writer is a
    # dependency and a download route on top of that. Naming what is missing
    # tells the next session what building it actually takes.
    "export": (
        "Export to a file is not built yet. It is planned as its own piece of "
        "work and needs two things this project does not have: a "
        "file-generation library in requirements.txt, and a download route to "
        "serve what it writes. Nothing about the figures is in the way -- they "
        "are read from the database on each load, and Print already puts this "
        "screen's report on paper over whatever range was generated, so the "
        "content an export would carry exists and is correct today."
    ),
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
