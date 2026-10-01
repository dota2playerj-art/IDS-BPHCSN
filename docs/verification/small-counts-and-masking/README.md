# Task 5d — small counts and masked numbers

The checklist for Task 5d. Two rules, one shared helper each.

- **D1 small counts.** For the Administrator and the Barangay Official, any row of
  a ranking or breakdown by diagnosis, complaint, condition or dispensed medicine
  with a count from 1 to 4 folds into one row, "Other (each fewer than 5)". The
  threshold is `SMALL_COUNT_THRESHOLD` in `config.py`. Totals stay exact. The Doctor
  sees every count.
- **D3 masked numbers.** On every SMS screen, export and JSON response, a phone
  number shows its last 4 digits only ("•••• ••• 1234"). Full numbers stay where
  the system sends messages.

Why D1: the Administrator can see who is in the queue and when. A count of 1 over a
short date range can point at one person.

## Part A — rankings and breakdowns

Every one is built from the three model functions below, so the helper is applied
there and every screen, chart, export and print view inherits it.

| Ranking | Built by | Screen / chart | Excel + PDF sheet | Admin | Official | Doctor |
|---|---|---|---|---|---|---|
| Most common diagnoses (range) | `get_consultation_stats()` `window.top_diagnoses` | Reports & Analytics; Community Reports | "Diagnoses", "Health Concerns" | fold | fold | all |
| Most common complaints (range) | `window.top_complaints` | Reports & Analytics (data only); Community Reports | "Diagnoses" | fold | fold | all |
| Same two, all time | `top_diagnoses`, `top_complaints` | no screen reads them | none | fold | fold | all |
| Most dispensed items (range) | `get_dispensing_stats()` `window.top_medicines`, `all_medicines` | Reports & Analytics table and chart | "Items Dispensed" | fold | fold | all |
| Chronic conditions, whole register | `get_condition_counts()` via `get_patient_report()` `conditions` | Reports & Analytics; Community Reports chart and table | "Demographics", "Health Concerns" | fold | fold | all |
| Senior chronic conditions | `senior_conditions` | Reports & Analytics table, text line and chart | "Senior Citizens" | fold | fold | all |
| Restricted-visit count line | `window.diagnoses_withheld` | Reports & Analytics, Community Reports | "Diagnoses" Basis | hide under 5 | hide under 5 | exact |

Roles that reach Reports & Analytics: Administrator (`/admin/reports_analytics`),
Barangay Official (`/official/reports_analytics`, `/official/community_reports`),
Doctor (`/staff/reports_analytics`). Health Center Staff has no route to it. The two
dashboards read the same builders: the Administrator dashboard reads trends and
totals only; the Official dashboard reads `patient_report`.

Not in scope, and not changed: appointments by service, age bands, sex split. They
are not a breakdown by diagnosis, complaint, condition or medicine.

## Part B — phone numbers on SMS pages

| Place | Shows a number today | Admin | Official | Doctor | Staff |
|---|---|---|---|---|---|
| SMS Notifications, latest broadcast recipient list | `recipient.mobile_number` | none (not fetched) | full → masked | full → masked | full → masked |
| SMS Notifications, appointment confirmations panel | `message.mobile_number` | panel absent | panel absent | full → masked | full → masked |
| Broadcast history, stats, flash after a send | counts only | counts | counts | counts | counts |
| Broadcast audit entry | message text, counts; no number | no number | no number | no number | no number |
| Appointment SMS audit entries (8 old rows) | no number (checked: 0 of 8) | none | n/a | n/a | n/a |
| Reports "SMS" sheet, Community Reports | counts only | counts | counts | counts | counts |
| JSON endpoints | none exist | | | | |

Full numbers stay in `sms_broadcast_recipients`, `appointment_sms_messages`, and in
`models/broadcasts.py` `send_broadcast()`, which hands them to the gateway.

## Task 5e — what the 5d helper did not yet cover

Counts tied to a health service or condition, shown to the Administrator or the
Barangay Official.

| Count | Where | Decision |
|---|---|---|
| Appointments by service requested (range and year to date) | Reports & Analytics screen, chart, print table, Excel, PDF; Official dashboard reads the same builder | fold under 5 into Other (D1) |
| Prenatal Check-up count beside the prenatal note | Reports & Analytics | reads "Fewer than 5" (D2) |
| Patients with any recorded condition | Excel summary and Health Concerns sheets | reads "Fewer than 5" (D2) |
| Patients (and seniors) with only free-text conditions | Reports & Analytics, Community Reports, Excel, PDF | reads "Fewer than 5" (D2) |
| Audit text quoting a phone number | Audit Logs screen and exports | masked when written, and by a migration for old entries (D3) |
| Per-dose and per-vaccine coverage (given, overdue, due now) | Vaccination Campaigns, Official only | not changed: cohort coverage with a denominator, not a ranking. Logged as an issue for the team |
| Queue "services today" | Patient Queue | not changed: the queue itself is visible to the Administrator |
