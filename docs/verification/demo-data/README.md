# Task 8 — fictional demo data

`seed_demo_data.py --replace` built the working database on this laptop. The old
`app.db` was archived and verified first (`archive_plain_databases.py`), then moved
aside as `previous-app.db`, and deleted once the new database ran.

## What was built (counts only)

patients 150, visits 394, sealed visits 4, immunizations 299, dispensing issues 346,
inventory items 15, broadcasts 10, audit entries 2835. The Service Schedule is empty.

## Page check

Every page in each role's menu, every report over the default range, the last 30 days
and the last 364 days, every report export, and a sample of patient profiles and print
views. Run through Flask's test client against a copy of `app.db`, so the first-sign-in
password rule did not need to be cleared on the real file.

| Role | Pages loaded | Redirected (not that role's page) | Errors |
|---|---|---|---|
| Administrator | 79 | 1 | 0 |
| Barangay Official | 24 | 1 | 0 |
| Doctor | 73 | 1 | 0 |
| Health Center Staff | 64 | 10 | 0 |

The app also started on the real `app.db` and served the sign-in page.
