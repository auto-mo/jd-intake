#!/usr/bin/env python3
"""See jd-intake before you set it up: a dashboard full of invented jobs for the example person.

Builds a throwaway database of invented postings for Alex Rivera (examples/profile), with evaluations,
stages, a rendered resume and sample outreach, then starts the dev server on it. Nothing here calls Claude,
Apify or a mail server, and nothing is written outside a temp folder.

Run:   python3 server/demo.py           then open http://127.0.0.1:8791/  (side panel preview: /_panel)
       DEV_PORT=8800 python3 server/demo.py   to use another port
Stop:  Ctrl+C. The temp folder is deleted on exit.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
os.environ.setdefault("JDI_PROFILE_DIR", os.path.join(REPO, "examples", "profile"))
os.environ["JDI_PROFILE_DIR"] = os.path.abspath(os.environ["JDI_PROFILE_DIR"])
TMP = tempfile.mkdtemp(prefix="jdintake-demo-")
os.environ["JDI_DATA_DIR"] = TMP

spec = importlib.util.spec_from_file_location("app_demo", os.path.join(HERE, "app.py"))
app = importlib.util.module_from_spec(spec)
sys.modules["app_demo"] = app
spec.loader.exec_module(app)
app.DB = os.path.join(TMP, "demo-src.db")
app.APPS = os.path.join(TMP, "applications")
os.makedirs(app.APPS, exist_ok=True)
app.init_db()
app.company_url_from_posting = lambda job: ""
with app.db() as con:
    con.execute("INSERT OR REPLACE INTO settings VALUES ('auto','false')")
    con.execute("INSERT OR REPLACE INTO settings VALUES ('threshold','60')")
c = app.app.test_client()

JD = ("{title}\n{company}, {location}\n\nWe are hiring a {title} to join our team. You will own analysis that shapes "
      "how the business runs, partner with finance and operations leaders, build forecasts and dashboards, and turn "
      "messy data into clear recommendations.\n\nWhat you will do\n- Size opportunities and build the business case for "
      "changes to how the network, the teams and the tools run.\n- Own the weekly operating review: the metrics, the "
      "narrative and the follow-ups.\n- Build forecasts and dashboards that leaders use to make decisions every week.\n"
      "- Run cross-functional projects from scoping to rollout, with clear success measures.\n- Partner with finance on "
      "budgets, targets and the monthly close.\n\nWhat you bring\n- 4+ years in analytics, operations or strategy.\n"
      "- SQL and Python; comfort with a BI tool such as Tableau or Looker.\n- Strong written and spoken communication, "
      "including presenting to executives.\n- A habit of turning ambiguous questions into a plan.\n\nNice to have: "
      "logistics, supply chain or healthcare operations experience.\n\nThis is an invented posting for the jd-intake "
      "demo. Any resemblance to a real company is a coincidence.\n")

# (company, title, location, score, recommendation, status, stage, days ago)
JOBS = [
    ("Acme Analytics", "Senior Strategy and Operations Associate", "Chicago, IL", 84, "APPLY", "applied", "interviewing", 9),
    ("Globex", "Business Operations Manager", "Remote (US)", 79, "TAILOR", "applied", "heard_back", 7),
    ("Initech", "Operations Analytics Lead", "Chicago, IL", 76, "TAILOR", "applied", "applied", 6),
    ("Umbrella Health", "Clinical Operations Analyst", "Chicago, IL", 72, "TAILOR", "applied", "applied", 6),
    ("Hooli Logistics", "Network Planning Manager", "Chicago, IL", 81, "APPLY", "applied", "applied", 5),
    ("Stark Freight", "Strategy Analyst", "New York, NY", 68, "TAILOR", "applied", "applied", 5),
    ("Wayne Retail", "Product Operations Manager", "Remote (US)", 74, "TAILOR", "applied", "applied", 4),
    ("Soylent Foods", "Supply Chain Analyst", "Chicago, IL", 63, "TAILOR", "applied", "rejected", 12),
    ("Vandelay Imports", "Operations Manager", "New York, NY", 70, "TAILOR", "applied", "applied", 3),
    ("Cyberdyne Systems", "Senior Data Engineer", "Remote (US)", 38, "SKIP", "skipped", None, 3),
    ("Tyrell Corp", "Director of Operations", "Los Angeles, CA", 41, "SKIP", "skipped", None, 2),
    ("Wonka Industries", "Analytics Manager", "Chicago, IL", 77, "APPLY", "scored", None, 1),
]


def render_example_resume():
    """Render the example person's default base resume once; every demo job points at a copy of it."""
    out = os.path.join(TMP, "example.docx")
    sys.path.insert(0, os.path.join(REPO, "engine"))
    import engine  # noqa: E402
    engine.render(engine.content_from_base(None), out)
    try:
        return engine.convert(out)
    except Exception as e:  # noqa: BLE001  LibreOffice missing: the demo still runs, without a PDF
        print(f"demo: no resume PDF ({e})")
        return None


def main():
    now = datetime.now().replace(microsecond=0)
    pdf = render_example_resume()
    for n, (co, title, loc, score, rec, status, stage, ago) in enumerate(JOBS):
        r = c.post("/jobs", json={"url": f"https://boards.example.com/{co.lower().replace(' ', '-')}/jobs/{100 + n}",
                                  "title": title, "company": co, "location": loc, "source": "greenhouse",
                                  "text": JD.format(title=title, company=co, location=loc)})
        job = r.get_json()
        ev = {"fit_score": score, "recommendation": rec, "resume_version": "operations" if n % 3 else "analytics",
              "strengths": ["Six years of operations analytics with a measured result in each role.",
                            "The network redesign study matches the posting's planning work closely."],
              "gaps": ["No formal people management, which the posting mentions as a plus."],
              "keyword_gaps": ["executive reporting"], "honest_take": "A credible fit; lead with the network study.",
              "level_fit": "at level", "blockers": [], "build_questions": []}
        fields = dict(status=status, evaluation=ev, evaluated_at=(now - timedelta(days=ago)).isoformat(),
                      captured_at=(now - timedelta(days=ago, hours=n)).isoformat())
        if status == "applied":
            fields.update(applied_at=(now - timedelta(days=ago - 1)).date().isoformat())
            if stage and stage != "applied":
                fields.update(stage=stage, stage_at=(now - timedelta(days=1)).isoformat())
            if pdf:
                dest = os.path.join(job["folder"], f"{app.userprofile.file_stem()}_{co.replace(' ', '')}.pdf")
                shutil.copy2(pdf, dest)
                fields["build"] = {"pdf": dest, "pages": 1, "fill_ok": True, "mode": "tailored", "base_version": ev["resume_version"]}
        app.update_job(job["id"], **fields)
        with app.db() as con:
            con.execute("UPDATE jobs SET captured_at=? WHERE id=?", (fields["captured_at"], job["id"]))
    print(f"demo: {len(JOBS)} invented jobs for {app.userprofile.name()}")
    env = dict(os.environ, DEV_SRC_DB=app.DB, JDI_DEMO="1")
    import signal
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))      # a plain kill still cleans up the temp folder
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "devserver.py")], env=env, check=False)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
