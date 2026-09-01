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
