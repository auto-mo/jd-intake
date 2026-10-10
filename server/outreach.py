"""Outreach for jd-intake: the prompts Claude answers and the paid calls server code makes.

The rule this file exists to keep: the model thinks, code spends. Everything that costs money (the
Apify people search, the email finder) is a plain function here, called by app.py once per click,
never by the model. The prompt builders return text for `claude -p` with every tool disabled, so a
model answer can shape who gets a message but can never start a paid call.

Everything about you comes from the profile (userprofile.py): your name, your schools for the
alumni pass, your preferred cities, your facts (profile.md), your voice (voice.md, voice-examples.md)
and the rules learned from your edits (learnings.md). Optional: on only with features.outreach.
"""
import datetime
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import unicodedata

import userprofile

APIFY = "https://api.apify.com/v2"
# Some bot checks refuse Python's default "Python-urllib" agent, so every outbound request names itself.
USER_AGENT = "jd-intake/0.3 (local server)"
# The employee search finds the same people as a profile search at under half the price (no page fee).
# Emails are looked up only for people you approve, in one batch, paid per person plus a little more only
# for a verified address.
HARVEST_ACTOR = "harvestapi~linkedin-company-employees"
EMAIL_ACTOR = "crustapi~linkedin-profile-scraper-email-finder"
# The seniority ids the actor accepts; 400 throws a bad request.
SENIORITY = ["100", "110", "120", "130", "200", "210", "220", "300", "310", "320"]


# ── secrets ──────────────────────────────────────────────────────────────────

def load_env(path):
    """KEY=VALUE lines from a local .env. No quoting rules beyond stripping one pair of quotes."""
    out = {}
    try:
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


# ── paid calls (code only) ───────────────────────────────────────────────────

def _http(method, url, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json",
                                                                        "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "null")


def apify_run(actor, payload, token, max_wait_s=300):
    """Start one actor run, wait for it, return its items and what Apify says it cost.

    Start-then-poll rather than run-sync on purpose: when run-sync times out the run keeps
    going and still bills, but the caller has lost it. Here the run id is known from the first
    response, so a slow run is waited on and a failed one is still recorded with its cost.
    Returns {"items", "usd", "run_id", "status", "error"}; never raises for an HTTP error.
    """
    q = urllib.parse.urlencode({"token": token})
    try:
        run = _http("POST", f"{APIFY}/acts/{actor}/runs?{q}&waitForFinish=60", payload, timeout=90)["data"]
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        return {"items": [], "usd": None, "run_id": None, "status": "START_FAILED", "error": _err(e)}
    t0 = time.time()
    while run.get("status") in ("READY", "RUNNING") and time.time() - t0 < max_wait_s:
        try:
            run = _http("GET", f"{APIFY}/actor-runs/{run['id']}?{q}&waitForFinish=60", timeout=90)["data"]
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
            return {"items": [], "usd": run.get("usageTotalUsd"), "run_id": run.get("id"),
                    "status": "POLL_FAILED", "error": _err(e)}
    items, error = [], None
    if run.get("status") == "SUCCEEDED":
        try:
            items = _http("GET", f"{APIFY}/datasets/{run['defaultDatasetId']}/items?{q}&clean=true&format=json",
                          timeout=90) or []
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
            error = _err(e)
    else:
        error = f"run ended {run.get('status')}"
    # Apify keeps settling the charge after the run ends (a run can read half its final cost at first).
    # This is a first figure; app.py re-reads it later.
    try:
        time.sleep(4)
        run = _http("GET", f"{APIFY}/actor-runs/{run['id']}?{q}", timeout=30)["data"] or run
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
        pass
    return {"items": items if isinstance(items, list) else [], "usd": run.get("usageTotalUsd"),
            "run_id": run.get("id"), "status": run.get("status"), "error": error,
            "events": run.get("chargedEventCounts")}


def run_cost(run_id, token):
    """The settled cost and charged events of a finished run, for the later re-check."""
    q = urllib.parse.urlencode({"token": token})
    run = _http("GET", f"{APIFY}/actor-runs/{run_id}?{q}", timeout=30)["data"]
    return run.get("usageTotalUsd"), run.get("chargedEventCounts")


def _err(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            return f"HTTP {e.code}: {e.read().decode()[:200]}"
        except Exception:  # noqa: BLE001
            return f"HTTP {e.code}"
    return str(e)[:200]


def people_search_input(company_url, titles, city, max_items):
    """Full profiles without the email search: emails are paid for later, only for approved people.
    Full, not Short: Short returns internal ids that break the profile links."""
    return {"profileScraperMode": "Full ($8 per 1k)", "companies": [company_url], "jobTitles": titles,
            "seniorityLevelIds": SENIORITY, "locations": [city, "United States"] if city else ["United States"],
            "maxItems": int(max_items)}


def _months(dur):
    """'1 yr 3 mos' -> 15. LinkedIn's own duration text; None when it says nothing countable."""
    y = re.search(r"(\d+)\s*yr", dur or ""); m = re.search(r"(\d+)\s*mo", dur or "")
    return (int(y.group(1)) * 12 if y else 0) + (int(m.group(1)) if m else 0) if (y or m) else None


def _span(months):
    if months is None:
        return ""
    y, m = divmod(months, 12)
    return " ".join(x for x in (f"{y} yr" if y else "", f"{m} mo" if m else "") if x) or "under a month"


def still_at_company(ctx, company):
    """False when the profile's current employer is plainly another company (people searches return some former
    staff, now at another employer). True when unknown."""
    now = (ctx or {}).get("company") or ""
    if not now or not company:
        return True
    a = re.sub(r"[^a-z0-9]", "", _fold(re.sub(r"\(.*?\)", "", company.lower())))
    b = re.sub(r"[^a-z0-9]", "", _fold(re.sub(r"\(.*?\)", "", now.lower())))
    return bool(a and b) and (a[:5] in b or b[:5] in a)


def person_context(p):
    """What the drafter should know about one person, from the Full profile the search already paid for:
    current role and how long they have been there, the path before it, schools, a slice of their About.
    Kept small on purpose; the draft uses it to choose an angle, not to recite their resume."""
    exp = [e for e in p.get("experience") or [] if isinstance(e, dict)]
    cur = next((e for e in exp if not e.get("endDate") or (e.get("endDate") or {}).get("text") == "Present"), {})
    company = cur.get("companyName") or ""
    at_company = [e for e in exp if company and e.get("companyName") == company]
    months = [_months(e.get("duration")) for e in at_company]
    started = ((at_company[-1] if at_company else cur).get("startDate") or {}).get("text") or ""
    past = []
    for e in exp:
        if e in at_company or len(past) >= 4:
            continue
        past.append(" ".join(x for x in (e.get("position") or "", f"at {e.get('companyName')}" if e.get("companyName") else "",
                                         f"({_span(_months(e.get('duration')))})" if _months(e.get("duration")) else "") if x))
    schools = []
    for e in p.get("education") or []:
        if isinstance(e, dict) and e.get("schoolName"):
            deg = ", ".join(x for x in (e.get("degree"), e.get("fieldOfStudy")) if x)
            yrs = "-".join(str((e.get(k) or {}).get("year")) for k in ("startDate", "endDate") if (e.get(k) or {}).get("year"))
            schools.append(" ".join(x for x in (e["schoolName"], f"({deg})" if deg else "", yrs) if x))
    about = re.sub(r"\s+", " ", p.get("about") or "").strip()
    return {k: v for k, v in {
        "current_role": cur.get("position") or "", "company": company,
        "roles_at_company": len(at_company),
        "at_company_for": _span(sum(x for x in months if x) if any(months) else None),
        "since": started, "location": (p.get("location") or {}).get("linkedinText") or "",
        "path_before": past, "schools": schools[:3], "about": about[:400],
        "open_to_work": bool(p.get("openToWork")) or None, "hiring": bool(p.get("hiring")) or None,
    }.items() if v not in ("", [], None, 0)}


def profiles_from_harvest(items):
    """HarvestAPI profile items as flat records. Field handling is Workflow 2's: the current
    position wins over the headline for the title, and only a valid or deliverable email counts."""
    out = []
    for p in items or []:
        if not isinstance(p, dict):
            continue
        name = f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip()
        url = p.get("linkedinUrl") or ""
        if not name or not url:
            continue
        cur = next((e for e in p.get("experience") or []
                    if not e.get("endDate") or (e.get("endDate") or {}).get("text") == "Present"), {})
        emails = [e for e in p.get("emails") or [] if (e.get("status") == "valid" or e.get("deliverable"))
                  and not personal_address(e.get("email"))]
        edu = " | ".join(e.get("schoolName") or "" for e in (p.get("education") or p.get("profileTopEducation") or []))
        out.append({"name": name, "first": (p.get("firstName") or name.split()[0]).strip(),
                    "headline": p.get("headline") or "", "title": cur.get("position") or p.get("headline") or "",
                    "linkedin_url": url, "location": (p.get("location") or {}).get("linkedinText") or "",
                    "education": edu, "email": (emails[0].get("email") if emails else None)
                    or (p.get("email") if not personal_address(p.get("email")) else None) or None,
                    "ctx": person_context(p)})
    return out


def alumni_search_input(company_url, max_items=5):
    """Everyone at the company who lists one of your schools, any title or seniority. None when the profile names
    no school, and then the alumni pass is skipped."""
    schools = userprofile.school_names()
    if not schools:
        return None
    return {"profileScraperMode": "Full ($8 per 1k)", "companies": [company_url], "schools": schools,
            "maxItems": int(max_items)}


def email_lookup_input(profile_urls):
    return {"profiles": list(profile_urls), "findEmail": True, "maxItems": 0}


def _fold(s):
    """Lowercase ASCII letters only: 'Haugsbø' -> 'haugsbo'."""
    s = (s or "").lower().translate(str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d", "þ": "th"}))
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if c.isascii() and (c.isalnum() or c == " "))


# Credentials and nicknames are not part of an address: a name shown as "Pat Quinn, MA, RCDD" must not turn
# into an address with the credentials in it. Case-sensitive, so a surname like "Ma" stays.
_CREDENTIALS = {"MA", "MS", "MSc", "MBA", "PhD", "PMP", "CFA", "CPA", "CISA", "CISSP", "RCDD", "PE", "JD", "MD",
                "PHR", "SPHR", "SHRM-CP", "SHRM-SCP", "CSM", "CSPO", "PMI-ACP", "Jr", "Sr", "II", "III", "MPH", "MSW"}


def clean_name(name):
    """'Pat Quinn, MA, RCDD' -> 'Pat Quinn'; 'Mei (Annie) Lin' -> 'Mei Lin';
    'Jordan Lee PMP MBA' -> 'Jordan Lee'."""
    n = re.sub(r"\([^)]*\)", " ", name or "").split(",")[0]
    words = n.split()
    return " ".join(w for i, w in enumerate(words) if i == 0 or w.strip(".") not in _CREDENTIALS)


def tidy_guess(name, email):
    """A guessed address whose local part is not a usual pattern of the person's clean first and last
    name is rebuilt as first.last at the same domain. Usual: first.last, firstlast, first_last, flast,
    f.last, first, last.first, first.l."""
    local, at, domain = (email or "").partition("@")
    parts = [_fold(w) for w in clean_name(name).split() if len(_fold(w)) > 1]
    if not at or len(parts) < 2:
        return email
    f, l = parts[0], parts[-1]
    usual = {f"{f}.{l}", f"{f}{l}", f"{f}_{l}", f"{f}-{l}", f"{f[0]}{l}", f"{f[0]}.{l}", f, f"{l}.{f}", f"{f}.{l[0]}",
             f"{f}.{''.join(parts[1:])}", f"{f}{''.join(parts[1:])}"}
    return email if local.lower() in usual else f"{f}.{l}@{domain}"


def name_fits_email(name, email):
    """A guessed address is only kept when its local part plainly spells this person's name: the
    last name (any part of it), plus the first name or its initial. Rejects mangled guesses such as
    'jamie.luander' for Jamie Lu Andersen."""
    local = _fold((email or "").split("@")[0].replace(".", " ").replace("_", " ").replace("-", " "))
    joined = local.replace(" ", "")
    parts = [w for w in _fold(clean_name(name)).split() if len(w) > 1]
    # No full surname (LinkedIn shows "Riley P." to non-connections): nothing to check a guess against.
    if len(parts) < 2 or not joined:
        return False
    first, lasts = parts[0], parts[1:]
    # The surname (the last part) must appear: a middle name alone is not enough evidence.
    last_ok = lasts[-1] in joined or "".join(lasts) in joined
    first_ok = first in joined or joined.startswith(first[0]) or local.split()[0] == first[0]
    return last_ok and first_ok


# The first lookup: in testing it found most addresses, matched every delivered address it could check and
# knew companies whose mail domain differs from their website. Paid per email found, nothing for misses. It
# once returned a different person at another company, so an answer is kept only on the company's own
# domains (`company_domain_ok`).
FINDER_ACTOR = "vulnv~linkedin-email-finder"

# Never email a personal address: outreach goes to work addresses only.
PERSONAL_DOMAINS = {"gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com", "outlook.com", "live.com",
                    "msn.com", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "gmx.com",
                    "mail.com", "zoho.com", "yandex.com", "rediffmail.com", "qq.com", "163.com"}


def personal_address(email):
    return (email or "").rsplit("@", 1)[-1].strip().lower() in PERSONAL_DOMAINS


def finder_input(profile_urls):
    return {"urls": list(profile_urls)}


def _stem(domain):
    """'mail.example.net' -> 'example', 'joinacme.com' -> 'joinacme'."""
    parts = (domain or "").lower().strip(".").split(".")
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")


def company_domain_ok(domain, company, known_domains=()):
    """True when an address's domain belongs to the company: the same stem as a known company domain
    (its website, an address already delivered or confirmed there), or the company's name squeezed
    together ('Copper Leaf' -> 'copperleaf'). copperleaf.net passes for Copper Leaf; leafcapital.com does not."""
    stem = _stem(domain)
    if not stem:
        return False
    name = re.sub(r"[^a-z0-9]", "", _fold(re.sub(r"\b(inc|llc|ltd|lp|l\.p\.|corp|co|group|labs?|ai|technologies)\b\.?", "",
                                                 (company or "").lower())))
    return stem in {_stem(d) for d in known_domains if d} or (bool(name) and (stem == name or stem in name.split() or name.startswith(stem) and len(stem) >= 3))


def emails_from_finder(items, people, company, known_domains=()):
    """Map profile URL to email for answers the finder found on the company's own domains."""
    def key(u):
        return (u or "").rstrip("/").rsplit("/", 1)[-1].lower()
    by_key = {key(p["linkedin_url"]): p for p in people}
    out = {}
    for it in items or []:
        p = by_key.get(key(it.get("linkedin_url") or it.get("url")))
        email = (it.get("email") or "").strip()
        if (p and it.get("found") and "@" in email and not personal_address(email)
                and company_domain_ok(email.rsplit("@", 1)[1], company, known_domains)):
            out[p["linkedin_url"]] = email
    return out


def emails_from_lookup(items, people):
    """Map each approved person's profile URL to (email, kind). kind is 'verified' when the mail
    server confirmed it, 'pattern' for a best guess that matches the name, absent otherwise."""
    def key(u):
        return (u or "").rstrip("/").rsplit("/", 1)[-1].lower()
    by_key = {key(p["linkedin_url"]): p for p in people}
    out = {}
    for it in items or []:
        p = by_key.get(key(it.get("inputUrl") or it.get("linkedinUrl") or it.get("publicIdentifier")))
        email = (it.get("email") or it.get("workEmail") or "").strip()
        if not p or "@" not in email or personal_address(email):
            continue
        status = (it.get("emailStatus") or "").lower()
        if status == "verified":
            out[p["linkedin_url"]] = (email, "verified")
        elif status == "pattern-likely" and name_fits_email(p["name"], email):
            out[p["linkedin_url"]] = (tidy_guess(p["name"], email), "pattern")
    return out


# ── prompts (the model thinks) ───────────────────────────────────────────────

TITLES_SCHEMA = {"type": "object", "properties": {"titles": {"type": "array", "items": {"type": "string"}}},
                 "required": ["titles"]}
RANK_SCHEMA = {"type": "object", "properties": {"selected": {"type": "array", "items": {
    "type": "object", "properties": {"linkedin_url": {"type": "string"}, "why": {"type": "string"},
                                     "priority": {"type": "string"}, "fit": {"type": "integer"}},
    "required": ["linkedin_url", "why", "fit"]}}}, "required": ["selected"]}
DRAFTS_SCHEMA = {"type": "object", "properties": {"drafts": {"type": "array", "items": {
    "type": "object", "properties": {"linkedin_url": {"type": "string"}, "email_subject": {"type": "string"},
                                     "email_body": {"type": "string"}, "linkedin_dm": {"type": "string"}},
    "required": ["linkedin_url", "email_subject", "email_body", "linkedin_dm"]}}}, "required": ["drafts"]}
AUDIT_SCHEMA = {"type": "object", "properties": {"audits": {"type": "array", "items": {
    "type": "object", "properties": {"linkedin_url": {"type": "string"}, "score": {"type": "integer"},
                                     "notes": {"type": "array", "items": {"type": "string"}}},
    "required": ["linkedin_url", "score", "notes"]}}}, "required": ["audits"]}


def role_name(title, company):
    """The role as a person says it: '(Senior) Product Analyst, United States - Example Co'
    becomes 'Senior Product Analyst'. Location and company suffixes go."""
    t = (title or "").strip()
    if company:
        t = re.sub(r"\s*[-|:]\s*" + re.escape(company) + r"\s*$", "", t, flags=re.I)
    t = re.sub(r",\s*(United States|USA|US|Remote|Hybrid|Onsite)\s*$", "", t, flags=re.I)
    t = re.sub(r"\((?:Sr\.?|Senior)\)\s*", "Senior ", t, flags=re.I)
    t = re.sub(r"\bAi\b", "AI", t)          # "Senior Ai Enablement Consultant", as some postings write it
    t = re.sub(r"\s*\([^)]*(?:remote|hybrid|onsite)[^)]*\)", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" -,") or (title or "").strip()


def link_rule(job):
    """What the email says about where the role is posted: the careers page link when there is one, otherwise the
    role by name with its job ID. Never a LinkedIn link."""
    if job.get("url"):
        return f"the careers page link {job['url']}"
    return f"the role by name with its job ID, as: {job.get('job_ref')}. No link at all"


def _who():
    return userprofile.name(), userprofile.first_name()


def _schools_text():
    names = userprofile.school_names()
    return " or ".join(names) if names else ""


def _job_head(job, ev):
    return (f"ROLE: {job.get('title')} at {job.get('company')} ({job.get('location') or 'location not given'})\n"
            f"POSTING: {job.get('url') or 'none'}\n"
            f"THE EVALUATION OF THE FIT: score {ev.get('fit_score')}, {ev.get('recommendation')}. "
            f"{ev.get('honest_take') or ''}")


def titles_prompt(job, jd_text, ev):
    name, _ = _who()
    return (f"{_job_head(job, ev)}\n\nJOB DESCRIPTION:\n{(jd_text or '')[:9000]}\n\n"
            f"{name} has already applied to this role and wants people at this company who can get the "
            "application seen: recruiters and talent acquisition who own this function's pipeline first, "
            "then the likely hiring manager and their leadership chain in the role's function.\n\n"
            "Give 5 to 8 LinkedIn job-title keywords that would surface those people at this company. Short, "
            "real titles people actually use on LinkedIn; broad enough to match, specific to this function. "
            "No generic titles like Employee or Staff.\n\n"
            'Answer with JSON only: {"titles": ["...", "..."]}')


def rank_prompt(job, jd_text, ev, profiles, keep):
    name, first = _who()
    slim = [{k: p[k] for k in ("name", "title", "headline", "linkedin_url", "location", "education")}
            for p in profiles]
    schools = _schools_text()
    cities = ", ".join(str(c) for c in userprofile.get()["targets"].get("preferred_cities") or [])
    order = ["recruiters or talent acquisition for this company or function"]
    if schools:
        order.append(f"alumni of {schools} (a warm path)")
    order.append("hiring managers and senior leaders in the role's own function who could refer internally")
    near = f"then location near the role{', or in ' + cities if cities else ''}"
    return (f"{_job_head(job, ev)}\n\nJOB DESCRIPTION (for the function and team):\n{(jd_text or '')[:5000]}\n\n"
            f"PROFILES FOUND AT THE COMPANY:\n{json.dumps(slim, indent=1)}\n\n"
            f"{name} has ALREADY APPLIED to this role. "
            f"Choose the {keep} people most able to get the application seen and the resume forwarded, in "
            "order. Rank by: " + "; ".join(f"{i}. {x}" for i, x in enumerate(order, 1)) + f"; {near}. Rank only on "
            "role, function, seniority, shared school and location; never on anything about the person's name or "
            "background. Leave out anyone clearly outside the role's function or too junior to help.\n\n"
            f"For each person give one sentence on why them, for this job, that {first} would find useful when "
            f"deciding whether to message them. Use only facts in their profile above. If fewer than {keep} are "
            "worth messaging, return fewer. Never invent anyone.\n\n"
            "Give each person a fit score from 1 to 10: how likely a message to them is to get this "
            "application in front of the hiring team. 9 or 10: owns or directly influences this role's "
            "pipeline. 6 to 8: in the role's function and senior enough to refer. 5 or below: a long shot. "
            "Score from their profile only; do not inflate.\n\n"
            'Answer with JSON only: {"selected": [{"linkedin_url": "...", "why": "...", "fit": 7, '
            '"priority": "Recruiter|Alumni|Hiring chain|Standard"}]}')


_RECRUITER = re.compile(r"recruit|talent|sourc|people partner|people ops|hiring|human resources|\bhr\b", re.I)
_FOUNDER = re.compile(r"\b(co-?founder|founder|ceo|chief executive|president)\b", re.I)
_LEADER = re.compile(r"\b(director|head|vp|vice president|principal|partner|chief|general manager|lead)\b", re.I)


def reader_kind(p):
    """Who the email is for, from their current title: it sets length, the ask and the credential."""
    title = f"{p.get('title') or ''} {p.get('headline') or ''}"
    if _RECRUITER.search(p.get("title") or ""):
        return "recruiter"
    if _FOUNDER.search(title):
        return "founder"
    if _LEADER.search(p.get("title") or ""):
        return "leader"
    return "peer"


def is_alum(p):
    """True when the person's education names one of your schools (profile `schools` and their aliases)."""
    edu = (p.get("education") or "").lower()
    return any(s in edu for s in userprofile.school_patterns())


def first_sentence(text):
    """The first sentence of substance after the greeting. A short courtesy paragraph ("I hope your week
    is going well.") is skipped: it is meant to be simple and is not what makes two emails read alike."""
    body = re.sub(r"^\s*(hi|hello|dear)\b[^\n,]*,?\s*", "", text or "", flags=re.I).strip()
    paras = [x.strip() for x in re.split(r"\n\s*\n", body) if x.strip()]
    if len(paras) > 1 and len(paras[0].split()) <= 15:
        body = "\n\n".join(paras[1:])
    # "I'm <name>." and the applied-with-link sentence are the same facts in every email by design;
    # sameness is judged on what comes next (why this person, or the story).
    first = re.escape(userprofile.first_name().lower())
    intro = re.compile(r"(i'?m|i am|my name is) " + first + r"\b", re.I)
    sentences = [x for x in re.split(r"(?<=[.?!])\s+|\n+", body) if x.strip()]
    for s in sentences:
        if len(s.split()) <= 4 or intro.match(s) or "http" in s:
            continue
        return s
    return sentences[0] if sentences else ""


def opening(text):
    """The first sentence's words, lowercased and without links, for comparing a batch."""
    return re.findall(r"[a-z]+", re.sub(r"https?://\S+", "", first_sentence(text).lower()))


def openings_alike(a, b):
    """Two openings read alike when their first eight words mostly overlap ("Would you be willing to pass my
    resume..." against "Would you be open to passing my resume...")."""
    a, b = set(opening(a)[:8]), set(opening(b)[:8])
    return bool(a and b) and len(a & b) / len(a | b) >= 0.5


def voice_examples():
    """Real emails you sent (profile voice-examples.md): the drafter's style guide."""
    return userprofile.read_text("voice-examples.md")


def voice_rules():
    return userprofile.read_text("voice.md").strip() or "(no voice notes yet)"


def email_words():
    w = (userprofile.get().get("outreach") or {}).get("email_words") or [110, 140]
    return int(w[0]), int(w[1])


def _edits_text(recent_edits):
    return "\n\n".join(f"DRAFT:\n{e['draft']}\nWHAT WAS SENT INSTEAD:\n{e['sent']}" for e in recent_edits) or "(none yet)"


def drafts_prompt(job, jd_text, ev, people, profile_md, voice, standing, has_attachment, recent_edits,
                  feedback=None, learnings=""):
    """One call drafts every person for a job, so the set stays varied instead of five copies."""
    name, first = _who()
    lo, hi = email_words()
    ppl = [dict({"linkedin_url": p["linkedin_url"], "name": p["name"], "first_name": p["first"], "title": p["title"],
                 "headline": p.get("headline", ""), "education": p.get("education", ""),
                 "why_chosen": p.get("why", ""), "has_email": bool(p.get("email")),
                 "reader": reader_kind(p), "alum": is_alum(p),
                 "about_them": p.get("ctx") or {}},
                **({"previous_draft": p["previous_draft"], "fix_these": p["fix_these"]} if p.get("fix_these") else {}),
                **({"do_not_open_like": p["avoid_openings"]} if p.get("avoid_openings") else {}))
           for i, p in enumerate(people)]
    revising = any(p.get("fix_these") for p in people)
    attach = ("The resume PDF will be attached to the email; say so once, plainly." if has_attachment else
              "No resume will be attached. Do not say one is attached.")
    fb = f"\nFEEDBACK ON THE LAST VERSION, APPLY IT:\n{feedback}\n" if feedback else ""
    role = role_name(job.get("title"), job.get("company"))
    return (f"You are drafting outreach emails and LinkedIn connection notes for {name}, in {first}'s "
            f"voice, to people at a company where {first} has already applied.\n\n{standing}\n\n"
            f"{_job_head(job, ev)}\n\nJOB DESCRIPTION:\n{(jd_text or '')[:7000]}\n\n"
            f"{first.upper()}'S FACTS (profile.md, the only source for any claim; never add a number that is not here):\n"
            f"{profile_md}\n\n"
            f"RECENT EDITS TO DRAFTS LIKE THESE (the strongest signal of what {first} wants):\n{_edits_text(recent_edits)}\n{fb}\n"
            f"{learnings}\n\n"
            f"RECIPIENTS:\n{json.dumps(ppl, indent=1)}\n\n"
            + ("THIS IS A REVISION. Each recipient carries previous_draft and fix_these, the notes from an audit "
               "of that draft. Rewrite so every note is resolved; keep what the notes praise; do not introduce a "
               "new problem while fixing one.\n\n" if revising else "") +
            f"THE ROLE, AS A PERSON SAYS IT: {role}. Never paste the posting's raw title with its location or "
            "company suffix.\n\n"
            f"HOW {first.upper()} WRITES. The rules (voice.md):\n{voice}\n\n"
            f"The emails below are {first}'s own. They are the style guide: if a sentence would look out of place "
            "in one of them, it does not go in. Do not lift lines from them word for word.\n\n"
            + voice_examples() + "\n\n"
            "WHAT EACH EMAIL DOES: greet by first name; a short friendly line before any business; who the sender "
            f"is, in a line; that they applied to the {role} role, naming it with {link_rule(job)}; one piece of "
            "work this person would care about, in plain words with one number from the facts; then the ask, "
            "plainly. The resume is attached when the line above says so.\n"
            "FOR THIS PERSON: read 'about_them' and choose what to mention and how to open: a shared school ('alum' "
            "is true), a past employer, that they founded something. Only what is literally true; never their "
            "headline, never an invented fact about them or the sender. A connection read off their profile is said "
            "as a guess, not a fact, and only when it is the reason for writing to them. A founder is asked whether "
            "they would be open to a short conversation, never to forward a resume. Name a team only if the posting "
            "names it.\n"
            "DON'T: narrate the email ('I'll keep this short'); use metaphors or abstract framing; hedge the ask "
            "('if it seems like a fit'); react to the posting; explain their work to them; flatter; open with the "
            "request before any context; mention the tool that drafted this email or any job-search automation as a "
            "credential, since it tells the reader the email was automated; use a LinkedIn link, em or en dashes, "
            "'actually', 'leverage', 'robust', 'delve'.\n"
            "A recipient carrying 'do_not_open_like' lists how the other emails in this set read: this one must "
            "not read like them.\n"
            f"LENGTH: {lo} to {hi} words after the greeting. Short paragraphs. {attach} No sign-off and no name at "
            "the end; the signature is added when it is sent.\n"
            f"SUBJECT: plain ('{role} application').\n"
            "LINKEDIN NOTE: 35 to 50 words, the same voice, no subject: 'Hi <first_name>,', that the sender applied to "
            "the role, one plain line connecting them to this person, and that they would love to connect.\n\n"
            'Answer with JSON only: {"drafts": [{"linkedin_url": "...", "email_subject": "...", '
            '"email_body": "...", "linkedin_dm": "..."}]} with one entry per recipient.')


def repair_prompt(draft, problems, person, job, standing, learnings=""):
    name, first = _who()
    lo, hi = email_words()
    return (f"{standing}\n\n{learnings}\n\nThis outreach draft for {name} failed checks. Fix ONLY these problems and "
            f"keep everything else as it is:\n- " + "\n- ".join(problems) + "\n\n"
            f"Recipient first name: {person['first']}. Role: {job.get('title')} at {job.get('company')}. "
            f"Where the role is posted: {link_rule(job)}. Never a LinkedIn link.\n"
            f"Keep {first}'s voice. The email starts 'Hi <name>,' then a short friendly line, never a request; the ask "
            f"comes last; {lo} to {hi} words after the greeting; no sign-off.\n\n"
            f"CURRENT DRAFT:\n{json.dumps(draft, indent=1)}\n\n"
            'Answer with JSON only: {"email_subject": "...", "email_body": "...", "linkedin_dm": "..."}')


FACTCHECK_SCHEMA = {"type": "object", "required": ["checks"], "properties": {"checks": {"type": "array", "items": {
    "type": "object", "required": ["linkedin_url", "unsupported", "fits_anyone"],
    "properties": {"linkedin_url": {"type": "string"},
                   "unsupported": {"type": "array", "items": {"type": "string"}},
                   "fits_anyone": {"type": "boolean"}, "use_instead": {"type": "string"}}}}}}


def factcheck_prompt(job, jd_text, items, profile_md, standing):
    """A literal check, separate from the audit: every claim about the sender against profile.md, every claim
    about the recipient against their profile, every claim about the company or role against the posting.
    Warmth and personalisation push a drafter into embellishing; this catches it."""
    name, first = _who()
    return (f"Fact-check outreach drafts {name} will send about the {job.get('title')} role at "
            f"{job.get('company')}. Today is {datetime.date.today().isoformat()}.\n\n"
            f"{first.upper()}'S FACTS (the only source for claims about the sender):\n"
            f"{profile_md}\n\n{standing}\n{first} has applied to this role; the email refers to it with {link_rule(job)}.\n\n"
            f"THE POSTING (the source for claims about the role, team or company):\n{(jd_text or '')[:7000]}\n\n"
            f"DRAFTS, each with 'about_them' (the recipient's profile, the only source for claims about them):\n"
            f"{json.dumps(items, indent=1)}\n\n"
            "For each draft, list in 'unsupported' every statement its sources do not support, each as: the quoted "
            "words, then why (what the source says instead, or that it says nothing). That covers: anything about "
            "the sender not in the facts or against a standing fact, including invented scenes, feelings, habits, "
            "outcomes and wrong durations; anything about the recipient not in 'about_them' or their title, "
            "including connections stretched by analogy and generalisations about people like them; any team, "
            "group or claim about the company not in the posting. Do not list the application itself, the posting "
            "link, the ask, courtesy lines, or what the sender hopes or would like. Be literal and strict. "
            "'fits_anyone': true if the draft would work unchanged for anyone else at the company; then say in "
            "'use_instead' what in 'about_them' it should have used.\n\n"
            'Answer with JSON only: {"checks": [{"linkedin_url": "...", "unsupported": ["..."], "fits_anyone": false, '
            '"use_instead": ""}]}')


def audit_prompt(job, items, voice, recent_edits, profile_md="", learnings=""):
    """A second read, before anything is sent: would the sender send this as written?"""
    name, first = _who()
    lo, hi = email_words()
    schools = _schools_text() or "one of the sender's schools"
    return (f"You are auditing outreach drafts written for {name} before any of them is sent. "
            f"Role: {job.get('title')} at {job.get('company')}.\n\n"
            f"{first.upper()}'S VOICE (voice.md):\n{voice}\n\n{learnings}\n\n"
            f"RECENT EDITS (what {first} changes is what {first} wants):\n{_edits_text(recent_edits)}\n\n"
            f"VERIFIED FACTS (a number that appears here is real; flag only a number or claim that does not):\n"
            f"{profile_md}\n\n"
            "Each draft carries 'reader' (recruiter, founder, leader or peer) and 'alum' (true when the recipient "
            f"went to {schools}). Judge whether its credential and its "
            "ask fit that reader and that person's title. Each draft also carries 'about_them': the recipient's current "
            "role, tenure, path, schools and About, from their profile.\n\n"
            "PERSONAL: there is no fixed shape. Judge whether the draft is written for this one person: its angle, its "
            "piece of work and its ask should follow from their seniority, function, tenure and path, and any real "
            "overlap with the sender. A draft that would work unchanged for anyone else at the company scores 55 or "
            "lower; say what in 'about_them' it should have used. Any claim about the recipient that 'about_them' does "
            "not support scores 30 or lower; quote it. Reciting their resume back to them, or naming their tenure when "
            "it is not natural, is a flaw.\n\n"
            f"{first.upper()}'S OWN EMAILS (the measure of the voice):\n" + voice_examples() + "\n\n"
            f"VOICE: a draft that would look out of place among {first}'s own emails above, or that breaks a rule in "
            "voice.md or in the learned rules, cannot score above 60. 40 or lower if it narrates the email ('I'll keep "
            "this short'), uses a metaphor or abstract framing, or hedges the ask ('if it reads like a fit'). 55 or "
            "lower if it states a connection read off their profile as fact instead of a guess, names a profile fact as "
            "a reason without saying the reason, or reuses a line from the example emails word for word. Quote the "
            "sentence.\n\n"
            "STANDING OUTREACH RULES: one credential at most; at most one plain factual sentence about the "
            "recipient's company; no call offered as boilerplate; say each thing once; assume the reader is "
            "competent; no steering the reader; no em dashes; one number in the story; "
            f"{lo} to {hi} words after the greeting for every email.\n\n"
            "HARD CAPS (these read as machine-written): a draft scores 40 or lower if it reacts to the posting ('the "
            "line that stayed with me', 'what drew me'), explains the reader's own work back to them, pastes the "
            "posting's raw title with its location or company suffix, reads like another draft in this set once past "
            "any simple courtesy and the introduction (the sentence saying who the sender is and that they applied, "
            "with the link, carries the same facts in every email and is never a reason to cap), or uses a rhetorical "
            "contrast to sound insightful. Also 40 or lower: it opens with a request before any context; to a "
            "founder, it asks them to forward the resume, mentions their headline or that they are hiring, or offers "
            "to 'take a call'; it says 'whoever is hiring'; it has a line that undercuts the sender; it states "
            "something the sender cannot know (the weather, their week) or jokes about the email being cold. Name "
            "the exact sentence in the note.\n\n"
            "OPENING WARMTH: a draft may open on a real connection with the reader or on a simple courtesy ('I hope "
            "your week is going well.'). A simple courtesy is fine; never mark it down for being simple or for "
            "resembling another draft's courtesy, unless the wording is identical. A real connection, when "
            "'about_them' offers one, is better.\n\n"
            "LINKEDIN NOTES: a draft with channel 'linkedin' and an empty email_body is a connection note, not "
            "an email. Judge it only on the note rules: 35 to 50 words, 'Hi <name>,', that the sender applied to the "
            "role, one plain line on why it fits, that they would love to connect, a shared school first when 'alum' "
            "is true, in the sender's voice. None of the email rules (length band, opening, story, per-reader ask) "
            "apply to a note, and 'would love to connect' is the right close. Notes to one company starting with the "
            "same fact is a small flaw, not a cap.\n\n"
            "THE RIGHT ASK BY READER (do not mark these as boilerplate): a recruiter is asked to flag the "
            "application; a founder is asked, plainly and once, whether they would be open to a short "
            "conversation about the role; a leader for a quick chat or the hiring manager's name; a peer for a "
            "short chat and a referral if it fits.\n\n"
            f"DRAFTS:\n{json.dumps(items, indent=1)}\n\n"
            f"For each draft give a score from 0 to 100 for how likely {first} is to send it without changing a "
            "word, and up to three short notes. A note names a specific sentence and what is wrong with it, "
            "or, for a strong draft, the one thing it does well. Do not rewrite the draft. Be strict: 85 and "
            f"up means you would bet {first} sends it unchanged.\n\n"
            'Answer with JSON only: {"audits": [{"linkedin_url": "...", "score": 0, "notes": ["..."]}]}')


# ── dry run (devserver.py and tests) ─────────────────────────────────────────

def fake_people_items(company, n):
    """HarvestAPI-shaped items with obviously fictional people, for the dev copy. Never shipped."""
    rng = random.Random(company)
    roles = ["Talent Acquisition Partner", "Senior Recruiter", "Director, Strategy", "Strategy Manager",
             "University Recruiter", "VP, Operations", "Senior Manager, Business Operations", "Chief of Staff"]
    school = (userprofile.school_names() or ["Lakeview University"])[0]
    out = []
    for i in range(n):
        first, last = f"Sample{i + 1}", "Person"
        out.append({"firstName": first, "lastName": last, "headline": roles[i % len(roles)],
                    "experience": [{"position": roles[i % len(roles)]}],
                    "linkedinUrl": f"https://www.linkedin.com/in/sample-{re.sub('[^a-z]', '', company.lower())}-{i}",
                    "location": {"linkedinText": "Chicago, Illinois"},
                    "education": [{"schoolName": school if i == 2 else "Example University"}],
                    "emails": [{"email": f"sample{i + 1}@example.com", "status": "valid"}] if rng.random() < 0.5 else []})
    return out
