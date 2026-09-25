# Clearing the pre-existing suite failures (2026-09-25)

The Doctor-role work (0f33500, 849a586, fe6aaee) reported suite failures that were
there **before** it began: 17 in the dispensing suite, plus checks in three other
suites. This pass took each failing check in turn and asked one question: is the
**test** out of date, or is the **application** wrong?

- **Stale assertion.** The application is right. The test quotes wording, a
  persona, a date or a count that was later changed on purpose. The test was
  updated to check the same property against what the application now says.
- **Real defect.** The test is right. It is reported below and **not fixed**, so
  the team can decide what to do.

No check was deleted or loosened to make it pass. Where the new wording made a
check pass without testing anything (one did), it was corrected until it tests
something again.

The suites are not in this repository, and deliberately so. Verification scripts
are kept outside the project (see `.gitignore`). They run on throwaway copies of
`app.db` in git worktrees, never on the live database. This file records what
changed in them and why.

## Result

| Suite | Before | After |
| --- | --- | --- |
| Dispensing (e04a0beb, Doctor as clinician) | 111 / 128 | **128 / 128** |
| Account management, Edit User / Reset Password (7b0d7b4d) | 81 / 82 | **82 / 82** |
| My Account (39d11d59) | 335 passed, 3 failed | **344 / 344** |
| Add User / Deactivate / Reactivate (033c26b6) | 108 passed, 11 failed | 117 passed, **2 failed: the real defect below** |

Every other suite matches its baseline check for check: RBAC and restricted
diagnosis 117/117, Reports and the seal 61/61, EPI 15/15, staff capabilities
27/27, the dose-given-elsewhere runs, the password-change audit check, and the
Doctor-role suite 129/129.

## Stale assertions: 30 failing checks, all corrected

17 in dispensing, 9 in Add User, 3 in My Account (one per role), 1 in account
management.

### Dispensing: 17 failures, 11 distinct checks, one cause plus one date

**Cause: 5747d94**, *Record the supplies and equipment a visit uses*. When gauze
and masks became dispensable, the section stopped saying "medicine" on purpose,
so a pack of gauze would not sit under a heading that says medicines. The suite
was written before that commit.

| The suite expected | The application says (on purpose) | Same property? |
| --- | --- | --- |
| `id="addMedicineLine"` (3 checks: present, `type="button"`, `hidden`) | `id="addItemLine"`, still `type="button"`, still `hidden` | Yes, all three hold |
| `Medicine on line 6` (expired stock blames the medicine) | `Item on line 6` | Yes |
| `6 medicines dispensed`, `10 …`, `1 medicine dispensed` | `6 items dispensed`, `10 …`, `1 item dispensed` | Yes |
| helper note: `Medicine History on` | `Dispensing History on` (the profile tab was renamed) | Yes |
| helper note: `One line per medicine with the whole amount given` | `One line per item …` | Yes |
| helper note: `the medicine has expired` | `the item has expired` | Yes |
| edit refusal: `Medicine on line 2` | `Item on line 2` | Yes |

**One check had been passing vacuously.** "It blames the quantity, not the
medicine" asserted that `Medicine on line 5` was *absent*. After the rename that
string cannot appear at all, so the check passed whatever the page said. It now
asserts that `Item on line 5` is absent, and it tests something again.

**The date.** "The vaccination note still dates the doses" looked for the literal
`Aug 28, 2026`, the day the suite was written. A new consultation is dated
`today()`, so the check now looks for today's date, formatted by the same
`display_date` filter the template uses.

### Add User: 9 of the 11 failures

- **Literal counts.** The suite asserted exactly 3 accounts, "the roster now
  counts four", no User Management audit entry ever, and no deactivation entry
  ever. Since then the database has gained real accounts (`bhwmanalastas`, then
  `doctor`) and real account-management entries. Each check now compares against
  a baseline recorded at the start of the run. A probe confirmed that rejected
  submits add **zero** audit rows. The first check now asserts what the suite
  relies on: the seeded `admin`, `staff` and `official` accounts exist, with
  their roles.
- **"The real database still holds exactly three accounts" / "gained no
  account-management audit rows."** These are meant to prove the run did not
  touch the real database. They now compare that database with itself before the
  run, instead of with the literals 3 and 0.
- **Persona (2 checks).** The audit entries were expected to name "Dr. Joshua
  Reyes". **f7e2607** corrected the Administrator's persona to Kagawad Antonio
  Acido. The checks now read the acting account's name from the database.
- **Password wording.** Expected `at least 3 of these four`. **65e0d7c** builds
  the sentence from `PASSWORD_CHARACTER_KINDS` and says `Use at least 3 of these
  4:`. The password `allsmallletters` is still refused under that rule.

### My Account: 3 failures, one per role

The suite asserted that **no** refusal writes an audit row. **ef47b94**, *Record a
refused own-password change*, deliberately made one refusal auditable: a wrong
current password on My Account now writes a "Refused own-password change attempt"
row, built from the stored account row and never from what was typed.

The replacement is stricter than the original. The refusal sequence contains two
wrong-current-password submits. The suite now asserts:

- exactly two rows appear, both that action;
- both are attributed to the signed-in account, under Authentication;
- none of the nine values typed during the run appears in either row.

### Account management (Edit User / Reset Password): 1 failure

"Audit names the acting administrator" expected "Dr. Joshua Reyes", which was
**f7e2607** again. The same literal was also used as the value the suite wrote
back when it "put the name back", so each run renamed the scratch database's
Administrator to the retired persona. The suite now reads the name once from the
database and uses it in both places.

### Doctor-role suite: 1 check, changed by 445554e, not pre-existing

`accessible_screens(Doctor) == accessible_screens(Health Center Staff)` stopped
holding when the Doctor was granted Reports & Analytics. That is the change
itself. It now asserts the Doctor's list is Health Center Staff's plus exactly
the three labels Screen 10 carries for the other roles (the page and its two
exports), and nothing more.

### Retired: three pre-port originals

`verify_rbac`, `verify_reports` and `verify_dispense` in their original form used
the Administrator as the clinician. The Doctor-role work ported all three to the
Doctor, and the ported copies replace them. The originals are kept, but no
longer run.

## Real defect: 2 checks, reported, not fixed

**An Administrator who deactivates their own account is never told they did so.
They are sent to the login page with "Invalid security credentials."**

Severity: **low.** The deactivation works: the account is switched off, the
session ends, the audit trail records both. No data is at risk and nothing is
exposed. What is wrong is what the person is told, and it happens only when two
or more Administrators exist and one deactivates itself.

What happens. `admin.set_user_status()` flashes the result and redirects to User
Management. `process_account_status()` composes the right message for this case:
"…You deactivated your own account, so you will be signed out on your next action
and will not be able to sign back in." But the redirect *is* the next action. The
guard added in **63f6962** sees an inactive account on that GET and clears the
session, which discards the flash with it. It then sends the person to
`/login?error=Invalid security credentials.`, the sentence a wrong password
produces. Someone who just made a deliberate, irreversible change to their own
access is told something that reads as a typing mistake, and the message written
for exactly this moment is never shown.

It has **never** worked. Run at its own commit (3494e7e), over the database as it
stood before that commit, the add-user suite passes 117 of 119. These are the
two failures. So it is not a regression, and the suite has been correct about it
from the start.

The decision for the team. The generic "Invalid security credentials." is
deliberate for anyone *else* whose session is revoked (63f6962: "Nowhere in the
application says an account has been deactivated"). The account holder who
switched themselves off is the one person that rule does not need to protect
from. Two ways to close it:

- clear the session in `set_user_status()` when the acting account deactivated
  itself, then redirect to the login page with a notice meant for that case; or
- decide the generic sentence is acceptable, and delete the message that can
  never be shown.

Until the team decides, the two checks stay as they are and keep failing.

## How to reproduce

The runner and the corrected suites are in the session scratchpad that did this
work (`…/claude/C--IDS-BPHCSN/4f281146-…/scratchpad/`: `run_suites.py`,
`suites/`, `doc_now/verify_doctor.py`). Each suite runs in a git worktree over a
fresh copy of a pristine database, and the live `app.db` is never opened for
writing. Each correction is marked `STALE-FIX` in the suite with the commit that
made the old assertion stale.
