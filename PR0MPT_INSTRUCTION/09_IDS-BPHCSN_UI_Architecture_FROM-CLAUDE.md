# IDS-BPHCSN UI ARCHITECTURE DOCUMENT

Version: 2.0
Status: Approved. Sections 1, 2, 3, 5, 7 and 8 reconciled against the built system on 2026-08-15 and re-checked on 2026-08-21; section 10 added. Sections 11, 12 and 13 added 2026-08-21.
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

**The system has 20 screens.** Screens 1–15 were the original inventory; screens 16–20 were built afterwards and are added here in Version 2.0.

`templates/` holds 23 `.html` files, of which three are not screens: `base.html` is the shared layout — sidebar, header, content region — and `_print.html` and `_chart_table.html` are partials included by the screens that print and the screens that render a chart's underlying figures as a table. The other 20 files are the 20 screens below, one file each.

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
| 11 | User Management | `user_management.html` | Administrator only | List every account that can sign in, with the screens each role's guards admit it to. Account writes are not implemented — an open scope decision. |
| 12 | Audit Logs | `audit_logs.html` | Administrator only | Monitor and filter recorded system activity by user, date, and action. |
| 13 | Settings | `settings.html` | Administrator only | Configuration screen. Nothing typed here is stored — the `settings` table is empty and no route writes it, so every input sits in a disabled fieldset. One block is live: the Security pane reports sign-in counts read from the audit trail. |
| 14 | Health Center Staff Dashboard | `staff_dashboard.html` | Health Center Staff | Operational overview scoped to staff duties — no admin modules. |
| 15 | Barangay Official Dashboard | `official_dashboard.html` | Barangay Official | Community-facing overview — no patient, inventory, or user data. |
| 16 | Health Programs | `health_programs.html` | Barangay Official | Programme membership, derived from patient records. Programmes with no source in the schema report their own absence. |
| 17 | Vaccination Campaigns | `vaccination_campaigns.html` | Barangay Official | Immunisation coverage against the DOH EPI schedule. The reporting unit is the scheduled dose, not a named campaign. |
| 18 | Community Reports | `community_reports.html` | Barangay Official | Community-level health summary, built from `reports_analytics_context()` so it cannot report the barangay differently from Screen 10. Exports a real spreadsheet and PDF. |
| 19 | Notifications | `notifications.html` | Barangay Official | Notification centre. Presentation only — there is no notifications table. |
| 20 | Record / Edit Consultation | `record_consultation.html` | Administrator, Health Center Staff | Write up the clinical record of a visit, and edit one already recorded. Two modes of one template and one context builder. See §10. |

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

Three screens are reachable but never appear in a sidebar, because they are always entered from another screen with a subject already chosen: **Patient Profile** (from Patient Records), **Add/Edit Medicine** (from Medicine Inventory), and **Record / Edit Consultation** (from the queue, or from a patient's Consultation History).

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
- **Accessible screens (14 of 20):** Login, Administrator Dashboard, Patient Records, Register Patient, Patient Profile, Medicine Inventory, Add/Edit Medicine, Appointment Scheduling, Record / Edit Consultation, SMS Notifications, Reports & Analytics, User Management, Audit Logs, Settings.
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
- **Accessible screens (10 of 20):** Login, Health Center Staff Dashboard, Patient Records, Register Patient, Patient Profile, Medicine Inventory, Add/Edit Medicine, Appointment Scheduling, Record / Edit Consultation, SMS Notifications.
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
- **Accessible screens (8 of 20):** Login, Barangay Official Dashboard, SMS Notifications, Health Programs, Vaccination Campaigns, Community Reports, Reports & Analytics, Notifications.
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
| **Header** | 80px fixed height, white background | **Identical across all screens.** Contains: search bar, sync status, notification bell, user avatar + role label + dropdown. Never redesigned per screen. |
| **Main Content Area** | Fluid, Bootstrap 12-column grid, `#F5F7FA` background | **The only region that changes.** Houses the screen-specific cards, tables, forms, and charts defined in the Screen Specifications. |
| **Footer** | No persistent footer bar observed in approved UI; system status/version info is anchored at the bottom of the sidebar instead (e.g., "System Online," version number) | Retain this sidebar-footer pattern — do not introduce a separate horizontal page footer, to stay consistent with the approved Dashboard. |

**Rule:** If a new screen appears to require a layout change to sidebar or header, that is a signal to stop and flag it — per the Design System, these two regions must never be redesigned.

---

## 5. Shared UI Components

| Component | Reused In |
|-----------|-----------|
| **Dashboard/Overview Cards** (white, 16px radius, soft shadow, 24px padding) | All three dashboards, Reports summary tiles |
| **Data Table** (rounded, white, soft shadow, alternating row hover, status badges, action buttons, search/filter/sort/pagination) | Patient Records, Medicine Inventory, Appointment Scheduling, User Management, Audit Logs, Reports (tabular sections) |
| **Search Bar** | Header (global patient/ID search), Patient Records, Medicine Inventory tables |
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
| **Table Style** | Rounded (16px), white, soft shadow, alternating row hover, status badges in dedicated column, action icons in dedicated column, search/filter/sort/pagination present on every data table. |
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

End of UI Architecture Document

Status: Approved

This document is now the official UI Architecture for the IDS-BPHCSN Capstone Project.

All future UI design, frontend development, and interface revisions must conform to this architecture unless an approved revision of this document is created.
