# IDS-BPHCSN PROJECT ROADMAP

Version: 1.1

Status: Active Development

Last reviewed: 13 August 2026 — reconciled against the running system and the live database
(see AUDIT_REPORT_2026-08-12_v3.md). Every status below was checked against code that runs,
not against intent.

---

# Purpose

This roadmap defines the complete development lifecycle of the Integrated Digital System for Barangay Poblacion Health Center Services and Community Notifications (IDS-BPHCSN).

It serves as the official project progress tracker from UI design until final capstone defense.

Every completed milestone should be updated by the project team.

---

# Official Methodology (per approved Capstone Proposal)

The approved Proposal defines the project methodology as the Agile Software Development Life
Cycle, in five official phases. The 10-phase breakdown below is an internal tracking tool that
maps onto these 5 phases — it is not a separate or competing methodology:

| Agile Phase (official) | Roadmap Phase(s) below |
|---|---|
| 1. Planning and Requirements | Phase 1: Research |
| 2. System Design | Phase 2: UI/UX Design |
| 3. Development and Coding | Phase 3: Frontend Development, Phase 4: Backend Development, Phase 5: Database Development |
| 4. Testing and Review | Phase 6: Integration, Phase 7: Testing |
| 5. Deployment and Feedback | Phase 8: Documentation, Phase 9: Presentation, Phase 10: Capstone Defense |

---

# Current Project Status

Current Phase

Phase 6: Integration — with Phase 7 (Testing) beginning. Phases 1 through 5 are complete.

Progress

In Progress

Completion

Approximately 70–75%.

What that figure means, stated plainly so it can be defended:

All four core objectives from the approved Proposal are built and working against real stored
data — Patient Records, Medicine Inventory, Appointment Scheduling with Community Notifications,
and Reports & Analytics. Role-based access control is enforced across all 56 routes for all three
roles with no gaps. The database holds 11 tables with 13 indexes and passes integrity and
foreign-key checks.

The remaining 25–30% is concentrated in four places, none of which is a core objective:

- Six screens are still presentation-only, rendering hard-coded content rather than live data:
  User Management, Audit Logs, Settings, and four of the five Barangay Official extension screens.
  Three of these are supporting infrastructure that 01_PROJECT_BIBLE.md ranks below the core
  objectives; the Barangay Official extension screens were never part of the approved Proposal.
- Two dashboards (Administrator, Health Center Staff) are partially wired — the inventory and
  immunization panels are live, several statistic cards and activity tables are still mockup.
- Phase 7 Testing has produced no artifacts yet.
- Phase 8 Documentation has not started; there is no README.md and the project is not yet under
  version control.

Scope added since the approved Proposal

DOH Expanded Program on Immunization (EPI) tracking was added during development and is fully
working: an `immunizations` table, the EPI schedule held in code, per-dose status on the Patient
Profile, due/overdue alerts on both dashboards, and coverage figures on Reports & Analytics.
Doses are recorded from the Record Consultation screen. This is not described in
03_SCREEN_SPECIFICATIONS.md yet — that document still describes the original 15 screens and is
the next documentation task.

---

# Project Timeline

Phase 1

Research

Status

Completed

Deliverables

✓ Approved Capstone Proposal

✓ Research Documentation

✓ Project Title

✓ Scope

✓ Objectives

---

Phase 2

UI/UX Design

Status

Completed

Deliverables — Original 15 screens

✓ Login Page

✓ Administrator Dashboard

✓ Patient Records

✓ Register Patient

✓ Patient Profile

✓ Medicine Inventory

✓ Add/Edit Medicine

✓ Appointment Scheduling

✓ Community Notifications (Admin/Staff-facing)

✓ Reports & Analytics

✓ User Management

✓ Audit Logs

✓ Settings

✓ Health Center Staff Dashboard

✓ Barangay Official Dashboard

Deliverables — Barangay Official extension (+5, beyond original 15, not in approved Proposal
but needed per the BO's sidebar in 09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md)

✓ Community Announcements (BO-scoped)

✓ Health Programs

✓ Vaccination Campaigns

✓ Community Reports (BO-scoped)

✓ Notifications (BO inbox)

Deliverables — added during development (not in the approved Proposal, not yet in
03_SCREEN_SPECIFICATIONS.md)

✓ Record Consultation — the clinical write-up screen, reached from the appointment queue.
  Records complaint, diagnosis, treatment, five vital signs, two paediatric growth measurements
  and the DOH EPI immunization doses given at the visit.

Goal

All 21 UI screens exist as HTML/Jinja templates and every one is reachable by the roles entitled
to it. NOTE: file existence does not mean the screen is fully wired to live data. As of the
13 August 2026 review: 10 screens are fully wired end to end, 2 are partially wired, and 9 still
render hard-coded content. See the latest AUDIT_REPORT for the per-screen breakdown. Phase 2 is
closed as a *design* phase; converting the remaining decorative screens to live data is tracked
under Phase 4 and Phase 6, not here.

---

Phase 3

Frontend Development

Status

Completed

Tasks

☑ Create Flask Project — `app.py` with an application factory, four blueprints
  (auth, admin, staff, official), and a flat endpoint namespace in `utils/endpoints.py`

☑ Configure Bootstrap — Bootstrap 5 CSS and JS, the Inter font family, the Material Symbols
  icon font and Chart.js 4.4.4 are all vendored locally under `static/`. The system loads
  nothing from the internet, so it runs on a LAN with no connectivity.

☑ Build Sidebar — role-scoped, built from `utils/context.py`, with a live low-stock badge

☑ Build Header — shared `base.html` layout across all 21 screens

☑ Build Dashboard — three role dashboards built; Administrator and Staff are partially wired
  (see Phase 4), Barangay Official is still presentation-only

☑ Build Forms — Register Patient, Add/Edit Medicine, Record Consultation, appointment booking
  and check-in, SMS compose; all with server-side validation and per-field error redisplay

☑ Build Tables — patient, inventory, appointment, consultation, broadcast and immunization tables

☐ Responsive Testing — not yet performed on real devices; layouts use Bootstrap's grid but this
  has not been verified against the tablet and phone widths the barangay staff would use

Deliverable

Working HTML pages. — Delivered.

---

Phase 4

Backend Development

Status

Completed — with one task carried forward (Audit Logs screen)

Tasks

☑ Authentication — hashed passwords via Werkzeug, session cleared on login, role-based dispatch
  to the correct dashboard. Account lockout after repeated failures is NOT implemented, although
  03_SCREEN_SPECIFICATIONS.md Screen 01 lists it; "Remember Me" and "Show Password" are also
  still outstanding on that screen.

☑ Role Management — `login_required` and `role_required` decorators on all 56 routes, verified
  with no gaps for Admin, Health Staff, Barangay Official and anonymous visitors. The Health
  Staff read-only restriction on SMS is enforced structurally: no send endpoint exists in the
  staff blueprint at all.

☑ Patient CRUD — create, edit, duplicate detection, three-way Active/Inactive/Deceased status

☑ Inventory CRUD — 19 fields, stock levels, expiry status, low-stock alerting

☑ Appointment CRUD — advance booking with slot-conflict detection, walk-in check-in,
  a same-day consultation queue, start/complete transitions guarded by a single-consultation
  invariant, plus cancel, reschedule and no-show closure

☑ Consultations and Immunization — clinical record with validated vitals, paediatric growth
  measurements, and DOH EPI dose recording. Editing a saved consultation writes a field-by-field
  before/after entry to the audit log.

☑ Reports — every figure, table and chart series on Reports & Analytics is computed server-side
  from live tables. Panels with no data source in the schema say so explicitly rather than
  inventing a number. Print / Export to Excel / Export to PDF are NOT wired.

☑ Notifications — SMS broadcasts persisted with audience resolution, duplicate-number merging,
  GSM-7/UCS-2 segment costing, per-recipient delivery rows, and a simulated/live gateway mode
  that becomes live as soon as SEMAPHORE_API_KEY is set

◐ Audit Logs — the WRITER is complete and in use: consultation edits and SMS sends both write
  real entries with full before/after detail. The reading query `get_audit_logs()` is written and
  correct but is not yet called by any route, so the Audit Logs SCREEN still shows hard-coded
  rows. This is the single cheapest remaining fix in the project and is carried into Phase 6.

Deliverable

Working Flask application. — Delivered.

---

Phase 5

Database Development

Status

Completed

Tasks

☑ Create SQLite Database — `schema.sql` plus 7 migration scripts. 11 tables, 13 named indexes.

☑ Create Users Table — 3 seeded accounts, one per role, with a CHECK constraint on role

☑ Create Patients Table — extended by migration with civil status, blood type, address detail,
  emergency contact, medical conditions, allergies and record status

☑ Create Medicines Table — `inventory_items`, extended by migration with generic and brand name,
  drug class, dosage, manufacturer, batch, unit cost, storage location and status

☑ Create Appointments Table — extended by migration with the queue statuses
  (Waiting, In Consultation), the walk-in flag and the check-in timestamp

☑ Create Audit Logs — `audit_logs`, written on consultation edits and SMS broadcast sends

☑ Additional tables not in the original list — `consultations`, `immunizations`,
  `sms_broadcasts`, `sms_broadcast_recipients`, `settings`, `schedule_logs`

☑ Testing — `PRAGMA integrity_check` returns ok and `PRAGMA foreign_key_check` reports zero
  violations. A database built fresh from `schema.sql` was diffed against a fully-migrated one:
  all 11 tables, all columns, all 13 indexes and all foreign keys match, with a single
  deliberate, documented difference (`consultations.updated_at` is nullable on the migrated path,
  because SQLite will not accept a non-constant default in ADD COLUMN).

Note on "Create Reports Table": no such table was created, deliberately. Reports are computed
from the live patient, consultation, appointment, inventory and immunization tables at render
time, so a report can never disagree with the records it summarises. This is a design decision,
not an omission.

Deliverable

Fully functioning database. — Delivered.

---

Phase 6

Integration

Status

In Progress — substantially complete

Tasks

☑ Connect UI — 10 of 21 screens are wired end to end to live data with working write paths;
  2 more are partially wired

☑ Connect Backend — shared context builders in `routes/*_views.py` are used by both the Admin
  and Staff variants of each screen, so the two role surfaces cannot drift apart

☑ Connect Database — all live screens read and write through the models layer; no template
  touches SQL

☑ Session Management — login, logout, session clearing, and a no-store cache header on every
  authenticated response

☑ User Roles — verified across all 56 routes under all four identities with zero gaps

☐ Wire the Audit Logs screen — the query and the data already exist; only the route context and
  the template loop remain (carried forward from Phase 4)

☐ Replace the remaining hard-coded dashboard panels with the live figures the context builders
  already compute

Deliverable

Integrated System

---

Phase 7

Testing

Status

Not Started as a formal phase — ad-hoc verification has been performed and recorded

Testing Types

☐ Functional Testing — no test suite exists. There is no `tests/` directory and no `test_*.py`
  file anywhere in the project. Individual flows have been exercised by hand and the results
  written up in the audit reports, but nothing is repeatable or automated.

☐ UI Testing — not performed on real devices or across browsers

☑ Database Testing — integrity and foreign-key checks pass; the fresh-install vs migrated
  comparison described in Phase 5 was carried out and recorded; all 7 migrations were re-run
  against a copy of the live database and 6 of 7 are cleanly idempotent

☐ User Acceptance Testing — not performed with barangay health center staff

☐ Bug Fixing — ongoing. Defects found by audit are logged in AUDIT_REPORT files and fixed in
  numbered sessions rather than tracked in a separate bug list.

Deliverable

Stable System

---

Phase 8

Documentation

Status

Not Started

Tasks

☐ User Manual

☐ Technical Documentation

☐ System Documentation

☐ Screenshots

☐ Appendix

Deliverable

Complete Documentation

---

Phase 9

Presentation

Status

Not Started

Tasks

☐ PowerPoint

☐ Demonstration Script

☐ Presenter Assignment

☐ Practice

Deliverable

Final Presentation

---

Phase 10

Capstone Defense

Status

Pending

Requirements

☐ Working System

☐ Documentation

☐ Presentation

☐ Demonstration

☐ Source Code

☐ Database

Deliverable

Successful Defense

---

# Milestones

Milestone 1

Approved Proposal

Status

Completed

---

Milestone 2

Complete UI Design

Status

Completed — 21 screens

---

Milestone 3

Frontend Completed

Status

Completed — all screens built and reachable; responsive testing outstanding

---

Milestone 4

Backend Completed

Status

Completed — all four core objectives working; the Audit Logs screen still needs its route
context, and the Reports export buttons are not wired

---

Milestone 5

Database Completed

Status

Completed — 11 tables, 13 indexes, 7 migrations, integrity and foreign-key checks passing

---

Milestone 6

System Integration

Status

In Progress — role enforcement, session management and the live screens are connected; the
remaining decorative screens are the outstanding work

---

Milestone 7

Testing Completed

Status

Pending

---

Milestone 8

Documentation Completed

Status

Pending

---

Milestone 9

Presentation Ready

Status

Pending

---

Milestone 10

Capstone Defense

Status

Pending

---

# Team Responsibilities

Member 1

Project Leader

Responsibilities

Project Management

Documentation

Presentation

AI Coordination

---

Member 2

Frontend Developer

Responsibilities

Bootstrap

HTML

CSS

JavaScript

---

Member 3

Backend Developer

Responsibilities

Flask

Authentication

CRUD Operations

Routing

---

Member 4

Database & Testing

Responsibilities

SQLite

Testing

Bug Reports

Documentation Support

---

# Weekly Progress Review

Every week review

Completed Tasks

Pending Tasks

Issues

Risks

Next Week Plan

AI Outputs

Approved Changes

---

# Risk Management

Potential Risks

AI Hallucinations

Incomplete UI

Database Errors

Time Constraints

Integration Problems

Version Conflicts

Mitigation

Review every AI output.

Maintain documentation.

Test continuously.

Backup project files.

Keep previous versions.

**Status of the last two mitigations, checked 21 August 2026.** "Keep previous versions" is
implemented: the project is under git with 27 commits, so every previous version is recoverable
and "Version Conflicts" is mitigated rather than merely listed. "Backup project files" remains a
manual practice — a dated copy of `app.db` taken outside the application — because `app.db` is
git-ignored and is still the only copy of the demonstration data. See Known Gaps below.

---

# File Management

Never overwrite important files.

Recommended versions

v1

v2

v3

Release Candidate

Final

Archive old versions.

---

# Known Gaps — as of 21 August 2026

Recorded here so that anyone reading this roadmap before a demo knows what is not finished. A gap
that is stated is defensible; a gap that is discovered is not.

**This section was rewritten on 21 August 2026 and every claim in it was re-checked against the
code on that date.** The previous version described the system as it stood on 13 August and had
gone badly out of date — it reported nine screens as decorative, denied that the project was under
version control, and denied that a README existed. All three were false by the time anyone would
have read them. What follows is what is actually true now; the corrected claims are listed at the
end of this section so the drift itself is on the record.

## Screens not backed by data

**One.** Notifications (Screen 19) is rendered by `routes/official.py::notifications()` as
`render_template('notifications.html')` with no context at all, and there is no `notifications`
table for it to read. It is the only screen in the system in that position.

Settings (Screen 13) is a partial case and is stated separately rather than counted above.
`settings()` now passes `settings_context()`, and the Security Settings pane reports live sign-in
and refused-sign-in counts read from the audit trail. Every other pane on the screen is a disabled
fieldset: the `settings` table exists in `schema.sql` and is empty, and no route writes to it. So
nothing typed on that screen is stored, and exactly one block on it is read.

Every other screen is driven by real queries. The Barangay Official's screens — Health Programs,
Vaccination Campaigns, Community Reports and the Official Dashboard — each take a context built in
`routes/official_views.py`, and each of them derives its figures from
`reports_analytics_context()` rather than counting anything itself, so they cannot disagree with
Reports & Analytics about the same barangay.

## Features named in the specifications that are not built

- Screen 01: **"Remember Me"** and **account lockout after repeated failed sign-ins**. Neither is
  built, and neither is rendered as a dead control. Note that account *deactivation* is enforced
  and audited — `routes/auth.py::_log_blocked_sign_in()` refuses a deactivated account and records
  whether the password supplied still worked — but that is a different mechanism from a
  failed-attempt counter. ("Show Password" is now built: `login.html` carries a working
  `aria-pressed` eye toggle.)
- Screen 09: **"Save Draft"** and **"Schedule"** for SMS broadcasts. Not built; the compose dialog
  offers Cancel and Send Broadcast only, so neither appears as a dead button.
- Screen 11: **account writes** — Add User, Reset Password, Disable, Enable, Delete. Present and
  disabled, each stating why, because every one of them touches authentication. This is an open
  scope decision for the team rather than an oversight.
- **Column sorting** on the list screens. The rows arrive in the order the query returns them and
  each screen states that order in its footer. This is the `sort` reason in `utils/unavailable.py`,
  quoted by Patient Records, Medicine Inventory and Appointment Scheduling.
- **Paging**. Every row the query returns is already on the page, so there is no second page; the
  `pagination` reason says so on the two screens that used to show page numbers.
- **Exporting only a ticked selection** on Patient Records' bulk bar (`export_selection`). Export
  of the full register is built; exporting a selection is not.
- **Backup and Restore** on Settings, and the **SMS gateway** controls on the same screen. The SMS
  integration itself is real — `utils/sms.py` posts to Semaphore and every send checks
  `SEMAPHORE_API_KEY` — so what is missing there is a configured key, not the feature.

## Engineering practice

- **Templates carry inline `<style>` and `<script>` blocks.** 17 of the 23 files in `templates/`
  do. `04_DEVELOPMENT_GUIDE.md` asks for separate CSS and JS files; `static/css/` and `static/js/`
  hold only vendor assets (Bootstrap, Chart.js, and the self-hosted Inter and Material Symbols
  fonts). This is a consistent, long-standing deviation from that standard and is the largest
  outstanding one.
- **No `tests/` directory.** Verification in this project is done by writing a throwaway script
  per task that exercises the routes end-to-end against an independent `sqlite3` connection and
  then deleting it. That has caught real defects, but it leaves nothing runnable behind, so a
  reviewer cannot re-run the suite that verified a change.
- **No `static/images/` and no `instance/` directory.**
- **`app.db` is git-ignored and is the only copy of the demonstration data.** Losing it loses every
  patient, appointment and stock row the demo runs on. The mitigation is a manual dated copy taken
  outside the application.

## Documentation debt — closed 21 August 2026

This subsection previously recorded that `03_SCREEN_SPECIFICATIONS.md` described 15 screens while
the system had 21, and that `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §1 also listed 15. Both
are now current and both were re-checked on 21 August 2026:

- The system has **20 screens**. `templates/` holds 23 `.html` files; three are not screens
  (`base.html`, the shared layout, plus the `_print.html` and `_chart_table.html` partials).
- `03_SCREEN_SPECIFICATIONS.md` documents Screens 01–20 and carries a
  "Reconciliation With The Built System" section, updated in the same pass as this one.
- `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §1 lists the same 20.

## What this section used to claim, and why it was wrong

Left here deliberately. The point of a Known Gaps section is that a reader can trust it, and the
way it loses that trust is by being written once and never re-read while the system moves past it.

| Previous claim | Actual state on 21 August 2026 |
|---|---|
| "The project is NOT under version control… there is no history and no rollback." | 27 commits on `master`, from the initial commit to `a46ee83`. |
| "No README.md, although 04_DEVELOPMENT_GUIDE.md lists one." | `README.md` exists, and states how to run the system, the three roles, and the migration order. |
| Nine screens listed as hard-coded or presentation-only. | One (Notifications). Settings is partly live. The other seven named are all data-driven. |
| "User Management — the `users` table holds 3 accounts; the screen shows 7 fixed rows." | The screen lists the real roster and derives each role's permissions from the live `url_map`. Only the account *writes* are still disabled. |
| "Audit Logs — real entries are being written, but the screen does not read them yet." | Screen 12 reads the trail through `get_audit_logs()`, filters it by module, and exports it. |
| "Settings — nothing reads or writes it." | Nothing *writes* it. The Security pane *reads* live sign-in counts from the audit trail. |
| "Screen 10: Print, Export to Excel and Export to PDF… not built." | All three are built. Seven screens have real `.xlsx` and `.pdf` download routes — Patient Records, Medicine Inventory, Appointment Scheduling, User Management, Audit Logs, Reports & Analytics and Community Reports; see `routes/roster_export.py`, `report_export.py` and `audit_export.py`. |
| "Export and print… the controls exist in the markup and are decorative." | No export control in this project is decorative. |
| "Search, sort, filter and export controls on most list screens are present but not wired." | Search and filter are wired on every list screen; export is built. **Sort genuinely is not**, and is the only one of the four still true. |
| "Sign-ins are not recorded." | `routes/auth.py` records sign-ins, sign-outs, refusals and blocked attempts. Screen 11 shows a real Last Login and Screen 12's Login Events card is live. |

---

# Success Indicators

The project is successful when

✓ All UI screens completed

✓ Frontend completed

✓ Backend completed

✓ Database connected

✓ Reports generated

✓ Authentication working

✓ User roles enforced

✓ Documentation complete

✓ Presentation completed

✓ System defended successfully

---

# Long-Term Vision

Future versions may include

Cloud Database

SMS Gateway Integration

Email Notifications

Patient Portal

Online Appointments

Analytics Dashboard

Mobile Application

These enhancements are outside the current capstone scope.

---

# Final Principle

Build the project one phase at a time.

Do not skip documentation.

Do not rush implementation.

Complete each milestone before moving to the next.

Consistency, quality, and maintainability are more important than speed.