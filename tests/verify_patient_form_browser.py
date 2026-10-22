"""Register / Edit Patient in a real browser (Task 22): the dropdowns as a person uses them.

At 360, 390 and 1366 pixels, in Chromium:
1. The address opens on Surigao del Norte / San Francisco / Poblacion, and the lists are exactly
   the 21 municipalities and the 11 barangays. Changing the province clears the city/municipality
   and the barangay; changing the city/municipality clears the barangay; Other province turns all
   three into typed boxes; a hidden box is disabled, so it is never submitted.
2. The civil status list follows the birth date as it is entered: under 18 only Single, selected,
   with the RA 11596 hint; 18 and over the adult list; a choice the new birth date makes invalid
   is cleared and the operator is asked to choose again.
3. Nothing is wider than the screen, with the hints and errors showing; no page script fails; a
   form filled in the browser saves the address the dropdowns show.
Needs the DEV-only package (pip install -r requirements-dev.txt; python -m playwright install
chromium). Without it, one SKIPPED line, which tests/run_all.py reports as a skip, never a pass.
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
    print("SKIPPED: verify_patient_form_browser.py needs Playwright, which is not installed. "
          + INSTALL_HELP)
    sys.exit(0)

import _support  # noqa: E402  (builds the test folder and database, sets the test keys)

from app import create_app  # noqa: E402

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
WIDTHS = (360, 390, 1366)
REGISTER = "/staff/register-patient"

from models.places import SAN_FRANCISCO_BARANGAYS, SURIGAO_DEL_NORTE_LGUS  # noqa: E402

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
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def years_ago(years, days=0):
    """The birth date of someone `years` old today (plus `days` younger), in the browser's calendar."""
    today = date.today()
    try:
        born = today.replace(year=today.year - years)
    except ValueError:                       # today is February 29
        born = today.replace(year=today.year - years, day=28)
    return (born + timedelta(days=days)).isoformat()


# A stored record with the old mismatched pair, for the Edit page.
conn = sqlite3.connect(TEST_DB)
OLD_PAIR = conn.execute(
    "INSERT INTO patients (patient_id, first_name, last_name, birth_date, sex, civil_status, "
    "address, municipality, province, contact_number, status) VALUES ('TST-11', 'Zqbrowser', "
    "'Oldpair', '1980-01-01', 'Female', 'Married', 'Purok 4', 'San Francisco', 'Surigao del Sur', "
    "'09000000911', 'Active')").lastrowid
conn.commit()
conn.close()


def start_server():
    from utils.server import build_server

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = build_server(app, "127.0.0.1", port)
    server.prepare()
    threading.Thread(target=server.serve, daemon=True).start()
    return f"http://127.0.0.1:{port}", server.stop


STATE = """() => {
  const sel = id => document.getElementById(id);
  const opts = el => Array.from(el.options).map(o => o.value);
  const on = el => !el.disabled && !el.closest('[hidden]');
  return {
    province: sel('provinceChoice').value,
    provinceTyped: on(sel('provinceTyped')), provinceTypedValue: sel('provinceTyped').value,
    municipality: sel('municipalitySelect').value, municipalityOptions: opts(sel('municipalitySelect')),
    municipalitySelectOn: on(sel('municipalitySelect')),
    municipalityTyped: on(sel('municipalityTyped')), municipalityTypedValue: sel('municipalityTyped').value,
    barangay: sel('barangaySelect').value, barangayOptions: opts(sel('barangaySelect')),
    barangaySelectOn: on(sel('barangaySelect')), barangaySelectShown: !sel('barangaySelect').closest('[hidden]'),
    barangayTyped: on(sel('barangayTyped')), barangayTypedValue: sel('barangayTyped').value,
    civil: sel('civilStatus').value, civilOptions: opts(sel('civilStatus')),
    hint: !sel('civilStatusHint').hidden, again: !sel('civilStatusAgain').hidden,
    age: sel('ageDisplay').value,
    wide: document.documentElement.scrollWidth,
  };
}"""


def watch_errors(page):
    errors = []
    page.on("pageerror", lambda e: errors.append("script: " + str(e)[:140]))
    page.on("console", lambda m: errors.append("console: " + m.text[:140])
            if m.type == "error" else None)
    return errors


def address_checks(page, where, width):
    s = page.evaluate(STATE)
    check(f"{where}: opens on Surigao del Norte / San Francisco / Poblacion",
          (s["province"], s["municipality"], s["barangay"])
          == ("Surigao del Norte", "San Francisco", "Poblacion"), s)
    check(f"{where}: the City/Municipality list is exactly the 21, in order",
          s["municipalityOptions"] == [""] + list(SURIGAO_DEL_NORTE_LGUS))
    check(f"{where}: the Barangay list is exactly the 11, in order",
          s["barangayOptions"] == [""] + list(SAN_FRANCISCO_BARANGAYS))
    check(f"{where}: the province list has no Surigao del Sur",
          page.evaluate("Array.from(document.getElementById('provinceChoice').options).map(o => o.value)")
          == ["Surigao del Norte", "Other province"])
    check(f"{where}: no sideways scroll", s["wide"] <= width, f"{s['wide']}px on {width}px")

    page.select_option("#municipalitySelect", "Dapa")
    s = page.evaluate(STATE)
    check(f"{where}: Dapa -> the barangay is a typed box, empty, and the list is off",
          s["barangayTyped"] and s["barangayTypedValue"] == "" and not s["barangaySelectOn"], s)
    page.fill("#barangayTyped", "Zqtyped")
    page.select_option("#municipalitySelect", "San Francisco")
    s = page.evaluate(STATE)
    check(f"{where}: back to San Francisco -> the barangay list again, cleared, typed box off and empty",
          s["barangaySelectOn"] and s["barangay"] == "" and len(s["barangayOptions"]) == 12
          and not s["barangayTyped"] and s["barangayTypedValue"] == "", s)
    page.select_option("#barangaySelect", "Diaz")
    page.select_option("#municipalitySelect", "San Francisco")
    check(f"{where}: choosing the same municipality again does not clear the barangay",
          page.evaluate(STATE)["barangay"] == "Diaz")

    page.select_option("#provinceChoice", "Other province")
    s = page.evaluate(STATE)
    check(f"{where}: Other province -> province, city/municipality and barangay are typed boxes, all empty",
          s["provinceTyped"] and s["municipalityTyped"] and s["barangayTyped"]
          and not s["municipalitySelectOn"] and not s["barangaySelectShown"]
          and s["provinceTypedValue"] == s["municipalityTypedValue"] == s["barangayTypedValue"] == "", s)
    check(f"{where}: Other province fits the screen", s["wide"] <= width, f"{s['wide']}px on {width}px")
    page.fill("#provinceTyped", "Zqprovince")
    page.fill("#municipalityTyped", "Zqtown")
    page.fill("#barangayTyped", "Zqbarangay")
    page.select_option("#provinceChoice", "Surigao del Norte")
    s = page.evaluate(STATE)
    check(f"{where}: back to Surigao del Norte -> the city/municipality is cleared and must be chosen",
          s["municipalitySelectOn"] and s["municipality"] == "" and not s["municipalityTyped"]
          and s["municipalityTypedValue"] == "" and not s["provinceTyped"] and s["provinceTypedValue"] == "", s)
    check(f"{where}: ... and the barangay waits for it (cleared, not choosable yet)",
          s["barangaySelectShown"] and not s["barangaySelectOn"] and s["barangay"] == ""
          and s["barangayOptions"] == [""] and not s["barangayTyped"], s)
    page.select_option("#municipalitySelect", "San Francisco")
    s = page.evaluate(STATE)
    check(f"{where}: then San Francisco offers its 11 barangays, none chosen",
          s["barangaySelectOn"] and s["barangay"] == "" and len(s["barangayOptions"]) == 12, s)


def civil_checks(page, where, width):
    page.fill("#birthDate", years_ago(70))
    s = page.evaluate(STATE)
    check(f"{where}: 70 years old -> Select… and the four adult statuses",
          s["civilOptions"] == ["", "Single", "Married", "Widowed", "Separated"] and not s["hint"], s)
    page.select_option("#civilStatus", "Married")
    page.fill("#birthDate", years_ago(10))
    s = page.evaluate(STATE)
    check(f"{where}: changed to 10 years old -> only Single, selected, with the RA 11596 hint",
          s["civilOptions"] == ["Single"] and s["civil"] == "Single" and s["hint"], s)
    check(f"{where}: the hint fits the screen", s["wide"] <= width, f"{s['wide']}px on {width}px")
    page.fill("#birthDate", years_ago(18, days=1))
    s = page.evaluate(STATE)
    check(f"{where}: 17 years and 364 days -> still only Single (age box says 17 years)",
          s["civilOptions"] == ["Single"] and s["civil"] == "Single" and s["age"] == "17 years", s)
    page.fill("#birthDate", years_ago(18))
    s = page.evaluate(STATE)
    check(f"{where}: exactly 18 today -> the adult list, the choice cleared, and asked to choose again",
          s["civilOptions"] == ["", "Single", "Married", "Widowed", "Separated"] and s["civil"] == ""
          and s["again"] and not s["hint"] and s["age"] == "18 years", s)
    page.select_option("#civilStatus", "Married")
    page.fill("#birthDate", years_ago(60))
    s = page.evaluate(STATE)
    check(f"{where}: 18 -> 60, Married is still valid and kept, no message",
          s["civil"] == "Married" and not s["again"], s)
    page.fill("#birthDate", years_ago(0, days=-30))
    check(f"{where}: a baby -> Single", page.evaluate(STATE)["civilOptions"] == ["Single"])


def main():
    base_url, stop_server = start_server()
    try:
        playwright_cm = sync_playwright().start()
        try:
            browser = playwright_cm.chromium.launch()
        except Exception as problem:
            playwright_cm.stop()
            print("SKIPPED: verify_patient_form_browser.py could not start Chromium "
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
    section("0. Signing in")
    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    page.goto("/login")
    page.fill("#username", "staff")
    page.fill("#password", _support.PASSWORDS["staff"])
    page.click("button[type=submit]")
    page.wait_for_load_state()
    state = context.storage_state() if "/login" not in page.url else None
    context.close()
    if not check("Health Center Staff signs in", state is not None):
        return

    for width in WIDTHS:
        section(f"1-2. The dropdowns and the civil status @{width}")
        context = browser.new_context(base_url=base_url, storage_state=state,
                                      viewport={"width": width, "height": 800})
        page = context.new_page()
        errors = watch_errors(page)
        page.goto(REGISTER)
        page.wait_for_load_state()
        address_checks(page, f"register @{width}", width)
        civil_checks(page, f"register @{width}", width)

        section(f"3. Errors, the Edit page and saving @{width}")
        page.goto(REGISTER)
        page.wait_for_load_state()
        page.select_option("#provinceChoice", "Other province")
        page.click("button.btn-primary-teal[type=submit]")
        page.wait_for_load_state()
        wide = page.evaluate("document.documentElement.scrollWidth")
        messages = page.evaluate(
            "Array.from(document.querySelectorAll('.invalid-feedback.d-block')).map(e => e.textContent)")
        check(f"register @{width}: an empty Other province form comes back with the three typed fields required",
              {"Type the province.", "Type the city or municipality.", "Type the barangay."} <= set(messages),
              messages)
        check(f"register @{width}: the form with its error messages fits the screen", wide <= width,
              f"{wide}px on {width}px")
        page.goto(f"{REGISTER}/{OLD_PAIR}")
        page.wait_for_load_state()
        s = page.evaluate(STATE)
        check(f"edit @{width}: the stored San Francisco / Surigao del Sur record shows its values and asks to correct",
              page.locator("#storedProblems").count() == 1 and s["province"] == "Other province"
              and s["provinceTypedValue"] == "Surigao del Sur" and s["municipalityTypedValue"] == "San Francisco", s)
        check(f"edit @{width}: it fits the screen", s["wide"] <= width, f"{s['wide']}px on {width}px")
        page.select_option("#provinceChoice", "Surigao del Norte")
        page.select_option("#municipalitySelect", "San Francisco")
        page.select_option("#barangaySelect", "Honrado")
        page.fill('input[name="emergency_contact_name"]', "Test Relative")
        page.select_option('select[name="emergency_contact_relationship"]', "Sibling")
        page.fill('input[name="emergency_contact_number"]', "09000000912")
        page.click("button.btn-primary-teal[type=submit]")
        page.wait_for_load_state()
        row = q1("SELECT province, municipality, barangay FROM patients WHERE id = ?", (OLD_PAIR,))
        check(f"edit @{width}: corrected in the browser, it saves Surigao del Norte / San Francisco / Honrado",
              "/patient_profile/" in page.url and tuple(row) == ("Surigao del Norte", "San Francisco", "Honrado"),
              (page.url, tuple(row)))
        # Put the old pair back for the next width.
        conn = sqlite3.connect(TEST_DB)
        conn.execute("UPDATE patients SET province = 'Surigao del Sur', barangay = NULL WHERE id = ?",
                     (OLD_PAIR,))
        conn.commit()
        conn.close()

        if width == 1366:
            page.goto(REGISTER)
            page.wait_for_load_state()
            for name, value in (("first_name", "Zqbrowserone"), ("last_name", "Wesotu"),
                                ("address", "Purok 7"), ("emergency_contact_name", "Test Relative"),
                                ("emergency_contact_number", "09000000913")):
                page.fill(f'input[name="{name}"]', value)
            page.fill("#birthDate", years_ago(12))
            page.check('input[name="sex"][value="Male"]')
            page.select_option('select[name="emergency_contact_relationship"]', "Mother")
            page.select_option("#provinceChoice", "Other province")
            page.fill("#provinceTyped", "Agusan del Sur")
            page.fill("#municipalityTyped", "San Francisco")
            page.fill("#barangayTyped", "Zqbarangay Uno")
            page.click("button.btn-primary-teal[type=submit]")
            page.wait_for_load_state()
            row = q1("SELECT civil_status, province, municipality, barangay FROM patients "
                     "WHERE first_name = 'Zqbrowserone'")
            check("register @1366: a 12-year-old from Agusan del Sur saves as Single with the typed address",
                  row is not None and tuple(row) == ("Single", "Agusan del Sur", "San Francisco",
                                                     "Zqbarangay Uno"), row and tuple(row))
        check(f"@{width}: no page script failed", not errors, "\n".join(errors))
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
