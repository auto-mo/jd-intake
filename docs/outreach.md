# Outreach (optional)

After you apply to a job, jd-intake can find people at the company worth writing to and draft
one personal email or LinkedIn note for each. You approve every message. It is off until you
turn it on.

## What happens, step by step

1. **You ask for it.** On an applied job, press Find people in the dashboard and choose how many
   profiles to search (5 to 50) and how many to keep (1 to 10). A second search for the same job
   costs again, so the server asks you to confirm it.
2. **Search.** An Apify actor lists the company's people on LinkedIn by job titles Claude chose
   for the role, plus a second pass for alumni of your schools (`schools` in `profile.yaml`).
   Small companies (under `outreach.small_company` people) also include founders and the CEO.
3. **Rank.** Claude ranks them for this role (recruiters, the likely hiring manager, people on
   the team, alumni) and says why for each. Ranking uses only role, team, seniority, tenure and
   real connections to you, never anything about a person's name or background.
4. **You decide.** Approve or reject each person. Nothing is drafted for someone you rejected.
5. **Email lookup.** For approved people only, a second Apify actor looks for a work email
   address. Only addresses actually found on the company's own domains are used. A guessed
   pattern is never emailed, and personal addresses (Gmail and the like) are never used. People
   without a found address get a LinkedIn note instead.
6. **Draft, check, audit, fact-check.** Claude writes one draft per person using your profile,
   your voice files and your recent edits. Code checks length, greeting, links and banned
   phrases; Claude then audits each draft for "would you send this unchanged" and fact-checks
   every claim: about you against `profile.md`, about the reader against their profile, about
   the company against the posting. Weak drafts get one revision. A claim that is still
   unsupported is shown on the draft.
7. **You approve.** Edit any draft in the dashboard, then Approve. Approved emails go into a
   queue and are sent only on weekdays inside `outreach.send_window` (your timezone), at most
   `outreach.daily_cap` a day, `outreach.gap_minutes` apart. You can pull one back before it goes.
8. **LinkedIn notes are never sent by software.** Copy them from the dashboard or the side
   panel's LinkedIn mode and send them yourself.

Sending email needs the email feature too ([email.md](email.md)). Without it you can still
search, rank and draft, and copy the drafts by hand.

**Auto mode** (a switch in the dashboard, off by default) queues an email without waiting for
you only when its audit score is 80 or more, it has no unsupported claim, and the address was
confirmed. Everything else still waits for you. Leave it off until you trust the drafts.

Every draft you edit before approving, and every draft you skip, goes to the learning inbox, so
`/learn` can turn your edits into rules ([how-it-learns.md](how-it-learns.md)).

## Set up Apify

1. Create an account at https://apify.com and add a payment method or prepaid credit. Set a
   monthly usage limit in the Apify console; it is the simplest guard against surprises.
2. Copy your API token from the Apify console (Settings, then API and Integrations).
3. Save it to `.env` with hidden input (run from the repo root):

   ```bash
   scripts/set_secret.sh APIFY_TOKEN
   ```

4. In `profile/profile.yaml` set `features: outreach: true` and fill the `outreach` block:
   `timezone`, `send_window`, `daily_cap`, `gap_minutes`, `small_company`, `email_words` and
   your `signature`.
5. Restart the server.

## What it costs

Apify bills your account per result. The actors this project uses, and the prices their
listings showed when the code was written (check the actor pages for current prices):

| Step | Actor | Billed |
|---|---|---|
| People search | `harvestapi~linkedin-company-employees`, full profiles | about $8 per 1,000 profiles returned |
| Email lookup | `vulnv~linkedin-email-finder` | about $0.03 per address found, nothing for a miss |
| Fallback lookup | `crustapi~linkedin-profile-scraper-email-finder` | a fraction of a cent per person, more for a verified address |

In practice a 25-profile search with a few lookups is cents to a few tens of cents. The
dashboard's Monitor tab shows what every run actually cost, read back from Apify. Claude calls
for ranking and drafting are separate (your plan, or your API key; drafting is the most
model-heavy step in the whole tool, see [api-key-mode.md](api-key-mode.md)).

Claude never spends money: only server code calls Apify, and only after your click.

## Your responsibility

- **LinkedIn.** Searching LinkedIn through a third-party scraper may conflict with LinkedIn's
  User Agreement. You decide whether to use it, and the risk to your account is yours.
- **Anti-spam law.** Cold email is regulated (for example CAN-SPAM in the US, GDPR and PECR in
  the UK and EU, CASL in Canada). Write to people for a real, individual reason, identify
  yourself, keep volumes low, and stop when someone asks you to. The default cap of 10 emails a
  day exists for a reason.
- **Your mail provider's limits.** Providers watch for bulk sending from personal accounts.
- **Accuracy.** The drafts are checked against your profile, but you are the one sending them.
  Read every one.

## Changing how drafts are written

- Your voice: `profile/voice.md` (rules and banned phrases) and `profile/voice-examples.md`
  (three to ten real emails you wrote). Real examples teach the drafter more than rules do.
- Your edits: run `/learn` after editing drafts; the rules land in `profile/learnings.md`, which
  the drafter reads first.
- Redraft one message with a note from its Redraft box. To redraft everything waiting for review
  with the current rules: `python3 server/tools/redraft.py --all`. To re-run only the audit:
  `python3 server/tools/rescore.py`. To list unsupported claims among waiting drafts:
  `python3 server/tools/factcheck.py`.
