"""Shared context builders for the inventory screens.

Screens 06 and 07 are rendered by two blueprints each -- once for the
Administrator and once for Health Center Staff -- from the same templates with
the same data. The queries live here so the two role variants cannot drift
apart; the routes stay thin and each keeps its own role_required guard and its
own redirect target.

This mirrors routes/patient_views.py exactly, including how a failed submit is
redisplayed: the template repopulates itself from a `form` dict, so edit mode
reuses that same mechanism rather than introducing a second one.
"""
from models.inventory import (
    DOSAGE_FORMS,
    DRUG_CLASSES,
    ITEM_CATEGORIES,
    ITEM_STATUSES,
    UNITS,
    create_inventory_item,
    generate_next_item_code,
    get_all_inventory_items,
    get_inventory_stats,
    update_inventory_item,
    validate_inventory_form,
)

# Handed to the template so every <select> and radio is rendered from the same
# tuples the validator checks against.
FORM_OPTIONS = {
    "item_categories": ITEM_CATEGORIES,
    "drug_classes": DRUG_CLASSES,
    "dosage_forms": DOSAGE_FORMS,
    "units": UNITS,
    "statuses": ITEM_STATUSES,
}

# The fields the form posts back, and the keys the template reads to repopulate
# itself. One tuple so a field cannot be collected without being redisplayed.
FORM_FIELDS = (
    "name", "generic_name", "brand_name", "category", "drug_class",
    "dosage_strength", "dosage_form", "unit", "stock_quantity",
    "low_stock_threshold", "expiry_date", "date_received", "batch_number",
    "manufacturer", "supplier", "unit_cost", "storage_location", "notes",
    "status",
)


def medicine_inventory_context():
    """Everything Screen 06 renders: the item list and the four stat cards."""
    items = get_all_inventory_items()
    return {
        "items": items,
        "stats": get_inventory_stats(items),
        "filter_options": _filter_options(items),
    }


def _filter_options(items):
    """The values the shelf actually holds, for Screen 06's filter dropdowns.

    Read off the items being rendered rather than from the master vocabularies
    in models/inventory.py: those list every category the form can record, and
    offering one nothing is stocked under would be a filter that can only ever
    return an empty table. Screen 12's module filter is built the same way.

    The category shown in a row is drug_class where there is one and category
    otherwise, so the option list is built from the same expression -- otherwise
    a filter value could not match the cell beside it.
    """
    categories = {(item["drug_class"] or item["category"]) for item in items}
    return {
        "categories": sorted(c for c in categories if c),
        "statuses": sorted({item["stock_status"] for item in items if item["stock_status"]}),
    }


def item_to_form(item):
    """Render a stored item back into the flat dict the form template reads.

    Numbers come back as strings because that is what an <input value=""> holds;
    passing the int would render 0 for an empty unit cost rather than a blank
    field.
    """
    form = {}
    for field in FORM_FIELDS:
        value = item.get(field)
        form[field] = "" if value is None else str(value)

    # A unit cost of 8.5 should redisplay as "8.50", the way the operator typed it.
    if item.get("unit_cost") is not None:
        form["unit_cost"] = f"{item['unit_cost']:.2f}"
    return form


def add_edit_medicine_context(form=None, errors=None, item=None):
    """Context for the medicine form.

    `item` set means edit mode: the template switches its wording, shows the
    existing item code instead of the next free one, and posts back to the same
    edit URL. On a GET the form is pre-filled from the record; on a redisplay
    after a failed submit the caller passes the submitted values instead, so the
    operator's edits are never thrown away.
    """
    if item is not None and form is None:
        form = item_to_form(item)

    return {
        "item": item,
        "next_item_code": item["item_code"] if item else generate_next_item_code(),
        "form": form or {},
        "errors": errors or {},
        "options": FORM_OPTIONS,
    }


def _extract_form(form_data):
    """Pull the submitted values into the shape the model and template share."""
    return {field: (form_data.get(field) or "").strip() for field in FORM_FIELDS}


# How many individual field changes the confirmation message names before it
# stops listing them and reports a count instead.
MAX_LISTED_CHANGES = 3


def _describe(value):
    """Render a stored value for the confirmation message."""
    if value is None or value == "":
        return "(blank)"
    return str(value)


def _save_message(name, changes):
    """The line flashed after an edit, naming what actually changed.

    An unconditional "updated" cannot distinguish a real save from one that wrote
    back the values already stored -- the case that makes an operator believe
    their edit was dropped. Naming the fields makes the two unmistakable.
    """
    if not changes:
        return f"No changes were made to {name} — the form was submitted with the stored values."

    listed = changes[:MAX_LISTED_CHANGES]
    parts = [
        f"{change['label']} {_describe(change['old'])} → {_describe(change['new'])}"
        for change in listed
    ]
    remaining = len(changes) - len(listed)
    if remaining:
        parts.append(f"and {remaining} more field{'s' if remaining != 1 else ''}")
    return f"{name} updated — " + ", ".join(parts) + "."


def process_add_edit_medicine(form_data, item=None):
    """Validate, then insert a new inventory item or update an existing one.

    `item` set means edit mode. Validation is identical either way -- the same
    validate_inventory_form() with the same required fields and format rules.

    Returns (item_row_id, context, message). The id and the context are mutually
    exclusive: an id means the caller should redirect to Medicine Inventory and
    flash `message`, a context means the caller should re-render the form. The
    message is built here rather than in each blueprint so the two roles cannot
    word the same outcome differently.
    """
    values = _extract_form(form_data)

    errors = validate_inventory_form(values)
    if errors:
        return None, add_edit_medicine_context(form=values, errors=errors, item=item), None

    # The submitted name, so a rename reports the name just saved.
    name = values.get("name") or (item["name"] if item else "Medicine")

    if item is not None:
        changes = update_inventory_item(item["id"], values)
        return item["id"], None, _save_message(name, changes)

    return create_inventory_item(values), None, f"{name} added to inventory."
