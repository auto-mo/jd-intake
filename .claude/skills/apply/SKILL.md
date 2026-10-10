---
name: apply
description: >
  DRAFT, not wired to the server. Fill a job application in the user's own Chrome through Claude
  in Chrome after resume-build has produced the files: open the apply link, fill the form from
  profile/application-answers.md and profile/profile.md, upload the resume and cover letter, and
  stop before Submit. Invoke on "apply", "fill the application", or "fill this form".
---

# apply (draft)

Status: written ahead of a browser integration and not run by the server. Use it interactively
in a Claude Code session that has Claude in Chrome connected. The user always clicks Submit.

## Read first, every time

The profile directory is `profile/` at the repo root, or `$JDI_PROFILE_DIR` when set.

1. `profile/learnings.md`: rules from the user's own edits, newest first. Rules scoped to forms
   or screening answers apply here.
2. `profile/skills/apply.md`, if it exists: the user's addendum from `skill-builder`.
3. `profile/application-answers.md`: the standard answers (work authorization, sponsorship,
   salary expectations, start date, relocation, demographic questions, how they heard).
4. `profile/profile.md` and `standing_facts` in `profile/profile.yaml`: facts for anything else.

## Inputs

- The application folder: `JD.md` (URL, title, company), the built `<file_stem>_<Company>.pdf`
  and, if present, `<file_stem>_<Company>_Cover_Letter.pdf`.

## Procedure

1. Open the apply link from `JD.md` in a new tab. If it is a job-board posting, follow the Apply
   button to the employer's applicant tracking system; prefer it over a one-click apply when
   both exist.
2. If the page asks to create an account or log in, stop and report "needs login" with the URL.
   Never create an account, never type a password, never solve a CAPTCHA.
3. If the user has an autofill extension and its button is present, the user may ask you to
   click it first.
4. When a form wants resume text pasted as plain text, paste plain text blocks with any
   non-ASCII currency symbols spelled out.
5. Walk every field on every step. Fill from `application-answers.md` first, then `profile.md`.
   Free-text screening questions: two to four sentences, facts from the profile only, no em
   dashes, no buzzwords. A question those two files cannot answer is left blank and reported,
   never guessed.
6. Work authorization and sponsorship questions are answered only from
   `application-answers.md`, word for word in meaning. Never infer them.
7. Upload the resume PDF to the resume field and the cover letter PDF to the cover letter field
   if the form has one. If the form takes a single document, upload the resume only.
8. Stop on the review or final step, before any button labelled Submit, Apply or Send. Save a
   screenshot into the application folder as `application-review.png`.
9. Report: the URL of the review page, the fields left blank, and anything unusual. The user
   clicks Submit.

## Never

- Submit, send, or confirm anything.
- Enter payment details, government ID numbers, or passwords.
- Change account settings or accept terms on the user's behalf.
- Invent an answer to a screening question.
