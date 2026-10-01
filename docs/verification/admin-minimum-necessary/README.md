# Task 5c — the Administrator's access, route by route

The checklist for Task 5c (care-team-only clinical data). The Administrator reaches
46 view functions in `routes/admin.py` (two of them answer two URLs each) and the
shared account routes in `routes/auth.py`. No other blueprint admits him:
`routes/staff.py` admits the Doctor and Health Center Staff only, and
`routes/official.py` admits the Barangay Official only.

Why: RA 11166 allows medical information to be shared only with health workers
involved in the patient's care. RA 10173 says processing must be adequate,
relevant and not excessive. The project follows the "minimum necessary" standard.
The Administrator runs the system; he is not part of anyone's care.

Status: **KEEP** (unchanged), **KEEP-REDUCED** (demographics or counts only),
**REMOVE** (the Administrator is refused on the server).

## Patient records (Screens 03, 04, 05)

| Route | Reads | Writes | Clinical data before Task 5c | Status |
|---|---|---|---|---|
| `GET /admin/patient_records` | every patient row, last visit | — | contact number, last visit date, edit links, Change Status | KEEP-REDUCED: demographics only, read-only |
| `GET /admin/patient_records/export.xlsx`, `.pdf` | the roster | — | contact number, last visit | KEEP-REDUCED: demographics only |
| `POST /admin/patient_records/export-selection.xlsx`, `.pdf` | ticked rows | — | same as above | KEEP-REDUCED: demographics only |
| `POST /admin/patient_records/archive` | patients | status | a patient write | REMOVE |
| `GET /admin/patient_profile/<id>` (and `?print=1`) | patient, consultations, doses, dispensing, appointments | audit entry when a seal withholds | every clinical field, contact numbers, check-in reasons, medicine names | KEEP-REDUCED: demographics only, one plain line instead of the clinical tabs |
| `POST /admin/patient_profile/<id>/correct-vaccination` | doses | doses | a clinical write | REMOVE |
| `GET/POST /admin/register_patient[/<id>]` | patient | patient | conditions, allergies, contacts; a patient write | REMOVE |

## Patient Queue and consultations (Screens 08, 20)

| Route | Reads | Writes | Clinical data before Task 5c | Status |
|---|---|---|---|---|
| `GET /admin/appointment_scheduling` | today's queue, calendar | — | immunization-due tags, check-in dialog and patient picker, action buttons | KEEP-REDUCED: read-only; who, status, times |
| `GET /admin/appointment_scheduling/export.xlsx`, `.pdf` | the same | — | (the reason column was already gone, Task 5b) | KEEP-REDUCED |
| `POST /admin/appointment_scheduling/check-in` | — | appointments | a queue write | REMOVE |
| `POST /admin/appointment_scheduling/start-consultation` | — | appointments | a queue write | REMOVE |
| `POST /admin/appointment_scheduling/complete-consultation` | — | appointments | a queue write | REMOVE |
| `GET/POST /admin/consultation/record/<id>` | appointment, patient | consultation, doses, dispensing | every clinical field | REMOVE |
| `GET/POST /admin/consultation/edit/<id>` | consultation | the same | every clinical field | REMOVE |

## Dashboard (Screen 02)

| Widget | Clinical data before Task 5c | Status |
|---|---|---|
| Six stat cards | counts | KEEP |
| In consultation now | patient name, plus a Continue Consultation button | KEEP-REDUCED: name and times, no button |
| Recent Patient Consultations | chief complaint, medicines dispensed per patient | REMOVE |
| Monthly Analytics charts | counts | KEEP |
| Medicine Inventory low stock | item names and stock, no patient | KEEP |
| Immunization Follow-up | children's names with the dose each is due | KEEP-REDUCED: counts only |
| SMS Broadcast, System Activity | action names | KEEP |

## Everything else

| Route | Clinical data before Task 5c | Status |
|---|---|---|
| Medicine Inventory: screen, two exports, archive, add/edit | none tied to a patient | KEEP |
| `GET /admin/sms_notifications` | broadcast recipients' mobile numbers; the appointment-SMS panel (patient, number, message about their visit) | KEEP-REDUCED: no numbers, no appointment-SMS panel |
| `POST /admin/sms_notifications/send` | none | KEEP |
| Reports & Analytics: screen, two exports | counts and rankings; "most dispensed" named sealed-visit medicines (M25) | KEEP; the ranking counts sealed-visit dispensing as "Confidential" (Step 6) |
| User Management: screen, add, edit, reset, status, two exports | none | KEEP |
| Audit Logs: screen, two exports | entries naming medicines and vaccines given to a named patient; correction entries quoting doses and dates; edit entries quoting vitals | KEEP-REDUCED: entries hold no patient-linked clinical content (Step 4) |
| Settings: screen, general, maintenance | none | KEEP |
| `GET /admin/settings/backup.db` | the whole database, plain | KEEP-REDUCED: an encrypted `.idsbackup` file (Step 5) |
| Service Schedule: screen, add, edit, delete | none | KEEP |
| `/account`, `/account/password`, `/session/keep-alive` (JSON), `/dashboard`, `/login`, `/logout` | none | KEEP |

Counts: 23 KEEP, 15 KEEP-REDUCED, 8 REMOVE.

Surprises found while listing:

- Changing a patient's status (Active, Inactive) was the Administrator's too. It is a patient write, so it goes.
- The appointment-SMS panel on SMS Notifications showed him each patient's mobile number and the text sent about their visit.
- The dashboard's Immunization Follow-up named each child and the dose they were due.
- Correction entries in Audit Logs quoted vaccine names and dates, and consultation edit entries quoted vitals.
