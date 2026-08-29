# helper-text-batch1/

Verification of Batch 1 of the helper-text rewrite — Record Consultation and
Patient Profile, the two screens the team noticed the problem on. Eleven notes
were rewritten or trimmed. Nothing else on either screen was touched: no layout,
no field, no route, no logic.

No images are committed — see the note in the parent README for why a screenshot
of a Patient Profile is a patient record.

## What the change is

Six notes on Record Consultation and five on Patient Profile stated a rule and
then argued for it. The arguments are gone; every rule they carried is still on
the screen. Where a reason is genuinely worth keeping — why height stops at five
years, why a dose on file cannot be unticked — it moved into a Jinja comment
beside the markup, which is where someone asking *why* is looking.

## How it was checked

Three passes, all against a **scratch copy** of `app.db`. The real database was
not written to by any of them.

### 1. Fact-by-fact, on the rendered page, under both roles

Ninety-seven assertions, run under Administrator and Health Center Staff. Every
"must survive" fact from the audit is a separate assertion against the rendered
text of the real screen — not against the template source, and not inferred from
the note simply being shorter. Each rewritten note also carries a negative
assertion that its old reasoning is gone.

Two branches needed setting up rather than finding:

- **Add mode on a pediatric patient.** PAT-023 is the only patient young enough
  for the growth and immunisation sections who also has a stored condition, so
  one page renders the conditions banner, the growth note and the immunisation
  note together. Both of their appointments are Completed, so the scratch copy
  got one extra appointment at In Consultation.
- **The nothing-dispensable empty state.** Reachable only when no medicine on
  the shelf is active, unexpired and in stock at once. Rendered for real by
  making the shelf query return nothing for one request, rather than by retiring
  every medicine in the inventory.

Result: **97 / 97**.

### 2. Route × role matrix, before and after

86 routes and 81 guarded route definitions were snapshotted before the first
edit and compared after the last. **Identical** — no route added, removed,
renamed or re-guarded, which is what a text-only change should look like.

### 3. Every GET route, under all three roles, before and after

183 (role, route) pairs were rendered on both sides of the change and the
outputs diffed. Each line carries the status code and the length of the rendered
text with whitespace collapsed, so a route that stopped rendering, started
redirecting, or lost a block shows up as a changed line.

**Two lines differed, and both were expected:**

| Route | Before | After |
| --- | --- | --- |
| `/admin/consultation/edit/<id>` | 200, 7836 chars | 200, 7329 chars |
| `/admin/patient_profile/<id>` | 200, 8111 chars | 200, 7990 chars |

Every other route came back byte-identical in length. The two that changed are
the two screens edited, both still 200, both shorter by roughly the number of
characters removed.

There is no committed automated suite in this project to regress against — the
128-check suite named in `medicine-lines/` was a working artefact of that session
and was never added to the repository. Pass 3 is the closest standing equivalent
and is what "no regressions" means here.

## Reproducing it

1. `python app.py` — confirm clean startup and that `/login` serves 200.
2. Sign in as Administrator, open a consultation for a patient under one year
   who has a condition on file (PAT-023), and read the four notes on it: the
   conditions banner, the Growth Measurements subheading and note, and the
   Immunizations Given Today note.
3. Open that patient's saved consultation from their profile's Consultation
   History. The immunisation note gains one extra line in edit mode — that a
   missed dose can still be added, and that additions are audit-logged.
4. Open a patient with dispensing history (PAT-016) and one with a general
   vaccination (PAT-008), and read the Medicine History and Other Vaccinations
   footers.
5. Open the Correct Vaccination dialog from a recorded row and read its three
   field hints.
6. Repeat signed in as Health Center Staff.

## One side effect, stated rather than tidied away

`app.db` gained 11 rows in `audit_logs` during this work — sign-ins and refused
sign-ins from the verification runs, including four refusals from a first attempt
that used the wrong demo passwords. They are an accurate record of what happened
at the login form and were left in place; deleting audit rows to make a working
session look tidier is the opposite of what that table is for. Nothing else in
the database changed: no patient, consultation, appointment, immunisation or
inventory row was touched, before or after.

`app.db.PRETASK_BACKUP_helpertext-batch1_20260829_101803` is the pre-task copy.
