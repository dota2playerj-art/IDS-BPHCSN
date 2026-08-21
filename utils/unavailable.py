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
Because one gap is usually several controls' problem, and one sentence written
into several templates is several sentences a month later. That was the case for
export across six screens and for print across the screens with no print layout;
both of those gaps have since closed, and the way they closed is the argument for
this file rather than against it. When export became real the claim about a
missing library was in one place, so it was corrected in one place -- and when the
last screen quoting it was wired, the reason was deleted in one place rather than
surviving in whichever templates nobody re-read.
inject_role_context() puts this dict on every render as `unavailable`, so a
screen states the reason by naming it.

Collecting them also means a reason can be corrected in one place when the
world changes. When printing was built for Patient Profile and Patient Records,
the print sentence had to stop saying the project had no print stylesheet; had
that claim been copied into eight templates, some of them would still be
saying it. The same thing then happened to export twice over: first when Export
Excel became real on the two report screens, so the shared sentence claiming the
project had no file-generation library had to go before the screens still quoting
it started lying about a dependency that is now installed -- and then again when
the last four screens were wired, at which point the sentence had nothing left to
be true about at all.

A REASON CAN SPLIT, AND THEN GO
-------------------------------
"export" is the entry that lived this whole arc, and it is now gone. It began
covering Export Excel and Export PDF together, which was correct while neither
existed. Excel became real on the report screens and PDF did not, so one sentence
would have had to be false about one of the two: it split into "export" -- the
screens with no export of any kind -- and "export_pdf", which the two report
screens quoted beside a working Export Excel.

"export_pdf" went first. Export PDF became real on both report screens -- fpdf2 is
a dependency and each screen has its own export.pdf route beside its export.xlsx
one -- so the two templates that quoted the reason stopped quoting it, and a reason
with nothing quoting it is exactly the drift this file exists to prevent. It went
the way "community_reports" did below: deleted once true of nothing, rather than
left sitting here describing a state the application has left.

"export" has now followed it. Patient Records, Medicine Inventory, Appointment
Scheduling and User Management each download a real spreadsheet and a real PDF
(routes/roster_export.py), which were the last four screens quoting it. What is
left behind is one narrower reason, "export_selection", for the one control that
is still genuinely absent -- the bulk bar's Export on Patient Records, which would
download the ticked records rather than the register. This is the whole life of a
shared reason: born when the gap is real, split when the gap is real for one
control and not another, narrowed when the general case closes and a specific one
does not, deleted when the last thing quoting it stops. One file is where all four
happen, so none of them is missed.

A reason can also split because it is aimed at the wrong *scope* rather than
because it became false. "print" was a sentence about a screen, and it was being
quoted by the print icon on a Medicine Inventory row -- a control offering to
print one item, answered by a paragraph about the sidebar. "medicine_print" was
written to say what actually stopped that button. Nothing about "print" had gone
false; it was simply answering a question the control was not asking.

And then "print" went entirely, which is the other half of this file's rule. Its
last two citations were the print icons on Appointment Scheduling, and those are
now working links into the patient's own profile. A shared reason is worth having
while something quotes it and not one commit longer, so it was deleted rather
than left describing screens that no longer ask.

A REASON CAN ALSO BE THE ARGUMENT FOR DELETING THE CONTROL
----------------------------------------------------------
"medicine_print" then went too, and not because it came true or false. It stayed
exactly as true as the day it was written -- a stock item has no page of its own,
and one printed table row is not a document -- and the row's print icon was
removed on the strength of it. That is the case this file had not met before: a
reason so specific that reading it back is enough to decide the control should
not exist, rather than that it is unfinished. The shelf on paper is Export PDF in
the toolbar, which is built. When a reason turns out to be a verdict, the honest
outcome is to remove the button and delete the sentence with it, not to leave a
permanently disabled icon explaining itself forever.

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

AND A REASON WITH ONLY ONE CITATION GOES THE SAME WAY
----------------------------------------------------
Nothing above is special to *shared* reasons. "medicine_detail" was quoted by
exactly one control -- the View icon on a Medicine Inventory row -- and it was
true and specific right up until View was built. It said the eight fields it
named were readable only through the editable form, and named the open
question: a screen of the item's own, or Consultation History's read-only panel
expanded in place. The panel was built, the button works, and the sentence was
deleted in the same commit rather than a later one. A reason outliving its gap
by even a commit is how this file starts lying, and a single citation is not a
reason to be gentler about it.

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
    # THERE IS NO "export" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It has been rewritten once and is now deleted, which is the whole life this
    # file's docstring describes. It first said export needed a file-generation
    # library and a download route, and that stopped being true when openpyxl and
    # fpdf2 landed and the report screens got their export.xlsx and export.pdf.
    # It was rewritten to name what was actually missing on the six screens still
    # quoting it: "the decision about what an export of this screen's rows should
    # hold -- which columns, which rows when the table is filtered, and what a
    # reader is meant to do with the file."
    #
    # That decision has now been taken, for all four screens that were left
    # quoting this. Patient Records, Medicine Inventory, Appointment Scheduling
    # and User Management each download a real spreadsheet and a real PDF -- the
    # columns are the ones their tables already show, the rows are the whole list
    # because these screens filter in the browser, and every file's cover sheet
    # says so outright rather than leaving a reader to assume it holds what was on
    # screen. See routes/roster_export.py.
    #
    # So nothing quotes this any more, and a reason with nothing quoting it is
    # exactly the drift this file exists to prevent. It goes the way "export_pdf",
    # "print" and "community_reports" went, rather than sitting here describing a
    # state the application has left.
    #
    # One control that used to quote it is still disabled, and it does not get
    # this sentence back -- it gets a true one of its own, immediately below. That
    # is the same split "print" made when a Medicine Inventory row icon needed a
    # reason about one item rather than about a whole screen.

    # A REASON CAN OUTLIVE ITS PARENT BY BEING NARROWER THAN IT.
    # The bulk bar on Patient Records offers Export beside Print and Change
    # Status, and it means something different from the toolbar's Export above
    # it: the ticked records, not the register. The shared reason would now be
    # false on this button -- export *is* built for this screen -- so what stops it
    # is written here instead, and it is neither a library nor a route.
    "export_selection": (
        "Exporting only the ticked records is not built. Export in the toolbar "
        "above is, and downloads the whole register; this button would download "
        "the selection, and the selection is the part that is missing. It is not "
        "that the browser cannot send it -- Change Status beside this posts the "
        "same ticked ids to the server already. It is that every download this "
        "project serves is a GET at a URL that can be bookmarked, re-fetched and "
        "read, and a file whose contents are decided by a list of primary keys in "
        "a query string is none of those things. Print beside this does export a "
        "selection, because printing prints what is on the page and needs no URL "
        "to carry it. Until that is settled: export the full roster and delete "
        "the rows you did not want, which is what a spreadsheet is for."
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
    # for its own control. "medicine_print" was that reason for a Medicine
    # Inventory row, and its tombstone is immediately below -- the control it
    # explained was removed rather than finished, which is the one outcome this
    # file's rule leaves implicit.

    # THERE IS NO "medicine_print" ENTRY ANY MORE, AND IT WENT A THIRD WAY.
    # Every other deletion in this file happened because the gap closed: the
    # feature was built and the reason stopped being true. This one was true to
    # the last line -- a stock item still has no page of its own, and a printed
    # copy of one table row still is not a document anybody would keep -- and the
    # button it explained was removed anyway, because that sentence was the
    # argument against the control existing at all rather than a note on
    # something worth finishing later.
    #
    # A reason this specific is worth re-reading as a verdict, not only as a
    # tooltip. It said the row has nothing to point at, that Edit is a form
    # rather than a record, and that View had already settled the "does an item
    # need a page?" question by expanding a read-only panel in place instead. All
    # three said the same thing: there is no single-item document here to print.
    # What the operator actually wants -- the shelf, on paper -- is Export PDF in
    # the toolbar above, which is built and dates and attributes the file it
    # produces. Patient Records keeps its print icon because the opposite is true
    # there: the record *is* a page, and printing it means printing that page.
    #
    # So the icon is gone from the row rather than sitting there disabled. This
    # file's rule is that a control either works or says why it cannot, and a
    # third case has always been implicit in it: a control that should not be on
    # the screen is removed, and its reason goes with it. Nothing quotes this any
    # more, which is the only test that matters here.

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
    # THERE IS NO "medicine_detail" ENTRY ANY MORE.
    # It was rewritten once and is now deleted, which is the arc the module
    # docstring describes. Its first version claimed "everything recorded about
    # it is in this row"; that was false, and the rewrite said so plainly --
    # eight stored fields (item code, brand name, date received, batch number,
    # manufacturer, unit cost, storage location and notes) appeared in no
    # template but add_edit_medicine.html, so reading any of them meant opening
    # the form that can also change them.
    #
    # The rewrite also named the one thing left undecided: whether a stock item
    # should get a screen of its own, or the treatment Consultation History
    # uses -- a read-only panel that expands in place, needing no new route or
    # template. That decision has been taken, and it went the second way. The
    # View icon on a Medicine Inventory row now opens exactly such a panel, built
    # from the same info-grid classes the consultation panel uses, showing all
    # eight of those fields beside the ones the row already shows. The route
    # count is unchanged, because no route was needed.
    #
    # So the last control quoting this stopped quoting it, and a reason with
    # nothing quoting it is exactly the drift this file exists to prevent. It
    # goes the way "export", "export_pdf", "print" and "community_reports" went,
    # rather than sitting here describing a gap the application has closed.
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
    # and notes is not one of them. Same defect the deleted "medicine_detail"
    # had: a list of fields that quietly included one the screen does not show.
    "appointment_detail": (
        "There is no separate view for one appointment. What the booking records "
        "is almost all in this row already -- its date, time, purpose, assigned "
        "staff and status -- so a detail view would mostly repeat the row it "
        "opened from. What it would add is the booking's notes, which this table "
        "has no column for; those are shown on Appointment Scheduling, under the "
        "patient's name on the same booking."
    ),
    # THERE IS NO "medicine_archive" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It is the entry this file argued with hardest, and it lost twice.
    #
    # Its first version said "retiring a stock item is not implemented" while
    # inventory_items had carried a status flag since the first schema and the
    # Add / Edit Medicine form had offered Active / Inactive on it all along. It
    # also held medicines to a bar it claimed patients cleared -- "its own
    # confirmation and audit entry" -- when no audit entry is written for a
    # patient archive either, and it warned of losing "batch and expiry history"
    # that retiring could not touch and that no table holds.
    #
    # The rewrite fixed all of that and narrowed the claim to what was genuinely
    # missing: not the status, which existed and was read everywhere, but the
    # shortcut -- "patients have a dedicated archive endpoint and a confirmation
    # dialog that names the record and offers just the statuses it can legally
    # move to, and medicines have neither". That sentence was exactly right, and
    # it is also a build order. It has now been carried out.
    #
    # Medicine Inventory's Archive icon opens a confirmation dialog that names
    # the item and its current status and offers only the transition that status
    # permits (models/inventory.py allowed_item_status_transitions), posting to
    # its own endpoint per role -- admin.archive_medicine and
    # staff.staff_archive_medicine -- where process_archive_medicine() re-reads
    # the stored status and re-derives the legal moves before writing, exactly as
    # process_archive_patients() does. Both directions work, so a mis-click is a
    # correctable clerical slip rather than a one-way door.
    #
    # And it re-implements nothing: set_item_status() writes the same status
    # column the Add / Edit Medicine form writes, so RETIRED_STATUS still has one
    # meaning, and the stat cards, the low-stock alert, both dashboards, the
    # sidebar badge and Reports & Analytics respect a retirement made this way
    # the moment it commits, because they were already respecting that column.
    #
    # Nothing quotes this any more, so it goes the way "export", "export_pdf",
    # "print", "medicine_detail" and "community_reports" went, rather than
    # sitting here describing a gap the application has closed.

    # ---- Whole screens with no data source ---------------------------------
    # REWRITTEN ONCE: "There is no settings table" was false. schema.sql defines
    # one -- setting_key, setting_value, updated_by, updated_at -- and has since
    # the first schema. What is true is the half that follows: nothing reads or
    # writes it. Naming the wiring as the gap rather than the table is the same
    # correction the deleted "medicine_archive" needed, and for the same reason:
    # a reason that denies an existing structure sends the next session off to
    # build something that is already there.
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
    # A reason that denies a working integration is the same defect the deleted
    # "medicine_archive" had, and it was worse here: it was the stated grounds
    # for disabling a Test Connection button that now has something real to
    # test.
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
