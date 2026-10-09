# Chapter 4 evidence — IDS-BPHCSN

Facts for Chapter 4 (Results and Discussion) of the capstone manuscript, gathered on 2026-10-09
from the code, `PROJECT_STATUS.md`, the git history (commit `9222c26` and before) and
`docs/verification/`. Every measurement and screenshot here used the **fictional demo database**
(`seed_demo_data.py`) built in a temporary folder; `app.db` was not opened. Nothing in the app,
its tests or its templates was changed for this file.

Rule followed throughout (the adviser's): only what was built and tested is reported; every
number below comes from a run on 2026-10-09 or from a dated record in the repository, with its
source named.

---

## 1. Modules (section 4.2)

The system has 21 screens on four roles: the **Administrator** (Admin, a Kagawad of the health
committee), the **Doctor**, **Health Center Staff** (Staff) and the **Barangay Official**
(Official). Roles are stored in `users.role` and enforced on the server on every request
(`utils/security.py` `login_required` / `role_required`); one rule, `holds_clinical_authority()`
in `utils/roles.py`, decides every Doctor-only action. Source for the permissions below:
`PROJECT_STATUS.md` §3 (permission matrix), confirmed by the final audit's route × role matrix
(`docs/verification/final-audit/README.md`).

### 1.1 User Management and Authentication

**Purpose.** Lets only known, active accounts in, keeps each session short on a shared computer,
and lets the Administrator manage who can sign in.

**Main functions**
- Sign-in with a hashed password; 5 wrong passwords in a row pause that username for 5 minutes
  (`utils/login_throttle.py`).
- Forced password change at first sign-in; random first-time passwords; a password rule of
  12 characters and 3 of 4 character kinds (`models/users.py`).
- Sign-out after 30 minutes idle and 12 hours after sign-in, with a warning 2 minutes before
  (`config.py`, `static/js/session.js`).
- Form tokens (CSRF) on every POST; sign-out is a POST (`utils/csrf.py`).
- Add User, Edit User, Reset Password, Deactivate / Reactivate; the last active Administrator
  cannot be deactivated or demoted (`routes/user_views.py`).
- My Account: change one's own password.
- Every sign-in, refusal and account change is audited.

**Users by role**
- Admin: everything above, including User Management and its Excel/PDF exports.
- Doctor, Staff, Official: sign in, My Account, change own password. No User Management.

**Contribution.** Every other module relies on it: it ties each record and audit entry to a
real account and keeps patient data behind a personal sign-in (RA 10173).

### 1.2 Patient Records (with sealed records)

**Purpose.** One record per patient: personal data, medical background, consultation history,
dispensing history, immunization record and visits.

**Main functions**
- Register and edit a patient (Save & Register Another); age shown in days, weeks, months or
  years from one helper (`models/patients.py` `format_age()`).
- Patient list with filters, sorting, header search; Excel and PDF of the list or of a ticked
  selection; printable profile.
- Status: Active / Inactive; **Deceased** only by the Doctor (`can_declare_death()`).
- **Sealed records (RA 11166):** the Doctor can seal (Restrict) a consultation. Its chief
  complaint, diagnosis, treatment plan, notes and the visit's check-in reason are stored
  encrypted (AES-256-GCM, key `SEALED_DATA_KEY`, bound to row and field;
  `utils/sealed_crypto.py`). Only `open_sealed_value()` decrypts, and only for the Doctor.
  Exports, prints, audit entries and backups never carry the text.

**Users by role**
- Doctor: everything, including declaring a death and sealing / unsealing.
- Staff: register, edit, Active / Inactive, view; sees a placeholder for sealed fields.
- Admin: demographics only (ID, name, sex, age, birth date, address); no contact number,
  conditions, visits or clinical data (`get_all_patients_demographics()`).
- Official: no access (no route).

**Contribution.** The central record the queue, consultations, immunization, dispensing,
reports and SMS audiences are built on.

### 1.3 Patient Queue and Consultation

**Purpose.** Runs the day's walk-in visits from check-in to the Doctor's diagnosis and records
each consultation.

**Main functions**
- Check-in with a required service from a fixed list (`VISIT_SERVICES`: Consultation,
  Follow-up Consultation, Hypertension / Diabetes Monitoring, Prenatal Check-up, Immunization,
  Dental).
- Five statuses: Waiting → In Consultation → Waiting for the Doctor (intake saved, service needs
  a diagnosis) or Completed; Left before being seen (same-day undo). One status × role mapping
  (`models/queue_actions.py`) draws the buttons and is checked on the server.
- Start only on a visit checked in today; one patient in the room at a time.
- Consultation form: vital signs, chief complaint, growth measurements for children, vaccines
  given (only eligible doses), medicines and supplies dispensed (FEFO), diagnosis and treatment
  plan (Doctor only), seal (Doctor only).
- "Send to the Doctor" instead of Completed for a service that needs him; Completed is refused
  without a diagnosis.
- The Doctor's list "Waiting for the Doctor" (all days, oldest first) with **See patient**.
- "Open visits from earlier days" on the queue; Excel and PDF of the queue; monthly calendar.

**Users by role**
- Staff: check in, start, intake, dispense, record vaccines, send to the Doctor, complete
  non-Doctor services, mark Left, change service. Cannot diagnose or seal.
- Doctor: all of Staff's, plus See patient, diagnosis, treatment plan, seal.
- Admin: read-only queue; no check-in reason, no service, no buttons.
- Official: no access.

**Contribution.** Turns the paper queue into a tracked flow where no Doctor-service visit can
be closed without the Doctor, and every visit leaves a record.

### 1.4 Immunization

**Purpose.** Tracks each child's doses against the DOH EPI schedule and allows a dose only when
it is due.

**Main functions**
- Schedule: BCG, Hepatitis B, Pentavalent ×3, OPV ×3, PCV ×3, IPV, MR (9 months), MMR
  (12 months) (`models/immunizations.py` `EPI_SCHEDULE`).
- One eligibility rule (`dose_eligibility()`, `DOSE_RULES`): minimum age, previous dose on
  file and valid, minimum interval (WHO tables; ACIP 4-day grace for card records). The form
  greys out doses not yet due ("From <date>") and the server refuses them.
- Evidence of each dose: given here, vaccination card (counts), parent's report (recorded, does
  not count). "Record dose given elsewhere" from the profile, shown only when the child is old
  enough.
- Every dose judged by one rule (`judge_records()`); a dose given too early reads "Given too
  early — ask the Doctor about a repeat", does not count, and can be repeated as a new record.
- Due date = the earliest date a dose can actually be given (`dose_due()`); status "No record"
  (not "Overdue"); follow-up list; audited corrections; other vaccines (rabies, etc.).

**Users by role**
- Staff and Doctor: record doses at a visit, record a dose given elsewhere, correct a record.
- Admin: no immunization data (demographics only); dashboard counts only.
- Official: coverage figures on Vaccination Campaigns and Community Reports (exact numbers, a
  decision recorded as L28 / L47).

**Contribution.** Prevents extra injections from doses given too early and gives the barangay
honest coverage figures.

### 1.5 Medicine and Supplies Inventory

**Purpose.** Tracks stock by delivery batch with expiry, and takes dispensed stock from the
right batch.

**Main functions**
- Items named by generic name, strength and dosage form (RA 6675); duplicates refused; supplies
  and equipment by item name and size.
- Batches (`inventory_batches`): lot, expiry, quantity received / remaining, date received,
  source, brand. Stock = usable (not expired) batches.
- Receive stock, Remove from stock (reason: Expired, Damaged, Lost, Returned, Count correction),
  Edit details; each one audited.
- **FEFO dispensing** (`models/dispensing.py` `record_dispensing()`): earliest expiry first,
  split across batches, expired batches never used, refusal with the amount available.
- Expiring soon (90 days) and expired counts; low-stock alert on usable stock; item page with
  its batches; Excel and PDF with a Batches sheet.

**Users by role**
- Admin, Staff, Doctor: view, add, edit, receive, remove, archive, export. Dispensing itself
  happens at a consultation (Staff, Doctor).
- Official: no access.

**Contribution.** Keeps expired medicine away from patients and shows the health center what
to reorder and what is about to expire.

### 1.6 Community SMS Notifications

**Purpose.** Sends health announcements to groups of residents by SMS.

**Main functions**
- Audiences: All Registered Patients, Senior Citizens (RA 9994), Parents / Guardians of
  children, Health Center Personnel (`models/broadcasts.py` `AUDIENCES`).
- Compose with segment counting (GSM-7 / UCS-2); send through Semaphore when
  `SEMAPHORE_API_KEY` is set ("Live"), otherwise saved and not sent ("Simulated"); the mode is
  shown on the screen and in Settings (`utils/sms.py`).
- History of broadcasts with recipient counts; numbers masked to the last 4 digits for every
  role; the Admin and the Official see counts only, no names.

**Users by role**
- Admin and Official: compose and send; counts only.
- Doctor and Staff: read; names with masked numbers.

**Contribution.** The "community notifications" half of the system's title. **Limit:** no
`SEMAPHORE_API_KEY` has been set, so every broadcast so far is Simulated; no message has been
sent to a real phone (`PROJECT_STATUS.md` §7).

### 1.7 Reports and Analytics

**Purpose.** Turns the records into figures for the health center and the barangay.

**Main functions**
- Report types: All Reports, Patient Statistics, Appointment Statistics, Consultation Summary,
  Medicine Inventory Status, SMS Notification Activity (`ANALYTICS_REPORT_TYPES`); any range
  up to 12 months; charts and tables; Print, Excel, PDF.
- Community Reports, Health Programs and Vaccination Campaigns for the Official.
- **Small counts:** for the Admin and the Official, ranking rows of 1–4 fold into "Other (each
  fewer than 5)" and single counts read "Fewer than 5" (`utils/small_counts.py`); sealed visits
  count as one "Confidential" row; the Doctor sees every count.

**Users by role**
- Admin and Official: reports with small counts folded; the Official also has Community
  Reports, Health Programs, Vaccination Campaigns.
- Doctor: Reports & Analytics with every count.
- Staff: no Reports & Analytics (dashboard figures only).

**Contribution.** Gives decision makers figures without exposing individuals.

### 1.8 Service Schedule

**Purpose.** Records which services run on which days (for example the 2nd and 4th Wednesday).

**Main functions**
- Add, edit, delete entries (service, weekdays, weeks of the month, note); validated; audited.
- Shown on every role's Service Schedule screen and as "services today" on the Patient Queue.

**Users by role**
- Admin: add, edit, delete.
- Doctor, Staff, Official: view.

**Contribution.** Tells staff and residents when a service runs. **Status:** the table is empty
on purpose until the health center's real service days are confirmed (`PROJECT_STATUS.md` §7,
item 4; M35).

### 1.9 Audit Logs

**Purpose.** Keeps an accountable record of who did what and when.

**Main functions**
- One entry per write, in the same transaction as the write (`routes/audit_entries.py`):
  sign-ins and refusals, accounts, settings, backups, maintenance, patients (including death
  declarations), consultations, doses, dispensing, inventory, queue actions, seals, schedule,
  SMS.
- No entry quotes clinical text, a medicine, vaccine or service name, a password or a whole
  phone number (masked on write).
- Filters, Excel and PDF.

**Users by role**
- Admin only. Other roles have no route.

**Contribution.** Accountability required by RA 10173 and the Data Privacy Act's security
measures; it is also the evidence trail used in the verification notes.

### 1.10 System Settings (backup, maintenance, network mode)

**Purpose.** Lets the Administrator run the system day to day.

**Main functions**
- General Settings: health center name, barangay, municipality, province, opening and closing
  time (shown on screens and letterheads).
- SMS pane: the Live / Simulated mode line.
- Security pane: session limits and the network mode line ("Network mode: Off (this computer
  only)" or "On — open https://<address>:<port>").
- Password Policy (read-only statement of the rule).
- Backup & Restore: download an encrypted `.idsbackup` (AES-256-GCM, key derived from
  `SEALED_DATA_KEY` by HKDF-SHA256, `utils/backup_crypto.py`); restore is
  `restore_backup.py` at the health-center PC (no Restore button, by design — L34).
- System Maintenance: maintenance mode closes the system to everyone but the Administrator.
- About System.
- Network mode itself is set in `.env` (`IDS_NETWORK=1`), served over HTTPS only
  (`utils/server.py`, `setup_https.py`).

**Users by role**
- Admin only.

**Contribution.** Keeps the data recoverable (encrypted backups) and lets the system be used
from other devices without sending records in plain text.

### 1.11 Dashboards (supporting)

Each role has its own dashboard (`admin_dashboard.html`, `staff_dashboard.html` for Staff and
the Doctor, `official_dashboard.html`): counts, low-stock and expiry alerts, the Doctor's
"Waiting for the Doctor" list, immunization follow-up counts. The Admin's dashboard reads no
visit or child list.

---

## 2. Testing conducted (section 4.3)

### 2.1 How the tests are run

All automated tests are plain Python suites in `tests/`, run with one command,
`python tests/run_all.py` (`--quick` skips the two slowest). Each suite builds its own fresh
database in the system temp folder from `schema.sql` plus made-up fixtures (`tests/_support.py`)
or from the fictional demo seed; a guard stops the run if any database path is inside the
project, and the runner checks that `app.db` has the same size, time and SHA-256 afterwards.
The suites drive the real application: HTTP requests through Flask's test client (most suites),
the real cheroot server (`verify_network_mode.py`), or a real Chromium browser through
Playwright (`verify_mobile_layout.py`). There is no separate unit-test framework (no pytest):
unit-level checks call a model or helper function directly inside the suites.

**Latest result (2026-10-09, this task, full run on the test computer in section 5):**
`TOTAL: 4903/4903 checks passed in 27/27 suites that ran` — `Live app.db unchanged (size, modified time and checksum match).` — `All checks passed.` Exit code 0. No suite was skipped (Playwright and Chromium are installed on this laptop). The tracker's last recorded total was 4724/4724 (Task 17); the difference is the phone suite (2080 checks now, 1901 then) and `verify_dispensing.py` (131 now, 133 in the tracker). The run took about 27 minutes in all; that is not a performance figure.

### 2.2 What each testing type means here

- **Unit** — a single function checked directly with chosen inputs (e.g. `dose_eligibility()`,
  `fold_small_counts()`, `mask_phone()`, `format_age()`, the AES-GCM helpers, FEFO in
  `record_dispensing()`, `secret_key_problem()`).
- **Integration** — several layers together: a route, its model and the database, or a report
  and its Excel/PDF file read back byte for byte.
- **System** — a whole workflow as a user would do it, through signed-in HTTP requests or a
  real browser (check-in to diagnosis, the status × role walk, every menu page per role).
- **Security** — refusals: forged requests with a valid token, wrong roles, missing tokens,
  expired sessions, encryption at rest, data that must not reach a role (markers searched in
  pages, exports and backup bytes).
- **Performance** — timed requests to the real server (section 5); measured once, in this task.
- **Usability / User Acceptance Testing — NOT conducted.** No real user (health center staff,
  the Doctor, the Kagawad or a barangay official) has tested the system yet. The phone-layout
  suite checks layout rules automatically (no sideways scroll, 44×44 px targets after
  WCAG 2.5.5); it is not a usability test with people, and it is not reported as one.

### 2.3 The suites

Check counts and results are from the full run of 2026-10-09. "Types" lists only what the suite
actually does.

| # | Suite | What it checks (one line) | Types | Checks | Latest result |
|---|---|---|---|---|---|
| 1 | `verify_epi.py` | Staff can still record an EPI dose and growth measurements at a consultation | Integration, System | 15 | 15/15 passed |
| 2 | `verify_staff_capabilities.py` | Staff keep every capability (intake, dispensing, stock by batch, sealed placeholder) | System, Security | 27 | 27/27 passed |
| 3 | `verify_add_user.py` | Add User, Deactivate / Reactivate, the last-Administrator guard, blocked sign-in of a deactivated account | System, Security | 121 | 121/121 passed |
| 4 | `verify_my_account.py` | My Account and changing one's own password (rules, refusals, session kept) | System, Security | 344 | 344/344 passed |
| 5 | `verify_password_change_audit.py` | A refused own-password change is audited and records no password | Security | 50 | 50/50 passed |
| 6 | `verify_edit_user_reset_password.py` | Edit User and Reset Password end to end | System, Security | 82 | 82/82 passed |
| 7 | `verify_rbac.py` | Consultation role rules and confidentiality through real HTTP requests | Integration, Security | 117 | 117/117 passed |
| 8 | `verify_reports.py` | A sealed diagnosis never reaches the ranking; reads the real Excel and PDF bytes | Integration, Security | 61 | 61/61 passed |
| 9 | `verify_dispensing.py` | Medicine lines on the consultation form, stock taken, refusals, helper text | Integration, System | 131 | 131/131 passed (the tracker table says 133; this run and a rerun counted 131, no failure) |
| 10 | `verify_doctor.py` | The Doctor role: only the Doctor diagnoses, seals, reads sealed text, declares a death; forged POSTs by every other role; maintenance mode | System, Security | 132 | 132/132 passed |
| 11 | `verify_service_schedule.py` | Service Schedule: validation, add / edit / delete by the Admin, every other role refused, audit entries | System, Security | 157 | 157/157 passed |
| 12 | `verify_database_integrity.py` | A fresh install records a consultation (H5); a failed write frees its lock (M16); schema structure | Integration | 18 | 18/18 passed |
| 13 | `verify_security_basics.py` | Secret key, debug mode, 30-minute / 12-hour sessions, forced password change, setup_env.py, no URL text on screens | Unit, Security | 82 | 82/82 passed |
| 14 | `verify_csrf.py` | Every POST needs a valid form token; sign-out is a POST; refusals are plain and audited | Security | 69 | 69/69 passed |
| 15 | `verify_audit_coverage.py` | Every health-record write leaves exactly one short entry with no clinical text; structural check over the code | Security, Integration | 65 | 65/65 passed |
| 16 | `verify_sealed_privacy.py` | Sealed fields encrypted (AES-256-GCM), Doctor-only reading, nothing in exports, audit or backup bytes; the migration | Unit, Security, Integration | 187 | 187/187 passed |
| 17 | `verify_admin_minimum_necessary.py` | The Administrator reaches no clinical data on any page, export or URL; encrypted backup | Security | 87 | 87/87 passed |
| 18 | `verify_small_counts_and_masking.py` | Small counts fold into Other for the Admin and the Official on screen, chart, Excel, PDF; phone masking | Unit, Integration, Security | 184 | 184/184 passed |
| 19 | `verify_demo_data.py` | The demo seed is fictional, deterministic (built twice and compared) and follows every rule; archiving verifies before removing | Integration, System | 118 | 118/118 passed |
| 20 | `verify_doctor_worklist_and_left.py` | The visit flow: service at check-in, Waiting for the Doctor, See patient, Left before being seen, earlier-day visits, status × role walk | System, Security | 266 | 266/266 passed |
| 21 | `verify_cleanup.py` | One project name, no placeholders, short text, SMS mode line, every menu page loads for each role | System | 50 | 50/50 passed |
| 22 | `verify_final_fixes.py` | Final-audit fixes: SMS counts only, README order, masking in every format, sign-in pause, frame header, rendered text length, age helper | Unit, System, Security | 73 | 73/73 passed |
| 23 | `verify_immunization_evidence.py` | Dose evidence (given here, card, parent's report), "No record", the record-elsewhere button and its corrections | System, Integration | 79 | 79/79 passed |
| 24 | `verify_inventory_batches.py` | Generic names, batches, Receive / Remove / Edit, FEFO, expired stock never used, expiry figures, migration | Unit, Integration, System | 126 | 126/126 passed |
| 25 | `verify_immunization_timing.py` | Vaccines only when due: minimum age, interval, previous dose, forged POSTs, repeats, corrections, due dates | Unit, System, Security | 126 | 126/126 passed |
| 26 | `verify_network_mode.py` | Local and network mode, the certificate script, the real cheroot server over HTTPS, Secure cookie, plain-HTTP refusal | System, Security | 56 | 56/56 passed |
| 27 | `verify_mobile_layout.py` | Real Chromium at 360, 390 and 1366 px for all roles: no sideways scroll, menu, tables, fields, dialogs, 44×44 targets, no script errors | System (layout) | 2080 | 2080/2080 passed (the tracker table says 1901, recorded before commit `cd773d4` changed this suite) |
| | **Total** | | | **4903** | **4903/4903 passed, 27/27 suites** |

### 2.4 Other testing and its evidence

| Activity | What was done | Result | Evidence |
|---|---|---|---|
| Final pre-defense audit (2026-10-02) | Independent read-only audit of code, tests and documents: full suite, 10 claims checked, route × role matrix through real sign-in (93 URL rules, 4 roles, GET and POST with a valid token), marker crawl, clean-clone install, docs drift | READY WITH FIXES. 2245/2245 checks; 8 of 10 claims passed; 2 failed (M37 recipient names; L35/L36 and docs drift); all fixed by 2026-10-03 (2294/2294) | `docs/verification/final-audit/README.md`; tracker "Final audit" and "Final fixes" lines |
| Adversarial role testing | (a) Route × role matrix through real sign-in: matched the permission matrix, no server error. (b) Marker crawl: unique markers written into every clinical field, then every GET rule requested with every patient, consultation and visit ID: 2,552 requests, 830 readable responses (HTML, Excel, PDF); Admin 633 requests / 0 forbidden markers found, Official 593 / 0, Staff 653 / 0 sealed markers, Doctor 673 / 0 server errors. Backup bytes: no marker. (c) In the suites: forged POSTs with valid tokens for every role (`verify_rbac.py`, `verify_doctor.py`, `verify_admin_minimum_necessary.py`), and the queue walk of 8 visit states × 4 roles × 8 actions (`verify_doctor_worklist_and_left.py`) | No leak of clinical, sealed or phone data to a role that must not see it; one gap (M37) found and fixed | final-audit README "Actual permission matrix", "Adversarial results" |
| Deliberate break-it (mutation) checks | A rule is broken on purpose in a scratch copy of the code (never the repository) and the suite is run; it must fail. Recorded counts per task: final audit 7; Task 6 3; Task 6b 14; Task 6c 10; Task 6d 13; Task 6e 4; Task 7 16; final fixes 15; two small fixes 2; Task 9 16; Task 10 14; Task 11 10; Task 12 25; Task 13 16; Task 14 28; Task 15 22; Task 16 24 (Tasks 5d and 5e: "each shown to fail when its rule is switched off", no count recorded). Task 17's suite carries its own break-it checks (table box removed, pinning broken, offcanvas removed, console error) | **At least 239 recorded mutations, all caught.** Some first attempts were not caught or not effective and led to a stronger check; each is named in the Task Log. One planned mutation (binding network mode to 0.0.0.0) was not run because it opens a Windows Firewall prompt | `PROJECT_STATUS.md` Task Log; final-audit README "Break-it"; `verify_mobile_layout.py` section "break-it" |
| Clean-copy install test | `git clone` into a temp folder, then the README steps exactly | Final audit: failed at the seed step (M36). After the fix (2026-10-03): every step worked and the sign-in page loaded; clone deleted | final-audit README "Clean-clone result"; tracker M36 |
| Network HTTPS tests | Both modes and their refusals in child processes; the certificate's names, size, validity and usage; the real cheroot server over HTTPS on 127.0.0.1 checked against the `.crt`; sign-in with a Secure HttpOnly cookie; CSRF refusals over HTTPS; plain HTTP to the HTTPS port gets no page | All checks pass (`verify_network_mode.py`). **Not done:** a real second PC, Android phone or iPhone on the Wi-Fi (L62) | `tests/verify_network_mode.py`; tracker Task 16, L62 |
| Mobile layout checks | Real Chromium at 360, 390 and 1366 px, all four roles, every menu page, a patient profile with every tab, the consultation forms, an inventory item and every dialog; plus 26,287 elements on 63 pages compared before and after at 992 px and wider | All checks pass; 992 px and wider unchanged except the width of one "Loaded HH:MM" text. **Not done:** a real phone, Safari, 320 px, large font (L64) | `tests/verify_mobile_layout.py`; screenshots in `docs/verification/mobile/` (git-ignored); tracker Task 17 |
| Performance measurement | `tests/perf/measure_performance.py` (this task) | See section 5 | `tests/perf/performance_results.md` |

---

## 3. Successful test cases (Table 4.1)

Each case is an existing automated check that passed in the full run of 2026-10-09
(4903/4903 checks, 27/27 suites). "Proven by" quotes the check's name as the suite prints it (confirmed against the
PASS lines of a verbose rerun of the same suites, 1878/1878, on 2026-10-09; `verify_add_user.py`
and `verify_mobile_layout.py` print only failures, so their names are taken from the code and
confirmed by a run with no failure line). "Actual outcome" is what the check observed when it passed.
The performance case (TC037) comes from section 5.

| ID | Module | Description | Testing type | Expected outcome | Actual outcome | Status | Proven by (suite — check) |
|---|---|---|---|---|---|---|---|
| TC001 | Authentication | Sign in with 5 wrong passwords, then the right one | Security | The username is paused for 5 minutes, with a short message; another account still signs in | Refused with the message; the other account signed in; the pause ended after 5 minutes | Pass | `verify_final_fixes.py` — "L41: after 5 wrong passwords the correct one is refused, with a short message, for 5 minutes"; "L41: the pause ends after 5 minutes" |
| TC002 | Authentication | Sign in with a deactivated account and its right password | Security | Refused; the attempt is audited | Refused; one audit entry, with no password in it | Pass | `verify_add_user.py` — "the deactivated account cannot sign in even with the right password"; "the blocked sign-in was audited against the new account" |
| TC003 | Authentication | Leave a session idle for 30 minutes (simulated clock) | Security | The next page sends the person to sign in; the sign-out is audited | Sent to sign-in with the idle message; audited; session cleared | Pass | `verify_security_basics.py` — "after 30 idle minutes, a page sends the person to sign in with the 'idle' key"; "the idle sign-out is audited" |
| TC004 | Authentication | Keep a session active past 12 hours | Security | Activity does not stretch the 12-hour limit | Keep-alives every 29 minutes did not stretch it; a later request got 401 "expired" | Pass | `verify_security_basics.py` — "keep-alives every 29 minutes do not stretch the 12-hour limit" |
| TC005 | Authentication | First sign-in of a new account | Security | The person is sent to My Account to set a password | Landed on My Account | Pass | `verify_security_basics.py` — "its first sign-in goes to My Account" |
| TC006 | All forms (CSRF) | POST Add User with no form token, and with another user's token | Security | Refused (400 "Your session expired"); nothing written | Refused both ways; nothing written | Pass | `verify_csrf.py` — "admin: Add User without a token is refused"; "another user's token is refused"; "it is a 400 titled 'Your session expired'" |
| TC007 | User Management | Deactivate the last active Administrator | System, Security | Refused; no audit entry for a deactivation | Refused; the button is disabled on screen | Pass | `verify_add_user.py` — "THE ATTEMPT TO DEACTIVATE THE LAST ADMINISTRATOR IS REFUSED"; "the Administrator's Deactivate button is disabled on the screen" |
| TC008 | User Management | Admin adds a Doctor, changes a role, resets a password | System | Each change saved; the new password signs in | All saved; the reset password signed in | Pass | `verify_doctor.py` — "admin Add User creates a Doctor"; "admin Edit User changes the role"; "admin Reset Password works (new password signs in)" |
| TC009 | Patient Records | Admin opens a patient's profile and the patient list | Security | Demographics only; no clinical marker, contact number or medicine name | Demographics only on profile, list and export | Pass | `verify_admin_minimum_necessary.py` — "his profile shows the demographics: ID, name, sex, age, birth date, address, …"; "*** no clinical marker, contact number or medicine name reaches the Administrator …" |
| TC010 | Patient Records | Staff try to mark a patient Deceased (forged POST) | Security | Refused; database unchanged. The Doctor can | Staff refused, database byte-identical; the Doctor marked and reversed it | Pass | `verify_doctor.py` — "Staff forged status Deceased on patient 1: refused, database byte-identical"; "doctor marked patient Deceased" |
| TC011 | Consultation | The Doctor records a consultation with diagnosis and plan | Integration, System | Saved, redirect to the profile, visit Completed | Saved (302 to profile); diagnosis and plan stored as written | Pass | `verify_doctor.py` — "doctor record saved (302 to profile)"; `verify_database_integrity.py` — "Doctor: record POST saved and redirected (no 500)" |
| TC012 | Consultation | Staff send a forged diagnosis or treatment plan | Security | Refused; the consultation row unchanged; one refusal audit entry | Refused; row byte-identical | Pass | `verify_doctor.py` — "Staff forged diagnosis on #36: refused, diagnosis byte-identical (FORGED-DX absent)" |
| TC013 | Patient Queue | "Mark Completed" on a Consultation visit with no diagnosis | Security, System | Refused on the server; the visit must go to the Doctor | Refused for Staff and the Doctor | Pass | `verify_doctor_worklist_and_left.py` — "Staff: 'Mark Completed' on a Consultation visit with no diagnosis is refused on the server" |
| TC014 | Patient Queue | A visit sent to the Doctor without an intake | System | The Doctor gets "See patient" on the queue and dashboard; it opens a new consultation | Button on both; opened a new consultation form with the diagnosis field | Pass | `verify_doctor_worklist_and_left.py` — "the Doctor's Patient Queue offers 'See patient' on that row"; "it opens a new consultation form for this visit (the Doctor sees the diagnosis field)" |
| TC015 | Patient Queue | Every action × every status × every role | System, Security | Each action the queue shows works; every other one is refused with no change | As expected for all combinations | Pass | `verify_doctor_worklist_and_left.py` — "each action the queue shows works for that role, and every other one is refused with no change …" |
| TC016 | Patient Queue | Mark a visit Left before being seen, then undo on a later day | System | Marked; the undo on a later day is refused | Marked; later-day undo refused | Pass | `verify_doctor_worklist_and_left.py` — "Staff mark a Waiting visit as left before being seen"; "an undo on a later day is refused: the visit stays closed" |
| TC017 | Patient Queue | Open visits from earlier days | System | Listed with every open status; the dashboard count and the queue agree | Listed; counts agree | Pass | `verify_doctor_worklist_and_left.py` — "it lists every open earlier visit, whatever its status: …"; "the Doctor's list, the dashboard count and the queue (today + earlier days) all agree" |
| TC018 | Sealed records | The Doctor seals a consultation at record time | Security | Diagnosis, plan, complaint, notes and check-in reason stored encrypted (`enc:v1:`) | All five encrypted; decrypt for the Doctor | Pass | `verify_sealed_privacy.py` — "sealed at record time: both fields are stored encrypted"; "Task 5b: the chief complaint and additional notes are encrypted too, and decrypt"; "Task 5b: the check-in reason of the linked queue visit is encrypted, bound to that row" |
| TC019 | Sealed records | Each role opens a sealed visit | Security | Staff see a placeholder, the Admin sees demographics, the Doctor sees the text | As expected; sealed text absent from the raw body for Staff and the Admin | Pass | `verify_doctor.py` — "[sealed at record time] staff profile: placeholder shown, sealed text absent from raw body"; "[sealed at record time] doctor profile: sealed text shown in full" |
| TC020 | Sealed records / Settings | Download a backup and search it for sealed text | Security | The file is encrypted; no sealed text in its bytes; it restores fully | Encrypted; no sentinel in the bytes; restored with the key | Pass | `verify_sealed_privacy.py` — "*** no sealed sentinel appears anywhere in the backup bytes ***"; "the backup restores fully: the sealed row is there, encrypted, and opens with the key" |
| TC021 | Immunization | Consultation form for a 1-month-old | System | Pentavalent, OPV and PCV dose 1 greyed out with the earliest date, no tick box | Greyed out with "From <date>" | Pass | `verify_immunization_timing.py` — "a 1-month-old: Pentavalent, OPV and PCV dose 1 show greyed out with the earliest date, not a tick box" |
| TC022 | Immunization | Forged POST of a dose for the 1-month-old | Security | Refused with the earliest date | Refused, date given | Pass | `verify_immunization_timing.py` — "a forged POST for … for the 1-month-old is refused, with the earliest date" |
| TC023 | Immunization | Boundaries: 6 weeks, dose 2 interval, MR at 9 months | Unit, System | Allowed exactly at the minimum age / interval, refused one day before | As expected at every boundary | Pass | `verify_immunization_timing.py` — "at exactly 6 weeks, dose 1 of Pentavalent, OPV and PCV are tick boxes; dose 2 is not"; "27 days after dose 1: dose 2 is not eligible, earliest tomorrow"; "MR is refused the day before 9 months and allowed at 9 months" |
| TC024 | Immunization | Record a parent's report with no card | System | Accepted; shown "Parent says given — no card" (amber); not counted as given | As expected | Pass | `verify_immunization_evidence.py` — "a parent report with no date is accepted (the date is optional)"; "it shows 'Parent says given — no card', amber, and is not counted as given" |
| TC025 | Inventory | Dispense from an item with several batches | Unit, Integration | Earliest expiry first, even if it arrived later; split across batches | Taken from the earliest expiry; split earliest first | Pass | `verify_inventory_batches.py` — "dispensing takes from the earliest expiry, even if it arrived later"; "when the earliest batch runs out it splits across batches, earliest first"; "the Doctor dispenses through the form: 9 units come from two batches, earliest first" |
| TC026 | Inventory | Dispense when an expired batch holds stock | Unit, Security | The expired batch is never used; an item with only expired stock is refused | Never used; refused with "no usable stock" | Pass | `verify_inventory_batches.py` — "an expired batch is never used, even when it expires first and holds more"; "an item whose only stock is expired is refused as having no usable stock" |
| TC027 | Inventory | Add a medicine that already exists (other case, spacing) | System | Refused as a duplicate | Refused | Pass | `verify_inventory_batches.py` — "the same generic name, strength and form is refused as a duplicate (any case, any spacing)" |
| TC028 | Community SMS | The Admin and the Official open SMS screens after broadcasts | Security | Counts only, no recipient name; numbers masked for the care team | Counts only; masked to the last 4 digits | Pass | `verify_final_fixes.py` — "Administrator: no recipient name on the SMS screen, the dashboards or the reports"; "Barangay Official: …"; "numbers are masked to the last four digits, none in full" |
| TC029 | Community SMS | No Semaphore key set | System | Settings and SMS Notifications say "Simulated" | "Simulated"; "Live" with a key | Pass | `verify_cleanup.py` — "with no key, Settings and SMS Notifications say 'Simulated'"; "with a key set, both say 'Live'" |
| TC030 | Reports | Diagnoses with counts 12, 5, 4, 1 and 3 sealed, viewed by each role | Unit, Security | The Admin and the Official see 12 and 5 named, the rest as "Other" (8); the Doctor sees every row | As expected on screen, chart, Excel and PDF | Pass | `verify_small_counts_and_masking.py` — "Administrator: diagnoses show 12 and 5 named; 1, 4 and the 3 sealed fold to Other = 8"; "Doctor: every diagnosis is named with its own count, Confidential included" |
| TC031 | Reports | Export Excel and PDF of the report | Integration | Files generated; the same rows as the screen | Generated; row for row equal to the model | Pass | `verify_small_counts_and_masking.py` — "Administrator: Excel export is generated"; "… the Excel diagnosis ranking is the model's, row for row"; "… PDF export is generated" |
| TC032 | Service Schedule | Staff, the Doctor and the Official POST to add, edit or delete an entry | Security | Refused; schedule and audit unchanged; the Admin can | Refused for all three; the entry survived every forged edit and delete | Pass | `verify_service_schedule.py` — "Health Center Staff POST /admin/service_schedule/add: schedule unchanged, no audit row"; "the Immunization entry survived every forged edit and delete" |
| TC033 | Audit Logs | Every write path in the code | Security (structural) | Each one writes an audit entry, or is listed as exempt with a reason | No unlisted write path | Pass | `verify_audit_coverage.py` — "every write path writes an audit entry, or is listed in EXEMPT with a reason" |
| TC034 | System Settings | Maintenance mode on | System | The Doctor gets the maintenance page and cannot sign in; the Admin is unaffected | As expected; access back when lifted | Pass | `verify_doctor.py` — "doctor gets the 503 maintenance page"; "doctor cannot sign in during maintenance"; "administrator unaffected" |
| TC035 | Network mode | Start network mode without a certificate; sign in over HTTPS | Security | Refuses to start, naming the command; over HTTPS the session cookie is Secure, HttpOnly, SameSite=Lax | As expected on the real cheroot server | Pass | `verify_network_mode.py` — "network mode with no certificate refuses to start, with one plain message naming the command"; "the session cookie is marked Secure and HttpOnly, with SameSite=Lax" |
| TC036 | All screens (mobile) | Every page and dialog at 360 and 390 px, every role | System (layout) | No sideways scroll, nothing cut off, 44×44 targets, no script error | As expected on every page | Pass | `verify_mobile_layout.py` — "<role> <page> @<width>: no sideways scroll", "… no script errors", "… every button and link is at least 44x44" (one check per role, page and width) |
| TC037 | Performance | Every measured action (section 5) | Performance | 95th percentile under 3 s | All 14 actions within 3 s at the 95th percentile; slowest: PDF export, 1,402 ms; 0 failed runs | Pass | `tests/perf/measure_performance.py`, `tests/perf/performance_results.md` |

---

## 4. Failed test cases and corrective actions (Table 4.2)

Every row is a real defect that was found, fixed and retested. Sources: the issue list and Task
Log in `PROJECT_STATUS.md` (IDs H, M, L), the commit named, and the verification note named.
"How found" is copied from those records; where a record does not say how a defect was found,
the row says "not recorded". Hashes are the current ones (history was rewritten on 2026-09-29,
so older hashes in chat logs no longer resolve). "Retest" names the check that now passes; all
of them passed in the full run of 2026-10-09 (section 2).

| ID | Module | How found | Initial result | Problem identified (cause) | Corrective action | Retest result | Evidence |
|---|---|---|---|---|---|---|---|
| F01 (H5) | Patient Queue and Consultation | Automated test: first run of the suites on a fresh database (Task 1, 2026-09-28) | Recording a consultation on a fresh install returned HTTP 500; 906 of 921 checks passed, all 15 failures from this | `schema.sql` declared `consultations.updated_at` NOT NULL, but the insert writes NULL; the live database only worked because a migration had added the column as nullable | `schema.sql` made to match the live database (`updated_at TEXT`, nullable); the whole schema compared with the live one and 5 differences resolved | 1249/1249 checks; `verify_database_integrity.py` "record POST saved and redirected (no 500)" and "updated_at is nullable, with no default" | `f1b9583`; tracker H5, "Schema drift" |
| F02 (M16) | All modules (database layer) | Automated test, right after F01 (Task 1) | After one failed write, every later write in the same process failed with "database is locked" | A failed write left its SQLite connection open, holding the write lock | New `db_connection()` closes every connection and rolls back a failed write; all 97 call sites in 14 files use it | `verify_database_integrity.py` "the next write succeeds while the failure is still held", "and it did not wait on a lock (under 2 seconds)" | `3fbe423`; tracker M16 |
| F03 | Patient Queue | Team use, 2026-08-29 | Start Consultation was refused, naming a patient who was not in Today's Queue | (a) a visit started at 23:36 and its form abandoned stayed In Consultation forever; (b) the screen judged the room from today's rows while the server checked every day | The stale visit closed honestly by a migration (no consultation invented); the screen reads the room from the same fact as the server; a banner names a visit left open from an earlier day | 47 scenario assertions at the time, against the real stuck row (see the note); the same one-room rule is checked today by `verify_doctor_worklist_and_left.py` "putting a visit back In Consultation is refused while someone else is in the room" | `ad979f5`; `docs/verification/stuck-consultation/README.md` |
| F04 | User Management (and 3 other dialogs) | Reported in use: Add User "redirects and loses the entry" | A form that failed validation looked as if it had thrown the entry away | The page script ran before Bootstrap loaded, so the dialog holding the error never reopened; the same bug was in four dialogs | The four scripts wait for the page to load (`DOMContentLoaded`); a note in `base.html` at the block | Every form re-submitted with invalid data redisplays itself; `verify_add_user.py` "a rejected submit reopens the dialog" | `c7beac4`; `docs/verification/form-redisplay` (in `docs/verification/README.md`) |
| F05 | Authentication | Not recorded (commit describes the defect and its verification) | A deactivated account could still sign in with its old password | The login query did not read `is_active` and the route never checked it | `is_active` checked at sign-in, after the password, with one identical refusal message; a blocked attempt is audited | `verify_add_user.py` "the deactivated account cannot sign in even with the right password", "the blocked sign-in was audited against the new account" | `4f06eb0` |
| F06 | Authentication | The module's own note named the gap | An account deactivated while signed in kept working until it signed out | `is_active` was read only at the login form | Every guarded request re-reads the account (one cached lookup per request) and ends the session of a deactivated or deleted account | `verify_add_user.py` "the deactivated administrator's live session is revoked on its next request" | `b70c28e` |
| F07 | User Management | Automated test: Add User suite 117/119 (2026-09-25) | An Administrator who deactivated their own account was told "Invalid security credentials" | The redirect after the change was the "next action"; the guard from F06 cleared the session and its message | The message is kept and shown on the sign-in page | Add User suite 122/122 then (121/121 today; the earlier 122 was a counting error, L42); `verify_add_user.py` "deactivating your own account says your session will end" | `b9f2185`; `docs/verification/stale-suite-assertions/README.md` |
| F08 | Authentication | Not recorded (the `login-message-lookup` note describes the defect and the fix) | `/login?error=<any text>` printed that text on a page headed with the health center's name | The form printed whatever arrived in `?error=` | The URL carries a key; the form shows only a sentence it looks up; unknown keys show nothing | Ten crafted values (HTML, script tag, 5,000 characters) show nothing; three more screens fixed later (L8, `e0c6e1e`) | `be20dfc`; `docs/verification/login-message-lookup/README.md` |
| F09 (H1) | Authentication | Status audit (2026-09-28) | The seeded accounts used passwords written in the code and README, including the Doctor's | Demo passwords were seeded and never changed | No password in code; random first-time passwords shown once; forced change at first sign-in; migration flags old accounts | `verify_security_basics.py` "its first sign-in goes to My Account"; final audit claim 4 (no password literal outside `tests/`) | `fbf7cef`, `093636e`; tracker H1 |
| F10 (H2) | Authentication | Status audit | Anyone with the code could forge a session cookie | `SECRET_KEY` fell back to a value written in `config.py` | No fallback; the app refuses to start without a proper key; `setup_env.py` creates it | `verify_security_basics.py` "refuses to start when SECRET_KEY is …" (missing, short, old default) | `3f7d9f6`; tracker H2 |
| F11 (M1) | System Settings | Status audit | `python app.py` always ran in debug mode (the debugger can run code) | `debug=True` in `app.py` | Debug only when `IDS_DEBUG=1` | `verify_security_basics.py` "debug is on only for IDS_DEBUG=1" | `a910ae4`; tracker M1 |
| F12 (M2) | All forms | Status audit | No POST form carried a CSRF token; sign-out was a GET | Not built | Flask-WTF on every POST; tokens in all forms and scripts; sign-out a POST form | `verify_csrf.py` 69/69 (e.g. "admin: Add User without a token is refused") | `77b6b32`–`05853eb`; tracker M2 |
| F13 (M3) | Authentication | Status audit: audit rows showed a session still in use 2 days after sign-in | No idle or absolute session limit | Not built | 30-minute idle and 12-hour limits on the server, a warning before, audited | `verify_security_basics.py` "after 30 idle minutes, a page sends the person to sign in…", "keep-alives every 29 minutes do not stretch the 12-hour limit" | `61900c4`; tracker M3 |
| F14 (H3) | Audit Logs | Status audit | Patient changes (including death declarations), inventory, dispensing, queue actions and new consultations wrote no audit entry | Audit writing covered only some modules | Every such write audits in the same transaction (`routes/audit_entries.py`); a structural check fails if a new write path skips it | `verify_audit_coverage.py` "every write path writes an audit entry, or is listed in EXEMPT with a reason" | `0ff453d`, `a5420f8`; tracker H3 |
| F15 (H4) | Patient Records (sealed) | Status audit | The Administrator could read sealed diagnoses through the backup and older audit entries (a risk path; 0 sealed records then) | Sealed text was stored plain | AES-256-GCM encryption of sealed fields; audit entries never quote them; later all free text of a sealed visit (Task 5b) and an encrypted backup (Task 5c) | `verify_sealed_privacy.py` "sealed at record time: both fields are stored encrypted", "*** no sealed sentinel appears anywhere in the backup bytes ***" | `f2c5bfa`, `2a662bd`, `6469425`, `0905493`; tracker H4, M21, M25, M26 |
| F16 (M4, M5) | Patient Queue | Status audit | The Doctor had no list of visits needing a diagnosis; a patient who left could not be closed | Not built | The Doctor's list; status "Left before being seen" with same-day undo | `verify_doctor_worklist_and_left.py` (e.g. "Staff mark a Waiting visit as left before being seen", "an undo on a later day is refused") | `4d1b9c9`, `f82659b`; tracker M4, M5 |
| F17 (M34) | Patient Queue | Found while building Task 6b (recorded as M34) | "Mark Completed" closed a Consultation visit with no intake and no diagnosis, so it never reached the Doctor | Completion did not look at the service | "Send to the Doctor" replaces it; the server refuses Completed without a diagnosis | `verify_doctor_worklist_and_left.py` "'Mark Completed' on a Consultation visit with no diagnosis is refused on the server" | `df58599`; tracker M34 |
| F18 | Immunization (migration) | Automated test (new evidence suite, Task 9) | The evidence migration failed on a reported dose with no date | The migration assumed every reported dose had a date | Migration fixed before it ran on any real database | `verify_immunization_evidence.py` 79/79 | `8df4ace`; Task 9 log line |
| F19 (M36) | Installation | Clean-clone install in the final audit (2026-10-02) | Following the README on a new computer stopped at the seed step | The README started `app.py` (which creates `app.db`) before the seed, which refuses an existing `app.db` | README order fixed; the seed refusal says to use `--replace` | Followed exactly in a temporary clone: every step worked, the sign-in page loaded; `verify_final_fixes.py` "the README starts with the steps in the order that works on a clean clone" | `dfaf0f0`; `docs/verification/final-audit/README.md` |
| F20 (M37) | Community SMS | Final audit, claim 1 (adversarial check) | The Official and the Administrator saw patients' full names in the SMS recipient panel | The recipient builder returned names to every role | Counts only for the Admin and the Official, enforced in `get_broadcast_recipients()` | `verify_final_fixes.py` "no recipient name on the SMS screen, the dashboards or the reports", "the data builder returns no recipients for the Administrator or the Official" | `4b7bcba`; tracker M37 |
| F21 (L41) | Authentication | Final audit | No limit on wrong passwords; no `X-Frame-Options`, no SameSite | Not built | 5 wrong passwords pause the username for 5 minutes; frame header; SameSite=Lax | `verify_final_fixes.py` "L41: after 5 wrong passwords the correct one is refused…", "L41: the pause ends after 5 minutes" | `21569ff`; tracker L41 |
| F22 (L38) | Audit Logs / SMS | Final audit | A mobile number written with dashes or spaces (09xx-xxx-xxxx, +63 9xx xxx xxxx) passed the masker unmasked (latent: no writer stored such text) | The pattern matched only unbroken digits | Masks 09…, +639…, 639… with any separators | `verify_final_fixes.py` "mask_phone shows the last four digits and nothing else in every format", "the audit writer stores no number in any of those formats, only its last four digits" | `6686e83`; tracker L38 |
| F23 (M39) — Task 6d | Patient Queue | Reported in the Task 6d brief; reproduced first by a failing test | A patient sent to the Doctor without an intake could not be opened by the Doctor: no button on his queue, the dashboard led back to the queue, the record page refused the visit | No action was defined for "Waiting for the Doctor" without a consultation record | **See patient** on the Doctor's queue and dashboard; opens the saved intake or a new linked consultation; one status × role mapping for buttons and server rules | `verify_doctor_worklist_and_left.py` "the Doctor's Patient Queue offers 'See patient' on that row", "it opens a new consultation form for this visit…"; status × role walk (8 states × 4 roles × 8 actions) | `47f01af` (failing test), `810ebd7`; tracker M39 |
| F24 (M40) | Patient Queue | Recorded in Task 6e | Changing the service of a visit Waiting for the Doctor to a non-Doctor service set it Completed with no service recorded | The correction function completed the visit | It goes to In Consultation instead; refused while the room is busy | `verify_doctor_worklist_and_left.py` "with the room busy, the correction is refused…" and the "never leaves Completed" checks (199–209) | `3e43d12`; tracker M40 |
| F25 (M41) | Immunization | Adviser review | A dose with nothing recorded here read "Overdue", though the child may have been vaccinated elsewhere; a dose given elsewhere could not be recorded outside a consultation | The record had no field for what a dose rests on (given here, card, or a parent's word) | Evidence types (given here, card, parent's report); "No record" instead of "Overdue"; Record dose given elsewhere | `verify_immunization_evidence.py` "it shows 'Parent says given — no card', amber, and is not counted as given" | `222eeb1`, `7ef616b`; tracker M41 |
| F26 (M43) | Patient Queue | Recorded in Task 10 | The Doctor's dashboard counted visits from earlier days that the Patient Queue did not show, so Staff could not mark them Left | The queue listed only today and, from earlier days, only status Waiting | "Open visits from earlier days" lists every open status with its actions; dashboard count and queue agree | `verify_doctor_worklist_and_left.py` "it lists every open earlier visit, whatever its status…", "the Doctor's list, the dashboard count and the queue (today + earlier days) all agree" | `8788c5d`; tracker M43 |
| F27 (M44) — Task 12 | Inventory | Adviser review | Restocking overwrote the item's one quantity and one expiry date, so the system lost which boxes expire when | One stock figure and one expiry per item | Stock by batch (lot, expiry, source, brand); Receive / Remove / Edit details; FEFO dispensing; expired batches never used | `verify_inventory_batches.py` "dispensing takes from the earliest expiry, even if it arrived later", "an expired batch is never used…" | `dde676f`; tracker M44 |
| F28 (M45) | Inventory | Adviser review | Medicines had a free "Medicine name" beside generic and brand (RA 6675) | Form design | Generic name, strength, dosage form; display name built; duplicates refused; brand on the batch | `verify_inventory_batches.py` "the same generic name, strength and form is refused as a duplicate (any case, any spacing)" | `dde676f`; tracker M45 |
| F29 (M46) — Task 13 | Immunization | Adviser review | A 1-month-old could be given a dose meant for older babies; a dose could be recorded before the previous dose or too soon after it | No eligibility rule | `dose_eligibility()` (minimum age, previous dose, interval); greyed-out form; server refusal; card doses given too early flagged | `verify_immunization_timing.py` "a 1-month-old: Pentavalent, OPV and PCV dose 1 show greyed out…", "a forged POST for … for the 1-month-old is refused, with the earliest date" | `a0eb5d2`; tracker M46 |
| F30 (L52–L54) | Immunization | Task 13's data check found one dose given here before its minimum age; L53, L54 recorded in the same task | That dose still counted; a correction could move a dose to a too-early date; a too-early dose could not be repeated | Only card doses were judged; one record per dose allowed | Every dose judged by one rule; repeats as new records; corrections checked | `verify_immunization_timing.py` sections 5–9 (126/126) | `6b64783`; tracker L52–L54 |
| F31 (M47–M49) | Immunization / Patient Records | Team in real use (a baby born 2026-09-03) | "Record dose given elsewhere" was offered on doses the baby was too young for; due dates ignored the repeat; ages showed only months, so 5 and 6 weeks could not be told apart | No age check on the button; due date from birth; age helper in months | Button only from 4 days before the minimum age; due date = earliest real date; ages in days / weeks / months / years | `verify_immunization_timing.py` section 10; `verify_final_fixes.py` "the registration page's age preview (JavaScript) gives the same text as the helper for 747 birth dates" | `747c69d`, `53be75b`; tracker M47–M49 |
| F32 (M50) | System Settings (network) | Comparison with the approved Proposal (`fb2b1ad`) | Only the server computer could use the system; opening it would have sent passwords and records in plain text | The server listened on 127.0.0.1 over HTTP | Local mode (default) and network mode over HTTPS only (cheroot, TLS 1.2+), refusing to start without a valid certificate; Secure cookie | `verify_network_mode.py` "network mode with no certificate refuses to start…", "in network mode the session cookie is Secure, HttpOnly and SameSite=Lax" | `c8c7c95`, `a1d8eeb`; tracker M50 |
| F33 (M51) | All screens (mobile) | Comparison with the Proposal; measured in a real browser | At 390 px the signed-in pages were 638–778 px wide; the header, tables and buttons ran off the screen | A fixed 280 px sidebar and no small-screen rules | Slide-in menu below 992 px, scrolling tables, one-column fields, full-screen dialogs, 44 px targets | `verify_mobile_layout.py` "no sideways scroll" on every page at 360 and 390 px; 992 px and wider unchanged (26,287 elements on 63 pages compared) | `30040fa`, `548b518`; tracker M51 |
| F34 (L60) | Network mode | Task 16 testing | A plain HTTP request to the HTTPS port printed a traceback (WinError 10038) to the console; the request was still refused | cheroot wrote an error page onto a socket the failed handshake had closed | `utils/server.py` closes that socket itself and writes one line to `logs/errors.log` | `verify_network_mode.py` three checks (console empty, one log line); they fail on the old code | `179c491`; tracker L60 |
| F35 (L63) | Patient Records | Automated test: the phone-layout suite (Task 17) | For the Administrator, the Patient Records page stopped with "Cannot read properties of null (reading 'addEventListener')" | The filter script assumed a Last Visit filter that the Administrator's demographics-only page does not have | The script skips a filter the role does not have; the phone suite now fails on any script or console error, and its list of known exceptions is gone | `verify_mobile_layout.py` "no script errors" on every page, every width | `0eb3538`, `cd773d4`; tracker L63 |
| F36 (L65) | Patient Records / Queue (mobile) | Task 17 review | (Latent) the pinned name column was the third column by position; a new column before it would pin the wrong one | CSS `nth-child(3)` | The column carries the class `pin-name` | `verify_mobile_layout.py` "the patient name column stays pinned while the table scrolls" | `cd773d4`; tracker L65 |

**Defects in the tests themselves (found and fixed).** These made a test weaker or flaky, not
the system wrong, and are reported for honesty:
- `verify_staff_capabilities.py` checked that a placeholder text was absent; the text no longer
  existed, so the check always passed. Now it uses the real placeholder and fails on a sealed
  record (L13, Task 1b).
- The Task 6 page check counted redirects to the password-change page as "loaded". Found in
  Task 6b; `verify_demo_data.py` now clears the first-sign-in flag and loads every page.
- `verify_cleanup.py` read only the first list of the sidebar and missed User Management, Audit
  Logs and Settings (fixed in the final fixes).
- `verify_doctor_worklist_and_left.py` failed when run before 09:00 (fixed clock times; fixed in
  `5934c80`).
- `verify_network_mode.py` hung or crashed on its first runs because an error skipped `stop()`
  and cheroot's threads kept the process alive; the server is now stopped in a `finally`.
- Several mutations were first not caught or not effective and needed a stronger check; each
  case is named in the Task Log (e.g. Task 6d, Task 12, Task 13, Task 15, Task 16).

---

## 5. Performance (section 4.3D and Table 4.1)

**Script:** `tests/perf/measure_performance.py` (written for this task; not part of
`run_all.py`). **Output:** `tests/perf/performance_results.md`. Run on 2026-10-09 at 15:53, with
no other test running, by `python tests/perf/measure_performance.py` (defaults: 3 warm-up runs,
then 30 timed runs per action; target 3,000 ms).

**Method.** The script builds the fictional demo database in a new temporary folder (refusing
any path inside the project), makes keys for that run only (so `.env` is not used), and starts
the **production server** in a child process through the same code `python app.py` uses
(`utils/server.run`: cheroot, local mode, 127.0.0.1, plain HTTP, 10 threads; it printed
"Local mode: this computer only. Open http://127.0.0.1:<port>"). Each role signs in through
`POST /login`. Each action is timed from sending the request to the last byte of the
response, with a new TCP connection per request and redirects not followed. Every response
was checked: HTML pages must be 200 and not the sign-in or error page, Excel must start `PK`,
PDF `%PDF`, the backup `IDSBAK1`, the report must not show a range refusal, and each save must
redirect to the patient's profile. A failed check would have been counted as a failed run;
there were none.

**Test computer**

- CPU: 13th Gen Intel(R) Core(TM) i5-13420H (12 logical processors)
- RAM: 15.6 GB
- OS: Windows 11 CoreSingleLanguage (build 10.0.26200)
- Python: 3.14.6
- Flask: 3.1.3
- Server: cheroot 11.1.2, local mode (127.0.0.1, HTTP), 10 threads

**Data.** Fictional demo database built by `seed_demo_data.py` in a temporary folder (148 s), never `app.db`: 1.3 MB as seeded, with 150 patients, 421 visits, 411 consultations, 302 immunizations, 15 inventory items, 27 inventory batches, 354 dispensing rows, 3199 audit entries. Then 66 visits were added for today, Waiting, one per timed save (each run starts its own visit first, untimed, as the queue does).

**Results (milliseconds, 30 timed runs each)**

| # | Action | Role | Request | Median | 95th pct | Min | Max | Within 3 s | Failed runs |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Sign in | all four roles in turn | `POST /login (password check, new session)` | 315 | 342 | 298 | 344 | Yes | 0 |
| 2 | Dashboard (Administrator) | Administrator | `GET /admin/dashboard` | 356 | 444 | 308 | 449 | Yes | 0 |
| 3 | Dashboard (Doctor) | Doctor | `GET /staff/dashboard` | 379 | 429 | 329 | 456 | Yes | 0 |
| 4 | Dashboard (Health Center Staff) | Health Center Staff | `GET /staff/dashboard` | 376 | 424 | 321 | 565 | Yes | 0 |
| 5 | Dashboard (Barangay Official) | Barangay Official | `GET /official/dashboard` | 385 | 417 | 346 | 440 | Yes | 0 |
| 6 | Search patients | Health Center Staff | `GET /staff/patient_records?search=dela` | 115 | 149 | 93 | 189 | Yes | 0 |
| 7 | Open a patient profile | Doctor | `GET /staff/patient_profile/<id>` | 54 | 92 | 37 | 126 | Yes | 0 |
| 8 | Load the Patient Queue | Health Center Staff | `GET /staff/appointment_scheduling` | 343 | 386 | 286 | 390 | Yes | 0 |
| 9 | Load Reports & Analytics (12 months) | Administrator | `GET /admin/reports_analytics?type=all&from=&to= (12 months)` | 361 | 405 | 305 | 455 | Yes | 0 |
| 10 | Export the report to Excel | Administrator | `GET /admin/reports_analytics/export.xlsx (12 months)` | 497 | 540 | 448 | 550 | Yes | 0 |
| 11 | Export the report to PDF | Administrator | `GET /admin/reports_analytics/export.pdf (12 months)` | 1252 | 1402 | 1172 | 1499 | Yes | 0 |
| 12 | Download an encrypted backup | Administrator | `GET /admin/settings/backup.idsbackup` | 111 | 139 | 101 | 144 | Yes | 0 |
| 13 | Save a consultation | Doctor | `POST /staff/consultation/record/<visit> (diagnosis, plan)` | 56 | 78 | 45 | 89 | Yes | 0 |
| 14 | Dispense medicine (FEFO) | Health Center Staff | `POST /staff/consultation/record/<visit> (intake + 1 medicine line)` | 70 | 95 | 53 | 132 | Yes | 0 |

**Checks on what the write runs left:** 33 of 33 Doctor visits and 33 of 33 Staff visits have a
saved consultation (warm-up runs included); all 33 units dispensed came from the usable batch
with the earliest expiry and none from an expired batch. The chosen medicine had 2 usable
batches and no expired batch, so this run shows FEFO order; refusal of an expired batch is shown
by TC026, not by this run.

**Reading the results**
- All 14 actions are within the 3-second target at the 95th percentile. The slowest is the PDF
  export of a 12-month report (median 1,252 ms, 95th percentile 1,402 ms). The dashboards, the
  Patient Queue and Reports & Analytics take about 0.3–0.45 s; a patient profile and a saved
  consultation about 0.05–0.1 s.
- Sign-in (about 0.3 s) includes checking the password hash, which is slow on purpose.
- "Search patients" is the server time for the patient list the header search lands on; the
  matching itself runs in the browser (`patient_records_context()`), so typing is not timed.
- **What these numbers do not cover:** one user at a time (no concurrent-load test); the client
  on the same computer, so no Wi-Fi delay and no HTTPS (network mode was not timed); the time
  the browser takes to draw the page and its charts; and a database larger than the demo data
  (150 patients, 421 visits over 12 months). The test computer is a developer laptop, not the
  health center's PC, whose specifications are not known yet.

---

## 6. Screenshots (section 4.2)

Folder: `docs/verification/chapter4/` (21 PNG files; images there are git-ignored by the
existing `docs/verification/**/*.png` rule, so they are on this laptop only and not in the
commit). Taken on 2026-10-09 in Chromium (Playwright) from the real server (cheroot, local
mode) on the fictional demo database in a temporary folder; desktop at 1366×768, phones at
390×844 with touch on. Every page answered 200 with no script error. Every name, address and
number on them is fictional (`seed_demo_data.py`). The script that took them is not in the
repository; it reuses `tests/perf/measure_performance.py` to build the data and start the server.
For a 12-month report the range is Nov 1, 2025 to Oct 9, 2026.

| File | Caption |
|---|---|
| `01-sign-in-1366.png` | Figure: Sign-in page |
| `02-dashboard-admin-1366.png` | Figure: Administrator dashboard (counts only, no patient list) |
| `03-dashboard-doctor-1366.png` | Figure: Doctor dashboard with the "Waiting for the Doctor" list |
| `04-dashboard-staff-1366.png` | Figure: Health Center Staff dashboard |
| `05-dashboard-official-1366.png` | Figure: Barangay Official dashboard |
| `06-patient-records-staff-1366.png` | Figure: Patient Records list (Health Center Staff view) |
| `07-patient-profile-personal-1366.png` | Figure: Patient profile, Personal Information tab |
| `08-patient-profile-consultations-1366.png` | Figure: Patient profile, Consultation History tab |
| `09-patient-profile-immunization-1366.png` | Figure: Patient profile, Immunization Record tab (DOH EPI doses with evidence and status) |
| `10-consultation-form-doctor-1366.png` | Figure: Record Consultation form opened by the Doctor |
| `11-patient-queue-staff-1366.png` | Figure: Patient Queue (Health Center Staff view) |
| `12-medicine-inventory-staff-1366.png` | Figure: Medicine Inventory list with usable stock and expiry counts |
| `13-inventory-item-batches-1366.png` | Figure: An inventory item and its batches (lot, brand, source, expiry, status) |
| `14-sms-notifications-admin-1366.png` | Figure: SMS Notifications (Administrator view; mode line shows Simulated) |
| `15-reports-analytics-admin-1366.png` | Figure: Reports & Analytics, All Reports over 12 months (Administrator view) |
| `16-service-schedule-admin-1366.png` | Figure: Service Schedule (Administrator view; empty until the health center's service days are confirmed) |
| `17-audit-logs-admin-1366.png` | Figure: Audit Logs |
| `18-settings-admin-1366.png` | Figure: System Settings |
| `19-phone-dashboard-staff-390.png` | Figure: Staff dashboard on a phone (390 px) |
| `20-phone-menu-open-staff-390.png` | Figure: The slide-in menu on a phone (390 px) |
| `21-phone-patient-queue-staff-390.png` | Figure: Patient Queue on a phone (390 px) |

A wider set (every page, every dialog, every role, at 360, 390 and 1366 px) is made by
`python tests/run_all.py mobile` into `docs/verification/mobile/` (also git-ignored).

---

## 7. Facts for the implementation plan and risks (sections 4.8 and 4.9)

### 7.1 Setup steps as built (for 4.8, the implementation plan)

Sources: `README.md` ("Getting started", "Using the system from other devices", "Sealed records
and the encryption key"), the scripts' own headers, `PROJECT_STATUS.md` §7.

**On the server computer (the health-center PC), once:**
1. Install Python 3 and the packages: `python -m venv .venv`, activate it,
   `pip install -r requirements.txt` (the only step that needs internet; Flask 3.1.3, Werkzeug,
   openpyxl, fpdf2, python-dotenv, Flask-WTF, cryptography, cheroot, tzdata). Everything else
   (Bootstrap, Chart.js, fonts) is vendored, so the system runs offline.
2. `python setup_env.py` — creates `.env` with a new `SECRET_KEY` (64 hex characters),
   `SEALED_DATA_KEY` and `IDS_DEBUG=0`. The app refuses to start without a proper key. Safe to
   run twice.
3. Accounts:
   - **Real deployment:** start the app with no `app.db`. It creates an empty database with four
     accounts (`admin`, `staff`, `official`, `doctor`) and random passwords, shown once in the
     terminal. Each person must set a new password at first sign-in. The Administrator then adds
     the real people through User Management (Add User), which also gives a first-time password.
   - **Demo:** `python archive_plain_databases.py`, then `python seed_demo_data.py` (fictional
     data, 5 accounts, passwords printed once); `--replace` archives an existing database first.
4. `python export_sealed_key.py` — asks for YES, prints `SEALED_DATA_KEY` once and writes
   nothing. Write it on paper, seal it in an envelope and give it to the Doctor. Without it,
   sealed records and backups cannot be opened if the computer fails.
5. Turn on BitLocker (or Device encryption) on this PC: the key sits in `.env` on the same disk
   as `app.db` (M23).
6. Optional: put `SEMAPHORE_API_KEY` in `.env` and restart to send SMS for real; otherwise SMS
   is "Simulated" and says so.
7. `python app.py` — local mode: `http://127.0.0.1:5001`, this computer only, served by
   cheroot. `IDS_PORT` changes the port; a port in use gives a plain message.
8. After the health center interview: enter the Service Schedule (Admin) and confirm the
   service list (M35).

**Network mode (other devices on the Wi-Fi), once:**
1. `python setup_https.py` — makes a self-signed certificate (RSA 3072, SHA-256, 2 years) naming
   the computer, `localhost`, 127.0.0.1 and every current network address, in
   `instance/certs/` (ignored by git); prints the addresses and the device steps. Refuses to
   overwrite without `--replace`.
2. In `.env`: `IDS_NETWORK=1`, keep `IDS_DEBUG=0`; start with `python app.py`. It listens on all
   addresses over **HTTPS only** (TLS 1.2 minimum) and refuses to start without a valid
   certificate or with debug on.
3. Windows Firewall: allow Python on **Private networks only**, never Public.
4. Give the server a **fixed address** in the router (a DHCP reservation). If the address
   changes, run `python setup_https.py --replace` and reinstall the certificate (L61; the team
   has not yet decided between this and a small local authority).
5. Install `ids-bphcsn.crt` (never the key) on each device: Windows (Install Certificate →
   Trusted Root Certification Authorities), Android (Settings → Security → Encryption &
   credentials → Install a certificate → CA certificate; use Chrome), iPhone (open the file,
   install the profile, then turn it on under Certificate Trust Settings). Then open the printed
   address, e.g. `https://192.168.1.10:5001`.
6. Settings → Security shows "Network mode: On — open https://<address>:<port>".

**Backups and restore:**
- The Administrator downloads Settings → Backup & Restore → an encrypted `.idsbackup` file
  (AES-256-GCM; key derived from `SEALED_DATA_KEY`). There is no automatic or scheduled backup;
  it is a manual download (the Backup Frequency placeholder was removed in Task 7).
- Restore at the health-center PC: `python restore_backup.py <file>` decrypts into a new
  database in `IDS-BPHCSN-backups` and checks it (`app.db` untouched); `--replace` copies the
  current `app.db` aside first, then puts the backup in place; restart the app. There is no
  Restore button, by design (L34).
- Old plain databases: `python archive_plain_databases.py` encrypts, verifies and only then
  removes them.

**Updates:** `git pull`; `pip install -r requirements.txt` when a package was added; run any new
script in `migrations/` once (each backs up `app.db` first, is safe twice and records itself in
the audit log); `python tests/run_all.py` before use.

### 7.2 Risks and existing mitigations (for 4.9)

"Existing" means in the code or docs today. Open items are marked **open**.

| Risk | Existing mitigation | Where |
|---|---|---|
| The sealed-data key is lost (PC failure): sealed records and every backup become unreadable | Key envelope for the Doctor; backups and restores use the same key | `export_sealed_key.py`, README "Sealed records…" |
| The server PC is stolen or its disk copied | Sealed fields encrypted; backups encrypted; BitLocker recommended. **Open:** BitLocker not verified on the presenting laptop (needs administrator rights); `app.db` outside the sealed fields is plain on disk (M23, accepted) | `utils/sealed_crypto.py`, `utils/backup_crypto.py`, §7 item 5 |
| Data loss (disk failure, deletion, corruption) | Encrypted backup download; `restore_backup.py` checks a backup before it is used; every write commits or rolls back as a whole (`db_connection()`); migrations back up first. **Open:** backups are manual; no schedule | `routes/settings_views.py`, `restore_backup.py`, `database/connection.py` |
| A worker reads clinical data beyond their role | Server-side role checks on every route; one clinical-authority rule; Admin demographics only; Official no patient access; sealed text Doctor-only; all writes audited | `utils/security.py`, `utils/roles.py`, `routes/audit_entries.py`; final-audit marker crawl (0 leaks) |
| Reports identify a person through small numbers | Rows of 1–4 fold into "Other" for the Admin and the Official; sealed visits as one Confidential row | `utils/small_counts.py` |
| A session left open on a shared PC | 30-minute idle and 12-hour limits, enforced on the server | `config.py`, `utils/security.py` |
| Password guessing or weak passwords | 12-character rule (3 of 4 kinds); 5 wrong passwords pause the username for 5 minutes; forced change at first sign-in; random first-time passwords | `models/users.py`, `utils/login_throttle.py` |
| Records sent in plain text over the Wi-Fi | Network mode is HTTPS only, refuses to start without a valid certificate; Secure, HttpOnly, SameSite=Lax cookie; local mode never listens on the network | `utils/server.py`, `setup_https.py`; `verify_network_mode.py` |
| Devices warn about the certificate or stop trusting it when the server's address changes | Fixed address in the router; `setup_https.py --replace`. **Open:** L61 (team decision); not yet tried on a real second PC, Android phone or iPhone (L62) | README "Using the system from other devices" |
| Another website makes a signed-in browser send a request (CSRF, clickjacking) | Form token on every POST; SameSite=Lax; `X-Frame-Options: DENY` | `utils/csrf.py`, `app.py` |
| Debug mode exposes code execution | Debug only with `IDS_DEBUG=1`; refused in network mode | `config.py`, `utils/server.py` |
| A child gets a vaccine too early (extra injection) | Eligibility rule on the form and the server; doses given too early flagged and not counted | `models/immunizations.py` |
| An expired medicine is dispensed | FEFO; expired batches never used or counted | `models/dispensing.py` |
| A visit that needs the Doctor is closed without him | "Send to the Doctor"; Completed refused without a diagnosis; Doctor's list | `models/appointments.py`, `models/queue_actions.py` |
| SMS not delivered, or believed sent when it was not | Mode line "Live" / "Simulated" on Settings and SMS Notifications. **Open:** no Semaphore key set, so no real SMS has been sent; live sending is one message at a time with a 15-second timeout (final-audit note) | `utils/sms.py` |
| The service list or schedule does not match the health center | Service Schedule built and empty on purpose. **Open:** interview needed (M35); second IPV dose not confirmed (L11) | `models/doctor_worklist.py`, `models/service_schedule.py` |
| Old copies of the database with real data outside the project | `archive_plain_databases.py` for `IDS-BPHCSN-backups`. **Open (outside the repo):** H7 `../classcheck_backups`, M19 old AI-session folders | tracker H7, M19 |
| Users find the screens hard to use | Plain wording (no text over 160 characters on menu pages, tested); phone layout. **Open:** no usability or acceptance test with real users yet | `verify_cleanup.py`, `verify_final_fixes.py`, `verify_mobile_layout.py` |
| Screens not usable on the staff's own phones | Phone layout checked at 360 and 390 px in Chromium. **Open:** not tried on a real Android phone, Safari, 320 px or large font (L64) | `verify_mobile_layout.py` |
| Default accounts left with first-time passwords | Each must change at first sign-in. **Open:** on the demo laptop, 5 of 5 accounts still must (final audit, §7 item 2) | `models/users.py` |
