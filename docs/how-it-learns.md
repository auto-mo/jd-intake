# How it learns from you

jd-intake gets more like you the more you correct it. Nothing is trained or uploaded: it keeps
a plain-text file of rules taken from your own edits, and every prompt reads that file first.

## The loop

1. **The server notices.** When you do something that shows a preference, the server appends
   one line to `data/learning-inbox.jsonl`:

   | Event | When |
   |---|---|
   | `draft_edited` | you changed an outreach draft before approving it (it keeps the draft and what was sent) |
   | `draft_rejected` | you skipped a draft (with your reason, if you gave one) |
   | `resume_feedback` | you asked for a revision of a resume |
   | `cover_feedback` | you asked for a revision of a cover letter |
   | `eval_override` | you applied to a job scored below your Auto threshold, or skipped one scored above it |

2. **You run `/learn`** in Claude Code, whenever you like (once a week is plenty). It reads the
   new events, compares each draft with what you actually did, and writes short rules with
   their scope and evidence into `profile/learnings.md`:

   ```
   ## 2026-01-15 · cold emails to recruiters · from an edited email
   - Open with the reason for writing, not a compliment. Evidence: "I loved your post on..."
     became "I applied for the analyst role last week."
   ```

   Rules about how you write also go into `profile/voice.md`. Processed events are recorded in
   `data/learning-inbox.processed`, so nothing is learned twice.

3. **Everything reads the rules first.** The evaluation, resume, cover letter and outreach
   prompts include `learnings.md` as rules from your own edits, newest first, overriding older
   rules. The skills read it before anything else.

4. **Rules get tidier over time.** When the same rule shows up three times, `/learn` promotes it
   to a Standing rules section at the top. A newer edit that contradicts an older rule wins for
   its scope, and the old rule is marked superseded rather than deleted.

5. **The skills catch up.** When rules change materially, `/learn` runs `skill-builder`, which
   rewrites your addenda in `profile/skills/` (your role families, claim rules, which base
   resume for which job). See below.

## One voice, different registers

You write differently to a recruiter, a founder, a former colleague and on a resume. Every rule
is scoped to an audience, and a single edit is treated as one data point, not a law for all
your writing.

## Teach it directly

- Paste or show your final version of anything it drafted and say "learn from this". A
  screenshot of an email you sent works too.
- Add real emails you wrote to `profile/voice-examples.md`. Examples teach the drafter more than
  rules do. Keep three to ten.
- Tell it why you rejected something. A reason is worth more than a silent skip.
- Edit `profile/learnings.md` or `profile/voice.md` by hand. They are plain Markdown.

Messages you type to Claude in chat are not treated as samples of your writing.

## What it will not do

- It never turns a learning into a new claim about your experience. A corrected fact goes to
  `profile/profile.md`, and only after you confirm it.
- It never changes your settings or turns a feature on.
- It never stores other people's names or contact details in a rule.

## The skill addenda

The skills in `.claude/skills/` are generic and shared. What is specific to you lives in
`profile/skills/<skill>.md`, written by `skill-builder` from your profile and learnings:

- `evaluate-jd.md`: your role families and how to score them, level rules, out-of-scope roles,
  which base resume for which job type, cover letter combinations.
- `resume-build.md`: role order, what each role may and may not claim, headline metrics, tools.
- `cover-letter-build.md`: combinations that work, your register for letters.
- `apply.md`: how you answer screening questions.

Run `skill-builder` again any time you change your profile. You can edit an addendum by hand;
mark a section `<!-- hand-written -->` and a re-run keeps it.
