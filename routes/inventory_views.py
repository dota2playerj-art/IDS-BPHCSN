"""Shared context builders for the inventory screens.

The inventory screens are rendered by two blueprints each -- once for the Administrator and
once for Health Center Staff and the Doctor -- from the same templates with the same data.
The queries live here so the two role variants cannot drift apart; the routes stay thin and
each keeps its own role_required guard and its own redirect target.

Three separate actions, as the adviser asked (Task 12): Edit details changes item fields
only, never a quantity; Receive stock adds a batch; Remove from stock takes an amount out of
one batch, with a reason.
"""
from config import EXPIRING_SOON_DAYS
from models.inventory import (
    ITEM_TEXT_LIMITS,
    TEXT_MAX_LENGTH,
    DOSAGE_FORMS,
    DRUG_CLASSES,
    FORM_FIELDS,
    ITEM_CATEGORIES,
    ITEM_STATUSES,
    NO_LOT_NUMBER,
    REMOVAL_REASONS,
    STOCK_SOURCES,
    UNITS,
    allowed_item_status_transitions,
    create_inventory_item,
    generate_next_item_code,
    get_all_inventory_items,
    get_inventory_item_by_id,
    get_inventory_stats,
    get_removals_for_item,
    is_medicine,
    receive_stock,
    remove_from_batch,
    set_item_status,
    update_inventory_item,
    validate_inventory_form,
    validate_receive_form,
)
from routes.audit_entries import (
    inventory_added, inventory_edited, inventory_status_changed, stock_received, stock_removed,
)
from utils.dates import today

# Handed to the template so every <select> and radio is rendered from the same tuples the
# validator checks against.
FORM_OPTIONS = {
    "item_categories": ITEM_CATEGORIES,
    "drug_classes": DRUG_CLASSES,
    "dosage_forms": DOSAGE_FORMS,
    "units": UNITS,
    "statuses": ITEM_STATUSES,
    "sources": STOCK_SOURCES,
    "reasons": REMOVAL_REASONS,
    "no_lot_number": NO_LOT_NUMBER,
}

RECEIVE_FIELDS = ("lot_number", "no_lot", "expiry_date", "quantity", "date_received", "source",
                  "brand_name")
REMOVE_FIELDS = ("batch_id", "quantity", "reason", "note")


def medicine_inventory_context():
    """Everything the inventory list renders: the item list and the stat cards."""
    items = get_all_inventory_items()
    return {
        "items": items,
        "stats": get_inventory_stats(items),
        "filter_options": _filter_options(items),
    }


def _filter_options(items):
    """The values the shelf actually holds, for the filter dropdowns.

    Read off the items being rendered rather than the master vocabularies: offering a
    category nothing is stocked under would be a filter that can only return an empty table.
    The category shown in a row is drug_class where there is one and category otherwise, and
    the statuses are read from display_status, which is what the Status cell prints.
    """
    categories = {(item["drug_class"] or item["category"]) for item in items}
    return {
        "categories": sorted(c for c in categories if c),
        "statuses": sorted({item["display_status"] for item in items if item["display_status"]}),
    }


def item_to_form(item):
    """Render a stored item back into the flat dict the form template reads.

    A medicine fills generic name, strength and form; a supply fills item name and size.
    Numbers come back as strings because that is what an <input value=""> holds.
    """
    def text(value):
        return "" if value is None else str(value)

    form = {
        "category": text(item.get("category")),
        "drug_class": text(item.get("drug_class")),
        "unit": text(item.get("unit")),
        "low_stock_threshold": text(item.get("low_stock_threshold")),
        "manufacturer": text(item.get("manufacturer")),
        "supplier": text(item.get("supplier")),
        "unit_cost": "" if item.get("unit_cost") is None else f"{item['unit_cost']:.2f}",
        "storage_location": text(item.get("storage_location")),
        "notes": text(item.get("notes")),
        "status": text(item.get("status")),
        "generic_name": "", "dosage_strength": "", "dosage_form": "",
        "item_name": "", "size": "",
    }
    if is_medicine(item.get("category")):
        form["generic_name"] = text(item.get("generic_name"))
        form["dosage_strength"] = text(item.get("dosage_strength"))
        form["dosage_form"] = text(item.get("dosage_form"))
    else:
        form["item_name"] = text(item.get("generic_name"))
        form["size"] = text(item.get("dosage_strength"))
    return form


def add_edit_medicine_context(form=None, errors=None, item=None):
    """Context for the item details form.

    `item` set means edit mode: the template switches its wording, shows the existing item
    code instead of the next free one, and posts back to the same edit URL. On a redisplay
    after a failed submit the caller passes the submitted values, so nothing typed is lost.
    """
    if item is not None and form is None:
        form = item_to_form(item)

    return {
        "item": item,
        "next_item_code": item["item_code"] if item else generate_next_item_code(),
        "form": form or {},
        "errors": errors or {},
        "options": FORM_OPTIONS,
        "item_text_limits": ITEM_TEXT_LIMITS,
    }


def _extract_form(form_data, fields):
    """Pull the submitted values into the shape the model and template share."""
    return {field: (form_data.get(field) or "").strip() for field in fields}


# How many individual field changes the confirmation message names before it stops listing
# them and reports a count instead.
MAX_LISTED_CHANGES = 3


def _describe(value):
    """Render a stored value for the confirmation message."""
    if value is None or value == "":
        return "(blank)"
    return str(value)


def _save_message(name, changes):
    """The line flashed after Edit details, naming what actually changed.

    An unconditional "updated" cannot tell a real save from one that wrote back the stored
    values, which is the case that makes an operator believe their edit was dropped.
    """
    if not changes:
        return f"No changes were made to {name}."

    listed = changes[:MAX_LISTED_CHANGES]
    parts = [
        f"{change['label']} {_describe(change['old'])} → {_describe(change['new'])}"
        for change in listed
    ]
    remaining = len(changes) - len(listed)
    if remaining:
        parts.append(f"and {remaining} more field{'s' if remaining != 1 else ''}")
    return f"{name} updated: " + ", ".join(parts) + "."


def process_add_edit_medicine(form_data, item=None, user_id=None, ip_address=None):
    """Validate, then insert a new inventory item or update an existing one.

    `item` set means edit mode. Returns (item_row_id, context, message). The id and the
    context are mutually exclusive: an id means the caller should redirect and flash
    `message`, a context means the caller should re-render the form. The message is built
    here so the two roles cannot word the same outcome differently. Adding an item adds no
    stock; stock is received afterwards, as a batch.
    """
    values = _extract_form(form_data, FORM_FIELDS)

    errors = validate_inventory_form(values, item["id"] if item else None)
    if errors:
        return None, add_edit_medicine_context(form=values, errors=errors, item=item), None

    try:
        if item is not None:
            changes = update_inventory_item(
                item["id"], values, audit=inventory_edited(item["id"], user_id, ip_address)
            )
            updated = get_inventory_item_by_id(item["id"])
            return item["id"], None, _save_message(updated["name"], changes)
        new_id = create_inventory_item(values, audit=inventory_added(user_id, ip_address))
    except ValueError:
        # Someone else added the same item between the check and the write.
        field = "generic_name" if is_medicine(values["category"]) else "item_name"
        errors = {field: "That item is already in the inventory."}
        return None, add_edit_medicine_context(form=values, errors=errors, item=item), None
    created = get_inventory_item_by_id(new_id)
    return new_id, None, f"{created['name']} added. Now receive its first stock."


def item_page_context(item_id, receive_form=None, receive_errors=None):
    """Everything the item page renders, or None if there is no such item."""
    item = get_inventory_item_by_id(item_id)
    if item is None:
        return None
    return {
        "item": item,
        "removals": get_removals_for_item(item_id),
        "options": FORM_OPTIONS,
        "receive_form": receive_form or {"date_received": today().isoformat()},
        "receive_errors": receive_errors or {},
        "expiring_soon_days": EXPIRING_SOON_DAYS,
        "batch_text_max": TEXT_MAX_LENGTH,
    }


def process_receive_stock(item_id, form_data, user_id=None, ip_address=None):
    """Validate and add one batch. Returns (batch_id, context, message): an id means redirect
    and flash `message`; a context means re-render the item page with the field errors."""
    item = get_inventory_item_by_id(item_id)
    if item is None:
        return None, None, "That inventory item could not be found."

    values = _extract_form(form_data, RECEIVE_FIELDS)
    errors = validate_receive_form(values, item)
    if errors:
        return None, item_page_context(item_id, values, errors), None

    batch_id = receive_stock(item_id, values, received_by=user_id,
                             audit=stock_received(user_id, ip_address))
    quantity = int(values["quantity"])
    return batch_id, None, f"Received {quantity:,} of {item['name']}."


def process_remove_stock(item_id, form_data, user_id=None, ip_address=None):
    """Take an amount out of one batch. Returns the message to flash."""
    item = get_inventory_item_by_id(item_id)
    if item is None:
        return "That inventory item could not be found."

    values = _extract_form(form_data, REMOVE_FIELDS)
    if not values["batch_id"].isdigit():
        return "Choose the batch to take stock out of."
    batch = next((b for b in item["batches"] if b["id"] == int(values["batch_id"])), None)
    if batch is None:
        return "That batch could not be found."

    removed, errors = remove_from_batch(
        item_id, batch["id"], values, removed_by=user_id,
        audit=stock_removed(user_id, ip_address))
    if errors:
        return " ".join(errors.values())
    return f"Removed {removed:,} from lot {batch['lot_number']} ({values['reason']})."


def process_archive_medicine(form_data, user_id=None, ip_address=None):
    """Apply the inventory list's status action. Returns the message to flash.

    The row-level Archive icon posts one item_id and the status it wants. Everything is
    re-checked here, because a POST can be made without ever loading the page: the status is
    validated against ITEM_STATUSES, and the requested move is checked against the item's
    stored status, never the one the page posted.
    """
    status = (form_data.get("status") or "").strip()
    if status not in ITEM_STATUSES:
        return "Choose a status to set: Mark Active or Mark Inactive."

    raw_id = (form_data.get("item_id") or "").strip()
    if not raw_id.isdigit():
        return "Select an inventory item to update."

    item = get_inventory_item_by_id(int(raw_id))
    if item is None:
        return "That inventory item could not be found."

    current_status = item["status"]
    if status == current_status:
        return f"No change. {item['name']} is already marked {status}."
    if status not in allowed_item_status_transitions(current_status):
        return (
            f"{item['name']} cannot be moved from {current_status} to {status}."
        )

    audit = inventory_status_changed(item["id"], current_status, status, user_id, ip_address)
    if not set_item_status(item["id"], status, audit=audit):
        return f"No change. {item['name']} is already marked {status}."

    if status == "Active":
        return (
            f"{item['name']} returned to service and marked Active. It counts "
            "towards the stat cards, the low-stock alert and the dashboards again."
        )
    return (
        f"{item['name']} retired and marked Inactive. Nothing was deleted. It is "
        "left out of the counts and alerts until it is marked Active again."
    )
