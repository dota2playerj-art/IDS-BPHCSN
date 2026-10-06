"""Create the HTTPS certificate and key for network mode. Run once on the server computer.

    python setup_https.py              create them (refuses if they already exist)
    python setup_https.py --replace    make new ones, for example when this computer's
                                       network address has changed

The certificate is self-signed. It names this computer, "localhost", 127.0.0.1 and every
network address this computer has now. It is valid for 2 years. The files go in
instance/certs/, which git ignores. The private key is written to a file and never printed.
ids-bphcsn.crt is the certificate alone, to install on each phone and computer, so their
browsers trust the address without a warning.
"""
import argparse
import ipaddress
import os
import secrets
import socket
import sys
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import config
from utils.network import local_ipv4_addresses
from utils.server import listen_port

KEY_BITS = 3072
VALID_DAYS = 730
# Started a little in the past, so a device whose clock is slightly behind still accepts it.
BACKDATE = timedelta(hours=1)

TRUST_STEPS = """\
Install ids-bphcsn.crt (not the key) on each device, once:
  Windows:  double-click ids-bphcsn.crt > Install Certificate > Current User >
            Place all certificates in: Trusted Root Certification Authorities > Finish.
            Close and reopen the browser.
  Android:  copy ids-bphcsn.crt to the phone. Settings > Security > Encryption & credentials >
            Install a certificate > CA certificate, and choose the file.
            (Menu names differ a little between phones. Use Chrome.)
  iPhone:   send ids-bphcsn.crt to the phone (AirDrop or e-mail) and open it.
            Settings > General > VPN & Device Management > install the profile.
            Then Settings > General > About > Certificate Trust Settings > turn it on."""


def alt_names(hostname, addresses):
    """The names and addresses the certificate is valid for."""
    names = [x509.DNSName(hostname), x509.DNSName("localhost"),
             x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
    for address in addresses:
        names.append(x509.IPAddress(ipaddress.IPv4Address(address)))
    return names


def make_certificate(hostname, addresses, now=None):
    """(private key, certificate): self-signed, RSA 3072, SHA-256, valid for 2 years."""
    now = now or datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"{config.SYSTEM_SHORT_NAME} on {hostname}"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, config.SYSTEM_SHORT_NAME),
    ])
    public = key.public_key()
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(public)
        .serial_number(int.from_bytes(secrets.token_bytes(16), "big") >> 1)
        .not_valid_before(now - BACKDATE)
        .not_valid_after(now + timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt_names(hostname, addresses)),
                       critical=False)
        # The devices trust this certificate itself, so it is marked as its own authority.
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True,
                                     key_cert_sign=True, content_commitment=False,
                                     data_encipherment=False, key_agreement=False,
                                     crl_sign=False, encipher_only=False,
                                     decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _write_private(path, data):
    """Write the key so only this user can read it, where the system allows that."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create the HTTPS certificate for network mode.")
    parser.add_argument("--replace", action="store_true",
                        help="replace the certificate and key that already exist")
    args = parser.parse_args(argv)

    files = (config.CERT_FILE, config.KEY_FILE, config.DEVICE_CERT_FILE)
    existing = [path.name for path in files if path.exists()]
    if existing and not args.replace:
        print(f"A certificate already exists in {config.CERT_DIR} ({', '.join(existing)}). "
              "Nothing was changed.\nTo make a new one, run: python setup_https.py --replace\n"
              "Then install the new ids-bphcsn.crt on every device again.")
        return 1

    hostname = socket.gethostname()
    addresses = local_ipv4_addresses()
    key, certificate = make_certificate(hostname, addresses)

    config.CERT_DIR.mkdir(parents=True, exist_ok=True)
    _write_private(config.KEY_FILE, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    pem = certificate.public_bytes(serialization.Encoding.PEM)
    config.CERT_FILE.write_bytes(pem)
    config.DEVICE_CERT_FILE.write_bytes(pem)

    port = listen_port() or config.DEFAULT_PORT
    valid_for = ", ".join([hostname, "localhost", "127.0.0.1"] + addresses)
    print(f"Created the HTTPS certificate in {config.CERT_DIR}")
    print(f"  {config.CERT_FILE.name} and {config.KEY_FILE.name}: for the server. "
          "Keep the key private; it is never printed.")
    print(f"  {config.DEVICE_CERT_FILE.name}: the certificate only, to install on devices.")
    print(f"Valid for: {valid_for}")
    print(f"Valid until: {certificate.not_valid_after_utc:%B %d, %Y}")
    if addresses:
        print("Open on other devices on the same Wi-Fi (after setting IDS_NETWORK=1 in .env):")
        for address in addresses:
            print(f"  https://{address}:{port}")
    else:
        print("No network address was found. Connect this computer to the Wi-Fi, "
              "then run: python setup_https.py --replace")
    print(TRUST_STEPS)
    print("If this computer's network address changes, run python setup_https.py --replace "
          "and install the new ids-bphcsn.crt again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
