# jd-intake: notes for Claude Code sessions in this repository

This repository is a job-search assistant: a Chrome extension (`extension/`), a local Flask
server (`server/`), a deterministic resume engine (`engine/`), an optional sponsorship plug-in
(`plugins/sponsorship/`) and Claude Code skills (`.claude/skills/`). `docs/architecture.md`
explains how they fit together.

## If the user is new

If `profile/profile.yaml` does not exist (or `$JDI_PROFILE_DIR/profile.yaml` when that is set),
the user has not been onboarded. Suggest `/onboard` before anything else.

## Rules for every session

1. **Read `profile/learnings.md` first** before writing anything for the user (a resume, a
   cover letter, an email, an evaluation, a form answer). Its rules come from the user's own
   edits and override older rules, newest first. Then read the matching addendum in
   `profile/skills/<skill>.md` if it exists.
2. **Never invent a claim.** Every fact about the user comes from `profile/profile.md`,
   `profile/profile.yaml` or a job's `ANSWERS.md`. A number, tool, title, date or achievement
   that is not there stays off the page until the user confirms it. Never invent a story, even a
   plausible one.
3. **Nothing outbound without the user's approval.** No email, message, form submission or
   application is sent or submitted by a session. The server sends only emails the user approved
   one by one, and never replies to anyone. LinkedIn notes are always sent by the user.
4. **Email is read only.** Code that reads mail must never mark, move, delete or reply. Never
   add a path that writes to someone the user is in process with.
5. **Everything personal lives in `profile/`, `data/` and `.env`**, which git ignores. Never
   write the user's name, contact details, employers, schools, numbers or anyone else's personal
   data into code, tests, docs, skills or examples. Code reads personal values through
   `server/userprofile.py`. Examples and tests use the invented person in `examples/profile/`.
6. **Never ask the user to paste a secret into chat.** Give one command that reads it with
   hidden input and writes it to `.env` (the template is in the `onboard` skill and in
   `docs/outreach.md`).
7. **Optional features stay behind their switch.** `sponsorship`, `outreach`, `email` and
   `alerts` are read with `userprofile.feature(...)`. Off means the UI hides the feature and the
   server refuses it with a message pointing at its doc.
8. **Keep the hard-won checks.** One page and 92 to 98 percent fill, no orphan lines, the
   duplicate audit, numbers traced to the profile, role order, the em dash filter, the
   read-only email rule, approval before sending. Generalize code; do not remove a check.
9. **No em dashes** in anything that ships: resumes, letters, emails, UI text, docs.
10. **Never rank or filter people by ethnicity, nationality or name origin.**
11. **The model writes words; code does what can be checked.** Prefer a deterministic check in
    code over a prompt instruction when both are possible.

## Working on the code

- Python 3.10+, standard library plus the packages in `requirements.txt`. No build step for the
  extension or the dashboard.
- Tests run against the example profile: `cd server && python3 test_api.py` (and the other
  `test_*.py` files); the extension's tests are in `extension/test/`.
- Before committing, run the privacy check (see `CONTRIBUTING.md`).
- Do not restart a running server while `GET /api/busy` is not empty.
- When behavior changes, update the matching file in `docs/` in the same change.
