"""How `python app.py` serves the app: local mode or network mode.

Local mode (the default): this computer only, http://127.0.0.1:<port>.
Network mode (IDS_NETWORK=1 in .env): every network address of this computer, HTTPS only.
It refuses to start without a valid certificate (setup_https.py), so plain HTTP is never
served to the network.

With debug off, both modes use cheroot, a production web server that serves HTTPS by
itself. With IDS_DEBUG=1, local mode uses Flask's own development server, as before;
network mode refuses debug, because the debugger runs code typed into a browser.
"""
import re
import ssl
from contextlib import suppress

import config
from utils.network import certificate_problem, https_urls

LOCAL_HOST = "127.0.0.1"
NETWORK_HOST = "0.0.0.0"
THREADS = 10


def listen_port(setting=None):
    """The port from IDS_PORT, or the default. None when the setting is not a usable port."""
    setting = config.PORT_SETTING if setting is None else setting
    if not setting:
        return config.DEFAULT_PORT
    if not setting.isdigit() or not 1024 <= int(setting) <= 65535:
        return None
    return int(setting)


def start_problem():
    """A short message saying why the app must not start, or None."""
    if listen_port() is None:
        return "IDS_PORT in .env must be a number from 1024 to 65535, or empty for 5001."
    if config.NETWORK_MODE:
        if config.DEBUG:
            return "Network mode cannot run with debug on. Set IDS_DEBUG=0 in .env."
        return certificate_problem(config.CERT_FILE, config.KEY_FILE)
    return None


def listen_settings():
    """(host, certificate, key) for the mode .env sets. Local mode has no certificate."""
    if config.NETWORK_MODE:
        return NETWORK_HOST, config.CERT_FILE, config.KEY_FILE
    return LOCAL_HOST, None, None


PLAIN_HTTP_MARKER = "plain HTTP sent to the HTTPS port"


def log_plain_http(message):
    """One short line in logs/errors.log for a device that sent plain HTTP to the HTTPS port."""
    found = re.search(r"Client \('([^']+)'", str(message))
    who = found.group(1) if found else "a device"
    try:
        from utils.errors import error_logger

        error_logger().error("Plain HTTP request to the HTTPS port refused, from %s. "
                             "The address to use starts with https://", who)
    except Exception:
        pass  # a log that cannot be written must never turn one problem into two


def _cheroot_classes():
    """cheroot's server and TLS adapter, changed in one way: a plain HTTP request to the HTTPS
    port is refused quietly (L60).

    cheroot answers it by writing an error page onto a socket the failed TLS handshake has
    already closed. On Windows that raised WinError 10038 from clean-up code, which Python
    printed to the console as a traceback. The request was refused all the same; only the
    noise was wrong. Here the socket is closed at once, nothing is written to it, and the
    server's own message becomes one line in logs/errors.log instead of console text.
    """
    from cheroot import errors, wsgi
    from cheroot.ssl.builtin import BuiltinSSLAdapter

    class Adapter(BuiltinSSLAdapter):
        def wrap(self, sock):
            try:
                return super().wrap(sock)
            except errors.NoSSLError:
                with suppress(OSError):
                    sock.close()
                raise errors.FatalSSLAlert(PLAIN_HTTP_MARKER) from None

    class Server(wsgi.Server):
        def error_log(self, msg="", level=20, traceback=False):
            if PLAIN_HTTP_MARKER in str(msg):
                log_plain_http(msg)
                return
            super().error_log(msg, level, traceback)

    return Server, Adapter


def build_server(app, host, port, cert_file=None, key_file=None):
    """A cheroot server for the app. With a certificate and key it speaks HTTPS only."""
    Server, Adapter = _cheroot_classes()

    server = Server((host, port), app, numthreads=THREADS, server_name=config.SYSTEM_SHORT_NAME)
    if cert_file:
        adapter = Adapter(str(cert_file), str(key_file))
        adapter.context.minimum_version = ssl.TLSVersion.TLSv1_2
        server.ssl_adapter = adapter
    return server


def run(app):
    """Start the app in the mode .env sets. Blocks until Ctrl+C."""
    problem = start_problem()
    if problem:
        raise SystemExit(f"{config.SYSTEM_SHORT_NAME} cannot start. " + problem)
    port = listen_port()

    if not config.NETWORK_MODE and config.DEBUG:
        app.run(host=LOCAL_HOST, port=port, debug=True)
        return

    host, cert_file, key_file = listen_settings()
    server = build_server(app, host, port, cert_file, key_file)
    if config.NETWORK_MODE:
        addresses = https_urls(port) or [f"https://localhost:{port}"]
        lines = ["Network mode: HTTPS only. Open one of these on devices on the same Wi-Fi:"]
        lines += [f"  {url}" for url in addresses]
        lines.append(f"  On this computer: https://localhost:{port}")
    else:
        lines = [f"Local mode: this computer only. Open http://{LOCAL_HOST}:{port}"]

    try:
        server.prepare()
    except OSError:
        raise SystemExit(f"{config.SYSTEM_SHORT_NAME} cannot start. Port {port} is already "
                         "in use. Another copy of the app may be running. Close it first.")
    print(f"{config.SYSTEM_SHORT_NAME} is running.", *lines, "Press Ctrl+C to stop.", sep="\n",
          flush=True)
    try:
        server.serve()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
