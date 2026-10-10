---
name: cover-letter-build
description: >
  Write a cover letter for the user (the person whose profile is in profile/) for a specific
  role, after evaluate-jd has chosen the cover letter combination. Invoke on "cover letter",
  "write the cover letter", a reply of COVER or BOTH after an evaluate-jd output, or when the
  jd-intake server calls it headlessly.
---

# cover-letter-build

Assemble a one-page cover letter from the user's building blocks, then adapt it to the
employer.

## Read first, every time

The profile directory is `profile/` at the repo root, or `$JDI_PROFILE_DIR` when set.

1. `profile/learnings.md`: rules from the user's own edits, newest first. They override older
   rules, including the defaults in this file. Rules scoped to cover letters apply in full;
   rules scoped to all writing apply too.
2. `profile/skills/cover-letter-build.md`, if it exists: the user's addendum from
   `skill-builder` (which combinations suit which employers, their register, combinations that
   worked before). Where it is more specific than this file, it wins.
3. `profile/cover_kb.yaml`: the sections and their variants, each with an `id`, `label`,
   `text` and a `note` on when to use it.
4. `profile/voice.md` (register, rules, banned phrases) and `profile/voice-examples.md` (real
   writing by the user, to imitate).
5. `profile/profile.md` and `standing_facts` in `profile/profile.yaml`: the only sources for any
   claim.
6. The application folder: `JD.md` and `EVALUATION.md`.

If `profile/profile.yaml` does not exist, stop and tell the user to run `/onboard` first.

## Inputs

- The combo from evaluate-jd: variant ids from `cover_kb.yaml` joined with ` + `, in section
  order (for example `opener-operations + story-network + close-simple`). Look each id up in
  `cover_kb.yaml`.
- If evaluate-jd said `Custom narrative` instead of `KB modular`, write the paragraphs from
  scratch in the user's voice from `profile.md` only, and keep a closing from the knowledge base.

## Rules

- Name the role and the employer exactly as the JD names them.
- **Never open on a gap or an apology.** The first sentence is a claim or a concrete story,
  never "although I lack".
- Register: the one in `voice.md`, direct first person. Plain language over idiom.
- **One credential per paragraph, at most.** Do not stack degrees, employers and metrics.
- **The middle of the letter is about the employer, not the user.** At least one paragraph names
  something specific and true about the employer from the JD: its work, customers, stage, or the
  problem the role exists to solve. No generic praise, and nothing about the employer that the
  JD does not say.
- Keep the knowledge base text as written except for names and light edits for flow. Do not
  rewrite the user's stories, and never add a number that is not in `profile.md`.
- If a block contains a phrase on the banned lists (`voice.md`, Pass 2 of resume-build), rewrite
  that clause plainly every time and keep the rest of the block.
- No em dashes, no buzzwords, no AI patterns ("rare combination", "throughline", "sits at the
  center of", "precisely what", "I keep coming back to", rule-of-three lists, not-X-but-Y).
- **Length:** `cover_letter.words` in `profile.yaml` (default 250 to 350 words), four paragraphs
  at most. Trim story text to fit rather than dropping the employer paragraph. When the employer
  asks specific questions for the letter, answer each one plainly; the letter may then run to
  six paragraphs.
- Tie past work, this role and future value in one arc. Do not repeat resume lines word for
  word.
- Completed degrees are completed: no future tense for them.

## Rendering (interactive use)

Write a spec and render it with the engine:

```bash
python3 engine/make_cover_letter.py spec.json
```

The spec is `{filename, date, recipient_lines, greeting, paragraphs, closing, signature}`. The
header (name, contact line, links) comes from the profile. `filename` is
`<file_stem>_<Company>_Cover_Letter.docx`. Check the PDF is one page, then look at it.

After delivery, if the user edits the letter themselves, suggest `/learn` so the edit becomes a
rule.

## Headless output (jd-intake server)

The server pastes this skill, the knowledge base, the profile, the voice files, the addendum,
the learnings, the JD and the evaluation into the prompt. Do not read files and do not ask.
Fill the JSON schema: `paragraphs` (the body paragraphs in order, without greeting or sign-off),
`recipient_lines` (for example `["Hiring Team", "<Employer>"]`), `greeting`, `filename`
(`<file_stem>_<Company>_Cover_Letter.docx`), `combo_used`, and `firm_specific_claim` (the one
sentence about the employer, so it can be checked). The server renders the file; do not write a
docx yourself.
