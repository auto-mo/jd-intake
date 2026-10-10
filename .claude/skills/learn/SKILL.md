---
name: learn
description: >
  Self-learning for jd-intake. Turns the user's own edits, overrides and rejections into short,
  scoped rules in profile/learnings.md (and voice rules in profile/voice.md) that every skill and
  every server prompt reads first. Use when the user types /learn, says "learn from this", "see
  what I changed", "I edited the draft", "update my voice", shows their own final version of
  something drafted for them (pasted text, a screenshot, an edited file), explains why they
  rejected a draft, or when data/learning-inbox.jsonl has unprocessed events.
---

# learn

The user's edits to a draft are the best evidence there is of how they want to come across.
This skill captures every one of them as a rule, so the next draft starts closer.

One voice, different registers: the user writes differently to a recruiter, a hiring manager, a
peer and on a resume. Every rule says which audience it applies to. Never generalize one edit to
every kind of writing.

The profile directory is `profile/` at the repo root, or `$JDI_PROFILE_DIR` when set. The data
directory is `data/`, or `$JDI_DATA_DIR` when set.

## Sources

1. **The learning inbox**, `data/learning-inbox.jsonl`, written by the server. One JSON object
   per line: `{"at", "kind", "job_id", "before", "after", "context"}`.

   | kind | before | after | What it teaches |
   |---|---|---|---|
   | `draft_edited` | the outreach draft | what was actually sent | voice, by reader type |
   | `resume_feedback` | (may be empty) | the user's revision feedback on a resume | resume rules |
   | `cover_feedback` | (may be empty) | the user's revision feedback on a cover letter | cover letter rules |
   | `eval_override` | the evaluation (score, recommendation) | what the user did instead (applied below the threshold, or skipped above it) | scoring rules |
   | `draft_rejected` | the draft | the reason, if one was given | what never to write |

   `context` carries details such as the reader type, the role or the company; use it to scope
   the rule. An event is processed when its key (`<at>|<kind>|<job_id>`) is a line in
   `data/learning-inbox.processed`. Never edit or rewrite `learning-inbox.jsonl` itself: the
   server appends to it while it runs.

2. **Something the user shows you in this conversation**: their final version of a draft
   (pasted, a screenshot, a file), a `*_edited` copy of a generated file, or an explanation of
   why they rejected something. Get both versions: the draft (from this conversation, the
   application folder, or ask for it) and their final.

Messages the user types to you in chat are not writing samples. Learn only from text they meant
to send, submit or publish, and from reasons they state.

## Steps

1. **Read first:** `profile/learnings.md` and `profile/voice.md`, so you know the rules already
   in force.

2. **Collect the events.** Read the inbox and the processed file; take every unprocessed event,
   oldest first. Add anything the user showed you.

3. **Diff each one line by line.** List every change, however small: words added or cut,
   greeting and sign-off, links, questions turned into statements or the reverse, hedges added
   or removed, names or reasons dropped, word swaps, punctuation, length, order. For an image,
   read it closely, including links, greeting and sign-off. Unchanged parts are evidence too:
   what the user kept, they approve of.

4. **Name the audience and the kind of writing** for each: cold email to a recruiter, to a
   hiring manager, to a founder, to a peer; LinkedIn note; follow-up; resume; cover letter;
   form answer; evaluation. This is the rule's scope.

5. **Turn each change into a rule.** One line, in the form
   `for <scope>: <rule>`, with the evidence as a short before and after quote. Say "one data
   point" when it is one. When the reason for an edit is unclear, say the reason is inferred,
   and ask the user in one line rather than guess. Never present an invented reason as theirs;
   quote them when they gave one.

   For `eval_override` events, the rule is about scoring: what the evaluation weighed that the
   user did not, or the reverse ("for evaluations: a role titled X with Y is worth applying to
   even when the level reads as a stretch"). One override is a data point, not a policy.

   For `draft_rejected` with no reason, record only a pattern you can see across several
   rejections; a single unexplained rejection teaches nothing on its own.

6. **Check for conflicts** with `learnings.md`, `voice.md` and the addenda in
   `profile/skills/`. The newer edit wins for its scope: mark the old rule
   `(superseded YYYY-MM-DD for <scope>)` rather than deleting it.

7. **Consolidate.** If a new rule repeats an existing one, do not add a duplicate: add the date
   to the existing entry's evidence. When the same rule has been seen three or more times,
   promote it: move it to a "Standing rules" section at the top of `learnings.md`, worded once,
   with its scope. Merge near-duplicates into one clear rule.

8. **Write it down.**
   - Append to `profile/learnings.md`, newest first, below any Standing rules section:
     ```
     ## YYYY-MM-DD · <scope> · from <source: an edited email, resume feedback, an override...>
     - <rule>. Evidence: "<before>" became "<after>".
     ```
   - For voice changes (wording, register, greeting, sign-off, length, tone), also add or update
     the rule in `profile/voice.md` under Rules, scoped, and add any phrase the user cut more
     than once to Banned phrases.
   - When the user wrote or rewrote a whole email themselves and it is a good example of their
     voice, ask whether to add it to `profile/voice-examples.md` (keep three to ten; replace the
     weakest when full).
   - Facts the user corrected (a wrong number, a claim they cannot make) go to
     `profile/profile.md`, after asking. A fact is not a style rule.

9. **Mark events processed:** append each event's key, one per line, to
   `data/learning-inbox.processed`.

10. **Decide whether the skills need rebuilding.** If a rule was promoted to Standing rules, a
    scoring rule changed, a claim rule changed, or more than five new rules were added, run the
    `skill-builder` skill now (or tell the user to, if they would rather review first).

11. **Report briefly:** how many events were processed, the rules added (one line each with
    scope), anything consolidated or superseded, whether skill-builder ran, and at most one
    question about an edit whose reason was unclear.

## Rules

- Keep entries short: rule, evidence, scope. No essays.
- No em dashes in anything written to the profile.
- Never store a secret, a password or another person's contact details in a learning. Refer to
  people by role ("the recruiter"), not by name.
- Never change `profile.yaml` feature switches or settings from a learning.
- Learnings are rules about how to write and judge, never new claims about the user's
  experience. A new claim needs the user's confirmation and goes to `profile.md`.
