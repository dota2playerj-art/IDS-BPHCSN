# add-user

Evidence folder for Add User — account creation, the last-Administrator guard,
and the Deactivate / Reactivate controls on User Management.

It is empty of images on purpose, and for a stronger reason than the folders
above it. This feature's whole subject is credentials: a screenshot of it would
show a roster of every account that can sign in to a database of patient
records, next to a form with a password in it. The run was driven against a
throwaway copy of `app.db` so that creating accounts, revoking them and signing
in as them left no test residue in the real patient database — and the copy it
ran against no longer exists.

The real `app.db` was confirmed byte-identical to
`app.db.PRETASK_BACKUP_add-user_20260902_182924` after the pass, by SHA-256 of
the whole file, and still holds exactly the three seeded accounts and zero
`User Management` audit rows.

What that pass covered, and how to reproduce it, is in the `add-user/` section
of `../README.md`.
