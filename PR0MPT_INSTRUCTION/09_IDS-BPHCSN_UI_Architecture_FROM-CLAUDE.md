# IDS-BPHCSN UI ARCHITECTURE DOCUMENT

Version: 2.0
Status: Approved. Sections 1, 2, 3, 5, 7 and 8 reconciled against the built system on 2026-08-15 and re-checked on 2026-08-21; section 10 added. Sections 11, 12 and 13 added 2026-08-21. Section 17 added 2026-08-26. Section 1's inventory and section 2's per-role screen lists re-counted on 2026-09-05, when My Account was added as Screen 21.
Prepared For: Integrated Digital System for Barangay Poblacion Health Center Services and Community Notifications (IDS-BPHCSN)
Institution: Northeastern Mindanao Colleges (NEMCO)

---

## Purpose of This Document

This document serves as the official UI architecture blueprint for the IDS-BPHCSN Capstone Project.

It defines:

- Complete screen inventory
- Navigation architecture
- User flows
- Global layout
- Shared UI components
- Design consistency rules
- Bootstrap component mapping
- UI development blueprint

All future UI generation and frontend development must follow this document unless an approved revision is made.

---

## 1. Complete Screen Inventory

**The system has 21 screens.** Screens 1–15 were the original inventory; screens 16–20 were built afterwards and are added here in Version 2.0; screen 21, My Account, was built on 2026-09-04 and added here on 2026-09-05.

`templates/` holds 25 `.html` files, of which four are not screens. `base.html` is the shared layout — sidebar, header, content region. `_print.html` and `_chart_table.html` are partials included by the screens that print and the screens that render a chart's underlying figures as a table. And `maintenance.html` is a **response page rather than a screen**: it has no route and no sidebar entry, and `utils/security.py::_maintenance_response()` renders it with a 503 *in place of* whatever screen the request asked for while maintenance mode is on. Nothing navigates to it, so counting it as a screen would imply somewhere to click that does not exist. The other 21 files are the 21 screens below, one file each.

The **Primary Role(s)** column is not a description kept in step by hand. It is the set of roles each view's own `role_required()` guard admits, read off `utils/security.py` and confirmed against the live `url_map` by `routes/user_views.py::accessible_screens()` — the same function that prints the permission list on Screen 11. If this column and the code ever disagree, the code is right and this table is stale.

| # | Screen | Template | Primary Role(s) | Purpose |
|---|--------|----------|------------------|---------|
| 1 | Login Page | `login.html` | All roles (unguarded) | Authenticate users and route them to the correct role-based dashboard. ✅ Approved |
| 2 | Administrator Dashboard | `admin_dashboard.html` | Administrator | Full operational overview: patient, appointment, inventory, and SMS figures plus recent activity. ✅ Approved |
| 3 | Patient Records | `patient_records.html` | Administrator, Health Center Staff | Browse, search, filter, and manage all registered patients. |
| 4 | Register Patient | `register_patient.html` | Administrator, Health Center Staff | Capture new patient personal, emergency contact, and medical information. |
| 5 | Patient Profile | `patient_profile.html` | Administrator, Health Center Staff | A single patient's full record across six tabs (personal, medical, consultation, medicine, vaccination, appointment history). |
| 6 | Medicine Inventory | `medicine_inventory.html` | Administrator, Health Center Staff | Track medicine stock, expiration, and low-stock/near-expiry status. |
| 7 | Add/Edit Medicine | `add_edit_medicine.html` | Administrator, Health Center Staff | Create or update a medicine record's details and stock. |
| 8 | Appointment Scheduling | `appointment_scheduling.html` | Administrator, Health Center Staff | Manage the appointment calendar, walk-in queue, and the live consultation queue. |
| 9 | SMS Notifications | `sms_notifications.html` | Administrator, Health Center Staff, Barangay Official | Compose, send, and record SMS broadcasts to a real recipient audience. Specified as "Community Notifications" in `03_SCREEN_SPECIFICATIONS.md`; same screen. |
| 10 | Reports & Analytics | `reports_analytics.html` | Administrator, Barangay Official | Consultation, inventory, registration, and immunisation reporting, over a selectable date range. Export Excel, Export PDF and Print are all built. |
| 11 | User Management | `user_management.html` | Administrator only | List every account that can sign in, with the screens each role's guards admit it to. Account writes are built: Add User, Edit User, Reset Password, and Deactivate/Reactivate, with the last-Administrator guard on the last two. |
| 12 | Audit Logs | `audit_logs.html` | Administrator only | Monitor and filter recorded system activity by user, date, and action. |
| 13 | Settings | `settings.html` | Administrator only | Configuration screen, part live. **General Settings is stored and read back** — the health center's name, barangay, municipality, province and the clinic's opening/closing times are written to the `settings` table and consumed by the SMS composer, all three export modules, the booking slot generator and every template header. **Password Policy, the sign-in figures, the database size and version are read from the running system** and are not editable anywhere. **Backup downloads a real, verified copy of the database.** **Maintenance Mode is live** — an Administrator can close the system to Health Center Staff and Barangay Officials, who are shown a 503 maintenance page and keep their sessions; Administrator access is structurally unaffected, so there is no self-lockout. The remaining panes sit in per-pane disabled fieldsets. User Preferences, Notification Settings and Clear Cache were removed outright. |
| 14 | Health Center Staff Dashboard | `staff_dashboard.html` | Health Center Staff | Operational overview scoped to staff duties — no admin modules. |
| 15 | Barangay Official Dashboard | `official_dashboard.html` | Barangay Official | Community-facing overview — no patient, inventory, or user data. |
| 16 | Health Programs | `health_programs.html` | Barangay Official | Programme membership, derived from patient records. Programmes with no source in the schema report their own absence. |
| 17 | Vaccination Campaigns | `vaccination_campaigns.html` | Barangay Official | Immunisation coverage against the DOH EPI schedule. The reporting unit is the scheduled dose, not a named campaign. |
| 18 | Community Reports | `community_reports.html` | Barangay Official | Community-level health summary, built from `reports_analytics_context()` so it cannot report the barangay differently from Screen 10. Exports a real spreadsheet and PDF. |
| 19 | Notifications | `notifications.html` | Barangay Official | Notification centre. Presentation only — there is no notifications table. |
| 20 | Record / Edit Consultation | `record_consultation.html` | Administrator, Health Center Staff | Write up the clinical record of a visit, and edit one already recorded. Two modes of one template and one context builder. See §10. |
| 21 | My Account | `my_account.html` | All three roles (`login_required`) | The signed-in person's own details, and a self-service password change requiring the current password. The only screen guarded by `login_required` rather than `role_required`, because what it reaches is one row — the caller's own — rather than a role's worth of screens. Entered from the header profile chip; it has no sidebar entry. |

**One screen is not backed by data: 19, Notifications.** It is rendered as `render_template('notifications.html')` with no context, because there is no `notifications` table. Nothing on it should be quoted as a system output; recorded activity lives on Screen 12.

Screen 13 is the partial case and is stated as one rather than lumped in above: its Security pane is live and everything else on it is a disabled fieldset. Screen 18 was in this sentence until 2026-08-21 and is now fully data-driven, as are 15, 16 and 17 — every Barangay Official screen takes a context from `routes/official_views.py`, and each derives its figures from `reports_analytics_context()` rather than counting anything itself.

---

## 1.1 Community Announcements → SMS Broadcasts

**Decision: Community Announcements is retired. SMS Notifications is the single community-notification mechanism.**

Community Announcements appeared in the original sidebar for the Administrator and the Barangay Official, and in the Barangay Official Dashboard as a "Health Announcements" widget. It was never a feature: a static template with no model, no table, and no create, edit, or delete route. Nothing could be posted, and nothing was stored.

SMS Notifications is real. It has a table (`sms_broadcasts`), a composer with a validated recipient audience, a send path, a stored history of what was sent and to whom, and an audit entry per broadcast. Its audiences are computed from actual patient and user records — all registered patients, senior citizens aged 60 and over, parents or guardians of children under 5, and health center personnel — and the two audiences that cannot be built ("Entire Barangay / All Residents" and "Pregnant Women") are listed with the reason they are unavailable rather than offered and silently failing.

Both features answered the same Proposal requirement: tell the community something. Keeping a screen that could not do it, alongside a screen that could, meant the system appeared to offer two notification channels while only one existed — the kind of gap a defence panel finds by clicking. So the announcement item was removed from every sidebar and the retirement recorded in `templates/base.html` next to where the menu item used to be.

Consequences worth knowing:

- The Barangay Official's "Announcements" sidebar item no longer exists. There is no announcements route to restore it to.
- The SMS sidebar item carries no badge. It used to read "12"; nothing in this system queues or holds SMS, so there was no pending count behind it.
- The Notifications item carries no badge either, for the same reason — there is no notifications table and nothing writes one.

Do not re-add an Announcements screen without adding the table and routes behind it first.

---

## 2. Navigation Structure

The menus below are transcribed from `templates/base.html`, which renders one sidebar and swaps only the items per role. The accessible and restricted lists are the enforced guards, not a summary of them.

Four screens are reachable but never appear in a sidebar. Three are entered from another screen with a subject already chosen: **Patient Profile** (from Patient Records), **Add/Edit Medicine** (from Medicine Inventory), and **Record / Edit Consultation** (from the queue, or from a patient's Consultation History). The fourth, **My Account**, is entered from the profile chip in the header — it has no sidebar entry because it belongs to no role's menu; every role reaches it the same way.

### Administrator

**Sidebar Menu Structure:**

```
MAIN MENU
├── Dashboard
├── Patient Records
├── Register Patient
├── Medicine Inventory   [low-stock count badge, omitted when zero]
├── Appointment Scheduling
├── SMS Notifications
└── Reports & Analytics

ADMINISTRATION
├── User Management
├── Audit Logs
└── Settings
```

- **Navigation hierarchy:** Two sidebar groups — "Main Menu" (operational) and "Administration" (governance). This is the only role for which the Administration group is rendered.
- **Accessible screens (15 of 21):** Login, Administrator Dashboard, Patient Records, Register Patient, Patient Profile, Medicine Inventory, Add/Edit Medicine, Appointment Scheduling, Record / Edit Consultation, SMS Notifications, Reports & Analytics, User Management, Audit Logs, Settings, My Account.
- **Restricted screens:** The two other dashboards, and the four Barangay Official screens — Health Programs, Vaccination Campaigns, Community Reports, Notifications. **The Administrator does not have access to every screen.** The earlier claim in this document that the role reached "all 15 screens" was never true of the built system: the community-facing screens are guarded to the Barangay Official alone.

### Health Center Staff

**Sidebar Menu Structure:**

```
MAIN MENU
├── Dashboard
├── Patient Records
├── Register Patient
├── Medicine Inventory   [low-stock count badge, omitted when zero]
├── Appointment Scheduling
└── SMS Notifications
```

- **Navigation hierarchy:** Single group, operational only — no "Administration" section is rendered for this role.
- **Accessible screens (11 of 21):** Login, Health Center Staff Dashboard, Patient Records, Register Patient, Patient Profile, Medicine Inventory, Add/Edit Medicine, Appointment Scheduling, Record / Edit Consultation, SMS Notifications, My Account.
- **Restricted screens:** Reports & Analytics, User Management, Audit Logs, Settings, and all four Barangay Official screens.
- **Resolved:** an earlier note here hedged that staff might get SMS "send/view only, not necessarily full broadcast history depending on future rule confirmation". The rule is settled in code — Health Center Staff render the same SMS screen as the Administrator, including the full broadcast history, and may send. `routes/staff.py` and `routes/admin.py` build it from one shared context builder.

### Barangay Official

**Sidebar Menu Structure:**

```
MAIN MENU
├── Dashboard
├── SMS Notifications
├── Health Programs
├── Vaccination Campaigns
├── Community Reports
├── Reports & Analytics
└── Notifications
```

- **Navigation hierarchy:** Single group, community-facing. No Administration section. No badges on any item — see §1.1.
- **Accessible screens (9 of 21):** Login, Barangay Official Dashboard, SMS Notifications, Health Programs, Vaccination Campaigns, Community Reports, Reports & Analytics, Notifications, My Account.
- **Restricted screens:** Patient Records, Patient Profile, Register Patient, Record / Edit Consultation, Medicine Inventory, Add/Edit Medicine, Appointment Scheduling, User Management, Audit Logs, Settings, and the other two dashboards.
- **The Barangay Official reaches no clinical screen.** This is the system's central access rule, and it holds against the enforced guards independently of this document: `accessible_screens("Barangay Official")` walks the live `url_map` and returns exactly the seven guarded screens above — no patient record, no patient profile, no consultation, no inventory.
- The "Announcements" item that this section previously listed does not exist. See §1.1.

---

## 3. User Flow

### Administrator Flow

```
Login
 → Administrator Dashboard
   → Patient Records → Patient Profile → (Edit patient / Consultation History → View or Edit)
   → Register Patient → (Save → back to Patient Records)
   → Medicine Inventory → Add/Edit Medicine → (Save → back to Inventory)
   → Appointment Scheduling → (Book / Reschedule / Cancel / Check in)
                            → Start Consultation → Record Consultation
                                                 → (Save → patient profile,
                                                    queue entry Completed)
   → SMS Notifications → (Compose → Send → History)
   → Reports & Analytics → (View over a date range; Export Excel / Export PDF / Print)
   → User Management → (View roster and derived permissions; writes not implemented)
   → Audit Logs → (Filter by user/date/action)
   → Settings → (Security pane live; every other pane disabled, nothing stored)
 → Logout
```

### Health Center Staff Flow

```
Login
 → Health Center Staff Dashboard
   → Patient Records → Patient Profile → Consultation History → (View / Edit)
   → Register Patient → (Save)
   → Appointment Scheduling → (Book / Reschedule / Cancel / Check in)
                            → Start Consultation → Record Consultation
   → Medicine Inventory → Add/Edit Medicine
   → SMS Notifications → (Compose → Send → History)
 → Logout
```

The staff flow is the administrator's operational flow minus Reports & Analytics and the Administration group. It is served by the same templates and the same context builders, under `role_required("Health Staff")` guards.

### Barangay Official Flow

```
Login
 → Barangay Official Dashboard
   → SMS Notifications → (Compose → Send → History)
   → Health Programs → (View membership and untracked notices)
   → Vaccination Campaigns → (View per-dose EPI coverage)
   → Community Reports → (View; Export Excel / Export PDF)
   → Reports & Analytics → (View)
   → Notifications → (Presentation only — the one screen with no data source)
 → Logout
```

No branch of this flow reaches a patient record, a consultation, or the inventory.

Logout is available from the header/profile dropdown on every screen, for every role, per the Global Navigation Rules in `03_SCREEN_SPECIFICATIONS.md`.

---

## 4. Global Layout Structure

Every screen — regardless of role — must be built from the same four regions:

| Region | Spec | Behavior |
|--------|------|----------|
| **Sidebar** | 280px fixed width, left, teal `#169B92` background, white text/icons | **Identical structure app-wide.** Only the *menu items* change per role (see Section 2) — never the styling, icon set, active/hover treatment, or position. |
| **Header** | 80px fixed height, white background | **Identical across all screens a role can reach.** Contains: global patient search, a "Loaded HH:MM" pill, the notification bell, and the user avatar + role label + dropdown. Never redesigned per screen — but two of the four are scoped to the role, on the same grounds §2 scopes the sidebar, and the detail is below this table. |
| **Main Content Area** | Fluid, Bootstrap 12-column grid, `#F5F7FA` background | **The only region that changes.** Houses the screen-specific cards, tables, forms, and charts defined in the Screen Specifications. |
| **Footer** | No persistent footer bar observed in approved UI; system status/version info is anchored at the bottom of the sidebar instead (e.g., "System Online," version number) | Retain this sidebar-footer pattern — do not introduce a separate horizontal page footer, to stay consistent with the approved Dashboard. |

**Rule:** If a new screen appears to require a layout change to sidebar or header, that is a signal to stop and flag it — per the Design System, these two regions must never be redesigned.

### 4.1 What the header actually holds, per role

The header was drawn with four elements and shipped with three of them wired to
nothing: a `<div>` reading "Search patient name or ID...", a pill reading "Synced
just now", and a bell with a red dot. All three appeared on all 21 screens for
all three roles. They are now the following, and the rule above is unchanged —
the header is still never redesigned *per screen*. What varies is per **role**,
which is the same axis §2 already scopes the sidebar on.

| Element | Administrator | Health Center Staff | Barangay Official | Notes |
|---|---|---|---|---|
| **Global patient search** | Yes | Yes | **Absent** | A real form. It submits `search` to that role's Patient Records URL and introduces no matching rule of its own — Patient Records' toolbar box has matched patient ID / name / contact number / address as a lower-cased substring since that screen was built, and it is what runs the term. The Barangay Official has no Patient Records (§2), so there is no destination to give the box; `patient_records_endpoint` is simply absent for that role and the header renders nothing. |
| **"Loaded HH:MM" pill** | Yes | Yes | Yes | Was "Synced just now". Nothing in this system syncs: one SQLite file, no background job, no second store. What it prints instead is the moment the page was rendered, from `utils.dates.now()` — the same clock every date on the screen comes from. Reload and it changes, which is what makes it checkable. |
| **Notification bell** | **Absent** | **Absent** | Yes | Links to the Barangay Official's Notifications screen, which is the only role that has one at any URL. The other two have no such screen, so their header has no bell — there is nothing to disable and explain. |
| **Red unread dot** | — | — | — | Removed for every role. There is no notifications table and nothing writes one, so there was no count behind it. Removed rather than zeroed, for the same reason the sidebar's hard-coded "5" badge went: a zero badge reads as an alert that is not there. |

---

## 5. Shared UI Components

| Component | Reused In |
|-----------|-----------|
| **Dashboard/Overview Cards** (white, 16px radius, soft shadow, 24px padding) | All three dashboards, Reports summary tiles |
| **Data Table** (rounded, white, soft shadow, alternating row hover, status badges, action buttons, search/filter/sort/pagination) | Patient Records, Medicine Inventory, Appointment Scheduling, User Management, Audit Logs, Reports (tabular sections) |
| **Search Bar** | Header (global patient search — Administrator and Health Center Staff only; it submits to Patient Records and that screen's own filter does the matching), Patient Records, Medicine Inventory tables |
| **Advanced Filter** | Patient Records, Medicine Inventory, Audit Logs, Appointment Scheduling |
| **Buttons** (Primary/Secondary/Danger/Success, Bootstrap-styled, 12px radius) | Every screen — form submissions, table actions, modals |
| **Forms** (48px input height, 12px radius, label-above, Bootstrap validation) | Register Patient, Add/Edit Medicine, Appointment scheduling form, Record / Edit Consultation, SMS composer, Login. *(Settings and User Management carry form markup but no working form — see §1.)* |
| **Modals** | Schedule Appointment (booking), Check In Patient, Cancel appointment, Reschedule appointment, Change Patient Status, Change Item Status (Medicine Inventory archive — see §12), Compose Broadcast, Confirm Logout. Every one of them follows the shape Patient Records' status dialog set: centred, 16px radius, header / body / footer, and where there is a choice to make the submit buttons *are* the choices. *(There is no Reset Password modal — password reset is not implemented.)* |
| **Pagination** | Patient Records, Medicine Inventory, User Management, Audit Logs tables |
| **Status Badges** (Success/Warning/Danger/Info/Neutral, 999px radius) | Patient status, medicine stock status, appointment status, user status, notification delivery status |
| **Alerts/Toasts** | Low-stock warnings, save/update confirmations, failed SMS send notices |
| **Charts** (Bar, Line, Pie, Donut — no 3D) | Administrator Dashboard, Reports & Analytics, Barangay Official Dashboard (community stats) |
| **Notifications Panel/Bell** | Header — global, all roles |
| **Profile Dropdown** | Header — global, all roles (shows name, role, logout) |
| **Breadcrumbs** | Patient Profile, Add/Edit Medicine, Settings sub-sections (to show hierarchy back to parent list) |
| **SMS Composer / Character Counter / Recipient Selector** | SMS Notifications (Screen 09) only |
| **Calendar Widget** | Appointment Scheduling |
| **Tabs** | Patient Profile (Personal/Medical/Consultation/Medicine/Vaccination/Appointment history — six tabs, as specified), Settings sections |
| **Untracked Notice** (a labelled statement, in place of a figure, naming what has no data source and why) | Reports & Analytics, Health Programs, Vaccination Campaigns, User Management, Audit Logs, Patient Records (Prenatal card), both community dashboards |
| **EPI Schedule Checklist** (one row per scheduled dose; recorded doses render locked with the date given, never as a checkbox) | Record / Edit Consultation only — see §9 and §10 |

---

## 6. Design Consistency Rules

| Category | Rule |
|----------|------|
| **Typography** | Inter (fallback Arial). Page Title 32px Bold · Section Title 24px Semi-Bold · Card Title 18px Semi-Bold · Body 16px Regular · Caption 14px Regular · Small Labels 12px Medium |
| **Colors** | Primary Teal `#169B92` (sidebar, buttons, active nav, links) · White `#FFFFFF` (cards/forms) · Background Gray `#F5F7FA` · Success `#22C55E` · Warning `#F59E0B` · Danger `#EF4444` · Info `#3B82F6` |
| **Spacing** | 8-point system only: 8/16/24/32/40/48/64px. No arbitrary spacing values. |
| **Icons** | Material Symbols Outlined exclusively. Never mix icon libraries. Consistent sizing throughout. |
| **Card Style** | White background, 16px radius, soft shadow, 24px padding. Cards never touch — maintain consistent gutter. |
| **Form Style** | 48px input height, 12px radius, label above input, light-gray placeholder text, teal border on focus, Bootstrap validation styling (no custom validation UI). |
| **Table Style** | Rounded (16px), white, soft shadow, alternating row hover, status badges in dedicated column, action icons in dedicated column. Search and filter are present on every data table; **sort** is present where more than one order is useful (Patient Records, Medicine Inventory) and deliberately absent where the query's order is itself the answer (Appointment Scheduling's queue) — see §15. **Pagination is not present on any table**: every row the query returns is already on the page. |
| **Button Style** | Primary = filled teal/white text; Secondary = white/teal border; Danger = red; Success = green. All rounded 12px, Bootstrap-based. |
| **Border Radius** | Cards 16px · Buttons 12px · Inputs 12px · Badges 999px · Tables 16px. No exceptions. |
| **Shadows** | Subtle/soft only — never dramatic or heavy drop shadows. |
| **Bootstrap Grid** | 12-column grid, Bootstrap 5, desktop-first (min width 1366px, target resolution 1920×1080). Mobile is a secondary, graceful-degradation target only. |

---

## 7. Bootstrap Component Mapping

| Screen | Bootstrap 5 Components |
|--------|-------------------------|
| Login Page | Card, Form (Input Group + Validation), Button, Icons (via Material Symbols, not Bootstrap Icons) |
| Administrator / Staff / Official Dashboards | Grid (Cards), Navbar/Sidebar (custom), Badge, Dropdown (profile), Offcanvas (mobile sidebar collapse), Toast (alerts) |
| Patient Records | Table, Pagination, Dropdown (filter), Input Group (search), Badge (status), Button Group (actions) |
| Register Patient | Form, Accordion (sectioned: Personal/Emergency/Medical), Button, Alert (validation errors) |
| Patient Profile | Nav Tabs/Pills, Card, Table (history logs), Breadcrumb, Button |
| Medicine Inventory | Table, Badge (stock/expiry status), Progress (stock level bar), Modal (quick edit), Pagination |
| Add/Edit Medicine | Form, Modal (if inline) or standalone page, Button, Alert (validation) |
| Appointment Scheduling | Calendar (custom component, not native Bootstrap), List Group (queue/today's schedule), Badge (status), Modal (schedule/reschedule) |
| SMS Notifications | Form (message editor), Dropdown/Checkbox group (recipients), Badge (delivery status), Table (history), Toast (send confirmation) |
| Record / Edit Consultation | Form (vitals + clinical record), Card (sectioned: patient banner / vitals / record / immunisations / follow-up), Checkbox group (EPI doses), Badge (dose status: Completed / Due Now / Upcoming / Overdue), Alert (validation) |
| Health Programs | Card, Table (programme membership), Badge, Alert (untracked notice) |
| Vaccination Campaigns | Card, Table (per-dose coverage), Chart (Chart.js donuts), Badge, Alert (untracked notice) |
| Community Reports | Card, Chart (Chart.js), Table, Button Group (export) — data-driven from `reports_analytics_context()` |
| Notifications | List Group, Badge, Nav Pills (category filter) — presentation only, no data source. The only screen still in this position. |
| Reports & Analytics | Card, Chart (via Chart.js/D3, not native Bootstrap), Table, Button Group (export), Nav Tabs (report type switch) |
| User Management | Table, Badge (status), Dropdown (role filter), Button. *(The add-user and reset-password controls are present and disabled — see §1.)* |
| Audit Logs | Table, Dropdown (filters: user/date/action), Pagination |
| Settings | Nav Tabs/Pills (sections), Form, Accordion, Button |

---

## 8. UI Development Blueprint (Checklist)

Use this checklist for every remaining screen, in order:

**Pre-build (per screen)**
- [ ] Re-read the screen's entry in `03_SCREEN_SPECIFICATIONS.md`
- [ ] Confirm which role(s) can access it (Section 2 of this document)
- [ ] Pull matching sample data from `06_DESIGN_CONTENT_LIBRARY.md`

**Build**
- [ ] Reuse sidebar exactly (swap only menu items per role)
- [ ] Reuse header exactly (no changes)
- [ ] Build main content area using only components listed in Section 5
- [ ] Apply only the values defined in Section 6 (colors, spacing, radius, type)
- [ ] Map to the Bootstrap components listed in Section 7 for that screen

**Post-build (per screen)**
- [ ] Compare against approved Login/Dashboard for visual drift
- [ ] Verify no new colors, fonts, icons, or layout patterns were introduced
- [ ] Verify realistic Filipino sample data is used (no Lorem Ipsum/John Doe)
- [ ] Confirm role-based restrictions are respected (no leaked admin-only actions)
- [ ] Flag any scope creep (features not in the approved Proposal) instead of silently adding them

**Build order (historical).** All 20 screens are built; this list is kept as the record of the order they were built in, not as remaining work:

1. Patient Records → 2. Register Patient → 3. Patient Profile → 4. Medicine Inventory → 5. Add/Edit Medicine → 6. Appointment Scheduling → 7. SMS Notifications → 8. Reports & Analytics → 9. User Management → 10. Audit Logs → 11. Settings → 12. Health Center Staff Dashboard → 13. Barangay Official Dashboard → 14. Record / Edit Consultation → 15. Health Programs → 16. Vaccination Campaigns

Community Reports and Notifications were built as UI alongside the Barangay Official Dashboard and have not been reconciled against real data. They are the outstanding work, not new screens.

**One addition to the post-build checklist, learned across the reconciliation passes:** a figure with no data source must report its own absence. Never invent one, and never leave a plausible-looking number in markup — an invented figure gets believed, and on a health record that is the expensive kind of wrong. Every screen already reconciled follows this rule; see the untracked notices listed in §5.

---

## 9. Scope Extension — Immunisation Tracking

**Immunisation tracking extends beyond the original Screen Specifications. It was added deliberately, and this section is the record of that.**

`03_SCREEN_SPECIFICATIONS.md` v1.0 mentions vaccination in three places only: a "Vaccination Records" tab on the Patient Profile, a "Vaccination Summary" table on Reports & Analytics, and a "Vaccination Campaigns" widget on the Barangay Official Dashboard. None of them specified where a dose is recorded, what schedule it is measured against, or how a child behind schedule is identified. There was no way to satisfy those three references without building the tracking underneath them.

**Why it was added.** Instructor feedback asked that infant immunisation tracking be traceable — that the system be able to show, for a named child, which doses were given, when, by whom, and which are still outstanding. "Traceable" is the operative word: a summary count cannot be traced back to a child, so a per-dose record was required.

**What was built.**

- **`EPI_SCHEDULE`**, a code constant in `models/immunizations.py`: the Department of Health Expanded Program on Immunization infant schedule — 14 scheduled doses across 8 vaccines (BCG, Hepatitis B, Pentavalent, OPV, PCV, IPV, MR, MMR), each with the age it is due and the dose number in its series.
- **The `immunizations` table**: this child's actual history — which dose, on what date, given by whom, during which consultation. `UNIQUE (patient_id, vaccine_code, dose_number)` so one dose cannot be recorded twice.
- **`get_immunization_status()`**: the single place that decides whether a dose is Completed, Due Now, Upcoming, or Overdue, resolved against the child's real birthday. The Patient Profile tab, the queue badge, the check-in message, the dashboard card, and Screen 17's coverage table all read its output; none recomputes it.
- **Capture on Screen 20**, the consultation form, for patients under 5 — because a dose is administered during a visit, which is where a health worker actually holds the syringe.

**Why the schedule is code and the doses are a table.** The EPI schedule is national policy: identical for every barangay, changed by DOH circular, and never by anything a user of this system does. There is deliberately no screen to edit it — a health worker who could redefine the national schedule from the UI could make a defaulting child look up to date. A child's doses are the opposite: a per-patient clinical fact that exists only because someone recorded it, so it is stored.

**Scope position for the defence.** This is an extension of the approved scope, not a replacement of it. It sits inside Core Objective 1 (Patient Records Management) and feeds Core Objective 4 (Automated Report Generation) — it does not add a fifth objective. Per `10_PROPOSAL_RECONCILIATION_NOTES.md` Correction 1, present the four core modules first; introduce immunisation tracking as how the vaccination references in the approved specification were actually satisfied.

**A dose recorded under a code a later schedule revision drops is not lost.** It is reported under "extra records" rather than silently disappearing, because a vaccination that happened, happened. That principle is the direct ancestor of §10.

---

## 10. Design Decision — Consultation View, Edit, and Add-Only Immunisations

**Read this before changing anything on the consultation form. Both behaviours below look like missing features and are not.**

### View and Edit are deliberately two different actions

The Consultation History tab on the Patient Profile offers **View** (an eye icon) and **Edit** (a pencil) on every consultation row. They are not duplicates:

- **View** expands a read-only panel showing the visit — vitals, complaint, diagnosis, treatment plan, notes, and any immunisation doses recorded during that visit. Nothing in it can change the record.
- **Edit** opens Screen 20 in edit mode, which writes an audit entry when saved.

The read-only panel already existed and already worked, but its only affordance was an unlabelled chevron in the first column, while the Actions column offered nothing but the pencil — so "read this visit" appeared to require opening the editable form. That is the wrong default for a clinical record: the common action is reading, and the safe action should not be the hidden one.

**The View button drives the same collapse target as the chevron.** It is not a second rendering of the record. One record, one read-only rendering, two ways in. Do not "fix" this by building View a panel of its own — a second rendering of a clinical record is a second thing to keep correct, and the two would eventually disagree about a real patient.

### The edit form is add-only for immunisation doses

**A previously recorded dose cannot be removed through Screen 20. This is intentional.**

The form once deleted every dose the consultation had recorded whose checkbox did not come back ticked. That made an absent form field mean *erase this child's vaccination record* — and a checkbox is absent from a submission for many reasons that have nothing to do with intent: a partial POST, a form rebuilt by script, a serialiser that drops unchecked inputs. A submission that never mentioned immunisations at all destroyed doses on file, leaving an audit line as the only trace.

So the behaviour now is:

- Any dose already on file renders as a **locked fact** with the date it was given, never as a checkbox — including a dose recorded by this very consultation.
- `_apply_immunization_edit()` **adds only**. It returns an empty `removed` list, always. Removal is not gated here; it is absent.
- No submission shape can delete a dose.

**Why not a confirm-and-delete control instead?** Because that leaves deletion reachable from a routine correction screen — the same screen a health worker opens to fix a typo in a treatment plan. This project already puts its genuinely destructive action (changing a patient's status) behind a dedicated modal and its own endpoint rather than inside a general edit form. Un-recording a dose given in error is rarer and more consequential than an archive, so it belongs on a deliberate correction path of its own, not as a side effect of saving a page.

**`models/immunizations.py::remove_immunizations()` is deliberately left in place and unused**, for that future path to call. It already scopes its DELETE to the consultation that recorded the dose, which is the hard part. Its being unused is not dead code to clean up — it is the groundwork for the correction path, and deleting it would mean rewriting the careful part later.

**If a future session is asked to "add the ability to delete a vaccination record":** that is a real gap, but it is a new deliberate correction path with its own route, its own confirmation, and its own audit entry. It is not a change to Screen 20's edit form.

---

## 11. Design Decision — Why the Administrator Has No Health Programs or Vaccination Campaigns Screen

**This is a deliberate access-control decision, not an unimplemented feature. Do not "fix" it by adding Admin routes to Screens 16 and 17.**

### The question

The Project Bible (`01_PROJECT_BIBLE.md`, "Target Users") lists "Full system access" as the Administrator's first responsibility. Yet Health Programs (Screen 16) and Vaccination Campaigns (Screen 17) are reachable only at `/official/health-programs` and `/official/vaccination-campaigns`, both guarded by `@role_required("Barangay Official")`. An Administrator who navigates there is bounced. Is that a contradiction, or a gap in the build?

### The resolution: it is intentional

Access in this system is scoped to **role function**, not to administrative rank. Screens 16 and 17 exist to serve the Barangay Official's civic and community-outreach function — monitoring public health activity in the barangay. They are not general administrative tools, and the Administrator's job function does not include running barangay outreach.

Critically, **no data is hidden from the Administrator by this scoping.** What is role-scoped is a *presentation*, not a record:

- **Programme memberships are literally the same object.** `health_programs_context()` calls `reports_analytics_context()` and reads its `programs` key — the identical pair (Immunization, Senior Citizen) that Reports & Analytics prints. The two screens cannot report different memberships, because there is only one list.
- **Immunisation coverage comes from one function.** Both Screen 17 and Reports & Analytics print `models.immunizations.get_immunization_coverage()`. Same call, same figures.
- **One aggregate is genuinely only on Screen 17**, and it should be stated rather than glossed: the per-dose DOH EPI schedule table from `get_dose_coverage()`. Reports & Analytics does not render it.
- **But its underlying records are more visible to the Administrator, not less.** Every dose behind that table is readable per-patient on the Patient Profile immunisation panel — a screen the Barangay Official cannot open at all, because they hold no patient-record access. At record level the Administrator's visibility is a strict superset of the Barangay Official's. What differs is one aggregated civic view, not the clinical data underneath it.

So "the Administrator cannot see this data" is not true. "The Administrator does not get the Barangay Official's outreach dashboard" is true, and is the intent.

### The standard this follows

**Least privilege (general enterprise RBAC).** Access is granted by the duties a role actually performs, not by seniority. Granting a screen simply because its holder outranks the intended user is the textbook violation — it widens the blast radius of a compromised account with no functional gain. Cf. NIST SP 800-53 AC-6 (Least Privilege) and the role-based access control model in NIST SP 800-162.

**HIPAA Minimum Necessary Standard (healthcare-specific).** 45 CFR §164.502(b) and §164.514(d) require a covered entity to limit access to protected health information to the minimum necessary for the purpose. §164.514(d)(2)(i) is explicit about the mechanism: the entity must **identify the persons or classes of persons in its workforce who need access to PHI to carry out their duties, and the category of PHI needed for each**. That is a job-function test, not a rank test. A blanket "administrators get everything" default is a widely-noted compliance weakness in HHS guidance and industry practice precisely because it substitutes seniority for the required duty analysis.

**The treatment exception does not rescue the opposite argument.** §164.502(b)(2)(i) exempts disclosures to, and requests by, a health care provider **for treatment** from the minimum necessary requirement — a clinician treating a patient is not to be throttled. That exception is inapplicable here: Screens 16 and 17 are administrative and reporting surfaces reporting aggregate community statistics, not direct patient-treatment access. Nothing on either screen is consulted to treat a patient. The clinical screens that *are* used in treatment — Patient Records, Patient Profile, Record Consultation — are open to the Administrator and to Health Center Staff, which is where that exception properly applies and where this system already applies it.

### Reconciling this with "Full system access" in the Project Bible

"Full system access" in `01_PROJECT_BIBLE.md` should be read as it is read in real EHR and enterprise systems, and as this build implements it:

1. **Full oversight and data visibility** — the Administrator can see the state of the whole system, achieved through Reports & Analytics, both dashboards, and Audit Logs. No figure in the system is invisible to them.
2. **Full access to every screen within the Administrator's own operational scope** — clinical records, inventory, scheduling, user management, settings and the audit trail. There is no screen in that scope an Administrator is refused.
3. **Not** literal reachability of every role-specific URL regardless of function. No production EHR grants the system administrator the community-health-worker's outreach console on the strength of the job title; it grants oversight of the data that console reports on.

Read that way there is no contradiction. The Administrator has full oversight *of* barangay programme and immunisation activity — via Reports & Analytics — without holding the Barangay Official's screens. Rank confers oversight; function confers the screen.

### If a future session is asked to "give Admin access to Health Programs"

Treat it as an access-control change requiring an approved revision of this document, not a routing fix. The technical change is trivial — two blueprint routes and two context-map entries. The reason not to make it is recorded above, and the correct answer to "the Administrator wants to see programme figures" is that they already can, on Screen 10.

---

## 12. Design Decision — Medicine Inventory's Row Actions

**Read this before adding a control back to a Medicine Inventory row.** Two of the four actions
that row once offered were resolved in opposite directions, because the reasons behind them said
opposite things.

### Archive reuses Patient Records' status pattern exactly

Archiving a stock item is a status change, and this project already had a proven shape for one, so
Screen 06 borrowed it rather than inventing a second:

- A confirmation dialog that names the item and its current status, and offers **only** the
  transitions that status permits. The rule lives in
  `models/inventory.py::allowed_item_status_transitions()` and is mirrored in the dialog's script
  only because the choice has to be made in the browser.
- The server re-derives the legal moves from the **stored** status before writing, never from what
  the page posted — the dialog decided what to offer from a page that may since have gone stale,
  and a POST can arrive without the page ever having been opened.
- **Both directions.** Active → Inactive retires an item; Inactive → Active puts it back. A
  one-way door turns a mis-click into something only the edit form can undo, which is the same
  argument `models/patients.py::allowed_status_transitions()` makes for reactivating a patient.

Nothing about "retired" is re-implemented. `set_item_status()` writes the same status column the
Add/Edit Medicine form already writes, so `RETIRED_STATUS` keeps one meaning and every figure that
already respected it — the four stat cards, the low-stock alert, both dashboards, the sidebar
badge and Reports & Analytics — respects a retirement made this way the moment it commits, with
none of them touched. Retiring is an UPDATE of one flag: no row is removed, and the stock figure,
batch number, expiry date and identifiers are unchanged, which is why marking it Active again
restores it everywhere.

### Print was removed, and removal was the finished outcome

The per-row print icon is gone. It is not disabled and it is not pending.

`utils/unavailable.py` carried a reason for it — a stock item has no page of its own, Edit is a
form rather than a record, and a printed copy of one table row is not a document anybody keeps —
and that reason stayed **true to the last line**. Read back, it is not a note about something
unfinished; it is the argument that the control should not exist. Patient Records keeps its print
icon for the opposite reason: a patient's record *is* a page, so printing it means printing that
page. The inventory document a reader actually wants is Export PDF in the toolbar, which is built.

This is a third outcome that the project's disabled-control rule leaves implicit. A control either
works, or it is visibly disabled and says why — **or it should not be on the screen at all, in
which case it is removed and its reason is deleted with it.**

---

## 13. Design Decision — One Booking Control, and a Way Back Into a Consultation

### Appointment Scheduling has exactly one New Appointment control

It had five, all opening the same dialog: the calendar header, the queue toolbar, the queue empty
state, the upcoming toolbar and the upcoming empty state. Five identical primary buttons is five
competing primary actions, which is the same as none.

The survivor is in the **queue toolbar, beside Check In Patient**, because that pairing is the
decision a desk actually makes: Check In is for somebody standing there now, New Appointment
commits to a day that has not come yet. It is deliberately styled as the *secondary* button of
that pair — Check In Patient remains the screen's single primary action, and promoting both would
recreate the problem the consolidation solved.

**The empty-state prose was rewritten, not just stripped of its buttons.** Deleting a control and
keeping the sentence that names it is the worse half of the change on its own: a reader told to
"book one with New Appointment" hunts a panel for a control that is not in it. The two affected
empty states now report state and say what fills it, in the passive shape used elsewhere in this
project ("Nothing has been recorded for this patient. Diagnoses entered during consultations will
appear here."). The queue's empty state still names Check In Patient, and that is not the same
thing — that button is directly above it. **Naming a control the reader is standing next to is
help; naming one they must go and find is not.**

The dialog is titled **"Schedule Appointment"**, not "New Appointment" and not "Book Appointment".
Its submit button already reads Book Appointment, and more importantly that submit is not always
Book: choosing the new-patient mode switches it to "Continue to Registration", because the dialog
can hand off to Register Patient on the way to a booking. A title has to cover both modes.
"Schedule" also matches the screen's own name and the Verb + Noun shape every other dialog here
uses.

### The dashboards offer a way back into a consultation, not a second way to start one

**A separate sidebar module for Consultation was considered and rejected.** Appointment Scheduling
→ Start Consultation → Record Consultation is the standard arrangement — the visit belongs to the
appointment, so the appointment is where it begins — and a standalone Consultation destination is
incoherent anyway, because a consultation only exists tied to one active patient.

What was genuinely missing is the **return trip**: a clinician who navigated away mid-visit had to
reload the queue and find the row again with the patient sitting in front of them. So both
dashboards carry a panel that names whoever is currently In Consultation and links straight to
that appointment's write-up form.

Three properties keep it a shortcut rather than a second entry point:

- It reads `get_active_consultation()` — the same call Appointment Scheduling uses to decide who
  may start a consultation, and deliberately not scoped to today — so the dashboard and the queue
  can never disagree about whether the room is occupied.
- It can only ever name a visit the queue has **already** started. It cannot begin one, and it
  cannot bypass the one-at-a-time rule.
- It contains no form and posts nothing.

Idle, it states "No active consultation right now" and points at Appointment Scheduling rather
than vanishing — the honesty pattern the rest of the dashboard already follows. A panel that
silently disappears teaches a reader that the screen is inconsistent, not that the room is empty.

---

## 14. Design Decision — The Three Header Elements, Answered Three Different Ways

The header carried a search box, a status pill and a notification bell on all 21 screens for all
three roles, and none of the three did anything. They were raised together, and the useful part of
the finding is that they were **not the same kind of problem** — one was an unbuilt feature worth
building, one was a false claim, and one was a control whose destination existed for exactly one
role. Three defects, three different correct answers.

### The search box was an unbuilt feature, so it was built

It was a `<div>` containing the words "Search patient name or ID..." — not an `<input>`, inside no
`<form>`, wired to nothing. But finding a patient quickly from wherever you happen to be is a real
need in a clinic, and Patient Records had already solved the matching half of it: a lower-cased
substring test against patient ID, full name, contact number and address, with the matchable text
written into each row's `data-search` by the server.

So the header does not search. It **submits**, and the screen that already knows how to match does
the matching:

```
header form  ──GET ?search=term──▶  /…/patient_records  ──▶  value="term" in #patientSearch
                                                        ──▶  applyFilters() on load
```

One rule, in one place. The count line, the empty state and Print List's "filtered by" note all
follow from that single pass, because they always did. Nothing on the server filters the roster:
the screen renders every registered patient and narrows them in the browser, which gives the same
answer a re-query would because there is no unseen page a match could hide on. Filtering
server-side *as well* would mean two matching rules for one box, and the day they disagreed the
screen would be showing a count it could not justify. The exports are untouched and still download
the whole register, exactly as their titles and cover sheets already say.

**The Barangay Official gets no search box at all.** §2 keeps that role out of patient data
entirely, so `patient_records_endpoint` is absent for it in `inject_role_context()` and the header
renders nothing there. This is worth stating precisely: it is not a control hidden from a role that
could still reach the data by typing a URL — the guards refuse `/admin/patient_records` and
`/staff/patient_records` for that role independently. It is a control with no destination to be
given.

### The pill was a false claim, so it now states something checkable

"Synced just now" was static text. Nothing in this application syncs — there is one SQLite file, no
background job, no second store and nothing to reconcile against — so the pill was asserting a
state the system has no mechanism to be in, and asserting the most reassuring version of it.

The honest replacement is the thing it was faking: how current what you are looking at is. Every
screen is built from the database at request time and no figure on it moves afterwards (responses
are sent `no-store` for that reason), so the pill prints the moment the page was rendered —
"Loaded 4:34 PM" — from `utils.dates.now()`, the one source of "now" in the application and the
same clock the dates on the screen come from. Its tooltip says outright that nothing updates until
you reload and that there is no background sync.

Reload it and the time changes. That is the whole point: the old pill asked to be believed, and
this one can be checked.

### The bell had a destination for one role, and none for the other two

This is the element the investigation actually turned on, and it corrected an assumption worth
recording.

**The Barangay Official's Notifications screen is real and reachable, but it is not a working
inbox.** It renders at `/official/notifications`, it is in that role's sidebar, and it returns 200
— and its entire content is a statement that this system stores no notifications, with the two
things it *can* point at (SMS Notifications, Vaccination Campaigns) linked from it. That is a
legitimate screen under this project's rules and it stays. It is simply not a source of alerts, and
anything wired to it must not imply that it is.

So:

- **Barangay Official** — the bell links to that screen. It is a real destination this role already
  holds, and the bell is a second door onto a sidebar item, which is what a header bell normally is.
  Its tooltip states that the system stores no notifications, so the control does not promise more
  than the page behind it delivers, and it takes an `active` state on the screen it points at like
  every other navigation control here.
- **Administrator and Health Center Staff** — no bell. Neither role has a Notifications screen at
  any URL, and both are refused `/official/notifications` by its guard. There is no destination, so
  there is nothing for a disabled-with-a-reason control to explain the absence of; the honest
  outcome is that the element is not there. This is the third case
  `utils/unavailable.py` already documents: *a control that should not be on the screen is removed,
  and its reason goes with it.*
- **The red dot is gone for every role.** There is no notifications table and nothing writes one, so
  there was never a count behind it. It was removed rather than set to zero, for the reason the
  sidebar's hard-coded "5" badge was removed: a zero badge reads as an alert that is not there.

### Why this does not violate "the header is never redesigned"

§4's rule is that the header is never redesigned **per screen**, and it is not: every screen a role
can reach shows that role the same header. What varies is per **role** — which is the axis §2
already scopes the sidebar on, and for the same reason. A role that cannot open Patient Records has
no use for a box that only leads there, and a role with no Notifications screen has nowhere for a
bell to go.

---

## 15. Design Decision — Sort Is Built on Two Screens and Refused on a Third

Three screens carried a Sort button and all three were disabled behind one shared reason. Two of
them now sort for real. The third still does not, and the interesting half of this decision is why
that is not an unfinished job.

### What each screen sorts by, and why those columns

| Screen | Sortable | Not offered, and why |
|---|---|---|
| **Patient Records** | Name (A–Z, default), Age, Last Visit, Status | *Address* is one free-text field with no purok in it, so an order over it groups nothing. *Contact Number* has no order anybody reads a roster in. *Patient ID* is assigned in registration order, so "sort by Patient ID" is "sort by when they registered" under a misleading label — Last Visit answers the question actually being asked. *Gender* has three values and is a filter, not an order. |
| **Medicine Inventory** | Medicine Name (A–Z, default), Current Stock, Expiration Date, Status | *Category* and *Supplier* are what Advanced Filter narrows by. *Reorder Level* on its own sorts by how large each item's threshold happens to be, which says nothing about the shelf; the question behind it is "what is running out", and Status answers that properly because `stock_status()` has already weighed each item's stock against its own reorder level. |

Every column offered is one the table already shows, and every one is compared on a value the
server wrote into the row as a `data-*` attribute — the arrangement the filters on these screens
already use. The browser derives nothing and re-formats nothing.

Two of those keys are worth naming because the obvious choice would have been wrong:

- **Age** sorts on `age_years`, the number, not on the Age column's text. That text reads
  "2 months, 23 days" for an infant, and comparing it would file a two-month-old between a
  two-year-old and a three-year-old. (The Advanced Filter's age bounds had this defect already and
  were reading the display string; they now read the same number the sort does.)
- **Status** sorts on a declared rank, not alphabetically. Patients use `PATIENT_STATUSES` order —
  Active, Inactive, Deceased — because alphabetical would read Active, Deceased, Inactive and put
  the most final of the three in the middle. Medicine uses `STATUS_SORT_ORDER`, which is
  `stock_status()`'s own urgency ladder, so "sort by status" groups the shelf the same way the badge
  already decides what to call each item.

### Sorting and filtering never touch each other

Sort reorders rows. Search and filter decide which rows are visible. Neither reads the other's
state, which is what makes them compose: sorting a filtered list keeps the filter, and filtering a
sorted list keeps the sort. Hidden rows are reordered too, so clearing a filter afterwards reveals
the rest already in the same order — which is what "the list is sorted by name" ought to mean.

Blanks sort last in **both** directions, deliberately. A patient with no recorded visit and a
medicine with no expiry date are absences, not extreme values: "soonest expiry first" must not open
on a page of items that have no expiry at all, and reversing must not then bury them.

### One comparator, two screens

`static/js/table-sort.js` is the whole sorting rule and both screens load it; each supplies only its
own column list. Two hand-written copies of a comparator is two chances for one screen to sort
blanks to the top while the other sorts them to the bottom, and nobody would notice until somebody
compared the two screens. This is the argument `utils/unavailable.py` makes for its shared reasons,
applied to behaviour.

Medicine Inventory needs one thing Patient Records does not, and it is the part that broke first
when this was built: a record there is **two** rows, an item row followed by its own read-only
detail row. The sorter takes a `companion` for that, and resolves every companion *before* moving
any row — `appendChild()` relocates rather than copies, so asking "what follows this row?" halfway
through a rebuild returns the neighbouring record's panel. Every detail row would end up under the
wrong medicine.

### Why Appointment Scheduling still refuses

Its queue is already ordered by an answer: whoever is in consultation now, then whoever is waiting,
then the not-yet-arrived, then everything resolved, ties broken by arrival time (`_STATUS_RANK` in
`models/appointments.py`). That order tells the desk who may be brought in next. Re-sorting it by
name or by booked time would throw that away while still looking like a working queue.

So the shared `sort` reason was **narrowed rather than deleted** — the arc `utils/unavailable.py`
documents for `export`, happening again. It stopped describing an unbuilt feature and started
describing a screen, and it now names the two screens where sorting *is* built, because a reader who
has just used Sort on Patient Records and then finds it disabled here is owed the difference between
the two screens rather than a blanket claim they can already disprove.

A roster and a shelf have no inherent order and several are useful. A queue has exactly one.

### The order in force is never a fixed sentence again

Both screens used to end with hard-coded words — "Sorted by surname, A–Z", "Sorted by medicine
name, A–Z" — which were true only because nothing could change the order. They are now written from
the same state the Sort button and the menu read, so all three change together or not at all. That
line was the first thing that would have gone false the moment this feature shipped.

---

## 16. Design Decision — Deactivation Now Holds on Every Request, and Costs Less Than It Did

`users.is_active` was consulted exactly once in an account's life: at the login form. An account
deactivated while its holder was signed in kept working until they chose to log out, which could be
days. `routes/auth.py` named this gap in its own module note and said closing it "would mean a
lookup on every guarded request rather than a change to this file". That is where the fix went.

### What a guarded request asks now

All 75 `@role_required` routes and the one `@login_required`-only route (`/dashboard`) run the same
three questions through one function, `_signed_in_account()` in `utils/security.py`:

| # | Question | Failure |
|---|---|---|
| 1 | Is there a session at all? | redirect to `/login` — unchanged, the anonymous case |
| 2 | Does the account still exist? | clear the session, refuse; no audit row, because there is no account to attribute one to |
| 3 | Is the account still active? | clear the session, refuse, **and** write an audit entry |

One function rather than a check in each decorator, so `login_required` and `role_required` cannot
come to disagree about what a valid session is — which they would, the first time one of them was
edited. Note that `login_required` previously asked only question 1 and never read the account at
all; it now asks all three.

The revocation takes effect on the holder's **next guarded request**. There is no push, and a
browser already showing a rendered page has already been sent it. The window is one click long, and
that is now the whole of the remaining boundary.

### Why this is cheaper than what it replaced

The obvious worry about a per-request account check is the query it adds to 76 routes. It adds none.
It removes one. Measured on this database, with the pre-change code run from a git worktree:

| | account lookups per request | database work |
|---|---|---|
| before (no check at all) | **2** | baseline |
| the naive way to add the check | **3** | one cycle more |
| what was built | **1** | one cycle *less* |

Two lookups were already happening, from two places that did not know about each other:
`role_required()` read the account row, and then `inject_role_context()` read the same row again on
every render. `database.connection.get_db()` opens a **new** SQLite connection per call and closes
it after, so those were two full connect / query / close cycles. Measured over 9 rounds of 400
calls, one cycle costs **~0.54–0.64 ms** on this database against **~0.027 ms** for the `SELECT`
alone on an open connection — so about 95% of a lookup is the connection, not the read.

The saving is therefore about half a millisecond of database work per authenticated request. That
is deliberately stated as *the lookup removed* rather than as a faster page: end-to-end request
timing on a laptop is dominated by noise, and repeated runs of the same nine screens disagreed by
tens of milliseconds in **both** directions. The lookup count is exact and reproducible; the wall
clock is not, so no claim is made from it.

`get_current_user()` now caches the row on `flask.g` for the life of the request. The three call
sites collapse to one lookup, and the `is_active` test reads a column on a row the request had
already fetched — it issues no query of its own and can issue none.

The lookup itself was never the expensive part: the `users` table holds three rows and the plan is
`SEARCH users USING INTEGER PRIMARY KEY (rowid=?)`, a primary-key hit rather than a scan.

Caching on `g` and not for longer is deliberate. A cache outliving the request would need an
invalidation rule when an account changes, and getting that wrong is precisely how a deactivation
check comes to pass a stale row — the defect this change exists to close. One request, one read, no
invalidation rule to get wrong.

### The refusal reveals nothing, by construction rather than by copying

`routes/auth.py`'s comment on its one refusal response said a fourth outcome added later "gets the
identical response by construction rather than by remembering to". This is that fourth outcome, so
the function moved to `utils/security.py` — which routes import, not the reverse — and both callers
now return the same response because they call the same function.

So a revoked session sees exactly what a wrong password sees: *"Invalid security credentials."* and
a redirect to `/login`. There is still nowhere in the application that says an account has been
deactivated. At the login form that wording would be an account-enumeration oracle; here it would be
the same sentence reachable by anyone holding a stolen session cookie. The distinction lives in the
audit trail, where only a signed-in Admin can read it.

### Its audit entry is a fourth phrase, and is deliberately outside the refusal count

`ACTION_SESSION_REVOKED` — "Ended session on deactivated account" — is its own phrase rather than a
reuse of `ACTION_LOGIN_BLOCKED`. Folding them together is the tempting shortcut, and it would make
the trail lie in a way nobody would catch by reading it: "Blocked sign-in" says a credential was
presented at the form and refused, whereas here nothing was presented — somebody was already inside
and the door closed behind them. An administrator asking "who is still trying to use the account I
switched off" would read the second as the first.

It is **not** added to `REFUSAL_ACTIONS`. That tuple feeds two visible figures whose labels say what
they count: Audit Logs' Security Events card is titled "Sign-ins refused against an account that
exists", and Settings labels the number "Refused sign-in attempts". A revoked session is not a
sign-in attempt, and adding it would leave two labels describing a total that no longer matches
them. The entry is still written under `MODULE_AUTH`, so it appears in the trail and under the
screen's Authentication filter; it is only kept out of a total whose name would stop being true. If
these are ever worth counting, the honest change is a card of their own.

### One entry per revocation, not one per click

Worth stating because a per-request check is exactly the shape of thing that fills a table. It does
not, and the reason is structural rather than a rate limit: the session is cleared in the same
breath as the entry is written, so the request after it carries no `user_id`, fails question 1, and
never reaches the logging path. A revoked holder writes one row and then looks like an anonymous
visitor. This was verified live rather than reasoned about — see the commit.

---

## 17. Correction — The Health Center's Location Was Wrong, and Was Invented Here

Every location string in this project said **San Francisco, Agusan del Sur**. The health center is
in **Barangay Poblacion, San Francisco (formerly Anao-Aon), Surigao del Norte** — a different
municipality in a different province, about 12 km from Surigao City, ZIP 8401, area code 086.

This is recorded here rather than quietly fixed because the interesting part is not the wrong value.
It is that the wrong value had no source, and the system's own structure then spread it into real
patient records.

### Where it came from: a placeholder nobody resolved

`06_DESIGN_CONTENT_LIBRARY.md` §Project Location listed Province and Municipality as
"(Use the province stated in the approved capstone proposal.)" — a deferral to a document that
cannot answer it. The full text of `Capstone_Proposal.pdf` was extracted, all 34 pages: it names
no municipality and no province anywhere, and its only geographic string is "Surigao City" on the
title page, as the college's address.

So the governance layer said "look it up", the document it pointed at was silent, and somebody
filled the gap with a plausible guess. There is a real San Francisco in Agusan del Sur; it is simply
not this one. Nothing in `01`–`10` ever stated the wrong value — the audit found zero occurrences of
"Agusan" in any governance document. It was invented in `models/patients.py` and spread outward from
there. `utils/dates.py` then cited `01_PROJECT_BIBLE.md` as its authority for the wrong location,
which the Bible had never said.

### How it surfaced: through use, not review

Nobody caught it by reading the code. It surfaced when real patients were registered.

`MUNICIPALITIES` and `PROVINCES` in `models/patients.py` are a **closed list** —
`validate_patient_form()` rejects anything not in them, which is normally the right design and is
why the form and the validator cannot drift apart. But the list on offer was
`("Agusan del Sur", "Surigao del Sur", "Davao de Oro")`. Whoever registered these patients reached
for "Surigao", found only *del Sur*, and took it. Seven real records ended up on the wrong side of a
province boundary, and those seven are the clearest evidence in the whole database of what was
actually meant. Two more were filed under "Bunawan", an Agusan del Sur municipality nowhere near
here, for the same reason: no correct answer was offered.

The lesson worth keeping is about closed lists. They are the right pattern, and this project should
keep using them — but a closed list is an assertion about the world, and a wrong one does not fail
loudly. It quietly records the nearest wrong answer and looks like clean data forever after.

### How it was corrected

Two commits, both structural-first so that no correction could orphan the data it was correcting.

**`14452ce`** — the core. `MUNICIPALITIES` became San Francisco plus the three LGUs it shares a land
border with (Surigao City, Malimono, Sison); `PROVINCES` became Surigao del Norte, keeping Surigao
del Sur because it genuinely adjoins and dropping Agusan del Sur and Davao de Oro, which border
neither. The ZIP example moved 8501 → 8401 and Settings' area code 085 → 086. Correcting the lists
alone would have orphaned the eleven stored records holding the old values — their Edit form would
have rendered a blank province and refused to save — so `migrate_correct_patient_location.py`
repaired all eleven in the same change. The fifteen patients with no municipality or province were
deliberately left alone: NULL is incomplete, not wrong, and inventing an address for them would have
been fabricating clinical data.

**`5050bf8`** — the leftovers. Settings' Province, Complete Address and Institution;
`populate_records.py`'s infant seed and three inventory supplier strings, plus
`migrate_correct_supplier_location.py` for the three live rows a reseed would not have touched
(`INSERT OR IGNORE`); and the login page's "San Francisco, Philippines", which was ambiguous against
the American city rather than wrong.

Both migrations follow the pattern already established in this project: idempotent, before and after
spelled out per row so the change is reviewable in the commit without running anything, and a
refusal to touch a row matching neither state. Both were run against a labelled backup of `app.db`
taken first and verified by a full-database diff afterwards — 21 intended cells in the first, 3 in
the second, and nothing else in any table moved. No `audit_logs` row was written for either:
`log_action()` refuses entries it cannot attribute, and a migration has no author to name.

### What is true now

Barangay Poblacion, San Francisco (formerly Anao-Aon), Surigao del Norte. ZIP 8401. Area code 086.
Surigao City ~12 km east. The municipality has eleven barangays and exactly one Poblacion — not
numbered barangays.

`06_DESIGN_CONTENT_LIBRARY.md` §Project Location now **states** these outright instead of deferring,
and says why. That is the actual fix. Every other change in these two commits was cleanup; the
placeholder was the defect.

---

End of UI Architecture Document

Status: Approved

This document is now the official UI Architecture for the IDS-BPHCSN Capstone Project.

All future UI design, frontend development, and interface revisions must conform to this architecture unless an approved revision of this document is created.
