# dispense-supplies-equipment/

Verification of two changes made together:

1. **Dispensing widened to Supply and Equipment.** `dispensable_items()` offered
   Medicine only; it now offers every category the inventory records, under the
   same rules already proven for medicine.
2. **"Low Stock Medicines" corrected to "Low Stock Items"** on both dashboards,
   matching Medicine Inventory's already-correct card — the count has always been
   able to include a Supply row (Sterile Gauze Pad is one of the six today).

No images are committed — see the note in the parent README for why a screenshot
of a Patient Profile is a patient record. What follows is what was exercised and
what was observed, so it can be produced again.

## Automated suites — 268 checks, all passing

Suites A–E run against **scratch copies** of `app.db`; F and G go over HTTP to a
real `python app.py` process.

| Suite | Checks | What it covers |
| --- | ---: | --- |
| **A** — model baseline | 27 | Captured *before* the change and re-run after. Medicine behaviour, the hard blocks, `parse_dispensing()`'s structural gate, the atomic rollback. |
| **B** — the widening | 75 | Supply and Equipment offered, dispensed and decremented; both hard blocks and the retirement block applied to each; a no-expiry item; mixed submissions; all-or-nothing rollback across categories. |
| **C** — HTTP, both roles | 98 | Record Consultation driven as a browser would, under Administrator *and* Health Center Staff: the rendered dropdown, a real save, the flash message, both hard blocks including a tampered client. |
| **D** — rendered sweep | 21 | Every GET screen rendered under all three roles and searched for stale wording. |
| **E** — exports | 30 | The generated `.xlsx` cells read back, and every `.pdf` export re-rendered. |
| **F** — live server | 17 | The real process on `127.0.0.1:5001`, real `app.db`, read-only. |
| **G** — live walk | 55 | A real consultation on the real database, both roles (see below). |

### Suite A is the regression evidence

The baseline was captured before any edit and diffed against the same suite run
afterwards. The **only** differences are the intended ones:

* two more items offered (the Supply and the Equipment),
* Supply/Equipment accepted instead of category-refused,
* the out-of-stock gauze now refused as *"is out of stock"* rather than
  *"filed under Supply, not Medicine"* — the more accurate of the two.

The nine medicines offered, and all 27 assertions, are identical before and
after. Medicine dispensing is untouched.

## The real walk (Suite G)

A `PRETASK_BACKUP` of `app.db` was taken first, as this project does for every
task that writes to the real database.

Every step went through the application's own endpoints — check-in and
start-consultation included — so nothing was staged behind the app's back. Run
once as **Administrator** and once as **Health Center Staff**:

| Step | Observed |
| --- | --- |
| Check In → Start Consultation | Real queue entry, real `In Consultation` status. |
| The dropdown | `Digital Thermometer (Equipment) — 6 pieces in stock`, `Disposable Face Mask (Supply) — 600 boxes in stock`, alongside the medicines. Out-of-stock gauze absent. |
| **Hard block** — thermometer ×31 against a shelf of 6 | Refused. Form bounced at 200, message named the shelf, **and the face-mask line on the same submission was rolled back with it**. No consultation written. |
| The real save | Face Mask ×2, Thermometer ×1, Paracetamol ×5 in one visit. Stock moved 600→598, 6→5, 745→740. Three rows in `medicine_dispensing`. |
| Patient Profile | **Dispensing History** tab lists the supply and the equipment beside the medicine. |

### The database was then restored

`app.db` was restored from the pre-task backup and verified **byte-for-byte
identical** to it. The verification records — 2 appointments, 2 consultations, 6
dispensing rows — are not left behind, following the same discipline as the
earlier "take the test run out of the database" cleanup.

The consultation-id gap (39, 40 rather than 38) is not a lost record: the table
is `AUTOINCREMENT` and `sqlite_sequence` already stood at 38 from that earlier
cleanup.

## The labelling decision

The section is now **Items Dispensed**, not "Medicines Dispensed".

It had to change: leaving it would put a pack of gauze under a heading that says
"medicines", which is the same class of stale-but-once-true sentence this project
has corrected before. "Items" is the word the rest of the system already uses for
inventory rows — *Item type* on the Add / Edit form, *Items tracked* in the
export, *Low Stock **Items*** on Medicine Inventory — so it is the existing plain
word rather than a new one.

Consequently relabelled, because all of them can now name a supply:

| Where | Was | Now |
| --- | --- | --- |
| Record Consultation section | Medicines Dispensed | Items Dispensed |
| Record Consultation column / control | Medicine · Add another medicine | Item · Add another item |
| Patient Profile tab | Medicine History | Dispensing History |
| Patient Profile stat card | Medicines Dispensed | Items Dispensed |
| Administrator dashboard column | Medicine | Dispensed |
| Reports & Analytics panel | Most Dispensed Medicines | Most Dispensed Items |
| Report export sheet | Medicine Dispensed | Items Dispensed |

Non-medicine options carry their item type — `Disposable Face Mask (Supply)` —
because the list now mixes three kinds of thing on a clinical form. Medicines are
left unmarked: labelling them too would put a word on nine options out of eleven
to distinguish the two that need it.

**The stored column is still `medicine_name`, and the table is still
`medicine_dispensing`.** Renaming either means a migration across a proven table
carrying a foreign key and a UNIQUE constraint, for nothing a reader ever sees —
the column holds the name of the thing dispensed, which is what it always held.

## Reproducing it

1. `python app.py`, sign in as the Administrator.
2. Appointment Scheduling → Check In Patient → Start Consultation → the
   `edit_note` action on the row.
3. Scroll to **Items Dispensed**. The dropdown now lists supplies and equipment
   marked as such, each with its live stock.
4. Ask for more of a supply than the shelf holds and save — the form bounces and
   *the whole submission* is refused, including any good lines beside it.
5. Dispense a supply and a medicine together, then check the flash, the patient's
   **Dispensing History** tab, and Medicine Inventory for the new stock levels.
6. An expired supply is never offered; posting its id anyway is refused by the
   server, exactly as an expired medicine is.
