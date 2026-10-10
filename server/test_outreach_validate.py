#!/usr/bin/env python3
"""Offline tests for outreach_validate.py. No model calls, no network, no clock.

Run:  python3 test_outreach_validate.py
"""
import json
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tests_common as tc  # noqa: E402
tc.block_network()
from outreach_validate import degree_words, next_send_slot, validate_and_clean  # noqa: E402

# The invented example person (examples/profile): Alex Rivera, MS in Data Science from Lakeview University.
SIGNERS = ("Alex Rivera", "Alex")
DEGREE_WORDS = degree_words([{"name": "MS in Data Science", "completed": True}])
OPTS = {"words": (110, 140), "banned": ("circle back",), "signer_names": SIGNERS, "degree_words": DEGREE_WORDS}


def vc(raw, first, mode, url, **kw):
    return validate_and_clean(raw, first, mode, url, **dict(OPTS, **kw))

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


URL = "https://example.com/jobs/123"
ET = ZoneInfo("America/New_York")

APPLIED_BODY = (
    "Hi Dana,\n\n"
    "I hope things are going well on your side, and thank you for giving a minute to a note from someone you have not met yet. I applied for the Strategy Consultant role on your team this week. I spent the last few years "
    "running freight analytics for retail clients, and most recently built the routing model behind "
    "a new regional network. The part I enjoyed most was sitting with the account teams and turning a messy spreadsheet into a model they trusted enough to use in front of a client. Your group does network planning work for the same kind of clients.\n\n"
    "Here is the posting so you have it handy: " + URL + ". If it is not a bother, could you flag my "
    "resume to the hiring team? I would be glad to send anything else that helps.")
EXPLORING_BODY = (
    "Hi Sam,\n\n"
    "I hope things are going well on your side, and thank you for giving a minute to a note from someone you have not met yet. I recently finished an MS at Lakeview and I have been reading about how your team "
    "builds demand models for regional launches, which is close to the work I did before "
    "graduate school and the part I enjoyed most. The part I enjoyed most was sitting with the account teams and turning a messy spreadsheet into a model they trusted enough to use in front of a client.\n\n"
    "Would you have twenty minutes for a call in the next couple of weeks? I would love to hear how "
    "your group thinks about hiring and where someone with my background could be useful.")
DM = "Hi Dana, I applied for the Strategy Consultant role and sent a note to your inbox. Thanks for reading."


def reply(subject="Strategy role", body=APPLIED_BODY, dm=DM, fence=False):
    raw = json.dumps({"email_subject": subject, "email_body": body, "linkedin_dm": dm})
    return "```json\n" + raw + "\n```" if fence else raw


def run(body=APPLIED_BODY, mode="Applied", first="Dana", subject="Strategy role", dm=DM):
    return vc(reply(subject, body, dm), first, mode, URL)


def has(r, frag):
    return any(frag in p for p in r["problems"])


# ---- validator: happy path and parsing ------------------------------------------------
r = run()
check("clean Applied draft passes", r["ok"] and r["problems"] == [], str(r["problems"]))
r = vc(reply(fence=True), "Dana", "Applied", URL)
check("fenced JSON parses", r["ok"] and r["subject"] == "Strategy role", str(r["problems"]))
r = vc("Sure, here you go: " + reply() + " hope that helps", "Dana", "Applied", URL)
check("JSON surrounded by chatter still parses", r["ok"], str(r["problems"]))
r = vc("not json at all", "Dana", "Applied", URL)
check("invalid JSON fails with the right problem", not r["ok"] and r["problems"][0].startswith("invalid JSON: "),
      str(r["problems"]))
r = vc("{\"email_subject\": \"x\", ", "Dana", "Applied", URL, stop_reason="max_tokens")
check("max_tokens truncation fails first", r["problems"] == ["response truncated (hit max_tokens)"], str(r))
r = vc("   ", "Dana", "Applied", URL)
check("empty reply fails", r["problems"] == ["empty model response"] and r["body"] == "", str(r))

# ---- validator: dashes ----------------------------------------------------------------
r = run(body=APPLIED_BODY.replace("retail clients, and", "retail clients — and"))
check("em dash becomes a comma", "clients, and" in r["body"] and "—" not in r["body"], r["body"][60:220])
r = run(body=APPLIED_BODY.replace("retail clients, and", "retail clients–and"))
check("en dash becomes a comma", "clients, and" in r["body"] and "–" not in r["body"])
r = run(body=APPLIED_BODY.replace("retail clients, and", "retail clients,— and"))
check("comma plus dash does not leave ',,'", ",," not in r["body"] and ", ," not in r["body"] and "clients, and" in r["body"])
r = run(body=APPLIED_BODY.replace("Here is the posting", "— Here is the posting"))
check("dash at line start leaves no leading comma", not any(ln.lstrip().startswith(",") for ln in r["body"].split("\n")), r["body"])
r = run(subject="Strategy – Dana", dm=DM.replace("Thanks", "— Thanks"))
check("dashes in subject and DM are cleaned too", r["subject"] == "Strategy, Dana" and "—" not in r["dm"], f'{r["subject"]!r} {r["dm"]!r}')
r = run(body=APPLIED_BODY.replace("last few years", "2019–2024"))
check("numeric en-dash range becomes a hyphen", "2019-2024" in r["body"], r["body"][60:160])

# ---- validator: graduation tense ------------------------------------------------------
def grad(sentence):
    return run(body=APPLIED_BODY.replace("I applied for", sentence + " I applied for", 1))


for src, want in (("I'm graduating from Lakeview.", "I recently graduated from Lakeview."),
                  ("I am graduating from Lakeview.", "I recently graduated from Lakeview."),
                  ("I'm finishing up my MS at Lakeview.", "I recently completed my MS at Lakeview."),
                  ("I am finishing my MS at Lakeview.", "I recently completed my MS at Lakeview."),
                  ("I will be graduating from Lakeview.", "I graduated from Lakeview."),
                  ("I will graduate from Lakeview.", "I recently graduated from Lakeview.")):
    r = grad(src)
    check(f"tense fix: {src}", want in r["body"] and not has(r, "future-tense"), r["body"][:110])
r = grad("I finish up, graduating in May.")
check("'graduating in May' is flagged (no month-specific rewrite)", has(r, "future-tense graduation"), str(r["problems"]))
r = grad("I am an MS candidate at Lakeview.")
check("'MS candidate' is flagged", has(r, "future-tense graduation"), str(r["problems"]))
r = grad("I have expected to graduate for a while.")
check("'expected to graduate' is flagged", has(r, "future-tense graduation"), str(r["problems"]))
r = grad("I graduated from Lakeview in May.")
check("past tense 'graduated' is not flagged", not has(r, "future-tense"), str(r["problems"]))
r = run(dm="Hi Dana, I'm graduating from Lakeview and applied for the role.")
check("graduation fix applies to the DM", "I recently graduated" in r["dm"], r["dm"])

# ---- validator: sign-offs, greeting, structure ---------------------------------------
r = run(body=APPLIED_BODY + "\n\nBest,\nAlex")
check("'Best,\\nAlex' is stripped", r["body"].endswith("hiring team? I would be glad to send anything else that helps."), r["body"][-60:])
for phrase in ("The line in the posting that stayed with me is the one about scale.",
               "The hub being centralized is the part I keep coming back to.",
               "What drew me to it is who the users are.",
               "Two things in the posting pull against each other.",
               "Most AI product work I see is aimed at customers."):
    r = run(body=APPLIED_BODY.replace("I applied for", phrase + " I applied for"))
    check(f"Rejected tell is flagged: {phrase[:40]}", not r["ok"] and any("AI-pattern phrasing" in x for x in r["problems"]), str(r["problems"]))
r = vc(json.dumps({"email_subject": "Hi", "email_body": APPLIED_BODY.replace(
        "the Strategy Consultant role", "the (Senior) Network Planning Analyst, United States - Globex role"),
        "linkedin_dm": "Hi Dana, I applied and would value connecting."}),
    "Dana", "Applied", URL, raw_title="(Senior) Network Planning Analyst, United States - Globex")
check("Pasting the posting's raw title is flagged", any("raw title" in x for x in r["problems"]), str(r["problems"]))
r = run(body=APPLIED_BODY + "\n\nThanks!\n\nAlex Rivera")
check("'Thanks!' then 'Alex Rivera' both stripped", r["body"].endswith("anything else that helps.") and r["ok"], r["body"][-60:])
r = run(body="Hi Dana,\n\nBest,\nAlex")
check("body of only greeting plus sign-off fails on paragraph count", has(r, "fewer than 2 paragraphs"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace("Hi Dana,", "Dana,"))
check("missing greeting flagged", has(r, "missing greeting line"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace("Hi Dana,", "Hi Priya,"))
check("wrong greeting name flagged", has(r, "greeting does not address Dana"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace("Hi Dana,", "Hi Danae,"))
check("greeting 'Danae' does not pass for 'Dana'", has(r, "greeting does not address"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace("\n\n", "\n"))
check("single paragraph flagged", has(r, "fewer than 2 paragraphs"), str(r["problems"]))
r = run(subject="")
check("missing subject flagged", has(r, "missing subject"), str(r["problems"]))
r = run(body="Hi Dana,\n\nI applied. " + URL + " Please flag my resume.")
check("too short flagged with count", has(r, "too short ("), str(r["problems"]))
r = run(body=APPLIED_BODY + "\n\n" + "word " * 330)
check("too long flagged", has(r, "too long ("), str(r["problems"]))

# ---- validator: modes -----------------------------------------------------------------
r = run(body=APPLIED_BODY.replace("could you flag my resume to the hiring team", "could you pass my resume along"))
check("Applied does NOT need a call ask", r["ok"] and not has(r, "conversation"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace("could you flag my resume to the hiring team? I would be glad to send anything else that helps.", "I hope your week goes well."))
check("Applied needs a resume/application ask", has(r, "no resume/application ask"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace(URL, "the link"))
check("Applied needs the careers link when there is one", has(r, "careers page link missing"), str(r["problems"]))
r = vc(json.dumps({"email_subject": "Strategy role", "email_body": APPLIED_BODY.replace(URL, "the Strategy Consultant role (job ID 1234567890)"),
                                   "linkedin_dm": DM}), "Dana", "Applied", None, job_id="1234567890")
check("Without a careers link, naming the job ID passes", r["ok"], str(r["problems"]))
r = vc(json.dumps({"email_subject": "Strategy role", "email_body": APPLIED_BODY.replace(URL, "the link"),
                                   "linkedin_dm": DM}), "Dana", "Applied", None, job_id="1234567890")
check("Without a careers link, a missing job ID is caught", has(r, "job ID 1234567890 missing"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace(URL, URL + " (also https://www.linkedin.com/jobs/view/1234567890/)"))
check("A LinkedIn job link in an email is rejected", has(r, "contains a LinkedIn link"), str(r["problems"]))
r = run(body=EXPLORING_BODY, mode="Exploring", first="Sam")
check("clean Exploring draft passes and needs no job link", r["ok"], str(r["problems"]))
r = run(body=EXPLORING_BODY.replace("Would you have twenty minutes for a call in the next couple of weeks?", "I hope your week goes well.")
        .replace("I would love to hear how", "It would help to learn how"), mode="Exploring", first="Sam")
check("Exploring needs a conversation ask", has(r, "no conversation ask"), str(r["problems"]))

# ---- validator: style words, meta, DM -------------------------------------------------
for word in ("leveraged", "spearheaded", "robust", "synergy", "dynamic", "delve", "tapestry", "passionate about"):
    r = run(body=APPLIED_BODY.replace("running", f"{word} and running"))
    check(f"AI-pattern word flagged: {word}", has(r, "AI-pattern word"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace("I spent", "I actually spent"))
check("'actually' flagged", has(r, "uses 'actually'"), str(r["problems"]))
r = run(body=APPLIED_BODY + "\n\nI apologize for the length.")
check("meta-commentary flagged", has(r, "meta-commentary"), str(r["problems"]))
r = run(body=APPLIED_BODY.replace("hiring team?", "hiring team at [insert company]?"))
check("placeholder flagged", has(r, "meta-commentary"), str(r["problems"]))
r = run(dm="")
check("missing DM flagged", has(r, "missing linkedin_dm"), str(r["problems"]))
r = run(dm="Hi Dana " + "word " * 56)
check("DM of 58 words flagged", has(r, "linkedin_dm too long"), str(r["problems"]))
r = run(dm="Hi Dana " + "word " * 53)
check("DM of 55 words allowed", not has(r, "linkedin_dm"), str(r["problems"]))

# ---- validator: profile-driven options ------------------------------------------------
r = run(body=APPLIED_BODY.replace("I would be glad", "I can circle back and I would be glad"))
check("a banned phrase from voice.md is flagged", has(r, "banned phrase (voice.md): 'circle back'"), str(r["problems"]))
r = validate_and_clean(reply(body=APPLIED_BODY.replace("I applied for", "I am an MS candidate at Lakeview. I applied for", 1)),
                       "Dana", "Applied", URL)
check("no finished degree: the tense checks are off", not has(r, "future-tense"), str(r["problems"]))
r = validate_and_clean(reply(body=APPLIED_BODY + "\n\nAlex Rivera"), "Dana", "Applied", URL)
check("no signer names: a bare name line is not taken for a sign-off", r["body"].endswith("Alex Rivera"), r["body"][-40:])
r = run(body=APPLIED_BODY.replace("this week.", "this week. " + "More detail here. " * 2))
check("the word band comes from the caller", not has(r, "too long"), str(r["problems"]))
r = vc(reply(body=APPLIED_BODY.replace("this week.", "this week. " + "More detail here. " * 2)), "Dana", "Applied", URL,
       words=(60, 80))
check("a tighter band from the profile flags the same body", has(r, "too long ("), str(r["problems"]))
check("degree_words: abbreviation plus generic words", DEGREE_WORDS[0] == "MS" and "degree" in DEGREE_WORDS, str(DEGREE_WORDS))
check("degree_words: none finished is empty", degree_words([]) == [])

# ---- scheduler ------------------------------------------------------------------------
def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def slot(now, scheduled=(), counts=None, seed=1, **kw):
    return next_send_slot(now, list(scheduled), counts or {}, random.Random(seed), **kw)


MON = at(2026, 9, 28, 10, 0)     # a Monday
s = slot(MON)
check("empty queue inside window: now plus 1 to 5 minutes", timedelta(minutes=1) <= s - MON <= timedelta(minutes=5), str(s))
last = at(2026, 9, 28, 11, 0)
s = slot(MON, [last, at(2026, 9, 28, 10, 30)])
check("gap counted from the latest scheduled time (20 to 40 min)", timedelta(minutes=20) <= s - last <= timedelta(minutes=40), str(s))
s = slot(at(2026, 9, 28, 12, 0), [at(2026, 9, 28, 9, 0)])
check("gap counted from now when the queue is in the past", timedelta(minutes=20) <= s - at(2026, 9, 28, 12, 0) <= timedelta(minutes=40), str(s))
s = slot(at(2026, 10, 2, 17, 45), [at(2026, 10, 2, 17, 50)])
check("Friday 5:50 PM rolls to Monday 8:00 to 8:15", s.date() == date(2026, 10, 5) and s.hour == 8 and s.minute <= 15, str(s))
s = slot(at(2026, 10, 3, 11, 0))
check("Saturday rolls to Monday morning", s.date() == date(2026, 10, 5) and s.hour == 8 and s.minute <= 15, str(s))
s = slot(at(2026, 10, 4, 9, 0), [at(2026, 10, 4, 12, 0)])
check("Sunday with a queue rolls to Monday morning", s.date() == date(2026, 10, 5) and s.hour == 8, str(s))
s = slot(at(2026, 9, 29, 6, 0))
check("Tuesday 6 AM waits for 8:00 the same day", s.date() == date(2026, 9, 29) and s.hour == 8 and s.minute <= 15, str(s))
s = slot(at(2026, 9, 29, 19, 0))
check("after close rolls to the next weekday morning", s.date() == date(2026, 9, 30) and s.hour == 8, str(s))
minutes = {s.minute for s in (slot(at(2026, 10, 3, 11, 0), seed=i) for i in range(40))}
check("morning start varies between 8:00 and 8:15", len(minutes) > 3 and max(minutes) <= 15, str(sorted(minutes)))

# daily cap: 4 sent + 6 queued Monday = 10, so the next lands on Tuesday
queued = [at(2026, 9, 28, 10 + i) for i in range(6)]
s = slot(at(2026, 9, 28, 9, 0), queued, {date(2026, 9, 28): 4}, daily_cap=10)
check("daily cap (sent plus scheduled) rolls to next weekday", s.date() == date(2026, 9, 29) and s.hour == 8, str(s))
s = slot(at(2026, 9, 28, 9, 0), [at(2026, 9, 28, 9, 30)], {date(2026, 9, 28): 8}, daily_cap=10)
check("one slot below the cap stays on the same day", s.date() == date(2026, 9, 28), str(s))
s = slot(at(2026, 10, 2, 9, 0), [at(2026, 10, 2, 9, 30)], {date(2026, 10, 2): 9}, daily_cap=10)
check("Friday at the cap rolls over the weekend to Monday", s.date() == date(2026, 10, 5), str(s))
s = slot(at(2026, 9, 28, 9, 0), [], {date(2026, 9, 28): 10, date(2026, 9, 29): 10}, daily_cap=10)
check("consecutive capped days are both skipped", s.date() == date(2026, 9, 30), str(s))

# DST: 2026-11-01 (Sunday) is the fall-back day. Friday 10-30 is EDT, Monday 11-02 is EST.
before = at(2026, 10, 30, 17, 50)
s = slot(before, [before])
check("DST: Friday EDT rolls to Monday EST at 8:00 local", s.date() == date(2026, 11, 2) and s.hour == 8 and s.utcoffset() == timedelta(hours=-5), f"{s} {s.utcoffset()}")
check("DST: absolute gap spans the extra hour", s.astimezone(timezone.utc) - before.astimezone(timezone.utc) >= timedelta(days=2, hours=14), str(s - before))
s = slot(at(2026, 11, 1, 12, 0))
check("DST: Sunday of the change rolls to Monday morning", s.date() == date(2026, 11, 2) and s.hour == 8, str(s))
s = slot(datetime(2026, 11, 2, 12, 55, tzinfo=timezone.utc), [datetime(2026, 11, 2, 12, 55, tzinfo=timezone.utc)])
check("UTC inputs are read in Eastern (12:55Z Monday is 7:55 EST, before open)", s.tzinfo is not None and s.utcoffset() == timedelta(hours=-5) and s.hour == 8, str(s))
before = at(2026, 3, 6, 17, 50)   # spring forward is Sunday 2026-03-08
s = slot(before, [before])
check("DST: spring-forward weekend rolls to Monday EDT", s.date() == date(2026, 3, 9) and s.hour == 8 and s.utcoffset() == timedelta(hours=-4), f"{s} {s.utcoffset()}")

# determinism and monotonic chaining
a, b = slot(MON, seed=7), slot(MON, seed=7)
check("same seed gives the same slot", a == b)
check("returned slot is in the requested zone", slot(MON).tzinfo == ET or str(slot(MON).tzinfo) == "America/New_York")
rng = random.Random(42)
now, sched, out = at(2026, 9, 28, 9, 30), [], []
for _ in range(45):
    n = next_send_slot(now, sched, {}, rng)
    out.append(n)
    sched.append(n)
inc = all(y > x for x, y in zip(out, out[1:]))
check("45 chained slots strictly increase", inc)
gaps_ok = all((y - x) >= timedelta(minutes=20) for x, y in zip(out[1:], out[2:]))
check("chained slots never closer than the 20 minute gap", gaps_ok, str([str(y - x) for x, y in zip(out, out[1:]) if y - x < timedelta(minutes=20)][:3]))
in_hours = all(x.weekday() < 5 and 8 <= x.hour < 18 for x in out)
check("every chained slot is a weekday between 8:00 and 18:00 Eastern", in_hours)
per_day = {}
for x in out:
    per_day[x.date()] = per_day.get(x.date(), 0) + 1
check("no day exceeds the daily cap of 10", max(per_day.values()) <= 10, str(per_day))
check("the queue actually spilled across several days", len(per_day) >= 4, str(per_day))

tc.report(results)
