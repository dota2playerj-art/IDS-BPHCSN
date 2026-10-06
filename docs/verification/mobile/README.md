# Phone-layout screenshots (Task 17)

`tests/verify_mobile_layout.py` saves one screenshot of every page it checks into this folder,
in a subfolder per role (`admin`, `doctor`, `staff1`, `official`, `signed-out`): every menu
page, a patient profile (every tab), the consultation forms, an inventory item, and each dialog,
at 360, 390 and 1366 pixels wide. The file name ends with the width, for example
`patient-records-390.png`. Each run deletes the old pictures and writes new ones.

The pictures are **not in version control**, for the reason in `../README.md`: they show the
fictional demo database, but the same screens in real use are patient records. Only this file
is tracked.

To make them again: `pip install -r requirements-dev.txt`, `python -m playwright install chromium`,
then `python tests/run_all.py mobile` (about 12 minutes; it builds the demo database first).
