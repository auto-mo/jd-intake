---
name: onboard
description: >
  Guided first-time setup for jd-intake. Use when the user types /onboard, says "set me up",
  "get started", "onboard me", "build my profile", or when any other skill finds that
  profile/profile.yaml does not exist. Checks prerequisites, reads the user's existing resume or
  LinkedIn PDF, interviews them in small batches for what is missing, writes every file in
  profile/, builds and renders one to three base resumes until each fits one full page, sets up
  optional features, and ends by running skill-builder. Resumable: run it again and it continues
  from what already exists in profile/.
---

# onboard

You are setting up jd-intake for a new user. By the end, `profile/` holds everything the server
and the skills need, at least one base resume renders to one full page, and the user knows how
to load the extension and start the server.

Talk to the user as "you". Keep every message short. Ask in small batches (three to six
questions), never a wall of questions. Say where you are in the process ("Step 3 of 9").

## Ground rules

- **Never invent a claim.** Everything in `profile.md` comes from the user's documents or from
  their answers in this conversation. A number, title, date, tool or achievement they have not
  confirmed stays off. When a document and an answer disagree, ask.
- **Never ask for a secret in chat.** Passwords, API keys and tokens go into `.env` through the
  hidden-input command in Step 6. If the user pastes one into chat anyway, do not repeat it, write
  it to `.env` yourself only if they ask, and suggest they rotate it.
- **Write in the exact format of `examples/profile/`.** Open the matching example file before
  writing each profile file, and keep every key, its nesting and its type. The loader is
  `server/userprofile.py`; do not add keys it does not read unless the user asks for one.
- **No em dashes** in anything you write to the profile.
- **Personal data stays in `profile/`, `.env` and `data/`**, which git ignores. Never write the
  user's details anywhere else in the repo.
- The profile directory is `profile/` at the repo root, or `$JDI_PROFILE_DIR` when set.

## Step 0: Where are we?

List `profile/`. If it is missing, create it. If `profile/.onboard-progress.md` exists, read it,
tell the user which steps are done, and continue from the first one that is not. Otherwise read
whatever profile files exist and treat a step as done only when its files are complete.

Keep `profile/.onboard-progress.md` current after every step: one line per step, `done` or
`todo`, plus open questions you still need to ask. It is how a later run resumes.

## Step 1: Prerequisites

Run these checks and report one line each, with the fix for anything missing:

| Check | Command | Fix |
|---|---|---|
| Python 3.10 or newer | `python3 --version` | macOS: `brew install python`; Linux: the distribution's `python3` package |
| Python packages | `python3 -c "import flask, yaml, docx, pypdf"` | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| LibreOffice (renders resumes to PDF) | `soffice --version` | macOS: `brew install --cask libreoffice`; Debian or Ubuntu: `sudo apt install libreoffice-writer` |
| Poppler (measures and rasterizes PDFs) | `pdfinfo -v` and `pdftoppm -v` | macOS: `brew install poppler`; Debian or Ubuntu: `sudo apt install poppler-utils` |
| Google Chrome (for the extension) | ask the user | https://www.google.com/chrome/ |
| Claude Code | `claude --version` | https://docs.claude.com/en/docs/claude-code |
| Claude login or API key | `claude -p "Reply ok." --tools ""` returns ok, or `ANTHROPIC_API_KEY` is set | `claude` then `/login` for a subscription; or see `docs/api-key-mode.md` |

On macOS, if `soffice` is not on the PATH after installing, it lives at
`/Applications/LibreOffice.app/Contents/MacOS/soffice`; suggest adding that folder to the PATH.

Do not install anything yourself unless the user asks you to. Carry on with the interview while
they install; the render step (Step 5) is the first one that needs LibreOffice and Poppler.

## Step 2: Read what they already have

Ask for any of these (more is better):
- Their current resume, PDF or DOCX. Ask for the path, or for them to drop it into the chat.
- Their LinkedIn profile as a PDF (on their LinkedIn profile page: More, then Save to PDF).
- Any older resumes or a list of achievements they keep.

Read each one: `pdftotext -layout <file> -` for a PDF, the Read tool or python-docx for a DOCX.
Extract identity and contact details, education (school, degree, dates, whether finished),
every role (employer, title, place, dates, bullets), skills and tools, certifications, projects.

Show the user a compact summary of what you found (roles with dates, degrees) and ask them to
correct anything wrong before you go further. Note conflicts between documents as questions.

## Step 3: Interview for what is missing

Ask in batches, in this order, skipping anything the documents already answered and the user
confirmed. Record answers as you go.

**Batch A: identity and targets.**
- Name as it should appear on a resume, and the first name to address them by.
- Email, phone, city and state (or region), LinkedIn URL, personal website if any.
- Target roles, in their words (several are fine). Roles they would never take.
- Level: entry, mid, senior or executive, and the title words that are at their level (for
  example analyst, associate, manager). Roughly how many years of work experience in all.
- Locations: where they will work, remote preferences, preferred cities.

**Batch B: work authorization.**
- Are they authorized to work in the country they are applying in?
- Do they need an employer to sponsor a visa, now or later? (Yes turns on the sponsorship
  question in Step 6.)
- Which posting requirements rule them out entirely (citizenship, security clearance, a visa
  type)? These become `hard_blockers`.
- Contract or freelance roles: acceptable or not?

**Batch C: the stories behind the numbers.** For each role, newest first, and for the two or
three bullets with the strongest numbers:
- What exactly happened, what they did themselves, and what changed because of it.
- How the number was measured, and whether they can defend it in an interview. A number they
  cannot defend is dropped or softened, with their agreement.
- What the role may NOT claim (for example "advised, did not run it", "designed the spec,
  partners built it"). These become claim rules.

**Batch D: tools and settled facts.**
- Tools they have really used, hands on. Tools they know of but have not used (never listed).
- Certifications, with the issuer.
- Settled facts: things a writer is likely to get wrong (for example "has not managed direct
  reports", "the degree is finished").
- Gaps they want handled honestly (a career break, a missing credential, a title they never
  held).

**Batch E: voice.** Ask for three or more emails or messages they wrote themselves and sent
(a note to a recruiter, a follow-up, a message to a colleague). Paste or file paths are both
fine. Ask how they want to come across (warm, direct, formal) and any phrases they hate.
Messages they type to you in this chat are not writing samples.

**Batch F: application answers.** Willing to relocate and where, earliest start date, salary
expectation (or "prefer not to say"), how they usually answer demographic questions (or
"decline to answer"), anything else forms keep asking them.

## Step 4: Write the profile files

Open each example in `examples/profile/` first and match its format exactly. Write:

1. `profile/profile.yaml`: `identity`, `standing_facts` (short, true sentences every writer must
   respect, including the finished degree in past tense), `degrees` (with `completed`),
   `schools` (with aliases as people write them on LinkedIn), `experience_order` (employers
   newest first, spelled exactly as on the resume), `keep_every_role`,
   `targets` including `years_experience`, `work_authorization`, `tools_confirmed`, `resume` (`file_stem` from their name, default
   `builds_title`, `bullets_per_role`, `font`), `cover_letter`, `features` (all false for now),
   `outreach` (their timezone and a signature; leave the rest at the example's defaults), and
   `models` (the example's defaults). Keep the explanatory comments.
2. `profile/profile.md`: every confirmed claim, organized like the example: Identity,
   Education, Experience (newest first, one heading per role, bullets with numbers), Skills and
   tools (confirmed), Settled questions, Gaps to be honest about. Add a "Claim rules" line under
   any role that has one. Anything unconfirmed stays off. This file is the only source any
   writer may use.
3. `profile/voice.md`: Register, Rules and Banned phrases sections, from Batch E and the samples.
4. `profile/voice-examples.md`: the samples they gave, each separated by `---`, with names of
   other people replaced by first names only. Three to ten.
5. `profile/application-answers.md`: the Batch F answers plus name, contact details and the
   work authorization summary, in the example's list format.
6. `profile/cover_kb.yaml`: sections 1 (opener), 2 (story) and 3 (closing), with two to four
   variants per section drafted from their real stories. Each variant gets a stable `id`, a
   `label`, the `text` and a `note` on when to use it. Show the user the drafted blocks and ask
   for edits before saving; their edits are voice evidence too, so record them for Step 8.
7. `profile/learnings.md`: copy the example's header and comment block; no entries yet.

Show the user a short summary of each file as you write it, not the full text.

## Step 5: Base resumes, rendered until they fit

Propose one to three base versions, each aimed at one family of target roles (for example
"operations" and "analytics"). Show the proposal (key, label, which roles it serves) and agree
on it with the user. Then write `profile/base_versions.yaml` in the example's format:
`default`, and under `versions` each key with `label`, `signals` (a regular expression of words
in postings that suggest this version), `education`, an optional `builds` section, `experience`
(every role in `experience_order`, newest first), `skills_title`, `skills` and `projects`. A
version can `inherit` another and override only what differs.

Bullets come only from `profile.md`. Follow the bullet standard and the line-length rule in the
`resume-build` skill (one full line is 135 to 148 characters, two full lines 255 to 280).

Render and check each version:

```bash
mkdir -p data/onboard
python3 engine/engine.py base <key> > data/onboard/<key>.json
python3 engine/engine.py fit data/onboard/<key>.json data/onboard/<file_stem>_<key>.docx
pdftoppm -jpeg -r 100 data/onboard/<file_stem>_<key>.pdf data/onboard/<key>-page
```

`fit` prints a JSON result. `verdict` must be `fit`: one page with at most 0.4 inch left empty at the bottom (roughly 96 percent full or more), no orphan
lines. If it is `over`, cut or shorten the weakest bullets; `under`, add real content from
`profile.md`, in this order until it fits: a bullet for a role with fewer than three; more confirmed detail
in the strongest bullets so they run to two full lines (ask the user for the scope, the tools, who used the
result, the number); a projects section (`builds`) with one to three items; a certifications or methods
line in skills; relevant coursework under education. Short careers often need two-line bullets to fill a
page; never pad with claims the user has not confirmed, and never stretch spacing to fake fullness; `orphans`, lengthen or shorten the named bullets by
the character counts in `measure.bullets`. Edit `base_versions.yaml`, re-run, and repeat until
it fits. Then look at the JPEG yourself and check dates are right-aligned, bold labels render,
and nothing reads wrong. Show the user the image path and ask them to open the PDF.

Ask the user to read every bullet. Any change they make is a correction to `profile.md` or
`base_versions.yaml` first, and voice evidence for Step 8.

## Step 6: Optional features

Ask which of these they want now. Each stays off until they say yes and finish its setup. Set
the switch under `features` in `profile.yaml` only when setup is done.

| Feature | What it does | Setup and costs |
|---|---|---|
| `sponsorship` | Looks up whether an employer has filed for work visas, and flags sponsorship language in postings. Offer it only if they need sponsorship. | `docs/sponsorship.md` |
| `outreach` | Finds people at a company after the user applies, ranks them, drafts emails and LinkedIn notes for approval. Paid lookups through Apify. | `docs/outreach.md` |
| `email` | Sends approved outreach over the user's own mailbox (SMTP) and reads replies read-only (IMAP) to track rejections, interviews and away replies. | `docs/email.md` |
| `alerts` | Sends a Telegram message when something breaks (a dead login, repeated failures). | `docs/alerts.md` |

For a feature that needs secrets, give the user ONE command per secret that reads it with hidden
input and writes it to `.env` at the repo root, replacing any earlier line for that key. Never
ask them to paste it in chat. Template (swap `KEY_NAME`; run from the repo root):

```bash
scripts/set_secret.sh KEY_NAME
```

Afterwards check the key is present without printing it:
`grep -c '^KEY_NAME=' .env`. The key names are in `.env.example`.

For outreach, also fill the `outreach` block (timezone, send window, daily cap, signature) with
the user. For email, explain the read-only rule in `docs/email.md` in one sentence and confirm
they agree before turning it on.

## Step 7: Tailor the skills

Run the `skill-builder` skill. It writes `profile/skills/<skill>.md` addenda from the profile:
role families and how to score them, claim rules, which base version for which job type, cover
letter combinations, level rules. Tell the user it can be re-run any time.

## Step 8: Record what you learned about their voice

If the user edited anything you drafted during onboarding (bullets, cover letter blocks), run
the `learn` skill on those edits so the first rules are in `profile/learnings.md` from day one.

## Step 9: Start using it

Tell the user, in this order:

1. **Start the server:** `python3 server/app.py` from the repo root. It listens on
   `http://127.0.0.1:8790` (set `JDI_PORT` to change it). Open that address for the dashboard.
   `docs/run-locally.md` shows how to start it automatically at login.
2. **Load the extension:** in Chrome open `chrome://extensions`, turn on Developer mode, click
   "Load unpacked" and choose the `extension/` folder. Pin it, then open a job posting on
   LinkedIn, Greenhouse, Lever, Ashby or Workday and click the icon (or press Ctrl+Shift+J,
   Command+Shift+J on a Mac) to open the side panel and capture it.
3. **What happens next:** the posting is evaluated, they answer up to three quick questions,
   and they approve a build. The tailored resume (and cover letter if asked) lands in
   `data/applications/<job>/` and, by default, a copy on the Desktop (`JDI_DROP_DIR`).
4. **It learns from them:** when they edit a draft or reject one, the server records it; running
   `/learn` now and then turns those into rules. `docs/how-it-learns.md` explains.
5. **Where things are:** `profile/` (theirs, never committed), `data/` (jobs and files), `.env`
   (secrets). `docs/privacy.md` says what leaves their machine.

Mark every step done in `profile/.onboard-progress.md` and finish with a three-line summary:
what was set up, what is still open, and the one thing to do next.
