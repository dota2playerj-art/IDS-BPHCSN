"""Run every test suite, each on its own fresh test database.

    python tests/run_all.py            run all suites
    python tests/run_all.py -v         also print each suite's full output
    python tests/run_all.py rbac epi   run only the suites whose names contain these words
    python tests/run_all.py --quick    skip the suites that take over 60 seconds (SLOW_SUITES)

The live app.db is never used: the runner checks its size, time and checksum after the run.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LIVE_DB = REPO / "app.db"
GUARD_EXIT_CODE = 97  # the same value as tests/_support.py

# Suites that take over 60 seconds. `--quick` skips them. verify_demo_data.py builds the
# demo database twice (about 3 minutes) to prove it is deterministic.
SLOW_SUITES = ("verify_demo_data.py",)

# Suite file, and the file name it had in the old temp folder.
SUITES = [
    ("verify_epi.py", "1ae1173e_verify_epi.py"),
    ("verify_staff_capabilities.py", "1ae1173e_verify_staff_caps.py"),
    ("verify_add_user.py", "033c26b6_verify_add_user.py"),
    ("verify_my_account.py", "39d11d59_verify_my_account.py"),
    ("verify_password_change_audit.py", "6225b991_check_pwaudit.py"),
    ("verify_edit_user_reset_password.py", "7b0d7b4d_e2e.py"),
    ("verify_rbac.py", "2aec74c4_verify_rbac_ported.py"),
    ("verify_reports.py", "2aec74c4_verify_reports_ported.py"),
    ("verify_dispensing.py", "e04a0beb_verify_dispense_ported.py"),
    ("verify_doctor.py", "verify_doctor.py"),
    ("verify_service_schedule.py", "verify_service_schedule.py"),
    ("verify_database_integrity.py", "(new in Task 1b)"),
    ("verify_security_basics.py", "(new in Task 2)"),
    ("verify_csrf.py", "(new in Task 3)"),
    ("verify_audit_coverage.py", "(new in Task 4)"),
    ("verify_sealed_privacy.py", "(new in Task 5)"),
    ("verify_admin_minimum_necessary.py", "(new in Task 5c)"),
    ("verify_small_counts_and_masking.py", "(new in Task 5d)"),
    ("verify_demo_data.py", "(new in Task 8)"),
    ("verify_doctor_worklist_and_left.py", "(new in Task 6)"),
    ("verify_cleanup.py", "(new in Task 7)"),
    ("verify_final_fixes.py", "(new in the final fixes)"),
    ("verify_immunization_evidence.py", "(new in Task 9)"),
]

# The suites were written at different times and end with different summary
# lines. Each pattern turns one of them into (passed, total).
SUMMARIES = [
    (re.compile(r"(\d+)/(\d+) checks passed"),
     lambda a, b: (a, b)),
    (re.compile(r"(\d+) passed, (\d+) failed"),
     lambda a, b: (a, a + b)),
    (re.compile(r"checks: (\d+) \| failures: (\d+)"),
     lambda a, b: (a - b, a)),
    (re.compile(r"PASSED: (\d+)\s+FAILED: (\d+)"),
     lambda a, b: (a, a + b)),
    (re.compile(r"^PASS (\d+)\s+FAIL (\d+)", re.M),
     lambda a, b: (a, a + b)),
]
FAIL_LINE = re.compile(r"^\s*(\[FAIL\]|FAIL\b|FAILED\b|- )")


def fingerprint(path):
    """Size, modified time and SHA-256 of a file, or None if it is absent."""
    if not path.exists():
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns, digest)


def parse_summary(output):
    """(passed, total) from the LAST summary line in the output, or None."""
    found = []
    for pattern, convert in SUMMARIES:
        for match in pattern.finditer(output):
            found.append((match.start(),
                          convert(int(match.group(1)), int(match.group(2)))))
    return max(found)[1] if found else None


def run_suite(name):
    folder = Path(tempfile.mkdtemp(prefix="ids-bphcsn-test-"))
    if REPO in folder.resolve().parents:
        print(f"STOPPED: the temporary folder {folder} is inside the project.")
        sys.exit(2)
    env = dict(os.environ, IDS_TEST_DIR=str(folder), PYTHONIOENCODING="utf-8")
    started = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(HERE / name)], cwd=str(REPO), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800,
        )
        output = proc.stdout + ("\n" + proc.stderr if proc.stderr.strip() else "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "timed out after 30 minutes", -1
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    seconds = time.time() - started
    leftover = folder.exists()
    return output, code, seconds, leftover


def main(argv):
    # Some Windows consoles cannot print every character the suites use, such
    # as "—". Replace those instead of stopping the run.
    sys.stdout.reconfigure(errors="replace")
    verbose = "-v" in argv
    quick = "--quick" in argv
    words = [a for a in argv if not a.startswith("-")]
    chosen = [s for s in SUITES if not words or any(w in s[0] for w in words)]
    skipped = [s[0] for s in chosen if quick and s[0] in SLOW_SUITES]
    chosen = [s for s in chosen if s[0] not in skipped]
    if not chosen:
        print("No suite matches:", " ".join(words))
        return 2

    before = fingerprint(LIVE_DB)
    print(f"Running {len(chosen)} suite(s). Each uses its own fresh test database.")
    if skipped:
        print("Skipped (slow): " + ", ".join(skipped))
    print("-" * 72)

    total_passed = total_checks = 0
    failed_suites = []
    for name, _old in chosen:
        output, code, seconds, leftover = run_suite(name)
        if code == GUARD_EXIT_CODE:
            print(output)
            print(f"\nSTOPPED: {name} tried to use a database inside the project.")
            print("The whole run was stopped. Nothing else was run.")
            return 2
        summary = parse_summary(output)
        if summary is None:
            line = f"{name:40s} CRASHED (exit {code}, no summary line)"
            failed_suites.append(name)
        else:
            passed, total = summary
            total_passed += passed
            total_checks += total
            ok = passed == total and code == 0
            status = "ok" if ok else "FAILED"
            line = f"{name:40s} {passed:4d}/{total:<4d} {status}"
            if not ok:
                failed_suites.append(name)
        print(f"{line}  ({seconds:.0f}s)")
        if leftover:
            print("    note: its temporary folder could not be deleted")
        if verbose:
            print(output)
        elif name in failed_suites:
            lines = [l for l in output.splitlines() if FAIL_LINE.match(l)]
            for l in lines[:15]:
                print("    " + l.strip()[:150])
            if len(lines) > 15:
                print(f"    ... and {len(lines) - 15} more failing lines (run with -v)")
            if summary is None:
                for l in output.strip().splitlines()[-8:]:
                    print("    | " + l[:150])

    print("-" * 72)
    print(f"TOTAL: {total_passed}/{total_checks} checks passed in "
          f"{len(chosen) - len(failed_suites)}/{len(chosen)} suites")

    after = fingerprint(LIVE_DB)
    if before != after:
        print("\n!!! The live app.db CHANGED during this run. Stop and tell the team. !!!")
        return 3
    print("Live app.db unchanged (size, modified time and checksum match)."
          if before else "No live app.db in this folder; none was created.")

    if skipped:
        print("Quick run: run the full suite before pushing.")
    if failed_suites:
        print("FAILED suites: " + ", ".join(failed_suites))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
