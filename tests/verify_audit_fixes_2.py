"""The fixes for the audit's open findings B12-B28 (Task 24).

B12  A second parent's report for one dose is refused in words, not with a server error.
B13  A huge reorder level is refused; B14 "inf", "nan", "1e9" and other non-numbers too.
B24  A PDF export never fails on long text; B25 the Patient Records search runs clean.
The sections for the later batches are added below as each batch is done.
Every name, date and number below is made up.
"""
import io
import re
import sqlite3
import sys
import zlib
from datetime import date, timedelta

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402

sys.stdout.reconfigure(errors="replace")

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID = 1, 2, 3, 5
REPO = _support.REPO

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail and not ok:
        for line in str(detail).splitlines()[:12]:
            print(f"       {line}")
    return ok


def section(title):
    print(f"\n--- {title} ---")


def db():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    return conn


def q1(sql, args=()):
    conn = db()
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def run_sql(sql, args=()):
    conn = db()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def client_as(user_id):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        _support.open_session(sess)
    return c


def body(response):
    return response.get_data(as_text=True)


def pdf_text(data):
    out = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            out.append(zlib.decompress(match.group(1)).decode("latin-1"))
        except Exception:
            out.append(match.group(1).decode("latin-1", "replace"))
    return "\n".join(out)


admin, staff, official, doctor = (client_as(i) for i in (ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID))
TODAY = date.today()

# ===========================================================================
section("B12. A SECOND PARENT'S REPORT FOR ONE DOSE IS REFUSED IN WORDS")
# ===========================================================================
born15 = date.fromisoformat(q1("SELECT birth_date FROM patients WHERE id = 15")[0])
first = run_sql("INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, date_administered, "
                "administered_by) VALUES (15, 'PENTA', 1, 'card', ?, 2)", ((born15 + timedelta(days=20)).isoformat(),))
second = run_sql("INSERT INTO immunizations (patient_id, vaccine_code, dose_number, evidence, date_administered, "
                 "administered_by) VALUES (15, 'PENTA', 1, 'card', ?, 2)", ((born15 + timedelta(days=60)).isoformat(),))
CHANGE = "/staff/patient_profile/15/dose-elsewhere/change"
r = staff.post(CHANGE, data={"record_id": str(first), "evidence": "parent_report", "date_given": "",
                             "place_given": "QA place one"})
check("setup: the first card record becomes a parent's report",
      r.status_code == 302 and q1("SELECT evidence FROM immunizations WHERE id = ?", (first,))[0] == "parent_report")
r = staff.post(CHANGE, data={"record_id": str(second), "evidence": "parent_report", "date_given": "",
                             "place_given": "QA typed place"})
page = body(r)
check("the second one is refused without a server error (200, the profile with the dialog open)",
      r.status_code == 200 and "elsewhereModal" in page, r.status_code)
check("the refusal says what is wrong, in plain words",
      "already has a parent&#39;s report" in page or "already has a parent's report" in page)
check("the typed place is kept in the reopened dialog", 'value="QA typed place"' in page)
check("nothing changed in the database",
      q1("SELECT evidence FROM immunizations WHERE id = ?", (second,))[0] == "card")
for rid in (first, second):
    run_sql("DELETE FROM immunizations WHERE id = ?", (rid,))

# ===========================================================================
section("B13, B14. INVENTORY NUMBERS: PLAIN, FINITE AND CAPPED")
# ===========================================================================
ITEM = {"category": "Medicine", "generic_name": "Qanumberol", "dosage_strength": "10 mg", "dosage_form": "tablet",
        "drug_class": "Analgesic / Antipyretic", "unit": "Tablet", "low_stock_threshold": "10", "unit_cost": "",
        "manufacturer": "", "supplier": "", "storage_location": "", "notes": "", "status": "Active"}


def add_item(**change):
    data = dict(ITEM)
    data.update(change)
    before = q1("SELECT COUNT(*) FROM inventory_items")[0]
    r = admin.post("/admin/add_edit_medicine", data=data)
    return r, q1("SELECT COUNT(*) FROM inventory_items")[0] - before


for label, change, message in (
        ("reorder level 999999999999999999999", {"low_stock_threshold": "999999999999999999999"},
         "Reorder level must be a whole number of 0 or more."),
        ("reorder level 100001", {"low_stock_threshold": "100001"}, "Enter a reorder level of 100,000 or less."),
        ("reorder level +5", {"low_stock_threshold": "+5"}, "Reorder level must be a whole number"),
        ("reorder level 1_000", {"low_stock_threshold": "1_000"}, "Reorder level must be a whole number"),
        ("unit cost inf", {"unit_cost": "inf"}, "Unit cost must be a number of 0 or more"),
        ("unit cost nan", {"unit_cost": "nan"}, "Unit cost must be a number of 0 or more"),
        ("unit cost 1e9", {"unit_cost": "1e9"}, "Unit cost must be a number of 0 or more"),
        ("unit cost -3", {"unit_cost": "-3"}, "Unit cost must be a number of 0 or more"),
        ("unit cost 1000001", {"unit_cost": "1000001"}, "Enter a unit cost of 1,000,000 or less.")):
    r, added = add_item(**change)
    check(f"{label}: refused beside the field, no server error, nothing saved",
          r.status_code == 200 and added == 0 and message in body(r), (r.status_code, added))
    check(f"{label}: the typed generic name is kept", 'value="Qanumberol"' in body(r))
r, added = add_item(low_stock_threshold="100000", unit_cost="2.50")
check("reorder level 100,000 and cost 2.50 are accepted", r.status_code == 302 and added == 1)
for label, qty in (("inf", "inf"), ("1e3", "1e3"), ("+5", "+5"), ("0", "0"), ("100001", "100001")):
    item = q1("SELECT id FROM inventory_items WHERE generic_name = 'Qanumberol'")[0]
    n = q1("SELECT COUNT(*) FROM inventory_batches WHERE inventory_item_id = ?", (item,))[0]
    r = admin.post(f"/admin/medicine_inventory/{item}/receive", data={
        "lot_number": "QA-LOT", "expiry_date": (TODAY + timedelta(days=400)).isoformat(), "quantity": qty,
        "date_received": TODAY.isoformat(), "source": "DOH", "brand_name": ""})
    check(f"receive quantity {label}: refused, no server error",
          r.status_code == 200 and q1("SELECT COUNT(*) FROM inventory_batches WHERE inventory_item_id = ?",
                                      (item,))[0] == n)

# ===========================================================================
section("B24. A PDF EXPORT NEVER FAILS ON LONG TEXT")
# ===========================================================================
from utils.document import CELL_CAPS, render  # noqa: E402

LONG = "Purok " + ("Qalongaddress " * 300)
run_sql("UPDATE patients SET address = ? WHERE id = 3", (LONG.strip(),))
for who, client, url in (("Staff", staff, "/staff/patient_records/export.pdf"),
                         ("Administrator", admin, "/admin/patient_records/export.pdf")):
    r = client.get(url)
    check(f"{who}: the Patient Records PDF is produced with a 4,000-character address on file",
          r.status_code == 200 and r.data[:4] == b"%PDF", r.status_code)
r = staff.get("/staff/patient_records/export.xlsx")
from openpyxl import load_workbook  # noqa: E402

cells = [str(c) for ws in load_workbook(io.BytesIO(r.data)).worksheets
         for row in ws.iter_rows(values_only=True) for c in row if c]
check("the Excel file keeps the long address in full", any(LONG.strip() in c for c in cells))
# Straight at the renderer: one cell far taller than a page, and an unbroken word.
sheets = [{"intro": "QA", "blocks": []}, {"heading": "QA", "intro": "", "blocks": [{
    "title": "QA", "columns": ["A", "B", "C", "D", "E", "F"],
    "rows": [["x" * 9000, "y " * 4000, "z", 1, 2.5, None], ["short", "short", "z", 1, 2.5, None]]}]}]
pdf = render(sheets, "QA Org", "QA", "QA", "QA", "QA")
text = pdf_text(pdf)
check("the renderer draws a 9,000-character cell and an 8,000-character cell (shortened with ...)",
      pdf[:4] == b"%PDF" and "short" in text)
normal = render([{"intro": "QA", "blocks": []}, {"heading": "QA", "intro": "", "blocks": [{
    "title": "QA", "columns": ["A", "B"], "rows": [["Ordinary text that fits", 3]]}]}], "QA", "QA", "QA", "QA", "QA")
check("ordinary text is never shortened", "Ordinary text that fits" in pdf_text(normal) and CELL_CAPS[0] is None)
run_sql("UPDATE patients SET address = 'Purok 1, Barangay Poblacion' WHERE id = 3")

# ===========================================================================
section("B25. PATIENT RECORDS SEARCH: NO SCRIPT ERROR")
# ===========================================================================
template = (REPO / "templates" / "patient_records.html").read_text(encoding="utf-8")
check("the search no longer looks for the old 'div[style]' wrapper",
      "closest('div[style]')" not in template and "closest('.table-responsive')" in template)
page = body(staff.get("/staff/patient_records"))
check("the table sits in a .table-responsive box and the empty message is outside it",
      re.search(r'<div class="table-responsive">\s*<table class="patient-table" id="patientTable">', page) is not None
      and page.find('id="emptyState"') > page.find("</table>"))

# ===========================================================================
section("B20. ONE COMPOSE FORM SENDS ONE BROADCAST")
# ===========================================================================
import threading  # noqa: E402

SEND = "/admin/sms_notifications/send"


def page_reference(client, url="/admin/sms_notifications"):
    m = re.search(r'name="send_reference" value="(SMS-\d{4}-\d{4,6})"', body(client.get(url)))
    return m.group(1) if m else None


def broadcasts():
    return q1("SELECT COUNT(*) FROM sms_broadcasts")[0]


ref = page_reference(admin)
check("the compose form carries the next reference as its one-time token", ref is not None, ref)
page = body(admin.get("/admin/sms_notifications"))
check("the Send button disables itself after the first click (script present)",
      'id="composeSend"' in page and "form.dataset.sending" in page and "send.disabled = true" in page)
recipients = None
form = {"message": "QA double press test", "audience": "all_patients", "category": "", "send_reference": ref}
n0 = broadcasts()
second_admin = client_as(ADMIN_ID)
codes = [None, None]


def press(i, client):
    codes[i] = client.post(SEND, data=form).status_code


threads = [threading.Thread(target=press, args=(0, admin)), threading.Thread(target=press, args=(1, second_admin))]
for t in threads:
    t.start()
for t in threads:
    t.join()
row = q1("SELECT id, reference, status, recipient_count, sent_count FROM sms_broadcasts ORDER BY id DESC LIMIT 1")
check("two requests at the same moment: no server error", codes == [302, 302], codes)
check("... exactly one broadcast is recorded, under the form's reference",
      broadcasts() == n0 + 1 and row["reference"] == ref, (broadcasts() - n0, row["reference"]))
check("... its recipients were texted once (one recipient row each) and the row is complete",
      q1("SELECT COUNT(*) FROM sms_broadcast_recipients WHERE broadcast_id = ?", (row["id"],))[0]
      == row["recipient_count"] == row["sent_count"] and row["status"] == "Sent")
r = admin.post(SEND, data=form)
shown = body(admin.get("/account"))
check("the same form sent again (back button, refresh): refused, nothing sent",
      r.status_code == 302 and broadcasts() == n0 + 1)
check("... with a plain message", f"This broadcast was already sent ({ref}). It was not sent again." in shown)
stale = dict(form, send_reference=ref, message="QA stale form")
admin.post(SEND, data=dict(form, send_reference=page_reference(admin), message="QA other sender"))
r = admin.post(SEND, data=dict(stale, send_reference=f"SMS-{TODAY.year}-9999"))
check("a form whose reference was taken by another broadcast: refused, dialog reopened with the typed message",
      r.status_code == 200 and "QA stale form" in body(r) and "was not sent" in body(r)
      and broadcasts() == n0 + 2)
r = admin.post(SEND, data=dict(form, send_reference="not-a-reference", message="QA forged"))
check("a malformed reference: refused, nothing sent", r.status_code == 200 and broadcasts() == n0 + 2)
r = admin.post(SEND, data={"message": "QA no form", "audience": "all_patients", "category": ""})
check("a post with no compose form (the demo seed's path) still sends once, under the next reference",
      r.status_code == 302 and broadcasts() == n0 + 3)

# ---------------------------------------------------------------------------
failed = [name for name, ok in results if not ok]
print("\n" + "=" * 78)
print(f"RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
for name in failed:
    print(f"  FAILED: {name}")
print("=" * 78)
sys.exit(1 if failed else 0)
