# appointment-sms

Evidence folder for the individual appointment SMS confirmation.

It is empty of images on purpose. The browser pass for this feature was driven
against a throwaway copy of `app.db` rather than the real one, so that
click-testing a feature which writes messages and audit entries left no test
residue in the patient database — and the copy it ran against no longer exists.

What that pass covered, and how to reproduce it, is in the `appointment-sms/`
section of `../README.md`.
