"""CSRF protection: every POST must carry the form token from a page this app
served (utils/csrf.py), and signing out is a POST.

Runs on a fresh test database built by tests/_support.py. Unlike the other
suites, the clients here are plain Flask test clients: they send no token unless
the test gives one, and every token comes from a page the client loaded, the
way a browser gets it.
"""
import html
import re
import sqlite3
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import _support  # noqa: E402  (first: builds the test database, points the app at it)

import config  # noqa: E402
from app import create_app  # noqa: E402
from flask.testing import FlaskClient  # noqa: E402
from itsdangerous import TimestampSigner, URLSafeTimedSerializer  # noqa: E402
from models.audit import ACTION_REQUEST_REFUSED  # noqa: E402

app = create_app()
_support.attach(app)
TEST_DB = _support.DB_PATH
REPO = Path(_support.REPO)
PW = _support.PASSWORDS
FETCH = {"X-Requested-With": "fetch"}

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


def q(sql, args=()):
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def run_sql(sql, args=()):
    conn = sqlite3.connect(TEST_DB)
    try:
        conn.execute(sql, args)
        conn.commit()
    finally:
        conn.close()


def browser():
    """A client that sends only what a test gives it, like a browser."""
    return FlaskClient(app, app.response_class, use_cookies=True)


def location(response):
    return response.headers.get("Location", "")


def text(response):
    return response.get_data(as_text=True)


TOKEN_INPUT = re.compile(r'<input type="hidden" name="csrf_token" value="([^"]+)">')
META = re.compile(r'<meta name="csrf-token" content="([^"]+)">')


def page_token(client, url):
    """The form token on a page, read from its HTML the way a browser sends it."""
    page = text(client.get(url))
    found = TOKEN_INPUT.search(page) or META.search(page)
    return html.unescape(found.group(1)) if found else None


def sign_in(username, password=None):
    """Sign in through the login page: load it, then post with its token."""
    client = browser()
    token = page_token(client, "/login")
    response = client.post("/login", data={
        "username": username, "password": password or PW[username], "csrf_token": token})
    return client, response


def signed_in(client):
    with client.session_transaction() as sess:
        return "user_id" in sess


def is_expired_page(response):
    return response.status_code == 400 and "Your session expired" in text(response)


def audit_count():
    return q("SELECT COUNT(*) FROM audit_logs")[0][0]


def last_refusal():
    rows = q("SELECT * FROM audit_logs WHERE action = ? ORDER BY id DESC LIMIT 1",
             (ACTION_REQUEST_REFUSED,))
    return rows[0] if rows else None


def token_aged(client, seconds):
    """A token for this client's session, signed as if made `seconds` ago."""
    class Aged(TimestampSigner):
        def get_timestamp(self):
            return int(time.time()) - seconds

    with client.session_transaction() as sess:
        raw = sess["csrf_token"]
    return URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token",
                                  signer=Aged).dumps(raw)


# ===========================================================================
section("1. PROTECTION IS ON FOR EVERY POST")
check("CSRF checking is on", app.config.get("WTF_CSRF_ENABLED") is True
      and app.config.get("WTF_CSRF_CHECK_DEFAULT") is True)
check("a token lasts as long as the longest session (config.py)",
      app.config["WTF_CSRF_TIME_LIMIT"] == int(config.ABSOLUTE_TIMEOUT.total_seconds()))
check("templates have csrf_field()", "csrf_field" in app.jinja_env.globals)
with app.test_request_context():
    field = str(app.jinja_env.globals["csrf_field"]())
check("csrf_field() is one hidden input named csrf_token",
      TOKEN_INPUT.fullmatch(field) is not None, field)

# ===========================================================================
section("2. THE LOGIN FORM")
anon = browser()
login_page = text(anon.get("/login"))
check("the login form carries a token", TOKEN_INPUT.search(login_page) is not None)
before = audit_count()
r = anon.post("/login", data={"username": "admin", "password": PW["admin"]})
check("signing in without the token is refused with the plain page", is_expired_page(r))
check("and nobody is signed in", not signed_in(anon))
check("a refused anonymous request writes no audit entry (no account to name)",
      audit_count() == before)

admin, r = sign_in("admin")
check("signing in with the page's token works",
      r.status_code == 302 and location(r).endswith("/admin/dashboard") and signed_in(admin),
      location(r))
old_login_token = page_token(browser(), "/login")
again = browser()
first_token = page_token(again, "/login")
r1 = again.post("/login", data={"username": "staff", "password": PW["staff"],
                                "csrf_token": first_token})
second_token = page_token(again, "/login")
r2 = again.post("/login", data={"username": "staff", "password": PW["staff"],
                                "csrf_token": second_token})
check("signing in twice in a row works (the login page gives a fresh token)",
      r1.status_code == 302 and r2.status_code == 302 and signed_in(again))
stale = again.post("/login", data={"username": "staff", "password": PW["staff"],
                                   "csrf_token": first_token})
check("the token from before signing in no longer works after it (new session, new token)",
      is_expired_page(stale))
logout_token = page_token(again, "/staff/dashboard")
again.post("/logout", data={"csrf_token": logout_token})
third_token = page_token(again, "/login")
r3 = again.post("/login", data={"username": "staff", "password": PW["staff"],
                                "csrf_token": third_token})
check("signing out and in again works", r3.status_code == 302 and signed_in(again))

# ===========================================================================
section("3. A POST WITHOUT A TOKEN IS REFUSED, IN EVERY BLUEPRINT")
staff, _ = sign_in("staff")
official, _ = sign_in("official")

# auth: change own password
r = staff.post("/account/password", data={
    "current_password": PW["staff"], "new_password": "Bago-Na-Password-2026",
    "confirm_new_password": "Bago-Na-Password-2026"})
check("auth: own password change without a token is refused", is_expired_page(r))
_, still = sign_in("staff")
check("auth: and the password did not change", still.status_code == 302)

# admin: add a user
before = audit_count()
r = admin.post("/admin/user_management/add", data={
    "full_name": "Walang Token", "username": "walangtoken", "role": "Health Center Staff",
    "password": "Walang-Token-Pass-77", "confirm_password": "Walang-Token-Pass-77"})
check("admin: Add User without a token is refused", is_expired_page(r))
check("admin: and no account was created",
      not q("SELECT 1 FROM users WHERE username = 'walangtoken'"))
entry = last_refusal()
check("admin: one audit entry is written, naming the account",
      audit_count() == before + 1 and entry is not None and entry["user_id"] == 1)
check("admin: the entry names the screen in one short sentence",
      entry is not None and entry["details"] == "The request was sent to User Management."
      and entry["module"] == "Authentication", entry and dict(entry))

# staff: check a patient in
free = q("""SELECT p.id FROM patients p WHERE p.status = 'Active' AND NOT EXISTS (
            SELECT 1 FROM appointments a WHERE a.patient_id = p.id
            AND a.appointment_date = date('now', 'localtime')) ORDER BY p.id LIMIT 1""")[0][0]
appts = len(q("SELECT id FROM appointments WHERE patient_id = ?", (free,)))
r = staff.post("/staff/appointment_scheduling/check-in",
               data={"patient_id": str(free), "reason": "Lagnat at ubo",
                     "service": "Consultation"})
check("staff: Check In without a token is refused", is_expired_page(r))
check("staff: and no visit was added",
      len(q("SELECT id FROM appointments WHERE patient_id = ?", (free,))) == appts)
entry = last_refusal()
check("staff: the audit entry names the Patient Queue",
      entry is not None and entry["user_id"] == 2
      and entry["details"] == "The request was sent to Patient Queue.")

# official: send a broadcast
sent = len(q("SELECT id FROM sms_broadcasts"))
broadcast = {"message": "Libreng bakuna sa Sabado.", "audience": "all_patients",
             "category": "Vaccination Reminder"}
r = official.post("/official/sms_notifications/send", data=broadcast)
check("official: Send SMS without a token is refused", is_expired_page(r))
check("official: and nothing was sent", len(q("SELECT id FROM sms_broadcasts")) == sent)

# ===========================================================================
section("4. A WRONG, FOREIGN OR OLD TOKEN IS REFUSED")
r = admin.post("/admin/user_management/add", data={
    "full_name": "Maling Token", "username": "malingtoken", "role": "Health Center Staff",
    "password": "Maling-Token-Pass-77", "confirm_password": "Maling-Token-Pass-77",
    "csrf_token": "hindi-ito-token"})
check("a made-up token is refused", is_expired_page(r))
staff_token = page_token(staff, "/staff/dashboard")
r = admin.post("/admin/user_management/add", data={
    "full_name": "Ibang Token", "username": "ibangtoken", "role": "Health Center Staff",
    "password": "Ibang-Token-Pass-77", "confirm_password": "Ibang-Token-Pass-77",
    "csrf_token": staff_token})
check("another user's token is refused", is_expired_page(r))
r = admin.post("/admin/user_management/add", data={"csrf_token": old_login_token})
check("a token from a different browser's login page is refused", is_expired_page(r))
check("none of these created an account",
      not q("SELECT 1 FROM users WHERE username IN ('malingtoken', 'ibangtoken')"))
limit = app.config["WTF_CSRF_TIME_LIMIT"]
page_token(admin, "/admin/dashboard")
r = admin.post("/session/keep-alive", headers=FETCH,
               data={"csrf_token": token_aged(admin, limit - 3600)})
check("a token from a page opened 11 hours ago still works", r.status_code == 204,
      r.status_code)
r = admin.post("/session/keep-alive", headers=FETCH,
               data={"csrf_token": token_aged(admin, limit + 60)})
check("a token older than the longest session is refused", r.status_code == 400)

# ===========================================================================
section("5. A POST WITH A VALID TOKEN WORKS")
r = admin.post("/admin/user_management/add", data={
    "full_name": "May Token", "username": "maytoken", "role": "Health Center Staff",
    "password": "Sariwang-Hangin-2026", "confirm_password": "Sariwang-Hangin-2026",
    "csrf_token": page_token(admin, "/admin/user_management")})
check("admin: Add User with the page's token works",
      r.status_code == 302 and q("SELECT 1 FROM users WHERE username = 'maytoken'"),
      r.status_code)
r = staff.post("/staff/appointment_scheduling/check-in", data={
    "patient_id": str(free), "reason": "Lagnat at ubo", "service": "Consultation",
    "csrf_token": page_token(staff, "/staff/appointment_scheduling")})
check("staff: Check In with the page's token works",
      r.status_code == 302
      and len(q("SELECT id FROM appointments WHERE patient_id = ?", (free,))) == appts + 1)
r = official.post("/official/sms_notifications/send", data=dict(
    broadcast, csrf_token=page_token(official, "/official/sms_notifications")))
check("official: Send SMS with the page's token works",
      r.status_code == 302 and len(q("SELECT id FROM sms_broadcasts")) == sent + 1)
doctor, _ = sign_in("doctor")
r = doctor.post("/account/password", data={
    "current_password": PW["doctor"], "new_password": "Bagong-Lihim-Na-2026",
    "confirm_new_password": "Bagong-Lihim-Na-2026",
    "csrf_token": page_token(doctor, "/account")})
_, with_new = sign_in("doctor", "Bagong-Lihim-Na-2026")
check("auth: own password change with the page's token works",
      r.status_code == 302 and with_new.status_code == 302)

# ===========================================================================
section("6. SIGNING OUT IS A POST")
c, _ = sign_in("staff")
r = c.get("/logout")
check("GET on the logout URL is not allowed", r.status_code == 405, r.status_code)
check("and it does not sign the user out",
      signed_in(c) and c.get("/staff/dashboard").status_code == 200)
r = c.post("/logout")
check("POST without a token is refused, and the user stays signed in",
      is_expired_page(r) and signed_in(c))
r = c.post("/logout", data={"csrf_token": page_token(c, "/staff/dashboard")})
check("POST with the page's token signs the user out",
      r.status_code == 302 and location(r).endswith("/login") and not signed_in(c))

run_sql("UPDATE users SET must_change_password = 1 WHERE username = 'bhwtest'")
c, r = sign_in("bhwtest")
check("an account that must change its password is sent to My Account",
      location(r).endswith("/account"), location(r))
r = c.post("/logout", data={"csrf_token": page_token(c, "/account")})
check("it can still sign out, from the menu on My Account",
      r.status_code == 302 and not signed_in(c))
_support.clear_password_change("bhwtest")

# Staff is signed in when an Administrator closes the system.
blocked_client, _ = sign_in("staff")
a, _ = sign_in("admin")
a.post("/admin/settings/maintenance", data={
    "action": "enable", "csrf_token": page_token(a, "/admin/settings")})
page = blocked_client.get("/staff/dashboard")
maint_token = TOKEN_INPUT.search(text(page))
check("the maintenance page offers Sign out as a form with a token",
      page.status_code == 503 and maint_token is not None and 'action="/logout"' in text(page))
r = blocked_client.post("/logout", data={"csrf_token": html.unescape(maint_token.group(1))
                                         if maint_token else ""})
check("and it signs the user out while the system is closed",
      r.status_code == 302 and not signed_in(blocked_client))
a.post("/admin/settings/maintenance", data={
    "action": "disable", "csrf_token": page_token(a, "/admin/settings")})
check("maintenance mode is off again",
      browser().get("/login").status_code == 200
      and sign_in("staff")[0].get("/staff/dashboard").status_code == 200)

# ===========================================================================
section("7. THE KEEP-ALIVE")
c, _ = sign_in("doctor", "Bagong-Lihim-Na-2026")
meta = page_token(c, "/staff/dashboard")
r = c.post("/session/keep-alive", headers=dict(FETCH, **{"X-CSRFToken": meta}))
check("the keep-alive works with the token in the header", r.status_code == 204,
      r.status_code)
r = c.post("/session/keep-alive", headers=FETCH)
body = r.get_json(silent=True) or {}
check("without it, it is refused with JSON the script can act on",
      r.status_code == 400 and body.get("refused") is True
      and body.get("login_url") == "/login", (r.status_code, body))
c.post("/logout", data={"csrf_token": meta})
r = c.post("/session/keep-alive", headers=dict(FETCH, **{"X-CSRFToken": meta}))
body = r.get_json(silent=True) or {}
check("after signing out, an old page's keep-alive is refused and told to go to login",
      r.status_code == 400 and body.get("login_url") == "/login")
script = (REPO / "static" / "js" / "session.js").read_text(encoding="utf-8")
helper = (REPO / "static" / "js" / "csrf.js").read_text(encoding="utf-8")
check("session.js sends the token and goes to login on a 400",
      "withCsrfToken" in script and "response.status === 400" in script)
check("csrf.js reads the token from the meta tag and sets X-CSRFToken",
      'meta[name="csrf-token"]' in helper and "X-CSRFToken" in helper)

# ===========================================================================
section("8. THE ERROR PAGE")
c, _ = sign_in("admin")
r = c.post("/admin/settings/general", data={})
page = text(r)
check("it is a 400 titled 'Your session expired'",
      r.status_code == 400 and "<title>IDS-BPHCSN | Your session expired</title>" in page
      and "<h1 class=\"expired-title\">Your session expired</h1>" in page)
check("it says what to do, in one plain sentence",
      "Please sign in again and repeat what you were doing." in page)
check("it has a button to the login page", re.search(r'<a class="btn-teal" href="/login">', page)
      and "Sign in</a>" in page)
visible = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(style|script)\b.*?</\1>", " ", page))
check("it has no technical words",
      not re.search(r"(?i)csrf|token|bad request|400|traceback|exception|error", visible),
      visible)
entry = last_refusal()
check("the refusal is in the audit trail, with the screen",
      entry is not None and entry["details"] == "The request was sent to Settings.")
check("the entry is one short sentence",
      entry is not None and len(entry["action"]) <= 60
      and entry["details"].count(".") == 1 and len(entry["details"]) <= 80)

# ===========================================================================
section("9. EVERY POST FORM IN templates/ CARRIES A TOKEN (structural)")
# The rule: {{ csrf_field() }} is the first thing inside every POST form's
# opening tag. One rule that is easy to see in review. It also covers a form
# whose opening tag is chosen by {% if %} (service_schedule.html): each opening
# tag carries its own token.
TEMPLATES = sorted((REPO / "templates").glob("*.html"))
FORM_OPEN = re.compile(r"<form\b(?P<attrs>[^>]*)>", re.I)
METHOD = re.compile(r"""\bmethod\s*=\s*(["']?)([^"'\s>]*)\1""", re.I)
TOKEN_FIRST = re.compile(r"\s*\{\{-?\s*csrf_field\(\)\s*-?\}\}")
FIELD_CALL = re.compile(r"\{\{-?\s*csrf_field\(\)\s*-?\}\}")
FORMMETHOD_POST = re.compile(r"""\bformmethod\s*=\s*["']?post""", re.I)
post_forms, problems = [], []
for path in TEMPLATES:
    source = path.read_text(encoding="utf-8")
    opens = list(FORM_OPEN.finditer(source))
    post_opens = []
    for form in opens:
        line = source.count("\n", 0, form.start()) + 1
        found = METHOD.search(form.group("attrs"))
        method = found.group(2).lower() if found else "get"
        if method not in ("get", "post"):
            problems.append(f"{path.name}:{line}: form method is not plain get or post")
            continue
        if method != "post":
            continue
        post_opens.append(form)
        post_forms.append(f"{path.name}:{line}")
        if not TOKEN_FIRST.match(source, form.end()):
            problems.append(f"{path.name}:{line}: POST form does not start with csrf_field()")
        if source.find("</form", form.end()) == -1:
            problems.append(f"{path.name}:{line}: POST form is never closed")
    # A button that turns a form into a POST must sit in a POST form.
    for button in FORMMETHOD_POST.finditer(source):
        before = [f for f in opens if f.start() < button.start()]
        owner = before[-1] if before else None
        if owner is None or owner not in post_opens:
            line = source.count("\n", 0, button.start()) + 1
            problems.append(f"{path.name}:{line}: formmethod=post outside a POST form")
    # Every csrf_field() is the one opening a POST form: none stray or doubled.
    if len(FIELD_CALL.findall(source)) != len(post_opens):
        problems.append(f"{path.name}: {len(FIELD_CALL.findall(source))} csrf_field() "
                        f"for {len(post_opens)} POST forms")
check(f"every POST form starts with its token ({len(post_forms)} forms in "
      f"{len(TEMPLATES)} templates)", post_forms and not problems, "\n".join(problems))
logout_links = [p.name for p in TEMPLATES
                if re.search(r"""href=["'][^"']*(logout|url_for\(\s*['"](auth\.)?logout)""",
                             p.read_text(encoding="utf-8"))]
check("no template links to logout (it must be a POST form)", not logout_links, logout_links)
base = (REPO / "templates" / "base.html").read_text(encoding="utf-8")
check("base.html gives scripts the token in one meta tag and loads csrf.js",
      '<meta name="csrf-token" content="{{ csrf_token() }}">' in base and "js/csrf.js" in base)

SCRIPTS = [p for p in (REPO / "static" / "js").glob("*.js") if not p.name.endswith(".min.js")]
js_problems = []
for path in TEMPLATES + SCRIPTS:
    source = path.read_text(encoding="utf-8")
    for call in re.finditer(r"\bfetch\s*\(", source):
        window = source[call.start():call.start() + 600]
        if re.search(r"""method\s*:\s*["']post""", window, re.I) and not re.search(
                r"withCsrfToken|X-CSRFToken", source[max(0, call.start() - 600):call.start() + 600]):
            js_problems.append(f"{path.name}: fetch POST without the token header")
    for pattern, what in ((r"XMLHttpRequest", "XMLHttpRequest"),
                          (r"sendBeacon", "sendBeacon (cannot send the header)"),
                          (r"createElement\(\s*['\"]form", "a form built in script"),
                          (r"\$\.(ajax|post)\(", "jQuery request")):
        if re.search(pattern, source) and not re.search(r"withCsrfToken|X-CSRFToken", source):
            js_problems.append(f"{path.name}: {what} without the token")
check("every script POST sends the token, and none uses a way that cannot",
      not js_problems, "\n".join(js_problems))

# ===========================================================================
section("10. EVERY SCREEN, EVERY ROLE: THE PAGE'S TOKEN IS ACCEPTED")
POST_ENDPOINTS = {r.endpoint for r in app.url_map.iter_rules() if "POST" in r.methods}
SKIP = re.compile(r"(?i)logout|export|download|backup|\.xlsx|\.pdf|/static/")


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms, self.links, self._form = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href", "").startswith("/"):
            self.links.append(attrs["href"])
        if tag == "form":
            self._form = {"method": (attrs.get("method") or "get").lower(),
                          "action": attrs.get("action") or "", "tokens": [],
                          "formactions": []}
            self.forms.append(self._form)
        if self._form is not None and tag == "input" and attrs.get("name") == "csrf_token":
            self._form["tokens"].append(attrs.get("value", ""))
        if (self._form is not None and tag == "button"
                and (attrs.get("formmethod") or "").lower() == "post"):
            self._form["formactions"].append(attrs.get("formaction", ""))

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None


def get_endpoint(path):
    try:
        return app.url_map.bind("localhost").match(path, method="GET")[0]
    except Exception:
        return None


# The screens (GET pages) of each role, from the URL map. Downloads are skipped.
GET_SCREENS = {r.endpoint for r in app.url_map.iter_rules()
               if "GET" in r.methods and r.endpoint != "static" and "." in r.endpoint
               and not SKIP.search(r.rule)}
ROLE_BLUEPRINTS = {"admin": {"admin", "auth"}, "staff": {"staff", "auth"},
                   "doctor": {"staff", "auth"}, "official": {"official", "auth"}}
# In the staff blueprint, but for the Doctor only (routes/staff.py).
DOCTOR_ONLY = {"staff.staff_reports_analytics"}
# Screens with no link to them, by design: the login page and the redirects.
NOT_LINKED = {"auth.login", "auth.index", "auth.dashboard"}
screens_seen = set()


def endpoint_for(action):
    try:
        return app.url_map.bind("localhost").match(urlsplit(action).path, method="POST")[0]
    except Exception:
        return None


# Some forms appear only when there is something to act on: a Service Schedule
# entry (Edit and Delete), and a consultation in progress (Record Consultation,
# and the Doctor's seal). Made here through the screens, with the page's token.
setup_admin, _ = sign_in("admin")
r = setup_admin.post("/admin/service_schedule/add", data={
    "service": "Family Planning", "weekdays": ["1", "3"], "note": "",
    "csrf_token": page_token(setup_admin, "/admin/service_schedule")})
check("setup: a Service Schedule entry is added through its form", r.status_code == 302,
      r.status_code)
setup_staff, _ = sign_in("staff")
waiting = q("SELECT id FROM appointments WHERE patient_id = ? ORDER BY id DESC LIMIT 1",
            (free,))[0][0]
r = setup_staff.post("/staff/appointment_scheduling/start-consultation", data={
    "appointment_id": str(waiting),
    "csrf_token": page_token(setup_staff, "/staff/appointment_scheduling")})
check("setup: a consultation is started from the Patient Queue",
      q("SELECT status FROM appointments WHERE id = ?", (waiting,))[0][0] == "In Consultation")

seen_endpoints, crawl_problems = set(), []
for role in ("admin", "staff", "doctor", "official"):
    password = "Bagong-Lihim-Na-2026" if role == "doctor" else PW[role]
    c, r = sign_in(role, password)
    # Wide, not deep: at most three pages per screen, so every screen is reached
    # before any one screen's filters and sort orders are walked.
    queue, visited, forms_here, per_screen = [location(r)], set(), 0, {}
    while queue:
        url = queue.pop(0)
        path = urlsplit(url).path
        screen = get_endpoint(path)
        if url in visited or SKIP.search(url) or per_screen.get(screen, 0) >= 3:
            continue
        visited.add(url)
        per_screen[screen] = per_screen.get(screen, 0) + 1
        response = c.get(url)
        if response.status_code != 200 or "text/html" not in response.content_type:
            continue
        parser = Forms()
        parser.feed(text(response))
        tokens = set()
        for form in parser.forms:
            if form["method"] != "post" and not form["formactions"]:
                continue
            forms_here += 1
            action = form["action"] or path
            for target in [action] + form["formactions"]:
                seen_endpoints.add(endpoint_for(target))
            if len(form["tokens"]) != 1:
                crawl_problems.append(f"{role} {url}: form to {action} has "
                                      f"{len(form['tokens'])} tokens")
            tokens.update(form["tokens"])
        meta = META.search(text(response))
        if meta:
            tokens.add(html.unescape(meta.group(1)))
        for token in tokens:
            ok = c.post("/session/keep-alive", headers=FETCH,
                        data={"csrf_token": html.unescape(token)}).status_code == 204
            if not ok:
                crawl_problems.append(f"{role} {url}: the page's token was refused")
        for link in parser.links:
            if link not in visited and not SKIP.search(link):
                queue.append(link)
    screens_reached = {s for s in per_screen if s}
    role_screens = {e for e in GET_SCREENS if e.split(".")[0] in ROLE_BLUEPRINTS[role]}
    if role == "staff":
        role_screens -= DOCTOR_ONLY
    screens_seen.update(screens_reached)
    print(f"       {role}: {len(visited)} pages, {len(screens_reached)} screens, "
          f"{forms_here} POST forms")
    unreached = sorted(role_screens - screens_reached - NOT_LINKED)
    check(f"{role}: every screen of the role was reached", not unreached,
          "not reached: " + ", ".join(unreached))
    check(f"{role}: every POST form on every screen reached has a token the server accepts",
          not [p for p in crawl_problems if p.startswith(role)],
          "\n".join(p for p in crawl_problems if p.startswith(role)))

# The login page is the one screen the signed-in crawl does not visit.
parser = Forms()
parser.feed(text(browser().get("/login")))
seen_endpoints.update(endpoint_for(f["action"]) for f in parser.forms if f["method"] == "post")
missing = sorted(e for e in POST_ENDPOINTS - seen_endpoints - {"auth.keep_alive"} if e)
print(f"       POST endpoints: {len(POST_ENDPOINTS)}; reached by a form in the crawl: "
      f"{len(POST_ENDPOINTS & seen_endpoints)}; keep-alive is sent from script")
check("every POST endpoint except the keep-alive is the action of a form on some screen",
      not missing, "not reached: " + ", ".join(missing))

# ===========================================================================
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print("  FAILED:", name)
print("=" * 78)
sys.exit(0 if not failed else 1)
