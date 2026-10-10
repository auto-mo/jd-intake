---
name: evaluate-jd
description: >
  Evaluate a job description for the user (the person whose profile is in profile/) before any
  application effort is spent. Trigger whenever a job posting, job link, or role description is
  shared and the user wants to know whether to pursue it, or says "evaluate this role", "is this
  worth applying to", "what do you think of this JD", "should I apply", "check this posting", or
  pastes a block of text that looks like a job description. Run this BEFORE resume-build or
  cover-letter-build: it produces the brief those skills consume. Never skip it and go straight
  to tailoring.
---

# evaluate-jd

Triage a job description honestly and produce a structured brief that feeds resume-build and
cover-letter-build. The purpose is to kill bad fits fast and surface the right framing for good
ones, before any effort is spent on a build.

## Read first, every time

The profile directory is `profile/` at the repo root, or `$JDI_PROFILE_DIR` when that is set.
Read these before scoring anything, in this order:

1. `profile/learnings.md`: rules taken from the user's own edits and overrides, newest first.
   They override older rules, including the defaults in this file.
2. `profile/skills/evaluate-jd.md`, if it exists: the user's own addendum written by the
   `skill-builder` skill (their role families and how to score them, level rules, which base
   version suits which job type, cover letter combinations). Where it is more specific than
   this file, it wins. It never relaxes a Hard Rule below.
3. `profile/profile.yaml`: name, targets (roles, level, locations), `work_authorization`,
   `tools_confirmed`, `features`, `standing_facts`.
4. `profile/profile.md`: every claim the user can make. The evidence dimension below is judged
   against this file only.
5. `profile/base_versions.yaml`: the base resumes (their keys, labels and `signals`).
6. `profile/cover_kb.yaml`: the cover letter blocks and their ids.

If `profile/profile.yaml` does not exist, stop and tell the user to run `/onboard` first.

**When the jd-intake server calls this skill headlessly**, it pastes the candidate context, the
addendum and the learnings into the prompt and turns tools off. Use what it pasted; do not try
to read files, and never ask a question.

## Candidate context

Build the candidate context from the files above, not from memory: the user's name, completed
degrees (entries in `degrees` with `completed: true` are finished; never write "expected",
"candidate" or "graduating" for them), years of experience, the kinds of work in `profile.md`,
target roles and level, preferred locations, and work authorization. `standing_facts` are true
statements every sentence must respect.

The roles the user wants are in `targets.roles`. The addendum may list role families with
notes on how to score each. **Never score a role down only because its title is not on that
list.** The question is always whether the user would clear the bar, not whether the title is
a favourite. The only domain skips are the ones the addendum or `learnings.md` names as out of
scope, plus the Hard Rules below.

---

## Evaluation workflow

### Step 0: Read the JD file
When invoked as `/evaluate-jd <path>`, read that file first. Its header carries the URL,
location, capture date, a `Seen before:` line if the posting was captured earlier and, when
the sponsorship feature is on, an `LCA:` line from a deterministic lookup. Treat those header
lines as facts. Never re-derive them.

### Step 1: Sponsorship check (only when `features.sponsorship` is on)
Skip this step entirely, writing `Not checked` in the SPONSORSHIP line with
`sponsorship_flag` set from the JD text alone, when `features.sponsorship` is off or
`work_authorization.needs_sponsorship` is false. Otherwise combine two inputs into one line:
- The `LCA:` header line. Filings and the year-over-year trend say whether this employer has
  actually sponsored. "No LCA record" means no filings under that name, a real negative signal
  for a large company and a weak one for a startup or a subsidiary name.
- Explicit language in the JD: "will not sponsor" or "must be authorized without sponsorship"
  is flagged clearly but does not block the evaluation. "Sponsorship available" is flagged
  positively. Silence is reported as silence.
Report both in the SPONSORSHIP line, LCA first. `docs/sponsorship.md` explains the plug-in.

Requirements that block whatever the sponsorship setting (citizenship, clearance) come from
`work_authorization.hard_blockers`.

### Step 2: Role classification
Name the kind of role in a few words, using the user's role families from the addendum when it
has them. This picks the base version and the framing. **It is descriptive only and never moves
the score**, except for a role family the addendum marks out of scope.

### Step 3: Fit scoring
The score answers one question: **if the user applied today, would this employer shortlist
them?** It is not how much they want the job. Score honestly across these dimensions and do not
inflate.

| Dimension | What to assess |
|---|---|
| **Hard requirements** | Years asked against the user's years, degree, named must-haves, certifications, domain years. What would a recruiter screen on first? |
| **Evidence on the page** | Can the resume actually show what this role screens for, from real work in `profile.md`? A requirement they meet but cannot evidence is a partial miss. |
| **Level fit** | Against `targets.level` and `targets.level_words_at_level`. Materially above lowers the score; materially below lowers it too. |
| **Work authorization** | Only when sponsorship is relevant (Step 1). A flag, never an automatic disqualifier unless the JD is absolute or the requirement is in `hard_blockers`. |
| **Differentiation** | Does the user's particular mix of experience make them stand out in this specific pile, or are they one of many? |

Say the gap in plain terms ("no supply chain work to show"), never as a label ("outside your
lane").

Weight hard requirements and evidence on the page most heavily. A role the user could plainly do
but has never held the title for is a stretch worth noting, not a skip.

### Step 4: Tailor, base or skip
- **Tailor**: a strong fit, and the base resume has meaningful keyword gaps or framing needs
  adjustment. Run resume-build.
- **Base**: a clean fit to an existing base version. Use it as is.
- **Skip**: only for an out-of-scope role family, a hard blocker from the profile, an explicit
  work authorization block that applies to the user, a contract arrangement the user has ruled
  out, or a bar so far above them that an application is not credible (for example many more
  years of a specific practice than they have, or a director with reports when they have never
  managed).

### Step 5: Keyword gap analysis (only if Tailor)
Identify four to six high-signal terms from the JD that are genuinely missing or underweighted
in the recommended base version. Do not list terms already well represented. These feed
resume-build.

### Step 5b: Build questions (always)
List the questions resume-build would have to ask before building for this JD. Only genuine
unknowns: tools or methods the JD names that are not in `tools_confirmed` or `profile.md`, and
claims the JD invites that only the user can confirm (people management, P&L, quota, a named
certification). If there are none, return an empty list. This list decides whether an approved
build can start without waiting.

**Each question must be answerable by tapping one option.** The user answers in a side panel,
often in a hurry. Give every question an `id` (short slug), the `question`, a one-line `why`
naming the JD language that prompted it, a `type`, `options`, and `affects` (what changes on
the resume).

- `yes_no` for a tool or a credential: options exactly `["Yes, hands on", "No"]`.
- `choice` for anything graded, with two to four concrete options that are real positions
  rather than degrees of confidence. For people management:
  `["Direct reports", "Informal mentoring only", "Neither"]`.
- `text` only when no option set is honest. Aim for none of these.

Never more than three questions. Keep the ones that change a bullet and drop the rest. Never
ask about anything `profile.md` already settles.

### Step 5c: Chip flags (always)
Two fields the panel turns into coloured chips, so keep them strict.

- `sponsorship_flag`: `explicit_no` only when the JD states it will not sponsor now or in the
  future, or requires citizenship or clearance. `explicit_yes` only when it offers sponsorship.
  Everything else, including silence and soft present-tense wording, is `silent`.
- `level_fit`: `at_level` when the JD's level matches `targets.level`. `stretch` when it asks
  for materially more (many more years, direct reports, owning a function). `under` when it is
  below the user's level.

### Step 5d: Blockers (always)
Up to three `blockers`, each `{label, kind}`: the reasons the score is what it is, shown as
pills read in one glance, so short (four words or fewer) and true. Empty when nothing
structural stands in the way.

- `contract`: "Contract, not W-2", "1099 only" (only when the user has ruled contracts out)
- `visa`: "No sponsorship in JD" (only with explicit language, and only when the user needs it)
- `clearance` / `citizenship`: "Requires clearance", "Citizens only"
- `years`: "Needs 8+ years" (only when materially above the user's years)
- `skill`: a named tool or credential the user lacks: "Requires Salesforce"
- `domain`: only for a family marked out of scope
- `level`: "Director level", "Manager with reports"
- `location`: only when the JD requires a place the user has said no to; location is a
  preference, not a filter, so this is rare
- `other`: anything else that genuinely blocks

Order by weight. Soft gaps belong in GAPS, not here. A blocker is something that on its own
would make you say Skip.

### Step 6: Base version and cover letter combination
- **Base version:** pick a key from `base_versions.yaml`. Match the JD against each version's
  `signals`, then apply the addendum's "which version for which job type" table if it has one.
  When two are close, the JD's lead signal (what its first paragraph and first requirements
  are about) wins.
- **Cover letter combo:** name one variant id per section of `cover_kb.yaml`, joined with
  ` + ` (for example `opener-operations + story-network + close-simple`). Use the variants'
  `note` fields and the addendum's combination table. If no block fits the employer, say
  `Custom narrative` in COVER LETTER FORMAT; otherwise `KB modular`.

---

## Output format

Produce the evaluation in exactly this structure. Each field must say something not already
covered elsewhere. Address the user as "you".

```
ROLE: [Title] at [Company]

JOB SUMMARY: [3 lines max. What the role is, who it serves, what the work involves.
Factual, no editorializing.]

─────────────────────────────────────
FIT SCORE: XX%
RECOMMENDATION: TAILOR / BASE / SKIP
─────────────────────────────────────

SPONSORSHIP: [One line. Explicit yes / Explicit no, flagged / Silent / Not checked]

STRENGTHS:
• [Max 2 bullets, specific to your actual experience in profile.md]

GAPS:
• [Max 3 bullets: honest mismatches, level issues, domain stretch.
  Fold work authorization risk in here as one bullet if relevant.]

RESUME VERSION: [a key from base_versions.yaml, or N/A]
TAILOR CALL: [Tailor / Base / Skip], [one-sentence rationale]

KEYWORD GAPS (if Tailor):
• [Term 1], missing from [resume section]
• [Term 2], underweighted in [resume section]

COVER LETTER COMBO: [variant ids joined with +]
COVER LETTER FORMAT: [KB modular / Custom narrative]

HONEST TAKE: [2 sentences max. Only something not already covered above.]

─────────────────────────────────────
Ready to build? RESUME | COVER | BOTH | SKIP
Override recommendation? Reply OVERRIDE to proceed anyway.
─────────────────────────────────────
```

---

## When called from the jd-intake server

The server invokes this skill headlessly with a JSON schema. Fill every schema field:
`fit_score` (integer 0 to 100), `recommendation`, `resume_version` (a key from
`base_versions.yaml`), `sponsorship` (the one-line SPONSORSHIP text), `strengths`, `gaps`,
`keyword_gaps` (empty unless Tailor), `cover_letter_combo`, `cover_letter_format`,
`honest_take`, `sponsorship_flag` and `level_fit` (Step 5c), `blockers` (Step 5d), and
`build_questions` (Step 5b, objects, not strings). Do not write a prose brief: the server
assembles it from these fields. The JD arrives inside the prompt; do not read files. Nobody is
at the terminal: never ask a question, never wait for a reply.

## Decision rules

- **Hard blockers** are the ones in `work_authorization.hard_blockers` (for example clearance or
  citizenship). Interviewing cannot convert these. A background check that is not a clearance is
  a "verify", never a score killer.
- **Low bar for low cost.** A one-click application or an inbound recruiter is a near-zero bar:
  recommend going ahead despite soft misfits (location, domain, travel). This never overrides a
  hard blocker. Roles that need a tailored resume, a custom cover letter or outreach get the
  full evaluation.
- **Location, travel and industry are preferences, never filters**, unless the addendum or
  `learnings.md` says otherwise. Note them; do not lower the score for them alone.
- Never assert whether the user has already applied or how long a posting has been open; the
  server's "Seen before" line is the only source for that.
- **Soft sponsorship language** (sponsorship on only): quote the exact sentence in the
  SPONSORSHIP line and let the user decide. Only absolute language is a flag on its own.
- Never cite job-board "match scores"; they are not evidence.
- Never guess the employer when the JD does not name one; say it is unnamed and score the text.
  Read company names from the document, never from memory.

## Hard rules

- Never inflate the fit score to be encouraging. A 55% is a 55%.
- No em dashes anywhere in the output. Use a comma, a colon, or a new sentence.
- Never recommend tailoring if Base is sufficient: tailoring has a time cost.
- When sponsorship is on, never skip the sponsorship check and never contradict the LCA line.
- Never produce resume bullets or cover letter text inside this skill.
- If the JD is vague or incomplete, extract the core capability themes from what is there and
  note what is missing before scoring.
- Every strength must point at something real in `profile.md`. Never credit the user with
  experience the profile does not show.
