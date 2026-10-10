# Visa sponsorship checks (optional)

For people who need an employer to sponsor a US work visa. Off by default, and irrelevant if
you do not need sponsorship.

## What it does

- **Past filings.** For each captured job, it looks up the employer in a summary of US
  Department of Labor labor condition application (LCA) disclosure data: how many filings, how
  many certified, and the trend between the last two fiscal years. The result is a line in the
  job's `JD.md` header and a chip in the side panel ("Sponsors", "Sponsored only N times",
  "Sponsors, but shrinking", "No LCA record"). The lookup is plain code, no model.
- **Posting language.** Code reads the posting for "will not sponsor", "must be authorized
  without sponsorship" and similar wording before Claude sees it, and the evaluation quotes any
  softer wording so you can judge it yourself.
- **Published exceptions.** Some employers say they do not sponsor except in named groups.
  `plugins/sponsorship/sponsorship-policies.yaml` lists those exceptions, with the source and the
  date read, so boilerplate does not turn into a blanket skip.

A missing record is a weak signal for a startup or a subsidiary that files under another name,
and a stronger one for a large company. Sponsorship is a flag in the evaluation, never an
automatic skip unless the posting is absolute.

## Turn it on

1. In `profile/profile.yaml`, set `work_authorization: needs_sponsorship: true` and write a
   one-line `summary` (it is what the application answers use).
2. Get the data. The lookup reads an employer summary built from the DOL Office of Foreign
   Labor Certification performance data (https://www.dol.gov/agencies/eta/foreign-labor/performance).
   `plugins/sponsorship/lca-schema.md` describes the file it expects, its columns, and where to
   put it. The first lookup converts it into a small SQLite cache next to the plug-in; later
   lookups are instant. The data is public; download a fresh year when the DOL publishes one.
3. Set `features: sponsorship: true` in `profile/profile.yaml` and restart the server.

If the data file is missing, the job header says so instead of guessing.

## Adding an employer's exceptions

Add an entry to `plugins/sponsorship/sponsorship-policies.yaml` only from the employer's own
published policy, with its URL and the date you read it. Make group names specific enough that
they cannot match ordinary sentences in a posting.

## Limits

LCA filings show that an employer has filed for a role, not that it will sponsor you. Postings
change, policies change, and a recruiter's answer beats any database. Ask early.
