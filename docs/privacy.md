# Privacy

jd-intake runs on your machine and has no account, no telemetry and no server of its own.
This page lists everything it stores and everything that leaves your machine.

## What stays on your machine

| Where | What |
|---|---|
| `profile/` | Your profile: identity and contact details, every claim about your experience, base resumes, cover letter blocks, voice rules and example emails, form answers, learnings, skill addenda |
| `data/jobhunt.db` | Every job you captured, its evaluation, stages, actions, people found, drafts, sent messages, inbox rows |
| `data/applications/<job>/` | The posting (`JD.md`), the evaluation, your answers, the built resume and cover letter, notes, the interview handoff note |
| `data/learning-inbox.jsonl` | Your edits and decisions, waiting for `/learn` |
| `.env` | Secrets for optional features |
| Your drop folder (`JDI_DROP_DIR`, default the Desktop) | Copies of finished PDFs, removed when you mark the job submitted |

`profile/`, `data/` and `.env` are in `.gitignore`, so a commit never includes them. The server
listens only on `127.0.0.1` and refuses requests from web pages, so other sites in your browser
cannot read your data through it.

## What leaves your machine, and to whom

**Anthropic (always).** Each Claude call sends its prompt: for an evaluation, the posting and
your profile; for a build, also the base resume and your answers; for outreach, the person's
public profile details and your voice examples; for inbox reading, the emails being sorted.
Anthropic's terms for your Claude plan or API account apply
(https://www.anthropic.com/legal). Claude Code may also keep local session files on your
machine.

**The job sites you browse (always).** The extension reads pages you are already looking at.
It does not send anything to them.

**Apify (outreach only).** The company's LinkedIn page address, the job titles to search, your
schools (for the alumni search), and the LinkedIn addresses of people you approved for an email
lookup. Apify's terms and privacy policy apply.

**Your mail provider (email only).** The emails you approved, sent from your account, and
read-only access to your inbox and sent mail over IMAP. Mail is read on your machine (or your
server); only the emails being sorted go to Anthropic, as above.

**Telegram (alerts only).** Short failure messages, which may name a company and role.

**Nobody else.** Nothing is sent to the authors of this project.

## Other people's data

Outreach stores public profile details of people you chose to contact, and the inbox stores
emails people sent you. Search only companies you applied to, and approve only the people you
mean to write to. If someone asks you to stop contacting them, skip their drafts and do not search them again.

## Keeping personal data out of the repository

If you change the code and commit, install the pre-commit privacy check described in
[CONTRIBUTING.md](../CONTRIBUTING.md). It blocks commits containing secrets, and the
identifiers you list in a private file kept outside the repository.
