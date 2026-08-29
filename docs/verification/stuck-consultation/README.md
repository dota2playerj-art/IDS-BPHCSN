# Stuck consultation — the 2026-08-29 block, and the mismatch behind it

Verification for the pass that closed appointment 67 and stopped the queue screen
disagreeing with the server about who holds the consultation room.

## What was wrong

Checking in Arnel Manalastas (PAT-018) on 2026-08-29 succeeded; starting his
consultation was refused with **"Remedios Manalastas is still in consultation"** —
naming a patient nowhere in Today's Queue.

Two separate defects, and only fixing both stops it recurring:

**a. One stale row.** Appointment 67 — Remedios Lagunzad Manalastas, PAT-026, a walk-in
on 2026-08-28 — was checked in at 23:36:30 and started six seconds later at
23:36:36. Nothing closed it. No consultation record was ever written for it. An
appointment leaves `In Consultation` only through `complete_consultation()`,
reached either from the queue's "Mark Completed" button or as the last step of
saving the write-up form; a form opened and abandoned leaves the row open
forever. There is no timeout and no sweep.

**b. Two scopes for one question.** `start_consultation()` guards with
`NOT EXISTS (... status = 'In Consultation')` over the whole table, no date
filter — deliberately, per `get_active_consultation()`'s docstring: a visit left
open when the clinic closed still occupies the clinician. But
`_apply_queue_flow()` and `get_queue_stats()` decided `can_start`, `is_ready`,
`room_free` and the "In Consultation" card from **today's rows only**. Before
midnight the two agree. After midnight they cannot: the stale row leaves today's
query while still holding the room. So the screen rendered an enabled **Start
Consultation** button, a "Ready to Consult" badge and a card reading
*In Consultation: 0*, and the server refused the click.

This had happened before. Scanning every `app.db.*BACKUP*` found the same shape
three times — appointment 59 (2026-08-27, ~49 min), appointment 64 (2026-08-28,
~6 h), appointment 67 (~16 h and counting). The first two were cleared by chance
when someone later finished the write-up. Only 67 crossed midnight, which is the
only reason it became visible as a bug.

## What was changed

| Fix | Where |
| --- | --- |
| a | `migrate_close_stuck_consultation.py` — appointment 67 to `Completed`, an honest note on the row, one `audit_logs` entry. No consultation record invented. |
| b | `models/appointments.py` — `_apply_queue_flow()` and `get_queue_stats()` take the room from `get_active_consultation()`, the same date-unscoped fact the server's UPDATE tests. |
| b | `routes/appointment_views.py`, `routes/dashboard_views.py` — resolve the room once per render, hand it to both the queue and its stat cards. |
| b | `templates/appointment_scheduling.html` — a warning banner over the queue naming a visit left open on an earlier day, with both resolutions on it; the "In Consultation" card counts the room, not today's rows; the footer keeps the today-only tally. |
| b | `routes/roster_export.py` — the export's "In consultation now" note says when the visit it names was started on another day. |

`in_consultation` (the room, whole-database) and `in_consultation_today` (today's
rows, the footer's disjoint tally) are now separate keys. They differ only while
the room is held by another day's visit.

**No automatic timeout was built, deliberately.** A visit genuinely still in
progress across midnight is a real possibility, and a timer that completed it
would silently discard a clinical record. The screen makes the state impossible
to miss and trivial to resolve; which of the two resolutions is true is the
clinician's call.

## Why `Completed` and not another status

Of the seven values the `status` CHECK admits, three could describe a visit that
began and stopped. `No-show` is false — she arrived, was checked in and was
brought in. `Cancelled` is false — a cancellation is a visit called off before it
happened; this one happened, and what is missing is the write-up. `Completed` is
true in the only sense this system gives the word: the queue entry is closed and
no longer holds the room. It asserts nothing about a consultation record — twelve
other `Completed` appointments have none, and the queue offers "Mark Completed"
beside "Record Consultation" for exactly this case.

That nothing was written is stated rather than implied: in the row's own `notes`,
and in an `audit_logs` entry under **Appointment Scheduling** (id 875) naming the
appointment, both statuses and the reason. Fabricating a consultation would have
put a diagnosis in a patient's clinical history that no clinician ever made.

## How it was tested

No committed automated test suite exists in this project, so two harnesses were
built for this pass and kept in the session scratchpad rather than the
repository. Both are described here well enough to rebuild.

### 1. Scenario suite — 47 assertions, all passing

Each scenario copies a database into a temp directory, points
`app.config["DATABASE"]` at the copy and asserts against it. Nothing writes to
the real `app.db`. The scenarios that reproduce the bug read from
`app.db.PRETASK_BACKUP_stuck-consultation_20260829_153935`, which still holds the
genuine stuck row, so they keep reproducing the real state now that the data is
corrected.

| | Scenario | Asserts |
| --- | --- | --- |
| S1 | The real bug, from the pre-fix backup | `room_free` false, `active_name` "Remedios Manalastas", `active_is_stale` true, `in_consultation` 1 / `in_consultation_today` 0, `ready` 0, no row offers `can_start` |
| S2 | A consultation in progress **today** | Unchanged behaviour: room held, `active_is_stale` **false**, both counts 1, the in-progress row can be completed, nobody else may start |
| S3 / S3b | Room free, two waiting | Both may start (out-of-turn allowed), exactly one is ready, and ready follows `checked_in_at` — proven by running the same scenario with the arrival order reversed |
| **S4** | **The invariant, four room states** | For every queue row, `can_start` is compared against **actually calling `start_consultation()`** on a pristine copy. Zero disagreements across stale-holder, holder-today, room-free and booked-not-arrived |
| S5 | The banner's Mark Completed | Banner present → POST → appointment 67 `Completed`, banner gone, room free, waiting patient may start, and the server really starts them |
| S6 | The banner's Record Consultation | The write-up form opens for the past-dated visit, saves, closes it, and a consultation exists |
| S7 | A malformed `appointment_date` | Stat cards render rather than raising; an unparseable date is not claimed as stale; the room is still held |

S4 is the one that matters most: it does not reason about agreement, it measures
it, by attempting the write the button would perform.

### 2. Route × role render matrix — 183 renders

Every GET route rendered under all three roles (61 rules × 3, parameterised rules
filled with real ids), bodies written to a directory and diffed before and after.
The sweep re-establishes the session before every request, because `/logout` is
one of the routes under test.

A **noise floor** was measured first by rendering twice with no code change:
22 files — every PDF and XLSX export — differ between two identical runs because
of embedded creation timestamps. HTML renders are stable once the per-page
"Loaded 3:39 PM" stamp is scrubbed.

- **Fix B alone** (code changed, database untouched): of 183 renders, **exactly 3**
  HTML screens changed — `admin`/`staff` Appointment Scheduling and the Staff
  dashboard. Every other HTML render byte-identical.
- **Both fixes**: 9 HTML screens differ, all accounted for — the two queue
  screens, both dashboards, Audit Logs (the new entry), Remedios's profile on both
  roles (her appointment history now reads Completed), and
  `/consultation/record/67` on both roles.
- The route × role **status matrix is unchanged** but for one cell:
  `/consultation/record/67` now redirects instead of rendering, because
  `record_consultation_context()` correctly refuses to write up a closed visit —
  *"Remedios Manalastas is marked Completed, not In Consultation."*
- No exceptions, no 500s, before or after.

### 3. End-to-end, on a copy of the corrected database

Banner absent → Arnel's row shows "Ready to Consult" with an enabled button →
POST start-consultation returns *"Arnel Manalastas is now In Consultation."* → the
card reads 1, "being seen now", **no** stale banner (his visit is today's) → both
Record Consultation and Mark Completed offered → completing works.

Run on a copy, deliberately: the real database is left with Arnel still
`Waiting`, which is the correct clinical state. Whether to call him in is the
clinician's decision, not a verification step's.

### 4. Migration safety

Dry-run twice on a copy (second run a no-op), and both refusal guards exercised
on their own copies: a row in an unexpected status, and a row that already has a
consultation. Both refuse, and both leave the row and `audit_logs` untouched.
Verification runs before the commit — on failure the transaction is rolled back
and nothing is written.

`python app.py` starts clean, no traceback; `/login` 200, guarded routes 302.

## Reproducing

1. `python app.py`, sign in as Health Center Staff, open Appointment Scheduling.
   With the corrected database the banner is absent and Start Consultation works.
2. To see the bug and the fix together, point `config.DATABASE` at
   `app.db.PRETASK_BACKUP_stuck-consultation_20260829_153935` and reload: the
   banner names Remedios Manalastas, APT-00067, Aug 28, the card reads 1, and every
   Start Consultation button is disabled with a tooltip naming her.
3. `python migrate_close_stuck_consultation.py` is idempotent — running it against
   the corrected database prints "Already Completed — nothing to repair."

## Not in version control

No screenshots are kept for this pass. The evidence above is textual — render
diffs, assertion output and database rows — and the queue screen shows patient
names, patient IDs, arrival times and reasons for visit, which is the same
material this folder's root `README.md` refuses to commit for the vaccination
correction. The `audit_logs` entry is the durable half of the record, and that
half lives in the database where it belongs.
