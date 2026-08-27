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
