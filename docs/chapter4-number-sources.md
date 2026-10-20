# Chapters 4 and 5 — where each number and statement comes from

Draft: `PR0MPT_INSTRUCTION/manuscript/CAPSTONE1_FINAL-CHAP_1-4_DRAFT.docx` (git-ignored; made on
2026-10-12 from `CAPSTONE1_FINAL-CHAP_1-3_REVISED.docx`, which was not modified). Chapters 1–3
of the draft were XML-identical to the input (all 239 body elements and the section settings);
`styles.xml` is unchanged.

**Corrections of 2026-10-12, before Chapter 5** (backup `..._DRAFT_before-fixes.docx`; a paragraph
diff shows exactly these five paragraphs changed and nothing else):
- Chapter 3, Phase 4: the evaluators are now "a member of the Barangay Health Committee of
  Barangay Poblacion and a nurse of the Rural Health Unit of San Francisco, Surigao del Norte".
- Chapter 3, Phase 5: "Feedback gathered from the evaluators during this phase".
- Chapter 4, §4.1 and §4.3 intro: the latest full run is now 5,121 checks in 28 suites, on
  October 12, 2026; §4.3 C: the phone suite's latest-run count is now 2,166 (it was 2,130; changed
  with the total so that both describe the same run).

**Chapter 5** was then inserted after Chapter 4 and before Appendix A (backup
`..._DRAFT_before-ch5.docx`): every other body element is XML-identical before and after;
`numbering.xml` gained two list instances (numIds 9 and 10) of the manuscript's existing decimal
list (abstractNum 2), so that lists A and B each start at 1. Word opens the file (115 pages).

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

## TO COMPLETE (current, in CAPSTONE1_FINAL-CHAP_1-5_DRAFT.docx)

Yellow items still pending (4):

1. §4.2, after the module list: "Screenshots to be refreshed from the final build before submission."
2. §4.6 User Feedback (2): "A duplicate-patient check is being added to patient registration and editing." (Task 20 is done in the code, 2026-10-20; the manuscript still says "is being added".)
3. §4.6, the note after it: "[update to 'was added and retested' after Task 20]"
4. §4.8, under Table 4.6: "[Durations are proposed in this draft; confirm them with the team and the health center.]"

Cleared 2026-10-12 (demonstration fix): the team confirmed the RHU nurse performed the UAT tasks herself and the Barangay Health
Committee member (a senior citizen with little technology experience) did not operate the system; the researchers demonstrated each task
and he then completed the rating form himself. §4.3 F and G, §4.7 (with a note under Table 4.5: "Passed" refers to the tasks performed by
the RHU nurse), §4.6 (one interpretation sentence, tied to Joshi et al. (2025), whose Chapter 2 summary says BHW proficiency was mostly
limited to basic tasks), §5.1, §5.2 and §5.3 A1/A2 were made consistent. The yellow "[confirm whether he performed the tasks ...]" was removed.

Also: insert the scans of the signed evaluation forms under Appendix C.

Cleared on 2026-10-12: the team confirmed that both evaluators rated every statement 5 on their signed forms, so the yellow
highlight and "[TO BE CONFIRMED]" were removed from the Chapter 5 rating sentences (5.1, 5.2 Security, 5.2 closing) and
from the three 5.2 sentences on UAT-10/11, UAT-03 to 09 and 16, and UAT-14/15. Recommendation B2 now cites the RHU
interview (Question 13, answer "Yes"; Appendix D) instead of "[TO BE CONFIRMED]". Chapter 3 Phase 1 now says
"(see Appendix D)". Appendix D was added from `rhu-real_data.docx` (the file named in the brief,
`Interview-rhu-realdata.docx`, does not exist; this is the only interview file in the folder): purpose, position (Nurse),
location, and every question with its recorded answer, no name. Typing fixes: "everything Tuesday and Thursday" to
"every Tuesday and Thursday" (Q5); "as long has it has time" to "as long as it has time" (Q10).

(History) the earlier Chapter 5 list of yellow items is superseded:



Yellow-highlighted in Chapter 5:

1. §5.1, last paragraph: "Both evaluators rated every criterion (Functionality, Usability,
   Reliability, Performance and Security) at a mean of 5.00, interpreted as Strongly Agree.
   [TO BE CONFIRMED]"
2. §5.2, Objective 1: "The evaluators' Security rating (mean of 5.00) and the passing of UAT-18
   are consistent with this conclusion. [TO BE CONFIRMED]"
3. §5.2, Objective 2: "The user acceptance tasks for receiving a delivery and dispensing a
   medicine (UAT-10 and UAT-11) passed."
4. §5.2, Objective 3: "The user acceptance tasks for the queue, the referral and vaccine doses
   (UAT-03 to UAT-09) and for SMS (UAT-16, in Simulated mode) passed."
5. §5.2, Objective 4: "The user acceptance tasks for the dashboard and for the 12-month report
   with its PDF export (UAT-14 and UAT-15) passed."
6. §5.2, closing: "The user evaluation showed strong acceptance by the two evaluators, but with
   only two evaluators the results cannot be generalized to all intended users. [TO BE
   CONFIRMED]"
7. §5.3 B, item 2: "The RHU said that it would accept reports through a computer system.
   [TO BE CONFIRMED]" — given in the Chapter 5 brief; not recorded in Chapter 4, Chapter 1 or
   EV, so it is marked for confirmation.

Items 3 to 5 depend on the user evaluation (yellow by the brief's rule) but are not ratings, so
they carry no "[TO BE CONFIRMED]".

## TO COMPLETE (Chapter 4, yellow-highlighted in the draft)

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
| 5,121 checks, 28 suites, all passed; October 12, 2026 | Full run of 2026-10-12: `TOTAL: 5121/5121 checks passed in 28/28 suites that ran`, live `app.db` unchanged; PS "How to run the tests" updated to match ("Today (full run of 2026-10-12): 5121/5121"). The earlier figure, 5,085 after Task 19, differed only in the phone suite (2130 then, 2166 now; no code change; cause not investigated). |
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
| 5,121 checks, 28 suites; October 12, 2026 | Full run of 2026-10-12; PS "How to run the tests" |
| 747 birth dates | EV §3 F31 retest; PS Task 15 |
| October 2, 2026; 10 claims; 93 page addresses (URL rules); four roles; 8 of 10 passed; 2 failed; corrected by October 3, 2026 | EV §2.4 "Final pre-defense audit"; FA |
| clean-copy install: failed at the seed step, then worked | EV §2.4 "Clean-copy install test"; F19 (M36) |
| 360, 390 and 1,366 pixels | EV §2.4 "Mobile layout checks" |
| 2,166 checks (phone suite, latest run) | Full run of 2026-10-12 (`verify_mobile_layout.py 2166/2166`); PS "How to run the tests" and the suite table |
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
| duplicate check at registration: exact first name, last name and birth date; not run on edit | CODE `models/patients.py` `find_possible_duplicates()`; `routes/patient_views.py` (the edit branch returns before the duplicate check). **Conflict reported:** the brief said the check "is being added"; a warning on an exact match already exists at registration (since the initial commit). The draft states both. **Changed by Task 20 (2026-10-20):** the check now also runs on an edit that changes a name or the birth date, and it catches different spellings (Rules A, B and C, `03_SCREEN_SPECIFICATIONS.md` Screen 04). The manuscript text is the team's to update. |
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

## Conflicts with Chapters 1–3 (both corrected on 2026-10-12; see the top of this file)

- Chapter 3, Phase 4 says user acceptance testing "were conducted with Barangay Health Workers and
  the Barangay Captain". The evaluation of 2026-10-12 was with a Barangay Health Committee member
  (Kagawad) and an RHU nurse (UE). Chapter 4 states the actual evaluators.
- Chapter 3, Phase 5 says feedback from "health center staff and barangay officials" was used for
  final refinements; the only recorded feedback is the RHU nurse's two comments.

---

# Chapter 5 — sources of its statements

Chapter 5 adds no new finding. **C4** = Chapter 4 of the draft; **C1** = Chapter 1; **C2** =
Chapter 2; **C3** = Chapter 3.

| Chapter 5 statement | Source |
|---|---|
| §5.1 the problem (logbooks, manual inventory, unstructured visits, posting and word of mouth) | C1 Project Context; C4 §4.1 |
| ten modules; four roles; one server computer; browser on computers and phones | C4 §4.1, §4.2 |
| Agile, one module at a time, testing after each module, revisions on the adviser's feedback | C3 Methodology (Phases 2 to 4) |
| 5,121 checks, 28 suites, October 12, 2026 | C4 §4.1, §4.3 (see the 4.1 table above) |
| 2,552 requests; no clinical data to the Administrator or the Official; no sealed text to Staff | C4 §4.3 D |
| thirty-six defects, all corrected and retested | C4 Appendix B (F01 to F36) |
| 14 actions within 3,000 ms at the 95th percentile; one computer, one user; PDF export 1,402 ms | C4 §4.5, Table 4.3 |
| October 12, 2026 evaluators; 18 UAT tasks passed; means of 5.00 (yellow) | C4 §4.6, §4.7; UE |
| §5.2 each objective's wording | C1 Specific Objectives (quoted) |
| Objective 1: under a second; no leak; encryption; audit; retrieval in daily use not measured; manual backups | C4 §4.5 Objective 1 |
| Objective 2: FEFO, expired batch never used, refusal; stock-outs not measured | C4 §4.5 Objective 2 |
| Objective 3: queue rules, referral, eligibility; SMS simulated; flow only after deployment | C4 §4.5 Objective 3 |
| Objective 4: six report types, 12 months, Excel and PDF rows match, within target, small counts; decisions not measured | C4 §4.5 Objective 4 |
| closing: SMS, stock-outs and effect in use not shown; tests do not prove absence of errors; one computer, one user; two evaluators | C4 §4.5 "Overall Discussion", §4.6 |
| §5.3 A1 training and adoption | C4 Table 4.6 (User training) |
| A2 Administrator and Data Protection Officer | Brief (RA 10173 requires personal information controllers to designate a DPO); C1 Scope (RA 10173) |
| A3 privacy notice | Brief; C1 Scope (RA 10173) |
| A4 key envelope; full-disk encryption; key on the same disk | C4 Table 4.6, Table 4.7 risks 2 and 4; EV §7.1 step 5 |
| A5 regular encrypted backups on a separate device; not scheduled | C4 §4.5 Objective 1, Table 4.7 risk 3 |
| A6 Semaphore account; every message simulated | C4 §4.2 Module 6, §4.5 Objective 3 |
| A7 fixed address; certificate warnings | C4 Table 4.6, Table 4.7 risk 7 |
| A8 UPS | Brief; C4 Table 4.7 risk 1 (power interruption) |
| A9 audit logs | C4 §4.2 Module 9 |
| A10 user feedback; RHU comments on the slip | C4 §4.6 User Feedback (1) |
| B1 electronic referral; slip only; RHU nurse stressed referral | C4 §4.6; C1 Limitation (no electronic referrals or reports to the RHU) |
| B2 electronic reports to the RHU | C1 Limitation; the RHU statement is from the brief (yellow, item 7 above) |
| B3 Philippine Health Information Exchange | C1 Limitation |
| B4 one system for the RHU and its barangay health centers | C3 Phase 1 (the RHU coordinates the barangay health centers); C1 Limitation (Barangay Poblacion only) |
| B5 automatic SMS reminders; Angni et al. (2025) | C2 (Angni et al., 2025); C4 §4.2 Module 4 (the date each remaining dose can be given) |
| B6 valid sequence; outbreak campaigns; previous dose on file and valid; routine DOH schedule only | C4 §4.2 Module 4, §4.4 (F29 paragraph); C1 Limitation; PS issue L55 ("Counting doses by valid sequence (CDC practice) is a deeper change, deferred") |
| B7 backup-restore screen | C1 Limitation; C4 §4.2 Module 10 |
| B8 two-factor authentication | C1 Limitation |
| B9 installable mobile application | C1 Limitation |
| B10 several users at once over Wi-Fi and HTTPS, larger database | C4 §4.5 (limits of Table 4.3) |
| B11 wider evaluation (BHWs, midwives, doctors); two evaluators | C4 §4.6 |
