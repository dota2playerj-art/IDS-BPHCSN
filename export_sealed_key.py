"""Show the sealed-record key once, so it can be written on paper for the Doctor.

    python export_sealed_key.py

Run it by hand at the health-center computer. It asks you to type YES, then
prints SEALED_DATA_KEY from .env with instructions. It writes nothing to disk.

Without this key, sealed records cannot be opened if this computer fails.
"""
import sys
from pathlib import Path

from dotenv import dotenv_values

from utils.sealed_crypto import key_problem

ENV_FILE = Path(__file__).resolve().parent / ".env"

INSTRUCTIONS = """
This is the key that encrypts sealed (Restricted) consultations.

1. Write it on paper exactly as shown. Check it twice.
2. Put the paper in an envelope, seal it, and write on it:
   "IDS-BPHCSN sealed-record key. Open only to restore the system."
3. Give the envelope to the Doctor to keep in a locked place.

Without this key, sealed records cannot be recovered if this computer fails.
Do not photograph it, type it into a message, or save it in a file.
"""


def main(read=input):
    if not ENV_FILE.exists():
        print(f"No .env file at {ENV_FILE}. Run: python setup_env.py")
        return 1
    key = dotenv_values(ENV_FILE).get("SEALED_DATA_KEY", "") or ""
    problem = key_problem(key)
    if problem:
        print(problem)
        return 1

    print(INSTRUCTIONS)
    answer = read("Make sure nobody else can see the screen. Type YES to show the key: ")
    if answer.strip() != "YES":
        print("Nothing was shown.")
        return 1

    print("\nSEALED_DATA_KEY:\n")
    print(f"    {key}\n")
    print("Close this window when you have written it down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
