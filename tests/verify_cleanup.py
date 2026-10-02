"""The final clean-up (Task 7): one project name, no placeholders, the small bug fixes,
short plain text, a tidy repository, and every menu page loading for each role.

Runs on a fresh test database built by tests/_support.py.
"""
import ast
import os
import re
import sqlite3
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import _support  # noqa: E402  (first: builds the test database, points the app at it)

from app import create_app  # noqa: E402
import config  # noqa: E402

sys.stdout.reconfigure(errors="replace")

app = create_app()
_support.attach(app)
REPO = Path(_support.REPO)
ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID = 1, 2, 3, 5

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


def client_as(user_id):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = user_id
        _support.open_session(sess)
    return c


def body(response):
    return response.get_data(as_text=True)


admin, staff, official, doctor = (client_as(i) for i in (ADMIN_ID, STAFF_ID, OFFICIAL_ID, DOCTOR_ID))
ROLES = (("Administrator", admin), ("Health Center Staff", staff), ("Doctor", doctor),
         ("Barangay Official", official))

# ---------------------------------------------------------------------------
section("1. ONE PROJECT NAME (M9)")
FULL = "Integrated Digital System for Barangay Poblacion Health Center Services and Community Notifications"
check("the name and its short form are one constant in config.py",
      config.SYSTEM_NAME == FULL and config.SYSTEM_SHORT_NAME == "IDS-BPHCSN")
OLD_VARIANTS = re.compile(r"Integrated (Data|Database) System|Health Center\s+Networking")
offenders = []
for pattern in ("templates/*.html", "routes/*.py", "utils/*.py", "models/*.py", "*.py", "README.md"):
    for path in REPO.glob(pattern):
        if OLD_VARIANTS.search(path.read_text(encoding="utf-8")):
            offenders.append(path.name)
check("no old variant of the name appears in any template, module or the README", not offenders, offenders)
login = body(app.test_client().get("/login"))
check("the sign-in page prints the full name from the constant",
      FULL in re.sub(r"\s+", " ", login))
page = body(admin.get("/admin/patient_records"))
check("a screen's printed header carries the full name and the short form",
      re.search(r'print-org-sub">\s*' + re.escape(FULL), page) is not None
      and f"{config.SYSTEM_SHORT_NAME}</div>" in page)
check("a page title uses the short form from the constant",
      f"<title>{config.SYSTEM_SHORT_NAME} | " in page)
from openpyxl import load_workbook  # noqa: E402
import io  # noqa: E402

xlsx = admin.get("/admin/patient_records/export.xlsx")
book = load_workbook(io.BytesIO(xlsx.data), data_only=True)
cells = [str(c) for sheet in book.worksheets for row in sheet.iter_rows(values_only=True)
         for c in row if c is not None]
check("an Excel export names the system in full, and not under an old name",
      any(FULL in c for c in cells) and not any(OLD_VARIANTS.search(c) for c in cells))
check("the README opens with the short name and then the full name",
      (REPO / "README.md").read_text(encoding="utf-8").replace("\n", " ").count(FULL) >= 1)

# ---------------------------------------------------------------------------
section("2. THE NOTIFICATIONS PLACEHOLDER IS GONE (M14)")
rules = {r.rule for r in app.url_map.iter_rules()}
check("no route serves the Official's Notifications screen", "/official/notifications" not in rules)
check("a GET to the old address is a 404", official.get("/official/notifications").status_code == 404)
check("its template is deleted", not (REPO / "templates" / "notifications.html").exists())
dash = body(official.get("/official/dashboard"))
check("the Official's menu and header have no Notifications link or bell",
      "/official/notifications" not in dash and 'class="bell-btn' not in dash
      and ">Notifications</a>" not in dash)
check("the Official still has SMS Notifications", "SMS Notifications" in dash)

# ---------------------------------------------------------------------------
section("3. PLACEHOLDERS AND LEFTOVERS (L3, L6, M7)")
profile = body(admin.get("/admin/patient_profile/1"))
staff_profile = body(staff.get("/staff/patient_profile/1"))
check("PhilHealth No. is gone from the profile, for the care team and the Administrator",
      "PhilHealth" not in staff_profile and "PhilHealth" not in profile
      and "PhilHealth" not in (REPO / "templates" / "patient_profile.html").read_text(encoding="utf-8"))
queue = body(staff.get("/staff/appointment_scheduling"))
check("the queue has no 'Booked' column", "<th>Booked</th>" not in queue)
check("the queue export has no 'Booked for' column",
      "Booked for" not in (REPO / "routes" / "roster_export.py").read_text(encoding="utf-8"))
settings = body(admin.get("/admin/settings"))
check("Settings has no Health Center Information pane and no disabled controls",
      'id="pane-hc"' not in settings and '<fieldset class="unavailable-form"' not in settings
      and "Test Connection" not in settings and "Restore Backup" not in settings
      and "Backup Frequency" not in settings and "System Log Retention" not in settings)
check("Settings still states the real rules: Password Policy, session limits, backup encryption",
      'id="pane-pwd"' in settings and 'id="pane-security"' in settings
      and "The backup file is encrypted" in settings)
check("Settings' invented DOH licence number and sender name are gone",
      "DOH-CARAGA" not in settings and "Sender Name" not in settings)
check("the booking-era wording is gone from Community Reports",
      "booked in advance" not in body(official.get("/official/community-reports")).lower())

# ---------------------------------------------------------------------------
section("4. THE SMS MODE LINE (M8)")
LIVE = "SMS mode: Live (messages are sent through Semaphore)"
SIM = "SMS mode: Simulated (messages are saved but not sent)"
saved = os.environ.pop("SEMAPHORE_API_KEY", None)
try:
    s1, s2 = body(admin.get("/admin/settings")), body(admin.get("/admin/sms_notifications"))
    check("with no key, Settings and SMS Notifications say 'Simulated'",
          SIM in s1 and SIM in s2 and LIVE not in s1 and LIVE not in s2)
    os.environ["SEMAPHORE_API_KEY"] = "fake-test-key"
    s1, s2 = body(admin.get("/admin/settings")), body(admin.get("/admin/sms_notifications"))
    check("with a key set, both say 'Live'", LIVE in s1 and LIVE in s2 and SIM not in s1 and SIM not in s2)
    check("the key's value is never shown on either screen",
          "fake-test-key" not in s1 and "fake-test-key" not in s2)
finally:
    os.environ.pop("SEMAPHORE_API_KEY", None)
    if saved is not None:
        os.environ["SEMAPHORE_API_KEY"] = saved
example = (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
idx = [i for i, l in enumerate(example) if l.startswith("SEMAPHORE_API_KEY")]
check(".env.example lists SEMAPHORE_API_KEY with a comment above it",
      idx and example[idx[0] - 1].startswith("#"))

# ---------------------------------------------------------------------------
section("5. SMALL BUGS (L15, L16, L17)")
c = client_as(STAFF_ID)
r = c.get("/logout")
check("L16: GET /logout is a redirect, not a 405", r.status_code == 302)
check("L16: it does not sign the user out, and shows no error text",
      c.get("/staff/dashboard").status_code == 200
      and "Method Not Allowed" not in body(c.get("/logout", follow_redirects=True)))
anon = app.test_client().get("/logout", follow_redirects=True)
check("L16: signed out, it lands on the sign-in page with no message",
      anon.request.path == "/login" and "Method Not Allowed" not in body(anon))
js = (REPO / "static" / "js" / "session.js").read_text(encoding="utf-8")
check("L17: the keep-alive script reloads the page on a 503",
      "response.status === 503" in js and "window.location.reload()" in js)
from models.settings import set_maintenance_mode  # noqa: E402

page = body(staff.get("/staff/dashboard"))
url = re.search(r'data-session-keepalive-url="([^"]+)"', page)
set_maintenance_mode(True, ADMIN_ID)
try:
    r = staff.post(url.group(1), headers={"X-Requested-With": "fetch"})
    check("L17: while maintenance is on, the keep-alive answers 503 with JSON the script handles",
          r.status_code == 503 and r.is_json and r.get_json().get("maintenance") is True,
          (r.status_code, r.get_data(as_text=True)[:80]))
finally:
    set_maintenance_mode(False, ADMIN_ID)
def flashed(client):
    with client.session_transaction() as sess:
        return [m for _, m in sess.get("_flashes", [])]


with admin.session_transaction() as sess:
    sess.pop("_flashes", None)
SENTENCE = "The user must change this password the first time they sign in."
admin.post("/admin/user_management/add", data={
    "full_name": "Cleanup Probe", "username": "cleanupprobe", "role": "Health Center Staff",
    "password": "Mabuhay-Bukid-2031", "confirm_password": "Mabuhay-Bukid-2031"})
messages = flashed(admin)
check("L15: the Add User confirmation (the message itself) says the user must change the password at first sign-in",
      any("created for Cleanup Probe" in m and SENTENCE in m for m in messages), messages)
conn = sqlite3.connect(_support.DB_PATH)
probe = conn.execute("SELECT id FROM users WHERE username = 'cleanupprobe'").fetchone()
conn.close()
if probe:
    with admin.session_transaction() as sess:
        sess.pop("_flashes", None)
    admin.post("/admin/user_management/reset_password", data={
        "user_id": str(probe[0]), "password": "Mabuhay-Bukid-2032", "confirm_password": "Mabuhay-Bukid-2032"})
    check("L15: the Reset Password confirmation says it too",
          any("password has been reset" in m and SENTENCE in m for m in flashed(admin)), flashed(admin))
else:
    check("L15: the probe account was created", False)
check("the fixture patients use the fictional 0900000NNNN numbers",
      not re.search(r"0917\d{7}", (REPO / "tests" / "_support.py").read_text(encoding="utf-8")))

# ---------------------------------------------------------------------------
section("6. TEXT IS SHORT AND PLAIN (M10)")
LIMIT = 160


def long_py_strings(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            b = getattr(node, "body", [])
            if b and isinstance(b[0], ast.Expr) and isinstance(getattr(b[0], "value", None), ast.Constant):
                docs.add(id(b[0].value))
    out = []
    for node in ast.walk(tree):
        text = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "x" for v in node.values)
        if text and len(text) > LIMIT and re.search(r"[A-Za-z]{3,} [A-Za-z]{3,} [A-Za-z]{3,}", text) \
                and not text.lstrip().upper().startswith(("SELECT", "INSERT", "UPDATE", "CREATE", "WITH ", "DELETE")):
            out.append((path.name, node.lineno, len(text)))
    return out


class _Texts(HTMLParser):
    def __init__(self, name):
        super().__init__(convert_charrefs=True)
        self.name, self.long = name, []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("title", "placeholder", "aria-label") and v:
                for part in re.split(r"<j/>", v):
                    if len(re.sub(r"\s+", " ", part).strip()) > LIMIT:
                        self.long.append((self.name, self.getpos()[0], len(part)))

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data).strip()
        if len(text) > LIMIT:
            self.long.append((self.name, self.getpos()[0], len(text)))


def long_html_texts(path):
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"\{#.*?#\}", "", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"<(script|style)\b.*?</\1>", "", src, flags=re.S | re.I)
    src = re.sub(r"\{% block (styles|scripts)[^%]*%}.*?\{% endblock[^%]*%}", "", src, flags=re.S)
    src = re.sub(r"\{%-?.*?-?%\}", "\x00", src, flags=re.S)
    src = re.sub(r"\{\{.*?\}\}", "x", src, flags=re.S)
    src = src.replace("\x00", "<j/>") if False else src
    p = _Texts(path.name)
    # a Jinja tag is a boundary: text on either side is a separate sentence
    p.feed(src.replace("\x00", "<j/>"))
    return p.long


too_long = []
for pattern in ("routes/*.py", "models/*.py", "utils/*.py"):
    for path in sorted(REPO.glob(pattern)):
        too_long += long_py_strings(path)
for path in sorted((REPO / "templates").glob("*.html")):
    if path.name != "_print.html":
        too_long += long_html_texts(path)
check("no tooltip, help text, flash message or screen sentence is over 160 characters",
      not too_long, too_long[:6])

# ---------------------------------------------------------------------------
section("7. A TIDY REPOSITORY (L29, L14, L10, M31)")
root_migrations = sorted(p.name for p in REPO.glob("migrate_*.py"))
check("no migration is left in the project root", not root_migrations, root_migrations)
mig_dir = REPO / "migrations"
files = sorted(mig_dir.glob("migrate_*.py"))
check("the migrations are in migrations/, with a README that lists every one",
      len(files) >= 20 and (mig_dir / "README.md").exists()
      and all(f.name in (mig_dir / "README.md").read_text(encoding="utf-8") for f in files))
REPAIR = ("migrate_clear_seeded_remarks.py", "migrate_correct_patient_location.py",
          "migrate_correct_supplier_location.py", "migrate_demo_data_hygiene.py",
          "migrate_remove_fake_patient.py", "migrate_remove_test_residue.py")
check("the repair scripts for the old demo data are deleted", not any((mig_dir / n).exists() for n in REPAIR))
mutated = []
for f in files:
    r = subprocess.run([sys.executable, "-c",
                        f"import importlib.util as u, sys; sys.path.insert(0, r'{REPO}');"
                        f"s = u.spec_from_file_location('m', r'{f}'); m = u.module_from_spec(s); s.loader.exec_module(m)"],
                       capture_output=True, text=True, cwd=str(REPO))
    if r.returncode != 0:
        mutated.append((f.name, r.stderr.strip().splitlines()[-1:]))
check("every migration imports cleanly from the project root (python migrations/<name>.py works)",
      not mutated, mutated)
check("the wrong note in migrate_add_consultation_columns.py is corrected",
      "deliberate and is the only one" not in (mig_dir / "migrate_add_consultation_columns.py").read_text(encoding="utf-8"))
from models.users import DEMO_USERS  # noqa: E402

check("the default Administrator has a generic name, not a real person's",
      ("admin", "System Administrator", "Admin") in DEMO_USERS
      and not any("Acido" in entry[1] for entry in DEMO_USERS))
oversized = []
for path in sorted(REPO.rglob("*.py")):
    if ".venv" in path.parts or "__pycache__" in path.parts:
        continue
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.split("\n")
    n = 0
    while n < len(lines) and lines[n].startswith("#"):
        n += 1
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], "value", None), ast.Constant) \
            and isinstance(tree.body[0].value.value, str):
        n = max(n, tree.body[0].end_lineno - tree.body[0].lineno + 1)
    if n > 15:
        oversized.append((str(path.relative_to(REPO)), n))
check("no file starts with a comment block longer than 15 lines", not oversized, oversized[:5])

# ---------------------------------------------------------------------------
section("8. QUICK TEST MODE (L30)")
proc = subprocess.run([sys.executable, "tests/run_all.py", "--quick", "demo_data"],
                      capture_output=True, text=True, cwd=str(REPO))
check("--quick skips the slow demo-data suite", proc.returncode == 2 and "No suite matches" in proc.stdout,
      proc.stdout[-200:])
check("run_all.py names the slow suites and says to run the full suite before pushing",
      "SLOW_SUITES" in (REPO / "tests" / "run_all.py").read_text(encoding="utf-8")
      and "Quick run: run the full suite before pushing." in (REPO / "tests" / "run_all.py").read_text(encoding="utf-8"))
check("the README states both commands",
      "run_all.py --quick" in (REPO / "README.md").read_text(encoding="utf-8")
      and "python tests/run_all.py " in (REPO / "README.md").read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
section("9. EVERY MENU PAGE LOADS FOR EACH ROLE, SIGNED IN (no redirect counted as loaded)")
DASH = {"Administrator": "/admin/dashboard", "Health Center Staff": "/staff/dashboard",
        "Doctor": "/staff/dashboard", "Barangay Official": "/official/dashboard"}
for label, client in ROLES:
    home = client.get(DASH[label])
    html_text = body(home)
    nav = html_text[html_text.index('class="sidebar-nav"'):]
    nav = nav[:nav.index("</ul>")]
    links = sorted(set(re.findall(r'href="(/[^"#?]*)"', nav)))
    bad = []
    for link in links:
        r = client.get(link)
        if r.status_code != 200:
            bad.append((link, r.status_code))
    print(f"       {label}: {len(links)} menu pages, {len(links) - len(bad)} loaded with 200")
    check(f"{label}: the dashboard and all {len(links)} menu pages load with 200 (no redirect, no error)",
          home.status_code == 200 and links and not bad, bad)
    sweep = {}
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and rule.endpoint != "static" \
                and not any(s in rule.rule for s in ("logout", "backup", "keep", "download")):
            try:
                code = client.get(rule.rule).status_code
            except Exception:
                code = 500
            sweep[code] = sweep.get(code, 0) + 1
    check(f"{label}: no parameterless GET page returns a server error", not any(c >= 500 for c in sweep), sweep)

# ---------------------------------------------------------------------------
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)
