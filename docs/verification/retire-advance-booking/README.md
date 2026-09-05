# retire-advance-booking

Evidence folder for the five-commit retirement of **advance booking** — the
date-and-time scheduling half of Screen 08 — and the renaming of that screen
from *Appointment Scheduling* to **Patient Queue**.

The change came from capstone adviser feedback: a government barangay health
center does not let a patient choose their own hour weeks ahead. People walk in,
and the desk works a queue. Everything that booked, moved or called off a future
visit is gone; check-in, the consultation queue, the calendar and the exports
remain.

It keeps **no images**, for the reason the other folders here give. Every screen
in this pass is a queue, a patient profile or a registration form carrying named
patients' records, and `.gitignore` excludes images under this folder for the
same reason it excludes `app.db`. What is committed is this file, naming what was
exercised and how to produce it again.

## The three stranded bookings were closed BEFORE any code was removed

Three appointments were still open when the pass began — **#15** (Grace Ilagan,
Consultation, Aug 17), **#22** (Liam Villanueva, Consultation, Aug 15) and
**#54** (Darwin Manalastas, Immunization, Aug 23). All three were past-dated and none
had ever been closed.

Each was marked **No-show** through the Cancel dialog while that dialog still
worked, in a real browser, reached the way the Patient Profile reached it
(`?cancel=<id>&back=profile:<patient_id>`). Nothing was deleted; the rows are in
the patients' appointment histories with a real outcome rather than sitting
`Scheduled` forever behind a deleted feature.

Screen 10 before and after, read off the rendered legend:

| Appointment Statistics | before | after |
|---|---|---|
| Still expected | 3 | **0** |
| Cancelled or no-show | 5 | **8** |
| Attended | 41 | 41 |
| Total in range | 49 | 49 |

Down by exactly three, up by exactly three, total unchanged — which is what
"nothing was deleted" looks like in the figures.

Recovery point: `app.db.PRETASK_BACKUP_retire-booking_20260905_224609`.

## How the browser pass was split

Following the convention `my-account/` and `general-vaccination-infant-list/`
set: **reads against the real `app.db`, writes against a throwaway copy.**

* Read-only half — served from `app.py` on **port 5001** against the real
  database. Both exports were downloaded from here.
* Write half — a copy of `app.db` served on **port 5056**. Every check-in,
  consultation, dispensing, immunisation and broadcast below was written there.

Afterwards the real database still held **29 patients, 28 consultations, 6
individual SMS messages, 2 broadcasts, 5 general vaccinations** and a highest
appointment id of **84** — none of the write pass reached it. The copy held 30
patients, 30 consultations and 3 broadcasts, which is where those writes went.

## What was exercised, and what it showed

**Check in an existing patient.** Leonora Buenaventura-Lim, from the Check In
dialog's picker. Flashed *"checked in as a walk-in at 23:37. They are Waiting
(1st in line) while Jomar Manalastas is in consultation."* The dialog's hint now reads
"Records their arrival and puts them in today's queue, in the order they got
here" — it used to promise to convert a booking.

**Check in a brand-new patient.** The dialog's *New patient (first visit)* path
handed off to Register Patient carrying `?check_in=1&check_in_reason=…`; saving
registered **PAT-031 Nestor Evangelista** *and* queued him in one step. The booking
hand-off that used to share that mechanism is gone, and only the check-in notice
renders.

**A full consultation, start to complete.** Started from the queue, written up on
Record Consultation, saved. Flashed *"Consultation recorded … Their visit is now
marked Completed. Nestor Evangelista is next and can be started now"* and landed on
the profile. Validation was exercised on the way: submitting without a diagnosis
or treatment plan was refused with both errors beside their fields and every
other value kept.

**Dispensing and immunisation, in the same save.** Nestor's visit recorded a
Tetanus / Td dose and 14 tablets of Amlodipine: *"Stock updated — Amlodipine now
276"* (from 290). Both still work, and the age-aware vaccine list still offers an
adult the adult vaccines.

**The queue's guard still holds.** Opening `/consultation/record/100` directly
while Nestor was still `Waiting` was refused: *"Nestor Evangelista is marked Waiting,
not In Consultation. Start the consultation from the queue before recording it."*

**The calendar.** Renders the month, one cell per day, with the four-colour
legend intact. Its cells are no longer buttons — they were clickable only to
filter the Upcoming list, which is gone.

**Both exports, downloaded in the browser** from the real database:

* `IDS-BPHCSN Patient Queue - Queue and calendar - 2026-09-05.xlsx` — 11,323 bytes
* `IDS-BPHCSN Patient Queue - Queue and calendar - 2026-09-05.pdf` — 9,424 bytes

The workbook's sheets are **About This File / Today's Queue / Calendar / Summary
/ Not Tracked** — no *Upcoming*. The Summary holds no upcoming figures. The PDF
is 3 pages and contains zero occurrences of "Upcoming", "Appointment Scheduling"
or "booked".

**SMS Notifications (Screen 09).** The six historical individual messages are all
still listed, read-only, under the corrected subtitle: *"…sent by hand when this
system still booked visits ahead. Advance booking was retired, so nothing adds to
this list — it is a closed record, kept because it happened."* Counter reads
**6 messages · 6 simulated, 0 live**.

**The community broadcast, which is a different feature and still works.**
Composed and sent to *Senior Citizens*: *"SMS-2026-0003 sent to 4 of 4 recipients
— 2 segments per recipient (UCS-2). SIMULATED SEND — no key is set for the
messaging service, so this broadcast was recorded in full but no message left the
system."* `gateway_configured()` is `False`, so nothing was transmitted from this
machine at any point in this pass.

**Screen 10, per the confirmed decision.** *Still expected* stays in the legend
reading **(0)**, and the bars still stack to each month's real total. A line under
the legend now says why it is zero and why it is still listed, so the zero is
explained rather than merely honest.

**Settings.** The clinic-hours helper no longer claims these two times decide what
the system offers and accepts. `SLOT_MINUTES` is untouched and still refuses a
clinic day shorter than one slot — 08:00–08:20 refused, 08:00–17:00 accepted.

## The BuildError check, which is the one this pass exists for

A `url_for()` pointing at a deleted endpoint raises only when the page holding it
is actually rendered, so it cannot be found by reading source. Two passes were
run, and both are reproducible:

1. **Every GET route rendered, as every role.** `189` route × role pairs, all
   three roles, against the real database. **Zero 4xx and zero 5xx.**
2. **Every `url_for()` in every template resolved statically**, because some sit
   in branches an ordinary page load never takes — an empty state, a dialog, a
   role-guarded block. 25 templates, **50 literal endpoint names** and **33
   context-supplied endpoint names across 63 name × role pairs**. All resolve.

Both scripts are described under *How to reproduce* below.

## How to reproduce

1. `python app.py`, sign in as the Administrator. Confirm the sidebar reads
   **Patient Queue** and the screen's heading, breadcrumb and browser tab title
   agree with it.
2. On the Patient Queue, confirm there is no New Appointment button, no Upcoming
   Appointments panel, no Upcoming Reminders strip beside the calendar, and no
   Reschedule or Cancel on any queue row. Under the queue, confirm the stated
   note **"Two things this screen does not do"**, which quotes
   `utils/unavailable.py` `advance_booking` and `queue_exit`.
3. Open Check In Patient and confirm the picker still scrolls inside its own list
   with no empty region below the last field — that is the shared
   `.patient-pick` / `.patient-option` CSS, which this pass deliberately did not
   touch. See `booking-dialog-gap/` for what that fix was.
4. On a Patient Profile: no **Schedule Appointment** button, three summary tiles
   rather than four, and Appointment History showing past appointments with only
   the read-only notes icon.
5. Exports: download both from the queue toolbar and confirm the file name says
   *Patient Queue - Queue and calendar* and the workbook has no Upcoming sheet.
6. Reports & Analytics: confirm *Still expected (0)* is in the legend with the
   sentence under it explaining the zero, and that each month's bars sum to that
   month's total.
7. The two verification scripts. Both are standalone and print a pass line:
   * a route sweep that renders every GET rule under each of the three roles and
     reports any 4xx/5xx, quoting the `BuildError` / `UndefinedError` out of the
     response body when there is one;
   * a template scan that pulls every `url_for(` argument out of
     `templates/*.html` and resolves it against `app.view_functions`, the flat
     alias map in `utils/endpoints.py`, and each role's `_endpoint` names from
     `inject_role_context()`.

## Known gaps, stated rather than left to be found

* **A patient who checks in and leaves before being seen cannot be closed off the
  queue.** Their row stays `Waiting`. This was never the queue's own closure —
  Cancel / No-show acted on bookings nobody had arrived for and refused outright
  once a patient was checked in — so nothing was taken away here, but the removal
  makes the absence visible. It needs a status the schema's CHECK does not admit
  and a guarded write of its own, and it is a task of its own. Named on the
  screen and in the export's Not Tracked sheet as `queue_exit`.
* **The BOOKED column on the queue table, and "Booked for" in the export, can now
  only ever be blank.** They are honest (they print an em dash), they are not
  false, and removing a table column was outside this pass's scope — recorded
  here so the next reader knows it was seen rather than missed.
* **No replacement schedule is described anywhere**, deliberately. A fixed
  schedule of service days is the honest successor to what was removed, and which
  days carry which services has not been confirmed with Barangay Poblacion Health
  Center. `advance_booking` says a schedule is planned and names no days.
