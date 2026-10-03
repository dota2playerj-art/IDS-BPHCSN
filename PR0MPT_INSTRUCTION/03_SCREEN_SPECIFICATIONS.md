# IDS-BPHCSN SCREEN SPECIFICATIONS

Version: 2.0

Status: Screens 01–15 approved. Screens 16–20 specified from the built system and reconciled against the code on 2026-08-15. Screen 21 (My Account) specified 2026-09-05; the file and screen counts and the Screen 11 and Screen 13 entries in the reconciliation section were re-checked against the running system on the same date. The Doctor role and the clinical-authority split added 2026-09-25 — see "Clinical Authority and the Doctor Role".

---

# Purpose

This document defines every screen of the IDS-BPHCSN system.

The system has 21 screens. Screen 19, Notifications, was a placeholder with no data and was removed in Task 7; its number is not reused.

Screens 01 to 15 are the original approved specifications and are unchanged below. Screens 16 to 20 were built after this document was first written and are specified here for the first time. Screen 21, My Account, was built on 4 September 2026, and Screen 22, Service Schedule, on 26 September 2026; both are specified at the end.

`templates/` holds 29 `.html` files. Twenty-three of them belong to the 21 screens (Patient Profile has a second file, `patient_profile_demographics.html`, the Administrator's demographics-only copy; Medicine Inventory has a second file, `inventory_item.html`, the item page). The other six are not screens, and are not screens for two different reasons (the sixth, `error.html`, is the plain page shown for a 404 or 500):

- **`base.html`** is the shared layout — sidebar, header, content region — that every screen renders inside.
- **`_print.html`** and **`_chart_table.html`** are partials, included by the screens that print and the screens that render a chart's underlying figures as a table.
- **`maintenance.html`** is a *response page*, not a screen. It has no route, no sidebar entry and no URL of its own: `utils/security.py::_maintenance_response()` renders it with a 503 status **instead of** whatever screen the request asked for, while maintenance mode is on. Nothing navigates to it, so it is closer to an error page than to a screen, and counting it as one would imply somewhere to click that does not exist.

Why My Account **is** counted as a screen when `maintenance.html` is not: it has its own route (`/account`), its own guard, its own context and a form that writes. It is entered deliberately, from the profile chip in the header rather than from a sidebar — which makes it unusual among the 22, but no more so than Patient Profile, Add/Edit Medicine and Record Consultation, which are also reachable only from another screen.

Record Consultation and Edit Consultation are two modes of one template, `record_consultation.html`, rendered by one shared context builder, and are specified together as Screen 20.

Screens 16 and 17 carry the numbers the code already uses for them (`routes/official.py`). See "Reconciliation With The Built System" at the end of this document for the numbering drift that exists in a few code comments.

Each screen specification includes:

- Purpose
- Authorized User
- Layout
- Components
- Navigation
- Actions
- Validation
- Backend Notes

The Login Page and Administrator Dashboard are the official visual references for the entire system.

Every screen must reuse the same design system.

---

# SCREEN 01

## Login Page

Purpose

Authenticate authorized users.

Authorized Users

- Administrator
- Doctor
- Health Center Staff
- Barangay Official

Components

- Logo
- System Title
- Username
- Password
- Show Password
- Remember Me
- Login Button

Behavior

Authenticate user.

Redirect based on role.

If the account must set its own password (new account, password reset by an Administrator, or a first-time password from a new install), go to My Account first (Screen 21). No other screen opens until it is done.

Session limits (added 2026-09-29): a person is signed out after 30 minutes without activity, and 12 hours after they sign in. Two minutes before the idle limit, the page asks "Are you still there?". The server enforces both limits and records each sign-out in the audit trail.

Form tokens (added 2026-09-29): the login form, like every form, carries a hidden token from the page. A form sent without a valid token (for example, an old page after signing out in another tab) is not acted on. The person sees a plain page, "Your session expired. Please sign in again and repeat what you were doing.", with a Sign in button.

Messages

The login form shows only known messages: invalid credentials, maintenance mode, signed out after 30 minutes without activity, and signed out after 12 hours. The link carries a short key, never the sentence. An unknown key shows nothing.

Validation

Required fields.

Invalid credentials.

There is no account lockout. A refused sign-in is recorded in the audit trail.

Navigation

Successful Login

↓

Dashboard

---

# SCREEN 02

## Administrator Dashboard

Purpose

Provide an operational overview of the health center: counts, stock and system activity. Since
Task 5c (2026-10-01) it lists no visit and no child by name; clinical data is for the care team.

Components

Sidebar

Header

Counts: Total Registered Patients, Today's Appointments, Active Inventory Items, Low Stock Items,
SMS Messages Sent, Monthly Consultations, and Waiting for the Doctor (a count, no names)

Monthly Analytics

Medicine Inventory

Immunization Follow-up (counts)

SMS Broadcast (counts only)

System Activity

Actions

Open any module.

Send an SMS broadcast.

Generate reports.

Search patient.

---

# SCREEN 03

## Patient Records

Purpose

Manage all registered patients.

Components

Search Bar

Advanced Filter

Patient Table

Pagination

Add Patient Button

Export Button

Actions Column

Table Columns

Patient ID

Full Name

Age

Gender

Address

Contact Number

Last Visit

Status

Actions

Search

Filter

Sort

View

Edit

Archive

Print

Backend Notes

Retrieve data from SQLite.

---

# SCREEN 04

## Register Patient

Purpose

Register a new patient.

Sections

Personal Information

Emergency Contact

Medical Information

Buttons

Save

Cancel

Reset

Fields

Patient ID

First Name

Middle Name

Last Name

Birthdate

Age

Gender

Civil Status

Address

Contact Number

Blood Type

Medical Conditions

Allergies

Validation

Required fields.

Duplicate patient detection.

---

# SCREEN 05

## Patient Profile

Purpose

Display complete patient information to the care team: the Doctor and Health Center Staff.

The Administrator's profile (Task 5c, 2026-10-01) is demographics only: patient ID, full name,
sex, age and birth date, address, status and registration date, read-only, with one plain line
where the tabs would be: "Clinical details are shown only to the Doctor and Health Center Staff."
It is a separate template, `patient_profile_demographics.html`, built from the demographic columns
only. No contact number is shown to him.

Tabs

Personal Information

Medical History

Consultation History

Medicine History

Vaccination Records

Appointment History

Buttons

Edit

Print

Back

---

# SCREEN 06

## Medicine Inventory

Purpose

Manage medicines.

Components

Search

Filter

Medicine Table

Low Stock Widget

Expiring Soon and Expired Widgets

Buttons

Add Medicine

Export Excel and Export PDF

Columns

Item (the display name: generic name, strength and form)

Category

Usable Stock

Reorder Level

Nearest Expiry

Expiring Soon (number of batches)

Expired (number of batches)

Status

**Stock is kept in batches (Task 12, 2026-10-03).** Usable stock is the sum of the item's batches that are
not expired. The Expiring Soon card counts batches that expire within 90 days and still hold stock; the
Expired card counts expired batches that still hold stock. Neither is part of any item's stock. A row opens
the **item page** (a second template of this screen, `inventory_item.html`): the item's details, a table of
its batches (lot, brand, source, date received, expiry, quantity received, quantity left, status), the
Receive stock form, a Remove from stock button on every batch that holds stock (an expired batch is
prompted), and the latest removals. The row's other actions are Edit details and Archive.

---

# SCREEN 07

## Add/Edit Medicine

Purpose

Manage medicine details.

Fields (a medicine)

Generic Name (required)

Strength (required; free text such as "500 mg" or "250 mg/5 mL")

Dosage Form (required; one list: tablet, capsule, syrup, suspension, drops, sachet, injection, cream,
ointment, inhaler, other)

Category (the drug class)

Unit, Reorder Level, Unit Cost, Manufacturer, Supplier, Storage Location, Notes, Status

Fields (a supply or equipment item)

Item Name (required) and Size or Specification, then the same unit, reorder level and the rest.

Buttons

Save

Cancel

Validation

There is no separate Medicine Name: the display name is built, for example "Paracetamol 500 mg tablet". Two
items with the same generic name, strength and form are refused. There is no quantity and no expiry date
on this screen: Edit details never changes stock. The brand name is entered when stock is received.

**Receive stock (Task 12).** On the item page. Lot number (required, or tick "No lot number"), expiry date
(required for a medicine, optional for a supply, not already past), quantity received (a whole number of 1
or more), date received (default today, not in the future), source (DOH, Municipal Health Office / RHU,
Barangay purchase, Donation, Other), optional brand name. It adds one batch and writes one audit entry.

**Remove from stock (Task 12).** On the item page, per batch. An amount from 1 up to what the batch holds,
a required reason (Expired, Damaged, Lost, Returned, Count correction) and an optional note. It takes the
amount out of that one batch and writes one audit entry (item, lot, amount, reason; the note is not copied).

---

# SCREEN 08

## Patient Queue

**Statuses and what moves a visit (Task 6b, 2026-10-02).** Waiting, then In Consultation. Saving the intake
makes the visit *Waiting for the Doctor* when its service needs a diagnosis and none was written, otherwise
*Completed*. The Doctor's diagnosis makes it *Completed*. The Completed card counts finished visits only; the
footer counts Waiting for the Doctor on its own.

**Send to the Doctor (Task 6c).** On a visit In Consultation whose service needs the Doctor, the button that
closed a visit with nothing written is **Send to the Doctor**. It sets Waiting for the Doctor. The server
refuses Completed on such a visit without a diagnosis ("This visit needs the Doctor first."). Services that do
not need him keep **Mark Completed**. Neither button is on the Administrator's queue.

**What each role can do on a row (Task 6d, 2026-10-03).** One mapping, status by role, decides the buttons
and the server's answer. Waiting: Staff and the Doctor can Start, mark Left before being seen, Change
service. In Consultation: Staff and the Doctor can open the intake (Record Consultation), Send to the Doctor
or Mark Completed (by service), mark Left, Change service. Waiting for the Doctor: the Doctor has **See
patient**; Staff and the Doctor can mark Left and Change service. Completed: view only. Left before being
seen: view only, plus Undo the same day. The Administrator only views. **See patient** opens the visit's
consultation record when Staff did the intake, or a new consultation for the visit when they did not (the
Doctor records vitals, complaint, diagnosis and treatment plan). Saving with a diagnosis makes the visit
Completed.

**Wording (Task 6d).** The colour legend lists the five statuses: Waiting, In Consultation, Waiting for the
Doctor, Completed, Left before being seen, each with the colour of its badge; the calendar's dots use them.
The summary line under the table uses the same five names. There is no Walk-in tag (every visit is a
walk-in). The vaccine badge says "2 vaccines: no record", or "1 vaccine: due" when none lacks a record.

**Change service never completes a visit (Task 6e).** If a visit that is Waiting for the Doctor is changed
to a service that does not need him, it goes to In Consultation, so the service is recorded first (refused
while another patient is in consultation). A service that needs him keeps today's status. The first Waiting
patient's badge reads **Next in line** (a display label; the stored status is Waiting).

**Service at check-in (Task 6b).** The Check In dialog has a required **Service** list on both tabs
(existing patient, new patient), with no default: Consultation, Follow-up Consultation, Hypertension /
Diabetes Monitoring, Prenatal Check-up, Immunization, Dental. A row has a **Change service** button, with a
dialog, while the visit is Waiting, In Consultation or Waiting for the Doctor. Health Center Staff and the
Doctor only. The Administrator's queue shows no service column, filter or button. An earlier day's Waiting
visit offers only Left before being seen: no Start and no Change service (Task 13).

**Left before being seen (Task 6, 2026-10-02).** A new status for a patient who checked in and went home.
Health Center Staff and the Doctor have a button on the row. It opens a dialog: "Mark this patient as left
before being seen?" The button is offered when the visit is Waiting, In Consultation, or Waiting for the
Doctor. It is refused on a visit with a diagnosis, and on one that is finished. The entry records who and
when and writes one audit entry ("Name (PAT-005), visit APT-00081."). **Undo** is on the row the same day and
puts the visit back to its previous status; it is refused on a later day, and refused while another patient is
in consultation if the visit was In Consultation. The Administrator's queue is read-only: no button, and the
server refuses his POST. The table footer counts these visits.

**Open visits from earlier days (Task 10, 2026-10-03).** Under the table: every visit from a day that has
gone and is still Waiting, In Consultation or Waiting for the Doctor, oldest first, with a Status column. Its
buttons come from the same status-by-role mapping as today's rows, so the Doctor sees **See patient** on a
visit waiting for him, and Staff and the Doctor can mark a visit Left before being seen. The Administrator sees
the list read-only. Nothing closes a visit automatically. The line under Today's table starts "Today:" and
gives the five status counts; a line under this section, "Earlier days:", gives the three open ones. The
Doctor's dashboard count, the Staff count and the queue (today plus earlier days) are the same number.

**Start is for today (Task 11, 2026-10-03).** A visit from an earlier day with status Waiting offers only Left
before being seen (and Change service); Start is not shown, and a Start POST on it is refused by the server
and by the SQL. A visit Waiting for the Doctor keeps See patient for the Doctor, whatever its day. The
mapping holds the day rule. **Older records:** the figures no longer show "Still expected", "Cancelled or
no-show", "Never closed" or "not yet arrived". A visit still carrying one of those four old statuses is
counted in one line, "Older records: N", on the reports, the community report and the files, and only when N
is above 0.

Purpose

Work today's queue: record who has arrived, in the order they arrived, and see
what each day of the month held.

Renamed from **Appointment Scheduling** on 2026-09-05, when advance booking was
retired. The screen no longer schedules anything; the name now says what it is.
The URL, the endpoint and the template file keep their old names.

Components

Services Today (a strip under the title, read from Screen 22 — added 2026-09-26)

Calendar (a record of each day's visits — it is not booked against)

Today's Queue

Buttons

Check In Patient

Start Consultation

Record Consultation

Mark Completed

Fields

Patient

Reason for visit (shown to the Doctor and Health Center Staff only; the Administrator's queue, its
export and its PDF have no reason column, for any visit — updated 2026-10-01, Task 5b. On a
Restricted visit the reason is encrypted: the Doctor reads it on screen, Health Center Staff see
"Restricted — Doctor access only", and no file or printout carries it.)

Status

Removed with advance booking: the Upcoming Appointments panel, the Upcoming
Reminders strip, and the Schedule / Reschedule / Cancel buttons and their three
dialogs, along with the Date, Time and Assigned Staff fields they collected. See
`utils/unavailable.py` `advance_booking`, which the screen itself quotes.

Services Today lists what the Service Schedule (Screen 22) says runs on the queue's own date, with
each service's note. With nothing entered it says the schedule has not been filled in, and with
nothing on today it says so; it never draws a blank. It restricts nothing: check-in, the queue order
and the consultation actions ignore it.

---

# SCREEN 09

## Community Notifications

Purpose

Send announcements.

Components

Recipient Selection

Message Editor

SMS Preview

Character Counter

Delivery Status

Buttons

Send

Save Draft

Schedule

History

Recipients

Residents

Senior Citizens

Pregnant Women

Parents

Health Workers

Entire Barangay

Who sees whom (final fixes, 2026-10-02). The Doctor and Health Center Staff see the recipients of the
most recent broadcast by name, with each mobile number masked to its last four digits ("•••• ••• 1234").
The Administrator and the Barangay Official see recipient counts only, for every audience: total, sent
and failed per broadcast, and a count per audience. They see no recipient name and no number. This is
decided on the server, in `get_broadcast_recipients()`, not in the template. The system receives no
delivery reports, so no message is ever marked delivered.

---

# SCREEN 10

## Reports & Analytics

Purpose

Generate reports.

Charts

Monthly Consultations

Medicine Usage

Patient Registration

Appointment Statistics

Tables

Top Diseases

Low Stock Medicines

Vaccination Summary

Buttons

Generate

Print

Export PDF

Export Excel

---

# SCREEN 11

## User Management

Purpose

Manage system users.

Columns

Name

Role

Username

Status

Last Login

Buttons

Add User

Reset Password

Disable

Enable

Delete

Passwords set here (added 2026-09-29)

Add User and Reset Password both say: "The user must change this password the first time they sign in." The account is marked, and the person must set their own password on My Account before they can open any other screen.

Roles

Administrator

Doctor

Health Center Staff

Barangay Official

---

# SCREEN 12

## Audit Logs

Purpose

Monitor activities.

Columns

Date

Time

User

Action

Module

IP Address

Status

Filters

User

Date

Action

What it records (added 2026-09-29, Task 4): changes to patient, clinical, stock and account
records, the Patient Queue, sign-ins, settings and SMS broadcasts. Each entry is written in the
same transaction as the change it describes, so a successful write always has one and a failed
one never does. No entry quotes a diagnosis, a treatment plan, a sealed field, a password or a
full contact number.

---

# SCREEN 13

## Settings

Purpose

Configure the system.

Sections (as built)

General Settings (the health center's name and address, and its opening and closing times; saved)

SMS (one line: "SMS mode: Live" or "SMS mode: Simulated")

Security Settings (read-only: what is enforced and what is recorded)

Password Policy (read-only)

Backup & Restore (Download Backup; restoring is done with `restore_backup.py`, and the screen says so)

System Maintenance (the maintenance switch)

About System

Buttons

Save (General Settings)

Download Backup

Turn maintenance mode on or off

There is no Restore button, no Reset, and no SMS gateway form. Restoring replaces every record, so it is
done on the health-center PC with `restore_backup.py`, which checks the file first.

Security pane (updated 2026-09-29)

It holds no controls. It states the rule in one read-only line: "Users are signed out after 30 minutes without activity, and 12 hours after they sign in." It also lists what is enforced and the sign-in counts. The old disabled controls (session timeout box, login attempt limit, two-factor switch, auto logout switch) were removed. Two-factor sign-in and lockout are not part of this system.

---

# SCREEN 14

## Health Center Staff Dashboard

Purpose

Dashboard for healthcare workers.

**Waiting for the Doctor (Tasks 6 and 6b, 2026-10-02).** On the Doctor's dashboard, a list of every visit with
the status Waiting for the Doctor, oldest first, across all days. Each row shows the patient's name and ID,
the check-in date and time, the service, how long it has waited ("2 days"), and a button: See patient
(the same one as on the Patient Queue: it opens the saved record, or a new consultation when there is none).
The list says "Patients who need a diagnosis, oldest first." Health Center Staff see one card, "Waiting for
the Doctor: N", and no list. The Administrator's dashboard has the same card and no names. Immunization,
prenatal and dental visits never get this status. A sealed visit is listed by name only and shows no sealed
text.

Widgets

Waiting for the Doctor (the Doctor's list; a count for Health Center Staff)

Today's Appointment List (the Patient Queue)

Recent Patient Registrations

Medicine Stock Alerts

Immunization Follow-up

Calendar

Quick Statistics

Quick Actions

No access to

User Management

Settings

Audit Logs

---

# SCREEN 15

## Barangay Official Dashboard

Purpose

View community health information.

Widgets

Community Health Overview

Community Announcement Feed (the SMS broadcasts sent)

Upcoming Health Events

Vaccination Campaign Schedule

Health Programme Membership

Recent Reports

Broadcast Send Summary (counts only)

Monthly Community Statistics

Quick Actions

View Reports

View Notification History (the SMS broadcast history)

No access to

Patient Medical Records

User Management

Settings

Inventory Management

---

# SCREEN 16

## Health Programs

Purpose

Report barangay health programme membership to the Barangay Official.

Authorized Users

- Barangay Official

Components

Programme Membership Cards

Programme List

Membership Breakdown

Untracked Notices

Programmes Reported

Immunization

Senior Citizen

Programmes Not Tracked

Prenatal

TB DOTS

Family Planning

Nutrition

Oral Health

Dengue Prevention

Backend Notes

Context built in `routes/official_views.py::health_programs_context()`.

There is no programmes table and no enrolment table. The two programmes reported are derived memberships counted from patient records, and each prints the basis it was counted on. The six with no source in the schema report their own absence rather than showing a figure.

Membership is reported as memberships, not people: a patient who qualifies for both programmes is counted under both.

The programme pair is `report_views.programs` — the same values Screen 10 and the Barangay Official Dashboard print, so the three screens cannot disagree.

This screen carries no doughnut chart. Two overlapping cohorts are not slices of one whole.

---

# SCREEN 17

## Vaccination Campaigns

Purpose

Report immunisation coverage against the Department of Health Expanded Program on Immunization (EPI) infant schedule.

Authorized Users

- Barangay Official

Components

Coverage Stat Cards

Per-Dose Coverage Table

Per-Vaccine Coverage Donuts

Untracked Notice

Reporting Unit

The scheduled EPI dose, not a named campaign.

Table

One row per scheduled dose — 14 rows, matching `EPI_SCHEDULE`.

Donuts

One per vaccine — 8, matching the distinct vaccine codes in `EPI_SCHEDULE`.

Backend Notes

Context built in `routes/official_views.py::vaccination_campaigns_context()`.

Figures come from `get_immunization_coverage()` and `get_dose_coverage()`, the same calls behind Screen 10 and the Barangay Official Dashboard.

**Honest status (Task 9, 2026-10-03).** "Overdue" is gone from every screen, badge, report and export. A dose
with nothing on file reads **No record** and still shows its due date. The dose table has the columns Given,
Given Elsewhere (Card), Parent Says Given, No Record, Due Now, Not Yet Due and Coverage. Coverage counts a dose
given here or seen on a card; a parent's word is its own column and is not counted. The Immunization Record tab
of the Patient Profile (Staff and the Doctor) has a **Record dose given elsewhere** button on every scheduled
dose that has no given-here or card record: a dialog asks for the proof (card seen, or the parent's word), the
date (required for a card, never in the future or before birth), and the place (optional). A card shows
"Given elsewhere" (green) with its date and place; a parent's report shows "Parent says given — no card"
(amber). Either can be changed or removed from the same row; a parent's report is upgraded by recording the card.
The profile alert (Task 15) is a title ("<N> doses to follow up") and one line listing the doses, for example
"Pentavalent dose 1 (repeat from Oct 31, 2026); BCG and Hepatitis B (parent says given, no card). Ask for the
vaccination card." The button shows only from 4 days before a dose's minimum age (and on rows with a parent's
report or a repeat), and the server refuses the others. The Due column shows the earliest date the dose can be
given, or "After <dose>" when the previous dose has no record. Ages read "12 days", "4 weeks 2 days", "5 months 3
days", "2 years 6 months", "7 years" on every screen. The Administrator and the Official have no such button or route. The
reasoning, the CDC basis and the FHIR mapping are in `01_PROJECT_BIBLE.md`.

Named campaigns are declared untracked. Nothing in the schema groups doses into a campaign — there is no campaign table, no target group and no coverage goal.

`coverage_pct` is None, not 0, on an empty cohort.

---

# SCREEN 18

## Community Reports

Purpose

Present a community-level health summary to the Barangay Official.

Authorized Users

- Barangay Official

Components

Summary Cards

Charts

Report Tables

Date Selector

Implementation Status

**Built and data-driven, as of 21 August 2026.** This entry previously read "Presentation only… every figure on the screen is written into the markup", and that has not been true since the screen was wired. `routes/official.py::community_reports()` passes `community_reports_context(args=request.args)`.

Every figure comes from `reports_analytics_context()` rather than being counted here, which matters more on this screen than on any other: Community Reports is the screen a barangay official reads a number off and puts in front of somebody, and a figure here that disagreed with Reports & Analytics would be two reports of one barangay wearing one name. The date selector is wired to the same range parser Screen 10 uses.

Export Excel and Export PDF are both real (`routes/report_export.py`), and Print works. Figures the schema cannot establish are reported as absent rather than invented.

---

# SCREEN 19

## Notifications — removed

This screen was a presentation-only placeholder: there is no notifications table and nothing writes one.
It was removed in Task 7, with its route, menu item and header bell. The real, recorded community
notification mechanism is Screen 09 (SMS Notifications). The number 19 is not reused.

---

# SCREEN 20

## Record / Edit Consultation

Purpose

Write up the clinical record of a completed visit, and edit a record already written.

Authorized Users

- Administrator (intake only)
- Doctor
- Health Center Staff (intake only)

Entry Points

Record — Patient Queue, on a queue entry moved to In Consultation.

Edit — Patient Profile, Consultation History tab, Edit action.

Sections

Patient Banner

Vital Signs

Clinical Record

Immunizations Given Today

Follow-Up

Fields

Chief complaint

Diagnosis (Doctor only)

Treatment plan / medicines given (Doctor only)

Mark this consultation Restricted (Doctor only)

Additional notes

Temperature

Blood pressure

Pulse rate

Respiratory rate

Weight

Height

Head circumference

Follow-up date

Buttons

Save

Cancel

Validation

Numeric ranges are enforced per field: Temperature 25–45 °C, Pulse rate 20–250 bpm, Respiratory rate 5–100 breaths/min, Weight 0.5–400 kg, Height 20–250 cm, Head circumference 20–70 cm.

Recording is refused unless the queue entry is In Consultation. A patient still in the waiting room cannot be written up.

Recording is refused if that queue entry has already been written up; the operator is sent to Consultation History to edit the existing record instead. This is enforced in `record_consultation_context()`, not by a database constraint.

Immunizations Given Today

Shown for patients under 5 only.

Every scheduled dose is offered, not only the outstanding ones, so a health worker catching a child up can see the whole schedule.

A dose already on file renders as a locked fact with the date it was given, not as a checkbox.

**Only eligible doses can be ticked (Task 13).** A dose is eligible today only if the child has reached its
minimum age, the previous dose of the same series is on file (given here or a card) and valid, and the minimum
interval has passed. A dose that is not eligible is greyed out, with the earliest date ("From Nov 14, 2026")
or the reason ("Needs Pentavalent dose 1 first"). The server refuses any non-eligible dose with one message
("This dose is not due yet. Earliest date: Nov 14, 2026."). Several eligible doses at one visit are allowed.
A dose given too early, whether given here or seen on a card, reads "Given too early — ask the Doctor about a repeat"
(amber) and does not count (Task 14). Its record stays on file. The same dose is eligible again from the later of its
minimum age and the invalid date plus 4 weeks, and the repeat is a new record. On the Immunization Record tab the
dose's row shows the record that counts; earlier records show under it ("Earlier dose on Nov 14, 2026 was too
early"), each with its Correct or Change button.
The table of minimum ages and intervals, the WHO and ACIP basis, and the note that there is no override
(outbreak campaigns that use other ages are outside this version) are in `01_PROJECT_BIBLE.md`.

The form is add-only for immunisations. A previously recorded dose cannot be removed here. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §10 for the reasoning.

Backend Notes

One template, `record_consultation.html`, rendered by two blueprints with one shared context builder in `routes/consultation_views.py`, so the Administrator's variant and the clinical floor's (Health Center Staff and Doctor) cannot drift apart. Each route keeps its own role guard and its own redirect target.

Only the Doctor is drawn, required and allowed to save the diagnosis and treatment plan. For the Administrator and Health Center Staff the panel is titled "Notes & Follow-up" and says the Doctor records the assessment. A diagnosis in a submission from either role is discarded server-side. See "Clinical Authority and the Doctor Role".

Recording is anchored to a queue entry and completes it on save.

Editing writes an audit entry naming what changed, and touches neither the patient, the visit date, nor who originally recorded it.

Immunisation tracking on this screen extends beyond the original scope of this document. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §9.

---

# SCREEN 21

## My Account

Purpose

Show the signed-in person their own account details, and let them change their own password without asking the Administrator.

Authorized Users

- Administrator
- Doctor
- Health Center Staff
- Barangay Official

All four, identically. This is the one screen in the system guarded by `@login_required` rather than `@role_required`, because what it reaches is not a role's worth of screens — it is one row, the caller's own.

Navigation

Entered from the profile chip in the header, on any screen. It has no sidebar entry, because it belongs to no role's menu.

Sections

Account Details

Change Password

Fields

Current Password

New Password

Confirm New Password

Read-only on this screen

Full name

Role

Username

Actions

Change Password

Validation

The current password must be supplied and must match. This is the whole difference between this screen and the Administrator's reset on Screen 11: a reset exists precisely *because* the old password is unavailable, and a change exists precisely because it is available and is the only thing proving the person at the keyboard is the account holder rather than whoever found the machine still signed in.

The new password is checked against the same password policy Screen 11 applies — length, character kinds, and refusal of anything containing the username or the person's own name.

When the account must set its own password (added 2026-09-29), the screen says "Please set your own password before you continue." Every other screen sends the person back here until they do. Logout still works. The new password must also differ from the current one. A successful change clears the requirement, and the audit entry says so.

A refused submit re-renders this screen at 200 with the error beside the box it belongs to, the project's form-redisplay standard. Nothing typed is written back into the page: all three boxes hold a password, and re-rendering one into the markup would put it somewhere it should not be.

Backend Notes

Context and both handlers live in `routes/account_views.py`.

**Neither handler takes an account to act on, and that is the guard.** Both call `get_current_user()` and act on whatever comes back, so there is no parameter, no hidden field and no path by which a request could name a different account. A posted `user_id` is not rejected — it is never read, which is the stronger answer.

Name, role and username are deliberately not editable here. That is the same boundary Screen 11 draws, kept from the other side: a role a person can raise on themselves is not a role, and a name the audit trail attributes actions to should not be changeable by the person the trail is about. The username is fixed for the life of the account for anybody.

There is no photograph, contact detail or preference of any kind, because nothing in this application stores or reads one.

Both outcomes are audited. A successful change writes "Changed own account password"; a refused one writes "Refused own-password change attempt", in the same shape the sign-in entries use, so an attempt against a password somebody does not know is as visible as a refused sign-in.

---

# SCREEN 22

## Service Schedule

Purpose

Say which services the health center runs on which days, so the people at the desk and in the
barangay know what is on. Built on 26 September 2026 as the successor to advance booking: the
facility decides the days, and patients walk in.

Authorized Users

- Administrator — reads, adds, edits and deletes
- Doctor — reads
- Health Center Staff — reads
- Barangay Official — reads

Navigation

A sidebar item for all four roles: beside the Patient Queue for the Administrator, the Doctor and
Health Center Staff, and after Health Programs for the Barangay Official. The Patient Queue's
Services Today strip links to it.

Sections

Running today

The week (Monday to Sunday, each service under every day it runs)

All entries (each once, with its note, and the next two dates for an entry tied to weeks of the
month)

Add / Edit / Delete panel (Administrator only)

Fields

Service — typed; names already on the schedule are suggested

Days it runs — Monday to Sunday, at least one

Weeks of the month — 1st to 4th, optional; blank means every week

Note — optional; anything that decides whether the service actually runs

Actions

Add to schedule, Save changes, Delete entry (Administrator only)

Validation

A service is required, 80 characters at most. At least one day. Weeks are 1st to 4th only, and
ticking all four is refused with a message to leave them blank, since four is not "every week" in a
month with a 5th occurrence. A note of 300 characters at most. An exact duplicate of an existing
entry is refused. A refused submit re-renders the screen at 200 with the panel holding exactly what
was typed and each message beside its field, the project's form-redisplay standard.

Backend Notes

Storage is the `service_schedule` table, which **ships empty**: the health center's days have not
been confirmed, so none were entered, and the screen says so rather than drawing seven blank days.
A day pattern is two columns: ISO weekday numbers, and optionally which occurrences in the month.
"Every weekday", "every Monday and Thursday" and "every 2nd and 4th Wednesday" are each one row.
See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §19.

The three reading routes (`/admin`, `/staff`, `/official`) share one context builder in
`routes/schedule_views.py`. The three writing routes exist under `/admin` only, guarded to the
Administrator, so a forged form from any other role has nowhere to go. Every add, edit and delete
is audited under the Service Schedule module. The schedule is information only: it restricts no
check-in or consultation and is not connected to SMS.

---

# Clinical Authority and the Doctor Role (added 2026-09-25)

The system has **four** roles: Administrator, Doctor, Health Center Staff, Barangay Official. The
Doctor was added when field data from the RHU of San Francisco, Surigao del Norte, showed that
clinical authority is the RHU physician's, while the Administrator — Kagawad Antonio Acido, a
barangay official and not a physician — administers the system. The decision record is in
`01_PROJECT_BIBLE.md` and `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §18.

**Which screens the Doctor reaches.** Health Center Staff's: Login, the clinical dashboard
(Screen 14, titled "Doctor Dashboard" for this role), Patient Records, Register Patient, Patient
Profile, Medicine Inventory, Add/Edit Medicine, Patient Queue, Record / Edit Consultation, SMS
Notifications (view-only, as staff see it) and My Account — plus Reports & Analytics (Screen 10),
with the same figures and the same Excel and PDF exports the Administrator and the Barangay Official
get. The Doctor is refused User Management, Audit Logs and Settings.

**What only the Doctor may do on those screens**, enforced on the server from the signed-in
account's stored role, not by hiding a control:

| Action | Screen | Doctor | Administrator | Health Center Staff |
|---|---|---|---|---|
| Enter or edit Diagnosis and Treatment Plan | 20 | Yes | No (no Screen 20) | No — intake only |
| Record or edit consultation intake | 20 | Yes | No (no Screen 20) | Yes |
| Mark a consultation Restricted, or lift it | 05, 20 | Yes | No | No |
| Read a Restricted consultation's diagnosis, plan, chief complaint and notes | 05, 20 | Yes | No (demographics only) | Placeholder |
| Read any clinical field, unsealed or not | 05, 20 | Yes | No (demographics only) | Yes |
| Read patient contact numbers | 03, 05, 09 | Yes | No | Yes |
| Read the check-in reason on the Patient Queue | 08 | Yes | No | Yes (placeholder if Restricted) |
| Check in, start or complete a visit on the Patient Queue | 08 | Yes | No (read-only) | Yes |
| Read the medicine names dispensed to a patient | 05, 20 | Yes | No | Yes |
| Register or edit a patient | 04 | Yes | No | Yes |
| Correct a recorded vaccination | 05 | Yes | No | Yes |
| Set a patient to Deceased, or reverse Deceased | 03 | Yes | No | No |
| Move a patient between Active and Inactive | 03 | Yes | No | Yes |

The Administrator's column changed on 2026-10-01 (Task 5c). Clinical data is for the care team
only: RA 11166 allows sharing only with health workers involved in the patient's care, RA 10173
requires processing to be adequate, relevant and not excessive, and the project follows the
minimum-necessary standard. This extends the reasoning behind the Doctor role. Each "No" is
enforced on the server: his `/admin/...` write routes are deleted, the `/staff/...` ones send him
to his dashboard, and his patient screens read demographic columns only.

A field a role may not write is not drawn for it, and a submission carrying it anyway has it
discarded before validation. On an edit, the stored value is put back and the refusal is recorded
in the audit trail, without the submitted text. The placeholder a non-Doctor sees reads
**"Restricted — Doctor access only"**. The sealed text is not in the page at all.

**Screen 12.** An audit entry for a consultation edit names the fields that changed ("Changed:
Temperature, Chief complaint") and never quotes a value, sealed or not (Task 5b; vitals too since
Task 5c). Dispensing and dose entries say how many, for whom and at which consultation, and never
which medicine or vaccine: "Dispensed 2 items for <Name> (PAT-005) at consultation #42." Audit Logs
are read by the Administrator.

**Screen 10 and 18.** Restricted consultations count in every total. In the diagnosis ranking they
appear as one row, **"Confidential"**, for every viewer, the Doctor included (updated 2026-10-01).
The Doctor reads sealed text on the patient's own record (Screens 05 and 20), never in an
aggregate or its exports.

**Screens 10 and 18, small counts (Task 5d, 2026-10-02).** For the Administrator and the Barangay
Official, every ranking or breakdown by diagnosis, complaint, chronic condition or dispensed
medicine folds any row with a count of 1 to 4 into one row, **"Other (each fewer than 5)"**. The
"Confidential" row folds the same way when its count is under 5, and the restricted-visit count line
reads "Fewer than 5". The charts, the printed tables, the Excel file and the PDF read the same
folded list. Totals stay exact. The Doctor sees every count. For dispensing, the test is on the
number of issues, since one issue is one visit. The reason: the Administrator can see who is in the
queue and when, so a count of 1 over a short range can identify a person. The threshold is
`SMALL_COUNT_THRESHOLD` in `config.py`.

**Screens 10 and 18, services and single counts (Task 5e).** "Appointments by service requested"
(screen, chart, print table, Excel, PDF) folds like the other rankings. A single count tied to a
condition or service reads "Fewer than 5" when it is 1 to 4, for the Administrator and the Official.

**Screen 12 (Task 5e).** No audit entry stores a whole phone number; entries are written masked.

**Screen 09, masked numbers (Task 5d).** The recipient list and the appointment-confirmation panel
show a number as "•••• ••• 1234" for every role. The Administrator's list shows names and delivery
results and no number at all. Audit entries mask any mobile number in their text.

**Stock accountability (Task 5d).** Dispensing writes no stock entry; an entry per issue would link a
medicine to a visit time. Accountability comes from the stock levels and the dispensed totals in
Reports & Analytics. The Doctor and Health Center Staff hold the full dispensing records.

**History.** Diagnoses written, and seals set, under the Administrator account before 2026-09-25
are unchanged and keep their attribution.

**Sealed records are encrypted (added 2026-10-01, Task 5).** The law: RA 11166 Section 44 makes it
unlawful to disclose a person's HIV status without written consent, and RA 10173 treats health
data as sensitive personal information. So:

- On a Restricted consultation, every free-text field of the visit is stored encrypted
  (AES-256-GCM): the diagnosis, treatment plan, chief complaint and additional notes, and the check-in
  reason of its queue visit (Task 5b). The reason is that RA 11166 Section 44 also forbids disclosing
  that a person has had an HIV-related test, and a chief complaint such as "for HIV testing" does
  that. Only the Doctor's screens decrypt them. The backup file carries them encrypted. Vitals,
  immunization records, dates and the fact of the seal are not free text and stay readable.
- On a Restricted visit, Health Center Staff cannot read or change the chief complaint and notes:
  the Edit Consultation form shows the placeholder, and a save leaves them as stored.
- The names of medicines dispensed at a Restricted visit show as the placeholder to the
  Administrator on the profile, the Edit Consultation form, the dashboard and in flash messages and
  audit entries. Quantities show as a bare number.
- Exports and print views never show sealed text, for any role. On Screen 05 the Doctor sees it on
  screen; Print Record prints "Restricted — Doctor access only" in its place. Printing the Edit
  Consultation page (Screen 20) from the browser prints "Sealed — not printed" in place of each
  sealed field; the screen itself does not change (Task 5b).
- Screens 10 and 18 rank chief complaints like diagnoses: a Restricted visit is one "Confidential" row.
- If the key on the computer cannot open a sealed record, the Doctor sees "This sealed record
  cannot be opened on this computer." Nothing crashes, and the audit trail records it.
- Screen 13, Backup (Task 5c): "The backup file is encrypted. It can only be opened with this
  system's key, using restore_backup.py on the health-center computer." The download is one
  AES-256-GCM `.idsbackup` file; the key is derived from SEALED_DATA_KEY.

Known limits. These stay readable to Health Center Staff for a Restricted visit: the visit date,
vital signs, immunizations, and the fact that the record is Restricted. The medicine names stay
plain in the database, because stock counts read them; Screens 10 and 18 count them under
"Confidential" (Task 5c), and the backup file is encrypted as a whole. Backups made before
2026-10-01 still hold plain text.

---

# Global Navigation Rules

Login

↓

Role Verification

↓

Dashboard

↓

Module

↓

Back to Dashboard

Logout available on every page. It is a button in the account menu that opens "Confirm Logout"; its Logout button sends a small form (with its token), not a link. The maintenance page's "Sign out" works the same way.

---

# Common Components

Every screen must reuse

Sidebar

Header

Cards

Buttons

Tables

Typography

Colors

Spacing

Icons

Status Badges

---

# Data Standards

Always use

Realistic Filipino names

Realistic medicine names

Realistic addresses

Realistic consultation records

Realistic healthcare statistics

Never use

Lorem Ipsum

John Doe

Sample Data

Placeholder Text

---

# Backend Integration Notes

Every screen must be designed for future integration with

Flask

Bootstrap

SQLite

Avoid designs that require unsupported frontend frameworks.

---

# Final Principle

Every screen must look like it belongs to one complete enterprise healthcare management system.

Consistency is more important than visual variety.

---

# Reconciliation With The Built System

Added in Version 2.0. **Re-checked against the code on 21 August 2026, and substantially rewritten
on that date** — most of what this section previously reported as unbuilt has since been built, and
a reconciliation section that under-reports the system is as misleading as one that over-reports
it. Screens 01 to 20 above are left exactly as approved; this section records only where the built
system differs from them.

The system has **21 screens**. `templates/` holds 29 `.html` files, of which six are not screens (`error.html`, the plain 404 and 500 page, is the sixth), and two screens have a second file (`patient_profile_demographics.html` and `inventory_item.html`):
`base.html` (the shared layout), the `_print.html` and `_chart_table.html` partials,
`maintenance.html` — a response page rendered with a 503 in place of the screen that was asked for,
with no route and nothing navigating to it — and `session_expired.html`, shown when a form token is refused. See the note under "Purpose" at the top of this
document for why My Account counts as a screen and `maintenance.html` does not.

## Specified but not built

**Screen 01 — "Locked session after multiple failed attempts."**

Still not implemented. There is no failed-attempt counter, so no account can be locked out by
repeated guessing. What *is* implemented, and should not be confused with it, is deactivation, and
it now holds at **both** ends of a session:

- at the login form, `routes/auth.py` refuses a deactivated account and writes an audit entry
  recording whether the password supplied still worked — the most actionable line the trail can
  produce;
- and on every guarded request, `utils/security.py` re-reads the account and clears the session the
  moment `is_active` reads false, so an account deactivated *while its holder is signed in* loses
  access at their next click rather than at their next sign-in. That entry is its own phrase,
  "Ended session on deactivated account", because nobody presented a credential — see §16 of the
  UI Architecture document.

"Remember Me" is also not built. "Show Password" **is** now built (`login.html`, a working
`aria-pressed` toggle).

**Screen 09 — "Save Draft", "Schedule".**

Not built. The compose dialog offers Cancel and Send Broadcast only, so neither appears as a dead
control.

**Screen 11 — account writes are BUILT.**

This entry previously read "Not implemented, and deliberately so… The buttons are present and
disabled, each stating why", and none of that has been true since 3 September 2026. **Add User,
Edit User, Reset Password and Deactivate/Reactivate all work**, each writing a real hashed password
or a real column change and each recording itself in the audit trail. The last-Administrator guard
refuses both deactivating and demoting the last account that can still sign in, and states the
reason beside the control rather than refusing silently.

**Delete is the one write that was never built**, and on present reasoning never will be: nothing
in this project deletes an account, because the audit trail attributes past entries to it.
Deactivation is the supported end of an account's life — it refuses the account at the login form
and ends any session it already has open, and it is reversible.

The `write`, `edit_user` and `reset_password` reasons that used to sit behind those buttons in
`utils/unavailable.py` and `routes/user_views.py::UNTRACKED` are retired. A reason that denies a
working control is the worst kind this project keeps.

**Column sorting — built on Screens 03 and 06; deliberately absent on Screen 08.**

Patient Records sorts by Name, Age, Last Visit and Status; Medicine Inventory sorts by Item
name, Usable stock, Nearest expiry and Status. Both run over the rows already rendered, the way
their search boxes and Advanced Filter panels do, so sorting composes with a narrowed list instead
of resetting it. One comparator serves both (`static/js/table-sort.js`); each screen supplies only
its own column list. The order in force is named on the Sort button, on the chosen option, and in
the line beside the table, all three written from one state.

the Patient Queue has no Sort button. The queue is already in the order that answers who may be
brought in next — in consultation, then waiting, then not yet arrived, then resolved — and
re-sorting it would discard the one thing that list is for. The button was removed in the final
fixes rather than left disabled.

**Paging.**

Not implemented and not needed: every row the query returns is already on the page. The page
numbers that used to sit in these footers were markup counting a roster the system does not hold.

**Screen 13 — Settings is now mostly live, and this entry has been rewritten twice over.**

It previously read "Nothing typed on that screen is stored. The `settings` table… is empty, and no
route writes to it". That has not been true since 3 September 2026.

- **General Settings is stored and read back.** The health center's name, barangay, municipality,
  province and the clinic's opening and closing times are written to the `settings` table and
  consumed by the SMS composer, all three export modules and every template header. The opening
  and closing times are shown on the screens and letterheads; there is no booking dialog.
- **Maintenance Mode is live.** An Administrator can close the system to Health Center Staff and
  Barangay Officials, who are shown a 503 maintenance page and keep their sessions. Administrator
  access is structurally unaffected, so there is no self-lockout.
- **Password Policy, the sign-in figures and the database size** are read from the running system
  and are not editable anywhere.
- **Download Backup is real** and serves a verified copy of the database, encrypted as one
  `.idsbackup` file since Task 5c; `restore_backup.py` opens it at the health-center PC.

Nothing on Settings is disabled any more (Task 7). **Restore** is not a button: a restore replaces
every record with no way to undo it, and doing it safely means stopping the application first, which a
screen inside that application cannot do. It is `restore_backup.py` on the health-center PC, and the
screen says so in one line. The **SMS gateway** form is gone: the line "SMS mode: Live" or "SMS mode:
Simulated" says whether `SEMAPHORE_API_KEY` is set in `.env`. The scheduled-backup, Health Center
Information, User Preferences, Notification Settings and Clear Cache controls were removed outright.

**Screen 19 — Notifications.** Removed in Task 7: it was rendered with no data. Recorded activity lives on
Screen 12, and community messages on Screen 09.

## Built since this specification was written

**Screen 03 — export of a ticked selection, from the bulk bar.**

This section previously listed this as not built, on the grounds that every download in this
project is a bookmarkable GET and a file whose contents are decided by a list of primary keys in
a query string is not that. Every clause of that was true; the premise underneath it was the
part worth re-reading. A bookmarkable URL is the right property for an export that answers "the
whole register" and the wrong one for an export that answers "these eleven records somebody
ticked", because the second has nothing stable to bookmark.

So the bulk bar now carries Export Excel and Export PDF, and they are the only two exports in the
project that are not GETs. They are submit buttons on the form the row checkboxes already belong
to, with a `formaction` sending it to an export route instead of the archive one — the same
`patient_ids` Change Status beside them has always posted, read by one rule in
`routes/patient_views.py`. The file itself is assembled by `routes/roster_export.py` through the
same cover / rows / Not Tracked machinery the full roster uses, and its cover states "a selection,
not the register" in the row where the roster's states the opposite, alongside how many records
were ticked, how many were found and how many are on the register. The `export_selection` reason
in `utils/unavailable.py` is retired.

**Export is real, on seven screens, in two formats each.**

This section previously stated that "Export and print are not implemented anywhere in this
project" and that the controls were decorative. That is no longer true of any of them. Patient
Records, Medicine Inventory, Patient Queue, User Management, Audit Logs, Reports &
Analytics and Community Reports each serve a real `.xlsx` and a real `.pdf` at their own route.
Each file carries a cover sheet naming its scope, and each states that it holds the full list
rather than the list as filtered on screen, because these screens filter in the browser and the
server never sees those filters. See `routes/roster_export.py`, `routes/report_export.py` and
`routes/audit_export.py`.

**Print is real** on the screens that include `templates/_print.html`, Reports & Analytics among
them. Printing a single patient from a Patient Records row opens that patient's profile with
`?print=1`, because the record *is* a page.

**Screen 10 — report type and date range are wired.** `reports_analytics_context()` takes the
request's query string and passes the range through to the same model functions the default view
uses, so a generated report and the default view are one code path with different dates.

**Screen 11 — Last Login is real**, and so is the permission list. The roster is the live `users`
table, each role's screen list is derived from the actual `role_required()` guards on the live
`url_map`, and Last Login is read from the audit trail. The seven invented staff rows are gone.

**Screen 12 — the trail is read, not just written.** Audit Logs reads real entries, filters them
by module, and exports them.

**Screen 06 — View and Archive are real; Print was removed (View now opens the item page, Task 12).**

- **View** (Task 12) opens the item page: details, batches, Receive stock and Remove from stock. The
  read-only panel in the row that it replaces held fields that now live on the batches.
- **Archive** opens a confirmation dialog offering only the transitions the item's stored status
  permits, and the server re-derives that list from the database before writing. It works in both
  directions, so retiring the wrong item is a correctable mis-click. It writes the same status
  column the Add/Edit form writes, so the stat cards, the low-stock alert, both dashboards, the
  sidebar badge and Reports & Analytics all respect a retirement the moment it commits.
- **"Print Inventory" per row was removed rather than built**, and this is a deliberate decision
  rather than an outstanding gap. A printed copy of one table row is not a document anybody keeps —
  unlike a patient's record, which is a page in its own right. (The item page added in Task 12 is where
  batches are received and removed, not a document to print.) The inventory document a reader actually wants is Export PDF in the toolbar, which is
  built. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §12.

**Screen 08 — advance booking retired, and the screen renamed Patient Queue.** This entry used to
record the consolidation of five New Appointment buttons down to one. That one has since gone with
the feature: on 2026-09-05 advance booking was removed outright, because a barangay health center
of this size sees patients in the order they arrive rather than at an hour agreed weeks before.
What is left is a walk-in queue and a calendar that reports what each day held. The screen says so
itself, quoting `utils/unavailable.py` `advance_booking`. See §13 of the architecture document.

**Screens 02 and 14 — a Continue Consultation shortcut.** Both dashboards name whoever is
currently In Consultation and link straight to that appointment's write-up form, or state that
nobody is. It cannot start a consultation and cannot bypass the one-at-a-time rule. See §13.

**Immunisation tracking against the DOH EPI schedule.** Recorded on Screen 20, reported on Screens
17 and 10, shown on the Patient Profile's Vaccination Records tab and on the dashboards. See
`09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §9.

**The consultation View action, and the add-only immunisation rule** on Screen 20's edit mode.
See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §10.

**Sign-in recording.** `routes/auth.py` records successful sign-ins, refused attempts and attempts
blocked on a deactivated account; `utils/security.py` records a session ended because its account
was deactivated mid-visit. Signing out is **not** recorded — `logout()` clears the session and
writes nothing — so these are sign-in counts rather than session counts. This is what put a real
figure behind Screen 11's Last Login, Screen 12's Login Events card and Screen 13's Security pane.

**Screens 15 to 18 are data-driven.** The Barangay Official Dashboard, Health Programs,
Vaccination Campaigns and Community Reports each take a context built in
`routes/official_views.py`, and each derives its figures from `reports_analytics_context()` rather
than counting anything itself — so no two of them can report the same barangay differently. Where
the schema cannot establish something these screens were drawn to show (six of the eight
programmes, and the campaign concept itself), the screen reports that absence rather than
inventing a number.

## Retired

Community Announcements. It was never a feature — a static template with no model and no create,
edit or delete route. Screen 09, SMS Notifications, is the single real community-notification
mechanism and covers the same Proposal requirement with a stored record of what was sent. See
`09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §1.1.

## Naming

Screen 09 is specified above as "Community Notifications". It is built and referred to throughout
the code and UI as "SMS Notifications" (`sms_notifications.html`, `sms_broadcasts`). They are the
same screen.

## Screen numbering drift inside code comments

The numbering in this document is authoritative. A few code comments use different numbers and should be read with that in mind. They are comments only — no behaviour depends on them, and they were left untouched by this documentation pass:

- `routes/patient_views.py`, `models/appointments.py`, `models/consultations.py` call Patient Profile "Screen 04". This document numbers it 05; 04 is Register Patient.
- `models/consultations.py` line 300 calls the consultation form "Screen 21" and line 331 calls it "Screen 09". This document numbers it 20; 09 is SMS Notifications.
- `routes/official.py` and `routes/official_views.py` call Health Programs "Screen 16" and Vaccination Campaigns "Screen 17". This document agrees.