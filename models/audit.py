"""Writes to audit_logs -- the record of who changed what, and when.

The table has existed since the first schema pass and held nothing; this is its
first writer. It is deliberately append-only: nothing here updates or deletes a
row, because an audit trail that can be edited answers no question worth asking.
"""
import config
from database.connection import db_connection
from utils.dates import day_start_utc, today
from utils.phone import mask_numbers_in_text

# The module pills the Audit Logs screen already renders. Named constants rather
# than literals at each call site so a typo cannot split one module into two.
MODULE_CONSULTATIONS = "Consultation Records"
MODULE_PATIENTS = "Patient Records"
MODULE_INVENTORY = "Medicine Inventory"
# KEPT AT ITS OLD SPELLING ON PURPOSE. Screen 08 was renamed Patient Queue on
# 2026-09-05, and this was not renamed with it. The value is not a label the
# screen shows -- it is the string stored in audit_logs.module on rows already
# written, and one such row exists (the August 29 correction that closed a
# consultation left open overnight). Changing the constant would file future
# writes under a second pill and leave that row alone under the first, which
# splits one module's history in the Audit Logs filter for no gain.
#
# Same ruling as the Administrator persona correction, which left 506 entries
# under the name they were written with: an audit trail records what was true
# when the row was written, and renaming a screen is not a reason to restate it.
MODULE_APPOINTMENTS = "Appointment Scheduling"
# The two immunisation tables, under one pill. Both halves of the Patient
# Profile's Immunization Record tab write here: the DOH EPI doses and the
# vaccinations given outside that schedule. One module rather than two because
# the question this pill answers is "which screen was touched", and those two
# lists are one screen -- the trail keeps them apart where it matters, in the
# activity phrase, which names which kind of record moved.
MODULE_IMMUNIZATIONS = "Immunization Records"
MODULE_SMS = "SMS Notifications"
# Sign-ins and refused sign-ins. Its own module rather than folded into one of
# the record modules above, because it answers a different question: those say
# what the record used to say and what it says now, this one says who was let in
# and who was turned away. Keeping it separate is also what lets the Audit Logs
# module filter show the authentication trail on its own.
MODULE_AUTH = "Authentication"
# Accounts themselves: one created, one deactivated, one switched back on.
#
# ITS OWN MODULE RATHER THAN A CORNER OF MODULE_AUTH, AND THE DISTINCTION IS THE
# SAME ONE THAT SEPARATES A RECORD MODULE FROM AN ACCESS ONE.
# MODULE_AUTH answers "who was let in and who was turned away" -- it is a trail
# of attempts, written by people presenting credentials, and the account rows it
# names are the subject of the attempt rather than the thing that changed.
# This module answers a different question: "who changed what an account IS".
# Creating one hands somebody a way into a system holding patient records;
# deactivating one takes it away. Those are administrative acts with an author
# who is not the account named in them, and folding them into Authentication
# would put them in a list whose every other row means somebody typed a password
# -- where a reader scanning for "when did this account appear, and who made it"
# would have to read past every sign-in in the trail to find out.
#
# It also keeps the module filter useful in both directions. An administrator
# reviewing access changes selects this and sees three kinds of row and nothing
# else; one investigating a suspected intrusion selects Authentication and is
# not shown the account housekeeping that produced the accounts.
MODULE_USERS = "User Management"
# Changes to the system's own configuration, and copies of the database taken
# off it. Its own module rather than a corner of MODULE_USERS, on the same
# distinction that separates User Management from Authentication: that one
# answers "who changed what an account IS", this one answers "who changed how the
# system itself is set up, and who took a copy of everything in it".
#
# Both kinds of entry here reach further than any single record. A settings save
# changes the facility name at the front of every SMS the barangay sends and on every
# export letterhead, and the clinic hours every booking is validated against -- so
# a message a patient disputes months later has to be explainable from this
# trail. A backup download puts every patient record in the system into one file
# on somebody's laptop, which is the single most consequential read this
# application offers and the one a reviewer most needs to be able to enumerate.
MODULE_SETTINGS = "Settings"
# The confidentiality seal on a consultation: who sealed one, who lifted one, and
# who was kept out of one.
#
# ITS OWN MODULE RATHER THAN A CORNER OF MODULE_CONSULTATIONS, on the same
# distinction that separates User Management from Authentication. That module
# answers "what did this consultation used to say, and what does it say now" --
# it is a trail of clinical content. This one answers a question no clinical
# trail can: "who decided this record is privileged, and who has been refused
# it". The two are read by different people looking for different things, and
# folding these entries into the consultation trail would bury them under an edit
# for every temperature ever corrected.
#
# It also keeps the module filter useful in both directions. An administrator
# reviewing confidentiality selects this and sees seals, liftings and refusals
# and nothing else; one reviewing what was actually recorded about a patient
# selects Consultation Records and is not shown the access housekeeping.
#
# WHY IT IS NAMED FOR THE DUTY RATHER THAN FOR THE LAW. RA 11166 is what made
# this necessary and is cited at every point in the code that implements it, but
# the seal is not HIV-specific and must not read as though it were: a module pill
# saying "RA 11166" beside an entry would tell everyone who could see the Audit
# Logs screen which law the sealed record falls under, which is most of the
# disclosure the seal exists to prevent.
MODULE_CONFIDENTIALITY = "Medical Confidentiality"
# The health center's service schedule: which services run on which days.
#
# ITS OWN MODULE RATHER THAN A CORNER OF MODULE_SETTINGS. Both are the facility's
# own configuration, but they are read by different people for different
# questions. Settings is the facility's identity and the switch that closes the
# system; this is what the barangay was told runs on which day, and "when did
# immunisation move off the 2nd Wednesday, and who moved it" is a question a
# health worker or an official asks without wanting a list of backup downloads
# in the way.
MODULE_SERVICE_SCHEDULE = "Service Schedule"

# Activity phrases, in the same voice as the ones on that screen ("Updated
# patient record", "Updated stock quantity").
ACTION_CONSULTATION_UPDATED = "Updated consultation record"
# The two correction phrases, written from routes/vaccination_correction_views.py
# when a recorded vaccination's own field values are put right.
#
# "Corrected", not "Updated", and the difference is the whole point of the path
# that writes these. Every other record in this system is edited through the form
# that created it; a vaccination is not, because both entry forms are deliberately
# add-only -- see routes/consultation_views.py _apply_immunization_edit(). A
# correction is therefore a rarer and more deliberate act than an edit, reached
# from a different screen behind its own confirmation, and the trail says so in
# the one word an administrator scanning it will actually read.
#
# THEY ARE TWO PHRASES RATHER THAN ONE FOR THE REASON ACTION_LOGIN_BLOCKED IS
# SEPARATE FROM ACTION_LOGIN_FAILED. Both sentences are about a vaccination
# record, and collapsing them would lose the distinction that decides what a
# reader does next. An EPI dose is graded against the national schedule: moving
# its date moves whether a child reads as Due Now or No record on every screen that
# counts them. A vaccination outside that schedule is graded against nothing, so
# correcting one changes a history and no status anywhere. An administrator
# asking "did a correction change who is showing as a defaulter?" needs those two
# to look different in a list, not to be filtered apart by reading each entry.
ACTION_IMMUNIZATION_CORRECTED = "Corrected EPI immunisation record"
ACTION_GENERAL_VACCINATION_CORRECTED = "Corrected other vaccination record"
# A broadcast is not editable, so unlike the consultation entry above there is no
# before-and-after to describe. What earns its place in `details` instead is the
# message itself, who it reached, and whether it was actually transmitted -- an
# entry that omitted the last of those would read as a send that happened.
ACTION_SMS_BROADCAST_SENT = "Sent community SMS broadcast"
# The individual counterpart, and its own phrase rather than a variant of the one
# above. Both are a message that went out, and collapsing them would lose the
# distinction that decides what a reader does next: a broadcast is what the
# barangay said to the community and names no patient, while this is one message
# to one named patient about their own appointment. An administrator asking "who
# have we texted about their bookings?" needs those two to look different in a
# list, not to be told apart by reading every entry.
#
# `details` carries the message itself, the number it was addressed to, the
# appointment it is about and whether it was actually transmitted -- an entry
# that omitted the last of those would read as a send that happened.
# NOTHING WRITES THIS ANY MORE, AND IT IS KEPT ANYWAY, LIKE MODULE_APPOINTMENTS
# ABOVE. Individual appointment confirmations were retired with advance booking
# on 2026-09-05, so no new row will ever carry this phrase. Eight rows already
# do. The constant stays as the documented spelling of what is in the table --
# deleting it would leave those eight rows' action phrase recorded nowhere but
# in the rows themselves, and the counts on Audit Logs select on these strings.
# It is not re-worded for the same reason it is not deleted: an audit trail
# records what was true when the row was written.
ACTION_APPOINTMENT_SMS_SENT = "Sent appointment SMS to patient"
# The two authentication outcomes, written from routes/auth.py's login route.
# Both phrases are stable strings because the counts below select on them: a
# reworded action would silently stop being counted, so they are constants for
# the same reason the module names are.
ACTION_LOGIN_SUCCESS = "Signed in"
ACTION_LOGIN_FAILED = "Refused sign-in attempt"
# A third outcome, and its own phrase rather than a variant of the one above.
# "The password did not match" and "the account has been deactivated" are refusals
# with nothing else in common: the first is a typo or a guess, the second is a
# revoked credential still being presented -- often, and this is the whole point,
# with the CORRECT password. Collapsing them into one phrase would bury the only
# entry on this screen that tells an administrator a credential they thought they
# had withdrawn is still in someone's hands and still being used.
ACTION_LOGIN_BLOCKED = "Blocked sign-in to deactivated account"
# A fourth phrase, and the first one that is not about the login form at all.
# The three above are written when somebody presents credentials. This one is
# written when a session that was already open is ended underneath its holder,
# because the account it belongs to has been deactivated since it started --
# utils/security.py checks the flag on every guarded request, so a revocation
# takes effect at the next click rather than at the next sign-in.
#
# IT IS ITS OWN PHRASE FOR THE SAME REASON ACTION_LOGIN_BLOCKED IS.
# Folding it into that one would be the more tempting shortcut, because both
# sentences are about a deactivated account -- and it would make the trail lie in
# a way nobody would catch by reading it. "Blocked sign-in" says a credential was
# presented at the form and refused. Here nothing was presented: somebody was
# already inside, and the door was closed behind them. An administrator chasing
# "who is still trying to use the account I switched off" would read the second
# as the first and conclude the credential is still in circulation.
ACTION_SESSION_REVOKED = "Ended session on deactivated account"

# A session the server ended because a session limit in config.py passed.
# Written by utils/security.py. Two phrases, so the trail says which limit it was.
# The numbers come from config.py, so the phrase matches the rule in force.
IDLE_TIMEOUT_MINUTES = int(config.IDLE_TIMEOUT.total_seconds() // 60)
ABSOLUTE_TIMEOUT_HOURS = int(config.ABSOLUTE_TIMEOUT.total_seconds() // 3600)
ACTION_SESSION_IDLE_TIMEOUT = (
    f"Signed out after {IDLE_TIMEOUT_MINUTES} minutes without activity"
)
ACTION_SESSION_ABSOLUTE_TIMEOUT = f"Signed out after {ABSOLUTE_TIMEOUT_HOURS} hours"

# A form or script request refused because it did not carry the token from a
# page this app served: an old page after the session ended, or a request made
# by another website (CSRF). Written by utils/csrf.py. Nothing was changed.
ACTION_REQUEST_REFUSED = "Refused a request from an expired or outside page"

# The three account-management phrases, written from routes/user_views.py when an
# Administrator creates an account or changes whether it may sign in.
#
# WHY THESE ARE AMONG THE MOST AUDIT-WORTHY ENTRIES IN THE SYSTEM.
# Every other entry in this table records a change to something the system holds:
# a temperature, a stock figure, a booking. These record a change to WHO CAN
# REACH ALL OF IT. An account created here is a new way into a database of
# patient records, and the account that created it chose its role -- so the two
# facts a reviewer needs are which account appeared and who decided it should.
# Both are in `details`, which spells out the new account's username, name and
# role, and the log_action() call carries the acting administrator as user_id.
#
# THE PASSWORD IS NOT IN ANY OF THEM, AND THAT PROHIBITION IS ABSOLUTE.
# It is the same rule routes/auth.py's module note states for a refused sign-in,
# and it binds harder here because this is the one place in the application where
# a password is legitimately in hand as plaintext, having just been typed by an
# administrator. Nothing about it reaches this table -- not the value, not a
# hash of it, not its length, not which of the strength rules it passed. What is
# recorded is that a password was set and that it was stored hashed, which is the
# fact a reviewer is actually asking about.
ACTION_USER_CREATED = "Created user account"
# Two phrases rather than one "Changed account status", for the reason
# ACTION_LOGIN_BLOCKED is separate from ACTION_LOGIN_FAILED: they are opposite
# acts, and the one a reviewer scans a list for is the one that took access away.
# A single phrase would make "six account status changes this month" a number
# that answers nothing -- six revocations and six restorations read identically
# in it, and only one of those is a security event.
ACTION_USER_DEACTIVATED = "Deactivated user account"
ACTION_USER_REACTIVATED = "Reactivated user account"

# Editing an account, split into two phrases for the same reason deactivation and
# reactivation are two rather than one "changed account status".
#
# A NAME CORRECTION AND A ROLE CHANGE ARE NOT THE SAME EVENT.
# Fixing a misspelt surname and moving an account from Health Center Staff to
# Administrator both arrive through one form, and under a single "Edited user
# account" phrase they would be one line each in a list, indistinguishable at a
# glance and counted together in any total. One of them is a typo; the other
# hands somebody every screen in the system, including this one -- the ability to
# create accounts, revoke them and reach every patient record.
#
# Privilege elevation is also the change most worth being able to scan for,
# because the recognised way it is abused is to raise a role, act, and lower it
# again: two edits that individually look ordinary and together look like nothing
# at all unless the trail lets a reviewer pull role changes out on their own.
#
# ACTION_USER_ROLE_CHANGED is therefore written whenever the role moved, EVEN IF
# the name moved in the same submit -- the more serious of the two facts names
# the entry, and `details` carries both changes in full. The `details` text
# always spells out the role that was held and the role that replaced it, side by
# side, so the pair can be read without joining this entry to an earlier one.
ACTION_USER_EDITED = "Edited user account"
ACTION_USER_ROLE_CHANGED = "Changed user account role"

# An administrator setting a new password on an existing account.
#
# ITS OWN PHRASE, NOT AN EDIT. It changes a credential rather than a detail of
# the account, and it is the one act on this screen that can be performed against
# an account without the holder knowing -- so "when was this account's password
# last replaced, and by whom" has to be a question the trail answers directly
# rather than one a reviewer reconstructs from a general edit entry.
#
# AND THE PROHIBITION FROM ACTION_USER_CREATED BINDS HERE UNCHANGED. Not the
# value, not a hash of it, not its length, not which strength rules it passed.
# What the entry records is that the password was replaced, by whom, on which
# account, and that the new one is stored only as a salted hash -- which is
# every fact about it a reviewer can act on.
ACTION_PASSWORD_RESET = "Reset user account password"

# The account holder setting their own password from My Account, having proved
# it is them by typing the one they currently sign in with.
#
# IT IS A SEPARATE PHRASE FROM ACTION_PASSWORD_RESET, AND THE TWO MUST NEVER BE
# COLLAPSED. Both end with a new hash in the same column, and that is the whole
# of what they have in common. A reset is performed BY somebody else, ON an
# account, without its holder's knowledge or consent being needed -- which is
# why the entry above exists at all. A change is performed by the holder, on
# their own account, and could not have been performed by anyone who did not
# already know the password. Read months later, "this account's password was
# replaced on the 4th" is an entirely different fact depending on which of those
# happened: one says an administrator handed somebody a new credential, the
# other says the person who already held it chose a different one. A single
# phrase would make the trail unable to tell a reviewer which.
#
# IT IS FILED UNDER MODULE_AUTH RATHER THAN MODULE_USERS, AND THAT IS A DECISION
# WITH A COST WORTH STATING.
# MODULE_USERS' own note above defines what belongs to it: "administrative acts
# with an author who is not the account named in them". This act is the exact
# negation of that clause -- the author IS the account named, and the row is
# attributed to them because they are the person who did it. It is also, like
# every other row under Authentication, written by somebody who presented a
# credential: the current password is verified against the stored hash before
# anything is written, in the same check_password_hash() call the login form
# makes. So it sits with the sign-ins, where the account is the subject and the
# actor at once.
#
# The cost is that "every time this account's password changed, by anyone" now
# spans two module filters rather than one. That is accepted rather than
# overlooked. The alternative costs more: filing it under User Management would
# put a health worker's own housekeeping into the list an administrator selects
# to review what OTHER administrators have done to accounts, which is the one
# thing the split between those two modules exists to prevent. The phrase, not
# the module, is what tells the two events apart -- and both phrases spell out
# in `details` who acted and on whose account, so neither row can be misread
# whichever filter surfaces it.
#
# THE PROHIBITION ON THE VALUE BINDS HERE EXACTLY AS IT DOES ABOVE, and it binds
# to two passwords now rather than one. Neither the new password nor the current
# one the holder typed to prove themselves reaches this table -- not the value,
# not a hash, not its length, not which strength rules it passed. The entry is
# composed from the stored account row.
ACTION_PASSWORD_CHANGED_SELF = "Changed own account password"

# The same screen's refusal: somebody signed in as this account opened My Account
# and typed a current password that is not the one the account signs in with.
#
# WHY THIS IS WORTH A ROW AT ALL, WHEN THE ATTEMPT CHANGED NOTHING.
# It is the same argument ACTION_LOGIN_FAILED rests on, arriving one door
# further in. A refused sign-in is recorded because a run of them against one
# account is the shape of somebody guessing, and that shape is invisible if only
# the successful attempt is written down. This screen is reachable only from
# inside an open session, which makes the refusal here narrower and, for the one
# case that matters, worse: the person at the keyboard holds a live session for
# this account and does not know its password. That is what an unattended,
# still-signed-in machine looks like from the trail -- somebody sat down at it
# and tried to take the account properly by changing its credential. A single
# such row is a mistyped password; a series of them is the event this table
# exists to make visible, and until now the series left no trace whatsoever.
#
# IT IS A SEPARATE PHRASE FROM ACTION_LOGIN_FAILED, AND MUST STAY ONE.
# Both are "a password was typed and did not match", and that is the whole of the
# overlap. A refused sign-in is somebody at the door who may be anybody; this is
# somebody already inside, holding a session the system itself issued. An
# administrator counting refused sign-ins to see who is being guessed at must not
# find these mixed in, because they answer a different question and, unlike a
# refused sign-in, every one of them was made by a session that was already
# trusted. The counts below select on the phrase, so collapsing the two would
# also silently change what those figures mean.
#
# THE PROHIBITION ON THE VALUE BINDS HERE AS IT DOES EVERYWHERE ELSE, and this
# is the entry where it binds hardest, because what was typed here is the one
# string in the system most likely to be a REAL password that simply belongs to
# a different account -- somebody typing their own password into a machine left
# signed in as a colleague. Nothing about it reaches this table: not the value,
# not a hash, not its length, not how near it came. The row is composed entirely
# from the stored account row, exactly as ACTION_LOGIN_FAILED's is.
ACTION_PASSWORD_CHANGE_FAILED_SELF = "Refused own-password change attempt"

# The two Settings actions.
#
# ACTION_SETTINGS_UPDATED covers the six General Settings values -- the health
# center's name, its barangay, municipality and province, and the clinic's
# opening and closing times. `details` names every value that actually moved,
# with what it was and what it became, because these are the only stored values
# in the system that nothing else records the history of: a patient record shows
# its own updated_at, an appointment shows its status, but a facility name that
# was corrected leaves no trace on any row it went out on. The SMS a patient
# received last month says what the name was; only this entry says when it
# changed and who decided it.
ACTION_SETTINGS_UPDATED = "Updated general settings"

# ACTION_BACKUP_DOWNLOADED is a read, and it is the only read in this entire
# trail. Nothing else here records somebody merely looking -- opening a patient
# record writes no row, and neither does exporting one screen's worth of
# figures. This one does, because what leaves is not a screen's worth of
# anything: it is the whole database, every patient, every consultation, every
# account hash, in one file that then exists outside this system entirely and
# cannot be recalled. "Who has a complete copy of the register, and since when"
# is a question a health center has to be able to answer, and this entry is the
# only place the answer could come from.
ACTION_BACKUP_DOWNLOADED = "Downloaded a database backup"

# Maintenance mode, closing and opening the system.
#
# TWO PHRASES RATHER THAN ONE "Changed maintenance mode", for the reason
# ACTION_USER_DEACTIVATED and ACTION_USER_REACTIVATED are two rather than one
# "changed account status": they are opposite acts, and only one of them takes
# access away. A single phrase would make "four maintenance changes this month"
# a number that answers nothing -- two closures and two reopenings read
# identically in it, and the question a reviewer is actually asking is when the
# health center could not reach its own records.
#
# THIS IS THE ONE ENTRY THAT EXPLAINS A WHOLE WINDOW OF REFUSALS. Nothing is
# written when a blocked health worker is turned away -- utils/security.py's
# _maintenance_response() says why -- so these two entries and the times on them
# are the entire record of why nobody but an Administrator could work between
# them. `details` therefore carries who closed it, and how many consultations
# were open at that moment, because that is the fact somebody will want back.
ACTION_MAINTENANCE_ENABLED = "Enabled maintenance mode"
ACTION_MAINTENANCE_DISABLED = "Disabled maintenance mode"

# The four confidentiality phrases. All under MODULE_CONFIDENTIALITY.
#
# TWO OF THEM ARE CHANGES AND TWO ARE NOT, WHICH IS WHY THERE ARE FOUR.
# Sealing and lifting move a column on a consultation. A withheld view and a
# refused field move nothing at all -- one is somebody being shown a placeholder,
# the other is a submission having two of its fields dropped. Collapsing any pair
# would make a count of them answer nothing.
#
# ACTION_CONSULTATION_RESTRICTED / _UNRESTRICTED are two phrases rather than one
# "changed restriction", for the reason ACTION_USER_DEACTIVATED and
# ACTION_USER_REACTIVATED are two: they are opposite acts and only one of them
# takes information away. "Six restriction changes this month" would read
# identically for six seals and six liftings, and a reviewer asking whether a
# patient's privileged record was ever opened up again needs those to look
# different in a list.
#
# `details` on both names the consultation, the patient, the visit date and who
# originally recorded it. IT NEVER NAMES THE DIAGNOSIS. That prohibition is
# absolute and it is the same shape as the one on passwords above: the audit
# trail is readable by any Administrator and is exported whole by
# routes/audit_export.py, so writing the sealed text into `details` would move
# the privileged information out of the one column that protects it and into the
# one place in this system that is designed to be read and downloaded. What the
# entry records is that a record was sealed, whose it is, and by whom -- which is
# every fact a reviewer can act on.
ACTION_CONSULTATION_RESTRICTED = "Marked consultation restricted"
ACTION_CONSULTATION_UNRESTRICTED = "Lifted consultation restriction"

# The read half. Written when a role that may not see a sealed diagnosis opens a
# patient's record and the system shows them the placeholder instead.
#
# WHY A REFUSED READ IS WORTH A ROW WHEN THE READ CHANGED NOTHING.
# It is the argument ACTION_BACKUP_DOWNLOADED rests on, narrowed to one record.
# That entry exists because "who has a complete copy of the register" is a
# question a health center must be able to answer, and nothing else in the trail
# could answer it. This one exists because "who has been at this patient's
# privileged record" is a question RA 11166 makes a health center answerable for,
# and an access rule that leaves no trace is a rule nobody can demonstrate was
# ever enforced. The entry is the evidence that the seal held.
#
# ONE ROW PER VIEW THAT ACTUALLY WITHHELD SOMETHING, NOT ONE PER SEALED ENTRY ON
# THE PAGE, AND NOT ONE PER SCREEN A HEALTH WORKER OPENS.
# This is the shape of thing that fills a table -- utils/security.py's
# _maintenance_response() declines to write a row per blocked click for exactly
# that reason -- so the boundary is drawn deliberately. A profile with three
# sealed visits writes one entry naming all three, because the event is "this
# person looked at this patient's record", not "this person failed to read
# entry #12". A profile with none writes nothing at all, because nothing was
# withheld and a row saying so would be a row about an ordinary page view.
ACTION_RESTRICTED_WITHHELD = "Withheld restricted consultation from view"

# The write half, and the more serious of the two. Written when a submission from
# a role that may not diagnose arrives carrying a diagnosis or a treatment plan
# anyway.
#
# IT IS A SEPARATE PHRASE FROM THE ONE ABOVE AND MUST STAY ONE. Both are the
# access rule doing its job, and that is the whole of the overlap. A withheld
# view is the ordinary, expected consequence of a health worker opening a record
# they work with every day -- there is nothing wrong with it and nobody did
# anything. A refused field cannot be produced by using this system as it is
# built: the fields are not rendered for that role, so a submission carrying them
# was assembled by something other than the form. A single row is a stale tab or
# a replayed request; a series of them is somebody probing the boundary, and that
# distinction is invisible if the two share a phrase.
#
# `details` names the fields that were dropped and NOT what they contained. The
# submitted text is the caller's guess at a diagnosis, and writing an unlicensed
# guess about a patient's condition into the permanent trail would create exactly
# the record the refusal exists to prevent -- attributed to the patient, readable
# by every Administrator, and carried into every audit export.
ACTION_DIAGNOSIS_REFUSED = "Refused clinical judgement from an unlicensed role"

# Task 5 (H4). The Doctor opened a sealed record and the key on this computer
# could not decrypt it: the key is missing or wrong, or the value is damaged.
# Nothing changed. Written by routes/sealed_access.py. No clinical text.
ACTION_SEALED_UNOPENABLE = "Could not open sealed consultation"
# Written once by migrate_redact_clinical_audit_text.py: diagnosis and treatment
# text was removed from earlier entries. The actor is the first active
# Administrator account, because audit_logs.user_id must name an account; the
# entry says it was the migration, not that person.
ACTION_CLINICAL_TEXT_REDACTED = "Removed clinical text from earlier audit entries"

# The three service-schedule entries, all under MODULE_SERVICE_SCHEDULE.
#
# THREE PHRASES RATHER THAN ONE "Changed service schedule", for the reason
# creation, editing and deactivation of accounts are three: a reviewer asking
# "was prenatal day ever dropped" is looking for a deletion, and it must not read
# the same as a note being reworded.
#
# `details` on a deletion carries everything the row said -- service, days and
# note -- because once the row is gone that entry is the only copy of it. An
# edit carries the before and after of each field that moved, in the
# "Label: before → after" shape the Audit Logs panel draws side by side, and a
# save that moved nothing writes no entry at all.
ACTION_SCHEDULE_ENTRY_ADDED = "Added service schedule entry"
ACTION_SCHEDULE_ENTRY_EDITED = "Edited service schedule entry"
ACTION_SCHEDULE_ENTRY_DELETED = "Deleted service schedule entry"

# Task 4 (H3): the health-record writes that used to leave no trace. Each is
# written by routes/audit_entries.py, in the same transaction as the change.
# Short, one-line details. Never diagnosis or treatment text, never a password,
# never a contact number. Patients are named as "Name (PAT-001)", like the
# entries above.
#
# Patient Records. A death declaration and its reversal have their own phrases:
# they are the most serious changes to a patient record.
ACTION_PATIENT_REGISTERED = "Registered patient"
ACTION_PATIENT_UPDATED = "Updated patient record"
ACTION_PATIENT_STATUS_CHANGED = "Changed patient status"
ACTION_PATIENT_DECLARED_DECEASED = "Declared patient deceased"
ACTION_PATIENT_DEATH_REVERSED = "Reversed death declaration"
# Task 20: a record saved after the possible-duplicate warning, because the
# operator ticked "This is a different person". Patient IDs only, never names.
ACTION_PATIENT_DUPLICATE_CONFIRMED = "Saved patient after a possible-duplicate warning"
# Consultation Records. A new consultation. Edits keep ACTION_CONSULTATION_UPDATED.
ACTION_CONSULTATION_RECORDED = "Recorded consultation"
# Immunization Records, written when a new consultation records doses. The
# three kinds stay apart, as the two correction phrases above do.
ACTION_EPI_DOSES_RECORDED = "Recorded EPI immunisation doses"
ACTION_REPORTED_DOSES_RECORDED = "Recorded doses given elsewhere"
ACTION_OTHER_VACCINATIONS_RECORDED = "Recorded other vaccinations"
# Doses given elsewhere, recorded from the Immunization Record tab with no consultation
# (Task 9). A card that was seen, a parent's word, and what can be done to either.
ACTION_ELSEWHERE_DOSE_RECORDED = "Recorded a dose given elsewhere"
ACTION_PARENT_REPORT_RECORDED = "Recorded a parent report of a dose"
ACTION_PARENT_REPORT_UPGRADED = "Upgraded a parent report to a card record"
ACTION_ELSEWHERE_DOSE_CHANGED = "Changed a dose record given elsewhere"
ACTION_ELSEWHERE_DOSE_REMOVED = "Removed a dose record given elsewhere"
# Medicine Inventory. Dispensing moves stock, so it is filed here. Stock is received as a
# batch and removed from one batch (Task 12); Edit details never changes a quantity.
ACTION_MEDICINE_DISPENSED = "Dispensed medicine"
ACTION_INVENTORY_ADDED = "Added inventory item"
ACTION_INVENTORY_EDITED = "Edited inventory item"
ACTION_STOCK_ADJUSTED = "Adjusted stock quantity"  # old entries; stock is now received and removed by batch
ACTION_STOCK_RECEIVED = "Received stock"
ACTION_STOCK_REMOVED = "Removed stock from a batch"
ACTION_INVENTORY_ARCHIVED = "Archived inventory item"
ACTION_INVENTORY_RESTORED = "Returned inventory item to service"
# Appointment Scheduling (the Patient Queue).
ACTION_PATIENT_CHECKED_IN = "Checked patient in"
ACTION_CONSULTATION_STARTED = "Started consultation"
ACTION_CONSULTATION_COMPLETED = "Completed consultation"
# A patient who checked in and went home before the Doctor saw them (Task 6, M5),
# and the same-day undo. The entry names the patient and the visit, never why.
ACTION_LEFT_BEFORE_SEEN = "Marked as left before being seen"
ACTION_LEFT_UNDONE = "Undid left before being seen"
# A patient sent on to the RHU or a hospital (Task 19), and the same-day undo. The entry names
# the patient, the visit and the destination from the list, never the reason or a facility name.
ACTION_REFERRED = "Referred a patient"
ACTION_REFERRAL_UNDONE = "Undid a referral"
# Task 6b: the intake is saved and the visit waits for the Doctor, and a correction of a
# visit's service.
ACTION_SENT_TO_DOCTOR = "Intake saved, waiting for the Doctor"
ACTION_SERVICE_CHANGED = "Changed the service of a visit"
# Task 6c: a visit that needs the Doctor is sent to him instead of being closed.
ACTION_VISIT_SENT = "Sent visit to the Doctor"

# Every action that means somebody was turned away at the login form. Grouped so
# the Security Events figure counts refusals rather than one particular kind of
# refusal -- adding a fourth outcome later must not silently shrink that number.
#
# ACTION_SESSION_REVOKED IS DELIBERATELY NOT IN THIS GROUP, AND THAT IS A CLAIM
# ABOUT TWO SCREENS RATHER THAN A PREFERENCE.
# The comment above says "at the login form", and both screens reading this
# figure say the same in their own words: Audit Logs' Security Events card is
# titled "Sign-ins refused against an account that exists", and Settings labels
# the number "Refused sign-in attempts". A revoked session is not a sign-in
# attempt. Adding it here would leave two visible labels describing a total that
# no longer matches them -- which is the precise failure utils/unavailable.py's
# docstring calls the hardest kind, a figure that is mostly right.
#
# The entry is not hidden by that. It is written under MODULE_AUTH like the other
# three, so it appears in the trail and under the screen's Authentication filter;
# it is only kept out of a total whose name would stop being true. If a future
# session wants these counted, the honest change is a card of their own, not a
# quiet addition to this tuple.
#
# ACTION_PASSWORD_CHANGE_FAILED_SELF IS OUT OF THIS GROUP FOR THE SAME REASON,
# and the temptation to include it is stronger, because unlike a revoked session
# it really is a password that was typed and refused. It is still not a sign-in
# attempt: it happens on My Account, inside a session the system already issued,
# and the two labels above would become false about the number the moment it was
# added. It is written under MODULE_AUTH and appears in the trail and under the
# Authentication filter like the rest; only the total it would misname excludes
# it. The same honest change applies -- a card of its own, not a quiet addition.
REFUSAL_ACTIONS = (ACTION_LOGIN_FAILED, ACTION_LOGIN_BLOCKED)

# Modules that are not a change to a stored record, and so are excluded from the
# "Record Updates" figure on the Audit Logs screen. A broadcast is a message that
# went out; a sign-in is an access event. Neither edits a clinical or stock row,
# and counting them as record updates would inflate the one figure on that screen
# that is supposed to answer "how much of the data has been altered".
#
# MODULE_SETTINGS joins them for the same reason and needs saying out loud,
# because one of its two entries is a read rather than a write: a settings save
# changes configuration and not a clinical or stock row, and a backup download
# changes nothing at all. Counting either as a "record update" would inflate the
# one figure on Audit Logs that is supposed to answer "how much of the data has
# been altered" -- and counting a download as an alteration would be the worst
# kind of wrong, because it would report data as having changed when what
# happened was that a copy of it left unchanged.
#
# MODULE_SERVICE_SCHEDULE joins them on the Settings argument exactly: an entry
# saying which days a service runs is the facility's configuration, not a
# clinical or stock row, and adding prenatal day to the schedule has altered
# nobody's record.
NON_RECORD_MODULES = (
    MODULE_SMS, MODULE_AUTH, MODULE_USERS, MODULE_SETTINGS,
    MODULE_SERVICE_SCHEDULE,
)

# The same exclusion drawn one level finer, for the one module whose entries are
# not all of a kind.
#
# WHY MODULE_CONFIDENTIALITY COULD NOT JUST JOIN THE TUPLE ABOVE. Two of its four
# actions genuinely change a stored consultation -- sealing one and lifting a seal
# both move a column on the row -- so excluding the whole module would understate
# "Record Updates" by every seal ever set. The other two change nothing whatever:
# a withheld view is somebody being shown a placeholder, and a refused field is a
# submission having two of its values dropped before they reached the database.
# Counting either as a record update would report data as having been altered when
# nothing was written, which is the failure ACTION_BACKUP_DOWNLOADED's note above
# calls the worst kind.
#
# So the module stays in the count and these two actions come out of it. Kept as a
# named tuple beside NON_RECORD_MODULES rather than as a condition typed into the
# query, for the reason that one is a tuple: a fifth confidentiality action added
# later must be classified deliberately, in this file, next to its own phrase --
# not discovered afterwards to have been counted as an edit to somebody's record.
NON_RECORD_ACTIONS = (ACTION_RESTRICTED_WITHHELD, ACTION_DIAGNOSIS_REFUSED,
                      ACTION_SEALED_UNOPENABLE, ACTION_CLINICAL_TEXT_REDACTED)


def log_action(user_id, action, module=None, details=None, ip_address=None,
               conn=None):
    """Append one entry. Returns its id, or None if it could not be attributed.

    A missing user_id means no entry rather than a fabricated one: user_id is NOT
    NULL and FK-constrained to a real account, and an audit row that cannot say
    who acted is worse than none -- it would read as though the change had no
    author. The caller's own write is not rolled back for it; losing a log line
    must never cost the clinical record it describes.

    `conn`: write the entry on the caller's connection and do not commit. The
    entry then commits with the change it describes, or rolls back with it, so a
    change never lacks its entry and a failed change never has one. The model
    write functions take an `audit` callback for this (see routes/audit_entries.py).
    """
    if not user_id:
        return None

    sql = """
        INSERT INTO audit_logs (user_id, action, module, details, ip_address)
        VALUES (?, ?, ?, ?, ?)
        """
    # No audit entry stores a whole phone number (Task 5e). Every writer comes
    # through here, so a number quoted in any entry's text is cut to its last four
    # digits before it is stored.
    parameters = (user_id, action, module, mask_numbers_in_text(details), ip_address)
    if conn is not None:
        return conn.execute(sql, parameters).lastrowid

    with db_connection() as own:
        cursor = own.execute(sql, parameters)
        own.commit()
        entry_id = cursor.lastrowid
    return entry_id


def get_audit_logs(module=None, limit=100):
    """Recent entries, newest first, with the acting user's name resolved.

    `limit=None` returns every matching entry rather than a page of them. The
    screen always passes a page size, because a table nobody can scroll past is
    not more useful for being longer. The export passes None: a downloaded audit
    trail that silently stopped at the hundredth entry would be the worst place in
    this system for a quiet omission, since the whole point of the file is that it
    is the complete record of who changed what.
    """
    clause = "WHERE a.module = ?" if module else ""
    parameters = [module] if module else []
    cap = ""
    if limit is not None:
        cap = "LIMIT ?"
        parameters = parameters + [limit]

    with db_connection() as conn:
        rows = conn.execute(
            f"""
        SELECT a.id, a.action, a.module, a.details, a.ip_address, a.created_at,
               u.full_name AS user_name, u.role AS user_role
        FROM audit_logs a
        JOIN users u ON u.id = a.user_id
        {clause}
        ORDER BY a.created_at DESC, a.id DESC
        {cap}
        """,
            parameters,
        ).fetchall()
    entries = []
    for row in rows:
        entry = dict(row)
        # An entry can quote a mobile number in its text. The screen, the export
        # and the dashboard feed all read here, so they show the last four digits
        # only (Task 5d, D3).
        entry["details"] = mask_numbers_in_text(entry["details"])
        entries.append(entry)
    return entries


def get_latest_entry(module, action):
    """The newest entry with this module and action, or None. Names its author.

    Its own query rather than get_audit_logs(module=...) with the caller picking
    through the result: that function filters on module only, so answering "when
    was the last backup downloaded" through it would mean fetching every Settings
    entry -- saves included -- and scanning them in Python for the right action.
    The answer is one row and the database can find it directly.

    Used by Settings' Backup pane for the only record that a backup was ever
    taken. models/backup.py writes no file and keeps no history of its own, by
    design, so the trail is not one source among several here -- it is the source.
    """
    with db_connection() as conn:
        row = conn.execute(
            """
        SELECT a.id, a.action, a.module, a.details, a.ip_address, a.created_at,
               u.full_name AS user_name, u.role AS user_role
          FROM audit_logs a
          JOIN users u ON u.id = a.user_id
         WHERE a.module = ? AND a.action = ?
      ORDER BY a.created_at DESC, a.id DESC
         LIMIT 1
        """,
            (module, action),
        ).fetchone()
    return dict(row) if row is not None else None


def count_audit_logs(module=None):
    """How many entries exist, for the module filter in force. One query, so the
    "showing N of M" line on the screen cannot disagree with the rows above it."""
    clause = "WHERE module = ?" if module else ""
    parameters = [module] if module else []

    with db_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM audit_logs {clause}", parameters
        ).fetchone()[0]
    return total


def get_audit_stats():
    """The figures the Audit Logs screen's stat cards report.

    Counted here rather than from the page's own row list: that list is capped by
    `limit`, so totals derived from it would silently start understating once the
    trail outgrew one page.

    THE TWO LOGIN FIGURES USED TO BE ABSENT, AND NOW ARE NOT
    --------------------------------------------------------
    This docstring used to say the screen's "Login Events" and "Security Events"
    cards returned nothing, because nothing was written: routes/auth.py started a
    session and logged neither the sign-in, nor the sign-out, nor the refusal. A
    count of logins would have been a count of zero dressed up as a measurement,
    which is the one thing this project's reporting rule forbids, so the template
    named the absence instead.

    That gap is closed. The login route now writes one entry per successful
    sign-in and one per sign-in refused against an account that exists, so
    `logins` and `refused_logins` below are counts of real rows and both cards
    report them.

    A refusal comes in two kinds and they are counted separately as well as
    together. `failed_logins` is a credential that did not match on an account
    that is allowed to sign in; `blocked_logins` is an account that has been
    deactivated, refused whether or not the password was right. The Security
    Events card adds them, because the question it answers is "is somebody being
    turned away"; the trail keeps them distinct, because the question an
    administrator asks next is "why", and the two answers lead to opposite
    investigations.

    Two things are still genuinely absent, and are counted nowhere because
    nothing writes them:

    * An attempt against a username that does not exist. user_id is NOT NULL and
      foreign-keyed to a real account, so there is no row such an attempt could be
      attributed to -- see log_action() above. What `failed_logins` counts is
      every refusal aimed at an account that exists, which is the only kind that
      could ever have succeeded.
    * Signing out. routes/auth.py clears the session and writes nothing, so these
      are sign-in counts and not session counts.

    Both are stated on the screen beside the figures rather than left to be
    inferred. See UNTRACKED in routes/audit_views.py.
    """
    start_of_today = day_start_utc(today())

    with db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        today_count = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE created_at >= ?", (start_of_today,)
        ).fetchone()[0]
        by_module = conn.execute(
            """
        SELECT module, COUNT(*) AS entries
          FROM audit_logs
         WHERE module IS NOT NULL
      GROUP BY module
      ORDER BY entries DESC, module
        """
        ).fetchall()
        # "Record Updates" on the screen means a change to a clinical or stock
        # record, as opposed to a message sent out or an access event -- so it is
        # every module except the ones NON_RECORD_MODULES names, rather than a second
        # list that could drift from MODULE_* above. This was "except SMS" until
        # authentication started writing; leaving it that way would have quietly
        # counted every sign-in as an edit to somebody's record.
        #
        # The action exclusion beside it is the same rule one level finer, for the
        # two confidentiality entries that change nothing -- see NON_RECORD_ACTIONS.
        # Their module is not excluded, because its other two entries do move a
        # column on a consultation.
        exclusions = ", ".join("?" for _ in NON_RECORD_MODULES)
        action_exclusions = ", ".join("?" for _ in NON_RECORD_ACTIONS)
        record_updates = conn.execute(
            f"""
        SELECT COUNT(*) FROM audit_logs
         WHERE module IS NOT NULL AND module NOT IN ({exclusions})
           AND action NOT IN ({action_exclusions})
        """,
            NON_RECORD_MODULES + NON_RECORD_ACTIONS,
        ).fetchone()[0]
        actors = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM audit_logs"
        ).fetchone()[0]

        # The two authentication figures, each selected on its own action so a
        # successful sign-in can never be counted as a refused one or the reverse.
        def _auth_count(action, since=None):
            clause = " AND created_at >= ?" if since else ""
            parameters = [MODULE_AUTH, action] + ([since] if since else [])
            return conn.execute(
                f"SELECT COUNT(*) FROM audit_logs WHERE module = ? AND action = ?{clause}",
                parameters,
            ).fetchone()[0]

        logins = _auth_count(ACTION_LOGIN_SUCCESS)
        logins_today = _auth_count(ACTION_LOGIN_SUCCESS, start_of_today)
        failed_logins = _auth_count(ACTION_LOGIN_FAILED)
        failed_logins_today = _auth_count(ACTION_LOGIN_FAILED, start_of_today)
        blocked_logins = _auth_count(ACTION_LOGIN_BLOCKED)
        blocked_logins_today = _auth_count(ACTION_LOGIN_BLOCKED, start_of_today)
        refused_logins = sum(_auth_count(a) for a in REFUSAL_ACTIONS)
        refused_logins_today = sum(_auth_count(a, start_of_today) for a in REFUSAL_ACTIONS)
        # How many distinct accounts have ever signed in -- not how many exist. An
        # account that has never signed in is absent from audit_logs entirely, which
        # is exactly what makes this figure worth reporting beside the total.
        login_accounts = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM audit_logs WHERE module = ? AND action = ?",
            (MODULE_AUTH, ACTION_LOGIN_SUCCESS),
        ).fetchone()[0]

    return {
        "total": total,
        "today": today_count,
        "record_updates": record_updates,
        "distinct_actors": actors,
        "by_module": [dict(row) for row in by_module],
        "logins": logins,
        "logins_today": logins_today,
        "failed_logins": failed_logins,
        "failed_logins_today": failed_logins_today,
        "blocked_logins": blocked_logins,
        "blocked_logins_today": blocked_logins_today,
        # What the Security Events card reports: every refusal, whatever its
        # reason. Summed over REFUSAL_ACTIONS rather than adding the two named
        # figures above, so a third refusal outcome added later is counted here
        # the moment it joins that tuple -- the alternative is a total that
        # quietly stops being one and a card that under-reports without failing.
        "refused_logins": refused_logins,
        "refused_logins_today": refused_logins_today,
        "login_accounts": login_accounts,
    }


def get_last_logins():
    """{user_id: the stored timestamp of that account's most recent sign-in}.

    One grouped query rather than one per account, so User Management's roster
    costs the same whether it lists three accounts or thirty.

    Only ACTION_LOGIN_SUCCESS is considered. A refused attempt is not a login,
    and letting one set a "last login" would be the worst possible reading of the
    column -- an account that has never once been signed into would show a time
    beside it because somebody guessed at its password. That holds for the
    deactivated case too, and matters more there: a blocked attempt can carry the
    correct password, so counting it would put a fresh "last login" against
    precisely the account whose access was supposed to have ended.

    An account missing from the result has never signed in. That absence is the
    answer, and the caller reports it as such rather than substituting a date.
    MAX() over the stored text is a correct maximum because created_at is written
    by CURRENT_TIMESTAMP in a fixed-width, zero-padded UTC format, so it sorts
    lexicographically in the same order it sorts chronologically.
    """
    with db_connection() as conn:
        rows = conn.execute(
            """
        SELECT user_id, MAX(created_at) AS last_login
          FROM audit_logs
         WHERE module = ? AND action = ?
      GROUP BY user_id
        """,
            (MODULE_AUTH, ACTION_LOGIN_SUCCESS),
        ).fetchall()
    return {row["user_id"]: row["last_login"] for row in rows}


def describe_changes(before, after, labels, formatters=None):
    """Turn two versions of a record into the readable half of an audit entry.

    Returns (summary, field_names): the "Label: old → new; ..." text, and the
    plain list of fields that moved. An empty field list means nothing changed,
    which is the caller's signal not to write an entry at all -- a save that
    altered nothing is not an event.

    Only keys present in `labels` are compared, and they are reported in that
    dict's order rather than the dict-of-values order, so two edits to the same
    record always list their fields the same way round.

    `formatters` maps a field to a callable rendering its value for a person: a
    temperature gains its unit, a date is spelled out. Anything without one is
    shown as stored, quoted if it is text, so a trailing space or a changed case
    is visible rather than looking like no change at all.
    """
    formatters = formatters or {}
    parts, changed = [], []

    for field, label in labels.items():
        old_value = before.get(field)
        new_value = after.get(field)
        if _same(old_value, new_value):
            continue
        changed.append(field)
        render = formatters.get(field, _default_render)
        parts.append(f"{label}: {render(old_value)} → {render(new_value)}")

    return "; ".join(parts), changed


def _same(old_value, new_value):
    """Whether two stored values are the same as far as an audit trail cares.

    None and "" are the same absence -- a field cleared to empty text and one
    never filled in both mean "not recorded", and reporting a move between them
    as a change would fill the log with edits nobody made. Numbers are compared
    numerically so 37 and 37.0 do not read as an edit.
    """
    if old_value is None or old_value == "":
        old_value = None
    if new_value is None or new_value == "":
        new_value = None
    if old_value is None or new_value is None:
        return old_value is new_value

    if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
        return float(old_value) == float(new_value)
    return str(old_value) == str(new_value)


def _default_render(value):
    if value is None or value == "":
        return "not recorded"
    if isinstance(value, (int, float)):
        return str(value)
    return f'"{value}"'
