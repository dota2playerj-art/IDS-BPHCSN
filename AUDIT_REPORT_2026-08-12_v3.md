# IDS-BPHCSN — FULL PROJECT AUDIT (v3)

**Date:** 12 August 2026
**Scope:** Read-only diagnostic. No project file was created, modified, or deleted by this audit
other than this report itself.
**Predecessors:** `AUDIT_REPORT_2026-08-06_v2.md` (project root). The v1 report is **not present in
the project** — only v2 survives, so v2 is the only baseline this report can be compared against.
**Authority followed:** `PR0MPT_INSTRUCTION/01`–`10` + `Capstone_Proposal.pdf.pdf`, per the source-of-
truth order in `01_PROJECT_BIBLE.md §Source of Truth Priority`.

## Method

Everything below was verified against the running code and the live database rather than inferred
from previous reports:

| Check | How it was verified |
|---|---|
| Route × role matrix | All 56 registered URL rules driven through Flask's test client under four session identities. GETs only for authorised roles; POST endpoints probed **only** with identities that must be refused, so no write ever executed. |
| Schema consistency | A fresh database was built from `schema.sql` inside the scratchpad and diffed column-by-column, constraint-by-constraint, FK-by-FK and index-by-index against the live `app.db`. |
| Migration health | All seven migrations re-run against a **copy** of `app.db` in the scratchpad, with `config.DATABASE` repointed at the copy first. `C:\classcheck\app.db` was never opened for writing. |
| Inert UI elements | Every `<button>` and `<a>` in all 22 template files parsed and classified against its attributes (`type=submit`, `form=`, `href`, `onclick`, `data-bs-toggle`, `data-bs-dismiss`), then each candidate confirmed by reading the template's own `<script>` block. |
| Live figures | The actual context builders (`reports_analytics_context`, `sms_notifications_context`, `appointment_scheduling_context`, the alert queries) executed inside a real app context. |

---

## Headline

The four core Proposal objectives are **built and genuinely working**. Ten screens are wired end-to-
end to real data with real write paths; the RBAC boundary is clean with zero gaps across 56 routes;
the schema has exactly one divergence between a fresh install and a migrated database, and it is
the one the code already documents as deliberate.

The remaining risk is **not** in the objectives. It is concentrated in five places:

1. **Chart.js is loaded from a public CDN on six screens.** On a LAN-only defense machine with no
   internet, every chart on Reports & Analytics — the entire Objective 4 deliverable — renders blank.
2. **The Appointment Scheduling screen is empty today.** Nothing is queued for 2026-08-12 and the
   only future booking is Cancelled, so Objective 3's flagship screen currently demos as a blank page.
3. **Nine screens print a frozen "Tuesday, July 7, 2026."** Today is 36 days later.
4. **The database contains visible junk test data** — patients named `qwe qwe` and `asd asdas`, one
   consultation recording a 3-month-old at 175 cm and 70 kg — in direct breach of
   `03_SCREEN_SPECIFICATIONS.md §Data Standards`.
5. **Zero immunization doses have ever been recorded**, so the tracking feature can only demonstrate
   its alert half, not its recording half.

Six screens remain wholly decorative. Four of those are the Barangay Official extension screens that
were never in the approved Proposal; two — Audit Logs and Settings — are supporting infrastructure
the Bible explicitly ranks below the core objectives.

---

# SECTION 1 — SCREEN-BY-SCREEN COMPLETION STATUS

There are **21 screens**, not 20. `templates/` holds 22 `.html` files: `base.html` (the shared
layout) plus 21 screens. The extra one is `record_consultation.html`, built during the
consultation work and **not listed in `03_SCREEN_SPECIFICATIONS.md`, `08_PROJECT_ROADMAP.md`, or
`09_UI_Architecture §1`**. See Section 5.

Legend: **LIVE** = renders stored data and has working write paths · **PARTIAL** = some panels live,
some hard-coded · **DECORATIVE** = renders no route context at all.

## Fully wired (10)

### 01 · Login — `login.html` — LIVE (with spec gaps)
Authenticates against `users.password_hash` via `check_password_hash`, dispatches by normalised role
to the three dashboards, clears the session on each login. Invalid credentials flash and redirect.

Gaps against `03_SCREEN_SPECIFICATIONS.md` Screen 01:
- **"Show Password" is inert.** `login.html:362` is `<button type="button" class="eye-toggle">` and
  the file contains **no `<script>` element at all** — the eye icon cannot toggle anything.
- **"Remember Me" is absent entirely.** No checkbox exists anywhere in the file.
- **"Locked session after multiple failed attempts" is not implemented.** No attempt counter, no
  lockout, in `routes/auth.py` or the schema.
- `login.html:371` "Forgot Password?" is `href="#"` — mitigated by the adjacent text telling the
  user to contact the administrator, so this one reads as intentional.

### 03 · Patient Records — `patient_records.html` — LIVE
Table, all four stat cards, pagination visibility and the empty state all come from
`patient_records_context()`. Row links reach the profile and the edit form. The bulk/single status
change is a real form posting to `archive_patients` / `staff_archive_patients` with a three-way
Active/Inactive/Deceased modal. The Prenatal card honestly reads "Not yet tracked".
Toolbar is decorative — see Section 2.

### 04 · Register Patient — `register_patient.html` — LIVE
Full create *and* edit against `patients`, server-side validation with per-field redisplay,
duplicate detection with a `confirm_duplicate` acknowledgement, JSON-encoded conditions/allergies,
live age preview mirroring `format_age()`. Carries two genuine handoffs: `?check_in=1` saves and
drops the new patient straight into today's queue; `?book=…` saves and books the appointment the
New Appointment dialog was opened for. Two footer buttons are inert — Section 2.

### 05 · Patient Profile — `patient_profile.html` — LIVE
All six tabs render from `patient_profile_context()`:
- Personal / Medical — live from the patient row.
- **Consultation History** — live, each row expandable to full vitals, each with an Edit link into
  the audited edit path.
- **Medicine History** — deliberately empty with an honest "not recorded yet" note. There is no
  dispensing table; this is a stated absence, not a broken panel.
- **Immunization Record** — fully live against `models/immunizations.py`: the DOH EPI schedule
  table, per-dose status badges, an overdue/due banner, an "other recorded doses" section, and a
  count badge riding on the tab itself. Shown for the under-5 cohort and any older patient with
  doses on file.
- **Appointment History** — live, with working Reschedule and Cancel links that round-trip back to
  the profile via `?back=profile:<id>`.

Three inert controls — Section 2. Two summary cards ("Assigned Health Worker", "Active
Prescriptions") say "Not yet tracked" honestly.

### 06 · Medicine Inventory — `medicine_inventory.html` — LIVE
Item table and all stat cards from `medicine_inventory_context()`; stock-level bars, expiry status
and low-stock ordering computed in `models/inventory.py`. Add and Edit links work. Toolbar
decorative — Section 2.

### 07 · Add/Edit Medicine — `add_edit_medicine.html` — LIVE
All 19 fields round-trip. Every `<select>` is rendered from the same tuples the validator checks.
Auto-generated item code in add mode, existing code in edit mode. The save confirmation names the
fields that actually changed, and says so plainly when nothing did.

### 08 · Appointment Scheduling — `appointment_scheduling.html` — LIVE (largest screen, 1,734 lines)
The most complete screen in the system:
- Month calendar navigating via `?month=`, each day cell clickable to filter the list below.
- Today's consultation queue ordered by arrival, with a single-consultation-at-a-time invariant
  enforced in the model (Start Consultation is disabled and explains itself while the room is busy).
- Check In (existing patient search, or new-patient handoff to registration).
- New Appointment with date/time/type/staff, slot-conflict detection with an explicit
  acknowledgement step, and a new-patient path validated *before* the patient record is created.
- Start / Complete consultation, Cancel (No-show vs Cancelled), Reschedule — all real POSTs.
- Two client-side live searches (`queueSearch`, `upcomingSearch`) genuinely wired at lines 1390 and
  1514.

Four toolbar controls and two print icons are inert — Section 2.

### 21 · Record Consultation — `record_consultation.html` — LIVE *(undocumented screen)*
Writes the full consultation record: four clinical text fields, five vitals, two paediatric growth
measures, follow-up date. Range-checked per field, blood pressure validated as two halves. Serves
both record and edit modes; the edit path writes a field-by-field before/after entry to
`audit_logs`, and refuses to move the patient or the visit date. **Immunization doses are recorded
from here** via checkboxes shown only for the paediatric cohort, and edits add/remove doses
correctly.

### 09 · SMS Notifications — `sms_notifications.html` — LIVE
Gateway status banner (live vs simulated, read fresh per render), four stat cards counted from
stored rows, broadcast history table, a detail panel naming actual recipients, working client-side
search and three filters (lines 583–616). Compose modal posts a real broadcast: audience resolution
with per-option counts and disabled empty audiences, GSM-7/UCS-2 segment counter sharing its
character sets with the server-side validator, duplicate-number merging, per-recipient rows written
to `sms_broadcast_recipients`, and an `audit_logs` entry per send. **Health Staff sees it read-only,
enforced by the absence of a send endpoint in that blueprint — not by hidden markup.**
There is no `Save Draft` or `Schedule` button (Screen 09 spec lists both) — Section 5.

### 10 · Reports & Analytics — `reports_analytics.html` — LIVE
Every KPI, table and chart series is server-rendered. All eight Chart.js datasets are emitted
through `| tojson` from `reports_analytics_context()` — there is not one literal data array left in
the file. Four panels whose data has no source in the schema (SMS delivery, medicine dispensing,
prenatal enrolment, programme enrolment, generated-report history) render an explicit "not yet
tracked" note naming the reason, rather than a plausible invention. The two toolbar selects are
`disabled` with an honest tooltip. **Caveat: the charts depend on a CDN — see Section 2.1.**

## Partially wired (2)

### 02 · Administrator Dashboard — `admin_dashboard.html` — PARTIAL
**Live:** the "Low Stock Medicines" stat card (`:143`), the Medicine Inventory panel with its
per-item stock bars and expiry dates (`:290–305`), and the Immunization Follow-up panel
(`:316–332`).

**Static mockup:** five of six stat cards — Total Registered Patients `2,418`, Today's Appointments
`34`, Active Inventory Items `203`, Pending SMS Alerts `12`, Monthly Consultations `318` (`:119–167`).
The "Recent Patient Consultations" table is five hard-coded rows for patients who do not exist
(`Maria Luisa Santos / P-2026-0312`, …) with a hard-coded "10 records today" (`:177–252`). All three
Monthly Analytics charts are hard-coded arrays (`:431–460`). The SMS Broadcast composer is a dead
form with a `disabled` send button and a recipient list reading "All Registered Patients (2,418)"
(`:342–367`). The System Activity feed is five hard-coded events (`:374–413`).

The real total is **25 patients**, and the real SMS composer lives two clicks away on Screen 09 and
works. This screen is the first thing an Admin sees at the defense.

### 14 · Health Center Staff Dashboard — `staff_dashboard.html` — PARTIAL
**Live:** the "Low Stock Medicines" card (`:143`), the "Children Due for Immunization" card
(`:162–167`), the Medicine Stock Alerts panel (`:340`), the Immunization Follow-up panel
(`:373–386`) with links into each child's profile, and all five Quick Action links (`:177–181`).

**Static mockup:** three of five stat cards — Today's Appointments `14`, Patients Served Today `9`,
New Patient Registrations `3` (`:118–139`). Today's Schedule, Recent Consultations and the
notifications panel are hard-coded rows. The mini-calendar is static.

Also: the greeting reads **"Welcome back, Melissa"** (`:110`) while the sidebar for the same session
says **"Angela Cruz"** and the database says **"Health Center Staff"** — three different names for
one account.

## Substantially decorative (9)

### 11 · User Management — `user_management.html` — DECORATIVE
`routes/admin.py:399` renders the template with **no context whatsoever**. Seven hard-coded user
rows against a `users` table holding three. Add User, Export, all filters, all 20 row action icons,
pagination, and all three detail-panel buttons are inert — 32 dead controls, the second-highest count
in the project.

### 12 · Audit Logs — `audit_logs.html` — DECORATIVE
This is the sharpest live-data/screen mismatch in the system. **Real audit data is being written**:
`models/audit.py::log_action()` is called on every consultation edit and every SMS broadcast, and
`audit_logs` currently holds 2 genuine rows with full before/after detail, module pill, IP address
and timestamp — written in exactly the four-column shape this screen's table already reads.

But `routes/admin.py:406` renders the template with no context, and `models/audit.py::get_audit_logs()`
— which exists, is correct, resolves the acting user's name and accepts a module filter — **is
called from nowhere in the codebase.** The screen shows seven hard-coded rows dated Jul 07 2026 and
paginates to page "184". Twenty dead controls.

This is the cheapest high-value fix in the project: the query, the writer, and the table markup all
already exist and already agree on their shape.

### 13 · Settings — `settings.html` — DECORATIVE
Ten tab panes, roughly 40 inputs, **not one `<form>` element in the file**. The `settings` table
exists and holds **0 rows**; nothing anywhere reads or writes it. Save Changes, Reset to Default,
Backup Now, Download Backup, Restore Backup, Clear Cache, Test Connection and the API-key eye toggle
are all inert.

**Flagged:** `settings.html:319` ships a hard-coded string that looks exactly like a live secret —
`value="sk_live_a83f92h1kd93js82"` in a password field labelled as the SMS gateway API key. It is
fake, but it reads as a real production credential committed into source. The genuine key mechanism
is the `SEMAPHORE_API_KEY` environment variable, documented at the top of `utils/sms.py`.

### 15 · Barangay Official Dashboard — `official_dashboard.html` — DECORATIVE
`routes/official.py:20` renders with no context. Every statistic, every list row and all six charts
are hard-coded. All four Quick Actions are `href="#"`, all four "View All" links are `href="#"`, and
both mini-calendar arrows are dead — 10 inert controls. Nothing on the Barangay Official's landing
page is real, even though `reports_analytics_context()` — which that same role can reach one click
away and which is fully live — could populate most of it.

### BO-1 · Community Announcements — `community_announcements.html` — DECORATIVE
Rendered for both Admin and Barangay Official. Eight hard-coded rows; the only Jinja in the file is
three `{% if current_role == 'admin' %}` guards demonstrating the authorship rule visually. There is
no create/edit/archive/delete endpoint anywhere in the application, and the `schedule_logs` table
that would back it holds 50 seeded `Announcement` rows that **nothing in the app ever reads**.
**44 inert controls — the highest count in the project.**

### BO-2 · Health Programs — `health_programs.html` — DECORATIVE
Eight hard-coded programme rows, one hard-coded chart, 14 inert controls. Frozen date at `:117`.

### BO-3 · Vaccination Campaigns — `vaccination_campaigns.html` — DECORATIVE
Nine hard-coded campaign rows, four hard-coded coverage charts, 15 inert controls. Frozen date at
`:120`. Notably, real immunization coverage data now exists behind
`models/immunizations.py::get_immunization_coverage()` and is already rendered on Reports &
Analytics — this screen does not read it.

### BO-4 · Community Reports — `community_reports.html` — DECORATIVE
Seven hard-coded report rows, two hard-coded charts, 20 inert controls including the Generate button.
Print / Export PDF / Export Excel are at least honestly `disabled`. Frozen date range defaulting to
`2026-01-01`–`2026-07-07`.

### BO-5 · Notifications (BO inbox) — `notifications.html` — DECORATIVE
**Contains zero Jinja expressions** — the only template in the project with none at all. Nine
hard-coded notification rows. Mark-as-read, dismiss, clear-all and the five filter chips are all
wired to JavaScript, so the screen *feels* interactive, but nothing persists: a refresh restores
every dismissed row. The sidebar badge for this screen is hard-coded to `5` in `base.html:161`.

## Shared layout — `base.html`
**Live:** role-scoped sidebar built from `inject_role_context()`, the Medicine Inventory low-stock
badge (real count, omitted entirely when zero), the flash-message stack, and the logout confirmation
modal.

**Decorative, and therefore present on all 21 screens:** the global header search box is a `<div>`
with placeholder text, not an input (`:198–201`); the "Synced just now" pill is static (`:203`); the
notification bell and its red dot open nothing (`:204`); the sidebar footer claims
"DOH-Licensed" (`:188`).

---

# SECTION 2 — DECORATIVE / UNWIRED ELEMENTS STILL REMAINING

A full parse of all 22 templates found **221 inert buttons and links**, distributed as follows.
(One reported hit — `patient_records.html:93` — is a false positive: it is a CSS selector inside a
`<style>` block. The true total is 220.)

| Template | Inert | Template | Inert |
|---|---:|---|---:|
| `community_announcements.html` | 44 | `medicine_inventory.html` | 14 |
| `user_management.html` | 32 | `official_dashboard.html` | 10 |
| `audit_logs.html` | 20 | `settings.html` | 9 |
| `community_reports.html` | 20 | `admin_dashboard.html` | 6 |
| `patient_records.html` | 15 | `appointment_scheduling.html` | 6 |
| `vaccination_campaigns.html` | 15 | `staff_dashboard.html` | 5 |
| `health_programs.html` | 14 | `patient_profile.html` | 3 |
| | | `reports_analytics.html` | 3 |
| | | `login.html` | 2 |
| | | `register_patient.html` | 2 |
| **Zero inert:** `base.html`, `add_edit_medicine.html`, `record_consultation.html`, `sms_notifications.html`, `notifications.html`\* | | | |

\* `notifications.html` scores zero only because every control carries an `onclick`. Those handlers
are client-side theatre — nothing persists.

## 2.1 — CROSS-CUTTING: Chart.js loads from a public CDN *(new finding, highest severity)*

`static/js/` contains **only** `bootstrap.bundle.min.js`. Bootstrap CSS, the Inter font family and
the Material Symbols font are all correctly vendored locally in `static/`. Chart.js is not:

```
templates/admin_dashboard.html:423        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/…">
templates/reports_analytics.html:512      (same)
templates/official_dashboard.html:492     (same)
templates/community_reports.html:307      (same)
templates/health_programs.html:341        (same)
templates/vaccination_campaigns.html:385  (same)
```

`04_DEVELOPMENT_GUIDE.md §System Architecture` specifies a **Client-Server / Star Topology**: one
Flask process, one SQLite file, clients connecting "typically over a local Wi-Fi router." On a
defense machine with no internet — or on a flaky venue connection — all eight Reports & Analytics
charts, all three Admin Dashboard charts and all seven Barangay Official charts render as blank
white boxes. Reports & Analytics *is* Objective 4, and its charts are the only part of it that
carries visually.

Worse, the failure is silent and partial: the KPI cards and tables on Reports & Analytics are pure
server-rendered HTML and will still display correctly, so the screen looks half-broken rather than
obviously offline.

Fix is a single file download into `static/js/chart.umd.min.js` plus six one-line `src` edits.

## 2.2 — CROSS-CUTTING: frozen date "Tuesday, July 7, 2026"

Hard-coded on nine screens, 36 days stale as of today:

| File | Line | Text |
|---|---|---|
| `admin_dashboard.html` | 112, 177 | "Tuesday, July 7, 2026 · Welcome back, Dr. Reyes"; "July 7, 2026 · 10 records today" |
| `staff_dashboard.html` | 110, 195 | "…Welcome back, Melissa…"; "Tuesday, July 7, 2026 · 14 appointments" |
| `official_dashboard.html` | 125 | page subtitle |
| `community_reports.html` | 96, 129 | subtitle + date-range default `2026-07-07` |
| `health_programs.html` | 117 | subtitle |
| `vaccination_campaigns.html` | 120 | subtitle |
| `notifications.html` | 82 | subtitle |
| `audit_logs.html` | 192, 248–284, 349 | filter default + all seven row timestamps |
| `user_management.html` | 246–266, 306, 415 | "Last Login" column |
| `settings.html` | 463 | "Last backup: Jul 07, 2026, 3:00 AM" |

The `display_date` / `long_date` Jinja filters and `utils.dates.today()` already exist and are used
correctly everywhere the data is live.

## 2.3 — Per-screen breakdown of what does nothing

### `patient_records.html`
| Line | Control |
|---|---|
| 180 | Search input `#patientSearch` — **no event listener anywhere in the file** |
| 185 | Sort button |
| 188 | Export button |
| 196–243 | Advanced Filter panel: Age Min/Max, Gender, Barangay/Purok, Status, Registration Date, Last Visit — the panel opens, nothing filters |
| 246, 247 | Reset Filters / Apply Filter |
| 264, 265 | Bulk-bar Export / Print |
| 302 | Row "visibility" icon (redundant — the name link works) |
| 304 | Row "print" icon |
| 328 | Empty-state "Clear Filters" → `resetDemo()`, which only un-hides a table that does not exist in that state |
| 340–346 | Pagination, hard-coded to 346 pages against 25 patients |

Note the filter panel's Status dropdown offers Active / Follow-up / Prenatal / Immunization /
Critical-Referred / Archived — none of which match the schema's real `Active / Inactive / Deceased`.

### `medicine_inventory.html`
Lines 184 (search, no listener), 189 (Sort), 192 (Export), 202–232 (filter panel: Category, Status,
Expiry From/To), 236/237 (Reset/Apply), 284 (row view), 286 (row print), 287 (row archive —
inventory has no archive path at all), 305 (Clear Filters → `resetDemo()`), 317–323 (pagination
showing 23 pages for 17 items).

### `appointment_scheduling.html`
Lines 459 (Sort), 462 (Export), 484–508 (filter panel: Date, Status, Service Type, Assigned Staff),
517/518 (Reset/Apply), 646 and 812 (row print icons). Everything else on this screen works.

### `patient_profile.html`
- `:173` **Print Record** — inert
- `:174` **Schedule Appointment** — inert. This one matters: the endpoint it should reach
  (`book_appointment`) exists and works, and the Appointment History tab immediately below already
  has working Reschedule and Cancel links. A one-line `<a href="{{ url_for(appointment_scheduling_endpoint) }}">`
  would close it.
- `:592` Medicine History "visibility" icon

### `register_patient.html`
- `:422` **Cancel** — `<button type="button">` with no handler. Inconsistent with
  `add_edit_medicine.html:299` and `record_consultation.html:452`, where Cancel is a working `<a href>`.
- `:425` **Save & Register Another** — inert.

### `reports_analytics.html`
- `:142` Print Report · `:143` Export to Excel · `:144` Export to PDF

All three are named in `03_SCREEN_SPECIFICATIONS.md` Screen 10 as required buttons. The screen is
honest about it (the subtitle at `:151` says "Filtering and export are not wired up yet") and the two
selects are properly `disabled`, but the three buttons still look clickable.

### `audit_logs.html`
Lines 175 (search), 177 (filter toggle — opens the panel), 182 (Refresh), 183 (Export), 192–219
(date, user, action, module filters), 228/229 (Reset/Apply), 254–308 (seven row view icons),
319–325 (pagination to page 184), 379 (View Patient Record), 380 (Print Entry).

### `user_management.html`
Lines 174 (search), 181 (Export), 182 (**Add User**), 191–212 (Role, Status, Last Login filters),
216/217 (Reset/Apply), 249–370 (20 row action icons: view / edit / reset-password / mail /
reactivate), 383–387 (pagination), 427 (Reset Password), 428 (Edit User), 430 (Deactivate Account).

### `settings.html`
Lines 320 (API-key eye toggle), 332 (Test Connection), 494 (Backup Now), 495 (Download Backup),
496 (Restore Backup), 528 (Clear Cache), 555 (Cancel), 556 (Reset to Default), 557 (**Save Changes**).
The ten pill tabs at 132–141 do work — they are Bootstrap `data-bs-toggle="pill"`.

### `admin_dashboard.html`
Lines 180–184 (five consultation filter chips), 415 (**View Audit Logs** → `href="#"`, when
`url_for('audit_logs')` exists and would work), plus the disabled Send Broadcast at 366.

### `staff_dashboard.html`
Lines 197, 265, 302 (three "View All" links → `href="#"`), 432, 433 (mini-calendar arrows).

### `official_dashboard.html`
Lines 165–168 (all four Quick Actions → `href="#"`; three of the four targets —
`community_announcements`, `community_reports`, `vaccination_campaigns` — are real reachable
endpoints for this role), 225, 262, 299, 373 (four "View All"), 438, 439 (calendar arrows).

### `community_announcements.html`
Lines 188 (search — has an id but no listener), 195 (Export), 196 and 489 (**Create Community
Announcement**, both copies), 205–240 (four filters), 244/245 (Reset/Apply), 288–472 (**38 row action
icons** across eight rows: view / edit / archive / delete), 498–502 (pagination).

### `community_reports.html`
Lines 115–129 (Report Type + date range), 133 (**Generate**), 211 (search), 213 (Report Type),
214 (Sort), 237–285 (13 view/download icons), 295–298 (pagination). Print / Export PDF / Export Excel
at 134–136 are correctly `disabled`.

### `health_programs.html`
Lines 165 (search), 167 (filter toggle — works), 170 (Sort), 179–191 (two filters), 201/202
(Reset/Apply), 229–299 (eight view icons), 310–312 (pagination).

### `vaccination_campaigns.html`
Lines 165 (search), 170 (Sort), 179–195 (two filters), 204/205 (Reset/Apply), 234–322 (nine view
icons), 333–335 (pagination).

### `notifications.html`
All controls carry `onclick`, so none register as inert — but `markAllRead()`, `clearAll()`,
`toggleRead()`, `dismissNotif()` and `setFilter()` only mutate the DOM. There is no notifications
table, no route, and no persistence: every action is undone by a page refresh.

### `base.html` (all 21 screens)
Header search `<div>` (`:198`), sync pill (`:203`), notification bell + dot (`:204`), hard-coded
Barangay Official notifications badge `5` (`:161`).

## 2.4 — Dead code

| Location | Finding |
|---|---|
| `models/dashboard.py` | `get_dashboard_metrics()` is called from nowhere. Its own docstring admits its resident count filters on `role = 'student'`, a value the `users.role` CHECK constraint forbids, so it can only ever return 0. Whole module is dead. |
| `models/audit.py:74` | `get_audit_logs()` — correct, complete, called from nowhere. See Screen 12. |
| `schedule_logs` table | 50 seeded rows, written only by `populate_records.py:395`, **read by no model, route or template.** |
| `patient_records.html:516`, `medicine_inventory.html:351/357`, `appointment_scheduling.html:1360/1368` | `showEmptyDemo()` / `showLoadingDemo()` — UI-state demo scaffolding, never invoked by any element. |

---

# SECTION 3 — ROUTE AND RBAC COMPLETENESS

**Verdict: clean. Zero gaps, zero regressions, zero newly-introduced holes across all 56 rules.**

Every rule was exercised under four identities. `role_required` composes over `login_required` in
every case, so anonymous access is refused before the role check even runs.

## 3.1 — Aggregate result

| | Anonymous | Admin | Staff | Barangay Official |
|---|---|---|---|---|
| Correct outcome on every one of 56 rules | ✅ | ✅ | ✅ | ✅ |
| Unauthorised access leaks | 0 | 0 | 0 | 0 |
| Unhandled 500s | 0 | 0 | 0 | 0 |

Anonymous hits `302 → /login` on all 54 protected rules; the two public rules are `/login` (200) and
`/logout` (302 → /login, harmless). Every cross-role attempt returns `302 → /dashboard`, which
re-dispatches the user to their own home — the consistent bounce pattern described in the route
module headers.

## 3.2 — Blueprint boundaries

| Blueprint | Prefix | Rules | Guard |
|---|---|---|---|
| `auth_bp` | `/` | 4 | `/`, `/login`, `/logout` open; `/dashboard` = `login_required` |
| `admin_bp` | `/admin/*` | 24 | `role_required("Admin")` on all 24, no exceptions |
| `staff_bp` | `/staff/*` | 19 | `role_required("Health Staff")` on all 19, no exceptions |
| `official_bp` | `/official/*` | 9 | `role_required("Barangay Official")` on 8; `community_announcements` additionally admits Admin |

The URL prefix and the guard say the same thing on every route, so a route filed in the wrong module
is visible in its own URL.

## 3.3 — The three permission boundaries established in recent sessions

**(a) Staff view-only on SMS — CORRECTLY ENFORCED, and enforced structurally.**

| Route | Admin | Staff | Official |
|---|---|---|---|
| `GET /admin/sms_notifications` | 200 | → /dashboard | → /dashboard |
| `GET /staff/sms_notifications` | → /dashboard | **200** | → /dashboard |
| `GET /official/sms_notifications` | → /dashboard | → /dashboard | 200 |
| `POST /admin/sms_notifications/send` | *(authorised)* | → /dashboard | → /dashboard |
| `POST /official/sms_notifications/send` | → /dashboard | → /dashboard | *(authorised)* |
| `POST /staff/sms_notifications/send` | **route does not exist** | | |

This is the right shape. The template hides the compose button from Staff via `can_broadcast`, but
that is presentation only — the actual permission is that **no send URL exists in the Staff
blueprint at all**, so a forged POST has nowhere to land. Confirmed: `utils/context.py:25–47` gives
the Staff branch no `send_broadcast_endpoint` key, so a template that tried to render one would fail
loudly rather than emit an Admin URL.

**(b) Barangay Official scoped access — CORRECTLY ENFORCED.**

The role reaches exactly eight screens: its dashboard, Reports & Analytics (read-only), SMS
Notifications (with send authority), Community Announcements, Health Programs, Vaccination
Campaigns, Community Reports, and its Notifications inbox.

It is refused from **all 15 Patient Records / Patient Profile / Register Patient / Medicine
Inventory / Add-Edit Medicine / Appointment Scheduling / Record Consultation routes** and all three
Administration screens — matching `09_UI_Architecture §2` and `03_SCREEN_SPECIFICATIONS.md` Screen 15
exactly.

Defence in depth is correct here too: `utils/context.py:76–85` simply omits
`patient_records_endpoint`, `medicine_inventory_endpoint` and `appointment_scheduling_endpoint` from
this role's context, so a shared template that reused one would raise rather than quietly emit a URL
the role bounces off. Read-only on Reports is a property of the route, not of filtered data — it is
a GET with no POST counterpart anywhere in `official_bp`.

**(c) Admin oversight — CORRECTLY ENFORCED, with one intentional asymmetry.**

Admin holds every Staff permission through its own 24-route surface (including Register Patient,
fixed in an earlier audit) plus the three Administration screens plus Community Announcements.

The one asymmetry: Admin is **refused** `/official/reports_analytics` (302 → /dashboard) and reaches
`/admin/reports_analytics` instead. Both routes call the identical `reports_analytics_context()` and
render byte-for-byte the same page, so this is a URL-space decision, not a capability gap. Correct.

## 3.4 — Health Center Staff and Reports & Analytics

Staff has **no** Reports & Analytics route and no sidebar entry for it. This is **correct, not a
gap**: `09_UI_Architecture §2` lists "Reports & Analytics (full version)" under that role's
*Restricted screens*, and `01_PROJECT_BIBLE.md §Navigation Structure` omits it from the Staff menu.
Recording this explicitly because it reads like a hole and is not one.

## 3.5 — Endpoint-namespace integrity

`utils/endpoints.py` maps bare template names onto blueprint-qualified endpoints and **aborts
registration if two blueprints expose the same view name**. All 31 view functions are uniquely
named, so the mapping is total and unambiguous. Every unknown or unauthorised name still raises the
original `BuildError`.

## 3.6 — Other security observations

| Item | Status |
|---|---|
| Password hashing | ✅ `generate_password_hash` / `check_password_hash`. A plaintext-`password` fallback exists in `routes/auth.py:39–40` but no such column exists in the schema, so it is unreachable. |
| SQL injection | ✅ Every query parameterised. The three f-string interpolations found (`models/audit.py:86`, `models/users.py:47`, the migration `ALTER` statements) interpolate only module-level constants, never request data. |
| Session fixation | ✅ `session.clear()` before establishing a new session on login. |
| Caching of authenticated pages | ✅ `no_store` after-request handler on every non-static response. |
| CSRF protection | ❌ **Absent.** No CSRF token on any of the 14 state-changing POST endpoints. Flask-WTF is not installed and is arguably out of scope for a LAN-only capstone, but it is worth having a prepared answer if a panelist asks. |
| Account lockout | ❌ Not implemented, though `03_SCREEN_SPECIFICATIONS.md` Screen 01 lists it under Validation. |
| `SECRET_KEY` | ⚠️ Defaults to the literal `"ids-bphcsn-dev-secret"` when the env var is unset (`config.py:12`). Acceptable for a LAN demo; state it as a known deployment step rather than being caught by it. |

---

# SECTION 4 — DATABASE AND MIGRATION HEALTH

## 4.1 — Table inventory (11 tables, live `app.db`, 167,936 bytes)

| # | Table | Rows | Written by | Read by |
|---:|---|---:|---|---|
| 1 | `users` | 3 | `seed_demo_users()` | auth, staff dropdown, audit join |
| 2 | `patients` | 25 | Register Patient, `populate_records.py` | Screens 03/04/05, reports, SMS audiences |
| 3 | `consultations` | 6 | Record Consultation | Screens 05/10, dashboards |
| 4 | `appointments` | 11 | Appointment Scheduling | Screens 08/05/10 |
| 5 | `immunizations` | **0** | Record Consultation checkboxes | Screen 05 tab, both dashboards, Screen 10 |
| 6 | `inventory_items` | 17 | Add/Edit Medicine, `populate_records.py` | Screens 06/07/10, sidebar badge, dashboards |
| 7 | `audit_logs` | 2 | consultation edits, SMS sends | **nothing** (see Screen 12) |
| 8 | `sms_broadcasts` | 2 | Screen 09 send | Screen 09 |
| 9 | `sms_broadcast_recipients` | 14 | Screen 09 send | Screen 09 detail panel |
| 10 | `settings` | **0** | **nothing** | **nothing** |
| 11 | `schedule_logs` | 50 | `populate_records.py` only | **nothing** |

Plus 13 named indexes and the internal `sqlite_sequence`.

## 4.2 — Fresh install vs. fully-migrated database

A clean database built from `schema.sql` was diffed against the live migrated `app.db`:

```
TABLES     11 of 11 present on both sides · 0 only-in-fresh · 0 only-in-live
COLUMNS    every column present on both sides · 0 missing · 0 extra
INDEXES    13 of 13 identical, byte-for-byte in their CREATE statements
FOREIGN KEYS   identical on all 11 tables
```

**Exactly one constraint divergence exists:**

| Column | `schema.sql` | Live (migrated) |
|---|---|---|
| `consultations.updated_at` | `TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP` | `TEXT` (nullable, no default) |

This is the divergence `migrate_add_consultation_columns.py` documents in its own header
(lines 47–52): SQLite rejects a non-constant default in `ADD COLUMN`, so the migration adds the
column plain and backfills it from `created_at`. All 6 live rows have a non-NULL `updated_at`, and
every application write sets it explicitly. **The migration's claim that this is "the only one" is
now empirically confirmed** — the diff found nothing else.

**Cosmetic only:** column *order* differs on `patients`, `inventory_items` and `consultations`,
because `ALTER TABLE ADD COLUMN` appends. All access is by name. Documented in each migration header.

`PRAGMA integrity_check` → `ok`. `PRAGMA foreign_key_check` → **0 violations**.

## 4.3 — Migration re-run results

All seven migrations were re-run against a scratchpad **copy** of the live database:

| Migration | Re-run result |
|---|---|
| `migrate_add_patient_columns.py` | ❌ **exit 1** — the known false positive (see 4.4) |
| `migrate_add_inventory_columns.py` | ✅ clean — no columns added, byte-for-byte verified |
| `migrate_add_consultation_columns.py` | ✅ clean — all 6 rows preserved, 0 backfilled, indexes asserted |
| `migrate_add_appointment_queue.py` | ✅ clean — rebuild skipped, CHECK probe rejects `'Bogus'` |
| `migrate_add_immunizations.py` | ✅ clean — UNIQUE and NOT NULL probes both fired correctly |
| `migrate_add_sms_broadcasts.py` | ✅ clean — all three constraint probes fired correctly |
| `migrate_enforce_single_consultation.py` | ✅ clean — exactly 1 row In Consultation, nothing to repair |

6 of 7 idempotent. The seventh is the known quirk, and it is confirmed harmless.

## 4.4 — The `migrate_add_patient_columns.py` quirk — confirmed as a false positive

**Reproduced exactly.** On re-run the script reports:

```
patients before migration: 25
columns added:   (none)
already present: [civil_status, blood_type, …, status]
patients after migration:  25

MIGRATION PROBLEMS:
  - 7 rows did not take the 'Active' default
```

**Root cause, precisely.** Lines 90–94 run an *unconditional* count:

```python
non_active = conn.execute(
    "SELECT COUNT(*) FROM patients WHERE status <> 'Active'").fetchone()[0]
if non_active:
    problems.append(f"{non_active} rows did not take the 'Active' default")
```

On the *first* run this is a correct assertion: the column has just been created with
`DEFAULT 'Active'`, so any non-Active row would mean the default failed. On any *later* run the
column already exists and `added` is empty, so the check is no longer measuring the migration's own
effect — it is measuring the health center's real archiving decisions. Those 7 rows are 5 patients
marked Inactive and 2 marked Deceased through the Patient Records status modal, exactly as intended.

**No data was harmed.** The same run's byte-for-byte comparison of every pre-existing value passed
silently, and the row count was unchanged at 25 before and after. The exit code is wrong; the data
is fine.

**New finding — the same latent bug exists in `migrate_add_inventory_columns.py:98–102`,** with an
identical unconditional `WHERE status <> 'Active'` count. It passes *today* only because all 17
inventory items happen to be Active. It will start reporting the same false failure the moment
anyone marks an item Inactive — and the Add/Edit Medicine form has an Active/Inactive radio at
`add_edit_medicine.html:287` that makes that a one-click action.

The one-line fix for both is to scope the assertion to the run that actually adds the column, exactly
as `migrate_add_consultation_columns.py:198` already does for its own fabrication check:

```python
if added:            # only assert the default on the run that created it
    non_active = …
```

## 4.5 — Other database findings

| Finding | Assessment |
|---|---|
| `immunizations` holds **0 rows** while `get_immunization_alert()` reports 6 children with 60 doses outstanding, 5 overdue | Not a bug — the alert measures the DOH EPI schedule against birthdates. But it means the *recording* half of the feature has never been exercised against real data. See Section 6. |
| `settings` holds 0 rows and has no reader or writer | Screen 13 is decorative. The table is correct and ready. |
| `schedule_logs` holds 50 rows nothing reads | Dead weight. Either wire Community Announcements to it or state plainly that announcements were descoped to SMS broadcasts. |
| `sqlite_sequence` shows `patients seq=87` for 25 rows, `inventory_items seq=98` for 17, `consultations seq=16` for 6 | Normal AUTOINCREMENT behaviour after deleted test rows. Harmless, but it means patient row ids jump (17 → 20 → 36 → 85) while `patient_id` stays a clean `PAT-001`…`PAT-025`. |
| `migrate_add_immunizations.py:69–72` `EXISTING_TABLES` omits `sms_broadcasts` / `sms_broadcast_recipients` | Only means those two tables are not snapshot-verified when that migration re-runs. Harmless in practice (it adds a table and touches nothing else) but the newer `migrate_add_sms_broadcasts.py` does list `immunizations`, so the omission is one-directional and easy to close. |
| No `.git` directory exists | `.gitignore` is present but inert — the project is **not under version control**. `08_PROJECT_ROADMAP.md §File Management` explicitly requires "Backup project files. Keep previous versions." `app.db` is the only copy of all demo data. |

---

# SECTION 5 — DOCUMENTATION AND HYGIENE

## 5.1 — Immunization documentation task: **STILL OUTSTANDING**, and larger than flagged

A grep for `immunization|immunisation` across all ten governance documents returns **zero matches**.
Neither `03_SCREEN_SPECIFICATIONS.md` nor `08_PROJECT_ROADMAP.md` has been touched.

The gap is wider than the immunization scope addition alone. **None** of the following — all built
and working — appears anywhere in the governance documents:

| Built and working | Documented? |
|---|---|
| DOH EPI immunization tracking (`immunizations` table, `EPI_SCHEDULE`, profile tab, dashboard alerts, coverage reporting) | ❌ nothing |
| **Screen 21 — Record Consultation** (`record_consultation.html`, 470 lines, 2 routes × 2 roles) | ❌ not in the screen inventory of `03`, `08` or `09 §1` |
| Walk-in queue / check-in workflow (`Waiting`, `In Consultation` statuses, `is_walkin`, `checked_in_at`) | ❌ nothing |
| Advance booking with conflict detection | ❌ nothing |
| Cancel / Reschedule / No-show closure | ❌ `03` Screen 08 lists the buttons, but not the No-show distinction |
| Single-consultation-at-a-time clinical invariant | ❌ nothing |
| SMS broadcast persistence (`sms_broadcasts`, `sms_broadcast_recipients`, segment costing, simulated vs live delivery mode) | ❌ nothing |
| Audit logging of consultation edits and SMS sends | ❌ `03` Screen 12 describes the *screen*, not the writer |

`03_SCREEN_SPECIFICATIONS.md` still documents 15 screens; the project has 21.

## 5.2 — `08_PROJECT_ROADMAP.md` is badly out of date

| Roadmap says | Reality |
|---|---|
| Current Phase: **UI/UX Design** | Phases 3–6 are substantially complete |
| Completion: **"Approximately 15%"** | ~70–75% by any reasonable measure |
| Phase 3 Frontend Development: **Not Started** | 21 templates, Flask project, Bootstrap, sidebar, header, dashboards, forms, tables all built |
| Phase 4 Backend Development: **Not Started** | Authentication ✅ Role management ✅ Patient CRUD ✅ Inventory CRUD ✅ Appointment CRUD ✅ Reports ✅ Notifications ✅ Audit logs ✅ (writer only) |
| Phase 5 Database Development: **Not Started** | 11 tables, 13 indexes, 7 migrations, FK-clean |
| Phase 6 Integration: **Not Started** | Session management, role enforcement, UI↔backend↔DB all connected |
| Milestones 3, 4, 5, 6: **Pending** | 3, 4, 5 are effectively met; 6 nearly so |

A panelist who reads the roadmap before the demo will believe the project is at 15%. This is the
single highest-leverage documentation fix available.

## 5.3 — `requirements.txt` — accurate, with one environment mismatch

```
Flask==3.1.3
Werkzeug==3.1.8
tzdata==2025.2
```

An AST parse of all 42 `.py` files found exactly **two** third-party import roots — `flask` and
`werkzeug`. Both are pinned. Everything else is standard library: `calendar`, `datetime`,
`functools`, `json`, `os`, `pathlib`, `re`, `sqlite3`, `sys`, `urllib`, `zoneinfo`.
**No import is missing from `requirements.txt`.**

Two notes:

1. **`tzdata` is declared but not installed in `.venv`.** `pip freeze` shows Flask, Werkzeug and
   their transitive dependencies only. `utils/dates.py:55–58` catches `ZoneInfoNotFoundError` and
   falls back to a fixed `+08:00`, so the app runs correctly — the two are identical today — but the
   running environment does not match the declared one. `pip install -r requirements.txt` fixes it.
2. **Chart.js is an undeclared runtime dependency.** It is not a Python package, so
   `requirements.txt` is the wrong place for it, but it is the one third-party asset the system needs
   that is not vendored. See §2.1.

## 5.4 — Leftover artifacts and structural hygiene

**No stray test or scratch files were found.** The 42 `.py` files are all accounted for: `app.py`,
`config.py`, `populate_records.py`, 7 migrations, 11 routes, 10 models, 8 utils, 3 database. No
`test_*.py`, no `.bak`, no `tmp`, no orphaned drafts anywhere in the tree.

Structural observations, in descending order of how much they matter for a defense:

| Item | Note |
|---|---|
| **Not a git repository** | `.gitignore` exists; `.git` does not. No version history, no rollback, no branch. `08_PROJECT_ROADMAP.md §Risk Management` lists "Version Conflicts" as a risk and "Keep previous versions" as the mitigation. |
| **No `README.md`** | `04_DEVELOPMENT_GUIDE.md §File Organization` lists one. A panelist handed the source folder has no entry point — no run instructions, no login credentials, no migration order. |
| **7 migration scripts loose in the project root** | Would read more professionally in a `migrations/` folder, numbered in dependency order. Their correct run order is currently implicit. |
| **`populate_records.py` in root** | Legitimate seeding script (uses `INSERT OR IGNORE`, so re-running is safe), but it is what put the 50 unread `schedule_logs` rows in the database, and it stamps all 25 patients with today's `created_at` — see Section 6. |
| **No separate CSS/JS files** | `04_DEVELOPMENT_GUIDE.md §CSS Guidelines` says "Create separate CSS files. Avoid inline styling," and §JavaScript Guidelines names `login.js`, `dashboard.js`, `patient.js`, etc. In practice every screen carries a large inline `<style>` block and its own inline `<script>`; `static/css/` holds only `bootstrap.min.css` and `fonts.css`. This is a long-standing, consistent deviation rather than a new defect — but it is a documented standard the code does not meet, and it is the kind of thing a panelist with the guide in hand can check in ten seconds. |
| **No `static/images/`, no `instance/`, no `tests/`** | All three are named in `04_DEVELOPMENT_GUIDE.md §File Organization`. `08_PROJECT_ROADMAP.md` Phase 7 lists five testing types, none of which have any artifact in the project. |
| `__pycache__/` present in root and each package | Gitignored — but see the git note above. Cosmetic. |
| `AUDIT_REPORT_2026-08-06_v2.md` in root; **v1 is absent** | v2 (86 KB) is the only prior audit in the project. This report is placed alongside it. |

## 5.5 — Data-standards breach

`03_SCREEN_SPECIFICATIONS.md §Data Standards` — *"Never use … Sample Data, Placeholder Text"* — and
`09_UI_Architecture §8` post-build checklist — *"Verify realistic Filipino sample data is used"* —
are both currently violated by the **live database**, not by the templates. See Section 6.1.

---

# SECTION 6 — DATA INTEGRITY SPOT CHECK

All figures read from `C:\classcheck\app.db` on **12 August 2026**, computed through the same model
functions the screens call.

## 6.1 — Headline counts

| Entity | Count | Detail |
|---|---:|---|
| **Users** | **3** | `admin` / Dr. Joshua Reyes / Admin · `staff` / Health Center Staff / Health Center Staff · `official` / Barangay Official / Barangay Official. All active. |
| **Patients** | **25** | `PAT-001` … `PAT-025`. 18 Active · 5 Inactive · 2 Deceased. 15 Male · 10 Female · 0 unrecorded. 21 have a contact number. 7 seniors (60+, 28% of roster). |
| **Consultations** | **6** | 5 seeded (Aug 3–7) + 1 recorded through the live UI (Aug 8). Only **1** carries vitals. All 6 sit in August 2026. |
| **Appointments** | **11** | 6 Completed · 2 Waiting · 1 Scheduled · 1 In Consultation · 1 Cancelled. 7 walk-ins, 4 booked. Attendance 90% YTD. |
| **Immunization records** | **0** | Table exists, indexed, constraints verified — and empty. |
| **SMS broadcasts** | **2** | `SMS-2026-0001` (Senior Citizens, 3 recipients, Barangay Health Advisory, sent by Barangay Official) · `SMS-2026-0002` (All Registered Patients, 11 recipients, General Reminder, sent by Admin). Both `simulated`, both GSM-7, 1 segment, **0 failures**. |
| **SMS recipient rows** | **14** | 3 + 11, all `Sent`, each carrying the honest "Simulated send: SEMAPHORE_API_KEY is not configured" gateway response. |
| **Audit log entries** | **2** | Both `Sent community SMS broadcast`, module `SMS Notifications`, IP `127.0.0.1`, with full detail strings naming the message, audience, counts, segments and delivery mode. |
| **Inventory items** | **17** | `MED-0001`…`MED-0017`. 14 Medicine · 2 Supply · 1 Equipment. All Active. **6 at or below reorder level, 2 out of stock, 3 already expired.** |
| **Schedule logs** | **50** | All `Announcement`/`Published`, Jul 1 – Oct 2026. Read by nothing. |
| **Settings** | **0** | — |

## 6.2 — What the live screens show right now

```
Reports & Analytics
  Total Registered Patients   25    (+25 this month)
  Appointments (YTD 2026)     11    (90% attended · 7 walk-ins)
  Inventory Items Tracked     17    (6 low stock)
  Consultations Recorded       6    (6 this month · 6 patients seen)
  Age bands       0-9:7  10-19:3  20-29:2  30-39:3  40-49:2  50-59:1  60-69:4  70+:3
  Sex             Female 10 (40%) · Male 15 (60%) · unrecorded 0
  Top services    Walk-in Consultation 7 · Consultation 1 · Hypertension Follow-up 1
                  · Immunization 1 · Prenatal Check-up 1
  Programmes      Immunization 0 · Senior Citizen (60+) 7

SMS Notifications
  Broadcasts recorded  2      Messages accepted 14      Messages failed 0
  Reachable contacts  11      Gateway: Simulated — no API key
  Audiences   All Registered Patients 11 · Senior Citizens 3
              · Parents/Guardians of Children Under 5 1 · Health Center Personnel 0

Appointment Scheduling (today, 12 Aug 2026)
  Queue: 0 rows.   Upcoming: 0 rows.   Room free.

Alerts
  Low stock 6 (2 out of stock)
  Immunization 6 children due · 5 overdue · 60 doses outstanding
```

Everything above is internally consistent and cross-checks correctly. Reachable contacts (11) is
right: 18 Active patients, minus 3 with no number, minus 4 duplicates of `09000000002` merged so
nobody is texted twice.

## 6.3 — Data quality issues found

### 🔴 Junk test records are visible in the live data

| Row | Content |
|---|---|
| `patients` id 36 / `PAT-019` | first_name `qwe`, last_name `qwe` |
| `patients` id 37 / `PAT-020` | first_name `asd`, last_name `asdas` |

These are not confined to Patient Records. They surface in:
- the **Appointment Scheduling queue** — appointments 8, 9 and 11 all belong to these two patients,
  and appointment 9 is the row currently holding `In Consultation`;
- the **SMS broadcast history**, permanently — `sms_broadcast_recipients` records
  `"qwe qwe qwe"` and `"asd asc asdas"` as having been texted by `SMS-2026-0002`. Those rows are
  historical fact and cannot be edited without falsifying the record; the honest fix is to delete
  that broadcast and re-send it after the patients are cleaned up;
- the **immunization alert**, since both are under 5 and count toward the "6 children due" figure.

Direct breach of `03_SCREEN_SPECIFICATIONS.md §Data Standards`.

### 🔴 One clinically nonsensical consultation

`consultations` id 16, patient 85 (`PAT-023`, Kenneth Manalastas, born **2026-05-01** — three months old):

| Field | Recorded |
|---|---|
| Chief complaint | Fever and cold |
| **Diagnosis** | **Heart failure** |
| Treatment plan | Amoxicilin *(sic)* |
| Temperature | **30.0 °C** (hypothermic) |
| Pulse | 120 bpm |
| Respiratory rate | 50 /min |
| **Weight** | **70.0 kg** |
| **Height** | **175.0 cm** |
| Head circumference | 30.0 cm |

**This is not a validation defect.** `models/consultations.py:92–99` sets deliberately wide ranges
(temperature 25–45 °C, weight 0.5–400 kg, height 20–250 cm) whose stated purpose is to catch a
slipped decimal point, not to second-guess a clinician. Every value above is inside those bounds. It
is a *data* problem: someone typed adult vitals into an infant's record while testing.

It is also the **only** consultation in the database carrying vitals at all, which means it is the
one that will be on screen if anyone expands a consultation record during the demo — and it is the
single row feeding the "Heart failure" entry in Reports & Analytics' Top Diagnoses table.

### 🟡 Appointment Scheduling is empty today

The queue reads today's date. The stale rows sit on other days:

| Appt | Date | Status | Patient |
|---:|---|---|---|
| 8 | 2026-08-08 | **Waiting** | asd asdas |
| 9 | 2026-08-09 | **In Consultation** | asd asdas |
| 11 | 2026-08-11 | **Waiting** | qwe qwe |
| 10 | 2026-08-13 | Cancelled | Arnel Manalastas |

So on 12 August the screen shows **zero queue rows and zero upcoming rows**. The one future booking
is cancelled. Objective 3's flagship screen currently demos as a blank page — while three
never-resolved visits sit in the past, one of them permanently "In Consultation" since 9 August.

### 🟡 Every patient and every consultation is dated August 2026

`populate_records.py` stamps `created_at` at run time, so all 25 patients registered "this month" and
all 6 consultations fall in August. The consequence is visible on Reports & Analytics: both six-month
trend charts read `Mar 0 · Apr 0 · May 0 · Jun 0 · Jul 0 · Aug 25` and `… Aug 6` — a single spike
against five empty months. The charts are correct; the data behind them has no history to show.

### 🟡 The immunization feature has never recorded a dose

`immunizations` = 0 rows. `get_immunization_coverage()` therefore returns
`enrolled 0, doses_given 0, awaiting_first_dose 6` and the Reports & Analytics "Immunization"
programme row shows a count of 0 — beside a Staff dashboard card reading "6 children due, 5 overdue,
60 doses outstanding."

Both numbers are correct and they are not contradictory, but they are the *alert* half of the
feature shown twice. The recording half — ticking a dose on Record Consultation and watching it
appear on the profile's Immunization Record tab with the status flipping from Overdue to Completed —
is the part that demonstrates the objective, and no data proves it has ever run end-to-end.

### 🟢 No integrity problems

`PRAGMA integrity_check` = `ok`. `PRAGMA foreign_key_check` = 0 violations. No orphaned consultation,
appointment, immunization or broadcast-recipient row. No duplicate `patient_id`, `item_code` or
broadcast `reference`. Exactly one appointment is `In Consultation`, satisfying the invariant
`migrate_enforce_single_consultation.py` exists to protect. All 6 consultations have a non-NULL
`updated_at`. Every broadcast's `recipient_count` / `sent_count` / `failed_count` matches its actual
per-recipient rows (3 = 3 + 0, 11 = 11 + 0).

---

# SECTION 7 — SUMMARY AND PRIORITIZED NEXT STEPS

Ranked by **impact on a capstone defense**, not by technical severity. Each item is sized for one
contained session, matching this project's established discipline.

## Tier 1 — Do these before the defense (each is small, each is visible)

**1. Vendor Chart.js locally.**
Download `chart.umd.min.js` into `static/js/`, change the `<script src>` on six templates to
`url_for('static', …)`. Without this, a venue with no internet blanks every chart on Reports &
Analytics — the whole visual payload of Objective 4 — plus both dashboards and three Barangay
Official screens. Bootstrap and both font families are already vendored; Chart.js is the only asset
left outside. *One session, mostly mechanical, removes the largest single-point failure in the demo.*

**2. Clean the demo data and reseat the queue.**
Delete or rename `PAT-019 (qwe qwe)` and `PAT-020 (asd asdas)`; correct or delete consultation 16's
adult vitals on a three-month-old; resolve appointments 8, 9 and 11 (the one stuck "In Consultation"
since 9 August); put two or three appointments on today and the next few days so Appointment
Scheduling is not blank. Note that broadcast `SMS-2026-0002` records the junk names permanently —
delete and re-send it rather than editing history. *Directly closes the `§Data Standards` breach and
un-blanks Objective 3's main screen.*

**3. Record real immunization doses.**
Walk one under-5 patient through Check In → Start Consultation → Record Consultation with two or
three EPI doses ticked, and confirm the profile's Immunization Record tab flips those rows from
Overdue to Completed and the dashboard alert count drops. This is the single most differentiated
feature in the project and it currently has **zero** evidence of ever having run. *Also produces the
first non-zero `immunizations` rows for Reports & Analytics.*

**4. Update `08_PROJECT_ROADMAP.md`.**
It says the project is at "Approximately 15%", in "UI/UX Design", with Phases 3, 4, 5 and 6 "Not
Started". A panelist reading it before the demo is told the system does not exist yet. Move Phases
3–6 to Complete/In Progress, tick the Phase 4 task list, mark Milestones 3–5 met, and restate
completion honestly. *One session of editing, disproportionate effect on how the work is perceived.*

## Tier 2 — High value, still small

**5. Wire the Audit Logs screen.** Everything needed already exists:
`models/audit.py::get_audit_logs()` is written, correct, and called from nowhere; `audit_logs` holds
real rows; and `audit_logs.html`'s table already has the four columns the query returns. Pass the
context in `routes/admin.py:406`, replace seven hard-coded rows with a `{% for %}`, and delete the
fake "184 pages". *The largest demonstrable-capability-per-line-of-code ratio left in the project,
and it turns a governance screen from mockup into evidence that consultation edits and SMS sends are
genuinely tracked.*

**6. Fix the frozen "Tuesday, July 7, 2026" on nine screens.** `utils.dates.today()` and the
`long_date` filter already exist. On the static screens this is one Jinja expression each. *Cheap,
and a stale date on half the screens is exactly what a sharp panelist notices first.*

**7. Make the two dashboards real.** Replace the five hard-coded Admin stat cards and the three
hard-coded Staff cards with figures from the context builders that already compute them —
`get_patient_stats()`, `get_appointment_report()`, `get_consultation_stats()`, `get_broadcast_stats()`
are all live and already feed Reports & Analytics. Replace the fake "Recent Patient Consultations"
table with the real six rows. *The Admin Dashboard is the first screen the panel sees; it currently
claims 2,418 patients against a real 25.*

**8. Fix the latent `migrate_add_inventory_columns.py` false positive.** Scope the
`status <> 'Active'` assertion to `if added:`, and apply the same one-line fix to
`migrate_add_patient_columns.py` so its known quirk stops firing too. *Ten minutes; removes a
migration that exits 1 on a healthy database — an awkward thing to have happen in front of a panel.*

**9. Put the project under version control.** `git init`, commit. The `.gitignore` is already
written and correct, and `app.db` is currently the only copy of all demo data.
`08_PROJECT_ROADMAP.md §Risk Management` asks for exactly this.

## Tier 3 — Documentation debt (defensible if acknowledged, damaging if discovered)

**10. Add the eight undocumented features to `03_SCREEN_SPECIFICATIONS.md`.** Immunization tracking,
**Screen 21 Record Consultation** (a whole screen missing from the inventory), the walk-in queue,
advance booking, cancel/reschedule/no-show, the single-consultation invariant, SMS broadcast
persistence, and audit logging. Update `09_UI_Architecture §1` from 15 screens to 21.

**11. Write a `README.md`.** Run instructions, the three demo logins, migration order, and the
`SEMAPHORE_API_KEY` activation step. `04_DEVELOPMENT_GUIDE.md` lists one; there isn't one.

**12. Decide and record what Community Announcements is.** Either wire it to the 50 `schedule_logs`
rows already sitting in the database, or state explicitly in the docs that announcements were
consolidated into the SMS broadcast feature and the screen is a UI prototype. Right now it is
44 dead controls over a table nothing reads — the weakest screen to be asked about.

## Tier 4 — Known and acceptable; prepare an answer rather than code

- **Reports & Analytics export buttons** (Print / Excel / PDF, `03` Screen 10 lists all three).
  The screen already says so in its own subtitle. If time allows, browser `window.print()` with a
  print stylesheet is a genuine, honest half-hour Print Report.
- **Six decorative screens** — User Management, Settings, and the four Barangay Official extension
  screens. Three of these are supporting infrastructure the Bible explicitly ranks below the core
  objectives; four were never in the approved Proposal at all. That is a defensible prioritisation —
  but say it first, before you are asked.
- **The remaining ~200 inert controls** are almost all search / sort / export / filter / pagination
  on those same decorative screens. Not worth wiring individually. Consider `disabled` with a
  tooltip on the most tempting ones (Add User, Save Changes, Create Community Announcement) so a
  panelist clicking around does not find silence — Reports & Analytics already does exactly this with
  its two disabled selects, and it reads as deliberate rather than unfinished.
- **`settings.html:319`** — replace the fake `sk_live_a83f92h1kd93js82` with an obvious placeholder.
  It reads as a real production credential committed to source.
- **No CSRF tokens, no login lockout, no `SECRET_KEY` in the environment.** All three are reasonable
  for a LAN-only barangay deployment, and two of them (lockout, Remember Me) are named in
  `03` Screen 01. Have the answer ready.

## What is genuinely finished

Worth stating plainly, because it is most of the system and it is solid:

- **All four core Proposal objectives are built and working** against real stored data, with real
  validation, real write paths and honest reporting of what the schema cannot answer.
- **RBAC is clean** — 56 routes, four identities, zero gaps, with the Staff SMS boundary enforced
  structurally (no endpoint exists) rather than cosmetically.
- **The database is sound** — 11 tables, integrity `ok`, zero FK violations, and a fresh install that
  matches a fully-migrated one on everything except one documented, deliberate nullable column.
- **The migrations are careful work** — six of seven idempotent, every one verifying its own effect
  byte-for-byte and probing that its constraints actually refuse bad data rather than merely
  declaring it.
- **The system tells the truth about itself.** Reports & Analytics names five things it cannot count
  and says why; the SMS screen states plainly that nothing has been transmitted; the profile's
  Medicine History says dispensing is not recorded. That discipline is unusual and it is worth
  pointing at during the defense.

---

*End of AUDIT_REPORT_2026-08-12_v3.*
