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
because it became false. "print" was a sentence about a screen, and it was being
quoted by the print icon on a Medicine Inventory row -- a control offering to
print one item, answered by a paragraph about the sidebar. "medicine_print" now
says what actually stops that button. Nothing about "print" had gone false; it
was simply answering a question the control was not asking.

And then "print" went entirely, which is the other half of this file's rule. Its
last two citations were the print icons on Appointment Scheduling, and those are
now working links into the patient's own profile. A shared reason is worth having
while something quotes it and not one commit longer, so it was deleted rather
than left describing screens that no longer ask.

A REASON CAN ALSO BE MOSTLY RIGHT, WHICH IS THE HARDEST CASE
------------------------------------------------------------
"settings" was rewritten a second time over a single word. It said nothing on
that screen is "stored or read". Stored was and is correct; read stopped being
correct the moment the Security Settings pane began reporting live counts of
sign-ins from the audit trail. A reason that is 95% true is more dangerous than
one that is plainly false, because nobody re-reads it -- and this one was the
sentence telling readers that every figure on the screen was inert, sitting
directly above the one figure that was not. The lesson this file keeps learning
is that the reasons have to be re-read whenever anything they describe is built,
not only when they collapse outright.

The three per-screen reasons that went false in the same change are not here,
because they are not shared: Audit Logs' "logins" and "security" and User
Management's "last_login" all lived in their own routes/*_views.py UNTRACKED
dicts, and were deleted or narrowed there. That split is the point of the
paragraph below.

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
    # THERE IS NO "print" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It said a screen had no print layout, and it was true of every screen that
    # quoted it, right up to the last one. Its last two citations were the print
    # icons on Appointment Scheduling's two tables, and those are now working
    # links: printing from a booking opens that patient's profile with ?print=1,
    # the same answer Patient Records gives for its own rows. Nothing quotes this
    # any more, and a reason with nothing quoting it is exactly the drift this
    # file exists to prevent -- so it goes, the way "export_pdf" and
    # "community_reports" went. See the module docstring.
    #
    # The screens that print now do so because they include templates/_print.html.
    # A screen that wants a print layout and has not got one writes a true reason
    # for its own control, which is what "medicine_print" below is.

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
    # THE SECOND SENTENCE HERE IS A CLAIM ABOUT THE TEMPLATES, AND IT WAS ONLY
    # TRUE OF ONE OF THE THREE SCREENS THAT QUOTE IT.
    # Appointment Scheduling's queue has always said "in arrival order, patients
    # in consultation first". Patient Records and Medicine Inventory stated no
    # order anywhere, though both are alphabetical -- ORDER BY last_name and
    # ORDER BY name COLLATE NOCASE. Rather than split one correct sentence into
    # three per-screen ones, the two screens were given the line they were
    # missing, so the claim below is now true wherever it is quoted. If a fourth
    # screen ever quotes this, it owes its reader the same sentence in its footer.
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
    # REWRITTEN: the old sentence listed "notes" among the fields "already in
    # this row". The Appointment History table on Patient Profile has five
    # columns before its actions -- Date, Time, Purpose, Assigned To, Status --
    # and notes is not one of them. Same defect medicine_detail had: a list of
    # fields that quietly included one the screen does not show.
    "appointment_detail": (
        "There is no separate view for one appointment. What the booking records "
        "is almost all in this row already -- its date, time, purpose, assigned "
        "staff and status -- so a detail view would mostly repeat the row it "
        "opened from. What it would add is the booking's notes, which this table "
        "has no column for; those are shown on Appointment Scheduling, under the "
        "patient's name on the same booking."
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
    # REWRITTEN ONCE: "There is no settings table" was false. schema.sql defines
    # one -- setting_key, setting_value, updated_by, updated_at -- and has since
    # the first schema. What is true is the half that follows: nothing reads or
    # writes it. Naming the wiring as the gap rather than the table is the same
    # correction medicine_archive needed, and for the same reason: a reason that
    # denies an existing structure sends the next session off to build something
    # that is already there.
    #
    # REWRITTEN AGAIN, AND THIS TIME BECAUSE ONE WORD IN IT HAD GONE FALSE.
    # It opened "Nothing on this screen is stored or read". The first half is
    # still exactly true -- the settings table is still empty and no route writes
    # it -- but the second stopped being true when routes/auth.py started
    # recording sign-ins: the Security Settings pane now reads live counts of
    # them from the audit trail (routes/settings_views.py). One word wrong in a
    # shared reason is the whole hazard this file exists for, and it was the
    # worst word to be wrong here, because this sentence is what tells a reader
    # that every figure on the screen is inert. A reader who checked the one
    # block that is live would have found the reason lying about it.
    #
    # Note the asymmetry that survives, because it is the real state: nothing on
    # this screen is *stored*, and exactly one block on it is *read*. The
    # disabled fieldset over every input is unchanged and still correct.
    "settings": (
        "Nothing typed on this screen is stored. The settings table exists in "
        "schema.sql -- setting_key, setting_value, updated_by, updated_at, ready "
        "for exactly this -- but no model function and no route writes to it, so "
        "the gap is the wiring rather than the place to put the values. Nothing "
        "entered here is saved, and no setting shown here is read by the running "
        "system: the values are the defaults the application is actually built "
        "with, which is why they are shown at all. The one exception is stated "
        "where it sits -- the Security Settings pane reports live counts of "
        "sign-ins and refused sign-ins from the audit trail, which are records "
        "of what happened rather than settings that were chosen."
    ),
    "backup": (
        "Backup and restore are not implemented. The database is a single "
        "SQLite file and the project's real backup practice is a dated copy of "
        "it taken outside the application; doing it from this screen needs a "
        "job that can safely quiesce and copy an open database."
    ),
    # REWRITTEN: THIS ONE HAD GONE FALSE, NOT MERELY IMPRECISE.
    # It said utils/sms.py records a broadcast "without contacting a provider",
    # and that there is "no connection to test and no credential in use". All
    # three claims describe a file that no longer exists. utils/sms.py is a real
    # Semaphore client: send_announcement_sms() posts to Semaphore's endpoint,
    # gateway_configured() reports whether a key is present, and
    # deliver_announcement_sms() chooses live or simulated per send by reading
    # SEMAPHORE_API_KEY from the environment. Its own docstring is headed
    # "TURNING THIS FEATURE LIVE" and says the feature is complete.
    # A reason that denies a working integration is the same defect as the one
    # medicine_archive had, and it was worse here: it was the stated grounds for
    # disabling a Test Connection button that now has something real to test.
    "sms_gateway": (
        "There is no API key configured, so there is nothing for these controls "
        "to act on. The integration itself is real and finished -- utils/sms.py "
        "posts to Semaphore's endpoint, and every send checks the "
        "SEMAPHORE_API_KEY environment variable to decide whether it goes on the "
        "wire or is recorded as simulated. Broadcasts are written to history "
        "either way, which is why SMS Notifications works today and marks its "
        "rows 'simulated'. Setting that variable is the whole activation step; "
        "nothing on this screen is part of it, because this screen stores "
        "nothing. A key revealed here would be a key this project never held, "
        "and a connection tested here would be testing the server's environment "
        "rather than anything typed above."
    ),
    # The last sentence points at Audit Logs for "recorded activity", and that
    # pointer got better rather than worse: the trail now holds sign-ins as well
    # as record edits and broadcasts, so a reader sent there for what the system
    # noticed finds more of it. Nothing here needed correcting -- it is listed in
    # this comment only because it was checked, and a reason that mentions
    # another screen's contents is exactly the kind that quietly goes stale.
    "notifications": (
        "There is no notifications table. Nothing in this system writes, "
        "stores or clears a notification, so marking one read or dismissing it "
        "would change only what this browser is showing until the next reload. "
        "Recorded activity lives on Audit Logs -- record edits, SMS broadcasts "
        "and sign-ins -- and community messages on SMS Notifications."
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
