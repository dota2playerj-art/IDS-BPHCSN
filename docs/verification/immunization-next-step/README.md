# Immunization Record — what to do about a Due/Overdue dose

Verification of the guidance added to the Due and Overdue rows on Patient
Profile's Immunization Record tab, and of the fact that **no way to record a
vaccination from that screen was added**.

Like the passes beside it, this folder retains **no images on purpose**: a
screenshot of the Immunization Record tab is a full patient record — name,
patient ID, age, sex, address, contact number and clinical vaccination history on
one screen. The browser pass below was driven against a *throwaway copy* of
`app.db` on port 5055, and the copy no longer exists. The real database was
SHA-256'd before and after the whole task against
`app.db.PRETASK_BACKUP_immunization-guidance_20260904_000238`: **byte-identical**.

## What was actually wrong, and what was deliberately left alone

A dose that is merely Due or Overdue had a blank Actions cell — a bare em dash.
That is not a missing feature, and the fix is not a button. A Due row is not a
record; it is the schedule saying a dose has not happened yet, and a vaccination
is only ever recorded during the visit it was given in, on the consultation form,
against a real queue entry. HL7 FHIR draws the same line between what was
administered and what is recommended. Offering "mark as given" from a static
profile screen with no visit behind it would invent a clinical event.

**So no such control was added, and the suite asserts its absence.** What the
blank cell lacked was not an action but an answer: staff were told a dose was four
weeks overdue and then told nothing about what to do. The cell now carries the
next step, and the step depends on where the child actually is.

| Where the child is right now | What the row shows | Where it goes |
| --- | --- | --- |
| **In Consultation** | `Record now →` | `…/consultation/record/<that appointment id>` — the write-up for *that* visit |
| **Waiting** in today's queue | `In today's queue →` | Appointment Scheduling, where the consultation is started |
| Not in today's queue | `At next visit` (plain text, with a tooltip) | nothing — no link could honestly point at a visit that is not happening |

The Waiting case does **not** link straight to Record Consultation, and that is
deliberate. `record_consultation_context()` refuses any queue entry that is not
`In Consultation` — a state guard that predates this work and is correct — so a
link there would hand over an error message instead of a screen. The queue is the
real next action, so the queue is where the link goes.

The banner above the table had the same problem in a smaller way: it read
"Record these during the child's next consultation" on *every* render, including
the one render where it matters most. If the child is with a clinician now, the
next consultation is this one. It now names the actual state and carries the same
link.

## Task 1 — the real patient

**Darwin Umali Manalastas, PAT-025**, born 1 June 2026, three months old on the day
of the pass (4 September 2026).

- **4 overdue** (BCG, Pentavalent 1, OPV 1, PCV 1) and **3 due now**
  (Pentavalent 2, OPV 2, PCV 2). One dose on file: Hepatitis B, given 20 August
  2026.
- **He is not currently at the health center.** No appointment for today at all;
  his rows are a Completed walk-in on 27 August, a Completed walk-in on 22 August,
  and a stale Scheduled booking dated 23 August. Nobody in the whole database was
  `Waiting` or `In Consultation` at the time of the pass.

So for him the honest answer is the general pointer, and a "quick link to their
current visit" would have had nothing to point at. That is the case the browser
pass confirms first, and the reason the "not here" state was built as the default
rather than as an edge case.

## The automated suite — 66 checks, 0 failures

Against a scratch copy, under **both** Admin and Health Center Staff, on the real
rendered HTML:

- **Case A — not checked in.** Both roles: all 7 outstanding rows carry
  `At next visit`, none is a bare dash, the tooltip explains why, the banner says
  he is not in today's queue, and **no consultation-record URL appears anywhere on
  the page**.
- **Case B — Waiting.** A queue entry is created for today. Both roles: all 7 rows
  link to *that role's own* Appointment Scheduling URL, the banner names the
  Waiting state, and the page still contains **no** `/consultation/record/` link.
  The queue URL is then fetched under each role: 200, with the patient on it.
- **Case C — In Consultation.** The same entry is advanced. Both roles: all 7 rows
  link to `/consultation/record/<appt>` with the *right* appointment id — asserted
  by a negative regex that no other id is linked — the banner offers **Open Record
  Consultation**, and following the link returns 200 on the real consultation
  form. Opening it wrote no immunization row.
- **Case D.** A patient with nothing outstanding gets none of the three strings.
- **Case E — roles.** Staff is refused the Administrator profile route and vice
  versa, a signed-out request is refused, and a wrong password is still refused.
- **In every case**, the outstanding rows carry no Correct button and the page
  carries no "mark given" control; the one Completed dose keeps its Correct
  pencil, unchanged.
- **No residue**: the immunization table is the same size at the end as at the
  start.

## The regression sweep

- **All 29 patients × 2 roles**: every Patient Profile renders 200.
- **Guidance agrees with the schedule for every patient**: the note appears
  exactly when `attention_count > 0`, and appears **exactly `attention_count`
  times** — never on a patient with nothing outstanding, never one row short.
- **186 GET renders across all three roles: no 5xx.**
- **Route × role matrix before and after: identical, zero drift.** No route was
  added; the links reuse `record_consultation_endpoint` and
  `appointment_scheduling_endpoint`, which `utils/context.py` already hands to
  exactly the two roles that have a Patient Profile.
- `python app.py` starts clean.

## The live browser pass

Administrator, against the scratch copy on port 5055.

1. **Not checked in.** Darwin's Immunization Record tab showed `At next visit` on
   all seven Overdue/Due Now rows, the Completed Hepatitis B row keeping its
   Correct pencil, and the red banner ending "Darwin is not in today's queue. These
   doses are recorded during a consultation…". Read out of the live DOM, not from
   the source.
2. **Checked in, Waiting.** A queue entry was created for today. The same rows
   became `In today's queue →` pointing at `/admin/appointment_scheduling`, with
   the tooltip "…Start the consultation from the queue, then record the dose on
   the consultation form."
3. **In Consultation.** **Start Consultation was pressed on the real queue screen**
   — not set in SQL — and the appointment moved to `In Consultation`. The rows
   became `Record now →` pointing at `/admin/consultation/record/80`, and
   **clicking one landed on Record Consultation for appointment 80, for Darwin**.

Both required cases — currently checked in, and not currently checked in — were
therefore exercised live as well as in the suite.

### Reproducing it

1. Copy `app.db` somewhere scratch and point `app.config["DATABASE"]` at the copy.
2. `python app.py`, sign in, open PAT-025 → Immunization Record. Every Overdue and
   Due Now row reads `At next visit`.
3. Check the child in from Appointment Scheduling and reload the profile: the rows
   become `In today's queue`.
4. Press **Start Consultation** on the queue and reload: the rows become
   `Record now` and link to that visit's write-up.
5. At no point does any row offer a way to mark a dose given.
