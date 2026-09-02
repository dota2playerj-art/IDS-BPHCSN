# form-redisplay

Evidence folder for the validation-redisplay audit: the Add User dialog's
failure to reopen on a rejected submit, the same defect found in three other
dialogs, and a form-by-form check of every server-side validation path in the
project.

It keeps **no images**, for the reason the `add-user/` folder above it gives —
the screens involved carry an account roster, a password form and patient
records. One screenshot was captured during the run to confirm the repaired Add
User dialog by eye and was deliberately not retained.

The whole pass ran against throwaway copies of `app.db`, and the live browser
run was driven against a scratch copy served on a separate port. The real
database was confirmed unchanged by SHA-256 over the whole file, before and
after: `app.db.PRETASK_BACKUP_form-redisplay_20260902_232151`.

What that pass covered, and how to reproduce it, is in the `form-redisplay/`
section of `../README.md`.
