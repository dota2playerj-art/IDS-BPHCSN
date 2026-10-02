"""Why a control on a screen cannot do its job."""

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
    # quoting this. Patient Records, Medicine Inventory, the Patient Queue
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
    # icons on the Patient Queue's tables, and those are now working
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
    # The Patient Queue had a disabled Sort button with a reason beside it. It was
    # removed (final fixes): the queue's order answers "who may be brought in next",
    # and a control that can never work is not on the screen, with or without a reason.
    "pagination": (
        "Paging is not implemented. Every row is already on this page, so there "
        "is no second page to turn to."
    ),

    # ---- Scheduling ---------------------------------------------------------
    # THESE TWO ARE A NEW KIND OF ENTRY FOR THIS FILE, AND THE DIFFERENCE IS
    # WORTH STATING. Every reason above is a tooltip on a control that is drawn
    # disabled. Neither of these has a control at all -- there is nothing to
    # disable, because what they describe was taken out rather than left dead.
    # They are rendered as stated text on the Patient Queue instead.
    #
    # The rule this file serves is still the rule: a screen either does a thing,
    # or it says plainly that it does not. Deleting a feature and saying nothing
    # is the version of a dead button that is hardest to find -- an operator who
    # used advance booking last week and cannot find it this week has no way to
    # tell "removed on purpose" from "broken this morning" unless the screen
    # says which. So they are quoted, they are read, and if either stops being
    # true they go the way "export" and "print" went.

    # WHY NOTHING BOOKS A DAY THAT HAS NOT COME.
    # Advance booking was built and it worked: a date, a half-hour slot, a
    # conflict warning, reschedule, cancel, no-show, and a text to the patient.
    # It was removed on 2026-09-05 anyway, because none of that was the problem.
    # The problem was that it modelled a clinic this one is not. Barangay
    # Poblacion sees people in the order they walk in; no one here is given ten
    # o'clock next Thursday, and a screen that offered it read convincingly in a
    # demonstration and wrongly in the building.
    #
    # THE SUCCESSOR IS BUILT, AND THIS STILL NAMES NO DAY, DELIBERATELY.
    # A real health center does publish a shape to its week -- one day for
    # immunisation, another for prenatal -- and this sentence used to say that a
    # fixed service-day schedule was "planned". It is built now: the Service
    # Schedule screen, filled in by the Administrator, with today's services in
    # the strip at the top of this screen. So "planned" went.
    #
    # What did not change is that the days themselves have not been confirmed
    # with the health center, and the schedule ships empty for that reason (see
    # migrate_add_service_schedule.py). Writing a plausible timetable into this
    # sentence would be the same mistake that advance booking was, in a smaller
    # font: a specific claim about how this facility runs, made up at a desk. So
    # the sentence points at where the days are kept, which stays true whether
    # the schedule is empty or full, and says nothing about what they are.
    "advance_booking": (
        "Visits cannot be booked ahead, by design. Patients are seen in the order they arrive: "
        "use Check In Patient."
    ),

    # "queue_exit" WAS HERE: a patient who left before being seen could not be closed. Staff
    # and the Doctor can now mark the visit "Left before being seen" (Task 6, M5), so the
    # reason is deleted rather than left describing a state the system has left.

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
    # them. The rewrite said so and pointed the reader at the Patient Queue
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
    # confirmation and audit entry" -- when, at the time, no audit entry was
    # written for a patient archive either (one is since Task 4), and it warned
    # of losing "batch and expiry history" that retiring could not touch and
    # that no table holds.
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

}
