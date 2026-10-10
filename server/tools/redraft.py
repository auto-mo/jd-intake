#!/usr/bin/env python3
"""Redraft, in place, every email and LinkedIn note still waiting for your review, with the current
prompts, person context and model (app.outreach_model()). Claude only: no paid calls, nothing is sent.

    python3 tools/redraft.py <job_id> [<job_id> ...]     # one process per job; run several in parallel
    python3 tools/redraft.py --all                        # every job with drafts in review, one by one

Run it while no outreach job is searching, ranking or drafting, after restarting the server if the
prompts changed. It prints each new draft with its audit score.
"""
import importlib.util, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE); sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("app_tool", os.path.join(HERE, "app.py"))
app = importlib.util.module_from_spec(spec); sys.modules["app_tool"] = app; spec.loader.exec_module(app)
from outreach_validate import AI_PHRASES, validate_and_clean  # noqa: E402

jobs = sys.argv[1:]
if jobs == ["--all"]:
    with app.db() as con:
        jobs = [r[0] for r in con.execute("SELECT DISTINCT job_id FROM messages WHERE status='review'")]
if not jobs:
    sys.exit(__doc__)
for jid in jobs:
    job = app.load_job(jid)
    people, replace = [], {}
    with app.db() as con:
        for r in con.execute("SELECT p.*, m.id mid FROM people p JOIN messages m ON m.person_id=p.id "
                             "WHERE p.job_id=? AND m.status='review' ORDER BY p.rank", (jid,)):
            r = dict(r); raw = json.loads(r.get("raw") or "{}")
            people.append({"id": r["id"], "name": r["name"], "first": raw.get("first") or r["name"].split()[0],
                           "title": r["title"], "headline": raw.get("headline", ""), "linkedin_url": r["linkedin_url"],
                           "location": r["location"], "education": raw.get("education", ""), "email": r["email"],
                           "email_source": r["email_source"], "why": r["why"], "priority": raw.get("priority", ""),
                           "ctx": raw.get("ctx") or {}})
            replace[r["id"]] = r["mid"]
    if not people:
        print(f"{jid}: nothing waiting for review"); continue
    app._draft_and_store(job, app._read(os.path.join(job["folder"], "JD.md")), job.get("evaluation") or {}, people,
                         validate_and_clean, replace=replace)
    with app.db() as con:
        for r in con.execute("SELECT p.name, p.title, m.channel, m.subject, m.draft, m.audit_score, m.model FROM messages m "
                             "JOIN people p ON p.id=m.person_id WHERE m.job_id=? AND m.status='review' ORDER BY p.rank", (jid,)):
            body = r[4] or ""
            print("=" * 90)
            print(f"{job['company']} | {r[0]} ({r[1]}) | {r[2]} | audit {r[5]} | {len(body.split())} words | {r[6]} | "
                  f"tells: {[m.group(0) for m in AI_PHRASES.finditer(body)]}")
            if r[3]:
                print("SUBJECT:", r[3])
            print(body)
