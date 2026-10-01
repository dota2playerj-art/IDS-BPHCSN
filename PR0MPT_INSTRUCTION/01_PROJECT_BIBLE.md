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
official, **not a physician**. The role administers the system and holds no clinical authority.

Responsibilities

- Full system administration (accounts, settings, backup, maintenance mode)
- User management
- Dashboard monitoring
- Reports
- Inventory supervision
- System settings
- Audit logs
- Record consultation intake (complaint, vital signs, vaccinations, dispensing) — not the
  diagnosis or treatment plan

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
- Manage appointments
- Dispense medicines
- Update inventory
- View notifications
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
Settings, Backup, Maintenance Mode, Reports & Analytics, and its operational screens. On Record
Consultation it now records intake exactly as Health Center Staff do. Under RA 11166 it sees the
"Restricted — Doctor access only" placeholder on a sealed consultation, as Health Center Staff do.

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
├── Patient Records
├── Medicine Inventory
├── Patient Queue
├── Community Notifications
├── Reports & Analytics
├── User Management
├── Audit Logs
└── Settings

Health Center Staff

├── Dashboard
├── Patient Records
├── Appointments
├── Medicine Inventory
└── Notifications

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
├── Community Reports
├── Announcements
└── Notifications

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
  field ("Changed: Diagnosis"). Older entries were cleaned by migrate_redact_clinical_audit_text.py.
- D3. In Reports & Analytics, sealed consultations count in every total and appear in the diagnosis
  ranking as one "Confidential" row, for every role.
- D4. Exports (Excel, PDF) and print views never contain sealed text, for any role, the Doctor
  included. The Doctor reads sealed text on screen only.
- D5. The Doctor keeps a printed copy of the key in a sealed envelope (export_sealed_key.py), so
  sealed records can be recovered if the computer fails.

**Known limits.** For a sealed visit these stay readable, on screens and in the backup: what was
dispensed (needed for stock counts; a medicine can hint at a condition), the visit date, chief
complaint, vital signs, additional notes, immunizations, and the fact that the record is sealed.
Backups made before 2026-10-01 hold plain text. The key sits in .env on the same computer as the
database, so the encryption protects copies that leave the computer; the computer itself needs
full-disk encryption (BitLocker).

---

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