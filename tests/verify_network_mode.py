"""Task 16: local mode and network mode, HTTPS, the certificate script and the cheroot server.

Network mode is turned on for this process only (IDS_TEST_NETWORK=1), with a certificate in
a temporary folder. The server under test listens on 127.0.0.1, never on the whole network,
so no firewall prompt appears. Child processes use their own test database.
"""
import atexit
import contextlib
import gc
import hashlib
import http.client
import io
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

CERT_DIR = Path(tempfile.mkdtemp(prefix="ids-bphcsn-certs-"))
atexit.register(shutil.rmtree, CERT_DIR, True)
os.environ["IDS_TEST_NETWORK"] = "1"
os.environ["IDS_CERT_DIR"] = str(CERT_DIR)
os.environ["IDS_PORT"] = ""
os.environ["IDS_DEBUG"] = "0"

import _support  # noqa: E402  (first: builds the test database, points the app at it)

import config  # noqa: E402
from app import create_app  # noqa: E402
from cryptography import x509  # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID  # noqa: E402
from utils import network  # noqa: E402
from utils import server as srv  # noqa: E402

REPO = Path(_support.REPO)
HERE = Path(__file__).resolve().parent
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


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


_children = [0]


def child_env(**values):
    """The environment for a child process: its own test database folder, and `values`."""
    _children[0] += 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["IDS_TEST_DIR"] = os.path.join(_support.TEST_DIR, f"child-{_children[0]}")
    env.update(values)
    return env


START_APP = f"import sys; sys.path.insert(0, r'{HERE}'); import _support; import app; app.main()"


def run_child(code_or_args, env, timeout=120):
    args = [sys.executable] + (code_or_args if isinstance(code_or_args, list) else ["-c", code_or_args])
    proc = subprocess.run(args, cwd=str(REPO), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


# ===========================================================================
section("1. THE TWO MODES AND THE START-UP CHECKS (D1, D2)")

check("IDS_PORT: empty means 5001; 5097 is used; text, 80 and 70000 are refused",
      srv.listen_port("") == 5001 and srv.listen_port("5097") == 5097
      and srv.listen_port("abc") is None and srv.listen_port("80") is None
      and srv.listen_port("70000") is None)

probe = "import config; print(config.NETWORK_MODE, config.SESSION_COOKIE_SECURE)"
outputs = {value: run_child(probe, child_env(IDS_NETWORK=value))[1].strip()
           for value in ("1", "", "yes", "0")}
check("IDS_NETWORK=1 turns network mode on, and with it the Secure cookie (D4)",
      outputs["1"] == "True True", outputs)
check("IDS_NETWORK empty, 'yes' or 0 is local mode, with no Secure cookie (local mode is plain HTTP)",
      all(outputs[v] == "False False" for v in ("", "yes", "0")), outputs)

host, cert_file, key_file = srv.listen_settings()
check("network mode listens on every address (0.0.0.0) with the certificate and key",
      host == "0.0.0.0" and cert_file == config.CERT_FILE and key_file == config.KEY_FILE,
      (host, cert_file, key_file))
config.NETWORK_MODE = False
check("local mode listens on 127.0.0.1 only, with no certificate (as before)",
      srv.listen_settings() == ("127.0.0.1", None, None), srv.listen_settings())
config.NETWORK_MODE = True

code, out = run_child(START_APP, child_env(IDS_TEST_NETWORK="1", IDS_DEBUG="0"))
check("network mode with no certificate refuses to start, with one plain message naming the command",
      code != 0 and "IDS-BPHCSN cannot start. Network mode needs an HTTPS certificate" in out
      and "Run: python setup_https.py" in out and "Traceback" not in out, out)
# tests/_support.py pins IDS_DEBUG=0 for every process, so this one is checked here: run()
# stops before it binds any port.
config.DEBUG = True
try:
    srv.run(object())
    refusal = "started"
except SystemExit as stop:
    refusal = str(stop)
config.DEBUG = False
check("network mode refuses debug mode (the debugger runs code typed into a browser)",
      refusal == "IDS-BPHCSN cannot start. Network mode cannot run with debug on. "
                 "Set IDS_DEBUG=0 in .env.", refusal)
code, out = run_child(START_APP, child_env(IDS_TEST_NETWORK="0", IDS_PORT="abc"))
check("a bad IDS_PORT is refused with a plain message", code != 0 and "IDS_PORT in .env" in out, out)

# Local mode starts as before: http://127.0.0.1:<port>, sign-in works, the cookie is not Secure.
port = free_port()
proc = subprocess.Popen([sys.executable, "-c", START_APP], cwd=str(REPO),
                        env=child_env(IDS_TEST_NETWORK="0", IDS_PORT=str(port), IDS_DEBUG="0"),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                        encoding="utf-8", errors="replace")
local = {}
try:
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/login")
            response = conn.getresponse()
            local["status"], local["server"] = response.status, response.getheader("Server", "")
            local["page"] = response.read().decode("utf-8", "replace")
            local["cookie"] = response.getheader("Set-Cookie", "")
            break
        except OSError:
            time.sleep(0.5)
    token = re.search(r'name="csrf_token" value="([^"]+)"', local.get("page", ""))
    cookie = local.get("cookie", "").split(";", 1)[0]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/login", body=f"username=staff&password={_support.PASSWORDS['staff']}"
                 f"&csrf_token={token.group(1) if token else ''}",
                 headers={"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie})
    response = conn.getresponse()
    local["login"] = (response.status, response.getheader("Location", ""),
                      response.getheader("Set-Cookie", ""))
    others = network.local_ipv4_addresses()
    local["lan"] = []
    for address in others:
        try:
            socket.create_connection((address, port), timeout=2).close()
            local["lan"].append(address)
        except OSError:
            pass
except Exception as error:  # noqa: BLE001  (recorded as a failed check below)
    local["error"] = repr(error)
    others = []
finally:
    proc.terminate()
    output = proc.communicate(timeout=30)[0]
check("local mode starts and serves the sign-in page at http://127.0.0.1:<port>",
      local.get("status") == 200 and "Sign In" in local.get("page", "") and "error" not in local,
      local.get("error") or local.get("status"))
check("local mode says so when it starts: 'Local mode: this computer only. Open http://127.0.0.1:<port>'",
      f"Local mode: this computer only. Open http://127.0.0.1:{port}" in output, output[-400:])
check("local mode with debug off is served by cheroot (it names the server IDS-BPHCSN), not by "
      "Flask's development server (which says Werkzeug) (D2)",
      local.get("server") == "IDS-BPHCSN", local.get("server"))
login = local.get("login", (0, "", ""))
check("signing in over plain HTTP in local mode works as before (302 to a screen, a session cookie "
      "that is HttpOnly and not Secure)",
      login[0] == 302 and "/login" not in login[1] and "HttpOnly" in login[2]
      and "Secure" not in login[2], login)
check(f"local mode cannot be reached from this computer's network addresses "
      f"({', '.join(others) or 'none found'})", not local.get("lan"), local.get("lan"))

# ===========================================================================
section("2. setup_https.py (D3)")

code, out = run_child([str(REPO / "setup_https.py")], child_env())
check("setup_https.py creates the certificate, the key and the device copy",
      code == 0 and config.CERT_FILE.is_file() and config.KEY_FILE.is_file()
      and config.DEVICE_CERT_FILE.is_file(), out)
key_text = config.KEY_FILE.read_text(encoding="ascii") if config.KEY_FILE.is_file() else ""
key_lines = [line for line in key_text.splitlines() if len(line) > 20 and "-----" not in line]
check("it never prints the private key (no PEM header, no line of the key)",
      "PRIVATE KEY" not in out and key_lines and not any(line in out for line in key_lines))
certificate = x509.load_pem_x509_certificate(config.CERT_FILE.read_bytes())
alt = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
dns = set(alt.get_values_for_type(x509.DNSName))
ips = {str(ip) for ip in alt.get_values_for_type(x509.IPAddress)}
addresses = network.local_ipv4_addresses()
check("the certificate names this computer's hostname and 'localhost'",
      {socket.gethostname(), "localhost"} <= dns, dns)
check(f"it names 127.0.0.1 and every network address of this computer ({', '.join(addresses)})",
      {"127.0.0.1", *addresses} <= ips, ips)
check("it prints the address to open for each network address, with the port",
      all(f"https://{a}:{config.DEFAULT_PORT}" in out for a in addresses), out[-600:])
check("it prints the steps for Windows, Android and iPhone",
      all(word in out for word in ("Windows:", "Android:", "iPhone:", "Trusted Root")), out[-600:])
days = (certificate.not_valid_after_utc - certificate.not_valid_before_utc).days
check(f"it is valid for about 2 years ({days} days)", 725 <= days <= 735, days)
check(f"the key is RSA {certificate.public_key().key_size} bits (at least 2048), signed with SHA-256",
      certificate.public_key().key_size >= 2048
      and certificate.signature_hash_algorithm.name == "sha256")
try:
    usage = list(certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
except x509.ExtensionNotFound:
    usage = []
check("it is marked for server authentication (needed by iPhones and Chrome)",
      ExtendedKeyUsageOID.SERVER_AUTH in usage, usage)
device = config.DEVICE_CERT_FILE.read_bytes()
check("the device copy (.crt) holds the certificate and no key",
      device == config.CERT_FILE.read_bytes() and b"PRIVATE KEY" not in device)
check("the certificate and key pass the start-up check", network.certificate_problem() is None,
      network.certificate_problem())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


before = digest(config.KEY_FILE)
code, out = run_child([str(REPO / "setup_https.py")], child_env())
check("a second run without --replace refuses, says how to replace, and changes nothing",
      code != 0 and "python setup_https.py --replace" in out and digest(config.KEY_FILE) == before, out)
code, out = run_child([str(REPO / "setup_https.py"), "--replace"], child_env())
check("--replace makes a new key and certificate",
      code == 0 and digest(config.KEY_FILE) != before and network.certificate_problem() is None, out)

code, out = run_child("import config; print(config.CERT_DIR)", child_env(IDS_CERT_DIR=""))
default_dir = Path(out.strip())
check("by default the files go in instance/certs/ in the project",
      default_dir == REPO / "instance" / "certs", out)
each =[subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=str(REPO)).returncode
        for path in ("instance/certs/ids-bphcsn-key.pem", "instance/certs/ids-bphcsn-cert.pem",
                     "instance/certs/ids-bphcsn.crt", "elsewhere/server.key",
                     "elsewhere/server.pem", "elsewhere/server.crt")]
check("git ignores the key, the certificate and the .crt in instance/certs/, and any .key, .pem or "
      ".crt file anywhere", each == [0] * 6, each)
tracked = subprocess.run(["git", "ls-files"], cwd=str(REPO), capture_output=True, text=True).stdout
check("no certificate or key is tracked in git",
      not re.search(r"(^instance/|\.(pem|key|crt|cer|p12|pfx)$)", tracked, re.M | re.I))

other = Path(tempfile.mkdtemp(prefix="ids-bphcsn-other-", dir=str(CERT_DIR)))
shutil.copy(config.CERT_FILE, other / "cert.pem")
subprocess.run([sys.executable, str(REPO / "setup_https.py")], cwd=str(REPO),
               env=child_env(IDS_CERT_DIR=str(other / "new")), capture_output=True)
problem = network.certificate_problem(other / "cert.pem", other / "new" / "ids-bphcsn-key.pem")
check("a key that does not belong to the certificate is refused", problem and "do not match" in problem,
      problem)
late = certificate.not_valid_after_utc + timedelta(days=1)
problem = network.certificate_problem(now=late)
check("an expired certificate is refused, with the command to replace it",
      problem and "expired" in problem and "--replace" in problem, problem)
problem = network.certificate_problem(other / "missing.pem", config.KEY_FILE)
check("a missing certificate is refused, naming the command",
      problem and "python setup_https.py" in problem, problem)

# ===========================================================================
section("3. THE REAL SERVER OVER HTTPS (D2, D4)")

app = create_app()
_support.attach(app)
_support.clear_password_change("staff")
check("in network mode the session cookie is Secure, HttpOnly and SameSite=Lax",
      app.config["SESSION_COOKIE_SECURE"] is True and app.config["SESSION_COOKIE_HTTPONLY"] is True
      and app.config["SESSION_COOKIE_SAMESITE"] == "Lax")

port = free_port()
_, cert_file, key_file = srv.listen_settings()
https_server = srv.build_server(app, "127.0.0.1", port, cert_file, key_file)
https_server.prepare()
threading.Thread(target=https_server.serve, daemon=True).start()

ORIGIN = f"https://127.0.0.1:{port}"
trust = None  # set inside the try below: the device certificate, as a phone would hold it


def https(method, path, host="127.0.0.1", body=None, headers=None, context=None):
    conn = http.client.HTTPSConnection(host, port, context=context or trust, timeout=15)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return (response.status, response.read().decode("utf-8", "replace"),
                response.getheader("Location", ""), response.msg.get_all("Set-Cookie") or [])
    finally:
        conn.close()


def sign_in(referer):
    status, page, _, cookies = https("GET", "/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    cookie = cookies[0].split(";", 1)[0] if cookies else ""
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie}
    if referer:
        headers["Referer"] = referer
    body = f"username=staff&password={_support.PASSWORDS['staff']}&csrf_token={token}"
    return https("POST", "/login", body=body, headers=headers)


# Any error below is a failed check, and the server always stops: cheroot's worker
# threads would otherwise keep this process alive.
try:
    trust = ssl.create_default_context(cafile=str(config.DEVICE_CERT_FILE))
    adapter = https_server.ssl_adapter
    check("the server will not speak anything older than TLS 1.2",
          adapter is not None and adapter.context.minimum_version >= ssl.TLSVersion.TLSv1_2,
          adapter and adapter.context.minimum_version)
    status, page, _, cookies = https("GET", "/login")
    check("GET https://127.0.0.1:<port>/login, checked against the certificate, is 200",
          status == 200 and "Sign In" in page, status)
    status, _, _, _ = https("GET", "/login", host="localhost")
    check("https://localhost:<port> works too (the name is in the certificate)", status == 200, status)
    try:
        https("GET", "/login", context=ssl.create_default_context())
        untrusted = "accepted"
    except ssl.SSLCertVerificationError:
        untrusted = "refused"
    check("a device that has not installed the .crt does not trust the server (the check is real)",
          untrusted == "refused", untrusted)
    status, _, location, cookies = sign_in(f"{ORIGIN}/login")
    session_cookie = next((c for c in cookies if c.startswith("session=")), "")
    check("signing in over HTTPS with a valid form token works (302 to a screen)",
          status == 302 and "/login" not in location, (status, location))
    check("the session cookie is marked Secure and HttpOnly, with SameSite=Lax",
          "Secure" in session_cookie and "HttpOnly" in session_cookie and "SameSite=Lax" in session_cookie,
          session_cookie)
    status, page, _, _ = https("GET", location or "/", headers={"Cookie": session_cookie.split(";", 1)[0]})
    check("the signed-in session works over HTTPS (the dashboard opens)", status == 200, status)
    status, page, _, _ = sign_in(None)
    check("over HTTPS, a POST with no Referer is refused by the form-token check (Flask-WTF strict mode)",
          status == 400 and "session expired" in page.lower(), status)
    status, page, _, _ = sign_in("https://example.com/login")
    check("over HTTPS, a POST whose Referer is another site is refused", status == 400, status)

    plain = {}
    # L60: the refusal must not print a traceback on the console; it is one line in errors.log.
    console = io.StringIO()
    error_log = Path(config.LOG_DIR) / "errors.log"
    lines_before = error_log.read_text(encoding="utf-8").splitlines() if error_log.exists() else []
    with contextlib.redirect_stderr(console):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/login")
            response = conn.getresponse()
            plain = {"status": response.status, "page": response.read().decode("utf-8", "replace")}
        except OSError as error:
            plain = {"error": type(error).__name__}
        time.sleep(0.5)
        gc.collect()  # the old noise came from clean-up code that runs when objects are collected
    check("a plain HTTP request to the HTTPS port gets no page",
          plain.get("status") != 200 and "Sign In" not in plain.get("page", ""), plain)
    check("L60: that refusal prints nothing to the console, no traceback",
          console.getvalue() == "", console.getvalue()[:300])
    lines_after = error_log.read_text(encoding="utf-8").splitlines() if error_log.exists() else []
    added = lines_after[len(lines_before):]
    check("L60: it writes exactly one short line to logs/errors.log, and no traceback",
          len(added) == 1 and "Plain HTTP request to the HTTPS port refused" in added[0]
          and len(added[0]) < 200, added)
    status, _, _, _ = https("GET", "/login")
    check("L60: the server still answers HTTPS after the refused request", status == 200, status)
except Exception as error:  # noqa: BLE001
    check("the HTTPS checks ran to the end without an error", False, repr(error))
finally:
    https_server.stop()

# ===========================================================================
section("4. THE SETTINGS LINE (D5)")

HTTPS_BASE = "https://localhost"
client = app.test_client()
with client.session_transaction(base_url=HTTPS_BASE) as sess:
    sess["user_id"] = 1
    _support.open_session(sess)


def settings_line():
    page = client.get("/admin/settings", base_url=HTTPS_BASE).get_data(as_text=True)
    found = re.search(r'id="network-mode-line">([^<]*)<', page)
    return found.group(1) if found else None


line = settings_line()
first = addresses[0] if addresses else socket.gethostname()
check("network mode: 'Network mode: On — open https://<address>:<port> on other devices on the "
      "same Wi-Fi'",
      line == f"Network mode: On — open https://{first}:{config.DEFAULT_PORT} "
              "on other devices on the same Wi-Fi", line)
real = network.local_ipv4_addresses
network.local_ipv4_addresses = lambda: []
line = settings_line()
network.local_ipv4_addresses = real
check("with no network address it names this computer instead",
      line and f"https://{socket.gethostname()}:" in line, line)
config.NETWORK_MODE = False
line = settings_line()
config.NETWORK_MODE = True
check("local mode: 'Network mode: Off (this computer only)'",
      line == "Network mode: Off (this computer only)", line)
staff = app.test_client()
with staff.session_transaction(base_url=HTTPS_BASE) as sess:
    sess["user_id"] = 2
    _support.open_session(sess)
check("only the Administrator reaches Settings (Staff are sent away)",
      staff.get("/admin/settings", base_url=HTTPS_BASE).status_code == 302)

# ===========================================================================
section("5. THE SIGN-IN PAGE, THE README AND THE SETTINGS FILES (D6, D7)")

page = client.get("/login", base_url=HTTPS_BASE).get_data(as_text=True)
check("the sign-in page no longer mentions appointments or announcements",
      "appointment" not in page.lower() and "announcement" not in page.lower())
check("it describes the system as it is, in one short line",
      "Patient records, consultations, immunization, the patient queue, medicine inventory, "
      "SMS notifications and reports in one system." in page)

readme = (REPO / "README.md").read_text(encoding="utf-8")
part = readme[readme.find("## Using the system from other devices"):]
part = part[:part.find("\n## ", 5)]
check("the README explains network mode: setup_https.py, IDS_NETWORK=1, the firewall on Private "
      "networks only, the .crt on each device, the address to open",
      all(text in part for text in ("python setup_https.py", "IDS_NETWORK=1", "Private networks only",
                                    "Never allow Public", "ids-bphcsn.crt", "https://")), part[:300])
lines = [line for line in part.splitlines()[1:] if line.strip()]
check(f"that section is short ({len(lines)} lines)", 6 <= len(lines) <= 12, len(lines))
example = (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
check(".env.example has IDS_NETWORK and IDS_PORT, each under a one-line comment",
      all(any(line.startswith(f"{name}=") and example[i - 1].startswith("#")
              for i, line in enumerate(example)) for name in ("IDS_NETWORK", "IDS_PORT")))
check("requirements.txt pins cheroot",
      re.search(r"^cheroot==\d", (REPO / "requirements.txt").read_text(encoding="utf-8"), re.M))

# ==== END ====
passed = sum(1 for _, ok in results if ok)
print("\n" + "=" * 78)
print(f"RESULT: {passed}/{len(results)} checks passed")
failed = [name for name, ok in results if not ok]
for name in failed:
    print(f"  FAILED: {name}")
sys.exit(1 if failed else 0)
