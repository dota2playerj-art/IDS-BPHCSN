"""Create the .env file this app needs, once per computer.

    python setup_env.py

It writes a new random SECRET_KEY and IDS_DEBUG=0 to .env in the project folder.
If .env already exists, it changes nothing. It never prints the key.

.env is ignored by git. Never commit it, and never copy it to another computer:
each computer should have its own key.
"""
import secrets
import sys
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def main():
    if ENV_FILE.exists():
        print(f".env already exists at {ENV_FILE}. Nothing was changed.")
        print("To make a new key, delete .env and run this again. "
              "Everyone will have to sign in again.")
        return 0
    key = secrets.token_hex(32)
    ENV_FILE.write_text(
        "# Created by setup_env.py. Keep this file private. Never commit it.\n"
        "# SECRET_KEY signs the sign-in cookies.\n"
        f"SECRET_KEY={key}\n"
        "# 1 turns on Flask debug mode. Use it only on your own computer.\n"
        "IDS_DEBUG=0\n",
        encoding="utf-8",
    )
    print(f"Created {ENV_FILE} with a new secret key and debug mode off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
