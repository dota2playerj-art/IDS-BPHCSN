# IDS-BPHCSN PROPOSAL RECONCILIATION NOTES

Version: 1.0
Status: Active
Prepared For: Capstone Project
Institution: Northeastern Mindanao Colleges (NEMCO)

---

# Purpose of This Document — UPDATED STATUS

**As of the Version 2.0 update to `01_PROJECT_BIBLE.md`, `04_DEVELOPMENT_GUIDE.md`, and
`08_PROJECT_ROADMAP.md`, every correction described below has been merged directly into those
three files.** This document is now a **historical changelog** explaining what changed and why
— it is no longer required reading for future AI sessions or Claude Code prompts. Reading
01_PROJECT_BIBLE.md, 04_DEVELOPMENT_GUIDE.md, and 08_PROJECT_ROADMAP.md alone is now sufficient;
they contain the corrected, current information directly.

Documents 01 through 09 in this project were originally generated with AI assistance (Gemini) 
before being adopted as working references. This document reconciled those files against the 
actual approved Capstone Proposal (Baluya, Embodo, Mapalad, Montenegro — May 2026), which is 
the single highest source of truth for this project per the Source of Truth Priority in 
`01_PROJECT_BIBLE.md`.

---

# Correction 1 — Core Objectives Are Four Modules, Not More

The approved Proposal's Specific Objectives define exactly four core modules:

1. Patient Records Management
2. Medicine and Supplies Inventory (with automated low-stock alerts)
3. Scheduling + Community Notification
4. Automated Report Generation

`03_SCREEN_SPECIFICATIONS.md` and `08_PROJECT_ROADMAP.md` additionally list User Management, 
Audit Logs, and Settings as full screens/modules. These are NOT listed as core objectives or 
scope items in the approved Proposal.

**Correction:** User Management, Audit Logs, and Settings remain valid and necessary — a 
multi-role system requires account management and configuration to function securely, and 
`01_PROJECT_BIBLE.md`'s Security Principles already imply this. However, they should be treated 
and presented as **supporting infrastructure**, not as equal-weight core objectives. When 
discussing project completion or defending scope, prioritize and present the four core modules 
first.

---

# Correction 2 — System Architecture Was Undocumented

The approved Proposal specifies:

> The IDS-BPHCSN follows a **Client-Server Architecture using a Star Topology** during both 
> development and deployment phases. This structure centralizes all database operations and 
> application logic at a single server point, with client devices (staff, admin, and official 
> workstations) connecting individually to that central point.

This was not documented anywhere in `04_DEVELOPMENT_GUIDE.md`. 

**Correction:** `04_DEVELOPMENT_GUIDE.md` should be treated as including this architecture 
specification. All backend/deployment planning should assume a single centralized Flask server 
with SQLite, accessed by multiple client devices over a local network (Wi-Fi router), not a 
distributed or multi-server design.

---

# Correction 3 — JavaScript Scope Includes jQuery

`04_DEVELOPMENT_GUIDE.md` states "JavaScript (Vanilla)" as the only approved frontend scripting 
approach. The approved Proposal's software specification table states:

> JavaScript: Vanilla JS, jQuery (CDN-based, no installation required)

**Correction:** jQuery (via CDN, no local installation) is an explicitly approved option 
alongside Vanilla JS. This does not change any UI/design work already completed, since all 
existing screens use Vanilla JS — but jQuery may be introduced going forward if it simplifies 
development, without requiring a scope exception.

---

# Correction 4 — Exact System Requirements (Previously Undocumented)

The approved Proposal specifies exact software and hardware requirements not currently 
reflected in `04_DEVELOPMENT_GUIDE.md`:

**Admin-side software:** Windows 10/11, Python 3.11 with Flask 3.0, SQLite (built-in), VS Code 
1.88+, Git/GitHub (latest), Semaphore API (Free Developer Tier), Chrome/Edge (latest).

**Client-side software:** Windows 10/11 or Android (mobile access), Chrome/Edge/Safari (latest), 
Bootstrap 5.3 via CDN, Vanilla JS/jQuery via CDN.

**Admin-side hardware:** Intel Core i5/AMD Ryzen 5 or higher, 8–16GB RAM, 512GB SSD, Windows 
10/11 (64-bit), minimum 10 Mbps broadband.

**Client-side hardware:** Desktop, laptop, or mobile device with a browser; Intel Core/AMD Ryzen 
3 or equivalent; 4–8GB RAM; 128–256GB SSD; minimum 10 Mbps connection with optional mobile 
hotspot backup; Wi-Fi router connecting to the central Flask server.

**Correction:** Add these exact specifications to `04_DEVELOPMENT_GUIDE.md`'s "Official 
Technology Stack" section for defense-readiness and environment-setup accuracy.

---

# Correction 5 — Official Methodology Is Agile SDLC, 5 Phases

The approved Proposal defines the project methodology as the **Agile Software Development Life 
Cycle**, in five phases:

1. Planning and Requirements
2. System Design
3. Development and Coding
4. Testing and Review
5. Deployment and Feedback

`08_PROJECT_ROADMAP.md` independently defines a 10-phase breakdown (Research, UI/UX Design, 
Frontend Development, Backend Development, Database Development, Integration, Testing, 
Documentation, Presentation, Capstone Defense).

**Correction:** The 10-phase Roadmap is not wrong — it can stand as a more granular internal 
tracking breakdown — but it must be explicitly mapped back to the 5 official Agile phases so the 
two documents don't appear to describe two different methodologies in a defense setting. 
Suggested mapping:

| Agile Phase (Proposal, official) | Roadmap Phase(s) (internal tracking) |
|---|---|
| 1. Planning and Requirements | Research |
| 2. System Design | UI/UX Design |
| 3. Development and Coding | Frontend Development, Backend Development, Database Development |
| 4. Testing and Review | Integration, Testing |
| 5. Deployment and Feedback | Documentation, Presentation, Capstone Defense |

---

# Correction 6 — Revenue Streams Exist (Business Model, Not Dev Scope)

The approved Proposal includes a Revenue Streams section describing a one-time software 
licensing fee, an optional customization fee, an optional ₱3,000/year support & maintenance 
fee, and an optional ₱1,000–2,000/session training service.

**Correction:** This is business-model content for the written proposal/defense narrative. It 
does not affect UI, development, or database work and requires no code or design changes. Noted 
here only so it isn't lost, and so it can be referenced if the defense panel asks about project 
sustainability or a business case.

---

# Correction 7 — External Entities Beyond the 3 Login Roles

The approved Proposal's Data Flow Diagrams describe four external entities interacting with the 
system: health center staff, barangay officials, patients, and community residents.

**Correction:** This is consistent with the existing 3-role login model (Administrator, Health 
Center Staff, Barangay Official) — "patients" and "community residents" are external entities 
who interact with the system indirectly (e.g., as subjects of patient records, or as SMS/ 
announcement recipients), not as authenticated users with accounts. This does not require a 
4th login role. No correction needed to the role model — noted here only to confirm the 
Proposal's diagrams do not imply a patient-facing login portal, which remains explicitly Out of 
Scope per `01_PROJECT_BIBLE.md`.

---

# Correction 8 — Sample Data Persona Note (Decision Needed, Not a Compliance Issue)

The approved Proposal's author list includes team member **Embodo, Sherwyne D.** This exact name 
is currently used as the in-app Administrator demo persona ("Dr. Sherwyne Embodo") across all 
built UI mockups.

**This is not a documentation error** — it's a project decision that hasn't been explicitly 
confirmed. Options:
- **Keep it** as an intentional signature/tribute from the development team.
- **Replace it** with a fully fictional demo name (per `06_DESIGN_CONTENT_LIBRARY.md`'s existing 
  sample name conventions) to avoid mixing a real team member's identity with fictional demo 
  data during a formal defense.

No default correction applied here — flagged for the project team's decision.

---

# Summary of Actions

| # | Correction | Action Required |
|---|---|---|
| 1 | Core objectives = 4 modules only | Reprioritize messaging; keep User Mgmt/Audit Logs/Settings as supporting infrastructure |
| 2 | Client-Server, Star Topology | Add to `04_DEVELOPMENT_GUIDE.md` |
| 3 | jQuery permitted | Add to `04_DEVELOPMENT_GUIDE.md` |
| 4 | Exact system requirements | Add to `04_DEVELOPMENT_GUIDE.md` |
| 5 | Agile 5-phase methodology | Add mapping table to `08_PROJECT_ROADMAP.md` |
| 6 | Revenue Streams exist | No dev action; note for defense narrative |
| 7 | External entities confirmed | No action; confirms existing role model is correct |
| 8 | "Sherwyne Embodo" persona | Team decision needed — keep or replace |

---

# Source of Truth Priority (Reaffirmed)

1. Approved Capstone Proposal
2. This Reconciliation Notes document
3. 01_PROJECT_BIBLE.md
4. 02_UI_DESIGN_SYSTEM.md
5. 03_SCREEN_SPECIFICATIONS.md
6. 04_DEVELOPMENT_GUIDE.md
7. 05_AI_MASTER_INSTRUCTIONS.md

---

End of Reconciliation Notes.
