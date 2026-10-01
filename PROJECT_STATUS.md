# IDS-BPHCSN — Project Status

Last updated: 2026-10-01
Updated by: Task 5 — sealed record privacy

Sections 1–7 started as a read-only status audit. The Task Log below says what each task after it changed. The live `app.db` has only ever been opened read-only by these tasks.

---

## 1. Where We Left Off

### Task Log

Newest first.

| Date | Task | Result |
|---|---|---|
| 2026-10-01 | Task 5 — sealed record privacy | H4 and L2 done. A sealed consultation's diagnosis and treatment plan are stored encrypted (AES-256-GCM, key `SEALED_DATA_KEY` in `.env`, separate from SECRET_KEY). Only `open_sealed_value()` decrypts, and only for the Doctor. The backup holds ciphertext, is VACUUMed, and still restores. No audit entry quotes a diagnosis or treatment plan, sealed or not. Reports show sealed visits as one "Confidential" row. Exports and Print Record never carry sealed text. A key that cannot open a record shows one plain line and is audited. `migrate_redact_clinical_audit_text.py` ran on this laptop's `app.db`: backup `app.db.PRETASK_BACKUP_redact-clinical-audit-text_20261001_161011`, 9 entries redacted, 0 sealed records to encrypt, 1 record entry (filed under account 1, the first active Administrator, and saying the migration did it). New: `export_sealed_key.py`, suite `verify_sealed_privacy.py`. Each laptop must run `pip install -r requirements.txt` (new package `cryptography`), `python setup_env.py` (adds the key), then the migration. Known limits recorded as M21–M23 and L19–L20. Tests: 1565/1565, 16 of 16 suites. |
| 2026-10-01 | Task 4 cleanup | L18 done. The two test fixture numbers with a real-looking `0917` prefix are now the fictional `0900000NNNN` pattern. The two dead functions the audit-coverage EXEMPT list carried, `set_appointment_status` and `remove_immunizations`, are deleted along with their EXEMPT entries and the comments explaining why they were kept, after a repo-wide search confirmed no callers. |
| 2026-10-01 | Task 4 — audit trail | H3 and M6 done. Patient registration, edits and status changes (a death declaration and its reversal have their own phrases), new consultations, doses recorded at a visit, dispensing, inventory changes and the Patient Queue now write an audit entry, in the same transaction as the change (`routes/audit_entries.py`). A failed or refused write leaves no entry. None of it quotes a diagnosis, a treatment plan, a sealed field, a password or a full contact number. The Audit Logs screen's wrong sentence about what the trail covers is corrected, and so are three stale "Not Tracked" claims this task's first pass missed in `routes/roster_export.py` and `routes/audit_export.py`, which still said patient, inventory and queue writes were unaudited after they had been covered. New suite `verify_audit_coverage.py`, including a structural check that fails if a future write path has no audit entry. Tests: 1457/1457, 15 of 15 suites. |
| 2026-09-29 | Task 3 — CSRF protection | M2 done. Every POST (26 forms, and the keep-alive) must carry a form token (Flask-WTF). A refused request shows "Your session expired" and is audited when the account is known. Logout is a POST form. New suite `verify_csrf.py`. Each laptop must run `pip install -r requirements.txt` once (new package Flask-WTF), or the app will not start. Tests: 1399/1399, 14 of 14 suites. |
| 2026-09-29 | Task H6 — privacy cleanup | H6 and M17 done. Real patient names, patient contacts' numbers, the test-account name and the retired demo passwords were replaced with fictional ones in the files, then in every commit and commit message (`git filter-repo`). Every commit hash changed. The migration `migrate_add_must_change_password.py` now stops when history has no old password; run it with `--flag-all`. Tests: 1331/1331, 13 of 13 suites. |
| 2026-09-29 | Task 2 — security basics | H1 (code side), H2, M1, M3, L1, L5 and L8 done. Secret key from `.env`, debug off, 30-minute idle and 12-hour limits, forced password change, random first-time passwords. The migration ran on this laptop's `app.db` and flagged 4 accounts. New suite `verify_security_basics.py`. Tests: 1331/1331, 13 of 13 suites. |
| 2026-09-28 | Task 1b — fresh install and connection fixes | H5, M16 and L13 done. `schema.sql` now matches the live database (see "Schema drift"). Every app connection goes through `db_connection()`. New suite `verify_database_integrity.py`. Tests: 1249/1249, 12 of 12 suites. |
| 2026-09-28 | Task 1 — repository safety | Tests now live in `tests/` and run with one command on a fresh test database. 5 stale worktrees removed. 54 backup copies moved out of the project. `.gitignore` tightened. The test run found a real defect (H5) and patient names in git (H6). |
| 2026-09-28 | Status audit | Wrote this file. Read-only. |

**Before the first push to GitHub:** H6 is done (Task H6). First confirm the rewritten history is good, then delete the backup bundle `IDS-BPHCSN-backups/repo-before-history-rewrite-20260929_101023.bundle`: it still holds the real data (M18).

**Commit hashes before 2026-09-29 changed in the history rewrite; the notes were updated.** A hash written anywhere outside this repository (chat logs, messages, old notes) no longer points at anything.

### How to run the tests

From the project folder, with the virtual environment active:

```
python tests/run_all.py            all suites
python tests/run_all.py -v         also print each suite's full output
python tests/run_all.py rbac       only the suites whose names contain "rbac"
```

- Each suite gets its own fresh test database, built from `schema.sql` plus test data (`tests/_support.py`), in the system temp folder. It is deleted when the suite ends.
- The live `app.db` is never used. A guard stops the whole run if any database path is inside the project folder. The runner also checks that `app.db` has the same size, time and checksum after the run.
- Test accounts use test-only passwords (`tests/_support.py`), not the demo passwords.
- All test data is made up. The old suites used a real staff member's name for account 4; the tests now use `bhwtest` / "Test Health Worker".
- "All passing" looks like: one `ok` line per suite, then `TOTAL: 1565/1565 checks passed in 16/16 suites` and `All checks passed.` Exit code 0.
- **Today (after Task 5): 1565/1565, all 16 suites pass.** Before Task 1b it was 906/921; every failure came from H5.
- Every POST needs a form token (Task 3). The suites' clients add a valid one for their own session (`tests/_support.py`, `TokenClient`); `verify_csrf.py` uses plain clients to test refusals.
- Run from `.venv` (`source .venv/Scripts/activate` on this laptop). The global Python install has no `python-dotenv`, and the suites fail to import `config` without it.

| Suite | Checks | Result after Task 5 |
|---|---|---|
| verify_epi.py | 15 | 15/15 |
| verify_staff_capabilities.py | 27 | 27/27 |
| verify_add_user.py | 122 | 122/122 |
| verify_my_account.py | 344 | 344/344 |
| verify_password_change_audit.py | 50 | 50/50 |
| verify_edit_user_reset_password.py | 82 | 82/82 |
| verify_rbac.py | 117 | 117/117 |
| verify_reports.py | 61 | 61/61 |
| verify_dispensing.py | 128 | 128/128 |
| verify_doctor.py | 129 | 129/129 |
| verify_service_schedule.py | 157 | 157/157 |
| verify_database_integrity.py (Task 1b) | 18 | 18/18 |
| verify_security_basics.py (Task 2) | 82 | 82/82 |
| verify_csrf.py (Task 3) | 68 | 68/68 |
| verify_audit_coverage.py (Task 4) | 58 | 58/58 |
| verify_sealed_privacy.py (Task 5) | 107 | 107/107 |

Not brought in: the four `d4d04b0e_*` scripts (they print values but have no pass/fail checks; they were only compared between two code trees), the three retired originals that `*_ported.py` replaced, the mutation worktrees, and one Doctor-suite check that ran old code from a worktree (L13).

### Where backups live

Copies of `app.db` go in the folder **`IDS-BPHCSN-backups`**, next to the project folder (same parent folder). Never in the project folder. They hold patient records. `.gitignore` also ignores any backup copy by name, as a second guard.

### Schema drift (Task 1b)

A fresh install (`schema.sql`, then the seed) was compared with the live `app.db` (read-only): tables, columns, types, NOT NULL, defaults, keys, foreign keys, CHECKs, indexes and triggers. Five differences were found.

| Difference | Resolved how |
|---|---|
| `consultations.updated_at`: NOT NULL with a default (fresh) vs nullable, no default (live) | `schema.sql` now matches live. Made by `migrate_add_consultation_columns.py`. This was H5. |
| `consultations.restricted_by` foreign key: ON DELETE RESTRICT (fresh) vs no ON DELETE (live) | `schema.sql` now matches live. The migration left it out on purpose (`migrate_add_consultation_restriction.py:63-67`), and nothing deletes accounts. |
| Column order in `consultations`, `inventory_items`, `patients` | Left as is. Live order comes from `ALTER TABLE ADD COLUMN`. No code reads columns by position: every INSERT names its columns, and audit text follows label order (`models/audit.py:839-866`). |

Everything else matches. `tests/verify_database_integrity.py` checks the consultations table of a fresh install against a stored structure, so it cannot drift back.

### Git snapshot

This table is the state found by the audit, before Task 1.

| Item | Finding |
|---|---|
| Branch | `master` (the only branch). No remote is configured: `git remote -v` prints nothing. |
| Working tree | Clean. No modified, staged or untracked files. |
| Stashes | None. |
| Total commits | 102. |
| Last commit | `b95dae6`, 2026-09-26 12:28 (+08:00). |
| Ignored but present | `app.db` (modified **2026-09-28 18:52**, after the last commit), 54 `app.db.*BACKUP*` copies in the root (moved out in Task 1), `.claude/`, `.vscode/`, and screenshots in `docs/verification/vaccination-correction/`. |
| Extra worktrees | 5 detached worktrees registered in `.git/worktrees/` (`wt_after`, `wt_base`, `wt_mut1`, `wt_mut2`, `wt_predoctor`). They sit in an earlier session's temp folder. `wt_mut1` changes `models/service_schedule.py:114` and `wt_mut2` changes `routes/admin.py:962`, both marked `# MUTANT`. These are deliberate mutation tests from the Service Schedule verification, not unfinished work. (Removed in Task 1.) |

### Last 20 commits

| Hash | Date | Message |
|---|---|---|
| b95dae6 | 2026-09-26 | Record the RBAC suite repair: it builds its own fixtures and runs again |
| be20dfc | 2026-09-26 | Show only known messages on the login form, never the text in the URL |
| 355c2ed | 2026-09-26 | Record that the self-deactivation message defect is fixed, and how it was verified |
| b9f2185 | 2026-09-26 | Tell an Administrator who deactivates their own account that they did |
| fe2cfb9 | 2026-09-26 | Record how the Service Schedule was verified, and what was not |
| 5645021 | 2026-09-26 | Say in the documents that there are 22 screens, and what the 22nd is |
| 9d13b7f | 2026-09-26 | Say at the top of the Patient Queue which services run today |
| f87282d | 2026-09-26 | Give every role a Service Schedule screen, and only the Administrator a pen |
| 085d14d | 2026-09-26 | Add a place to record which services run on which days, and leave it empty |
| 33c3831 | 2026-09-25 | Sort the old suite failures into stale tests and one real defect |
| 8818686 | 2026-09-25 | Let the Doctor read Reports & Analytics, with the same figures as everyone else |
| b9c05b4 | 2026-09-25 | Say in the documents that there are four roles, and that the Administrator is not the doctor |
| 113d6b7 | 2026-09-25 | Let only the doctor diagnose, seal, read what is sealed, and declare a death |
| 262465a | 2026-09-24 | Add a Doctor role, and an account to hold it until the RHU names one |
| 50990b7 | 2026-09-06 | Let a dose given at another facility be recorded as one, instead of claimed |
| cb0bae2 | 2026-09-05 | Record the browser pass, and finish the sentences the last four commits missed |
| d10ac7b | 2026-09-05 | Take the sheet of future visits out of a file that can no longer hold one |
| b66263a | 2026-09-05 | Call the screen what it now is, and say on it what it no longer does |
| e493402 | 2026-09-05 | Take the booking surfaces off the screens that offered them |
| cd211fc | 2026-09-05 | Take away every way to record a visit for a day that has not come |

### What happened after the last commit

No code changed after 2026-09-26. The live database did change. The last four audit rows (read-only query on `audit_logs`) show:

| Audit id | Time (PHT) | Event |
|---|---|---|
| 1277 | 2026-09-26 13:04 | `admin` signed in. |
| 1278 | 2026-09-28 18:46 | `admin` changed account `official` from Barangay Official to **Doctor**. |
| 1279 | 2026-09-28 18:46 | 31 seconds later, `admin` changed it back to Barangay Official. |
| 1280 | 2026-09-28 18:52 | `admin` renamed account `doctor` from "RHU Physician (demo)" to a real physician's name. |

The `app.db` modification time (18:52:51) matches audit row 1280. There was no new sign-in on 2026-09-28, so the session from 2026-09-26 was still open two days later.

### Best judgment of the in-progress task

1. **The last coding task is finished and committed.** Sep 24–26 added the Doctor role, moved clinical authority to it, added the Service Schedule, and fixed two defects (self-deactivation message, login `?error=` echo). Each has a verification note under `docs/verification/`.
2. **The task in progress is operational: setting up the real Doctor account.** Commit `262465a` says "The team renames it through Edit User", and on 2026-09-28 the team did. The rename is done. The password was **not** changed. The account still signs in with the password written in `models/users.py:141` (checked read-only against the stored hash). The brief role switch on `official` looks like someone trying the Doctor screens before renaming the real account.
3. **Open items left by the last session:**
   - The Service Schedule table is empty (0 rows) on purpose until the health center is interviewed (`085d14d`; `models/service_schedule.py:23`).
   - Three screens still print query-string text: Reports range errors, and Register Patient's check-in reason and address prefill. These were recorded, not fixed, in `docs/verification/login-message-lookup/README.md` (commit `be20dfc`).

Completeness of the in-progress task: about half done. Name set; password, contact details and a decision on the demo account are still open.

### Tests

**Update (Task 1):** the suites are now in `tests/`. See "How to run the tests" above. The last recorded Add User result was 122/122 (the suite gained 3 checks with the fix in `b9f2185`), not 119/119.

At audit time: not run. There was no test suite in the repository. The suites (RBAC, Doctor role, reports, dispensing, EPI and others) live in an earlier session's Windows temp folder (`...\AppData\Local\Temp\claude\C--IDS-BPHCSN\15a6f5db-...\scratchpad\suites\`). The runner there says it works on database copies (`run_suites.py`, header), but it runs in the detached worktrees and was not inspected in full. Following rule 2, it was skipped. The last recorded results are in commit `33c3831`: RBAC 117/117, Doctor role 129/129, dispensing 128/128, Add User 117/119 (the 2 failures were the self-deactivation defect, since fixed in `b9f2185`).

---

## 2. Module Status

### How the app is built

| Item | Finding |
|---|---|
| Entry point | `app.py:46` `create_app()`; `app.py:67` runs `app.run(debug=True, port=5001)`. |
| Config | `config.py`: plain module; `SECRET_KEY` from the environment with a hardcoded fallback (`config.py:12`). |
| Database | SQLite file `app.db` in the project root (`config.py:13`). New connection per call (`database/connection.py:27`). |
| Schema | `schema.sql` is run once when `app.db` does not exist (`database/schema.py:7-26`), then `seed_demo_users()` runs. Existing databases are evolved by 23 standalone `migrate_*.py` scripts. No migration framework. |
| Blueprints | `auth` (/), `admin` (/admin), `staff` (/staff, shared by Health Center Staff and Doctor), `official` (/official). See `routes/__init__.py`. |
| Size | 94 view functions: 46 admin, 29 staff, 13 official, 6 auth. |
| Stack actually used | Flask 3.1.3 (`requirements.txt:1`), SQLite, Bootstrap and Chart.js vendored in `static/`, vanilla JS (no jQuery found), openpyxl and fpdf2 for exports. |

```
app.py  config.py  schema.sql  populate_records.py  migrate_*.py (23)
database/   connection.py, schema.py
models/     appointments, appointment_sms, audit, backup, broadcasts, consultations,
            dispensing, general_vaccinations, immunizations, inventory, patients,
            service_schedule, settings, users
routes/     admin, auth, staff, official (blueprints) + *_views.py builders + *_export.py
utils/      roles, security, context, endpoints, sms, phone, dates, names, unavailable,
            workbook, document
templates/  24 pages + _print.html, _chart_table.html
docs/verification/   23 verification notes (images git-ignored)
PR0MPT_INSTRUCTION/  01–10 planning docs + Capstone_Proposal.pdf
```

### Module table

| Module | Status | Main routes | Templates | Tables | Gaps |
|---|---|---|---|---|---|
| Patient Records | Complete | `admin.py:114-276`, `staff.py:117-283, 556` (list, profile, register/edit, status, Excel/PDF, selection export) | patient_records, patient_profile, register_patient | patients (+ reads consultations, immunizations, general_vaccinations, medicine_dispensing, appointments) | Writes are not audited (`routes/audit_views.py:58`). PhilHealth No. always shows "Not recorded"; no column (`templates/patient_profile.html:407, 541`). |
| Medicine Inventory + low stock | Complete | `admin.py:342-391`, `staff.py:294-340` | medicine_inventory, add_edit_medicine | inventory_items, medicine_dispensing | Low-stock alert is one function, `models/inventory.py:598`, used by the badge, dashboards and reports. Add/edit/archive and dispensing are not audited. |
| Walk-in Queue (Patient Queue) | Complete | `admin.py:418-477`, `staff.py:367-422` (view, export, check-in, start, complete) | appointment_scheduling | appointments | No way to close a patient who leaves before being seen; the row stays Waiting (`utils/unavailable.py:399`). "Booked" column is a leftover from booking (`templates/appointment_scheduling.html:631`). Queue actions are not audited. |
| Service Schedule | Complete (code); no data | `admin.py:948-1001` (edit, Admin only), `staff.py:627`, `official.py:204` (read) | service_schedule | service_schedule (0 rows) | The team must enter the real service days. |
| Consultations | Complete | `admin.py:490, 516`, `staff.py:435, 466` | record_consultation | consultations, medicine_dispensing, immunizations, general_vaccinations | New consultations write no audit entry; only edits do (`routes/consultation_views.py:1508`). No list of visits waiting for the Doctor's diagnosis. |
| Immunization (EPI) | Complete | Recorded inside consultations; correction at `admin.py:231`, `staff.py:223` | record_consultation, patient_profile (vaccine tab) | immunizations, general_vaccinations | Schedule follows the DOH EPI infant schedule (`models/immunizations.py:116-140`: BCG, HepB, Penta×3, OPV×3, PCV×3, IPV×1, MR 9 mo, MMR 12 mo). Whether DOH's second IPV dose applies: Not verified. |
| Reports and Analytics | Complete | `admin.py:579-618`, `staff.py:521-541` (Doctor only), `official.py:47-88` | reports_analytics, _chart_table, _print | reads all clinical tables | Some UI text is wrong (Issue M6). Prenatal and programme enrolment are shown as "not recorded" (`routes/report_views.py:263-283`). |
| Community Reports, Health Programs, Vaccination Campaigns (Official) | Partial | `official.py:126-182` | community_reports, health_programs, vaccination_campaigns | reads only | Real data where it exists; invented figures were removed and replaced with "not recorded" notes (`routes/official_views.py:30-40`). |
| Official Notifications | Missing (placeholder) | `official.py:196-199` renders with no data | notifications | none | Screen says notifications are not recorded (`utils/unavailable.py:676`). |
| Community SMS | Partial | `admin.py:549, 561`, `official.py:98, 111` (send), `staff.py:494` (read only) | sms_notifications | sms_broadcasts, sms_broadcast_recipients, appointment_sms_messages (history only) | Semaphore call exists (`utils/sms.py:39-68`) but no API key is set, so every send is saved as "simulated" (`utils/sms.py:190-218`). Plain text only; GSM-7/UCS-2 segment counting at `utils/sms.py:115`. |
| Account Management | Complete | `admin.py:631-770` (add, edit, reset password, activate/deactivate, export); `auth.py:470, 495` (My Account, own password) | user_management, my_account | users, audit_logs | No email or SMS of passwords anywhere (no mail code in the project). Reset uses a password the Administrator types. Demo passwords are a problem (Issue H1). |
| Settings: General | Complete | `admin.py:858` | settings (`pane-general`) | settings | — |
| Settings: Password Policy | Partial | none (display only) | settings (`pane-pwd`, line 793) | none | Read-only display of the fixed rule in `models/users.py:374-375` (12 chars, 3 of 4 kinds). Not configurable. |
| Settings: Backup | Partial | `admin.py:930` (download) | settings (`pane-backup`) | reads whole DB | Download only. Restore not built (`utils/unavailable.py:637`). Backup includes sealed diagnoses (Issue H4). |
| Settings: Maintenance Mode | Complete | `admin.py:914` | settings (`pane-maint`), maintenance | settings | Enforced on every guarded route (`utils/security.py:416`) and at login (`routes/auth.py:409-416`). |
| Settings: other panes | Missing (disabled on purpose) | — | settings | — | Health Center Information, SMS Gateway, Security toggles (2FA, auto logout) are disabled with a reason (`utils/unavailable.py:601, 664`). |
| Authentication | Complete | `auth.py:330-461` | login | users, audit_logs | Session re-check every request (`utils/security.py:360-419`). No CSRF, no idle timeout, weak secret fallback (Issues H2, M2, M3). |
| Restricted/Sealed records (RA 11166) | Complete (screens) | `staff.py:265` (Doctor only) + record/edit form | patient_profile, record_consultation | consultations.is_restricted / restricted_by / restricted_at | Redacted on profile, dispensing join and edit form. Still readable by the Administrator through the backup file and older audit entries (Issue H4). 0 sealed records in live data. |
| Audit Logs | Partial | `admin.py:783-809` | audit_logs | audit_logs | Only sign-in, users, settings, SMS, consultation edits, immunization corrections, confidentiality and schedule are logged (`models/audit.py:133-489`). |
| Dashboards | Complete | `admin.py:103`, `staff.py:107` (Staff and Doctor), `official.py:37` | admin_dashboard, staff_dashboard, official_dashboard | reads only | — |

---

## 3. Roles and Permissions

### How roles are stored and enforced

- **Storage:** `users.role` with `CHECK (role IN ('Admin','Doctor','Health Center Staff','Barangay Official'))` (`schema.sql:12`). Four roles.
- **Normalizing:** `utils/roles.py:16-27` maps spellings to `admin`, `doctor`, `health staff`, `barangay official`.
- **Route guards:** `@login_required` and `@role_required(...)` (`utils/security.py:422-453`). Both re-read the stored account on each request. They check that it exists, is active, and is allowed through maintenance mode.
- **Clinical rules inside shared builders:** `holds_clinical_authority()` (`utils/roles.py:47`) is the single rule. `can_diagnose()` (`models/consultations.py:177`), `can_view_restricted()` (`models/consultations.py:198`) and `can_declare_death()` (`models/patients.py:157`) all delegate to it. The role comes from the stored row via `current_role()` (`utils/security.py:137`), not from the request.
- **Templates:** hide controls too, but every restricted action checked below also has a server-side check.

### Permission matrix

A = Allowed, D = Denied. "Denied (no route)" means no URL exists for that role.

| Action | Admin | Doctor | HC Staff | Brgy Official | Enforced at |
|---|---|---|---|---|---|
| Sign in, My Account, change own password | A | A | A | A | `auth.py:337, 470, 495` |
| Own dashboard | A | A | A | A | `admin.py:103`, `staff.py:107`, `official.py:37` |
| Patient Records list / profile / export | A | A | A | D (no route) | `admin.py:114-259`, `staff.py:117-283` |
| Register / edit patient | A | A | A | D (no route) | `admin.py:276`, `staff.py:556` |
| Mark Active ↔ Inactive | A | A | A | D (no route) | `admin.py:210`, `staff.py:206` |
| **Mark Deceased / reverse Deceased** | D | A | D | D | Route admits Admin/Staff, refused in `routes/patient_views.py:406-411` |
| Correct an immunization record | A | A | A | D (no route) | `admin.py:231`, `staff.py:223` |
| Medicine Inventory view / export | A | A | A | D (no route) | `admin.py:342-361`, `staff.py:294-314` |
| Add / edit / archive inventory item | A | A | A | D (no route) | `admin.py:374, 391`, `staff.py:327, 340` |
| Patient Queue view, check-in, start, complete | A | A | A | D (no route) | `admin.py:418-477`, `staff.py:367-422` |
| Record / edit consultation intake (vitals, complaint, vaccines, dispensing) | A | A | A | D (no route) | `admin.py:490, 516`, `staff.py:435, 466` |
| **Write diagnosis / treatment plan** | D | A | D | D | Stripped server-side: `routes/consultation_views.py:178-215` (`can_diagnose`) |
| **Seal / unseal a consultation** | D (no route) | A | D | D (no route) | `staff.py:265` `role_required("Doctor")` + `routes/consultation_views.py:1603` |
| **Read a sealed diagnosis on screens** | D | A | D | D | `models/consultations.py:198`, `routes/patient_views.py:583`, `models/dispensing.py:746` |
| SMS Notifications view | A | A (read) | A (read) | A | `admin.py:549`, `staff.py:494`, `official.py:98` |
| Send SMS broadcast | A | D (no route) | D (no route) | A | `admin.py:561`, `official.py:111` |
| Reports & Analytics + exports | A | A | D | A | `admin.py:579-618`, `staff.py:521-541` (Doctor only), `official.py:47-88` |
| Community Reports, Health Programs, Vaccination Campaigns, Notifications | D (no route) | D (no route) | D (no route) | A | `official.py:126-199` |
| Service Schedule view | A | A | A | A | `admin.py:948`, `staff.py:627`, `official.py:204` |
| Service Schedule add / edit / delete | A | D (no route) | D (no route) | D (no route) | `admin.py:975-1001` |
| User Management (add, edit, reset, status, export) | A | D (no route) | D (no route) | D (no route) | `admin.py:631-770` |
| Audit Logs + exports | A | D (no route) | D (no route) | D (no route) | `admin.py:783-809` |
| Settings, maintenance switch, backup download | A | D (no route) | D (no route) | D (no route) | `admin.py:819-930` |
| Use the system during maintenance | A | D | D | D | `utils/security.py:416`, `routes/auth.py:409-416` |

Wrong-role requests redirect to the user's own dashboard (`utils/security.py:442-443`).

### Template-only restrictions

None found. Every route carries a guard. The only unguarded routes are `/`, `/login` and `/logout`, which are meant to be public. Each hidden control checked has a matching server check: diagnosis, seal, Deceased, schedule edit, and SMS send.

### Clinical actions a non-physician can perform

- Through screens and routes: **none.** Diagnosis, treatment plan, sealing and declaring death are all refused server-side for everyone but the Doctor.
- Through side channels, the **Administrator (not a physician) can still read sealed diagnoses**:
  1. Settings → Download Backup (`admin.py:930`) hands over the whole database, sealed text included.
  2. Audit Logs entries written before `113d6b7`, or written while a record was not yet sealed, still quote diagnosis text. Existing entries are never rewritten (`models/consultations.py:388-392`). The live DB has 9 unredacted "Diagnosis:" audit entries.
- Existing data: 28 of 29 live consultations have a diagnosis written by a non-Doctor account (6 by Admin, 22 by Health Center Staff), from before the rule existed.

---

## 4. Doctor Role Status

**Complete** (in code, committed 2026-09-24 to 2026-09-26). The team's belief that it is "possibly not built" is out of date.

### Where "doctor" / "physician" appears

| Place | Evidence |
|---|---|
| Schema | `schema.sql:12` (role CHECK), `schema.sql:3` comment |
| Migration | `migrate_add_doctor_role.py` (rebuilds `users` with the new CHECK, adds the `doctor` account) |
| Seed | The demo `doctor` account: see `models/users.py:141` |
| Role list | `models/users.py:162` `CLINICAL_ROLES`, `:298` `ROLE_CHOICES`, `:313` `DOCTOR_ROLE` |
| Single rule | `utils/roles.py:44-49` `CLINICAL_AUTHORITY_ROLE = "doctor"`, `holds_clinical_authority()` |
| Permissions | `models/consultations.py:161, 177, 198`; `models/patients.py:157`; `models/dispensing.py:746` |
| Guards | `routes/staff.py:101` `CLINICAL_FLOOR_ROLES = ("Health Staff", "Doctor")`; `staff.py:265` seal; `staff.py:521-541` reports |
| Login / dispatch | `routes/auth.py:437-442, 518` |
| Server checks | `routes/consultation_views.py:207, 1603`; `routes/patient_views.py:406` |
| Template context | `utils/context.py:58, 108-114, 274` |
| Templates | `base.html:291` (Reports menu), `staff_dashboard.html:6` ("Doctor Dashboard"), `record_consultation.html:919-923`, `patient_records.html:594-622, 834-852`, `patient_profile.html` (10 places), `user_management.html:110, 645`, `settings.html:1004`, `maintenance.html:1` |
| User Management badge | `routes/user_views.py:313` |
| Docs | `01_PROJECT_BIBLE.md` (26 mentions), `03_SCREEN_SPECIFICATIONS.md` (25), `09_...Architecture` (42) |
| Live DB | Account id 5, username `doctor`, role Doctor, active, renamed to a real physician on 2026-09-28 (audit id 1280) |

### What is still missing

1. The live Doctor account still uses the demo password from source code (`models/users.py:141`). Verified read-only against the stored hash.
2. No worklist of consultations waiting for a diagnosis. Staff intake saves the visit with no diagnosis (`routes/consultation_views.py:190-196`), and the Doctor has to find it.
3. Sealed text is still reachable by the Administrator through the backup file and older audit entries (see §3).
4. Old diagnoses written by Admin and Staff accounts stay as they are (`models/consultations.py:53`). The demo data contradicts the new rule.
5. ~~The Doctor's automated suite is outside the repository.~~ Done in Task 1: `tests/verify_doctor.py` (128 checks; one worktree-only check dropped, L13).
6. `README.md` still lists three roles and no Doctor login. `08_PROJECT_ROADMAP.md` never mentions the Doctor.

---

## 5. Issues Found

Severity: High = breaks a feature, or is a security or legal risk. Medium = wrong behavior or confusing. Low = cleanup.
Count: **6 High, 24 Medium, 23 Low.** Done: M11, M15, L9 (Task 1); H5, M16, L13 (Task 1b); H1 (code side), H2, M1, M3, L1, L5, L8 (Task 2); H6, M17 (Task H6); M2 (Task 3); H3, M6, L18 (Task 4); H4, L2 (Task 5). Added in Task 1: H5, H6, M16, L13. Added in Task 1b: L14. Added in Task 2: M17. Added in Task H6: M18, M19, L15. Added in Task 3: M20, L16, L17. Added in Task 4: L18 (done the same session). Added in Task 5: M21–M24, L19–L23.

| # | Severity | File:line | Problem | Suggested direction |
|---|---|---|---|---|
| H1 | High | `models/users.py:138-141`, `README.md:22-23` | All four seeded accounts in the live DB still use the passwords written in source code and README. That includes the `doctor` account now named after a real physician. The Admin/Staff/Official passwords also fail the app's own 12-character rule (`models/users.py:374`). | **Done in code (Task 2):** no password is in the code or README. A new install makes random first-time passwords, shows them once, and each person must change theirs at first sign-in. `migrate_add_must_change_password.py` flagged admin, staff, official and doctor on this laptop. **Fully closed only when every team laptop has run the migration and each flagged account has set a new password.** Task H6 removed the old passwords from every file and every commit, so on any other laptop run the migration with `--flag-all`. |
| H2 | High | `config.py:12` | `SECRET_KEY` falls back to the hardcoded `"ids-bphcsn-dev-secret"`, and there is no `.env`. Anyone with the code can forge a session cookie for any user id, including the Administrator. | **Done (Task 2):** `config.py` has no fallback. The app refuses to start when SECRET_KEY is missing, shorter than 32 characters, or the old default. `python setup_env.py` creates `.env` once per computer. |
| H3 | High | `routes/audit_views.py:58`; `routes/patient_views.py:406-420` | Patient register/edit/status changes (including **declaring a death**), inventory changes, dispensing, queue actions and new consultations write no audit entry. | **Done (Task 4):** every one of these writes an entry through `routes/audit_entries.py`, in the same transaction as the change. `tests/verify_audit_coverage.py` includes a structural check so a future write path cannot skip it. |
| H4 | High | `routes/admin.py:930`; `models/consultations.py:388-392` | The Administrator (not a physician) can read sealed diagnoses through the backup download and through audit entries written before sealing. This is an RA 11166 risk. There are 0 sealed records today, so it is a risk path, not a current leak. | **Done (Task 5):** sealed diagnosis and treatment plan are encrypted in the database, so the backup carries ciphertext (and is VACUUMed, so no old plain text sits in free pages). No audit entry quotes either field, and the migration removed the text from the 9 older entries. Limits that remain: M21–M23, L19–L20. |
| H5 | High | `schema.sql:114` (consultations `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`); `models/consultations.py:999-1005` | On a database built from `schema.sql` (any fresh install or new clone), recording a consultation fails with HTTP 500: the insert writes `updated_at = NULL` into a NOT NULL column. The live `app.db` works only because a migration added this column as nullable. Found by the test run in Task 1. **Done (Task 1b):** `schema.sql` now declares `updated_at TEXT` (nullable, no default), as the live DB does, so the app behaves the same on both. | — |
| H6 | High | 12 tracked files, e.g. `docs/verification/retire-advance-booking/README.md`, `migrate_clear_seeded_remarks.py`, `AUDIT_REPORT_2026-08-06_v2.md`, comments in `models/audit.py` and `routes/user_views.py`; 10 commits; 3 commit messages | 16 of the 29 patient full names in the live `app.db`, and 6 patient contact numbers, appear in tracked files and in git history. They are not from the demo seed script. Whether they are real people: Not verified. A push would publish them. | **Done (Task H6):** the 12 patients not from the seed, their contacts, their 11 numbers, the test account named after a real person and the 4 retired passwords now read as fictional names, `0900000NNNN` numbers and "(retired demo password)", in the files and in all history. The team member's name stays where it credits the proposal. |
| M1 | Medium | `app.py:67` | `debug=True` whenever the app starts with `python app.py` (the README's run command). The Werkzeug debugger allows code execution if reached. Default bind is 127.0.0.1, so the risk is lower. | **Done (Task 2):** debug follows IDS_DEBUG; only `1` turns it on. Host 127.0.0.1, port 5001. |
| M2 | Medium | (none found: no `csrf` anywhere) | POST forms have no CSRF token. Logout is a GET (`routes/auth.py:458`). | **Done (Task 3):** Flask-WTF `CSRFProtect` checks every POST (`utils/csrf.py`); each form starts with `{{ csrf_field() }}`, scripts send the X-CSRFToken header from a meta tag, and logout is POST only. |
| M3 | Medium | `templates/settings.html:659`; `config.py` | No idle timeout. The "Auto Logout on Inactivity" toggle is disabled. Audit rows 1277→1278 show a session still in use 2 days after sign-in. Risky on a shared health-center PC. | **Done (Task 2):** signed out after 30 minutes without activity and 12 hours after sign-in (`config.py`), enforced on the server, audited, with a warning 2 minutes before the idle limit (`static/js/session.js`). |
| M4 | Medium | `routes/consultation_views.py:190-196` | Doctor has no "awaiting diagnosis" list; visits saved by staff without a diagnosis are easy to miss. | Add a panel on the Doctor Dashboard. |
| M5 | Medium | `utils/unavailable.py:399` | A patient who leaves before being seen cannot be closed; the row stays Waiting. | Add a "Left without being seen" status. |
| M6 | Medium | `routes/report_views.py:284-289` | Screen text says Audit Logs records "three things: consultation edits, SMS broadcasts, and sign-ins". It also records users, settings, backup, maintenance, confidentiality, immunization corrections and schedule. | **Done (Task 4):** the sentence now names what the trail covers in general terms rather than listing kinds that go stale. The same wrong claim was also found and corrected in `routes/roster_export.py` (three "Not Tracked" rows that said patient, inventory and queue writes were unaudited) and `routes/audit_export.py` (the export's own "Not Tracked" sheet intro). |
| M7 | Medium | `templates/settings.html:793`; `utils/unavailable.py:601, 637, 664` | Settings is less complete than the team believes. Password Policy is display-only, Backup has no restore, and three panes are disabled. | Confirm this is acceptable for the defense, or finish the missing parts. |
| M8 | Medium | `utils/sms.py:190-218` | No `SEMAPHORE_API_KEY`, so every SMS broadcast is saved as "simulated". Nothing has been sent for real. | Get a Semaphore key before the defense, or state it clearly in the demo. |
| M9 | Medium | `README.md:3`; `routes/report_export.py:253, 373`; `routes/roster_export.py:362, 458`; `routes/audit_export.py:135`; `templates/patient_records.html:179` (and 3 other print headers) | Three project names are used. The correct one (`01_PROJECT_BIBLE.md:12`, `templates/login.html:309`) is "Integrated Digital System … Community Notifications". Printed reports say "Integrated Data System". | Use one constant for the name. |
| M10 | Medium | `templates/user_management.html:526`, `templates/patient_profile.html:713`, audit row 1278 | Wordy UI text. 16 tooltips are over 160 characters (longest 319), and audit sentences run 400–600 characters. Hard for non-native English readers. | Cut to one short sentence each. |
| M11 | Medium | `docs/verification/README.md`; commit `b95dae6` | **Done (Task 1).** The suites are in `tests/`, run with `python tests/run_all.py`, each on a fresh test database. | — |
| M12 | Medium | `git remote -v` (empty) | No remote. The only copy of the code is this laptop. | Push to a private remote. |
| M13 | Medium | live DB; `populate_records.py:251-274` | 28 of 29 demo consultations have diagnoses by non-Doctor accounts, and the seed script still writes diagnoses. This contradicts the new rule during a demo. | Decide whether to clear or reattribute the demo diagnoses. |
| M14 | Medium | `routes/official.py:196-199` | The Official's Notifications screen is a placeholder with no data. | Remove it from the menu, or build it. |
| M15 | Medium | project root (`app.db.*BACKUP*`, 54 files, 26,525,696 bytes) | **Done (Task 1).** All 54 moved to `IDS-BPHCSN-backups` next to the project folder. Count, bytes and every file's checksum match. | — |
| M16 | Medium | `database/connection.py:27`; `models/consultations.py:1007-1011` | A write that fails leaves its SQLite connection open. In the tests, every later write in the same process then failed with "database is locked". Seen after H5. Effect on the running server: Not verified. **Done (Task 1b):** new `db_connection()` in `database/connection.py` closes every connection and rolls back a failed write. All 97 app call sites use it (14 files). | — |
| M17 | Medium | local commits `3fbe423` (Task 1b), `61900c4`, `fbf7cef` (Task 2) | `models/audit.py` and `routes/user_views.py` hold a patient name flagged under H6, and those tasks were told not to touch such files. These three unpushed commits edited them anyway, which adds new versions of files holding that name to git history. `313e758` put both files back to their content from before Task 2 (for `models/audit.py` that still includes Task 1b's connection fix). No new personal data was added. | **Done (Task H6):** the history rewrite covered these commits. The session-timeout phrases went back to `models/audit.py`, and the reset passes `must_change=True` itself again. |
| M18 | Medium | `../IDS-BPHCSN-backups/repo-before-history-rewrite-20260929_101023.bundle` | The backup of the old history taken before the rewrite. It still holds every real name, number and old password that Task H6 removed. | Delete it once the team confirms the rewritten repository is good. Never push or share it. |
| M19 | Medium | `%TEMP%\claude\C--IDS-BPHCSN\` (earlier session folders, outside the repo) | About 30 folders from earlier AI sessions (scratch copies, old suites, task logs), about 530 files, still hold real patient names or the old passwords. Task H6 did not delete them. | Delete the old session folders on this laptop once nothing in them is needed. |
| M20 | Medium | `utils/csrf.py` `_log_refusal()`; `schema.sql` (`audit_logs.user_id` NOT NULL) | A request refused for a bad form token is recorded only when a signed-in account is known. A refused request with nobody signed in (for example the login form) leaves no trace, because an audit row must name an account. | Decide whether anonymous refusals matter. If so, allow a NULL user in `audit_logs` or keep a separate count. |
| L1 | Low | `routes/auth.py:352-353` | Legacy branch compares a plain-text `password` column. The column no longer exists, so this is dead code. | **Done (Task 2):** the branch is deleted. |
| L2 | Low | `routes/consultation_views.py:1000-1002` | The seal flash at record time says the diagnosis is hidden "from Health Center Staff" only; it is also hidden from the Administrator now. | **Done (Task 5):** both seal messages now say the text is hidden from everyone except the Doctor. |
| L3 | Low | `templates/appointment_scheduling.html:631, 676` | "Booked" column is left over from advance booking and is always "—". | Remove the column. |
| L4 | Low | `templates/community_reports.html:542, 554` | "Booked, not yet resolved" and "booked in advance" figures refer to retired booking. | Reword or remove. |
| L5 | Low | `templates/settings.html:655` | A disabled "Two-Factor Authentication" toggle is shown. This is an out-of-scope security add-on. | **Done (Task 2):** the switch is gone, with the other three disabled security controls. The pane now states the session limits in one read-only line. |
| L6 | Low | `templates/patient_profile.html:407, 541` | "PhilHealth No." always shows "Not recorded"; there is no column. | Remove, or add the field. |
| L7 | Low | `templates/patient_profile.html:1355`; `routes/settings_views.py:17`; `routes/report_views.py:258` | Stale comments: Reschedule/Cancel controls (gone), "booking slot generator" (gone), "Medicine only" dispensing (supplies are dispensable now). | Update the comments. |
| L8 | Low | `docs/verification/login-message-lookup/README.md` | Reports range errors and Register Patient (check-in reason, address prefill) print query-string text. It is escaped, so this is text spoofing only. | **Done (Task 2):** report messages come from a fixed table; the check-in reason is handed over by POST and kept in the session; Save & Register Another carries a patient id and reads the address from the stored record. |
| L9 | Low | `.git/worktrees/wt_*` | **Done (Task 1).** All 5 were on commits already in master, with no other commits. Removed with `git worktree remove --force`, then `git worktree prune`. | — |
| L10 | Low | e.g. `utils/security.py:1-89`, `routes/auth.py:1-120` | Very long code comments. Hard for the team to maintain and explain at the defense. | Trim to short summaries; keep the reasoning in docs. |
| L11 | Low | `models/immunizations.py:116-140` | EPI has one IPV dose (14 weeks). Whether a second DOH IPV dose applies: Not verified. | Confirm with the RHU nurse. |
| L12 | Low | `PR0MPT_INSTRUCTION/08_PROJECT_ROADMAP.md:75` | Says "89 guarded endpoints for all three roles". Code has 91 guarded view functions and four roles. | Update with the other doc fixes (§6). |
| L13 | Low | `tests/verify_doctor.py` (section H); `tests/verify_staff_capabilities.py` | Two test gaps. (1) One Doctor-suite check ran the old code from a worktree; it is not run now, and the row it made is written directly. (2) The staff suite checks that "Restricted — Administrator access only" is absent; that text no longer exists, so the check always passes. **Done (Task 1b):** (2) now uses the app's real placeholder text, and fails on a sealed record. (1) is not replaced: it tested old code that no longer exists. What it protected (an old Administrator seal stays sealed) is still checked in section S, and section F checks that the Administrator cannot seal now. | — |
| L14 | Low | `migrate_add_consultation_columns.py:47-52` | Its note says the `updated_at` difference between a migrated and a fresh database is "deliberate" and "the only one". After Task 1b there is no such difference. This task may not edit migrations. | Update the note when migrations are next touched. |
| L15 | Low | `routes/user_views.py` (`process_create_user`, `process_reset_password`) | Task 2 added "must change it the first time they sign in" to the Add User and Reset Password confirmations, then took it out to avoid touching this file under H6. The forms still say it; the confirmation does not. | Put the sentence back in both messages (and the tests that read them). |
| L16 | Low | `routes/auth.py` `logout()` | Opening `/logout` in the address bar (an old bookmark) now shows the framework's plain "405 Method Not Allowed" page, in technical words. It does not sign anyone out, which is correct. | Send a GET to /logout to the dashboard or login page instead. |
| L17 | Low | `static/js/session.js` | The keep-alive handles 204, 401 and (Task 3) 400. A 503 (maintenance mode switched on) is ignored, so the page only shows the maintenance screen at the next click. | Reload the page on a 503, so the maintenance screen appears. |
| L18 | Low | `models/appointments.py:1043`, `models/immunizations.py:1155` | Task 4's audit-coverage EXEMPT list carried two functions, `set_appointment_status` and `remove_immunizations`, kept unused on purpose for a future caller. Confirmed by repo-wide search to have no callers anywhere (routes, templates, JS, tests, migrations). | **Done (session cleanup, 2026-10-01):** both deleted, with the EXEMPT entries and the two comments in `routes/consultation_views.py` that explained why `remove_immunizations` was kept. `PR0MPT_INSTRUCTION/09_IDS-BPHCSN_UI_Architecture_FROM-CLAUDE.md:448` still describes `remove_immunizations()` as deliberately kept and not yet updated. |
| M21 | Medium | `models/dispensing.py`; `templates/patient_profile.html` (Dispensing History); `templates/admin_dashboard.html` (Medicine column) | Known limit (Task 5). What was dispensed at a sealed visit stays readable to every clinical role and in the backup. It is needed for stock counts and for staff to hand the medicine over. A medicine can hint at the condition (for example, an antiretroviral). The Task 4 audit entry already leaves item names out for a sealed visit. | Team decides whether the profile and dashboard should hide item names for a sealed visit from non-Doctors. Stock rows must stay. |
| M22 | Medium | `../IDS-BPHCSN-backups/` | Known limit (Task 5). Backups made before 2026-10-01 hold plain text: the 9 audit entries that quoted diagnoses, and any record sealed before then. That includes this task's own pre-migration backup. | Keep them locked away, and delete them once the team is sure the migrated `app.db` is good. |
| M23 | Medium | `.env` on the health-center PC | Known limit (Task 5). The key sits on the same computer as `app.db`, so encryption protects copies that leave the computer (backups), not the computer itself. If the key is lost, sealed records cannot be opened. | Turn on BitLocker on that PC. Run `python export_sealed_key.py` once and give the key to the Doctor in a sealed envelope (D5). |
| M24 | Medium | `models/consultations.py` `describe_consultation_changes()` | Team decision. D2 covers the diagnosis and treatment plan only. Edit entries still quote the chief complaint and additional notes, which are clinical text read by the Administrator, and those two fields stay plain under a seal. | Decide whether they should be named only, like the diagnosis. |
| L19 | Low | `models/consultations.py` `DOCTOR_ONLY_FIELDS` | Known limit (Task 5), by design. For a sealed visit, the visit date, chief complaint, vital signs, additional notes, immunizations and the fact of the seal stay readable on screens and in the backup. | None needed. The seal covers the Doctor's two fields. |
| L20 | Low | `templates/record_consultation.html` | Known limit (Task 5). Print Record on the profile prints the placeholder for the Doctor, but printing the Edit Consultation form from the browser prints what is on the form, sealed text included. | Add a print stylesheet that hides the two fields, if the team wants it. |
| L21 | Low | `tests/_support.py` (fixture patients' `contact_number`) | Fixture patients use `0917`-prefixed numbers, the real-looking pattern replaced in `verify_audit_coverage.py`. | Use the `0900000NNNN` pattern. |
| L22 | Low | `routes/patient_views.py` `_log_withheld_consultations()` docstring | Says nothing is written "for the Administrator". Since 2026-09-25 the Administrator is withheld from too. | Fix the sentence. |
| L23 | Low | `routes/consultation_views.py` `_log_restriction()` | The seal and lift audit entries are written in their own transaction, after the seal commits. Task 4's "same transaction" rule was not applied here. | Pass the entry into `set_consultation_restriction()` as an `audit` callback. |

Checked and **not** found: `TODO`/`FIXME`/`XXX` markers; `href="#"` or "coming soon" stubs; broken `url_for()` targets (123 literal calls and 73 context endpoint names all resolve); missing static files; "Agusan del Sur" as a live value (it appears only in notes about the correction, in code comments and docs 06/09, and not at all in the live DB); passwords sent by email or SMS; offline mode, national database integration, or non-plain-text SMS.

---

## 6. Documentation Drift

| Document | Says | Code says |
|---|---|---|
| `README.md:3` | "Integrated **Database** System … Services and Notifications" | Bible and login screen: "Integrated **Digital** System … Services and **Community** Notifications" |
| `README.md:5-7, 22-23` | Three roles; three demo logins | Four roles (`schema.sql:12`); a `doctor` account exists |
| `08_PROJECT_ROADMAP.md:5-9, 75, 108, 925` | Last reviewed 5 Sep; "89 guarded endpoints for all three roles"; README "states … the three roles" | Doctor role added 24–25 Sep; 91 guarded view functions |
| `08_PROJECT_ROADMAP.md` | No mention of the Doctor role or the Service Schedule's clinical split | Both built |
| `03_SCREEN_SPECIFICATIONS.md:1328-1329` | Opening time "changes the slots the booking dialog offers" | Booking dialog removed; times only show on screens and letterheads |
| `04_DEVELOPMENT_GUIDE.md:71` | Flask 3.0 | Flask 3.1.3 (`requirements.txt:1`) |
| `04_DEVELOPMENT_GUIDE.md:82, 206` | jQuery via CDN | No jQuery; all assets vendored for offline use (`README.md:18-20`) |
| Team context (this audit's brief) | Doctor role "possibly not built" | Complete (§4) |
| Team context | Settings "done" (4 sections) | General and Maintenance live; Password Policy display-only; Backup has no restore (§2) |
| Team context | SMS through Semaphore done | Built, but simulated until an API key is set |
| `01_PROJECT_BIBLE.md`, `03_...`, `09_...` | Four roles, Doctor holds clinical authority, walk-in queue, 22 screens | Match the code (updated in `b9c05b4`, `8818686`, `5645021`) |
| `06_...`, `09_...` "Agusan" mentions | History of the location correction | Correct as history; no live leftovers |

`02`, `05`, `07` and `10` were only scanned for role, booking and location terms (no hits). They were not reviewed in depth.

---

## 7. Recommended Next Steps

1. **Reset all live passwords and set a real `SECRET_KEY` from the environment.** Anyone with the code can currently sign in as any account or forge a session (H1, H2). *(Code side done in Task 2. On each laptop: pull, run `python setup_env.py` and `python migrate_add_must_change_password.py --flag-all`, then each person sets a new password.)*
2. **Add a private git remote and move the test suites into the repo.** The code exists on one laptop, and the tests sit in a temp folder (M11, M12). *(Tests: done in Task 1. Remote: decide H6 first.)*
3. ~~Audit patient, inventory, queue, dispensing and death-declaration writes.~~ **Done (Task 4).** Every one of these writes an audit entry now (H3).
4. ~~Decide the RA 11166 policy for sealed text in backups and old audit entries, then build it.~~ **Done (Task 5).** Sealed fields are encrypted, and audit entries hold no clinical text (H4). On each laptop run the steps in the Task 5 log line, and give the Doctor the key envelope.
5. **Fix the project name and update README and 08_PROJECT_ROADMAP to four roles.** The docs the team relies on were already wrong about the Doctor role (M9, §6).
