# IDS-BPHCSN UI ARCHITECTURE DOCUMENT

Version: 1.0
Status: Approved
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

Screens are listed in development order, matching `08_PROJECT_ROADMAP.md`.

| # | Screen | Primary Role(s) | Purpose |
|---|--------|------------------|---------|
| 1 | Login Page | All roles | Authenticate users and route them to the correct role-based dashboard. ✅ Approved |
| 2 | Administrator Dashboard | Administrator | Give the administrator a full operational overview: patient, appointment, inventory, and SMS stats plus recent activity. ✅ Approved |
| 3 | Patient Records | Administrator, Health Center Staff | Browse, search, filter, and manage all registered patients. |
| 4 | Register Patient | Administrator, Health Center Staff | Capture new patient personal, emergency contact, and medical information. |
| 5 | Patient Profile | Administrator, Health Center Staff | Display a single patient's full record across tabs (personal info, medical/consultation/medicine/vaccination/appointment history). |
| 6 | Medicine Inventory | Administrator, Health Center Staff | Track medicine stock, expiration, and low-stock/near-expiry status. |
| 7 | Add/Edit Medicine | Administrator, Health Center Staff | Create or update a medicine record's details and stock. |
| 8 | Appointment Scheduling | Administrator, Health Center Staff | Manage the appointment calendar, walk-in queue, and today's schedule. |
| 9 | Community Notifications | Administrator, Barangay Official | Compose, send, and track SMS/web announcements to residents. |
| 10 | Reports & Analytics | Administrator, Barangay Official (view-only) | Generate and export consultation, inventory, registration, and vaccination reports. |
| 11 | User Management | Administrator only | Manage system user accounts, roles, and status. |
| 12 | Audit Logs | Administrator only | Monitor and filter all system activity by user, date, and action. |
| 13 | Settings | Administrator only | Configure health center info, SMS gateway, backup/restore, and security. |
| 14 | Health Center Staff Dashboard | Health Center Staff | Operational overview scoped to staff duties (patients, appointments, medicine requests) — no admin modules. |
| 15 | Barangay Official Dashboard | Barangay Official | Community-facing overview: announcements, community reports, vaccination campaigns — no patient/inventory/user data. |

---

## 2. Navigation Structure

### Administrator

**Sidebar Menu Structure** (matches approved Admin Dashboard mockup, extended per Project Bible):

```
MAIN MENU
├── Dashboard
├── Patient Records
├── Medicine Inventory
├── Appointment Scheduling
├── SMS / Community Notifications
└── Reports & Analytics

ADMINISTRATION
├── User Management
├── Audit Logs
└── Settings
```

- **Navigation hierarchy:** Two sidebar groups — "Main Menu" (operational) and "Administration" (governance) — exactly as shown in the approved dashboard.
- **Accessible screens:** All 15 screens.
- **Restricted screens:** None.

### Health Center Staff

**Sidebar Menu Structure:**

```
MAIN MENU
├── Dashboard
├── Patient Records
├── Appointments
├── Medicine Inventory
└── Notifications
```

- **Navigation hierarchy:** Single group, operational only — no "Administration" section rendered at all for this role.
- **Accessible screens:** Health Center Staff Dashboard, Patient Records, Register Patient, Patient Profile, Medicine Inventory, Add/Edit Medicine, Appointment Scheduling, Community Notifications (send/view only, not necessarily full broadcast history depending on future rule confirmation).
- **Restricted screens:** User Management, Audit Logs, Settings, Reports & Analytics (full version — Screen Spec 14 does not list Reports as a staff widget).

### Barangay Official

**Sidebar Menu Structure:**

```
MAIN MENU
├── Dashboard
├── Community Reports
├── Announcements
└── Notifications
```

- **Navigation hierarchy:** Single group, read/community-facing only.
- **Accessible screens:** Barangay Official Dashboard, Reports & Analytics (read-only view — community/statistical reports only), Community Notifications (view + post announcements per Project Bible responsibilities).
- **Restricted screens:** Patient Records, Patient Profile, Register Patient, Medicine Inventory, Add/Edit Medicine, Appointment Scheduling, User Management, Audit Logs, Settings — explicitly listed as "No access to" in Screen Spec 15.

---

## 3. User Flow

### Administrator Flow

```
Login
 → Administrator Dashboard
   → Patient Records → Patient Profile → (Edit / Print / Back)
   → Register Patient → (Save → back to Patient Records)
   → Medicine Inventory → Add/Edit Medicine → (Save → back to Inventory)
   → Appointment Scheduling → (Schedule / Reschedule / Cancel / Complete)
   → Community Notifications → (Compose → Send/Schedule/Save Draft → History)
   → Reports & Analytics → (Generate → Export PDF/Excel)
   → User Management → (Add/Reset/Disable/Enable/Delete User)
   → Audit Logs → (Filter by user/date/action)
   → Settings → (Update → Save)
 → Logout
```

### Health Center Staff Flow

```
Login
 → Health Center Staff Dashboard
   → Patient Records → Register Patient / Patient Profile
   → Appointments → (Schedule / Update status)
   → Medicine Inventory → Add/Edit Medicine (update stock only)
   → Notifications → (View; send if role permits)
 → Logout
```

### Barangay Official Flow

```
Login
 → Barangay Official Dashboard
   → Community Reports → (View statistics, vaccination campaigns)
   → Announcements → (Post / view health announcements)
   → Notifications → (View delivery status)
 → Logout
```

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
| **Forms** (48px input height, 12px radius, label-above, Bootstrap validation) | Register Patient, Add/Edit Medicine, Appointment scheduling form, Settings, User Management (add user), Login |
| **Modals** | Add/Edit Medicine (quick edit), Reset Password, Delete/Archive confirmation, Add Appointment |
| **Pagination** | Patient Records, Medicine Inventory, User Management, Audit Logs tables |
| **Status Badges** (Success/Warning/Danger/Info/Neutral, 999px radius) | Patient status, medicine stock status, appointment status, user status, notification delivery status |
| **Alerts/Toasts** | Low-stock warnings, save/update confirmations, failed SMS send notices |
| **Charts** (Bar, Line, Pie, Donut — no 3D) | Administrator Dashboard, Reports & Analytics, Barangay Official Dashboard (community stats) |
| **Notifications Panel/Bell** | Header — global, all roles |
| **Profile Dropdown** | Header — global, all roles (shows name, role, logout) |
| **Breadcrumbs** | Patient Profile, Add/Edit Medicine, Settings sub-sections (to show hierarchy back to parent list) |
| **SMS Composer / Character Counter / Recipient Selector** | Community Notifications screen only |
| **Calendar Widget** | Appointment Scheduling |
| **Tabs** | Patient Profile (Personal/Medical/Consultation/Medicine/Vaccination/Appointment history), Settings sections |

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
| Community Notifications | Form (message editor), Dropdown/Checkbox group (recipients), Badge (delivery status), Table (history), Toast (send confirmation) |
| Reports & Analytics | Card, Chart (via Chart.js/D3, not native Bootstrap), Table, Button Group (export), Nav Tabs (report type switch) |
| User Management | Table, Modal (add user/reset password), Badge (status), Dropdown (role filter), Button |
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

**Build order (recommended, follows Roadmap):**
1. Patient Records → 2. Register Patient → 3. Patient Profile → 4. Medicine Inventory → 5. Add/Edit Medicine → 6. Appointment Scheduling → 7. Community Notifications → 8. Reports & Analytics → 9. User Management → 10. Audit Logs → 11. Settings → 12. Health Center Staff Dashboard → 13. Barangay Official Dashboard

---

End of UI Architecture Document

Status: Approved

This document is now the official UI Architecture for the IDS-BPHCSN Capstone Project.

All future UI design, frontend development, and interface revisions must conform to this architecture unless an approved revision of this document is created.
