# PAT-029 and the last of the invented figures on Settings

Verification of two things done together because they are the same problem in
two places: a fictional patient sitting in the live roster with a real-looking
appointment on tomorrow's queue, and the figures on Screen 13 that were still
asserting facts nobody had checked.

**No images were retained from this pass, and that is deliberate.** Every render
below was produced against a *throwaway copy* of `app.db`, so exercising the
screens left no sign-in rows in the real database — the live trail still holds
1057 sign-ins, the same number it held before this work started, while the copy
the sweep drove went to 1061. A screenshot of Patient Records or Appointment
Scheduling is a patient record either way and would be excluded from git for the
reason the parent README gives. What survives is the recipe and the suite, which
is the checkable half.

## What was removed from the database

| | |
| --- | --- |
| `patients` id 95 | `PAT-029` "JOhn asc asdas", Inactive, born 2026-07-01, civil status Married |
| `appointments` id 78 | patient 95, **2026-09-03 12:30**, Consultation, **Scheduled** |

Both were written on 2026-09-02 at 06:25:57 by somebody trying the Register
Patient form and then the booking dialog. Somebody had already set the patient
Inactive, which in this system does not touch their bookings — so the fictional
visit was still Scheduled for the following day and still on the queue, the
calendar and the day's counts.

`migrate_remove_fake_patient.py` does the removal and carries the full reasoning:
why these rows are deleted where this project otherwise archives, why the
appointment is deleted rather than Cancelled, and why the audit entry it writes
has to say *which* fictional PAT-029 it means — there have now been two, and
freeing the identifier hands it to the next real registration.

## How "only these rows changed" was established

A backup was taken immediately before the run
(`app.db.PRETASK_BACKUP_fake-patient-pat029_20260902_174847`) and the migration
refuses to start without it. Three separate checks, two of them inside the
transaction:

1. **Before deleting** — every table with a foreign key to `patients` or
   `appointments` is queried for these two ids. Eight relationships, all zero.
   Anything found aborts the run rather than orphaning it.
2. **Before committing** — every row of every table is compared column by column
   against the backup. Any difference other than the two declared removals and
   the one appended audit entry rolls the transaction back. `foreign_key_check`
   and `integrity_check` are asked of the database rather than inferred from the
   deletion order.
3. **After committing, independently** — a separate script diffed the backup
   against the live file again, table by table and column by column, without
   using any of the migration's own code. It reported **3 differing rows in the
   whole database**: `patients` 95 removed, `appointments` 78 removed,
   `audit_logs` 1107 added. Every other table was byte-identical.

Both refusal paths were exercised on scratch copies before the real run, and
both roll back completely:

* a planted `consultations` row pointing at patient 95 → `REFUSED`, nothing
  deleted, exit 1;
* id 95 edited to hold a plausible real patient → the identity check refuses it,
  and the whole transaction including appointment 78 is rolled back, exit 1.

Re-running the migration is a no-op: it reports both rows already gone, writes no
second audit entry, and exits 0.

## What changed on Screen 13

| Row | Was | Now |
| --- | --- | --- |
| Backup Size | `248 MB` | `Not tracked`, grey, with the reason on hover |
| Backup Schedule | `Daily, 3:00 AM` | `None`, grey, with the reason on hover |
| SMS → Billing Info | `Cost per SMS ₱0.50`, `Billing Account: Barangay LGU Account` | section removed |
| The shared scope-note reason | "The values shown are the settings the application actually runs on" | says most values are placeholder text, and names the few that are not |
| The note's live exception | "the one exception" | names all three |

The two backup rows get *different* words on purpose, and the SMS section is
deleted rather than relabelled, for the distinction the removed Cache Status
field already recorded on this screen: "Not tracked" belongs to something the
system has and does not record. Backups are that — hand-made file copies, so one
exists and has a size nobody writes down. A schedule and a billing account are
not: neither exists at all, and "Not tracked" would be asserting one that nobody
happened to record. Each template comment carries its own half of that argument.

## The automated suite

49 checks, run against a scratch copy alongside the work. All 49 passed.

* **Route sweep** — all 51 parameterless GET routes rendered under all three
  roles, 153 renders, no 5xx.
* **Settings, as Administrator** — every fabricated string asserted *absent* from
  the rendered HTML (`248 MB`, `Daily, 3:00 AM`, `3:00 AM`, `Billing Info`,
  `Cost per SMS`, `Billing Account`, `Barangay LGU Account`, `0.50`, and both
  retired sentences); every replacement asserted *present*; the shared reason
  counted at exactly 5 occurrences (the note plus four disabled buttons); and no
  `{#` left in the output, so none of the new commentary leaks to the browser.
* **The three live values are live** — the sign-in count matches a direct
  `COUNT(*)` against the scratch database, Head Physician renders the signed-in
  administrator, and the Database row renders the interpreter's own
  `sqlite3.sqlite_version`.
* **The patient is gone** — `PAT-029`, `asdas` and `JOhn asc` searched across all
  51 responses under all three roles, including the `.xlsx` and `.pdf` exports as
  bytes. Two appearances survive and are asserted *by name* rather than skipped:
  the audit entry recording the removal, which has to name what it removed, and
  Register Patient's `Auto-generated: PAT-029` preview, which is the reissue that
  entry warns about.
* **Nothing is Scheduled for 2026-09-03 any more**, and the Aug 31 removal entry
  naming the *first* PAT-029 is still in the trail, unrewritten.

### Reproducing it

1. Copy `app.db` somewhere scratch and point a throwaway launcher at it, so the
   run writes nothing to the real database:

   ```python
   import config
   config.DATABASE = r"C:/path/to/scratch/app.db"
   import app as m
   m.app.config["DATABASE"] = config.DATABASE
   m.app.run(port=5055)
   ```

2. Sign in as the Administrator and open **Settings → Backup & Restore**. The
   three rows read `Not tracked`, `Not tracked`, `None`, all grey, each with its
   own reason on hover.
3. **Settings → SMS Gateway Configuration**. The pane ends at **Test
   Connection**; there is no Billing Info below it, and the Connection Status
   pill still reads **Not configured**.
4. Read the note at the top of the screen. It should name three live values and
   nothing else should claim to be live.
5. **Patient Records** and **Appointment Scheduling** — no PAT-029, and nothing
   booked for 2026-09-03 except the real Cancelled appointment for PAT-018.
6. **Audit Logs → Patient Records** — the removal entry, naming both rows, the
   reasoning, and which PAT-029 it means.
