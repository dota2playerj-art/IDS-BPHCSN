"""This computer's network addresses, the HTTPS certificate check, and the Settings line.

Used by utils/server.py (network mode), setup_https.py and the Settings screen.
"""
import ipaddress
import socket
import ssl
from datetime import datetime, timezone

import config

SETUP_COMMAND = "python setup_https.py"


def _usable(address):
    """A private or public IPv4 address another device could reach: not loopback or link-local."""
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast)


def _route_address():
    """The address this computer uses for its main network, or None.

    Connecting a UDP socket sends nothing; it only asks the system which address it
    would send from.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def local_ipv4_addresses():
    """This computer's network IPv4 addresses, the main one first. Empty when offline."""
    found = []
    main = _route_address()
    if main and _usable(main):
        found.append(main)
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    for info in infos:
        address = info[4][0]
        if _usable(address) and address not in found:
            found.append(address)
    return found


def https_urls(port):
    """The addresses other devices open, one per network address."""
    return [f"https://{address}:{port}" for address in local_ipv4_addresses()]


def certificate_problem(cert_file=None, key_file=None, now=None):
    """A short message saying what is wrong with the HTTPS certificate, or None."""
    cert_file = cert_file or config.CERT_FILE
    key_file = key_file or config.KEY_FILE
    fix = f"Run: {SETUP_COMMAND}"
    for path in (cert_file, key_file):
        if not path.is_file():
            return f"Network mode needs an HTTPS certificate, and {path.name} is missing. {fix}"
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_file), str(key_file))
    except (ssl.SSLError, OSError, ValueError):
        return ("The HTTPS certificate or its key cannot be read, or they do not match. "
                f"{fix} --replace")
    from cryptography import x509

    certificate = x509.load_pem_x509_certificate(cert_file.read_bytes())
    now = now or datetime.now(timezone.utc)
    if now >= certificate.not_valid_after_utc:
        return f"The HTTPS certificate has expired. {fix} --replace"
    return None


def network_mode_line(port):
    """The one read-only line Settings shows the Administrator."""
    if not config.NETWORK_MODE:
        return "Network mode: Off (this computer only)"
    addresses = local_ipv4_addresses()
    address = addresses[0] if addresses else socket.gethostname()
    return (f"Network mode: On — open https://{address}:{port} "
            "on other devices on the same Wi-Fi")
