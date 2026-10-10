# Run it with an Anthropic API key

If you do not have a Claude subscription, Claude Code can use an Anthropic API key instead.
Everything works the same; the difference is that every model call is billed to your API
account per token.

## Set it up

1. Create a key in the Anthropic Console (https://console.anthropic.com/) and add a spending
   limit there. A limit is the simplest protection against surprises.
2. Make the key available to the server's environment. The server starts `claude -p` for every
   model call, and Claude Code uses `ANTHROPIC_API_KEY` when it is set.

   For a one-off run:

   ```bash
   read -rsp "Paste your Anthropic API key, then Enter: " ANTHROPIC_API_KEY; echo
   export ANTHROPIC_API_KEY
   python3 server/app.py
   ```

   For a server that starts at login, put it in the launchd `EnvironmentVariables` or the
   systemd `Environment=` line (see [run-locally.md](run-locally.md)), in a file only you can
   read. Never commit it; `scripts/privacy_scan.py` blocks a commit that contains one.

3. Check it:

   ```bash
   claude -p "Reply ok." --tools ""
   ```

Note: if you also have a subscription login, an `ANTHROPIC_API_KEY` in the environment can take
precedence over it. Unset the variable when you want to go back to your plan, and check which
one is in use with `claude` then `/status`.

## What it costs

Prices per token are on [Anthropic's pricing page](https://www.anthropic.com/pricing); they
change, so this page does not repeat them. What drives the bill is how many calls each action
makes, how much text goes into each, and which model runs it.

| Action | Model calls | Model (default, from `profile.yaml`) | Relative cost |
|---|---|---|---|
| Evaluate a posting | 1, plus at most 1 short call to pick a resume approach when it is a close call | `evaluate` (sonnet), `planner` (opus) | Low |
| Build a tailored resume | 1 writing call, up to 2 short fix rounds, at most 1 duplicate repair | `build` (sonnet) | Low to medium |
| Base resume (no tailoring) | 0 | | Free |
| Cover letter | 1, up to 2 short fix rounds | `build` (sonnet) | Low |
| Revise a resume or letter from your feedback | 1 or 2 | `build` (sonnet) | Low |
| Ask a question in the side panel | 1 | `ask` (opus) | Low to medium |
| Interview handoff note | 1 short call per update | `handoff` (sonnet) | Low |
| Inbox reading (email on) | a short sorting call when new mail arrives, checked every 30 minutes | `inbox` (sonnet) | Low, but steady |
| Outreach for one job | search titles, ranking, drafting for every person, an audit, a fact-check and a revision round | `outreach` (opus) | The highest by far |

Each evaluation, build and cover letter stores Claude's own cost estimate (`cost_usd`) on the
job, so after a handful of jobs you can see what you are really spending.

To spend less:
- Use `sonnet` for `outreach`, `ask` and `planner` in the `models` block of
  `profile/profile.yaml`. The drafts are a little less polished; the checks still run.
- Leave Auto off in the side panel, so only postings you choose are evaluated.
- Use a base resume when the evaluation says Base.
