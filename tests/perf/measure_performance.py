"""Chapter 4 performance: response times of the real server on the fictional demo data.

Builds the demo database in a temporary folder (never app.db), starts the production server
(cheroot, local mode, utils/server.run) on it in a child process, signs in as each role and
times each action over HTTP: warm-up runs first, then timed runs; median and 95th percentile.
    python tests/perf/measure_performance.py [--runs 30] [--warmup 3] [--out FILE]
Not part of tests/run_all.py: it measures, it does not pass or fail the code.
"""
import argparse
import base64
import contextlib
import ctypes
import http.client
import io
import math
import os
import platform
import re
import secrets
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import date, datetime
from http.cookies import SimpleCookie
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIVE_DB = REPO / "app.db"
TARGET_MS = 3000
ROLES = {"admin": "Administrator", "doctor": "Doctor", "staff1": "Health Center Staff",
         "official": "Barangay Official"}
DASHBOARDS = {"admin": "/admin/dashboard", "doctor": "/staff/dashboard",
              "staff1": "/staff/dashboard", "official": "/official/dashboard"}
# A fixed term typed into the header search; it is not read from any database.
SEARCH_TERM = "dela"


def guard(path):
    """Stop if a path is the live database or inside the project folder."""
    resolved = Path(path).resolve()
    if resolved == LIVE_DB.resolve() or REPO in resolved.parents:
        raise SystemExit(f"STOPPED: {resolved} is inside the project. Only a temp folder is used.")
    return str(resolved)


# ---------------------------------------------------------------------------
# The child process: the production server on the temporary database
# ---------------------------------------------------------------------------
def serve(database):
    sys.path.insert(0, str(REPO))
    import config

    config.DATABASE = guard(database)
    import app as app_module
    from utils.server import run

    if Path(app_module.app.config["DATABASE"]).resolve() != Path(database).resolve():
        raise SystemExit("STOPPED: the app is not on the temporary database.")
    run(app_module.app)


# ---------------------------------------------------------------------------
# The demo database
# ---------------------------------------------------------------------------
def build_database(folder, total_runs):
    """Seed the demo data, set known passwords and add today's visits for the write actions."""
    sys.path.insert(0, str(REPO))
    import seed_demo_data as seed
    from utils import dates
    from werkzeug.security import generate_password_hash

    database = guard(Path(folder) / "perf_demo.db")
    started = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        seed.build(database, say=lambda *a, **k: None, show_passwords=False)
    built_in = time.time() - started

    passwords = {}
    conn = sqlite3.connect(database)
    try:
        for username in ROLES:
            passwords[username] = "Perf-" + secrets.token_urlsafe(12)
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 "
                         "WHERE username = ?", (generate_password_hash(passwords[username]), username))
        # The demo data as seeded, before the visits added below for the two write actions.
        counts = {name: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for name, table in (
            ("patients", "patients"), ("visits", "appointments"), ("consultations", "consultations"),
            ("immunizations", "immunizations"), ("inventory items", "inventory_items"),
            ("inventory batches", "inventory_batches"), ("dispensing rows", "medicine_dispensing"),
            ("audit entries", "audit_logs"))}
        size_mb = Path(database).stat().st_size / 2 ** 20
        if conn.execute("SELECT COUNT(*) FROM appointments WHERE status = 'In Consultation'").fetchone()[0]:
            raise SystemExit("STOPPED: the demo data has a visit In Consultation; Start would be refused.")
        today = dates.today().isoformat()
        staff_id = conn.execute("SELECT id FROM users WHERE username = 'staff1'").fetchone()[0]
        adults = [r[0] for r in conn.execute(
            "SELECT id FROM patients WHERE status = 'Active' AND date(birth_date) <= date(?, '-18 years') "
            "ORDER BY id", (today,))]
        visits = {"doctor": [], "staff1": []}
        for index in range(2 * total_runs):
            who = "doctor" if index < total_runs else "staff1"
            cursor = conn.execute(
                "INSERT INTO appointments (patient_id, scheduled_by, appointment_type, appointment_date, "
                "appointment_time, status, is_walkin, checked_in_at) "
                "VALUES (?, ?, 'Consultation', ?, '08:00', 'Waiting', 1, ?)",
                (adults[index % len(adults)], staff_id, today, f"{today} 08:00:00"))
            visits[who].append(cursor.lastrowid)

        # The medicine for the FEFO runs: the one whose earliest usable batch can cover every
        # run alone, preferring one that also holds an expired batch with stock left.
        item = None
        for row in conn.execute(
                "SELECT i.id, "
                " (SELECT COUNT(*) FROM inventory_batches b WHERE b.inventory_item_id = i.id "
                "   AND b.quantity_remaining > 0 AND date(b.expiry_date) >= date(?)) AS usable, "
                " (SELECT COUNT(*) FROM inventory_batches b WHERE b.inventory_item_id = i.id "
                "   AND b.quantity_remaining > 0 AND date(b.expiry_date) < date(?)) AS expired "
                "FROM inventory_items i WHERE i.category = 'Medicine' AND i.status = 'Active' "
                "ORDER BY expired DESC, usable DESC, i.id", (today, today)):
            first = conn.execute(
                "SELECT id, quantity_remaining FROM inventory_batches WHERE inventory_item_id = ? "
                "AND quantity_remaining > 0 AND date(expiry_date) >= date(?) "
                "ORDER BY date(expiry_date), id LIMIT 1", (row[0], today)).fetchone()
            if row[1] >= 2 and first and first[1] >= total_runs:
                item = {"id": row[0], "first_batch": first[0], "usable_batches": row[1],
                        "expired_batches": row[2]}
                break
        if item is None:
            raise SystemExit("STOPPED: no medicine has two usable batches with enough stock.")
        patient = conn.execute(
            "SELECT p.id FROM patients p ORDER BY "
            "(SELECT COUNT(*) FROM immunizations i WHERE i.patient_id = p.id) + "
            "(SELECT COUNT(*) FROM consultations c WHERE c.patient_id = p.id) DESC, p.id LIMIT 1").fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {"path": database, "passwords": passwords, "visits": visits, "item": item,
            "patient": patient, "counts": counts, "size_mb": size_mb, "built_in": built_in,
            "today": today}


def start_server(database, folder):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ, IDS_PORT=str(port), IDS_NETWORK="0", IDS_DEBUG="0",
               PYTHONIOENCODING="utf-8")
    env.pop("SEMAPHORE_API_KEY", None)
    log = open(Path(folder) / "server.log", "w", encoding="utf-8")
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", database],
                             cwd=str(REPO), env=env, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + 60
    while time.time() < deadline:
        if child.poll() is not None:
            break
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/login")
            if conn.getresponse().status == 200:
                conn.close()
                return port, child, log
        except OSError:
            time.sleep(0.3)
    child.kill()
    log.close()
    raise SystemExit("STOPPED: the server did not start:\n"
                     + (Path(folder) / "server.log").read_text(encoding="utf-8")[-2000:])


# ---------------------------------------------------------------------------
# A small HTTP client: one new connection per request, cookies kept, no redirects followed
# ---------------------------------------------------------------------------
TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"|name="csrf-token" content="([^"]+)"')


class Client:
    def __init__(self, port):
        self.port = port
        self.cookies = {}

    def request(self, method, path, form=None):
        headers = {}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        body = None
        if form is not None:
            body = urllib.parse.urlencode(form)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        started = time.perf_counter()
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        elapsed = (time.perf_counter() - started) * 1000
        for header in response.headers.get_all("Set-Cookie") or []:
            for name, morsel in SimpleCookie(header).items():
                if morsel.value and "1970" not in (morsel["expires"] or ""):
                    self.cookies[name] = morsel.value
                else:
                    self.cookies.pop(name, None)
        conn.close()
        return response.status, response.headers, data, elapsed

    def token(self, path):
        status, _, data, _ = self.request("GET", path)
        found = TOKEN.search(data.decode("utf-8", "replace"))
        if status != 200 or not found:
            raise RuntimeError(f"no form token on {path} (HTTP {status})")
        return found.group(1) or found.group(2)

    def sign_in(self, username, password):
        token = self.token("/login")
        status, headers, _, elapsed = self.request(
            "POST", "/login", {"csrf_token": token, "username": username, "password": password})
        location = headers.get("Location", "")
        return elapsed, status == 302 and "/login" not in location and "/account" not in location, \
            f"HTTP {status} to {location or 'nowhere'}"


def page_ok(status, headers, data, kind="html"):
    """Whether a GET returned the page or file asked for, and a short reason when it did not."""
    if status != 200:
        return False, f"HTTP {status} {headers.get('Location', '')}"
    if kind == "html":
        text = data.decode("utf-8", "replace")
        if 'id="password"' in text and 'name="username"' in text:
            return False, "the sign-in page came back"
        if "Something went wrong" in text:
            return False, "the error page came back"
        return True, ""
    signature = {"xlsx": b"PK", "pdf": b"%PDF", "backup": b"IDSBAK1"}[kind]
    return data.startswith(signature), f"{len(data)} bytes, starts {data[:8]!r}"


# ---------------------------------------------------------------------------
# Measuring
# ---------------------------------------------------------------------------
def measure(label, role, how, action, warmup, runs, results):
    """Run `action(i)` warmup + runs times; it returns (ms, ok, detail). Keep the timed runs."""
    times, failures = [], []
    for i in range(warmup + runs):
        try:
            elapsed, ok, detail = action(i)
        except Exception as problem:  # a crash is a failed run, recorded, never hidden
            elapsed, ok, detail = None, False, f"{type(problem).__name__}: {problem}"
        if i < warmup:
            if not ok:
                failures.append(f"warm-up {i + 1}: {detail}")
            continue
        if ok:
            times.append(elapsed)
        else:
            failures.append(f"run {i - warmup + 1}: {detail}")
    row = {"label": label, "role": role, "how": how, "times": times, "failures": failures}
    if times:
        ordered = sorted(times)
        row.update(median=statistics.median(ordered),
                   p95=ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)],
                   minimum=ordered[0], maximum=ordered[-1])
    results.append(row)
    shown = (f"median {row['median']:.0f} ms, p95 {row['p95']:.0f} ms" if times else "no timed run")
    print(f"  {label:<44} {shown}{'  FAILURES: ' + str(len(failures)) if failures else ''}", flush=True)
    return row


def run_measurements(port, demo, warmup, runs):
    results = []
    clients = {}
    for username, password in demo["passwords"].items():
        clients[username] = Client(port)
        _, ok, detail = clients[username].sign_in(username, password)
        if not ok:
            raise SystemExit(f"STOPPED: {ROLES[username]} could not sign in ({detail}).")

    def get(username, path, kind="html"):
        def action(_):
            status, headers, data, elapsed = clients[username].request("GET", path)
            ok, detail = page_ok(status, headers, data, kind)
            return elapsed, ok, detail
        return action

    usernames = list(ROLES)

    def sign_in(i):
        username = usernames[i % len(usernames)]
        return Client(port).sign_in(username, demo["passwords"][username])

    measure("Sign in", "all four roles in turn", "POST /login (password check, new session)",
            sign_in, warmup, runs, results)
    for username, path in DASHBOARDS.items():
        measure(f"Dashboard ({ROLES[username]})", ROLES[username], f"GET {path}",
                get(username, path), warmup, runs, results)
    search = f"/staff/patient_records?search={SEARCH_TERM}"
    measure("Search patients", "Health Center Staff", f"GET {search}",
            get("staff1", search), warmup, runs, results)
    profile = f"/staff/patient_profile/{demo['patient']}"
    measure("Open a patient profile", "Doctor", "GET /staff/patient_profile/<id>",
            get("doctor", profile), warmup, runs, results)
    measure("Load the Patient Queue", "Health Center Staff", "GET /staff/appointment_scheduling",
            get("staff1", "/staff/appointment_scheduling"), warmup, runs, results)

    today = date.fromisoformat(demo["today"])
    month, year = today.month - 11, today.year
    if month < 1:
        month, year = month + 12, year - 1
    query = urllib.parse.urlencode({"type": "all", "from": date(year, month, 1).isoformat(),
                                    "to": today.isoformat()})

    def report(_):
        status, headers, data, elapsed = clients["admin"].request("GET", f"/admin/reports_analytics?{query}")
        ok, detail = page_ok(status, headers, data)
        if ok and "Reports are limited to" in data.decode("utf-8", "replace"):
            ok, detail = False, "the range was refused"
        return elapsed, ok, detail

    measure("Load Reports & Analytics (12 months)", "Administrator",
            "GET /admin/reports_analytics?type=all&from=&to= (12 months)", report, warmup, runs, results)
    measure("Export the report to Excel", "Administrator", "GET /admin/reports_analytics/export.xlsx (12 months)",
            get("admin", f"/admin/reports_analytics/export.xlsx?{query}", "xlsx"), warmup, runs, results)
    measure("Export the report to PDF", "Administrator", "GET /admin/reports_analytics/export.pdf (12 months)",
            get("admin", f"/admin/reports_analytics/export.pdf?{query}", "pdf"), warmup, runs, results)
    measure("Download an encrypted backup", "Administrator", "GET /admin/settings/backup.idsbackup",
            get("admin", "/admin/settings/backup.idsbackup", "backup"), warmup, runs, results)

    # The two writes. Each run starts its own visit first (not timed), as the queue does.
    def start(username, visit):
        client = clients[username]
        token = client.token("/staff/appointment_scheduling")
        status, _, _, _ = client.request("POST", "/staff/appointment_scheduling/start-consultation",
                                         {"csrf_token": token, "appointment_id": str(visit)})
        return client.token(f"/staff/consultation/record/{visit}")

    def save(username, visit, form):
        token = start(username, visit)
        status, headers, _, elapsed = clients[username].request(
            "POST", f"/staff/consultation/record/{visit}", dict(form, csrf_token=token))
        location = headers.get("Location", "")
        return elapsed, status == 302 and "/staff/patient_profile/" in location, \
            f"HTTP {status} to {location or 'nowhere'}"

    consult = {"chief_complaint": "Performance run", "diagnosis": "Performance run",
               "treatment_plan": "Performance run", "temperature": "36.8",
               "blood_pressure": "120/80", "pulse_rate": "78", "respiratory_rate": "18", "weight": "60"}
    measure("Save a consultation", "Doctor", "POST /staff/consultation/record/<visit> (diagnosis, plan)",
            lambda i: save("doctor", demo["visits"]["doctor"][i], consult), warmup, runs, results)
    intake = {"chief_complaint": "Performance run", "temperature": "36.8", "blood_pressure": "120/80",
              "pulse_rate": "78", "respiratory_rate": "18", "weight": "60",
              "dispense_item_0": str(demo["item"]["id"]), "dispense_qty_0": "1"}
    measure("Dispense medicine (FEFO)", "Health Center Staff",
            "POST /staff/consultation/record/<visit> (intake + 1 medicine line)",
            lambda i: save("staff1", demo["visits"]["staff1"][i], intake), warmup, runs, results)
    return results


def check_writes(demo, total_runs):
    """What the write runs left in the database: every visit saved, every unit from the right batch."""
    conn = sqlite3.connect(demo["path"])
    try:
        notes = []
        for who in ("doctor", "staff1"):
            ids = demo["visits"][who]
            saved = conn.execute(
                f"SELECT COUNT(*) FROM consultations WHERE appointment_id IN ({','.join('?' * len(ids))})",
                ids).fetchone()[0]
            notes.append(f"{ROLES[who]}: {saved} of {len(ids)} visits have a saved consultation.")
        item = demo["item"]
        rows = conn.execute(
            "SELECT b.id, b.expiry_date, l.quantity FROM medicine_dispensing d "
            "JOIN medicine_dispensing_batches l ON l.dispensing_id = d.id "
            "JOIN inventory_batches b ON b.id = l.batch_id "
            "JOIN consultations c ON c.id = d.consultation_id "
            "WHERE d.inventory_item_id = ? AND c.appointment_id IN (%s)" % ",".join("?" * total_runs),
            [item["id"], *demo["visits"]["staff1"]]).fetchall()
        from_first = sum(q for b, _, q in rows if b == item["first_batch"])
        expired = sum(q for _, e, q in rows if e and e < demo["today"])
        notes.append(f"FEFO: {sum(q for _, _, q in rows)} units dispensed in {total_runs} runs; "
                     f"{from_first} from the usable batch with the earliest expiry, {expired} from an "
                     f"expired batch (the item has {item['usable_batches']} usable and "
                     f"{item['expired_batches']} expired batch(es) with stock).")
    finally:
        conn.close()
    return notes


# ---------------------------------------------------------------------------
# The computer
# ---------------------------------------------------------------------------
def computer():
    cpu = platform.processor()
    ram = None
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass

        class Memory(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        memory = Memory()
        memory.dwLength = ctypes.sizeof(Memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            ram = memory.ullTotalPhys
    elif hasattr(os, "sysconf"):
        with contextlib.suppress(ValueError, OSError):
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    os_name = platform.platform()
    if sys.platform == "win32":
        release = platform.win32_ver()
        os_name = f"Windows {release[0]} {platform.win32_edition() or ''} (build {release[1]})".replace("  ", " ")
    import importlib.metadata

    import cheroot

    return {"CPU": f"{cpu} ({os.cpu_count()} logical processors)",
            "RAM": f"{ram / 2 ** 30:.1f} GB" if ram else "not read",
            "OS": os_name, "Python": platform.python_version(),
            "Flask": importlib.metadata.version("flask"),
            "Server": f"cheroot {cheroot.__version__}, local mode (127.0.0.1, HTTP), 10 threads"}


def report_text(results, demo, info, notes, warmup, runs, started, server_banner):
    lines = [f"# Performance measurement — {started:%Y-%m-%d %H:%M}", "",
             f"Made by `tests/perf/measure_performance.py`. {warmup} warm-up runs, then {runs} timed "
             f"runs per action. Target: {TARGET_MS} ms. Time = from sending the request to the last "
             "byte of the response, measured by a client on the same computer (no Wi-Fi in the path), "
             "one new connection per request, redirects not followed.", "",
             "## Test computer", ""]
    lines += [f"- {k}: {v}" for k, v in info.items()]
    lines += [f"- Server banner: {server_banner}", "", "## Data", "",
              f"Fictional demo database built by `seed_demo_data.py` in a temporary folder "
              f"({demo['built_in']:.0f} s), never `app.db`: {demo['size_mb']:.1f} MB as seeded, with "
              + ", ".join(f"{v} {k}" for k, v in demo["counts"].items())
              + f". Then {2 * len(demo['visits']['doctor'])} visits were added for today, Waiting, one "
              "per timed save (each run starts its own visit first, untimed, as the queue does).", "",
              "## Results (milliseconds)", "",
              "| # | Action | Role | Request | Median | 95th pct | Min | Max | Within 3 s | Failed runs |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for n, row in enumerate(results, 1):
        if row["times"]:
            within = "Yes" if row["p95"] <= TARGET_MS else "No"
            figures = f"{row['median']:.0f} | {row['p95']:.0f} | {row['minimum']:.0f} | {row['maximum']:.0f}"
        else:
            within, figures = "—", "— | — | — | —"
        lines.append(f"| {n} | {row['label']} | {row['role']} | `{row['how']}` | {figures} | {within} | "
                     f"{len(row['failures'])} |")
    lines += ["", "## Checks on what the write runs left", ""] + [f"- {n}" for n in notes]
    failed = [(row["label"], f) for row in results for f in row["failures"]]
    lines += ["", "## Failed runs", ""]
    lines += [f"- {label}: {f}" for label, f in failed] or ["None."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--out", default=str(REPO / "tests" / "perf" / "performance_results.md"))
    parser.add_argument("--serve")
    args = parser.parse_args()
    if args.serve:
        return serve(args.serve)

    sys.stdout.reconfigure(errors="replace")
    started = datetime.now()
    folder = tempfile.mkdtemp(prefix="ids-bphcsn-perf-")
    guard(Path(folder) / "x")
    # Keys made for this run only, set before config is imported, so .env is never used.
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    os.environ["SEALED_DATA_KEY"] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    os.environ["IDS_DEBUG"] = "0"
    os.environ["IDS_NETWORK"] = "0"
    os.environ["IDS_LOG_DIR"] = str(Path(folder) / "logs")
    child = log = None
    try:
        total = args.warmup + args.runs
        print("Building the fictional demo database in a temporary folder ...", flush=True)
        demo = build_database(folder, total)
        port, child, log = start_server(demo["path"], folder)
        banner = next((line.strip() for line in (Path(folder) / "server.log").read_text(
            encoding="utf-8").splitlines() if line.startswith("Local mode")), "not printed")
        print(f"Server: {banner}\nMeasuring ({args.warmup} warm-up + {args.runs} timed runs each):", flush=True)
        results = run_measurements(port, demo, args.warmup, args.runs)
        notes = check_writes(demo, total)
        text = report_text(results, demo, computer(), notes, args.warmup, args.runs, started, banner)
        Path(args.out).write_text(text, encoding="utf-8")
        print("\n" + "\n".join(notes) + f"\nWritten to {args.out}")
    finally:
        if child is not None:
            child.terminate()
            child.wait(timeout=30)
        if log is not None:
            log.close()
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    main()
