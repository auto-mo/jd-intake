# Contributing

Thanks for helping. Two things matter more than anything else here: keep personal data out of
the repository, and keep the checks that stop the tool from inventing claims or sending things
without approval. `CLAUDE.md` lists the rules; they apply to people as much as to Claude.

## Install the privacy check first

`scripts/privacy_scan.py` blocks a commit that contains a secret (API keys, tokens, private
keys) or any of your own identifiers.

1. Make a list of your identifiers, one regular expression per line: your name, emails, phone,
   employers, schools, people you have written to. Keep it **outside** the repository, because
   the list itself is personal.
2. Point the check at it and install the hook:

   ```bash
   export JDI_DENYLIST=/path/outside/the/repo/my-denylist.txt     # add to your shell profile
   ln -s ../../scripts/privacy_scan.py .git/hooks/pre-commit
   ```

3. Check the whole tree any time with `python3 scripts/privacy_scan.py --all`.

## Keep personal data out

- Your profile, your jobs and your secrets live in `profile/`, `data/` and `.env`, which git
  ignores. Never move them, copy from them, or paste from them into code, tests, docs or skills.
- Examples and tests use the invented person in `examples/profile/`. Add to it with invented
  names and numbers (`example.com` addresses, `555` phone numbers).
- Real postings, recruiter emails and LinkedIn profiles are other people's data; do not commit
  them as fixtures. Invent them.

## Before you open a pull request

- Run the tests: `cd server && python3 test_api.py && python3 test_outreach_validate.py && python3 test_outreach_flow.py && python3 test_inbox.py`, and the extension's tests in `extension/test/`.
- Update the matching page in `docs/` when behavior changes.
- No em dashes in anything user-facing.
- Keep pull requests to one change each.
