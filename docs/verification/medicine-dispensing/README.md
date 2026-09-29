# medicine-dispensing/

Real-browser verification of medicine dispensing (`a8b213f`), run against the
real `app.db` as the Administrator after the feature had already been verified
at the code and database level by four automated suites (140 checks).

No images are committed — see the note in the parent README for why a screenshot
of a Patient Profile is a patient record. What follows is what was exercised and
what was observed, so it can be produced again.

## What was walked

| Step | Observed |
| --- | --- |
| Administrator Dashboard | Medicine column on Recent Patient Consultations reads real issues ("Ferrous Sulfate — 76 tablets", "Paracetamol — 20 tablets, Vitamin C — 30 tablets") and an em dash where none was given. Sidebar badge and Low Stock card both 8. |
| Monthly Analytics | The "Medicine Units Dispensed" panel is a real amber bar chart on the same six-month axis as the two teal ones, in place of the "not yet tracked" box. |
| Check In → Start Consultation → Record Consultation | PAT-016, walk-in. The Medicines Dispensed section renders below Other Vaccinations with four blank lines. |
| The medicine dropdown | Offers exactly ten items, each with its live stock ("Paracetamol 500mg Tablet — 800 tablets in stock"). Expired Amoxicillin, Cetirizine and Salbutamol, out-of-stock Mefenamic Acid, the Supply (gauze) and the Equipment (thermometer) are all absent. |
| **Hard block 1** — Metformin ×50 against a shelf of 10 | Refused. "This consultation was not saved." · "**Quantity on line 1:** Only 10 tablets of Metformin remain in stock, so 50 tablets cannot be dispensed." The quantity box is outlined red and still holds `50`; the dropdown is still on Metformin — the bounce replays the operator's entry. The error is blamed on the *quantity*, because there is stock, just not that much. |
| **Hard block 2** — expired Amoxicillin | The form never offers it, so this was driven through a **deliberately tampered client**: an `<option value="2">` was injected into the select from the console and submitted. Refused. "**Medicine on line 1:** Amoxicillin expired on Aug 09, 2026 and cannot be dispensed." Blamed on the *medicine* this time — no smaller number fixes an expired drug. This is the case the server-side check exists for. |
| Happy path — Losartan ×30 and Paracetamol ×20 in one visit | Saved. "2 medicines dispensed: Losartan — 30 tablets, Paracetamol — 20 tablets. Stock updated — Losartan now 230, Paracetamol now 780. Their visit is now marked Completed." |
| Patient Profile → Medicine History | "2 issues on file · 50 units in total · most recent first", with Medicine, Quantity, Date Dispensed, For (Diagnosis) and Dispensed By. The stat card above reads "2 — Medicines Dispensed". |
| Reports & Analytics | All three canvases instantiated and painted (35,839 / 69,623 / 30,569 non-transparent pixels, checked against the live `Chart` instances rather than by eye). Most Dispensed Medicines ranked Diatabs 101, Ferrous Sulfate 76, Paracetamol 40, Losartan 30, Vitamin C 30 — by units, ties alphabetical. |

## What the walk found

One defect the automated suites could not have caught, because it was a true
sentence that had quietly become false rather than a broken behaviour: the hint
under **Treatment plan / medicines given** still read "Stock deduction is not
linked to this yet." It sits directly beneath a field about medicines given, and
it told the operator the opposite of what the form now does. Corrected in
`templates/record_consultation.html`, and rewritten to divide the two fields
rather than merely drop the claim — the box is the clinical instruction, the
section above is the units that left the shelf.

## Reproducing it

1. `python app.py`, sign in as the Administrator.
2. Appointment Scheduling → Check In Patient → pick anyone → Start Consultation →
   the edit_note action on the row.
3. Scroll to **Medicines Dispensed**. Pick a medicine whose option shows less
   stock than you ask for, and save — that is hard block 1.
4. Hard block 2 cannot be reached through the form by design, since an expired
   medicine is never offered. Inject an option carrying the id of an expired item
   and submit it; the server refuses regardless of what the client sent.
5. Dispense two medicines legitimately and check the flash, then the patient's
   Medicine History tab, then Medicine Inventory for the new stock levels.
