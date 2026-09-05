# general-vaccination-infant-list

Evidence folder for the age-aware trim of the **Other Vaccinations Given**
section on Record / Edit Consultation: the section stays visible at every age,
and for a patient under one it now prints only the vaccines that age can
actually be given.

It keeps **no images**, for the reason the folders above it give — every screen
involved is a Record Consultation form carrying a named infant's chief
complaint, vitals and vaccination history.

The read-only half of the pass ran against the real `app.db` (GETs only, no
writes). Every save was made against a throwaway copy served through a test
client pointed at `scratch_test.db`; the real database was left holding the same
5 `general_vaccinations` rows and 28 consultations it held before the pass, and
`app.db.PRETASK_BACKUP_infant-vaccine-list_20260905_174050` is the recovery
point.

What the pass covered, and how to reproduce it, is in the
`general-vaccination-infant-list/` section of `../README.md`.
