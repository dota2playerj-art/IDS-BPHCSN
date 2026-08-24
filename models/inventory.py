"""Medicine and supply inventory queries.

Like models/patients.py, the read functions return plain dicts rather than
sqlite3.Row objects: Screen 06 renders a stock status, a badge class and a
progress bar that are all derived from stock_quantity, low_stock_threshold and
expiry_date rather than stored. sqlite3.Row is read-only, so each row is copied
into a dict and the derived keys are added alongside.
"""
from datetime import datetime

from database.connection import get_db
from utils.dates import today

# The vocabularies the Add/Edit Medicine form offers. The template renders its
# <select> options from these same tuples, so a constrained field cannot accept a
# value the form never offered, and the two cannot drift apart.
#
# ITEM_CATEGORIES is the item *type* and matches the inventory_items.category
# CHECK exactly -- a value outside it would be rejected by the database.
ITEM_CATEGORIES = ("Medicine", "Supply", "Equipment")

# The therapeutic classification, stored in drug_class. The first six are the
# options Screen 06's filter panel and Screen 07's "Category" dropdown already
# listed; the last two were added so the seeded Cetirizine and Salbutamol have an
# honest class instead of being filed under a heading that does not describe them.
DRUG_CLASSES = (
    "Antihypertensive",
    "Analgesic / Antipyretic",
    "Antibiotic",
    "Antidiabetic",
    "Vitamins & Supplements",
    "Oral Rehydration",
    "Antihistamine",
    "Bronchodilator",
)

# Screen 07 listed six dosage forms and six units; "Nebule", "Piece" and "Pack"
# are added because the inventory also holds nebules and non-dosed supplies.
DOSAGE_FORMS = ("Tablet", "Capsule", "Syrup", "Sachet", "Injection", "Ointment", "Nebule")
UNITS = ("Tablet", "Capsule", "Bottle", "Sachet", "Vial", "Box", "Piece", "Pack")

ITEM_STATUSES = ("Active", "Inactive")

# Human wording for the "what changed" line flashed after a save. Keyed by column
# so the message names the field the operator sees on the form, not the column.
FIELD_LABELS = {
    "name": "Medicine name",
    "generic_name": "Generic name",
    "brand_name": "Brand name",
    "category": "Item type",
    "drug_class": "Category",
    "dosage_strength": "Dosage strength",
    "dosage_form": "Dosage form",
    "unit": "Unit of measure",
    "stock_quantity": "Current stock",
    "low_stock_threshold": "Reorder level",
    "expiry_date": "Expiration date",
    "date_received": "Date received",
    "batch_number": "Batch number",
    "manufacturer": "Manufacturer",
    "supplier": "Supplier",
    "unit_cost": "Unit cost",
    "storage_location": "Storage location",
    "notes": "Notes",
    "status": "Status",
}

# Fields marked with * on the form and required for every item regardless of type.
REQUIRED_FIELDS = {
    "name": "Medicine name is required.",
    "category": "Item type is required.",
    "unit": "Unit of measure is required.",
    "date_received": "Date received is required.",
    "stock_quantity": "Current stock is required.",
    "low_stock_threshold": "Reorder level is required.",
    "status": "Status is required.",
}

# Also marked with * on the form, but only meaningful for an actual medicine: a
# box of gauze has no generic name, dosage strength or expiry batch. Requiring
# these of every row would make Supply and Equipment items unaddable and their
# stock uneditable, so they are enforced only when category == 'Medicine'.
MEDICINE_ONLY_REQUIRED_FIELDS = {
    "generic_name": "Generic name is required for a medicine.",
    "drug_class": "Category is required for a medicine.",
    "dosage_strength": "Dosage strength is required for a medicine.",
    "dosage_form": "Dosage form is required for a medicine.",
    "batch_number": "Batch number is required for a medicine.",
    "expiry_date": "Expiration date is required for a medicine.",
}

# Every column the form writes, in one place so the INSERT, the UPDATE and the
# redisplay cannot fall out of step. item_code, created_at and updated_at are
# absent on purpose: the first is auto-assigned, the other two are timestamps.
INVENTORY_FIELDS = (
    "name", "generic_name", "brand_name", "category", "drug_class",
    "dosage_strength", "dosage_form", "unit", "stock_quantity",
    "low_stock_threshold", "expiry_date", "date_received", "batch_number",
    "manufacturer", "supplier", "unit_cost", "storage_location", "notes",
    "status",
)

# Stored as numbers rather than text, so they are normalised apart from the rest.
INTEGER_FIELDS = ("stock_quantity", "low_stock_threshold")
DECIMAL_FIELDS = ("unit_cost",)
TEXT_FIELDS = tuple(
    field for field in INVENTORY_FIELDS
    if field not in INTEGER_FIELDS + DECIMAL_FIELDS
)

# An item expiring within this many days is flagged for review before use. Screen
# 06's third stat card names the window explicitly ("Near Expiry (90 days)"), and
# get_status_distribution() and the dashboards all read this same constant, so the
# window is stated once for the whole project.
NEAR_EXPIRY_DAYS = 90

# The stored lifecycle status that takes an item out of service. It is one of
# ITEM_STATUSES above, set on the Add / Edit Medicine form, and until now it was
# written by that form and read by nothing at all: an Inactive item still sat in
# the list looking stocked, still counted in all four stat cards, and could still
# raise a low-stock alert on both dashboards, the sidebar badge and Reports &
# Analytics. Naming it here is what lets every operating figure below agree on
# which rows are in service.
#
# It is deliberately the same soft flag patients have -- schema.sql calls it "a
# soft lifecycle flag, as on patients" -- and it retires a row rather than
# removing one. Nothing is deleted and no history is lost; the row keeps its
# batch number, its expiry date and its stock figure, and going back to Active
# restores it everywhere.
RETIRED_STATUS = "Inactive"

# stock status -> the badge class Screen 06's stylesheet defines.
STATUS_BADGE_CLASS = {
    # Retired is not a stock condition and is not returned by stock_status(). It
    # is what Screen 06 shows *instead* of one for an item out of service, since
    # "Low Stock" on something nobody is restocking is exactly the sentence this
    # badge should never say.
    "Retired": "badge-retired",
    "In Stock": "badge-instock",
    "Low Stock": "badge-lowstock",
    "Critical": "badge-critical",
    "Out of Stock": "badge-critical",
    "Near Expiry": "badge-nearexpiry",
    "Expires Today": "badge-expirestoday",
    "Expired": "badge-expired",
}


# Screen 06's Sort control, Status column. The order is stock_status()'s own
# resolution order -- the sequence its docstring lays out and its `if` ladder
# walks, most urgent first -- so "sort by status" groups the shelf the same way
# the badge already decides what to call each item. Sorting these alphabetically
# would open on Critical and bury Out of Stock between Near Expiry and In Stock,
# which is the opposite of what a pharmacist opens this screen to find.
#
# "Retired" is not a stock condition and stock_status() never returns it, so it
# is not in that ladder; it goes last here because an item nobody is restocking
# is the least urgent thing on the shelf, which is the same judgement in_service()
# already makes when it keeps retired items out of the low-stock alert.
STATUS_SORT_ORDER = (
    "Out of Stock",
    "Expired",
    "Expires Today",
    "Critical",
    "Low Stock",
    "Near Expiry",
    "In Stock",
    "Retired",
)


def status_rank(display_status):
    """Where a status sits in STATUS_SORT_ORDER, or None if it is not one.

    None rather than a large number on purpose: the sort holds unknown values at
    the bottom in both directions, and a status this module does not recognise is
    exactly that -- an absence of a known rank, not a very unurgent item.
    """
    return (
        STATUS_SORT_ORDER.index(display_status)
        if display_status in STATUS_SORT_ORDER else None
    )


def allowed_item_status_transitions(current_status):
    """The statuses an item currently in current_status may be moved to.

    Every status except the one it already holds, in ITEM_STATUSES order, which
    on a two-value lifecycle yields exactly the two cases the Archive dialog
    offers:

        Active   -> Inactive   (retire it)
        Inactive -> Active     (put it back in service)

    The second direction is deliberate, and it is the one
    models/patients.py allowed_status_transitions() argues for at length:
    retiring the wrong row is a mis-click, and a one-way door turns a clerical
    slip into something only an edit form can undo.

    An unrecognised status (a hand-edited row) yields both, so the dialog still
    offers a way out rather than presenting no options at all.

    The caller passes the status it read back out of the database, never the one
    the page posted: the dialog decides what to offer from a page that can be
    stale, and a POST can be made without loading that page at all. That is the
    same reason get_patient_statuses() exists on the patient side; here the
    fresh read is get_inventory_item_by_id(), which the caller already needs for
    the item's name, so there is no second query for the same row.
    """
    return tuple(status for status in ITEM_STATUSES if status != current_status)


def _parse_date(value):
    """Read a stored ISO date into a date, or None if it is absent/malformed."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def days_until_expiry(expiry_date, on_date=None):
    """Whole days from on_date (default today) until expiry_date, or None.

    Negative once the date has passed, which is what makes the expired check a
    plain comparison against zero.
    """
    parsed = _parse_date(expiry_date)
    if parsed is None:
        return None
    return (parsed - (on_date or today())).days


def stock_status(stock_quantity, low_stock_threshold, expiry_date, on_date=None):
    """The single status badge Screen 06 shows for one item.

    An item can be several of these at once -- low on stock *and* near expiry --
    but the table has one badge, so they are resolved in order of how urgently
    each demands action:

      Out of Stock   nothing on the shelf; whether it also expired is moot
      Expired        physically present but must not be dispensed
      Expires Today  still dispensable today, unusable tomorrow
      Critical       at or below half the reorder level
      Low Stock      at or below the reorder level
      Near Expiry    usable for a while yet, review before it lapses
      In Stock       nothing to flag

    The expiry tiers follow standard pharmacy practice: the printed date is a
    "use by", not a "discard before", so an item is usable *through* the whole of
    its expiry date and only becomes Expired the day after. That is why the
    Expired test is `remaining < 0` rather than `<= 0`, and why day zero has its
    own tier instead of sharing one with something ninety days out.

    "Expires Today" sits directly below Expired and above the stock tiers for the
    same reason Expired does: a deadline that lands today outranks a restocking
    level, because no amount of restocking makes today's stock last past midnight.

    The stat cards deliberately do *not* use this: they count each condition
    independently, so an item that is both low and near expiry is counted in both
    totals rather than being claimed by whichever won here.
    """
    stock = stock_quantity or 0
    threshold = low_stock_threshold or 0
    remaining = days_until_expiry(expiry_date, on_date)

    if stock == 0:
        return "Out of Stock"
    if remaining is not None and remaining < 0:
        return "Expired"
    if remaining == 0:
        return "Expires Today"
    if stock <= threshold:
        # Half the reorder level or less is the point at which a restock stops
        # being routine, matching the mockup's separate "Critical" badge.
        return "Critical" if stock * 2 <= threshold else "Low Stock"
    if remaining is not None and remaining <= NEAR_EXPIRY_DAYS:
        return "Near Expiry"
    return "In Stock"


def _stock_bar(stock_quantity, low_stock_threshold):
    """Percentage fill and colour class for the stock bar on Screen 06.

    There is no "full shelf" column to measure against, so the reorder level is
    the reference point: the bar reads half full exactly at the threshold and
    full at twice it. That keeps the bar honest about the only capacity figure
    the record actually carries, instead of inventing a maximum.
    """
    stock = stock_quantity or 0
    threshold = low_stock_threshold or 0

    if threshold <= 0:
        # No reorder level set, so there is nothing to be low against.
        return (100 if stock > 0 else 0), "fill-good"

    percent = min(100, round(stock / (threshold * 2) * 100))
    if stock <= threshold * 0.5:
        fill = "fill-low"
    elif stock <= threshold:
        fill = "fill-warn"
    else:
        fill = "fill-good"
    return percent, fill


def _display_dosage(row):
    """'500mg' + 'Capsule' -> '500mg Capsule'. Screen 06's Dosage / Form column."""
    parts = [row["dosage_strength"], row["dosage_form"]]
    return " ".join(str(part).strip() for part in parts if part)


def _to_item(row, on_date=None):
    """Copy an inventory_items row into a dict and add the derived display fields."""
    item = dict(row)
    status = stock_status(
        item.get("stock_quantity"),
        item.get("low_stock_threshold"),
        item.get("expiry_date"),
        on_date,
    )
    percent, fill_class = _stock_bar(
        item.get("stock_quantity"), item.get("low_stock_threshold")
    )

    # stock_status stays the pure stock condition whatever the item's lifecycle
    # status is -- it is a fact about the shelf, and a retired item can still be
    # short or expired. What changes for a retired item is not the fact but who
    # is in scope for it, and that is decided once, in in_service() below, rather
    # than by quietly rewriting the fact here.
    item["stock_status"] = status
    item["is_retired"] = item.get("status") == RETIRED_STATUS

    # What Screen 06 puts in its Status column. A retired row shows "Retired"
    # rather than a stock condition it is not being judged on, which also puts
    # the value into that screen's existing Status filter -- so retired items are
    # reachable through the one control that already filters by status, exactly
    # as Inactive and Deceased patients are on Patient Records, instead of
    # needing a "show retired" toggle this project has nowhere else.
    item["display_status"] = "Retired" if item["is_retired"] else status
    item["status_badge_class"] = STATUS_BADGE_CLASS.get(
        item["display_status"], "badge-instock"
    )
    # For Screen 06's Sort control; see STATUS_SORT_ORDER above. Ranked on
    # display_status rather than stock_status so the sort groups by what the
    # Status column actually shows -- a retired item sorts as Retired, which is
    # what its badge says and what the Status filter beside it matches on.
    item["status_rank"] = status_rank(item["display_status"])
    item["stock_percent"] = percent
    item["stock_fill_class"] = fill_class
    item["days_until_expiry"] = days_until_expiry(item.get("expiry_date"), on_date)
    item["display_dosage"] = _display_dosage(row)
    item["is_low_stock"] = (item.get("stock_quantity") or 0) <= (
        item.get("low_stock_threshold") or 0
    )
    item["is_out_of_stock"] = (item.get("stock_quantity") or 0) == 0
    # Expiry facts, exposed as flags so no template has to re-derive them from the
    # day count and reach a different answer about where the boundaries fall.
    item["expires_today"] = item["days_until_expiry"] == 0
    item["is_expired"] = (
        item["days_until_expiry"] is not None and item["days_until_expiry"] < 0
    )
    item["threshold_pct"] = _threshold_pct(
        item.get("stock_quantity"), item.get("low_stock_threshold")
    )
    return item


def _threshold_pct(stock_quantity, low_stock_threshold):
    """Stock as a percentage of this item's own reorder level, or None.

    This is what the dashboard alert panels read as "% of reorder level": 100%
    means the stock has just landed on the reorder point, and anything under it
    is short by that proportion. Distinct from _stock_bar()'s percentage, which
    measures a bar against a comfortably-stocked shelf rather than the threshold.

    None when no reorder level is set, because there is then nothing to be a
    percentage of.
    """
    threshold = low_stock_threshold or 0
    if threshold <= 0:
        return None
    return round((stock_quantity or 0) / threshold * 100)


def get_all_inventory_items():
    """Every inventory item, ordered by name."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM inventory_items ORDER BY name COLLATE NOCASE"
    ).fetchall()
    conn.close()
    return [_to_item(row) for row in rows]


def get_inventory_item_by_id(item_id):
    """One inventory item by primary key, or None if no such row exists."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM inventory_items WHERE id = ?", (item_id,)
    ).fetchone()
    conn.close()
    return _to_item(row) if row else None


def in_service(items):
    """The items every operating figure in this module is computed over.

    One definition of "in scope", read by the stat cards, the status doughnut and
    the low-stock alert, so those three cannot come to disagree about whether a
    retired item counts. An item the health centre has stopped stocking is not
    short of stock in any sense that asks somebody to reorder it, is not awaiting
    disposal off a shelf it is no longer on, and is not part of how the working
    inventory divides up.

    This is the pattern the project already uses for patients, not a new one. The
    roster on Patient Records lists every patient whatever their status, and the
    exclusion of the non-Active ones happens further out, in the derived lists
    where being non-Active changes what should be done: the SMS audience excludes
    them in its SQL (models/broadcasts.py) and the immunisation follow-up list and
    coverage denominator exclude them in Python (models/immunizations.py), each
    for a reason particular to what that list is for. This is the inventory's
    version of the same step.

    Deliberately NOT applied in get_all_inventory_items(). Hiding retired rows
    from Screen 06 would contradict the promise the equivalent patient dialog
    makes -- "the patient stays listed here under the new status" -- and would
    leave an operator no way to see, or undo, a retirement. They stay listed,
    badged "Retired", and filterable by that value; they simply stop being
    counted.
    """
    return [item for item in items if not item["is_retired"]]


def get_inventory_stats(items=None):
    """Counts behind the four stat cards on Screen 06.

    Every figure is computed from the rows themselves rather than stored, so a
    stock edit that crosses a threshold moves the cards on the next render with
    nothing else to keep in step. `items` may be passed in to avoid a second
    query when the caller has already loaded the list.

    Retired items are excluded from all four cards by in_service(). The cards
    report the working inventory, while the table below them lists every row, so
    the two would appear to disagree whenever anything is retired -- and rather
    than let a reader guess, retired_count is returned alongside so Screen 06 can
    name the difference in words instead of leaving it to be discovered.
    """
    if items is None:
        items = get_all_inventory_items()

    retired_count = sum(1 for item in items if item["is_retired"])
    items = in_service(items)

    low_stock = [item for item in items if item["is_low_stock"]]
    out_of_stock = [item for item in items if item["is_out_of_stock"]]
    # "Expires Today" is a badge tier, not a separate counting bucket: day zero is
    # inside the near-expiry window, so it stays counted here. Splitting it out
    # would silently drop the Near Expiry card by one on the very day an item
    # becomes most urgent, which is the opposite of what that card is for. The
    # separate expires_today_count below is a subset of this figure, not a rival.
    near_expiry = [
        item
        for item in items
        if item["days_until_expiry"] is not None
        and 0 <= item["days_until_expiry"] <= NEAR_EXPIRY_DAYS
    ]
    expires_today = [item for item in items if item["expires_today"]]
    expired = [item for item in items if item["is_expired"]]

    return {
        "total_items": len(items),
        "medicine_count": sum(1 for item in items if item["category"] == "Medicine"),
        "retired_count": retired_count,
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "near_expiry_count": len(near_expiry),
        "expires_today_count": len(expires_today),
        "expired_count": len(expired),
        "near_expiry_days": NEAR_EXPIRY_DAYS,
    }


def get_status_distribution(items=None):
    """The four segments of Screen 10's Medicine Inventory Status doughnut.

    A doughnut has to partition its total, so each item is counted exactly once,
    under the most urgent condition that applies to it:

      Low Stock    at or below its own reorder level (out-of-stock included)
      Expired      not short, but past its expiry date
      Near Expiry  not short and not expired, but lapsing within the window
      In Stock     nothing to flag

    Low Stock is resolved *first* specifically so this segment always equals the
    low_stock_count reported by the dashboards, the sidebar badge and Medicine
    Inventory. An item that is both short and expired lands in Low Stock here,
    where the badge on Screen 06 would call it Expired -- the two answer different
    questions (what is the one thing to say about this row, versus how does the
    whole inventory divide up for restocking), and only this one has to add up.

    The counts therefore sum to total_items, which the legend and the panel
    subtitle both rely on.

    An item expiring *today* is counted under Near Expiry, not Expired: it is
    still dispensable for the rest of the day, and the Expired segment is what a
    reader will treat as "must be pulled from the shelf". It keeps its own
    "Expires Today" badge on Screen 06 -- the badge answers what to do about one
    row, this chart answers how the shelf divides up, and those differ.

    Retired items are excluded by in_service(), which the Low Stock invariant
    above actually requires: that segment is promised to equal the low_stock_count
    the dashboards and the sidebar badge report, and those now exclude retired
    items, so counting them here would break the one thing this function is
    documented to guarantee. `total` is therefore the working inventory too, which
    is what the legend and the panel subtitle are describing.
    """
    if items is None:
        items = get_all_inventory_items()

    items = in_service(items)
    low_stock = expired = near_expiry = in_stock = 0
    for item in items:
        remaining = item["days_until_expiry"]
        if item["is_low_stock"]:
            low_stock += 1
        elif item["is_expired"]:
            expired += 1
        elif remaining is not None and remaining <= NEAR_EXPIRY_DAYS:
            near_expiry += 1
        else:
            in_stock += 1

    return {
        "in_stock": in_stock,
        "low_stock": low_stock,
        "near_expiry": near_expiry,
        "expired": expired,
        "total": len(items),
    }


def get_inventory_report():
    """Stock-level summary for Screen 10.

    Predates the rest of this module and keeps its original keys, since Reports &
    Analytics is rendered from them for both roles that reach it. The items are
    the same enriched dicts the inventory screen uses, so a report can show the
    stock status without recomputing it.

    The counts and the ordered low-stock list come from get_low_stock_alert() --
    the same call behind the two dashboards and the sidebar badge -- so Screen 10
    cannot report a different low-stock figure from the rest of the project.

    Every figure here is over the working inventory: `items` is narrowed by
    in_service() before anything is counted from it, so the totals, the
    out-of-stock list and the doughnut all describe the same set of rows that the
    low-stock list does. A report that counted retired items in its total while
    the alert beside it did not would be the same disagreement this function was
    written to prevent, one level up.
    """
    items = in_service(get_all_inventory_items())
    alert = get_low_stock_alert()

    return {
        "items": items,
        "total_items": len(items),
        # Ordered most-critical-first by get_low_stock_alert(), which is the order
        # Screen 10's Low Stock Medicines list wants to read them in.
        "low_stock_items": alert["low_stock_items"],
        "out_of_stock_items": [item for item in items if item["is_out_of_stock"]],
        "low_stock_count": alert["low_stock_count"],
        "out_of_stock_count": alert["out_of_stock_count"],
        "status_distribution": get_status_distribution(items),
    }


def _criticality(item):
    """Sort key putting the item in most urgent need of restocking first.

    Stock as a fraction of its own reorder level, so a per-item comparison rather
    than a raw quantity: 15 of a 60 reorder level outranks 90 of a 90 one, even
    though 90 is the larger number.

    Ties are broken by how many units short the item is, largest first. Without
    that, every out-of-stock item scores 0.0 and their order falls out of however
    the rows arrived -- so an item needing 40 units could be listed below one
    needing 1. Items with no reorder level sort last; they cannot be judged short.
    """
    threshold = item.get("low_stock_threshold") or 0
    stock = item.get("stock_quantity") or 0
    if threshold <= 0:
        return (1, 0, 0)
    return (0, stock / threshold, -(threshold - stock))


def get_low_stock_alert(limit=None):
    """The in-system low-stock alert behind the dashboards and the sidebar badge.

    Proposal Objective 2 asks for staff to be alerted when stock falls below the
    defined threshold. This is that alert: every screen that reports a low-stock
    figure reads it from here, so the dashboard stat card, the sidebar badge and
    the detail panel cannot disagree with each other or with Medicine Inventory.
    All of them ultimately derive from the same per-item is_low_stock flag set in
    _to_item().

    `limit` caps only the returned item list, never the counts -- a panel with
    room for five rows still reports the true total above them.

    The list is keyed "low_stock_items" rather than the more obvious "items"
    because this dict is handed to Jinja, where `low_stock.items` would resolve
    to dict.items -- the built-in method -- and silently iterate nothing.

    Retired items are excluded by in_service(), and this is the exclusion that
    matters most: an item the centre has stopped stocking cannot be "below its
    reorder level" in any sense that asks somebody to go and reorder it. Because
    every low-stock figure in the project reads this one function, that exclusion
    reaches the sidebar badge, both dashboards and Reports & Analytics without any
    of them being touched -- which is the whole reason the figure was centralised
    here.
    """
    items = in_service(get_all_inventory_items())
    low_stock = sorted(
        (item for item in items if item["is_low_stock"]), key=_criticality
    )

    return {
        "low_stock_items": low_stock if limit is None else low_stock[:limit],
        "low_stock_count": len(low_stock),
        "out_of_stock_count": sum(1 for item in items if item["is_out_of_stock"]),
        "total_items": len(items),
    }


def _parse_int(raw):
    """('12', True) for a valid non-negative integer, (None, False) otherwise."""
    text = str(raw or "").strip()
    if not text:
        return None, False
    try:
        value = int(text)
    except ValueError:
        return None, False
    return value, value >= 0


def _parse_decimal(raw):
    """('8.5', True) for a valid non-negative number, (None, False) otherwise."""
    text = str(raw or "").strip()
    if not text:
        return None, False
    try:
        value = float(text)
    except ValueError:
        return None, False
    return value, value >= 0


def validate_inventory_form(values):
    """Server-side validation. Returns {field: message}; empty means valid.

    Runs independently of the browser -- the form carries `novalidate`, and a
    POST can arrive without ever touching the page.
    """
    errors = {}

    for field, message in REQUIRED_FIELDS.items():
        if not (values.get(field) or "").strip():
            errors[field] = message

    category = (values.get("category") or "").strip()
    if category and category not in ITEM_CATEGORIES:
        errors["category"] = "Choose an item type from the list."

    # The medicine-only fields; see MEDICINE_ONLY_REQUIRED_FIELDS.
    if category == "Medicine":
        for field, message in MEDICINE_ONLY_REQUIRED_FIELDS.items():
            if not (values.get(field) or "").strip():
                errors[field] = message

    # Constrained fields: reject anything the form does not itself offer.
    for field, allowed, label in (
        ("drug_class", DRUG_CLASSES, "category"),
        ("dosage_form", DOSAGE_FORMS, "dosage form"),
        ("unit", UNITS, "unit of measure"),
        ("status", ITEM_STATUSES, "status"),
    ):
        value = (values.get(field) or "").strip()
        if value and field not in errors and value not in allowed:
            errors[field] = f"Choose a {label} from the list."

    for field, label in (
        ("stock_quantity", "Current stock"),
        ("low_stock_threshold", "Reorder level"),
    ):
        raw = (values.get(field) or "").strip()
        if raw and field not in errors:
            _, ok = _parse_int(raw)
            if not ok:
                errors[field] = f"{label} must be a whole number of 0 or more."

    unit_cost = (values.get("unit_cost") or "").strip()
    if unit_cost:
        _, ok = _parse_decimal(unit_cost)
        if not ok:
            errors["unit_cost"] = "Unit cost must be a number of 0 or more."

    # Expiry may legitimately be in the past -- an expired batch still sits on the
    # shelf awaiting disposal, and Screen 06 has a badge for exactly that -- so
    # only the format is checked here.
    expiry_date = (values.get("expiry_date") or "").strip()
    if expiry_date and "expiry_date" not in errors:
        if _parse_date(expiry_date) is None:
            errors["expiry_date"] = "Enter a valid date in YYYY-MM-DD format."

    date_received = (values.get("date_received") or "").strip()
    if date_received and "date_received" not in errors:
        parsed = _parse_date(date_received)
        if parsed is None:
            errors["date_received"] = "Enter a valid date in YYYY-MM-DD format."
        elif parsed > today():
            errors["date_received"] = "Date received cannot be in the future."

    return errors


def _build_record(values):
    """Normalise submitted form values into the column values to store.

    Shared by create_inventory_item() and update_inventory_item() so an insert
    and an edit can never normalise the same field differently.
    """
    record = {field: (values.get(field) or "").strip() or None for field in TEXT_FIELDS}

    for field in INTEGER_FIELDS:
        value, ok = _parse_int(values.get(field))
        # Validation has already rejected a malformed figure; a blank one on a
        # field that is not required stores as 0, matching the column default.
        record[field] = value if ok else 0

    for field in DECIMAL_FIELDS:
        value, ok = _parse_decimal(values.get(field))
        record[field] = value if ok else None

    return record


def create_inventory_item(values):
    """Insert an inventory item and return its new primary key.

    created_at and updated_at are left to their DEFAULT CURRENT_TIMESTAMP.
    """
    record = _build_record(values)

    columns = ["item_code"] + list(INVENTORY_FIELDS)
    placeholders = ", ".join("?" for _ in columns)
    parameters = [generate_next_item_code()] + [record[f] for f in INVENTORY_FIELDS]

    conn = get_db()
    cursor = conn.execute(
        f"INSERT INTO inventory_items ({', '.join(columns)}) VALUES ({placeholders})",
        parameters,
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def update_inventory_item(item_id, values):
    """Overwrite one item's form-collected fields.

    Deliberately leaves item_code and created_at alone -- the identifier and the
    date the item entered the system are historical fact -- and refreshes
    updated_at, which is what makes "last updated" on a stock edit meaningful.

    Returns the list of fields that actually changed, as
    [{"field", "label", "old", "new"}, ...]. An empty list means the submitted
    form carried exactly the stored values, which is a real and confusing outcome
    for an operator -- the row's updated_at moves but nothing they can see
    differs, so it looks indistinguishable from a save that was silently dropped.
    The caller uses this to say which is which instead of flashing an
    unconditional "updated".
    """
    record = _build_record(values)

    conn = get_db()
    before = conn.execute(
        "SELECT * FROM inventory_items WHERE id = ?", (item_id,)
    ).fetchone()
    if before is None:
        conn.close()
        return []

    changes = [
        {
            "field": field,
            "label": FIELD_LABELS.get(field, field),
            "old": before[field],
            "new": record[field],
        }
        for field in INVENTORY_FIELDS
        if before[field] != record[field]
    ]

    assignments = ", ".join(f"{field} = ?" for field in INVENTORY_FIELDS)
    parameters = [record[field] for field in INVENTORY_FIELDS] + [item_id]
    conn.execute(
        f"UPDATE inventory_items SET {assignments}, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        parameters,
    )
    conn.commit()
    conn.close()
    return changes


def set_item_status(item_id, status):
    """Move one item between Active and Inactive. Returns rows changed.

    This is the whole of the Archive action on Screen 06, and it is deliberately
    the same shape as set_patient_status(): retiring is an UPDATE of one already
    existing flag and nothing else. No row is removed, item_code, created_at, the
    batch number, the expiry date and the stock figure are all untouched, and
    only updated_at moves alongside the status -- which is why going back to
    Active restores the item everywhere it was counted before.

    It writes the same column the Add / Edit Medicine form writes, so there is
    one definition of retired in the system and every figure that already
    respects RETIRED_STATUS respects this the moment it commits. Nothing here
    re-implements that logic.

    `AND status != ?` makes the count honest, exactly as it does on patients:
    SQLite's rowcount reports rows matched, not rows changed, so without it
    re-retiring an already-Inactive item would claim an update that did not
    happen and would bump updated_at for a write that changed nothing.
    """
    if status not in ITEM_STATUSES:
        raise ValueError(
            f"{status!r} is not an item status; expected one of {ITEM_STATUSES}."
        )

    conn = get_db()
    cursor = conn.execute(
        """
        UPDATE inventory_items
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status != ?
        """,
        (status, int(item_id), status),
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected


def generate_next_item_code():
    """Next free identifier in the existing MED-#### series.

    Reads the highest number currently in use rather than counting rows, so a gap
    left by an earlier record cannot cause a UNIQUE collision. Four digits to
    match the reference Screen 07 displays ("MED-0037"); a series past MED-9999
    simply grows wider.

    One series covers medicines, supplies and equipment alike, because item_code
    is UNIQUE across the whole table and the screen these codes appear on is
    Medicine Inventory.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT item_code FROM inventory_items WHERE item_code LIKE 'MED-%'"
    ).fetchall()
    conn.close()

    highest = 0
    for row in rows:
        suffix = str(row["item_code"]).split("-", 1)[1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))

    return f"MED-{highest + 1:04d}"
