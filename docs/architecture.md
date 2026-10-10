# Architecture

Four parts, all on your machine: a Chrome extension that captures postings, a local Flask server
that keeps the tracker and calls Claude, a deterministic resume engine, and Claude Code skills
for the conversational work. One rule runs through all of it: **the model writes words and
makes judgment calls; code does everything that can be checked**, and nothing is sent or
submitted without your click.

```
 Chrome                       Local server (127.0.0.1:8790)                  Claude Code
 ┌──────────────┐  JSON   ┌──────────────────────────────────┐  claude -p  ┌──────────────┐
 │ extension/   │ ──────► │ server/app.py   tracker, prompts │ ──────────► │ model calls  │
 │ side panel   │ ◄────── │ dashboard.html  the dashboard    │ ◄────────── │ (no tools)   │
 └──────────────┘         │ engine/         render and fit   │             └──────────────┘
                          │ plugins/sponsorship  (optional)  │
                          │ outreach.py  ──► Apify (optional)│
                          │ mailer.py    ──► SMTP/IMAP (opt.)│
                          └──────────────────────────────────┘
                              reads profile/  writes data/
```

## Components

**`extension/`** (Manifest V3). Content scripts read the posting on LinkedIn, Greenhouse, Lever,
Ashby, Workday or a generic page; the side panel shows what was captured, the evaluation, the
questions, the built documents (with a drag handle for uploading the PDF), and the job's
stage. It talks only to the server address set in its settings (default
`http://127.0.0.1:8790`). Tests are in `extension/test/`.

**`server/`**:
- `app.py`: the Flask app. Job capture and dedupe, the pre-screen (deterministic blockers read
  from the posting), evaluation, the build and cover letter pipelines, revisions, stages, the
  dashboard API, the outreach pipeline, the send queue, the inbox watch, interview handoff notes,
  alerts. State is a SQLite database in the data folder. Every Claude call is a `claude -p`
  subprocess, almost always with tools turned off and everything the model needs pasted inline.
- `userprofile.py`: the one place anything personal is read from. Everything about you comes
  from the profile directory through it.
- `outreach.py`, `outreach_validate.py`: people search and email lookup through Apify, ranking,
  drafting, audit and fact-check prompts, and the deterministic checks on drafts.
- `mailer.py`: SMTP sending of approved messages and read-only IMAP reading.
- `inbox.py`: sorting received mail into rejections, interviews, replies and so on.
- `handoff.py`: the interview handoff note.
- `dashboard.html`: the dashboard, served at `/`.
- `tools/`: redraft, rescore and fact-check scripts for drafts waiting for review.
- `devserver.py`: a throwaway copy of the server on port 8791, against a copy of the database
  with sample outreach data, Auto off and no paid calls or email, for trying dashboard changes.

**`engine/`**: the resume and cover letter generator. No model inside.
- `engine.py`: `render` (content to `.docx` through `template.docx`), `convert` (LibreOffice to
  PDF), `measure` (every line's width from the PDF), `fit` (moves only layout spacing until the
  page is one page and 92 to 98 percent full), `check` (em dashes, banned phrases, role order,
  repeated content, every number traced to your profile, answers or base version).
- `build.py`: the XML helpers. `base_render.py`: render a base version as is.
  `make_cover_letter.py`: the cover letter. `measure.py`, `deficit.py`: line-fill reports.

**`plugins/sponsorship/`**: the optional LCA lookup (`lca_lookup.py`), the expected data format
(`lca-schema.md`), and employers' published exceptions (`sponsorship-policies.yaml`).

**`.claude/skills/`**: `onboard`, `skill-builder`, `learn`, `evaluate-jd`, `resume-build`,
`cover-letter-build`, `apply`. The server pastes the relevant skill text into its prompts, so
the same method governs a build in Claude Code and a build from the side panel.

**`scripts/privacy_scan.py`**: the pre-commit check for secrets and personal identifiers.

## The profile files

All in `profile/` (or `$JDI_PROFILE_DIR`), written by `/onboard`. `examples/profile/` holds an
invented person in exactly this format.

| File | What it holds | Read by |
|---|---|---|
| `profile.yaml` | Identity and contact line, standing facts, degrees, schools, employer order, targets and level, work authorization and hard blockers, confirmed tools, resume and cover letter settings, feature switches, outreach settings, models | everything |
| `profile.md` | Every claim a resume, letter or email may make. The only source of numbers | evaluate, build, cover letter, outreach, fact-checks |
| `base_versions.yaml` | The base resumes (keys are your own names), each with `signals` that suggest it | evaluate, build, engine |
| `cover_kb.yaml` | Cover letter sections and variants with ids | evaluate, cover letter |
| `voice.md` | How you write: register, rules, banned phrases | cover letter, outreach |
| `voice-examples.md` | Real emails you wrote | outreach drafter and audit |
| `application-answers.md` | Common form answers | apply |
| `learnings.md` | Rules from your own edits, newest first | every prompt and skill, first |
| `approaches.yaml` (optional) | Ways to approach a resume by job type | build |
| `skills/<skill>.md` | Your addenda to each skill, from `skill-builder` | the matching skill |
| `.onboard-progress.md` | Where onboarding got to | onboard |

Changes to `profile.yaml` take effect without a restart.

## The data folder

`data/` (or `$JDI_DATA_DIR`):

| Path | What |
|---|---|
| `jobhunt.db` | SQLite: jobs, settings, action log, people, messages, inbox rows, API call costs |
| `applications/<yyyy-mm>-<company>-<title>/` | One folder per job: `JD.md`, `EVALUATION.md`, `ANSWERS.md`, the `.docx` and `.pdf`, `page-1.jpg`, `NOTES.md`, the cover letter, `HANDOFF.md`, and `_build/` (the engine files and the content and layout JSON for that build) |
| `learning-inbox.jsonl` | Learnable events, appended by the server |
| `learning-inbox.processed` | Keys of events `/learn` has processed |
| `onboard/` | Renders made during onboarding |

## A job's life

1. **Capture** (`POST /jobs`): the extension sends the posting; the server dedupes it, makes the
   folder and `JD.md`, runs the pre-screen and, with sponsorship on, the LCA lookup.
2. **Evaluate**: code settles what it can (blockers, level, confirmed tools, a first guess at the
   base version), then one model call scores the fit and returns the brief, up to three questions
   and the cover letter combination. With Auto on, a clean capture is evaluated at once and a job
   above your threshold goes straight to questions or a build.
3. **Questions**: you answer in the side panel; answers go to `ANSWERS.md`, and any you mark
   "remember" go to your profile.
4. **Build**: one model call writes the edits to the base version; the engine merges, renders,
   fits and checks; at most two short fix rounds for lines that will not fit; a build that repeats
   itself is blocked rather than delivered.
5. **Cover letter** (if asked): one model call, a word and phrase check, render, one-page check.
6. **Submitted**: you upload and submit yourself, then mark it; the Desktop copies are removed.
7. **After**: stages, outreach, inbox tracking and the handoff note.
