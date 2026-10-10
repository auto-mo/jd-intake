#!/usr/bin/env python3
"""Report, for every draft waiting for review, the claims its sources do not support (you against
profile.md, the recipient against their profile, the company against the posting) and whether it
would work for anyone at the company. The same check the pipeline runs (app._factcheck_round).
Read-only: prints one JSON line per draft and changes nothing. Claude only, nothing is sent.

    python3 tools/factcheck.py <job_id> [<job_id> ...]     # no ids: every job with drafts in review
"""
import importlib.util, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE); sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("app_tool", os.path.join(HERE, "app.py"))
app = importlib.util.module_from_spec(spec); sys.modules["app_tool"] = app; spec.loader.exec_module(app)

with app.db() as con:
    jobs = sys.argv[1:] or [r[0] for r in con.execute("SELECT DISTINCT job_id FROM messages WHERE status='review'")]
for jid in jobs:
    job = app.outreach_job(app.load_job(jid))
    with app.db() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT m.channel, m.draft, p.name, p.title, p.linkedin_url, p.email, p.raw FROM messages m "
            "JOIN people p ON p.id=m.person_id WHERE m.job_id=? AND m.status='review'", (jid,))]
    checked = [({"linkedin_url": r["linkedin_url"], "name": r["name"], "title": r["title"],
                 "email": r["email"] if r["channel"] == "email" else None,
                 "ctx": json.loads(r["raw"] or "{}").get("ctx") or {}},
                {"body": r["draft"] if r["channel"] == "email" else "", "dm": r["draft"] if r["channel"] != "email" else ""}, [])
               for r in rows]
    facts = app._factcheck_round(job, app._read(os.path.join(job["folder"], "JD.md")), checked)
    for p_, _, _ in checked:
        c = facts.get(p_["linkedin_url"]) or {}
        print(json.dumps({"job": jid, "name": p_["name"], "unsupported": c.get("unsupported") or [],
                          "fits_anyone": bool(c.get("fits_anyone")), "use_instead": c.get("use_instead") or ""}), flush=True)
