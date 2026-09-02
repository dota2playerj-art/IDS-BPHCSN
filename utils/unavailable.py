"""Why a control on a screen cannot do its job.

Every entry here is the tooltip on a control that is rendered `disabled`. The
rule this file serves is the one User Management set for its Add User and Edit
User buttons and that the rest of the system now follows:

    a control either works, or it is visibly disabled and says why.
    It is never left looking live while silently doing nothing when clicked.

A dead button is worse than a missing one. It teaches an operator that the
system is unreliable, and in a defence it is the first thing a panel finds by
clicking. Naming the specific missing piece -- a library, a table, a route --
also tells the next session what building it would actually take, which
"Coming soon" does not.

The two buttons that named the rule are now on opposite sides of it, which is
the rule working rather than the rule breaking. Add User creates a real account
with a real hashed password, so it carries no `disabled` and no reason at all --
a working control needs no excuse, and leaving one on it would be the same
defect as a false reason. Edit User is still not built and still says so.

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

"export" then followed it. Patient Records, Medicine Inventory, Appointment
Scheduling and User Management each download a real spreadsheet and a real PDF
(routes/roster_export.py), which were the last four screens quoting it. What it
left behind was one narrower reason, "export_selection", for the one control
still genuinely absent -- the bulk bar's Export on Patient Records, which would
download the ticked records rather than the register.

And that one has now gone too, which finishes the arc. This is the whole life of
a shared reason: born when the gap is real, split when the gap is real for one
control and not another, narrowed when the general case closes and a specific one
does not, deleted when the last thing quoting it stops. One file is where all four
happen, so none of them is missed.

A REASON CAN ALSO BE THE SPECIFICATION FOR CLOSING ITSELF
---------------------------------------------------------
"export_selection" is worth one more paragraph, because of how it went. It did
not collapse the way "export" did, when a dependency landed and made it false. It
was true when written and it was precise: it said the obstacle was not the
browser -- "Change Status beside this posts the same ticked ids to the server
already" -- but the URL, because every download this project serves is a
bookmarkable GET and a file whose contents are a list of primary keys in a query
string is not bookmarkable, not readable and stale the moment the page is.

Every clause of that was correct, and read once more it is a build order rather
than a refusal. The premise it rested on -- that a download must be a GET -- was
the one thing in it nobody had examined, and it does not survive examination for
this control. A bookmarkable URL is the right property for an export that answers
"the whole register", because that question has the same answer tomorrow. It is
the wrong property for one that answers "these eleven records somebody ticked",
because there is no stable thing to bookmark. So the bulk bar's two Export
buttons submit the form the checkboxes already belong to, by POST, with a
formaction pointing at an export route instead of the archive one; the ids arrive
the same way Change Status's already do, and routes/roster_export.py assembles
them through the same machinery the full roster uses.

The lesson is the one this file keeps re-learning from the other direction. A
reason specific enough to name what it is waiting for is a reason somebody can
act on -- and the thing worth re-reading in it is not the gap it describes but
the assumption it takes for granted.

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

"appointment_detail" has now gone the same way, and it is worth naming because
it failed in the harder direction. It never collapsed outright: every clause in
it stayed literally true, and it still misdirected, because "the booking's notes
are on Appointment Scheduling" holds only for a booking in today's queue or
still to come. A note on a visit six weeks ago was on no screen at all. A reason
can be accurate about where something is and still be the wrong answer to why a
control is dead, and that is the version hardest to catch by re-reading. The
View icon it sat on now opens the note in place, to the same expand-in-place
pattern "medicine_detail" was deleted for.

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

    # THERE IS NO "export_selection" ENTRY ANY MORE, AND THAT IS THE POINT.
    # It was written when "export" was deleted, to be the one true thing left to
    # say about the one control still disabled on Patient Records: the bulk bar's
    # Export, which meant the ticked records rather than the register. It
    # outlived its parent by being narrower than it, exactly as this file's
    # docstring describes -- and it has now gone the same way, because the
    # control it explained works.
    #
    # It is the only reason in this file's history that was deleted by being
    # *followed* rather than by going false. It named the obstacle exactly and
    # cleared the browser of blame; what it got wrong was a premise it never
    # stated as one, that a download has to be a bookmarkable GET. The bulk bar
    # now has two Export buttons, Excel and PDF to match the toolbar's pair, and
    # they submit the checkboxes by POST to their own routes -- the same
    # patient_ids Change Status beside them has always posted, assembled by
    # routes/roster_export.py through the same machinery the full roster uses and
    # covered by a cover sheet that says "a selection, not the register" where
    # the roster's says the opposite.
    #
    # Nothing quotes this any more, and a reason with nothing quoting it is
    # exactly the drift this file exists to prevent. It goes the way "export",
    # "export_pdf", "print", "medicine_detail" and "community_reports" went. The
    # full argument is in the docstring above, because it is the most useful
    # thing this file has learned: the part of a reason worth re-reading is the
    # assumption it takes for granted.
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
    # NARROWED, BECAUSE THE GENERAL CASE CLOSED AND ONE SPECIFIC CASE DID NOT.
    # This is the arc "export" lived and the module docstring describes, happening
    # again: the sentence was written when nothing in the project could sort, it
    # was quoted by three screens, and two of them can sort now.
    #
    # Patient Records and Medicine Inventory have real Sort controls -- four
    # columns each, over the rows already rendered, composing with the search box
    # and the Advanced Filter rather than resetting them (static/js/table-sort.js,
    # one comparator shared by both). So the old wording had gone false in every
    # part at once: "column sorting is not implemented" is wrong, "the rows arrive
    # in the order the query returns them" is wrong the moment somebody sorts,
    # and "a menu that was never built" is wrong because the menu exists and those
    # two screens open it.
    #
    # The third screen still quoting this is Appointment Scheduling, and what
    # stops it is not the missing menu -- the menu is now sitting in a shared file
    # it could load in an afternoon. What stops it is that its queue's order is
    # already the answer to a question, and re-sorting it would throw that answer
    # away. So the reason below stops describing an unbuilt feature and starts
    # describing a screen, which is what it should have been about all along.
    #
    # It also names where sorting DOES work. A reader who has just used Sort on
    # Patient Records and then finds it disabled here is owed the difference
    # between the two screens, not a blanket claim they can already disprove.
    #
    # If Appointment Scheduling's Upcoming Appointments panel ever gets its own
    # Sort control, this reason does not cover it: that panel is a list of future
    # bookings with no queue position, and the argument below does not apply to it.
    # SHORTENED. Nine clauses, six of them argument -- and it is a tooltip, so
    # the argument was being made at a size nobody finishes reading. The reasons
    # are the ones above and they stay above: the queue's order is the answer to
    # "who may be brought in next", re-sorting it by name or booked time throws
    # that answer away while still looking like a working queue, and a roster and
    # a shelf sort usefully several ways where a queue sorts usefully one way.
    # What the operator needs is that it cannot be sorted, what the order is, and
    # where sorting does work.
    "sort": (
        "This queue cannot be sorted. Its order is who is in consultation, then "
        "who is waiting, then who has not arrived, then everyone already seen or "
        "cancelled -- and arrival time within each. Sort works on Patient Records "
        "and Medicine Inventory."
    ),
    "pagination": (
        "Paging is not implemented. Every row is already on this page, so there "
        "is no second page to turn to."
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
    # THERE IS NO "save_and_another" ENTRY ANY MORE, for the same reason.
    # It said Save & Register Another was not implemented because returning to a
    # blank form "is a second outcome for the registration POST, and that write
    # path is not being changed for a convenience shortcut". The button is now
    # built, and the sentence's own objection is what shaped it: the write path
    # was not changed. The button is a plain submit on the same form, posting to
    # the same route, through the same validate_patient_form() and the same
    # duplicate check, and the flag it carries is read only after that has
    # returned a saved row id. The one thing it changes is the redirect, and a
    # destination is not a write path.
    #
    # It was built because the reason above measured the cost in the wrong place.
    # "Use Register Patient again from the sidebar" is a fair answer for one
    # registration; at a community health drive, where staff register a queue of
    # people back to back from one desk, it is a detour taken once per person.
    # THERE IS NO "appointment_detail" ENTRY ANY MORE, AND IT WENT THE WAY
    # "medicine_detail" DID -- for the same reason, to the same pattern.
    #
    # Its first version listed "notes" among the fields "already in this row",
    # which was false: Appointment History has five columns before its actions
    # -- Date, Time, Purpose, Assigned To, Status -- and notes is not one of
    # them. The rewrite said so and pointed the reader at Appointment Scheduling
    # instead, "under the patient's name". That was honest about the note
    # existing, and it was still a bad answer, because it is only true of a
    # booking that is in today's queue or still to come. A note on a visit six
    # weeks ago is on no panel of that screen at all, so the sentence sent a
    # reader off the profile to look for something they would not find.
    #
    # The View icon on an Appointment History row now opens a read-only panel in
    # place, built from the same info-grid classes and the same Bootstrap
    # collapse as Consultation History's panel and Medicine Inventory's View,
    # showing appointment.notes -- the column get_appointments_for_patient()
    # was already selecting and no template was reading. No new route, no new
    # screen, and nothing that can write.
    #
    # Nothing quotes this any more, so it goes rather than sitting here
    # describing a gap the application has closed.
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
    # SHORTENED, AND SPLIT WITH THE SCREEN RATHER THAN REPEATED BY IT.
    # This is printed inside Screen 13's opening note and is also the tooltip on
    # four disabled buttons, so it has to stand alone -- but it and the note were
    # saying the same thing twice, in different words, and between them put about
    # a thousand characters and three filenames above the fold. It now carries
    # what the screen is; the note carries only the live exception.
    #
    # The four schema columns are gone from the sentence and are recorded here
    # instead, because the correction they were making still matters to anyone
    # picking the work up: the settings table DOES exist -- setting_key,
    # setting_value, updated_by, updated_at -- and the gap is that no model
    # function and no route writes to it. A reason that denies an existing
    # structure sends the next session off to build something already there.
    # REWRITTEN A THIRD TIME, AND THIS TIME THE FALSE PART WAS THE LONGER PART.
    # The second sentence read "The values shown are the settings the application
    # actually runs on; they are changed in its own configuration, not on this
    # screen." That is true of about six values on Screen 13 and false of about
    # twenty-five, and it was printed above all of them.
    #
    # True. The health center's name, which models/appointment_sms.py puts at the
    # front of every message and every export puts in its header; the barangay,
    # which is part of that same name; the opening and closing times, which are
    # models/appointments.py's CLINIC_OPEN_HOUR and CLINIC_CLOSE_HOUR and which
    # BOOKING_TIME_SLOTS is built from, so a POST outside them is refused; the
    # gateway provider, which is the Semaphore endpoint utils/sms.py posts to.
    #
    # False. The contact number, the email address, the complete address, the DOH
    # licence number, the date established, the facility description and type,
    # the language, the records-per-page figure, both dashboard toggles, every
    # notification channel and reminder, every password rule, the session
    # timeout, the log and backup retention periods. Nothing reads any of them.
    # The contact number, the email and the licence number appear nowhere in this
    # project except on this screen -- they were typed into the mockup and have
    # sat there since.
    #
    # And two that were false in the more damaging direction, because the
    # sentence was vouching for a rule rather than for a value. "Operating Days:
    # Monday - Friday": validate_booking() checks that the date is in the future
    # and inside the horizon and that the time is one of the slots, and never
    # looks at the day of the week, so a Saturday booking is taken. "Sender Name:
    # IDS-BPHCSN": utils/sms.py deliberately sends no sender ID, because an
    # account without an approved one has its messages delivered under
    # Semaphore's default.
    #
    # This is the "mostly right" hazard from the top of this file at a far worse
    # ratio than the case that section was written about. That one was a single
    # word. This was a clause that was correct about six fields, wrong about
    # twenty-five, and load-bearing for a reader deciding whether to believe the
    # screen.
    #
    # What replaces it does not try to list the six. The tooltip has to stand
    # alone on four buttons, three examples are enough to show what kind of thing
    # qualifies, and the full inventory is the paragraph above -- which is where
    # someone maintaining it will look, rather than in a title attribute.
    "settings": (
        "Every field is read-only, because no part of the system stores what is "
        "typed here. Most of the values shown are placeholder text and configure "
        "nothing. A few do match how the system actually runs -- the health "
        "center's name, the clinic's opening and closing times, the SMS gateway "
        "provider -- but those are set in its own configuration, not on this "
        "screen."
    ),
    "backup": (
        "Backup and restore are not built. The database is one file, and the "
        "practice today is to copy it, with the date in the name, outside the "
        "application. Doing it from this screen needs a job that can copy the "
        "file safely while the system is running."
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
    # SHORTENED. Six sentences on a disabled button, ending on a rhetorical
    # figure -- "a key revealed here would be a key this project never held".
    # The variable name went with them: an administrator turning this on is
    # setting it on the server, and the exact spelling belongs in the note at the
    # top of utils/sms.py that tells them how, not in a tooltip. What is left is
    # why the buttons are dead, what turns them on, and what happens meanwhile.
    "sms_gateway": (
        "No API key is set on the server, so these controls have nothing to act "
        "on. Setting that key is the whole step -- nothing on this screen is "
        "part of it. Until then broadcasts are still written to history and "
        "marked simulated, which is why SMS Notifications works today."
    ),
    # The last sentence points at Audit Logs for "recorded activity", and that
    # pointer got better rather than worse: the trail now holds sign-ins as well
    # as record edits and broadcasts, so a reader sent there for what the system
    # noticed finds more of it. Nothing here needed correcting -- it is listed in
    # this comment only because it was checked, and a reason that mentions
    # another screen's contents is exactly the kind that quietly goes stale.
    "notifications": (
        "Notifications are not recorded. Nothing in this system writes, stores "
        "or clears one. Recorded activity is on Audit Logs -- record edits, SMS "
        "broadcasts and sign-ins -- and community messages on SMS Notifications."
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
