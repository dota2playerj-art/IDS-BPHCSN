# IDS-BPHCSN

Integrated Digital System for Barangay Poblacion Health Center Services and
Community Notifications. A Flask 3.1 application (SQLite, Bootstrap 5.3, vanilla JavaScript)
covering patient records, medicine inventory, a daily patient queue and consultations,
immunisation tracking, SMS broadcasts, reporting, and role-scoped dashboards for four
roles: the Administrator, the Doctor, Health Center Staff and the Barangay Official.

## What each role sees

- **Health Center Staff** check patients in (choosing the service), take the intake, dispense
  medicine and record vaccinations.
- **The Doctor** writes the diagnosis and treatment plan, can seal a consultation, declares a death,
  and has a list of visits **Waiting for the Doctor**.
- **The Administrator** (a Kagawad) manages accounts, settings, the Service Schedule, SMS
  broadcasts, inventory and reports. Patient data is demographics and counts only. The Patient Queue
  is read-only.
- **The Barangay Official** sees community reports and SMS broadcasts, and no patient records.

Clinical data is for the care team only (the Doctor and Health Center Staff). Ranking rows with
fewer than 5 are folded into "Other" for the Administrator and the Official, and phone numbers are
masked on the screens that show them to roles outside the care team.

## The visit flow

A patient is checked in with a service chosen from a fixed list, then **Waiting**, **In Consultation**,
and then **Waiting for the Doctor** (the intake is saved and the service needs a diagnosis) or
**Completed** (immunization, prenatal and dental visits are finished by Staff). The Doctor's diagnosis
completes a visit. A patient who goes home is marked **Left before being seen**, and it can be undone the
same day. The flow is described in `PR0MPT_INSTRUCTION/01_PROJECT_BIBLE.md`.

## Getting started

Do these steps in order, once on each computer. Run them from the project folder.

1. Create and activate a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Install the packages. This is the only step that needs internet, and only once:
   ```
   pip install -r requirements.txt
   ```
3. Create the secret keys. This makes a `.env` file. The app will not start without it, and
   it must never be committed:
   ```
   python setup_env.py
   ```
4. Archive any old plain database. It is safe to run when there is nothing to archive:
   ```
   python archive_plain_databases.py
   ```
5. Build the demo database. It prints the five account passwords **once**, on the screen.
   Write them down:
   ```
   python seed_demo_data.py
   ```
6. Start the app:
   ```
   python app.py
   ```
7. Open <http://127.0.0.1:5001>, sign in, and set a new password. Each account must do this
   the first time it signs in.

If port 5001 is already in use, another copy of the app is running. Close it first.

After 5 wrong passwords in a row for one username, sign-in is closed to that username for 5 minutes.

## Using the system from other devices

By default the system works on this computer only. To use it from other computers and phones on
the same Wi-Fi (always over HTTPS):

1. Run `python setup_https.py` once. It makes the certificate and prints the addresses to open.
2. In `.env`, set `IDS_NETWORK=1` (keep `IDS_DEBUG=0`), then start the app with `python app.py`.
3. When Windows Firewall asks, allow Python on **Private networks only**. Never allow Public networks.
4. Install `instance/certs/ids-bphcsn.crt` on each device (the script prints the steps). Never copy the key file.
5. On each device, open the printed address, for example `https://192.168.1.10:5001`.

If this computer's address changes, run `python setup_https.py --replace` and install the new `.crt` again.
Settings shows which mode is on.

The app runs entirely offline: Bootstrap, Chart.js and the Inter/Material fonts are vendored
under `static/`, so no CDN is reached at any point. There is no jQuery; the scripts are plain
JavaScript.

`python setup_env.py` is a one-time step on each computer. It creates `.env` with a new secret
key and a key for sealed records, or adds what is missing.

SMS runs in one of two modes, shown in Settings and on SMS Notifications. Without a
`SEMAPHORE_API_KEY` in `.env`, messages are saved but not sent ("Simulated"). With the key set, and the
app restarted, they are sent through Semaphore ("Live").

If you start the app with no `app.db` at all (skipping step 5), it makes an empty database with
four accounts (`admin`, `staff`, `official`, `doctor`) and random passwords, shown once in the
terminal. To get demo data after that, run `python seed_demo_data.py --replace`.

## Running the tests

```
python tests/run_all.py            # every suite (about 5 minutes)
python tests/run_all.py --quick    # skips the slow demo-data suite (about 3 minutes)
```

Use `--quick` while you work, and run the full suite before you push.

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
`python migrations/migrate_seal_free_text_fields.py`. It makes a backup first and is safe to run twice.

## The database

`app.db` is **not** in version control. It is generated, and everything needed to
rebuild it is tracked:

```
python seed_demo_data.py   # builds app.db with fictional demo data (see below)
```

If the schema changes after a database already exists, the scripts in `migrations/` bring it
up to date. Each one is idempotent — safe to re-run — and each verifies afterwards that no existing
row moved. A new laptop does not need them: it builds the demo database instead.

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
exists, the script stops and tells you to run `python seed_demo_data.py --replace`, which
archives the old one first (see below) and builds a new one. `--path` builds somewhere else.

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
migrations/             idempotent schema migrations, each self-verifying (see its README)
seed_demo_data.py       builds the fictional demo database
archive_plain_databases.py   encrypts old plain databases, verifies, removes
setup_env.py            creates .env with the secret keys
setup_https.py          creates the HTTPS certificate for network mode
restore_backup.py       opens an encrypted .idsbackup file
export_sealed_key.py    prints the sealed-records key for the Doctor's envelope
tests/                  the test suites; run python tests/run_all.py
docs/verification/      a note for each task and the final audit
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
