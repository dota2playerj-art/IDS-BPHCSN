# Recording a dose as previously given elsewhere

Verification of the change that lets a health worker record an EPI dose the
child received **somewhere else** — another hospital, another barangay — without
this health center claiming to have given it.

## The finding this closes

From capstone adviser testing. An infant showed **Overdue** for EPI doses the
child had already received elsewhere. Staff had no way to record that. The only
way to stop the Overdue reading was to tick "given today", which would have filed
another facility's vaccination as this health center's own work, on today's date,
under the name of a health worker who never gave it — three untruths to silence
one false alarm. So the schedule went on calling a vaccinated child a defaulter,
the follow-up list went on chasing them, and the coverage figures went on
counting a protected child as unprotected.

## What was checked, and against what

The exact scenario, on a real infant record:

**Darwin Umali Manalastas (PAT-025), born 1 June 2026, three months old.**
Before: `1 of 14 scheduled doses given · 4 overdue · 3 due now`, and a red
**7 OVERDUE** badge on his queue row. The four overdue were BCG, Pentavalent
dose 1, OPV dose 1 and PCV dose 1 — three of which he had actually had.

The visit was driven through the real screens in Chrome, signed in as **Jennifer
Ramos, Health Center Staff**: Check In Patient → Start Consultation → Record
Consultation → tick three doses in the new **Previously given elsewhere** column
→ Save & Complete Visit.

| Dose | Recorded as | Date entered |
| --- | --- | --- |
| BCG | previously given elsewhere | 2 Jun 2026 |
| Pentavalent dose 1 | previously given elsewhere | 20 Jul 2026 |
| OPV dose 1 | previously given elsewhere | **left blank — mother did not remember the day** |
| PCV dose 1 | *nothing* — he genuinely has not had it | — |

After: `4 of 14 scheduled doses given · 3 reported as given elsewhere · 1 overdue
· 3 due now`. The false Overdue is gone; the one **real** Overdue (PCV dose 1)
remains, which is the whole test — the change must not silence a genuine alarm.

Verified against the database directly:

```
id 18  BCG    dose 1  source=reported  date_administered=2026-06-02  consultation_id=55
id 19  PENTA  dose 1  source=reported  date_administered=2026-07-20  consultation_id=55
id 20  OPV    dose 1  source=reported  date_administered=NULL        consultation_id=55
id  3  HEPB   dose 1  source=administered  date_administered=2026-08-20
```

Every one carries the consultation it was learned at. The undated row is the
honesty rule holding: nothing invented a date to fill the column.

## Where it is visibly distinguished

Confirmed rendering in the browser, not only in the markup, as **Admin** and as
**Health Center Staff**:

* **Patient Profile → Immunization Record.** Three separate cells say it, on
  purpose. Date Given prints *Date not known* in italics where there is none;
  Administered By prints **Not given here** with *Recorded by Jennifer Ramos*
  underneath, refusing to name anyone as having administered it; Status carries
  **Completed** with **Reported — elsewhere** beneath it. The on-site Hepatitis B
  dose on the same table reads `Aug 20, 2026 · Jennifer Ramos · Completed` with
  no badge — the two are unmistakable side by side.
* **Immunization Record summary line.** `4 of 14 scheduled doses given · 3
  reported as given elsewhere · 1 overdue · 3 due now`.
* **Consultation History panel.** The heading changed from "Immunizations Given
  at This Visit" to **Recorded** at this visit, because a reported dose belongs
  to the visit but was not given at it. Each row then says which it is, with a
  different icon.
* **Record / Edit Consultation.** A dose already reported is locked like any
  other dose on file, with a `history` icon and the tooltip *"Reported — given
  elsewhere (date not known) — a dose on file cannot be removed from this form"*.
* **Correct Vaccination dialog.** On a reported dose the date field becomes
  **Date given (optional)** and explains why; on an administered dose it stays
  required, and clearing it is refused. The subject line names the provenance.
* **Flash message.** *"3 doses recorded as previously given elsewhere: BCG
  (Jun 02, 2026), Pentavalent dose 1 (Jul 20, 2026), OPV dose 1 (date not known).
  Still PCV dose 1 (overdue)…"*
* **Audit trail.** A separate phrase of its own — *"Doses recorded as previously
  given elsewhere: MR (Aug 15, 2026)"* — never folded into "Immunisations added",
  because the audit trail is the one record that cannot later be put right.
* **Barangay Official reports.** Vaccination Campaigns: *"20 Immunization Doses
  Recorded · 17 given here · 3 reported as given elsewhere"*, plus a new **Of
  Which Reported** column on the dose-by-dose coverage table. Community Reports:
  *"17 Immunization Doses Given Here … plus 2 dated in this range but reported as
  given elsewhere"* — 2 not 3, because the undated dose falls in no range, which
  is correct. Official Dashboard and Health Programs carry the same split, and so
  do the PDF and Excel exports.

## What is refused

Every one of these was exercised, through the model and through the real
endpoint, and each left the database untouched:

| Attempt | Result |
| --- | --- |
| one dose ticked in **both** columns | refused, naming the dose — never silently resolved |
| a date in the future | refused |
| a date **after** the visit recording it | refused — "previously given" means before this encounter |
| a date before the child was born | refused |
| a date that is not a date | refused |
| a date typed with the tick box left unticked | refused — the save would otherwise discard it |
| a dose the DOH schedule does not list | dropped by the same gate the "given today" boxes use |
| clearing the date on an **administered** dose | refused, by the dialog and by the table CHECK |
| an undated **reported** dose | **accepted** — this is the point |

The mutual exclusion between the two columns is enforced on the server
(`parse_reported_doses`). The page script is a convenience only, and was checked
separately: ticking one column unticks the other and clears its date box.

## Both roles

Recording a dose as given elsewhere is intake, not diagnosis, so it stays open to
Health Center Staff under the diagnosis restriction. Verified end to end as both
**Admin** and **Health Center Staff**; the Patient Profile labelling is identical
for both.

## Regressions checked

* **Route × role matrix** — 186 probes (every GET route as each of the three
  roles), byte-identical before and after.
* **Diagnosis restriction** — the two fields are absent from the Staff form, a
  forged Staff POST carrying a diagnosis stores nothing and is logged as
  *"Refused clinical judgement from an unlicensed role"*, a sealed record renders
  as the placeholder for Staff and in full for the Administrator, and a Staff
  attempt to lift a seal 404s.
* **EPI tracking** — every due date recomputed independently against each child's
  birthday (0 mismatches), every dose on file grades Completed and only those,
  every patient's four status counts sum to the schedule length, the split
  `administered + reported == completed` holds for every patient, and
  `up_to_date + needing_attention == eligible` still holds on the follow-up list.
* **Migrations** — all 21 run; `migrate_add_immunization_source.py` is idempotent
  and re-runs as a no-op with its constraint proofs intact.
* **Fresh install** — a database built only from `schema.sql` carries the column,
  both CHECKs fire, and the undated-reported case is accepted.

Two older migrations had assertions that a later feature had already invalidated,
and this work was what tripped them. Both were corrected to verify what they are
answerable for rather than to forbid what came after — see the commit.

Three data-cleanup migrations (`migrate_demo_data_hygiene.py`,
`migrate_remove_fake_patient.py`, `migrate_remove_test_residue.py`) exit 1. They
compare the live database against a frozen backup snapshot and were confirmed to
fail identically on the pre-task database. Pre-existing, and untouched here.

## Images

None kept. `.gitignore` excludes every image under this folder for the reason the
parent `README.md` gives: a screenshot of the Patient Profile is a patient record,
and a repository that refuses to hold `app.db` cannot sensibly hold a picture of
it. The screenshots taken during this pass showed Darwin Manalastas's full name,
patient ID, age, address, contact number and vaccination history.

## Reproducing it

1. `python migrate_add_immunization_source.py`
2. `python app.py`
3. Sign in as Health Center Staff. Patient Queue → Check In Patient → an infant
   with outstanding doses → Start Consultation → Record Consultation.
4. In **Immunizations Given Today**, tick a dose in the **Previously given
   elsewhere** column. Give one a date; leave another's blank.
5. Save. Read the flash message, then open the patient's **Immunization Record**
   tab and compare a reported row against an on-site one.
