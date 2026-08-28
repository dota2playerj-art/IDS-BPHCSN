# medicine-lines/

Real-browser verification of the dynamic **Add another medicine** lines and the
two shortened helper notes on Record Consultation, run against the real `app.db`
under both roles that hold the capability, after the change had already been
verified at the code and database level by a 128-check automated suite.

No images are committed — see the note in the parent README for why a screenshot
of a Patient Profile is a patient record. What follows is what was exercised and
what was observed, so it can be produced again.

## What changed, in one line each

The section used to render exactly four medicine lines, fixed. It now renders
two and grows on request up to ten, and the two helper notes under **Other
Vaccinations** and **Medicines Dispensed** state their rules without arguing for
them.

## What was walked

### Administrator — PAT-016, APT-00064, six medicines

| Step | Observed |
| --- | --- |
| The form on load | Two blank medicine lines, not four. A dashed amber **+ Add another medicine** below them. Both helper notes in their short form. |
| Four clicks on the button | Six lines. Field names `dispense_item_0`…`_5` and `dispense_qty_0`…`_5`, aria-labels "…on line 1" through "…on line 6", each new line carrying the same eleven-option medicine list as the two the server rendered, and focus landing in the select that had just appeared. |
| The ceiling | Driven separately on a copy of the served page: ten clicks reached ten lines, at which point the button hid itself and "10 medicines is the most one visit can record." appeared in its place. An eleventh click added nothing. |
| **Hard block 1** — Metformin ×50 against a shelf of 10, **on line 5** | Refused. "This consultation was not saved" · "**Quantity on line 5:** Only 10 tablets of Metformin remain in stock, so 50 tablets cannot be dispensed." All six lines came back with every value intact, only `dispense_qty_4` outlined red. Nothing written: no consultation row, and all six medicines still at their pre-submit stock. |
| **Hard block 2** — expired Amoxicillin **on line 6** | The form never offers an expired medicine, so this was driven through a **deliberately tampered client**: an `<option value="2">` injected into line 6's select from the console. Refused. "**Medicine on line 6:** Amoxicillin expired on Aug 09, 2026 and cannot be dispensed." Blamed on the medicine this time, not the quantity. Nothing written; the injected option was gone on re-render, because the server never offers it. |
| The save | Six medicines in one visit — Paracetamol 20, Amlodipine 30, Losartan 30, Ferrous Sulfate 30, Metformin 10, Vitamin C 20. Flash named all six and the six new stock levels. `medicine_dispensing` rows 7–12 against consultation 35, every quantity matching, every stock decremented exactly, `dispensed_by` = 1, the queue entry Completed. |
| Patient Profile → Medicine History | "8 issues on file · 190 units in total", all six of the new ones listed against the diagnosis they were given for. |

### Health Center Staff — PAT-008, APT-00065, five medicines

Checked in from the queue as a walk-in, started, then written up — the whole
path, not a URL typed in.

| Step | Observed |
| --- | --- |
| The medicine list | Nine items, not ten. Metformin was gone, because the Administrator's save above had taken the last ten tablets off the shelf. The list follows the shelf, live. |
| Three clicks on the button | Five lines, correctly named and labelled. |
| **Hard block 1** — Cotrimoxazole ×40 against a shelf of 15, **on line 5** | Refused, blamed on the quantity, all five lines replayed. |
| **Hard block 2** — expired Cetirizine **on line 5**, injected | Refused. "**Medicine on line 5:** Cetirizine expired on Jul 15, 2026 and cannot be dispensed." |
| Both refusals, checked in the database | No consultation row for APT-00065, `medicine_dispensing` still at 11 rows, and Cotrimoxazole, Cetirizine and the other four all at their pre-submit stock. |
| The save | Five medicines — Diatabs 12, ORS Powder Sachet 6, Paracetamol 15, Amlodipine 30, Cotrimoxazole 10. Rows 13–17 against consultation 36, `dispensed_by` = 2, every stock decremented exactly, the queue entry Completed. |

## What the walk found

One defect, and it is **not** from this change and was **not** fixed here: the
amber notice above a refused consultation reads "1 field need attention" — the
noun is pluralised and the verb is not. `routes/consultation_views.py` builds it
in two places. It predates this work and is left for a task of its own rather
than folded into an unrelated commit.

## Reproducing it

1. `python app.py`, sign in as the Administrator.
2. Appointment Scheduling → Check In Patient → pick anyone → Start Consultation →
   the edit_note action on the row.
3. Scroll to **Medicines Dispensed**. Two lines. Click **+ Add another medicine**
   until there are more than four, and keep clicking to reach ten — the button
   hides itself there.
4. Put more of something on a line past the fourth than the dropdown says is in
   stock, and save. That is hard block 1, and the bounce brings every line back.
5. Hard block 2 cannot be reached through the form by design, since an expired
   medicine is never offered. Inject an option carrying the id of an expired item
   into a line past the fourth and submit it; the server refuses regardless of
   what the client sent.
6. Correct the offending line and save. Check the flash, then the patient's
   Medicine History tab, then Medicine Inventory for the new stock levels.
7. Repeat signed in as Health Center Staff.

With JavaScript off the button never appears — it is rendered `hidden` and the
script is what reveals it — and the two server-rendered lines still record a
consultation. That is the only behaviour of this section that depends on the
browser at all.
