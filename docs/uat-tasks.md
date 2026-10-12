# User acceptance tasks (evaluation form, Part B)

The 18 tasks and expected results of Part B of the team's evaluation form, used in the user
evaluation of October 12, 2026 (Chapter 4, Table 4.5). The form itself was made outside this
repository; this file keeps its task list for later reference. The facilitator marked each task
Passed or Failed. In the October 12, 2026 evaluation every task was marked Passed.

## Part B1 — Health Center Staff account

| ID | Task | Expected result |
|---|---|---|
| UAT-01 | Sign in and set your own password | You are signed in, and your new password is saved |
| UAT-02 | Register a new (fictional) patient | The patient is saved and gets a patient ID |
| UAT-03 | Check in a patient for a service (for example, Consultation) | The patient appears in today's Patient Queue as Waiting |
| UAT-04 | Start the visit and record the intake (vital signs and chief complaint) | The intake is saved, and the visit moves to Waiting for the Doctor |
| UAT-05 | Refer a patient to the RHU and print the referral slip | The visit shows Referred, and the slip prints with the patient's details |
| UAT-06 | Mark a patient as Left before being seen | The visit shows Left before being seen |
| UAT-07 | For a baby in the demo data, give a vaccine dose that is due | The dose is saved and shows as given |
| UAT-08 | Try to give a vaccine dose that is not yet due | The dose cannot be selected, and the earliest date is shown |
| UAT-09 | Record a dose given elsewhere, using a vaccination card | The dose shows as Given elsewhere |
| UAT-10 | Receive a new medicine delivery with its lot number and expiry date | A new batch is added, and the stock goes up |
| UAT-11 | Give (dispense) a medicine to a patient | The stock goes down, starting with the batch that expires first |
| UAT-12 | Open the system on a mobile phone and view the Patient Queue | The page fits the phone screen and is easy to use |

## Part B2 — Barangay Official account

| ID | Task | Expected result |
|---|---|---|
| UAT-13 | Sign in and set your own password | You are signed in, and your new password is saved |
| UAT-14 | View the dashboard | Summary figures for the health center are shown |
| UAT-15 | Open Reports for the last 12 months and export it to PDF | The report appears and the PDF downloads |
| UAT-16 | Send an SMS health alert to residents | The message is saved and shows in the SMS history (SMS mode was Simulated) |
| UAT-17 | View the Service Schedule | The services and their days are shown |
| UAT-18 | Check that patients' diagnoses and treatments cannot be seen from this account | No clinical details are shown anywhere |
