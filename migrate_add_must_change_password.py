"""Add users.must_change_password, and mark accounts still on an old demo password.

usage:
    python migrate_add_must_change_password.py [database]
    python migrate_add_must_change_password.py [database] --flag-all

The database defaults to app.db (config.DATABASE).

WHAT IT DOES, IN ORDER
----------------------
1. Reads the old demo passwords from git history: every version of
   models/users.py whose DEMO_USERS list held a password. They are kept in
   memory only. They are never written to this file, printed, or stored.
2. Before it changes anything, copies the database into the folder
   IDS-BPHCSN-backups next to the project, with a timestamped name. When there
   is nothing to change, it makes no copy and writes nothing.
3. Adds users.must_change_password (INTEGER NOT NULL DEFAULT 0) if it is missing.
4. Sets must_change_password = 1 for every account whose stored hash matches an
   old demo password. Prints those usernames. Never prints a password.

Safe to run twice. The second run finds the column and the flags in place and
changes nothing.

If git or the history cannot be read, it stops and changes nothing. Then
--flag-all marks every account instead, so everyone sets a new password once.

The H6 privacy cleanup (2026-09-29) took the old passwords out of git history.
Every old version now reads "(retired demo password)" instead, and step 1
skips that text. So on any copy of the repository made after the cleanup, step
1 finds nothing and the script stops: run it with --flag-all.

Afterwards it checks that only the new column moved: the same accounts, the
same values in every other column, and the same number of rows in every table.
"""
import ast
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from werkzeug.security import check_password_hash

import config

PROJECT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT.parent / "IDS-BPHCSN-backups"
TASK = "must-change-password"
COLUMN = "must_change_password"
COLUMN_SQL = f"ALTER TABLE users ADD COLUMN {COLUMN} INTEGER NOT NULL DEFAULT 0"
# What the history rewrite put where each old password was. Not a password.
RETIRED = "(retired demo password)"


def old_demo_passwords(repo=PROJECT):
    """Every password DEMO_USERS ever held, read from git history. A set.

    Raises RuntimeError when git or the history cannot be read.
    """
    log = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", "models/users.py"],
        cwd=repo, capture_output=True, text=True, encoding="utf-8",
    )
    if log.returncode != 0 or not log.stdout.strip():
        raise RuntimeError("git history of models/users.py could not be read")
    found = set()
    for sha in log.stdout.split():
        show = subprocess.run(
            ["git", "show", f"{sha}:models/users.py"],
            cwd=repo, capture_output=True, text=True, encoding="utf-8",
        )
        if show.returncode != 0:
            continue
        try:
            tree = ast.parse(show.stdout)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "DEMO_USERS"
                            for t in node.targets)
                    and isinstance(node.value, ast.List)):
                continue
            for entry in node.value.elts:
                # Old shape: (username, password, full name, role).
                if (isinstance(entry, ast.Tuple) and len(entry.elts) == 4
                        and all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                                for e in entry.elts)
                        and entry.elts[1].value != RETIRED):
                    found.add(entry.elts[1].value)
    if not found:
        raise RuntimeError("no old demo password was found in git history")
    return found


def _columns(conn):
    return [row[1] for row in conn.execute("PRAGMA table_info(users)")]


def _snapshot(conn):
    """Every table's row count, and every users row without the new column."""
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    keep = [c for c in _columns(conn) if c != COLUMN]
    users = conn.execute(
        f"SELECT {', '.join(keep)} FROM users ORDER BY id").fetchall()
    return counts, users


def _backup(db_path, backup_dir):
    """A consistent copy of the database, made with SQLite's backup interface."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{Path(db_path).name}.PRETASK_BACKUP_{TASK}_{stamp}"
    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def run(db_path, candidates=None, backup_dir=BACKUP_DIR, flag_all=False):
    """Apply the migration. Returns a dict describing what happened.

    `candidates` is the set of old passwords to compare against. It is used
    only in memory. With flag_all=True, every account is marked instead.
    """
    db_path = str(db_path)
    if not Path(db_path).exists():
        raise SystemExit(f"No database at {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        has_column = COLUMN in _columns(conn)
        accounts = conn.execute(
            f"SELECT id, username, password_hash"
            f"{', ' + COLUMN if has_column else ''} FROM users ORDER BY id").fetchall()
        to_flag = []
        for account in accounts:
            already = has_column and account[COLUMN] == 1
            if already:
                continue
            if flag_all:
                to_flag.append(account)
            elif account["password_hash"] and any(
                    check_password_hash(account["password_hash"], p) for p in candidates or ()):
                to_flag.append(account)

        result = {"database": db_path, "backup": None, "column_added": False,
                  "flagged": [a["username"] for a in to_flag], "problems": []}
        if has_column and not to_flag:
            return result  # nothing to change: no copy, no write

        result["backup"] = str(_backup(db_path, backup_dir))
        before_counts, before_users = _snapshot(conn)

        conn.execute("BEGIN")
        if not has_column:
            conn.execute(COLUMN_SQL)
            result["column_added"] = True
        for account in to_flag:
            conn.execute(f"UPDATE users SET {COLUMN} = 1 WHERE id = ?", (account["id"],))
        conn.execute("COMMIT")

        # Verification: only the new column moved.
        after_counts, after_users = _snapshot(conn)
        if after_counts != before_counts:
            result["problems"].append("a table's row count changed")
        if [tuple(r) for r in after_users] != [tuple(r) for r in before_users]:
            result["problems"].append("a users column other than the new one changed")
        info = {r[1]: r for r in conn.execute("PRAGMA table_info(users)")}
        column = info.get(COLUMN)
        if column is None or column[2] != "INTEGER" or column[3] != 1 or str(column[4]) != "0":
            result["problems"].append(f"{COLUMN} is missing or not INTEGER NOT NULL DEFAULT 0")
        flagged_now = {r[0] for r in conn.execute(
            f"SELECT username FROM users WHERE {COLUMN} = 1")}
        if not set(result["flagged"]) <= flagged_now:
            result["problems"].append("an account meant to be flagged is not")
        return result
    finally:
        conn.close()


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flag_all = "--flag-all" in argv
    db_path = args[0] if args else config.DATABASE
    print(f"database: {db_path}")

    candidates = None
    if not flag_all:
        try:
            candidates = old_demo_passwords()
        except RuntimeError as exc:
            print(f"STOPPED: {exc}. Nothing was changed.")
            print("Run again with --flag-all to make every account set a new password.")
            return 1
        print(f"old demo passwords read from git history: {len(candidates)} "
              "(kept in memory only, not shown)")

    result = run(db_path, candidates, flag_all=flag_all)
    if result["backup"] is None:
        print("Nothing to change: the column exists and no account needs flagging.")
        print("No backup was made and nothing was written.")
        return 0
    print(f"backup: {result['backup']}")
    print(f"column {COLUMN}: {'added' if result['column_added'] else 'already present'}")
    if result["flagged"]:
        print("accounts that must set a new password at next sign-in:")
        for username in result["flagged"]:
            print(f"  {username}")
    else:
        print("no account was using an old demo password")
    if result["problems"]:
        print("\nMIGRATION PROBLEMS:")
        for problem in result["problems"]:
            print("  -", problem)
        print("Restore from the backup above if needed.")
        return 1
    print("Checked: only the new column changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
