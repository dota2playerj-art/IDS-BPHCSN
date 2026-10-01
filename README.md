# IDS-BPHCSN

Integrated Database System for Barangay Poblacion Health Center Services and
Notifications. A Flask application covering patient records, medicine inventory,
a daily patient queue and consultations, immunisation tracking, SMS broadcasts,
reporting, and role-scoped dashboards for the Administrator, Health Center Staff
and Barangay Official.

## Running it

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python setup_env.py
python app.py
```

`python setup_env.py` is a one-time step on each computer. It creates `.env`
with a new secret key and a key for sealed records, or adds what is missing. The
app will not start without them. Never commit `.env`.

The app serves on <http://127.0.0.1:5001>. It runs entirely offline: Bootstrap,
Chart.js and the Inter/Material fonts are vendored under `static/`, so no CDN is
reached at any point.

On a new install, the first run creates four accounts (`admin`, `staff`,
`official`, `doctor`) with random passwords. It shows them once, in the
terminal. Write them down then; they are not shown again. Each person must set
their own password the first time they sign in.

## Running the tests

```
python tests/run_all.py
```

Each suite runs on its own fresh test database in the system temp folder, and
never on `app.db`. The runner prints one line per suite and a total, and exits
with 0 only when every check passes. See `PROJECT_STATUS.md` for current results.

## Sealed records and the encryption key

The Doctor can seal (Restrict) a consultation. Everything written on that visit (the chief
complaint, diagnosis, treatment plan, additional notes, and the reason given at check-in) is
then stored encrypted with `SEALED_DATA_KEY`, a key in `.env`. Each installation has its own key,
made by `python setup_env.py`. Run `python export_sealed_key.py` once, write the key on
paper, seal it in an envelope and give it to the Doctor. Without it, sealed records cannot
be recovered if the computer fails. A backup opens sealed records only on a computer with
the same key. Because the key lives in `.env` on the health-center PC, turn on full-disk
encryption (BitLocker) on that PC.

**Restoring a backup.** The backup you download from Settings is one encrypted file
(`.idsbackup`). It opens only with this system's key, which is in `.env` and in the
Doctor's envelope. At the health-center PC, run `python restore_backup.py <file>`. It
decrypts the file into a new database in `IDS-BPHCSN-backups` and checks it; `app.db` is
not touched. Add `--replace` to put it in place: it copies the current `app.db` aside
first, and then you restart the app.

After pulling an update that adds a migration, run it once on each laptop, for example
`python migrate_seal_free_text_fields.py`. It makes a backup first and is safe to run twice.

## The database

`app.db` is **not** in version control. It is generated, and everything needed to
rebuild it is tracked:

```
python seed_demo_data.py   # builds app.db with fictional demo data (see below)
python app.py              # starts the app
```

If the schema changes after a database already exists, the `migrate_*.py`
scripts in the project root bring it up to date. Each one is idempotent — safe to
re-run — and each verifies afterwards that no existing row moved.

Because `app.db` is untracked, **a fresh clone starts with no data.** If the
current demo dataset matters to you, copy `app.db` across by hand or restore it
from a backup. Regenerating the demo data gives the same people and records on every
laptop (see "Demo data").

## Demo data

`python seed_demo_data.py` builds a new `app.db` from `schema.sql` and fills it with
**fictional** data: about 150 patients and about 400 visits over the past 12 months.
Every name, address and phone number is invented, and phone numbers all look like
`0900000NNNN`. It is deterministic: the same people and visits on every laptop, dated
relative to the day you run it. It writes through the app's own routes, as each role
(Staff intake, Doctor diagnosis, sealing), so the rules, encryption and audit entries
are the real ones. The Service Schedule is left empty on purpose.

It prints the five account passwords **once**, in a block on the screen. Write them
down. Each account must change its password at first sign-in. If `app.db` already
exists, the script stops; add `--replace` to archive the old one first (see below)
and build a new one. `--path` builds somewhere else.

## Archiving old databases

Older databases and backups may hold real people's records as plain files. Run
`python archive_plain_databases.py` **once on each laptop**. It finds `app.db` and
every plain file in `IDS-BPHCSN-backups`, encrypts each into an
`archive-<name>-<time>.idsbackup` file (the same format as the Backup download,
opened with `restore_backup.py`), decrypts it again and compares every table, and only
then removes the plain file. A file that does not match is kept and reported. `app.db`
is moved aside as `previous-app.db` until the new demo database works; then run
`python archive_plain_databases.py --remove-previous`. It prints counts only, and it
is safe to run twice.

## Version control

The project is under git, with an established history running from the initial
commit (`Initial commit: IDS-BPHCSN capstone project, all four core objectives
complete`) through the feature and audit-fix work that followed. `git log
--oneline` shows it. Nothing needs initialising — just commit as you go.

The everyday loop is:

```
git status                      # what changed
git add <files>                 # or: git add .   to stage everything
git commit -m "Short description of the change"
```

Commit in small, related batches with a message that says what changed and why,
rather than one large commit at the end of a session.

`.gitignore` keeps `app.db`, `.venv/`, `__pycache__/`, `.claude/` and editor and
OS clutter out of the repository. Everything else — application code, templates,
`schema.sql`, every migration, the vendored `static/` assets and the governance
documents in `PR0MPT_INSTRUCTION/` — is tracked on purpose.

## Layout

```
app.py                  application factory and entry point
config.py               paths and SECRET_KEY
schema.sql              full schema for a fresh database
migrate_*.py            idempotent schema migrations, each self-verifying
seed_demo_data.py       builds the fictional demo database
archive_plain_databases.py   encrypts old plain databases, verifies, removes
routes/                 blueprints, one per role surface, plus shared context builders
models/                 all data access; each figure has exactly one owner here
utils/                  dates, roles, security, SMS, phone formatting, endpoint shim
database/               connection handling and first-run bootstrap
templates/              Jinja templates; base.html holds the shared shell
static/                 vendored CSS, JS and fonts
PR0MPT_INSTRUCTION/     project bible, screen specifications, roadmap
```

A note on how the code is meant to be read: figures are owned in one place and
never re-derived on a screen, and anything a screen cannot show honestly says so
rather than displaying an invented number. The `UNTRACKED` dictionaries in
`routes/report_views.py` and `routes/official_views.py` are where those
explanations live.
