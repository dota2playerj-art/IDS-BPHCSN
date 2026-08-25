# IDS-BPHCSN SCREEN SPECIFICATIONS

Version: 2.0

Status: Screens 01–15 approved. Screens 16–20 specified from the built system and reconciled against the code on 2026-08-15.

---

# Purpose

This document defines every screen of the IDS-BPHCSN system.

The system has 20 screens.

Screens 01 to 15 are the original approved specifications and are unchanged below. Screens 16 to 20 were built after this document was first written and are specified here for the first time.

`templates/` holds 21 `.html` files. `base.html` is the shared layout — sidebar, header, content region — and is not a screen. The other 20 files are the 20 screens, one file each.

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

Validation

Required fields.

Invalid credentials.

Locked session after multiple failed attempts.

Navigation

Successful Login

↓

Dashboard

---

# SCREEN 02

## Administrator Dashboard

Purpose

Provide a complete overview of the health center.

Components

Sidebar

Header

Dashboard Cards

Recent Consultations

Today's Appointments

Medicine Inventory Summary

Quick Actions

Notifications

Activity Timeline

System Status

Reports Preview

Actions

Open any module.

View notifications.

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

Display complete patient information.

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

Expiration Widget

Buttons

Add Medicine

Update Stock

Print Inventory

Columns

Medicine Name

Category

Quantity

Expiration Date

Supplier

Status

---

# SCREEN 07

## Add/Edit Medicine

Purpose

Manage medicine details.

Fields

Medicine Name

Generic Name

Category

Quantity

Unit

Expiration Date

Supplier

Storage Location

Buttons

Save

Update

Cancel

Validation

No negative quantity.

Expiration date required.

---

# SCREEN 08

## Appointment Scheduling

Purpose

Manage appointments.

Components

Calendar

Upcoming Appointments

Walk-in Queue

Today's Schedule

Buttons

Schedule

Reschedule

Cancel

Complete

Fields

Patient

Date

Time

Purpose

Assigned Staff

Status

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

Roles

Administrator

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

---

# SCREEN 13

## Settings

Purpose

Configure the system.

Sections

General Settings

Health Center Information

SMS Settings

Backup

Restore

Security

Account

Buttons

Save

Reset

Backup Database

Restore Database

---

# SCREEN 14

## Health Center Staff Dashboard

Purpose

Dashboard for healthcare workers.

Widgets

Today's Patients

Appointments

Medicine Requests

Recent Consultations

Notifications

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

Health Announcements

Community Reports

Vaccination Campaigns

Upcoming Programs

Statistics

Quick Actions

View Reports

View Notifications

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

## Notifications

Purpose

Present a notification centre to the Barangay Official.

Authorized Users

- Barangay Official

Components

Notification List

Category Filters

Read/Unread States

Implementation Status

Presentation only. `routes/official.py::notifications()` renders the template with no context.

There is no notifications table and nothing writes one, which is why the sidebar item for this screen carries no unread badge.

The real, recorded community-notification mechanism is Screen 09 (SMS Notifications).

---

# SCREEN 20

## Record / Edit Consultation

Purpose

Write up the clinical record of a completed visit, and edit a record already written.

Authorized Users

- Administrator
- Health Center Staff

Entry Points

Record — Appointment Scheduling, on a queue entry moved to In Consultation.

Edit — Patient Profile, Consultation History tab, Edit action.

Sections

Patient Banner

Vital Signs

Clinical Record

Immunizations Given Today

Follow-Up

Fields

Chief complaint

Diagnosis

Treatment plan / medicines given

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

The form is add-only for immunisations. A previously recorded dose cannot be removed here. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §10 for the reasoning.

Backend Notes

One template, `record_consultation.html`, rendered by two blueprints with one shared context builder in `routes/consultation_views.py`, so the Administrator and Health Center Staff variants cannot drift apart. Each route keeps its own role guard and its own redirect target.

Recording is anchored to a queue entry and completes it on save.

Editing writes an audit entry naming what changed, and touches neither the patient, the visit date, nor who originally recorded it.

Immunisation tracking on this screen extends beyond the original scope of this document. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §9.

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

Logout available on every page.

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

The system has **20 screens**. `templates/` holds 23 `.html` files, of which three are not screens:
`base.html` (the shared layout) and the `_print.html` and `_chart_table.html` partials.

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

**Screen 11 — "Add User", "Reset Password", "Disable", "Enable", "Delete".**

Not implemented, and deliberately so rather than overlooked. Every write on that screen touches
authentication — password hashing, role assignment, and the ability to revoke a sign-in — so it is
an open scope decision for the team. The buttons are present and disabled, each stating why.

**Column sorting — built on Screens 03 and 06; deliberately absent on Screen 08.**

Patient Records sorts by Name, Age, Last Visit and Status; Medicine Inventory sorts by Medicine
Name, Current Stock, Expiration Date and Status. Both run over the rows already rendered, the way
their search boxes and Advanced Filter panels do, so sorting composes with a narrowed list instead
of resetting it. One comparator serves both (`static/js/table-sort.js`); each screen supplies only
its own column list. The order in force is named on the Sort button, on the chosen option, and in
the line beside the table, all three written from one state.

Appointment Scheduling's Sort stays disabled, and its reason changed from "not implemented" to
what actually stops it: the queue is already in the order that answers who may be brought in next
— in consultation, then waiting, then not yet arrived, then resolved — and re-sorting it would
discard the one thing that list is for. See the `sort` reason in `utils/unavailable.py`.

**Paging.**

Not implemented and not needed: every row the query returns is already on the page. The page
numbers that used to sit in these footers were markup counting a roster the system does not hold.

**Screen 13 — Settings: everything except the Security pane.**

Nothing typed on that screen is stored. The `settings` table exists in `schema.sql` and is empty,
and no route writes to it, so every input sits inside a disabled fieldset. Backup and Restore do
nothing; the project's real backup practice is a manual dated copy of `app.db` taken outside the
application. The SMS gateway controls are disabled for a different reason — the integration in
`utils/sms.py` is real and finished, and what is absent is a configured `SEMAPHORE_API_KEY`.

**Screen 19 — Notifications.**

The one screen in the system rendered with no context at all
(`render_template('notifications.html')`), because there is no `notifications` table. Nothing on
it should be quoted as a system output. Recorded activity lives on Screen 12.

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
Records, Medicine Inventory, Appointment Scheduling, User Management, Audit Logs, Reports &
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

**Screen 06 — View and Archive are real; Print was removed.**

- **View** opens a read-only panel in the row, showing the eight stored fields that previously had
  no reader outside the editable form.
- **Archive** opens a confirmation dialog offering only the transitions the item's stored status
  permits, and the server re-derives that list from the database before writing. It works in both
  directions, so retiring the wrong item is a correctable mis-click. It writes the same status
  column the Add/Edit form writes, so the stat cards, the low-stock alert, both dashboards, the
  sidebar badge and Reports & Analytics all respect a retirement the moment it commits.
- **"Print Inventory" per row was removed rather than built**, and this is a deliberate decision
  rather than an outstanding gap. A stock item has no page of its own and a printed copy of one
  table row is not a document anybody keeps — unlike a patient's record, which is a page in its own
  right. The inventory document a reader actually wants is Export PDF in the toolbar, which is
  built. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §12.

**Screen 08 — one New Appointment button, not five.** The screen carried five controls opening the
same booking dialog; four were removed and the empty-state prose that named them was rewritten to
report state instead of issuing instructions. The survivor sits in the queue toolbar beside Check
In Patient. The dialog itself is titled "Schedule Appointment". See §13 of the architecture
document.

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