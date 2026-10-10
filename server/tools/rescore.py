#!/usr/bin/env python3
"""Re-score every draft waiting for review with the current audit (one batch per job, so it can judge the
set together) and recompute the "opens like" flags. Claude only: nothing is redrafted, paid for or sent.
Use it after changing the audit prompt.

    python3 tools/rescore.py [<job_id> ...]     # no ids: every job with drafts in review
"""
import importlib.util, sys, os, json
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE); sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("app_tool", os.path.join(HERE, "app.py")); app = importlib.util.module_from_spec(spec)
sys.modules["app_tool"] = app; spec.loader.exec_module(app)
o = app.outreach
with app.db() as con:
    jobs = sys.argv[1:] or [r[0] for r in con.execute("SELECT DISTINCT job_id FROM messages WHERE status='review'")]
for jid in jobs:
    job = app.outreach_job(app.load_job(jid))
    with app.db() as con:
        rows = [dict(r) for r in con.execute("SELECT m.id mid, m.channel, m.subject, m.draft, m.validator_notes vn, p.* FROM messages m "
                                             "JOIN people p ON p.id=m.person_id WHERE m.job_id=? AND m.status='review' ORDER BY p.rank", (jid,))]
    checked = []
    for r in rows:
        raw = json.loads(r.get("raw") or "{}")
        is_email = r["channel"] == "email"
        p_ = {"linkedin_url": r["linkedin_url"], "name": r["name"], "title": r["title"], "headline": raw.get("headline", ""),
              "education": raw.get("education", ""), "email": r["email"] if is_email else None, "ctx": raw.get("ctx") or {}}
        checked.append((p_, {"subject": r["subject"] or "", "body": r["draft"] if is_email else "", "dm": "" if is_email else r["draft"]}, r))
    audits = app._audit_round(job, [(p_, v, []) for p_, v, _ in checked], app.voice_block(), app.recent_edits())
    out = []
    with app.db() as con:
        for i, (p_, v, r) in enumerate(checked):
            notes = [n for n in json.loads(r["vn"] or "[]") if not n.startswith("opens like")]
            mine = v["body"] or v["dm"]
            twin = next((q for q, w, rr in checked[:i] if rr["channel"] == r["channel"]
                         and o.openings_alike(mine, w["body"] or w["dm"])), None)
            if twin:
                notes.append(f"opens like the draft to {twin['name']}; change one first line")
            a = audits.get(p_["linkedin_url"]) or {}
            con.execute("UPDATE messages SET audit_score=?, audit_notes=?, validator_notes=? WHERE id=?",
                        (app._score(a), json.dumps(a.get("notes") or []), json.dumps(notes), r["mid"]))
            out.append((r["name"], r["channel"][0], app._score(a), bool(twin)))
    print(jid[8:45], out, flush=True)
