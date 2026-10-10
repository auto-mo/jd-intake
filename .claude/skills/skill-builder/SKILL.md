---
name: skill-builder
description: >
  Tailor the jd-intake skills to the user. Writes user-specific addenda to
  profile/skills/<skill>.md (role families and how to score them, claim rules, which base resume
  for which job type, cover letter combinations, level rules) that evaluate-jd, resume-build,
  cover-letter-build and apply read before they work. Can also create a brand-new custom skill
  in .claude/skills/ for a workflow the user describes. Use at the end of onboarding, when the
  user says "rebuild my skills", "update the skills", "make a skill for ...", and whenever
  profile/ or profile/learnings.md has changed materially (the learn skill triggers it).
---

# skill-builder

The generic skills in `.claude/skills/` hold the method: the scoring rubric, the build phases,
the one-page rules, the verification passes. Everything about this particular user goes into
short addenda in `profile/skills/`, which each skill reads right after `profile/learnings.md`.
This keeps the generic skills shareable and the user's tailoring private (git ignores
`profile/`).

The profile directory is `profile/` at the repo root, or `$JDI_PROFILE_DIR` when set.

## Inputs (read all of them)

- `profile/profile.yaml`, `profile/profile.md`, `profile/base_versions.yaml`,
  `profile/cover_kb.yaml`, `profile/voice.md`, `profile/application-answers.md`
- `profile/learnings.md`, newest first. A rule there that keeps recurring belongs in an addendum
  as a standing rule.
- `profile/approaches.yaml`, if it exists.
- The existing addenda in `profile/skills/`, so a re-run updates rather than starts over.
- The generic skills themselves, so an addendum never repeats or contradicts their method.

## Rules for every addendum

- **Only what is specific to this user.** Never copy the generic method. If a line would be true
  for anyone, it does not belong.
- **Every fact traces to the profile or the learnings.** Never invent a role family, a claim, a
  metric or a preference. When the profile is silent on something an addendum would need, leave
  it out and list it under "Open questions" at the end of the addendum.
- **An addendum may tighten a generic rule, never loosen a Non-negotiable or Hard Rule** (one
  page, no invented claims, nothing outbound without approval).
- Short: aim for under 120 lines each. Tables over prose.
- Start each file with:
  `<!-- written by skill-builder on YYYY-MM-DD from profile/ and learnings.md; re-run to update -->`
- No em dashes.
- Before overwriting an addendum, read it. A section the user wrote by hand (marked
  `<!-- hand-written -->`) is kept as is.

## What each addendum holds

### `profile/skills/evaluate-jd.md`
- **Role families** from `targets.roles` and the experience in `profile.md`: for each, a short
  name, title words that signal it, what the user brings to it, and how to score it (what a
  strong fit looks like, the usual gaps).
- **Out of scope**: families the user said they will not take, as skips.
- **Level rules** from `targets.level` and `level_words_at_level`: what counts as at level,
  stretch and under, in years and title words.
- **Which base version for which job type**: a table of base version key, the families it
  serves, and the tie-breaker when two are close.
- **Cover letter combinations**: a table of employer or role type and the recommended variant
  ids from `cover_kb.yaml`, plus when to recommend a custom narrative.
- **Work authorization**: the hard blockers in plain words, and, only if
  `work_authorization.needs_sponsorship` is true, how much weight sponsorship signals get.
- **Tools**: the confirmed list in one line, and tools known as NOT used.

### `profile/skills/resume-build.md`
- **Role order** from `experience_order`, with dates, and whether every role must stay.
- **Claim rules per role**: what each role may and may not claim (from the "Claim rules" lines
  in `profile.md` and from learnings).
- **Headline metrics**: the numbers in `profile.md` worth leading with, and any that must
  appear only once on a page.
- **Which base version for which job type** (same table as above).
- **Tools**: confirmed, light use only, never used.
- **Resume rules from learnings** that have recurred.

### `profile/skills/cover-letter-build.md`
- Combinations by employer or role type, and combinations that worked before (from learnings).
- The user's register for letters, and phrases to avoid, from `voice.md` and learnings scoped
  to cover letters.
- Which stories pair well and which never go together.

### `profile/skills/apply.md`
- Work authorization and sponsorship answers, pointing at `application-answers.md`.
- How the user wants screening questions answered (length, tone), from learnings.

## Creating a custom skill

When the user describes a workflow of their own ("a skill that drafts a thank-you note after
an interview", "a skill that checks a posting against my salary floor"):

1. Ask what triggers it, what it reads, what it produces, and what it must never do. Two or
   three questions at most.
2. Create `.claude/skills/<name>/SKILL.md` with YAML frontmatter: `name` (lowercase, hyphens)
   and a `description` that says what it does and the phrases that should trigger it.
3. In the body: a "Read first" section that reads `profile/learnings.md` and any profile files
   it needs by path; the steps; the rules (never invent a claim, nothing sent or submitted
   without the user's approval, no em dashes); the output.
4. Never put the user's personal details in the skill itself: reference the profile files.
5. Keep custom skills out of git: append `.claude/skills/<name>/` to `.git/info/exclude` (a
   local file git never shares). Tell the user that is where it went and why.
6. Tell the user how to run it (`/<name>` in Claude Code).

## When to re-run

- After onboarding (the onboard skill runs it).
- After the `learn` skill reports that rules changed materially: a new standing rule, a rule
  promoted from repeated edits, a change to targets, level or work authorization.
- After the user edits `profile.yaml`, `profile.md`, `base_versions.yaml` or `cover_kb.yaml` by
  hand in a way that changes what a skill should do.

## Finish

Report in a few lines: which addenda were written or changed, what changed in each (one line
each), and any open questions the profile could not answer. Suggest the user skim the addenda;
they are plain Markdown and can be edited by hand (mark hand-written sections so a re-run keeps
them).
