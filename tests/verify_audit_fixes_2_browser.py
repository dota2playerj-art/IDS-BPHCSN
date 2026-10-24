"""The browser's half of the audit fixes B12-B28 (Task 24), in a real Chromium.

B26  Patient Records, Sort by Age: babies are in age order (5 weeks, 5 months, 7 months).
B27  The Official dashboard at 390 px: a broadcast with a long unbroken run does not push the
     page wider than the screen.
B23  A device in Los Angeles with its clock two days behind: the age preview, the civil-status
     list and the "Printed ..." stamp follow the server's Philippine date, not the device's.
B16  A refused Remove from stock: the dialog opens again with the typed amount, reason and note.
Every name, date and number below is made up.

Needs the DEV-only package: pip install -r requirements-dev.txt, then
python -m playwright install chromium. Without them it prints one SKIPPED line and nothing else;
tests/run_all.py reports that as a skip, never a pass.
"""
import socket
import sqlite3
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(errors="replace")

INSTALL_HELP = ("To run it:  pip install -r requirements-dev.txt   then   "
                "python -m playwright install chromium")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIPPED: verify_audit_fixes_2_browser.py needs Playwright, which is not installed. "
          + INSTALL_HELP)
    sys.exit(0)

import _support  # noqa: E402  (builds the test folder and database, sets the test keys)

from app import create_app  # noqa: E402

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
ADMIN_ID = 1
TODAY = date.today()

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if detail and not ok:
        for line in str(detail).splitlines()[:12]:
            print(f"       {line}")
    return ok


def section(title):
    print(f"\n--- {title} ---", flush=True)


def q1(sql, args=()):
    conn = sqlite3.connect(TEST_DB)
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def run_sql(sql, args=()):
    conn = sqlite3.connect(TEST_DB)
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def add_patient(first, birth_date):
    pid = q1("SELECT MAX(id) FROM patients")[0] + 1
    run_sql("INSERT INTO patients (id, patient_id, first_name, last_name, birth_date, sex, civil_status, "
            "address, municipality, province, contact_number, status) VALUES (?, ?, ?, 'Qabrowser', ?, "
            "'Female', 'Single', 'Purok 1', 'San Francisco', 'Surigao del Norte', ?, 'Active')",
            (pid, f"PAT-{pid:03d}", first, birth_date, f"0900000{pid:04d}"))
    return f"PAT-{pid:03d}"


# The babies of B26, deliberately inserted out of age order.
BABIES = [(label, add_patient(f"Zzqababy{label}", (TODAY - timedelta(days=days)).isoformat()))
          for label, days in (("m5", 160), ("m7", 220), ("w5", 38), ("m9", 280))]
AGE_ORDER = ["w5", "m5", "m7", "m9"]

# The broadcast of B27: 1,600 letters with no space, the newest one on the Official's dashboard.
run_sql("INSERT INTO sms_broadcasts (reference, message, category, audience, audience_label, recipient_count, "
        "sent_count, failed_count, segments, encoding, status, delivery_mode, sent_by) VALUES "
        "('BC-ZZB27', ?, 'General Reminder', 'all_patients', 'All patients', 1, 1, 0, 1, 'GSM-7', 'Sent', "
        "'simulated', ?)", ("Q" * 1600, ADMIN_ID))


# The batch of B16, on the newest active item.
B16_ITEM = q1("SELECT id FROM inventory_items WHERE status = 'Active' ORDER BY id DESC LIMIT 1")[0]
B16_BATCH = run_sql("INSERT INTO inventory_batches (inventory_item_id, lot_number, expiry_date, quantity_received, "
                    "quantity_remaining, date_received, source) VALUES (?, 'QA-B16B', ?, 30, 30, ?, 'DOH')",
                    (B16_ITEM, (TODAY + timedelta(days=300)).isoformat(), TODAY.isoformat()))


def start_server():
    from utils.server import build_server

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = build_server(app, "127.0.0.1", port)
    server.prepare()
    threading.Thread(target=server.serve, daemon=True).start()
    return f"http://127.0.0.1:{port}", server.stop


def watch_errors(page):
    errors = []
    page.on("pageerror", lambda e: errors.append("script: " + str(e)[:140]))
    return errors


def sign_in(browser, base_url, username):
    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    page.goto("/login")
    page.fill("#username", username)
    page.fill("#password", _support.PASSWORDS[username])
    page.click("button[type=submit]")
    page.wait_for_load_state()
    ok = "/login" not in page.url
    state = context.storage_state() if ok else None
    context.close()
    check(f"{username} signs in", ok)
    return state


def run_checks(browser, base_url):
    states = {name: sign_in(browser, base_url, name) for name in ("staff", "official")}
    if not all(states.values()):
        return

    section("B26. PATIENT RECORDS, SORT BY AGE")
    context = browser.new_context(base_url=base_url, storage_state=states["staff"],
                                  viewport={"width": 1366, "height": 800})
    page = context.new_page()
    errors = watch_errors(page)
    page.goto("/staff/patient_records")
    page.wait_for_load_state()
    page.evaluate("document.querySelector('.sort-option[data-sort-key=\"age\"]').click()")
    shown = page.evaluate("Array.from(document.querySelectorAll('tr.patient-row'))"
                          ".map(r => r.querySelector('.pat-id').textContent.trim())")
    position = {ref: i for i, ref in enumerate(shown)}
    babies = dict(BABIES)
    got = sorted(AGE_ORDER, key=lambda label: position.get(babies[label], 10 ** 6))
    check("youngest first: 5 weeks, 5 months, 7 months, 9 months", got == AGE_ORDER, got)
    first_adult = next((i for i, ref in enumerate(shown) if ref not in babies.values()
                        and int(q1("SELECT birth_date < ? FROM patients WHERE patient_id = ?",
                                   ((TODAY - timedelta(days=366)).isoformat(), ref))[0] or 0)), None)
    check("every baby comes before the first patient over a year old",
          first_adult is not None and max(position[babies[label]] for label in AGE_ORDER) < first_adult)
    page.evaluate("document.querySelector('.sort-option[data-sort-key=\"age\"]').click()")
    shown = page.evaluate("Array.from(document.querySelectorAll('tr.patient-row'))"
                          ".map(r => r.querySelector('.pat-id').textContent.trim())")
    position = {ref: i for i, ref in enumerate(shown)}
    got = sorted(AGE_ORDER, key=lambda label: position.get(babies[label], -1))
    check("oldest first reverses it: 9 months, 7 months, 5 months, 5 weeks", got == AGE_ORDER[::-1], got)
    check("no page script failed", not errors, "\n".join(errors))
    context.close()

    section("B27. OFFICIAL DASHBOARD AT 390 PX WITH A LONG UNBROKEN BROADCAST")
    context = browser.new_context(base_url=base_url, storage_state=states["official"],
                                  viewport={"width": 390, "height": 800})
    page = context.new_page()
    page.goto("/official/dashboard")
    page.wait_for_load_state()
    check("set-up: the long broadcast is on the dashboard", "QQQQQQQQQQ" in page.evaluate("document.body.innerText"))
    wide = page.evaluate("document.documentElement.scrollWidth")
    check("no sideways scroll", wide <= 390, f"the page is {wide}px wide on a 390px screen")
    context.close()

    section("B23. A DEVICE IN LOS ANGELES WITH ITS CLOCK TWO DAYS BEHIND")
    from utils.dates import now as clinic_now, today as clinic_today

    context = browser.new_context(base_url=base_url, storage_state=states["staff"],
                                  timezone_id="America/Los_Angeles", viewport={"width": 1366, "height": 800})
    page = context.new_page()
    page.clock.set_system_time(datetime.now(timezone.utc) - timedelta(days=2))
    errors = watch_errors(page)
    page.goto("/staff/register-patient")
    page.wait_for_load_state()
    day = clinic_today()
    device_day = page.evaluate("(() => { const d = new Date(); return [d.getFullYear(), d.getMonth() + 1, d.getDate()]; })()")
    check("set-up: the device's own date is not the clinic's", device_day != [day.year, day.month, day.day],
          (device_day, day))
    try:
        eighteen = day.replace(year=day.year - 18)
    except ValueError:  # Feb 29
        eighteen = day.replace(year=day.year - 18, day=28)
    page.fill("#birthDate", eighteen.isoformat())
    page.dispatch_event("#birthDate", "change")
    age = page.input_value("#ageDisplay")
    options = page.evaluate("Array.from(document.querySelectorAll('#civilStatus option')).map(o => o.value)")
    check("born 18 years ago today (clinic date): the age preview says 18 years", age == "18 years", age)
    check("... and the civil-status list is the adult one (Married offered)", "Married" in options, options)
    page.fill("#birthDate", (eighteen + timedelta(days=1)).isoformat())
    page.dispatch_event("#birthDate", "change")
    check("one day short of 18: 17 years, only Single", page.input_value("#ageDisplay") == "17 years"
          and page.evaluate("Array.from(document.querySelectorAll('#civilStatus option')).map(o => o.value)")
          == ["Single"])
    for path in ("/staff/patient_records", f"/staff/patient_profile/{q1('SELECT MIN(id) FROM patients')[0]}"):
        page.goto(path)
        page.wait_for_load_state()
        # The clinic's date and hour now or two minutes ago (the page was built in between).
        moments = (clinic_now(), clinic_now() - timedelta(minutes=2))
        expected = {f"{m:%B} {m.day}, {m.year} at {(m.hour + 11) % 12 + 1}:" for m in moments}
        stamps = page.evaluate("Array.from(document.querySelectorAll('.print-stamp')).map(e => e.textContent)")
        check(f"{path}: the 'Printed' stamp carries the clinic's date and hour", stamps
              and all(any(s.startswith(e) for e in expected) for s in stamps), (stamps, expected))
    check("no page script failed", not errors, "\n".join(errors))
    context.close()

    section("B16. A REFUSED REMOVE FROM STOCK REOPENS THE DIALOG WITH WHAT WAS TYPED")
    context = browser.new_context(base_url=base_url, storage_state=states["staff"],
                                  viewport={"width": 1366, "height": 800})
    page = context.new_page()
    errors = watch_errors(page)
    page.goto(f"/staff/medicine_inventory/{B16_ITEM}")
    page.wait_for_load_state()
    page.click(f"button[data-batch-id='{B16_BATCH}']")
    page.wait_for_selector("#removeStockModal.show")
    page.evaluate("document.getElementById('removeQuantity').removeAttribute('max')")  # as a stale page would
    page.fill("#removeQuantity", "31")
    page.select_option("#removeReason", "Lost")
    page.fill("#removeNote", "QA browser note")
    page.click("#removeStockModal button[type=submit]")
    page.wait_for_load_state()
    page.wait_for_selector("#removeStockModal.show", timeout=5000)
    state = page.evaluate("""() => ({
        quantity: document.getElementById('removeQuantity').value,
        reason: document.getElementById('removeReason').value,
        note: document.getElementById('removeNote').value,
        lot: document.getElementById('removeLot').textContent,
        message: (document.querySelector('#removeStockModal .invalid-feedback') || {}).textContent || ''})""")
    check("the dialog is open again with 31, Lost and the note, on lot QA-B16B",
          state["quantity"] == "31" and state["reason"] == "Lost" and state["note"] == "QA browser note"
          and state["lot"] == "QA-B16B", state)
    check("... with the message beside the amount", "holds only 30" in state["message"], state)
    check("nothing was removed", q1("SELECT quantity_remaining FROM inventory_batches WHERE id = ?",
                                    (B16_BATCH,))[0] == 30)
    check("no page script failed", not errors, "\n".join(errors))
    context.close()


def main():
    base_url, stop_server = start_server()
    try:
        playwright_cm = sync_playwright().start()
        try:
            browser = playwright_cm.chromium.launch()
        except Exception as problem:
            playwright_cm.stop()
            print("SKIPPED: verify_audit_fixes_2_browser.py could not start Chromium "
                  f"({str(problem).splitlines()[0][:120]}). " + INSTALL_HELP)
            return None
        try:
            run_checks(browser, base_url)
        finally:
            browser.close()
            playwright_cm.stop()
    finally:
        stop_server()
    return True


if main() is None:
    sys.exit(0)

failed = [name for name, ok in results if not ok]
print("\n" + "=" * 78)
print(f"RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
for name in failed:
    print(f"  FAILED: {name}")
print("=" * 78)
sys.exit(1 if failed else 0)
