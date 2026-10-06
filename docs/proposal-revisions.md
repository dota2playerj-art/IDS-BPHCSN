# Proposal Revisions: Chapter 1 Against the Built System

Prepared: 2026-10-06. Read-only review. No code or other document was changed.

**Sources read.** The approved Proposal (`PR0MPT_INSTRUCTION/Capstone_Proposal.pdf`, all three chapters, 34 PDF pages, with the text and the figures extracted); `PROJECT_STATUS.md` (Task Log to Task 15, decisions, issues); `README.md`; documents 01, 03, 04, 08, 09 and 10 in `PR0MPT_INSTRUCTION/`; and the code wherever a claim needed checking.

**Page numbers** are PDF page numbers (the cover is page 1). The Proposal has no printed page numbers in its text layer.

**Verdicts.** *True*: the code does what the sentence says. *Partly true*: part of the sentence holds. *Not true*: the code does not do it, or does the opposite. *Cannot check*: the claim is an outcome, a hardware figure or a tool choice that the code cannot show.

---

## A. Open issues

Every row of the tracker (`PROJECT_STATUS.md` §5) whose resolution is not marked Done or Accepted.

| ID | Issue | Needs the health center interview? |
|---|---|---|
| H1 | The code side is done. The issue closes only when every team laptop has run the password migration and each flagged account has set its own password. | No |
| H7 | Six plain database copies and 15 zip backups sit in `../classcheck_backups`, outside the repository. They must be archived or deleted. | No |
| M12 | The row still reads "Pre-defense action: push to a private remote". The status note in §7 (2026-10-02) says this is done. The row should be marked Done. | No |
| M19 | Old AI session folders on this laptop still hold real names or old passwords. They must be deleted. | No |
| M35 | The list of visit services (`models/doctor_worklist.py:25-32`) was not confirmed with the health center. Family planning and nutrition are not in it. | **Yes** |
| L11 | Whether a second IPV dose applies is not confirmed. | **Yes** (RHU nurse) |
| L34 | No Restore button, by design. The suggested direction is "Accept", but the row is not marked Accepted. | No |

Pre-defense checklist items in §7 that are not tracker issues: the Service Schedule is empty until the interview (**Yes**, interview); the Semaphore key is not set (No); BitLocker on the presenting laptop is not verified (No); the five demo accounts must change their passwords (No).

Tracker note: the count line in §5 says "7 High, 46 Medium, 54 Low". The table holds 7 High (H1–H7), 49 Medium (M1–M49) and 58 Low (L1–L58), 114 in all. The count line was not updated after Tasks 14 and 15.

---

## B. Claim check

### B.1 General Objective (page 5)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B1 | Develop the IDS-BPHCSN, "a web-based application". | True | Flask application, `app.py:54` `create_app()`. Note: the objective gives the name as "Integrated Digital System for Barangay Poblacion Health Center (IDS-BPHCSN)"; the system's name is "… Health Center Services and Community Notifications" (`config.SYSTEM_NAME`, M9). |
| B2 | It "digitizes health center services and inventory management". | True | Patient records, consultations, immunization, patient queue (`routes/staff.py:108-785`); inventory (`routes/staff.py:333-429`). |
| B3 | It provides "a reliable channel for community notifications". | Partly true | SMS broadcasts exist (`models/broadcasts.py`). Without `SEMAPHORE_API_KEY` every message is saved but not sent (`utils/sms.py:168-176`; README lines 77-79). Messages reach only people whose mobile number is on record (`models/broadcasts.py:47-92`). "Reliable" cannot be checked. |

### B.2 Specific Objectives (pages 5-6)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B4 | SO1: a patient records management module. | True | Patient Records, Register Patient, Patient Profile (`routes/staff.py:108, 322, 687`). |
| B5 | SO1: it "eliminates data retrieval delays". | Cannot check | An outcome. The means exist: the header search and the Patient Records filter (doc 09 §4.1). |
| B6 | SO1: it "minimizes the risk of patient record loss". | Partly true | Encrypted backup download (`routes/admin.py:740`, `utils/backup_crypto.py`) and `restore_backup.py`. Backups are manual: the Administrator downloads them; there is no automatic schedule (Backup Frequency was removed in Task 7). |
| B7 | SO2: a medicine and supplies inventory module. | True | Categories Medicine, Supply and Equipment (`inventory_items.category`); batches (`schema.sql:184`). |
| B8 | SO2: it "prevents stock-outs". | Cannot check | An outcome. Dispensing is refused when usable stock is not enough (`models/dispensing.py:400`, test `verify_inventory_batches.py`). |
| B9 | SO2: "automated low-stock alerts". | Partly true | The alert is computed automatically from usable stock and each item's reorder level (`models/inventory.py:243-259, 528`). It is **shown** in the system (sidebar badge `utils/context.py:299`; dashboards `routes/dashboard_views.py:226`; inventory list; reports). It is **not sent** by SMS or e-mail. |
| B10 | SO2: "real-time stock level monitoring". | True | Dispensing deducts stock in the same transaction as the consultation (`routes/consultation_views.py:1008`); every screen reads stock from the batches when it loads. Screens do not refresh on their own. |
| B11 | SO3: a scheduling module that improves "appointment coordination". | Not true | Advance booking was built and then removed on 2026-09-05 on the adviser's advice (`08_PROJECT_ROADMAP.md:295-299`; `utils/unavailable.py:153-156`: "Visits cannot be booked ahead, by design"). The system has a walk-in Patient Queue instead. |
| B12 | SO3: a community notification module. | True | SMS Notifications; send routes `routes/admin.py:371`, `routes/official.py:108`. |
| B13 | SO3: it expands health information reach "via web and SMS". | Partly true | SMS: yes (simulated without the key). Web: there is no public page. Signed-in users can read past broadcasts on SMS Notifications, and the Official's dashboard lists them as a "Community Announcement Feed" (`routes/official_views.py:167`, `templates/official_dashboard.html:239`). Residents have no web access. |
| B14 | SO4: an automated report generation module. | True | Reports & Analytics, computed from the live tables on request (`routes/report_views.py:304-336`); Excel, PDF and print (`routes/admin.py:389-428`). No report is generated or sent on a schedule. |
| B15 | SO4: it "enables data-driven decision-making". | Cannot check | An outcome. |
| B16 | SO4: "consolidated health service summaries and inventory status reports". | True | Patient, consultation, queue, immunization, dispensing, inventory and SMS figures in one report (`routes/report_views.py:310-329`). |

### B.3 Scope (pages 6-7)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B17 | Manages patient records, including personal information and consultation history. | True | Patient Profile tabs (doc 09 §1, screen 5); `templates/patient_profile.html`. |
| B18 | Can monitor and update the inventory of medicines and medical supplies. | True | Receive stock `models/inventory.py:859`; Remove from stock `:888`; Edit details. Test `verify_inventory_batches.py`. |
| B19 | **Sends** automated low-stock alerts to health center staff below defined thresholds. | Partly true | The thresholds and the alert exist (B9). Nothing is sent: the alert appears only when a user opens the system. |
| B20 | Enables the scheduling of **appointments**. | Not true | See B11. |
| B21 | Enables the scheduling of **health center activities**. | Partly true | The Service Schedule records which services run on which weekdays (`models/service_schedule.py`; `routes/admin.py` schedule routes). It has no dated events, and it ships empty until the interview (§7 item 4). |
| B22 | **Can post announcements.** | Not true | No web page posts an announcement separate from an SMS broadcast. There is no announcements route or table. Community Announcements was a static template with no data and was retired (doc 09 §1.1; `routes/official.py:3`; `migrations/migrate_drop_schedule_logs.py`). The Official's "Community Announcement Feed" only lists SMS broadcasts already sent (B13). |
| B23 | SMS feature allows officials to send alerts to basic cellphones. | Partly true | The Administrator and the Barangay Official can send (`routes/admin.py:371`, `routes/official.py:108`); messages are plain SMS, so basic phones can receive them. They go out only when a Semaphore key is set (`utils/sms.py:168-176`). |
| B24 | "… to ensure residents without internet access stay informed". | Partly true | Recipients are registered patients with a valid mobile number, senior patients, parents or guardians of patients under 5, and health center personnel (`models/broadcasts.py:68-92`). "Entire Barangay / All Residents" is listed as unavailable: the system holds no resident contact list (`models/broadcasts.py:47-54`). |
| B25 | Generates reports on medicines distributed. | True | `get_dispensing_stats()` `models/dispensing.py:757`. |
| B26 | … current stock levels. | True | `get_inventory_report()` `models/inventory.py:488`. |
| B27 | … patient consultation summaries. | True | `get_consultation_report()` `models/consultations.py:504`. |
| B28 | … appointment records. | Partly true | The report covers walk-in visits by status and service (`get_appointment_report()` `models/appointments.py:1384`). There are no booked appointments. |
| B29 | Accessible via standard web browsers on **desktop** devices. | Partly true | True on the computer that runs the server. As installed, the server listens on that computer only: `app.run(host="127.0.0.1", port=5001)` (`app.py:94`). Other desktops cannot connect without a change to this setting. |
| B30 | Accessible via standard web browsers on **mobile** devices. | True (since Task 16 and 17) | Phones can connect in network mode (B29) and every screen is usable at 360 px and up (B.8, update after Task 17). Checked in Chromium emulating a phone, not yet on a real phone (L62, L64). |
| B31 | Developed using Python, Flask, SQLite, Bootstrap 5, HTML, CSS, JavaScript and the Semaphore API. | True | `requirements.txt:1` (Flask 3.1.3); `static/css/bootstrap.min.css` (Bootstrap v5.3.3); `utils/sms.py:31` (Semaphore). The system also uses Chart.js 4.4.4, openpyxl, fpdf2, Flask-WTF, cryptography and python-dotenv (`requirements.txt`). |

### B.4 Limitation (page 7)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B32 | Requires a stable internet connection to access all features. | Not true | Every file the screens use is stored under `static/`; no page loads anything from the internet (README lines 70-72; `templates/base.html:13-14, 470-471`). Internet is needed only to send live SMS (`utils/sms.py:31`, `https://api.semaphore.co`) and once for `pip install` (README line 41). |
| B33 | Does not support offline functionality; all features are inaccessible without internet. | Not true | Same evidence as B32. All features except live SMS work with no internet. |
| B34 | Does not support telemedicine or remote medical diagnosis. | True | No video, messaging or remote-consultation feature exists in `routes/`. |
| B35 | Does not support clinical decision-support functionalities. | Partly true | No diagnostic support. But the immunization rules are rule-based support: the system refuses a dose before its minimum age or interval and computes the earliest date each dose can be given (`DOSE_RULES` `models/immunizations.py:83-96`; `dose_eligibility()` `:390`; `dose_due()` `:465`). |
| B36 | Limited to Barangay Poblacion Health Center; no integration with national health databases such as the PHIE. | True | One `settings` record holds one health center's details (`schema.sql:570`). The only outside connection is the Semaphore SMS call. |
| B37 | Does not implement enterprise-grade security measures; governed by RA 10173. | Partly true | No two-factor authentication, single sign-on or HTTPS (`app.py:94` serves plain HTTP). But the system has much more than the sentence suggests: hashed passwords and forced change at first sign-in, a sign-in pause after 5 wrong passwords (`utils/login_throttle.py:14`), 30-minute idle and 12-hour limits (`config.py:66-68`), form tokens (Flask-WTF), an audit trail (`models/audit.py:625`), AES-256-GCM for sealed consultations and backups (`utils/sealed_crypto.py`, `utils/backup_crypto.py`). Tests: `verify_security_basics.py`, `verify_csrf.py`, `verify_sealed_privacy.py`. |
| B38 | SMS is limited to text and does not support images or attachments. | True | The gateway call sends one text field (`utils/sms.py:24-28`). Also: there is no route that receives replies. |

### B.5 Table 1, software specification (pages 21-23)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B39 | Admin side: Windows 10 / Windows 11. | Partly true | Built and tested on Windows 11. Windows 10: not tested. |
| B40 | Python 3.11 with Flask 3.0. | Not true | Flask 3.1.3 (`requirements.txt:1`). The team laptop's environment runs Python 3.14.6. Python 3.11 was not tested. |
| B41 | SQLite (built in with Python). | True | `database/connection.py`; one file, `app.db`. |
| B42 | Visual Studio Code 1.88 or higher. | Cannot check | An editor choice; the code does not depend on it. |
| B43 | Git / GitHub. | True | Git history on `master`; the remote is a GitHub repository. |
| B44 | Semaphore API (Free Developer Tier). | Partly true | The Semaphore call is built (`utils/sms.py:13-43`). No key is set, so it runs in Simulated mode. The account tier cannot be checked from the code. |
| B45 | Admin browser: Chrome / Edge, latest. | Cannot check | Standard HTML; no browser-specific code. No browser test is recorded in the repository for this review. |
| B46 | Client side: Windows 10/11 or Android. | Partly true | Windows: on the server computer only (B29). Android phones: not usable (B30). |
| B47 | Client browser: Chrome / Edge / Safari, latest. | Cannot check | As B45. |
| B48 | Bootstrap 5.3 "accessed via CDN, no installation". | Partly true | Bootstrap is 5.3.3, but it is a local file (`static/css/bootstrap.min.css`, `static/js/bootstrap.bundle.min.js`). **No CDN** is used. |
| B49 | JavaScript: Vanilla JS, jQuery (CDN-based). | Partly true | Plain JavaScript only. **No jQuery** in the project: the only matches for "jquery" are inside the vendored Bootstrap and Chart.js files. **No CDN.** |

### B.6 Table 2, hardware specification (pages 23-25)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B50 | Admin side: Core i5 / Ryzen 5, 8-16 GB RAM, 512 GB SSD, 64-bit Windows. | Cannot check | No performance test was recorded. The system is one Flask process and one SQLite file. |
| B51 | Admin side: minimum 10 Mbps stable broadband. | Not true | Not needed to run the system (B32). Live SMS needs some internet connection; its speed is not measured. |
| B52 | Admin side: keyboard and mouse. | True | All input is through web forms. |
| B53 | Client device: desktop, laptop or mobile device with a browser. | Partly true | Desktop or laptop: yes, on the server computer (B29). Mobile: no (B30). |
| B54 | Client: Core / Ryzen 3, 4-8 GB RAM, 128-256 GB SSD. | Cannot check | Not measured. |
| B55 | Client: minimum 10 Mbps connection, optional mobile hotspot. | Not true | Clients need no internet (B32). |
| B56 | Network equipment: Wi-Fi router with a stable connection to the Flask server. | Not true (as installed) | The server accepts connections only from its own computer (`app.py:94`). A router is needed only if the team opens the server to the local network (question G3). |

### B.7 System Architecture paragraph (page 25) and its figure (page 26)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| B57 | Client-server architecture. | True | One Flask server; users work through a browser. |
| B58 | Star topology "during both development and deployment", with staff, officials and the administrator on their own computers or mobile devices. | Not true (as installed) | The server listens on 127.0.0.1 (`app.py:94`), so only the server computer can use it. Mobile devices are not supported (B30). The figure also shows three clients and omits the Doctor. |
| B59 | All database operations and application logic are centralized on the Flask server. | True | Every connection goes through `db_connection()` (`database/connection.py`); one `app.db`. |
| B60 | No software installation is needed at the client side. | True | Clients need only a browser. The server computer needs Python and the packages (README "Getting started"). |

### B.8 Phone-width check (390 px)

**Method.** A scratch script (not in the repository) signed in as each of the four roles on the suites' temporary test database (`tests/_support.py`, never `app.db`), loaded every sidebar page (32 pages) and the sign-in page through the Flask test client, and read the layout rules each page ships. The CSS in `templates/base.html` and each template was also read. No page was rendered in a real browser.

**Results.**

- All 32 signed-in pages returned 200. All 32 use the same fixed sidebar: `.sidebar{width:280px; position:fixed}` and `.main-wrap{margin-left:280px}` (`templates/base.html:39-41, 66`).
- No signed-in page has a `max-width` media query, and none has a menu toggle (no offcanvas or hamburger button). The sidebar never collapses.
- At 390 px, the sidebar covers 280 px and leaves about **110 px** for the page content.
- The header search box is a fixed 340 px wide, inside 32 px side padding (`templates/base.html:66-77`). It cannot fit in 110 px, so the page scrolls sideways.
- The 32 pages hold 51 tables. None is wrapped in Bootstrap's `table-responsive`.
- Bootstrap's grid classes still adapt, but they adapt to a 110 px column.
- Only one template has a small-screen rule: `patient_profile_demographics.html:32` (`max-width: 575px`), the Administrator's demographics profile.
- The sign-in page has no media query. Its brand panel (`flex:0 0 44%`, `templates/login.html:33-35`) and the form panel stay side by side. At 390 px the form panel is about 218 px wide, less 64 px of padding, so the sign-in card gets about 154 px.
- Doc 09 §6 already states the design rule: "desktop-first (min width 1366px … ). Mobile is a secondary, graceful-degradation target only." The roadmap lists responsive testing as not done (`08_PROJECT_ROADMAP.md:259-260`).

**Verdict:** the screens work at desktop and laptop widths. They do not work on a phone-width browser.

**Update after Task 17 (M51).** Below 992 px the sidebar is a slide-in menu (`static/css/responsive.css`), the header stays one line, every table scrolls inside its own `.table-responsive` box, fields are one column, dialogs are full screen below 576 px, and every button, link and checkbox is at least 44 by 44 px. `tests/verify_mobile_layout.py` opens every screen and dialog in a real browser at 360, 390 and 1366 px as each of the four roles and checks all of this. The Proposal's statement about mobile devices (B30, B53) is now true as written, with the real-phone caveat in L64.

### B.9 Summary of Not true findings

B11 and B20 (appointments), B22 (post announcements), B30 (mobile devices), B32 and B33 (internet required; no offline use), B40 (Python 3.11 with Flask 3.0), B51 and B55 (10 Mbps internet), B56 (Wi-Fi router to the server, as installed), B58 (star topology with clients on their own devices, as installed).

---

## C. Proposed revisions to Chapter 1

Each item gives the action, the proposed text (for REVISE and ADD), and one line on what drove the change. "As built" means the change only makes the text match the code; no adviser point, law or standard drove it.

### C.1 General Objective

**REVISE.** The main objective of this project is to develop the Integrated Digital System for Barangay Poblacion Health Center Services and Community Notifications (IDS-BPHCSN), a web-based application that digitizes the health center's patient records, consultations, immunization records, daily patient queue and medicine inventory, and provides an SMS channel for community notifications.

*Reason:* the full system name (as built, `config.SYSTEM_NAME`); immunization added under the DOH EPI schedule; "reliable channel" replaced by the channel that exists (B3).

### C.2 Specific Objectives

**SO1 — REVISE.** To design and develop a patient records management module that stores each patient's personal information, consultation history, immunization record and dispensed medicines, lets authorized users find a record by name or patient ID, and protects the records through role-based access, an audit trail and encrypted backups.

*Reason:* adviser feedback (the Doctor role) and RA 10173 and RA 11166 require access by role; the outcome claims (B5, B6) are replaced by what the module does.

**SO2 — REVISE.** To develop a medicine and supplies inventory module that records stock by delivery batch with its lot number and expiry date, identifies medicines by generic name, dispenses the batch that expires first, and shows low-stock and expiry alerts within the system.

*Reason:* adviser feedback (batches and expiry; generic names), RA 6675 (Generics Act) and FEFO; alerts are shown, not sent (B9).

**SO3 — REVISE.** To design and develop a patient queue module and a community notification module that organize the health center's daily walk-in visits in order of arrival, show which services the health center offers on which days, and send health announcements by SMS.

*Reason:* adviser feedback (walk-in queue instead of advance booking, B11); no web announcement feature was built (B13, B22).

**SO4 — REVISE.** To develop an automated report generation module that compiles patient, consultation, immunization coverage, patient queue, medicine dispensing, inventory and SMS summaries over a selected date range, and prints or exports them to Excel and PDF, to support planning by the health center and the barangay.

*Reason:* adviser feedback (walk-in queue: "appointment" becomes "patient queue"); DOH EPI coverage figures; the report contents as built (B16, B25-B28).

### C.3 Scope

| # | Proposal bullet | Action | Proposed text | Reason |
|---|---|---|---|---|
| S1 | The system manages patient records, including personal information and consultation history. | REVISE | The system manages patient records, including personal information, consultation history, immunization records and medicines dispensed. Clinical data is shown only to the care team, the Doctor and Health Center Staff. | Adviser feedback (the Doctor role); RA 10173, RA 11166 and the HIPAA minimum-necessary standard. |
| S2 | The system can monitor and update the inventory of medicines and medical supplies. | REVISE | The system monitors and updates the inventory of medicines, medical supplies and equipment. Each delivery is recorded as a batch with its lot number, expiry date, source and quantity, and each medicine is named by its generic name, strength and dosage form. | Adviser feedback (batches and expiry; generic names); RA 6675. |
| S3 | The system sends automated low-stock alerts to health center staff when medicine or supply quantities fall below defined threshold levels. | REVISE | The system shows a low-stock alert on the dashboards, the inventory list and the menu when the usable stock of an item falls to or below its reorder level. It also marks batches that have expired or will expire within 90 days. | Alerts are shown, not sent (B19); adviser feedback (batches and expiry). |
| S4 | — | ADD (after S3) | The system dispenses medicines from the batch with the earliest expiry date first, and it never dispenses from an expired batch. | FEFO; adviser feedback (batches and expiry). |
| S5 | The system enables the scheduling of appointments and health center activities. | REVISE | The system manages a daily walk-in patient queue. Staff check in each patient with the service needed, and patients are seen in the order they arrive. The system does not book appointments in advance. | Adviser feedback (walk-in queue). |
| S6 | — | ADD (after S5) | The system records which services the health center offers on which days of the week, and shows the services of the day on the patient queue. | Successor to booking after the adviser's feedback (walk-in queue); `models/service_schedule.py`. |
| S7 | The system can post announcements. | REMOVE | — | Not built; SMS is the one notification channel (doc 09 §1.1; B22). Final wording depends on question G1. |
| S8 | The system includes an SMS notification feature allowing officials to send alerts to basic cellphones to ensure residents without internet access stay informed. | REVISE | The system includes an SMS notification feature that allows the Administrator and the Barangay Official to send text messages to the basic cellphones of registered patients, parents or guardians of children under five, senior citizens and health center personnel whose mobile numbers are on record. Messages are sent through the Semaphore SMS gateway. | As built (B23, B24); recipients are limited to contacts on record. |
| S9 | The system generates reports in terms of medicines distributed, current stock levels, patient consultation summaries, and appointment records. | REVISE | The system generates reports on patients, consultations, immunization coverage, patient queue visits, medicines dispensed, current stock levels, expiring batches and SMS broadcasts, and prints or exports them to Excel and PDF. In reports for the Administrator and the Barangay Official, any count from one to four is grouped as "Other" to protect privacy. | Adviser feedback (walk-in queue; batches and expiry); DOH EPI; RA 10173 and the HIPAA minimum-necessary standard (small counts). |
| S10 | The application is developed as a web-based system accessible via standard web browsers on both desktop and mobile devices. | REVISE | The application is a web-based system used through a standard web browser on a desktop or laptop computer. | As built (B29, B30, B.8). Final wording depends on questions G2 and G3. |
| S11 | The system is developed using Python with the Flask web framework …, SQLite …, Bootstrap 5, HTML, CSS, and JavaScript …, and Semaphore API …. | REVISE | The system is developed using Python with the Flask 3.1 web framework for the backend, SQLite for the database, Bootstrap 5.3, HTML, CSS and plain JavaScript for the interface, Chart.js for charts, openpyxl and fpdf2 for Excel and PDF files, and the Semaphore API for SMS. All interface files are stored on the server, and no content delivery network (CDN) is used. | As built (B31, B40, B48, B49). |
| S12 | — | ADD | The system has four user roles: the Administrator, the Doctor, Health Center Staff and the Barangay Official. Only the Doctor writes the diagnosis and treatment plan, seals a confidential consultation, and declares a patient deceased. | Adviser feedback (the Doctor role). |
| S13 | — | ADD | The system records consultations. Health Center Staff record the intake, which covers the complaint, vital signs, vaccines given and medicines dispensed. A visit that needs a diagnosis waits for the Doctor and cannot be completed without one. | Adviser feedback (the Doctor role); `models/appointments.py:776` `_completion_blocked()`. |
| S14 | — | ADD | The system tracks the immunization of children against the routine schedule of the DOH Expanded Program on Immunization. It accepts a dose only when the child has reached the minimum age and the minimum interval, shows the earliest date each dose can be given, and records doses given elsewhere with their proof. A dose with nothing on file is shown as "No record", not "Overdue". | Adviser feedback ("No record" instead of "Overdue"; vaccine timing); DOH EPI; WHO; CDC General Best Practices; HL7 FHIR. |
| S15 | — | ADD | The system lets the Doctor seal a confidential consultation. The written details of a sealed visit are stored encrypted, and only the Doctor can read them. | RA 11166 (Section 44); RA 10173. |
| S16 | — | ADD | The system keeps an audit trail of sign-ins and of every change to patient, consultation, inventory, queue, account and settings records. It allows the Administrator to manage user accounts, system settings, maintenance mode and encrypted backups. | RA 10173 (security of sensitive personal information). |

### C.4 Limitation

| # | Proposal bullet | Action | Proposed text | Reason |
|---|---|---|---|---|
| L1 | The system requires a stable internet connection to access all features and perform operations. | REVISE | The system runs on the health center's computer and does not need an internet connection, except to send SMS through the Semaphore gateway and to install the software packages once. | Not true as written (B32); as built. |
| L2 | The system does not support offline functionality; all features are inaccessible in the absence of an internet connection. | REMOVE | — | Not true (B33); replaced by L1. |
| L3 | — | ADD | As installed, the system is used on the computer that runs it. Use from other computers on the health center's network needs a change to the server setting. | As built (`app.py:94`). Keep or drop according to question G3. |
| L4 | The system does not support telemedicine, remote medical diagnosis, or clinical decision-support functionalities. | REVISE | The system does not support telemedicine, remote medical diagnosis or diagnostic decision support. Its only clinical rules are the immunization schedule checks of minimum age and minimum interval. | The vaccine-timing rules are decision support (B35); adviser feedback (vaccine timing); WHO. |
| L5 | The system is limited to Barangay Poblacion Health Center and does not integrate with national health databases such as the Philippine Health Information Exchange. | REVISE | The system serves one health center per installation, Barangay Poblacion Health Center, and does not exchange data with national health databases such as the Philippine Health Information Exchange. | As built (B36). |
| L6 | The system does not implement enterprise-grade security measures and is governed by the Data Privacy Act of 2012 (Republic Act No. 10173). | REVISE | The system protects data through password sign-in, role-based access, session time limits, an audit trail, and AES-256-GCM encryption of sealed consultations and backups, in line with the Data Privacy Act of 2012 (Republic Act No. 10173). It does not provide two-factor authentication, single sign-on or encrypted (HTTPS) network connections. | RA 10173; RA 11166; as built (B37). |
| L7 | The SMS notification feature is limited to text-based messages only and does not support multimedia content such as images or attachments. | REVISE | The SMS notification feature sends one-way, text-only messages. It does not receive replies and does not support images or attachments. | As built (B38). |
| L8 | — | ADD | Without a Semaphore API key, the system saves SMS messages but does not send them, and its screens show "SMS mode: Simulated". | As built (`utils/sms.py:164-176`). |
| L9 | — | ADD | The immunization module follows the routine DOH EPI schedule for infants. It does not cover outbreak or catch-up campaigns that use other ages, and its schedule rules cannot be overridden. | DOH EPI; adviser feedback (vaccine timing; no override, Bible Task 13 D5). |
| L10 | — | ADD | A dose that a parent reports without a vaccination card is recorded, but it is not counted as given. | CDC General Best Practices; HL7 FHIR (`reportOrigin` recall); adviser feedback ("No record"). |
| L11 | — | ADD | Each dose is judged against the previous valid dose of its series. A dose given after a dose that does not count is also marked for the Doctor's review, so the system may suggest more repeats than a full review of the valid doses would. | CDC General Best Practices; tracker L55 (accepted). |
| L12 | — | ADD | The encryption key is kept on the same computer as the database. Full-disk encryption (such as BitLocker) is recommended on that computer, and the Doctor keeps a printed copy of the key. | RA 10173; tracker M23. |
| L13 | — | ADD | The Administrator downloads backups when needed; there is no automatic backup schedule. A backup is restored with a script on the health center computer, not from a screen. | As built (B6; tracker L34). |
| L14 | — | ADD | The screens are designed for desktop and laptop computers and are not suited to phone-width browsers. | As built (B.8). Keep or drop according to question G2. |

### C.5 Other Chapter 1 text

These sentences are outside the objectives, scope and limitation, but they are in Chapter 1 and no longer match the system.

| Where | Current text | Action | Proposed text | Reason |
|---|---|---|---|---|
| Project Context, last paragraph (page 4) | "… consolidates patient records management, medicine inventory tracking, appointment scheduling, and community health notifications …" | REVISE | "… consolidates patient records and consultations, immunization tracking, medicine inventory, a daily patient queue, and community health notifications by SMS …" | Adviser feedback (walk-in queue); DOH EPI. |
| Purpose and Description (page 4) | "… it allows multi-user access across different devices without requiring software installation …" | REVISE | "… it is used through a standard web browser, so the application does not have to be installed on each user's device …" | As built (B29). Revisit after question G3. |
| Purpose and Description (page 4) | "As the staff utilizes the system, they can easily monitor stock levels and generate reports …" | REVISE | "As the staff use the system, they can monitor stock levels and export patient, inventory and queue lists, while the Doctor, the Administrator and the barangay officials can view summary reports …" | As built: Health Center Staff have list exports (`routes/staff.py:128-180, 343-353, 453-463`) but no Reports & Analytics (permission matrix, `PROJECT_STATUS.md` §3). |
| Purpose and Description (page 4) | "… barangay officials can use the platform to broadcast health-related announcements directly to residents." | REVISE | "… barangay officials can use the platform to send health announcements by SMS to registered residents." | As built (B24). |
| Pages 4, 12, 27 | "IDS-BPICSN" | REVISE | "IDS-BPHCSN" | Spelling of the acronym. |

---

## D. Features built beyond the Proposal

| # | Feature | What it does | Why it was added |
|---|---|---|---|
| D1 | Doctor role | A fourth role. Only the Doctor writes the diagnosis and treatment plan, seals a consultation, reads sealed text and declares a death (`utils/roles.py:47`). | Adviser feedback: the Administrator is a barangay official, not a physician. |
| D2 | Consultation records | Intake by Staff (complaint, five vital signs, growth measurements, vaccines, dispensing); diagnosis by the Doctor (`templates/record_consultation.html`). | The Proposal named consultation history but no screen to write it. |
| D3 | Visit flow and the Doctor's list | Statuses Waiting, In Consultation, Waiting for the Doctor, Completed and Left before being seen; "Send to the Doctor"; the Doctor's list of waiting visits (`models/doctor_worklist.py:109`; `models/queue_actions.py`). | Adviser feedback (the Doctor role); no visit that needs a diagnosis may close without one. |
| D4 | Walk-in Patient Queue with service at check-in | Check-in with a required service from a fixed list; one patient in consultation at a time; same-day undo of "Left" (`models/appointments.py:609`). | Adviser feedback: a government health center sees patients in order of arrival. |
| D5 | Service Schedule | Which services run on which weekdays; edited by the Administrator, read by all. | Successor to advance booking (adviser feedback, walk-in queue). |
| D6 | Immunization tracking (DOH EPI) | The infant schedule, a status for each dose, coverage figures, and the follow-up list (`models/immunizations.py:36, 689, 1063`). | Not in the Proposal; the health center's main child service. |
| D7 | Proof for doses given elsewhere | Evidence types "given here", "card" and "parent report"; "Record dose given elsewhere"; "No record" instead of "Overdue" (`models/immunizations.py:1682`). | Adviser feedback; CDC General Best Practices; HL7 FHIR. |
| D8 | Vaccine timing, repeats and due dates | A dose only from its minimum age and interval; doses given too early are flagged and can be repeated; the due date is the earliest date a dose can be given (`models/immunizations.py:301, 390, 465, 501`). | Adviser feedback (vaccine timing); WHO tables; ACIP 4-day grace (CDC). |
| D9 | Ages in days, weeks, months and years | One helper on every screen (`models/patients.py:248`). | Found in use: staff could not tell a 5-week-old from a 6-week-old. |
| D10 | Other vaccinations | Records vaccines given at any age outside the infant schedule: Hepatitis B, tetanus, influenza, pneumococcal, COVID-19, rabies or another named vaccine (`models/general_vaccinations.py:17-24`). | The health center gives these vaccines too, and the EPI schedule does not cover them. |
| D11 | Dispensing from consultations | Medicines and supplies dispensed at a visit, deducted from stock (`models/dispensing.py:400`). | Links stock to care; needed for "medicines distributed" reports. |
| D12 | Batches, expiry and FEFO | Receive stock, Remove from stock with a reason, Expired and Expiring soon, FEFO dispensing (`models/inventory.py:859, 888`). | Adviser feedback (batches and expiry); FEFO. |
| D13 | Generic names | A medicine is generic name + strength + dosage form; the brand belongs to the batch (`models/inventory.py:41`). | Adviser feedback; RA 6675. |
| D14 | Sealed consultations | Free text of a sealed visit encrypted with AES-256-GCM; key envelope for the Doctor (`models/consultations.py:227`; `export_sealed_key.py`). | RA 11166 Section 44; RA 10173. |
| D15 | Care-team-only clinical data | The Administrator sees demographics and counts only; the Official sees no patient records. | RA 10173; RA 11166; HIPAA minimum necessary. |
| D16 | Small counts and masked numbers | Counts of 1 to 4 fold into "Other" for the Administrator and the Official; phone numbers show the last four digits (`utils/small_counts.py:33`; `utils/phone.py:58`). | RA 10173; HIPAA minimum necessary. |
| D17 | Audit trail and Audit Logs screen | One short entry for every record change and sign-in, written with the change; no clinical text (`models/audit.py:625`; `routes/admin.py:593`). | RA 10173 (accountability for sensitive data). |
| D18 | Account security | User Management, My Account, forced password change, sign-in pause, session limits, form tokens (`routes/admin.py:441`; `utils/login_throttle.py`). | RA 10173; tracker issues H1, H2, M2, M3. |
| D19 | Settings, maintenance mode and encrypted backup | Health center details, closing the system for maintenance, and a backup download as one encrypted file (`routes/admin.py:724, 740`; `restore_backup.py`). | RA 10173 and its NPC circular on backup and restore. |
| D20 | Barangay Official screens | Health Programs, Vaccination Campaigns and Community Reports, built from the same figures as Reports & Analytics. | The Official needs community figures without patient data. |
| D21 | Excel, PDF and print | Exports of reports, patient lists, inventory, the queue, audit logs and accounts. | Reports must leave the system for meetings and files. |
| D22 | Patient status | Active, Inactive and Deceased; only the Doctor sets Deceased (`models/patients.py:158`). | Adviser feedback (the Doctor role). |
| D23 | Fictional demo data and automated tests | `seed_demo_data.py` builds invented data through the real screens; 25 test suites, 2767 checks after Task 15. | Privacy of real people (RA 10173); evidence for Phase 4 Testing. |

---

## E. New or changed limitations

Honest limits of the system as built. The last column says where Section C covers it.

| # | Limitation | Evidence | In C? |
|---|---|---|---|
| E1 | Routine DOH EPI infant schedule only. No outbreak or catch-up campaign ages; no override of the rules. | Bible, Task 13 D5; `models/immunizations.py:83-96` | L9 |
| E2 | A second IPV dose is not in the schedule until the interview confirms it. | Tracker L11 | — |
| E3 | Parent-reported doses are recorded but do not count as given. | Bible, Task 9; CDC | L10 |
| E4 | Doses are judged by record against the previous valid dose, not recounted by valid sequence; a dose after an invalid one is also flagged. | Tracker L55 | L11 |
| E5 | A card dose given too early and its repeat cannot both be saved at one consultation; the early dose must be recorded from the profile first. | Tracker L56 | — |
| E6 | No advance appointment booking; walk-in only. | `utils/unavailable.py:153-156` | S5 |
| E7 | The list of visit services is fixed in the code; the Service Schedule ships empty. | Tracker M35; §7 item 4 | — |
| E8 | SMS is simulated without a Semaphore key. Live SMS needs internet. | `utils/sms.py:164-176` | L8, L1 |
| E9 | SMS is one-way and text-only, and reaches only contacts on record; no "all residents" or "pregnant women" audience. | `models/broadcasts.py:47-62` | L7, S8 |
| E10 | Low-stock and expiry alerts are shown in the system, not sent. | B9 | S3 |
| E11 | Restore is by script (`restore_backup.py`), not a screen. Backups are manual downloads. | Tracker L34; README "Restoring a backup" | L13 |
| E12 | The encryption key is on the same computer as the database. Full-disk encryption is recommended. If the key is lost, sealed records cannot be opened. | Tracker M23; README "Sealed records" | L12 |
| E13 | For a sealed visit, the visit date, vital signs, immunizations and the fact of the seal stay readable to Staff, by design. | Tracker L19 | — |
| E14 | No two-factor authentication and no single sign-on. | Tracker L5 | L6 |
| E15 | Plain HTTP. If the server is opened to the network, passwords and health data travel unencrypted on the Wi-Fi unless HTTPS is added. | `app.py:94` (no TLS setting) | L6, G3 |
| E16 | As installed, only the server computer can use the system. | `app.py:94` | L3 |
| E17 | Screens are not usable at phone width. | B.8 | L14, S10 |
| E18 | One health center per installation. | `schema.sql:570` | L5 |
| E19 | Pregnancy is not recorded; prenatal care exists only as a visit service. | `models/broadcasts.py:55-60` | — |
| E20 | A refused form submission with nobody signed in (for example, on the sign-in page) leaves no audit entry. | Tracker M20 | — |
| E21 | The Barangay Official sees exact immunization counts; the small-count rule does not cover them, by decision. | Tracker L28, L47 | — |

---

## F. Other parts of the Proposal now out of date

| # | Place (PDF page) | What no longer matches | Suggested change |
|---|---|---|---|
| F1 | Chapter 1, Project Context and Purpose (pages 2-5) | Appointment scheduling; multi-device access; staff generating reports; "IDS-BPICSN". | See C.5. |
| F2 | Chapter 2 introduction (page 8) | Lists "scheduling" among the needs reviewed. | Optional: say "patient queue and scheduling". The literature itself needs no change. |
| F3 | Chapter 3 introduction (page 16) and Conceptual Framework text (pages 16-17) | "appointment scheduling", "Appointment details", "scheduling, and notification dispatch". | Name the patient queue, consultations and immunization. |
| F4 | Figure 1, IPO model (page 17) | Inputs include "Appointment Details" and "Health Announcements"; the process box "Scheduling & Notification Module"; no consultation or immunization. | Inputs: patient information, consultation and vital-sign data, immunization records, medicine and supply batches, visit check-ins, SMS messages. Process: the four revised modules. |
| F5 | Methodology, Phase 1 (page 19) | "User roles were also defined Admin, Health Center Staff and Barangay Official" (three roles). | Four roles, with the Doctor, and the reason (adviser feedback). |
| F6 | Methodology, Phase 1 and Phase 3 (pages 19-20) | "appointment scheduling"; "scheduling and notifications" as a core module. | "patient queue and notifications". |
| F7 | Methodology, Phase 4 (page 20) | Describes module and usability testing only. | Optional: mention the 25 automated test suites (`tests/run_all.py`). Usability testing with staff cannot be checked from the repository. |
| F8 | Methodology, Phase 5 (pages 20-21) | "accessible via a standard web browser on both desktop and mobile devices". | Desktop and laptop only (B.8), unless G2 changes it. |
| F9 | System Requirements, Tables 1 and 2 (pages 21-25) | Flask 3.0 (now 3.1.3); Python 3.11 (tested on 3.14.6); Bootstrap and jQuery "via CDN" (local files, no jQuery); 10 Mbps internet for admin and client; Wi-Fi router; Android clients. | Replace with the versions in S11; state that internet is needed only for live SMS and the one-time install; decide the network rows after G3. |
| F10 | System Architecture paragraph and figure (pages 25-26) | Star topology with clients on their own devices; three clients (Health Center Staff, Administrator, Barangay Official); no Doctor. | Add the Doctor; state how the server is reached after G3; remove mobile devices unless G2 changes it. |
| F11 | Figure 3, Existing Context Diagram, and Figure 4, Existing Data Flow Diagram (pages 26-28) | They describe the manual system. | No change needed. |
| F12 | Figure 5, Proposed Context Diagram, and its text (page 29) | Residents "Request Appointments / Request Medicine" and "View Web Announcements"; "BHW/Admin" "Upload Announcement", "Schedule Appointment". The text names four entities; the figure shows two. No Doctor, no Barangay Official, no SMS gateway. | Entities: Administrator, Doctor, Health Center Staff, Barangay Official, Patients/Residents (receive SMS only; they do not use the system), Semaphore SMS gateway. Remove appointments and web announcements. |
| F13 | Figure 6, Proposed Data Flow Diagram, and its text (pages 30-31) | Process 3.0 "Scheduling Management"; 4.0 "Save announcements"; residents "View announcements on the website"; Process 4.0 drawn twice; "Appointment details" flows into 2.0 Medicine Inventory and "Report request" into 3.0 Scheduling (labels crossed); Health Center Staff "Generate reports"; no Doctor; no consultation, immunization or dispensing process; one undivided data store. | Redraw with processes for patient records, consultations and immunization, inventory and dispensing, patient queue, SMS notifications, reports, and system administration; add the Doctor; show the data stores (17 tables in `schema.sql`). |
| F14 | Database design / ERD | The section "Process model and data design" holds no ERD or data dictionary. | If the final manuscript needs one, it must show the 17 tables in `schema.sql`, including `inventory_batches`, `medicine_dispensing_batches`, `immunizations` (with `evidence`) and `service_schedule`. |
| F15 | Use case diagram | None in the Proposal. | If one is required, use the four roles and the permission matrix in `PROJECT_STATUS.md` §3. |
| F16 | Screen list | None in the Proposal. | The built system has 21 screens (doc 09 §1). |
| F17 | Project Schedule, Gantt chart (page 32) | Months are labelled 2025, while the Proposal is dated May 2026 and the repository history runs from 2026-08-14 to 2026-10-04. Task 4.3 is "Scheduling & Notification Module". | Correct the year and the dates from the team's records; rename task 4.3. |
| F18 | Revenue Streams (pages 33-34) | Support fee covers "database backups". | No change needed; training would now cover four roles. |

---

## G. Questions for the team

| # | Question | Why it matters |
|---|---|---|
| G1 | Remove the scope item "The system can post announcements", or build a simple announcements page? If a page is built, who reads it? Residents have no accounts. | Decides S7, B13 and Figures 5 and 6. Doc 09 §1.1 recorded the decision to keep SMS as the only channel. |
| G2 | Make the screens work on phones (a collapsible sidebar and scrolling tables), or state desktop and laptop only? | Decides S10, L14 and the client rows of Tables 1 and 2. |
| G3 | Keep the server on the one computer (127.0.0.1), or open it to the health center's local network? If opened, will the team add HTTPS and a firewall rule? | Decides L3, the System Architecture paragraph, the star-topology figure and the Wi-Fi router row. Opening it without HTTPS sends passwords and health data in plain text on the Wi-Fi (E15). |
| G4 | Will the team set a Semaphore key and show live SMS at the defense? | Decides whether Chapter 1 says the system "sends" SMS or "can send" it once a key is set (L8). |
| G5 | Which Python version should the Proposal state: 3.11, as approved, or the version actually tested (3.14.6)? | B40. A stated version should be one the team has run the tests on. |
| G6 | Keep the hardware figures in Table 2, or replace them with a computer the team has actually used? | B50 and B54 cannot be checked. |
| G7 | After the interview: the real service list (M35), the Service Schedule days, and whether a second IPV dose applies (L11). | Affects S5, S6, S14 and E2. |
| G8 | Should Chapter 1 name the laws and standards (RA 10173, RA 11166, RA 6675, DOH EPI, CDC, WHO, HL7 FHIR), or leave them to Chapter 3? | The adviser may prefer the scope to stay short. |
| G9 | Should Health Center Staff have Reports & Analytics, as the Proposal's Purpose suggests, or only the list exports they have now? | C.5; the permission matrix gives Reports to the Administrator, the Doctor and the Official only. |
| G10 | The sign-in page still says the system manages "appointments, community announcements" (`templates/login.html:270`). Change it in a later task? | It contradicts the revised Chapter 1. This task changes no code. |
| G11 | The Gantt chart's months: what are the real dates of each phase? | F17. Only the team's records can answer it. |
