"""The browser's half of the audit fixes B12-B28 (Task 24), in a real Chromium.

B26  Patient Records, Sort by Age: babies are in age order (5 weeks, 5 months, 7 months).
B27  The Official dashboard at 390 px: a broadcast with a long unbroken run does not push the
     page wider than the screen.
The sections for the later batches are added below as each batch is done.
Every name, date and number below is made up.

Needs the DEV-only package: pip install -r requirements-dev.txt, then
python -m playwright install chromium. Without them it prints one SKIPPED line and nothing else;
tests/run_all.py reports that as a skip, never a pass.
"""
import socket
import sqlite3
import sys
import threading
from datetime import date, timedelta
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
