---
name: resume-build
description: >
  Build a tailored one-page resume for the user (the person whose profile is in profile/)
  against a specific job description. Invoke whenever a resume needs to be created, tailored,
  rebuilt, or corrected for a role. Trigger phrases include "tailor", "tailor resume", "tailor
  it", "build the resume", "make a resume for this", "resume for this one", "can you tailor", or
  a reply of RESUME or BOTH after an evaluate-jd output. Also invoke when a job description is
  pasted alongside any request to apply, when fixing or adjusting an existing build (page too
  short, wrong order, add a bullet, swap a role), and when producing a resume that will be
  stitched into a larger application document. Needs a job description and a base version (a
  key from profile/base_versions.yaml). ALWAYS run Phase 0 and ask every open question in a
  single message BEFORE building anything. The goal is one build, not a build followed by
  corrections.
---

# resume-build

Produce a one-page, fully verified, visually correct tailored resume.

The output is a `.docx` rendered through the engine (`engine/`, a template-driven generator
around `engine/template.docx`), converted to PDF with LibreOffice, rasterized, and visually
inspected before delivery.

## Read first, every time

The profile directory is `profile/` at the repo root, or `$JDI_PROFILE_DIR` when set.

1. `profile/learnings.md`: rules from the user's own edits, newest first. They override older
   rules, including the defaults in this file.
2. `profile/skills/resume-build.md`, if it exists: the user's addendum from `skill-builder`
   (their claims rules, which base version for which job type, headline metrics, role notes).
   Where it is more specific than this file, it wins. It never relaxes a Non-negotiable.
3. `profile/profile.md`: the only source for any claim or number.
4. `profile/profile.yaml`: identity and contact details, `experience_order`, `keep_every_role`,
   `tools_confirmed`, `standing_facts`, `degrees`, and `resume` (file stem, bullets per role).
5. `profile/base_versions.yaml`: the approved base resumes.
6. The application folder: `JD.md`, `EVALUATION.md` (the evaluate-jd brief) and `ANSWERS.md`
   (the user's answers to the build questions) when they exist.

If `profile/profile.yaml` does not exist, stop and tell the user to run `/onboard` first.

---

## When to invoke this skill

**Invoke for:**

- Any request to tailor, build, rebuild, or adjust a resume for a specific role
- A job description pasted with an instruction to apply, even without the word "resume"
- Fixing an existing build: page underfilled, wrong order, add or cut a bullet, swap a role,
  change emphasis
- Building a resume that will be combined with a cover letter into one document
- A follow-up on a resume already delivered in this conversation. The verification passes
  apply to every rebuild, not only the first one.

**Do not invoke for:**

- Evaluating a job description with no build requested. That is `evaluate-jd`.
- Writing a cover letter alone. That is `cover-letter-build`.
- Filling application forms. That is `apply`.
- Drafting outreach messages or recruiter replies, or general career advice.

**If a role was evaluated as a skip and the user asks for a build anyway,** build it. The flag
has been raised once; do not re-litigate it.

---

## Non-negotiables

1. **Exactly one page.** Never two. Never overflowing.
2. **The page must be visually full.** 92 to 98 percent vertical fill. Underfill looks worse
   than dense text and reads as thin experience.
3. **Strict reverse chronological order**, the order in `experience_order`. Never reorder
   without explicit approval asked for in Phase 0.
4. **Every claim traceable to `profile.md` or `ANSWERS.md`.** Never invent a detail to make a
   bullet land better. Never invent a number.
5. **Keep every role** when `keep_every_role` is true (the default). Trim bullets, not roles.
6. **No em dashes anywhere.**
7. **Ask before building, never after.** One build.
8. **Visual verification before delivery.** Never present a file you have not looked at.
9. **Completed degrees read as completed.** For a degree with `completed: true`, never write
   "expected", "candidate", "student" or a future tense.

---

## Phase 0: Ask everything first

**Mandatory, and before any code.** Read the JD, find every open question, and ask them all in
one short message. Do not build, discover a gap, then rebuild.

Scan the JD for:

- **Named tools not in `tools_confirmed` or `profile.md`.** Ask directly: "The JD names Sigma and
  Snowflake. Have you used either?" Do not assume absence and do not quietly include them for
  keyword match.
- **Named methods** (Agile ceremonies, Scrum, a specific framework). Same rule.
- **Claims the JD invites that only the user can confirm**: board-level reporting, P&L, quota,
  people management, a certification. Ask before writing a bullet around it.
- **A structural decision, only when it departs from standard.** Standard is: reverse
  chronological, every role, the base version's sections. Ask only when proposing a departure,
  such as adding a projects section above EXPERIENCE or dropping a role.
- **Base version**, if the JD and the evaluation do not make it obvious.

Two to five questions at most. **Ask only where you need information you do not have.** Do not
ask for confirmation of a default, do not ask a question the JD or `profile.md` answers, and do
not narrate decisions that need no input. If nothing is genuinely open, build without asking.

When the user answers, offer to add each new confirmed fact to `profile/profile.md` so the next
build starts further ahead. Write it only if they say yes.

---

## Phase 1: Extract the JD's own language

- **Named responsibilities**, in their words. These become bullet openers.
- **Stated requirements**, separating hard gates from nice-to-haves.
- **Repeated phrases.** A term that appears three or more times is a screening criterion.
  Address it, or deliberately decline to and say so at delivery.

---

## Phase 2: Build

### Bullet standard

Every bullet must land an outcome. A bullet that only describes scope or responsibility is a
failure.

| Fails | Passes |
|---|---|
| "Served as operations partner to the regional team" | "Rebuilt the weekly forecast for 40 sites, cutting stockouts 18% in a quarter" |
| "Managed cross-functional initiatives across 5 functions" | "Found where throughput broke down across 5 functions, sized each fix, and sequenced them into a plan that cut cycle time 30%" |

(Examples are invented; real numbers come only from `profile.md`.)

The test: after reading the bullet, can the reader say what changed because the user was
there? If not, rewrite it.

One practice bullet per role is allowed with no metric if it demonstrates a stated JD
requirement. Never more than one.

Writing rules:
- Lead each bullet with a verb. No "Responsible for", no "Worked on".
- Never repeat a verb across the page. Track the ones already spent.
- Conservative, defensible numbers only. Never round upward. One instance of any given
  percentage on the page.
- Result before mechanism when the two compete for space.
- No first person, except inside a projects line where it distinguishes a personal build.
- Plain past tense for finished work, present for current roles.
- Tailor by selection and emphasis, not by invention. `profile.md` has more than fits. Choose.

### Structure and role order

The role order is `experience_order` in `profile.yaml`, newest first. It is not a judgment call.

- Roles carry `resume.bullets_per_role` bullets (default 1 to 4). Weight toward the role that
  best answers the JD, but do not move it up the page.
- **Dropping a role is a decision to raise in Phase 0, never a space-saving default**, and is
  not allowed at all when `keep_every_role` is true.
- Section order follows the base version: EDUCATION, an optional builds section (its title is
  `resume.builds_title`), EXPERIENCE, SKILLS, optional projects.
- A builds or projects section above EXPERIENCE is used only when the base version has one or
  the JD screens hard on hands-on building. Ask in Phase 0 before adding one.
- The addendum's role notes (what each role may and may not claim) apply to every bullet.

### Line-length rule

Every bullet renders as exactly one full line or exactly two full lines. A trailing line under
about 70 percent width is the most visible defect on a resume. At the default format (Times New
Roman 10 pt, narrow margins, justified): one full line is 135 to 148 characters, two full lines
255 to 280 (about 10 fewer with a bold lead label). 149 to 250 is the dead zone. These are
planning aids; the measure step is the proof.

---

## Format specification

The engine and `engine/template.docx` carry the format. Do not vary it unless asked.

| Property | Value |
|---|---|
| Page | US Letter, 12240 x 15840 twips. A4 is a known failure mode |
| Margins | 567 DXA all sides (about 1 cm, deliberately tight) |
| Body | `resume.font` (default Times New Roman), 10 pt |
| Name | 14 pt bold, centered |
| Contact line | 10 pt, centered: `location | phone | email` from `profile.yaml`, plus LinkedIn and website links when set |
| Section headers | 10 pt bold, centered, full-width bottom border |
| Dates | right-aligned with a right tab stop at 11088. Never a positional tab: LibreOffice ignores it |
| Bullets | justified, hanging indent 180/180 |
| Summary section | none unless the user asks |

Never insert an empty spacer paragraph right before a skills line: it breaks the run and drops
the bold label.

---

## Tools

**Confirmed, safe to include when relevant:** everything in `tools_confirmed` and anything
`profile.md` lists as used. The addendum may note tools that are confirmed only as light use
(list them only when the JD names them) and tools confirmed as NOT used (never list them).

**Everything else: ask in Phase 0.** Do not assume the user has not used something. Do not
include something to improve keyword match. A confirmed answer updates `tools_confirmed` (ask
before writing it).

---

## Phase 3: Verification passes

Run all three. Do not skip one because the build looks fine.

### Pass 1: Content
- Does every bullet land an outcome?
- Is every number in `profile.md`, `ANSWERS.md` or the base version? If not, flag it.
- Is anything asserted that the user has not actually said? Facts about their own systems,
  projects and engagements come from them. If unsure what something does, ask.
- Did dropping a bullet leave an unexplained gap?

### Pass 2: Voice
- No em dashes.
- No buzzwords: robust, leveraging, cutting-edge, seamless, spearheaded, best-in-class,
  synergy, holistic, passionate, dynamic, results-driven.
- No AI patterns: "rare combination", "throughline", "sits at the center of", "sits at the
  intersection of", "precisely what X demands", "is not abstract to me", "I keep coming back
  to", rule-of-three lists, symmetrical A/B pairings, not-X-but-Y, antithesis closers,
  colon-then-triplet closers, sentence fragments as emphasis.
- The banned phrases in `profile/voice.md` and every rule in `learnings.md` scoped to resumes.
- Never editorialize about the user's seniority or apologize for their experience level.
- Approved wording outranks a fresh rewrite: if a bullet already exists in a base version and
  still fits, keep it rather than rephrasing for its own sake.
- Would the user say this out loud? If a phrase is more composed than spoken, cut it.

### Pass 3: Visual and structural

From the repo root, for any content JSON in the engine's shape:

```bash
python3 engine/engine.py fit content.json <application folder>/<file_stem>_<Company>.docx
```

`fit` renders, converts, measures every line and moves only layout spacing until the page is
one page and 92 to 98 percent full; when spacing runs out it names the bullets that need
characters added or cut. It also exits 2 on a repeated bullet or heading. Then:

```bash
pdfinfo <name>.pdf | grep Pages                     # must read 1
python3 engine/deficit.py <name>.pdf content.json   # per-bullet characters to add or cut
python3 engine/engine.py dups <name>.docx           # repeated bullets, items or headings
pdftoppm -jpeg -r 100 <name>.pdf page               # writes page-1.jpg
```

**Verify chronological order mechanically** after any edit that moves or inserts a role:
`pdftotext -layout <name>.pdf - | grep -E "<employer 1>|<employer 2>|..."` with the employers
from `experience_order`, and compare against that order.

**Look at `page-1.jpg`** and check:
- Exactly one page.
- **VERTICAL FILL. This is a blocking gate, not an observation.** At 100 dpi a US Letter page is
  about 1100 pixels tall. Content must reach roughly 1000 to 1080 pixels (92 to 98 percent).
  If it stops materially short, **do not deliver.** Add a bullet to a role carrying fewer than
  three, restore a dropped one, or expand the role that best answers the JD, then rebuild.
  Noting the gap in the delivery message is not a fix, and asking whether to pad it is not a
  fix. Never pad with filler; if there is nothing worth adding, the earlier cuts were wrong.
- No orphaned one- or two-word last lines.
- Dates right-aligned, not inline. Bold labels on skills lines render bold. Section borders
  full width. Margins even.

**Verify links** when the document has any:
```bash
python3 -c "
import pypdf, sys
r = pypdf.PdfReader(sys.argv[1])
for i, p in enumerate(r.pages):
    for a in (p.get('/Annots') or []):
        o = a.get_object(); act = o.get('/A')
        if act and '/URI' in act: print('page', i + 1, act['/URI'])
" <name>.pdf
```

---

## Phase 4: Deliver

Leave the `.docx`, the `.pdf`, `page-1.jpg` and `NOTES.md` in the application folder. Files are
named `<file_stem>_<Company>` (`resume.file_stem` in `profile.yaml`, company with no spaces).
The server copies the finished PDF to `JDI_DROP_DIR` when that is set.

Then say, in this order:

1. **What changed from the base**, as specific swaps. Not a summary of the resume.
2. **Structural decisions**, if any, with the reason so the user can overrule.
3. **Claims to verify**, one to three items: bullets whose truth only the user can confirm.
4. **Tools deliberately omitted**, if any.

Keep it short. The user does not need the resume described back to them. If they then edit the
resume themselves or give feedback, suggest running `/learn` so the change becomes a rule.

---

## Approved metrics

Every number in `profile.md` is approved. The addendum may list the user's headline metrics and
any that must appear at most once on a page (the same percentage used for two different things
reads as a template). Anything not in `profile.md` or `ANSWERS.md` needs the user's
confirmation before it goes on the page.

---

## Failure log

Each of these has happened. The checks above exist because of them.

- **Underfilled page, delivered anyway.** The most frequent failure. A resume gets
  repositioned, bullets are cut, the gap is noticed in the render, and it ships with a note
  about it. Noticing is not fixing. The fill number is a gate.
- **Broke chronology while patching.** A role inserted below an older one while adding bullets
  back. Run the chronology grep after every structural edit.
- **Wrong facts about the user's own work.** A system described from its name instead of from
  what it does. Ask what something does rather than inferring.
- **Fabricated a story.** An invented, plausible anecdote. Never invent an experience.
- **Assumed a tool gap that did not exist.** Left a tool off and flagged it as a gap when the
  user had used it. Ask, do not assume.
- **Asked after building instead of before.** All questions go in Phase 0.
- **Silent formatting break.** An empty spacer paragraph before a skills line killed the bold
  label. Only visible in the render.
- **The same item twice.** Edits meant to replace a section were applied on top of it, leaving
  an old item beside its rewrite. `engine.py dups` catches it; the server blocks such a build.

---

## When called from the jd-intake server (headless)

The server writes the words with one tool-less model call and renders with code. It pastes this
skill's content sections, the profile, the addendum, the learnings, the base version, the JD,
`EVALUATION.md` and `ANSWERS.md` into the prompt. Nobody is at the terminal.

- **Never ask.** Phase 0 already happened: `EVALUATION.md` holds the brief and `ANSWERS.md` the
  user's answers. A question with no answer means the claim stays off the page and goes in
  `claims_to_verify` or `tools_omitted`.
- **Never drop a role** when `keep_every_role` is true. Trim bullets, not roles.
- **Do not read files or run anything** when the prompt says so; everything is inline.
- When run as `/resume-build <folder>/JD.md` with tools, work only inside that folder. The
  machinery is in its `_build/` subfolder (the engine files copied there). Deliverables go in
  the folder itself, never inside `_build/`. Run the Pass 3 loop, write `NOTES.md` (what
  changed, structural decisions, claims to verify, tools omitted), and finish by filling the
  JSON schema the server passes.
