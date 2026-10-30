# hubtal-kyc

A small web workflow for Indonesia visa-sponsorship KYC cases, covering both the **EOR** and the **non-EOR** variant.
Built as a take-home prototype; the process comes from the supplied reference form, simplified where it made sense.

## Quick start

Prerequisite: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and Django for you).

```bash
uv run python manage.py migrate
uv run python manage.py seed          # demo reviewer account + two demo cases (prints the links and the login)
uv run python manage.py runserver
```

- Applicant side: <http://127.0.0.1:8000/> — pick a flow, fill in the sections, upload documents, submit.
- Reviewer side: <http://127.0.0.1:8000/review/> — sign in with the demo account that `seed` prints.
- Tests: `uv run python manage.py test`

State is a local SQLite file (`db.sqlite3`) and uploaded files in `media/`; both are git-ignored.
Delete them and run `migrate` again to reset.

## Status

Work in progress; this README grows with the code. Sections still to come: architecture and data model, decisions,
what I did not build, what to change before production, how AI was used.
