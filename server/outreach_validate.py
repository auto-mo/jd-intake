#!/usr/bin/env python3
"""Deterministic outreach checks and the send-time scheduler. Standard library only, no I/O.

validate_and_clean: cleans what the model wrote and lists what is still wrong; the caller decides
whether to ask the model for a repair. Everything personal (the word band, your banned phrases, your
name for stripping a stray sign-off, your finished degrees for the tense fixes) is passed in by app.py
from the profile.
next_send_slot: staggered weekday work-hours send times in your time zone.
"""
import json
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Words and phrases that read as model output.
AI_WORDS = re.compile(
    r"\b(leverag(?:e|es|ed|ing)|spearhead(?:s|ed|ing)?|robust|synergies|synergy|dynamic"
    r"|delve[sd]?|delving|tapestry|passionate about)\b", re.I)
ACTUALLY = re.compile(r"\bactually\b", re.I)
# Phrases that announce a reaction to the posting or explain the reader's own work back to them
# ("the line in the posting that stayed with me", "the part I keep coming back to", "two things in the
# posting pull against each other") plus the same family. A hit is a problem the repair pass must
# rewrite, naming the phrase. Your own banned phrases (voice.md) are checked as well.
AI_PHRASES = re.compile(
    r"(stay(?:s|ed)? with me|stuck with me|keeps? coming back|kept coming back|keep returning|"
    r"caught my (?:eye|attention)|what (?:drew|draws|drives|excites|interests) me|what struck me|struck me|"
    r"resonat\w*|stood out|jumps? out|jumped out|the line (?:in|from) (?:the|your) (?:posting|description|role)|"
    r"the part of the (?:posting|role|description)|the part i (?:keep|kept)|(?:pulls?|pulling) against each other|"
    r"the real (?:question|design question|challenge|problem|work) (?:is|here)|is the difference between|"
    r"most (?:\w+ ){1,3}(?:work|teams|products?|tools?|companies) (?:i see|i've seen|out there)|i came across|hope (?:this|my) (?:email|note|message) finds you|i wanted to (?:reach out|introduce)|"
    r"i(?:'m| am) reaching out because|it'?s not (?:just|about)|not just about|game[- ]changer|"
    r"i'?ve been thinking about|i keep thinking|honest version|"
    # Scraped-profile tells and passing the buck ("Your headline says you are hiring, so I would take a
    # short call or you can send it on to whoever runs the search").
    r"your (?:linkedin )?headline|(?:i would|i'd) take a (?:short |quick )?call|"
    # The tool that drafted the email, used as a credential, tells the reader it was automated.
    r"my (?:own )?job search (?:runs|is run|pipeline)|job[- ]search (?:pipeline|system|automation)|"
    # Narrating the email, a metaphor, a hedged ask.
    r"keep (?:this|it) (?:short|brief)|easy to act on|(?:a|one) person next to|next to (?:the|my) application|"
    r"if (?:it|this|my background) (?:reads|seems|looks|sounds) like (?:a )?(?:fit|match)|"
    # An invented warm line about the weather, and a joke about the email itself.
    r"\bweather\b|turned (?:cold|chilly|warm)|cold (?:email|note|message|outreach))", re.I)
# The first sentence after the greeting is a request: asking with no context reads as spam.
OPENS_WITH_ASK = re.compile(
    r"^(would|could|can|will) you\b|^(can|may|could) i ask\b|^i(?:'d| would) like to ask\b|^a (?:small|quick) ask\b"
    r"|^(?:would|could) it be possible\b|^i(?:'m| am) (?:hoping|writing to ask)\b", re.I)
EMAIL_WORDS = (110, 140)          # the default band; the profile's outreach.email_words replaces it
META = re.compile(
    r"(i apologize|i'm sorry|as an ai|i do not have|i don't have enough|let me know if you|i cannot"
    r"|i was unable|here is the email|here'?s the email|\[insert|\bTBD\b|placeholder)", re.I)

# A model reads a recent graduation date and writes "finishing my degree". For a profile with a finished degree,
# the common shapes are fixed and the rest flagged. degree_words() turns the finished degrees into the words a
# sentence uses for them ("MBA", "MS", "degree").
def degree_words(degrees):
    """Words for the finished degrees: the abbreviation that starts each name ("MBA", "MS", "PhD"), plus the generic
    ones. [] when no degree is finished, which turns the tense checks off."""
    if not degrees:
        return []
    out = []
    for d in degrees:
        first = ((d.get("name") if isinstance(d, dict) else str(d)) or "").split()[:1]
        if first and len(first[0]) <= 5:
            out.append(first[0].strip(".,"))
    return list(dict.fromkeys(out + ["degree", "master's", "masters", "bachelor's"]))


def _deg(words):
    return "(?:" + "|".join(re.escape(w) for w in words) + ")"


def tense_fixes(words):
    """(pattern, replacement) pairs; the "I" forms first so "I'm finishing up my MBA" does not become
    "I'm recently completed"."""
    if not words:
        return []
    d = _deg(words)
    return [
        (r"\bI(?:'m| am) (?:finishing(?: up)?|about to finish) my (" + d + r")\b", r"I recently completed my \1"),
        (r"\bI(?:'m| am) (?:graduating|about to graduate)\b", "I recently graduated"),
        (r"\b(?:I will|I'll) graduate\b", "I recently graduated"),
        (r"\bI will finish my (" + d + r")\b", r"I recently completed my \1"),
        (r"\bwill be graduating\b", "graduated"),
        (r"\bwill graduate\b", "graduated"),
        (r"\bfinishing up my (" + d + r")\b", r"recently completed my \1"),
        (r"\bam finishing my (" + d + r")\b", r"recently completed my \1"),
    ]


def future_grad_regex(words):
    """The future-tense graduation phrases still wrong after the fixes, or None when no degree is finished."""
    if not words:
        return None
    d = _deg(words)
    return re.compile(
        r"\b(i (?:will )?finish(?:ing)? my " + d + r"|finishing (?:up )?my " + d + r"|about to (?:finish|graduate)"
        r"|i graduate(?! d)|graduating (?:in|this|next)|" + d + r" (?:candidate|student)|will be graduating"
        r"|expected (?:to )?graduat\w*|when i graduate|soon-to-be|upcoming graduation)\b", re.I)


SIGNOFF = re.compile(r"^(thanks|thank you|best|warm regards|regards|sincerely|cheers|all the best"
                     r"|looking forward|warmly)\b", re.I)


def name_line(names):
    """A line that is only your name (a stray signature the model added), or None with no names."""
    names = [n for n in (names or []) if n and n.strip()]
    if not names:
        return None
    return re.compile(r"^(" + "|".join(re.escape(n.strip()) for n in sorted(names, key=len, reverse=True)) + r")[.,!]?$", re.I)


def _undash(text):
    """Em and en dashes become commas. Tidy the seams so we never emit ',,' or a leading comma."""
    def sub(m):
        s, e = m.start(), m.end()
        # A numeric range (2019-2021) keeps meaning as a hyphen; a comma would wreck it.
        if "–" in m.group(0) and s and e < len(text) and text[s - 1].isdigit() and text[e].isdigit():
            return "-"
        if s == 0 or text[s - 1] == "\n" or e == len(text) or text[e] == "\n":
            return ""
        return ", "
    text = re.sub(r"[ \t]*[—–][ \t]*", sub, text)
    text = re.sub(r",[ \t]*(?:,[ \t]*)+", ", ", text)
    return re.sub(r"(?m)^[ \t]*,[ \t]*", "", text)


def _fix_tense(text, words=()):
    for pat, rep in tense_fixes(list(words)):
        text = re.sub(pat, rep, text, flags=re.I)
    return text


def _strip_signoff(paras, signer_names=()):
    """Drop trailing sign-off paragraphs. The mailer appends the real signature."""
    nl = name_line(signer_names)

    def named(x):
        return bool(nl and nl.match(x))

    def is_signoff(p):
        lines = [x.strip() for x in p.split("\n") if x.strip()]
        if lines and all(SIGNOFF.match(x) or named(x) for x in lines):
            return True
        return bool(lines) and bool(SIGNOFF.match(lines[0])) and all(
            named(x) or SIGNOFF.match(x) for x in lines[1:])
    while paras and is_signoff(paras[-1]):
        paras = paras[:-1]
    return paras


def _fail(problems):
    return {"ok": False, "problems": problems, "subject": "", "body": "", "dm": ""}


LINKEDIN_LINK = re.compile(r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/\S*", re.I)


def validate_and_clean(raw_text, first_name, mode, job_url, stop_reason=None, raw_title=None, job_id=None,
                       words=None, banned=(), signer_names=(), degree_words=()):
    """`first_name` is the recipient's. `words` (low, high) is the email body band, `banned` your never-use phrases,
    `signer_names` your name forms (a line holding only one is a stray sign-off), `degree_words` from degree_words()."""
    if stop_reason == "max_tokens":
        return _fail(["response truncated (hit max_tokens)"])
    if not raw_text or not raw_text.strip():
        return _fail(["empty model response"])
    stripped = re.sub(r"```json\n?", "", raw_text)
    stripped = re.sub(r"```\n?", "", stripped).strip()
    s, e = stripped.find("{"), stripped.rfind("}")
    try:
        parsed = json.loads(stripped[s:e + 1] if s != -1 and e != -1 else "")
    except ValueError as ex:
        return _fail(["invalid JSON: " + str(ex)[:60]])
    if not isinstance(parsed, dict):
        return _fail(["invalid JSON: not an object"])

    def field(k):
        v = parsed.get(k)
        return v.strip() if isinstance(v, str) else ""
    subject, body, dm = (_undash(field("email_subject")), _undash(field("email_body")),
                         _undash(field("linkedin_dm")))
    body, dm = _fix_tense(body, degree_words), _fix_tense(dm, degree_words)

    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    paras = _strip_signoff(paras, signer_names)
    body = "\n\n".join(paras)

    problems = []
    if not subject:
        problems.append("missing subject")
    first_line = (paras[0] if paras else "").split("\n")[0].strip()
    if not re.match(r"hi\s+\w+", first_line, re.I):
        problems.append("missing greeting line")
    elif first_name and not re.match(r"hi\s+" + re.escape(first_name) + r"(?!\w)", first_line, re.I):
        problems.append("greeting does not address " + first_name)
    if len(paras) < 2:
        problems.append("fewer than 2 paragraphs")
    lo, hi = tuple(words or EMAIL_WORDS)
    words = len(body.split()) - len(first_line.split())
    if words < lo - 10:
        problems.append(f"too short ({words} words after the greeting); write {lo} to {hi}")
    if words > hi + 15:
        problems.append(f"too long ({words} words after the greeting); write {lo} to {hi}")
    after_greeting = body.split("\n", 1)[1].strip() if "\n" in body else ""
    if OPENS_WITH_ASK.search(after_greeting):
        problems.append("opens with the ask; start with a warm line and who you are, and ask last")
    if mode == "Exploring":
        # Applied mode drops the call ask on purpose: only offer a call when the situation needs it.
        if not re.search(r"(call|coffee|chat|conversation|connect|speak|meet)", body, re.I):
            problems.append("no conversation ask")
    elif mode == "Applied":
        if not re.search(r"(resume|application|pass (it|my|along)|flag|forward|hiring team|internally)",
                         body, re.I):
            problems.append("no resume/application ask (Applied mode)")
        # The careers page link when there is one, else the job ID; never a LinkedIn link.
        if job_url and job_url not in body:
            problems.append("careers page link missing (Applied mode)")
        elif not job_url and job_id and str(job_id) not in body:
            problems.append(f"job ID {job_id} missing: name the role with its job ID, no link")
    if LINKEDIN_LINK.search(body):
        problems.append("contains a LinkedIn link; an email names the careers page or the job ID, never LinkedIn")
    everything = "\n".join((subject, body, dm))
    if META.search(everything):
        problems.append("meta-commentary/placeholder present")
    if AI_WORDS.search(everything):
        problems.append("AI-pattern word present")
    if ACTUALLY.search(everything):
        problems.append("uses 'actually'")
    for m in AI_PHRASES.finditer(everything):
        problems.append(f"AI-pattern phrasing: '{m.group(0)}' (rewrite that sentence as a plain statement, no reaction to the posting)")
    low = everything.lower()
    for b in banned or ():
        if b and b.lower() in low:
            problems.append(f"banned phrase (voice.md): '{b}'")
    # The posting's raw title ("(Senior) X, United States - Example Co") pasted in: people say the role plainly.
    if raw_title and raw_title.strip() and raw_title.strip() in everything and re.search(r"\s[-,|]\s|\(", raw_title):
        problems.append("pastes the posting's raw title; name the role the way a person would")
    fg = future_grad_regex(list(degree_words))
    if fg and fg.search(everything):
        problems.append("future-tense graduation")
    if not dm:
        problems.append("missing linkedin_dm")
    elif len(dm.split()) > 55:
        problems.append("linkedin_dm too long")
    return {"ok": not problems, "problems": problems, "subject": subject, "body": body, "dm": dm}


def _next_weekday(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def next_send_slot(now, scheduled, sent_counts, rng, window=(8, 18), gap=(20, 40), daily_cap=10,
                   tz="America/New_York"):
    zone = ZoneInfo(tz)
    now = now.astimezone(zone)
    sched = [s.astimezone(zone) for s in scheduled]
    open_t, close_t = time(window[0]), time(window[1])

    def plus(dt, minutes):
        # Add in UTC: wall-clock arithmetic on a zoneinfo datetime would ignore a DST jump.
        return (dt.astimezone(timezone.utc) + timedelta(minutes=minutes)).astimezone(zone)

    def in_window(dt):
        return dt.weekday() < 5 and open_t <= dt.time() < close_t

    def morning(day):
        # Not always on the hour, so the first send of a day does not look scripted.
        return plus(datetime.combine(day, open_t, tzinfo=zone), rng.randint(0, 15))

    if not sched and in_window(now):
        cand = plus(now, rng.randint(1, 5))
    else:
        cand = plus(max([now] + sched), rng.randint(*gap))

    while True:
        if not in_window(cand):
            # Before opening on a weekday is still that day; anything else waits for the next weekday.
            if cand.weekday() < 5 and cand.time() < open_t:
                cand = morning(cand.date())
            else:
                cand = morning(_next_weekday(cand.date()))
            continue
        day = cand.date()
        used = sent_counts.get(day, 0) + sum(1 for s in sched if s.date() == day)
        if used >= daily_cap:
            cand = morning(_next_weekday(day))
            continue
        return cand
