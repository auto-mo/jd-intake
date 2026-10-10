"""The one place the server, the resume engine and the tools read anything personal from.

Everything about the user lives in a profile directory (default: <repo>/profile, written by the `onboard`
skill). Point JDI_PROFILE_DIR somewhere else to use another one; the tests point it at examples/profile.

Files (see examples/profile/ for an invented person):
  profile.yaml          identity, targets, settings, feature switches, models
  profile.md            every claim a resume, cover letter or email may make (the source of truth)
  base_versions.yaml    base resumes the tailored ones start from
  cover_kb.yaml         cover letter building blocks
  voice.md              how the user writes, plus banned phrases
  voice-examples.md     real emails the user sent, for the drafter to imitate
  application-answers.md  common form answers
  learnings.md          rules the `learn` skill took from the user's own edits
  approaches.yaml       optional: resume approaches by job type

Nothing here caches across a change on disk for long: get() rereads profile.yaml when its mtime changes,
so an edit (or a `learn` run) takes effect without a restart.
"""
import copy
import os
import re

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def profile_dir():
    return os.path.abspath(os.environ.get("JDI_PROFILE_DIR") or os.path.join(REPO, "profile"))


def path(name):
    """Absolute path of a file in the profile directory (it may not exist yet)."""
    return os.path.join(profile_dir(), name)


def exists():
    return os.path.isfile(path("profile.yaml"))


def read_text(name, default=""):
    try:
        with open(path(name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


DEFAULTS = {
    "identity": {"name": "", "first_name": "", "email": "", "phone": "", "location": "", "linkedin": "", "website": ""},
    "standing_facts": [],
    "degrees": [],
    "schools": [],
    "experience_order": [],
    "keep_every_role": True,
    "targets": {"roles": [], "level": "mid", "level_words_at_level": [], "locations": [], "preferred_cities": [],
                "years_experience": 0},
    "work_authorization": {"needs_sponsorship": False, "summary": "", "hard_blockers": [], "routes": []},
    "tools_confirmed": [],
    "resume": {"file_stem": "", "builds_title": "SELECTED PROJECTS", "bullets_per_role": [1, 4], "font": "Times New Roman"},
    "cover_letter": {"words": [250, 350], "signature": ""},
    "features": {"sponsorship": False, "outreach": False, "email": False, "alerts": False},
    "outreach": {"timezone": "America/New_York", "send_window": [9, 17], "daily_cap": 10, "gap_minutes": [20, 40],
                 "small_company": 300, "email_words": [110, 140], "signature": ""},
    "models": {"evaluate": "sonnet", "build": "sonnet", "planner": "opus", "ask": "opus", "outreach": "opus",
               "inbox": "sonnet", "handoff": "sonnet"},
}

_cache = {"mtime": None, "dir": None, "data": None}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def get():
    """profile.yaml merged over DEFAULTS. Missing file: the defaults, so the server still starts and the
    dashboard can say onboarding has not run yet."""
    p = path("profile.yaml")
    try:
        m = os.path.getmtime(p)
    except OSError:
        m = None
    if _cache["data"] is None or _cache["mtime"] != m or _cache["dir"] != profile_dir():
        data = {}
        if m is not None:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        merged = _merge(DEFAULTS, data)
        ident = merged["identity"]
        if not ident.get("first_name") and ident.get("name"):
            ident["first_name"] = ident["name"].split()[0]
        if not merged["resume"].get("file_stem") and ident.get("name"):
            merged["resume"]["file_stem"] = re.sub(r"[^A-Za-z0-9]+", "_", ident["name"]).strip("_")
        if not merged["cover_letter"].get("signature"):
            merged["cover_letter"]["signature"] = ident.get("name", "")
        _cache.update(mtime=m, dir=profile_dir(), data=merged)
    return _cache["data"]


# ── convenience accessors (read fresh each call through get()) ──────────────────────────────────────────

def name():
    return get()["identity"]["name"] or "the candidate"


def first_name():
    return get()["identity"]["first_name"] or "the candidate"


def feature(key):
    return bool(get()["features"].get(key))


def model(key, default="sonnet"):
    return get()["models"].get(key) or default


def file_stem():
    return get()["resume"]["file_stem"] or "Resume"


def standing_facts():
    return list(get()["standing_facts"])


def school_patterns():
    """Lowercase strings that mark someone as an alum of one of the user's schools."""
    out = []
    for s in get()["schools"]:
        out.append(s.get("name", "").lower())
        out += [a.lower() for a in s.get("aliases") or []]
    return list(dict.fromkeys(x for x in out if x))


def school_names():
    return [s.get("name") for s in get()["schools"] if s.get("name")]


def completed_degrees():
    return [d for d in get()["degrees"] if d.get("completed")]


def contact_line():
    """The resume and cover letter contact line, e.g. "Chicago, IL | +1 (555) 010-0199 | alex@example.com"."""
    i = get()["identity"]
    return " | ".join(x for x in (i.get("location"), i.get("phone"), i.get("email")) if x)


# ── base resumes ──────────────────────────────────────────────────────────────────────────────────────────

def _to_engine(v):
    """base_versions.yaml entry -> the tuple shape engine.py works with."""
    return {
        "education": [(e["school"], e.get("date", ""), e.get("place", ""), list(e.get("lines") or []))
                      for e in v.get("education") or []],
        "builds": {"title": (v.get("builds") or {}).get("title") or get()["resume"]["builds_title"],
                   "items": [tuple(x) for x in (v.get("builds") or {}).get("items") or []]} if v.get("builds") else {},
        "experience": [(x["company"], x.get("title", ""), x.get("dates", ""), list(x.get("bullets") or []))
                       for x in v.get("experience") or []],
        "skills_title": v.get("skills_title") or "SKILLS",
        "skills": [tuple(x) for x in v.get("skills") or []],
        "projects": list(v.get("projects") or []),
    }


def base_versions():
    """{key: {"label", "signals", "content"}} with `inherit` resolved. Empty when onboarding has not run."""
    try:
        with open(path("base_versions.yaml"), encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except OSError:
        return {}
    vs = raw.get("versions") or {}
    out = {}
    for key, v in vs.items():
        merged = dict(vs.get(v.get("inherit")) or {}, **{k: x for k, x in v.items() if k != "inherit"}) if v.get("inherit") else v
        out[str(key)] = {"label": merged.get("label", str(key)), "signals": merged.get("signals", ""),
                         "content": _to_engine(merged)}
    return out


def default_version():
    try:
        with open(path("base_versions.yaml"), encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except OSError:
        raw = {}
    keys = list((raw.get("versions") or {}).keys())
    d = str(raw.get("default") or (keys[0] if keys else ""))
    return d
