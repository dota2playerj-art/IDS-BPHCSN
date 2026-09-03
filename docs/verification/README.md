# Verification evidence

Screenshots and other artefacts captured while exercising a feature in a real
browser, kept so a later reader — a reviewer, an adviser, or whoever picks the
work up next — can see that something was actually clicked rather than only
reasoned about.

## The images in here are deliberately NOT in version control

`.gitignore` excludes every image under this folder. The folder and this file
are tracked; the pictures are not, and that is a decision rather than an
oversight.

The reason is the one `.gitignore` already gives for `app.db` and its backups:
they hold real patient records, and those do not belong in version control. A
screenshot of the Patient Profile **is** a patient record. The vaccination
correction images below show a full name, a patient ID, an age and sex, a home
address, a contact number, a chief complaint and a clinical vaccination history
— on one screen, in one file, readable by anyone who clones the repository, and
permanent in its history in a way a deleted file is not. That is more
identifying material than a single row of `app.db`, not less. A repository that
refuses to hold the database cannot sensibly hold a picture of the database.

So the evidence lives on the machine that produced it. What is committed is this
file, naming what was captured and how to produce it again, so the absence is
stated rather than left for someone to trip over.

## booking-dialog-gap/

Verification that the Schedule Appointment dialog no longer carries an empty
scrollable region below its last field. The fields were never missing: the hidden
`position:absolute` radios in the patient list had no positioned ancestor of their
own, so they were laid out against Bootstrap's positioned `.modal-body` instead of
inside the list that clips them, and added their whole unclipped length to that
element's scroll height -- 1542px of scroll for 871px of form. `position:relative`
on `.patient-option` fixes both this dialog and Check In Patient. Confirmed in the
browser, including a real appointment booked end to end and the form-redisplay
path re-checked, with the route x role matrix identical across 210 pairs.

## view-icon-removal/

Verification that User Management's View icon and its Actions column are gone —
the icon called the same `selectUser()` the row's own click calls, so it opened a
panel that clicking anywhere else in the row had already opened — and that the
keyboard access the button carried incidentally moved onto the row rather than
being deleted with it. 202 checks, a measured table layout with no trailing gap,
and a live pass in which an account was chosen by Enter and by Space and its Edit
dialog opened from there.

## immunization-next-step/

Verification that every Due and Overdue row on the Immunization Record tab now
says what to do next -- a link to the visit being written up, a link to the queue
that visit has to be started from, or the plain fact that the dose is given at the
child's next consultation -- and that **no way to record a vaccination from that
screen was added**, which is the point of the change rather than an omission from
it. 66 checks over both roles and all three states, plus a live browser pass in
which the consultation was actually started from the queue and the row's link
followed to the right write-up.

## form-redisplay/

Verification that a form which fails validation redisplays **itself**, with the
error beside the field it belongs to and every non-sensitive value still filled
in — checked on every form in the project by submitting genuinely invalid data
to each, not by reading the code.

### What was actually wrong

Add User was reported as redirecting away on a validation failure and losing
both the entry and the error. It was not redirecting: the POST returned 200, the
name, username and role were re-rendered, the error was in the markup, and the
password boxes were correctly cleared. **The dialog just never reopened.**

`base.html` renders `{% block scripts %}` *before* it loads
`bootstrap.bundle.min.js`, so an inline `if (modal && window.bootstrap)` guard is
evaluated while `window.bootstrap` is still undefined. The condition is false,
nothing throws, nothing reaches the console — and the correctly-rendered dialog
stays at `display:none`. From the desk that is indistinguishable from being
thrown back to User Management with everything discarded, which is exactly how
it was reported.

The project had already met this defect once and written it up, on
`patient_profile.html`'s tab-opening script. That note named the cause and the
fix; the fix had simply never been applied anywhere else.

**Four dialogs carried the same bug** — Add User, Book Appointment, Reschedule,
and the SMS compose box (both the Administrator's and the Barangay Official's
route into it). All four are now wrapped in `DOMContentLoaded`, and `base.html`
carries a note at the block itself so the next dialog does not repeat it.

### Every form, with its tested result

Invalid data was POSTed to each. `redisplay` means the form came back at 200
with its own errors; `action post` means nothing is typed into it, so a flash
and a redirect is the correct shape rather than a defect.

| Form | Roles tested | Result |
| --- | --- | --- |
| Add User | Admin | **was broken (dialog never reopened) — fixed** |
| Book Appointment | Admin, Health Staff | **was broken (dialog never reopened) — fixed** |
| Reschedule | Admin | **was broken (dialog never reopened) — fixed** |
| SMS Broadcast (compose) | Admin, Barangay Official | **was broken (dialog never reopened) — fixed** |
| Register Patient | Admin, Health Staff | already correct — redisplay, 10 field errors, values kept |
| Edit Patient | Admin | already correct — redisplay with errors |
| Add/Edit Medicine | Admin, Health Staff | already correct — redisplay, value kept |
| Edit Medicine | Admin | already correct — redisplay with errors |
| Record Consultation | Admin, Health Staff | already correct — redisplay, diagnosis and treatment plan kept |
| Edit Consultation | Admin | already correct — redisplay with errors |
| Correct Vaccination (EPI + general) | Admin, Health Staff | **was the last exception (redirected, edit lost) — fixed: redisplay, values kept** |
| Cancel / No-show | Admin | action post — specific message, nothing typed to lose |
| Appointment SMS | Admin | action post — specific message |
| Deactivate / Reactivate | Admin | action post — specific message |
| Archive Medicine, Archive Patients | Admin | action post — specific message |
| Check In, Start / Complete Consultation | Admin | action post — specific message |
| Login | — | redirects by design; says only "Invalid security credentials." |

Two entries in that table need their reasoning kept, because both look like the
reported bug at first glance and neither is it.

**Record Consultation** first appeared to redirect away. It does not. The probe
was aimed at a `Scheduled` appointment, and the form refuses anything that is not
`In Consultation` — a *state* guard, reached before validation, which answers
with its own clear sentence. Put the queue entry in the state the form is for and
a blank chief complaint redisplays the form with the error and keeps the
diagnosis and treatment plan that were typed alongside it.

**Correct Vaccination** used to genuinely redirect, and it was the one place the
established pattern was not followed. That has now been fixed, closing the last
known exception across the project. It was never the reported defect — the error
was delivered in full and named every problem, so nobody was left guessing — but
the edit itself was thrown away: the dialog reopened pre-filled from the stored
record, not from what was typed. `process_vaccination_correction()` now returns a
third value, a `reopen` state, and on any refusal (a field error, or a duplicate
conflict) both the Administrator's and the Health Staff's route re-render Patient
Profile with the correction dialog open on what was typed, each error beside the
field it belongs to, and nothing flashed — the same shape Add User and Register
Patient use. The vaccine tab is opened underneath, since that is where the record
and the Correct button live. A `DOMContentLoaded` callback shows the dialog, for
the reason `base.html` documents at the scripts block: it is rendered before
Bootstrap loads, so a bare `if (window.bootstrap)` there would be silently false —
exactly the trap `e2616a5` fixed on four other dialogs. The successful and
no-change paths are unchanged: they still flash a sentence and redirect, which is
right for an outcome no retyping fixes.

### The automated suites

- **28 form probes** across three roles, one per form above, each submitting
  genuinely invalid data.
- **5 modal-reopen probes** asserting, on the real rendered response, that the
  reopen call is emitted *and* is inside a `DOMContentLoaded` callback. This is
  the check that would have caught the original defect: the earlier suite
  asserted the reopen call was present in the HTML, which it always was.
- **The Add User suite re-run: 120 checks, 0 failures.** Its five hard-coded
  counts ("exactly three accounts", "zero User Management audit rows") were made
  relative to a baseline captured at the start of the run — they were written
  when the roster could not grow, and the feature they verify is what makes it
  grow, so an absolute count reports ordinary use of the feature as a regression.
- Route × role matrix before and after: **identical, zero drift.**

### The live browser pass

Driven against a scratch copy on a separate port, signed in as the
Administrator. Add User was submitted with **three distinct failures** — a weak
password, a missing required field, and a duplicate username differing only in
capitalisation — and each was confirmed in the live DOM: dialog visible, the
right error text showing, `is-invalid` on the right field, name/username/role
still filled in, and **both password boxes empty**. Book Appointment, Reschedule
and SMS compose were each submitted invalid and confirmed to reopen with their
errors visible. Register Patient was confirmed still correct as the reference
full-page form.

Before the fix, the same submit was observed with the dialog at `display: none`,
`.field-error` elements present in the DOM but with no visible box, and every
typed value sitting in a form nobody could see.

### Reproducing it

1. Copy `app.db` somewhere scratch and point `app.config["DATABASE"]` at it.
2. `python app.py`, sign in as the Administrator, open User Management.
3. Add User → fill it in, give it a five-character password, Create Account.
4. The dialog must come straight back, showing "Too short. A password must be at
   least 12 characters; this one is 5.", with the name, username and role still
   there and both password boxes empty.
5. Repeat with a blank Full Name, and with a username that differs from an
   existing one only in capitals.
6. Do the same on Appointment Scheduling (book with nothing filled in) and on SMS
   Notifications (send an empty broadcast).

## add-user/

Verification of **Add User** — an Administrator creating an account with a
password they set directly, the refusal to deactivate the last remaining active
Administrator, and the Deactivate / Reactivate controls wired to the `is_active`
flag the login route and the per-request session check already enforced.

It retained **no images on purpose**, and for a sharper reason than the passes
below: this screen's subject *is* credentials. A picture of it is a roster of
every way into the system beside a form with a password in it. The whole run went
against a throwaway copy of `app.db`, so creating accounts, revoking them and
signing in as them left nothing in the real database — confirmed afterwards by
SHA-256 over the whole file against
`app.db.PRETASK_BACKUP_add-user_20260902_182924`: **byte-identical**, still three
accounts, still zero `User Management` audit rows.

### The automated suite

**120 checks, all passing.** They cover, in one end-to-end run against a scratch
copy:

- **Creation.** A real Health Center Staff account (`mdelacruz`) created through
  the live POST endpoint, then read back out of the database: role stored in the
  schema's own spelling, active, `email`/`phone` left NULL, the plaintext
  password absent from every column of the row, and the stored hash verifying
  that password under the *same* scheme as the seeded accounts.
- **Every validation rule, one submit each.** Sixteen rejected posts — blank
  fields, a role outside the schema's `CHECK` list, four username rules, five
  password rules, a mismatched confirmation, and a duplicate username in both its
  exact and its differently-capitalised form. After all sixteen: no account
  created, no audit row written.
- **What a rejected submit does with what was typed.** Name, username and role
  come back filled in; the dialog reopens on them; and **neither password is
  written back into the HTML** — asserted by searching the rendered page for the
  submitted value.
- **The new account's own access.** It signs in, reaches a Health Staff screen,
  is refused User Management, and — the check that matters — is refused when it
  POSTs directly to the account-creation and account-status endpoints, with the
  database confirming nothing changed. A role that could reach those could make
  itself an Administrator.
- **The last-Administrator guard, attempted for real.** With one active
  Administrator, a genuine POST to deactivate it is refused; the account is still
  active afterwards and no deactivation entry was written. The guard is then
  shown to *follow* the last Administrator rather than a fixed id: with a second
  Administrator created the first can be deactivated, after which the second
  becomes the one that cannot. It is also called at the model level — no route,
  no session, no template — where `deactivate_user()` returns the same refusal,
  proving the rule protects the table rather than the screen.
- **Deactivate and reactivate.** A non-Administrator account is deactivated, is
  then refused at the login form *with the correct password*, and the refusal is
  audited against it. Reactivating restores the same credential — the stored hash
  is verified untouched across both transitions, and the account signs back in
  with its original password. Repeating either action is answered "no change".
- **Malformed and forged posts** — unknown action, non-numeric id, id that does
  not exist — each refused with its own sentence rather than a traceback.
- **The audit trail.** Every creation, deactivation and reactivation writes an
  entry under the new `User Management` module, attributed to the acting
  administrator, naming both the account and the administrator in `details`, and
  reporting how many Administrators can still sign in. **The password appears in
  none of them** — asserted against the entry, against the whole `audit_logs`
  table, and against the rendered Audit Logs screen.
- **No regressions.** A wrong password and an unknown username are still refused
  and still audited exactly as before; the Barangay Official still reaches its own
  dashboard and is still refused both other surfaces; the roster and audit exports
  still build. A sweep rendering every GET route across all three roles returned
  **no 5xx**.

The route × role matrix was snapshotted before and after: the diff is exactly the
two new `Admin`-only POST rules and nothing else, with the other 88 unchanged.

### One case the suite asserts against the database rather than the screen

An Administrator may deactivate **their own** account whenever another
Administrator remains. The flash message that act produces is never displayed,
and that is correct rather than a defect: the redirect lands on User Management,
whose guard runs the per-request deactivation check, which calls
`session.clear()` — and the flash queue lives in the session. The holder arrives
at the login form, which says only "Invalid security credentials." because
`utils/security.py` deliberately reveals nothing there about an account's status.

So the outcome is verified where it is actually recorded — the flag in the
database, the deactivation entry, and the session-revocation entry — and the
operator is not left uninformed, because the confirmation dialog warns them
before they confirm. That warning's presence is itself one of the checks.

### Reproducing it

1. Copy `app.db` somewhere scratch and point `app.config["DATABASE"]` at the
   copy. Do not run this against the real database: it creates accounts and
   writes audit rows, and both persist.
2. `python app.py`, sign in as the Administrator, open User Management.
3. Add User, and try the rules against it — a short password, one containing the
   username, `staff` and then `STAFF` as the username.
4. Create a real account, sign out, and sign in as it. Confirm it reaches the
   Health Staff screens and not User Management.
5. Back as the Administrator, confirm the sole Administrator's Deactivate button
   is disabled and says why. Deactivate the new account, try to sign in as it,
   then reactivate it and sign in again with the same password.
6. Read the Audit Logs screen filtered to **User Management**.

## pat029-settings-honesty/

Verification of the removal of a fake patient — `PAT-029` "JOhn asc asdas" — and
the appointment it had Scheduled for the following day, together with the last of
the invented figures on Settings.

Like the pass below, it retained **no images on purpose**: the whole run was
driven against a throwaway copy of `app.db`, so signing in three times and
rendering every screen left nothing in the real database. The live sign-in count
is unchanged by this work.

What that folder records instead is the evidence that is checkable rather than
photographable: an independent column-by-column diff of the pre-task backup
against the live file showing **3 differing rows in the whole database** and
naming all three, both of the migration's refusal paths exercised on scratch
copies, and a 49-check suite covering the route sweep, every retired string
asserted absent from the rendered HTML, every replacement asserted present, and
the two places `PAT-029` is still allowed to appear — asserted by name rather
than skipped.

## appointment-sms/

Verification of the individual appointment SMS confirmation — one text to one
patient about their own booking, sent by hand after it is made, moved or called
off.

**No images were retained from this pass, and that is deliberate.** The whole run
was driven against a *throwaway copy* of `app.db` rather than the real one, so
that click-testing a feature that writes messages and audit entries left no test
residue in the patient database. A screenshot of that session shows the same real
patient name, contact number and appointment a screenshot of the live system
would, so it would be excluded from git for the reason above either way — and the
copy it came from no longer exists. What survives instead is the reproduction
recipe below and the automated suite, which is the more checkable half.

### What was exercised in a real browser

Signed in as **Health Center Staff** and then as the **Administrator**, against
the app served from a scratch database copy. The role column says which account
actually produced each state in the browser; the automated suite below then
covers every state under *both* roles.

| Role | State | What it showed |
| --- | --- | --- |
| Staff | New booking, patient with a mobile | The teal offer panel under the flash: the exact 137-character message, "1 GSM-7 segment", the simulated-mode note, and a live **Send SMS Confirmation** button. |
| Staff | After pressing Send | `APT-SMS-2026-0001 — new appointment message to Grace Ilagan on 09171000777. SIMULATED SEND — …`, and the offer gone from the next render. |
| Staff | New booking, patient with **no** mobile | A plain dashed grey block: "New appointment — no SMS can be sent … Add a mobile number through Edit Profile on their patient record. The appointment itself is saved and is unaffected." **No button, no form, no disabled control** — nothing clickable at all. |
| Admin | Reschedule | Same panel, labelled "Appointment moved", button **Send SMS Notice of Change**, message stating the new date and time. |
| Admin | Cancellation | Same panel, labelled "Appointment cancelled", button **Send SMS Cancellation Notice**. |
| Admin | SMS Notifications (Screen 09) | The new **Individual appointment messages** panel listing all three sends with their references, the patient, the event, the sender and a Simulated flag — beneath the community broadcast history, which was unchanged. |

The **Barangay Official** was not driven through the browser: that account's
sign-in would not take through the automation being used, and rather than report
a click-through that did not happen, its one claim — that the individual-message
panel is absent for that role while the broadcast history stays — was checked
against the same running application and the same database through its own login
route. It is also the last check in the automated suite below.

### Reproducing it

1. Copy `app.db` somewhere scratch and point a throwaway launcher at it, so the
   run writes nothing to the real database:

   ```python
   import app as m
   m.app.config["DATABASE"] = r"C:/path/to/scratch/app.db"
   m.app.run(port=5055)
   ```

   Running `python app.py` instead works exactly the same way — it simply leaves
   the messages and audit entries in the real database.
2. Sign in, open **Appointment Scheduling**, and book a future visit for a
   patient who has a mobile number (PAT-007 has one). The offer appears above the
   page title, under the flash.
3. Press Send, then repeat for **Reschedule** and **Cancel** on the same booking.
4. Book one more for a patient with no number on file — PAT-016, PAT-017, PAT-021
   and PAT-022 all have an empty `contact_number` — and confirm the block that
   appears carries no control of any kind.
5. Repeat signed in as the other role.

Every send writes an `appointment_sms_messages` row and an `audit_logs` entry
under **SMS Notifications**, so the Audit Logs screen and that table are the
other half of this evidence — and that half *is* in the database rather than in a
picture.

### The automated suite

Run alongside the browser pass, also against a scratch copy: 85 checks over both
roles and all three events, covering the recorded row, the composed text, the
audit entry, the no-number state's markup, forged posts, event/status mismatches,
role isolation, and a broadcast send proving Screen 09's community half is
untouched. All 85 passed, as did a sweep rendering all 183 GET routes across the
three roles with no 5xx.

## vaccination-correction/

Real-browser verification of the vaccination correction path (`e7416d8`), run
against the real `app.db` after the feature had already been verified at the
code and database level. Four corrections were made through the UI — both record
types, under both roles that hold the capability.

| File | What it shows |
| --- | --- |
| `admin-epi-dialog-prefilled.jpg` | Administrator, PAT-022. The Correct dialog open on the recorded BCG dose, pre-filled with its stored vaccine and date. |
| `admin-epi-after-correction.jpg` | The same record after submitting: dialog closed, flash message, Immunization Record tab showing the corrected date. |
| `admin-general-dialog-prefilled.jpg` | Administrator, PAT-007. The same dialog on a general vaccination — the free-text vaccine name and dose number in place of the EPI schedule list. |
| `admin-general-after-correction.jpg` | The dose number correction applied and confirmed on screen. |
| `staff-epi-dialog-prefilled.jpg` | Health Center Staff, PAT-022, on the recorded Hepatitis B dose. The form posts to the Staff endpoint, not the Administrator's. |
| `staff-epi-after-correction.jpg` | The date correction applied. |
| `staff-general-dialog-prefilled.jpg` | Health Center Staff, PAT-007, showing the Administrator's earlier correction already on the record. |
| `staff-general-edited-before-submit.jpg` | Two fields edited but not yet submitted — the state a confirmation dialog exists to give someone a last look at. |
| `staff-general-after-correction.jpg` | Both fields corrected, the flash naming both. |
| `staff-general-after-reload.jpg` | The same record after a full page reload, proving the change persisted rather than only rendering once. |

Two further frames were captured and discarded: one caught the modal backdrop
mid-animation and one was a compositor artefact that made an opaque dialog look
washed out. Neither documents anything — the dialog's computed opacity was
checked in the live DOM at the time and was correct.

### Reproducing them

1. `python app.py`, then sign in as the Administrator.
2. Open a patient with a recorded vaccination — PAT-022 has EPI doses, PAT-007
   has a general vaccination — and go to the Immunization Record tab.
3. Click the pencil in the Actions column of a recorded row. Only recorded rows
   have one; a dose that is merely Due or Upcoming is not a record yet.
4. Change a value and Save Correction, then reload.
5. Repeat signed in as Health Center Staff.

Every correction writes an `audit_logs` entry under **Immunization Records**
naming the acting account and both values, so the Audit Logs screen is the other
half of this evidence — and that half *is* in the database rather than in a
picture.

### The redisplay pass (last exception fixed)

A later pass verified that a *refused* correction now reopens the dialog with the
edit kept, rather than redirecting and losing it (the change described under
form-redisplay above). Run against the real `app.db`, then restored from a
pre-task backup so nothing typed during the pass survived.

Automated first: 57 checks POSTing genuinely invalid data — a future date, an
off-schedule EPI pair, an out-of-range dose, a blank vaccine name — to both the
EPI and the general path, under both Admin and Health Staff, asserting on the
rendered response that the page returns 200 (not a redirect), the `DOMContentLoaded`
modal-show is emitted, each typed value comes back, the right field carries
`is-invalid`, the banner counts the right number of fields, and no row or audit
entry was written. Then 5 more for the success, no-change and duplicate-conflict
outcomes. All passed.

Then live in the browser, all four role × path cells: an invalid submit reopened
the dialog over the Immunization Record tab, the red "This correction was not
saved" banner at the top, the offending field boxed in red with its message, and
what was typed still in place — the future date on the EPI path, the blank
vaccine name and preserved dose on the general path. A valid submit in the same
session saved, closed the dialog, and redirected with the audit-log flash,
confirming the success path is unchanged. Screenshots were captured but, like the
rest of this folder, are not committed — they are full Patient Profile screens.
