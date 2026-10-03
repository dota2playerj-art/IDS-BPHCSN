"""What was handed over or used at a visit, and the stock it came off."""
from database.connection import db_connection
from models.consultations import (
    CONFIDENTIAL_LABEL,
    RESTRICTED_PLACEHOLDER,
    can_view_restricted,
    open_sealed_value,
)
from models.inventory import (
    ITEM_CATEGORIES,
    RETIRED_STATUS,
    get_all_inventory_items,
    usable_batches,
)
from utils.dates import display_date, resolve_range, today
from utils.roles import is_care_team
from utils.small_counts import fold_small_counts

# What this form may dispense: every category the inventory records, read from
# models.inventory rather than listed again here, so a category added to the
# vocabulary cannot end up dispensable on one screen and not on another.
#
# The test that reads this is therefore satisfied by any item the Add Medicine
# form could have created, and is kept for the same reason the rowcount check in
# record_dispensing() is kept -- it is the guard that does not depend on the
# vocabulary being what this module assumes.
DISPENSABLE_CATEGORIES = ITEM_CATEGORIES

# How many item lines the form starts with, and the most it will read from one
# submission.
#
# The section used to render exactly four lines, fixed, on the argument that four
# covers what a barangay consultation issues and that a visit needing a fifth
# could be edited afterwards. Both halves of that were wrong. A patient on
# maintenance drugs for two chronic conditions who arrives with an infection is
# an ordinary afternoon at this station, not an edge case; and telling the
# operator to save the visit and reopen it to finish recording what they have
# already handed to the patient is a worse answer than one more line.
#
# So the form starts at DISPENSE_START_ROWS and grows on request. The starting
# figure is low because most consultations dispense nothing and most that do
# dispense one thing -- four blank rows made the common case wear the shape of
# the rare one. Two lines are server-rendered, so the section still records a
# consultation with JavaScript off; only the lines past them need the button.
#
# DISPENSE_MAX_ROWS is a bound on the parse loop rather than a clinical opinion:
# parse_dispensing() reads fields by index and something has to stop it. Ten is
# far past any single visit this station will record, and a ceiling the form
# never reaches costs nothing.
DISPENSE_START_ROWS = 2
DISPENSE_MAX_ROWS = 10

# The largest amount one line may carry. Not a storage limit -- the column would
# take any integer -- but a typo guard, and the specific typo it is aimed at is a
# year in a quantity box. "2026" tablets of anything would empty a shelf in one
# save and pass every other check in this file, because the stock check only asks
# whether the units are there. A thousand units to one patient at one visit is
# already far beyond a barangay issue; four digits is never one.
QUANTITY_RANGE = (1, 1000)

# The form posts one pair of fields per line. Named through these functions so
# the template, the parser and the error messages cannot disagree about a field
# name -- the same arrangement models/general_vaccinations.py uses for its rows.
#
# The prefixes keep the word "dispense" rather than "medicine", which is what
# they always said, so widening the section to supplies and equipment changed no
# posted field name and no already-rendered form.
ITEM_FIELD_PREFIX = "dispense_item_"
QUANTITY_FIELD_PREFIX = "dispense_qty_"


def item_field(index):
    """The form field carrying the chosen item for one line."""
    return "{}{}".format(ITEM_FIELD_PREFIX, index)


def quantity_field(index):
    """The form field carrying the amount for one line."""
    return "{}{}".format(QUANTITY_FIELD_PREFIX, index)


# Labels for the error summary at the top of the consultation form, which prints
# `field_labels.get(field, field)` and would otherwise show a raw field name.
FIELD_LABELS = {}
for _index in range(DISPENSE_MAX_ROWS):
    FIELD_LABELS[item_field(_index)] = "Item on line {}".format(_index + 1)
    FIELD_LABELS[quantity_field(_index)] = "Quantity on line {}".format(_index + 1)
del _index


# Units whose plural is not simply "+s". models.inventory.UNITS is the closed
# list this has to cover, and "Box" is the only member of it that sibilates --
# but the rule rather than the exception is written out, because the list is one
# a future item could be added to.
def _plural(count, unit):
    """'8 tablets', '1 sachet', '3 boxes', or '8 units' when none is on file.

    Error messages are the whole point of this: "Only 8 of Amoxicillin remain"
    is a sentence a health worker has to finish themselves, and the unit is
    already sitting on the inventory row.
    """
    word = str(unit or "").strip().lower() or "unit"
    if count == 1:
        return "1 {}".format(word)
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return "{} {}es".format(count, word)
    return "{} {}s".format(count, word)


def dispensing_label(record):
    """'Paracetamol — 10 tablets'. The one place a dispensing becomes words.

    Read by the profile's Dispensing History tab, the consultation form's
    already-recorded list, the flash message and the audit line, so all four name
    an issue identically -- the job vaccination_label() does for a vaccination.
    """
    return "{} — {}".format(
        record["medicine_name"],
        _plural(record["quantity_dispensed"], record.get("unit")),
    )


# WHO MAY READ THE MEDICINE NAMES OF A SEALED VISIT (Task 5b, D3).
# A medicine can reveal a condition: an antiretroviral names HIV as surely as a
# diagnosis does. The care team -- the Doctor and Health Center Staff, who hand the
# medicine over -- still see what was dispensed. The Administrator runs the system
# and is not part of the patient's care, so on a patient-linked view of a sealed
# visit they see the placeholder where the name would be. See
# utils.roles.is_care_team().
def can_see_sealed_medicines(role):
    """Whether this role may read the names dispensed at a sealed visit."""
    return is_care_team(role)


def _describe(item):
    """'Paracetamol 500 mg tablet' for an option label: the item's display name, which is
    already built from its generic name, strength and form."""
    return item["name"]


def dispensable_items(items=None):
    """The items the form may offer, in the order it lists them.

    Three conditions, and each is one this project already decides somewhere else:

        a category the inventory   Medicine, Supply and Equipment all qualify; the test is
        records                    kept as a guard rather than as a narrowing.
        not retired                the same flag in_service() excludes from every figure.
        usable stock above zero    stock_quantity on an enriched item is the sum of its
                                   usable batches, so an item whose only stock is expired
                                   is not offered.

    An option list is a suggestion and a POST need not have come from one, so the same rules
    are enforced again by _refusal(). Sorted by label, so the three categories interleave
    alphabetically.

    `items` lets a caller that has already loaded the inventory pass it in.
    """
    if items is None:
        items = get_all_inventory_items()

    offered = []
    for item in items:
        if (item.get("category") not in DISPENSABLE_CATEGORIES
                or item.get("is_retired")
                or (item.get("stock_quantity") or 0) <= 0):
            continue
        offered.append({
            "id": item["id"],
            "name": item["name"],
            "label": _describe(item),
            "unit": item.get("unit"),
            "stock_quantity": item.get("stock_quantity") or 0,
            "stock_status": item.get("stock_status"),
            "category": item.get("category"),
            # So the option can say "820 tablets available" and the operator sees the limit
            # before they hit it rather than after.
            "stock_text": _plural(item.get("stock_quantity") or 0, item.get("unit")),
        })
    offered.sort(key=lambda entry: entry["label"].lower())
    return offered


def _refusal(row, usable_total, quantity):
    """Why this item cannot be dispensed in this amount, or None if it can.

    THE SINGLE DEFINITION OF THE HARD BLOCKS. Called by check_dispensing() before anything
    is written and again by record_dispensing() inside the write transaction, so the check
    the operator was shown and the check that governs the write cannot come apart.

    `usable_total` is the amount in the item's usable batches: not expired, not empty. An
    expired batch is never used, so it is not in it. When the amount is short the message
    says how much is available.
    """
    name = row["name"]
    unit = row["unit"]

    if row["status"] == RETIRED_STATUS:
        return (
            "{} has been retired from the inventory and cannot be dispensed. "
            "Set it back to Active on Medicine Inventory if it is in use again."
            .format(name)
        )

    if usable_total <= 0:
        return (
            "{} has no usable stock, so none can be dispensed. Expired stock is "
            "not used.".format(name)
        )

    if quantity > usable_total:
        return (
            "Only {} of {} available, so {} cannot be dispensed."
            .format(_plural(usable_total, unit), name, _plural(quantity, unit))
        )

    return None


def _blamed_field(index, usable_total, quantity):
    """Which of a line's two boxes a refusal should be reported against.

    The quantity box when the amount is the thing that has to change -- there is usable
    stock, just not that much of it -- and the item box for everything else, because a
    retired or empty item cannot be fixed by typing a smaller number.
    """
    if usable_total > 0 and quantity > usable_total:
        return quantity_field(index)
    return item_field(index)


def _usable_total(conn, item_id):
    """The amount an item can be dispensed from right now: its usable batches, FEFO order."""
    return sum(batch["quantity_remaining"] for batch in usable_batches(conn, item_id))


def parse_dispensing(form_data):
    """Read the "Items Dispensed" section. Returns (entries, errors).

    `entries` is [{'index', 'item_id', 'quantity'}] for the lines that were
    filled in, in form order. A line with neither field filled is not an entry
    and not an error -- most consultations dispense nothing, and most that do
    dispense fill a single line.

    `errors` is {field: message}, merged by the caller into the consultation's
    own errors so one refusal summary covers the whole form.

    This is the structural gate only: is there an item, is the amount a sensible
    whole number, is the same item on two lines. Whether the shelf can actually
    supply it is check_dispensing()'s question, because that one needs the
    database and this one does not.

    HALF-FILLED LINES ARE ERRORS, NOT SILENT DROPS. A quantity typed with no item
    chosen, or an item chosen with no quantity, is somebody in the middle of
    recording an issue -- and a save that quietly discarded it would take units
    off a patient's record that the operator watched themselves type.
    """
    entries, errors = [], {}
    chosen = {}

    # Every index the form could have posted, not the number it started with:
    # the operator may have asked for more lines, and a line the server declined
    # to read would be something handed over and not recorded.
    for index in range(DISPENSE_MAX_ROWS):
        raw_item = str(form_data.get(item_field(index)) or "").strip()
        raw_quantity = str(form_data.get(quantity_field(index)) or "").strip()

        if not raw_item and not raw_quantity:
            continue

        if not raw_item:
            errors[item_field(index)] = (
                "Choose the item this quantity was given from, or clear the "
                "quantity."
            )
            continue

        if not raw_item.isdigit():
            # The value came from somewhere other than the dropdown this form
            # renders. Refused rather than looked up, exactly as
            # parse_general_vaccinations() refuses a vaccine key its list does
            # not contain.
            errors[item_field(index)] = (
                "That is not an item this form offers. Pick one from the list."
            )
            continue
        item_id = int(raw_item)

        if not raw_quantity:
            errors[quantity_field(index)] = (
                "Enter how many were given, or clear the item on this line."
            )
            continue

        low, high = QUANTITY_RANGE
        if not raw_quantity.isdigit() or not (low <= int(raw_quantity) <= high):
            errors[quantity_field(index)] = (
                "Enter the amount given as a whole number between {} and {}."
                .format(low, high)
            )
            continue
        quantity = int(raw_quantity)

        # One item, one line, with the whole amount on it -- the rule the
        # table's UNIQUE (consultation_id, inventory_item_id) enforces. Caught
        # here so the operator is told which line to fix instead of meeting a
        # constraint error at the write.
        if item_id in chosen:
            errors[item_field(index)] = (
                "This item is already on line {}. Put the whole amount given "
                "at this visit on that one line.".format(chosen[item_id] + 1)
            )
            continue
        chosen[item_id] = index

        entries.append({"index": index, "item_id": item_id, "quantity": quantity})

    return entries, errors


def check_dispensing(entries, consultation_id=None):
    """The two hard blocks, run before anything is saved. Returns {field: message}.

    Empty means every line can be supplied *as the shelf stands right now*. It is
    not a promise: record_dispensing() checks again inside its transaction and
    that is the check that governs. This one exists so a refusal comes back as a
    form with the message under the offending line, rather than as a consultation
    that saved with a failure notice attached to it.

    `consultation_id` is passed when editing a visit that may already have
    dispensing on file, so a line repeating an item already issued at that visit
    is refused here with the amount named -- rather than at the UNIQUE
    constraint, which would say nothing useful to the person who typed it.
    """
    if not entries:
        return {}

    errors = {}
    with db_connection() as conn:

        existing = {}
        if consultation_id:
            existing = {
                row["inventory_item_id"]: row
                for row in conn.execute(
                    "SELECT inventory_item_id, medicine_name, unit, quantity_dispensed "
                "FROM medicine_dispensing WHERE consultation_id = ?",
                    (consultation_id,),
                ).fetchall()
            }

        for entry in entries:
            already = existing.get(entry["item_id"])
            if already is not None:
                errors[item_field(entry["index"])] = (
                    "{} is already recorded for this visit ({}). Correct that entry "
                "rather than dispensing it a second time.".format(
                        already["medicine_name"],
                        _plural(already["quantity_dispensed"], already["unit"]),
                    )
                )
                continue

            row = conn.execute(
                "SELECT id, name, unit, category, status FROM inventory_items WHERE id = ?",
                (entry["item_id"],),
            ).fetchone()

            if row is None:
                errors[item_field(entry["index"])] = (
                    "That item is no longer in the inventory. Pick one from the "
                "list."
                )
                continue

            # Unreachable for any row the Add Medicine form could have created, since
            # every category it offers is dispensable. Kept as the guard for a row
            # that arrived some other way, so a category this module has never heard
            # of cannot be dispensed by default.
            if row["category"] not in DISPENSABLE_CATEGORIES:
                errors[item_field(entry["index"])] = (
                    "{} is filed under {}, which is not something this form can "
                "dispense. Correct its item type on Medicine Inventory."
                    .format(row["name"], row["category"] or "no item type")
                )
                continue

            usable_total = _usable_total(conn, row["id"])
            refusal = _refusal(row, usable_total, entry["quantity"])
            if refusal:
                errors[_blamed_field(entry["index"], usable_total, entry["quantity"])] = refusal

    return errors


class _Refused(Exception):
    """Raised inside record_dispensing()'s transaction to roll the whole lot back."""


def record_dispensing(patient_id, entries, dispensed_by, date_dispensed,
                      consultation_id=None, audit=None):
    """Write what was given or used at one visit and take it off the shelf.

    Returns (stored, errors). `stored` is the rows actually written, each with
    the item's name, unit and the stock level it left behind; `errors` is
    {field: message} and is non-empty only when the write was refused.

    ATOMIC, AND ALL-OR-NOTHING ACROSS THE WHOLE SUBMISSION
    ------------------------------------------------------
    Every insert and every decrement in one submission happen inside one
    transaction. Two things follow, and both are the point of the function:

    * A dispensing record and the stock movement it caused can never disagree.
      They are written by two statements that commit together or roll back
      together, so there is no instant at which one exists without the other and
      no failure that can leave one behind.

    * If any line is refused, none of the lines are written. A partial save would
      leave the operator looking at a form they have to resubmit, with some of
      its lines already dispensed -- and resubmitting would dispense those twice.
      Refusing the lot is the only outcome that makes "fix it and save again"
      safe.

    BEGIN IMMEDIATE, not the implicit transaction sqlite3 would start on the
    first INSERT. The stock figure is read, judged and decremented in three
    steps, and between a deferred read and its write another connection may
    commit its own dispensing of the same medicine. IMMEDIATE takes the write
    lock up front, so the stock this function reads is the stock it decrements.

    FEFO (First Expiry, First Out): the amount comes from the usable batch with the
    earliest expiry, then the next, until it is covered. Which batches were used is
    recorded for each dispensing (medicine_dispensing_batches). Staff do not pick batches.

    Each batch decrement is itself guarded -- `AND quantity_remaining >= ?` -- and its
    rowcount is checked. That is the last refusal, after the form's and _refusal()'s, and
    it holds with no Python involved at all. If it ever fires, something upstream is
    wrong; it rolls back rather than writing a record whose stock movement did not happen.

    `audit(conn, stored)` is called inside that transaction, before the commit,
    so a refused or failed submission leaves no audit entry either.
    """
    if not entries:
        return [], {}

    day = date_dispensed
    day = day.isoformat() if hasattr(day, "isoformat") else str(day)

    with db_connection() as conn:
        # Must be set before the transaction opens; inside one it is a no-op. This is
        # what makes the table's foreign keys real rather than decorative, so a row
        # cannot name an inventory item or a user that is not there.
        conn.execute("PRAGMA foreign_keys = ON")

        stored, errors = [], {}
        try:
            conn.execute("BEGIN IMMEDIATE")

            for entry in entries:
                row = conn.execute(
                    "SELECT id, name, unit, category, status, low_stock_threshold "
                    "FROM inventory_items WHERE id = ?",
                    (entry["item_id"],),
                ).fetchone()

                if row is None or row["category"] not in DISPENSABLE_CATEGORIES:
                    errors[item_field(entry["index"])] = (
                        "That item is no longer available to dispense. Pick one "
                    "from the list."
                    )
                    raise _Refused

                # FEFO: the usable batches, earliest expiry first. Expired and empty
                # batches are not in the list, so they are never used.
                batches = usable_batches(conn, row["id"])
                usable_total = sum(batch["quantity_remaining"] for batch in batches)
                refusal = _refusal(row, usable_total, entry["quantity"])
                if refusal:
                    errors[_blamed_field(entry["index"], usable_total, entry["quantity"])] = refusal
                    raise _Refused

                # The same item, at the same visit, already on file. The table's
                # UNIQUE (consultation_id, inventory_item_id) would refuse the insert
                # below anyway, but by raising; asking first, in the same transaction
                # and under the same lock, lets the refusal be worded. This is the check
                # that makes a double-submitted form safe.
                if consultation_id:
                    already = conn.execute(
                        "SELECT medicine_name, unit, quantity_dispensed "
                    "FROM medicine_dispensing "
                    "WHERE consultation_id = ? AND inventory_item_id = ?",
                        (consultation_id, entry["item_id"]),
                    ).fetchone()
                    if already is not None:
                        errors[item_field(entry["index"])] = (
                            "{} is already recorded for this visit ({}). Correct that "
                        "entry rather than dispensing it a second time.".format(
                                already["medicine_name"],
                                _plural(already["quantity_dispensed"], already["unit"]),
                            )
                        )
                        raise _Refused

                cursor = conn.execute(
                    """
                INSERT INTO medicine_dispensing
                    (patient_id, consultation_id, inventory_item_id,
                     medicine_name, unit, quantity_dispensed, date_dispensed,
                     dispensed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (patient_id, consultation_id, entry["item_id"], row["name"],
                     row["unit"], entry["quantity"], day, dispensed_by),
                )
                dispensing_id = cursor.lastrowid

                # Take it batch by batch, earliest expiry first, splitting across batches
                # when one runs out. Each decrement is guarded in SQL, so a batch can
                # never go below zero; if one ever fails, the whole submission rolls back.
                needed, taken = entry["quantity"], []
                for batch in batches:
                    if needed <= 0:
                        break
                    amount = min(needed, batch["quantity_remaining"])
                    moved = conn.execute(
                        "UPDATE inventory_batches "
                        "SET quantity_remaining = quantity_remaining - ? "
                        "WHERE id = ? AND quantity_remaining >= ?",
                        (amount, batch["id"], amount),
                    )
                    if moved.rowcount != 1:
                        errors[quantity_field(entry["index"])] = (
                            "{}'s stock changed while this was being saved, so nothing "
                        "was dispensed. Reload and try again.".format(row["name"])
                        )
                        raise _Refused
                    conn.execute(
                        "INSERT INTO medicine_dispensing_batches "
                        "(dispensing_id, batch_id, quantity) VALUES (?, ?, ?)",
                        (dispensing_id, batch["id"], amount),
                    )
                    taken.append((batch["lot_number"], amount))
                    needed -= amount
                if needed > 0:
                    # Unreachable: usable_total was checked against the same batches under
                    # the same lock. Kept so a record never exists without its stock move.
                    errors[quantity_field(entry["index"])] = (
                        "{}'s stock changed while this was being saved, so nothing "
                    "was dispensed. Reload and try again.".format(row["name"])
                    )
                    raise _Refused
                conn.execute(
                    "UPDATE inventory_items SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (entry["item_id"],),
                )

                stored.append({
                    "index": entry["index"],
                    "item_id": entry["item_id"],
                    "medicine_name": row["name"],
                    "unit": row["unit"],
                    "quantity_dispensed": entry["quantity"],
                    # The batches used, as (lot number, amount), earliest expiry first.
                    "batches": taken,
                    # What the item holds in usable stock now, for the flash message.
                    "stock_after": usable_total - entry["quantity"],
                    "low_stock_threshold": row["low_stock_threshold"] or 0,
                })

            # The audit entry is part of the same all-or-nothing transaction.
            if audit and stored:
                audit(conn, stored)
            conn.commit()
        except _Refused:
            conn.rollback()
            stored = []
        except Exception:
            # Any other failure -- a constraint nobody anticipated, a disk error --
            # must not leave a decrement without its record or the reverse.
            conn.rollback()
            raise

    return stored, errors


# One SELECT behind all three readers below, so the profile tab, the consultation
# form and the dashboard table describe an issue with the same columns.
#
# Both joins to something other than users are LEFT joins, and for two different
# reasons. consultation_id is ON DELETE SET NULL -- the medicine was handed over
# whether or not its paperwork survived -- and inventory_item_id is ON DELETE
# RESTRICT, so an item cannot go missing, but a LEFT join means a row still reads
# correctly if one ever did. Neither is what the record *says*: medicine_name and
# unit are on the dispensing row itself, so the history is legible with both
# joins returning nothing.
_DISPENSING_SELECT = """
SELECT d.id, d.patient_id, d.consultation_id, d.inventory_item_id,
       d.medicine_name, d.unit, d.quantity_dispensed, d.date_dispensed,
       d.dispensed_by, d.created_at,
       u.full_name AS dispensed_by_name,
       i.item_code AS item_code,
       c.consultation_date AS consultation_date,
       c.diagnosis AS consultation_diagnosis,
       c.is_restricted AS consultation_restricted
FROM medicine_dispensing d
JOIN users u ON u.id = d.dispensed_by
LEFT JOIN inventory_items i ON i.id = d.inventory_item_id
LEFT JOIN consultations c ON c.id = d.consultation_id
"""


def _to_records(rows, viewer_role=None):
    """Stored dispensing rows -> the dicts the three readers below hand out.

    `viewer_role` None is for a caller that names no role. It is treated as a
    role that may read nothing sealed: a sealed diagnosis becomes the placeholder,
    and so do the medicine names of a sealed visit (D3).

    WHY A DISPENSING ROW HAS TO BE REDACTED AT ALL.
    It does not hold a diagnosis; it joins to one. _DISPENSING_SELECT brings
    `c.diagnosis` along so the Dispensing History tab can print the column headed
    "For (Diagnosis)" without a query per row, and that column is on the same
    Patient Profile page whose Consultation History is sealed. Withholding the
    diagnosis in one tab and printing it two tabs across would be a seal that
    protects nothing -- and it is exactly the kind of second copy of a value that
    an access rule applied only at the obvious place leaves behind.

    The medicine name is the second such copy. For a role outside the care team
    the name, the unit and the item code are taken out of the record itself, and
    the label becomes the placeholder. The quantity stays, as a bare number: a
    count does not say what was counted.
    """
    can_view = viewer_role is not None and can_view_restricted(viewer_role)
    can_see_medicines = (viewer_role is not None
                         and can_see_sealed_medicines(viewer_role))
    records = [dict(row) for row in rows]
    for record in records:
        record["consultation_restricted"] = bool(
            record.get("consultation_restricted")
        )
        record["medicines_withheld"] = (
            record["consultation_restricted"] and not can_see_medicines
        )
        if record["medicines_withheld"]:
            record["medicine_name"] = RESTRICTED_PLACEHOLDER
            record["unit"] = None
            record["item_code"] = None
            record["inventory_item_id"] = None
        record["label"] = (
            RESTRICTED_PLACEHOLDER if record["medicines_withheld"]
            else dispensing_label(record)
        )
        record["quantity_text"] = _plural(
            record["quantity_dispensed"], record.get("unit")
        )
        record["consultation_unopenable"] = False
        if not record["consultation_restricted"]:
            continue
        # A sealed diagnosis is stored encrypted. The Doctor gets it decrypted;
        # everyone else, and every caller that names no role, gets the placeholder.
        if can_view:
            text, opened = open_sealed_value(record["consultation_diagnosis"],
                                             record["consultation_id"], "diagnosis",
                                             viewer_role)
            record["consultation_diagnosis"] = text
            record["consultation_unopenable"] = not opened
        else:
            record["consultation_diagnosis"] = RESTRICTED_PLACEHOLDER
    return records


def get_dispensing_for_patient(patient_id, viewer_role):
    """Everything issued to one patient, most recent first, redacted to fit.

    The Dispensing History tab on Screen 04. Newest first, matching the general
    vaccination history and for the same reason: this is a plain record of what
    was given rather than a schedule read in order, and the most useful line is
    the last thing the patient collected.

    The visit's own date and diagnosis come along from _DISPENSING_SELECT, so the
    tab can say which consultation an issue belongs to and what it was given for
    without a second query per row.

    That diagnosis is why `viewer_role` has no default here, exactly as it has
    none on models.consultations.get_consultations_for_patient(): this is the
    second place on the Patient Profile where a sealed diagnosis would otherwise
    reach the page, and a default would be a decision about confidentiality made
    by whichever value looked harmless when the signature was written. The
    dispensing itself is withheld only from a role outside the care team, and
    only on a sealed visit -- see _to_records() and utils.roles.is_care_team().
    """
    with db_connection() as conn:
        rows = conn.execute(
            _DISPENSING_SELECT
            + " WHERE d.patient_id = ? ORDER BY d.date_dispensed DESC, d.id DESC",
            (patient_id,),
        ).fetchall()
    return _to_records(rows, viewer_role)


def get_dispensing_for_consultation(consultation_id, viewer_role):
    """The items issued during one visit, oldest row first, redacted to fit.

    Its callers are the "already dispensed at this visit" list on the
    consultation form and the same list in the profile's per-visit detail panel.
    Both print the medicine, so the role is compulsory: on a sealed visit a role
    outside the care team gets the placeholder (D3).
    """
    if not consultation_id:
        return []
    with db_connection() as conn:
        rows = conn.execute(
            _DISPENSING_SELECT + " WHERE d.consultation_id = ? ORDER BY d.id",
            (consultation_id,),
        ).fetchall()
    return _to_records(rows, viewer_role)


def get_dispensing_by_consultation(consultation_ids, viewer_role):
    """{consultation_id: [record, ...]} for a list of visits, in one query.

    The Recent Consultations table on the Administrator dashboard has a Dispensed
    column and prints five rows. Asking per row would be five queries for a panel
    that already has its consultations in hand; this is one.

    Redacted for `viewer_role`, like get_dispensing_for_consultation(): the panel
    is on the Administrator's dashboard, and the Administrator does not see the
    medicine names of a sealed visit (D3).
    """
    ids = [int(value) for value in consultation_ids if value]
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    with db_connection() as conn:
        rows = conn.execute(
            _DISPENSING_SELECT
            + " WHERE d.consultation_id IN ({}) ORDER BY d.id".format(placeholders),
            ids,
        ).fetchall()

    grouped = {}
    for record in _to_records(rows, viewer_role):
        grouped.setdefault(record["consultation_id"], []).append(record)
    return grouped


# How many medicines the most-dispensed list ranks. Matches
# models.consultations.TOP_DIAGNOSIS_LIMIT so the two ranked panels on Reports &
# Analytics are the same length and read as a pair.
TOP_MEDICINE_LIMIT = 5

# The one row every sealed visit's dispensing is ranked under (Task 5c, M25), the
# same word the diagnosis ranking uses. The key cannot collide with a medicine
# name, because no name is empty.
CONFIDENTIAL_KEY = ""


def get_dispensing_stats(months=6, limit=TOP_MEDICINE_LIMIT, on_date=None,
                         start=None, end=None, *, viewer_role):
    """The dispensing figures Reports & Analytics and the dashboards report.

    Deliberately the same shape as models.consultations.get_consultation_stats():
    all-time totals at the top level, and everything the selected range answers
    inside a `window` block. A screen that plots both series reads them the same
    way, and the two cannot end up describing different windows.

    THE TREND IS CLIPPED TO THE RANGE, not to whole months, for the reason
    get_consultation_stats() gives: a report for 1-10 August whose August bar
    showed the whole month would put one number on the chart underneath a
    different one on the card, and nothing on the sheet would say which answered
    the range that was asked for.

    THE RANKING IS BY ITEM (inventory_item_id), NOT BY THE NAME TEXT STORED ON THE
    ROW. An item renamed by Edit details, or by the Task 12 migration, is still one
    medicine: its issues before and after are one line, with its current display
    name. Each dispensing row keeps its stored name as its historical record (the
    profile's Dispensing History still shows it); only the totals group by item.

    date_dispensed is clinic-local date text, exactly as consultation_date is, so
    the range compares against its leading ten characters with no timezone
    conversion.

    `viewer_role` HAS NO DEFAULT. It decides the small-count rule (Task 5d, D1):
    for the Administrator and the Barangay Official an item issued fewer than 5
    times in the range, and the Confidential row when it is that small, are folded
    into one Other row that adds up their units and issues. The test is on issues,
    not units, because one issue is one visit, and one visit is what a small count
    can point at. The window's totals are never changed.
    """
    reference = on_date or today()
    window = resolve_range(start=start, end=end, months=months, on_date=reference)
    lo, hi = window["start"].isoformat(), window["end"].isoformat()

    with db_connection() as conn:
        totals = conn.execute(
            "SELECT COUNT(*) AS events, COALESCE(SUM(quantity_dispensed), 0) AS units "
        "FROM medicine_dispensing"
        ).fetchone()
        patients_supplied = conn.execute(
            "SELECT COUNT(DISTINCT patient_id) FROM medicine_dispensing"
        ).fetchone()[0]

        # is_restricted comes along so dispensing at a sealed visit can be counted
        # under one Confidential row instead of by name (Task 5c, M25).
        scoped = conn.execute(
            """
        SELECT COALESCE(i.name, d.medicine_name) AS medicine_name,
               COALESCE(i.unit, d.unit) AS unit, d.quantity_dispensed, d.patient_id,
               d.inventory_item_id, substr(d.date_dispensed, 1, 7) AS month,
               COALESCE(c.is_restricted, 0) AS sealed
        FROM medicine_dispensing d
        LEFT JOIN inventory_items i ON i.id = d.inventory_item_id
        LEFT JOIN consultations c ON c.id = d.consultation_id
        WHERE substr(d.date_dispensed, 1, 10) BETWEEN ? AND ?
        """,
            (lo, hi),
        ).fetchall()

    units_by_month, events_by_month = {}, {}
    by_medicine = {}
    for row in scoped:
        month = row["month"]
        units_by_month[month] = units_by_month.get(month, 0) + row["quantity_dispensed"]
        events_by_month[month] = events_by_month.get(month, 0) + 1
        # A SEALED VISIT'S MEDICINE IS NOT RANKED BY NAME. A medicine can reveal a
        # condition, and a ranking with a count of 1 over a one-day range points at
        # one visit -- the reason models/consultations.py gives for diagnoses.
        # Its units and events still count, under one Confidential row.
        if row["sealed"]:
            entry = by_medicine.setdefault(
                CONFIDENTIAL_KEY,
                {"medicine_name": CONFIDENTIAL_LABEL, "unit": None,
                 "units": 0, "events": 0, "confidential": True},
            )
        else:
            entry = by_medicine.setdefault(
                row["inventory_item_id"],
                {"medicine_name": row["medicine_name"], "unit": row["unit"],
                 "units": 0, "events": 0},
            )
        entry["units"] += row["quantity_dispensed"]
        entry["events"] += 1

    trend = [
        {
            "month": start_day.strftime("%Y-%m"),
            "label": label,
            "units": units_by_month.get(start_day.strftime("%Y-%m"), 0),
            "events": events_by_month.get(start_day.strftime("%Y-%m"), 0),
        }
        for start_day, _, label in window["months"]
    ]

    # Most units first, ties broken alphabetically so equal counts do not
    # reshuffle between page loads -- the same rule _ranked_conditions() follows
    # on Screen 18.
    ranked = sorted(
        by_medicine.values(),
        key=lambda entry: (-entry["units"], entry["medicine_name"].lower()),
    )
    # Folded before the text is made, so the Other row gets one too. Its unit is
    # blank for the reason the Confidential row's is: it adds up different items.
    ranked = fold_small_counts(
        ranked, viewer_role, label_key="medicine_name",
        sum_keys=("events", "units"), extra={"unit": None},
    )
    for entry in ranked:
        entry["units_text"] = _plural(entry["units"], entry["unit"])
    # The Confidential row is ranked by its units like any other, and kept even
    # when it falls outside the top `limit`, so the list accounts for it. The Other
    # row is always last and is not counted against the limit.
    named = [entry for entry in ranked if not entry.get("other")]
    top = named[:limit]
    top.extend(entry for entry in named[limit:]
               if entry.get("confidential") and entry not in top)
    top.extend(entry for entry in ranked if entry.get("other"))

    return {
        "total_events": totals["events"],
        "total_units": totals["units"],
        "patients_supplied": patients_supplied,
        "months": months,
        "trend": trend,
        "window": {
            "start": window["start"],
            "end": window["end"],
            "custom": window["custom"],
            "events": len(scoped),
            "units": sum(row["quantity_dispensed"] for row in scoped),
            "patients": len({row["patient_id"] for row in scoped}),
            # Distinct items handed over, sealed visits included. A count names
            # nothing.
            "medicines": len({row["inventory_item_id"] for row in scoped}),
            "trend": trend,
            "top_medicines": top,
            "all_medicines": ranked,
        },
    }
