"""Migration: stock is kept in batches, medicines are named by generic name (Task 12).

Each item's quantity and expiry date become one opening batch (lot "Opening stock"), and
each existing dispensing row is linked to that batch. A medicine's name is split into
generic name, strength and dosage form where that can be done, and the display name is
rebuilt from them ("Paracetamol 500 mg tablet"). A medicine that cannot be split is left as
it is and counted, so staff can fix it with Edit details. The five columns that moved to the
batches (stock_quantity, expiry_date, date_received, batch_number, brand_name) are then
dropped from inventory_items.

The database defaults to app.db (config.DATABASE). A copy is saved first in the
IDS-BPHCSN-backups folder next to the project.

Run: python migrations/migrate_inventory_batches.py (project root). Safe to run twice.
"""
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import sys as _sys
from pathlib import Path as _P

_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))  # so it runs from the project root
import config  # loads .env into the environment

PROJECT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "inventory-batches"

ACTION = "Changed how stock is recorded"
MODULE = "Medicine Inventory"

# The vocabulary is written out here on purpose: a migration must keep working when the
# application's constants change later.
FORMS = ("tablet", "capsule", "syrup", "suspension", "drops", "sachet", "injection",
         "cream", "ointment", "inhaler", "other")
OLD_FORM_TO_NEW = {"nebule": "other"}
OPENING_LOT = "Opening stock"
MOVED_COLUMNS = ("stock_quantity", "expiry_date", "date_received", "batch_number", "brand_name")

NEW_TABLES = (
    """
    CREATE TABLE inventory_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inventory_item_id INTEGER NOT NULL,
        lot_number TEXT NOT NULL,
        expiry_date TEXT,
        quantity_received INTEGER NOT NULL CHECK (quantity_received >= 0),
        quantity_remaining INTEGER NOT NULL CHECK (quantity_remaining >= 0),
        date_received TEXT NOT NULL,
        source TEXT NOT NULL CHECK (source IN ('DOH', 'Municipal Health Office / RHU',
                                               'Barangay purchase', 'Donation', 'Other')),
        brand_name TEXT,
        received_by INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id) ON DELETE RESTRICT,
        FOREIGN KEY (received_by) REFERENCES users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE inventory_removals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        reason TEXT NOT NULL CHECK (reason IN ('Expired', 'Damaged', 'Lost', 'Returned',
                                               'Count correction')),
        note TEXT,
        removed_by INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (batch_id) REFERENCES inventory_batches(id) ON DELETE RESTRICT,
        FOREIGN KEY (removed_by) REFERENCES users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE medicine_dispensing_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dispensing_id INTEGER NOT NULL,
        batch_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        FOREIGN KEY (dispensing_id) REFERENCES medicine_dispensing(id) ON DELETE CASCADE,
        FOREIGN KEY (batch_id) REFERENCES inventory_batches(id) ON DELETE RESTRICT
    )
    """,
)
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_inventory_batches_item "
    "ON inventory_batches(inventory_item_id, expiry_date)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_removals_batch ON inventory_removals(batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_dispensing_batches_dispensing "
    "ON medicine_dispensing_batches(dispensing_id)",
    "CREATE INDEX IF NOT EXISTS idx_dispensing_batches_batch "
    "ON medicine_dispensing_batches(batch_id)",
)

_NUM = r"\d[\d,]*(?:\.\d+)?"
_UNIT = r"(?:mg|mcg|g|ml|l|iu|units?|%)"
_STRENGTH = re.compile(
    rf"{_NUM}\s*/\s*{_NUM}\s*{_UNIT}|{_NUM}\s*{_UNIT}(?:\s*/\s*(?:{_NUM})?\s*{_UNIT}?)?",
    re.IGNORECASE)


def needs_work(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return "inventory_batches" not in tables


def _backup(db_path, backup_dir):
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{Path(db_path).name}.PRETASK_BACKUP_{TASK}_{stamp}"
    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_strength(text):
    """'500mg' -> '500 mg', '400/80mg' -> '400/80 mg'. One space between a number and its unit."""
    return re.sub(r"(\d)\s*(mg|mcg|ug|g|kg|ml|l|iu|units?|meq|mmol|%)(?![A-Za-z])", r"\1 \2",
                  _clean(text), flags=re.IGNORECASE)


def split_name(name, generic_name, strength, dosage_form):
    """(generic, strength, form) for a medicine, or None when any of the three is unknown."""
    name, generic = _clean(name), _clean(generic_name)
    strength = normalize_strength(strength)
    form = _clean(dosage_form).lower()
    form = OLD_FORM_TO_NEW.get(form, form)
    if form not in FORMS:
        form = ""

    rest = name
    if not strength:
        found = _STRENGTH.search(name)
        if found:
            strength = normalize_strength(found.group(0))
    found = _STRENGTH.search(rest)
    if found:
        rest = (rest[:found.start()] + " " + rest[found.end():])
    word_found = ""
    for word in FORMS + tuple(OLD_FORM_TO_NEW):
        match = re.search(rf"\b{word}s?\b", rest, re.IGNORECASE)
        if match:
            word_found = OLD_FORM_TO_NEW.get(word, word)
            rest = rest[:match.start()] + " " + rest[match.end():]
            break
    if not form:
        form = word_found
    if not generic:
        generic = _clean(rest)
    if generic and strength and form:
        return generic[:1].upper() + generic[1:], strength, form
    return None


def build_name(generic, strength, form):
    return " ".join(part for part in (generic, strength, form) if part)


def run(db_path, backup_dir=BACKUP_DIR):
    """Apply the migration. Returns a dict describing what happened."""
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise SystemExit(f"No database at {db_path}")
    result = {"database": db_path, "backup": None, "items": 0, "parsed": 0, "needs_fix": 0,
              "supplies": 0, "opening_batches": 0, "dispensing_linked": 0, "problems": []}
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        if not needs_work(conn):
            return result
        result["backup"] = str(_backup(db_path, backup_dir))
        problems = result["problems"]
        items = [dict(r) for r in conn.execute("SELECT * FROM inventory_items ORDER BY id")]
        dispensing = [dict(r) for r in conn.execute("SELECT * FROM medicine_dispensing")]
        stock_before = sum(item["stock_quantity"] or 0 for item in items)
        result["items"] = len(items)
        audit_before = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        actor = conn.execute(
            "SELECT id FROM users WHERE role = 'Admin' AND is_active = 1 "
            "ORDER BY id LIMIT 1").fetchone()
        if actor is None:
            raise SystemExit("Stopped. No active Administrator account to file the entry under.")

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            for statement in NEW_TABLES:
                conn.execute(statement)

            batch_of = {}
            for item in items:
                stock = item["stock_quantity"] or 0
                received = item["date_received"] or str(item["created_at"] or "")[:10]
                cursor = conn.execute(
                    "INSERT INTO inventory_batches (inventory_item_id, lot_number, expiry_date, "
                    "quantity_received, quantity_remaining, date_received, source, brand_name) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'Other', ?)",
                    (item["id"], OPENING_LOT, item["expiry_date"] or None, stock, stock,
                     received or datetime.now().strftime("%Y-%m-%d"),
                     _clean(item["brand_name"]) or None))
                batch_of[item["id"]] = cursor.lastrowid
                result["opening_batches"] += 1

                if item["category"] == "Medicine":
                    parts = split_name(item["name"], item["generic_name"],
                                       item["dosage_strength"], item["dosage_form"])
                    if parts is None:
                        result["needs_fix"] += 1
                        continue
                    generic, strength, form = parts
                    conn.execute(
                        "UPDATE inventory_items SET generic_name = ?, dosage_strength = ?, "
                        "dosage_form = ?, name = ? WHERE id = ?",
                        (generic, strength, form, build_name(generic, strength, form),
                         item["id"]))
                    result["parsed"] += 1
                else:
                    # A supply keeps a simple item name (in generic_name) and a size.
                    base = _clean(item["generic_name"]) or _clean(item["name"])
                    size = _clean(item["dosage_strength"])
                    conn.execute(
                        "UPDATE inventory_items SET generic_name = ?, dosage_strength = ?, "
                        "dosage_form = NULL, name = ? WHERE id = ?",
                        (base, size or None, build_name(base, size, ""), item["id"]))
                    result["supplies"] += 1

            for row in dispensing:
                conn.execute(
                    "INSERT INTO medicine_dispensing_batches (dispensing_id, batch_id, quantity) "
                    "VALUES (?, ?, ?)",
                    (row["id"], batch_of[row["inventory_item_id"]], row["quantity_dispensed"]))
                result["dispensing_linked"] += 1

            conn.execute("DROP INDEX IF EXISTS idx_inventory_low_stock")
            for column in MOVED_COLUMNS:
                conn.execute(f"ALTER TABLE inventory_items DROP COLUMN {column}")
            for statement in INDEXES:
                conn.execute(statement)

            conn.execute(
                "INSERT INTO audit_logs (user_id, action, module, details) VALUES (?, ?, ?, ?)",
                (actor["id"], ACTION, MODULE,
                 "Done by the migration script migrate_inventory_batches.py, not by this "
                 f"account. {result['opening_batches']} opening "
                 f"batch{'' if result['opening_batches'] == 1 else 'es'} made from the old stock "
                 f"figures, {result['dispensing_linked']} dispensing "
                 f"row{'' if result['dispensing_linked'] == 1 else 's'} linked to them, "
                 f"{result['parsed']} medicine name{'' if result['parsed'] == 1 else 's'} split "
                 f"into generic name, strength and form, {result['needs_fix']} left to fix."))

            # Checks, before anything is committed.
            columns = {r[1] for r in conn.execute("PRAGMA table_info(inventory_items)")}
            if columns & set(MOVED_COLUMNS):
                problems.append("a moved column is still on inventory_items")
            if conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0] != len(items):
                problems.append("the item count changed")
            if conn.execute("SELECT COUNT(*) FROM inventory_batches").fetchone()[0] != len(items):
                problems.append("there is not one opening batch per item")
            stock_after = conn.execute(
                "SELECT COALESCE(SUM(quantity_remaining), 0) FROM inventory_batches").fetchone()[0]
            if stock_after != stock_before:
                problems.append("the stock total changed")
            linked = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(quantity), 0) FROM medicine_dispensing_batches"
            ).fetchone()
            if linked[0] != len(dispensing):
                problems.append("a dispensing row was not linked")
            if linked[1] != sum(r["quantity_dispensed"] for r in dispensing):
                problems.append("the linked quantities do not match the dispensed quantities")
            if conn.execute("SELECT COUNT(*) FROM medicine_dispensing").fetchone()[0] != len(dispensing):
                problems.append("the dispensing row count changed")
            if result["parsed"] + result["needs_fix"] + result["supplies"] != len(items):
                problems.append("the item counts do not add up")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                problems.append("foreign_key_check found a violation")
            if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] != audit_before + 1:
                problems.append("the audit table did not gain exactly one row")
            conn.execute("ROLLBACK" if problems else "COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys = ON")
        return result
    finally:
        conn.close()


def main(argv):
    db_path = argv[0] if argv else config.DATABASE
    print(f"database: {db_path}")
    result = run(db_path)
    if result["problems"]:
        print("STOPPED. Nothing was changed:")
        for problem in result["problems"]:
            print(f"  - {problem}")
        return 1
    if not result["backup"]:
        print("Nothing to do. Stock is already kept in batches.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"items: {result['items']}")
    print(f"medicine names split into generic name, strength and form: {result['parsed']}")
    print(f"medicines left to fix with Edit details: {result['needs_fix']}")
    print(f"supplies and equipment: {result['supplies']}")
    print(f"opening batches made: {result['opening_batches']}")
    print(f"dispensing rows linked to them: {result['dispensing_linked']}")
    print("1 audit entry recording this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
