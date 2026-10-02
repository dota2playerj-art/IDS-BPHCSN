"""Create the .env file this app needs, or add what is missing from it."""
import secrets
import sys
from pathlib import Path

from utils.sealed_crypto import new_key

ENV_FILE = Path(__file__).resolve().parent / ".env"

HEADER = "# Created by setup_env.py. Keep this file private. Never commit it.\n"

# name -> (comment, function that makes a new value)
VARIABLES = {
    "SECRET_KEY": ("# SECRET_KEY signs the sign-in cookies.",
                   lambda: secrets.token_hex(32)),
    "SEALED_DATA_KEY": ("# SEALED_DATA_KEY encrypts sealed consultations. Do not change it.\n"
                        "# Without it, sealed records cannot be opened.",
                        new_key),
    "IDS_DEBUG": ("# 1 turns on Flask debug mode. Use it only on your own computer.",
                  lambda: "0"),
}


def _names_in(text):
    names = set()
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.add(line.split("=", 1)[0].strip())
    return names


def _block(name):
    comment, make = VARIABLES[name]
    return f"{comment}\n{name}={make()}\n"


def main():
    if not ENV_FILE.exists():
        ENV_FILE.write_text(HEADER + "".join(_block(name) for name in VARIABLES),
                            encoding="utf-8")
        print(f"Created {ENV_FILE} with new keys and debug mode off.")
        return 0

    text = ENV_FILE.read_text(encoding="utf-8")
    missing = [name for name in VARIABLES if name not in _names_in(text)]
    if not missing:
        print(f".env already has everything at {ENV_FILE}. Nothing was changed.")
        return 0

    addition = "".join(_block(name) for name in missing)
    if text and not text.endswith("\n"):
        addition = "\n" + addition
    with ENV_FILE.open("a", encoding="utf-8") as handle:
        handle.write(addition)
    print(f"Added to {ENV_FILE}: {', '.join(missing)}. Existing values were not changed.")
    if "SEALED_DATA_KEY" in missing:
        print("Next: run python export_sealed_key.py and give the key to the Doctor "
              "in a sealed envelope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
