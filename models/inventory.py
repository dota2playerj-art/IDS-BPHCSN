"""Medicine and supply inventory: items, and the batches their stock is kept in.

An item is a kind of thing the health center stocks. A medicine is defined by its generic
name, strength and dosage form (RA 6675, the Generics Act, asks government health agencies
to use generic names); its display name is built from them. The stock of an item is the
sum of its usable batches: each delivery is a batch with its own lot, expiry date, source
and brand. A batch past its expiry date is Expired and is never counted or dispensed.

The read functions return plain dicts rather than sqlite3.Row objects: the screens render
a stock status, a badge class and a progress bar that are derived, not stored.
"""
import math
import re
from datetime import datetime

from config import EXPIRING_SOON_DAYS
from database.connection import db_connection
from utils.dates import today

# The vocabularies the forms offer. The templates render their <select> options from these
# same tuples, so a constrained field cannot accept a value the form never offered.
#
# ITEM_CATEGORIES is the item *type* and matches the inventory_items.category CHECK. A
# Medicine is named by generic name, strength and form; a Supply or Equipment item has a
# simple item name and a size.
ITEM_CATEGORIES = ("Medicine", "Supply", "Equipment")
MEDICINE_CATEGORY = "Medicine"

# The therapeutic classification, stored in drug_class.
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

# The one list of dosage forms.
DOSAGE_FORMS = ("tablet", "capsule", "syrup", "suspension", "drops", "sachet",
                "injection", "cream", "ointment", "inhaler", "other")
UNITS = ("Tablet", "Capsule", "Bottle", "Sachet", "Vial", "Box", "Piece", "Pack")

ITEM_STATUSES = ("Active", "Inactive")

# Where a delivery came from, and why stock is taken out of a batch.
STOCK_SOURCES = ("DOH", "Municipal Health Office / RHU", "Barangay purchase", "Donation",
                 "Other")
REMOVAL_REASONS = ("Expired", "Damaged", "Lost", "Returned", "Count correction")
# What the lot number says when a delivery had none. Allowed only with the tick box.
NO_LOT_NUMBER = "No lot number"
# The cap on one delivery or one removal. A typo guard, not a storage limit.
MAX_QUANTITY = 100000

# Human wording for the "what changed" line flashed after Edit details.
FIELD_LABELS = {
    "generic_name": "Generic name",
    "category": "Item type",
    "drug_class": "Category",
    "dosage_strength": "Strength",
    "dosage_form": "Dosage form",
    "unit": "Unit of measure",
    "low_stock_threshold": "Reorder level",
    "manufacturer": "Manufacturer",
    "supplier": "Supplier",
    "unit_cost": "Unit cost",
    "storage_location": "Storage location",
    "notes": "Notes",
    "status": "Status",
}
SUPPLY_FIELD_LABELS = {"generic_name": "Item name", "dosage_strength": "Size"}

# The columns Edit details writes, apart from the display name. item_code, created_at and
# updated_at are absent on purpose: the first is auto-assigned, the other two are timestamps.
ITEM_FIELDS = (
    "generic_name", "category", "drug_class", "dosage_strength", "dosage_form", "unit",
    "low_stock_threshold", "manufacturer", "supplier", "unit_cost", "storage_location",
    "notes", "status",
)
# The form fields. A medicine posts generic_name, dosage_strength and dosage_form; a supply
# posts item_name and size instead. Both sets are carried so a redisplay keeps what was typed.
FORM_FIELDS = (
    "category", "generic_name", "dosage_strength", "dosage_form", "item_name", "size",
    "drug_class", "unit", "low_stock_threshold", "manufacturer", "supplier", "unit_cost",
    "storage_location", "notes", "status",
)

# stock status -> the badge class the inventory screen's stylesheet defines.
STATUS_BADGE_CLASS = {
    "Retired": "badge-retired",
    "In Stock": "badge-instock",
    "Low Stock": "badge-lowstock",
    "Critical": "badge-critical",
    "Out of Stock": "badge-critical",
    "Expiring Soon": "badge-nearexpiry",
}
BATCH_BADGE_CLASS = {
    "Usable": "badge-instock",
    "Expiring soon": "badge-nearexpiry",
    "Expired": "badge-expired",
    "Empty": "badge-retired",
}

# The order "sort by status" uses: most urgent first. Retired is not a stock condition and
# goes last.
STATUS_SORT_ORDER = ("Out of Stock", "Critical", "Low Stock", "Expiring Soon", "In Stock",
                     "Retired")

# The stored lifecycle status that takes an item out of service. An Inactive item is left
# out of every operating figure (the stat cards, the low-stock alert, the dashboards and the
# reports) but keeps its batches, and going back to Active restores it everywhere.
RETIRED_STATUS = "Inactive"

# FEFO: the usable batch with the earliest expiry first. A batch with no expiry date is last.
# Ties go to the older delivery, then the lower id, so the order never wobbles.
FEFO_ORDER = ("CASE WHEN expiry_date IS NULL THEN 1 ELSE 0 END, expiry_date, "
              "date_received, id")


def status_rank(display_status):
    """Where a status sits in STATUS_SORT_ORDER, or None if it is not one."""
    return (
        STATUS_SORT_ORDER.index(display_status)
        if display_status in STATUS_SORT_ORDER else None
    )


def allowed_item_status_transitions(current_status):
    """The statuses an item currently in current_status may be moved to.

    Every status except the one it already holds. The caller passes the status it read back
    out of the database, never the one the page posted: a POST can be made without loading
    the page at all. An unrecognised status yields both, so the dialog still offers a way out.
    """
    return tuple(status for status in ITEM_STATUSES if status != current_status)


def is_medicine(category):
    return category == MEDICINE_CATEGORY


# --- names ----------------------------------------------------------------------------

def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


# A number followed by one of these units gets one space between them: "500mg" -> "500 mg".
# Only units are spaced, so "4x4 in" on a supply is left as typed.
_STRENGTH_UNIT = re.compile(r"(\d)\s*(mg|mcg|ug|g|kg|ml|l|iu|units?|meq|mmol|%)(?![A-Za-z])",
                            re.IGNORECASE)


def normalize_strength(text):
    """'500mg' -> '500 mg', '250 mg/5mL' -> '250 mg/5 mL'. One space between a number and its unit."""
    return _STRENGTH_UNIT.sub(r"\1 \2", _clean(text))


def _capitalize(text):
    text = _clean(text)
    return text[:1].upper() + text[1:]


def build_display_name(category, generic_name, strength, form):
    """'Paracetamol 500 mg tablet' for a medicine; 'Gauze pad 4 x 4 in' for a supply."""
    if is_medicine(category):
        parts = [_capitalize(generic_name), normalize_strength(strength), _clean(form).lower()]
    else:
        parts = [_capitalize(generic_name), _clean(strength)]
    return " ".join(part for part in parts if part)


def _identity_key(category, generic_name, strength, form):
    """What makes two items the same item: generic name, strength and form, ignoring case
    and spaces. A supply is told apart by its item name and size."""
    def squash(text):
        return re.sub(r"\s+", "", str(text or "")).lower()
    return (is_medicine(category), squash(generic_name), squash(strength),
            squash(form) if is_medicine(category) else "")


def find_duplicate(conn, category, generic_name, strength, form, exclude_id=None):
    """The display name of an existing item with the same identity, or None."""
    wanted = _identity_key(category, generic_name, strength, form)
    for row in conn.execute(
        "SELECT id, name, category, generic_name, dosage_strength, dosage_form "
        "FROM inventory_items"
    ).fetchall():
        if exclude_id is not None and row["id"] == exclude_id:
            continue
        if _identity_key(row["category"], row["generic_name"], row["dosage_strength"],
                         row["dosage_form"]) == wanted:
            return row["name"]
    return None


def needs_details(item):
    """A medicine that is missing its generic name, strength or a listed dosage form
    (the migration could not split its old name). Staff fix it with Edit details."""
    if not is_medicine(item.get("category")):
        return False
    return not (_clean(item.get("generic_name")) and _clean(item.get("dosage_strength"))
                and item.get("dosage_form") in DOSAGE_FORMS)


# --- dates and statuses -----------------------------------------------------------------

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

    Negative once the date has passed. The printed date is a "use by", so a batch is usable
    through the whole of its expiry date and is Expired from the day after.
    """
    parsed = _parse_date(expiry_date)
    if parsed is None:
        return None
    return (parsed - (on_date or today())).days


def batch_status(expiry_date, quantity_remaining, on_date=None):
    """Empty, Expired, Expiring soon or Usable: the one status of a batch."""
    if (quantity_remaining or 0) <= 0:
        return "Empty"
    days = days_until_expiry(expiry_date, on_date)
    if days is not None and days < 0:
        return "Expired"
    if days is not None and days <= EXPIRING_SOON_DAYS:
        return "Expiring soon"
    return "Usable"


def stock_status(usable_stock, low_stock_threshold, expiring_soon_batches=0):
    """The single status badge the inventory list shows for one item.

    An item can be several of these at once, but the table has one badge, so they are
    resolved in order of how urgently each demands action: Out of Stock, Critical (at or
    below half the reorder level), Low Stock, Expiring Soon, In Stock. `usable_stock`
    counts usable batches only, so expired stock never makes an item look stocked.
    """
    stock = usable_stock or 0
    threshold = low_stock_threshold or 0
    if stock == 0:
        return "Out of Stock"
    if stock <= threshold:
        return "Critical" if stock * 2 <= threshold else "Low Stock"
    if expiring_soon_batches:
        return "Expiring Soon"
    return "In Stock"


def _stock_bar(stock_quantity, low_stock_threshold):
    """Percentage fill and colour class for the stock bar: half full at the reorder level,
    full at twice it."""
    stock = stock_quantity or 0
    threshold = low_stock_threshold or 0

    if threshold <= 0:
        return (100 if stock > 0 else 0), "fill-good"

    percent = min(100, round(stock / (threshold * 2) * 100))
    if stock <= threshold * 0.5:
        fill = "fill-low"
    elif stock <= threshold:
        fill = "fill-warn"
    else:
        fill = "fill-good"
    return percent, fill


def _threshold_pct(stock_quantity, low_stock_threshold):
    """Stock as a percentage of this item's own reorder level, or None."""
    threshold = low_stock_threshold or 0
    if threshold <= 0:
        return None
    return round((stock_quantity or 0) / threshold * 100)


def _display_dosage(row):
    """'500 mg tablet' (strength and form), the Strength / Form column."""
    parts = [row["dosage_strength"], row["dosage_form"]]
    return " ".join(str(part).strip() for part in parts if part)


def _to_batch(row, on_date=None):
    batch = dict(row)
    status = batch_status(batch["expiry_date"], batch["quantity_remaining"], on_date)
    batch["status"] = status
    batch["badge_class"] = BATCH_BADGE_CLASS[status]
    batch["days_until_expiry"] = days_until_expiry(batch["expiry_date"], on_date)
    batch["is_usable"] = status in ("Usable", "Expiring soon")
    batch["is_expired"] = status == "Expired"
    batch["is_expiring_soon"] = status == "Expiring soon"
    batch["is_empty"] = status == "Empty"
    return batch


def _to_item(row, batches, on_date=None):
    """Copy an inventory_items row into a dict and add the figures derived from its batches."""
    item = dict(row)
    batches = [_to_batch(batch, on_date) for batch in batches]
    usable = [batch for batch in batches if batch["is_usable"]]
    expiring = [batch for batch in batches if batch["is_expiring_soon"]]
    expired = [batch for batch in batches if batch["is_expired"]]

    item["batches"] = batches
    item["stock_quantity"] = sum(batch["quantity_remaining"] for batch in usable)
    item["expired_quantity"] = sum(batch["quantity_remaining"] for batch in expired)
    # The nearest expiry among the batches that can still be used.
    dated = sorted(batch["expiry_date"] for batch in usable if batch["expiry_date"])
    item["nearest_expiry"] = dated[0] if dated else None
    item["expiring_soon_batches"] = len(expiring)
    item["expired_batches"] = len(expired)

    status = stock_status(item["stock_quantity"], item.get("low_stock_threshold"),
                          len(expiring))
    percent, fill_class = _stock_bar(item["stock_quantity"], item.get("low_stock_threshold"))

    # stock_status stays the pure stock condition whatever the item's lifecycle status is;
    # what changes for a retired item is who is in scope for it, decided in in_service().
    item["stock_status"] = status
    item["is_retired"] = item.get("status") == RETIRED_STATUS
    item["display_status"] = "Retired" if item["is_retired"] else status
    item["status_badge_class"] = STATUS_BADGE_CLASS.get(item["display_status"], "badge-instock")
    item["status_rank"] = status_rank(item["display_status"])
    item["stock_percent"] = percent
    item["stock_fill_class"] = fill_class
    item["display_dosage"] = _display_dosage(row)
    item["is_medicine"] = is_medicine(item.get("category"))
    item["needs_details"] = needs_details(item)
    item["is_low_stock"] = item["stock_quantity"] <= (item.get("low_stock_threshold") or 0)
    item["is_out_of_stock"] = item["stock_quantity"] == 0
    item["threshold_pct"] = _threshold_pct(item["stock_quantity"], item.get("low_stock_threshold"))
    return item


def _load_items(conn, where="", parameters=(), on_date=None):
    rows = conn.execute(
        f"SELECT * FROM inventory_items {where} ORDER BY name COLLATE NOCASE, id", parameters
    ).fetchall()
    by_item = {}
    for batch in conn.execute(
        "SELECT * FROM inventory_batches ORDER BY " + FEFO_ORDER
    ).fetchall():
        by_item.setdefault(batch["inventory_item_id"], []).append(batch)
    return [_to_item(row, by_item.get(row["id"], []), on_date) for row in rows]


def get_all_inventory_items(on_date=None):
    """Every inventory item, ordered by name, each with its batches."""
    with db_connection() as conn:
        return _load_items(conn, on_date=on_date)


def get_inventory_item_by_id(item_id, on_date=None):
    """One inventory item by primary key, or None if no such row exists."""
    with db_connection() as conn:
        found = _load_items(conn, "WHERE id = ?", (item_id,), on_date)
    return found[0] if found else None


def get_removals_for_item(item_id, limit=10):
    """The latest amounts taken out of this item's batches, newest first."""
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT r.quantity, r.reason, r.note, r.created_at, b.lot_number, "
            "       u.full_name AS removed_by_name "
            "FROM inventory_removals r "
            "JOIN inventory_batches b ON b.id = r.batch_id "
            "LEFT JOIN users u ON u.id = r.removed_by "
            "WHERE b.inventory_item_id = ? ORDER BY r.id DESC LIMIT ?",
            (item_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def in_service(items):
    """The items every operating figure in this module is computed over: not retired.

    One definition of "in scope", read by the stat cards, the status doughnut, the low-stock
    alert and the expiry report, so they cannot disagree about whether a retired item counts.
    Retired items stay listed on the inventory screen, badged "Retired", so a retirement can
    be seen and undone.
    """
    return [item for item in items if not item["is_retired"]]


def get_inventory_stats(items=None):
    """Counts behind the stat cards on the inventory screen and the dashboards.

    Every figure is computed from the rows themselves rather than stored. Retired items are
    excluded; retired_count is returned alongside so the screen can say so. The expiring-soon
    and expired figures count batches that still hold stock, and the expired ones are not part
    of any item's stock.
    """
    if items is None:
        items = get_all_inventory_items()

    retired_count = sum(1 for item in items if item["is_retired"])
    items = in_service(items)

    return {
        "total_items": len(items),
        "medicine_count": sum(1 for item in items if item["category"] == MEDICINE_CATEGORY),
        "retired_count": retired_count,
        "low_stock_count": sum(1 for item in items if item["is_low_stock"]),
        "out_of_stock_count": sum(1 for item in items if item["is_out_of_stock"]),
        "expiring_soon_count": sum(item["expiring_soon_batches"] for item in items),
        "expired_count": sum(item["expired_batches"] for item in items),
        "needs_details_count": sum(1 for item in items if item["needs_details"]),
        "expiring_soon_days": EXPIRING_SOON_DAYS,
    }


def get_status_distribution(items=None):
    """The four segments of the Medicine Inventory Status doughnut.

    A doughnut has to partition its total, so each item is counted once, under the most
    urgent condition that applies to it:

      Low Stock      at or below its own reorder level (out-of-stock included)
      Expired        not short, but holding an expired batch
      Expiring Soon  not short and not expired, but holding a batch that expires soon
      In Stock       nothing to flag

    Low Stock is resolved first so this segment always equals the low_stock_count the
    dashboards and the sidebar badge report. The counts sum to total.
    """
    if items is None:
        items = get_all_inventory_items()

    items = in_service(items)
    low_stock = expired = expiring_soon = in_stock = 0
    for item in items:
        if item["is_low_stock"]:
            low_stock += 1
        elif item["expired_batches"]:
            expired += 1
        elif item["expiring_soon_batches"]:
            expiring_soon += 1
        else:
            in_stock += 1

    return {
        "in_stock": in_stock,
        "low_stock": low_stock,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "total": len(items),
    }


def get_expiry_batches(items=None):
    """The batches that need attention, soonest expiry first: those expiring soon and those
    expired, that still hold stock, on items in service. Stock facts with no patient link."""
    if items is None:
        items = get_all_inventory_items()
    rows = []
    for item in in_service(items):
        for batch in item["batches"]:
            if batch["is_expired"] or batch["is_expiring_soon"]:
                rows.append({
                    "item_id": item["id"],
                    "item_name": item["name"],
                    "unit": item.get("unit"),
                    "batch_id": batch["id"],
                    "lot_number": batch["lot_number"],
                    "expiry_date": batch["expiry_date"],
                    "quantity_remaining": batch["quantity_remaining"],
                    "status": batch["status"],
                    "days_until_expiry": batch["days_until_expiry"],
                })
    rows.sort(key=lambda row: (row["expiry_date"] or "", row["item_name"].lower(),
                               row["lot_number"], row["batch_id"]))
    return rows


def get_inventory_report():
    """Stock-level summary for Reports & Analytics.

    The counts and the ordered low-stock list come from get_low_stock_alert(), the same call
    behind the dashboards and the sidebar badge, so the report cannot show a different
    low-stock figure. Every figure is over the working inventory (retired items left out).
    """
    items = in_service(get_all_inventory_items())
    alert = get_low_stock_alert()
    batches = get_expiry_batches(items)

    return {
        "items": items,
        "total_items": len(items),
        # Most critical first, as get_low_stock_alert() orders them.
        "low_stock_items": alert["low_stock_items"],
        "out_of_stock_items": [item for item in items if item["is_out_of_stock"]],
        "low_stock_count": alert["low_stock_count"],
        "out_of_stock_count": alert["out_of_stock_count"],
        "status_distribution": get_status_distribution(items),
        "expiry_batches": batches,
        "expiring_soon_count": sum(1 for row in batches if row["status"] == "Expiring soon"),
        "expired_count": sum(1 for row in batches if row["status"] == "Expired"),
        "expiring_soon_days": EXPIRING_SOON_DAYS,
    }


def _criticality(item):
    """Sort key putting the item in most urgent need of restocking first.

    Usable stock as a fraction of its own reorder level; ties go to the larger shortfall.
    Items with no reorder level sort last; they cannot be judged short.
    """
    threshold = item.get("low_stock_threshold") or 0
    stock = item.get("stock_quantity") or 0
    if threshold <= 0:
        return (1, 0, 0)
    return (0, stock / threshold, -(threshold - stock))


def get_low_stock_alert(limit=None):
    """The in-system low-stock alert behind the dashboards and the sidebar badge.

    Every screen that reports a low-stock figure reads it from here. It counts usable stock
    only: an expired batch never keeps an item off the list. `limit` caps only the returned
    item list, never the counts. The list is keyed "low_stock_items" rather than "items"
    because Jinja would resolve `low_stock.items` to dict.items.
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


# --- validation ---------------------------------------------------------------------------

# Plain digits only (audit B13, B14): int() and float() also read "1_000", "+5", "1e9",
# "inf" and "nan", and a number too big for SQLite failed with a server error.
_WHOLE_NUMBER = re.compile(r"[0-9]+")
_DECIMAL_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
MAX_REORDER_LEVEL = 100000
MAX_UNIT_COST = 1000000


def _parse_int(raw):
    """(12, True) for a valid non-negative integer, (None, False) otherwise."""
    text = str(raw or "").strip()
    if not text or not _WHOLE_NUMBER.fullmatch(text) or len(text) > 9:
        return None, False
    return int(text), True


def _parse_decimal(raw):
    """(8.5, True) for a valid non-negative number, (None, False) otherwise."""
    text = str(raw or "").strip()
    if not text:
        return None, False
    if not _DECIMAL_NUMBER.fullmatch(text) or len(text) > 15:
        return None, False
    value = float(text)
    return value, math.isfinite(value) and value >= 0


def _get(values, field):
    return (values.get(field) or "").strip()


def _item_identity(values):
    """(generic_name, strength, form) as the form posted them, by item type."""
    if is_medicine(_get(values, "category")):
        return (_clean(_get(values, "generic_name")), normalize_strength(_get(values, "dosage_strength")),
                _get(values, "dosage_form").lower())
    return _clean(_get(values, "item_name")), _clean(_get(values, "size")), ""


def validate_inventory_form(values, item_id=None):
    """Server-side validation of Edit details and Add medicine. Returns {field: message}.

    Runs independently of the browser: the form carries `novalidate`, and a POST can arrive
    without ever touching the page. There is no quantity or expiry here: those belong to
    batches (Receive stock).
    """
    errors = {}
    category = _get(values, "category")
    if not category:
        errors["category"] = "Item type is required."
    elif category not in ITEM_CATEGORIES:
        errors["category"] = "Choose an item type from the list."

    medicine = is_medicine(category)
    if medicine:
        if not _get(values, "generic_name"):
            errors["generic_name"] = "Generic name is required."
        if not _get(values, "dosage_strength"):
            errors["dosage_strength"] = "Strength is required, for example 500 mg."
        form = _get(values, "dosage_form").lower()
        if not form:
            errors["dosage_form"] = "Dosage form is required."
        elif form not in DOSAGE_FORMS:
            errors["dosage_form"] = "Choose a dosage form from the list."
        if not _get(values, "drug_class"):
            errors["drug_class"] = "Category is required for a medicine."
    elif category in ITEM_CATEGORIES and not _get(values, "item_name"):
        errors["item_name"] = "Item name is required."

    # Constrained fields: reject anything the form does not itself offer.
    checks = [("unit", UNITS, "unit of measure"), ("status", ITEM_STATUSES, "status")]
    if medicine:
        checks.append(("drug_class", DRUG_CLASSES, "category"))
    for field, allowed, label in checks:
        value = _get(values, field)
        if not value:
            if field in ("unit", "status"):
                errors[field] = f"{label.capitalize()} is required."
        elif field not in errors and value not in allowed:
            errors[field] = f"Choose a {label} from the list."

    raw = _get(values, "low_stock_threshold")
    if not raw:
        errors["low_stock_threshold"] = "Reorder level is required."
    else:
        level, ok = _parse_int(raw)
        if not ok:
            errors["low_stock_threshold"] = "Reorder level must be a whole number of 0 or more."
        elif level > MAX_REORDER_LEVEL:
            errors["low_stock_threshold"] = f"Enter a reorder level of {MAX_REORDER_LEVEL:,} or less."

    unit_cost = _get(values, "unit_cost")
    if unit_cost:
        cost, ok = _parse_decimal(unit_cost)
        if not ok:
            errors["unit_cost"] = "Unit cost must be a number of 0 or more, such as 2.50."
        elif cost > MAX_UNIT_COST:
            errors["unit_cost"] = f"Enter a unit cost of {MAX_UNIT_COST:,} or less."

    if not errors:
        generic, strength, form = _item_identity(values)
        with db_connection() as conn:
            duplicate = find_duplicate(conn, category, generic, strength, form, item_id)
        if duplicate:
            field = "generic_name" if medicine else "item_name"
            errors[field] = f"{duplicate} is already in the inventory."

    return errors


def _build_record(values):
    """Normalise submitted form values into the column values to store, display name included.

    Shared by create_inventory_item() and update_inventory_item() so an insert and an edit
    can never normalise the same field differently.
    """
    category = _get(values, "category")
    generic, strength, form = _item_identity(values)
    medicine = is_medicine(category)
    count, ok = _parse_int(values.get("low_stock_threshold"))
    cost, cost_ok = _parse_decimal(values.get("unit_cost"))

    def text(field):
        return _get(values, field) or None

    return {
        "name": build_display_name(category, generic, strength, form),
        "generic_name": _capitalize(generic),
        "category": category,
        "drug_class": text("drug_class") if medicine else None,
        "dosage_strength": strength or None,
        "dosage_form": form if medicine else None,
        "unit": text("unit"),
        "low_stock_threshold": count if ok else 0,
        "manufacturer": text("manufacturer"),
        "supplier": text("supplier"),
        "unit_cost": cost if cost_ok else None,
        "storage_location": text("storage_location"),
        "notes": text("notes"),
        "status": text("status") or "Active",
    }


def create_inventory_item(values, audit=None):
    """Insert an inventory item (details only, no stock) and return its new primary key.

    A duplicate of an existing item raises ValueError; the form's validation has already
    checked, and this checks again inside the write. `audit(conn, new_id)` is called before
    the commit.
    """
    record = _build_record(values)
    columns = ["item_code", "name"] + list(ITEM_FIELDS)
    placeholders = ", ".join("?" for _ in columns)

    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if find_duplicate(conn, record["category"], record["generic_name"],
                          record["dosage_strength"], record["dosage_form"]):
            raise ValueError("That item is already in the inventory.")
        parameters = ([_next_item_code(conn), record["name"]]
                      + [record[field] for field in ITEM_FIELDS])
        cursor = conn.execute(
            f"INSERT INTO inventory_items ({', '.join(columns)}) VALUES ({placeholders})",
            parameters,
        )
        new_id = cursor.lastrowid
        if audit:
            audit(conn, new_id)
        conn.commit()
    return new_id


def update_inventory_item(item_id, values, audit=None):
    """Overwrite one item's details. Never touches stock: there is no quantity here.

    Leaves item_code and created_at alone and refreshes updated_at. Returns the list of
    changes, [{"field", "label", "old", "new"}, ...]; an empty list means the submitted form
    carried exactly the stored values, so the caller can say that instead of "updated".
    A change of the generic name, strength or form that would duplicate another item raises
    ValueError. `audit(conn, changes)` is called before the commit when something changed.
    """
    record = _build_record(values)

    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        before = conn.execute(
            "SELECT * FROM inventory_items WHERE id = ?", (item_id,)
        ).fetchone()
        if before is None:
            return []
        if find_duplicate(conn, record["category"], record["generic_name"],
                          record["dosage_strength"], record["dosage_form"], item_id):
            raise ValueError("That item is already in the inventory.")

        labels = dict(FIELD_LABELS)
        if not is_medicine(record["category"]):
            labels.update(SUPPLY_FIELD_LABELS)
        changes = [
            {
                "field": field,
                "label": labels.get(field, field),
                "old": before[field],
                "new": record[field],
            }
            for field in ITEM_FIELDS
            if before[field] != record[field]
        ]

        fields = ("name",) + ITEM_FIELDS
        assignments = ", ".join(f"{field} = ?" for field in fields)
        parameters = [record[field] for field in fields] + [item_id]
        conn.execute(
            f"UPDATE inventory_items SET {assignments}, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            parameters,
        )
        if audit and changes:
            audit(conn, changes)
        conn.commit()
    return changes


def set_item_status(item_id, status, audit=None):
    """Move one item between Active and Inactive. Returns rows changed.

    Retiring is an UPDATE of one flag and nothing else: no row is removed, and the batches
    are untouched. `AND status != ?` makes the count honest, since SQLite's rowcount reports
    rows matched, not rows changed. `audit(conn)` is called before the commit when the
    status actually changed.
    """
    if status not in ITEM_STATUSES:
        raise ValueError(
            f"{status!r} is not an item status; expected one of {ITEM_STATUSES}."
        )

    with db_connection() as conn:
        cursor = conn.execute(
            """
        UPDATE inventory_items
           SET status = ?, updated_at = CURRENT_TIMESTAMP
         WHERE id = ? AND status != ?
        """,
            (status, int(item_id), status),
        )
        affected = cursor.rowcount
        if audit and affected:
            audit(conn)
        conn.commit()
    return affected


def _next_item_code(conn):
    """Next free identifier in the MED-#### series, one series for every item type.

    Reads the highest number in use rather than counting rows, so a gap cannot cause a
    UNIQUE collision.
    """
    rows = conn.execute(
        "SELECT item_code FROM inventory_items WHERE item_code LIKE 'MED-%'"
    ).fetchall()
    highest = 0
    for row in rows:
        suffix = str(row["item_code"]).split("-", 1)[1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"MED-{highest + 1:04d}"


def generate_next_item_code():
    with db_connection() as conn:
        return _next_item_code(conn)


# --- batches: Receive stock, Remove from stock ----------------------------------------------

def validate_receive_form(values, item):
    """Server-side validation of Receive stock. Returns {field: message}."""
    errors = {}
    no_lot = bool(_get(values, "no_lot"))
    if not no_lot and not _get(values, "lot_number"):
        errors["lot_number"] = "Enter the lot number, or tick No lot number."

    expiry = _get(values, "expiry_date")
    if not expiry:
        if is_medicine(item["category"]):
            errors["expiry_date"] = "Expiry date is required for a medicine."
    else:
        parsed = _parse_date(expiry)
        if parsed is None:
            errors["expiry_date"] = "Enter a valid date in YYYY-MM-DD format."
        elif parsed < today():
            errors["expiry_date"] = "That expiry date has already passed."

    quantity, ok = _parse_int(values.get("quantity"))
    if not ok or quantity < 1:
        errors["quantity"] = "Enter the quantity received as a whole number of 1 or more."
    elif quantity > MAX_QUANTITY:
        errors["quantity"] = f"Enter a quantity of {MAX_QUANTITY:,} or less."

    received = _get(values, "date_received")
    if received:
        parsed = _parse_date(received)
        if parsed is None:
            errors["date_received"] = "Enter a valid date in YYYY-MM-DD format."
        elif parsed > today():
            errors["date_received"] = "Date received cannot be in the future."

    source = _get(values, "source")
    if not source:
        errors["source"] = "Source is required."
    elif source not in STOCK_SOURCES:
        errors["source"] = "Choose a source from the list."
    return errors


def receive_stock(item_id, values, received_by=None, audit=None):
    """Add one batch to an item. Returns the new batch id, or None if there is no such item.

    The caller has validated `values`. A blank date received is today. `audit(conn, batch_id)`
    is called before the commit.
    """
    lot = NO_LOT_NUMBER if _get(values, "no_lot") else _clean(_get(values, "lot_number"))
    quantity, _ = _parse_int(values.get("quantity"))
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM inventory_items WHERE id = ?", (item_id,)).fetchone() is None:
            return None
        cursor = conn.execute(
            "INSERT INTO inventory_batches (inventory_item_id, lot_number, expiry_date, "
            "quantity_received, quantity_remaining, date_received, source, brand_name, "
            "received_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, lot, _get(values, "expiry_date") or None, quantity, quantity,
             _get(values, "date_received") or today().isoformat(), _get(values, "source"),
             _clean(_get(values, "brand_name")) or None, received_by),
        )
        batch_id = cursor.lastrowid
        conn.execute("UPDATE inventory_items SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (item_id,))
        if audit:
            audit(conn, batch_id)
        conn.commit()
    return batch_id


def remove_from_batch(item_id, batch_id, values, removed_by=None, audit=None):
    """Take an amount out of ONE batch, with a reason. Returns (removed, errors).

    `errors` is {field: message}; `removed` is the amount taken out, or None when refused.
    The reason is required and must be one of REMOVAL_REASONS; the amount must be a whole
    number from 1 up to what the batch holds. The decrement is guarded in SQL, so the batch
    cannot go below zero even if two requests race. `audit(conn, details)` is called before
    the commit, with the batch id, the amount and the reason.
    """
    errors = {}
    reason = _get(values, "reason")
    if not reason:
        errors["reason"] = "Choose a reason."
    elif reason not in REMOVAL_REASONS:
        errors["reason"] = "Choose a reason from the list."
    quantity, ok = _parse_int(values.get("quantity"))
    if not ok or quantity < 1:
        errors["quantity"] = "Enter the amount as a whole number of 1 or more."
    if errors:
        return None, errors

    note = _clean(_get(values, "note")) or None
    with db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        batch = conn.execute(
            "SELECT id, quantity_remaining FROM inventory_batches "
            "WHERE id = ? AND inventory_item_id = ?", (batch_id, item_id)
        ).fetchone()
        if batch is None:
            return None, {"batch": "That batch could not be found."}
        if quantity > batch["quantity_remaining"]:
            return None, {"quantity": f"This batch holds only {batch['quantity_remaining']:,}."}
        cursor = conn.execute(
            "UPDATE inventory_batches SET quantity_remaining = quantity_remaining - ? "
            "WHERE id = ? AND quantity_remaining >= ?", (quantity, batch_id, quantity))
        if cursor.rowcount != 1:
            return None, {"quantity": "The batch changed while this was being saved. Try again."}
        conn.execute(
            "INSERT INTO inventory_removals (batch_id, quantity, reason, note, removed_by) "
            "VALUES (?, ?, ?, ?, ?)", (batch_id, quantity, reason, note, removed_by))
        conn.execute("UPDATE inventory_items SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (item_id,))
        if audit:
            audit(conn, {"batch_id": batch_id, "quantity": quantity, "reason": reason})
        conn.commit()
    return quantity, {}


def usable_batches(conn, item_id, on_date=None):
    """The batches an item can be dispensed from, in FEFO order (earliest expiry first), on
    the connection's own transaction. Expired and empty batches are never in this list."""
    return conn.execute(
        "SELECT id, lot_number, expiry_date, quantity_remaining FROM inventory_batches "
        "WHERE inventory_item_id = ? AND quantity_remaining > 0 "
        "AND (expiry_date IS NULL OR expiry_date >= ?) ORDER BY " + FEFO_ORDER,
        (item_id, (on_date or today()).isoformat()),
    ).fetchall()
