# Chapter 4 — where each number comes from

Draft: `PR0MPT_INSTRUCTION/manuscript/CAPSTONE1_FINAL-CHAP_1-4_DRAFT.docx` (git-ignored; made on
2026-10-12 from `CAPSTONE1_FINAL-CHAP_1-3_REVISED.docx`, which was not modified). Chapters 1–3
of the draft are XML-identical to the input (all 239 body elements and the section settings);
`styles.xml` is unchanged.

Abbreviations for the sources:
- **EV** = `docs/chapter4-evidence.md` (section number given)
- **PERF** = `tests/perf/performance_results.md`
- **PS** = `PROJECT_STATUS.md` (Task Log row or "How to run the tests")
- **FA** = `docs/verification/final-audit/README.md`
- **UE** = the user evaluation facts of 2026-10-12, given by the team in the Task brief (not in the
  repository; the signed forms go in Appendix C)
- **UAT** = `docs/uat-tasks.md` (Part B of the evaluation form, given by the team)
- **CODE** = the file named
- **MS** = the Chapter 1–3 manuscript

---

## TO COMPLETE (yellow-highlighted in the draft)

1. §4.2, after the module list: "Screenshots to be refreshed from the final build before
   submission." (The 21 screenshots were taken on 2026-10-09, before the referral feature of
   2026-10-10; the queue screenshot shows no Referred status.)
2. §4.6, User Feedback (2): "A duplicate-patient check is being added to patient registration and
   editing." — change to "was added and retested" after Task 20.
3. §4.6, the note right after it: "[update to 'was added and retested' after Task 20]" — delete
   when item 2 is done.
4. §4.7, after Table 4.5: "[confirm whether he performed the tasks or observed a demonstration]"
   (the member of the Barangay Health Committee).
5. §4.8, under Table 4.6: "[Durations are proposed in this draft; confirm them with the team and
   the health center.]" — the durations in Table 4.6 are a plan, not a measured fact.

Also to do (not highlighted): insert the scans of the signed evaluation forms under
"Appendix C. Signed Evaluation Forms" (heading only).

---

## Introduction and 4.1

| Number in the draft | Source |
|---|---|
| 5.3 (Bootstrap) | MS Chapter 1 Scope; Chapter 3 Table 1 |
| four user roles | EV §1; MS Chapter 1 Scope |
| ten modules | EV §1.1–1.10 (1.11 dashboards are "supporting") |
| 5,085 checks, 28 suites, all passed | PS "How to run the tests": "Today (after Task 19): 5085/5085, all 28 suites pass". Note: a full run on 2026-10-12 (this task, no code change) gave `TOTAL: 5121/5121 checks passed in 28/28 suites`; the difference is the phone suite (2166 checks, 2130 in PS). The draft keeps the PS figures as the brief asked; update PS and the draft together if the newer total is wanted. |
| October 10, 2026 (referral feature) | PS Task Log, Task 19 row |
| October 2, 2026 (final audit) | EV §2.4; FA |
| October 9, 2026 (performance) | PERF header "2026-10-09 15:53" |
| October 12, 2026; two evaluators | UE |
| four specific objectives | MS Chapter 1, Specific Objectives |

## 4.2 System Modules/Features

| Number | Source |
|---|---|
| 12 characters, three of four kinds | EV §1.1 |
| five wrong passwords, five minutes | EV §1.1 (`utils/login_throttle.py`) |
| 30 minutes idle, 12 hours, warning two minutes before | EV §1.1 (`config.py`, `static/js/session.js`) |
| Data Privacy Act of 2012, RA 10173; RA 11166; RA 6675 (Generics Act of 1988) | EV §1.1, 1.2, 1.5; MS Chapter 1 Scope |
| AES-256-GCM | EV §1.2, §1.10 |
| six services listed (Consultation … Immunization) | CODE `models/doctor_worklist.py` `VISIT_SERVICES`; PS Task 19 D4 (EV §1.3 still lists Dental: superseded by Task 19) |
| statuses (three open, three ending: Completed, Left before being seen, Referred) | PS Task 19 D1; MS Chapter 1 Scope |
| one patient in consultation at a time | EV §1.3 |
| A4 referral slip; same-day undo; destinations RHU, Caraga Regional Hospital, Other | PS Task 19 D1, D2; CODE `models/referrals.py` `REFERRAL_DESTINATIONS` |
| EPI schedule: three doses each of Pentavalent, OPV, PCV; MR 9 months; MMR 12 months | EV §1.4 (`models/immunizations.py` `EPI_SCHEDULE`) |
| 90 days (expiring soon) | EV §1.5 |
| last four digits (phone masking) | EV §1.6 |
| one credit per segment | CODE `utils/sms.py` comment "Semaphore bills one message credit per segment" |
| six report types; up to 12 months | EV §1.7 (`ANALYTICS_REPORT_TYPES`) |
| counts of one to four, "Other (each fewer than 5)" | EV §1.7 (`utils/small_counts.py`) |
| second and fourth Wednesday (example) | EV §1.8 |
| demo data holds the schedule from the RHU interview | PS Task 19 D5; M35 "Done (Task 19)" |
| 992 pixels; 44 by 44 pixels | EV §1 / PS Task 17 D1, D4 |
| Figures 4.1–4.16 | EV §6 (files and captions). 16 of the 21 screenshots used; not used: 04, 05 (Staff and Official dashboards), 08 (Consultation History tab), 16 (Service Schedule: shows the schedule empty, which is out of date since Task 19), 19 (phone dashboard). Desktop shots 6 in wide; the three 390×844 phone shots are 3 in wide (6 in would be 13 in tall, more than an A4 page) |

## 4.3 System Testing Procedures

| Number | Source |
|---|---|
| 5,085 checks, 28 suites | PS "How to run the tests" |
| 747 birth dates | EV §3 F31 retest; PS Task 15 |
| October 2, 2026; 10 claims; 93 page addresses (URL rules); four roles; 8 of 10 passed; 2 failed; corrected by October 3, 2026 | EV §2.4 "Final pre-defense audit"; FA |
| clean-copy install: failed at the seed step, then worked | EV §2.4 "Clean-copy install test"; F19 (M36) |
| 360, 390 and 1,366 pixels | EV §2.4 "Mobile layout checks" |
| 2,130 checks (phone suite, latest run) | PS "How to run the tests": "2130 of them are the phone-layout suite" |
| 26,287 elements, 63 pages, 992 pixels and above, one time label | EV §2.4; PS Task 17 D6 ("only the width of the 'Loaded HH:MM' text moved") |
| 2,552 requests; 633 / 593 / 653 / 673; 830 readable responses; 0 markers; Doctor 0 server errors | EV §2.4 "Adversarial role testing"; FA "Adversarial results" (633+593+653+673 = 2,552) |
| 30-minute idle, 12-hour session | EV §1.1 |
| at least 239 recorded mutations up to October 9, 2026 | EV §2.4 "Deliberate break-it (mutation) checks" |
| 33 mutations for the referral feature | PS Task 19 row: "29 mutations of the referral rules and 4 of the demo data … all caught" (29 + 4 = 33) |
| 14 actions; 3 warm-ups; 30 timed runs; 3,000 ms; 95th percentile | PERF header; EV §5 |
| 150 patients, 421 visits, 411 consultations, 302 immunizations | PERF "Data" |
| Intel Core i5-13420H, 15.6 GB RAM, Windows 11 | PERF "Test computer" |
| 17 statements, five criteria, rated 1 to 5 | UE |
| 18 tasks; UAT-01 to UAT-12 (Staff), UAT-13 to UAT-18 (Official) | UAT |

## 4.4 Test Cases

| Number | Source |
|---|---|
| Table 4.1: 21 rows (TC001, 003, 006, 009, 010, 012, 013, 014, 038, 018, 020, 021, 022, 025, 026, 028, 030, 032, 033, 036, 037) | EV §3, plus TC038 (below) |
| numbers inside the TC rows (5 passwords / 5 minutes, 30 minutes, 12 hours, 29 minutes, 1-month-old, 6 weeks, 27 days, 9 months, 12/5/4/1/3 sealed, Other (8), 360/390 pixels, 44 × 44, 14 actions, 3 seconds, 1,402 ms, 0 failed runs) | EV §3 (each row's "Proven by") |
| **TC038** (new ID) | Not in EV §3, which predates Task 19. Made from `tests/verify_referrals.py` checks, run on 2026-10-12 (122/122): "Staff can refer a Waiting visit: it is Referred, with who, when and where from"; "Administrator: POST refer (valid token) is refused on the server; nothing changes, no audit entry"; "Barangay Official: POST refer (valid token) is refused …"; "Staff: the slip prints the health center, the date and time, name, ID, age and sex" |
| "All 38 test cases in Appendix A" | TC001–TC037 (EV §3) + TC038 |
| Table 4.2: 10 rows (F01, F02, F15, F17, F20, F23, F26, F27, F29, F35) | EV §4 |
| F01: HTTP 500; 15 of 921 checks failed; 5 differences; 1,249 of 1,249 | EV §4 F01 ("906 of 921 checks passed, all 15 failures from this"; "1249/1249") |
| F02: 97 call sites in 14 files; under 2 seconds | EV §4 F02 |
| F15: AES-256-GCM | EV §4 F15 |
| F29 detail: 6 weeks, 27 days, 9 months | EV §3 TC023 |
| 126 checks (immunization timing suite) | PS suite table; EV §2.3 row 25 |

## 4.5 Results and Discussion — Table 4.3 and text

| Number | Source |
|---|---|
| Table 4.3, all 14 medians and 95th percentiles (315/342, 356/444, 379/429, 376/424, 385/417, 115/149, 54/92, 343/386, 361/405, 497/540, 1,252/1,402, 111/139, 56/78, 70/95); target 3,000 | PERF "Results" |
| 0 failed runs | PERF "Failed runs: None" |
| about 0.3 to 0.45 s; less than 0.1 s; about 0.3 s (sign-in) | EV §5 "Reading the results" (profile 92 ms and save 78 ms at the 95th percentile, both under 0.1 s) |
| 150 patients, 421 visits | PERF "Data" |
| 33 units, earliest-expiry batch | PERF "Checks on what the write runs left" |
| 2,552 requests | EV §2.4 |
| Security mean 5.00; all criteria 5.00 | UE |
| UAT-03 to UAT-09, UAT-10, 11, 14, 15, 16, 18; UAT-12 | UAT; UE (all Passed) |
| 12-month report | PERF row 11; EV §1.7 |
| six report types | EV §1.7 |
| F31 (found in real use) | EV §4 F31 ("Team in real use") |
| network mode / phone layout not tried on other devices | PS issues L62 and L64 (open); the phone used in UAT-12 comes from UE/UAT |

## 4.6 User Evaluation/Acceptance Results

| Number | Source |
|---|---|
| October 12, 2026; two evaluators and their roles; BHWs and Barangay Captain not available | UE |
| Part C, 17 statements, five criteria, 1–5 | UE |
| scale 4.21–5.00 Strongly Agree; 3.41–4.20 Agree; 2.61–3.40 Neutral; 1.81–2.60 Disagree; 1.00–1.80 Strongly Disagree | UE |
| Table 4.4: every mean 5.00, "Strongly Agree"; n = 2 | UE |
| duplicate check at registration: exact first name, last name and birth date; not run on edit | CODE `models/patients.py` `find_possible_duplicates()`; `routes/patient_views.py` (the edit branch returns before the duplicate check). **Conflict reported:** the brief said the check "is being added"; a warning on an exact match already exists at registration (since the initial commit). The draft states both. |
| referral slip designed from the interview, not an RHU form | PS issue L68 |

## 4.7 User Acceptance Testing

| Number | Source |
|---|---|
| Table 4.5: UAT-01 to UAT-18, tasks and expected results | UAT (verbatim) |
| Actual results; all Passed; no errors | UE ("every task Passed, with no errors"); the Actual Result wording restates the expected result in the past tense; UAT-16 adds "simulated" as instructed |
| 18 tasks | UAT |

## 4.8 Implementation Plan (Table 4.6)

| Item | Source |
|---|---|
| Setup steps (packages, `.env` and keys, HTTPS certificate and network mode, firewall Private only, fixed address, certificate on devices, accounts with random first-time passwords, key envelope for the Doctor, BitLocker, Service Schedule, Semaphore key, backups, restore program, updates and migrations) | EV §7.1 |
| four accounts created on an empty database | EV §7.1 step 3 |
| "confirm that the router lets devices on the Wi-Fi reach each other" | Added by this draft for risk 6 (Wi-Fi blocking devices); not in EV §7.1 |
| "check … the SMS account credit" (Monitoring) | Added by this draft for risk 8; not in EV §7.1 |
| Durations (1 day, 1 hour, 2 days, 3 days, First 3 months, Weekly, As needed) | **Proposed by this draft; no source.** Highlighted (TO COMPLETE item 5) |
| What was done in the demonstration (install, keys, demo data, test suite) | PS §7 "Status (final audit)": demo database rebuilt; full suite run. Not claimed as done: certificate on devices, key envelope, BitLocker (PS §7 items 2, 5 open) |

## 4.9 Risk Management (Table 4.7)

| Item | Source |
|---|---|
| 12 risks | Set by the brief; mitigations from EV §7.2 and the code |
| each write saved completely or not at all | EV §7.2 "Data loss" (`db_connection()`) |
| encrypted sealed fields and backups; BitLocker; key envelope | EV §7.2 |
| migrations back up the database first | EV §7.1 "Updates" |
| five-minute pause after five wrong passwords; 30-minute and 12-hour limits | EV §1.1 |
| fixed address; certificate made again | EV §7.1 network step 4; PS L61 |
| segment count; each recipient's result; Failed or Partial | CODE `models/broadcasts.py` (`STATUS_FAILED`, `STATUS_PARTIAL`, per-recipient outcomes); `utils/sms.py` |
| same-day undo of Left and Referred | EV §1.3; PS Task 19 D1 |
| RHU doctor visits on no fixed day; referral to RHU / Caraga Regional Hospital | PS Task 19 field data |

## Appendices

| Item | Source |
|---|---|
| Appendix A: TC001–TC038 | EV §3 (TC001–TC037, reworded in plain English; "Proven by" left out) + TC038 above |
| Appendix B: F01–F36 | EV §4 (reworded; commit hashes and file names left out). Numbers: F01 15 of 921, 5 differences, 1,249; F02 97, 14, 2 seconds; F13 2 days, 30-minute, 12-hour; F21 five, five minutes; F31 4 days, 747; F33 390, 638 to 778, 280, 992, 44; F08 ten crafted values |
| Appendix C | heading only (UE: the team inserts the scans) |

## Facts left out (could not be supported)

- A test case ID for the referral feature among TC001–TC037: none exists, so TC038 was made
  from the referral suite's own checks (see 4.4).
- The Service Schedule screenshot (16): left out because it shows an empty schedule, which is
  out of date since Task 19.
- Whether the Barangay Health Committee member performed the tasks himself: not known
  (TO COMPLETE item 4).
- Implementation durations: no source (TO COMPLETE item 5).

## Conflicts with Chapters 1–3 (not changed; Chapters 1–3 must stay as they are)

- Chapter 3, Phase 4 says user acceptance testing "were conducted with Barangay Health Workers and
  the Barangay Captain". The evaluation of 2026-10-12 was with a Barangay Health Committee member
  (Kagawad) and an RHU nurse (UE). Chapter 4 states the actual evaluators.
- Chapter 3, Phase 5 says feedback from "health center staff and barangay officials" was used for
  final refinements; the only recorded feedback is the RHU nurse's two comments.
