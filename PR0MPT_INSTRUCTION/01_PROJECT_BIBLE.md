# IDS-BPHCSN PROJECT BIBLE

Version: 1.0
Status: Active Development
Prepared For: Capstone Project
Institution: Northeastern Mindanao Colleges (NEMCO)

---

# Project Title

Integrated Digital System for Barangay Poblacion Health Center Services and Community Notifications (IDS-BPHCSN)

---

# Purpose of this Document

This document serves as the single source of truth for the entire IDS-BPHCSN project.

Its purpose is to provide complete project context for AI assistants, developers, designers, researchers, and project members. Every future task involving UI design, software development, documentation, database design, testing, debugging, or report generation must follow the information contained in this document.

Whenever there is conflicting information between different documents, the approved Capstone Proposal shall be treated as the highest authority.

---

# Project Overview

IDS-BPHCSN is a desktop web-based healthcare management system developed for Barangay Poblacion Health Center.

The system aims to replace manual record keeping with an integrated digital platform that manages patient information, medicine inventory, appointments, community notifications, reports, and administrative functions.

The project is developed as part of the Capstone Project requirement at Northeastern Mindanao Colleges.

---

# Problem Statement

The Barangay Health Center currently experiences challenges associated with manual operations, including:

- Paper-based patient records
- Slow retrieval of patient information
- Manual appointment scheduling
- Inefficient medicine inventory monitoring
- Delayed dissemination of community announcements
- Limited reporting capabilities
- Difficulty tracking healthcare services

These issues reduce operational efficiency and increase the possibility of human error.

---

# Project Objectives

## General Objective

Develop an integrated digital healthcare management system that improves efficiency, organization, and communication within Barangay Poblacion Health Center.

## Specific Objectives

Per the approved Capstone Proposal, the project has exactly four core objectives. These define
project success and must be prioritized above all other work:

1. Digitize and manage patient records (Patient Records, Register Patient, Patient Profile).
2. Manage medicine and supplies inventory, including automated low-stock alerts (Medicine
   Inventory, Add/Edit Medicine).
3. Work the daily patient queue and deliver community notifications (Patient Queue,
   Community Notifications).
4. Generate automated healthcare reports (Reports & Analytics).

Supporting outcomes (improve administrative efficiency, reduce paperwork, improve data
accessibility, support informed decision making) are the expected *results* of achieving the
four core objectives above, not separate objectives to design or build independently.

---

# Target Users

The system supports four user roles. The fourth, Doctor, was added on 2026-09-25; the
decision record below says why.

## Administrator

The Administrator is Kagawad Antonio Acido, chair of the barangay Health Committee — a barangay
official, **not a physician**. The role administers the system. It holds no clinical authority and,
since Task 5c (2026-10-01), sees no clinical data: that is for the care team, the Doctor and Health
Center Staff (RA 11166; RA 10173; the minimum-necessary standard). See "Clinical Data Is for the
Care Team".

Responsibilities

- Full system administration (accounts, settings, encrypted backup, maintenance mode)
- User management and the Service Schedule
- Dashboard monitoring (counts only)
- Reports & Analytics (counts and rankings)
- Inventory management (add, edit, archive, stock)
- SMS broadcasts
- Audit logs
- A read-only patient list and profile, demographics only, and a read-only Patient Queue

---

## Doctor

The RHU physician. The demo account is named "RHU Physician (demo)" until the real doctor's name
is confirmed.

Responsibilities

- Diagnose, and record the treatment plan
- Mark a consultation Restricted when it holds privileged information, and lift that mark
- Read a Restricted consultation in full
- Declare a patient deceased, and reverse that status
- Everything Health Center Staff do on the clinical floor: register patients, work the patient
  queue, record consultations, dispense medicines, update inventory, view SMS notifications
- Read Reports & Analytics — the consultation counts and top-diagnoses ranking — with the same
  figures and exports the Administrator and the Barangay Official see

The Doctor has no User Management, Audit Logs or Settings, and is blocked by maintenance mode like
every role but the Administrator.

---

## Health Center Staff

Responsibilities

- Register patients
- Record consultation intake (complaint, vital signs, vaccinations, dispensing) — not the
  diagnosis or treatment plan, which are the Doctor's
- Check patients in, choosing the service, and work the Patient Queue
- Dispense medicines
- Update inventory
- View SMS notifications
- Change a patient's status between Active and Inactive (not Deceased, which is the Doctor's)

---

## Barangay Official

Responsibilities

- View community reports
- Receive health announcements
- Monitor public health activities
- Access authorized information only

---

# Decision Record — Clinical Authority Belongs to the Doctor (2026-09-25)

**Decision.** A fourth role, **Doctor**, was added, and clinical authority was moved to it from the
Administrator. Only the Doctor may enter or edit a consultation's **diagnosis** and **treatment
plan**, **seal** a consultation as Restricted or lift a seal, **read** a sealed consultation, and
**declare a patient deceased** (or reverse that status).

**Why.** Clinical authority had been given to the Administrator on the assumption that the
Administrator was the health center's licensed doctor. That stopped being true when the
Administrator's persona was corrected: the Administrator is **Kagawad Antonio Acido**, chair of the
barangay Health Committee, an elected barangay official and not a physician. Field data gathered
from the RHU of San Francisco, Surigao del Norte, then showed two genuinely separate jobs:

- **System administration** — accounts, settings, backup, maintenance mode — is the Kagawad's.
- **Clinical authority** — consultation diagnosis, medical certificates, declaring death — is the
  RHU doctor's.
- Nurses and midwives (Health Center Staff) carry out the doctor's orders, run programmes, take
  the intake and refer patients.

The system as it stood let the only account that could diagnose be held by someone not licensed to.
The Administrator is not the doctor, and no part of this project may say it is.

**What the Administrator keeps.** Every system-administration power: User Management, Audit Logs,
Settings, Backup, Maintenance Mode, Reports & Analytics, and its operational screens. (As of
2026-09-25 it still recorded consultation intake; since Task 5c it records none and reads patients
as demographics only. See "Clinical Data Is for the Care Team".)

**What did not change.** A diagnosis the Administrator account wrote before this decision keeps its
text and its attribution. A seal the Administrator set stays set and stays attributed to it. No
audit entry was rewritten. The last-Administrator guard still protects the Administrator role.

**Reports & Analytics — decided afterwards (2026-09-25).** The Doctor was at first deliberately
not given Reports & Analytics, and the question was left to the team. The team granted it. The
consultation counts and the top-diagnoses ranking are the doctor's own clinical material, and they
serve disease prevention, which the RHU named as its main goal. Granting it exposes nothing new:
the Barangay Official already reads the same figures, and a sealed diagnosis appears in the
ranking only as "Confidential" for every viewer, the Doctor included — the Doctor reads sealed
text on the patient's own record, never in an aggregate. The Doctor sees the same screen, the same figures and the same two
exports as the other two roles; there is no doctor-specific view. User Management, Audit Logs and
Settings stay with the Administrator.

---

# System Scope

## Core Objective Modules (per approved Capstone Proposal)

- Patient Records Management
- Patient Profile Management
- Consultation Records
- Medicine Inventory
- Patient Queue
- Community Notifications
- Reports and Analytics

## Supporting Infrastructure Modules

These are necessary for the system to function securely with four distinct roles, but are not
themselves core objectives from the approved Proposal. They should be built after the core
objective modules are functional, not treated as equal priority.

- User Authentication
- Administrator Dashboard
- Health Center Staff Dashboard
- Barangay Official Dashboard
- User Management
- Audit Logs
- System Settings

---

# Out of Scope

The following features are intentionally excluded.

- Online patient self-registration
- Online payment processing
- Telemedicine consultation
- Mobile application
- Artificial Intelligence diagnosis
- Electronic prescriptions
- Integration with external hospital systems

---

# Technology Stack

Frontend

- HTML5
- CSS3
- Bootstrap 5
- JavaScript

Backend

- Python
- Flask

Database

- SQLite

Development Environment

- Visual Studio Code

Version Control

- Git (optional)

System Architecture

- Client-Server Architecture using a Star Topology. A single centralized Flask/SQLite server
  handles all database operations and application logic; client devices (Admin, Staff, and
  Barangay Official workstations) connect individually to that central server over a local
  network. See 04_DEVELOPMENT_GUIDE.md for full technical detail.

---

# Design Philosophy

The system shall follow a clean, professional, and modern healthcare management interface.

The interface must emphasize:

- Simplicity
- Readability
- Consistency
- Accessibility
- Professional appearance
- Government healthcare aesthetic
- Desktop-first experience

The interface should resemble a production-ready government information system without copying any existing official software.

---

# UI Principles

Every page must maintain the same visual identity.

Consistency is mandatory.

The following elements should remain consistent across all screens:

- Sidebar
- Header
- Typography
- Buttons
- Cards
- Tables
- Colors
- Icons
- Navigation
- Spacing
- Shadows
- Border radius

Only the content area should change between modules.

---

# Navigation Structure

Login

↓

Administrator Dashboard

├── Dashboard
├── Patient Records (demographics only)
├── Medicine Inventory
├── Patient Queue (read-only)
├── Service Schedule
├── SMS Notifications
├── Reports & Analytics
├── User Management
├── Audit Logs
└── Settings

Health Center Staff

├── Dashboard
├── Patient Records
├── Register Patient
├── Medicine Inventory
├── Patient Queue
├── Service Schedule
└── SMS Notifications

Doctor (the Health Center Staff menu, served from the same screens, plus Reports & Analytics)

├── Dashboard
├── Patient Records
├── Register Patient
├── Medicine Inventory
├── Patient Queue
├── SMS Notifications
└── Reports & Analytics

Barangay Official

├── Dashboard
├── SMS Notifications
├── Health Programs
├── Service Schedule
├── Vaccination Campaigns
├── Community Reports
└── Reports & Analytics

---

# Functional Requirements

The system shall:

- Authenticate users.
- Store patient records.
- Search patient information.
- Update consultation records.
- Manage medicine inventory.
- Monitor medicine stock levels.
- Schedule appointments.
- Generate reports.
- Send community notifications.
- Manage user accounts.
- Record audit logs.
- Manage system settings.

---

# Non-Functional Requirements

The system shall be:

- Reliable
- Secure
- Easy to use
- Responsive
- Organized
- Consistent
- Maintainable
- Scalable for future improvements

---

# Security Principles

The system shall implement:

- Login authentication
- Role-based access control
- Protected administrator pages
- Session management
- Input validation
- Secure database access

How these are done now (2026-09-29):

- The secret key that signs sign-in cookies is read from a .env file on each computer
  (`python setup_env.py` creates it). The app will not start without a proper key.
  Debug mode is off unless IDS_DEBUG=1.
- A person is signed out after 30 minutes without activity, and 12 hours after they sign
  in. The page warns 2 minutes before the idle limit.
- Every form, and every request a page sends from script, carries a form token from the
  page (added 2026-09-29, Task 3). Another website cannot make a signed-in browser change
  anything. A request without a valid token is refused with a page that says "Your session
  expired", and is recorded in the audit trail when the account is known.
- Signing out is a button that sends a form, not a link. Opening the logout address does
  not sign anyone out.
- No password is written in the code. A new install makes random first-time passwords and
  shows them once in the terminal.
- A new account, a password reset by the Administrator, and a first-time password must all
  be replaced by the person at their first sign-in, before any other screen opens.
- No screen prints text taken from the address bar.
- Every health-record write is in the audit trail (added 2026-09-29, Task 4): patient
  registration, edits and status changes, a death declaration and its reversal, new
  consultations, doses recorded at a visit, dispensing, inventory changes and the Patient
  Queue. Each entry is one short line naming who, what and which record, written in the
  same transaction as the change. None of it quotes a diagnosis, a treatment plan, a sealed
  field, a password or a full contact number.
- Sealed records are encrypted (added 2026-10-01, Task 5). See "Sealed Records and the Law".

---

# Sealed Records and the Law

**The law.** RA 11166 (Philippine HIV and AIDS Policy Act), Section 44: it is unlawful to disclose,
without written consent, that a person has HIV or AIDS, has had an HIV-related test, has HIV
infection or a related illness, or has been exposed to HIV. This binds anyone who handles personal
data at work. Medical confidentiality allows sharing only with health workers involved in the
patient's care. RA 10173 (Data Privacy Act) makes health data sensitive personal information. NPC
Circular 2023-06, which replaced NPC Circular 16-01 in March 2024, requires such data to be
protected to industry standards, with a written backup-and-restore process. Circular 16-01 set
AES-256 as the minimum encryption standard. So backups must exist and must restore fully, but
sealed clinical text inside them must be unreadable without the key.

**Decisions (2026-10-01, Task 5).**

- D1. On a sealed (Restricted) consultation, the diagnosis and treatment plan are stored encrypted
  with AES-256-GCM. The key is SEALED_DATA_KEY in .env, separate from SECRET_KEY. Only the Doctor's
  screens decrypt. The backup carries ciphertext and still restores fully.
- D2. No audit entry stores diagnosis or treatment-plan text, sealed or not. An edit names the
  field ("Changed: Diagnosis"). Older entries were cleaned by migrations/migrate_redact_clinical_audit_text.py.
- D3. In Reports & Analytics, sealed consultations count in every total and appear in the diagnosis
  ranking as one "Confidential" row, for every role.
- D4. Exports (Excel, PDF) and print views never contain sealed text, for any role, the Doctor
  included. The Doctor reads sealed text on screen only.
- D5. The Doctor keeps a printed copy of the key in a sealed envelope (export_sealed_key.py), so
  sealed records can be recovered if the computer fails.

**Decisions (2026-10-01, Task 5b).** Task 5 sealed only the diagnosis and treatment plan. Section
44 also forbids disclosing that a person *has undergone an HIV-related test*. A chief complaint, a
note or a check-in reason such as "for HIV testing" discloses exactly that, even with the diagnosis
encrypted. Task 5b closes the rest.

- D1. A sealed visit encrypts every free-text field of that visit: the chief complaint, the
  additional notes, and the check-in reason of its linked queue visit, as well as the diagnosis and
  treatment plan. Vitals, immunization records, dates and the fact of the seal stay readable.
- D2. Those fields follow the existing seal rule: on screen, only the Doctor reads them; everyone
  else sees "Restricted — Doctor access only". Exports and prints never contain them, for any role.
- D3. The names of medicines dispensed at a sealed visit are hidden from the Administrator on every
  patient-linked view, export and print. The Doctor and Health Center Staff, who are part of the
  patient's care, still see them. Stock levels and per-item totals not tied to a patient stay visible.
- D4. On the Patient Queue the Administrator sees each patient, their status and times, but not the
  check-in reason, for any visit (minimum necessary). The Doctor and Health Center Staff still see it.
- D5. No audit entry stores a chief complaint, note, check-in reason or other free clinical text.
  An edit entry lists field names only ("Changed: Chief complaint, Additional notes").
- D6. When the Doctor prints the Edit Consultation page from the browser, sealed fields print as
  "Sealed — not printed".

**Known limits.** For a sealed visit these stay readable to Health Center Staff: the visit date,
vital signs, immunizations, and the fact that the record is sealed. The names of medicines dispensed
at a sealed visit stay plain in the database, because stock counts read them. Since Task 5c the
backup file is encrypted as a whole and Reports & Analytics count them under "Confidential". Backups made before 2026-10-01 hold plain
text. The key sits in .env on the same computer as the database, so the encryption protects copies
that leave the computer; the computer itself needs full-disk encryption (BitLocker).

---

# Clinical Data Is for the Care Team

**Decision (2026-10-01, Task 5c).** Clinical data is for the care team only: the Doctor and Health
Center Staff. The Administrator manages the system, not patients' care.

- RA 11166: medical confidentiality allows sharing only with health workers involved in the
  patient's care.
- RA 10173 (Data Privacy Act): processing must be adequate, relevant and not excessive.
- The HIPAA "minimum necessary" standard, which this project already follows.

This extends the adviser's reasoning behind the Doctor role. That moved clinical authority to the
Doctor because the Administrator is not a physician; this moves clinical data to the care team for
the same reason.

**The Administrator keeps** accounts, Settings, maintenance mode, Service Schedule editing, SMS
broadcasts, Audit Logs, full inventory management, Reports & Analytics, a read-only patient list
and profile showing demographics only (patient ID, name, sex, age and birth date, address, status,
registration date), a read-only Patient Queue, and a dashboard of counts.

**He loses, on the server:** every clinical field (chief complaint, vitals, diagnosis, treatment
plan, notes, check-in reasons, conditions, allergies, immunization records, which medicines a
patient received), patient contact numbers, and every patient or clinical write (registering or
editing patients, status changes, the immunization correction, the queue's check-in, start and
complete, recording or editing consultations).

**With it:** audit entries name no medicine, vaccine or clinical value; the backup download is an
encrypted `.idsbackup` file, restored with `restore_backup.py` at the health-center PC, using a key
derived from SEALED_DATA_KEY (one key, one envelope); the most-dispensed ranking counts sealed-visit
dispensing as "Confidential".

The Doctor, Health Center Staff and the Barangay Official are unchanged.

**Small counts (2026-10-02, Task 5d).** In Reports & Analytics and Community Reports, for the
Administrator and the Barangay Official, any row of a ranking or breakdown by diagnosis, complaint,
condition or dispensed medicine with a count of 1 to 4 is folded into one row, "Other (each fewer
than 5)". The "Confidential" row folds the same way when its count is under 5. Totals stay exact.
The Doctor sees every count. The threshold is `SMALL_COUNT_THRESHOLD` in `config.py`. The reason:
the Administrator can see who is in the queue and when, so a count of 1 over a short date range can
identify a person (RA 10173, minimum necessary).

**Masked numbers (Task 5d).** On every SMS screen, export and JSON response, for every role, a phone
number shows its last four digits only ("•••• ••• 1234"). Recipient counts and delivery results stay.
Full numbers stay only where the system sends messages. The mask works on every common Philippine format
(09…, +639…, 639…, with spaces, dashes, dots or brackets), including inside audit entries.

**No placeholder panels (final fixes).** The "Notifications" panel on the Staff and Official dashboards, which only said none are recorded, is removed. SMS Notifications is the one notification screen.

**Recipients (final fixes).** The Administrator and the Barangay Official see recipient counts only on every
SMS screen, for every audience: total, sent and failed per broadcast, and a count per audience. They see no
recipient name. The Doctor and Health Center Staff see names with masked numbers. The rule is in the data
builder (`get_broadcast_recipients()`), not in the template.

**Small counts everywhere (2026-10-02, Task 5e).** The rule covers any count tied to a health service
or condition: "Appointments by service requested" folds rows of 1 to 4 into "Other (each fewer than
5)" for the Administrator and the Official, and a single count tied to a condition or service (such as
patients with only free-text conditions, or Prenatal Check-up visits) reads "Fewer than 5" when it is 1
to 4. Zero stays "0". Audit entries never store a whole phone number: they are written masked, and
`migrations/migrate_mask_audit_phone_numbers.py` masked the old ones.

**The visit flow, the Doctor's list and Left before being seen (2026-10-02, Tasks 6 and 6b).** The Doctor
comes only on certain days, while Staff take the intake every day. A visit moves like this:

1. **Check-in.** Staff choose the service from one fixed list (Consultation, Follow-up Consultation,
   Hypertension / Diabetes Monitoring, Prenatal Check-up, Immunization, Dental). The choice is required, has
   no default, and is checked on the server. Status: *Waiting*.
2. **Start.** *In Consultation*. One patient at a time.
3. **Intake saved.** If the service needs a diagnosis (the first three) and none was written: *Waiting for
   the Doctor*. Otherwise: *Completed*. Prenatal, immunization and dental visits are finished by Staff.
   A visit that needs the Doctor can never be Completed without his diagnosis, by any route: if the intake
   is not written, the queue's button is **Send to the Doctor** (status *Waiting for the Doctor*, one short
   audit entry), and the server refuses "Mark Completed" with "This visit needs the Doctor first."
4. **Diagnosis saved by the Doctor.** *Completed*. If the Doctor records the whole consultation himself, with a
   diagnosis, it goes straight to *Completed*. He may write a diagnosis on any visit; it stays *Completed*.
5. **Left before being seen.** Staff and the Doctor can set it, after a confirmation, on a visit that is
   Waiting, In Consultation or Waiting for the Doctor. It is refused on a visit with a diagnosis or a finished
   one. It is recorded (who and when) and audited, and can be undone the same day, back to the previous
   status. The Administrator's queue stays read-only.
6. **Correcting the service.** Staff and the Doctor can change a visit's service until it is Completed or
   Left before being seen. Each change is audited. The Administrator cannot.

The Doctor's dashboard lists every visit with the status *Waiting for the Doctor*, oldest first, across all
days, with how long it has waited. Visits from earlier days are marked. Health Center Staff and the
Administrator see the count only ("Waiting for the Doctor: N"), with no names. One function decides, so the
three agree. Which services need a diagnosis is one named constant (`SERVICES_NEEDING_DOCTOR`), a subset of
the list Staff choose from (`VISIT_SERVICES`). "Completed" counts only finished visits. Visits still *Waiting*
from earlier days are shown to Staff under "Still waiting from earlier days"; nothing closes them
automatically. Queue reports count Waiting for the Doctor and Left before being seen as their own figures.
The service names a clinical fact, so the Administrator's queue, its export and his dashboard show no
service.

**Stock accountability.** Dispensing writes no stock entry, because an entry per issue would tie a
medicine to a visit time. Accountability comes from the stock levels and from the dispensed totals
in Reports & Analytics. The Doctor and Health Center Staff hold the full dispensing records. Receiving
stock and removing it from a batch are not patient events, so each writes an audit entry that names the
item, the lot and the amount (Task 12).

---

# Decision Record — Honest Immunization Status (2026-10-03, Task 9)

**The concern (raised by the capstone adviser).** The profile marked a dose "Overdue" when no dose was
recorded here. But the child may have been vaccinated elsewhere, for example BCG and Hepatitis B at the
hospital of birth. The system cannot know that, and "Overdue" claimed that it did. There was also no way to
record a dose given elsewhere outside a consultation.

**The basis.** CDC General Best Practices for Immunization: only written, dated records are accepted as
evidence of vaccination (self-report is accepted for only a few adult vaccines); vaccination is not
postponed when records are missing, staff try to find the records, and without records the person is
treated as unvaccinated. HL7 FHIR R4 Immunization: `primarySource = false` for a dose recorded from another
source, and `reportOrigin` tells a written record from recall.

**What a dose rests on.** Every dose record has one evidence type:

| Evidence | Meaning | FHIR | Counts as given? |
|---|---|---|---|
| `given_here` | Given at this health center during a consultation | `primarySource` true | Yes |
| `card` | Given elsewhere; the vaccination card or record book was **seen**. Date required | `primarySource` false, `reportOrigin` "record" | Yes ("Given elsewhere", green) |
| `parent_report` | The parent or guardian says it was given and has no card. Date optional | `primarySource` false, `reportOrigin` "recall" | No ("Parent says given — no card", amber) |

A dose with nothing on file reads **No record** (it used to read Overdue) and still shows its due date.
Completion, the follow-up lists and every coverage figure count `given_here` and `card` only; a parent's
report has its own line ("Parent says given, no card: N"). One function, `get_immunization_status()`,
decides all of it, so no screen can disagree.

**Recording a dose given elsewhere.** A **Record dose given elsewhere** button on every scheduled dose that
has no `given_here` or `card` record, on the Immunization Record tab. Health Center Staff and the Doctor only;
it works outside a consultation. The person must choose the proof (card seen, or the parent's word); a card
needs a date; no date is in the future or before birth; the place is optional. A parent's report can be
upgraded to a card when the card is shown, or removed. A dose given here is never replaced or removed this
way. The consultation form asks for the same proof on its Given elsewhere column. The Administrator and
the Barangay Official have no route to any of it.

**Audit.** Entries name no vaccine: "Recorded 1 dose given elsewhere for <Name> (PAT-008).", "Recorded a
parent report of 1 dose for <Name> (PAT-008).", "Upgraded a parent report to a card record for <Name>
(PAT-008)."

**Existing data.** `migrations/migrate_immunization_evidence.py` set every earlier dose given here to
`given_here` and every earlier dose reported as given elsewhere to `card`. That second step was a decision of
the brief: those doses were recorded before proof was asked for, so a team that wants certainty should check
them against the cards.

# Decision Record — Stock in Batches, Named by Generic Name (2026-10-03, Task 12)

**The two concerns (raised with the capstone adviser).** First, restocking edited one quantity and one
expiry date per medicine. A new delivery has a different expiry from the old stock, so the system lost
which boxes expire when. Second, the add-medicine form had a separate "Medicine name" next to the generic
and brand names. RA 6675 (the Generics Act) asks government health agencies to use generic names in
purchasing, prescribing and dispensing; the brand name is optional and the generic name comes first.

**The item.** An item is a kind of thing the health center stocks, and it holds no quantity and no expiry
date. A medicine is defined by three required fields: **generic name**, **strength** (free text, for
example "500 mg" or "250 mg/5 mL") and **dosage form** (one list, `DOSAGE_FORMS`: tablet, capsule, syrup,
suspension, drops, sachet, injection, cream, ointment, inhaler, other). Its display name is built from them
and never typed: "Paracetamol 500 mg tablet". Two items with the same generic name, strength and form are
refused as duplicates (case and spaces ignored). A medical supply or equipment item (`category` Supply or
Equipment; Medicine is the only drug) keeps a simple item name and a size or specification instead. The
brand name is not an item field.

**The batch.** Each delivery is one batch: lot number (required; "No lot number" only with a tick box),
expiry date (required for a medicine, optional for a supply), quantity received, date received (default
today), source (DOH, Municipal Health Office / RHU, Barangay purchase, Donation, Other) and an optional
brand name, which belongs to the batch because deliveries of the same generic can come from different
makers. An item's stock is the sum of its usable batches.

**Three separate actions.** *Edit details* changes item fields only, never a quantity. *Receive stock* adds
a batch. *Remove from stock* takes an amount out of ONE batch, with a required reason (Expired, Damaged,
Lost, Returned, Count correction) and an optional note. Each writes one short audit entry: who, the item
display name, the lot number and the amount. No patient is involved, so the medicine name is allowed there
(inventory entries have always named items). Whoever could manage inventory before can do all three: the
Administrator, Health Center Staff and the Doctor; the Barangay Official still cannot.

**FEFO (First Expiry, First Out).** Dispensing takes automatically from the usable batch with the earliest
expiry, splits across batches when one runs out, and records which batch or batches each dispensing used
(`medicine_dispensing_batches`). A batch with no expiry date is used last. Staff do not pick batches. An
expired batch is never used. If usable stock is not enough, dispensing is refused with one plain message
showing the amount available. The Administrator still never sees which patient received which medicine:
the batch links sit with the dispensing records, which only the care team reads.

**Expiry handling.** A batch past its expiry date is *Expired*: not usable, not counted in stock, shown with
a "Remove from stock" prompt. A batch expiring within 90 days (`EXPIRING_SOON_DAYS` in `config.py`, the one
constant) is *Expiring soon*. A batch is usable through the whole of its expiry date. The inventory list
shows, per item, usable stock, the nearest expiry, and the numbers of expiring-soon and expired batches. The
item page lists its batches. The low-stock alert counts usable stock only. The dashboards and the inventory
report show the two batch counts, and the report lists the batches (item, lot, expiry, amount) with Excel
and PDF. These are stock facts with no patient link, so the small-count rule does not apply to them.

**Migration.** `migrations/migrate_inventory_batches.py` makes one opening batch (lot "Opening stock") from
each item's old quantity and expiry, links every earlier dispensing row to it, splits each medicine's name
into generic name, strength and form where it can, and lists the rest (counts only) for staff to fix with
Edit details. It backs up first, is safe to run twice and writes one audit entry about itself.

---

# Decision Record — Vaccines Only When Due (2026-10-03, Task 13)

**The concern (found with the capstone adviser).** A 1-month-old had a dose recorded. At a second
consultation the form still allowed ticking a vaccine meant for older babies. The system let staff record
a dose before the child was old enough, before the previous dose of the series, or too soon after it. A dose
given too early does not count and must be repeated, so the child gets an extra injection.

**The basis.** WHO routine immunization tables: Pentavalent, OPV and PCV primary doses start at a minimum
age of 6 weeks, with at least 4 weeks between doses; the first measles-containing dose is at 9 months, with
at least 4 weeks between the first and the second. A dose given before the minimum age or interval is
invalid and is repeated after at least the minimum interval. ACIP: when checking records of doses given
elsewhere, a 4-day grace period applies.

**The rule.** One function, `dose_eligibility()` in `models/immunizations.py`, used by the consultation form,
the server and every screen. A scheduled dose is eligible today only if (a) the child has reached its minimum
age, (b) the previous dose of the same series is on file as given here or on a card, and is valid, and (c)
at least the minimum interval has passed since that dose. A dose already validly recorded is never eligible
again. A parent's report does not count as a previous dose. The values are named fields in `DOSE_RULES`, one
row per scheduled dose, next to the schedule. The recommended ages shown to users are unchanged.

| Dose | Minimum age | Minimum interval | Previous dose required |
|---|---|---|---|
| BCG | birth | none | none |
| Hepatitis B | birth | none | none |
| Pentavalent 1, OPV 1, PCV 1 | 6 weeks | none | none |
| Pentavalent 2, OPV 2, PCV 2 | 6 weeks | 4 weeks | dose 1 of the same vaccine |
| Pentavalent 3, OPV 3, PCV 3 | 6 weeks | 4 weeks | dose 2 of the same vaccine |
| IPV | 14 weeks (as scheduled) | none | none |
| MR | 9 months | none | none |
| MMR | 12 months | 4 weeks | MR |

**On the consultation form.** Only eligible doses have a tick box. A dose that is not eligible is greyed out
with the earliest date ("From Nov 14, 2026") or the reason ("Needs Pentavalent dose 1 first"). The server
refuses any non-eligible dose with one plain message, for example "This dose is not due yet. Earliest date:
Nov 14, 2026.", whatever the form showed. Several eligible doses at one visit are allowed (co-administration
is normal); doses ticked at the same visit do not count as the "previous dose" of each other. A card dose
reported at the same visit, with its date, does.

**Doses given elsewhere (a card).** They are history, recorded with their real date. A card dose dated more
than 4 days before the minimum age, or more than 4 days before the minimum interval after the previous dose
on file, reads **Given too early — ask the Doctor about a repeat** (amber). It stays on file but does not
count for completion, coverage or the next dose's eligibility, and the child stays on the follow-up list.
Within the 4-day grace it counts. (From Task 14 a dose given here is judged by the same rule; the form still
offers a dose only from its date.) Staff and the Doctor can change or remove such a card record from its row; the Doctor decides about
a repeat.

**What this version does not do (D5).** There is no override. The system follows the routine DOH schedule;
outbreak campaigns that use other ages are outside its scope.

**Queue (D6).** An earlier day's Waiting visit no longer offers Change service; only Left before being seen.

**Existing data.** A record that breaks the rule is not changed. The counts found are in the tracker.

# Decision Record — Every Dose Judged, and Repeats (2026-10-03, Task 14)

**The concern.** Task 13 judged only a dose given elsewhere on a card. A dose given here before its minimum age
(recorded before the rule existed) still counted, and a dose given too early could not be repeated: the table
held one record per dose, so the early record had to be removed first.

**One validity rule.** `judge_records()` in `models/immunizations.py` judges every recorded dose, whatever its
evidence (given here or card). A dose given more than 4 days before its minimum age, or before the minimum
interval after the previous VALID dose of its series, is invalid (ACIP 4-day grace). An invalid dose reads
**Given too early — ask the Doctor about a repeat** (amber), stays in the history, and does not count for
completion, coverage or eligibility. A dose whose previous dose is on file but does not count is invalid too.
Parent reports are not judged and never count. Every screen, report and write path reads this one rule.

**Repeats.** A dose may have more than one record. When a dose has only invalid records, it is eligible again
from the later of its minimum age and (the last invalid date + the series' minimum interval; 4 weeks when the
series has none). A repeat recorded at a consultation, or from the profile as a dose given elsewhere, is a NEW
record. A repeat dated too soon after the invalid dose is itself invalid. The dose's row shows the record that
counts; earlier invalid records show under it ("Earlier dose on Nov 14, 2026 was too early"), each with its
Correct or Change button. Only one VALID record per dose can exist: a second is refused. The next dose of the
series is judged from the repeat, not from the invalid dose.

**Corrections.** A corrected date is checked for sense (not in the future, not before birth), then judged by the
same rule. A correction to a too-early date makes the dose invalid, and the message says so. The correction keeps
its audit entry.

**Table.** The one-record-per-dose constraint is gone (`migrations/migrate_immunization_repeats.py`: backup first,
every record kept with its id, safe to run twice, one audit entry). The table keeps one rule: a dose has at most
one parent's report.

**Existing data.** The one dose given here before its minimum age in `app.db` (id 302) is now judged by the rule:
it reads Given too early and does not count. It was not changed.

# Decision Record — Dates a Dose Can Be Given, and Ages in Weeks (2026-10-04, Task 15)

**Found by the team in real use.** A 30-day-old baby had an early Pentavalent dose 1 recorded. The profile offered
"Record dose given elsewhere" on doses the baby was far too young to have had; it showed that dose "Due Oct 15"
though its repeat could not be given before Oct 31, and showed later doses with dates counted from birth; the age
read only in months, so staff could not tell a 5-week-old from a 6-week-old; and the alert carried long helper text.

**The Due column.** A dose's due date is the earliest date it can actually be given (`dose_due()`): the later of its
minimum age date, the previous valid dose + the minimum interval, and for a repeat the last invalid dose + the
series' interval. When the previous dose will be repeated, the date follows the repeat (never earlier than today).
When a previous dose has no record, the row reads "After <that dose>" instead of a date. The recommended age column
is unchanged. A dose is not Due Now or No record before it can be given.

**The button.** "Record dose given elsewhere" appears on a dose only from 4 days before its minimum age date (the
ACIP grace). Rows with a parent's report (to upgrade to a card) and rows that need a repeat keep it. The server
refuses the same doses with one message ("<Name> is not old enough for <dose> yet. It can be recorded from <date>."),
on the profile and on the consultation form's "given elsewhere" tick.

**Age.** One helper, `format_age()`, used by the profile, the patient list, the check-in list, the consultation form,
the prints and the exports, and mirrored in the registration preview: under 28 days "12 days"; to 16 weeks "4 weeks
2 days"; to 24 months "5 months 3 days"; to 5 years "2 years 6 months"; then "7 years". Calendar months, exact
leap-year and month-end arithmetic. Age filters and report age groups are unchanged.

**Text.** The profile alert is a title ("3 doses to follow up") and one line ("Pentavalent dose 1 (repeat from Oct
31, 2026); BCG and Hepatitis B (parent says given, no card). Ask for the vaccination card."). The "not in today's
queue" sentence, the "next consultation" sentence and the "At next visit" notes are gone.

# Sample Development Workflow

Research

↓

UI Design

↓

Prototype Approval

↓

Frontend Development

↓

Backend Development

↓

Database Integration

↓

Testing

↓

Documentation

↓

Final Presentation

---

# AI Collaboration Rules

Artificial Intelligence tools are used as development assistants.

AI may assist in:

- UI Design
- Code Generation
- Documentation
- Debugging
- Database Design
- Testing
- Content Writing

Human project members remain responsible for:

- Reviewing outputs
- Verifying correctness
- Implementing improvements
- Making final decisions

AI-generated content shall always be reviewed before inclusion in the final project.

---

# Source of Truth Priority

When conflicts occur, follow this order.

1. Approved Capstone Proposal
2. This Project Bible (as of Version 2.0, corrections from 10_PROPOSAL_RECONCILIATION_NOTES.md
   have been merged directly into this document and 04_DEVELOPMENT_GUIDE.md /
   08_PROJECT_ROADMAP.md — the reconciliation file itself now serves only as a historical
   changelog and no longer needs to be actively cross-referenced)
3. UI Design System
4. Screen Specifications
5. Development Guide
6. AI Master Instructions

---

# Success Criteria

The project is considered successful when:

- All required modules are completed.
- User authentication works correctly.
- Patient management functions operate correctly.
- Inventory management functions operate correctly.
- Appointment scheduling functions operate correctly.
- Reports are generated correctly.
- Community notifications function properly.
- The interface remains visually consistent.
- The system demonstrates role-based access control.
- The system satisfies the approved Capstone requirements.

---

# Version History

Version 1.0

Initial Project Bible created for the IDS-BPHCSN Capstone Project.

Version 2.0

Reconciled against the actual approved Capstone Proposal. Specific Objectives and System Scope
reorganized to correctly prioritize the four core objective modules (Patient Records, Medicine
Inventory, Patient Queue + Community Notifications, Reports & Analytics) over
supporting infrastructure (User Management, Audit Logs, Settings). Added System Architecture
(Client-Server, Star Topology). Full detail of what changed and why is preserved in
10_PROPOSAL_RECONCILIATION_NOTES.md.

Version 2.1 (2026-09-25)

Four roles. Added the Doctor role and moved clinical authority — diagnosis, treatment plan,
sealing and reading Restricted consultations, declaring death — to it from the Administrator, who
is a barangay Kagawad and not a physician. See "Decision Record — Clinical Authority Belongs to the
Doctor".

Version 2.2 (2026-09-25)

The Doctor reads Reports & Analytics, with the same figures and exports as the Administrator and
the Barangay Official. Sealed diagnoses stay out of the ranking for every viewer. See the Reports &
Analytics paragraph at the end of the Decision Record.

Version 2.3 (2026-09-29)

Security basics. The secret key comes from .env, and debug mode is off by default. Sessions end
after 30 minutes without activity or 12 hours after sign-in. No password is written in the code:
first-time passwords are random and shown once, and every new or reset password must be changed
at first sign-in. See "Security Principles".

Version 2.4 (2026-09-29)

Form tokens (CSRF). Every form and script request carries a token from its page, and signing
out is a form, not a link. A refused request shows "Your session expired". See "Security
Principles".

Version 2.5 (2026-09-29)

Audit coverage (H3). Patient, consultation, dispensing, inventory and Patient Queue writes now
leave an audit entry, written with the change so a successful write always has one. The Audit
Logs screen's description of what the trail covers was corrected (M6). See "Security
Principles".

Version 2.6 (2026-10-01)

Sealed record privacy (H4). Sealed diagnoses and treatment plans are encrypted, audit entries
never quote clinical text, reports show sealed visits as "Confidential", and exports and prints
never carry sealed text. See "Sealed Records and the Law".

Version 2.7 (2026-10-01)

Task 5b, seal all free text. A sealed visit now encrypts its chief complaint, additional notes and
the check-in reason too, because RA 11166 Section 44 also covers the fact that a person was tested.
The Administrator no longer sees the check-in reason on the Patient Queue, or the medicine names of
a sealed visit. Audit entries name free-text fields and never quote them. See "Sealed Records and
the Law".

Version 2.8 (2026-10-01)

Task 5c, care-team-only clinical data. The Administrator sees demographics, counts and read-only
views, and writes no patient or clinical record. Audit entries name no medicine or vaccine. The
backup download is encrypted. See "Clinical Data Is for the Care Team".

Version 2.9 (2026-10-02)

Task 5d, small counts and masked numbers. Ranking rows with fewer than 5 fold into "Other" for the
Administrator and the Barangay Official. Phone numbers show their last four digits on SMS screens.
Stock accountability is stated correctly. See "Clinical Data Is for the Care Team".

Version 3.0 (2026-10-02)

Task 6, the Doctor's list and Left before being seen. See "Clinical Data Is for the Care Team".

Version 3.1 (2026-10-02)

Task 6b, the service chosen at check-in and the status Waiting for the Doctor. "Completed" now means
finished. See "The visit flow" under "Clinical Data Is for the Care Team".

Version 3.2 (2026-10-02)

Task 6c, no skipping the Doctor: a visit that needs him cannot be Completed without a diagnosis, and no
audit entry names a visit's service.

Version 3.3 (2026-10-03)

Task 12, stock in batches and medicines named by generic name (RA 6675). Each delivery is a batch with its
own lot, expiry, source and brand; dispensing is FEFO; a batch past its expiry date is never used or
counted. See "Decision Record — Stock in Batches, Named by Generic Name".

Version 3.4 (2026-10-03)

Task 13, vaccines only when due: a dose needs the minimum age, the previous dose of its series and the
minimum interval (WHO routine immunization tables; ACIP 4-day grace for cards). See "Decision Record —
Vaccines Only When Due".

Task 14, every dose judged, and repeats: one validity rule for every recorded dose, and a dose given too early
can be repeated as a new record. See "Decision Record — Every Dose Judged, and Repeats".

Task 15, dates a dose can be given, and ages in weeks: the Due column shows the earliest date a dose can be given,
the record-elsewhere button waits until the child is old enough, and ages show weeks for a baby. See "Decision
Record — Dates a Dose Can Be Given, and Ages in Weeks".
