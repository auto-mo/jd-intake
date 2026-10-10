#!/usr/bin/env python3
"""A throwaway copy of the server for building and testing the dashboard.

Runs on http://127.0.0.1:8791 against a COPY of jobhunt.db with sample outreach data seeded on
three applied jobs. The real database, the real server on 8790, the model and every paid API
are untouched: Auto is off in the copy and outreach runs in dry-run mode (fixture results, no
Apify, no email). Every optional feature is shown on in the copy, so each tab can be looked at.

Run:  python3 devserver.py          Stop: Ctrl+C. The copy is deleted on exit.
"""
import atexit
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("DEV_PORT", "8791"))

spec = importlib.util.spec_from_file_location("app_dev", os.path.join(HERE, "app.py"))
app = importlib.util.module_from_spec(spec)
sys.modules["app_dev"] = app
spec.loader.exec_module(app)

TMP = tempfile.mkdtemp(prefix="jdintake-dev-")
atexit.register(shutil.rmtree, TMP, True)
# DEV_SRC_DB points at another database to copy; never commit a copy of a real one.
src_path = os.environ.get("DEV_SRC_DB") or app.DB
if os.path.exists(src_path):                     # no database yet (a fresh install): the copy starts empty
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(os.path.join(TMP, "dev.db"))
    src.backup(dst)
    src.close(); dst.close()
app.DB = os.path.join(TMP, "dev.db")
app.DROP_DIR = os.path.join(TMP, "drop"); os.makedirs(app.DROP_DIR)
app.OUTREACH_DRY_RUN = True
app.MY_REPLIES = os.path.join(TMP, "my-replies.md")       # never the real file
app.LEARNING_INBOX = os.path.join(TMP, "learning-inbox.jsonl")
# Show every optional feature (dry run keeps them inert). The demo (demo.py) leaves sponsorship off, since the
# example person does not need it.
app.userprofile.feature = (lambda key: key != "sponsorship") if os.environ.get("JDI_DEMO") else (lambda key: True)
app.company_url_from_posting = lambda job: ""   # the dev copy never reads LinkedIn
app.company_site_from_linkedin = lambda url: ""
app.company_page_info = lambda url: {}          # nor a company page (the name-match fallback of the link backfill)
app.HANDOFF_DIR = os.path.join(TMP, "handoff")            # handoff notes go here, never into a real application folder
_real_claude = app.run_claude


def _no_model_for_handoff(prompt, schema=None, **kw):
    """The dev copy asks the model nothing for a handoff note: its summary falls back to the code-written one."""
    if schema is app.hf.SUMMARY_SCHEMA or schema is app.PERSON_SCHEMA:     # a profile read falls back to the page's own reading here
        return {"error": "dev server: no model"}
    return _real_claude(prompt, schema=schema, **kw)


app.run_claude = _no_model_for_handoff
app.HANDOFF_AUTO = True                                   # a stage move on the dev copy writes a note under HANDOFF_DIR
app.HANDOFF_BACKGROUND = False
app.init_db()

SAMPLE_PEOPLE = [
    ("Avery Sample", "Senior Talent Acquisition Partner", "Owns hiring for the strategy and operations team this role sits in."),
    ("Jordan Example", "Director, Business Strategy", "Likely hiring manager; leads the team named in the posting."),
    ("Riley Placeholder", "Strategy Manager", "Does the same work one level up and joined from an MBA program two years ago."),
    ("Casey Fixture", "University Recruiter", "Runs graduate hiring for the company's Chicago office."),
    ("Morgan Demo", "VP, Strategy and Operations", "Senior sponsor for the function; can forward to the hiring team."),
]
EMAIL = ("Hi {first},\n\nI recently applied to the {title} role at {company} ({url}) and wanted to reach out "
         "directly. Sample draft text for building the dashboard, not a real message.\n\n"
         "Would you be open to a short conversation, or to passing my resume along to the hiring team?")
DM = "Hi {first}, I applied to {title} at {company} and would value connecting. Sample note."


def seed():
    now = datetime.now().replace(microsecond=0)
    with app.db() as con:
        con.execute("UPDATE settings SET v='false' WHERE k IN ('auto','outreach_auto')")
        rows = con.execute("SELECT id, data FROM jobs WHERE status='applied' ORDER BY captured_at DESC LIMIT 3").fetchall()
        for n, r in enumerate(rows):
            d = json.loads(r["data"])
            keep = (5, 3, 0)[n]
            d["company_url"] = d.get("company_url") or f"https://www.linkedin.com/company/sample-{n}"
            d["outreach"] = {"state": ("ready", "ready", "failed")[n], "search_size": 15, "keep": keep or 5,
                             "started_at": (now - timedelta(hours=5 + n)).isoformat(),
                             "error": None if n < 2 else "Apify returned no profiles for this company (sample)."}
            con.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(d), r["id"]))
            con.execute("INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?)",
                        ((now - timedelta(hours=5 + n)).isoformat(), r["id"], "apify",
                         json.dumps({"maxItems": 15}), 15 if n < 2 else 0, 0.15, 1, None))
            for i, (name, title, why) in enumerate(SAMPLE_PEOPLE[:keep]):
                pid = f"{r['id']}-p{i}"
                email = f"{name.split()[0].lower()}@example.com" if i != 2 else None
                con.execute("INSERT OR REPLACE INTO people (id, job_id, name, title, linkedin_url, email, email_source, "
                            "rank, why, location, raw, found_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (pid, r["id"], name, title, f"https://www.linkedin.com/in/sample-{n}-{i}", email,
                             "harvestapi" if i % 2 == 0 else ("finder" if email else None), i + 1, why,
                             "Chicago, IL", "{}", (now - timedelta(hours=5)).isoformat(), "approved"))
                if i == 1:
                    con.execute("INSERT INTO api_calls VALUES (?,?,?,?,?,?,?,?)",
                                (now.isoformat(), r["id"], "email", "{}", 1, 0.02, 1, None))
                first = name.split()[0]
                fill = dict(first=first, title=d.get("title"), company=d.get("company"), url=d.get("url"))
                estatus = ["review", "queued", "sent", "failed", "review"][i]
                if email:
                    con.execute("INSERT OR REPLACE INTO messages (id, person_id, job_id, channel, subject, draft, sent_text, "
                                "audit_score, audit_notes, validator_notes, status, created_at, approved_at, scheduled_at, "
                                "sent_at, auto, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (pid + "-e", pid, r["id"], "email", f"{d.get('title')} at {d.get('company')}",
                                 EMAIL.format(**fill), EMAIL.format(**fill) if estatus in ("queued", "sent") else None,
                                 [86, 91, 78, 64, 55][i],
                                 json.dumps(["Opens on the application and the link, as the Applied rules ask.",
                                             "Middle paragraph is about their team, not your background."] if i != 4 else
                                            ["Two credentials in one email; the rule is one.",
                                             "Offers a call where the situation does not need one."]),
                                 json.dumps([] if i != 4 else ["repaired: greeting did not address the first name"]),
                                 estatus, (now - timedelta(hours=4)).isoformat(),
                                 (now - timedelta(hours=2)).isoformat() if estatus in ("queued", "sent") else None,
                                 (now + timedelta(minutes=40)).isoformat() if estatus == "queued" else None,
                                 (now - timedelta(hours=1)).isoformat() if estatus == "sent" else None,
                                 0, "SMTP server returned 451 (sample)" if estatus == "failed" else None))
                lstatus = ["review", "review", "sent", "skipped", "review"][i]
                con.execute("INSERT OR REPLACE INTO messages (id, person_id, job_id, channel, draft, audit_score, "
                            "audit_notes, validator_notes, status, created_at, sent_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (pid + "-l", pid, r["id"], "linkedin", DM.format(**fill), 88,
                             json.dumps(["Under the connection-note limit."]), "[]", lstatus,
                             (now - timedelta(hours=4)).isoformat(),
                             (now - timedelta(hours=1)).isoformat() if lstatus == "sent" else None))
        # A fourth applied job waiting on your approval of people, one of them already contacted.
        w = con.execute("SELECT id, data FROM jobs WHERE status='applied' ORDER BY captured_at DESC LIMIT 1 OFFSET 3").fetchone()
        if w:
            d = json.loads(w["data"])
            d["company_url"] = d.get("company_url") or "https://www.linkedin.com/company/sample-review"
            d["outreach"] = {"state": "people_review", "search_size": 15, "keep": 3, "people": 3,
                             "started_at": now.isoformat()}
            con.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(d), w["id"]))
            for i, (name, title, why) in enumerate(SAMPLE_PEOPLE[:3]):
                con.execute("INSERT OR REPLACE INTO people (id, job_id, name, title, linkedin_url, email, email_source, "
                            "rank, why, location, raw, found_at, status, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (f"{w['id']}-r{i}", w["id"], name, title, f"https://www.linkedin.com/in/sample-review-{i}",
                             None, None, i + 1, why, "Chicago, IL",
                             json.dumps({"headline": title + " at a sample company", "education": "Lakeview University" if i == 1 else "",
                                         "priority": "Recruiter" if i == 0 else "Hiring chain", "first": name.split()[0]}),
                             now.isoformat(), "proposed",
                             "Already contacted 2026-09-28 about a sample role at this company" if i == 2 else None))
        # Two more states to look at: one mid-search (the live pulse) and one where everything went out.
        more = con.execute("SELECT id, data FROM jobs WHERE status='applied' ORDER BY captured_at DESC LIMIT 2 OFFSET 4").fetchall()
        if len(more) == 2:
            d = json.loads(more[0]["data"]); d["company_url"] = d.get("company_url") or "https://www.linkedin.com/company/sample-live"
            d["outreach"] = {"state": "searching", "search_size": 15, "keep": 5, "started_at": now.isoformat()}
            con.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(d), more[0]["id"]))
            d = json.loads(more[1]["data"]); d["company_url"] = d.get("company_url") or "https://www.linkedin.com/company/sample-done"
            d["outreach"] = {"state": "ready", "search_size": 15, "keep": 2, "people": 2, "started_at": now.isoformat()}
            con.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(d), more[1]["id"]))
            for i, (name, title, why) in enumerate(SAMPLE_PEOPLE[3:5]):
                pid = f"{more[1]['id']}-d{i}"
                con.execute("INSERT OR REPLACE INTO people (id, job_id, name, title, linkedin_url, email, email_source, rank, why, "
                            "location, raw, found_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (pid, more[1]["id"], name, title, f"https://www.linkedin.com/in/sample-done-{i}",
                             f"done{i}@example.com", "harvestapi", i + 1, why, "Chicago, IL", "{}", now.isoformat(), "approved"))
                con.execute("INSERT OR REPLACE INTO messages (id, person_id, job_id, channel, subject, draft, sent_text, audit_score, "
                            "audit_notes, validator_notes, status, created_at, approved_at, sent_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (pid + "-e", pid, more[1]["id"], "email", "Sample subject", "Sample sent email.", "Sample sent email.",
                             88, "[]", "[]", "sent", now.isoformat(), now.isoformat(), now.isoformat()))
    return [r["id"] for r in rows]


# The side panel, served from here for a visual check: the real sidepanel.html, css and js from the
# extension folder, pointed at this server instead of 8790, with a stand-in for the Chrome APIs and for the background
# script's capture of a profile. Dev only: nothing here exists in the real server.
EXT = os.path.join(os.path.dirname(HERE), "extension")
SHIM = """<script>
window.__listeners = [];
window.chrome = {
  runtime: { onMessage: { addListener: function (f) { window.__listeners.push(f); } },
    sendMessage: function (m) {
      if (m && m.type === 'capture-active-tab') {
        var p = window.__profile || {};
        return fetch('/api/people/manual', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) })
          .then(function (r) { return r.json(); }).then(function (res) { window.__listeners.forEach(function (f) { f({ type: 'person-created', result: res }); }); });
      }
      if (m && m.type === 'refresh-person') {
        var q = window.__profile || {};
        return fetch('/api/people/' + encodeURIComponent(m.person_id) + '/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(q) })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); }).then(function (x) {
            window.__listeners.forEach(function (f) { f(x.ok ? { type: 'person-refreshed', person_id: m.person_id, result: x.d } : { type: 'person-refresh-failed', person_id: m.person_id, message: x.d.error }); });
          });
      }
      return Promise.resolve();
    } },
  tabs: { query: function (q, cb) { cb([{ id: 1, url: (window.__profile || {}).linkedin_url || 'https://www.linkedin.com/jobs/', active: true }]); },
    onActivated: { addListener: function () {} }, onUpdated: { addListener: function () {} },
    create: function (o) { window.__opened = (window.__opened || []).concat(o.url); }, update: function () {} },
  storage: { session: { get: function () { return Promise.resolve({}); }, set: function () { return Promise.resolve(); }, remove: function () {} } }
};
window.__profile = { name: 'Pat Jones', linkedin_url: 'https://www.linkedin.com/in/pat-jones-123/', title: 'Director, Strategy', headline: 'Director, Strategy at Brightwave',
  location: 'Chicago, Illinois, United States', company: 'Brightwave', company_url: 'https://www.linkedin.com/company/brightwave', about: 'I lead strategy.' };
</script>"""


@app.app.route("/_panel")
def _dev_panel():
    html = open(os.path.join(EXT, "sidepanel.html")).read()
    return html.replace('<link rel="stylesheet" href="sidepanel.css">', '<link rel="stylesheet" href="/_ext/sidepanel.css">') \
               .replace('<script src="sidepanel.js"></script>', SHIM + '<script src="/_ext/sidepanel.js"></script>')


@app.app.route("/_ext/<name>")
def _dev_ext(name):
    from flask import Response
    body = open(os.path.join(EXT, os.path.basename(name))).read()
    if name == "sidepanel.js":
        body = body.replace("http://127.0.0.1:8790", "")
    return Response(body, mimetype="text/css" if name.endswith(".css") else "application/javascript")


if __name__ == "__main__":
    ids = seed()
    for j in app.tracked_jobs():      # a note for each job already in an interview process, so the links can be looked at
        if app.handoff_wanted(j):
            app.generate_handoff(j["id"])
    print(f"dev copy at {app.DB}; sample outreach on: {', '.join(ids)}")
    print(f"dashboard: http://127.0.0.1:{PORT}/   (dry run, no model, no paid calls)")
    app.app.run(host="127.0.0.1", port=PORT, threaded=True)
