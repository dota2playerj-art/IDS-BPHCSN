# Performance measurement — 2026-10-09 15:53

Made by `tests/perf/measure_performance.py`. 3 warm-up runs, then 30 timed runs per action. Target: 3000 ms. Time = from sending the request to the last byte of the response, measured by a client on the same computer (no Wi-Fi in the path), one new connection per request, redirects not followed.

## Test computer

- CPU: 13th Gen Intel(R) Core(TM) i5-13420H (12 logical processors)
- RAM: 15.6 GB
- OS: Windows 11 CoreSingleLanguage (build 10.0.26200)
- Python: 3.14.6
- Flask: 3.1.3
- Server: cheroot 11.1.2, local mode (127.0.0.1, HTTP), 10 threads
- Server banner: Local mode: this computer only. Open http://127.0.0.1:64879

## Data

Fictional demo database built by `seed_demo_data.py` in a temporary folder (148 s), never `app.db`: 1.3 MB as seeded, with 150 patients, 421 visits, 411 consultations, 302 immunizations, 15 inventory items, 27 inventory batches, 354 dispensing rows, 3199 audit entries. Then 66 visits were added for today, Waiting, one per timed save (each run starts its own visit first, untimed, as the queue does).

## Results (milliseconds)

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

## Checks on what the write runs left

- Doctor: 33 of 33 visits have a saved consultation.
- Health Center Staff: 33 of 33 visits have a saved consultation.
- FEFO: 33 units dispensed in 33 runs; 33 from the usable batch with the earliest expiry, 0 from an expired batch (the item has 2 usable and 0 expired batch(es) with stock).

## Failed runs

None.
