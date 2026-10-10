#!/usr/bin/env python3
"""Inbox watch: the filter, the person match, rejections holding outreach, away replies drafting a dated
follow-up, the send gate, undo and correction, your own replies, interview handoff notes, and the mailer's
SMTP and IMAP shapes.

No network and no model: the mailbox read and run_claude are stubbed, the mailer runs against fake SMTP and IMAP
classes, and every send path tested returns before a send would be attempted. Example profile, temporary data.

Run:  python3 test_inbox.py
"""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tests_common as tc  # noqa: E402

TMP = tc.setup_env("jdintake-inbox-")
app = tc.load_app("app_inbox", TMP)
HERE = tc.HERE
ib = app.ib
tc.feature(app, email=True)                       # the inbox read and the sender run only with the email feature on
app.OUTREACH_DRY_RUN = False                      # the inbox read is stubbed below; nothing reaches a mailbox
MAIL_ENV = {"MAIL_ADDRESS": "alex.rivera@example.com", "MAIL_PASSWORD": "app-password", "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "465", "IMAP_HOST": "imap.example.com", "IMAP_PORT": "993", "MAIL_SENT_FOLDER": "Sent"}
app.secrets = lambda: dict(MAIL_ENV)
app.in_send_window = lambda et: True
app.backfill_company_url = lambda job_id: None    # no background LinkedIn reads racing the tests
app.init_db()
c = app.app.test_client()
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


# ── pure functions ───────────────────────────────────────────────────────────────────────────
sent = [{"email": "jordan.lee@globex.example", "person_id": "p-jordan", "name": "Jordan Lee", "job_id": "j", "message_id": "m"},
        {"email": "priya.shah@globex.example", "person_id": "p-priya", "name": "Priya Shah", "job_id": "j", "message_id": "m2"},
        {"email": "morgan.diaz@initech.example", "person_id": "p-morgan", "name": "Morgan Diaz PMP MBA", "job_id": "k",
         "message_id": "m3"}]
check("person: exact address", (ib.match_person({"from_address": "Morgan.Diaz@initech.example"}, sent) or {}).get("person_id") == "p-morgan")
check("person: other alias, same name (last.first@ at the same company)",
      (ib.match_person({"from_address": "lee.jordan@globex.example", "from_name": "Lee, Jordan"}, sent) or {}).get("person_id") == "p-jordan")
check("person: same domain, different name is no match",
      ib.match_person({"from_address": "chris.wong@globex.example", "from_name": "Wong, Chris"}, sent) is None)
check("person: credentials are not the surname",
      (ib.match_person({"from_address": "mdiaz@initech.example", "from_name": "Morgan Diaz"}, sent) or {}).get("person_id") == "p-morgan")

ctx = {"people_emails": {}, "company_domains": {"initech.example"}, "companies": ib.company_names("NLC (Northwind Labs Collective)") | {"ryan"}}
check("company names: both forms of a name with its acronym", {"nlc", "northwind labs collective"} <= ctx["companies"], str(ctx["companies"]))
check("relevant: ATS sender", ib.relevant({"from_address": "no-reply@ashbyhq.com", "subject": "Update"}, ctx) == "ats")
check("relevant: company domain", ib.relevant({"from_address": "x@initech.example", "subject": "hi"}, ctx) == "company")
check("relevant: company named in the subject",
      ib.relevant({"from_address": "kim@northwindlabs.example", "subject": "Engagement Lead - NLC"}, ctx) == "name")
check("relevant: LinkedIn rejection kept", ib.relevant({"from_address": "jobs-noreply@linkedin.com",
                                                       "subject": "Your application to Senior Consultant at Hooli"}, ctx) == "linkedin")
check("relevant: LinkedIn 'was sent' dropped", ib.relevant({"from_address": "jobs-noreply@linkedin.com",
                                                           "subject": "Alex, your application was sent to Ryan"}, ctx) is None)
check("relevant: job alert dropped though it names a company",
      ib.relevant({"from_address": "alerts@adzuna.com", "subject": "NLC is hiring"}, ctx) is None)
check("relevant: unrelated mail dropped", ib.relevant({"from_address": "news@example.org", "subject": "Weekly digest"}, ctx) is None)
check("relevant: a name inside a word does not count",
      ib.relevant({"from_address": "a@b.org", "subject": "Taylor's newsletter"}, ctx) is None)
check("return date: real and after the email", ib.valid_return_date("2026-10-12", "2026-10-09T10:08:16") == "2026-10-12")
check("return date: before the email is refused", ib.valid_return_date("2026-10-01", "2026-10-09T10:08:16") is None)
check("return date: nonsense is refused", ib.valid_return_date("Monday", "2026-10-09T10:08:16") is None)
check("follow-up day: back Monday, follow up Tuesday", ib.business_day_after("2026-10-12") == "2026-10-13")
check("follow-up day: back Friday, follow up Monday", ib.business_day_after("2026-10-16") == "2026-10-19")


# ── fixtures: two applied jobs with outreach ─────────────────────────────────────────────────
def mkjob(jid, company, title):
    job = {"id": jid, "job_key": jid, "captured_at": app.now(), "status": "applied", "company": company, "title": title,
           "applied_at": "2026-10-04T10:00:00", "folder": os.path.join(TMP, jid)}
    os.makedirs(job["folder"], exist_ok=True)
    app.save_job(job)


def mkperson(pid, jid, name, email):
    with app.db() as con:
        con.execute("INSERT INTO people (id, job_id, name, title, email, email_source, status, raw) VALUES (?,?,?,?,?,?,?,?)",
                    (pid, jid, name, "Manager", email, "finder", "approved", json.dumps({"first": name.split()[0]})))


def mkmsg(mid, pid, jid, status, sent_at=None, scheduled_at=None, kind=None):
    with app.db() as con:
        con.execute("INSERT INTO messages (id, person_id, job_id, channel, subject, draft, sent_text, status, created_at, "
                    "sent_at, scheduled_at, gmail_id, kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (mid, pid, jid, "email", "Strategy Lead application", "Hi there, a draft.", "Hi there, a draft.", status,
                     "2026-10-05T09:00:00", sent_at, scheduled_at, "g-" + mid if status == "sent" else None, kind))


def status(mid):
    return (app._message(mid) or {}).get("status")


mkjob("acme", "Acme Health", "Strategy Lead")
mkjob("globex", "Globex", "Program Manager")
mkperson("p-a1", "acme", "Ann Lee", "ann.lee@acme.com")
mkperson("p-a2", "acme", "Bo Chan", "bo.chan@acme.com")
mkperson("p-a3", "acme", "Cy Ward", "cy.ward@acme.com")
mkperson("p-g1", "globex", "Dana Fox", "dana.fox@globex.com")
mkperson("p-g2", "globex", "Eli Park", "eli.park@globex.com")
past = (datetime.now() - timedelta(minutes=5)).replace(microsecond=0).isoformat()
mkmsg("m-a1", "p-a1", "acme", "sent", sent_at="2026-10-06T10:00:00")
mkmsg("m-a2", "p-a2", "acme", "queued", scheduled_at=past)
mkmsg("m-a3", "p-a3", "acme", "review")
mkmsg("m-g1", "p-g1", "globex", "sent", sent_at="2026-10-06T11:00:00")
soon = (datetime.now() + timedelta(hours=2)).replace(microsecond=0).isoformat()
mkmsg("m-g2", "p-g2", "globex", "queued", scheduled_at=soon)

back = (datetime.now() + timedelta(days=3)).date().isoformat()
MAIL = [
    {"id": "i-rej", "thread_id": "i-rej", "from_address": "no-reply@ashbyhq.com", "from_name": "Acme Hiring Team",
     "subject": "Update from Acme Health", "date": "2026-10-08T14:00:00.000Z",
     "text": "Hi Alex, after careful consideration we have decided to move forward with other candidates."},
    {"id": "i-ooo", "thread_id": "i-ooo", "from_address": "fox.dana@globex.com", "from_name": "Fox, Dana",
     "subject": "Automatic reply: Strategy Lead application", "date": "2026-10-08T15:00:00.000Z",
     "text": f"I am out of the office until {back}. For anything urgent contact Sam Roe (sam.roe@globex.com)."},
    {"id": "i-ack", "thread_id": "i-ack", "from_address": "no-reply@us.greenhouse-mail.io", "from_name": "",
     "subject": "Thank you for applying to Globex", "date": "2026-10-04T15:00:00.000Z", "text": "We received your application."},
    {"id": "i-news", "thread_id": "i-news", "from_address": "news@example.org", "from_name": "Example News",
     "subject": "Weekly digest", "date": "2026-10-08T12:00:00.000Z", "text": "Nothing about jobs."},
]
LABELS = {"i-rej": {"kind": "rejection", "job_id": "acme", "evidence": "we have decided to move forward with other candidates"},
          "i-ooo": {"kind": "out_of_office", "job_id": "globex", "return_date": back, "delegate": "Sam Roe (sam.roe@globex.com)",
                    "evidence": f"I am out of the office until {back}."},
          "i-ack": {"kind": "received", "job_id": "globex", "evidence": "We received your application."}}
seen_prompts = []


def fake_claude(prompt, schema=None, **kw):
    seen_prompts.append(prompt)
    if schema is ib.CLASSIFY_SCHEMA:
        ids = [line.split("=== EMAIL ")[1].strip() for line in prompt.splitlines() if line.startswith("=== EMAIL ")]
        return {"structured": {"emails": [dict(LABELS[i], id=i) for i in ids if i in LABELS]},
                "timing": {"model_used": ["claude-sonnet"]}}
    if schema is ib.FOLLOWUP_SCHEMA:
        body = "Hi Dana,\n\nWelcome back. Circling back on my note about the Program Manager role in case it got buried. Would you be open to a quick chat?"
        if "ALEX ASKED FOR A REWRITE" in prompt:
            body = "Hi Dana,\n\nHope the time away was good. Would a short call this week work?"
        return {"structured": {"email_body": body}, "timing": {"model_used": [app.outreach_model()]}}
    raise AssertionError("unexpected Claude call")


app.run_claude = fake_claude
real_fetch = app.fetch_inbox
app.mailer.fetch = lambda env, days, sent=False: [dict(MAIL[0]), dict(MAIL[0]), dict(MAIL[1])]
got = real_fetch(30)
check("fetch: the mailer's read is passed through, one entry per message id", [m["id"] for m in got] == ["i-rej", "i-ooo"], str(got))
app.fetch_inbox = lambda days, sent=False: [] if sent else [dict(m) for m in MAIL]


def wait_drafted(secs=10):
    """The follow-up is written on a thread; wait until no message is still drafting."""
    import time
    end = time.time() + secs
    while time.time() < end:
        with app.db() as con:
            if not con.execute("SELECT 1 FROM messages WHERE status='drafting'").fetchone():
                return True
        time.sleep(0.05)
    return False


out = app.check_inbox(30)
wait_drafted()
check("read: four fetched, one ignored, three read", out.get("fetched") == 4 and out.get("ignored") == 1 and out.get("read") == 3, str(out))
check("read: the classifier never saw the unrelated email", not any("Weekly digest" in p for p in seen_prompts))
with app.db() as con:
    ig = con.execute("SELECT text, status FROM inbox WHERE id='i-news'").fetchone()
check("read: an ignored email keeps no body", ig and ig["status"] == "ignored" and not ig["text"])

# rejection: Acme's unsent outreach held, stage Rejected
check("rejection: queued email held", status("m-a2") == "held", status("m-a2"))
check("rejection: draft in review held", status("m-a3") == "held", status("m-a3"))
check("rejection: the sent email is untouched", status("m-a1") == "sent")
check("rejection: stage is Rejected", app.load_job("acme").get("stage") == "rejected")
check("rejection: other job untouched", status("m-g2") == "queued")
check("rejection: hold names the reason", "Acme Health sent a rejection on 2026-10-08" in (app._message("m-a2") or {}).get("error", ""))

# away reply: matched to Dana through her other alias, follow-up drafted for the weekday after
with app.db() as con:
    ooo = dict(con.execute("SELECT * FROM inbox WHERE id='i-ooo'").fetchone())
    fu = con.execute("SELECT * FROM messages WHERE kind='followup'").fetchone()
check("away: matched to the person emailed", ooo["person_id"] == "p-g1", str(ooo["person_id"]))
check("away: return date kept", ooo["return_date"] == back)
check("away: follow-up drafted, waiting for review", fu and fu["status"] == "review" and fu["reply_to"] == "m-g1", str(dict(fu) if fu else None))
check("away: follow-up subject threads the first email", fu and fu["subject"] == "Re: Strategy Lead application")
check("away: not before the weekday after return", fu and fu["not_before"][:10] == ib.business_day_after(back), fu and fu["not_before"])
check("away: follow-up prompt carried your voice and the first email",
      any("ALEX'S OWN EMAILS" in p and "Hi there, a draft." in p for p in seen_prompts))
check("acknowledgement: noted, nothing done", app._inbox_row("i-ack")["status"] == "noted")

# a second read does not act twice
out2 = app.check_inbox(30)
check("read twice: nothing new", out2.get("new") == 0, str(out2))

# approve the follow-up: the slot respects not_before, and it does not push other emails behind it
r = c.post(f"/api/messages/{fu['id']}/approve", json={})
fq = app._message(fu["id"])
check("follow-up approved: queued on or after its date", r.status_code == 200 and fq["status"] == "queued"
      and fq["scheduled_at"][:10] >= ib.business_day_after(back), f"{r.status_code} {fq['scheduled_at']}")
mkperson("p-g3", "globex", "Flo Diaz", "flo.diaz@globex.com")
mkmsg("m-g3", "p-g3", "globex", "review")
c.post("/api/messages/m-g3/approve", json={})
check("a later email is not pushed behind the dated follow-up", app._message("m-g3")["scheduled_at"] < fq["scheduled_at"],
      f"{app._message('m-g3')['scheduled_at']} vs {fq['scheduled_at']}")

# send gate: closed job held at send time; person away reslotted
with app.db() as con:
    con.execute("UPDATE messages SET status='queued', scheduled_at=?, error=NULL WHERE id='m-a3'", (past,))
check("send gate: a closed job's email is held, not sent", app.send_due() == "held" and status("m-a3") == "held")
mkmsg("m-g5", "p-g1", "globex", "queued", scheduled_at=past)     # a second email to Dana while she is away
got = app.send_due()
check("send gate: someone away is moved past their return", got == "reslotted"
      and app._message("m-g5")["scheduled_at"][:10] >= ib.business_day_after(back), f"{got} {app._message('m-g5')}")

# a reply from Dana after her first email holds the follow-up at send time
with app.db() as con:
    con.execute("INSERT INTO inbox (id, received_at, from_address, kind, job_id, person_id, status) VALUES "
                "('i-reply', '2026-10-09T09:00:00', 'dana.fox@globex.com', 'reply', 'globex', 'p-g1', 'suggest')")
    con.execute("UPDATE messages SET scheduled_at=? WHERE id=?", (past, fu["id"]))
    con.execute("UPDATE messages SET scheduled_at='2026-12-01T10:00:00' WHERE id IN ('m-g2','m-g3','m-g5')")
check("send gate: no follow-up once they wrote back", app.send_due() == "held" and "wrote back" in app._message(fu["id"])["error"],
      str(app._message(fu["id"])))

# approve, release and find-people refuse a closed job
mkperson("p-a4", "acme", "Gus Hale", "gus.hale@acme.com")
mkmsg("m-a4", "p-a4", "acme", "review")
r = c.post("/api/messages/m-a4/approve", json={})
check("approve: refused on a closed job", r.status_code == 409 and "Not queued" in r.get_json()["error"], r.get_data(as_text=True))
r = c.post("/api/messages/m-a2/release", json={})
check("release: refused while the job is closed", r.status_code == 409)
_restore_o = tc.feature(app, email=True, outreach=True)
r = c.post("/api/jobs/acme/outreach", json={})
_restore_o()
check("find people: refused on a closed job", r.status_code == 409 and "Not searching" in (r.get_json() or {}).get("error", ""),
      f"{r.status_code} {r.get_data(as_text=True)}")

# undo: the stage and the held emails come back
r = c.post("/api/inbox/i-rej/undo", json={})
check("undo: ok", r.status_code == 200 and r.get_json()["status"] == "undone", r.get_data(as_text=True))
check("undo: stage back to applied", app.load_job("acme").get("stage") is None, str(app.load_job("acme").get("stage")))
check("undo: queued email re-queued", status("m-a2") == "queued", status("m-a2"))
check("undo: review draft back in review", status("m-a3") in ("held", "review"), status("m-a3"))
check("undo: job open again", app.job_closed("acme") is None, str(app.job_closed("acme")))

# correction: you mark the acknowledgement as a rejection
r = c.post("/api/inbox/i-ack/set", json={"kind": "rejection"})
check("set: a corrected kind is acted on", r.status_code == 200 and r.get_json()["status"] == "acted"
      and app.load_job("globex").get("stage") == "rejected" and status("m-g3") == "held", r.get_data(as_text=True))
r = c.post("/api/inbox/i-ack/set", json={"kind": "received"})
check("set: and back again restores it", r.status_code == 200 and app.load_job("globex").get("stage") is None
      and status("m-g3") == "queued", f"{app.load_job('globex').get('stage')} {status('m-g3')}")

# list
r = c.get("/api/inbox")
d = r.get_json()
check("list: ignored mail not listed", r.status_code == 200 and all(i["id"] != "i-news" for i in d["items"]))
check("list: jobs offered for assignment", any(j["id"] == "acme" for j in d["jobs"]))
check("list: no email bodies in the list", all("text" not in i for i in d["items"]))

# redraft of a follow-up goes through the follow-up writer
with app.db() as con:
    con.execute("UPDATE messages SET status='review' WHERE id=?", (fu["id"],))
r = c.post(f"/api/messages/{fu['id']}/redraft", json={"feedback": "shorter"})
wait_drafted()
check("redraft: follow-up rewritten by the follow-up writer", r.status_code == 200
      and "short call" in (app._message(fu["id"])["draft"] or ""), app._message(fu["id"])["draft"])

# interview loop: nothing automated reaches a company you are in process with
mkperson("p-g6", "globex", "Hal Ito", "hal.ito@globex.com")
mkmsg("m-g6", "p-g6", "globex", "review")
mkmsg("m-g7", "p-g6", "globex", "queued", scheduled_at=past)
r = c.post("/jobs/globex/stage", json={"stage": "interviewing", "note": "first round"})
check("interview loop: moving to Interviewing holds unsent mail", r.status_code == 200
      and status("m-g6") == "held" and status("m-g7") == "held", f"{status('m-g6')} {status('m-g7')}")
check("interview loop: the hold says why", "process (Interviewing)" in (app._message("m-g6") or {}).get("error", ""))
r = c.post("/api/messages/m-g6/release", json={})
check("interview loop: release refused while in process", r.status_code == 409 and "process" in r.get_json()["error"])
with app.db() as con:
    con.execute("UPDATE messages SET status='queued', scheduled_at=?, error=NULL WHERE id='m-g7'", (past,))
check("interview loop: held at send time too", app.send_due() == "held" and status("m-g7") == "held")
mkmsg("m-g8", "p-g6", "globex", "sent", sent_at="2026-10-07T10:00:00")    # so only the gate can say no
check("interview loop: no follow-up drafted for someone at a company you are talking to",
      app.start_followup({"person_id": "p-g6", "return_date": back}) is None)
for st in ("heard_back", "assessment", "offer"):
    app.update_job("globex", stage=st)
    check(f"interview loop: {st} counts as in process", "process" in (app.job_closed("globex") or ""))
c.post("/jobs/globex/stage", json={"stage": "applied", "note": ""})
r = c.post("/api/messages/m-g6/release", json={})
check("interview loop: released once back to Applied", r.status_code == 200 and status("m-g6") == "review", r.get_data(as_text=True))

# back on the return date itself
today = datetime.now().date().isoformat()
with app.db() as con:
    con.execute("UPDATE people SET ooo_until=? WHERE id='p-g2'", (today,))
check("away: on the return date they count as back", app.person_away_until("p-g2") is None)
with app.db() as con:
    con.execute("UPDATE people SET ooo_until=? WHERE id='p-g2'", (back,))
check("away: before the return date they are away", app.person_away_until("p-g2") == back)

# ── what needs you: one rule, read by the strip, the bell, the Inbox tab and the Jobs row (UI audit step 3) ──
def mkinbox(iid, job_id, kind, status, received, why="company", return_date=None):
    with app.db() as con:
        con.execute("INSERT INTO inbox (id, received_at, from_address, from_name, subject, why, kind, job_id, status) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (iid, received, "x@example.com", "Sender", "Subject " + iid, why, kind, job_id, status))


app.update_job("globex", stage=None, stage_at="2026-10-01T00:00:00")    # your last stage change predates these emails
with app.db() as con:
    base_ids = [i for i, _ in app.inbox_needs(con)]
base_gl = c.get("/api/overview").get_json()
base_gl = [j for j in base_gl["jobs"] if j["id"] == "globex"][0]["inbox"]
app.update_job("acme", stage="rejected")
mkinbox("n-int1", "globex", "interview", "suggest", "2026-10-08T09:00:00")      # invitation
mkinbox("n-int2", "globex", "interview", "suggest", "2026-10-08T10:00:00")      # reminder: the newest wins
mkinbox("n-asm", "globex", "assessment", "suggest", "2026-10-07T09:00:00")      # a different stage: asked too
mkinbox("n-acme", "acme", "interview", "suggest", "2026-10-08T11:00:00")        # acme is Rejected: not asked
mkinbox("n-rej1", None, "rejection", "unmatched", "2026-10-08T12:00:00", why="company")   # untracked company: needs you
mkinbox("n-rej2", None, "rejection", "unmatched", "2026-10-08T12:30:00", why="ats")       # ATS notice: folded away
mkinbox("n-rej3", None, "rejection", "unmatched", "2026-10-08T13:00:00", why=None)
mkinbox("n-oth", None, "reply", "unmatched", "2026-10-08T14:00:00", why="company")        # not a rejection: not asked
mkinbox("n-und", "globex", "interview", "undone", "2026-10-09T15:00:00")                 # undone: not asked
with app.db() as con:
    got = app.inbox_needs(con)
ids = [i for i, _ in got]
mine = [i for i in ids if i.startswith("n-")]
check("needs: newest suggestion per job and stage, untracked rejections not from an ATS",
      mine == ["n-rej3", "n-rej1", "n-int2", "n-asm"], str(mine))
check("needs: a suggestion for a closed job is not asked", "n-acme" not in ids)
app.update_job("globex", stage="interviewing")
with app.db() as con:
    ids2 = [i for i, _ in app.inbox_needs(con)]
check("needs: a job already at the suggested stage, or past it, is not asked again",
      "n-int2" not in ids2 and "n-asm" not in ids2, str(ids2))
app.update_job("globex", stage=None, stage_at="2026-10-01T00:00:00")
n = c.get("/notifications").get_json()
check("notifications: inbox count, and it is part of the total",
      n["inbox"] == len(ids) and n["total"] == n["people"] + n["approve"] + n["linkedin"] + n["failed"] + n["inbox"], str(n))
inb = c.get("/api/inbox").get_json()
check("api/inbox: lists the ids that need you, same as the bell", inb["needs"] == ids and len(inb["needs"]) == n["inbox"], str(inb["needs"]))
check("api/inbox: every id that needs you is in the items", set(ids) <= {i["id"] for i in inb["items"]})
ov = {j["id"]: j for j in c.get("/api/overview").get_json()["jobs"]}
gl = ov["globex"]["inbox"]
check("overview: the undone email is not counted, the others are", gl["count"] == base_gl["count"] + 3, f"{gl} vs {base_gl}")
check("overview: newest kind and time", gl["last_at"] >= "2026-10-08T10:00:00" and gl["last_kind"], str(gl))
check("overview: needs counts the suggestions for that job", gl["needs"] == base_gl["needs"] + 2, f"{gl} vs {base_gl}")
check("overview: every job carries the four fields", all(k in ov["acme"]["inbox"] for k in ("count", "last_kind", "last_at", "needs")))
lst = {j["id"]: j for j in c.get("/jobs").get_json()}
check("GET /jobs: the same summary rides along, and is not stored with the job",
      lst["globex"]["inbox"] == gl and "inbox" not in app.load_job("globex"))
check("a job's panel read carries it too", c.get("/api/jobs/globex/people").get_json()["job"]["inbox"] == gl)
app.update_job("acme", stage=None)

# On hold: a paused search holds outreach and is undone like a rejection
mkjob("initech", "Initech", "Growth Strategist")
mkperson("p-i1", "initech", "Ivy Moss", "ivy.moss@initech.com")
mkmsg("m-i1", "p-i1", "initech", "queued", scheduled_at=soon)
with app.db() as con:
    con.execute("INSERT INTO inbox (id, received_at, from_address, subject, kind, job_id, status) VALUES "
                "('i-pause', '2026-10-09T10:00:00', 'hr@initech.com', 'Update', 'paused', 'initech', 'new')")
app.act_on_inbox("i-pause")
check("paused: stage On hold", app.load_job("initech").get("stage") == "paused", str(app.load_job("initech").get("stage")))
check("paused: unsent mail held with the reason", status("m-i1") == "held" and "put the search on hold" in app._message("m-i1")["error"])
check("paused: send gate says the search is on hold", "on hold" in (app.job_closed("initech") or ""))
check("paused: counts as open, not closed", "paused" in app.OPEN_STAGES and "paused" not in app.CLOSED_STAGES)
r = c.post("/api/inbox/i-pause/undo", json={})
check("paused: undo restores Applied", r.status_code == 200 and app.load_job("initech").get("stage") is None,
      str(app.load_job("initech").get("stage")))
app.update_job("initech", stage="rejected")
with app.db() as con:
    con.execute("UPDATE inbox SET status='new', acted=NULL WHERE id='i-pause'")
app.act_on_inbox("i-pause")
check("paused: never reopens a rejected job", app.load_job("initech").get("stage") == "rejected")
check("paused: is a kind the classifier may return", "paused" in ib.KINDS and "paused:" in ib.classify_prompt([], [], "2026-10-09"))

# suggestions only move forward
app.update_job("initech", stage="interviewing")
with app.db() as con:
    con.execute("INSERT INTO inbox (id, received_at, from_address, kind, job_id, status) VALUES "
                "('i-oldassess', '2026-10-01T10:00:00', 'hr@initech.com', 'assessment', 'initech', 'suggest')")
    ids = [x[0] for x in app.inbox_needs(con)]
check("suggest: no Assessment for a job already Interviewing", "i-oldassess" not in ids, str(ids))
app.update_job("initech", stage="heard_back", stage_at="2026-09-01T00:00:00")
with app.db() as con:
    ids = [x[0] for x in app.inbox_needs(con)]
check("suggest: Assessment offered to a job at Heard back", "i-oldassess" in ids, str(ids))
app.update_job("initech", stage="paused", stage_at="2026-10-05T10:00:00")
with app.db() as con:
    ids = [x[0] for x in app.inbox_needs(con)]
check("suggest: an email older than the last stage change does not ask again", "i-oldassess" not in ids, str(ids))
with app.db() as con:
    con.execute("INSERT INTO inbox (id, received_at, from_address, kind, job_id, status) VALUES "
                "('i-resume', '2026-10-07T10:00:00', 'hr@initech.com', 'interview', 'initech', 'suggest')")
    ids = [x[0] for x in app.inbox_needs(con)]
check("suggest: a paused search moves on when new mail arrives", "i-resume" in ids, str(ids))

# ── UI audit step 6: "Add as a job" from an email about a company you applied to outside the tool ──────────────────
check("classifier schema asks for company and title, not required",
      {"company", "title"} <= set(ib.CLASSIFY_SCHEMA["properties"]["emails"]["items"]["properties"])
      and not {"company", "title"} & set(ib.CLASSIFY_SCHEMA["properties"]["emails"]["items"]["required"]))
check("classifier prompt asks for them only when no job matches", "company and title: only when job_id is" in
      ib.classify_prompt([{"id": "x", "from_address": "a@b.c", "subject": "s", "text": "t"}], [], "2026-10-09"))

MAIL_NEW = [
    {"id": "z-asm", "thread_id": "z-asm", "from_address": "no-reply@ashbyhq.com", "from_name": "Zenith Labs Recruiting",
     "subject": "Assessment for Program Lead", "date": "2026-10-07T09:00:00.000Z", "text": "Please complete the assessment."},
    {"id": "z-rej", "thread_id": "z-rej", "from_address": "talent@yonder.example", "from_name": "Yonder Talent",
     "subject": "Your application to Yonder", "date": "2026-10-08T09:00:00.000Z", "text": "We will not move forward."},
    {"id": "z-rep", "thread_id": "z-rep", "from_address": "sam@yonder.example", "from_name": "Sam",
     "subject": "Yonder: quick note", "date": "2026-10-08T10:00:00.000Z", "text": "Thanks for the call."},
]
LABELS.update({"z-asm": {"kind": "assessment", "job_id": "", "company": "Zenith Labs", "title": "Program Lead",
                         "evidence": "Please complete the assessment."},
               "z-rej": {"kind": "rejection", "job_id": "", "company": "Yonder", "title": "Strategy Associate",
                         "evidence": "We will not move forward."},
               "z-rep": {"kind": "reply", "job_id": "acme", "company": "ignored because a job matched", "title": "x",
                         "evidence": "Thanks for the call."}})
app.fetch_inbox = lambda days, sent=False: [] if sent else [dict(m) for m in MAIL + MAIL_NEW]
ib_relevant = ib.relevant
ib.relevant = lambda msg, ctx: "company" if (msg.get("from_address") or "").endswith(("yonder.example",)) else ib_relevant(msg, ctx)
out = app.check_inbox(30)
ib.relevant = ib_relevant
check("add job: the read kept the three new emails", out.get("read") == 3, str(out))
with app.db() as con:
    zr = {r["id"]: dict(r) for r in con.execute("SELECT * FROM inbox WHERE id LIKE 'z-%'")}
check("add job: guesses stored when no job matched", zr["z-asm"]["guess_company"] == "Zenith Labs"
      and zr["z-asm"]["guess_title"] == "Program Lead" and zr["z-asm"]["status"] in ("suggest", "noted", "unmatched"), str(zr["z-asm"]))
check("add job: no guesses stored when a job matched", zr["z-rep"]["guess_company"] is None and zr["z-rep"]["job_id"] == "acme")
check("add job: an unmatched rejection waits as unmatched", zr["z-rej"]["status"] == "unmatched" and zr["z-rej"]["job_id"] is None)
check("add job: the list carries the guesses", [i for i in c.get("/api/inbox").get_json()["items"] if i["id"] == "z-asm"][0]["guess_company"] == "Zenith Labs")

r = c.post("/api/inbox/z-asm/add_job", json={"company": "", "title": "Program Lead"})
check("add job: company and role are required", r.status_code == 400, r.get_data(as_text=True))
r = c.post("/api/inbox/z-rep/add_job", json={"company": "Acme", "title": "x"})
check("add job: refused when the email already has a job", r.status_code == 409)
r = c.post("/api/inbox/i-news/add_job", json={"company": "Acme", "title": "x"})
check("add job: an ignored email is not found", r.status_code == 404)
r = c.post("/api/inbox/z-asm/add_job", json={"company": "Zenith Labs", "title": "Program Lead", "stage": "applied",
                                                  "applied_at": "2026-09-30", "note": "referral"})
d = r.get_json()
zj = d.get("job") or {}
check("add job: job made, source manual, applied on the date given", r.status_code == 201 and zj.get("source") == "manual"
      and zj.get("status") == "applied" and zj.get("applied_at", "").startswith("2026-09-30"), r.get_data(as_text=True)[:300])
check("add job: the email now belongs to it and offers the stage", d["inbox"]["job_id"] == zj["id"] and d["inbox"]["status"] == "suggest"
      and d["inbox"]["suggest_stage"] == "assessment", str(d["inbox"]))
with app.db() as con:
    check("add job: the stage suggestion reaches Needs you", ("z-asm", zj["id"]) in app.inbox_needs(con))
ov = [j for j in c.get("/api/overview").get_json()["jobs"] if j["id"] == zj["id"]][0]
check("add job: the Jobs row shows the email", ov["inbox"]["count"] == 1 and ov["inbox"]["last_kind"] == "assessment", str(ov["inbox"]))

# a stage chosen on the form is kept, and then nothing is asked again
r = c.post("/api/inbox/z-rep/set", json={"kind": "reply", "job_id": None})
r = c.post("/api/inbox/z-rep/add_job", json={"company": "Yonder", "title": "Strategy Associate", "stage": "heard_back"})
d = r.get_json()
check("add job: the stage picked on the form is kept", r.status_code == 201 and d["job"]["stage"] == "heard_back"
      and d["job"]["stage_history"][-1]["stage"] == "heard_back", r.get_data(as_text=True)[:300])
with app.db() as con:
    check("add job: and a suggestion for the stage you already chose is not asked", all(i != "z-rep" for i, _ in app.inbox_needs(con)))

# a rejection: the read closes the new job, so Undo has something to put back; held mail is none (new job)
r = c.post("/api/inbox/z-rej/add_job", json={"company": "Yonder Two", "title": "Strategy Associate", "stage": "rejected"})
d = r.get_json()
check("add job: a rejection closes the new job through the read", r.status_code == 201 and d["job"]["stage"] == "rejected"
      and d["inbox"]["status"] == "acted" and d["inbox"]["acted"].get("stage_before") == "applied", r.get_data(as_text=True)[:400])
check("add job: its outreach is closed", "rejected" in (app.job_closed(d["job"]["id"]) or ""))
r2 = c.post("/api/inbox/z-rej/undo", json={})
check("add job: undo reopens the job but leaves it tracked", r2.status_code == 200 and app.load_job(d["job"]["id"]).get("stage") is None
      and app.load_job(d["job"]["id"])["source"] == "manual")

# link to the posting: the same duplicate rule as /jobs/manual
mkinbox("z-dup", None, "reply", "unmatched", "2026-10-08T11:00:00")
r = c.post("/api/inbox/z-dup/add_job", json={"company": "Q", "title": "T", "url": "https://jobs.example.com/q/1"})
r = c.post("/api/inbox/z-dup/set", json={"kind": "reply", "job_id": None})
mkinbox("z-dup2", None, "reply", "unmatched", "2026-10-08T11:30:00")
r = c.post("/api/inbox/z-dup2/add_job", json={"company": "Q", "title": "T", "url": "https://jobs.example.com/q/1"})
check("add job: the same link twice is refused as a duplicate", r.status_code == 409 and "already tracked" in r.get_json()["error"], r.get_data(as_text=True))

# read this company's earlier mail again: ignored rows of that domain are dropped, a 60-day read starts, never for an ATS
import time as _time
reads = []
real_check = app.check_inbox
app.check_inbox = lambda days=30: reads.append(days) or {}
with app.db() as con:
    for n, a in enumerate(("hr@zeta.example", "ceo@mail.zeta.example", "hr@other.example")):
        con.execute("INSERT INTO inbox (id, received_at, from_address, status) VALUES (?,?,?,?)", (f"z-ign{n}", "2026-09-20T10:00:00", a, "ignored"))
    con.execute("INSERT INTO inbox (id, received_at, from_address, from_name, subject, kind, status) VALUES "
                "('z-zeta', '2026-10-08T12:00:00', 'hr@zeta.example', 'Zeta', 'Interview', 'interview', 'unmatched')")
    con.execute("INSERT INTO inbox (id, received_at, from_address, from_name, subject, kind, status) VALUES "
                "('z-ats', '2026-10-08T12:00:00', 'no-reply@greenhouse-mail.io', 'ATS', 'Interview', 'interview', 'unmatched')")
r = c.post("/api/inbox/z-zeta/add_job", json={"company": "Zeta", "title": "Lead", "stage": "interviewing", "reread": True})
_time.sleep(0.3)
d = r.get_json()
with app.db() as con:
    left = {x["id"] for x in con.execute("SELECT id FROM inbox WHERE id LIKE 'z-ign%'")}
check("reread: that company's ignored mail is dropped, subdomains too, others kept", r.status_code == 201
      and left == {"z-ign2"} and d["reread"] == {"dropped": 2, "started": True}, f"{left} {d.get('reread')}")
check("reread: a 60-day read was started", reads == [60], str(reads))
r = c.post("/api/inbox/z-ats/add_job", json={"company": "Atsco", "title": "Lead", "reread": True})
_time.sleep(0.2)
check("reread: never for an ATS sender", r.status_code == 201 and r.get_json()["reread"] == {"dropped": None, "started": False} and reads == [60],
      f"{r.get_data(as_text=True)[-120:]} {reads}")
app.check_inbox = real_check

# an older database gets the new columns without losing anything
import sqlite3
old_db = os.path.join(TMP, "old.db")
con_old = sqlite3.connect(old_db)
con_old.execute("CREATE TABLE inbox (id TEXT PRIMARY KEY, thread_id TEXT, received_at TEXT, from_address TEXT, from_name TEXT, "
                "subject TEXT, text TEXT, why TEXT, kind TEXT, job_id TEXT, person_id TEXT, return_date TEXT, delegate TEXT, "
                "evidence TEXT, status TEXT, acted TEXT, seen_at TEXT)")
con_old.execute("INSERT INTO inbox (id, status) VALUES ('keep', 'noted')")
con_old.commit(); con_old.close()
keep_db = app.DB
app.DB = old_db
app.init_db()
con_old = sqlite3.connect(old_db)
cols = {r_[1] for r_ in con_old.execute("PRAGMA table_info(inbox)")}
kept = con_old.execute("SELECT status FROM inbox WHERE id='keep'").fetchone()
con_old.close()
app.DB = keep_db
check("migration: the new inbox columns are added to an old database, rows kept",
      {"guess_company", "guess_title", "to_address"} <= cols and kept == ("noted",), str(cols))

# ── UI audit step 10: your own replies ────────────────────────────────────────────────────────────────────────────
q = """Hi Ann,

Tuesday works for me.

Best,
Alex

On Mon, Oct 5, 2026 at 3:12 PM Ann Lee <ann.lee@acme.com> wrote:
> Can you do Tuesday?
> Ann"""
check("strip: the quoted history after 'On ... wrote:' goes", ib.strip_quoted(q) == "Hi Ann,\n\nTuesday works for me.\n\nBest,\nAlex", repr(ib.strip_quoted(q)))
check("strip: an Outlook 'From:' block goes", ib.strip_quoted("Sounds good.\n\nFrom: Ann Lee\nSent: Monday\nTo: Alex\nSubject: x\n\nold") == "Sounds good.")
check("strip: a wrapped 'wrote:' goes", ib.strip_quoted("Thanks!\n\nOn Mon, Oct 5, 2026 at 3:12 PM Ann <a@b.com>\nwrote:\n> hi") == "Thanks!")
check("strip: quoted lines go, your own 'On Tuesday' stays", ib.strip_quoted("real\n> quoted\nOn Tuesday we met.") == "real\nOn Tuesday we met.")
check("strip: a plain 'From' in a sentence stays", ib.strip_quoted("From: my side it is fine.\nThanks") == "From: my side it is fine.\nThanks")
check("recipients: names, case and repeats", ib.recipients("Ann Lee <Ann@Acme.com>, bo@acme.com, ann@acme.com") == ["ann@acme.com", "bo@acme.com"])

mkperson("p-g9", "globex", "Ivy Nash", "ivy.nash@globex.com")
mkmsg("m-g9", "p-g9", "globex", "sent", sent_at="2026-10-06T12:00:00")
with app.db() as con:
    con.execute("INSERT INTO messages (id, person_id, job_id, channel, subject, draft, status, created_at, kind, reply_to, scheduled_at) "
                "VALUES ('m-g9-f1', 'p-g9', 'globex', 'email', 'Re: Strategy Lead application', 'Hi Ivy, circling back.', 'queued', "
                "'2026-10-09T08:00:00', 'followup', 'm-g9', ?)", (past,))
    con.execute("UPDATE messages SET scheduled_at='2026-12-01T10:00:00' WHERE status='queued' AND id != 'm-g9-f1'")
check("hold: before you write, the follow-up is clear to go", app.answered_since(app._message("m-g9-f1")) is None)

SENT = [
    {"id": "s-ann", "thread_id": "s-ann", "from_address": "alex.rivera@example.com", "from_name": "Alex Rivera", "to": "Ann Lee <ann.lee@acme.com>",
     "subject": "Re: Strategy Lead application", "date": "2026-10-08T13:00:00.000Z", "text": q},
    {"id": "g-m-a1", "thread_id": "g-m-a1", "from_address": "alex.rivera@example.com", "from_name": "Alex Rivera", "to": "ann.lee@acme.com",
     "subject": "Strategy Lead application", "date": "2026-10-06T10:00:00.000Z", "text": "Sent by the server."},
    {"id": "s-rand", "thread_id": "s-rand", "from_address": "alex.rivera@example.com", "from_name": "Alex Rivera", "to": "friend@random.org",
     "subject": "Lunch", "date": "2026-10-08T12:00:00.000Z", "text": "Lunch?"},
    {"id": "s-dom", "thread_id": "s-dom", "from_address": "alex.rivera@example.com", "from_name": "Alex Rivera", "to": "recruiting@globex.com",
     "subject": "Question about the role", "date": "2026-10-08T14:00:00.000Z", "text": "Hi, one question about the role.\n\n> old text"},
    {"id": "s-thr", "thread_id": "i-ooo", "from_address": "alex.rivera@example.com", "from_name": "Alex Rivera", "to": "someone@elsewhere.net",
     "subject": "Re: Automatic reply", "date": "2026-10-08T16:00:00.000Z", "text": "Thanks for letting me know."},
    {"id": "s-ivy", "thread_id": "s-ivy", "from_address": "alex.rivera@example.com", "from_name": "Alex Rivera", "to": "Ivy Nash <ivy.nash@globex.com>",
     "subject": "Re: Strategy Lead application", "date": "2026-10-08T17:00:00.000Z", "text": "Ivy, a quick note from me.\n\n# not a heading\n"},
]
calls = []
app.fetch_inbox = lambda days, sent=False: (calls.append(sent) or ([dict(m) for m in SENT] if sent else []))
out = app.check_inbox(30)
check("sent: both reads made, five kept of six (the server's own is skipped)", calls == [False, True] and out.get("my_replies") == 4
      and "error" in out, f"{calls} {out}")
with app.db() as con:
    sr = {r["id"]: dict(r) for r in con.execute("SELECT * FROM inbox WHERE id IN (%s)" % ",".join("'%s'" % m["id"] for m in SENT))}
check("sent: the server's own email is not stored", "g-m-a1" not in sr)
check("sent: to a person you emailed: that person and their job", sr["s-ann"]["person_id"] == "p-a1" and sr["s-ann"]["job_id"] == "acme"
      and sr["s-ann"]["kind"] == "my_reply" and sr["s-ann"]["status"] == "noted" and sr["s-ann"]["to_address"] == "ann.lee@acme.com", str(sr["s-ann"]))
check("sent: the quoted history is not stored", sr["s-ann"]["text"].endswith("Alex") and "Can you do Tuesday" not in sr["s-ann"]["text"])
check("sent: to a company's domain: its only job", sr["s-dom"]["job_id"] == "globex" and "old text" not in sr["s-dom"]["text"], str(sr["s-dom"]))
check("sent: in a thread about a job: that job", sr["s-thr"]["job_id"] == "globex" and sr["s-thr"]["person_id"] is None, str(sr["s-thr"]))
check("sent: unrelated mail is remembered as seen, no body", sr["s-rand"]["status"] == "ignored" and not sr["s-rand"]["text"] and sr["s-rand"]["to_address"] == "friend@random.org")
with app.db() as con:
    check("sent: never in Needs you", not any(i.startswith("s-") for i, _ in app.inbox_needs(con)))
d = c.get("/api/inbox").get_json()
check("sent: listed with its recipient, never as suggest", any(i["id"] == "s-ann" and i["to_address"] == "ann.lee@acme.com" and i["suggest_stage"] is None for i in d["items"]))
gl = [j for j in c.get("/api/overview").get_json()["jobs"] if j["id"] == "globex"][0]["inbox"]
check("sent: not counted as something the company said", gl["last_kind"] != "my_reply", str(gl))
txt = open(app.MY_REPLIES).read()
check("file: created with its header, which says the drafter does not read it", txt.startswith("# My replies") and "NOT read by the outreach drafter" in txt)
check("file: one entry per kept reply, with date, to whom and role, job and message id",
      txt.count("\n### ") == 4 and "to Ann Lee (Manager, Acme Health) | job: Acme Health, Strategy Lead | msg:s-ann" in txt, txt[-700:])
check("file: no quoted history in it", "Can you do Tuesday" not in txt and "Tuesday works for me." in txt)
check("file: your own '#' line cannot pass for a heading", "\n### " not in txt.split("msg:s-ivy")[1] and " # not a heading" in txt)
check("monitor: four waiting for review", app.my_replies_waiting() == (4, 4) and c.get("/api/monitor").get_json()["inbox"]["my_replies"] == {"waiting": 4, "total": 4})

calls.clear()
out = app.check_inbox(30)
check("sent: a second read adds nothing", out.get("my_replies") == 0 and open(app.MY_REPLIES).read() == txt, str(out))
with app.db() as con:
    con.execute("DELETE FROM inbox WHERE id='s-ann'")
SENT.append(dict(SENT[0]))
out = app.check_inbox(30)
check("file: even with the row gone, a message id is written once", open(app.MY_REPLIES).read().count("msg:s-ann") == 1, str(out))

open(app.MY_REPLIES, "a").write("\n## Reviewed 2026-10-09\n")
check("monitor: after a Reviewed line nothing waits", app.my_replies_waiting() == (0, 4))
SENT.append({"id": "s-new", "thread_id": "s-new", "from_address": "alex.rivera@example.com", "from_name": "Alex Rivera",
             "to": "bo.chan@acme.com", "subject": "Hello", "date": "2026-10-09T09:00:00.000Z", "text": "Hi Bo, hello."})
app.check_inbox(30)
check("monitor: a new entry after the marker counts", app.my_replies_waiting() == (1, 5), str(app.my_replies_waiting()))

# a follow-up to someone you have written to yourself is held
why = app.answered_since(app._message("m-g9-f1"))
check("hold: you wrote to them since the first email", why and why.startswith("you wrote to them yourself on 2026-10-08"), str(why))
check("hold: your own reply is not read as theirs", "they wrote back" not in (why or ""))
check("hold: send_due holds it with that reason", app.send_due() == "held" and "you wrote to them yourself" in (app._message("m-g9-f1")["error"] or ""),
      str(app._message("m-g9-f1")))
with app.db() as con:
    con.execute("UPDATE messages SET status='queued', error=NULL, scheduled_at=? WHERE id='m-g9-f1'", (past,))
    con.execute("UPDATE inbox SET received_at='2026-10-05T09:00:00' WHERE id='s-ivy'")      # before the first email went out
check("hold: a note written before the first email does not count", app.answered_since(app._message("m-g9-f1")) is None)

# the sent read failing does not fail the received read
def boom(days, sent=False):
    if sent:
        raise RuntimeError("mailbox down")
    return []
app.fetch_inbox = boom
out = app.check_inbox(30)
check("sent: a failed sent read is reported, the received read stands", "sent mail: " in (out.get("error") or "") and out.get("fetched") == 0, str(out))

# ── the mailer: SMTP send and read-only IMAP, against fake servers (no network) ─────────────────────────────────
import email as _email
import email.policy as _policy
import importlib.util as _ilu
import imaplib as _imaplib
import smtplib as _smtplib
from email.message import EmailMessage as _EM

_mspec = _ilu.spec_from_file_location("mailer_real", os.path.join(HERE, "mailer.py"))
mailer = _ilu.module_from_spec(_mspec)
_mspec.loader.exec_module(mailer)            # a fresh copy: the app's copy has its three calls replaced by refusals
smtp_log = []


class FakeSMTP:
    def __init__(self, host, port, timeout=None, context=None):
        smtp_log.append(("connect", type(self).__name__, host, port))
        self.sent = None

    def starttls(self, context=None):
        smtp_log.append(("starttls",))

    def login(self, user, pw):
        smtp_log.append(("login", user))

    def send_message(self, msg):
        smtp_log.append(("send", msg))

    def quit(self):
        smtp_log.append(("quit",))


class FakeSMTP_SSL(FakeSMTP):
    pass


def raw_mail(frm, to, subject, body, mid, date="Thu, 08 Oct 2026 14:00:00 +0000", refs=None, irt=None, html=False):
    m = _EM(policy=_policy.SMTP)
    m["From"], m["To"], m["Subject"], m["Date"], m["Message-ID"] = frm, to, subject, date, f"<{mid}>"
    if refs:
        m["References"] = refs
    if irt:
        m["In-Reply-To"] = irt
    if html:
        m.set_content(body, subtype="html")
    else:
        m.set_content(body)
    return m.as_bytes()


def dsn(rcpt, status="5.1.1", action="failed"):
    """A multipart/report delivery-status notification (RFC 3464), as a mail server sends one."""
    return ("From: Mail Delivery Subsystem <mailer-daemon@example.com>\r\nTo: alex.rivera@example.com\r\n"
            "Subject: Delivery Status Notification (Failure)\r\nDate: Fri, 09 Oct 2026 09:00:00 +0000\r\n"
            f"Message-ID: <dsn-{rcpt}>\r\nMIME-Version: 1.0\r\n"
            'Content-Type: multipart/report; report-type=delivery-status; boundary="BOUND"\r\n\r\n'
            "--BOUND\r\nContent-Type: text/plain\r\n\r\nYour message was not delivered.\r\n"
            "--BOUND\r\nContent-Type: message/delivery-status\r\n\r\n"
            "Reporting-MTA: dns; mx.example.com\r\n\r\n"
            f"Final-Recipient: rfc822; {rcpt}\r\nAction: {action}\r\nStatus: {status}\r\n"
            "Diagnostic-Code: smtp; 550 5.1.1 The email account that you tried to reach does not exist.\r\n\r\n"
            "--BOUND--\r\n").encode()


INBOX_RAW = {
    b"1": raw_mail("Jordan Lee <jordan.lee@globex.example>", "alex.rivera@example.com", "Re: Strategy role", "Thanks, Alex. Tuesday works.",
                   "r1@globex.example", refs="<root@example.com> <mid@example.com>"),
    b"2": raw_mail("Alex Rivera <alex.rivera@example.com>", "jordan.lee@globex.example", "Re: Strategy role", "My own copy.", "mine@example.com"),
    b"3": raw_mail("Initech Careers <careers@initech.example>", "alex.rivera@example.com", "Update", "<p>We will <b>not</b> move forward.</p><br>Thanks",
                   "r3@initech.example", irt="<orig@example.com>", html=True),
}
SENT_RAW = {b"7": raw_mail("Alex Rivera <alex.rivera@example.com>", "Jordan Lee <jordan.lee@globex.example>", "Hello", "Hi Jordan.", "s7@example.com")}
BOUNCE_RAW = {b"9": dsn("ghost.person@globex.example"),
              b"10": raw_mail("postmaster@initech.example", "alex.rivera@example.com", "Undeliverable: Hello",
                              "Delivery has failed to these recipients: nobody@initech.example\nRemote server returned 550 5.1.10 RESOLVER.ADR.RecipientNotFound",
                              "b10@initech.example"),
              b"11": dsn("slow.person@globex.example", status="4.4.1", action="delayed")}
imap_log = []


class FakeIMAP:
    def __init__(self, host, port, ssl_context=None, timeout=None):
        imap_log.append(("connect", host, port))
        self.folder = None

    def login(self, user, pw):
        imap_log.append(("login", user))

    def select(self, folder, readonly=False):
        imap_log.append(("select", folder, readonly))
        self.folder = folder
        return "OK", [b"3"]

    def uid(self, cmd, *args):
        imap_log.append(("uid", cmd) + tuple(a for a in args if a is not None))
        store = SENT_RAW if "Sent" in (self.folder or "") else {**INBOX_RAW, **BOUNCE_RAW}
        if cmd == "SEARCH":
            if "FROM" in args or "SUBJECT" in args:
                return "OK", [b" ".join(BOUNCE_RAW)]
            return "OK", [b" ".join(k for k in store if k not in BOUNCE_RAW)]
        if cmd == "FETCH":
            ids = args[0].split(b",")
            return "OK", [(b"%s (BODY[] {n})" % i, store[i]) for i in ids if i in store] + [b")"]
        imap_log.append(("FORBIDDEN", cmd))
        return "NO", []

    def append(self, folder, flags, when, data):
        imap_log.append(("append", folder, flags))
        return "OK", []

    def store(self, *a):
        imap_log.append(("FORBIDDEN", "store"))

    def expunge(self):
        imap_log.append(("FORBIDDEN", "expunge"))

    def logout(self):
        imap_log.append(("logout",))


_real_smtp = (_smtplib.SMTP, _smtplib.SMTP_SSL)
_real_imap = _imaplib.IMAP4_SSL
_smtplib.SMTP, _smtplib.SMTP_SSL, _imaplib.IMAP4_SSL = FakeSMTP, FakeSMTP_SSL, FakeIMAP
try:
    env = dict(MAIL_ENV)
    check("mailer: nothing missing with a full .env", mailer.missing(env) == [] and mailer.missing(env, read=True) == [])
    check("mailer: missing keys named, values never", mailer.missing({"MAIL_ADDRESS": "a@b.c"}) == ["MAIL_PASSWORD", "SMTP_HOST"]
          and mailer.missing({}, read=True) == ["MAIL_ADDRESS", "MAIL_PASSWORD", "IMAP_HOST"])
    try:
        mailer.send({}, "x@y.example", "s", "b")
        check("mailer: send without setup raises MailError", False)
    except mailer.MailError as e:
        check("mailer: send without setup raises MailError pointing at docs/email.md", "docs/email.md" in str(e) and "MAIL_ADDRESS" in str(e), str(e))
    att = os.path.join(TMP, "Alex_Rivera_Globex.pdf")
    open(att, "wb").write(b"%PDF-1.4 test")
    out = mailer.send(env, "jordan.lee@globex.example", "Strategy role", "Hi Jordan,\n\nA note.\n\nBest,\nAlex Rivera",
                      attachment=att, from_name="Alex Rivera")
    sent_msg = next(x[1] for x in smtp_log if x[0] == "send")
    check("mailer send: port 465 is SSL, logs in as MAIL_ADDRESS, no STARTTLS",
          ("connect", "FakeSMTP_SSL", "smtp.example.com", 465) in smtp_log and ("login", "alex.rivera@example.com") in smtp_log
          and ("starttls",) not in smtp_log and smtp_log[-1] == ("quit",), str(smtp_log[:3]))
    check("mailer send: returns the Message-ID without brackets", out["id"] and "<" not in out["id"] and sent_msg["Message-ID"].strip("<>") == out["id"],
          str(out))
    check("mailer send: From carries your name, To and Subject as given",
          sent_msg["From"] == "Alex Rivera <alex.rivera@example.com>" and sent_msg["To"] == "jordan.lee@globex.example"
          and sent_msg["Subject"] == "Strategy role", str(sent_msg["From"]))
    atts = [p_ for p_ in sent_msg.iter_attachments()]
    check("mailer send: the resume is attached as a PDF under its own name",
          len(atts) == 1 and atts[0].get_filename() == "Alex_Rivera_Globex.pdf" and atts[0].get_content_type() == "application/pdf")
    check("mailer send: no In-Reply-To on a first email", sent_msg["In-Reply-To"] is None)
    smtp_log.clear()
    mailer.send(dict(env, SMTP_PORT="587"), "jordan.lee@globex.example", "Re: Strategy role", "Hi Jordan, circling back.",
                in_reply_to="<first@example.com>")
    fu_msg = next(x[1] for x in smtp_log if x[0] == "send")
    check("mailer send: any other port uses STARTTLS", ("connect", "FakeSMTP", "smtp.example.com", 587) in smtp_log and ("starttls",) in smtp_log)
    check("mailer send: a follow-up threads under your own earlier email",
          fu_msg["In-Reply-To"] == "<first@example.com>" and fu_msg["References"] == "<first@example.com>", str(fu_msg["In-Reply-To"]))
    try:
        mailer.send(env, "", "s", "b")
        check("mailer send: no recipient is refused", False)
    except mailer.MailError:
        check("mailer send: no recipient is refused", True)
    imap_log.clear()
    mailer.send(dict(env, MAIL_SAVE_SENT="true"), "jordan.lee@globex.example", "s", "b")
    check("mailer send: MAIL_SAVE_SENT files a read copy in the Sent folder", ("append", '"Sent"', "\\Seen") in imap_log, str(imap_log))

    imap_log.clear()
    got_in = mailer.fetch(env, 3)
    check("mailer fetch: the inbox is opened read only", ("select", '"INBOX"', True) in imap_log, str(imap_log[:4]))
    check("mailer fetch: bodies are fetched with BODY.PEEK and nothing is stored, moved or deleted",
          any(x[:2] == ("uid", "FETCH") and "(BODY.PEEK[])" in x for x in imap_log) and not any(x[0] == "FORBIDDEN" for x in imap_log), str(imap_log))
    check("mailer fetch: your own copy in a combined folder is skipped", [m["id"] for m in got_in] == ["r1@globex.example", "r3@initech.example"],
          str([m["id"] for m in got_in]))
    m1 = got_in[0]
    check("mailer fetch: the shape app.py reads", set(m1) == {"id", "thread_id", "date", "from_address", "from_name", "to", "subject", "text"}
          and m1["from_address"] == "jordan.lee@globex.example" and m1["from_name"] == "Jordan Lee" and m1["text"] == "Thanks, Alex. Tuesday works.",
          str(m1))
    check("mailer fetch: the thread id is the conversation's root from References, else In-Reply-To",
          m1["thread_id"] == "root@example.com" and got_in[1]["thread_id"] == "orig@example.com")
    check("mailer fetch: the date is ISO 8601 with a zone", m1["date"].startswith("2026-10-08T14:00:00") and m1["date"].endswith("+00:00"), m1["date"])
    check("mailer fetch: an HTML-only body is read as text", "We will not move forward." in got_in[1]["text"] and "<" not in got_in[1]["text"],
          got_in[1]["text"])
    imap_log.clear()
    got_sent = mailer.fetch(env, 3, sent=True)
    check("mailer fetch sent: reads MAIL_SENT_FOLDER read only and keeps your own mail",
          ("select", '"Sent"', True) in imap_log and [m["id"] for m in got_sent] == ["s7@example.com"], str(imap_log[:4]))
    try:
        mailer.fetch(dict(env, MAIL_SENT_FOLDER=""), 3, sent=True)
        check("mailer fetch sent: no sent folder set is a clear error", False)
    except mailer.MailError as e:
        check("mailer fetch sent: no sent folder set is a clear error", "MAIL_SENT_FOLDER" in str(e))
    imap_log.clear()
    bounces = mailer.find_bounces(env, 14)
    byaddr = {b["recipient"]: b for b in bounces}
    check("mailer bounces: the shape app.py reads", bounces and all(set(b) == {"recipient", "code", "status", "reason", "permanent", "date"} for b in bounces),
          str(bounces))
    check("mailer bounces: a delivery-status report gives the recipient, status and a permanent failure",
          byaddr.get("ghost.person@globex.example", {}).get("permanent") is True and byaddr["ghost.person@globex.example"]["status"] == "5.1.1"
          and byaddr["ghost.person@globex.example"]["code"] == "550", str(byaddr.get("ghost.person@globex.example")))
    check("mailer bounces: a plain-text bounce is read the way a person would",
          byaddr.get("nobody@initech.example", {}).get("permanent") is True, str(byaddr.get("nobody@initech.example")))
    check("mailer bounces: a delay is reported but not permanent", byaddr.get("slow.person@globex.example", {}).get("permanent") is False,
          str(byaddr.get("slow.person@globex.example")))
    check("mailer bounces: read only too", ("select", '"INBOX"', True) in imap_log and not any(x[0] == "FORBIDDEN" for x in imap_log))
finally:
    _smtplib.SMTP, _smtplib.SMTP_SSL = _real_smtp
    _imaplib.IMAP4_SSL = _real_imap

# record_bounces: only a permanent failure marks a sent email bounced
mkperson("p-bx", "globex", "Ghost Person", "ghost.person@globex.example")
mkmsg("m-bx", "p-bx", "globex", "sent", sent_at="2026-10-07T10:00:00")
n_b = app.record_bounces([dict(byaddr["slow.person@globex.example"], recipient="ghost.person@globex.example"),
                          byaddr["ghost.person@globex.example"]])
check("bounces: a permanent failure marks the sent email bounced, a delay does not",
      n_b == 1 and status("m-bx") == "bounced" and "Bounced:" in (app._message("m-bx")["error"] or ""), f"{n_b} {app._message('m-bx')}")
app.mailer.find_bounces = lambda env, days=14: [dict(byaddr["ghost.person@globex.example"])]
check("bounces: check_bounces reads through the mailer with the email feature on", app.check_bounces() == 0 and status("m-bx") == "bounced")

# ── UI audit step 8: people you captured by hand are people you know ───────────────────────────────────────────
with app.db() as con:
    for pid_, name_, email_, co_ in (("contact-kim", "Kim Lee", "kim.lee@zeta.example", "Zeta Corp"), ("contact-taylor", "Taylor Brooks", None, "Zeta Corp")):
        con.execute("INSERT INTO people (id, job_id, name, title, linkedin_url, email, status, raw) VALUES (?,?,?,?,?,?,?,?)",
                    (pid_, None, name_, "Director", "https://www.linkedin.com/in/" + pid_, email_, "approved",
                     json.dumps({"manual": True, "company": co_, "first": name_.split()[0]})))
cctx = app.inbox_context(app.tracked_jobs())
dok = app.outreach.company_domain_ok
check("contact: one with an address is matched by it", (ib.match_person({"from_address": "Kim.Lee@zeta.example"}, cctx["sent"], dok) or {}).get("person_id") == "contact-kim")
check("contact: and mail from that address is relevant as a person's", ib.relevant({"from_address": "kim.lee@zeta.example", "subject": "hi"}, cctx) == "person")
check("contact: one with no address is matched by name on their company's domain",
      (ib.match_person({"from_address": "taylor.brooks@zeta.com", "from_name": "Brooks, Taylor"}, cctx["sent"], dok) or {}).get("person_id") == "contact-taylor")
check("contact: another company's domain with the same name is not them",
      ib.match_person({"from_address": "taylor.brooks@other.com", "from_name": "Brooks, Taylor"}, cctx["sent"], dok) is None)
check("contact: their company's domain with another name is not them",
      ib.match_person({"from_address": "pat.smith@zeta.com", "from_name": "Pat Smith"}, cctx["sent"], dok) is None)
check("contact: without the company check, an address-less contact never matches", ib.match_person(
    {"from_address": "taylor.brooks@zeta.com", "from_name": "Brooks, Taylor"}, cctx["sent"]) is None)
LABELS["z-kim"] = {"kind": "reply", "job_id": "", "company": "Zeta Corp", "title": "Lead", "evidence": "Happy to chat."}
app.fetch_inbox = lambda days, sent=False: [] if sent else [{"id": "z-kim", "thread_id": "z-kim", "from_address": "kim.lee@zeta.example",
    "from_name": "Kim Lee", "subject": "Re: hello", "date": "2026-10-09T10:00:00.000Z", "text": "Happy to chat."}]
out = app.check_inbox(30)
with app.db() as con:
    kr = dict(con.execute("SELECT * FROM inbox WHERE id='z-kim'").fetchone())
check("contact: their email is read, and filed against them", out.get("read") == 1 and kr["person_id"] == "contact-kim" and kr["why"] == "person", str(kr))
check("contact: the guesses are kept, as no tracked job matched", kr["job_id"] is None and kr["guess_company"] == "Zeta Corp")

# ── UI audit step 12: interview handoff notes ────────────────────────────────────────────────────────────────────
import hashlib
import shutil
import handoff as hf

app.HANDOFF_DIR = os.path.join(TMP, "handoff")            # never a real application folder
app.HANDOFF_AUTO, app.HANDOFF_BACKGROUND = True, False    # hooks on, run inline
summary_calls = []
SUMMARY = {"mode": "ok"}
real_claude_h = app.run_claude


def hand_claude(prompt, schema=None, **kw):
    if schema is hf.SUMMARY_SCHEMA:
        summary_calls.append(prompt)
        if SUMMARY["mode"] == "fail":
            return {"error": "claude is down"}
        if SUMMARY["mode"] == "raise":
            raise RuntimeError("boom")
        if SUMMARY["mode"] == "one":
            return {"structured": {"bullets": ["only one bullet"]}}
        return {"structured": {"bullets": [
            "**Stage:** Interviewing since 2026-10-08 " + chr(8212) + " applied 2026-10-01.",
            "**Next step:** a call with Ana Cruz, Tuesday 10/13 at 2:00 PM ET, link https://harbor.example/book/abc."]}}
    return real_claude_h(prompt, schema=schema, **kw)


app.run_claude = hand_claude
HJD = ("# AI Lead at Harbor Labs\n\n- URL: https://www.linkedin.com/jobs/search-results/?currentJobId=4400123&eBP=" + "A" * 400 +
       "&refId=zzz\n- Location: Chicago\n- Source: linkedin\n- Captured: 2026-10-01T09:00:00\n- LCA: none\n\n---\n\n"
       "About us. We build agents " + chr(8212) + " fast.\n\nRequired: Claude Code.\n")
HEVAL = """# evaluate-jd brief

FIT SCORE: 72%
RECOMMENDATION: TAILOR

SPONSORSHIP: No LCA record found; JD says nothing about sponsorship

STRENGTHS:
• Shipped agentic tools end to end.
• Founder-level ownership.

GAPS:
• No consulting brand on the resume.
• The posted pay band reads below the level you are targeting, so level may come up.

KEYWORD GAPS:
• AI Factory
• agentic development

HONEST TAKE: The tool fit is strong; the band is the question.

Build questions:
- Did other teams adopt it?
"""
HNOTES = """# Build notes: Harbor Labs / AI Lead

Mode: tailored. Base version operations. Model sonnet. Fit verdict: fit, 1 page.

## What changed from the base
- Moved the agent builds to the top third

## Claims to verify
- Route planner adopted by two regions: be ready to name who
"""


# The example profile's base resume, rendered once (locally, with LibreOffice) for the notes to read.
BASE_DOCX = os.path.join(TMP, "base", "Resume_Base.docx")
os.makedirs(os.path.dirname(BASE_DOCX))
app.engine.render(app.engine.content_from_base("operations"), BASE_DOCX)
BASE_PDF = app.engine.convert(BASE_DOCX)


def mkhand(jid, company, stage="interviewing", with_resume=True, evaluation=HEVAL, ext=None):
    folder = os.path.join(TMP, jid)
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, "JD.md"), "w").write(HJD)
    if evaluation:
        open(os.path.join(folder, "EVALUATION.md"), "w").write(evaluation)
    open(os.path.join(folder, "NOTES.md"), "w").write(HNOTES)
    job = {"id": jid, "job_key": jid, "captured_at": "2026-10-01T09:00:00", "status": "applied", "company": company, "title": "AI Lead",
           "applied_at": "2026-10-01T10:00:00", "folder": folder, "source": "linkedin", "url": "https://www.linkedin.com/jobs/view/4400123/",
           "evaluated_at": "2026-10-01T09:30:00", "evaluation": {"fit_score": 72}}
    if stage:
        job.update(stage=stage, stage_at="2026-10-08T11:00:00", stage_history=[{"stage": stage, "at": "2026-10-08T11:00:00", "note": "AI interview done"}])
    if with_resume:
        shutil.copy(BASE_PDF, os.path.join(folder, "Resume_Harbor.pdf"))
        shutil.copy(BASE_DOCX, os.path.join(folder, "Resume_Harbor.docx"))
        job["build"] = {"pdf": os.path.join(folder, "Resume_Harbor.pdf"), "docx": os.path.join(folder, "Resume_Harbor.docx"),
                        "base_version": "operations", "mode": "tailored", "pages": 1}
    app.save_job(job)
    return app.load_job(jid)


def mkmail(iid, jid, kind, at, frm, name, subject, text, pid=None, to=None, status="noted", seen=None):
    with app.db() as con:
        con.execute("INSERT INTO inbox (id, thread_id, received_at, from_address, from_name, subject, text, why, kind, job_id, person_id, "
                    "status, seen_at, to_address) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (iid, iid, at, frm, name, subject, text, "person", kind, jid, pid, status, seen or "2026-10-09T12:00:00", to))


hjob = mkhand("hoff", "Harbor Labs")
mkperson("p-h1", "hoff", "Ana Cruz", "ana.cruz@harborlabs.example")
with app.db() as con:
    con.execute("UPDATE people SET title='Senior Recruiter', rank=1 WHERE id='p-h1'")
    con.execute("INSERT INTO messages (id, person_id, job_id, channel, subject, draft, sent_text, status, created_at, sent_at, gmail_id) "
                "VALUES ('m-h1', 'p-h1', 'hoff', 'email', 'AI Lead application', 'Hi Ana, draft', 'Hi Ana,\n\nI applied to the AI Lead role.\n\nAlex', 'sent', "
                "'2026-10-05T09:00:00', '2026-10-06T10:00:00', 'g-m-h1')")
mkmail("h-int", "hoff", "interview", "2026-10-08T15:19:00", "ana.cruz@harborlabs.example", "Cruz, Ana", "Next steps with Harbor Labs",
       "Hi Alex,\n\nLet's schedule a call. Book here: https://harbor.example/book/abc\n\nAna\n\nOn Wed, Oct 7, 2026 at 3:12 PM Alex Rivera <alex.rivera@example.com> wrote:\n> quoted old words that must go",
       pid="p-h1")
mkmail("h-mine", "hoff", "my_reply", "2026-10-08T15:40:00", "alex.rivera@example.com", "Alex Rivera", "Re: Next steps with Harbor Labs",
       "Thanks Ana, Tuesday works.\n\nAlex", pid="p-h1", to="ana.cruz@harborlabs.example")
mkmail("h-ghost", "hoff", "reply", "2026-10-09T09:00:00", "sam.roe@harborlabs.example", "Roe, Sam", "Intro", "Hi, I lead the team. Sam", pid=None)
mkmail("h-ack", "hoff", "received", "2026-10-01T10:05:00", "no-reply@ashbyhq.com", "Harbor Careers", "Verify your email", "Your code is 155569.")
mkmail("h-twin", "hoff", "interview", "2026-10-09T09:10:00", "ana.cruz@talent.harborlabs.example", "Ana Cruz", "Scheduled: call",
       "Confirmed. Details: https://harbor.example/c?d=" + "x" * 300 + "&n=1 and the link https://zoom.example/j/123?pwd=abc", pid=None)
mkmail("h-noreply", "hoff", "interview", "2026-10-09T09:15:00", "noreply@scheduling.harborlabs.example", "Harbor Scheduling", "Call confirmed", "Your call is confirmed.")
mkmail("h-undone", "hoff", "rejection", "2026-10-09T09:30:00", "no-reply@ashbyhq.com", "", "Update", "unfortunately", status="undone")

check("step12 wanted: stage interviewing", app.handoff_wanted(app.load_job("hoff")))
mkhand("h-none", "Quiet Co", stage=None)
check("step12 wanted: applied with no stage and no interview mail is not", not app.handoff_wanted(app.load_job("h-none")))
mkmail("h-n1", "h-none", "received", "2026-10-02T09:00:00", "no-reply@x.com", "", "Thanks", "We received it.")
check("step12 wanted: an acknowledgement alone does not qualify", not app.handoff_wanted(app.load_job("h-none")))
mkmail("h-n2", "h-none", "assessment", "2026-10-03T09:00:00", "hr@x.com", "HR", "Assessment", "Please complete this.")
check("step12 wanted: an assessment email qualifies without a stage", app.handoff_wanted(app.load_job("h-none")))
mkhand("h-rej", "Closed Co", stage="rejected")
check("step12 wanted: rejected with no interview mail is not", not app.handoff_wanted(app.load_job("h-rej")))
mkhand("h-pau", "Paused Co", stage="paused")
check("step12 wanted: on hold qualifies", app.handoff_wanted(app.load_job("h-pau")))

out = app.generate_handoff("hoff", force=True)
path = out["file"]
doc = open(path, encoding="utf-8").read()
check("step12: written under the redirected folder, marker first", path.startswith(app.HANDOFF_DIR) and out["name"] == "HANDOFF.md"
      and doc.startswith(hf.MARKER + "\n"), path)
check("step12: nothing was written into the job's own folder", not [f for f in os.listdir(hjob["folder"]) if f.startswith("HANDOFF")])
check("step12: no em dash anywhere in what is written", chr(8212) not in doc)
for sec in ("# Harbor Labs: AI Lead, interview prep handoff", "## Where it stands", "## Timeline", "## People at Harbor Labs", "## The email thread",
            "## What the tracker's evaluation said (2026-10-01)", "## Claims on the resume to be ready to back up", "## The resume used",
            "## Things worth settling in or after the screen", "## The full job description (captured from LinkedIn, 2026-10-01)"):
    check(f"step12: section present: {sec[:46]}", sec in doc)
check("step12: the closing line about read-only email is there", doc.rstrip().endswith("every reply to a recruiter or interviewer is Alex's own.*"))
check("step12: the summary comes from the model call, em dash stripped", "**Next step:** a call with Ana Cruz, Tuesday 10/13" in doc
      and "**Stage:** Interviewing since 2026-10-08, applied" in doc and len(summary_calls) == 1, doc[doc.index("## Where"):][:300])
check("step12: the summary prompt carried the timeline and no raw URL tail", "AI interview done" in summary_calls[0] and "eBP=" not in summary_calls[0])
check("step12: the email thread has your reply, verbatim, labelled as yours", "**Alex to Ana Cruz, 2026-10-08 3:40 PM**" in doc and "> Thanks Ana, Tuesday works." in doc)
check("step12: their email is quoted with the sender's name turned around", "**Ana Cruz to Alex, 2026-10-08 3:19 PM**" in doc and "> Let's schedule a call. Book here: https://harbor.example/book/abc" in doc)
check("step12: quoted history is stripped from their email", "quoted old words that must go" not in doc and "wrote:" not in doc)
check("step12: what the tracker sent for you is in the thread, marked", "sent by the tracker" in doc and "> I applied to the AI Lead role." in doc)
check("step12: an email you undid is left out", "unfortunately" not in doc)
check("step12: an automated acknowledgement is in the timeline but not the thread, and the thread says so",
      "Email from Harbor Careers (acknowledgement): Verify your email" in doc and "155569" not in doc
      and "Automated acknowledgements (1) are in the timeline only." in doc)
check("step12: a mailer's tracking link is cut, a short link is kept", "xxxxxxxxxx" not in doc and "https://harbor.example/c?[tracking tail cut]" in doc
      and "https://zoom.example/j/123?pwd=abc" in doc)
check("step12: one person writing from two addresses is one row; a mailer is not a person",
      doc.count("| Ana Cruz |") == 1 and "ana.cruz@harborlabs.example, ana.cruz@talent.harborlabs.example" in doc and "Harbor Careers" not in doc.split("## The email thread")[0].split("## People")[1])
check("step12: timeline rows for apply, the stage move with your note, the cold email, both replies",
      "| 2026-10-01 | Applied on 2026-10-01 (tailored resume, base operations). |" in doc and "through LinkedIn" not in doc and "Stage set to Interviewing. AI interview done" in doc
      and "Cold email sent by the tracker to Ana Cruz." in doc and "You replied to Ana Cruz" in doc and "Email from Ana Cruz (interview): Next steps with Harbor Labs" in doc)
# step 14 fixes: how you applied is said only when known; a sender's signature gives a title
base_job = app.load_job("hoff")
check("step14 applied: a LinkedIn capture alone does not say how you applied", "through" not in hf.applied_text(base_job) and hf.applied_text(base_job) == "Applied on 2026-10-01.",
      hf.applied_text(base_job))
check("step14 applied: a job added by hand says so", hf.applied_text(dict(base_job, source="manual")) == "Applied on 2026-10-01 outside the tracker (job added by hand).")
check("step14 applied: a careers page link is named, without its tracking tail",
      hf.applied_text(dict(base_job, careers_url="https://careers.harbor.example/jobs/1?utm_source=x")) == "Applied on 2026-10-01 through the company's careers page (https://careers.harbor.example/jobs/1).")
check("step14 applied: a note on the Applied stage follows the date",
      hf.applied_text(dict(base_job, stage_history=[{"stage": "applied", "at": "2026-10-01T10:00:00", "note": "Referred by Dana Fox."}])) == "Applied on 2026-10-01. Referred by Dana Fox.")
check("step14 applied: no date still reads as a sentence", hf.applied_text({}) == "Applied.")
EXPECT = "Senior Talent Partner"
check("step14 signature: one line with slashes", hf.signature_title("Lee, Jordan", "Hi Alex,\n\nBest,\nJordan Lee / Senior Talent Partner / Evanston, IL\n") == EXPECT)
check("step14 signature: the lines after the name", hf.signature_title("Jordan Lee", "Hi,\n\nJordan Lee\nSenior Talent Partner\nEvanston, IL\n+1 312 555 0100") == EXPECT)
check("step14 signature: a place is not a title", hf.signature_title("Jordan Lee", "Hi,\n\nJordan Lee\nEvanston, IL\nhttps://globex.example/x") == "")
check("step14 signature: a phone, a link, an email are not titles", hf.signature_title("Jordan Lee", "Hi\n\nJordan Lee\n+1 (312) 555-0100\nwww.globex.example\njordan@globex.example") == "")
check("step14 signature: a title with a comma and two letters is still a title", hf.signature_title("Jordan Lee", "Hi\n\nJordan Lee\nDirector, HR\n") == "Director, HR")
check("step14 signature: a sign-off or a company line is not a title", hf.signature_title("Jordan Lee", "Hi\n\nJordan Lee\nThanks\nGlobex Corporation\n") == "")
check("step14 signature: no signature, no title", hf.signature_title("Jordan Lee", "Hi Alex, call me.") == "")
check("step14 signature: too long to be a title", hf.signature_title("Jordan Lee", "Hi\n\nJordan Lee\n" + "Senior Recruiter " * 10) == "")
mkhand("hsig", "Sig Co")
mkmail("hs-1", "hsig", "interview", "2026-10-08T15:19:00", "jordan.lee@sigco.example", "Lee, Jordan", "Interview",
       "Hi Alex,\n\nCould you do Tuesday?\n\nJordan Lee / Senior Talent Partner / Evanston, IL\n\nOn Wed, Oct 7 Alex wrote:\n> Jordan Lee / Quoted Title / x", pid=None)
mkmail("hs-2", "hsig", "reply", "2026-10-08T16:00:00", "pat.lee@sigco.example", "Pat Lee", "Hello", "Hi,\n\nPat Lee\nEvanston, IL\n", pid=None)
mfacts = app.handoff_facts(app.load_job("hsig"))
byn = {p_["name"]: p_ for p_ in mfacts["people"]}
check("step14 people: a sender who is not on the list gets the title from their signature", byn["Jordan Lee"]["title"] == "Senior Talent Partner", str(byn))
check("step14 people: a signature with no title leaves 'not known' in the table", byn["Pat Lee"]["title"] == "")
check("step14 timeline: the first row of a LinkedIn-captured job says nothing about how", mfacts["events"][0]["text"].startswith("Applied on 2026-10-01") and "through" not in mfacts["events"][0]["text"], mfacts["events"][0]["text"])
rendered = hf.render(mfacts, ["x"], "abc") if hasattr(hf, "render") else ""
check("step14 people: the table says 'not known' for a missing title and the title for a found one",
      "| Jordan Lee | Senior Talent Partner |" in rendered and "| Pat Lee | not known |" in rendered, rendered[rendered.find("## People"):][:400])
check("step12: people table has Ana with her title and status, and Sam, who was never searched for",
      "| Ana Cruz | Senior Recruiter | ana.cruz@harborlabs.example" in doc and "Replied 2026-10-08 (interview)" in doc
      and "| Sam Roe |" in doc and "sam.roe@harborlabs.example" in doc)
check("step12: a no-reply scheduler is not a person", "Harbor Scheduling" not in doc.split("## The email thread")[0].split("## People")[1]
      and "Email from Harbor Scheduling (interview): Call confirmed" in doc)
check("step12: the evaluation's strengths, gaps, keywords and honest take", "**Fit 72%, tailored.**" in doc and "  - Shipped agentic tools end to end." in doc
      and "  - No consulting brand on the resume." in doc and "**JD words the resume leans on:** AI Factory, agentic development." in doc
      and "**Honest take:** The tool fit is strong; the band is the question." in doc)
check("step12: claims come from NOTES.md", "- Route planner adopted by two regions: be ready to name who" in doc)
check("step12: the resume section names the file, base and mode, carries its text and the tailoring notes",
      "(`Resume_Harbor.pdf`, base operations, tailored)" in doc and "ALEX RIVERA" in doc.upper() and "Tailoring notes:" in doc
      and "- Moved the agent builds to the top third" in doc)
check("step12: things to settle names the level gap only", "- The posted pay band reads below the level you are targeting" in doc
      and "No consulting brand" not in doc.split("## Things worth settling")[1].split("## The full")[0])
check("step12: the JD has no capture header or tracking URL, and the posting link is short", "eBP=" not in doc and "AAAA" not in doc
      and "Posting: https://www.linkedin.com/jobs/view/4400123/" in doc and "We build agents, fast." in doc and "- LCA:" not in doc)
check("step12: the header names the resume to attach", "attach `Resume_Harbor.pdf`" in doc.split("\n")[5], doc.split("\n")[5][:200])

# unchanged facts: no second model call, no rewrite
n_before = len(summary_calls)
again = app.generate_handoff("hoff")
check("step12: nothing new means no rewrite and no model call", again.get("changed") is False and len(summary_calls) == n_before, str(again))

# regeneration on new mail: the inbox read is the schedule
LABELS["h-new"] = {"kind": "interview", "job_id": "hoff", "evidence": "see you Tuesday"}
app.fetch_inbox = lambda days, sent=False: [] if sent else [{"id": "h-new", "thread_id": "h-new", "from_address": "ana.cruz@harborlabs.example",
    "from_name": "Cruz, Ana", "subject": "Confirmed: Tuesday 2 PM", "date": "2026-10-09T18:00:00.000Z",
    "text": "Confirmed for Tuesday at 2 PM ET. See you then.\n\nOn Thu, Oct 8, 2026 at 3:40 PM Alex wrote:\n> Thanks Ana"}]
out = app.check_inbox(30)
doc2 = open(path, encoding="utf-8").read()
check("step12 regenerate: new mail for the job rewrote the note", out.get("read") == 1 and "Confirmed for Tuesday at 2 PM ET." in doc2
      and "Confirmed: Tuesday 2 PM" in doc2 and len(summary_calls) == n_before + 1, f"{out} {len(summary_calls)}")
check("step12 regenerate: the read email is not duplicated in the older text", doc2.count("Let's schedule a call.") == 1)
n2 = len(summary_calls)
app.fetch_inbox = lambda days, sent=False: []
app.check_inbox(30)
check("step12 regenerate: a read with nothing new does not call the model", len(summary_calls) == n2)
# mail for a job that does not qualify does not write a note
LABELS["h-q"] = {"kind": "received", "job_id": "h-rej", "evidence": "thanks"}
mkperson("p-hq", "h-rej", "Quin Roe", "quin.roe@closedco.example")
app.fetch_inbox = lambda days, sent=False: [] if sent else [{"id": "h-q", "thread_id": "h-q", "from_address": "quin.roe@closedco.example",
    "from_name": "Quin Roe", "subject": "Thanks", "date": "2026-10-09T18:05:00.000Z", "text": "thanks"}]
app.check_inbox(30)
check("step12 regenerate: a job that is not in an interview process gets no note", not os.path.exists(os.path.join(app.HANDOFF_DIR, "h-rej", "HANDOFF.md")))

# stage change writes it once
n3 = len(summary_calls)
mkhand("h-stage", "Stage Co", stage=None)
r_ = c.post("/jobs/h-stage/stage", json={"stage": "assessment", "note": "OA sent"})
check("step12 stage: moving to Assessment writes the note", r_.status_code == 200 and os.path.exists(os.path.join(app.HANDOFF_DIR, "h-stage", "HANDOFF.md"))
      and len(summary_calls) == n3 + 1)
c.post("/jobs/h-rej/stage", json={"stage": "withdrawn", "note": ""})
check("step12 stage: a closing stage does not", not os.path.exists(os.path.join(app.HANDOFF_DIR, "h-rej", "HANDOFF.md")))
c.post("/jobs/h-none/stage", json={"stage": "applied", "note": ""})
check("step12 stage: nor does 'applied'", not os.path.exists(os.path.join(app.HANDOFF_DIR, "h-none", "HANDOFF.md")))

# the hand-written file is never overwritten; the note goes beside it
mkhand("h-hand", "Hand Co")
hand_dir = os.path.join(app.HANDOFF_DIR, "h-hand")
os.makedirs(hand_dir, exist_ok=True)
HAND = "# Hand Co, by hand\n\nMy own notes.\n"
open(os.path.join(hand_dir, "HANDOFF.md"), "w").write(HAND)
o = app.generate_handoff("h-hand", force=True)
check("step12 hand-written: left byte for byte as it was", open(os.path.join(hand_dir, "HANDOFF.md")).read() == HAND)
check("step12 hand-written: the note is HANDOFF.generated.md, and says so", o["name"] == "HANDOFF.generated.md" and os.path.exists(os.path.join(hand_dir, "HANDOFF.generated.md"))
      and "A hand-written HANDOFF.md sits beside this file" in open(os.path.join(hand_dir, "HANDOFF.generated.md")).read())
o2 = app.generate_handoff("h-hand", force=True)
check("step12 hand-written: a second write still leaves it alone", open(os.path.join(hand_dir, "HANDOFF.md")).read() == HAND and o2["name"] == "HANDOFF.generated.md")
mkmail("h-hand-1", "h-hand", "interview", "2026-10-09T10:00:00", "x@handco.example", "X Y", "Call", "Call me.", status="noted", seen="2999-01-01T00:00:00")
app.fetch_inbox = lambda days, sent=False: []
app.check_inbox(30)
check("step12 hand-written: the inbox hook leaves it alone too", open(os.path.join(hand_dir, "HANDOFF.md")).read() == HAND)
info = app.handoff_info(app.load_job("h-hand"))
check("step12 hand-written: the link opens the generated note, not the hand-written one", info and info["name"] == "HANDOFF.generated.md", str(info))
# a hand-written file that the generator wrote is replaced in place, and no .generated.md appears
check("step12 own file: replaced in place with no .generated.md beside it", not os.path.exists(os.path.join(app.HANDOFF_DIR, "hoff", "HANDOFF.generated.md")))

# the model call fails: a code-written summary, and the file still gets written
for mode, label in (("fail", "an error"), ("raise", "an exception"), ("one", "an unusable answer")):
    SUMMARY["mode"] = mode
    o = app.generate_handoff("hoff", force=True)
    d_ = open(o["file"], encoding="utf-8").read()
    check(f"step12 fallback: {label} gives a code-written summary and still writes the note",
          o["summary"] == "code" and "**Stage:** Interviewing since 2026-10-08. Applied 2026-10-01." in d_
          and "**Latest email from them:** Ana Cruz, 2026-10-09" in d_ and "written by code because the model call failed" in d_ and "## The email thread" in d_)
SUMMARY["mode"] = "ok"
o = app.generate_handoff("hoff", force=True)
check("step12 fallback: the next good call replaces the code-written summary", o["summary"] == "claude"
      and "written by code" not in open(o["file"], encoding="utf-8").read())

# routes
r_ = c.get("/api/jobs/h-none/handoff")
check("step12 route: GET 404 when there is no note", r_.status_code == 404)
r_ = c.get("/api/jobs/hoff/handoff")
check("step12 route: GET serves the markdown as text", r_.status_code == 200 and r_.mimetype == "text/plain" and r_.get_data(as_text=True).startswith(hf.MARKER)
      and "no-store" in r_.headers.get("Cache-Control", ""), f"{r_.status_code} {r_.mimetype}")
check("step12 route: GET is read only (no POST body needed, nothing changed)", open(path, encoding="utf-8").read() == r_.get_data(as_text=True))
r_ = c.post("/api/jobs/h-none/handoff", json={})
j_ = r_.get_json()
check("step12 route: POST writes one on demand for an applied job, even with no interview yet", r_.status_code == 200 and j_["name"] == "HANDOFF.md"
      and j_["info"]["name"] == "HANDOFF.md" and os.path.exists(os.path.join(app.HANDOFF_DIR, "h-none", "HANDOFF.md")), str(j_))
check("step12 route: POST 404 for an unknown job", c.post("/api/jobs/nope/handoff", json={}).status_code == 404)
with app.db() as con:
    con.execute("UPDATE jobs SET status='scored', data=json_set(data, '$.status', 'scored') WHERE id='h-none'")
check("step12 route: POST 409 for a job not marked submitted", c.post("/api/jobs/h-none/handoff", json={}).status_code == 409)
ov = {j["id"]: j for j in c.get("/api/overview").get_json()["jobs"]}
check("step12 overview: the Jobs row carries the handoff info when a note exists, None when not",
      ov["hoff"]["handoff"] and ov["hoff"]["handoff"]["name"] == "HANDOFF.md" and ov["h-rej"]["handoff"] is None, str(ov["hoff"]["handoff"]))
lst = {j["id"]: j for j in c.get("/jobs").get_json()}
check("step12 panel list: GET /jobs carries it too", lst["hoff"]["handoff"] and lst["h-rej"]["handoff"] is None)
check("step12 stored: the info is computed, never saved in the job", "handoff" not in app.load_job("hoff"))

# a resume that repeats itself is flagged inside the note (step 13 tie-in)
eng_ = app.engine
dupc = eng_.apply_edits(eng_.content_from_base("operations"), {"build_edits": [
    {"index": 1, "label": "Route planner, a Python tool", "text": "Wrote a small Python tool that plans daily delivery routes for one region, cutting planning time from three hours to twenty minutes."}]})
eng_.render(dupc, os.path.join(hjob["folder"], "Resume_Harbor.docx"))
o = app.generate_handoff("hoff", force=True)
d_ = open(o["file"], encoding="utf-8").read()
check("step12 resume check: a resume that repeats itself is called out in the note", "**Check:** the tracker's duplicate check found a problem" in d_
      and "own it plainly" in d_)
shutil.copy(BASE_DOCX, os.path.join(hjob["folder"], "Resume_Harbor.docx"))

# a job built elsewhere: the note goes in that folder; no resume, no evaluation: those sections say so or are left out
ext = os.path.join(TMP, "external-build")
os.makedirs(ext)
hx = mkhand("h-ext", "Ext Co", with_resume=False, evaluation=None)
app.update_job("h-ext", external_folder=ext)
app.HANDOFF_DIR = None
o = app.generate_handoff("h-ext", force=True)
check("step12 external: written into the folder the job was built in", o["file"] == os.path.join(ext, "HANDOFF.md") and os.path.exists(o["file"]))
dx = open(o["file"], encoding="utf-8").read()
check("step12 external: no resume and no evaluation are said plainly or left out", "No resume file is recorded for this job." in dx
      and "## What the tracker's evaluation said" not in dx and "## Things worth settling" not in dx)
app.HANDOFF_DIR = os.path.join(TMP, "handoff")
app.HANDOFF_AUTO = False
app.run_claude = real_claude_h

shutil.rmtree(TMP, ignore_errors=True)
tc.report(results)
