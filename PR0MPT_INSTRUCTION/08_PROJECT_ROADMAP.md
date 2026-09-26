# IDS-BPHCSN PROJECT ROADMAP

Version: 1.1

Status: Active Development

Last reviewed: 5 September 2026 — the Current Project Status section was re-measured against the
running system and the live database in a full verification pass (all four core objectives driven
end to end, a 377-probe route × role matrix, and the complete account-management lifecycle). The
21 August 2026 reconciliation of the Known Gaps section still stands. Every status below was
checked against code that runs, not against intent.

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

Phase 6: Integration — complete. Phase 7 (Testing) is the outstanding phase, and what is missing
there is a *committed* suite rather than verification itself; see Phase 7 below for the
distinction. Phases 1 through 6 are complete.

Progress

Feature-complete for the approved scope; documentation and test-suite work outstanding.

Completion

Approximately 95%.

**This section was rewritten on 5 September 2026 and every figure in it was re-measured against
the running system on that date.** The previous version reported 70–75%, six decorative screens,
no README and no version control. All of those were false by the time anyone would have read
them — and, worse, this document's own "Known Gaps" section had already listed most of them as
corrected claims since 21 August. A roadmap that contradicts itself is read top to bottom, so the
stale half was the half being believed. What that drift said, and what was actually true, is
recorded at the end of this section rather than quietly deleted.

What the figure means, stated plainly so it can be defended:

All four core objectives from the approved Proposal are built and working against real stored
data — Patient Records, Medicine Inventory, Patient Queue with Community Notifications,
and Reports & Analytics. Each was exercised end to end on 4 September 2026 by driving the real
forms over HTTP against the live database: a patient registered, edited and reopened; a dispense
moved stock across its threshold and the low-stock alert reacted on every surface that reports it;
a patient booked, checked in, consulted and written up with dispensing and immunisation in one
save; a broadcast sent to a computed audience with per-recipient rows.

Role-based access control is enforced across all **89 guarded endpoints** for all three roles with
no gaps, confirmed by a 377-probe route × role matrix run under four identities — Administrator,
Health Center Staff, Barangay Official and anonymous — with **zero leaks**. The database holds
**13 tables with 19 indexes** and passes integrity and foreign-key checks.

The remaining ~5% is concentrated in three places, none of which is a core objective:

- **One screen is presentation-only:** Notifications (Screen 19), which renders with no context
  because there is no `notifications` table and nothing writes one. Every other screen in the
  system is driven by real queries. User Management, Audit Logs, the Barangay Official screens and
  both partially-wired dashboards named in the previous version of this section are all live.
- **Phase 7 Testing has no committed artifacts.** Verification is real and substantial but is
  written fresh each session and discarded, so nobody else can re-run it. Converting it to a
  committed suite is a conversion, not a start from nothing.
- **A short list of features named in the specifications is deliberately unbuilt**, each declared
  on the screen that would have carried it rather than rendered as a dead control: account lockout,
  Remember Me, Restore, SMS draft and scheduling, and a configured SMS gateway key. These are open
  scope decisions, not oversights. See "Features named in the specifications that are not built"
  below.

Supporting infrastructure is complete and was driven end to end in the same pass. Account
management works in full — Add User, Edit User, Reset Password and Deactivate/Reactivate — with the
last-Administrator guard holding on both deactivation and demotion, and counting only accounts that
can still sign in. Self-service password change is built, and a refused attempt is recorded in its
own audit phrase. On Settings, **General Settings and Maintenance Mode are genuinely live**: the
health center's name, barangay, municipality, province and clinic hours are written to the
`settings` table and read back by the SMS composer, the export modules, the booking slot generator
and every template header, and closing the system to non-Administrators works with no possibility
of self-lockout. **Download Backup is built** and serves a real database file that opens and passes
its own integrity check; **Restore is the one half that remains unbuilt**, and says so on itself,
because restoring safely means stopping the application first — which is not something a screen
inside that application can do.

README.md exists and states how to run the system, the three roles and the migration order. The
project is under version control on `master`.

Scope added since the approved Proposal

DOH Expanded Program on Immunization (EPI) tracking was added during development and is fully
working: an `immunizations` table, the EPI schedule held in code, per-dose status on the Patient
Profile, due/overdue alerts on both dashboards, and coverage figures on Reports & Analytics.
Doses are recorded from the Record Consultation screen. It is documented: 03_SCREEN_SPECIFICATIONS.md
now specifies Screens 01–20, and §9 of 09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md records the
scope extension and its reasoning.

What this section used to claim, and why it was wrong

Kept for the same reason the equivalent table in Known Gaps is kept: a status section loses a
reader's trust by being written once and never re-read while the system moves past it, and the way
to earn it back is to show the drift rather than erase it.

| Previous claim | Actual state on 5 September 2026 |
|---|---|
| "Approximately 70–75%." | ~95%. All four core objectives and all supporting infrastructure are built and were exercised end to end. |
| "enforced across all 80 guarded routes" | 89 guarded endpoints, verified by a 377-probe route × role matrix with zero leaks. |
| "The database holds 10 tables with 12 indexes" | 13 tables, 19 indexes. Integrity and foreign-key checks both clean. |
| "Six screens are still presentation-only… User Management, Audit Logs, Settings, and four of the five Barangay Official extension screens." | One: Notifications. User Management and Audit Logs are fully live; Settings is live apart from the panes that declare themselves unbuilt; all Barangay Official screens take a real context from `routes/official_views.py`. |
| "Two dashboards (Administrator, Health Center Staff) are partially wired… several statistic cards and activity tables are still mockup." | Both are data-driven, including the Continue Consultation shortcut and the immunisation due/overdue panels. |
| "Phase 8 Documentation has not started; there is no README.md and the project is not yet under version control." | README.md exists. The project has been under Git since before this claim was written. |
| "03_SCREEN_SPECIFICATIONS.md… still describes the original 15 screens" | It specifies Screens 01–20 and carries a reconciliation section against the built system. |

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

✓ Patient Queue

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

☑ Build Header — shared `base.html` layout across all 22 screens

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
  03_SCREEN_SPECIFICATIONS.md Screen 01 lists it; "Remember Me" is also still outstanding on that
  screen. "Show Password" IS built — `login.html` carries a working `aria-pressed` eye toggle.

☑ Role Management — `login_required` and `role_required` decorators on all 89 guarded endpoints, verified
  with no gaps for Admin, Health Staff, Barangay Official and anonymous visitors. The Health
  Staff read-only restriction on SMS is enforced structurally: no send endpoint exists in the
  staff blueprint at all.

☑ Patient CRUD — create, edit, duplicate detection, three-way Active/Inactive/Deceased status

☑ Inventory CRUD — 19 fields, stock levels, expiry status, low-stock alerting

☑ Walk-in queue — check-in, a same-day consultation queue, and start/complete transitions
  guarded by a single-consultation invariant

  This line read "Appointment CRUD — advance booking with slot-conflict detection … plus
  cancel, reschedule and no-show closure" until **2026-09-05**. All of that was built and all
  of it worked; it was removed anyway, on the adviser's point that a government barangay health
  center does not let a patient pick their own hour weeks ahead. Screen 08 is now the Patient
  Queue. See `utils/unavailable.py` `advance_booking`, which Screen 08 quotes on itself.

☑ Service schedule — which services run on which days (every weekday, specific weekdays, or
  the Nth weekday of the month), with a note per service. All four roles read it; only the
  Administrator changes it, and every change is audited. Today's services head the Patient
  Queue. Built on **2026-09-26** as the successor to advance booking, and **shipped empty**:
  the health center's days are not yet confirmed, so none were entered. Filling it in is a
  data task for the Administrator once they are. Informational only — it restricts no check-in
  or consultation and is not connected to SMS. See 09_UI_Architecture §19.

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

☑ Create SQLite Database — `schema.sql` plus 8 migration scripts. 10 tables, 12 named indexes.

☑ Create Users Table — 3 seeded accounts, one per role, with a CHECK constraint on role

☑ Create Patients Table — extended by migration with civil status, blood type, address detail,
  emergency contact, medical conditions, allergies and record status

☑ Create Medicines Table — `inventory_items`, extended by migration with generic and brand name,
  drug class, dosage, manufacturer, batch, unit cost, storage location and status

☑ Create Appointments Table — extended by migration with the queue statuses
  (Waiting, In Consultation), the walk-in flag and the check-in timestamp

☑ Create Audit Logs — `audit_logs`, written on consultation edits, SMS broadcast sends, and
  authentication events. Six distinct actions are recorded, in four groups: consultation edits;
  SMS broadcasts; sign-ins (successful, refused, and blocked on a deactivated account); and
  sessions ended because the account was deactivated mid-visit. Signing out is deliberately not
  recorded, so these are sign-in counts rather than session counts.

☑ Additional tables not in the original list — `consultations`, `immunizations`,
  `sms_broadcasts`, `sms_broadcast_recipients`, `settings`. A sixth, `schedule_logs`, was created
  and has since been dropped by `migrate_drop_schedule_logs.py`: it was declared to back
  Community Announcements, that screen was retired as a feature that never existed, and nothing
  else ever read the table. This is why the counts above read 10 tables and 12 indexes rather
  than the 11 and 13 recorded earlier in this document's history.

☑ Testing — `PRAGMA integrity_check` returns ok and `PRAGMA foreign_key_check` reports zero
  violations. A database built fresh from `schema.sql` was diffed against a fully-migrated one:
  all 10 tables, all columns, all 12 indexes and all foreign keys match, with a single
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

Completed

Tasks

☑ Connect UI — every screen but Notifications is wired to live data; the screens with write
  paths all have working ones. Notifications is the single exception and has no table to read

☑ Connect Backend — shared context builders in `routes/*_views.py` are used by both the Admin
  and Staff variants of each screen, so the two role surfaces cannot drift apart

☑ Connect Database — all live screens read and write through the models layer; no template
  touches SQL

☑ Session Management — login, logout, session clearing, and a no-store cache header on every
  authenticated response

☑ User Roles — verified across all 89 guarded endpoints under all four identities with zero gaps.
  The application exposes 96 URL rules beyond static files, resolving to 92 endpoints; 89 of
  those endpoints are guarded (86 under `role_required`, plus `/dashboard`, `/account` and
  `/account/password` under `login_required`) and three are deliberately open (`/`, `/login`,
  `/logout`). The sweep of 4 September 2026 probed every guarded route under each of the four
  identities -- 377 checks -- and found no leak. Write routes were probed only from identities
  that must be refused, so a passing guard was never given the chance to alter data.

☑ Wire the Audit Logs screen — done. Screen 12 reads the trail through `get_audit_logs()`,
  filters it by user, date and module, and exports it to `.xlsx` and `.pdf`

☑ Replace the remaining hard-coded dashboard panels with the live figures the context builders
  already compute — done. Both the Administrator and Health Center Staff dashboards are
  data-driven, including the immunisation due/overdue panels and the Continue Consultation
  shortcut

Deliverable

Integrated System

---

Phase 7

Testing

Status

Not Started as a formal phase — ad-hoc verification has been performed and recorded

Testing Types

☐ Functional Testing — **no automated test suite exists.** There is no `tests/` directory, no
  `test_*.py` file, and no pytest or unittest dependency anywhere in the project. This is stated
  plainly here because it is the kind of gap a reviewer should be told about rather than left to
  discover.

  What *has* been done is substantial and should not be mistaken for nothing. Verification is
  performed by driving the real application through Flask's test client — genuine GET and POST
  requests to the same endpoints a browser uses, against a copy of the live database — and the
  results are written up in the audit reports. The most recent pre-review sweep exercised all
  four core objectives end to end (register/view/edit a patient, add a medicine and move its
  stock through every alert tier, book and check in an appointment, send a broadcast), ran the
  full 320-check route × role matrix, drove the mid-session deactivation case through its whole
  eight-step lifecycle, and confirmed all 26 export routes return valid `.xlsx` and `.pdf` files.

  The distinction that matters: these checks are **scripted but not committed**. They are written
  fresh each session, run once, and discarded, so they prove the system worked at that moment but
  cannot be re-run on demand by someone else or in CI. Converting them into a committed suite is
  the outstanding work, and it is a conversion rather than a start from nothing.

☐ UI Testing — not performed on real devices or across browsers

☑ Database Testing — integrity and foreign-key checks pass; the fresh-install vs migrated
  comparison described in Phase 5 was carried out and recorded; all 8 migrations were re-run
  against a copy of the live database and 7 of 8 are cleanly idempotent (the eighth,
  `migrate_drop_schedule_logs.py`, is a `DROP TABLE IF EXISTS` and is a no-op on re-run)

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

Completed — 22 screens (Service Schedule, the 22nd, added 2026-09-26)

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

Completed — 10 tables, 12 indexes, 8 migrations, integrity and foreign-key checks passing

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

Settings (Screen 13) is a partial case and is stated separately rather than counted above, and
the balance has shifted decisively since this was written. **General Settings is stored and read
back**: the health center's name, barangay, municipality, province and the clinic's opening and
closing times are written to the `settings` table by `admin.save_general_settings` and consumed by
the SMS composer, all three export modules, the booking slot generator and every template header —
saving a new opening time changes the slots the booking dialog offers on the next render.
**Maintenance Mode is live**, written by `admin.set_maintenance_mode` and read on every guarded
request. The Password Policy pane, the sign-in figures and the database size are read from the
running system and are not editable anywhere. **Download Backup is real** and serves a verified
copy of the database. What remains disabled is Restore, the SMS gateway controls and the scheduling
controls, each inside its own fieldset stating its own reason — so the claim that "nothing typed on
that screen is stored" is no longer true of it, and has not been since 3 September 2026.

Every other screen is driven by real queries. The Barangay Official's screens — Health Programs,
Vaccination Campaigns, Community Reports and the Official Dashboard — each take a context built in
`routes/official_views.py`, and each of them derives its figures from
`reports_analytics_context()` rather than counting anything itself, so they cannot disagree with
Reports & Analytics about the same barangay.

## Features named in the specifications that are not built

- Screen 01: **"Remember Me"** and **account lockout after repeated failed sign-ins**. Neither is
  built, and neither is rendered as a dead control. Note that account *deactivation* is enforced
  and audited in two places — `routes/auth.py::_log_blocked_sign_in()` refuses a deactivated
  account at the login form and records whether the password supplied still worked, and
  `utils/security.py` re-reads the account on every guarded request, so an account deactivated
  *while its holder is signed in* loses that session on its next click rather than at logout.
  Both are a different mechanism from a failed-attempt counter. ("Show Password" is now built:
  `login.html` carries a working `aria-pressed` eye toggle.)
- Screen 09: **"Save Draft"** and **"Schedule"** for SMS broadcasts. Not built; the compose dialog
  offers Cancel and Send Broadcast only, so neither appears as a dead button.
- Screen 11: **account writes are BUILT** and this entry no longer belongs in a list of things
  that are not. Add User, Edit User, Reset Password and Deactivate/Reactivate all work, each with
  a real hashed password and a real audit entry, and the last-Administrator guard refuses both
  deactivating and demoting the last account that can still sign in. Delete is the one write that
  was never built and never will be on present reasoning: nothing in this project deletes an
  account, because the audit trail attributes past entries to it. Deactivation is the supported
  end of an account's life.
- **Column sorting on the Patient Queue's table**, and only there. Sorting itself is built:
  Patient Records sorts by Name, Age, Last Visit and Status, and Medicine Inventory by Medicine
  Name, Current Stock, Expiration Date and Status, over the rendered rows and composing with each
  screen's search box and Advanced Filter (`static/js/table-sort.js`, one comparator shared by
  both). The queue is the one table that refuses, and it refuses by argument rather than for want
  of the control: its order is already a clinical answer — in consultation, then waiting, then
  not yet arrived, then resolved — and re-sorting it would discard the one thing that list is for.
  This is the `sort` reason in `utils/unavailable.py`, now quoted by that one screen.
- **Paging**. Every row the query returns is already on the page, so there is no second page; the
  `pagination` reason says so on the two screens that used to show page numbers.
- **Restore** on Settings, and the **SMS gateway** controls on the same screen. Backup is no
  longer in this list: Download Backup serves a real database file that opens and passes its own
  integrity check. Restore is deliberately the harder half — a backup is a copy and risks nothing,
  while a restore replaces every record with no way to undo it, and doing that safely means
  stopping the application first, which a screen inside that application cannot do. The SMS
  integration itself is real — `utils/sms.py` posts to Semaphore and every send checks
  `SEMAPHORE_API_KEY` — so what is missing there is a configured key, not the feature.

## Engineering practice

- **Templates carry inline `<style>` and `<script>` blocks.** 19 of the 25 files in `templates/`
  do. `04_DEVELOPMENT_GUIDE.md` asks for separate CSS and JS files; `static/css/` and `static/js/`
  are still almost entirely vendor assets (Bootstrap, Chart.js, and the self-hosted Inter and
  Material Symbols fonts). The one exception is `static/js/table-sort.js`, the shared sort
  comparator written for Patient Records and Medicine Inventory — the project's first piece of
  first-party JavaScript in a file of its own, and the shape the rest of this debt would be paid
  off in. This is a consistent, long-standing deviation from that standard and is the largest
  outstanding one.
- **No `tests/` directory.** Verification in this project is done by writing a throwaway script
  per task that exercises the routes end-to-end against an independent `sqlite3` connection and
  then deleting it. That has caught real defects, but it leaves nothing runnable behind, so a
  reviewer cannot re-run the suite that verified a change.
- **No `static/images/` and no `instance/` directory.**
- **`app.db` is git-ignored and is the only copy of the demonstration data.** Losing it loses every
  patient, appointment and stock row the demo runs on. The mitigation is a manual dated copy taken
  outside the application.

## Documentation debt — closed 21 August 2026, re-counted 5 and 26 September 2026

This subsection previously recorded that `03_SCREEN_SPECIFICATIONS.md` described 15 screens while
the system had 21, and that `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §1 also listed 15. Both
were brought current on 21 August 2026, re-counted on 5 September 2026 after My Account and the
maintenance response page were added, and re-counted again on 26 September 2026 when the Service
Schedule was built:

- The system has **22 screens**. `templates/` holds 26 `.html` files; four are not screens —
  `base.html` (the shared layout), the `_print.html` and `_chart_table.html` partials, and
  `maintenance.html`, which is a **response page rather than a screen**: it has no route and
  nothing navigates to it, because `utils/security.py` renders it with a 503 in place of the
  screen that was asked for.
- **My Account is counted as a screen** — it has its own route, guard, context and a form that
  writes, and is entered from the header profile chip. It is Screen 21.
- **The Service Schedule is Screen 22**, read by all four roles and changed only by the
  Administrator. See `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §19.
- `03_SCREEN_SPECIFICATIONS.md` documents Screens 01–22 and carries a
  "Reconciliation With The Built System" section, updated in the same pass as this one.
- `09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md` §1 lists the same 22.

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
| "Screen 10: Print, Export to Excel and Export to PDF… not built." | All three are built. Seven screens have real `.xlsx` and `.pdf` download routes — Patient Records, Medicine Inventory, Patient Queue, User Management, Audit Logs, Reports & Analytics and Community Reports; see `routes/roster_export.py`, `report_export.py` and `audit_export.py`. |
| "Export and print… the controls exist in the markup and are decorative." | No export control in this project is decorative. |
| "Search, sort, filter and export controls on most list screens are present but not wired." | All four are wired. Search, filter and export are built on every list screen; **sort** is built on Patient Records and Medicine Inventory, and is deliberately refused on Patient Queue's queue, whose order is itself the answer. None of the four is still true as written. |
| "Exporting only a ticked selection on Patient Records' bulk bar (`export_selection`)… is not [built]." | Built. The bulk bar carries Export Excel and Export PDF, which submit the ticked `patient_ids` by POST to `export-selection.xlsx` / `.pdf` per role and are assembled by `routes/roster_export.py` through the same machinery the full roster uses. They are the only exports in the project that are not GETs, because a selection has no stable URL to bookmark; the cover sheet says "a selection, not the register" where the roster's says the opposite. The `export_selection` reason is retired. |
| "Sign-ins are not recorded." | `routes/auth.py` records successful sign-ins, refused attempts and attempts blocked on a deactivated account; `utils/security.py` records a session ended because its account was deactivated mid-visit. **Sign-outs are not recorded** — `logout()` clears the session and writes nothing — so these are sign-in counts rather than session counts. Screen 11 shows a real Last Login and Screen 12's Login Events card is live. |

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