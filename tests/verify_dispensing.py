# -*- coding: utf-8 -*-
"""Verification suite: dynamic medicine lines + shortened helper text.

Runs on a fresh test database built by tests/_support.py, so it can
dispense freely.
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile

import _support  # noqa: E402  (first: builds the test database, points the app at it)
ROOT = str(_support.REPO)

import app as appmod
import models.dispensing as dsp
from models.dispensing import (
    DISPENSE_MAX_ROWS,
    DISPENSE_START_ROWS,
    item_field,
    parse_dispensing,
    quantity_field,
)
from routes.consultation_views import _dispensing_row_count

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    line = ("  PASS  " if ok else "  FAIL  ") + name
    if not ok and detail != "":
        line += "   -- " + str(detail)
    print(line)


def section(title):
    print("")
    print(title)
    print("-" * len(title))


# --------------------------------------------------------------- test database
dbcopy = _support.DB_PATH
appmod.app.config["DATABASE"] = dbcopy
appmod.app.config["SECRET_KEY"] = "test-secret"
_support.attach(appmod.app)
print("test database: " + dbcopy)


def db():
    conn = sqlite3.connect(dbcopy)
    conn.row_factory = sqlite3.Row
    return conn


def login(client, username, password):
    return client.post("/login",
                       data={"username": username, "password": password},
                       follow_redirects=True)


def stock_of(item_id):
    conn = db()
    row = conn.execute("SELECT stock_quantity FROM inventory_items WHERE id=?",
                       (item_id,)).fetchone()
    conn.close()
    return row["stock_quantity"]


def dispensing_rows(consultation_id):
    conn = db()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM medicine_dispensing WHERE consultation_id=? ORDER BY id",
        (consultation_id,))]
    conn.close()
    return rows


def consultation_for(appointment_id):
    conn = db()
    row = conn.execute("SELECT id FROM consultations WHERE appointment_id=?",
                       (appointment_id,)).fetchone()
    conn.close()
    return row["id"] if row else None


def make_in_consultation(patient_id, day="2026-08-28"):
    """A fresh queue entry parked at In Consultation, ready to be written up."""
    conn = db()
    cur = conn.execute(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, "
        "appointment_date, appointment_time, status, is_walkin, checked_in_at) "
        "VALUES (?, 1, 'Walk-in Consultation', ?, '09:00', 'In Consultation', 1, "
        "datetime('now'))", (patient_id, day))
    conn.commit()
    appointment_id = cur.lastrowid
    conn.close()
    return appointment_id


BASE_FORM = {
    "chief_complaint": "Fever and cough for three days",
    "diagnosis": "Acute viral upper respiratory infection",
    "treatment_plan": "Paracetamol 500mg every 6 hours for 3 days; fluids; review in 3 days",
    "temperature": "37.8",
    "blood_pressure": "110/70",
    "pulse_rate": "88",
    "respiratory_rate": "18",
    "weight": "58",
    "remarks": "",
}


def with_lines(pairs):
    """BASE_FORM plus one (item_id, quantity) per medicine line, in order."""
    data = dict(BASE_FORM)
    for index, (item_id, quantity) in enumerate(pairs):
        data[item_field(index)] = str(item_id)
        data[quantity_field(index)] = str(quantity)
    return data


def rendered_line_count(html):
    return len(re.findall(r'name="dispense_item_\d+"', html))


# WHAT THIS SUITE DISPENSES IS READ OFF THE SHELF, NOT WRITTEN DOWN HERE.
# An earlier version named inventory ids directly and went stale the first time a
# real consultation emptied one of them -- which is exactly the thing this system
# is for. So the medicines come from dispensable_items(), the same function the
# form's dropdown is built from, and the expired one comes from the inventory
# rows that function excludes.
with appmod.app.app_context():
    from models.dispensing import dispensable_items
    SHELF = [dict(row) for row in dispensable_items()]

_conn = db()
SHELF_STOCK = {
    row["id"]: row["stock_quantity"]
    for row in _conn.execute("SELECT id, stock_quantity FROM inventory_items")
}
_expired = _conn.execute(
    "SELECT id, name FROM inventory_items "
    "WHERE category = 'Medicine' AND expiry_date < date('now') "
    "ORDER BY stock_quantity DESC LIMIT 1").fetchone()
_conn.close()

EXPIRED_ID, EXPIRED_NAME = (_expired["id"], _expired["name"]) if _expired else (None, None)

# Ordered so the tightest shelf comes last: the insufficient-stock block is aimed
# at whichever medicine has the least of it, which is the one a small quantity
# can legitimately exceed.
SHELF.sort(key=lambda row: SHELF_STOCK.get(row["id"], 0), reverse=True)
SHELF_IDS = [row["id"] for row in SHELF]
SCARCE_ID = SHELF_IDS[-1]
SCARCE_NAME = SHELF[-1]["label"].split()[0]
SCARCE_STOCK = SHELF_STOCK[SCARCE_ID]

print("shelf: %d dispensable medicines; scarcest is %s at %d; expired sample is %s"
      % (len(SHELF), SCARCE_NAME, SCARCE_STOCK, EXPIRED_NAME))
assert len(SHELF) >= 6, "this suite needs at least six dispensable medicines"
assert EXPIRED_ID is not None, "this suite needs an expired medicine to refuse"


# ==================================================== 1. constants and labels
section("1. Constants and field naming")
check("DISPENSE_START_ROWS is 2", DISPENSE_START_ROWS == 2, DISPENSE_START_ROWS)
check("DISPENSE_MAX_ROWS is 10", DISPENSE_MAX_ROWS == 10, DISPENSE_MAX_ROWS)
check("the ceiling is well past the old fixed 4", DISPENSE_MAX_ROWS > 4)
check("the old DISPENSE_ROWS constant is gone", not hasattr(dsp, "DISPENSE_ROWS"))
check("FIELD_LABELS covers every index up to the ceiling",
      all(item_field(i) in dsp.FIELD_LABELS and quantity_field(i) in dsp.FIELD_LABELS
          for i in range(DISPENSE_MAX_ROWS)))
check("FIELD_LABELS names line 10 correctly",
      dsp.FIELD_LABELS[quantity_field(9)] == "Quantity on line 10",
      dsp.FIELD_LABELS.get(quantity_field(9)))

# ==================================================== 2. the parser
section("2. parse_dispensing reads every line, not only the first four")
entries, errors = parse_dispensing(
    {k: v for i, a in enumerate(SHELF_IDS[:6])
     for k, v in ((item_field(i), str(a)), (quantity_field(i), "2"))})
check("six lines parsed", len(entries) == 6, len(entries))
check("no parse errors", errors == {}, errors)
check("line 5 (index 4) survived", any(e["index"] == 4 for e in entries))
check("line 6 (index 5) survived", any(e["index"] == 5 for e in entries))

TEN_ITEMS = SHELF_IDS[:DISPENSE_MAX_ROWS]
form_ten = {}
for i, item in enumerate(TEN_ITEMS):
    form_ten[item_field(i)] = str(item)
    form_ten[quantity_field(i)] = "1"
entries_ten, errors_ten = parse_dispensing(form_ten)
check("every line up to the ceiling parsed",
      len(entries_ten) == len(TEN_ITEMS), len(entries_ten))
check("no errors at the ceiling", errors_ten == {}, errors_ten)

beyond = dict(form_ten)
beyond[item_field(DISPENSE_MAX_ROWS)] = "1"
beyond[quantity_field(DISPENSE_MAX_ROWS)] = "1"
entries_beyond, _ = parse_dispensing(beyond)
check("a line past the ceiling is not read",
      len(entries_beyond) == len(TEN_ITEMS), len(entries_beyond))

_, errors_dup = parse_dispensing({item_field(0): str(SHELF_IDS[0]), quantity_field(0): "5",
                                  item_field(5): str(SHELF_IDS[0]), quantity_field(5): "5"})
check("the same medicine twice is refused on a line past 4",
      item_field(5) in errors_dup, errors_dup)

_, errors_half = parse_dispensing({quantity_field(5): "5"})
check("a half-filled line 6 is an error, not a silent drop",
      item_field(5) in errors_half, errors_half)

_, errors_big = parse_dispensing({item_field(7): str(SHELF_IDS[0]),
                                  quantity_field(7): "2026"})
check("the quantity typo guard still holds on line 8",
      quantity_field(7) in errors_big, errors_big)

# ==================================================== 3. how many lines render
section("3. How many lines the server renders")
check("a fresh form renders the starting count", _dispensing_row_count({}) == 2,
      _dispensing_row_count({}))
check("a bounce with 6 filled lines renders 6",
      _dispensing_row_count({item_field(i): "1" for i in range(6)}) == 6)
check("a bounce with only line 6 filled still renders 6",
      _dispensing_row_count({item_field(5): "1"}) == 6,
      _dispensing_row_count({item_field(5): "1"}))
check("a half-filled line 7 (quantity only) still renders 7",
      _dispensing_row_count({quantity_field(6): "3"}) == 7)
check("never fewer than the starting count",
      _dispensing_row_count({item_field(0): "1"}) == 2)
check("never more than the ceiling",
      _dispensing_row_count({item_field(i): "1" for i in range(DISPENSE_MAX_ROWS)})
      == DISPENSE_MAX_ROWS)

# STALE-FIX (2026-09-25): 60940ce made supplies and equipment dispensable and
# renamed the section's wording from "medicine" to "item" on purpose (the
# button id, the field labels, the flash, the helper note, and the profile tab
# "Dispensing History"). Every check below asserting the old word now asserts
# the new one, with the same property. "it blames the quantity, not the
# medicine" had been passing VACUOUSLY -- "Medicine on line 5" can no
# longer appear at all -- and tests something again with "Item on line 5".
# ==================================================== 4. both roles, end to end
# Task 5c: the Administrator no longer records consultations or dispenses -- that
# is the care team's. His run through this section became the Doctor's, which is
# the other role that dispenses, and the refusal of his old route is checked
# right after the loop.
ROLES = [
    ("doctor", _support.PASSWORDS["doctor"], "/staff/consultation/record/{}", "Doctor", 16),
    ("staff", _support.PASSWORDS["staff"], "/staff/consultation/record/{}", "Health Center Staff", 8),
]
ACCOUNT_IDS = {"admin": 1, "staff": 2, "doctor": 5}

for username, password, url_pattern, role, patient in ROLES:
    section("4. %s -- the form, both hard blocks, and a six-medicine save" % role)
    client = appmod.app.test_client()
    resp = login(client, username, password)
    check("%s signs in" % username, resp.status_code == 200, resp.status_code)

    # ---- the fresh form
    appointment = make_in_consultation(patient)
    page = client.get(url_pattern.format(appointment))
    html = page.get_data(as_text=True)
    check("the form loads", page.status_code == 200, page.status_code)
    check("renders exactly %d medicine lines" % DISPENSE_START_ROWS,
          rendered_line_count(html) == DISPENSE_START_ROWS, rendered_line_count(html))
    check("no longer renders the old fixed four", rendered_line_count(html) != 4)
    check("the Add another medicine button is on the page",
          'id="addItemLine"' in html)
    check("it is type=button, so it cannot submit the form",
          re.search(r'<button type="button"[^>]*id="addItemLine"', html) is not None)
    check("it is rendered hidden, for the JavaScript-off case",
          'id="addItemLine" hidden' in html)
    check("the blank row template is on the page", 'id="dispenseRowTemplate"' in html)
    check("the tbody carries the server's field prefixes",
          'data-item-prefix="dispense_item_"' in html
          and 'data-quantity-prefix="dispense_qty_"' in html)
    check("the tbody carries the ceiling",
          'data-max-rows="%d"' % DISPENSE_MAX_ROWS in html)
    template_html = html.split('id="dispenseRowTemplate"')[1].split("</template>")[0]
    check("the template row posts nothing until the script names it",
          template_html.count('name=""') == 2, template_html.count('name=""'))
    check("the template row carries the same medicine list as a real line",
          template_html.count("in stock</option>")
          == html.split('id="dispenseRows"')[1].split("</tbody>")[0]
                 .count("in stock</option>") // DISPENSE_START_ROWS)

    # ---- hard block 1, on a line BEYOND the old four: insufficient stock
    over = SCARCE_STOCK + 40
    lines = [(item, 5) for item in SHELF_IDS[:4]] + [(SCARCE_ID, over)]
    before = {item: stock_of(item) for item, _ in lines}
    resp = client.post(url_pattern.format(appointment), data=with_lines(lines))
    html = resp.get_data(as_text=True)
    check("%d %s against a shelf of %d, on LINE 5, is refused"
          % (over, SCARCE_NAME, SCARCE_STOCK), "was not saved" in html, "no refusal")
    check("the refusal names line 5", "Quantity on line 5" in html, "line 5 unnamed")
    check("it blames the quantity, not the medicine",
          "Item on line 5" not in html)
    check("the refusal says how many remain",
          re.search(r"Only .*%s" % SCARCE_NAME, html) is not None)
    check("no consultation was written", consultation_for(appointment) is None)
    check("not one of the five lines moved stock",
          all(stock_of(item) == before[item] for item in before),
          {i: (before[i], stock_of(i)) for i in before})
    check("the bounce replays all five lines", rendered_line_count(html) == 5,
          rendered_line_count(html))
    check("it kept the amount the operator typed on line 5",
          'name="dispense_qty_4" value="%d"' % over in html)
    check("it kept the scarce medicine selected on line 5",
          '<option value="%d" selected' % SCARCE_ID in html)

    # ---- hard block 2, on a line beyond the old four: expired medicine
    before_expired = stock_of(EXPIRED_ID)
    resp = client.post(url_pattern.format(appointment),
                       data=with_lines([(item, 5) for item in SHELF_IDS[:5]]
                                       + [(EXPIRED_ID, 5)]))
    html = resp.get_data(as_text=True)
    check("expired %s on LINE 6 is refused" % EXPIRED_NAME, "was not saved" in html)
    check("the refusal names the expiry", "expired on" in html)
    check("it blames the medicine, not the quantity", "Item on line 6" in html)
    check("expired stock was not touched", stock_of(EXPIRED_ID) == before_expired)
    check("no consultation was written", consultation_for(appointment) is None)
    check("the bounce replays all six lines", rendered_line_count(html) == 6,
          rendered_line_count(html))

    # ---- the real save: SIX medicines in one visit
    six = list(zip(SHELF_IDS[:6], (12, 6, 8, 9, 15, 20)))
    before = {item: stock_of(item) for item, _ in six}
    resp = client.post(url_pattern.format(appointment), data=with_lines(six),
                       follow_redirects=True)
    html = resp.get_data(as_text=True)
    check("the six-medicine consultation saved", "was not saved" not in html)
    check("the flash says 6 items dispensed", "6 items dispensed" in html,
          "flash not found")
    consultation_id = consultation_for(appointment)
    check("the consultation row exists", consultation_id is not None)
    stored = dispensing_rows(consultation_id) if consultation_id else []
    check("SIX dispensing rows are in the database", len(stored) == 6, len(stored))
    check("every medicine and quantity matches what was submitted",
          sorted((r["inventory_item_id"], r["quantity_dispensed"]) for r in stored)
          == sorted(six),
          sorted((r["inventory_item_id"], r["quantity_dispensed"]) for r in stored))
    check("every one of the six came off the shelf",
          all(stock_of(item) == before[item] - qty for item, qty in six),
          {item: (before[item], stock_of(item)) for item, _ in six})
    check("lines 5 and 6 are on file too, not only the first four",
          any(r["inventory_item_id"] == six[4][0] for r in stored)
          and any(r["inventory_item_id"] == six[5][0] for r in stored))
    check("the dispensing rows name the acting account",
          all(r["dispensed_by"] == ACCOUNT_IDS[username] for r in stored),
          [r["dispensed_by"] for r in stored])
    check("the visit is marked Completed", "Completed" in html)

# ==================================================== 4b. the Administrator is refused
section("4b. Administrator -- refused on the server, and nothing leaves the shelf (Task 5c)")
client = appmod.app.test_client()
resp = login(client, "admin", _support.PASSWORDS["admin"])
check("admin signs in", resp.status_code == 200, resp.status_code)
appointment = make_in_consultation(14)
lines = [(item, 3) for item in SHELF_IDS[:2]]
before = {item: stock_of(item) for item, _ in lines}
page = client.get("/admin/consultation/record/%d" % appointment)
check("his old form URL no longer exists (404)", page.status_code == 404, page.status_code)
resp = client.post("/admin/consultation/record/%d" % appointment, data=with_lines(lines))
check("a POST to it is refused (404)", resp.status_code == 404, resp.status_code)
resp = client.post("/staff/consultation/record/%d" % appointment, data=with_lines(lines))
check("a POST to the care team's URL sends him to his dashboard",
      resp.status_code == 302 and resp.headers.get("Location", "").endswith("/dashboard"),
      (resp.status_code, resp.headers.get("Location")))
check("no consultation was written", consultation_for(appointment) is None)
check("nothing came off the shelf",
      all(stock_of(item) == before[item] for item in before),
      {i: (before[i], stock_of(i)) for i in before})

# ==================================================== 5. the ceiling itself
section("5. The ceiling itself -- %d medicines in one visit" % len(TEN_ITEMS))
client = appmod.app.test_client()
login(client, "doctor", _support.PASSWORDS["doctor"])  # PORTED: clinician
appointment = make_in_consultation(12)
ten = [(item, 2) for item in TEN_ITEMS]
before = {item: stock_of(item) for item, _ in ten}
resp = client.post("/staff/consultation/record/%d" % appointment,
                   data=with_lines(ten), follow_redirects=True)
html = resp.get_data(as_text=True)
check("the %d-medicine consultation saved" % len(ten), "was not saved" not in html)
check("the flash says %d items dispensed" % len(ten),
      "%d items dispensed" % len(ten) in html)
consultation_id = consultation_for(appointment)
stored = dispensing_rows(consultation_id) if consultation_id else []
check("%d dispensing rows are on file" % len(ten), len(stored) == len(ten), len(stored))
check("every one of them came off the shelf",
      all(stock_of(item) == before[item] - qty for item, qty in ten))
check("this reached the ceiling, or the whole shelf where that is smaller",
      len(ten) == min(DISPENSE_MAX_ROWS, len(SHELF)),
      (len(ten), DISPENSE_MAX_ROWS, len(SHELF)))

# ==================================================== 6. helper text
section("6. Helper text -- what went and what stayed")
appointment = make_in_consultation(16)
html = client.get("/staff/consultation/record/%d" % appointment).get_data(as_text=True)
text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

REMOVED = [
    "an invented number is worse than a blank",
    "Nothing here is graded due or overdue",
    "which is exactly why being in stock is not the test",
    "taking it back would mean putting units on the shelf",
    "the same rule the immunisation record follows",
    "Leave every box unticked",
    "Leave every line blank",
    "A dose number is only worth filling in",
    "not warned about",
]
for phrase in REMOVED:
    check('design-reasoning prose gone: "%s"' % phrase[:44], phrase not in text,
          "still on the page")

KEPT = [
    "Tick what was given today",
    "Other Vaccinations on",
    "dose number only where the vaccine has one",
    "comes off Medicine Inventory at once",
    "Dispensing History",
    "refused if the shelf holds less",
    "the item has expired",
]
for phrase in KEPT:
    check('rule still stated: "%s"' % phrase[:44], phrase in text, "MISSING")

# STALE-FIX: was the literal "Aug 28, 2026" -- the day this suite was written.
# A new consultation is dated today() (routes/consultation_views.py), so the note
# must print today's date through the same filter the template uses.
from utils.dates import display_date, today as _today
check("the vaccination note still dates the doses", display_date(_today()) in text,
      display_date(_today()))
notes = re.findall(r'<div class="cohort-note">(.*?)</div>', html, re.S)
lengths = [len(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", n)).strip()) for n in notes]
print("       cohort-note lengths on this page: %s" % lengths)
check("the vaccination note is under 250 characters", lengths[-2] < 250, lengths[-2])
check("the medicine note is under 300 characters", lengths[-1] < 300, lengths[-1])

# ==================================================== 7. no regressions
section("7. No regression on the ordinary paths")
appointment = make_in_consultation(16)
resp = client.post("/staff/consultation/record/%d" % appointment,
                   data=dict(BASE_FORM), follow_redirects=True)
html = resp.get_data(as_text=True)
check("a consultation with no medicine at all still saves",
      "was not saved" not in html)
consultation_id = consultation_for(appointment)
check("and wrote no dispensing rows",
      consultation_id is not None and dispensing_rows(consultation_id) == [])

appointment = make_in_consultation(16)
ONE_ID = SHELF_IDS[0]
before_paracetamol = stock_of(ONE_ID)
resp = client.post("/staff/consultation/record/%d" % appointment,
                   data=with_lines([(ONE_ID, 5)]), follow_redirects=True)
html = resp.get_data(as_text=True)
check("a single-item consultation still saves", "1 item dispensed" in html)
check("and it moved the stock", stock_of(ONE_ID) == before_paracetamol - 5)

appointment = make_in_consultation(16)
data = with_lines([(ONE_ID, 5)])
data["diagnosis"] = ""
before_paracetamol = stock_of(ONE_ID)
resp = client.post("/staff/consultation/record/%d" % appointment, data=data)
html = resp.get_data(as_text=True)
check("a consultation error still bounces the whole form", "was not saved" in html)
check("and dispenses nothing when it does",
      stock_of(ONE_ID) == before_paracetamol)
check("and replays the medicine line",
      'name="dispense_qty_0" value="5"' in html)

# editing a saved consultation still refuses a repeat of what it already holds
appointment = make_in_consultation(16)
client.post("/staff/consultation/record/%d" % appointment,
            data=with_lines([(ONE_ID, 5)]), follow_redirects=True)
consultation_id = consultation_for(appointment)
data = with_lines([(SHELF_IDS[1], 5), (ONE_ID, 5)])
resp = client.post("/staff/consultation/edit/%d" % consultation_id, data=data)
html = resp.get_data(as_text=True)
check("editing refuses a medicine already dispensed at that visit",
      "already recorded for this visit" in html)
check("and the refusal names the second line", "Item on line 2" in html)

# ==================================================== summary
print("")
print("=" * 64)
print("PASS %d   FAIL %d" % (len(PASS), len(FAIL)))
if FAIL:
    print("")
    print("FAILURES:")
    for name in FAIL:
        print("  - " + name)
# The temporary folder and its database are removed by tests/_support.py.
sys.exit(1 if FAIL else 0)
