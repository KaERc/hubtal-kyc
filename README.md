# hubtal-kyc

A small web workflow that replaces the form-and-spreadsheet process for **Indonesia visa-sponsorship KYC**, for both
the **EOR** and the **non-EOR** variant. It is a take-home prototype: a coherent working slice, not a finished product.
The process comes from the supplied reference form, simplified where that made it better (see
[Where I departed from the form](#where-i-departed-from-the-form)).

## Quick start

Prerequisite: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and Django for you). No other services.

```bash
uv run python manage.py migrate
uv run python manage.py seed          # demo reviewer account + three demo cases (prints the login and the case links)
uv run python manage.py runserver
```

- Applicant side: <http://127.0.0.1:8000/> — pick a flow, fill in the sections, upload documents, submit.
- Reviewer side: <http://127.0.0.1:8000/review/> — sign in with the demo account that `seed` prints
  (username `reviewer`; the password is printed too. Demo only, set `KYC_DEMO_PASSWORD` to change it).
- Tests: `uv run python manage.py test`

State is a local SQLite file (`db.sqlite3`) and uploaded files in `media/`; both are git-ignored.
Delete them and run `migrate` again to reset. The page styling loads Pico CSS from a CDN, so the first load needs internet.

### A two-minute tour

1. Open the link `seed` printed for the *EOR, waiting for your answer* case: the reviewer asked a question about one
   section. Answer it, then **Send answers back to review**.
2. Sign in as the reviewer: the case list shows completeness and open requests. Open a case: red-flag answers are
   at the top, then every answer, documents, notes, requests and the history of status changes.
3. Start a fresh case on the home page, leave it half-filled and look at the case page: it says exactly what is missing,
   and **Submit** stays disabled until nothing is.

## Architecture

One generic engine, driven by flow definitions that are plain data.

```
kyc/flows/spec.py          vocabulary: Flow, Section, Field, Doc (dataclasses)
kyc/flows/indonesia_*.py   the two flows: questions, options, conditions, declarations. No logic.
kyc/engine.py              reads a Flow: which fields are visible, validation, completeness, the reviewer's view
kyc/workflow.py            the case state machine: the only place a status changes
kyc/models.py              Case (answers as JSON), Document, InfoRequest, ReviewNote, CaseEvent
kyc/views.py, templates/   server-rendered Django pages; a few lines of JavaScript only to show/hide conditional fields
kyc/demo.py, seed          sample answers generated from the flow definitions themselves
```

Nothing outside `kyc/flows/` knows about Indonesia, EOR or any particular question. The templates draw whatever
a section describes; the engine judges completeness from the same description.

### Data model

| Model | What it holds |
|---|---|
| `Case` | `flow_key`, `flow_version`, `status`, a private `token` (the applicant's link), `data` (answers as JSON: `{section: {field: value}}`, a list of those for repeated sections such as beneficial owners), `submitted_at` |
| `Document` | an uploaded file attached to a case under a `Doc.key` from the flow |
| `InfoRequest` | a reviewer's question, optionally about one section, with the applicant's reply and when it was answered |
| `ReviewNote` | an internal note; never shown to the applicant |
| `CaseEvent` | history: event, from → to status, who, when, IP. Written only by the state machine |

**Why answers are JSON.** The shape of the answers belongs to the flow definition, not to the database schema. A new
country or a changed question needs no migration. The cost is that answers cannot be queried or constrained in SQL;
if reporting is needed later, project the few fields that matter into columns, or move to Postgres `JSONB` with indexes.
