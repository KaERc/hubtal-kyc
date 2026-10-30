# hubtal-kyc

A small web workflow that replaces the form-and-spreadsheet process for **Indonesia visa-sponsorship KYC**, for both
the **EOR** and the **non-EOR** variant. It is a take-home prototype: a coherent working slice, not a finished product.
The process comes from the supplied reference form, simplified where that made it better (see
[Where I departed from the form](README.md#where-i-departed-from-the-form)).

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

1. **Answer a reviewer's question.** `seed` prints three numbered links, one per demo case (it only runs on an empty
   database; to get the links again, delete `db.sqlite3` and `media/`, run `migrate`, then `seed`). Open **link 2** (*EOR, question
   open*). At the top of the page is a box *Question from the reviewer* about a bankruptcy answer. Type a reply, click
   **Send answer**, then click **Send answers back to review**.
2. **See it as the reviewer.** Go to <http://127.0.0.1:8000/review/> and sign in. The list shows each case with its
   completeness and open requests; the case from step 1 is now *In review*. Open any case: answers that need attention are
   at the top, then every answer, documents, notes, requests and the history of status changes.
3. **See what "incomplete" looks like.** On the home page start a fresh case and leave it half-filled. The case page lists
   exactly what is missing, and **Submit** stays disabled until nothing is.

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
country or a changed question needs no migration. The cost: the database knows nothing about the answers. No column types,
no `NOT NULL`, no foreign keys, no indexes. They can still be read with JSON operators (Django's `data__applicant__full_name`
style lookups work on SQLite and PostgreSQL), but filtering or reporting across many cases is slow and awkward, and
validity is enforced only by the application (`engine.py`), never by the database. If reporting is needed later, project the
few fields that matter into columns, or move to PostgreSQL `JSONB` with indexes.

**My position.** I am a proponent of normalised schemas, and I know this one is not: a JSON column holding nested answers
breaks first normal form (the list of beneficial owners is a repeating group inside a single column), and because the
database cannot see the dependencies between the values, it cannot enforce second or third normal form either. I chose it
for this prototype knowingly, as the price of the brief's requirement that a new country or variant should not mean rebuilding
the application, and I would not carry it into production unchanged. The marker on `Case.data` and the first row of the
ledger below say where it ends. Direction for production: the entities that screening has to search and deduplicate
(applicant, candidate, beneficial owners, documents) become typed tables; only what is genuinely free-form stays JSON
(`JSONB`).

## Decisions

**One adaptive engine, two flows.** EOR and non-EOR are two flow definitions run by the same engine, not one form full
of `if`s and not two separate apps. They share nothing but the vocabulary (sections, fields, conditions, documents,
declarations), which is exactly what a Singapore flow or an "Indonesia, remote worker" variant would share too.

**Conditions are data.** `show_if` on a field or document says when it applies (`purpose == other`, "any of these four
immigration answers is yes", "certification == yes"). The server and the browser read the same description. Hidden
answers are dropped on save, so a stale "other: ..." never lingers and never counts as missing.

**The applicant needs no account.** Starting a case gives a private link with an unguessable token. Fewer steps for
the applicant, nothing to remember, and the reviewer side is the only place with passwords. The cost is that the link
is the credential; see "Before production".

**Saving is forgiving, submitting is strict.** Every section saves on its own, valid answers are kept even if another
field is wrong or empty, so nobody loses work. A malformed value (bad email, a birth date in the future) is rejected
with a message next to the field and shows what was typed. *Missing* is not an error on save; it is computed from the
flow and shown as "N missing" per section and as a list on the case page. **Submit** is blocked until nothing is missing.

**One state machine.** `workflow.py` is a table of events (`submit`, `start_review`, `request_info`, `respond`,
`approve`, `reject`) with the statuses each can start from, who may fire it, and a guard (cannot submit with gaps,
cannot approve while a question is unanswered). `fire()` is the only code that changes a status, and it writes the
history row, so the audit trail cannot drift from the status. I considered a library and chose a ~40-line table:
there is one machine, no parallel states, and a dependency would not remove any code.

**Reviewer feedback is attached to the case, not to email.** "Request information" creates a question, optionally about
one section, and moves the case to *information requested*. That unlocks editing for the applicant, who sees the
question on the case page and answers it there. Sending the case back is blocked until every question has a reply.
Notes are separate and internal.

**Red flags are visible.** A field can name the answer that needs attention (`flag_on`: "yes" to "ever bankrupt?", a
third-party transfer as the method of receiving funds). Those answers are listed at the top of the reviewer's page.
This is a pointer for a human, not a decision: nothing is auto-rejected.

**Declarations and consent are recorded as evidence.** Each statement is its own required checkbox, the signature is the
typed name, and what is stored is: the confirmations, the case's `flow_version` (which pins the exact wording, because
the wording lives in versioned code), the submission time, and the IP in the history. That is enough for a prototype;
whether it is *legally* sufficient is a question for the people who own compliance, not for this code.

**Documents are requirements of the flow.** Each flow lists the documents it needs, which may be conditional or
optional. Uploads are checked by extension, size and file signature, stored outside the web root, and served only
through views that check the case token or the reviewer login, always as downloads.

### Where I departed from the form

I treated the form as a description of today's process, not a specification.

- **Asked once, not twice.** The EOR form asks the expected start date and the work location both in the employer part and in
  the candidate part. They are asked once, in *Employee engagement*, which also took the work arrangement and the expected
  employment period from the candidate part: they describe the job, not the person.
- **Follow-up questions are conditional.** "Others: ____" became an `Other` option plus a required follow-up that appears
  only then. "Employer / business name" and "Position" in non-EOR are asked only when the source of wealth is employment or
  business ownership. "If yes, please provide details" is required only when one of the four immigration answers is yes.
- **Gaps in the form, fixed.** Years of experience offered only "< 5" and "5–10" (no 10+); I added "More than 10 years".
  Non-EOR did not ask for the passport expiry date; it does now. A visa case needs a passport copy, so it is a required
  document although the form never listed one.
- **The candidate consents for themselves.** In the EOR form only the company declares, including consent for the
  *candidate's* data. I added a short candidate consent section. This one needs legal review before anyone relies on it.
- **Dates and numbers are checked.** Birth dates must be in the past, expiry and start dates in the future, ownership is
  between 0 and 100, emails and phone numbers must look like emails and phone numbers.
- **Who fills what.** The EOR form is really two people's work. Sections carry a *To be filled in by* label (employer or
  candidate), but there is still one link per case; see "Before production".

## Adding a country or a variant

Create a module in `kyc/flows/` that exports `FLOW`. It is picked up automatically. No migration, no view, no template.

```python
# kyc/flows/singapore_ep.py  (illustrative, not in the repo)
from .spec import Doc, Field, Flow, Section, ch, with_other

FLOW = Flow(
    key='sg-ep', version='2027-01-15', country='SG', title='Singapore — Employment Pass', subject='applicant.full_name',
    sections=(
        Section('applicant', 'Applicant', (
            Field('full_name', 'Full name'),
            Field('nric_fin', 'NRIC / FIN', required=False),
            *with_other(Field('purpose', 'Purpose', 'select', options=ch('Work', ('other', 'Other')))),
        )),
    ),
    docs=(Doc('passport', 'Passport copy'),),
)
```

A mistake in a flow (an unknown subject, a condition that points at a field that does not exist, a duplicate key) raises when
the app starts instead of on an applicant's page, and the tests include "every registered flow can be completed from its own
description", so a new flow is checked for free.

**When requirements change.** Edit the flow and bump `version`. New cases get the new version, old cases keep the version
they were started under. Honest limit: the old *definition* is not archived. For production, keep the previous versions of a
flow importable (or snapshot the wording at submit) so an old case can still be shown exactly as it was agreed.

## What I intentionally did not build

Within the time box I kept to one coherent slice: both flows, applicant and reviewer, end to end.

- **Applicant sign-in, invitations, one link per party.** The EOR case has an employer part and a candidate part but one link.
- **Email or any other notification.** Neither side is told anything; they come back to their page.
- **Identity verification, sanctions and adverse-media screening, registry lookups.** Out of scope by the brief. They would
  plug in as background jobs triggered by a state change, with results shown to the reviewer as facts on the case.
- **A second country.** Shown as an example above and verified to load, not shipped.
- **Reviewer assignment, search, bulk actions, per-field comments** (requests are per section).
- **Translations, a country picker, phone normalisation.** English, free-text countries.
- **A history of *answer* changes.** Only status changes are recorded.
- **Automated browser tests.** The show/hide JavaScript was checked by hand in a browser, not by a test.
- **Deployment, CI, Docker.** It runs locally with three commands.

## Shortcuts with a known ceiling

Each shortcut carries a `ponytail:` comment in the code, one comment per row. This table is that ledger. What was left
out of scope entirely is in the previous section.

| Where | Shortcut | Ceiling | Revisit when |
|---|---|---|---|
| `kyc/models.py` `Case.data` | Answers as one JSON document | Breaks first normal form (nested lists such as owners); no types, constraints or indexes, and the dependencies between answers are invisible to the database | Screening or reporting must search across cases: normalise persons, owners and documents into typed tables, or PostgreSQL `JSONB` with indexes |
| `kyc/models.py` `Case.token` | The link is the only credential, one per case | Anyone with the link has the case; employer and candidate of an EOR case share it | Before real applicants use it: emailed, expiring links per party |
| `kyc/models.py` `Case.flow_version` | Only the version string is stored | The old flow definition and the declaration wording are not archived | Before production: snapshot answers and wording at submit |
| `kyc/models.py` `Document` | Files on local disk | Unencrypted, not virus-scanned; Django reads the whole upload before the 10 MB check | Private object storage with scanning, size limit at the proxy |
| `kyc/views.py` `start` | Public, unthrottled case creation | Anyone can create cases | On the internet: cases created by operations, or a rate limit and a captcha |
| `kyc/views.py` `client_ip` | The socket address as the client IP | Behind a proxy it is the proxy's address | Read a trusted `X-Forwarded-For` |
| `kyc/views.py` `review_list` | No pagination or search | All cases of a status are listed and progress is computed per case | The list outgrows a screen or two |
| `kyc/workflow.py` `incomplete` | Every guard recomputes the progress | A few queries per page load | Profiling shows it: cache on the case for the request |
| `kyc/workflow.py` `fire` | No notifications | Both sides learn of a change only by opening their page | Send mail or enqueue a screening job from `fire` |
| `kyc/urls.py` | No login throttling | Unlimited password guesses | `django-axes`, or a rate limit in front |
| `config/settings.py` database | SQLite | One file, one process | Deployment: PostgreSQL |
| `config/settings.py` environment | Settings read from the environment by hand | No typing or validation (`KYC_DEBUG` is on only for the string `1`) | More settings appear: `pydantic-settings` |
| `kyc/engine.py` `PHONE` | A loose phone pattern, countries as free text | Accepts numbers nobody can call; "Estonia" and "EE" are different answers | Data quality starts to matter: `phonenumbers` and a country list |
| `kyc/templates/kyc/base.html` | Stylesheet from a CDN | The first load needs internet; no integrity hash | Production: vendor the file or build the CSS, add an integrity hash |

## What I would change before production

The ledger above shows where each shortcut sits in the code. This list is the same work in the order I would do it, plus what
is not in the code at all (operations, tests, deployment).

1. **The link is the credential.** Replace it with emailed, expiring links per party (or accounts), and let operations
   create cases instead of leaving the start page public. Today anyone can start cases.
2. **Personal data.** Passport numbers, birth dates and scans need encryption at rest, private object storage with
   short-lived download links, virus scanning, and a retention and deletion policy. Check which data-protection regimes
   apply to the applicants (I did not research that here).
3. **A frozen record at submit.** Store a copy of the answers and the declaration wording when the case is submitted, so a
   later edit or a new flow version can never change what was agreed.
4. **Database and concurrency.** PostgreSQL. Saving a section already re-reads the case under a row lock (and SQLite is set to
   begin transactions immediately, so the lock holds there too), because answers are one JSON document and two people may fill
   different sections at once. `workflow.fire` locks the case too and judges the move on the current status. The locking itself
   is not covered by a concurrent test; the tests check the stale-status case, not true parallelism.
5. **Reviewer access.** Real accounts with roles, SSO or two-factor sign-in, login throttling (there is none), an access log
   for who looked at personal data.
6. **Deployment settings.** `KYC_SECRET_KEY`, `KYC_DEBUG=0` (the app refuses to start with `KYC_DEBUG=0` and the development
   key), `KYC_ALLOWED_HOSTS`, HTTPS with secure cookies, a trusted proxy
   header for the client IP (it currently reads the socket address), and an upload size limit at the proxy: Django receives
   the whole body before the 10 MB check runs.
7. **Operations.** Error tracking, structured logs without personal data, backups, CI with the tests and a browser test of
   the conditional fields.

## Tests

`uv run python manage.py test` runs the suite in a second or two. It covers the engine (conditions, validation, completeness,
red flags, "every registered flow can be completed"), the state machine (guards, who may fire what, the recorded history) and
the pages end to end over HTTP (applicant to approval, access control, locking, upload checks, file access).

## How AI was used

I built this with **Claude Code** (Anthropic's coding agent, model Claude Sonnet 5.5) and its *ponytail* skill, which pushes
towards the smallest solution that works. The agent wrote nearly all of the code, tests, templates and this README. It did
not start from a blank prompt: it works inside a setup that I maintain, and that setup shaped the result as much as the brief did.

**The context I gave it**

- A `CLAUDE.md` that I wrote for my projects folder. Among its rules: plan first and wait for my answer on large tasks;
  verify before reporting success (tests, rendered pages, link checks); mark guesses as guesses; commit in small steps and push
  only when I ask; keep personal notes out of repositories others will read; name its own mistakes and write down
  the rule that prevents them.
- Notes it keeps from earlier sessions with me, including lessons from a previous take-home: the README with run instructions
  has to exist from the first commits (I once let it sit as a stub), my branch and commit conventions (`area/topic/name` branches,
  `--no-ff` merges, English messages with attribution), and preference for minimal code. The previous take-home's repository
  was the reference for structure and conventions. That is why the history here looks as it does.

**What the agent proposed and I let stand:** the scope for the time box (a thin vertical slice, everything else listed above),
Django as the stack, and the data-driven design with one engine and a flow definition per variant.

**Where I steered or corrected it**

- I asked whether the allowed status changes should be an explicit state machine rather than a list of allowed statuses; it
  answered with an event-based table, without a library, and I did not push for one.
- The first version of the history was one large commit. I reminded it of my rule and it redid the history as small commits on
  topic branches.
- It cited a rule from another of my projects in a review finding and presented it as mine for this one; I questioned it, it
  admitted the mix-up, and the settings stayed as they are.
- Nothing is pushed until I have read it myself.

**Checks run during the build**

- Tests were written with the code. Two of them were verified by breaking the code on purpose and watching them fail (zero percent
  counted as "not answered"; the reviewer-only guard removed from the case list).
- Both flows load and every page of both renders; the applicant and reviewer paths were walked in a browser, including the
  conditional fields and the red-flag view. The commands in this README were run from a fresh clone.
- An independent code-review pass found 10 issues. Eight were fixed with regression tests (for example a huge number crashing a
  save, two reviewers acting on the same case at once, a stale list silently dropping entries). Two were left on purpose: the
  progress being recomputed in several guards, and reading three settings from the environment by hand.
- A claim in this README that turned out wrong when re-read against the form (which questions the EOR form asks twice) was
  corrected, and the "drop in a new flow" claim was tested with a throwaway Singapore module.
