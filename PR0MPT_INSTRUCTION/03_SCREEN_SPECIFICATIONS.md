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

Presentation only. `routes/official.py::community_reports()` renders the template with no context, and every figure on the screen is written into the markup.

This screen has not been reconciled against real data the way Screens 16 and 17 were. Until it is, nothing on it should be quoted as a system output.

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

Added in Version 2.0. Checked against the code on 2026-08-15.

Screens 01 to 15 above are left exactly as approved. This section records where the built system differs from them, so a reader can tell a design intention from a delivered feature without opening the code. Nothing here revises the specification; each item is either a deliberate decision or an unbuilt item.

## Specified but not built

Screen 01 — "Locked session after multiple failed attempts."

Not implemented. `routes/auth.py` checks the password and starts the session; there is no failed-attempt counter and no lockout, so no account can be locked out. Sign-ins are not recorded either, which is why Screen 11 has no last-login time and Screen 12's Login Events card reports the same absence.

Screen 03 — "Export", "Print". Screen 06 — "Print Inventory". Screen 10 — "Export PDF", "Export Excel", "Print Report".

Export and print are not implemented anywhere in this project. No screen writes a CSV, an Excel file or a PDF, and no print handler is bound. The controls exist in the markup and are decorative. Screen 10 states this beside its toolbar, and its "Recent Generated Reports" table reports that no export history is recorded. Screen 06 carries an Export button and a per-row print icon, both unwired.

Screen 10 — report type and date-range selectors.

Decorative. The figures shown always cover the whole registered roster; filtering is not wired.

Screen 11 — "Last Login" column, "Add User", "Reset Password", "Disable", "Enable", "Delete".

Not implemented, and deliberately so rather than overlooked. Every write on that screen touches authentication — password hashing, role assignment, and the ability to revoke a sign-in — so it is an open scope decision for the team. The buttons are present and disabled, each stating why. The three accounts are managed in `models/users.py`. Last Login has no column behind it, per the Screen 01 note above.

Screen 13 — Settings, all sections including Backup and Restore.

Presentation only. `routes/admin.py::settings()` renders the template with no context, and nothing on the screen reads or writes configuration. Backup and Restore do nothing. The project's real backup practice is a manual dated archive kept outside the repository.

Screens 18 and 19 — Community Reports, Notifications.

Presentation only, as recorded in their entries above.

## Built beyond this specification

Immunisation tracking against the DOH EPI schedule. Recorded on Screen 20, reported on Screens 17 and 10, shown on the Patient Profile's Vaccination Records tab and on the dashboards. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §9 for the scope note.

The consultation View action, and the add-only immunisation rule on Screen 20's edit mode. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §10.

## Retired

Community Announcements. It was never a feature — a static template with no model and no create, edit or delete route. Screen 09, SMS Notifications, is the single real community-notification mechanism and covers the same Proposal requirement with a stored record of what was sent. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §1.1.

## Naming

Screen 09 is specified above as "Community Notifications". It is built and referred to throughout the code and UI as "SMS Notifications" (`sms_notifications.html`, `sms_broadcasts`). They are the same screen.

## Screen numbering drift inside code comments

The numbering in this document is authoritative. A few code comments use different numbers and should be read with that in mind. They are comments only — no behaviour depends on them, and they were left untouched by this documentation pass:

- `routes/patient_views.py`, `models/appointments.py`, `models/consultations.py` call Patient Profile "Screen 04". This document numbers it 05; 04 is Register Patient.
- `models/consultations.py` line 300 calls the consultation form "Screen 21" and line 331 calls it "Screen 09". This document numbers it 20; 09 is SMS Notifications.
- `routes/official.py` and `routes/official_views.py` call Health Programs "Screen 16" and Vaccination Campaigns "Screen 17". This document agrees.