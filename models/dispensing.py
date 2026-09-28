"""What was handed over or used at a visit, and the stock it came off.

THE OTHER HALF OF OBJECTIVE 2
-----------------------------
models/inventory.py tracks what is on the shelf. Until this module existed, every
writer into it moved that figure *up* or corrected it wholesale -- Add Medicine
sets a stock level, Edit Medicine overwrites one -- so "real-time monitoring of
medicine inventory" was monitoring a purchase ledger. Nothing took a unit off a
shelf and said who it went to.

This is the write path that does, and it is the only one. A row here is one issue
of one medicine to one patient during one consultation, and inserting it
decrements that medicine's stock_quantity in the same transaction. The record and
the shelf move together or neither moves.

WHY DISPENSING LIVES ON THE CONSULTATION FORM
---------------------------------------------
Because a dispensing event that is not traceable to the clinical encounter that
justified it is not, at this level of facility, a legitimate record. DOH guidance
for a barangay health station requires medicine given out to be traceable to the
medical supervision behind it, and HL7 FHIR models the same thing structurally:
MedicationDispense -- "issuing a dose from ward stock to a patient for
consumption" -- carries the Encounter it happened during. So there is no
standalone "dispense a medicine" screen in this system, deliberately. The
consultation is where a clinician decides a patient needs something, and it is
where the system lets them record having given it.

WHAT THIS MODULE COVERS
-----------------------
Every category the inventory records: Medicine, Supply and Equipment.

It began narrower. The original line was medicines only, on the argument that
what this implements is the FHIR sense of a dose issued to a patient *for
consumption* -- a tablet, a capsule, a sachet of ORS -- while a pack of gauze
leaves the store as a facility consumable used during a procedure and a
thermometer is not handed over at all. The stated cost of drawing it there was
that supplies and equipment leaving the store were recorded nowhere, which was
named at the time as a real remaining gap needing a path of its own.

That gap is what this now closes, and it closes it here rather than in a second
module, because a second module would be this one with the word "medicine"
changed. Gauze and masks are genuinely used up during real visits at this
station; the consultation is the only moment the system observes them leaving
the shelf, and the alternative to recording them here is not a tidier record but
no record at all. The stock half of Objective 2 is "real-time monitoring of
inventory", and an inventory whose supplies only ever move upward is not being
monitored.

What that widening does mean, said plainly rather than glossed: a row here is no
longer purely a clinical dispensing event. A pack of gauze used during a
procedure appears on the visit alongside the medicines the patient took away,
because the visit is what consumed it. The screens say "items" rather than
"medicines" throughout for exactly that reason -- see the labelling note below.

WHAT THE THREE CATEGORIES SHARE, AND WHY ONE RULE COVERS THEM
-------------------------------------------------------------
Nothing in the two hard blocks was ever specific to medicine. "Do not go
negative" is arithmetic about a shelf, and "do not issue expired stock" is a
question about a date -- gauze and saline expire exactly as tablets do, and both
tests already read models.inventory.stock_status(), which has never asked what
category it was looking at.

The one case the widening genuinely adds is an item with no expiry date at all,
which is ordinary for equipment: a thermometer has a stock level and no expiry.
That case needs no special handling and is deliberately given none.
days_until_expiry() returns None when there is no date to parse, stock_status()
tests `remaining is not None and remaining < 0`, and None fails that test -- so
an item with no expiry date is simply never Expired, while every other check
still applies to it in full. Skipping the expiry test is therefore what the
existing code already does for a missing date; it is not a branch added here,
and nothing exempts such an item from the stock block.

LABELLING
---------
The database column is still `medicine_name`, and the table is still
`medicine_dispensing`. Renaming either would be a migration across a proven table
with a foreign key and a UNIQUE constraint on it, for no gain a reader ever sees:
the column holds the name of the thing dispensed, which is what it always held.
The user-facing wording is what had to be right, and that says "item" throughout.

THE TWO HARD BLOCKS
-------------------
Both are refusals, not warnings, and both are checked twice.

    insufficient stock   a health center cannot hand over units it does not
                         have. Dispensing more than the shelf holds would drive
                         stock_quantity negative, and every figure in
                         models/inventory.py -- the status badge, the reorder
                         bar, the low-stock alert -- is derived from that number.
                         One negative row would make the whole screen lie.

    expired medicine     stock_status() already knows the answer and Screen 06
                         already badges it. Expired stock is physically present
                         and must not be given to a patient, which is precisely
                         why "present on the shelf" cannot be the test.

_refusal() is the single definition of both, and it is called from two places:
check_dispensing(), which runs before anything is written so the form can bounce
with the message beside the field, and record_dispensing(), which runs again
inside the write transaction on the row it is about to decrement. The second is
the authoritative one. The first exists so the operator gets a form back rather
than a saved consultation with a failure notice attached; it is a convenience,
and it is never trusted. A POST can arrive without the page ever having been
loaded, and the shelf can move between the page loading and the save.

Neither check re-derives anything. The expiry test is models.inventory
.stock_status() -- the same function behind the badge on Medicine Inventory --
and the retirement test is its RETIRED_STATUS. A second opinion about whether a
medicine is expired is exactly the drift models/inventory.py's own header warns
against.
"""
from database.connection import db_connection
from models.consultations import RESTRICTED_PLACEHOLDER, can_view_restricted
from models.inventory import (
    ITEM_CATEGORIES,
    RETIRED_STATUS,
    get_all_inventory_items,
    stock_status,
)
from utils.dates import display_date, resolve_range, today

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


def _describe(item):
    """'Paracetamol 500mg Tablet' for an option label, from an enriched item."""
    dosage = (item.get("display_dosage") or "").strip()
    return "{} {}".format(item["name"], dosage).strip()


def dispensable_items(items=None):
    """The items the form may offer, in the order it lists them.

    Four conditions, and each is one this project already decides somewhere else
    rather than a new judgement made here:

        a category the inventory   see the module header. Medicine, Supply and
        records                    Equipment all qualify; the test is kept as a
                                   guard rather than as a narrowing.
        not retired                models.inventory.RETIRED_STATUS -- the same
                                   flag in_service() excludes from every
                                   operating figure. An item the centre has
                                   stopped stocking is not one to hand out.
        not expired                stock_status() via is_expired -- the same call
                                   behind the badge on Screen 06. An item with no
                                   expiry date is not expired and never becomes
                                   so, which is how a thermometer passes this
                                   without a rule of its own.
        stock above zero           there is nothing to give

    The last two are the two hard blocks, applied here as well so the form does
    not offer a choice it is about to refuse. That is not a substitute for the
    refusal -- an option list is a suggestion and a POST need not have come from
    one -- but a dropdown listing an expired item and then rejecting it is a
    worse screen than one that never offered it.

    Sorted by label, so the three categories interleave alphabetically rather than
    grouping. The operator is looking for one named thing and knows its name; the
    alternative -- medicines, then supplies, then equipment -- would make them
    know which drawer the system files it under before they can find it.

    `items` lets a caller that has already loaded the inventory pass it in rather
    than querying twice.
    """
    if items is None:
        items = get_all_inventory_items()

    offered = []
    for item in items:
        if (item.get("category") not in DISPENSABLE_CATEGORIES
                or item.get("is_retired")
                or item.get("is_expired")
                or (item.get("stock_quantity") or 0) <= 0):
            continue
        offered.append({
            "id": item["id"],
            "name": item["name"],
            "label": _describe(item),
            "unit": item.get("unit"),
            "stock_quantity": item.get("stock_quantity") or 0,
            "stock_status": item.get("stock_status"),
            # Carried so the dropdown can mark a supply or a piece of equipment
            # as such. The list mixes three kinds of thing now, and on a clinical
            # form the difference between a drug and a consumable is worth
            # stating at the moment somebody picks one.
            "category": item.get("category"),
            # So the option can say "820 tablets in stock" and the operator sees
            # the limit before they hit it rather than after.
            "stock_text": _plural(item.get("stock_quantity") or 0, item.get("unit")),
        })
    offered.sort(key=lambda entry: entry["label"].lower())
    return offered


def _refusal(row, quantity):
    """Why this item cannot be dispensed in this amount, or None if it can.

    THE SINGLE DEFINITION OF BOTH HARD BLOCKS. Called by check_dispensing()
    before anything is written and again by record_dispensing() inside the write
    transaction, on the row it is about to decrement. Two callers, one rule, so
    the check the operator was shown and the check that actually governs the
    write cannot come apart.

    Category-blind, and always was: nothing below asks what kind of thing it is
    looking at. An item with no expiry date -- ordinary for equipment -- is not
    expired, because stock_status() only calls something expired when it has a
    date that has passed. Every other test still applies to it in full.

    `row` is anything with the inventory columns on it: an enriched dict from
    get_inventory_item_by_id(), or a bare sqlite3.Row read inside a transaction.
    It deliberately takes the raw columns and calls stock_status() itself rather
    than reading a derived flag, because the derived flags are only present on
    the enriched dicts -- and it is the in-transaction call, on a raw row, that
    is the one that has to be right.
    """
    name = row["name"]
    stock = row["stock_quantity"] or 0
    unit = row["unit"]

    if row["status"] == RETIRED_STATUS:
        return (
            "{} has been retired from the inventory and cannot be dispensed. "
            "Set it back to Active on Medicine Inventory if it is in use again."
            .format(name)
        )

    # The same call behind the badge on Screen 06. Expired stock is physically on
    # the shelf, which is exactly why stock alone cannot be the test -- and why
    # this is a refusal rather than a warning. Returns a non-Expired status for an
    # item carrying no expiry date, which is how equipment passes here.
    status = stock_status(stock, row["low_stock_threshold"], row["expiry_date"])
    if status == "Expired":
        return (
            "{} expired on {} and cannot be dispensed. Remove it from the shelf "
            "and dispense from an unexpired batch."
            .format(name, display_date(row["expiry_date"]))
        )

    if stock <= 0:
        return (
            "{} is out of stock, so none can be dispensed. Restock it on "
            "Medicine Inventory first.".format(name)
        )

    if quantity > stock:
        return (
            "Only {} of {} remain in stock, so {} cannot be dispensed. Restock "
            "before dispensing more than what is on the shelf."
            .format(_plural(stock, unit), name, _plural(quantity, unit))
        )

    return None


def _blamed_field(index, row, quantity):
    """Which of a line's two boxes a refusal should be reported against.

    The quantity box when the amount is the thing that has to change -- there is
    stock, just not that much of it -- and the item box for everything else,
    because an expired, retired or empty item cannot be fixed by typing a smaller
    number.

    Shared by check_dispensing() and record_dispensing() rather than written
    twice, for the reason _refusal() itself is shared: the two run the same rule
    at different moments, and a refusal that highlighted a different box before
    and after the save would be the same rule disagreeing with itself.
    """
    stock = row["stock_quantity"] or 0
    if stock > 0 and quantity > stock:
        return quantity_field(index)
    return item_field(index)


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
                "SELECT id, name, unit, category, status, stock_quantity, "
            "       low_stock_threshold, expiry_date "
            "FROM inventory_items WHERE id = ?",
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

            refusal = _refusal(row, entry["quantity"])
            if refusal:
                errors[_blamed_field(entry["index"], row, entry["quantity"])] = refusal

    return errors


class _Refused(Exception):
    """Raised inside record_dispensing()'s transaction to roll the whole lot back."""


def record_dispensing(patient_id, entries, dispensed_by, date_dispensed,
                      consultation_id=None):
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

    The decrement is itself guarded -- `AND stock_quantity >= ?` -- and its
    rowcount is checked. That is the third and last refusal of the insufficient
    stock block, after the form's and _refusal()'s, and it is the one that holds
    with no Python involved at all. If it ever fires, something upstream is
    wrong; it rolls back rather than writing a record whose stock movement did
    not happen.
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
                    "SELECT id, name, unit, category, status, stock_quantity, "
                "       low_stock_threshold, expiry_date "
                "FROM inventory_items WHERE id = ?",
                    (entry["item_id"],),
                ).fetchone()

                if row is None or row["category"] not in DISPENSABLE_CATEGORIES:
                    errors[item_field(entry["index"])] = (
                        "That item is no longer available to dispense. Pick one "
                    "from the list."
                    )
                    raise _Refused

                refusal = _refusal(row, entry["quantity"])
                if refusal:
                    errors[_blamed_field(entry["index"], row, entry["quantity"])] = refusal
                    raise _Refused

                # The same item, at the same visit, already on file. The table's
                # UNIQUE (consultation_id, inventory_item_id) would refuse the insert
                # below anyway -- that is the guarantee, and it is why the constraint
                # exists -- but it would refuse it by raising, which reaches the
                # operator as a failed request rather than as a sentence telling them
                # what is already recorded. So the constraint is asked *first*, in the
                # same transaction and under the same lock, and the refusal is worded.
                #
                # This is the check that makes a double-submitted form safe. The
                # second POST finds the first one's row, refuses the whole
                # submission, and rolls back -- so nothing is dispensed twice and no
                # stock moves twice.
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
                UPDATE inventory_items
                   SET stock_quantity = stock_quantity - ?,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND stock_quantity >= ?
                """,
                    (entry["quantity"], entry["item_id"], entry["quantity"]),
                )
                if cursor.rowcount != 1:
                    # Unreachable through the form -- _refusal() above has already
                    # compared the same two numbers on the same row inside the same
                    # lock. Kept because it is the refusal that does not depend on
                    # any of that being true.
                    errors[quantity_field(entry["index"])] = (
                        "{}'s stock changed while this was being saved, so nothing "
                    "was dispensed. Reload and try again.".format(row["name"])
                    )
                    raise _Refused

                conn.execute(
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

                stored.append({
                    "index": entry["index"],
                    "item_id": entry["item_id"],
                    "medicine_name": row["name"],
                    "unit": row["unit"],
                    "quantity_dispensed": entry["quantity"],
                    # What the shelf holds now, read off the figure this statement
                    # just wrote rather than recomputed. The flash message says it
                    # back to the operator, which is the moment a stock level is
                    # worth anything.
                    "stock_after": (row["stock_quantity"] or 0) - entry["quantity"],
                    "low_stock_threshold": row["low_stock_threshold"] or 0,
                })

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

    `viewer_role` None means "do not redact", which is the right default for the
    two callers that never put a diagnosis on a screen -- see each of them. Where
    a diagnosis IS shown, the role is compulsory at that function's own signature
    rather than defaulted here.

    WHY A DISPENSING ROW HAS TO BE REDACTED AT ALL.
    It does not hold a diagnosis; it joins to one. _DISPENSING_SELECT brings
    `c.diagnosis` along so the Dispensing History tab can print the column headed
    "For (Diagnosis)" without a query per row, and that column is on the same
    Patient Profile page whose Consultation History is sealed. Withholding the
    diagnosis in one tab and printing it two tabs across would be a seal that
    protects nothing -- and it is exactly the kind of second copy of a value that
    an access rule applied only at the obvious place leaves behind.
    """
    can_view = can_view_restricted(viewer_role) if viewer_role is not None else True
    records = [dict(row) for row in rows]
    for record in records:
        record["label"] = dispensing_label(record)
        record["quantity_text"] = _plural(
            record["quantity_dispensed"], record.get("unit")
        )
        record["consultation_restricted"] = bool(
            record.get("consultation_restricted")
        )
        if not can_view and record["consultation_restricted"]:
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
    dispensing itself is never withheld -- what was handed over is what a health
    worker needs in order to do their job, and none of it is sealed.
    """
    with db_connection() as conn:
        rows = conn.execute(
            _DISPENSING_SELECT
            + " WHERE d.patient_id = ? ORDER BY d.date_dispensed DESC, d.id DESC",
            (patient_id,),
        ).fetchall()
    return _to_records(rows, viewer_role)


def get_dispensing_for_consultation(consultation_id):
    """The items issued during one visit, oldest row first.

    Not redacted, and it does not need to be: its two callers are the "already
    dispensed at this visit" list on the consultation form and the same list in
    the profile's per-visit detail panel, and both print the medicine, the
    quantity and who issued it. Neither reads consultation_diagnosis, so there is
    nothing on this path for a seal to withhold.
    """
    if not consultation_id:
        return []
    with db_connection() as conn:
        rows = conn.execute(
            _DISPENSING_SELECT + " WHERE d.consultation_id = ? ORDER BY d.id",
            (consultation_id,),
        ).fetchall()
    return _to_records(rows)


def get_dispensing_by_consultation(consultation_ids):
    """{consultation_id: [record, ...]} for a list of visits, in one query.

    The Recent Consultations table on the Administrator dashboard has a Dispensed
    column and prints five rows. Asking per row would be five queries for a panel
    that already has its consultations in hand; this is one.

    Not redacted, for the reason get_dispensing_for_consultation() above is not:
    the only screen behind it is that dashboard panel, which prints the medicines
    and reads no diagnosis from these rows. That is the whole reason, and it is
    worth saying because a second one used to be given: the panel is on the
    Administrator's dashboard only. That no longer helps -- the Administrator may
    not read a sealed diagnosis either -- so the safety rests on no diagnosis
    being read here at all, which is true of the query, not of who calls it.
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
    for record in _to_records(rows):
        grouped.setdefault(record["consultation_id"], []).append(record)
    return grouped


# How many medicines the most-dispensed list ranks. Matches
# models.consultations.TOP_DIAGNOSIS_LIMIT so the two ranked panels on Reports &
# Analytics are the same length and read as a pair.
TOP_MEDICINE_LIMIT = 5


def get_dispensing_stats(months=6, limit=TOP_MEDICINE_LIMIT, on_date=None,
                         start=None, end=None):
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

    THE RANKING IS BY medicine_name, THE SNAPSHOT, NOT BY ITEM. Two rows share a
    line only if they say the same thing. If an inventory row is renamed
    mid-range -- which the Edit Medicine form allows and which is how the supplier
    and location corrections in this project were made -- the issues before and
    after appear under the names they were actually recorded with, rather than
    being pooled under whichever name the item happens to carry today. A report
    of what was dispensed should read back what the records say.

    date_dispensed is clinic-local date text, exactly as consultation_date is, so
    the range compares against its leading ten characters with no timezone
    conversion.
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

        scoped = conn.execute(
            """
        SELECT medicine_name, unit, quantity_dispensed, patient_id,
               inventory_item_id, substr(date_dispensed, 1, 7) AS month
        FROM medicine_dispensing
        WHERE substr(date_dispensed, 1, 10) BETWEEN ? AND ?
        """,
            (lo, hi),
        ).fetchall()

    units_by_month, events_by_month = {}, {}
    by_medicine = {}
    for row in scoped:
        month = row["month"]
        units_by_month[month] = units_by_month.get(month, 0) + row["quantity_dispensed"]
        events_by_month[month] = events_by_month.get(month, 0) + 1
        entry = by_medicine.setdefault(
            row["medicine_name"],
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
    for entry in ranked:
        entry["units_text"] = _plural(entry["units"], entry["unit"])

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
            "medicines": len(by_medicine),
            "trend": trend,
            "top_medicines": ranked[:limit],
            "all_medicines": ranked,
        },
    }
