#!/usr/bin/env python3
"""Offline regression tests for the jd-intake server. No model calls, no network.

Runs against the invented example profile (examples/profile, Alex Rivera), a temporary database and a
temporary applications directory, so your own jobs and folders are never touched.

Run:  python3 test_api.py
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tests_common as tc  # noqa: E402

TMP = tc.setup_env("jdintake-test-")
app = tc.load_app("app_under_test", TMP)
HERE = tc.HERE
app.init_db()
c = app.app.test_client()
_real_backfill = app.backfill_company_url
_real_revise_worker = app.revise_worker          # later stubbed for the route tests; step 13 runs the real one
app.backfill_company_url = lambda job_id: None   # no background lookups racing the tests

# An invented approaches file (approaches.yaml is optional in a profile; the example has none).
APPROACHES = os.path.join(TMP, "approaches.yaml")
with open(APPROACHES, "w") as f:
    f.write("""approaches:
  builder:
    name: Builder
    signals: [prototype, ship, hands-on, python, agents]
    lead_with: the system you built and what it changed
    push_down: process work
    builds_section: always
  program_ops:
    name: Program and governance
    signals: [tracker, raid, milestones, decision log, status updates, readouts, approvals, escalate, dependencies, governed]
    lead_with: the coordination, the cadence and the decisions it produced
    push_down: technical build detail
    builds_section: never
    projects: [Operations dashboard]
    skills_lines: [Program management, Reporting]
    skills_title: SKILLS
    drop_projects: [coursework]
    watch: [do not invent process detail the profile does not hold]
    learned: [a governance reader skips past build bullets]
""")
app.approaches_yaml = lambda: APPROACHES

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def post(path, body=None):
    r = c.post(path, json=body if body is not None else {})
    try:
        return r.status_code, r.get_json()
    except Exception:  # noqa: BLE001
        return r.status_code, None


def get(path):
    r = c.get(path)
    return r.status_code, r.get_json()


CAPTURE = {"url": "https://www.linkedin.com/jobs/view/9000001/", "title": "Strategy Consultant",
           "company": "Acme Analytics", "location": "Chicago, IL", "text": "z" * 3000, "source": "linkedin"}

# ---- A4: capture, folder, LCA, job key -------------------------------------------------
st, job = post("/jobs", CAPTURE)
check("A4 capture returns 201", st == 201, f"got {st}")
check("A4 job key from LinkedIn id", job["job_key"] == "linkedin:9000001", job["job_key"])
check("A4 capture quality ok", job["capture_quality"] == "ok", job["capture_quality"])
check("A4 JD.md written", os.path.exists(os.path.join(job["folder"], "JD.md")))
check("A4 no sponsorship lookup with the sponsorship feature off", job.get("lca") is None, str(job.get("lca")))
if tc.lca_data_present():
    _restore = tc.feature(app, sponsorship=True)
    _lca = app.lca_for("Acme Analytics")
    check("A4 LCA lookup runs with the plug-in on and its data downloaded", _lca is None or "matched_name" in _lca or _lca.get("missing"),
          str(_lca)[:120])
    _restore()
else:
    tc.skip(results, "A4 LCA lookup against downloaded data",
            "plugins/sponsorship/data/ is empty (run plugins/sponsorship/download_lca.py to enable this test)")
check("A4 text_head present for the panel", bool(job.get("text_head")))
jid = job["id"]

# ---- A4: duplicate -----------------------------------------------------------------------
st, dup = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9000001"))
check("A4 duplicate detected, same id", dup["id"] == jid and dup.get("duplicate_of"), str(dup.get("duplicate_of")))

# ---- A6: evaluate refuses an empty capture ---------------------------------------------
st, empty = post("/jobs", {"url": "https://boards.greenhouse.io/x/jobs/1", "title": "Empty",
                           "company": "Nobody", "text": "", "source": "greenhouse"})
check("A6 empty capture flagged", empty["capture_quality"] == "empty", empty["capture_quality"])
st, err = post(f"/jobs/{empty['id']}/evaluate")
check("A6 evaluate on empty refused with 400", st == 400, f"got {st}: {err}")

# ---- A5: re-capture overwrites an empty capture in place -------------------------------
st, re_cap = post("/jobs", {"url": "https://boards.greenhouse.io/x/jobs/1", "title": "Now Filled",
                            "company": "Nobody", "text": "y" * 2500, "source": "greenhouse"})
check("A5 re-capture keeps the same id", re_cap["id"] == empty["id"], re_cap["id"])
check("A5 re-capture marked and upgraded", re_cap.get("recaptured") and re_cap["capture_quality"] == "ok")
check("A5 re-capture is not a duplicate", not re_cap.get("duplicate_of"))
st, third = post("/jobs", {"url": "https://boards.greenhouse.io/x/jobs/1", "title": "Same again",
                           "company": "Nobody", "text": "y" * 2500, "source": "greenhouse"})
check("A5 equal-length re-capture is a duplicate", bool(third.get("duplicate_of")))

# ---- v2 answers: composition, write-back, legacy ----------------------------------------
ev = {"fit_score": 80, "recommendation": "TAILOR", "resume_version": "analytics", "sponsorship": "silent",
      "strengths": [], "gaps": [], "keyword_gaps": [], "honest_take": "t", "brief": "b",
      "sponsorship_flag": "silent", "level_fit": "at_level",
      "build_questions": [{"id": "q1", "question": "Used Smartsheet?", "why": "JD names it",
                           "type": "yes_no", "options": ["Yes, hands on", "No"], "affects": "Tools line"}]}
app.update_job(jid, status="scored", evaluation=ev, questions=ev["build_questions"])

st, gated = post(f"/jobs/{jid}/approve", {"cover_letter": False})
check("Approve with open questions waits for answers", gated["status"] == "questions", gated["status"])

# remember_to_profile appends to profile.md in the profile directory: point that one file at a temp copy so the
# shipped example is never written to.
TMP_PROFILE_MD = os.path.join(TMP, "profile.md")
shutil.copy(os.path.join(tc.EXAMPLE_PROFILE, "profile.md"), TMP_PROFILE_MD)
_real_path = app.userprofile.path
app.ROOT = TMP

app.build_worker = lambda job_id: None            # do not run a real build in the test
job_now = app.load_job(jid)
app.compose_answers_md(dict(job_now, answer_choices=[{"id": "q1", "choice": "No", "remember": True}],
                            answers=[{"text": "nothing else", "at": "now"}]))
answers_md = open(os.path.join(job_now["folder"], "ANSWERS.md")).read()
check("Answers written as Q and A pairs", "Q: Used Smartsheet?" in answers_md and "A: No" in answers_md, answers_md[:80])
check("Answers carry what the answer affects", "affects: Tools line" in answers_md)
app.userprofile.path = lambda name: TMP_PROFILE_MD if name == "profile.md" else _real_path(name)
app.remember_to_profile(job_now, [{"id": "q1", "choice": "No", "remember": True}])
app.userprofile.path = _real_path
prof = open(TMP_PROFILE_MD).read()
check("The shipped example profile.md was not written to", "Used Smartsheet?" not in app.userprofile.read_text("profile.md"))
check("Remembered answer appended to the profile", "Used Smartsheet?" in prof and "**No**" in prof, prof[-120:])

legacy = dict(job_now, evaluation={"build_questions": ["A plain legacy question?"]},
              answer_choices=[], answers=[])
app.compose_answers_md(legacy)
check("Legacy string questions still compose", "A plain legacy question?" in
      open(os.path.join(job_now["folder"], "ANSWERS.md")).read())

# ---- evaluation pre-pass: code settles the anchors, the model keeps the judgment -----------
jd_a = ("Senior Strategy Consultant. 8+ years of consulting experience required. We are unable to sponsor "
        "visas. Tools: Snowflake, Looker and Smartsheet. You will own analytics for our clients: data pipelines, "
        "dashboards, insights and SQL. "
        "Founded 20 years ago.")
_off = app.pre_evaluate({"title": "Senior Strategy Consultant", "prescreen": app.pre_screen(jd_a)}, jd_a)
check("pre_evaluate: sponsorship off means no sponsorship flag and no visa pre-screen",
      _off["sponsorship_flag"] is None and not any(p["kind"] == "visa" for p in app.pre_screen(jd_a)), str(_off["sponsorship_flag"]))
_restore = tc.feature(app, sponsorship=True)
pre = app.pre_evaluate({"title": "Senior Strategy Consultant", "prescreen": app.pre_screen(jd_a)}, jd_a)
check("pre_evaluate: explicit no sponsorship from the pre-screen", pre["sponsorship_flag"] == "explicit_no", str(pre))
check("pre_evaluate: years of experience, not the company's age", pre["years_asked"] == 8, str(pre["years_asked"]))
check("pre_evaluate: senior title is a stretch", pre["level_fit"] == "stretch")
check("pre_evaluate: unconfirmed tools become candidate questions, confirmed ones do not",
      pre["tools_named_unconfirmed"] == ["Snowflake", "Smartsheet"] and pre["tools_named_confirmed"] == ["SQL", "Looker"], str(pre))
check("pre_evaluate: analytics vocabulary points at the analytics base (its signals in base_versions.yaml)",
      pre["version_hint"] == "analytics", str(pre["version_signal"]))
jd_b = "Operations Consultant. Visa sponsorship is available for the right candidate. Own process and cross-functional programs."
pre_b = app.pre_evaluate({"title": "Operations Consultant", "prescreen": []}, jd_b)
_restore()
check("pre_evaluate: explicit yes when the JD offers sponsorship", pre_b["sponsorship_flag"] == "explicit_yes"
      and pre_b["level_fit"] == "at_level" and pre_b["version_hint"] == "operations", str(pre_b))
check("pre_evaluate: a posting with no signal falls back to the profile's default version",
      app.pre_evaluate({"title": "Analyst", "prescreen": []}, "Nothing to see.")["version_hint"] == "operations")
eval_calls = []
def fake_eval_claude(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None):
    eval_calls.append({"prompt": prompt, "tools": tools, "effort": effort})
    return {"structured": {"fit_score": 61, "recommendation": "TAILOR", "resume_version": "analytics", "sponsorship": "s",
                           "strengths": ["a"], "gaps": ["b"], "keyword_gaps": [], "cover_letter_combo": "C", "cover_letter_format": "KB",
                           "honest_take": "t", "sponsorship_flag": "silent", "level_fit": "at_level", "blockers": [], "build_questions": []},
            "session_id": "ev-1", "cost": 0.01, "timing": {"wall_ms": 5, "turns": 1, "context_tokens": 1, "output_tokens": 1, "model": model}}
real_run_claude = app.run_claude
app.run_claude = fake_eval_claude
app.update_job(jid, status="evaluating")
app.evaluate_worker(jid)
app.run_claude = real_run_claude
evj = app.load_job(jid)
check("Evaluation is told to address the user as you, by the profile's first name",
      "Alex reads this directly: write to them as you" in eval_calls[0]["prompt"])
check("Evaluation carries the learned rules heading", "RULES LEARNED FROM Alex's OWN EDITS" in eval_calls[0]["prompt"]
      and "CANDIDATE: Alex Rivera" in eval_calls[0]["prompt"], eval_calls[0]["prompt"][:200])
check("Evaluation call is tool-less at the set effort and carries the pre-computed block",
      eval_calls and eval_calls[0]["tools"] == "" and eval_calls[0]["effort"] == app.EVAL_EFFORT
      and "PRE-COMPUTED BY CODE" in eval_calls[0]["prompt"] and "OUTPUT SIZE" in eval_calls[0]["prompt"], str([(c["tools"], c["effort"]) for c in eval_calls]))
check("Evaluation keeps the pre-pass beside the model's verdict", evj["status"] == "scored" and evj["evaluation"]["pre"]["version_hint"] in app.userprofile.base_versions()
      and evj["evaluation"]["fit_score"] == 61, str(evj["evaluation"].get("pre")))
app.update_job(jid, status="scored", evaluation=ev)

# ---- the Ask box in answers mode: first person, sources inline, tool-less ------------------
ask_calls = []
def fake_ask_claude(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None, **kw):
    ask_calls.append({"prompt": prompt, "tools": tools, "resume": resume, "model": model})
    return {"result": "**Salary**\nOpen to discussion based on total compensation.", "session_id": "ask-1",
            "timing": {"wall_ms": 5, "turns": 1, "context_tokens": 1, "output_tokens": 1, "model": model}}
real_run_claude = app.run_claude
app.run_claude = fake_ask_claude
st, asked = post(f"/jobs/{jid}/ask", {"text": "What are your salary expectations?"})
check("Ask records the message on the thread", st == 200 and asked["messages"][-1]["text"].startswith("What are"), str(asked["messages"][-1]))
app.ask_worker(jid, "What are your salary expectations?")
app.run_claude = real_run_claude
check("Every ask is tool-less and carries the voice, standard answers and profile inline, addressed as you",
      ask_calls and ask_calls[-1]["tools"] == "" and all(k in ask_calls[-1]["prompt"] for k in ("first person", "addressing Alex as you", "VOICE", "STANDARD ANSWERS", "STORY BANK", "FACTS", "WHAT WAS TYPED", "Choose the story for THIS reader", "RULES LEARNED FROM Alex's OWN EDITS")),
      str([k in (ask_calls[-1]["prompt"] if ask_calls else "") for k in ("VOICE", "STANDARD ANSWERS", "FACTS")]))
check("The answer lands on the thread", app.load_job(jid)["messages"][-1]["text"].startswith("**Salary**"))
check("Answers run on the smarter model", ask_calls[-1]["model"] == app.userprofile.model("ask") == "opus")
app.update_job(jid, messages=[], ask_busy=False)

# ---- plain-JSON answers: the contract, the parser, the strict fallback ---------------------
check("schema_hint names every key and the required ones",
      "bullet_edits: list of objects with company, index, text" in app.schema_hint(app.CONTENT_SCHEMA)
      and "Required: bullet_edits, changes" in app.schema_hint(app.CONTENT_SCHEMA))
check("extract_json handles fences, nested braces in strings and escaped quotes",
      app.extract_json('Sure:\n```json\n{"a": [{"b": "x}y"}], "c": "d\\"e"}\n```') == {"a": [{"b": "x}y"}], "c": 'd"e'}
      and app.extract_json("nothing") is None)
raw_calls = []
def fake_raw(prompt, schema, resume, model, timeout, tools, permission_mode, effort, system_prompt, setting_sources):
    raw_calls.append({"schema": schema, "resume": resume, "prompt": prompt[-120:]})
    if schema is None and not prompt.startswith("evaluate again"):
        return {"result": "here: {\"fit_score\": 70}", "session_id": "s-plain", "timing": {"wall_ms": 10, "turns": 1, "output_tokens": 5}}
    if schema is None:
        return {"result": "{\"fit_score\": 61, \"recommendation\": \"TAILOR\", \"resume_version\": \"operations\", \"sponsorship\": \"s\", \"strengths\": [], \"gaps\": [], \"keyword_gaps\": [], \"honest_take\": \"t\", \"sponsorship_flag\": \"silent\", \"level_fit\": \"at_level\", \"blockers\": [], \"build_questions\": []}",
                "session_id": "s-plain2", "timing": {"wall_ms": 10, "turns": 1, "output_tokens": 5}}
    return {"structured": {"fit_score": 70, "recommendation": "SKIP"}, "session_id": "s-strict", "timing": {"wall_ms": 20, "turns": 2, "output_tokens": 9}}
real_raw = app._run_claude
app._run_claude = fake_raw
out = app.run_claude("evaluate", schema=app.EVAL_SCHEMA)
check("Incomplete plain JSON falls back to the strict path on the same session",
      out.get("structured", {}).get("recommendation") == "SKIP" and raw_calls[1]["schema"] is not None and raw_calls[1]["resume"] == "s-plain"
      and out["timing"]["fallback"] and out["timing"]["wall_ms"] == 30, str(raw_calls))
raw_calls.clear()
out = app.run_claude("evaluate again", schema=app.EVAL_SCHEMA)
app._run_claude = real_raw
check("Complete plain JSON is used as the structured answer with no second call",
      len(raw_calls) == 1 and raw_calls[0]["schema"] is None and "Empty lists are allowed" in raw_calls[0]["prompt"]
      and out.get("structured", {}).get("fit_score") == 61, str([(c["schema"] is not None) for c in raw_calls]))

# ---- the builds section is code's call --------------------------------------------------
d, hits = app.builds_decision("You will build AI agents hands-on, prototype with Claude Code and Cursor, and ship weekly.")
check("builds_decision: a JD that screens on building says so", d and len(hits) >= 4, str(hits))
d, hits = app.builds_decision("Strategy consulting for healthcare payers; prototype workflows occasionally; hands-on analysis.")
check("builds_decision: two signals are not a screen", not d, str(hits))
check("The content call carries code's decision, not a maybe",
      "BUILDS SECTION: not for this JD" in app.scope_instruction({}, "all", "plain consulting role")
      and "screens hard on hands-on building" in app.scope_instruction({}, "all", "build AI agents hands-on with Claude Code and Cursor, ship prototypes"))

# ---- approaches: code decides when the signals are clear, the block reaches the prompt --------
aps = app.load_approaches()
check("approaches.yaml loads its approaches", set(aps) == {"builder", "program_ops"}, str(list(aps)))
pm_jd = ("Maintain portfolio trackers, RAID logs, milestones and decision logs for a governed set of AI pilots; produce "
         "status updates and readouts for leadership; coordinate approvals with controls partners; escalate dependencies.")
sc = app.score_approaches(pm_jd, "Program Analyst")
check("score_approaches: a governance JD scores program_ops highest", max(sc, key=sc.get) == "program_ops" and sc["program_ops"] >= 6, str(sc))
ap = app.pick_approach({"title": "Program Analyst", "company": "X"}, pm_jd, {})
check("pick_approach: clear signals are decided by code, no model call", ap["id"] == "program_ops" and ap["by"] == "code", str(ap))
blk = app.approach_block({"evaluation": {"approach": ap}})
check("approach_block carries lead-with, watch list and what was learned",
      "Lead every role with: the coordination" in blk and "Watch: do not invent process detail" in blk and "Learned from a real build" in blk, blk[:200])
check("scope_instruction honours the approach's never/always rule",
      "not for this JD" in app.scope_instruction({}, "all", "build AI agents hands-on with Claude Code, ship prototypes, cursor", {"evaluation": {"approach": ap}})
      and "screens hard" in app.scope_instruction({}, "all", "nothing", {"evaluation": {"approach": {"id": "builder"}}}))
ordered, moved = app.apply_approach_order({"experience": [["Northbridge Logistics", "r", "d", ["Designed the forecasting service", "Led the network study", "Built a routing tool"]], ["Copperleaf Health", "r", "d", ["Coordinated"]]]}, {"evaluation": {"approach": ap}})
dropped, mv = app.apply_approach_order({"experience": [], "projects": [["", "Built a coursework churn model"], ["Route planner: ", "tool"]]}, {"evaluation": {"approach": ap}})
check("apply_approach_order: drop_projects removes the coursework project whatever the model did", len(dropped["projects"]) == 1 and "dropped 1" in mv[0], str(dropped["projects"]))
check("apply_approach_order: build-verb bullets move to the end of the role, order kept",
      ordered["experience"][0][3] == ["Led the network study", "Designed the forecasting service", "Built a routing tool"] and moved == ["Northbridge Logistics"], str(ordered["experience"][0][3]))
wc = app.approach_warnings({"experience": [["Northbridge Logistics", "r", "d", ["Designed the forecasting service", "Led"]], ["Copperleaf Health", "r", "d", ["Coordinated"]]]}, {"evaluation": {"approach": ap}})
check("approach_warnings: a role opening on a build verb is flagged under program_ops", len(wc) == 1 and "Northbridge" in wc[0], str(wc))

# ---- threshold: open questions no longer hold auto-build; answers on a built job revise ----
app.update_job(jid, status="scored", evaluation=dict(ev, fit_score=80), questions=ev["build_questions"], build=None)
post("/settings", {"auto": True, "threshold": 70})
started = []
app.build_worker = lambda job_id: started.append(job_id)
q_calls = []
def fake_eval_with_questions(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None, **kw):
    return {"structured": dict(ev, fit_score=80, build_questions=ev["build_questions"]), "session_id": "ev-2", "cost": 0,
            "timing": {"wall_ms": 5, "turns": 1, "context_tokens": 1, "output_tokens": 1, "model": model}}
app.run_claude = fake_eval_with_questions
app.update_job(jid, status="evaluating")
app.evaluate_worker(jid)
app.run_claude = real_run_claude
import time as _t; _t.sleep(0.2)
check("Over the threshold with an open question, Auto asks the question instead of building",
      started == [] and app.load_job(jid)["status"] == "questions" and len(app.load_job(jid)["questions"]) == 1,
      f"{started} {app.load_job(jid)['status']}")
def fake_eval_no_questions(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None, **kw):
    return {"structured": dict(ev, fit_score=80, build_questions=[]), "session_id": "ev-3", "cost": 0,
            "timing": {"wall_ms": 5, "turns": 1, "context_tokens": 1, "output_tokens": 1, "model": model}}
app.run_claude = fake_eval_no_questions
app.update_job(jid, status="evaluating")
app.evaluate_worker(jid)
app.run_claude = real_run_claude
check("Over the threshold with no questions, Auto builds", started == [jid] and app.load_job(jid)["status"] == "building")
# a clean capture with Auto on is evaluated without a click
evals = []
app.evaluate_worker = lambda job_id: evals.append(job_id)
st, auto_job = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9000777/", text="About the job\n" + "y" * 3000))
check("A clean capture with Auto on starts evaluating at once", st == 201 and auto_job["status"] == "evaluating" and evals == [auto_job["id"]], f"{auto_job.get('status')} {evals}")
st, blocked = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9000778/", text="About the job\nAn active secret clearance is required. " + "y" * 3000))
check("A hard pre-screen block (a blocker listed in the profile) waits for you instead", blocked["status"] == "captured" and len(evals) == 1, blocked.get("status"))
st, empty_first = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9000780/", text="About the job\nshort"))
check("An unusable capture does not evaluate", empty_first["capture_quality"] != "ok" and len(evals) == 1, empty_first["capture_quality"])
st, refilled = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9000780/", text="About the job\n" + "y" * 3000))
check("Re-capturing over an unusable one evaluates it, same job id",
      refilled["id"] == empty_first["id"] and refilled["status"] == "evaluating" and evals[-1] == refilled["id"] and len(evals) == 2,
      f"{refilled.get('status')} {evals}")
st, again2 = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9000780/", text="About the job\n" + "y" * 3000))
check("Capturing it a third time does not evaluate again", len(evals) == 2 and (again2.get("captured_again") or {}).get("count", 0) >= 1, str(evals))
post("/settings", {"auto": False})
st, quiet = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9000779/", text="About the job\n" + "q" * 3000))
check("With Auto off a capture just waits", quiet["status"] == "captured" and len(evals) == 2)
post("/settings", {"auto": True})
app.update_job(jid, status="built", evaluation=dict(ev, fit_score=80), questions=ev["build_questions"],
               build={"pdf": os.path.join(app.load_job(jid)["folder"], "x.pdf"), "verdict": "fit", "session_id": "s"})
open(os.path.join(app.load_job(jid)["folder"], "x.pdf"), "wb").write(b"%PDF")
revs = []
app.revise_worker = lambda job_id, doc, feedback: revs.append((doc, feedback))
st, ans = post(f"/jobs/{jid}/answer", {"answers": [{"id": "q1", "choice": "Yes, hands on", "remember": False}], "note": ""})
check("Answering on a built job revises instead of rebuilding, and clears the questions",
      st == 200 and ans["status"] == "built" and ans["revising"]["doc"] == "resume" and ans["questions"] == []
      and revs and "Used Smartsheet?" in revs[0][1] and "Yes, hands on" in revs[0][1], f"{st} {ans.get('status')} {ans.get('revising')} {revs}")
app.update_job(jid, revising=None, status="scored")
post("/settings", {"auto": True, "threshold": 65})

# ---- the degree is finished: every prompt says so and the slip is caught -----------------------
check("future_grad_hits catches future-tense graduation for the finished degree",
      app.future_grad_hits("I finish my MS in May") and app.future_grad_hits("As an MS candidate")
      and app.future_grad_hits("expected to graduate in May") and not app.future_grad_hits("I finished my MS in May"))
check("The standing fact (from profile.yaml) is in the standing block",
      "Alex finished an MS in Data Science at Lakeview University in May 2025" in app.standing_block()
      and "MS in Data Science (Lakeview University, May 2025) is complete" in app.standing_block(), app.standing_block()[:200])
check("The standing block is in the content and cover prompts",
      app.standing_block() in app.content_prompt(app.load_job(jid), app.engine.content_from_base("analytics"), "analytics")
      and app.standing_block() in app.cover_prompt(app.load_job(jid)))
check("Writing prompts carry the learned rules under the first name",
      "RULES LEARNED FROM Alex's OWN EDITS" in app.content_prompt(app.load_job(jid), app.engine.content_from_base("analytics"), "analytics")
      and "RULES LEARNED FROM Alex's OWN EDITS" in app.cover_prompt(app.load_job(jid)))
chk = app.cover_check({"paragraphs": ["I finish my MS in May and I would love to join. " * 12]})
check("cover_check flags future-tense graduation", any("past tense" in p for p in chk["problems"]), str(chk["problems"]))
bad_ms = app.engine.content_from_base("operations")
bad_ms["experience"][0][3][0] = "As an MS candidate I led the research."
chk2 = app.engine.check(bad_ms, app.engine.sources_for_check(app.load_job(jid)["folder"], "operations"))
check("engine.check flags future-tense graduation in the resume", any("finished, not in progress" in p for p in chk2["problems"]), str(chk2["problems"]))
ask_calls2 = []
def fake_slip(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None, **kw):
    ask_calls2.append(prompt)
    if resume == "slip-1":
        return {"result": "I finished my MS in May.", "session_id": "slip-2", "timing": {"wall_ms": 1, "turns": 1, "output_tokens": 1}}
    return {"result": "I finish my MS in May.", "session_id": "slip-1", "timing": {"wall_ms": 1, "turns": 1, "output_tokens": 1}}
real_rc = app.run_claude
app.run_claude = fake_slip
app.update_job(jid, messages=[], ask_busy=True)
app.ask_worker(jid, "Why this role?")
app.run_claude = real_rc
check("A future-tense slip in an answer is corrected on the same session, once",
      app.load_job(jid)["messages"][-1]["text"] == "I finished my MS in May." and len(ask_calls2) == 2
      and "These degrees are finished: MS in Data Science (May 2025)" in ask_calls2[1], str(ask_calls2[-1])[:120])
app.update_job(jid, messages=[], ask_busy=False)

# ---- em dash guard ----------------------------------------------------------------------
check("Em dashes stripped from every field type",
      app.strip_em_dashes({"a": "x — y", "b": ["p — q"]}) == {"a": "x, y", "b": ["p, q"]})
check("En dash preserved for date ranges", app.strip_em_dashes("May 2025 – Present") == "May 2025 – Present")

# ---- re-capture never resets an evaluated job; Evaluate again keeps the record -------------
app.update_job(jid, status="scored", evaluation=ev, evaluated_at="2026-09-14T15:02:44")
st, same = post("/jobs", dict(CAPTURE, text="z" * 3010))          # 10 chars longer: LinkedIn noise
check("Re-capture of an evaluated job keeps its status", same["status"] == "scored" and same.get("duplicate_of"), same["status"])
check("Re-capture of an evaluated job keeps the evaluation", app.load_job(jid)["evaluation"]["fit_score"] == 80)
check("Re-capture with the same text is not flagged as changed", not app.load_job(jid).get("jd_changed"))
st, grown = post("/jobs", dict(CAPTURE, text="z" * 3000 + " Now with a whole new paragraph of requirements. " * 12))
check("Re-capture with a grown posting keeps the evaluation but flags the change",
      app.load_job(jid)["evaluation"] and (app.load_job(jid).get("jd_changed") or {}).get("old_chars") == 3000, str(app.load_job(jid).get("jd_changed")))
check("The earlier JD is kept beside the new one", os.path.exists(os.path.join(app.load_job(jid)["folder"], "JD.previous.md")))
app.evaluate_worker = lambda job_id: None                       # do not run a model in the test
st, again = post(f"/jobs/{jid}/evaluate")
check("Evaluate again records the previous verdict", again["status"] == "evaluating" and
      again["previous_evaluations"][-1]["fit_score"] == 80, str(again.get("previous_evaluations")))
app.update_job(jid, status="scored")

# ---- thumbnail: the rendered page, or a plain 404 before there is one ---------------------
r = c.get(f"/jobs/{jid}/thumb")
check("Thumb 404 before a build", r.status_code == 404, f"got {r.status_code}")
jpg = os.path.join(app.load_job(jid)["folder"], "page-1.jpg")
open(jpg, "wb").write(b"\xff\xd8\xff\xe0 not really a jpeg \xff\xd9")
app.update_job(jid, build={"pdf": jpg[:-4] + ".pdf", "jpg": jpg, "mode": "base", "pages": 1})
r = c.get(f"/jobs/{jid}/thumb")
check("Thumb serves page-1.jpg as image/jpeg", r.status_code == 200 and r.mimetype == "image/jpeg"
      and r.data.startswith(b"\xff\xd8"), f"{r.status_code} {r.mimetype}")
check("Thumb is not cached", "max-age=0" in (r.headers.get("Cache-Control") or ""), r.headers.get("Cache-Control"))
r = c.get("/jobs/no-such-job/thumb")
check("Thumb on unknown job is 404", r.status_code == 404)

# ---- search: title, company and the full JD.md, every word must match -------------------
with open(os.path.join(app.load_job(jid)["folder"], "JD.md"), "a") as f:
    f.write("\nExperience with Snowflake and dbt is a plus.\n")
st, sr = get("/search?q=Snowflake")
check("Search finds a word deep in JD.md", jid in sr["ids"], str(sr))
st, sr = get("/search?q=acme")
check("Search matches the company name, case-insensitively", jid in sr["ids"], str(sr))
st, sr = get("/search?q=snowflake unicorns")
check("Search needs every word", jid not in sr["ids"], str(sr))
st, sr = get("/search?q=")
check("Empty search returns nothing", sr["ids"] == [], str(sr))

# ---- the engine: base build fits without a model; tailored build with the model stubbed ----
import time as _time
eng_job = app.load_job(jid)
t0 = _time.time()
res = app.base_build(dict(eng_job, evaluation=dict(ev, recommendation="BASE")))
base_s = _time.time() - t0
check("Engine base build renders one page", res.get("pages") == 1 and os.path.exists(res["pdf"]), str(res)[:200])
if res.get("verdict") == "under":
    tc.skip(results, "Engine base build fills the page",
            f"the example profile's base resume renders at {res.get('fill_pct')}% fill (verdict under); "
            "examples/profile/base_versions.yaml needs more content for this check to run")
else:
    check("Engine base build fills the page", res.get("verdict") == "fit" and 90 <= res.get("fill_pct", 0) <= 99.5,
          f"{res.get('verdict')} {res.get('fill_pct')}")
check("Engine base build writes page-1.jpg and NOTES.md", os.path.exists(res["jpg"]) and
      os.path.exists(os.path.join(eng_job["folder"], "NOTES.md")))
check("Engine base build under 30 s", base_s < 30, f"{base_s:.1f}s")

# A stubbed model that returns the base bullets with one orphan-shaped bullet, then fixes it.
base_an = app.engine.content_from_base("analytics")
calls = []
put_back = {"done": False}
def fake_run_claude(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None):
    calls.append({"prompt": prompt, "resume": resume, "tools": tools, "model": model})
    last_role, mid_role, first_role = base_an["experience"][-1], base_an["experience"][-2], base_an["experience"][-3]
    if not resume:
        # first answer drops six bullets, so the page is under-full even at the loosest layout
        edits = [{"company": last_role[0], "index": i, "text": ""} for i in range(len(last_role[3]))] + \
                [{"company": r[0], "index": len(r[3]) - k, "text": ""} for r in (mid_role, first_role) for k in (1, 2)]   # the last two of each
    elif put_back["done"]:
        edits = []                                                                          # later fix rounds change nothing
    else:
        put_back["done"] = True
        edits = [{"company": last_role[0], "index": 99, "text": t} for t in last_role[3]] + \
                [{"company": r[0], "index": 99, "text": t} for r in (mid_role, first_role) for t in r[3][-2:]]     # put them back
    spec = {"bullet_edits": edits, "skill_edits": [], "project_edits": [],
            "changes": ["Test swap — with a dash"] if edits else [], "claims_to_verify": ["A claim"], "tools_omitted": []}
    return {"structured": spec, "session_id": "sess-1", "cost": 0.01,
            "timing": {"wall_ms": 10, "api_ms": 9, "turns": 1, "context_tokens": 100, "output_tokens": 50, "model": model}}
real_run_claude = app.run_claude
app.run_claude = fake_run_claude
eng_job = dict(eng_job, evaluation=dict(eng_job.get("evaluation") or ev, approach={"id": "program_ops", "name": "Program and governance", "by": "code", "why": "test", "adjustments": []}))
res = app.tailored_build(eng_job)
app.run_claude = real_run_claude
check("Engine tailored build: one content call, then fix rounds on its session, no tools",
      calls and calls[0]["tools"] == "" and calls[0]["resume"] is None
      and all(c["resume"] == "sess-1" for c in calls[1:]), str([(c["tools"], c["resume"]) for c in calls]))
check("The content call carries the builds-section rule", "BUILDS SECTION" in calls[0]["prompt"])
check("Content prompt carries the JD, the skill and the profile inline",
      "JOB DESCRIPTION" in calls[0]["prompt"] and "resume-build" in calls[0]["prompt"] and "FACTS" in calls[0]["prompt"])
check("Content prompt lists the base with indices and asks for edits only",
      "Northbridge Logistics (" in calls[0]["prompt"] and "[0]" in calls[0]["prompt"] and "EDITS ONLY" in calls[0]["prompt"])
fixes = [c for c in calls if c["resume"] == "sess-1"]
check("Fix round names companies with indices and asks for edits only",
      fixes and all("Verdict: under" in c["prompt"] and "edits" in c["prompt"] for c in fixes) and any("bullet [" in c["prompt"] for c in fixes),
      fixes[0]["prompt"][-300:] if fixes else "no fix round")
_c = json.load(open(os.path.join(eng_job["folder"], "_build", "content.json")))
check("Edits applied cumulatively: deletions then appends leave the base content whole",
      all(_c["experience"][k][3] == list(base_an["experience"][k][3]) for k in range(len(base_an["experience"]))),
      str([len(r[3]) for r in _c["experience"]]))
# apply_edits on its own: replace, append, delete, unknown company ignored
_e = app.engine.apply_edits(base_an, {"bullet_edits": [
    {"company": "Copperleaf Health", "index": 1, "text": "Replaced."}, {"company": "Copperleaf Health", "index": 99, "text": "Appended."},
    {"company": "Brightline Retail", "index": 0, "text": ""}, {"company": "Nowhere Inc", "index": 0, "text": "Dropped."}],
    "project_edits": [{"index": 0, "label": "New", "text": "A project."}]})
_d = app.engine.apply_edits(base_an, {"skill_edits": [{"index": 0, "label": "Analytics", "text": "Analytics: SQL, forecasting"}]})
check("apply_edits: a label repeated inside the text is stripped once", _d["skills"][0] == ["Analytics: ", "SQL, forecasting"], str(_d["skills"][0]))
check("apply_edits: replace, append, delete, ignore unknown company, add a project",
      _e["experience"][1][3][1] == "Replaced." and _e["experience"][1][3][-1] == "Appended."
      and len(_e["experience"][-1][3]) == len(base_an["experience"][-1][3]) - 1 and _e["projects"] == [["New: ", "A project."]], str(_e["projects"]))
check("Engine tailored build renders one page", res.get("pages") == 1, str(res.get("pages")))
check("Engine tailored build reports its verdict and timing", res.get("verdict") in ("fit", "orphans", "under", "over")
      and res["timing"]["turns"] == len(calls), f"{res.get('verdict')} {res.get('timing')}")
check("Em dash stripped from the model's change list, fix-round changes appended",
      res["changes"] == ["Test swap, with a dash"] * 2, str(res["changes"]))
check("content.json and layout.json written beside the build",
      os.path.exists(os.path.join(eng_job["folder"], "_build", "content.json")) and
      os.path.exists(os.path.join(eng_job["folder"], "_build", "layout.json")))
notes = open(os.path.join(eng_job["folder"], "NOTES.md")).read()
check("NOTES.md composed by the server", "What changed from the base" in notes and "Claims to verify" in notes, notes[:120])

# engine.check: the deterministic content gate
cbase = app.engine.content_from_base("operations")
chk = app.engine.check(cbase, app.engine.sources_for_check(eng_job["folder"], "operations"))
check("check(): the base version passes clean", chk["ok"] and not chk["unverified_numbers"], str(chk))
bad = app.engine.content_from_base("operations")
bad["experience"][0][3][0] = "Grew revenue 999% — a rare combination of luck."
bad["experience"][0], bad["experience"][1] = bad["experience"][1], bad["experience"][0]
chk = app.engine.check(bad, app.engine.sources_for_check(eng_job["folder"], "operations"))
check("check(): catches the em dash, the banned phrase and the order",
      any("em dash" in p for p in chk["problems"]) and any("banned" in p for p in chk["problems"])
      and any("order" in p for p in chk["problems"]), str(chk["problems"]))
check("check(): an untraceable number is listed", any(u["number"] == "999%" for u in chk["unverified_numbers"]),
      str(chk["unverified_numbers"]))

# ---- documents: cover thumb and file routes, cover generation gate, open one document -----
r = c.get(f"/jobs/{jid}/thumb?doc=cover")
check("Cover thumb 404 before a cover letter", r.status_code == 404, str(r.status_code))
app.update_job(jid, build=res)                                   # the engine build from above, a real PDF
r = c.get(f"/jobs/{jid}/file?doc=resume")
check("File route serves the resume PDF", r.status_code == 200 and r.mimetype == "application/pdf"
      and r.data.startswith(b"%PDF"), f"{r.status_code} {r.mimetype}")
r = c.get(f"/jobs/{jid}/file?doc=cover")
check("File route 404 for a missing cover letter", r.status_code == 404)
app.update_job(jid, status="scored")
st, gate = post(f"/jobs/{jid}/cover")
check("Cover generation refused before the resume is built", st == 409, f"got {st}")
app.update_job(jid, status="built")
cover_pdf = os.path.join(app.load_job(jid)["folder"], "Alex_Rivera_Test_Cover_Letter.pdf")
open(cover_pdf, "wb").write(b"%PDF-1.4 fake")
app.update_job(jid, cover={"pdf": cover_pdf, "docx": cover_pdf[:-4] + ".docx", "pages": 1})
real_popen = app.subprocess.Popen
opened = []
app.subprocess.Popen = lambda args, **kw: opened.append(list(args))
st, o = post(f"/jobs/{jid}/open", {"what": "cover"})
app.subprocess.Popen = real_popen
check("Open one document opens only that PDF", st == 200 and opened and opened[-1][-1] == cover_pdf, str(opened))
app.update_job(jid, cover=None, status="scored")

# ---- cover letter engine: deterministic checks, requirements, stubbed model, revise -------
cr = app.cover_requirements("We are hiring. In your cover letter, please tell us why you want this role and "
                            "describe a time you led change. Salary is competitive. Cover letters are optional.")
check("cover_requirements finds the employer's asks and skips the noise",
      len(cr) == 1 and cr[0].startswith("In your cover letter, please tell us"), str(cr))
short = {"paragraphs": ["Too short — really."], "recipient_lines": [], "greeting": "Dear Hiring Team,"}
chk = app.cover_check(short)
check("cover_check: short letter, em dash flagged", not chk["ok"] and any("under" in x for x in chk["problems"])
      and "em dash" in chk["problems"], str(chk))
good_paras = [("This is a plain sentence about the work I have done and what it produced for the people involved. " * 4).strip()] * 4
chk = app.cover_check({"paragraphs": good_paras})
check("cover_check: a 250 to 350 word letter passes", chk["ok"] and 250 <= chk["words"] <= 350, str(chk))
cover_calls = []
def fake_cover_claude(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None):
    cover_calls.append({"prompt": prompt, "resume": resume, "tools": tools, "effort": effort})
    paras = [p for p in good_paras]
    if not resume:
        paras = paras[:1]                       # first answer is too short; the fix round completes it
    return {"structured": {"paragraphs": paras, "recipient_lines": ["Hiring Team", "Acme Analytics"], "greeting": "Dear Hiring Team,",
                           "filename": "x.docx", "combo_used": "A + 1", "firm_specific_claim": "Acme Analytics builds forecasts."},
            "session_id": "cov-1", "cost": 0.02,
            "timing": {"wall_ms": 10, "api_ms": 9, "turns": 1, "context_tokens": 100, "output_tokens": 50, "model": model}}
app.run_claude = fake_cover_claude
cj = dict(app.load_job(jid), cover_requirements=["In your cover letter, please tell us why."])
cres = app.cover_letter_build(cj, instructions="Mention Chicago.")
app.run_claude = real_run_claude
check("Cover engine: one tool-less call, then a low-effort fix round on the same session",
      len(cover_calls) == 2 and cover_calls[0]["tools"] == "" and cover_calls[1]["resume"] == "cov-1" and cover_calls[1]["effort"] == "low",
      str([(c["tools"], c["resume"], c["effort"]) for c in cover_calls]))
check("Cover prompt carries the skill, the KB, the JD and the employer's asks inline",
      all(k in cover_calls[0]["prompt"] for k in ("cover-letter-build", "KNOWLEDGE BASE", "JOB DESCRIPTION", "tell us why", "Mention Chicago")))
check("Cover engine renders a one-page PDF and reports words and rounds",
      "error" not in cres and cres.get("pages") == 1 and os.path.exists(cres["pdf"]) and cres["fix_rounds"] == 1
      and 250 <= cres["words"] <= 350, str({k: cres.get(k) for k in ("pages", "words", "fix_rounds", "error")}))
# revise gate
app.update_job(jid, status="built", build=res, cover=None)
st, rv = post(f"/jobs/{jid}/revise", {"doc": "cover", "feedback": "shorter"})
check("Revise refuses a document that does not exist yet", st == 409, f"got {st}")
st, rv = post(f"/jobs/{jid}/revise", {"doc": "resume", "feedback": ""})
check("Revise needs feedback text", st == 400, f"got {st}")
app.revise_worker = lambda job_id, doc, feedback: None
st, rv = post(f"/jobs/{jid}/revise", {"doc": "resume", "feedback": "Lead with the Copperleaf work"})
check("Revise marks the job revising with the document and the feedback",
      st == 200 and rv["revising"]["doc"] == "resume" and "Copperleaf" in rv["revising"]["feedback"], str(rv.get("revising")))
app.update_job(jid, revising=None, status="scored")

# ---- skip removes the drop-folder copies the server made ----------------------------------
skip_copy = os.path.join(app.DROP_DIR, "Alex_Rivera_Skipped.pdf")
open(skip_copy, "w").write("x")
app.update_job(jid, desktop_files=[skip_copy], status="built")
st, sk = post(f"/jobs/{jid}/skip")
check("Skip removes the server's drop-folder copy", sk["status"] == "skipped" and not os.path.exists(skip_copy))
app.update_job(jid, status="scored")

# ---- A8: Submitted deletes only what the server copied ---------------------------------
mine = os.path.join(app.DROP_DIR, "Alex_Rivera_Test.pdf")
open(mine, "w").write("x")
your_own = os.path.join(app.DROP_DIR, "Something_Of_Yours.pdf")
open(your_own, "w").write("x")
app.update_job(jid, desktop_files=[mine], status="built", build={"pdf": mine, "mode": "base", "pages": 1})
st, done = post(f"/jobs/{jid}/submitted")
check("A8 Submitted marks the job applied", done["status"] == "applied", done["status"])
check("A8 Submitted removed the server's copy", not os.path.exists(mine))
check("A8 Submitted left an unrelated file alone", os.path.exists(your_own))

# ---- message relay and open --------------------------------------------------------------
st, msg = post(f"/jobs/{jid}/message", {"role": "assistant", "text": "from the channel"})
check("Channel relay appends to the thread", msg["messages"][-1]["text"] == "from the channel")
st, bad = post(f"/jobs/{jid}/message", {"text": ""})
check("Empty relay message refused", st == 400, f"got {st}")

# ---- settings ------------------------------------------------------------------------------
st, se = post("/settings", {"auto": True, "threshold": 65, "build_model": "sonnet"})
check("Settings round trip", se["auto"] and se["threshold"] == 65 and se["build_model"] == "sonnet", str(se))
st, se = post("/settings", {"build_model": "nonsense"})
check("Bad build model rejected", se["build_model"] == "sonnet", str(se))

# ---- A7: boot reconciliation ---------------------------------------------------------------
app.update_job(jid, status="building")
app.reconcile_on_boot()
check("A7 interrupted build marked honestly", app.load_job(jid)["status"] == "error" and
      "restart" in (app.load_job(jid).get("error") or ""), app.load_job(jid).get("error"))

# ---- A10: the generator writes outside _build ---------------------------------------------
tpl = os.path.join(app.TEMPLATE_DIR, "build.py")
src = open(tpl).read()
check("A10 generator targets the parent folder from _build",
      'OUT_DIR = os.path.dirname(HERE) if os.path.basename(HERE) == "_build" else HERE' in src)
check("A10 server seeds machinery into _build", 'os.path.join(job["folder"], "_build")' in open(os.path.join(HERE, "app.py")).read())

# ---- Tracker and outreach ---------------------------------------------------
post("/settings", {"auto": False})   # an earlier test leaves Auto on; a capture would then call the model
st, cj = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9100001/", company="Acme Health", text="a1 " * 1200,
                            title="Strategy Lead", company_url="https://www.linkedin.com/company/Acme-Health/life/?trk=x"))
check("Company URL captured and normalised", cj.get("company_url") == "https://www.linkedin.com/company/acme-health",
      str(cj.get("company_url")))
st, cj2 = post("/jobs", dict(CAPTURE, url="https://www.linkedin.com/jobs/view/9100002/", company="Acme Health", text="a2 " * 1200,
                             title="Ops Lead"))
check("Company URL reused for the next job at the same company",
      cj2.get("company_url") == "https://www.linkedin.com/company/acme-health", str(cj2.get("company_url")))
st, bad = post(f"/jobs/{jid}/company_url", {"url": "https://example.com/acme"})
check("Company URL route rejects a non-LinkedIn link", st == 400, f"got {st}")
st, good = post(f"/jobs/{jid}/company_url", {"url": "linkedin.com/company/acme-analytics/about"})
check("Company URL route stores the normalised link",
      st == 200 and good.get("company_url") == "https://www.linkedin.com/company/acme-analytics", str(good))

r = c.post(f"/jobs/{cj2['id']}/company_url", json={"url": "https://www.linkedin.com/company/x"},
           headers={"Origin": "https://evil.example"})
check("A web page cannot call a state-changing outreach route", r.status_code == 403, f"got {r.status_code}")
r = c.post(f"/jobs/{cj2['id']}/company_url", json={"url": "https://www.linkedin.com/company/acme-health"},
           headers={"Origin": "chrome-extension://abcdefghijklmnop"})
check("The extension can", r.status_code == 200, f"got {r.status_code}")
r = c.post(f"/jobs/{cj2['id']}/company_url", json={"url": "https://www.linkedin.com/company/acme-health"},
           headers={"Origin": "http://127.0.0.1:8790", "Host": "127.0.0.1:8790"})
check("The dashboard can", r.status_code == 200, f"got {r.status_code}")
r = c.post(f"/jobs/{cj2['id']}/company_url", json={"url": "https://www.linkedin.com/company/acme-health"},
           headers={"Origin": "http://evil.example:8790", "Host": "evil.example:8790"})
check("DNS rebinding is refused (matching Origin and Host that are not local)", r.status_code == 403, f"got {r.status_code}")

st, be = post(f"/jobs/{cj2['id']}/built_external", {"folder": os.path.join(TMP, "does-not-exist")})
check("Built elsewhere refuses a folder that does not exist", st == 400, f"got {st}")
ext = os.path.join(TMP, "Globex referral build"); os.makedirs(ext)
st, be = post(f"/jobs/{cj2['id']}/built_external", {"folder": ext})
check("Built elsewhere marks the job and keeps the folder",
      st == 200 and be["status"] == "built_external" and be["external_folder"] == ext, str(be.get("status")))
st, sub = post(f"/jobs/{cj2['id']}/submitted")
check("A job built elsewhere can be marked submitted", st == 200 and sub["status"] == "applied", str(sub.get("status")))

st, ov = get("/api/overview")
row = next((j for j in ov["jobs"] if j["id"] == cj["id"]), None)
check("Overview lists every job with its company URL and an empty outreach record",
      st == 200 and row and row["company_url"].endswith("acme-health") and row["outreach"]["state"] == "none"
      and row["outreach"]["found"] == 0, str(row and row["outreach"]))
check("Overview counts statuses", ov["counts"]["all"] == len(ov["jobs"]) and ov["counts"].get("applied", 0) >= 1,
      str(ov["counts"]))
st, nt = get("/notifications")
check("Notifications start at zero", st == 200 and nt["total"] == 0, str(nt))
check("Notifications carry the inbox count (zero with nothing read)", nt.get("inbox") == 0, str(nt))
check("Overview rows carry an inbox summary, empty when no email came in",
      row["inbox"] == {"count": 0, "last_kind": None, "last_at": None, "needs": 0}, str(row.get("inbox")))
st, jl = get("/jobs")
check("GET /jobs carries the same inbox summary", st == 200 and all("inbox" in j and j["inbox"]["count"] == 0 for j in jl), str(jl[:1]))

with app.db() as con:
    # People with messages have been approved; that is the only way a message exists.
    con.execute("INSERT INTO people (id, job_id, name, title, rank, why, found_at, status) VALUES "
                "('p1', ?, 'Dana Reyes', 'Talent Acquisition Partner', 1, 'Owns strategy hiring', ?, 'approved')", (cj["id"], app.now()))
    con.execute("INSERT INTO people (id, job_id, name, title, rank, found_at, status) VALUES "
                "('p2', ?, 'Sam Ortiz', 'Director, Strategy', 2, ?, 'approved')", (cj["id"], app.now()))
    for mid, pid, ch, stt in (("m1", "p1", "email", "review"), ("m2", "p1", "linkedin", "review"),
                              ("m3", "p2", "email", "sent"), ("m4", "p2", "linkedin", "sent")):
        con.execute("INSERT INTO messages (id, person_id, job_id, channel, draft, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?)", (mid, pid, cj["id"], ch, "draft text", stt, app.now()))
st, ov = get("/api/overview")
o = next(j for j in ov["jobs"] if j["id"] == cj["id"])["outreach"]
check("Overview tallies people and messages per job",
      o["found"] == 2 and o["emailed"] == 1 and o["dm_sent"] == 1 and o["to_approve"] == 1 and o["to_send_dm"] == 1, str(o))
st, nt = get("/notifications")
check("Notifications count what is waiting", nt["approve"] == 1 and nt["linkedin"] == 1 and nt["total"] == 2, str(nt))
with app.db() as con:
    con.execute("INSERT INTO inbox (id, received_at, from_address, from_name, subject, why, kind, job_id, status) VALUES "
                "('ib1', '2026-10-08T09:00:00', 'hr@acme.example', 'Acme HR', 'Interview invitation', 'company', 'interview', ?, 'suggest')", (cj["id"],))
st, nt = get("/notifications")
check("An email waiting on you counts in the bell and the total", nt["inbox"] == 1 and nt["total"] == 3, str(nt))
st, ov = get("/api/overview")
ib_ = next(j for j in ov["jobs"] if j["id"] == cj["id"])["inbox"]
check("The overview's inbox summary names the newest email and what needs you",
      ib_ == {"count": 1, "last_kind": "interview", "last_at": "2026-10-08T09:00:00", "needs": 1}, str(ib_))
with app.db() as con:
    con.execute("DELETE FROM inbox WHERE id='ib1'")
st, pp = get(f"/api/jobs/{cj['id']}/people")
check("People drill-down returns each person with their messages, in rank order",
      st == 200 and [x["name"] for x in pp["people"]] == ["Dana Reyes", "Sam Ortiz"]
      and len(pp["people"][0]["messages"]) == 2 and pp["people"][0]["why"] == "Owns strategy hiring", str(pp)[:200])

# ---- owner only: every route, reads included ---------------------------------
# Real ids in the paths, so a route that slipped the guard would do its work and not 404. The
# model and the subprocesses are stubbed for the sweep: a leak shows up as a recorded call, not a real run.
spawned = []
real_threading, real_subprocess = app.threading, app.subprocess


class _Stub:
    def __getattr__(self, name):
        return lambda *a, **kw: spawned.append(name) or _Stub()


app.threading, app.subprocess = _Stub(), _Stub()
refused, leaked = 0, []
for rule in app.app.url_map.iter_rules():
    if rule.endpoint == "static":
        continue
    path = rule.rule.replace("<job_id>", cj["id"]).replace("<mid>", "m1")
    for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
        for hdrs in ({"Origin": "https://evil.example"},
                     {"Origin": "http://evil.example:8790", "Host": "evil.example:8790"},
                     {"Host": "evil.example:8790"}):
            r = c.open(path, method=method, json={} if method == "POST" else None, headers=hdrs)
            if r.status_code == 403 and "Access-Control-Allow-Origin" not in r.headers:
                refused += 1
            else:
                leaked.append(f"{method} {path} {hdrs} -> {r.status_code}")
app.threading, app.subprocess = real_threading, real_subprocess
check("A web page and a rebinding page are refused on every route, reads included, with no CORS header",
      not leaked and refused > 90, "; ".join(leaked[:4]) or f"only {refused} checked")
check("Nothing ran while they were refused (no thread, no subprocess)", not spawned, str(spawned))

st, s0 = get("/settings")
r = c.post("/settings", json={"auto": True}, headers={"Origin": "https://evil.example"})
check("A web page cannot turn Auto on (it would start Claude runs on every capture)",
      r.status_code == 403 and get("/settings")[1]["auto"] == s0["auto"], f"got {r.status_code}")

r = c.get("/jobs", headers={"Origin": "chrome-extension://abcdefghijklmnop"})
check("The extension reads jobs, and gets its own origin back rather than *",
      r.status_code == 200 and r.headers.get("Access-Control-Allow-Origin") == "chrome-extension://abcdefghijklmnop",
      f"{r.status_code} {r.headers.get('Access-Control-Allow-Origin')}")
r = c.options("/jobs", headers={"Origin": "chrome-extension://abcdefghijklmnop",
                                "Access-Control-Request-Method": "POST"})
check("The extension's preflight passes", r.status_code == 204 and
      r.headers.get("Access-Control-Allow-Origin") == "chrome-extension://abcdefghijklmnop", f"got {r.status_code}")
r = c.get(f"/jobs/{cj['id']}/thumb", headers={"Host": "127.0.0.1:8790"})
check("The side panel's <img> (no Origin) still reaches the thumb route", r.status_code in (200, 404)
      and r.get_json(silent=True) != {"error": "not from the dashboard or the extension"}, f"got {r.status_code}")
for host, mid in (("127.0.0.1:8790", "m1"), ("localhost:8790", "m2")):
    r = c.get("/api/overview", headers={"Host": host})
    check(f"The dashboard loads its data at http://{host} (same origin, no Origin on a GET)",
          r.status_code == 200 and "Access-Control-Allow-Origin" not in r.headers, f"got {r.status_code}")
    r = c.post(f"/api/messages/{mid}/skip", json={}, headers={"Host": host, "Origin": f"http://{host}"})
    check(f"The dashboard can act at http://{host}", r.status_code == 200, f"got {r.status_code}")
r = c.post(f"/jobs/{cj['id']}/message", json={"role": "assistant", "text": "relay"},
           headers={"Host": "127.0.0.1:8790"})
check("The channel relay (Node fetch, no Origin) still posts messages", r.status_code == 200, f"got {r.status_code}")

# ---- LinkedIn repaints the pane after the URL changes ------------------
post("/settings", {"auto": False})
WK = dict(CAPTURE, url="https://www.linkedin.com/jobs/search-results/?currentJobId=4457528207", company="Initech",
          title="Solutions Architect", text="Initech builds billing software for regional banks. " * 120)
st, wk = post("/jobs", WK)
check("The first capture of a job is filed as new", st == 201 and wk["job_key"] == "linkedin:4457528207", wk.get("job_key"))
# You click Globex: the URL already says Globex, the pane still shows Initech, and no shown id is readable.
st, r = post("/jobs", dict(WK, url="https://www.linkedin.com/jobs/search-results/?currentJobId=4429389320"))
check("A capture whose text is a recent job's text under another id is refused, not filed", st == 409
      and r.get("stale_of") == wk["id"] and "Initech" in r.get("error", ""), f"{st} {r}")
check("Nothing was filed under the Globex id", app.find_by_key("linkedin:4429389320") is None)
# Same moment, but the pane's own title link says Initech: it is the Initech job, seen again.
st, r = post("/jobs", dict(WK, url="https://www.linkedin.com/jobs/search-results/?currentJobId=4429389320", shown_job_id="4457528207"))
check("With the pane's job id, the capture is filed under the job it actually shows",
      r.get("id") == wk["id"] and (r.get("duplicate_of") or {}).get("id") == wk["id"], str(r.get("duplicate_of")))
st, loc2 = post("/jobs", dict(WK, url="https://www.linkedin.com/jobs/view/4457528299/", shown_job_id="4457528299"))
check("The same description posted as a second job (another location) is filed when the pane confirms it",
      st == 201 and loc2["job_key"] == "linkedin:4457528299", f"{st} {loc2.get('job_key')}")
# A moment later the pane shows Globex: a different description, so a new job under the Globex id.
NK = dict(WK, url="https://www.linkedin.com/jobs/search-results/?currentJobId=4429389320", company="Globex",
          title="Chief of Staff to the CEO", text="Globex makes logistics software for mid-size shippers. " * 120,
          shown_job_id="4429389320")
st, nk = post("/jobs", NK)
check("Once the pane repaints, the real job is filed under its own id", st == 201 and nk["job_key"] == "linkedin:4429389320"
      and nk["company"] == "Globex", f"{st} {nk.get('job_key')}")
st, r = post("/jobs", dict(NK, url="https://www.linkedin.com/jobs/search-results/?currentJobId=999", shown_job_id="4429389320"))
check("When the URL and the pane disagree, the stored link is the pane's job", r.get("id") == nk["id"], str(r.get("id")))

# ---- UI audit step 7: company links filled for a hand-added job, and fixable by hand -----------------------------
import time as _t
PAGES = {"https://www.linkedin.com/company/zenco-labs": {"name": "Zenco Labs", "website": "https://zenco.example"},
         "https://www.linkedin.com/company/other-slug": {"name": "Totally Different Co", "website": "https://other.example"},
         "https://www.linkedin.com/company/acme-corp": {"name": "Acme Corp"}}
page_reads = []
app.company_page_info = lambda url: (page_reads.append(url) or PAGES.get(url, {}))
app.backfill_company_url = _real_backfill

st, zj = post("/jobs/manual", {"company": "Zenco Labs", "title": "Chief of Staff"})
_t.sleep(0.3)      # the manual route starts the backfill on a thread
zj2 = app.load_job(zj["id"])
check("A hand-added job starts the link backfill: LinkedIn page found by name when the page names the same company",
      st == 201 and zj2.get("company_url") == "https://www.linkedin.com/company/zenco-labs", str(zj2.get("company_url")))
check("...and the website comes from that same page read", zj2.get("company_website") == "https://zenco.example", str(zj2.get("company_website")))
check("...one read, not two", page_reads.count("https://www.linkedin.com/company/zenco-labs") == 1, str(page_reads))
acts = [a for a in app.db().execute("SELECT action, detail FROM actions WHERE job_id=?", (zj["id"],))]
check("...and logged with where it came from", any(a[0] == "company_url" and "guessed" in a[1] for a in acts), str(acts))

page_reads.clear()
st, wj = post("/jobs/manual", {"company": "Wrong Slug Inc", "title": "Analyst"})
app.update_job(wj["id"], company_url=None)
page_reads.clear()
PAGES["https://www.linkedin.com/company/wrong-slug"] = {"name": "Totally Different Co"}
app.backfill_company_url(wj["id"])
check("A page that names another company is never kept", not app.load_job(wj["id"]).get("company_url"), str(app.load_job(wj["id"]).get("company_url")))
check("...and at most two reads are spent finding out", len(page_reads) <= 2, str(page_reads))

st, aj = post("/jobs/manual", {"company": "Acme Corp Inc", "title": "Analyst"})
app.update_job(aj["id"], company_url=None)
page_reads.clear()
app.backfill_company_url(aj["id"])
check("The name without its corporate suffix is the second guess", app.load_job(aj["id"]).get("company_url") == "https://www.linkedin.com/company/acme-corp"
      and len(page_reads) == 2, f"{app.load_job(aj['id']).get('company_url')} {page_reads}")

app.company_page_info = lambda url: {}
st, nj = post("/jobs/manual", {"company": "Nowhere Ltd", "title": "Analyst"})
app.backfill_company_url(nj["id"])
check("An unreadable page leaves both links empty, not a guess", not app.load_job(nj["id"]).get("company_url")
      and not app.load_job(nj["id"]).get("company_website"))

st, r = post("/jobs/manual", {"company": "Linked Co", "title": "PM", "company_url": "linkedin.com/company/Linked-Co/about"})
check("The add form's company LinkedIn page is kept, normalised", st == 201 and r["company_url"] == "https://www.linkedin.com/company/linked-co", str(r.get("company_url")))
st, r = post("/jobs/manual", {"company": "Linked Co 2", "title": "PM", "company_url": "https://example.com/x"})
check("...and refused when it is not a LinkedIn company link", st == 400 and "LinkedIn" in r["error"], f"{st} {r}")

app.backfill_company_url = lambda job_id: None
# the website by hand
st, r = post(f"/jobs/{zj['id']}/company_website", {"url": "initech.example"})
check("Website by hand: a bare domain gets https", st == 200 and r["company_website"] == "https://initech.example", f"{st} {r}")
st, r = post(f"/jobs/{zj['id']}/company_website", {"url": "http://www.zenco.example/about"})
check("Website by hand: http is allowed and replaces the old one", st == 200 and r["company_website"] == "http://www.zenco.example/about")
for bad in ("https://www.linkedin.com/company/zenco", "javascript:alert(1)", "ftp://zenco.example", "not a url", "", "https://localhost"):
    st, r = post(f"/jobs/{zj['id']}/company_website", {"url": bad})
    check(f"Website by hand: refused {bad!r}", st == 400, f"{st} {r}")
st, r = post("/jobs/nope/company_website", {"url": "https://x.example"})
check("Website by hand: unknown job is 404", st == 404)
row = [j for j in get("/api/overview")[1]["jobs"] if j["id"] == zj["id"]][0]
check("Website by hand: the overview carries it", row["company_website"] == "http://www.zenco.example/about", row["company_website"])
check("Website by hand: logged", any(a[0] == "company_website" for a in app.db().execute("SELECT action FROM actions WHERE job_id=?", (zj["id"],))))
st, r = post(f"/jobs/{zj['id']}/company_url", {"url": "linkedin.com/company/zenco-labs-2"})
check("LinkedIn page by hand: a wrong link is replaced", st == 200 and r["company_url"].endswith("zenco-labs-2"))

# ---- the profile: /api/profile/status with and without one ------------------------------------------------
st, ps = get("/api/profile/status")
check("Profile status: onboarded, with the profile's name and first name", st == 200 and ps["onboarded"]
      and ps["name"] == "Alex Rivera" and ps["first_name"] == "Alex", str({k: ps.get(k) for k in ("onboarded", "name")}))
check("Profile status: every optional feature is off in the example",
      ps["features"] == {"sponsorship": False, "outreach": False, "email": False, "alerts": False}, str(ps["features"]))
check("Profile status: base versions by key with their labels",
      ps["base_versions"] == {"operations": "Strategy and operations", "analytics": "Analytics"}, str(ps["base_versions"]))
check("Profile status: setup lists only the names of missing .env keys",
      ps["setup"]["outreach"]["missing"] == ["APIFY_TOKEN"] and {"MAIL_ADDRESS", "MAIL_PASSWORD", "SMTP_HOST", "IMAP_HOST"} <= set(ps["setup"]["email"]["missing"])
      and ps["setup"]["alerts"]["missing"] == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"], str(ps["setup"]))
check("Profile status: sending settings and signature from the profile",
      ps["sending"] == {"timezone": "America/Chicago", "window": [9, 17], "daily_cap": 10} and ps["signature"] == "Best,\nAlex Rivera"
      and ps["docs"]["email"] == "docs/email.md", str(ps["sending"]))
with open(app.ENV_FILE, "w") as f:
    f.write("APIFY_TOKEN=fake-for-test\nMAIL_ADDRESS=alex.rivera@example.com\nMAIL_PASSWORD=x\nSMTP_HOST=smtp.example.com\n")
st, ps = get("/api/profile/status")
check("Profile status: keys present in .env drop off the missing lists, values never returned",
      ps["setup"]["outreach"]["missing"] == [] and ps["setup"]["email"]["missing"] == ["IMAP_HOST"]
      and "fake-for-test" not in json.dumps(ps), str(ps["setup"]))
os.remove(app.ENV_FILE)
NO_PROFILE = os.path.join(TMP, "no-profile")
os.makedirs(NO_PROFILE)
os.environ["JDI_PROFILE_DIR"] = NO_PROFILE
st, ps = get("/api/profile/status")
os.environ["JDI_PROFILE_DIR"] = tc.EXAMPLE_PROFILE
check("Profile status without a profile: not onboarded, no name, features off, no base versions, still 200",
      st == 200 and ps["onboarded"] is False and ps["name"] == "" and ps["base_versions"] == {}
      and not any(ps["features"].values()) and ps["profile_dir"] == NO_PROFILE, str(ps)[:200])
st, h = get("/health")
check("Health reports the profile and its features", h["profile"]["onboarded"] and h["profile"]["features"]["email"] is False, str(h.get("profile")))

# ---- optional features: off means refused, with a pointer to the doc ----------------------------------------
st, r = post(f"/api/jobs/{cj['id']}/outreach")
check("Outreach off: drafting outreach is refused with a pointer to docs/outreach.md",
      st == 400 and "docs/outreach.md" in r["error"] and r["needs"] == "feature:outreach", f"{st} {r}")
st, r = post(f"/api/jobs/{cj['id']}/people/approve_all")
check("Outreach off: approving people is refused too", st == 400 and r["needs"] == "feature:outreach", f"{st} {r}")
st, r = post("/api/bounces/check")
check("Email off: the bounce check is refused with a pointer to docs/email.md",
      st == 400 and "docs/email.md" in r["error"] and r["needs"] == "feature:email", f"{st} {r}")
st, r = post("/api/inbox/check")
check("Email off: the inbox read is refused", st == 400 and r["needs"] == "feature:email", f"{st} {r}")
check("Email off: the sender and the readers do nothing", app.send_due() is None and app.check_bounces() == 0
      and app.check_inbox() == {"fetched": 0})
_restore = tc.feature(app, email=True)
st, r = post("/api/bounces/check")
check("Email on but not set up: the bounce check answers without touching a mailbox", st == 200 and r["newly_bounced"] == 0, f"{st} {r}")
_restore()

# ---- the learning inbox: revision feedback and overrides are written for the `learn` skill -------------------
def learn_rows():
    try:
        return [json.loads(x) for x in open(app.LEARNING_INBOX)]
    except OSError:
        return []


rows = learn_rows()
check("Learning inbox lives in the data dir", app.LEARNING_INBOX.startswith(TMP), app.LEARNING_INBOX)
check("Learning inbox: resume revision feedback is recorded with the job",
      any(r["kind"] == "resume_feedback" and r["after"] == "Lead with the Copperleaf work" and r["job_id"] == jid for r in rows),
      str([r["kind"] for r in rows]))
check("Learning inbox: a skip of a job scored above the threshold is an eval override",
      any(r["kind"] == "eval_override" and r["after"] == "skip" and r["before"]["fit_score"] == 80 for r in rows), str([r["kind"] for r in rows]))
check("Learning inbox: every row has the contract's fields",
      rows and all(set(r) == {"at", "kind", "job_id", "before", "after", "context"} and r["kind"] in app.LEARN_KINDS for r in rows))
app.revise_worker = lambda job_id, doc, feedback: None
_cpdf = os.path.join(app.load_job(jid)["folder"], "cover-for-revise.pdf")
open(_cpdf, "wb").write(b"%PDF")
app.update_job(jid, status="built", build={"pdf": _cpdf}, cover={"pdf": _cpdf, "pages": 1}, revising=None, cover_busy=False)
st, rv = post(f"/jobs/{jid}/revise", {"doc": "cover", "feedback": "Open with the warehouse study, not the degree"})
check("Learning inbox: cover revision feedback is recorded", st == 200 and any(
    r["kind"] == "cover_feedback" and r["after"].startswith("Open with the warehouse") for r in learn_rows()), f"{st}")
app.update_job(jid, revising=None, cover=None, status="scored")
app.learn_event("not_a_kind", jid, after="x")
check("Learning inbox: an unknown kind is never written", not any(r["kind"] == "not_a_kind" for r in learn_rows()))

# ---- from_owner: the extension id pins which extension may call ---------------------------------------------
app.EXTENSION_ID = "abcdefghijklmnop"
r = c.get("/jobs", headers={"Origin": "chrome-extension://abcdefghijklmnop"})
check("With JDI_EXTENSION_ID set, that extension is allowed and gets its origin back",
      r.status_code == 200 and r.headers.get("Access-Control-Allow-Origin") == "chrome-extension://abcdefghijklmnop", str(r.status_code))
r = c.get("/jobs", headers={"Origin": "chrome-extension://someotherextension"})
check("With JDI_EXTENSION_ID set, any other extension is refused with no CORS header",
      r.status_code == 403 and "Access-Control-Allow-Origin" not in r.headers, str(r.status_code))
r = c.get("/jobs")
check("With JDI_EXTENSION_ID set, a local tool with no Origin still works", r.status_code == 200)
app.EXTENSION_ID = ""
r = c.get("/jobs", headers={"Origin": "chrome-extension://someotherextension"})
check("Without JDI_EXTENSION_ID, any extension is accepted", r.status_code == 200, str(r.status_code))
r = c.get("/jobs", headers={"Origin": "chrome-extension://x", "Host": "evil.example:8790"})
check("Without JDI_EXTENSION_ID, a non-local Host is still refused", r.status_code == 403, str(r.status_code))
check("No Claude call reached the guard during the suite", not tc.CLAUDE_CALLS, str(tc.CLAUDE_CALLS[:3]))

# ---- UI audit step 13: a build that repeats itself is repaired or blocked, never "built" ---------------------
EDITS13 = [
    {"index": 0, "label": "Warehouse demand forecast", "text": "Built a weekly demand forecast in Python for 40 warehouses that cut stockouts by 18% in its first quarter."},
    {"index": 1, "label": "Route planner, a Python tool", "text": "Wrote a small Python tool that plans daily delivery routes for one region, cutting planning time from three hours to twenty minutes."},
]
JD13 = ("Operations Product Builder. You ship hands-on prototypes and build tools in Python. Zero-to-one products, "
        "write code, deploy models for the operations team. Required: Python. " * 6)
st, j13 = post("/jobs", {"url": "https://www.linkedin.com/jobs/view/9130013/", "title": "Operations Product Builder", "company": "Initech Test",
                         "location": "Chicago, IL", "text": JD13, "source": "linkedin"})
ev13 = dict(ev, recommendation="TAILOR", resume_version="operations", fit_score=70, build_questions=[],
            approach={"id": "builder", "name": "Builder", "by": "code", "why": "test", "adjustments": []})
app.update_job(j13["id"], status="scored", evaluation=ev13, questions=[], cover_letter=False)
calls13 = []
mode13 = {"repair": "delete", "first": "dup"}      # what the stub does when asked


def fake13(prompt, schema=None, resume=None, model="sonnet", timeout=600, tools=None, permission_mode="dontAsk", effort=None):
    calls13.append({"prompt": prompt, "resume": resume, "tools": tools})
    empty = {"bullet_edits": [], "skill_edits": [], "project_edits": [], "build_edits": [], "changes": [], "claims_to_verify": [], "tools_omitted": []}
    if "found repeated material" in prompt:
        spec = dict(empty, changes=["Removed the repeated item"])
        if mode13["repair"] == "delete":
            spec["build_edits"] = [{"index": 2, "label": "", "text": ""}]
        elif mode13["repair"] == "wrong":      # deletes something else, so the repeat stays
            spec["build_edits"] = [{"index": 0, "label": "", "text": ""}]
    elif "Verdict:" in prompt:
        spec = dict(empty)                     # a fix round: no changes
    elif "FEEDBACK from Alex" in prompt:
        spec = dict(empty, build_edits=[{"index": 99, "label": "Route planner again", "text": EDITS13[1]["text"]}],
                    changes=["Added the stack"]) if mode13["first"] == "dup-on-revise" else dict(empty)
    else:
        spec = dict(empty, build_edits=EDITS13, builds_title="SYSTEMS BUILT", changes=["Rewrote the builds section"],
                    claims_to_verify=["A claim"])
    return {"structured": spec, "session_id": "sess-13", "cost": 0.0,
            "timing": {"wall_ms": 5, "api_ms": 4, "turns": 1, "context_tokens": 10, "output_tokens": 5, "model": model}}


def desktop_pdfs():
    return sorted(os.listdir(app.DROP_DIR))


real_run_claude = app.run_claude
app.run_claude = fake13

# 1. the repair round clears the repeat; the build is built, one page, no duplicate in the file
before = desktop_pdfs()
app._run_build(j13["id"])
b13 = app.load_job(j13["id"])
first = calls13[0]
check("Step 13 prompt: the edit rule is stated (index replaces, past the end appends, empty deletes, unmentioned stays)",
      "EDIT RULES" in first["prompt"] and "an empty text deletes that item" in first["prompt"]
      and "every item you do not mention stays" in first["prompt"] and "never in project_edits" in first["prompt"], first["prompt"][-300:])
check("Step 13 prompt: a builds section already in the base is edited in place by index, not rewritten",
      "Edit that section in place" in first["prompt"] and "indexed [0] to [2]" in first["prompt"], "")
check("Step 13 prompt: the two to three items wording is for a base with no builds section",
      "two to three items" in app.scope_instruction(dict(app.engine.content_from_base("operations"), builds=None), "all", JD13, dict(b13, evaluation=ev13)) and
      "two to three items" not in app.scope_instruction(app.engine.content_from_base("operations"), "all", JD13, dict(b13, evaluation=ev13)))
repairs = [c for c in calls13 if "found repeated material" in c["prompt"]]
check("Step 13: a rewrite that repeats an item the base keeps (two build_edits on a three-item base) triggers exactly one repair round",
      len(repairs) == 1 and "builds item [1]" in repairs[0]["prompt"] and "builds item [2]" in repairs[0]["prompt"], len(repairs))
check("Step 13: the repair round names the pair and asks for an empty-text edit, tool-less, on the content session",
      "empty text" in repairs[0]["prompt"] and repairs[0]["tools"] == "" and repairs[0]["resume"] == "sess-13")
check("Step 13: after repair the job is built, not blocked", b13["status"] == "built" and not (b13.get("build") or {}).get("blocked"),
      f"{b13['status']} {b13.get('error')}")
c13 = json.load(open(os.path.join(b13["folder"], "_build", "content.json")))
check("Step 13: the built content has two builds items and no duplicate", len(c13["builds"]["items"]) == 2
      and not app.engine.find_duplicates(c13)["hard"], str(len(c13["builds"]["items"])))
check("Step 13: the finished .docx passes the audit", not app.engine.audit_docx(b13["build"]["docx"])["hard"])
check("Step 13: what was repeated is recorded on the build and in NOTES.md",
      len(b13["build"].get("dup_repair") or []) == 1 and "Repeated content found" in open(os.path.join(b13["folder"], "NOTES.md")).read())
check("Step 13: a repaired build is copied to the drop folder, one page", b13["build"]["pages"] == 1 and len(desktop_pdfs()) == len(before) + 1,
      str(desktop_pdfs()))

# 2. the repair does not clear it: blocked, job error, message kept, nothing on the drop folder
mode13["repair"] = "wrong"
calls13.clear()
before = desktop_pdfs()
app.update_job(j13["id"], status="scored", error=None, build=None)
app._run_build(j13["id"])
b13 = app.load_job(j13["id"])
check("Step 13: an unrepaired duplicate stops the build: status error, never built", b13["status"] == "error", b13["status"])
check("Step 13: the message is kept on the job and names the repeated items",
      (b13.get("error") or "").startswith("Build stopped") and "builds item" in b13["error"] and "Route plan" in b13["error"],
      str(b13.get("error")))
check("Step 13: nothing was copied to the drop folder", desktop_pdfs() == before, str(desktop_pdfs()))
check("Step 13: the build record is marked blocked", bool((b13.get("build") or {}).get("blocked")))
check("Step 13: the repair was tried once, not looped", len([c for c in calls13 if "found repeated material" in c["prompt"]]) == 1)
check("Step 13: the block is logged", any(a[0] == "build_blocked" for a in app.db().execute("SELECT action FROM actions WHERE job_id=?", (j13["id"],))))
check("Step 13: the blocked resume is never offered for an email", app.resume_pdf_for(b13) is None and "blocked" in app.resume_problem(b13))
st, ov = get("/api/overview")
check("Step 13: the overview carries the error for the card", [x for x in ov["jobs"] if x["id"] == j13["id"]][0]["status"] == "error")

# 3. a clean model answer needs no repair call at all
mode13["first"] = "clean"
calls13.clear()
def fake_clean(prompt, **kw):
    out = fake13(prompt, **kw)
    out["structured"] = {"bullet_edits": [], "skill_edits": [], "project_edits": [], "build_edits": [], "changes": [],
                         "claims_to_verify": [], "tools_omitted": []}
    return out
app.run_claude = fake_clean
app.update_job(j13["id"], status="scored", error=None, build=None)
app._run_build(j13["id"])
b13 = app.load_job(j13["id"])
check("Step 13: no duplicate means no repair call, and the job is built", b13["status"] == "built"
      and not [c for c in calls13 if "found repeated material" in c["prompt"]], f"{b13['status']} {len(calls13)}")
app.run_claude = fake13

# 4. a revision that adds a repeat is repaired; one that cannot be repaired leaves the earlier resume in place
good_pdf = open(b13["build"]["pdf"], "rb").read()
good_docx = open(b13["build"]["docx"], "rb").read()
mode13.update(first="dup-on-revise", repair="delete")
calls13.clear()
app.update_job(j13["id"], build=dict(b13["build"], sessions={"all": "sess-13"}, session_id="sess-13", verdict="fit"))
_real_revise_worker(j13["id"], "resume", "Add the stack")
r13 = app.load_job(j13["id"])
rc = json.load(open(os.path.join(r13["folder"], "_build", "content.json")))
check("Step 13 revise: the repeat the revision added is repaired before the page is fitted",
      len([c for c in calls13 if "found repeated material" in c["prompt"]]) == 1 and not app.engine.find_duplicates(rc)["hard"]
      and not r13.get("revise_error"), f"{r13.get('revise_error')} {len(calls13)}")
good_pdf = open(r13["build"]["pdf"], "rb").read()
good_docx = open(r13["build"]["docx"], "rb").read()
good_content = open(os.path.join(r13["folder"], "_build", "content.json")).read()
mode13["repair"] = "wrong"
calls13.clear()
before = desktop_pdfs()
_real_revise_worker(j13["id"], "resume", "Add the stack again")
r13 = app.load_job(j13["id"])
check("Step 13 revise: a repeat that survives the repair is blocked with the message on the job", (r13.get("revise_error") or "").startswith("Build stopped"),
      str(r13.get("revise_error")))
check("Step 13 revise: the earlier resume files are put back, the job keeps its status",
      open(r13["build"]["pdf"], "rb").read() == good_pdf and open(r13["build"]["docx"], "rb").read() == good_docx
      and open(os.path.join(r13["folder"], "_build", "content.json")).read() == good_content and r13["status"] == "built",
      r13["status"])
check("Step 13 revise: nothing new on the drop folder", desktop_pdfs() == before)
check("Step 13 revise: the block is logged", any(a[0] == "revise_blocked" for a in app.db().execute("SELECT action FROM actions WHERE job_id=?", (j13["id"],))))
app.run_claude = real_run_claude

shutil.rmtree(TMP, ignore_errors=True)
tc.report(results)
