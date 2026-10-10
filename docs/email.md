# Email (optional)

With email on, jd-intake does two things with your own mailbox:

- **Sends** the outreach emails you approved (and their short follow-ups, which you also
  approve), over SMTP, with your resume attached when one is ready.
- **Reads**, over IMAP and strictly read only, your inbox and your sent mail, to keep your job
  tracker current.

It uses the standard library only (`server/mailer.py`), so any provider that offers SMTP and
IMAP works.

## The read-only rule

This is the most important thing to know about the feature.

- **It never replies to anyone.** There is no code path that answers, forwards or replies to a
  message someone else sent you. The only email it sends is cold outreach you approved one by
  one, and a follow-up to your own earlier email after someone's out-of-office reply, which you
  also approve.
- **It never writes to anyone at a company where you are in process** (heard back, assessment,
  interviewing, offer, on hold). An approved email to such a company is held, not sent, and a
  follow-up is held once the person has written back or you have written to them yourself.
- **Reading never changes your mailbox.** Folders are opened read only and messages are fetched
  without being marked read, moved, flagged or deleted.
- **Every reply to a real conversation is yours.** For a job that reaches an interview, it writes
  a handoff note (`HANDOFF.md` in the job's folder) with the posting, the people, the emails so
  far and the resume you sent, so you can prepare in a Claude chat. It never acts on those
  emails.

## What reading does

Every 30 minutes, and whenever you press "Read inbox now" in the Inbox tab, it reads recent mail and
matches it to your tracked jobs (by the people you wrote to, the company's domain, and the
email's content). Claude sorts each relevant email: rejection, interview, assessment, reply,
out-of-office, search on hold, received (an automated acknowledgement), or other. Then:

- A rejection closes the job; a paused search puts it On hold. Both can be undone.
- An interview, assessment or reply is offered to you as a stage change ("Needs you").
- An out-of-office reply with a return date moves any queued email to that person until they are
  back, and can offer a short follow-up for your approval.
- Bounces mark the address as bad; it is never used again.
- An email about a job you are not tracking can be added as a job with one click.
- Your own sent replies are read so the tracker knows you have already written to someone, and
  so `/learn` can study how you write.

## Set it up

You need an **app password**, not your normal login password. App passwords are separate
passwords for one program, and you can revoke one without changing anything else.

| Provider | App password | SMTP | IMAP | Sent folder |
|---|---|---|---|---|
| Gmail | Turn on 2-Step Verification, then Google Account, Security, App passwords | `smtp.gmail.com`, port 465 | `imap.gmail.com`, port 993 (IMAP must be enabled in Gmail settings) | `[Gmail]/Sent Mail` |
| Outlook.com | Turn on two-step verification, then Microsoft account, Security, Advanced security options, App passwords | `smtp-mail.outlook.com`, port 587 | `outlook.office365.com`, port 993 | `Sent` |
| Fastmail | Settings, Privacy and Security, Integrations, New app password (allow IMAP and SMTP) | `smtp.fastmail.com`, port 465 | `imap.fastmail.com`, port 993 | `Sent` |

Work and school accounts often block app passwords or IMAP; ask your administrator, or use a
personal account. Provider menus change; search their help pages for "app password" if the path
above has moved.

Add each setting to `.env` at the repo root (the key names are in `.env.example`). Settings that
are not secret can be added with a text editor; for the password, use hidden input so it never
appears on screen or in your shell history:

```bash
scripts/set_secret.sh MAIL_PASSWORD
```

The keys:

| Key | Example |
|---|---|
| `MAIL_ADDRESS` | `you@example.com` |
| `MAIL_PASSWORD` | the app password |
| `SMTP_HOST`, `SMTP_PORT` | `smtp.gmail.com`, `465` (465 uses SSL; any other port uses STARTTLS) |
| `IMAP_HOST`, `IMAP_PORT` | `imap.gmail.com`, `993` |
| `MAIL_SENT_FOLDER` | `[Gmail]/Sent Mail` or `Sent` |
| `MAIL_INBOX_FOLDER` (optional) | default `INBOX` |
| `MAIL_SAVE_SENT` (optional) | `true` to file a copy of each sent email in the sent folder, for providers whose SMTP does not do it (Gmail and Outlook do) |

Then set `features: email: true` in `profile/profile.yaml` and restart the server. Press "Read inbox now"
in the Inbox tab to try a read.

## Good practice

- Send from the address you apply with, so replies land in one place.
- Keep the daily cap low (the default is 10) and the send window to working hours.
- Revoke the app password if you stop using the feature.
