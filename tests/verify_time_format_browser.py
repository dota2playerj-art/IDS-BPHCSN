"""The browser's half of the 12-hour clock (Task 21): static/js/time-format.js, in a real browser.

1. IDSTime.formatTime() / formatDateTime() give the same answers as utils/dates.py for the same
   cases, for all 1,440 minutes of a day, and whatever language the browser is set to.
2. The pages that show times, opened in Chromium at 360, 390 and 1366 pixels: the widest time
   ("12:35 PM") does not push the Patient Queue, the Doctor's dashboard, the referral slip or the
   Audit Logs wider than the screen, the printed-page stamp is 12-hour in a German-language
   browser, and no page script fails.

Needs the DEV-only package: pip install -r requirements-dev.txt, then
python -m playwright install chromium. Without them it prints one SKIPPED line and nothing else;
tests/run_all.py reports that as a skip, never a pass.
"""
import re
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
    print("SKIPPED: verify_time_format_browser.py needs Playwright, which is not installed. "
          + INSTALL_HELP)
    sys.exit(0)

import _support  # noqa: E402  (builds the test folder and database, sets the test keys)

from app import create_app  # noqa: E402

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
HELPER = Path(_support.REPO) / "static" / "js" / "time-format.js"
STAFF_ID = 2
WIDTHS = (360, 390, 1366)
TWELVE = re.compile(r"^(?:[1-9]|1[0-2]):[0-5]\d(?::[0-5]\d)? (?:AM|PM)$")
STAMP = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4} at (?:[1-9]|1[0-2]):[0-5]\d (?:AM|PM)$")

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


def run_sql(sql, args=()):
    conn = sqlite3.connect(TEST_DB)
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Visits at 12:35, the widest time of day on the 12-hour clock.
# ---------------------------------------------------------------------------
today = date.today()
run_sql("UPDATE appointments SET status = 'Completed' "
        "WHERE status IN ('In Consultation', 'Waiting', 'Waiting for the Doctor')")
from models.referrals import RHU  # noqa: E402

_next = [100]


def add_visit(status, days_ago=0, consultation=False):
    pid = _next[0]
    _next[0] += 1
    run_sql("INSERT INTO patients (id, patient_id, first_name, last_name, birth_date, sex, "
            "civil_status, address, municipality, province, contact_number, status) VALUES "
            "(?, ?, 'Zztmbrowser', 'Timemark', '1985-01-01', 'Female', 'Single', 'Purok 1', "
            "'San Francisco', 'Surigao del Norte', ?, 'Active')",
            (pid, f"PAT-{pid:03d}", f"0900000{pid:04d}"))
    day = (today - timedelta(days=days_ago)).isoformat()
    visit = run_sql(
        "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, "
        "appointment_time, status, is_walkin, checked_in_at) VALUES (?, ?, 'Consultation', ?, "
        "'12:35', ?, 1, ?)", (pid, STAFF_ID, day, status, f"{day} 12:35:00"))
    if consultation:
        run_sql("INSERT INTO consultations (patient_id, recorded_by, appointment_id, "
                "consultation_date, chief_complaint) VALUES (?, ?, ?, ?, 'cough')",
                (pid, STAFF_ID, visit, day))
    return visit, pid


add_visit("Waiting")
add_visit("Waiting", days_ago=2)
add_visit("Waiting for the Doctor", consultation=True)
_, profile_pid = add_visit("Waiting for the Doctor", days_ago=1, consultation=True)
slip_visit, _ = add_visit("Waiting")
run_sql("UPDATE appointments SET status = 'Referred', status_before_referred = 'Waiting', "
        "referral_destination = ?, referred_by = ?, referred_at = ? WHERE id = ?",
        (RHU, STAFF_ID, f"{today.isoformat()} 12:35:00", slip_visit))


def start_server():
    from utils.server import build_server

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = build_server(app, "127.0.0.1", port)
    server.prepare()
    threading.Thread(target=server.serve, daemon=True).start()
    return f"http://127.0.0.1:{port}", server.stop


# ---------------------------------------------------------------------------
# 1. The helper, on its own
# ---------------------------------------------------------------------------
CASES = [
    ("00:00", False, "12:00 AM"), ("00:05", False, "12:05 AM"), ("11:59", False, "11:59 AM"),
    ("12:00", False, "12:00 PM"), ("12:30", False, "12:30 PM"), ("13:05", False, "1:05 PM"),
    ("23:59", False, "11:59 PM"), ("14:21:05", True, "2:21:05 PM"), ("14:21:05", False, "2:21 PM"),
    ("00:00:00", True, "12:00:00 AM"), ("2026-10-12 11:34", False, "11:34 AM"),
    ("2026-10-12 14:21:05", False, "2:21 PM"), ("2026-10-12 14:21:05", True, "2:21:05 PM"),
    ("2026-10-12T00:05:00", False, "12:05 AM"), ("2026-10-12 23:59:59.123", False, "11:59 PM"),
    ("9:30", False, "9:30 AM"), ("", False, ""), ("   ", False, ""), ("noon", False, ""),
    ("24:00", False, ""), ("12:60", False, ""), ("2026-10-12", False, ""),
]


def helper_checks(page, label):
    page.goto("about:blank")
    page.add_script_tag(path=str(HELPER))
    for value, seconds, expected in CASES:
        got = page.evaluate("([v, s]) => IDSTime.formatTime(v, s)", [value, seconds])
        check(f"{label}: formatTime({value!r}{', seconds' if seconds else ''}) -> {expected!r}",
              got == expected, got)
    check(f"{label}: null and undefined -> ''",
          page.evaluate("[IDSTime.formatTime(null), IDSTime.formatTime(undefined)]") == ["", ""])
    check(f"{label}: Date objects: 00:05 -> 12:05 AM, noon with seconds -> 12:00:00 PM, "
          "an invalid Date -> ''",
          page.evaluate("[IDSTime.formatTime(new Date(2026, 9, 12, 0, 5)),"
                        " IDSTime.formatTime(new Date(2026, 9, 12, 12, 0, 0), true),"
                        " IDSTime.formatTime(new Date('nonsense'))]")
          == ["12:05 AM", "12:00:00 PM", ""])
    check(f"{label}: formatDateTime(Date 2026-10-22 14:21) -> 'October 22, 2026 at 2:21 PM'",
          page.evaluate("IDSTime.formatDateTime(new Date(2026, 9, 22, 14, 21))")
          == "October 22, 2026 at 2:21 PM")
    check(f"{label}: formatDateTime of stored text with seconds -> "
          "'October 2, 2026 at 12:05:09 AM'",
          page.evaluate("IDSTime.formatDateTime('2026-10-02 00:05:09', true)")
          == "October 2, 2026 at 12:05:09 AM")
    check(f"{label}: formatDateTime of a time with no date, or nothing -> ''",
          page.evaluate("[IDSTime.formatDateTime('14:21'), IDSTime.formatDateTime(null)]")
          == ["", ""])
    return page.evaluate("""() => {
        const out = [];
        for (let h = 0; h < 24; h++) for (let m = 0; m < 60; m++)
          out.push(IDSTime.formatTime((h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m));
        return out;
    }""")


# ---------------------------------------------------------------------------
# 2. The pages
# ---------------------------------------------------------------------------
def watch_errors(page):
    errors = []
    page.on("pageerror", lambda e: errors.append("script: " + str(e)[:140]))
    page.on("console", lambda m: errors.append("console: " + m.text[:140])
            if m.type == "error" else None)
    return errors


def page_checks(browser, base_url, state, role, pages):
    for width in WIDTHS:
        context = browser.new_context(base_url=base_url, storage_state=state, locale="de-DE",
                                      viewport={"width": width, "height": 800})
        page = context.new_page()
        errors = watch_errors(page)
        for path, label, expect in pages:
            page.goto(path)
            page.wait_for_load_state()
            where = f"{role} {label} @{width}"
            wide = page.evaluate("document.documentElement.scrollWidth")
            check(f"{where}: no sideways scroll", wide <= width,
                  f"the page is {wide}px wide on a {width}px screen")
            text = page.evaluate("document.body.innerText")
            if expect:
                check(f"{where}: shows {expect!r}", expect in text)
            check(f"{where}: no 24-hour 12:35 without PM",
                  not re.search(r"12:35(?! ?PM)", text))
            pill = re.search(r"Loaded (\S+ [AP]M)", text)
            if width >= 992:
                check(f"{where}: the 'Loaded' pill is 12-hour", pill and TWELVE.match(pill.group(1)),
                      pill and pill.group(0))
        check(f"{role} @{width}: no page script failed", not errors, "\n".join(errors))
        context.close()


def main():
    base_url, stop_server = start_server()
    try:
        playwright_cm = sync_playwright().start()
        try:
            browser = playwright_cm.chromium.launch()
        except Exception as problem:
            playwright_cm.stop()
            print("SKIPPED: verify_time_format_browser.py could not start Chromium "
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


def run_checks(browser, base_url):
    from utils.dates import display_date, format_time

    section("1. IDSTime in an English-language browser")
    context = browser.new_context(locale="en-US")
    minutes = helper_checks(context.new_page(), "en-US")
    context.close()
    python_minutes = [format_time(f"{h:02d}:{m:02d}") for h in range(24) for m in range(60)]
    check("all 1,440 minutes: the browser and utils/dates.py give the same text",
          minutes == python_minutes,
          next((f"{a} != {b}" for a, b in zip(minutes, python_minutes) if a != b), ""))
    check("all 1,440 minutes match the 12-hour pattern", all(TWELVE.match(t) for t in minutes))

    section("2. IDSTime in a German-language browser, which writes 14:21 on its own")
    context = browser.new_context(locale="de-DE")
    page = context.new_page()
    german = page.evaluate("new Date(2026, 9, 22, 14, 21).toLocaleTimeString()")
    check("the German browser's own clock is 24-hour (so the next checks mean something)",
          "14:21" in german, german)
    minutes_de = helper_checks(page, "de-DE")
    check("all 1,440 minutes are the same as in the English browser", minutes_de == minutes)
    context.close()

    section("3. Signing in")
    states = {}
    for username in ("staff", "doctor", "admin", "official"):
        context = browser.new_context(base_url=base_url)
        page = context.new_page()
        page.goto("/login")
        page.fill("#username", username)
        page.fill("#password", _support.PASSWORDS[username])
        page.click("button[type=submit]")
        page.wait_for_load_state()
        ok = "/login" not in page.url
        states[username] = context.storage_state() if ok else None
        context.close()
        check(f"{username} signs in", ok)
    if not all(states.values()):
        return

    earlier = f"{display_date(today - timedelta(days=2))} · 12:35 PM"
    section("4. The pages that show times, at 360, 390 and 1366 pixels")
    page_checks(browser, base_url, states["staff"], "staff", [
        ("/staff/appointment_scheduling", "patient queue", earlier),
        ("/staff/dashboard", "dashboard", "12:35 PM"),
        (f"/staff/appointment_scheduling/referral-slip/{slip_visit}", "referral slip", "12:35 PM"),
        (f"/staff/patient_profile/{profile_pid}", "patient profile", None),
    ])
    page_checks(browser, base_url, states["doctor"], "doctor", [
        ("/staff/dashboard", "dashboard", f"{display_date(today)} · 12:35 PM"),
        ("/staff/appointment_scheduling", "patient queue", earlier),
    ])
    page_checks(browser, base_url, states["admin"], "admin", [
        ("/admin/appointment_scheduling", "patient queue", earlier),
        ("/admin/audit_logs", "audit logs", None),
        ("/admin/dashboard", "dashboard", None),
    ])

    section("5. The printed-page stamp, in a German-language browser")
    # Each page with a role that can open it: Reports & Analytics is the Doctor's (and the
    # Administrator's), Community Reports the Official's.
    for user, path, label in (
            ("staff", "/staff/patient_records", "Patient Records"),
            ("staff", f"/staff/patient_profile/{profile_pid}", "Patient Profile"),
            ("admin", f"/admin/patient_profile/{profile_pid}", "Patient Profile (Administrator)"),
            ("doctor", "/staff/reports_analytics", "Reports & Analytics"),
            ("official", "/official/community-reports", "Community Reports")):
        context = browser.new_context(base_url=base_url, storage_state=states[user],
                                      locale="de-DE")
        page = context.new_page()
        errors = watch_errors(page)
        response = page.goto(path)
        page.wait_for_load_state()
        reached = response is not None and response.status == 200 and page.url.endswith(path)
        check(f"{label}: {user} opens {path}", reached, page.url)
        if not reached:
            context.close()
            continue
        stamps = page.evaluate(
            "Array.from(document.querySelectorAll('.print-stamp')).map(e => e.textContent)")
        check(f"{label}: 'Printed ...' reads like 'October 22, 2026 at 2:21 PM'",
              stamps and all(STAMP.match(s) for s in stamps), repr(stamps))
        check(f"{label}: no page script failed", not errors, "\n".join(errors))
        context.close()


if main() is None:
    sys.exit(0)

failed = [name for name, ok in results if not ok]
print("\n" + "=" * 78)
print(f"RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
for name in failed:
    print(f"  FAILED: {name}")
print("=" * 78)
sys.exit(1 if failed else 0)
