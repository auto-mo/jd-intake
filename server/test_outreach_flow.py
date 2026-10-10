#!/usr/bin/env python3
"""End-to-end test of the outreach pipeline with the model stubbed and every paid call faked.

No model calls, no Apify, no email: the pipeline runs in dry-run mode, run_claude is replaced by a stub that
answers by schema, and the sender's mailer.send is a recorder. Example profile, temporary data, as in test_api.py.

Run:  python3 test_outreach_flow.py
"""
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tests_common as tc  # noqa: E402

TMP = tc.setup_env("jdintake-flow-")
app = tc.load_app("app_flow", TMP)
HERE = tc.HERE
tc.feature(app, outreach=True, email=True)       # people search, drafting and the sender are optional features
app.OUTREACH_DRY_RUN = True
app.backfill_company_url = lambda job_id: None   # no background lookups racing the tests
app.init_db()
c = app.app.test_client()
results = []
calls = {"titles": 0, "rank": 0, "drafts": 0, "audit": 0, "repair": 0}
low_once = {}     # the first person of the first audit scores 50 once, then 85 after a revision


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def link_in(prompt):
    """What the drafter was told to name the role with: the careers link, else 'job ID <id>'."""
    m = re.search(r"the careers page link (\S+?)[.;]?\s", prompt)
    if m:
        return m.group(1)
    m = re.search(r"\(job ID ([\w-]+)\)", prompt)
    return f"job ID {m.group(1)}" if m else "no link"


def body_for(first, url):
    return (f"Hi {first},\n\nI hope things are going well on your side, and thank you for giving a minute to a note from someone you have not met yet. I recently applied to the Strategy Lead role at Acme Health ({url}) and wanted to "
            "reach out directly. The posting's focus on consolidating payer analytics across regions, and on turning "
            "operational data into decisions leadership can act on, is the work I most want to be doing next.\n\n"
            "At Northbridge Logistics I led a network redesign study across 40 warehouses, "
            "separating what could change this quarter from what needed better data first. The part I enjoyed most was sitting with the account teams and turning a messy spreadsheet into a model they trusted enough to use in front of a client.\n\n"
            "Would you be open to passing my resume along to the hiring team, or flagging my application "
            "internally? My resume is attached.")


def fake_claude(prompt, schema=None, **kw):
    """Answers by schema, the way the real calls are told to answer."""
    urls = re.findall(r'"linkedin_url": "([^"]+)"', prompt)
    if schema is app.outreach.TITLES_SCHEMA:
        calls["titles"] += 1
        return {"structured": {"titles": ["Talent Acquisition Partner", "Director, Strategy"]}}
    if schema is app.outreach.RANK_SCHEMA:
        calls["rank"] += 1
        return {"structured": {"selected": [{"linkedin_url": u, "why": f"Reason {i}", "priority": "Recruiter", "fit": 9 - i}
                                            for i, u in enumerate(urls[:3])]}}
    if schema is app.outreach.DRAFTS_SCHEMA:
        calls["drafts"] += 1
        firsts = re.findall(r'"first_name": "([^"]+)"', prompt)
        job_url = link_in(prompt)
        fb = "Tighter. " if "FEEDBACK ON THE LAST VERSION" in prompt else ""
        if "THIS IS A REVISION" in prompt:
            fb = "Revised. "
        drafts = []
        for i, (u, f) in enumerate(zip(urls, firsts)):
            b = body_for(f, job_url)
            if i == 1 and not fb:
                b = b.replace(f"Hi {f},", "Hello there,")        # fails the greeting check -> repair
            drafts.append({"linkedin_url": u, "email_subject": "Strategy Lead at Acme Health",
                           "email_body": b.replace("wanted to reach out directly.", "wanted to reach out directly. " + fb) if fb else b,
                           "linkedin_dm": f"Hi {f}, I applied to Strategy Lead at Acme Health and would value connecting."})
        return {"structured": {"drafts": drafts}}
    if schema is app.outreach.FACTCHECK_SCHEMA:
        calls["fact"] = calls.get("fact", 0) + 1
        bad = fact_mode.get("bad")            # a name whose draft carries an invented claim
        out = []
        for u in re.findall(r'"linkedin_url": "([^"]+)"', prompt):
            flagged = bool(bad) and bad in u and (fact_mode.get("sticky") or not fact_mode.get("seen"))
            if flagged:
                fact_mode["seen"] = True
            out.append({"linkedin_url": u, "unsupported": ["'I sat with the users every week' (not in the facts)"] if flagged else [],
                        "fits_anyone": False})
        return {"structured": {"checks": out}}
    if schema is app.outreach.AUDIT_SCHEMA:
        calls["audit"] += 1
        out = []
        for i, u in enumerate(urls):
            if not low_once and i == 0:
                low_once[u] = 1
                out.append({"linkedin_url": u, "score": 50, "notes": ["Two credentials; the rule is one."]})
            elif u in low_once:
                out.append({"linkedin_url": u, "score": 85, "notes": ["One credential now."]})
            else:
                out.append({"linkedin_url": u, "score": 90, "notes": ["Middle paragraph is about them."]})
        return {"structured": {"audits": out}}
    calls["repair"] += 1               # the repair schema is an inline dict
    first = re.search(r"Recipient first name: (\S+)\.", prompt).group(1)
    job_url = link_in(prompt)
    return {"structured": {"email_subject": "Strategy Lead at Acme Health", "email_body": body_for(first, job_url),
                           "linkedin_dm": f"Hi {first}, I applied and would value connecting."}}


fact_mode = {}
app.run_claude = fake_claude


def post(path, body=None, headers=None):
    r = c.post(path, json=body or {}, headers=headers or {})
    return r.status_code, r.get_json()


def get(path):
    r = c.get(path)
    return r.status_code, r.get_json()


def wait_state(jid, want, secs=20):
    for _ in range(secs * 10):
        st = (app.load_job(jid).get("outreach") or {}).get("state")
        if st in want:
            return st
        time.sleep(0.1)
    return (app.load_job(jid).get("outreach") or {}).get("state")


post("/settings", {"auto": False})

# ---- the email verification rule ------------------------------------------------------------------------
o = app.outreach
check("A guessed address that spells the name is kept", o.name_fits_email("Jordan Lee", "jordan.lee@globex.example")
      and o.name_fits_email("Aaron Brennan", "abrennan@x.com") and o.name_fits_email("Elin Mae Søndergaard", "elin.sondergaard@globex.example"))
check("A mangled or unrelated guess is rejected", not o.name_fits_email("Elin Mae Søndergaard", "elin.maesndrgd@globex.example")
      and not o.name_fits_email("Jordan Lee", "info@globex.example") and not o.name_fits_email("Vic Tran", "victor.t@globex.example")
      and not o.name_fits_email("Riley P.", "riley.p@getumbrella.example"))
_ppl = [{"name": "Jordan Lee", "linkedin_url": "https://www.linkedin.com/in/jordan-l"},
        {"name": "Elin Mae Søndergaard", "linkedin_url": "https://www.linkedin.com/in/elin-s"},
        {"name": "Priya Shah", "linkedin_url": "https://www.linkedin.com/in/priya-s/"}]
_got = o.emails_from_lookup([
    {"inputUrl": "https://www.linkedin.com/in/jordan-l", "email": "jordan.lee@globex.example", "emailStatus": "pattern-likely"},
    {"inputUrl": "https://www.linkedin.com/in/elin-s", "email": "elin.maesndrgd@globex.example", "emailStatus": "pattern-likely"},
    {"inputUrl": "https://www.linkedin.com/in/priya-s", "email": "priya.shah@globex.example", "emailStatus": "verified"}], _ppl)
check("Lookup results: verified kept, name-fitting guess kept as a guess, mangled guess dropped",
      _got == {"https://www.linkedin.com/in/jordan-l": ("jordan.lee@globex.example", "pattern"),
               "https://www.linkedin.com/in/priya-s/": ("priya.shah@globex.example", "verified")}, str(_got))
CAP = {"url": "https://www.linkedin.com/jobs/view/9300001/", "title": "Strategy Lead", "company": "Acme Health",
       "location": "Chicago, IL (Hybrid)", "text": "Strategy role. " * 300, "source": "linkedin"}

# ---- the feature switch ------------------------------------------------------------------------------
_off = tc.feature(app, outreach=False)
st, j0 = post("/jobs", dict(CAP, url="https://www.linkedin.com/jobs/view/9300099/", text="Off role. " * 400, company="Offco"))
app.update_job(j0["id"], status="applied", company_url="https://www.linkedin.com/company/offco")
st, r = post(f"/api/jobs/{j0['id']}/outreach", {"search_size": 8, "keep": 3})
check("With outreach off, finding people is refused with a pointer to the doc and nothing runs",
      st == 400 and r.get("needs") == "feature:outreach" and "docs/outreach.md" in r.get("error", "")
      and not (app.load_job(j0["id"]).get("outreach") or {}).get("state"), f"{st} {r}")
_off()

# ---- guards before anything is spent --------------------------------------------------------
st, j = post("/jobs", CAP)
jid = j["id"]
app.update_job(jid, company_url="https://www.linkedin.com/company/acme-health")
st, r = post(f"/api/jobs/{jid}/outreach", {"search_size": 8, "keep": 3})
check("Find people waits until the job is applied (the drafts say you applied)", st == 409, f"got {st}")
app.update_job(jid, company_url=None)
app.update_job(jid, status="applied", evaluation={"fit_score": 82, "recommendation": "TAILOR", "honest_take": "Good fit."})
st, r = post(f"/api/jobs/{jid}/outreach", {"search_size": 8, "keep": 3})
check("Find people refuses a job with no company LinkedIn link, and says what it needs",
      st == 400 and r.get("needs") == "company_url", str(r))
app.update_job(jid, company_url="https://www.linkedin.com/company/acme-health")
r = c.post(f"/api/jobs/{jid}/outreach", json={}, headers={"Origin": "https://evil.example"})
check("A web page cannot start a paid search", r.status_code == 403, f"got {r.status_code}")
app.OUTREACH_DRY_RUN = False
st, r = post(f"/api/jobs/{jid}/outreach", {"search_size": 8, "keep": 3})
check("Without an Apify token in .env, a live search refuses and says so",
      st == 400 and r.get("needs") == "apify_token", str(r))
app.OUTREACH_DRY_RUN = True
with app.db() as con:
    check("Nothing was spent by any refused request", con.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0] == 0)

# ---- the pipeline ------------------------------------------------------------------------------
st, r = post(f"/api/jobs/{jid}/outreach", {"search_size": 8, "keep": 3})
check("Find people starts (202) with your numbers", st == 202 and r["outreach"]["search_size"] == 8
      and r["outreach"]["keep"] == 3, str(r.get("outreach")))
state = wait_state(jid, ("people_review", "ready", "failed"))
check("After the search it stops for your approval of each person", state == "people_review", state)
with app.db() as con:
    proposed = [dict(x) for x in con.execute("SELECT * FROM people WHERE job_id=? ORDER BY rank", (jid,))]
    early_blitz = con.execute("SELECT COUNT(*) FROM api_calls WHERE service='blitzapi' AND job_id=?", (jid,)).fetchone()[0]
    early_msgs = con.execute("SELECT COUNT(*) FROM messages WHERE job_id=?", (jid,)).fetchone()[0]
check("Each proposed person carries a fit score out of 10 from the ranking", [x for x in get("/api/queue")[1]["people"]][0]["fit"] == 9,
      str([x.get("fit") for x in get("/api/queue")[1]["people"]]))
check("Everyone found is proposed, nobody approved yet", len(proposed) == 3 and all(x["status"] == "proposed" for x in proposed),
      str([x["status"] for x in proposed]))
check("Nothing is drafted and no email lookup is paid for before you approve", early_blitz == 0 and early_msgs == 0,
      f"blitz {early_blitz}, messages {early_msgs}")
check("Drafting has not been asked of the model yet", calls["drafts"] == 0, str(calls))
st, n = get("/notifications")
check("The bell counts people waiting for approval", n["people"] == 3 and n["total"] == 3, str(n))
st, q = get("/api/queue")
check("The queue lists them with the job and why", len(q["people"]) == 3 and q["people"][0]["job"]["company"] == "Acme Health"
      and q["people"][0]["why"], str(q["people"][:1])[:200])
r = c.post(f"/api/people/{proposed[0]['id']}/decide", json={"decision": "approve"}, headers={"Origin": "https://evil.example"})
check("A web page cannot approve a person", r.status_code == 403, f"got {r.status_code}")
st, r = post(f"/api/people/{proposed[0]['id']}/decide", {"decision": "maybe"})
check("Only approve or reject", st == 400, f"got {st}")
for x in proposed:
    st, r = post(f"/api/people/{x['id']}/decide", {"decision": "approve"})
check("The last approval says nobody is left", r.get("left_for_job") == 0, str(r))
st, r = post(f"/api/people/{proposed[0]['id']}/decide", {"decision": "reject"})
check("A decision cannot be changed after the fact", st == 409, f"got {st}")
state = wait_state(jid, ("ready", "failed"))
o = app.load_job(jid)["outreach"]
check("Once everyone is decided, drafting runs and finishes ready", state == "ready", f"{state}: {o.get('error')}")
with app.db() as con:
    ppl = [dict(x) for x in con.execute("SELECT * FROM people WHERE job_id=? ORDER BY rank", (jid,))]
    msgs = [dict(x) for x in con.execute("SELECT * FROM messages WHERE job_id=?", (jid,))]
    apify = con.execute("SELECT COUNT(*) FROM api_calls WHERE service='apify' AND job_id=?", (jid,)).fetchone()[0]
    blitz_rows = [json.loads(r[0]) for r in con.execute("SELECT request FROM api_calls WHERE service='email' AND job_id=?", (jid,))]
    blitz = sum(r.get("profiles", 0) for r in blitz_rows)
with app.db() as con:
    alumni_pass = [json.loads(r[0]) for r in con.execute("SELECT request FROM api_calls WHERE service='apify' AND job_id=?", (jid,))]
check("One click makes exactly two searches: the titled one and the alumni pass for the profile's schools",
      apify == 2 and sum(1 for r in alumni_pass if r.get("search") == "alumni" and r.get("schools") == ["Lakeview University"]) == 1,
      f"apify calls {apify}")
check("It kept the number you asked for, in rank order, with a reason each",
      len(ppl) == 3 and [p["rank"] for p in ppl] == [1, 2, 3] and all(p["why"] for p in ppl), str([p["name"] for p in ppl]))
no_email_from_search = sum(1 for p in ppl if p["email_source"] != "harvestapi")
check("One batched email lookup for the job, covering exactly the approved people the search gave no email",
      len(blitz_rows) == (1 if no_email_from_search else 0) and blitz == no_email_from_search, f"{len(blitz_rows)} calls, {blitz} vs {no_email_from_search}")
check("One message per person: email when there is an address, a LinkedIn note otherwise",
      len(msgs) == 3 and all((m["channel"] == "email") == bool(next(p for p in ppl if p["id"] == m["person_id"])["email"])
                              for m in msgs), str([(m["channel"]) for m in msgs]))
check("Every message waits for you (auto mode is off)", all(m["status"] == "review" for m in msgs),
      str([m["status"] for m in msgs]))
check("The model was asked once for titles and ranking, and twice for drafts and audit (one revision)",
      calls["titles"] == calls["rank"] == 1 and calls["drafts"] == calls["audit"] == 2, str(calls))
low_url = next(iter(low_once))
low_p = next(p for p in ppl if p["linkedin_url"] == low_url)
low_m = next(m for m in msgs if m["person_id"] == low_p["id"])
check("A draft the audit scored under 70 was revised from the audit's notes and the better one kept",
      low_m["audit_score"] == 85 and "Revised." in (low_m["draft"] or "")
      and any("revised after audit: 50 to 85" in n for n in json.loads(low_m["validator_notes"])),
      f"{low_m['audit_score']} {json.loads(low_m['validator_notes'])}")
check("A draft that failed the checks was repaired once and says so",
      calls["repair"] == 1 and any(any("repaired" in n for n in json.loads(m["validator_notes"])) for m in msgs), str(calls))
check("Audit scores and notes are stored", all(m["audit_score"] in (85, 90) and json.loads(m["audit_notes"]) for m in msgs))
check("With no careers link, emails name the job ID and carry no LinkedIn link",
      all("job ID 9300001" in (m["draft"] or "") and "linkedin.com" not in (m["draft"] or "")
          for m in msgs if m["channel"] == "email"), str([m["draft"][:200] for m in msgs if m["channel"] == "email"][:1]))
check("No em dashes in any stored draft", not any("—" in (m["draft"] or "") for m in msgs))

st, ov = get("/api/overview")
row = next(x for x in ov["jobs"] if x["id"] == jid)["outreach"]
check("Overview shows the people found", row["found"] == 3 and row["state"] == "ready", str(row))
st, n = get("/notifications")
check("The bell counts what waits", n["total"] == 3, str(n))

st, r = post(f"/api/jobs/{jid}/outreach", {"search_size": 8, "keep": 3})
check("A second search on the same job needs an explicit yes (it costs again)", st == 409 and r.get("needs") == "again", str(r))

# ---- actions on messages ---------------------------------------------------------------------------
emails = [m for m in msgs if m["channel"] == "email"]
notes = [m for m in msgs if m["channel"] == "linkedin"]
if emails:
    e = emails[0]
    st, r = post(f"/api/messages/{e['id']}/approve", {"body": e["draft"] + "\n\nEdited by hand — once."})
    check("Approve queues the email with a planned send time", st == 200 and r["status"] == "queued" and r["scheduled_at"],
          str(r.get("status")))
    check("Your edit is kept as the text that will be sent, dashes cleaned", "Edited by hand" in r["sent_text"]
          and "—" not in r["sent_text"], r.get("sent_text", "")[-40:])
    _ed = [json.loads(x) for x in open(app.LEARNING_INBOX) if '"draft_edited"' in x]
    check("Approve with edits writes one draft_edited event to the learning inbox: the draft before, the text after",
          len(_ed) == 1 and _ed[0]["before"] == e["draft"] and "Edited by hand" in _ed[0]["after"] and _ed[0]["job_id"] == jid
          and _ed[0]["context"]["channel"] == "email" and _ed[0]["context"]["message"] == e["id"], str(_ed)[:300])
    slot = datetime.fromisoformat(r["scheduled_at"])
    check("The planned time is in the future", slot > datetime.now() - timedelta(seconds=5), r["scheduled_at"])
    et_slot = slot.astimezone(app.send_tz())
    check("The planned time is a weekday between 9 AM and 5 PM in the profile's time zone (America/Chicago)",
          et_slot.weekday() < 5 and 9 <= et_slot.hour < 17, et_slot.isoformat())
    st, mon0 = get("/api/monitor")
    check("Monitor states the window from the profile", mon0["sending"]["window"] == "Weekdays, 9 AM to 5 PM (America/Chicago)",
          mon0["sending"]["window"])
    st, r = post(f"/api/messages/{e['id']}/pullback")
    check("Pull back returns it to review", r["status"] == "review" and not r["scheduled_at"], str(r.get("status")))
    st, r = post(f"/api/messages/{e['id']}/approve")
    check("Approving again works", r["status"] == "queued", str(r.get("status")))
    st, mon = get("/api/monitor")
    check("Monitor counts an edited approval in the edit rate", mon["quality"]["edited"] >= 1, str(mon["quality"]))
    _ed2 = [json.loads(x) for x in open(app.LEARNING_INBOX) if '"draft_edited"' in x]
    check("Re-approving after a pull back does not record the same edit twice", len(_ed2) == 1, f"{len(_ed2)} events")
if notes:
    st, r = post(f"/api/messages/{notes[0]['id']}/linkedin_sent")
    check("A LinkedIn note is marked sent by you", st == 200 and r["status"] == "sent" and r["sent_at"], str(r.get("status")))
    st, r = post(f"/api/messages/{notes[0]['id']}/approve")
    check("A LinkedIn note can never be approved for sending by software", st == 409, f"got {st}")

target = next(m for m in msgs if m["status"] == "review" and m["id"] not in (emails[:1] and [emails[0]["id"]] or []))
st, r = post(f"/api/messages/{target['id']}/redraft", {"feedback": "Tighter."})
check("Redraft starts", st == 200 and r["status"] == "drafting", str(r.get("status")))
for _ in range(100):
    if app._message(target["id"])["status"] == "review":
        break
    time.sleep(0.1)
m2 = app._message(target["id"])
check("Redraft rewrites the same message in place with your feedback applied",
      m2["status"] == "review" and ("Tighter." in (m2["draft"] or "") or target["channel"] == "linkedin"), m2["status"])

# ---- the sender, with mailer.send recording instead of sending ------------------------------------------------
got = []


def fake_send(env, to, subject, body, attachment=None, in_reply_to=None, from_name=""):
    got.append({"env": dict(env), "to": to, "subject": subject, "body": body, "attachment": attachment,
                "in_reply_to": in_reply_to, "from_name": from_name})
    return {"id": f"msg-{len(got)}@example.com"}


app.mailer.send = fake_send
open(app.ENV_FILE, "w").write("MAIL_ADDRESS=alex.rivera@example.com\nMAIL_PASSWORD=app-password\nSMTP_HOST=smtp.example.com\n")
if emails:
    with app.db() as con:
        con.execute("UPDATE messages SET scheduled_at=? WHERE id=?", ((datetime.now() - timedelta(minutes=1)).isoformat(), emails[0]["id"]))
    app.OUTREACH_DRY_RUN = False
    app.in_send_window = lambda et: False
    check("Outside the window a due email is re-slotted, not sent", app.send_due() == "reslotted" and not got)
    with app.db() as con:
        con.execute("UPDATE messages SET scheduled_at=? WHERE id=?", ((datetime.now() - timedelta(minutes=1)).isoformat(), emails[0]["id"]))
    post("/settings", {"outreach_paused": True})
    check("Paused means nothing sends", app.send_due() is None and not got)
    post("/settings", {"outreach_paused": False})
    app.in_send_window = lambda et: True
    check("Inside the window a due email is sent", app.send_due() == "sent" and len(got) == 1)
    check("The mailer got the .env settings, the address, the edited text and your name",
          got and got[0]["env"]["SMTP_HOST"] == "smtp.example.com" and got[0]["to"] and "Edited by hand" in got[0]["body"]
          and got[0]["from_name"] == "Alex Rivera" and got[0]["in_reply_to"] is None, str(got[:1])[:200])
    check("The email as sent ends with the profile's signature", got and got[0]["body"].endswith("Best,\nAlex Rivera"), got[0]["body"][-40:] if got else "")
    check("The message is marked sent with the mailer's Message-ID", app._message(emails[0]["id"])["status"] == "sent"
          and app._message(emails[0]["id"])["gmail_id"] == "msg-1@example.com")
    check("Nothing else was due, so nothing else sent", app.send_due() is None and len(got) == 1)
    if len(emails) > 1:
        with app.db() as con:
            con.execute("UPDATE people SET status='rejected' WHERE id=?", (emails[1]["person_id"],))
            con.execute("UPDATE messages SET status='queued', scheduled_at=? WHERE id=?",
                        ((datetime.now() - timedelta(minutes=1)).isoformat(), emails[1]["id"]))
        check("The sender refuses anyone you did not approve, even if a message got queued",
              app.send_due() == "blocked" and len(got) == 1 and app._message(emails[1]["id"])["status"] == "failed")
    # ---- a resume that repeats itself is never attached (UI audit step 13) ----------------------------
    dupc = app.engine.apply_edits(app.engine.content_from_base("operations"), {"build_edits": [
        {"index": 1, "label": "Route planner, a Python tool", "text": "Wrote a small Python tool that plans daily delivery routes for one region, cutting planning time from three hours to twenty minutes."}]})
    clean = app.engine.content_from_base("operations")
    rdir = os.path.join(TMP, "resume-audit")
    os.makedirs(rdir)
    paths = {}
    for tag, content in (("dup", dupc), ("clean", clean)):
        docx = os.path.join(rdir, f"Alex_{tag}.docx")
        app.engine.render(content, docx)
        open(docx[:-5] + ".pdf", "wb").write(b"%PDF-1.4 stand-in " + tag.encode())
        paths[tag] = docx[:-5] + ".pdf"
    check("audit fixture: the duplicate content really does repeat", bool(app.engine.find_duplicates(dupc)["hard"]))
    for jid_, tag in (("j-audit-dup", "dup"), ("j-audit-ok", "clean")):
        app.save_job({"id": jid_, "job_key": jid_, "captured_at": app.now(), "status": "applied", "company": "Audit Co " + tag,
                      "title": "Strategy Lead", "applied_at": "2026-10-04T10:00:00", "folder": os.path.join(rdir, jid_),
                      "build": {"pdf": paths[tag], "docx": paths[tag][:-4] + ".docx"}})
        with app.db() as con:
            con.execute("INSERT INTO people (id, job_id, name, title, email, email_source, status, raw) VALUES (?,?,?,?,?,?,?,?)",
                        ("p-" + jid_, jid_, "Pat Lee", "Manager", f"pat.lee@{tag}audit.example", "finder", "approved", "{}"))
            con.execute("INSERT INTO messages (id, person_id, job_id, channel, subject, draft, sent_text, status, created_at, scheduled_at, model) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("m-" + jid_, "p-" + jid_, jid_, "email", "Strategy Lead application",
                        "Hi Pat, a draft.", "Hi Pat, a draft.", "queued", "2026-10-05T09:00:00", (datetime.now() - timedelta(minutes=1)).isoformat(),
                        app.outreach_model()))
    n_before = len(got)
    check("resume_pdf_for: a resume that repeats itself is not offered for attachment",
          app.resume_pdf_for(app.load_job("j-audit-dup")) is None and "repeats itself" in app.resume_problem(app.load_job("j-audit-dup")),
          str(app.resume_problem(app.load_job("j-audit-dup"))))
    check("resume_pdf_for: a clean resume is", app.resume_pdf_for(app.load_job("j-audit-ok")) == paths["clean"]
          and app.resume_problem(app.load_job("j-audit-ok")) is None)
    check("send: an email whose resume repeats itself is held, not sent", app.send_due() == "held"
          and app._message("m-j-audit-dup")["status"] == "held" and len(got) == n_before, str(app._message("m-j-audit-dup")))
    check("send: the hold says why and what to do", "repeats itself" in (app._message("m-j-audit-dup")["error"] or "")
          and "rebuild" in app._message("m-j-audit-dup")["error"], str(app._message("m-j-audit-dup")["error"]))
    check("send: nothing was attached or posted for the held one", len(got) == n_before)
    check("send: the hold is logged for the Monitor", any(a[0] == "outreach_held" for a in app.db().execute(
          "SELECT action FROM actions WHERE job_id='j-audit-dup'")))
    st_, rel = post("/api/messages/m-j-audit-dup/release")
    check("release: refused while the resume still repeats itself", st_ == 409 and "repeats itself" in rel.get("error", ""), f"{st_} {rel}")
    check("send: the clean resume goes, with its attachment", app.send_due() == "sent" and len(got) == n_before + 1
          and os.path.basename(got[-1]["attachment"] or "") == "Alex_clean.pdf"
          and open(got[-1]["attachment"], "rb").read().startswith(b"%PDF"), str(got[-1])[:200] if got else "")
    # a rebuilt, clean resume lets the held email be released again
    app.engine.render(clean, paths["dup"][:-4] + ".docx")
    st_, rel = post("/api/messages/m-j-audit-dup/release")
    check("release: allowed once the resume is rebuilt clean", st_ == 200 and rel["status"] == "review", f"{st_} {str(rel)[:120]}")
    # a build the server blocked is never attached, even if its docx cannot be read
    app.update_job("j-audit-ok", build={"pdf": paths["clean"], "blocked": "Build stopped"})
    check("a blocked build is never offered", app.resume_pdf_for(app.load_job("j-audit-ok")) is None)
    # no .docx beside the PDF (a job built elsewhere): nothing to audit, so it is allowed
    os.makedirs(os.path.join(rdir, "ext"), exist_ok=True)
    ext_pdf = os.path.join(rdir, "ext", "Resume_Ext.pdf")
    open(ext_pdf, "wb").write(b"%PDF-1.4 ext")
    check("a PDF with no .docx beside it cannot be audited and is allowed",
          app.resume_pdf_for({"external_folder": os.path.join(rdir, "ext")}) == ext_pdf)
    open(paths["clean"][:-4] + ".docx", "wb").write(b"not a zip")
    app.update_job("j-audit-ok", build={"pdf": paths["clean"]})
    check("an unreadable .docx holds rather than attaches", "could not be checked" in (app.resume_problem(app.load_job("j-audit-ok")) or ""))
    app.OUTREACH_DRY_RUN = True

# ---- rejecting people --------------------------------------------------------------------------------------
st, j3 = post("/jobs", dict(CAP, url="https://www.linkedin.com/jobs/view/9300003/", text="Role 9300003. " * 400, company="Beta Corp", title="Strategy Lead"))
app.update_job(j3["id"], status="applied", evaluation={"fit_score": 78, "recommendation": "TAILOR"},
               company_url="https://www.linkedin.com/company/beta-corp")
post(f"/api/jobs/{j3['id']}/outreach", {"search_size": 8, "keep": 3})
wait_state(j3["id"], ("people_review", "failed"))
with app.db() as con:
    p3 = [dict(x) for x in con.execute("SELECT * FROM people WHERE job_id=? ORDER BY rank", (j3["id"],))]
rejected = p3[0]
post(f"/api/people/{rejected['id']}/decide", {"decision": "reject"})
for x in p3[1:]:
    post(f"/api/people/{x['id']}/decide", {"decision": "approve"})
wait_state(j3["id"], ("ready", "failed"))
with app.db() as con:
    m3 = [dict(x) for x in con.execute("SELECT person_id FROM messages WHERE job_id=?", (j3["id"],))]
    b3 = [json.loads(x["request"]) for x in con.execute(
        "SELECT request FROM api_calls WHERE service='email' AND job_id=?", (j3["id"],))]
check("A rejected person gets no draft", rejected["id"] not in [x["person_id"] for x in m3] and len(m3) == 2, str(m3))
need3 = sum(1 for x in p3[1:] if not x["email"])
check("The email lookup covers only approved people without an email, never a skipped person",
      sum(r.get("profiles", 0) for r in b3) == need3 and len(b3) == (1 if need3 else 0), f"{b3} vs {need3}")

# ---- approve everyone at once -------------------------------------------------------------------------------
st, j4 = post("/jobs", dict(CAP, url="https://www.linkedin.com/jobs/view/9300004/", text="Role 9300004. " * 400, company="Gamma Labs", title="Strategy Lead"))
app.update_job(j4["id"], status="applied", evaluation={"fit_score": 74, "recommendation": "TAILOR"},
               company_url="https://www.linkedin.com/company/gamma-labs")
post(f"/api/jobs/{j4['id']}/outreach", {"search_size": 8, "keep": 3})
wait_state(j4["id"], ("people_review", "failed"))
r = c.post(f"/api/jobs/{j4['id']}/people/approve_all", json={}, headers={"Origin": "https://evil.example"})
check("A web page cannot approve everyone", r.status_code == 403, f"got {r.status_code}")
drafts_before = calls["drafts"]
st, r = post(f"/api/jobs/{j4['id']}/people/approve_all")
check("Approve all approves everyone waiting in one step", st == 200 and r.get("approved") == 3, str(r))
wait_state(j4["id"], ("ready", "failed"))
with app.db() as con:
    st4 = [x[0] for x in con.execute("SELECT status FROM people WHERE job_id=?", (j4["id"],))]
check("Everyone is approved and drafting ran once for the job", st4 == ["approved"] * 3 and calls["drafts"] - drafts_before in (1, 2)
      and app.load_job(j4["id"])["outreach"]["state"] == "ready", f"{st4}, drafts calls +{calls['drafts'] - drafts_before}")
st, r = post(f"/api/jobs/{j4['id']}/people/approve_all")
check("Approve all with nobody waiting says so", st == 409, f"got {st}")

# ---- the per-job panel and a drafting retry that never searches again ------------------------------------
st, pj = get(f"/api/jobs/{j3['id']}/outreach")
check("The job panel returns its row, everyone with a status, and messages by group",
      st == 200 and pj["job"]["id"] == j3["id"] and len(pj["people"]) == 3
      and sorted(x["status"] for x in pj["people"]) == ["approved", "approved", "rejected"]
      and all(k in pj for k in ("review", "linkedin", "queued", "failed", "sent", "drafting")), str(pj.get("job", {}).get("outreach"))[:200])
check("Overview counts approved and skipped people per job",
      next(x for x in get("/api/overview")[1]["jobs"] if x["id"] == j3["id"])["outreach"]["people_skipped"] == 1)
st, r = post(f"/api/jobs/{j3['id']}/outreach/resume")
check("Resume is refused unless the pipeline failed", st == 409, f"got {st}")
# Simulate a drafting failure after approval: drop the drafts, mark failed, mark one person's lookup empty.
with app.db() as con:
    con.execute("DELETE FROM messages WHERE job_id=?", (j3["id"],))
    no_mail = con.execute("SELECT id FROM people WHERE job_id=? AND status='approved' AND email IS NULL", (j3["id"],)).fetchall()
    for x in no_mail:
        con.execute("UPDATE people SET email_source='not_found' WHERE id=?", (x["id"],))
    apify_before = con.execute("SELECT COUNT(*) FROM api_calls WHERE service='apify' AND job_id=?", (j3["id"],)).fetchone()[0]
    blitz_before = con.execute("SELECT COUNT(*) FROM api_calls WHERE service='blitzapi' AND job_id=?", (j3["id"],)).fetchone()[0]
app.set_outreach(j3["id"], state="failed", error="Claude: simulated drafting failure")
r = c.post(f"/api/jobs/{j3['id']}/outreach/resume", json={}, headers={"Origin": "https://evil.example"})
check("A web page cannot resume a pipeline", r.status_code == 403, f"got {r.status_code}")
st, r = post(f"/api/jobs/{j3['id']}/outreach/resume")
check("Retry drafting starts for the approved people", st == 202, f"got {st}: {r}")
wait_state(j3["id"], ("ready", "failed"))
with app.db() as con:
    apify_after = con.execute("SELECT COUNT(*) FROM api_calls WHERE service='apify' AND job_id=?", (j3["id"],)).fetchone()[0]
    blitz_after = con.execute("SELECT COUNT(*) FROM api_calls WHERE service='blitzapi' AND job_id=?", (j3["id"],)).fetchone()[0]
    redrafted = con.execute("SELECT COUNT(*) FROM messages WHERE job_id=?", (j3["id"],)).fetchone()[0]
check("Retrying the drafting runs no new people search", apify_after == apify_before, f"{apify_before} -> {apify_after}")
check("An email lookup that already came back empty is never paid for again", blitz_after == blitz_before,
      f"{blitz_before} -> {blitz_after}")
check("The approved people get their drafts back", redrafted == 2 and app.load_job(j3["id"])["outreach"]["state"] == "ready",
      f"{redrafted} drafts, {app.load_job(j3['id'])['outreach']['state']}")

# ---- a refused email lookup is not an answer -------------------------------------------------------------
st, j5 = post("/jobs", dict(CAP, url="https://www.linkedin.com/jobs/view/9300005/", text="Role 9300005. " * 400, company="Delta Co", title="Strategy Lead"))
app.update_job(j5["id"], status="applied", evaluation={"fit_score": 70}, company_url="https://www.linkedin.com/company/delta-co",
               outreach={"state": "drafting", "search_size": 8, "keep": 1})
with app.db() as con:
    con.execute("INSERT INTO people (id, job_id, name, title, linkedin_url, rank, why, raw, found_at, status) "
                "VALUES ('d1', ?, 'Dee Example', 'Recruiter', 'https://www.linkedin.com/in/dee-example', 1, 'Owns hiring', "
                "'{\"first\": \"Dee\"}', ?, 'approved')", (j5["id"], app.now()))
open(app.ENV_FILE, "w").write("APIFY_TOKEN=fake-for-test\n")
real_run, app.OUTREACH_DRY_RUN = app.outreach.apify_run, False
app.outreach.apify_run = lambda actor, payload, token, max_wait_s=300: {
    "items": [], "usd": None, "run_id": None, "status": "START_FAILED", "events": None,
    "error": "HTTP 403: full-permission-actor-not-approved"}
app._continue_outreach(j5["id"])
app.outreach.apify_run, app.OUTREACH_DRY_RUN = real_run, True
with app.db() as con:
    src = con.execute("SELECT email_source FROM people WHERE id='d1'").fetchone()[0]
    logged = con.execute("SELECT ok, error FROM api_calls WHERE job_id=? AND service='email'", (j5["id"],)).fetchone()
check("A refused email lookup is logged as failed and the person stays eligible for a later lookup",
      src is None and logged and logged[0] == 0 and "403" in (logged[1] or ""), f"source {src!r}, logged {logged}")

# ---- auto mode ------------------------------------------------------------------------------------------
r = c.post("/settings", json={"outreach_auto": True}, headers={"Origin": "https://evil.example"})
check("A web page cannot switch auto mode on", r.status_code == 403 and not app.get_settings()["outreach_auto"], f"got {r.status_code}")
post("/settings", {"outreach_auto": True, "people_auto": True})
st, j2 = post("/jobs", dict(CAP, url="https://www.linkedin.com/jobs/view/9300002/", text="Role 9300002. " * 400, title="Ops Lead"))
app.update_job(j2["id"], status="applied", evaluation={"fit_score": 80, "recommendation": "TAILOR"},
               company_url="https://www.linkedin.com/company/acme-health")
post(f"/api/jobs/{j2['id']}/outreach", {"search_size": 8, "keep": 3})
state = wait_state(j2["id"], ("people_review", "ready", "failed"))
with app.db() as con:
    p2 = [dict(x) for x in con.execute("SELECT * FROM people WHERE job_id=? ORDER BY rank", (j2["id"],))]
held = [x for x in p2 if x["status"] == "proposed"]
check("With auto approval on, people are approved without a click", sum(1 for x in p2 if x["status"] == "approved") >= 1,
      str([x["status"] for x in p2]))
check("Someone already emailed for another job is held for you even in auto, with the reason",
      state == "people_review" and held and all((x["note"] or "").startswith("Already contacted") for x in held),
      f"{state} {[(x['name'], x['note']) for x in held]}")
for x in held:
    post(f"/api/people/{x['id']}/decide", {"decision": "approve"})
wait_state(j2["id"], ("ready", "failed"))
with app.db() as con:
    m3 = [dict(x) for x in con.execute("SELECT channel, status, auto, validator_notes FROM messages WHERE job_id=?", (j2["id"],))]
clean_emails = [m for m in m3 if m["channel"] == "email" and not json.loads(m["validator_notes"])]
check("Auto mode queues clean, high-scoring emails without a click",
      all(m["status"] == "queued" and m["auto"] == 1 for m in clean_emails), str(m3))
check("Auto mode never touches LinkedIn notes or repaired drafts",
      all(m["status"] == "review" for m in m3 if m["channel"] == "linkedin" or json.loads(m["validator_notes"])), str(m3))
post("/settings", {"outreach_auto": False, "people_auto": False})

# ---- what the drafter knows about a person ------------------------------------------------------------------
item = {"firstName": "Noel", "lastName": "L", "linkedinUrl": "https://www.linkedin.com/in/nl", "headline": "x",
        "about": "I lead the  Field Analytics team.", "openToWork": False,
        "experience": [
            {"position": "Head of Field Analytics", "companyName": "Umbrella", "duration": "1 yr 7 mos",
             "startDate": {"text": "Apr 2025"}, "endDate": {"text": "Present"}},
            {"position": "Analyst", "companyName": "Umbrella", "duration": "8 mos", "startDate": {"text": "Aug 2024"}},
            {"position": "co-founder & ceo", "companyName": "Fidelo Labs", "duration": "2 yrs 6 mos"},
            {"position": "Management Consultant", "companyName": "Larkspur Partners", "duration": "8 yrs 9 mos"}],
        "education": [{"schoolName": "Westbrook Institute of Technology", "degree": "B.Tech",
                       "startDate": {"year": 2006}, "endDate": {"year": 2010}}]}
ctx = app.outreach.person_context(item)
check("Tenure adds every role at the current company", ctx.get("at_company_for") == "2 yr 3 mo" and ctx.get("since") == "Aug 2024", str(ctx))
check("The path before is kept, with each stint's length",
      ctx.get("path_before") == ["co-founder & ceo at Fidelo Labs (2 yr 6 mo)", "Management Consultant at Larkspur Partners (8 yr 9 mo)"], str(ctx))
check("Schools carry degree and years; About is tidied; empty fields are dropped",
      ctx.get("schools") == ["Westbrook Institute of Technology (B.Tech) 2006-2010"]
      and ctx.get("about") == "I lead the Field Analytics team." and "open_to_work" not in ctx, str(ctx))
seen = {}
real = app.run_claude
def spy(prompt, schema=None, **kw):
    if schema is app.outreach.DRAFTS_SCHEMA:
        seen["prompt"] = prompt
    return real(prompt, schema, **kw)
app.run_claude = spy
app._draft_round(app.outreach_job(app.load_job(jid)), "JD", {}, [dict(app.outreach.profiles_from_harvest([item])[0], id="x", why="")],
                 __import__("outreach_validate").validate_and_clean, "", [])
app.run_claude = real
check("The drafter sees the person's context", '"about_them"' in seen.get("prompt", "") and "Fidelo Labs" in seen.get("prompt", ""))

# ---- careers page link ------------------------------------------------------------------------------------
st, r = post("/api/careers_url", {"job_key": "linkedin:9300001", "url": "https://www.linkedin.com/jobs/view/9300001/"})
check("A LinkedIn link is refused as a careers page", st == 400, f"{st} {r}")
st, r = post("/api/careers_url", {"job_key": "linkedin:1", "url": "https://careers.acme.com/jobs/77"})
check("A careers link for a posting not captured yet says so", st == 404, f"{st}")
st, r = post("/api/careers_url", {"job_key": "linkedin:9300001", "url": "https://careers.acme.com/jobs/77?utm_source=linkedin&src=li"})
oj = app.outreach_job(app.load_job(jid))
check("The Apply click's careers page is stored without tracking and becomes the email's link",
      st == 200 and oj["url"] == "https://careers.acme.com/jobs/77?src=li", f"{st} {oj.get('url')}")
check("The drafter is told to use it and never a LinkedIn link",
      "the careers page link https://careers.acme.com/jobs/77?src=li" in app.outreach.link_rule(oj))
check("outreach_job can be applied twice without losing the captured address",
      app.outreach_job(oj)["capture_url"] == oj["capture_url"] and app.outreach_job(oj)["url"] == oj["url"])
app.update_job(jid, careers_url=None)
check("With no careers link the drafter names the role and its LinkedIn job ID",
      "(job ID 9300001)" in app.outreach.link_rule(app.outreach_job(app.load_job(jid))))

# ---- after Mark submitted: stay in Active until you answer ---------------------------------------------------
saved_o = app.load_job(jid).get("outreach")
app.update_job(jid, outreach=None, outreach_pending=None, outreach_decision=None)
st, r = post(f"/jobs/{jid}/submitted", {})
check("Mark submitted leaves the job waiting on your reach-out answer", st == 200 and r.get("outreach_pending") is True, str(r.get("outreach_pending")))
st, r = post(f"/jobs/{jid}/outreach_decision", {"decision": "maybe"})
check("Only a no is recorded through the decision route", st == 400)
st, r = post(f"/jobs/{jid}/outreach_decision", {"decision": "pass"})
check("Your no clears the wait and is kept", st == 200 and r["outreach_pending"] is False and r["outreach_decision"] == "pass")
app.update_job(jid, outreach_pending=True)
app.set_outreach(jid, state="searching")
check("Starting outreach clears the wait too", app.load_job(jid)["outreach_pending"] is False)
app.update_job(jid, outreach=saved_o, outreach_pending=None, outreach_decision=None)
app.update_job(jid, outreach={"state": "ready"})
st, r = post(f"/jobs/{jid}/submitted", {})
check("A job whose outreach already started is not held", r.get("outreach_pending") is False)
app.update_job(jid, outreach=saved_o, outreach_pending=None)

# ---- stages after Applied, and jobs added by hand ------------------------------------------------------------
st, r = post(f"/jobs/{jid}/stage", {"stage": "dancing"})
check("An unknown stage is refused", st == 400)
st, r = post(f"/jobs/{jid}/stage", {"stage": "heard_back", "note": "Email: someone will reach out"})
check("A stage is set with its note", st == 200 and r["stage"] == "heard_back" and r["stage_note"] == "Email: someone will reach out")
st, r = post(f"/jobs/{jid}/stage", {"stage": "interviewing"})
check("Each change is kept with its date", [h["stage"] for h in r["stage_history"]] == ["heard_back", "interviewing"]
      and all(h["at"] for h in r["stage_history"]))
st, r = post(f"/jobs/{jid}/stage", {"stage": "applied"})
check("Back to applied clears the stage", st == 200 and r["stage"] is None)
app.update_job(jid, status="built")
st, r = post(f"/jobs/{jid}/stage", {"stage": "offer"})
check("A job not yet submitted cannot take a stage", st == 409)
app.update_job(jid, status="applied", stage=None, stage_history=[])

st, r = post("/jobs/manual", {"company": "Initech"})
check("Adding a job by hand needs company and role", st == 400)
st, r = post("/jobs/manual", {"company": "Initech", "title": "Solutions Architect", "applied_at": "Oct 1"})
check("A malformed applied date is refused", st == 400)
st, r = post("/jobs/manual", {"company": "Initech", "title": "Senior Program Manager, Operations", "applied_at": "2026-09-28",
                              "stage": "assessment", "note": "Online assessment due Friday",
                              "url": "https://careers.initech.example/en/jobs/3051234/senior-program-manager?cmpid=li"})
mj = r
check("A job added by hand is applied, staged and dated, with no evaluation",
      st == 201 and mj["status"] == "applied" and mj["source"] == "manual" and mj["stage"] == "assessment"
      and mj["applied_at"].startswith("2026-09-28") and mj["evaluation"] is None, f"{st} {r}")
check("Its careers link becomes the email's link", app.outreach_job(app.load_job(mj["id"]))["url"].startswith("https://careers.initech.example/en/jobs/3051234/"))
check("Its folder holds a JD.md", os.path.exists(os.path.join(mj["folder"], "JD.md")))
st, r = post("/jobs/manual", {"company": "Initech", "title": "Senior Program Manager, Operations",
                              "url": "https://careers.initech.example/en/jobs/3051234/senior-program-manager?cmpid=li"})
check("The same posting cannot be added twice", st == 409 and r.get("id") == mj["id"], f"{st} {r}")
st, r = post("/jobs/manual", {"company": "Acme", "title": "PM", "url": "https://www.linkedin.com/jobs/view/7700001/"})
check("A LinkedIn link files the job under its LinkedIn id and is never a careers link",
      st == 201 and r["job_key"] == "linkedin:7700001" and not r.get("careers_url"), f"{st} {r}")
# An older job still in process is listed even past the 50 most recent.
old = dict(app.load_job(mj["id"]), id="zz-old-interviewing", job_key="manual:zz-old", captured_at="2020-01-01T00:00:00",
           stage="interviewing")
app.save_job(old)
for i in range(55):
    app.save_job(dict(old, id=f"zz-filler-{i}", job_key=f"manual:zz-filler-{i}", captured_at=f"2030-01-01T00:00:{i:02d}",
                      status="skipped", stage=None))
st, lst = get("/jobs")
ids = [j["id"] for j in lst]
check("The job list carries older jobs still in process, and only those past the newest 50",
      "zz-old-interviewing" in ids and mj["id"] in ids and sum(1 for i in ids if i.startswith("zz-filler")) == 50, f"{len(ids)}")
with app.db() as con:
    con.execute("DELETE FROM jobs WHERE id LIKE 'zz-%'")

# ---- guessed addresses only on a domain that receives mail ------------------------------------------------
app.mail_domain_ok = app.unguarded["mail_domain_ok"]     # the real check, on cached domains and a stubbed `dig` only
app._MX_CACHE.update({"getumbrella.example": False, "umbrella.example": True, "acme-good.com": True})
check("A domain with real mail servers keeps the guess",
      app.guess_on_a_real_domain("ann.lee@acme-good.com", "Acme") == ("ann.lee@acme-good.com", "lookup-guess"))
check("A forwarding-only domain with no confirmed address drops the guess for a LinkedIn note",
      app.guess_on_a_real_domain("taylor.shaw@getumbrella.example", "Nobody Inc") == (None, "bad-domain"))
saved_conf = app.confirmed_domain_for
app.confirmed_domain_for = lambda company: "umbrella.example" if company == "Umbrella" else None
check("It moves to the domain of an address confirmed at the same company",
      app.guess_on_a_real_domain("taylor.shaw@getumbrella.example", "Umbrella") == ("taylor.shaw@umbrella.example", "lookup-guess"))
app.confirmed_domain_for = saved_conf
real_run = app.subprocess.run
app.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(OSError("no dns"))
check("When DNS cannot be asked, the guess is left alone", app.mail_domain_ok("never-cached.example") is None
      and app.guess_on_a_real_domain("x.y@never-cached.example", "X")[1] == "lookup-guess")
app.subprocess.run = real_run
check("The real check reads a forwarding-only MX as no mailbox",
      bool(app.FORWARD_ONLY.search("eforward2.registrar-servers.com.")) and not app.FORWARD_ONLY.search("aspmx.l.google.com."))

# ---- credentials, nicknames and domains learned from bounces ----------------------------------------------
o = app.outreach
check("Credentials and nicknames are not part of a name",
      o.clean_name("Lee Fisher, MA, RCDD") == "Lee Fisher" and o.clean_name("Mei (Audrey) Chen") == "Mei Chen"
      and o.clean_name("Morgan Diaz PMP MBA") == "Morgan Diaz" and o.clean_name("Sam Ma") == "Sam Ma")
check("A guess carrying a credential is rebuilt as first.last",
      o.tidy_guess("Lee Fisher, MA, RCDD", "lee.fishermarcdd@initech.com") == "lee.fisher@initech.com"
      and o.tidy_guess("Mei (Audrey) Chen", "mei.audreychen@hooli.example") == "mei.chen@hooli.example")
check("A usual pattern is left as it is",
      o.tidy_guess("Aaron Brennan", "abrennan@x.com") == "abrennan@x.com" and o.tidy_guess("Jordan Lee", "jordan.lee@globex.example") == "jordan.lee@globex.example")
with app.db() as con:
    con.execute("DELETE FROM settings WHERE k='mail_domains'")
app.learn_from_bounce("lee.fisher@initech.com", "5.7.1",
                      "550 5.7.1 This is not an official Initech email. Please contact support@initech.io - gcdp a64.c318 - gsmtp")
app.learn_from_bounce("morgan.price@getumbrella.example", "5.7.1", "554 5.7.1 <morgan.price@getumbrella.example>: Relay access denied")
app.learn_from_bounce("vic.tran@globex.example", "5.1.1", "550 Invalid Recipient")
md = app.mail_domains()
check("A domain rejection naming the real domain is remembered as an alias", md["alias"] == {"initech.com": "initech.io"}, str(md))
check("A domain rejection with no alternative marks the domain bad; a wrong person does not", md["bad"] == ["getumbrella.example"], str(md))
saved_dd = app.domain_delivered
app.domain_delivered = lambda d, settle_min=10: d == "delivered.example"
app.learn_from_bounce("ghost@delivered.example", "5.7.1", "550 5.7.1 not an official email, contact support@delivered.io")
check("A domain that already delivered someone else's email is not blamed for one person's rejection",
      "delivered.example" not in app.mail_domains()["alias"] and "delivered.example" not in app.mail_domains()["bad"])
app.domain_delivered = saved_dd
app._MX_CACHE.update({"initech.io": True, "initech.com": True, "getumbrella.example": True})
check("Guesses move to the learned domain", app.guess_on_a_real_domain("tess.spell@initech.com", "Initech") == ("tess.spell@initech.io", "lookup-guess"))
check("Guesses on a rejected domain are dropped even when it has mail servers",
      app.guess_on_a_real_domain("a.b@getumbrella.example", "Nobody") == (None, "bad-domain"))
with app.db() as con:
    con.execute("DELETE FROM settings WHERE k='mail_domains'")

app.mail_domain_ok = lambda domain: None                 # guarded again: no `dig` from here on

# ---- the finder (vulnv) first, kept only on the company's own domains -------------------------------------
o = app.outreach
check("A sister domain of the company passes (globex.net for Globex, initech.io for Initech)",
      o.company_domain_ok("globex.net", "Globex", ["globex.com"]) and o.company_domain_ok("initech.io", "Initech"))
check("Another company's domain is refused (a same-name person at another firm)",
      not o.company_domain_ok("capitalandinvestment.example", "Globex", ["globex.com"]) and not o.company_domain_ok("luckyshoes.example", "Globex"))
fp = [{"linkedin_url": "https://www.linkedin.com/in/dmorales", "name": "Dana Morales"},
      {"linkedin_url": "https://www.linkedin.com/in/1samking", "name": "Sam King"}]
got = o.emails_from_finder([{"linkedin_url": "https://www.linkedin.com/in/dmorales/", "found": True, "email": "dmorales@globex.net"},
                            {"linkedin_url": "https://www.linkedin.com/in/1samking", "found": True, "email": "sam-king@capitalandinvestment.example"},
                            {"linkedin_url": "https://www.linkedin.com/in/nobody", "found": False}], fp, "Globex", ["globex.com"])
check("The finder's answers are kept only on the company's domains", got == {"https://www.linkedin.com/in/dmorales": "dmorales@globex.net"}, str(got))

# ---- former staff, the pipeline as a credential, careers links -------------------------------------------------
o = app.outreach
check("Someone now at another company is not written to about this one",
      not o.still_at_company({"company": "Soylent"}, "NLC (Northwind Labs Collective)") and not o.still_at_company({"company": "Vandelay"}, "The Initech Company")
      and o.still_at_company({"company": "NLC"}, "NLC (Northwind Labs Collective)") and o.still_at_company({}, "Acme"))
import outreach_validate as ov
r = ov.validate_and_clean(json.dumps({"email_subject": "x", "email_body": "Hi Drew,\n\nHope your week is going well. " + "word " * 100 +
                                      "My own job search runs on a pipeline I built at home.", "linkedin_dm": "Hi"}), "Drew", "Applied", None)
check("Citing your own job-search pipeline is caught", any("AI-pattern" in x for x in r["problems"]), str(r["problems"]))
check("A careers link with the job number drops its query junk",
      app.clean_careers_url("https://careers.globex.example/ops/jobs/9139?lang=en-usSenior+Operations+Consultant&mode=apply&iis=LinkedIn")
      == "https://careers.globex.example/ops/jobs/9139")

# ---- never a personal address ------------------------------------------------------------------------------
o = app.outreach
check("Personal addresses are recognised", o.personal_address("someone.personal@gmail.com") and not o.personal_address("srivers@globex.net"))
check("The finder's personal answers are dropped",
      o.emails_from_finder([{"linkedin_url": "https://www.linkedin.com/in/s", "found": True, "email": "sr123@gmail.com"}],
                           [{"linkedin_url": "https://www.linkedin.com/in/s"}], "Globex", ["globex.net"]) == {})
check("A people-search profile's personal email is not used",
      o.profiles_from_harvest([{"firstName": "K", "lastName": "Y", "linkedinUrl": "https://www.linkedin.com/in/k", "email": "k@gmail.com",
                                "emails": [{"email": "k@gmail.com", "status": "valid"}]}])[0]["email"] is None)

# ---- only found addresses get an email -----------------------------------------------------------------------
st, j6 = post("/jobs", dict(CAP, url="https://www.linkedin.com/jobs/view/9300006/", text="Role 9300006. " * 400, company="Gamma Co", title="Strategy Lead"))
app.update_job(j6["id"], status="applied", evaluation={"fit_score": 70}, company_url="https://www.linkedin.com/company/gamma-co",
               outreach={"state": "drafting", "search_size": 8, "keep": 1})
with app.db() as con:
    con.execute("INSERT INTO people (id, job_id, name, title, linkedin_url, rank, why, raw, found_at, status) "
                "VALUES ('g1', ?, 'Gail Example', 'Recruiter', 'https://www.linkedin.com/in/gail-example', 1, 'Owns hiring', "
                "'{\"first\": \"Gail\"}', ?, 'approved')", (j6["id"], app.now()))
def _stub(actor, payload, token, max_wait_s=300):
    if actor == app.outreach.FINDER_ACTOR:
        return {"items": [{"linkedin_url": "https://www.linkedin.com/in/gail-example", "found": False}], "usd": 0.0, "run_id": "f1", "error": None}
    return {"items": [{"inputUrl": "https://www.linkedin.com/in/gail-example", "email": "gail.example@gamma.co",
                       "emailStatus": "pattern-likely"}], "usd": 0.0035, "run_id": "c1", "error": None}
real_run, app.OUTREACH_DRY_RUN = app.outreach.apify_run, False
app.outreach.apify_run = _stub
app._continue_outreach(j6["id"])
app.outreach.apify_run, app.OUTREACH_DRY_RUN = real_run, True
with app.db() as con:
    g = dict(con.execute("SELECT email, email_source FROM people WHERE id='g1'").fetchone())
    ch = [r[0] for r in con.execute("SELECT channel FROM messages WHERE person_id='g1'")]
check("A pattern guess is never used: no address, and the person gets a LinkedIn note",
      g["email"] is None and g["email_source"] == "guess-unused" and ch == ["linkedin"], f"{g} {ch}")

# ---- bounces ----------------------------------------------------------------------------------------------------
with app.db() as con:
    bm = dict(con.execute("SELECT m.id, p.email FROM messages m JOIN people p ON p.id=m.person_id WHERE m.channel='email' "
                          "AND p.email IS NOT NULL LIMIT 1").fetchone())
    con.execute("UPDATE messages SET status='sent', sent_at=? WHERE id=?", (app.now(), bm["id"]))
n = app.record_bounces([{"recipient": bm["email"].upper(), "code": "450", "status": "4.2.1", "reason": "mailbox busy", "permanent": False}])
check("A temporary failure is not recorded as a bounce", n == 0)
n = app.record_bounces([{"recipient": bm["email"].upper(), "code": "550", "status": "5.1.1", "reason": "550 Invalid Recipient", "permanent": True}])
with app.db() as con:
    row = dict(con.execute("SELECT status, error FROM messages WHERE id=?", (bm["id"],)).fetchone())
check("A permanent failure marks the sent email bounced with the server's reason",
      n == 1 and row["status"] == "bounced" and "550 Invalid Recipient" in row["error"], str(row))
check("Recording the same bounce again changes nothing",
      app.record_bounces([{"recipient": bm["email"], "permanent": True, "reason": "x"}]) == 0)
check("A bounced address is never used again", app.bounced_address(bm["email"]) is True)
st, q = get("/api/queue")
check("The Outreach queue lists bounced emails", any(m["id"] == bm["id"] for m in q.get("bounced", [])))
st, mon = get("/api/monitor")
check("Monitor counts sent and bounced by where the address came from", "bounces" in mon and
      sum(v["bounced"] for v in mon["bounces"]["by_source"].values()) >= 1, str(mon.get("bounces")))
with app.db() as con:
    con.execute("UPDATE messages SET status='review', error=NULL, sent_at=NULL WHERE id=?", (bm["id"],))

# ---- the fact check ----------------------------------------------------------------------------------------
fjob = app.outreach_job(app.load_job(jid))
fpeople = [dict(app.outreach.profiles_from_harvest(app.outreach.fake_people_items("factco", 2))[i], id=f"fact-{i}", why="",
                email=f"f{i}@example.com", email_source="harvestapi") for i in range(2)]
target = fpeople[1]["linkedin_url"].rsplit("/", 1)[-1]
fact_mode.update(bad=target, sticky=False, seen=False)
with app.db() as con:
    before = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
app._draft_and_store(fjob, "JD", {}, fpeople, __import__("outreach_validate").validate_and_clean)
with app.db() as con:
    m = dict(con.execute("SELECT validator_notes FROM messages WHERE person_id='fact-1'").fetchone())
check("A claim the fact check cannot support sends that draft back, and the clean revision is kept",
      "revised after audit" in m["validator_notes"] and "unsupported claim" not in m["validator_notes"], m["validator_notes"])
fact_mode.update(bad=target, sticky=True, seen=False)
with app.db() as con:
    con.execute("DELETE FROM messages WHERE person_id LIKE 'fact-%'")
app._draft_and_store(fjob, "JD", {}, fpeople, __import__("outreach_validate").validate_and_clean)
with app.db() as con:
    m = dict(con.execute("SELECT validator_notes, status FROM messages WHERE person_id='fact-1'").fetchone())
check("A claim still unsupported after the revision is shown to you on the draft",
      "unsupported claim: 'I sat with the users every week'" in m["validator_notes"], m["validator_notes"])
fact_mode.clear()
with app.db() as con:
    con.execute("DELETE FROM messages WHERE person_id LIKE 'fact-%'")

# ---- the model is pinned and checked ------------------------------------------------------------------------
check("Outreach uses the profile's outreach model", app.outreach_model() == app.userprofile.model("outreach") == "opus")
check("An exact model id pin must match exactly; an alias must be part of the id that answered",
      app._model_matches("claude-opus-5-5", ["claude-opus-5-5"]) and not app._model_matches("claude-opus-5-5", ["claude-opus-5-6"])
      and app._model_matches("opus", ["claude-opus-5-5"]) and not app._model_matches("opus", ["claude-haiku-4-5-20251001"]))
real = app.run_claude
app.run_claude = lambda prompt, schema=None, **kw: {"structured": {"titles": []}, "timing": {"model_used": ["claude-haiku-4-5-20251001"]}}
try:
    app._claude_json("x", app.outreach.TITLES_SCHEMA); refused = False
except RuntimeError as e:
    refused = "claude-haiku" in str(e)
app.run_claude = real
check("A draft answered by a different model is refused, not stored", refused)
with app.db() as con:
    models = {r[0] for r in con.execute("SELECT model FROM messages")}
check("Every stored draft records the model that wrote it", models == {app.outreach_model()}, str(models))

# ---- alike openings ----------------------------------------------------------------------------------------
o = app.outreach
check("Two openings that ask for the same favour in other words count as alike",
      o.openings_alike("Hi Riley,\n\nWould you be willing to pass my resume to whoever is hiring for the Strategic Projects Lead role?",
                       "Hi Val,\n\nWould you be open to passing my resume to the hiring manager for the Strategic Projects Lead role?"))
check("An ask and an applied-this-week opening are not alike",
      not o.openings_alike("Hi A,\n\nWould you pass my resume to the hiring manager?",
                           "Hi B,\n\nI applied this week to the Operations Architect role: https://x.y/1"))
check("The first sentence is read after the greeting, up to its end",
      o.first_sentence("Hi Mitchell,\n\nWe both went to Lakeview. I applied.") == "We both went to Lakeview.")

# ---- alumni pass for a job searched before it existed -----------------------------------------------------
post("/settings", {"people_auto": True})
with app.db() as con:
    before = {r[0] for r in con.execute("SELECT linkedin_url FROM people WHERE job_id=?", (j2["id"],))}
alum_items = app.outreach.fake_people_items("lakeview alum late", 1)
added = app.alumni_pass(j2["id"], items=alum_items)
with app.db() as con:
    newp = [dict(r) for r in con.execute("SELECT * FROM people WHERE job_id=?", (j2["id"],)) if r["linkedin_url"] not in before]
    drafted = con.execute("SELECT COUNT(*) FROM messages WHERE person_id=?", (newp[0]["id"] if newp else "",)).fetchone()[0]
check("A late alumni pass adds the alum, approves them with auto on, and drafts for them only",
      added == 1 and len(newp) == 1 and newp[0]["status"] == "approved" and drafted >= 1, f"{added} {newp} {drafted}")
check("A late alumni pass reuses a paid run's people without a second search",
      app.alumni_pass(j2["id"], items=alum_items) == 0)
post("/settings", {"people_auto": False})

# ---- restart in the middle ------------------------------------------------------------------------------
app.set_outreach(jid, state="drafting")
with app.db() as con:
    con.execute("UPDATE messages SET status='sending' WHERE job_id=? AND channel='email' AND status='queued'", (j2["id"],))
app.reconcile_on_boot()
check("A pipeline interrupted by a restart says so", app.load_job(jid)["outreach"]["state"] == "failed")
with app.db() as con:
    stuck = con.execute("SELECT COUNT(*) FROM messages WHERE status='sending'").fetchone()[0]
check("A send cut off by a restart is shown as failed, never silently resent", stuck == 0)

# ---- UI audit step 8: a person captured from a LinkedIn profile ---------------------------------------------------
def wait_person(pid, secs=20):
    for _ in range(secs * 10):
        if pid not in app._person_busy:
            return True
        time.sleep(0.1)
    return False


snap = (dict(calls),)
with app.db() as con:
    api0 = con.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0]
    msg0 = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
PERSON = {"name": "Pat Jones, MBA", "linkedin_url": "https://www.linkedin.com/in/Pat-Jones-123/?trk=public", "title": "Director, Strategy",
          "headline": "Director, Strategy at Acme Health", "location": "Chicago, IL", "company": "Acme Health",
          "company_url": "https://www.linkedin.com/company/acme-health/life", "about": "I lead strategy. " * 200}
st, r = post("/api/people/manual", PERSON)
pp = r.get("person") or {}
check("Capture: a person is saved as a contact, approved, with no job", st == 201 and r["created"] and pp["job_id"] is None
      and pp["status"] == "approved" and pp["manual"] and pp["name"] == "Pat Jones", f"{st} {pp}")
check("Capture: the profile link is the clean /in/ slug", pp["linkedin_url"] == "https://www.linkedin.com/in/pat-jones-123", pp.get("linkedin_url"))
with app.db() as con:
    ctx_ = json.loads(con.execute("SELECT raw FROM people WHERE id=?", (pp["id"],)).fetchone()[0])["ctx"]
check("Capture: the about text is cut to 400 characters and kept for the drafter", 0 < len(ctx_["about"]) <= 400
      and ctx_["company"] == "Acme Health" and ctx_["current_role"] == "Director, Strategy", str(ctx_)[:200])
check("Capture: the jobs offered start with the ones at their company (both Acme Health jobs, and the one called Acme, a first word), then the rest",
      len(r["jobs"]) >= 2 and {jid, j2["id"]} <= {x["id"] for x in r["jobs"] if x["match"]} and all(x["company"].startswith("Acme") for x in r["jobs"] if x["match"])
      and [x["match"] for x in r["jobs"]] == sorted((x["match"] for x in r["jobs"]), reverse=True), str([(x["company"], x["match"]) for x in r["jobs"]]))
with app.db() as con:
    check("Capture: nothing is drafted, nothing is paid, the model is not asked",
          con.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0] == api0 and con.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == msg0
          and calls == snap[0], f"{calls} {snap[0]}")
st, r2 = post("/api/people/manual", PERSON)
check("Capture: the same profile again is not duplicated and says it is tracked", st == 200 and not r2["created"]
      and r2["person"]["id"] == pp["id"] and len(r2["tracked"]) == 1, f"{st} {r2.get('tracked')}")
st, r3 = post("/api/people/manual", dict(PERSON, name=""))
check("Capture: a name is required", st == 400)
st, r3 = post("/api/people/manual", dict(PERSON, linkedin_url="https://www.linkedin.com/company/acme"))
check("Capture: only a profile link counts", st == 400)
r = c.post("/api/people/manual", json=PERSON, headers={"Origin": "https://evil.example"})
check("Capture: a web page cannot do it", r.status_code == 403)
st, r3 = post("/api/people/manual", dict(PERSON, name="Sam Existing", linkedin_url=ppl[0]["linkedin_url"]))
check("Capture: someone the search already found is reported on their job, not saved again",
      st == 200 and not r3["created"] and r3["tracked"][0]["job"]["id"] == jid, str(r3.get("tracked")))
st, got = get(f"/api/people/{pp['id']}")
check("Read one person", st == 200 and got["person"]["name"] == "Pat Jones" and got["job"] is None and got["messages"] == [])

st, r = post(f"/api/people/{pp['id']}/draft")
check("Draft: needs a job first, and says so", st == 409 and "job first" in r["error"], str(r))
st, r = post(f"/api/people/{pp['id']}/attach", {"job_id": "nope"})
check("Attach: an unknown job is refused", st == 404)
rej = app.load_job(j2["id"])
app.update_job(j2["id"], stage="rejected")
st, r = post(f"/api/people/{pp['id']}/attach", {"job_id": j2["id"]})
check("Attach: a rejected job is not an open application", st == 409, str(r))
app.update_job(j2["id"], stage=None)
rank_before = max(p["rank"] for p in ppl)
st, r = post(f"/api/people/{pp['id']}/attach", {"job_id": jid})
check("Attach: a contact goes on a job's list in place, last in rank, still approved", st == 200 and r["person"]["job_id"] == jid
      and r["person"]["id"] == pp["id"] and r["person"]["status"] == "approved" and r["person"]["rank"] == rank_before + 1, str(r.get("person")))
st, r = post(f"/api/people/{pp['id']}/attach", {"job_id": jid})
check("Attach: the same job again changes nothing", st == 200 and r["person"]["job_id"] == jid)
st, r = post(f"/api/people/{pp['id']}/attach", {"job_id": j2["id"]})
check("Attach: a second job gets a second row for the same person", st == 200 and r["person"]["id"] == f"{j2['id']}-pat-jones-123"
      and r["person"]["job_id"] == j2["id"], str(r.get("person")))
check("Batch drafting never picks up a person you captured by hand",
      all(x["id"] != pp["id"] for x in app._approved_people(jid)) and all("pat-jones" not in x["id"] for x in app._approved_people(j2["id"])))
st, n = get("/notifications")
check("A captured person is not something waiting for your approval", n["people"] == 0, str(n))

# Draft a note: refused while the job is in process, then one LinkedIn note, never queued by auto mode
app.update_job(jid, stage="interviewing")
st, r = post(f"/api/people/{pp['id']}/draft")
check("Draft: refused for a job in process", st == 409 and "Not drafting" in r["error"] and "process" in r["error"], str(r))
app.update_job(jid, stage=None)
n_drafts = calls["drafts"]
st, r = post(f"/api/people/{pp['id']}/draft")
check("Draft: starts on your click (202) and reports it is working", st == 202 and r["busy"]["what"] == "draft", str(r))
check("Draft: a second click while it works is refused", post(f"/api/people/{pp['id']}/draft")[0] == 409)
check("Draft: finishes", wait_person(pp["id"]))
st, got = get(f"/api/people/{pp['id']}")
check("Draft: one LinkedIn note (no address yet), waiting for review, and the model was asked once for drafts",
      len(got["messages"]) == 1 and got["messages"][0]["channel"] == "linkedin" and got["messages"][0]["status"] == "review"
      and calls["drafts"] == n_drafts + 1 and not got["error"], f"{got['messages']} {got['error']} {calls}")
st, r = post(f"/api/people/{pp['id']}/draft")
check("Draft: a person with a draft waiting is not drafted again", st == 409 and "already a draft" in r["error"], str(r))

# Find their email: one dry-run lookup, logged, kept on the company's domain, not repeated
with app.db() as con:
    api1 = con.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0]
st, r = post(f"/api/people/{pp['id']}/find_email")
check("Find email: starts on your click", st == 202 and r["busy"]["what"] == "email", str(r))
check("Find email: finishes", wait_person(pp["id"]))
st, got = get(f"/api/people/{pp['id']}")
with app.db() as con:
    calls_now = [dict(x) for x in con.execute("SELECT * FROM api_calls ORDER BY rowid")][api1:]
check("Find email: an address is kept, from the finder", got["person"]["email"] and got["person"]["email_source"] == "finder", str(got["person"]))
check("Find email: exactly one lookup is logged against the job", len(calls_now) == 1 and calls_now[0]["service"] == "email"
      and calls_now[0]["job_id"] == jid, str(calls_now))
st, r = post(f"/api/people/{pp['id']}/find_email")
check("Find email: a person with an address is not looked up again", st == 409 and "Already has an email" in r["error"], str(r))

# the email draft, with auto mode on: waits for your approval, not queued behind your back
post("/settings", {"outreach_auto": True})
post(f"/api/messages/{got['messages'][0]['id']}/skip", {"reason": "Too formal for a recruiter"})
_rej = [json.loads(x) for x in open(app.LEARNING_INBOX) if '"draft_rejected"' in x]
check("Skip writes a draft_rejected event with the reason given", any(
    x["context"].get("message") == got["messages"][0]["id"] and x["context"].get("reason") == "Too formal for a recruiter" for x in _rej), str(_rej)[-300:])
st, r = post(f"/api/people/{pp['id']}/draft")
check("Draft: again once the first was skipped", st == 202, str(r))
wait_person(pp["id"])
st, got = get(f"/api/people/{pp['id']}")
em = [m for m in got["messages"] if m["channel"] == "email"]
check("Draft: with an address it is an email, and auto mode did not queue it", len(em) == 1 and em[0]["status"] == "review", str(got["messages"]))
post("/settings", {"outreach_auto": False})

# not found, then the guard against paying twice
st, r = post("/api/people/manual", dict(PERSON, name="Quinn Nobody", linkedin_url="https://www.linkedin.com/in/quinn-nobody"))
qid = r["person"]["id"]
real_ef = app.outreach.emails_from_finder
app.outreach.emails_from_finder = lambda *a, **k: {}
post(f"/api/people/{qid}/find_email"); wait_person(qid)
app.outreach.emails_from_finder = real_ef
check("Find email: nothing found is remembered", app._person_out(qid)["person"]["email_source"] == "not_found")
st, r = post(f"/api/people/{qid}/find_email")
check("Find email: a person looked up with no result is not paid for again without a yes", st == 409 and r.get("needs") == "again", str(r))
st, r = post(f"/api/people/{qid}/find_email", {"again": True})
wait_person(qid)
check("Find email: with your yes it looks again", st == 202 and app._person_out(qid)["person"]["email"], str(r))
env_keep = open(app.ENV_FILE).read()
open(app.ENV_FILE, "w").write("")
app.OUTREACH_DRY_RUN = False
st, r = post("/api/people/manual", dict(PERSON, name="Riley Notoken", linkedin_url="https://www.linkedin.com/in/riley-notoken"))
rid = r["person"]["id"]
st, r = post(f"/api/people/{rid}/find_email")
app.OUTREACH_DRY_RUN = True
open(app.ENV_FILE, "w").write(env_keep)
check("Find email: without an Apify token a live lookup refuses and says so", st == 400 and r.get("needs") == "apify_token", str(r))

# forget
st, r = post(f"/api/people/{rid}/forget")
check("Forget: a captured contact with nothing on it can be removed", st == 200 and app._person_out(rid) is None, str(r))
st, r = post(f"/api/people/{pp['id']}/forget")
check("Forget: someone on a job, or with a draft, stays", st == 409)

# ---- UI audit step 14: reading a profile with one model call, ranking the jobs, saved contacts ---------------------
check("Match: a long name with its bracketed acronym and the acronym's X unit are one company",
      app.same_company("Globex Consulting Group (GCG)", "GCG X")
      and app.same_company("GCG X", "Globex Consulting Group") and app.same_company("GCG", "GCG X"))
check("Match: a corporate suffix and a longer brand do not hide the same company", app.same_company("Acme Health Inc.", "Acme Health")
      and app.same_company("Pied Piper", "Pied Piper Partners") and app.same_company("NLC", "Northwind Labs Collective (NLC)"))
check("Match: different companies, and a generic first word, are not the same", not app.same_company("Umbrella Corp", "Globex Consulting Group")
      and not app.same_company("Bank of Springfield", "Bank") and not app.same_company("Vertex", "Vortex") and not app.same_company("", "GCG X"))


def mkjob(jid_, company, title="Strategy Lead", cu="", stage=None, applied="2026-10-01T10:00:00"):
    d = {"id": jid_, "job_key": jid_, "captured_at": applied, "status": "applied", "company": company, "title": title,
         "company_url": cu, "applied_at": applied, "folder": os.path.join(TMP, jid_), "source": "linkedin"}
    if stage:
        d["stage"] = stage
    os.makedirs(d["folder"], exist_ok=True)
    app.save_job(d)
    return d


mkjob("s14-gcgx", "GCG X", "(Senior) Operations Product Builder", "https://www.linkedin.com/company/gcgx", stage="heard_back")
mkjob("s14-gcg", "Globex Consulting Group", "Consultant", "https://www.linkedin.com/company/globex-consulting-group")
mkjob("s14-other", "Zeta Corp", "Analyst")
mkjob("s14-quartz", "Quartz Labs", "PM", "https://www.linkedin.com/company/quartz")
mkjob("s14-old", "GCG X Legacy", "Old role", "https://www.linkedin.com/company/gcgx", stage="rejected")
ours = lambda lst: [x for x in lst if x["id"].startswith("s14-")]
r_ = ours(app.open_jobs_for_person("Globex Consulting Group (GCG)", "https://www.linkedin.com/company/globex-consulting-group/"))
check("Rank: the job with the person's own company page first, then the same company by name, then the rest",
      [x["id"] for x in r_][:2] == ["s14-gcg", "s14-gcgx"] and [x["group"] for x in r_][:2] == [0, 1] and all(x["group"] == 2 for x in r_[2:]), str([(x["id"], x["group"]) for x in r_]))
check("Rank: both company groups are matches with a reason, the rest are not", r_[0]["match"] and r_[0]["reason"] == "Same company page on LinkedIn"
      and r_[1]["match"] and "GCG X" in r_[1]["reason"] and not any(x["match"] or x["reason"] for x in r_[2:]), str(r_[:2]))
check("Rank: a job in process is listed with its hold, so it can be attached and not drafted for", r_[1]["hold"] and "process" in r_[1]["hold"], r_[1]["hold"])
check("Rank: a rejected job is not offered", all(x["id"] != "s14-old" for x in r_))
r_ = ours(app.open_jobs_for_person("GCG X", ""))
check("Rank: 'GCG X' with no link finds both GCG jobs by name", {x["id"] for x in r_ if x["match"]} == {"s14-gcgx", "s14-gcg"}, str([(x["id"], x["match"]) for x in r_]))
r_ = ours(app.open_jobs_for_person("Quartz Systems", "https://www.linkedin.com/company/quartz"))
check("Rank: the same company page wins even when the names differ", r_[0]["id"] == "s14-quartz" and r_[0]["group"] == 0, str(r_[0]))
r_ = ours(app.open_jobs_for_person("", ""))
check("Rank: no company, nothing is a match", not any(x["match"] for x in r_))

RAW = {"h1": "Casey Morgan", "page_title": "Casey Morgan - Senior Talent Partner - GCG X | LinkedIn",
       "top_card": "Casey Morgan\nSenior Talent Partner at GCG X\nEvanston, Illinois, United States\nGCG X",
       "experience": "Experience\nSenior Talent Partner\nGCG X · Full-time\nJun 2024 - Present\nTechnical Recruiter\nInitech\n2019 - 2024",
       "company_links": [{"href": "https://www.linkedin.com/company/gcgx/life?trk=x", "text": "GCG X"},
                        {"href": "https://www.linkedin.com/company/initech/", "text": "Initech"}]}
person_calls, person_prompts = [], []
PERSON_SAY = {"structured": {"name": "Casey Morgan", "headline": "Senior Talent Partner at GCG X", "title": "Senior Talent Partner", "company": "GCG X",
                             "company_url": "https://www.linkedin.com/company/gcgx/", "location": "Evanston, Illinois, United States"}}


def person_claude(prompt, schema=None, **kw):
    if schema is app.PERSON_SCHEMA:
        person_calls.append(kw)
        person_prompts.append(prompt)
        return PERSON_SAY if not isinstance(PERSON_SAY, Exception) else {"error": "claude exited 1"}
    return fake_claude(prompt, schema=schema, **kw)


app.run_claude = person_claude
snap = (len(person_calls), dict(calls))
GV = {"name": "Casey Morgan", "linkedin_url": "https://www.linkedin.com/in/cmorgan/", "title": "", "headline": "", "company": "", "company_url": "",
      "location": "", "about": "GCG X builds operations software", "raw": RAW}
st, r = post("/api/people/manual", GV)
pp = r.get("person") or {}
check("Read: one model call, Sonnet at low effort with no tools", st == 201 and len(person_calls) == snap[0] + 1 and person_calls[-1].get("model") == "sonnet"
      and person_calls[-1].get("effort") == "low" and person_calls[-1].get("tools") == "", str(person_calls[-1:]))
check("Read: the prompt carries the experience text and every company link in page order", "Senior Talent Partner" in person_prompts[-1] and "Jun 2024 - Present" in person_prompts[-1]
      and person_prompts[-1].index("company/gcgx") < person_prompts[-1].index("company/initech"), person_prompts[-1][-300:])
check("Read: title, company, company link and place come back from the model, the link as the company's clean address",
      pp["title"] == "Senior Talent Partner" and pp["company"] == "GCG X" and pp["company_url"] == "https://www.linkedin.com/company/gcgx"
      and pp["location"] == "Evanston, Illinois, United States" and pp["headline"] == "Senior Talent Partner at GCG X" and pp["read"] == "model", str(pp))
check("Read: the GCG job at that company is the first match, preselected material", r["jobs"][0]["id"] == "s14-gcgx" and r["jobs"][0]["match"] and r["jobs"][0]["group"] == 0, str(r["jobs"][:2]))
check("Read: nothing was paid for or drafted by the read (only the one model call)", calls == snap[1])
PERSON_SAY = {"structured": dict(PERSON_SAY["structured"], company_url="https://www.linkedin.com/company/not-sent")}
st, r = post("/api/people/manual", dict(GV, name="Dana Fox", linkedin_url="https://www.linkedin.com/in/dana-fox"))
check("Read: a company link the page never offered is dropped, never invented, then found by its link text",
      r["person"]["company_url"] == "https://www.linkedin.com/company/gcgx" and r["person"]["company"] == "GCG X", str(r["person"]))
PERSON_SAY = {"structured": dict(PERSON_SAY["structured"], company="Acme Corp", company_url="https://www.linkedin.com/company/not-sent")}
st, r = post("/api/people/manual", dict(GV, name="Lee Wu", linkedin_url="https://www.linkedin.com/in/lee-wu"))
check("Read: a company link that matches nothing sent is empty", r["person"]["company"] == "Acme Corp" and r["person"]["company_url"] == "", str(r["person"]))
PERSON_SAY = {"error": "claude exited 1"}
n0 = len(person_calls)
st, r = post("/api/people/manual", dict(GV, name="Kim Roe", linkedin_url="https://www.linkedin.com/in/kim-roe", title="Director", headline="Director at Acme", company="Acme Health",
                                        company_url="https://www.linkedin.com/company/acme-health/", location="Chicago"))
check("Read: when the call fails the page's own reading is saved", st == 201 and len(person_calls) == n0 + 1 and r["person"]["company"] == "Acme Health"
      and r["person"]["title"] == "Director" and r["person"]["read"] == "page" and r["person"]["company_url"] == "https://www.linkedin.com/company/acme-health", str(r["person"]))
PERSON_SAY = {"structured": {"nonsense": True}}
st, r = post("/api/people/manual", dict(GV, name="Sky Lin", linkedin_url="https://www.linkedin.com/in/sky-lin", company="Acme Health"))
check("Read: an answer that is not the contract falls back to the page's reading", r["person"]["company"] == "Acme Health" and r["person"]["read"] == "page", str(r["person"]))
n0 = len(person_calls)
st, r = post("/api/people/manual", dict(GV, name="No Raw", linkedin_url="https://www.linkedin.com/in/no-raw", raw=None, company="Acme Health"))
check("Read: with no raw material the model is not asked", len(person_calls) == n0 and r["person"]["company"] == "Acme Health")
st, r = post("/api/people/manual", dict(GV, name="Junk Raw", linkedin_url="https://www.linkedin.com/in/junk-raw", raw={"company_links": "nope"}))
check("Read: raw material with nothing in it is the same as none", st == 201 and len(person_calls) == n0, str(r)[:100])
big = dict(RAW, experience="x " * 20000, top_card="y " * 5000)
cl = app.clean_person_raw(big)
check("Read: the raw material is cut to about 8,000 characters", cl and len(cl["top_card"]) + len(cl["experience"]) + len(cl["h1"]) + len(cl["page_title"]) <= 8000, str(len(cl["experience"])))

# Refresh: Robin was saved with nothing but her name; the second read fixes her
PERSON_SAY = {"structured": {"name": "Casey Morgan", "headline": "", "title": "", "company": "", "company_url": "", "location": ""}}
st, r = post("/api/people/manual", dict(GV, name="Robin Hale", linkedin_url="https://www.linkedin.com/in/robin-hale"))
fid = r["person"]["id"]
check("Refresh setup: a contact saved with no company has no matching job", r["person"]["company"] == "" and not any(x["match"] for x in r["jobs"]))
PERSON_SAY = {"structured": {"name": "Robin Hale", "headline": "CIO", "title": "Chief Information Officer", "company": "GCG X", "company_url": "https://www.linkedin.com/company/gcgx", "location": "New York"}}
n0 = len(person_calls)
st, r = post(f"/api/people/{fid}/refresh", dict(GV, name="Robin Hale", linkedin_url="https://www.linkedin.com/in/Robin-Hale/?x=1"))
check("Refresh: one call fills title, company, link, place and headline; the name is untouched", st == 200 and len(person_calls) == n0 + 1 and r["refreshed"] and r["read"] == "model"
      and r["person"]["title"] == "Chief Information Officer" and r["person"]["company"] == "GCG X" and r["person"]["company_url"].endswith("/gcgx")
      and r["person"]["location"] == "New York" and r["person"]["headline"] == "CIO" and r["person"]["name"] == "Robin Hale", str(r)[:300])
check("Refresh: the jobs come back ranked for the new company", r["jobs"][0]["id"] == "s14-gcgx" and r["jobs"][0]["match"], str(r["jobs"][:1]))
check("Refresh: job, email and messages are not touched", r["person"]["job_id"] is None and not r["person"]["email"] and r["messages"] == [])
st, r2 = get(f"/api/people/{fid}")
check("Refresh: it is saved, not only returned", r2["person"]["company"] == "GCG X" and r2["person"]["read"] == "model")
st, r = post(f"/api/people/{fid}/refresh", dict(GV, linkedin_url="https://www.linkedin.com/in/someone-else"))
check("Refresh: another person's profile is refused with the words the panel shows", st == 409 and r["error"] == "Open Robin Hale's profile first", str(r))
st, r = post(f"/api/people/{fid}/refresh", {"name": "Robin Hale"})
check("Refresh: a payload with no profile link is refused too", st == 409, str(r))
st, r = post(f"/api/people/{fid}/refresh", {"linkedin_url": "https://www.linkedin.com/in/robin-hale"})
check("Refresh: a payload with nothing read is a 400", st == 400, str(r))
st, r = post("/api/people/nobody/refresh", GV)
check("Refresh: an unknown person is a 404", st == 404)
check("Refresh: a web page cannot do it", c.post(f"/api/people/{fid}/refresh", json=GV, headers={"Origin": "https://evil.example"}).status_code == 403)
PERSON_SAY = {"error": "claude exited 1"}
st, r = post(f"/api/people/{fid}/refresh", {"linkedin_url": "https://www.linkedin.com/in/robin-hale", "raw": RAW})
check("Refresh: when the call fails and the page found nothing, what was saved is kept", st == 200 and r["read"] == "page" and r["person"]["company"] == "GCG X"
      and r["person"]["title"] == "Chief Information Officer" and r["read_error"], str(r)[:300])
st, r = post(f"/api/people/{fid}/refresh", {"linkedin_url": "https://www.linkedin.com/in/robin-hale", "raw": RAW, "company": "Acme Health", "title": "CIO"})
check("Refresh: when the call fails the page's own reading is used", r["person"]["company"] == "Acme Health" and r["person"]["title"] == "CIO", str(r["person"]))
app.run_claude = fake_claude

# Saved contacts at a company show on its job (step 14, item 4)
with app.db() as con:
    con.execute("UPDATE people SET raw=json_set(raw, '$.company', 'Globex Consulting Group (GCG)', '$.company_url', '') WHERE id=?", (fid,))
st, rows = get("/jobs")
bj = [x for x in rows if x["id"] == "s14-gcgx"][0]
check("Contacts: the job's panel row lists a saved contact at its company (by name), with nothing else changed",
      fid in [x["id"] for x in bj["contacts"]] and all(x["name"] and x["reason"] for x in bj["contacts"]), str(bj["contacts"]))
check("Contacts: a contact at another company is not listed", all(x["id"] != fid for x in [x for x in rows if x["id"] == "s14-other"][0]["contacts"]))
check("Contacts: a rejected job offers none", all(not x["contacts"] for x in rows if x["id"] == "s14-old"))
st, ov = get("/api/overview")
check("Contacts: the dashboard's overview carries them too", fid in [x["id"] for x in [j_ for j_ in ov["jobs"] if j_["id"] == "s14-gcgx"][0]["contacts"]])
st, pj = get("/api/jobs/s14-gcgx/people")
check("Contacts: the job's people panel lists them, with who and why", fid in [x["id"] for x in pj["contacts"]] and pj["contacts"][0]["reason"] and pj["job"]["contacts"], str(pj["contacts"]))
st, r = post(f"/api/people/{fid}/attach", {"job_id": "s14-gcgx"})
check("Contacts: Add to this job attaches in place (a job in process can still be attached)", st == 200 and r["person"]["job_id"] == "s14-gcgx", str(r)[:200])
st, pj = get("/api/jobs/s14-gcgx/people")
check("Contacts: once attached they are on the list, not offered again", fid not in [x["id"] for x in pj["contacts"]] and fid in [x["id"] for x in pj["people"]])
st, r = post(f"/api/people/{fid}/draft")
check("Contacts: drafting stays refused for the job in process", st == 409 and "process" in r["error"], str(r))

check("No Claude call reached the guard during the suite", not tc.CLAUDE_CALLS, str(tc.CLAUDE_CALLS[:3]))
shutil.rmtree(TMP, ignore_errors=True)
tc.report(results)
