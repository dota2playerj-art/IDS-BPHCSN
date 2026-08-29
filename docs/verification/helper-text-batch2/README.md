# helper-text-batch2/

Verification of Batch 2 of the helper-text rewrite — Settings and the shared
reason dictionaries. Eighteen strings, six files, no logic or layout touched.

This batch differs from Batch 1 in one way that shaped how it was checked: most
of these strings are **shared**. One edit to `UNAVAILABLE["sort"]` changes four
screens; `SNAPSHOT_NOTE` prints thirteen times across two report screens and is
carried into both exports. So the question is not only "is each note right" but
"did the change reach every place that prints it, and nowhere else".

No images are committed — see the note in the parent README.

## What changed

| Where | Entries | Longest before → after |
| --- | --- | --- |
| `templates/settings.html` | 4 blocks | 618 → 330 ch |
| `utils/unavailable.py` | 7 of 7 entries | 716 → 267 ch |
| `routes/audit_views.py` | 2 | 901 → 485 ch |
| `routes/official_views.py` | 5 | 391 → 265 ch |
| `routes/user_views.py` | 2 | 458 → 235 ch |
| `routes/report_views.py` | `SNAPSHOT_NOTE` | 183 → 131 ch |

Two pairs were written **together** rather than shortened separately, because
each pair was stating one set of facts twice, at two lengths, in two
vocabularies:

- **Settings' opening note + `UNAVAILABLE["settings"]`.** The shared reason is
  also the tooltip on four disabled buttons, so it has to stand alone there. It
  now carries what the screen is; the note carries only the live exception.
  Together they read as one statement of 329 characters, down from about 1,000.
- **Settings' Security note + `audit_views.UNTRACKED["login_scope"]`.** Both
  now carry the same five sentences word for word. `login_scope` adds only the
  three facts that are about its card rather than about signing in.

## How it was checked

Four passes, all against a **scratch copy** of `app.db`.

### 1. Fact-by-fact, on the rendered page — 116 / 116

Every "must survive" fact is a separate assertion against the rendered output,
with a negative assertion beside it that the old wording is gone.

**Most of these strings are tooltips, not body copy.** `sort`, `pagination`,
`appointment_detail`, `backup`, `sms_gateway`, `settings` and `login_scope` all
render into `title=` attributes. A check that only read visible text would have
passed on every one of them *by their absence*. The suite parses `title=`
attributes as a separate surface and asserts against that, including how many
times each tooltip appears (`settings` on four buttons, `backup` on three,
`login_scope` on both sign-in cards).

`LOCAL_UNTRACKED["announcements"]` renders only when nothing has been published,
and this database has broadcasts, so that one is asserted against the constant
directly rather than pretended to be covered.

### 2. Both "written together" pairs state matching facts

The five shared sentences are asserted present on Settings (as body copy) *and*
on Audit Logs (as tooltip text), by identical string match. Not "both are
shorter" — the same sentence, on both screens.

### 3. Route × role matrix

86 routes and 81 guarded definitions, snapshotted before the first edit and
compared after the last: **identical**.

### 4. Before/after render comparison, and every changed line accounted for

177 (role, route) pairs rendered on both sides of the change. Each line carries
the status code, the visible-text length, and the combined length of every
`title=` attribute on the page — the tooltip column exists because without it a
shared reason could change on four disabled buttons and the diff would show
nothing.

**68 lines changed.** Rather than eyeball them, `_explain_deltas.py` reconciled
each one: for every changed page it counted how many times each edited string
renders on each surface, multiplied by how much that string shrank, and compared
the prediction to the measurement. For Settings, whose template prose changed as
well as the strings it prints, the old template file was rendered beside the new
one — same app, same database, same constants, only the file swapped — so the
template's contribution was measured rather than estimated.

Result: **all 68 reconcile exactly**, and the converse check found no page that
renders an edited string and did not change.

## A bug in the checking, found and fixed

Batch 1's before/after harness walked the routes in sorted order, which puts
`/logout` ahead of every `/official/*` and `/staff/*` route. It signed the
session out a third of the way through and measured the login page for
everything after — identically on both sides of the change, so the diff stayed
clean and the fault was invisible.

The effect on Batch 1's reported result: its two-changed-lines conclusion holds
for what it actually measured, but its coverage was narrower than the report
claimed. Administrator routes were genuinely exercised; the Health Center Staff
and Barangay Official routes after `/logout` were not.

`_smoke_routes.py` now excludes `/logout` and `/login`, and this batch's run
covers all 177 pairs signed in. Batch 1's two templates were re-rendered under
all three roles in this run as part of the before/after baseline, and behave as
that batch reported.

## Two things left alone, and why

Both are real instances of the pattern. Neither is in this batch's brief, and
neither was quietly fixed:

- **`templates/settings.html`, the API-key field hint.** "The key is read from
  the server's environment, not from this screen. `utils/sms.py` checks for it
  on every send." A filename on screen, two lines from a tooltip this batch just
  removed `SEMAPHORE_API_KEY` from. The audit put it in the "already right"
  bucket on length alone.
- **Five reason-dict entries the audit also filed as "already right"**, which
  are short but name a table or a function: `official_views["events"]`
  ("the schema"), `report_views["sms"]` (`sms_broadcasts`),
  `report_views["prenatal"]` ("the schema"),
  `report_views["generated_reports"]` (`audit_logs`),
  `user_views["reset_password"]` (`seed_demo_users()`).

The audit sorted entries by length and by whether they argued their own design.
It did not sort them by whether they name code, so five short entries that do
came through as "keep". That is a gap in the audit, not in this batch.

## Reproducing it

1. `python app.py` — confirm clean startup and `/login` serving 200.
2. Sign in as Administrator and open **Settings**. Read the opening note, then
   the Security Settings pane at the bottom. Hover Save Changes, Reset to
   Default, Test Connection and Backup Now.
3. Open **Audit Logs** and hover the two sign-in stat cards. The five sentences
   about signing in should be word for word the ones on Settings.
4. Open **Appointment Scheduling** and hover the disabled Sort button;
   **Patient Records** and **Medicine Inventory** and hover "Single page";
   a **Patient Profile** and hover the disabled view icon on an appointment row.
5. Open **Reports & Analytics** and confirm the snapshot note under the
   inventory, roster and programme panels.
6. Sign in as Barangay Official and open the dashboard, Health Programs,
   Vaccination Campaigns and Notifications.
7. Repeat step 4 signed in as Health Center Staff.

## Database

`app.db` gained one row in `audit_logs` — a sign-in by the `official` account
from a verification run. Nothing else changed: a table-by-table row-count diff
against `app.db.PRETASK_BACKUP_helpertext-batch2_20260829_103100` shows
`audit_logs` +1 and every other table identical. The row is an accurate record
of a sign-in that happened and was left in place, as in Batch 1.
