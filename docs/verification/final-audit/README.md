# Final pre-defense audit (2026-10-02)

An independent, read-only audit of the code, the tests and the documents, done before the defense. Every behavior test ran through the Flask test client on a temporary database (the tests' own fixture in the system temp folder) or in a temporary clone. `app.db` was opened read-only (`?mode=ro`) and was used for counts only. Nothing in the repository was changed except this file and `PROJECT_STATUS.md`.

## Verdict

**READY WITH FIXES.**
Every privacy and permission rule held under attack: 2245/2245 checks pass, all 7 break-it mutations were caught, and 40/40 adversarial checks found no leak of a clinical marker, sealed field or full phone number to any role, export, print or backup.
Fix before the defense: H7 (plain copies of the old database in `../classcheck_backups`, outside the repo), M36 (README setup order), M37 (Official sees recipient names), and the docs drift in M38. None of these is a code-level leak of clinical data.

## Claims verified

| # | Claim | Result | Evidence |
|---|---|---|---|
| 1 | Roles: Admin demographics and counts only; the Doctor alone diagnoses, seals, reads sealed records and declares death; Staff check in, take the intake and dispense; the Official has no patient access | **Fail (one gap)** | Route matrix below matches the docs; `utils/roles.py:47` `holds_clinical_authority`, `:63` `is_care_team`; `routes/patient_views.py:322` (Admin gets `get_all_patients_demographics`); `routes/staff.py:249` (seal is Doctor-only); `models/patients.py:158` `can_declare_death`. Adversarial: Staff diagnosis refused, Staff seal/lift refused, Staff "Deceased" refused, Admin/Official reach no care-team URL by any ID. **Gap (M37):** the Official and the Admin see patients' full names in the SMS recipient panel (`routes/broadcast_views.py:136`), including the "children with guardians" and "seniors" audiences. |
| 2 | Sealed visits: every free-text field AES-256-GCM, Doctor reads on screen only, never in exports, prints, audit or backups | Pass | `models/consultations.py:125` `SEALED_FIELDS` + the check-in reason; `utils/sealed_crypto.py` (AES-GCM, row- and field-bound); `models/consultations.py:227` `open_sealed_value`. Adversarial: all five fields stored `enc:v1:`, absent from the raw DB file, every Doctor export, every Staff page, every Admin/Official response and the backup; Doctor sees them on screen (control). `verify_sealed_privacy.py` 187/187. |
| 3 | Backups download as encrypted `.idsbackup`; `restore_backup.py` restores them | Pass | `routes/settings_views.py:435` `encrypt_backup(...)`; `utils/backup_crypto.py` (HKDF from SEALED_DATA_KEY). Adversarial: file starts `IDSBAK1`, no marker or phone number in the bytes; `restore_backup.restore()` into a temp folder passed `integrity_check` and every table matched the source (audit_logs differed only by the backup's own entry). Note: the CLI always writes to `../IDS-BPHCSN-backups` (no folder option), so the temp-folder restore called `restore()` directly. |
| 4 | SECRET_KEY required; debug off; CSRF on every POST; logout is POST; 30-min idle / 12-h limits; forced password change; no passwords in code | Pass | `config.py:66` `secret_key_problem`, `app.py:52-60` (refuses to start), `config.py:39` DEBUG only for `IDS_DEBUG=1`, `config.py:53,55`; `utils/csrf.py:91`; `routes/auth.py:356-363`; `utils/security.py:478`. Adversarial: POST without token → 400; GET /logout does not sign out, POST does; a fresh clone's first sign-in lands on My Account; no password literal outside `tests/`. |
| 5 | Every write path audited; no clinical text, no medicine/vaccine/service names, no full phone numbers | Pass | `routes/audit_entries.py`; `models/audit.py:641` masks on write; `verify_audit_coverage.py` section 9 (structural). Adversarial: raw `audit_logs` after the scenario holds no marker, no inventory item name, no service name and no full number. Latent gap L38 (masker misses numbers with separators). |
| 6 | Service at check-in; Doctor-service visits go to Waiting for the Doctor and cannot complete without a diagnosis; Left before being seen with same-day undo | Pass | `models/doctor_worklist.py:25`; `models/appointments.py:772` `_completion_blocked`, `:1051` `mark_left`, `:1095` `undo_left`. Adversarial: Staff intake → Waiting for the Doctor; Mark Completed refused; Doctor's diagnosis → Completed; Immunization visit completes without the Doctor; undo works the same day and is refused two days later. |
| 7 | Small counts (1–4) fold into "Other" for Admin and Official; sealed visits show as "Confidential" | Pass | `utils/small_counts.py:28-55`; `models/consultations.py:656`. Adversarial: single-count diagnosis, complaint, medicine and vaccine markers never appeared in any report screen, Excel or PDF (4 ranges × 5 types) for Admin or Official. |
| 8 | SMS numbers masked to the last 4 digits; mode line shows Live or Simulated honestly | Pass | `utils/phone.py:52`; `utils/sms.py:164-175`. Adversarial: 18 stored recipient numbers, 0 shown in full to any of the four roles; "Simulated" on Settings and every SMS screen with no key, "Live" with a key. |
| 9 | Demo data fictional, deterministic, follows every rule | Pass | `verify_demo_data.py` 103/103 (builds twice, compares). Clean clone built 150 patients, 4 sealed visits, every intake by Staff, every diagnosis by the Doctor. Live `app.db` (read-only): demo marker 5001, 0 patient numbers outside `0900000NNNN`. |
| 10 | No placeholders, no disabled controls, one project name, docs match the code | **Fail** | One name: Pass (no old variant in the repo). Disabled control left: the queue's Sort button (L35). Rendered text over 160 characters (L36). Docs drift in 03, 04, 08, 09 and the tracker (M38, L42). |

## Actual permission matrix

Built through real sign-in (`POST /login` with each fixture account) for all 93 URL rules (90 endpoints), GET and POST with a valid form token, on a temporary fixture database. **A** = the view ran (200, or its own redirect after validating the form). **R** = refused by `role_required` (redirect to the person's own dashboard). Anonymous: every guarded route redirects to `/login`. No route returned a server error.

| Route group | Admin | Staff | Doctor | Official |
|---|---|---|---|---|
| `/account`, `/account/password`, `/session/keep-alive`, `/dashboard` | A | A | A | A |
| `/admin/*` (all 39 rules: dashboard, patient records and 4 exports, demographics profile, inventory + add/edit/archive/exports, queue view + 2 exports, SMS view/send, reports + 2 exports, users + add/edit/reset/status/exports, audit + 2 exports, settings, general, maintenance, backup, schedule view/add/edit/delete) | A | R | R | R |
| `/staff/*` clinical floor (dashboard, patients + 4 exports, profile, register/edit patient, status, vaccination correction, inventory + add/edit/archive/exports, queue + check-in/start/complete/send-to-doctor/mark-left/undo/change-service + 2 exports, record/edit consultation, SMS view, schedule view) | R | A | A | R |
| `/staff/patient_profile/<id>/restrict-consultation` | R | R | A | R |
| `/staff/reports_analytics` + 2 exports | R | R | A | R |
| `/official/*` (dashboard, reports + 2 exports, SMS view/send, health programs, vaccination campaigns, community reports + 2 exports, schedule view) | R | R | R | A |
| `/admin/...` patient and clinical write routes | 404 (no route) | — | — | — |

Compared with `PROJECT_STATUS.md` §3: **no difference at route level.** Two wording differences: the doc names a Notifications screen for the Official (removed in Task 7), and says the Admin's patient list has "two exports" (it has four, with the two selection exports). Inside the routes, the per-request rules (Doctor-only diagnosis, seal, Deceased; Staff placeholder on sealed text) all held.

## Adversarial results

**Test run.** `python tests/run_all.py`: **2245/2245 checks in 21/21 suites**, live `app.db` unchanged. Per suite: epi 15, staff_capabilities 27, add_user 121, my_account 344, password_change_audit 50, edit_user_reset_password 82, rbac 117, reports 61, dispensing 133, doctor 132, service_schedule 157, database_integrity 18, security_basics 82, csrf 69, audit_coverage 60, sealed_privacy 187, admin_minimum_necessary 87, small_counts_and_masking 184, demo_data 103 (207 s), doctor_worklist_and_left 166, cleanup 50.

**Break-it** (each change made in a scratch copy of the code, never the repo; baseline on the unchanged copy passed 814/814):

| Mutation | Caught by | Result |
|---|---|---|
| M1 `can_view_restricted()` returns True for every role | `verify_sealed_privacy.py` 162/187 | Caught |
| M2 Admin's roster reads full patient rows (numbers, conditions) | `verify_admin_minimum_necessary.py` 84/87 | Caught |
| M3 backup served as plain SQLite | `verify_admin_minimum_necessary.py` 78/87, `verify_sealed_privacy.py` | Caught |
| M4 small counts never fold | `verify_small_counts_and_masking.py` 128/184 (`verify_reports.py` still 61/61) | Caught |
| M5 audit entries stored with whole numbers | `verify_small_counts_and_masking.py` 182/184 (`verify_audit_coverage.py` still 60/60) | Caught |
| M6 a Doctor-service visit completes with no diagnosis | `verify_doctor_worklist_and_left.py` 157/166 | Caught |
| M7 CSRF switched off | `verify_csrf.py` (fails) | Caught |

Test-strength note: most suites sign in by writing `user_id` into the session (`client_as()`), not through `/login`. The real-sign-in matrix above found no difference, so this is not a gap today. The 160-character check in `verify_cleanup.py` reads template source, not rendered pages (see L36).

**Marker crawl.** Unique markers were written into every clinical field through the real routes (Staff check-in reason, intake complaint and notes; Doctor diagnosis and plan; one visit sealed by the Doctor at record time), and directly into conditions, allergies, emergency contact, contact numbers, dispensing snapshots, dose notes and an "other" vaccine. Then every GET rule was requested with every patient, consultation and appointment ID, with report types × 4 date ranges, queue months, profile tabs and audit filters, plus every link found on the pages and the POST selection exports:

| Role | Requests | Readable responses (HTML, Excel, PDF) | Forbidden markers found |
|---|---|---|---|
| Administrator (all markers forbidden) | 633 | 246 | 0 |
| Barangay Official (all markers forbidden) | 593 | 85 | 0 |
| Health Center Staff (sealed markers forbidden) | 653 | 218 | 0 |
| Doctor (none forbidden; checked for server errors) | 673 | 281 | 0 errors |

Positive controls passed (the same extraction finds the markers where they belong: Doctor's screen, Staff's profile). No sealed marker in any Doctor export. IDOR: Admin and Official got 0 care-team pages for every patient, consultation and appointment ID; Staff's edit form of a sealed visit carries no sealed text; a seal posted under the wrong patient ID acts on the stored record's own patient. Backup: no marker or number in the bytes; restored and matched (claim 3).

## Clean-clone result

`git clone` into a temp folder, then README "Running it" with the existing `.venv` (it already holds every pinned package; README's `pip install -r requirements.txt` needs internet, and README does not say so).

| Step | Result |
|---|---|
| `python setup_env.py` | Pass: `.env` created with SECRET_KEY, SEALED_DATA_KEY, IDS_DEBUG=0; second run changes nothing |
| `python app.py` | Pass, with a deviation: port 5001 was in use by the team's running app, and `app.py` hard-codes 5001, so the clone was started on 5097 with the same `app.run`. Debug off; `/login` served (200, title "IDS-BPHCSN \| Sign In"); `app.db` and four random passwords created at the first request |
| `python seed_demo_data.py` (README "The database") | **Fails as written**: "app.db already exists. Use --replace…", because the previous README step created it (M36) |
| `python seed_demo_data.py --replace` | Pass in 59 s: 150 patients, 410 visits, 4 sealed, 3159 audit entries; the empty install is archived to `../IDS-BPHCSN-backups/previous-app.db` |
| Sign in as the demo Admin | Pass: lands on My Account (forced password change) |

README gaps: setup order (M36); no note that `pip install` needs internet, or how to install offline; nothing about a port already in use; the Layout section leaves out `tests/`, `docs/`, `setup_env.py`, `restore_backup.py` and `export_sealed_key.py` (L44). The clone and its server were removed afterwards.

## Issues found

New issues take the next free IDs (H7, M36–M38, L35–L44).

| ID | Severity | File:line | Problem | Suggested fix |
|---|---|---|---|---|
| H7 | High | `../classcheck_backups/` (outside the repo); `archive_plain_databases.py:21` | 6 plain SQLite copies of this project's database (2026-08-14 to 08-16, before the H6 clean-up) and 15 full `.zip` backups sit next to the project. Task 8's archiver scans only `IDS-BPHCSN-backups`, so they were never encrypted or removed. Whether they hold real names: not verified (no rows were opened). | Archive or delete the folder before the defense (e.g. point `archive_plain_databases.py` at it once), and check the zips for old history. |
| M36 | Medium | `README.md:32-40`, `README.md:98-101`, `README.md:122-125` | "Running it" starts `app.py` (which creates `app.db`), then "The database" says `python seed_demo_data.py`, which refuses because `app.db` exists. A new teammate following the README is stopped. | Put `python seed_demo_data.py` before `python app.py` in "Running it". |
| M37 | Medium | `routes/broadcast_views.py:136`; `models/broadcasts.py:470-477` | The SMS recipient panel shows patients' full names (with masked numbers) to the Barangay Official and the Administrator, including the "children with guardians" and "seniors" audiences. This contradicts "the Official has no patient access". | Show counts and masked numbers only, or initials, to roles outside the care team. |
| M38 | Medium | `PR0MPT_INSTRUCTION/09_…md:62,116,177,264,284,304`; `03_…md:655-670,1464-1470`; `08_…md:75,78,250,568,818-823`; `04_…md:81` | The docs still describe removed features as current (Official's Notifications screen and bell; Settings' Health Center Information, SMS Settings and disabled Restore/SMS gateway controls), 22 screens, 13 tables (there are 14), "90 guarded view functions" (87 of 90 are guarded), and "Bootstrap 5.3 via CDN" (vendored, as the next line says). | Update those lines; see Docs drift. |
| L35 | Low | `templates/appointment_scheduling.html:547` | A permanently disabled "Sort" button remains on the Patient Queue. | Remove it; the order is fixed and the tooltip already explains it. |
| L36 | Low | `templates/audit_logs.html:153,178`; `templates/settings.html:422`; `templates/user_management.html:288`; `templates/service_schedule.html:127` | Rendered text over 160 characters: two tooltips (186 and 207, made long by `{{ untracked.login_scope }}`) and about 20 multi-sentence paragraphs (up to 382). `verify_cleanup.py` checks source only. | Shorten them, and measure rendered pages in the test. |
| L37 | Low | `models/appointments.py:528,1196`; `models/appointment_sms.py:86`; `routes/audit_entries.py:161` | Dead code: `count_active_consultations`, `parse_iso_date`, `get_appointment_sms_by_id` have no caller; `_doses()` takes an unused `labels_of`. | Delete them. |
| L38 | Low | `utils/phone.py:49` | The audit masker matches only unbroken digits; "0917-123-4567", "0917 123 4567" and "+63 917 123 4567" pass through unmasked. No writer quotes such text today (stored numbers are normalized), so this is latent. | Allow spaces, dashes and brackets in the pattern. |
| L39 | Low | `schema.sql:97-111`; `.gitignore:59`; `utils/security.py:447` | Stale comments: the seal "seals the two doctor-only fields… and nothing else" (all free text since Task 5b); config "falls back to a dev value" (it has no fallback); "95 guarded routes" (87). | Correct the comments. |
| L40 | Low | `utils/security.py:294-295`, `utils/security.py:333-334` | Audit text reads "…; the the account was deactivated…" (doubled word in stored entries). | Drop the second "the". |
| L41 | Low | `routes/auth.py:223`; `app.py:34` | No sign-in throttling or lockout; no `X-Frame-Options` or SameSite cookie setting. The app listens on 127.0.0.1 only, so the risk is low. | A short delay or lockout after repeated failures; set the header and `SESSION_COOKIE_SAMESITE="Lax"` in `no_store()`/config. |
| L42 | Low | `PROJECT_STATUS.md:58,62-84`; §2; §3 row "Community Reports… Notifications" | The tracker's per-suite table is off by one in three suites (add_user 122→121, dispensing 134→133, csrf 68→69; total unchanged), says "after Task 6b", and §2/§3 still describe pre-task gaps and the removed Notifications screen. | Refresh the table, mark §2 as the original snapshot, and drop Notifications from §3. |
| L43 | Low | `tests/_support.py:95`; `migrations/migrate_correct_admin_persona.py:16`; `tests/verify_my_account.py:107`; `tests/verify_password_change_audit.py:103`; `tests/verify_doctor.py:752`; docs 01/03/06/09; 3 verification notes | The real Administrator's name (as given in `01_PROJECT_BIBLE.md:83`) is still used as a test fixture and in a migration. M31 changed only the fresh-install account. | Use a fictional name in fixtures and the migration; keep it in the docs only with the person's consent. |
| L44 | Low | `README.md:32-48,162-178` | No note that `pip install` needs internet or how to install offline; no word on port 5001 being in use; the Layout section omits `tests/`, `docs/`, `setup_env.py`, `restore_backup.py`, `export_sealed_key.py`. | Add the three lines. |

Also seen, not counted as issues: about 50 `ids-bphcsn-test-*` folders remain in the system temp folder from suite runs that were stopped early (fictional fixture data only); `utils/sms.py:37` sends live messages one by one with a 15-second timeout, so a hanging network would hold a large broadcast for minutes.

## Docs drift

| Document | Says | Code says |
|---|---|---|
| `09_…md:62` | "One screen is not backed by data: 19, Notifications" | Removed in Task 7; no route |
| `09_…md:116,177` | The Official's screens include Notifications; "10 of 22" screens | 21 screens; no Notifications |
| `09_…md:264,284,304` | The header has a notification bell (the Official's links to Notifications) | Bell removed in Task 7 |
| `03_…md:655-670` | Settings sections: General, Health Center Information, SMS Settings, Backup, Restore | Panes: General, SMS (mode line), Security, Password Policy, Backup & Restore (download only), Maintenance, About (`templates/settings.html:148-154`) |
| `03_…md:1464-1470`, `08_…md:818-823,860` | Restore, the SMS gateway controls and the scheduled-backup controls are "still disabled" | Removed in Task 7; restore is `restore_backup.py` |
| `08_…md:89` | Restore, lockout, etc. "declared on the screen that would have carried it" | Restore declared; no lockout exists (L41) |
| `08_…md:75` | "90 guarded view functions (93 routes)" | 90 view functions, 87 guarded, 93 rules |
| `08_…md:78` | "13 tables with 19 indexes" | 14 tables, 19 indexes (`schema.sql`) |
| `08_…md:250,568` | "22 screens" | 21 |
| `08_…md:343,599` | "8 migration scripts", "10 tables, 12 indexes" (as current status) | 25 migrations, 14 tables |
| `04_…md:81` | "Bootstrap 5.3 via CDN" | Vendored under `static/` (as line 82 and README say) |
| `README.md:32-40` vs `:98-125` | Run `app.py`, then `seed_demo_data.py` | The seed refuses once `app.py` has created `app.db` (M36) |
| `PROJECT_STATUS.md` §3 | Official has "Notifications"; Admin patient list has "two exports" | No Notifications; four exports |
| `PROJECT_STATUS.md:58,62-84` | Suite counts after Task 6c/6b | 121, 133 and 69 in three suites (L42) |
| `schema.sql:97-111` | The seal covers diagnosis and treatment plan only | All free text and the check-in reason (L39) |

README, 01 and every backticked file and function name in 01, 03, 04, 08, 09 resolve to real code. The only exceptions are historical mentions (`populate_records.py` in 09:932; the old migration names in the tracker's log).

## Defense checklist status

From `PROJECT_STATUS.md` §7 "Before the defense", as far as can be seen from this laptop:

| # | Item | Status |
|---|---|---|
| 1 | Rebuild the demo database | **Done**: live `app.db` has the demo marker (5001), 150 patients, 4 sealed visits, all numbers `0900000NNNN` |
| 2 | Set the five passwords | **Not done**: 5 of 5 accounts still must change their password at first sign-in |
| 3 | Semaphore key, or say SMS is simulated | **Not done (key)**: no `SEMAPHORE_API_KEY` in `.env`; the screens honestly say "Simulated", so say so at the defense |
| 4 | Fill the Service Schedule after the interview; confirm services (M35) | **Not done**: 0 rows |
| 5 | BitLocker on the presenting laptop; give the Doctor the key envelope | **Not verified**: BitLocker status needs administrator rights; the envelope cannot be seen |
| 6 | Run the full test suite | **Done** today: 2245/2245 |
| 7 | Push to the private remote after the old bundle and backups are dealt with | **Done**: `master` equals `origin/master`; the GitHub repository answers 404 without sign-in (private). M18, M22, M32 are Done (bundle deleted by the team; old backups archived in Task 8). **M19 still open**: 56 old session folders in `%TEMP%\claude\C--IDS-BPHCSN`. **New H7**: `../classcheck_backups` |
