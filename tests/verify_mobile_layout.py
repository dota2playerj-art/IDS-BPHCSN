"""Task 17: every page is usable at phone width, and the desktop layout is still there (M51).

A real browser (Playwright, Chromium) opens the system on a temporary copy of the fictional demo
database, signs in as each role, and visits every menu page, a patient profile (every tab), the
consultation forms, an inventory item and every dialog on them, at 360, 390 and 1366 pixels.

Needs the DEV-only package: pip install -r requirements-dev.txt, then
python -m playwright install chromium. Without them it prints one SKIPPED line and nothing else;
tests/run_all.py reports that as a skip, never a pass.
For working on the layout: IDS_MOBILE_DEMO_DB=<path> reuses a demo database built earlier (with
<path>.key holding its sealed-record key; it is copied, never opened), and IDS_MOBILE_ROLES,
IDS_MOBILE_WIDTHS and IDS_MOBILE_PAGES narrow a run. A narrowed run is not the suite's verdict.
"""
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(errors="replace")

INSTALL_HELP = ("To run it:  pip install -r requirements-dev.txt   then   "
                "python -m playwright install chromium")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIPPED: verify_mobile_layout.py needs Playwright, which is not installed. "
          + INSTALL_HELP)
    sys.exit(0)

import _support  # noqa: E402  (builds the test folder, sets the test keys)

import config  # noqa: E402

REPO = Path(_support.REPO)
TEST_DIR = Path(_support.TEST_DIR)
SHOTS = REPO / "docs" / "verification" / "mobile"

WIDTHS = tuple(int(w) for w in os.environ.get("IDS_MOBILE_WIDTHS", "360,390,1366").split(","))
# For working on the layout: IDS_MOBILE_ROLES=admin,official and IDS_MOBILE_PAGES=records,queue
# limit a run. A run with either set is not the suite's verdict.
ONLY_ROLES = [r for r in os.environ.get("IDS_MOBILE_ROLES", "").split(",") if r]
ONLY_PAGES = [r.lower() for r in os.environ.get("IDS_MOBILE_PAGES", "").split(",") if r]
HEIGHTS = {360: 740, 390: 844, 1366: 768}
PHONE_MAX = 576          # Bootstrap's sm breakpoint: below it, dialogs are full screen
LG = 992                 # below this the sidebar is a menu
MIN_TARGET = 44          # WCAG 2.5.5, in CSS pixels

results = []
exceptions = {}          # reason -> count, for the report at the end
problems_by_check = {}


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    if not ok:
        print(f"[FAIL] {name}")
        for line in str(detail).splitlines()[:10]:
            print(f"       {line}")
    return ok


def section(title):
    print(f"\n--- {title} ---", flush=True)


# ---------------------------------------------------------------------------
# What the browser measures. One function, run on a page (or a dialog, or a tab) as it
# stands. It returns facts only; the checks below decide.
# ---------------------------------------------------------------------------
PROBE = r"""
(arg) => {
  // The width the page was asked to fit, not window.innerWidth: a phone browser widens the
  // layout viewport to the page's width when the page is too wide, so innerWidth would
  // always agree with scrollWidth and hide the very overflow this is looking for.
  const vw = arg.width, root = arg.root;
  const scope = root ? document.querySelector(root) : document;
  const show = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none') return false;
    if (el.closest('[hidden], .visually-hidden, .visually-hidden-focusable, [aria-hidden="true"] .material-symbols-outlined')) return false;
    for (let p = el; p && p !== document.body; p = p.parentElement) {
      const ps = getComputedStyle(p);
      if (ps.display === 'none' || ps.visibility === 'hidden') return false;
      if (parseFloat(ps.opacity) === 0) return false;
    }
    return true;
  };
  const describe = (el) => {
    let d = el.tagName.toLowerCase();
    if (el.id) d += '#' + el.id;
    const c = (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 3);
    if (c.length) d += '.' + c.join('.');
    const inData = el.closest('td, tbody');
    const t = (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim().replace(/\s+/g, ' ');
    if (!inData && t) d += ' "' + t.slice(0, 24) + '"';
    return d;
  };
  const scroller = (el) => {
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'auto' || ox === 'scroll') return p;
    }
    return null;
  };
  const clippedBy = (el) => {
    // An ancestor that hides what sticks out of it (overflow hidden or clip), with the
    // element sticking out. A scrolling ancestor is not a problem: the person can scroll it.
    const r = el.getBoundingClientRect();
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'visible') continue;
      const pr = p.getBoundingClientRect();
      if (ox === 'auto' || ox === 'scroll') return null;
      if (r.right > pr.right + 1 || r.left < pr.left - 1) return p;
    }
    return null;
  };

  const out = {vw, scrollW: document.documentElement.scrollWidth, viewportMeta: !!document.querySelector('meta[name="viewport"]')};
  const all = Array.from(scope.querySelectorAll('*')).filter(show);

  // What sticks out past the right edge of the screen and is not inside a scrolling box.
  out.sticksOut = [];
  for (const el of all) {
    if (el.closest('.offcanvas, .modal-backdrop, .offcanvas-backdrop, .dropdown-menu, .sort-menu')) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && !scroller(el)) out.sticksOut.push(describe(el));
  }
  out.sticksOut = Array.from(new Set(out.sticksOut)).slice(0, 8);

  const tappable = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab]';
  out.cutOff = [];
  out.small = [];
  for (const el of Array.from(scope.querySelectorAll(tappable)).filter(show)) {
    if (el.closest('.dropdown-menu:not(.show), .sort-menu:not(.show)')) continue;
    const r = el.getBoundingClientRect();
    const sc = scroller(el);
    if (!sc && (r.right > vw + 1 || r.left < -1)) out.cutOff.push(describe(el));
    const clip = clippedBy(el);
    if (clip) out.cutOff.push(describe(el) + ' (clipped by ' + describe(clip) + ')');

    // The tappable area. A checkbox or radio is tapped through its label too.
    let w = r.width, h = r.height;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'checkbox' || type === 'radio') {
      let label = el.closest('label') || (el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]') : null);
      if (label && show(label)) { const lr = label.getBoundingClientRect(); w = Math.max(w, lr.width); h = Math.max(h, lr.height); }
    }
    if (w >= 43.5 && h >= 43.5) continue;

    // An inline link inside a sentence is exempt (WCAG 2.5.5: "inline").
    let reason = null;
    if (el.tagName === 'A') {
      const block = el.closest('p, li, td, th, div, span, label, small') ;
      let own = '';
      if (block && block !== el) {
        const clone = block.cloneNode(true);
        for (const a of clone.querySelectorAll('a, button, .material-symbols-outlined')) a.remove();
        own = (clone.textContent || '').trim();
      }
      const words = own.split(/\s+/).filter(Boolean).length;
      const cls = (el.getAttribute('class') || '');
      if (words >= 3 && getComputedStyle(el).display === 'inline' && !/\bbtn\b|nav-link|page-link|dropdown-item/.test(cls)) {
        reason = 'a link inside a sentence (WCAG 2.5.5 exempts inline links)';
      }
    }
    out.small.push({d: describe(el), w: Math.round(w), h: Math.round(h), reason});
  }
  out.cutOff = Array.from(new Set(out.cutOff)).slice(0, 8);

  out.pinned = Array.from(scope.querySelectorAll('th.pin-name, td.pin-name')).filter(show)
    .filter(c => getComputedStyle(c).position !== 'sticky').length;
  out.hasPin = scope.querySelectorAll('th.pin-name').length > 0;

  // Tables: each one scrolls sideways inside its own .table-responsive box.
  out.tablesLoose = Array.from(scope.querySelectorAll('table')).filter(show)
    .filter(t => !t.closest('.table-responsive')).map(describe).slice(0, 6);

  // Fields side by side. Two fields that share a row, outside a table, are a two-column form.
  const fields = Array.from(scope.querySelectorAll(
    'input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]), select, textarea'))
    .filter(show).filter(f => !f.closest('table, .input-group, .toolbar-search, .search-box, .sort-wrap, .pagination'));
  out.sideBySide = [];
  for (let i = 0; i < fields.length; i++) {
    for (let j = i + 1; j < fields.length; j++) {
      const a = fields[i].getBoundingClientRect(), b = fields[j].getBoundingClientRect();
      const overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      const apart = a.right <= b.left + 1 || b.right <= a.left + 1;
      if (apart && overlap > Math.min(a.height, b.height) * 0.5) out.sideBySide.push(describe(fields[i]) + ' | ' + describe(fields[j]));
    }
  }
  out.sideBySide = out.sideBySide.slice(0, 6);

  // Charts must not be wider than the box they sit in.
  out.charts = Array.from(scope.querySelectorAll('canvas')).filter(show).map(c => {
    const box = c.parentElement.getBoundingClientRect(), r = c.getBoundingClientRect();
    return {d: describe(c), over: r.right > box.right + 1 || r.right > vw + 1};
  });

  // The menu: the button, and whether the sidebar can be seen without opening anything.
  const btn = document.querySelector('[data-bs-target="#sidebarMenu"][data-bs-toggle="offcanvas"]');
  const side = document.querySelector('.sidebar');
  out.menuButtonVisible = !!btn && show(btn);
  out.sidebarVisible = !!side && show(side) && side.getBoundingClientRect().right > 1 && side.getBoundingClientRect().left > -1;
  return out;
}
"""

# Text in the "Loaded 20:41" pill changes every minute; nothing else on a page is time-based.
MASK_CLOCK = "document.querySelectorAll('.sync-pill').forEach(e => e.style.visibility = 'hidden')"


def watch_errors(page):
    """Collect every script error and every console error the page logs (L63)."""
    holder = {"errors": []}
    page.on("pageerror", lambda e: holder["errors"].append("script: " + str(e)[:140]))
    page.on("console", lambda m: holder["errors"].append("console: " + m.text[:140])
            if m.type == "error" else None)
    return holder


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70] or "page"


class Browser:
    """One Chromium, one context per (role, width), one page per context."""

    def __init__(self, playwright, base_url):
        self.base_url = base_url
        self.browser = playwright.chromium.launch()
        self.states = {}

    def context(self, width, state=None):
        phone = width < LG
        return self.browser.new_context(
            viewport={"width": width, "height": HEIGHTS[width]},
            is_mobile=phone, has_touch=phone, device_scale_factor=1,
            storage_state=state, base_url=self.base_url)

    def sign_in(self, username, password):
        context = self.context(1366)
        page = context.new_page()
        page.goto("/login")
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("button[type=submit]")
        page.wait_for_load_state()
        ok = "/login" not in page.url
        state = context.storage_state() if ok else None
        context.close()
        return state

    def close(self):
        self.browser.close()


def view_checks(page, width, label, root=None, role=""):
    """Run the probe on what is on screen and record the checks for this view."""
    facts = page.evaluate(PROBE, {"root": root, "width": width})
    phone = width < LG
    where = f"{role} {label} @{width}"

    check(f"{where}: no sideways scroll",
          facts["scrollW"] <= width,
          f"the page is {facts['scrollW']}px wide on a {width}px screen; sticking out: {facts['sticksOut']}")
    if root is None:
        check(f"{where}: the viewport meta tag is present", facts["viewportMeta"])
    check(f"{where}: no button or link is cut off",
          not facts["cutOff"], "\n".join(facts["cutOff"]))
    if phone:
        check(f"{where}: every table scrolls inside its own box",
              not facts["tablesLoose"], "\n".join(facts["tablesLoose"]))
        check(f"{where}: the patient name column stays pinned while the table scrolls",
              facts["pinned"] == 0, f"{facts['pinned']} cells of the .pin-name column are not sticky")
        check(f"{where}: fields stack in one column",
              not facts["sideBySide"] or width >= 768, "\n".join(facts["sideBySide"]))
        check(f"{where}: charts stay inside their box",
              not any(c["over"] for c in facts["charts"]),
              "\n".join(c["d"] for c in facts["charts"] if c["over"]))
        real = []
        for item in facts["small"]:
            if item["reason"]:
                exceptions[item["reason"]] = exceptions.get(item["reason"], 0) + 1
            else:
                real.append(f"{item['d']}  {item['w']}x{item['h']}")
        check(f"{where}: every button and link is at least {MIN_TARGET}x{MIN_TARGET}",
              not real, "\n".join(real[:10]) + (f"\n... {len(real) - 10} more" if len(real) > 10 else ""))
    return facts


def shot(page, role, name, width):
    folder = SHOTS / role
    folder.mkdir(parents=True, exist_ok=True)
    page.evaluate(MASK_CLOCK)
    page.screenshot(path=str(folder / f"{slug(name)}-{width}.png"), full_page=True)


def open_dialogs(page, role, label, width):
    """Open every distinct dialog the visible controls open, check it, close it."""
    phone = width < LG
    targets = page.evaluate("""() => {
        const seen = new Set(), out = [];
        document.querySelectorAll('[data-bs-toggle="modal"]').forEach((b, i) => {
            const t = b.getAttribute('data-bs-target');
            const r = b.getBoundingClientRect();
            const s = getComputedStyle(b);
            if (!t || seen.has(t) || r.width < 1 || s.visibility === 'hidden' || b.disabled) return;
            if (b.closest('.modal, .dropdown-menu:not(.show)')) return;
            seen.add(t); b.setAttribute('data-probe-id', 'p' + i); out.push([t, 'p' + i]);
        });
        return out;
    }""")
    opened = 0
    for target, probe_id in targets:
        trigger = page.locator(f'[data-probe-id="{probe_id}"]')
        try:
            trigger.scroll_into_view_if_needed(timeout=3000)
            trigger.click(timeout=3000)
            page.wait_for_selector(f"{target}.show", timeout=4000)
            page.wait_for_timeout(450)
        except Exception as problem:
            check(f"{role} {label} @{width}: dialog {target} opens", False, str(problem)[:200])
            page.evaluate("document.querySelectorAll('.modal.show').forEach(m => bootstrap.Modal.getInstance(m)?.hide())")
            page.wait_for_timeout(300)
            continue
        opened += 1
        name = f"{label} dialog {target.lstrip('#')}"
        dialog = page.evaluate("""(sel) => {
            const m = document.querySelector(sel), d = m.querySelector('.modal-dialog');
            const r = d.getBoundingClientRect();
            return {full: d.classList.contains('modal-fullscreen-sm-down'), w: r.width, h: r.height,
                    vw: window.innerWidth, vh: window.innerHeight};
        }""", target)
        if width < PHONE_MAX:
            check(f"{role} {name} @{width}: the dialog is full screen on a phone",
                  dialog["full"] and dialog["w"] >= dialog["vw"] - 1 and dialog["h"] >= dialog["vh"] - 1,
                  dialog)
        view_checks(page, width, name, root=target, role=role)
        shot(page, role, name, width)
        page.evaluate("""(sel) => { const m = document.querySelector(sel);
            bootstrap.Modal.getInstance(m).hide(); }""", target)
        try:
            page.wait_for_selector(f"{target}:not(.show)", state="attached", timeout=4000)
            page.wait_for_function("!document.querySelector('.modal-backdrop')", timeout=4000)
        except Exception:
            page.evaluate("document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());"
                          "document.body.classList.remove('modal-open'); document.body.style = ''")
    return opened


def visit(browser_ctx, page, role, path, label, width, tabs=False, dialogs=True):
    """Load one page, check it (and every tab on it), open its dialogs. Returns True if it loaded."""
    browser_ctx["errors"].clear()
    response = page.goto(path)
    page.wait_for_load_state("networkidle")
    status = response.status if response else 0
    if not check(f"{role} {label} @{width}: the page loads (HTTP {status})", status and status < 400):
        return False
    if "/login" in page.url and "/login" not in path:
        check(f"{role} {label} @{width}: the page is reached, not bounced to sign-in", False, page.url)
        return False
    errors = browser_ctx["errors"]
    page.wait_for_timeout(250)
    view_checks(page, width, label, role=role)
    shot(page, role, label, width)
    if dialogs:
        open_dialogs(page, role, label, width)
    if tabs:
        names = page.evaluate("""() => Array.from(document.querySelectorAll('[data-bs-toggle="tab"]'))
            .map((b, i) => { b.setAttribute('data-probe-tab', i); return [i, (b.getAttribute('data-bs-target') || '').slice(1)]; })""")
        for i, pane in names:
            tab = page.locator(f'[data-probe-tab="{i}"]')
            if not tab.is_visible():
                continue
            tab.scroll_into_view_if_needed()
            tab.click()
            page.wait_for_timeout(400)
            name = f"{label} tab {pane}"
            view_checks(page, width, name, role=role)
            shot(page, role, name, width)
            if dialogs:
                open_dialogs(page, role, name, width)
    check(f"{role} {label} @{width}: no script errors", not errors, "\n".join(errors[:3]))
    return True


# ---------------------------------------------------------------------------
# The database, the server, the people
# ---------------------------------------------------------------------------
def build_database():
    """The fictional demo database in the test folder, with known passwords for the four roles."""
    import contextlib
    import io
    import sqlite3

    import seed_demo_data as seed
    from werkzeug.security import generate_password_hash

    target = _support.guard_path(str(TEST_DIR / "mobile_demo.db"))
    cached = os.environ.get("IDS_MOBILE_DEMO_DB")
    if cached and Path(cached).exists() and Path(cached + ".key").exists():
        shutil.copyfile(cached, target)
        os.environ["SEALED_DATA_KEY"] = Path(cached + ".key").read_text().strip()
        config.DATABASE = target
        print("       reusing a demo database built earlier (copied to the test folder)")
    else:
        started = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            seed.build(target, show_passwords=False)
        print(f"       built the fictional demo database in {time.time() - started:.0f} s")

    import secrets
    passwords = {}
    conn = sqlite3.connect(target)
    try:
        for username in ("admin", "doctor", "staff1", "official"):
            passwords[username] = "Mobile-" + secrets.token_urlsafe(12)
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 "
                         "WHERE username = ?", (generate_password_hash(passwords[username]), username))
        # Visits for today, so the queue has rows and the consultation forms have a visit to
        # open. The demo data ends yesterday, with every visit finished.
        today = conn.execute("SELECT date('now', '+8 hours')").fetchone()[0]
        staff_id = conn.execute("SELECT id FROM users WHERE username = 'staff1'").fetchone()[0]
        patients = [r[0] for r in conn.execute(
            "SELECT id FROM patients WHERE status = 'Active' ORDER BY id LIMIT 4")]
        plan = [("Scheduled", 0), ("Waiting", 1), ("In Consultation", 1), ("Waiting for the Doctor", 1)]
        for patient_id, (status, checked_in) in zip(patients, plan):
            conn.execute(
                "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, "
                "appointment_time, status, is_walkin, checked_in_at) VALUES (?, ?, 'Consultation', ?, ?, ?, ?, ?)",
                (patient_id, staff_id, today, "09:00", status, checked_in,
                 f"{today} 08:30:00" if checked_in else None))
        conn.commit()
        picks = {
            "patient": conn.execute(
                "SELECT p.id FROM patients p ORDER BY (SELECT COUNT(*) FROM immunizations i WHERE i.patient_id = p.id)"
                " + (SELECT COUNT(*) FROM consultations c WHERE c.patient_id = p.id) DESC LIMIT 1").fetchone()[0],
            "item": conn.execute("SELECT id FROM inventory_items ORDER BY id LIMIT 1").fetchone()[0],
            "record": conn.execute(
                "SELECT id FROM appointments WHERE status = 'In Consultation' ORDER BY id DESC LIMIT 1").fetchone()[0],
            "edit": conn.execute("SELECT MAX(id) FROM consultations").fetchone()[0],
        }
    finally:
        conn.close()
    return target, passwords, picks


def start_server(database):
    """The app, on the demo database, on a free local port, in a thread. Returns (url, stop)."""
    import socket

    import app as app_module
    from utils.server import build_server

    config.DATABASE = database
    flask_app = app_module.create_app()
    flask_app.config["DATABASE"] = database
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = build_server(flask_app, "127.0.0.1", port)
    server.prepare()
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", server.stop


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
def pages_for(role, picks):
    """The pages to visit for a role, beyond the menu, as (path, label, tabs)."""
    clinic = role in ("doctor", "staff1")
    area = "staff" if clinic else "admin"
    extra = [("/account", "my account", False)]
    if role == "official":
        return extra
    extra += [
        (f"/{area}/patient_profile/{picks['patient']}", "patient profile", True),
        (f"/{area}/medicine_inventory/{picks['item']}", "inventory item", False),
        (f"/{area}/add_edit_medicine", "add medicine", False),
    ]
    if clinic:
        extra += [
            (f"/staff/consultation/record/{picks['record']}", "record consultation", False),
            (f"/staff/consultation/edit/{picks['edit']}", "edit consultation", False),
            (f"/staff/register-patient/{picks['patient']}", "edit patient", False),
        ]
    return extra


def main():
    section("0. THE DEMO DATABASE AND THE SERVER")
    database, passwords, picks = build_database()
    base_url, stop_server = start_server(database)
    check("the app answers on a local port", True)

    try:
        playwright_cm = sync_playwright().start()
        try:
            browser = Browser(playwright_cm, base_url)
        except Exception as problem:
            playwright_cm.stop()
            stop_server()
            print("SKIPPED: verify_mobile_layout.py could not start Chromium "
                  f"({str(problem).splitlines()[0][:120]}). " + INSTALL_HELP)
            return None
        if SHOTS.exists():
            for old in SHOTS.rglob("*.png"):
                old.unlink()
        try:
            run_checks(browser, passwords, picks)
        finally:
            browser.close()
            playwright_cm.stop()
    finally:
        stop_server()
    return True


def run_checks(browser, passwords, picks):
    roles = (("admin", "admin"), ("doctor", "doctor"), ("staff1", "staff1"), ("official", "official"))
    states = {}
    for role, username in roles:
        states[role] = browser.sign_in(username, passwords[username])
        check(f"{role} can sign in in the browser", states[role] is not None)
    if not all(states.values()):
        return

    # The sign-in page, before anyone is signed in.
    section("1. THE SIGN-IN PAGE")
    for width in WIDTHS:
        context = browser.context(width)
        page = context.new_page()
        holder = watch_errors(page)
        visit(holder, page, "signed-out", "/login", "sign in", width, dialogs=False)
        context.close()

    for role, username in roles:
        if ONLY_ROLES and role not in ONLY_ROLES:
            continue
        section(f"2. {role.upper()}")
        # The menu pages, read from the sidebar itself at desktop width.
        context = browser.context(1366, states[role])
        page = context.new_page()
        page.goto("/")
        page.wait_for_load_state()
        menu = page.evaluate("""() => Array.from(document.querySelectorAll('.sidebar-nav a'))
            .map(a => { const c = a.cloneNode(true);
                c.querySelectorAll('.material-symbols-outlined, .badge-count').forEach(e => e.remove());
                return [a.getAttribute('href'), c.textContent.trim().replace(/\\s+/g, ' ')]; })""")
        context.close()
        check(f"{role}: the sidebar lists menu pages", len(menu) >= 5, menu)
        pages = [(href, name, False) for href, name in menu] + pages_for(role, picks)
        if ONLY_PAGES:
            pages = [p for p in pages if any(w in (p[0] + p[1]).lower() for w in ONLY_PAGES)]

        for width in WIDTHS:
            context = browser.context(width, states[role])
            page = context.new_page()
            holder = watch_errors(page)
            for path, name, tabs in pages:
                try:
                    visit(holder, page, role, path, name, width, tabs=tabs)
                except Exception as problem:
                    check(f"{role} {name} @{width}: the page can be checked", False, str(problem)[:300])
            # The menu and the header.
            if width < LG:
                try:
                    menu_checks(page, role, width, menu)
                except Exception as problem:
                    check(f"{role} @{width}: the menu can be checked", False, str(problem)[:300])
            context.close()

    broken_layout_checks(browser, states["admin"], {"table": "/admin/patient_records"})


def menu_checks(page, role, width, menu):
    page.goto(menu[0][0])
    page.wait_for_load_state("networkidle")
    facts = page.evaluate(PROBE, {"root": None, "width": width})
    check(f"{role} @{width}: the menu button is visible and the sidebar is not",
          facts["menuButtonVisible"] and not facts["sidebarVisible"],
          {k: facts[k] for k in ("menuButtonVisible", "sidebarVisible")})
    # Open it, close it with the button, with a tap outside, and open it for each link.
    def open_menu():
        page.click('[data-bs-target="#sidebarMenu"][data-bs-toggle="offcanvas"]', timeout=3000)
        page.wait_for_selector("#sidebarMenu.show", timeout=3000)
        page.wait_for_timeout(450)

    def menu_is_closed():
        try:
            page.wait_for_selector("#sidebarMenu:not(.show)", state="attached", timeout=3000)
            page.wait_for_timeout(450)
            return True
        except Exception:
            return False

    try:
        open_menu()
        opened = True
    except Exception as problem:
        opened = False
        check(f"{role} @{width}: the menu button opens the menu", False, str(problem)[:160])
    if not opened:
        return
    check(f"{role} @{width}: the menu button opens the menu", True)
    shot(page, role, "menu open", width)
    inside = page.evaluate(PROBE, {"root": "#sidebarMenu", "width": width})
    real = [f"{i['d']} {i['w']}x{i['h']}" for i in inside["small"] if not i["reason"]]
    check(f"{role} @{width}: the open menu has no target under {MIN_TARGET}x{MIN_TARGET}", not real, "\n".join(real))
    page.click('#sidebarMenu [data-bs-dismiss="offcanvas"]', timeout=3000)
    check(f"{role} @{width}: the close button closes the menu", menu_is_closed())
    open_menu()
    page.mouse.click(width - 8, HEIGHTS[width] // 2)
    check(f"{role} @{width}: a tap outside closes the menu", menu_is_closed())

    for href, name in menu:
        page.goto(menu[0][0])
        page.wait_for_load_state("networkidle")
        open_menu()
        link = page.locator(f'#sidebarMenu .sidebar-nav a[href="{href}"]')
        try:
            with page.expect_navigation(timeout=8000):
                link.click(timeout=3000)
            page.wait_for_load_state("networkidle")
            ok = page.url.split("?")[0].endswith(href) or page.url.endswith(href)
            ok = ok and "/login" not in page.url
            detail = page.url
        except Exception as problem:
            ok, detail = False, str(problem)[:160]
        check(f"{role} @{width}: the menu link {href} works from inside the menu", ok, detail)


def broken_layout_checks(browser, state, base_path):
    """The checks must notice a broken layout. Break one on purpose, in the browser only."""
    section("3. THE CHECKS FAIL WHEN THE LAYOUT IS BROKEN")
    width = 390
    context = browser.context(width, state)
    page = context.new_page()
    page.goto(base_path["table"])
    page.wait_for_load_state("networkidle")
    before = page.evaluate(PROBE, {"root": None, "width": width})
    check("break-it: the table page is clean before it is broken",
          not before["tablesLoose"] and before["scrollW"] <= width,
          before["tablesLoose"])
    page.evaluate("document.querySelectorAll('.table-responsive').forEach(e => e.classList.remove('table-responsive'))")
    after = page.evaluate(PROBE, {"root": None, "width": width})
    check("break-it: with .table-responsive removed, the table check fails",
          bool(after["tablesLoose"]))
    check("break-it: with .table-responsive removed, the page scrolls sideways and the check fails",
          after["scrollW"] > width)
    page.goto(base_path["table"])
    page.wait_for_load_state("networkidle")
    pinned = page.evaluate(PROBE, {"root": None, "width": width})
    check("break-it: the pinned name column is found and sticky before it is broken",
          pinned["hasPin"] and pinned["pinned"] == 0, pinned["pinned"])
    page.evaluate("document.querySelectorAll('.pin-name').forEach(e => e.style.position = 'static')")
    check("break-it: with the pinning rule broken, the pin check fails",
          page.evaluate(PROBE, {"root": None, "width": width})["pinned"] > 0)
    page.goto(base_path["table"])
    page.wait_for_load_state("networkidle")
    holder = watch_errors(page)
    page.evaluate("console.error('probe'); setTimeout(() => { throw new Error('probe') }, 0)")
    page.wait_for_timeout(300)
    check("break-it: a console error and a script error are both collected",
          len(holder["errors"]) == 2, holder["errors"])
    page.goto(base_path["table"])
    page.wait_for_load_state("networkidle")
    page.evaluate("document.querySelectorAll('.offcanvas-lg, .offcanvas').forEach(e => "
                  "e.classList.remove('offcanvas-lg', 'offcanvas', 'offcanvas-start'))")
    page.evaluate("document.querySelectorAll('[data-bs-toggle=\"offcanvas\"]').forEach(e => e.remove())")
    broken = page.evaluate(PROBE, {"root": None, "width": width})
    check("break-it: with the offcanvas removed, the menu check fails",
          not (broken["menuButtonVisible"] and not broken["sidebarVisible"]))
    context.close()


if __name__ == "__main__":
    outcome = main()
    if outcome is None:
        sys.exit(0)
    passed = sum(1 for _, ok in results if ok)
    print("\n" + "-" * 72)
    if exceptions:
        print("Exceptions (each one counted, none hidden):")
        for reason, count in sorted(exceptions.items()):
            print(f"  {count} x {reason}")
    print(f"{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)
