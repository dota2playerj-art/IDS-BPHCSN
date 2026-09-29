# service-schedule

Evidence folder for the Service Schedule (Screen 22): 085d14d (storage, empty),
f87282d (the screen, Administrator-only writes, audit) and 9d13b7f (today's
services on the Patient Queue).

It keeps **no images**, for the reason the other folders here give. What is
committed is this file, naming what was exercised and how to produce it again.

## The schedule ships empty, and the live database proves it

The health center has not been interviewed, so no service day was entered.
Against the pre-task backup `app.db.PRETASK_BACKUP_service-schedule_20260926_002801`,
the live `app.db` differs by exactly one object, the `service_schedule` table,
which holds **0 rows**. All 14 tables that existed before are identical row for
row, and there is no Service Schedule audit entry. The migration ran on the live
database once, on 2026-09-26.

Re-running `migrate_add_service_schedule.py` on a copy of the migrated database
leaves its logical dump identical: 1,472 statements before and after. Two
header bytes change, SQLite's file change counter at offsets 24–27 and 92–95.
The rolled-back constraint probes bump them. No data or schema changes.

## How the date was controlled

`utils/dates.py` is the application's one source of "now". `today()` looks up
`now` in that module's globals at call time. The suites replace
`utils.dates.now` with a function that returns 09:00 clinic time on the chosen
date. That moves "today" for every caller at once: the queue, the schedule's
"Running today", the header. Each queue page read was also checked for its own
`Today's Queue <date>` line, which proves the whole screen used the controlled
date.

## Nth weekday of the month

A "2nd and 4th Wednesday" entry was read off the Patient Queue on **every
Wednesday from 2 Sep 2026 to 25 Aug 2027**. That is 52 Wednesdays, including
four 5th Wednesdays: 30 Sep 2026, 30 Dec 2026, 31 Mar 2027 and 30 Jun 2027. The
entry was listed on every 2nd and 4th Wednesday and on no 1st, 3rd or 5th.

Separately, `week_of_month()` was compared against a brute-force calendar count
for every day from 2026 to 2035. A multi-weekday entry, "1st and 3rd Tuesday
and Friday", was compared the same way for every day from 2026 to 2030, and it
was also read off the queue as Health Center Staff and as the Doctor.

The checks were shown to be able to fail. With `(day - 1) // 7 + 1` changed to
`day // 7 + 1`, the calendar comparison fails. With the Doctor added to the Add
route's guard, the forged-POST check fails.

## Read-only roles cannot write

Forged POSTs were sent to add, edit and delete an existing row from the
**Doctor**, **Health Center Staff** and **Barangay Official** accounts, one set
carrying `role=Admin` in the body. Every one was redirected to that role's
dashboard by `role_required("Admin")` before the view ran. After each one, the
schedule and the audit log were identical to before. A POST to each role's own
read-only URL returns 405. With `?edit=` and `?delete=` in the URL, the three
roles are still drawn no form and no action URL.

## The schedule restricts nothing

On a Sunday with nothing scheduled, and on a day that lists only one other
service, a walk-in with a fever was checked in and their consultation started.
The Doctor then saved the consultation: the row was written and the queue entry
closed as Completed.

## Route × role matrix

All registered rules were requested for the four roles and anonymous, at
33c3831 (before the task) and at 9d13b7f. The 460 cells from before are
unchanged. The 30 added cells are the six new routes and nothing else. There
were no 5xx responses. POST-only rules were requested only by roles their guard
refuses, so no write view ran.

## Regression suites

Every suite was run at 33c3831 and at 9d13b7f on copies of the same data, and
compared check by check. No check went from pass to fail. Add User's 2 failing
checks fail identically at both commits. They are the real defect recorded in
`stale-suite-assertions/`.

| Suite | Before | After |
| --- | --- | --- |
| Service Schedule (this task) | n/a | 157 / 157 |
| Independent checks (this task, second session) | n/a | 65 / 65 |
| RBAC and restricted diagnosis | 117 / 117 | 117 / 117 |
| Reports and the seal | 61 / 61 | 61 / 61 |
| Dispensing | 128 / 128 | 128 / 128 |
| Doctor role | 129 / 129 | 129 / 129 |
| Account management | 82 / 82 | 82 / 82 |
| My Account | 344 / 344 | 344 / 344 |
| EPI / staff capabilities | 15 / 15, 27 / 27 | 15 / 15, 27 / 27 |
| Add User | 117 passed, 2 failed | 117 passed, 2 failed |

`python app.py` starts without error against the live database. Anonymous GETs
to all three schedule URLs redirect to login. The live database's hash was the
same before and after every test run.

## Not done

**No real-browser pass.** Every rendering claim above comes from the HTML the
application returned, read per role on controlled dates, not from clicking in a
browser. The side panel needs no script to reopen, so nothing tested here
depends on JavaScript. Even so, the screen's layout has not been looked at by a
person.
