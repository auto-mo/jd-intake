# Local API

The server is a Flask app at `http://127.0.0.1:8790` (`JDI_PORT`). Single user, no login. Its
clients are the Chrome extension, the dashboard at `/`, and local tools such as `curl`. Bodies
and responses are JSON; timestamps are ISO 8601 local time.

## Who may call it

Every route, reads included, answers only when the Host is `127.0.0.1` or `localhost` and the
Origin is absent (curl, scripts), the server's own (`http://<Host>`), or `chrome-extension://`.
Anything else gets `403 {"error": "not from the dashboard or the extension"}`. This stops a web
page open in your browser from reading your jobs or spending money through the server, including
by DNS rebinding. `Access-Control-Allow-Origin` is sent only to a `chrome-extension://` origin,
never `*`. With `JDI_EXTENSION_ID` set, only that extension id is accepted.

## Optional features

A route that belongs to an optional feature that is off returns
`400 {"error": "<Feature> is off. Turn on features.<key> in profile/profile.yaml and finish its setup (docs/<key>.md).", "needs": "feature:<key>"}`.
Missing secrets for a feature that is on are reported by name (never value) in
`GET /api/profile/status`.

## The job object

```json
{
  "id": "2026-01-northbridge-operations-analyst",     // slug, also the application folder name
  "url": "https://www.example.com/jobs/123",
  "source": "linkedin | greenhouse | lever | ashby | workday | generic | manual",
  "job_key": "linkedin:123",                           // dedupe key (site:id) or "url:<sha1-12>"
  "title": "Operations Analyst", "company": "Northbridge Logistics", "location": "Chicago, IL",
  "text_chars": 6120, "text_head": "first 300 characters of the capture",
  "capture_quality": "ok | short | empty",             // short = under 800 characters
  "captured_at": "2026-01-12T21:30:00",
  "status": "captured | evaluating | scored | questions | queued | building | built | built_external | applied | skipped | error | needs_login",
  "stage": null,                                        // after applied: heard_back | assessment | interviewing | offer | paused | rejected | withdrawn
  "folder": "<data>/applications/<id>",
  "prescreen": [ { "kind": "clearance", "hard": true, "label": "Requires clearance", "evidence": "..." } ],
  "lca": null,                                          // sponsorship feature only: the employer's filings, or null
  "duplicate_of": null,                                 // { id, status, captured_at } when seen before
  "evaluation": null,                                   // see Evaluation
  "questions": [                                        // build questions waiting for answers
    { "id": "snowflake", "question": "Have you used Snowflake?", "why": "The JD names it three times",
      "type": "yes_no | choice | text", "options": ["Yes, hands on", "No"], "affects": "the Tools line" }
  ],
  "messages": [ { "role": "user | assistant", "text": "...", "at": "..." } ],   // the Ask thread
  "desktop_files": [],                                  // copies in JDI_DROP_DIR, removed on submitted
  "build": null,                                        // { mode, docx, pdf, jpg, pages, verdict, fill_pct, claims_to_verify, changes, tools_omitted, cost_usd, ... }
  "cover": null,                                        // { docx, pdf, pages, words, combo_used, firm_specific_claim, ... }
  "error": null
}
```

The evaluation carries `fit_score` (0 to 100), `recommendation` (`TAILOR | BASE | SKIP`),
`resume_version` (a key from your `base_versions.yaml`), `sponsorship`, `strengths`, `gaps`,
`keyword_gaps`, `cover_letter_combo`, `cover_letter_format`, `honest_take`, `sponsorship_flag`
(`explicit_no | explicit_yes | silent`), `level_fit` (`at_level | stretch | under`), `blockers`,
`build_questions`, `approach`, `pre` (what code settled before the model ran), `brief` (the
assembled text) and `cost_usd`.

## Capture, evaluate, build

| Method | Path | Body | What it does |
|---|---|---|---|
| GET | `/health` | | `{ok, claude: "ready" or "missing" or "not_logged_in", version}` |
| GET | `/api/profile/status` | | Whether onboarding has run, your name, which features are on, the `.env` keys each one still needs, the send window, your base versions |
| POST | `/jobs` | `{url, title, company, location, text, source, page_title}` | Creates the job: slug, folder, `JD.md`, pre-screen, LCA lookup (sponsorship on), dedupe. A repeat returns the existing job with `duplicate_of`. With Auto on, a clean capture is evaluated at once |
| GET | `/jobs` | | Recent jobs, newest first |
| GET | `/jobs/<id>` | | One job |
| POST | `/jobs/manual` | `{company, title, url?, applied_at?, stage?, note?, company_url?}` | A job you applied to outside the tracker |
| POST | `/jobs/<id>/evaluate` | | Runs the evaluation in the background: `evaluating`, then `scored` (or `error`, `needs_login`). With Auto on and a score at or above the threshold, it moves on to questions or a build |
| POST | `/jobs/<id>/approve` | `{cover_letter: bool}` | Starts the build, or returns the job at `questions` if build questions are unanswered |
| POST | `/jobs/<id>/answer` | `{answers: [{id, choice, note?, remember?}], note?}` | Writes `ANSWERS.md`, adds `remember` answers to `profile.md`, then builds (or revises a built job) |
| POST | `/jobs/<id>/ask` | `{text}` | A free-text question about the job; the answer is appended to `messages` |
| POST | `/jobs/<id>/message` | `{role?, text, status?}` | Appends to the job's thread (for local tools) |
| POST | `/jobs/<id>/cover` | `{instructions?}` | Writes the cover letter for a built job |
| POST | `/jobs/<id>/revise` | `{doc: "resume" or "cover", feedback}` | Revises a built document from your feedback, then fits and checks it again |
| POST | `/jobs/<id>/skip` | | Status `skipped`; removes the drop-folder copies |
| POST | `/jobs/<id>/submitted` | | Status `applied`, records `applied_at`, removes the drop-folder copies |
| POST | `/jobs/<id>/built_external` | `{folder}` | You built the documents elsewhere; points the job at that folder |
| POST | `/jobs/<id>/open` | `{what?: "resume", "cover" or "documents"}` | Opens the folder or a PDF on the server's machine |
| GET | `/jobs/<id>/thumb?doc=resume` or `cover` | | The first page as JPEG |
| GET | `/jobs/<id>/file?doc=resume` or `cover` | | The PDF itself (the side panel's drag handle) |
| GET | `/search?q=` | | Ids of jobs whose title, company, location or full posting contain every word |
| GET | `/stats` | | Typical durations from your own history |
| GET | `/actions?job=<id>` | | The action log, newest first |
| GET | `/api/busy` | | What a restart would interrupt right now (empty when safe) |
| GET, POST | `/settings` | `{auto?, threshold?, auto_apply?, build_model?, outreach_auto?, outreach_paused?, people_auto?}` | Read or change settings |

## Tracking

| Method | Path | Body | What it does |
|---|---|---|---|
| GET | `/` | | The dashboard |
| GET | `/api/overview` | | Every job with its stage, outreach state, inbox summary and handoff link; counts; settings |
| POST | `/jobs/<id>/stage` | `{stage, note?}` | `applied`, `heard_back`, `assessment`, `interviewing`, `offer`, `paused`, `rejected` or `withdrawn`, kept with its date and note |
| POST | `/jobs/<id>/company_url` | `{url}` | The company's LinkedIn page, reused for later jobs at the same company |
| POST | `/jobs/<id>/company_website` | `{url}` | The company's website |
| POST | `/api/careers_url` | `{job_key, url}` | The employer's own posting address, recorded by the extension when you click Apply |
| POST | `/api/backfill_companies` | | Fills missing company links for applied jobs in the background |
| GET | `/notifications` | | Counts for the badge: people to review, emails to approve, LinkedIn notes to send, failures, inbox items that need you, next send time |
| GET | `/api/jobs/<id>/handoff` | | The interview handoff note as plain text (404 when there is none) |
| POST | `/api/jobs/<id>/handoff` | | Writes the handoff note now (submitted jobs only) |

A generated handoff note starts with `<!-- generated by jd-intake; edits are overwritten -->`.
A `HANDOFF.md` without that line is yours and is never touched; the generated note then goes to
`HANDOFF.generated.md`.

## Outreach (feature `outreach`)

| Method | Path | Body | What it does |
|---|---|---|---|
| POST | `/api/jobs/<id>/outreach` | `{search_size 5..50, keep 1..10, again?}` | Applied jobs only. Starts the people search (paid). `400 needs: company_url` or `needs: apify_token`; `409 needs: again` when people were already found |
| GET | `/api/jobs/<id>/outreach` | | One job's people and messages for the review panel |
| POST | `/api/jobs/<id>/outreach/resume` | | Retries drafting for approved people, with no new search |
| POST | `/jobs/<id>/outreach_decision` | `{decision: "pass"}` | You do not want outreach for this job |
| GET | `/api/jobs/<id>/people` | | People for a job, ranked, with `why` and their messages |
| POST | `/api/jobs/<id>/people/approve_all` | | Approves everyone still proposed, then drafts once |
| POST | `/api/people/<id>/decide` | `{decision: "approve" or "reject"}` | When nobody is left undecided, email lookup and drafting start for the approved |
| POST | `/api/people/manual` | `{name, linkedin_url, title?, headline?, location?, company?, company_url?, about?, raw?}` | Saves a person you captured from their LinkedIn profile as a contact. Nothing paid runs, nothing is drafted |
| GET | `/api/people/<id>` | | One person, their job and messages, and whether work is in progress |
| POST | `/api/people/<id>/refresh` | same as manual | Re-reads a captured person from their open profile |
| POST | `/api/people/<id>/attach` | `{job_id}` | Adds a contact to an open application |
| POST | `/api/people/<id>/draft` | | Drafts for one person, on your click |
| POST | `/api/people/<id>/find_email` | `{again?}` | One paid email lookup for one person, on your click |
| POST | `/api/people/<id>/forget` | | Removes a contact with no job and no messages |
| GET | `/api/queue` | | Drafts to review, LinkedIn notes to send, queued, failed, recently sent |
| GET | `/api/monitor` | | Spend by week and job, draft quality, sending state |
| POST | `/api/messages/<id>/approve` | `{subject?, body?}` | Your approval: the email is queued for the next slot in your send window |
| POST | `/api/messages/<id>/skip`, `/pullback`, `/retry` | | Skip a draft, pull a queued email back to review, retry a failed one |
| POST | `/api/messages/<id>/redraft` | `{feedback}` | Rewrites that draft in place |
| POST | `/api/messages/<id>/linkedin_sent` | `{text?}` | You sent the LinkedIn note yourself |
| POST | `/api/messages/<id>/release` | | A held message back to review; refused while its job is closed or its resume fails the duplicate check |

Message statuses: `drafting`, `review`, `queued`, `sending`, `sent`, `held`, `skipped`,
`failed`. Person statuses: `proposed`, `approved`, `rejected`.

An approved email to a company where you are in process is held, not sent. A follow-up is held
once the person has written back or you have written to them yourself.

## Inbox (feature `email`)

| Method | Path | Body | What it does |
|---|---|---|---|
| GET | `/api/inbox` | | Every email read about a tracked job, newest first, with `needs`: the ids of those that need you |
| POST | `/api/inbox/check` | `{days?}` (1 to 60, default 3) | Reads now. `409` while a read is running |
| POST | `/api/inbox/<id>/undo` | | Puts back what that email changed |
| POST | `/api/inbox/<id>/set` | `{kind, job_id}` | Your correction: undoes the first reading and acts again |
| POST | `/api/inbox/<id>/add_job` | `{company, title, url?, applied_at?, stage?, note?, company_url?, reread?}` | Turns an email about an untracked job into a job |
| POST | `/api/bounces/check` | | Reads delivery failures now |

Email kinds: `rejection`, `paused`, `out_of_office`, `reply`, `interview`, `assessment`,
`received`, `other`, and `my_reply` for your own sent replies. Reading is read only; see
[email.md](email.md).

## File actions on another machine

| Method | Path | What it does |
|---|---|---|
| GET | `/api/mac/next?wait=<seconds>` | The oldest pending file action (open a file, copy to the drop folder) for a helper running on your desktop machine, waiting up to 30 seconds for one. Actions older than two minutes expire |
| POST | `/api/mac/<id>/done` | `{ok, error?}`: the helper finished it |

No such helper ships with this project; in local mode the server does these actions itself.

## Models and costs

Every model call is `claude -p` with tools turned off and everything inline, using the model
named for that task in the `models` block of `profile.yaml`. Builds, cover letters and
evaluations store `cost_usd`, Claude Code's own estimate at API prices (on a subscription
nothing is billed per call; use it to compare runs). Paid Apify calls are logged with their
settled cost and shown in `/api/monitor`.

## Robustness

- Builds, cover letters and revisions run side by side, one thread each; only LibreOffice is
  serialized (about two seconds a render).
- On restart, any job left `evaluating`, `building` or `queued` becomes `error` with
  "Interrupted by a server restart". Press the button again.
- Every string a model returns passes through an em dash filter before it is stored.
