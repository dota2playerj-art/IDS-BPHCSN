"""How `python app.py` serves the app: local mode or network mode.

Local mode (the default): this computer only, http://127.0.0.1:<port>.
Network mode (IDS_NETWORK=1 in .env): every network address of this computer, HTTPS only.
It refuses to start without a valid certificate (setup_https.py), so plain HTTP is never
served to the network.

With debug off, both modes use cheroot, a production web server that serves HTTPS by
itself. With IDS_DEBUG=1, local mode uses Flask's own development server, as before;
network mode refuses debug, because the debugger runs code typed into a browser.
"""
import ssl

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


def build_server(app, host, port, cert_file=None, key_file=None):
    """A cheroot server for the app. With a certificate and key it speaks HTTPS only."""
    from cheroot import wsgi
    from cheroot.ssl.builtin import BuiltinSSLAdapter

    server = wsgi.Server((host, port), app, numthreads=THREADS,
                         server_name=config.SYSTEM_SHORT_NAME)
    if cert_file:
        adapter = BuiltinSSLAdapter(str(cert_file), str(key_file))
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

    if config.NETWORK_MODE:
        server = build_server(app, NETWORK_HOST, port, config.CERT_FILE, config.KEY_FILE)
        addresses = https_urls(port) or [f"https://localhost:{port}"]
        lines = ["Network mode: HTTPS only. Open one of these on devices on the same Wi-Fi:"]
        lines += [f"  {url}" for url in addresses]
        lines.append(f"  On this computer: https://localhost:{port}")
    else:
        server = build_server(app, LOCAL_HOST, port)
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
