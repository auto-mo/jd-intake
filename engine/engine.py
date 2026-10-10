#!/usr/bin/env python3
"""Deterministic resume engine: render, measure, fit, check. No model inside.

The model's only job is the words. Everything that can be code is code:

  render(content, docx, layout)  content dict -> .docx through template.docx, same XML as build.py
  convert(docx)                  .docx -> .pdf through LibreOffice (about a second)
  measure(pdf, content)          pages, trailing whitespace, and per bullet: lines, last-line
                                 fill, orphan, characters to add or cut
  fit(content, docx)             render/convert/measure in a loop, moving only layout knobs
                                 (line spacing, gaps, section spacing) until the page is one
                                 page and 92 to 98 percent full; when the knobs run out it
                                 says exactly which bullets need how many characters
  check(content, sources)        em dashes, banned phrases, role order, repeated bullets and
                                 headings, and every number in a bullet traced to profile.md,
                                 ANSWERS or the base version

Everything personal (name, links, role order, finished degrees, banned phrases, base versions)
comes from the profile through server/userprofile.py, read fresh on every call.

Content shape (same as userprofile.base_versions()[key]["content"]):
  {"education": [[school, date, city, [lines]]], "experience": [[company, role, date, [bullets]]],
   "skills_title": str, "skills": [[label, text]], "projects": [[label, text]]}

Usage from the command line, for a look at any content.json:
  python3 engine.py fit content.json /path/to/Your_Name_Company.docx
  python3 engine.py dups file.docx|content.json ...    repeated bullets or headings (exit 2 if any)
  python3 engine.py base <version>                      a base version as content JSON
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build as g  # noqa: E402  (XML helpers, the template path, the profile hookup)
up = g.up          # server/userprofile.py

PAGE_H = 792.0
MARGIN = 28.35                       # 567 DXA
LEFT, RIGHT = MARGIN, 612 - MARGIN
WIDTH = RIGHT - LEFT
BOTTOM = PAGE_H - MARGIN

# Trailing whitespace after the last baseline, in inches. A 92 to 98 percent fill on a 10.2 in
# text column is roughly 0.2 to 0.8 in; pages that read as full sit under 0.40, so that is the
# ceiling, and 0.06 keeps a safety line above the margin.
TRAIL_MIN, TRAIL_MAX = 0.06, 0.40

# Layout knobs and their ranges. DEFAULT is what build.py has always produced; t moves every
# knob together from TIGHT (t=0) through DEFAULT to LOOSE (t=1), so a fit is one number.
TIGHT = {"line": 216, "gap": 0, "section_before": 80, "section_after": 40, "bullet_after": 0, "edu_after": 20}
DEFAULT = {"line": 230, "gap": 8, "section_before": 120, "section_after": 60, "bullet_after": 0, "edu_after": 40}
LOOSE = {"line": 262, "gap": 20, "section_before": 200, "section_after": 100, "bullet_after": 40, "edu_after": 80}
T_DEFAULT = 0.5

# Future-tense graduation language is a defect once a degree is finished (profile `degrees` with
# completed: true). These generic phrases plus "<degree> candidate/student" per finished degree.
FUTURE_GRAD_GENERIC = [
    "expected graduation", "expected to graduate", "graduating in", "graduating this",
    "will graduate", "degree expected", "anticipated graduation", "currently pursuing",
]

# Phrases that read as generated filler on any resume. The profile's voice.md adds its own list.
BANNED_GENERIC = [
    "rare combination", "throughline", "sits at the center of", "sits at the intersection of",
    "precisely what", "is not abstract to me", "i keep coming back to", "what makes my work different",
]


def banned_phrases():
    """Generic banned phrases plus the bullets under voice.md's "Banned phrases" heading, lowercase."""
    out = list(BANNED_GENERIC)
    on = False
    for line in up.read_text("voice.md").splitlines():
        if line.lstrip().startswith("#"):
            on = "banned phrases" in line.lower()
            continue
        m = re.match(r"\s*[-*]\s+(.+)", line)
        if on and m:
            ph = m.group(1).strip()
            # a quoted phrase, maybe with a note after it; an apostrophe inside double quotes stays
            q = re.match(r'^["\u201c](.+?)["\u201d]', ph) or re.match(r"^'(.+?)'(?:\s|$)", ph)
            ph = (q.group(1) if q else ph).strip().strip(".").lower()
            if ph and ph not in out:
                out.append(ph)
    return out


def future_grad_phrases():
    """[] when no degree is finished; otherwise the generic list plus "<abbr> candidate/student"."""
    done = up.completed_degrees()
    if not done:
        return []
    out = list(FUTURE_GRAD_GENERIC)
    for d in done:
        first = (d.get("name") or "").split()[:1]
        if first and len(first[0]) <= 5:              # MBA, MS, MSc, PhD, BA ...
            out += [f"{first[0].lower()} candidate", f"{first[0].lower()} student"]
    return list(dict.fromkeys(out))


def role_order():
    """Employers newest first (profile `experience_order`); empty means the order is not checked."""
    return list(up.get().get("experience_order") or [])


def bullets_per_role():
    lo, hi = (up.get().get("resume") or {}).get("bullets_per_role") or [1, 4]
    return int(lo), int(hi)


def builds_title():
    return (up.get().get("resume") or {}).get("builds_title") or "SELECTED PROJECTS"


# ── layout ───────────────────────────────────────────────────────────────────

def layout_at(t):
    """Interpolate the knobs: t in [0, 0.5] runs TIGHT to DEFAULT, [0.5, 1] DEFAULT to LOOSE."""
    t = max(0.0, min(1.0, t))
    out = {}
    for k in DEFAULT:
        if t <= 0.5:
            a, b, u = TIGHT[k], DEFAULT[k], t / 0.5
        else:
            a, b, u = DEFAULT[k], LOOSE[k], (t - 0.5) / 0.5
        out[k] = int(round(a + (b - a) * u))
    return out


def _section(title, lay):
    return ('<w:p><w:pPr><w:pBdr>'
            '<w:bottom w:val="single" w:color="000000" w:sz="6" w:space="1"/>'
            f'</w:pBdr><w:spacing w:after="{lay["section_after"]}" w:before="{lay["section_before"]}"/>'
            '<w:jc w:val="center"/></w:pPr>' + g.run(title, bold=True) + "</w:p>")


def _para_pr(lay, justify=True, numbered=True):
    pr = "<w:pPr>"
    if numbered:
        pr += '<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>'
    pr += f'<w:spacing w:after="{lay["bullet_after"]}" w:line="{lay["line"]}" w:lineRule="auto"/>'
    if justify:
        pr += '<w:jc w:val="both"/>'
    return pr + "</w:pPr>"


def _run(text, bold=False, condense=0):
    """build.py's run, plus optional character condensing in twentieths of a point (a
    typesetter's orphan fix: -6 is 0.3 pt tighter per character, invisible on the page)."""
    r = g.run(text, bold=bold)
    if condense:
        r = r.replace("<w:rPr>", f'<w:rPr><w:spacing w:val="{int(condense)}"/>', 1)
    return r


def _bullet(text, lay, label=None, condense=0):
    runs = (_run(label, bold=True, condense=condense) if label else "") + _run(text, condense=condense)
    return "<w:p>" + _para_pr(lay) + runs + "</w:p>"


def _skill_line(label, text, lay, condense=0):
    return ("<w:p>" + _para_pr(lay, numbered=False) + _run(label, bold=True, condense=condense)
            + _run(text, condense=condense) + "</w:p>")


def _gap(lay):
    if lay["gap"] <= 0:
        return ""
    return (f'<w:p><w:pPr><w:spacing w:after="0"/><w:rPr><w:sz w:val="{lay["gap"]}"/>'
            '</w:rPr></w:pPr></w:p>')


def body_xml(c, lay):
    cond = lay.get("condense") or {}          # {"r<role>b<index>" | "p<index>" | "s<index>": twips}
    p = [g.name_line(), g.contact_line(), _section("EDUCATION", lay)]
    for school, date, city, lines in c["education"]:
        p.append(g.tabbed(school, date))
        p.append(g.plain(city))
        for i, l in enumerate(lines):
            p.append(g.plain(l, after=lay["edu_after"] if i == len(lines) - 1 else 0))
    builds = c.get("builds") or {}
    if builds.get("items"):
        # A builds section above EXPERIENCE, only when the content carries one (useful when a
        # posting screens hard on hands-on work). Same bullet geometry as projects.
        p.append(_section(builds.get("title") or builds_title(), lay))
        for bi, (label, text) in enumerate(builds["items"]):
            p.append(_bullet(text, lay, label=label or None, condense=cond.get(f"b{bi}", 0)))
    p.append(_section("EXPERIENCE", lay))
    for ri, (company, role, date, bullets) in enumerate(c["experience"]):
        p.append(g.plain(company, bold=True))
        p.append(g.tabbed(role, date, indent=180))
        for bi, b in enumerate(bullets):
            p.append(_bullet(b, lay, condense=cond.get(f"r{ri}b{bi}", 0)))
        p.append(_gap(lay))
    p.append(_section(c.get("skills_title") or "SKILLS & PROJECTS", lay))
    for si, (label, text) in enumerate(c.get("skills") or []):
        p.append(_skill_line(label, text, lay, condense=cond.get(f"s{si}", 0)))
    if c.get("projects"):
        p.append(g.plain("Projects:", bold=True))
        for pi, (label, text) in enumerate(c["projects"]):
            p.append(_bullet(text, lay, label=label or None, condense=cond.get(f"p{pi}", 0)))
    return "".join(p)


def render(content, out_docx, layout=None):
    lay = layout or layout_at(T_DEFAULT)
    return g.write_docx(body_xml(content, lay), out_docx)


# LibreOffice shares one user profile, so two conversions at once trip over each other. Builds
# run in parallel; only this two-second step queues. The thread lock covers one process; the
# file lock covers all of them (the server, a dev copy, the test suites), since a test run and a
# live build converting at the same moment is exactly where collisions come from.
_convert_lock = threading.Lock()
_CONVERT_LOCKFILE = os.path.join(tempfile.gettempdir(), "jd-intake", "soffice.lock")


def convert(docx):
    import fcntl
    out_dir = os.path.dirname(os.path.abspath(docx))
    pdf = docx[:-5] + ".pdf"
    if os.path.exists(pdf):
        os.remove(pdf)
    os.makedirs(os.path.dirname(_CONVERT_LOCKFILE), exist_ok=True)
    with _convert_lock, open(_CONVERT_LOCKFILE, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        for attempt in range(2):          # local and free, so one retry is fine
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, docx],
                           capture_output=True, text=True, timeout=180)
            if os.path.exists(pdf):
                break
            time.sleep(1.5)
    if not os.path.exists(pdf):
        raise RuntimeError("LibreOffice produced no PDF")
    return pdf


def rasterize(pdf):
    folder = os.path.dirname(os.path.abspath(pdf))
    subprocess.run(["pdftoppm", "-jpeg", "-r", "100", "-f", "1", "-l", "1", pdf, os.path.join(folder, "page")],
                   capture_output=True, timeout=60)
    return os.path.join(folder, "page-1.jpg")


# ── measure ──────────────────────────────────────────────────────────────────

def _lines(pdf):
    xml = subprocess.run(["pdftotext", "-bbox-layout", pdf, "-"], capture_output=True, text=True).stdout
    pages = xml.count("<page ")
    lines = []
    for pm in re.finditer(r'<page [^>]*>(.*?)</page>', xml, re.S):
        for lm in re.finditer(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>',
                              pm.group(1), re.S):
            xmin, ymin, xmax, ymax, inner = lm.groups()
            words = re.findall(r'>([^<]*)</word>', inner)
            txt = " ".join(words).replace("&apos;", "'").replace("&amp;", "&").replace("&quot;", '"')
            lines.append({"xmin": float(xmin), "xmax": float(xmax), "y": float(ymin), "text": txt,
                          "words": len(words), "page": pm.start()})
    # number pages in order of appearance
    starts = sorted({l["page"] for l in lines})
    for l in lines:
        l["page"] = starts.index(l["page"]) + 1
    lines.sort(key=lambda l: (l["page"], l["y"]))
    return pages, lines


def measure(pdf, content):
    """Return {"pages", "trailing_in", "fill_pct", "bullets": [...], "orphans": [...]}.

    A bullet group starts at a line with the bullet glyph and continues while lines start at
    the hanging indent (build.py indents bullet text 180 DXA, about 9 pt). Mapping to the
    content is by order: experience bullets first, then projects, which is the order the page
    is written in."""
    pages, lines = _lines(pdf)
    page1 = [l for l in lines if l["page"] == 1]
    last_y = max((l["y"] for l in page1), default=0.0)
    trailing_in = (BOTTOM - last_y) / 72.0
    groups, cur = [], None
    for l in page1:
        if l["text"].startswith("• ") or l["text"] == "•":
            if cur:
                groups.append(cur)
            cur = [l]
        elif cur is not None and LEFT + 4 < l["xmin"] < LEFT + 20:
            cur.append(l)
        elif cur is not None:
            groups.append(cur)
            cur = None
    if cur:
        groups.append(cur)

    src = [(-3, bi, (lbl or "") + t) for bi, (lbl, t) in enumerate((content.get("builds") or {}).get("items") or [])]
    src += [(ci, bi, b) for ci, (_, _, _, bs) in enumerate(content["experience"]) for bi, b in enumerate(bs)]
    src += [(-1, pi, (lbl or "") + t) for pi, (lbl, t) in enumerate(content.get("projects") or [])]
    bullets, orphans = [], []
    for i, grp in enumerate(groups):
        if i >= len(src):
            break
        ci, bi, text = src[i]
        n = len(grp)
        last = grp[-1]
        last_fill = (last["xmax"] - LEFT) / WIDTH * 100
        l1 = max(len(grp[0]["text"]) - 2, 1)
        chars_per_line = l1 if n > 1 else max(len(text), 1)
        # Characters to add (+) to fill the last line to ~97 percent, or to cut (-) so the
        # last line disappears into the one above. Both are estimates from the first line's
        # character count, which is what the fitted text will look like.
        if n == 1:
            delta_fill = round(chars_per_line * (97 - last_fill) / 100) if last_fill < 90 else 0
            delta_cut = 0
        else:
            delta_fill = round(chars_per_line * (97 - last_fill) / 100)
            delta_cut = -round(chars_per_line * last_fill / 100) - 4
        orphan = n > 1 and (last["words"] <= 1 or last_fill < 12)
        row = {"role": ci, "index": bi, "lines": n, "last_fill": round(last_fill, 1),
               "chars": len(text), "add_to_fill": delta_fill, "cut_to_drop_line": delta_cut,
               "orphan": orphan, "text": text}
        bullets.append(row)
        if orphan:
            orphans.append(row)
    # Skills lines are plain paragraphs at the left margin, so a continuation line looks like a
    # new paragraph to the grouping above. Find each by its bold label instead and follow the
    # text: a line is a continuation while its words are the tail of the skill's own text.
    skills = []
    for si, (lbl, text) in enumerate(content.get("skills") or []):
        full = ((lbl or "") + text).replace("  ", " ")
        start = next((k for k, l in enumerate(page1) if l["text"].startswith((lbl or "").strip()[:18])), None)
        if start is None:
            continue
        grp = [page1[start]]
        k = start + 1
        while k < len(page1) and page1[k]["xmin"] < LEFT + 4 and page1[k]["text"] and page1[k]["text"] in full \
                and not any(page1[k]["text"].startswith((l2 or "").strip()[:18]) for l2, _ in content["skills"] if l2):
            grp.append(page1[k])
            k += 1
        n = len(grp)
        last = grp[-1]
        last_fill = (last["xmax"] - LEFT) / WIDTH * 100
        cpl = max(len(grp[0]["text"]), 1)
        row = {"role": -2, "index": si, "lines": n, "last_fill": round(last_fill, 1), "chars": len(full),
               "add_to_fill": round(cpl * (97 - last_fill) / 100) if (n == 1 and last_fill < 90) or n > 1 else 0,
               "cut_to_drop_line": (-round(cpl * last_fill / 100) - 4) if n > 1 else 0,
               "orphan": n > 1 and (last["words"] <= 1 or last_fill < 12), "text": full}
        skills.append(row)
        if row["orphan"]:
            orphans.append(row)
    text_h = BOTTOM - MARGIN
    fill_pct = round((last_y - MARGIN) / text_h * 100, 1) if page1 else 0.0
    line_h_in = 11.5 / 72.0                                   # one 10 pt line at the default spacing
    lines_over = len([l for l in lines if l["page"] > 1])
    lines_under = int((trailing_in - TRAIL_MAX) / line_h_in) if trailing_in > TRAIL_MAX else 0
    return {"pages": pages, "trailing_in": round(trailing_in, 2), "fill_pct": fill_pct,
            "bullets": bullets + skills, "orphans": orphans, "groups_seen": len(groups), "bullets_expected": len(src),
            "lines_over": lines_over, "lines_under": lines_under}


# ── fit ──────────────────────────────────────────────────────────────────────

def fit(content, out_docx, log=None):
    """Find the loosest layout that keeps one page with trailing whitespace in range.

    Returns {"ok", "t", "layout", "measure", "pdf", "docx", "verdict", "renders"}.
    verdict: "fit" | "over" (one page impossible even at TIGHT: cut) | "under" (page not full
    even at LOOSE: add) | "orphans" (fits, but a bullet still ends on a lone word).

    Two passes: the layout search, then, if a bullet ends on a lone word, the same search with
    that bullet's characters condensed a fraction of a point (a typesetter's fix, invisible on
    the page), which pulls the word up without a model round."""
    say = log or (lambda *_: None)
    state = {"renders": 0, "last_t": None}

    def attempt(t, condense):
        state["renders"] += 1
        state["last_t"] = t
        lay = layout_at(t)
        if condense:
            lay["condense"] = dict(condense)
        render(content, out_docx, lay)
        pdf = convert(out_docx)
        m = measure(pdf, content)
        say(f"t={t:.3f} cond={len(condense or {})} pages={m['pages']} trailing={m['trailing_in']} fill={m['fill_pct']}")
        return lay, pdf, m

    def ok(m):
        return m["pages"] == 1 and m["trailing_in"] >= TRAIL_MIN

    def in_range(m):
        return ok(m) and m["trailing_in"] <= TRAIL_MAX

    def trail(m):
        # a second page reads as negative trailing space, so interpolation still has a slope
        return m["trailing_in"] if m["pages"] == 1 else -0.3

    def search(condense):
        """Two or three renders in the common case: measure at the default, aim a guess by
        linear interpolation at 0.2 in of trailing space, then bisect only if the guess misses."""
        lay, pdf, m = attempt(T_DEFAULT, condense)
        if in_range(m):
            return lay, pdf, m, T_DEFAULT
        if ok(m):                                   # too much white: loosen
            lo, mlo = T_DEFAULT, m
            lay, pdf, m = attempt(1.0, condense)
            if in_range(m):
                return lay, pdf, m, 1.0
            if ok(m) and m["trailing_in"] > TRAIL_MAX:
                return lay, pdf, m, 1.0             # still under at the loosest: "under"
            hi, mhi = 1.0, m
        else:                                       # over: tighten
            hi, mhi = T_DEFAULT, m
            lay, pdf, m = attempt(0.0, condense)
            if not ok(m):
                return lay, pdf, m, 0.0             # over even at the tightest: "over"
            if in_range(m):
                return lay, pdf, m, 0.0
            lo, mlo = 0.0, m
        best = None
        for _ in range(4):
            d_lo, d_hi = trail(mlo), trail(mhi)
            if d_lo > d_hi + 0.05:
                guess = lo + (hi - lo) * (d_lo - 0.2) / (d_lo - d_hi)
                guess = min(max(guess, lo + 0.02), hi - 0.02)
            else:
                guess = (lo + hi) / 2
            lay, pdf, m = attempt(guess, condense)
            if in_range(m):
                return lay, pdf, m, guess
            if ok(m):
                lo, mlo, best = guess, m, (lay, pdf, m, guess)
            else:
                hi, mhi = guess, m
        if best is None:
            lay, pdf, m = attempt(lo, condense)
            best = (lay, pdf, m, lo)
        lay, pdf, m, t = best
        if state["last_t"] != t:
            lay, pdf, m = attempt(t, condense)
        return lay, pdf, m, t

    lay, pdf, m, t = search(None)
    condense = {}
    if m["pages"] == 1 and m["orphans"]:
        # Find the mildest condensing that clears every orphan at this t, then search again
        # with it, since freed lines change where the page fills.
        for level in (-3, -6, -9, -12):
            for row in m["orphans"]:
                condense[_key(row)] = level
            lay2, pdf2, m2 = attempt(t, condense)
            if not m2["orphans"] or m2["pages"] > 1:
                break
        if condense:
            # Usually the freed lines still leave the page in range at the same t (one render);
            # only search again when they do not.
            lay, pdf, m = attempt(t, condense)
            if not (m["pages"] == 1 and TRAIL_MIN <= m["trailing_in"] <= TRAIL_MAX):
                lay, pdf, m, t = search(condense)
    if m["pages"] > 1 or (m["trailing_in"] < TRAIL_MIN and t == 0.0):
        verdict = "over"
    elif m["trailing_in"] > TRAIL_MAX:
        verdict = "under"
    elif m["orphans"]:
        verdict = "orphans"
    else:
        verdict = "fit"
    return {"ok": verdict == "fit", "verdict": verdict, "t": round(t, 3), "layout": lay, "measure": m,
            "pdf": pdf, "docx": out_docx, "renders": state["renders"]}


def _key(row):
    return ("p%d" % row["index"] if row["role"] == -1 else "s%d" % row["index"] if row["role"] == -2
            else "b%d" % row["index"] if row["role"] == -3 else "r%db%d" % (row["role"], row["index"]))


# ── duplicates ───────────────────────────────────────────────────────────────
#
# A model's edits can leave the same bullet on the page twice (for example, replacing indices 0 to 3
# of a five-item section while index 4 still says the same thing). Fit, page count, fill and
# orphans cannot see this: a repeated bullet is just another bullet.
#
# Thresholds were tuned on about a hundred real built resumes: every pair at or above 0.50 was the
# same system or claim stated twice (0.8 caught only half of them, even with the six-word rule),
# while legitimate neighbours, such as two bullets in one role that share a list of functions,
# score 0.24 to 0.29. Words are lowercased, punctuation is dropped and stop words are ignored, so a
# changed label, colon or period does not hide a repeat.

DUP_STOP = frozenset(
    "a an the and or of to in on for with by at as is are was were that this these those it its from into "
    "across over under my own all than then also their his her".split())
DUP_HEAD_WORDS = 6        # two bullets that open with the same six words are one bullet
DUP_FAIL = 0.50           # content-word Jaccard at or above this fails the build
DUP_WARN = 0.40           # at or above this (bullets only) is listed as a warning for a look
DUP_MIN_WORDS = 4         # fewer content words than this and similarity says nothing
DUP_SKILL_FAIL = 0.80     # skills lines are comma lists that overlap by nature; same label fails separately


def _words(s):
    return re.sub(r"[^a-z0-9€£¥%$~+]+", " ", (s or "").lower().replace("&", " and ")).split()


def _content_words(s):
    return [w for w in _words(s) if w not in DUP_STOP]


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else 0.0


def duplicate_pairs(rows):
    """rows: [(where, label, text, kind)] with kind "bullet" or "skill". A skills line is compared with
    every row (the model has put skills-style lines under Projects); bullets are compared with bullets by
    wording. Returns one dict per repeated pair: {"a", "b", "why", "score", "hard", "a_text", "b_text"}. Hard pairs fail a
    build; soft pairs (bullets only) are worth a look."""
    out = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            wa_, la, ta, ka = rows[i]
            wb_, lb, tb, kb = rows[j]
            fa, fb = (la or "") + ta, (lb or "") + tb
            wa, wb = _words(fa), _words(fb)
            if not wa or not wb:
                continue
            ca, cb = _content_words(fa), _content_words(fb)
            score = _jaccard(ca, cb) if min(len(set(ca)), len(set(cb))) >= DUP_MIN_WORDS else 0.0
            why, hard = None, False
            if wa == wb:
                why, hard = "are identical", True
            elif "skill" in (ka, kb):        # a skills line, or a skills-style line that landed under Projects
                na, nb = " ".join(_words(la)), " ".join(_words(lb))
                if na and na == nb:
                    why, hard = "carry the same label", True
                elif score >= DUP_SKILL_FAIL:
                    why, hard = f"overlap {score:.2f}", True
            else:
                if len(wa) >= DUP_HEAD_WORDS and len(wb) >= DUP_HEAD_WORDS and wa[:DUP_HEAD_WORDS] == wb[:DUP_HEAD_WORDS]:
                    why, hard = f"open with the same {DUP_HEAD_WORDS} words", True
                elif score >= DUP_FAIL:
                    why, hard = f"overlap {score:.2f}", True
                elif score >= DUP_WARN:
                    why, hard = f"overlap {score:.2f}", False
            if why:
                out.append({"a": wa_, "b": wb_, "why": why, "score": round(score, 2), "hard": hard,
                            "a_text": fa.strip(), "b_text": fb.strip()})
    return out


def _content_rows(c):
    rows = []
    for bi, (lbl, t) in enumerate((c.get("builds") or {}).get("items") or []):
        rows.append((f"builds item [{bi}]", lbl, t, "bullet"))
    for company, _, _, bs in c["experience"]:
        for bi, b in enumerate(bs):
            rows.append((f"{company} bullet [{bi}]", "", b, "bullet"))
    for pi, (lbl, t) in enumerate(c.get("projects") or []):
        rows.append((f"project [{pi}]", lbl, t, "bullet"))
    for si, (lbl, t) in enumerate(c.get("skills") or []):
        rows.append((f"skills line [{si}]", lbl, t, "skill"))
    return rows


def duplicate_headings(headings):
    """headings: list of heading strings as they appear on the page. Returns the repeated ones."""
    seen, dup = set(), []
    for h in headings:
        k = " ".join(_words(h))
        if not k:
            continue
        if k in seen and h not in dup:
            dup.append(h)
        seen.add(k)
    return dup


def find_duplicates(c):
    """Repeated bullets, skills lines, section headings, roles and schools in a content dict.
    Returns {"hard": [...], "soft": [...], "headings": [...]}; "hard" and "headings" fail a build."""
    pairs = duplicate_pairs(_content_rows(c))
    b = c.get("builds") or {}
    heads = ["EDUCATION", b.get("title") or builds_title() if b.get("items") else "", "EXPERIENCE",
             c.get("skills_title") or "SKILLS & PROJECTS"]
    problems = [f"section heading \"{h}\" appears more than once" for h in duplicate_headings(heads)]
    for what, names in (("role", [r[0] for r in c["experience"]]), ("school", [e[0] for e in c["education"]])):
        for n in duplicate_headings(names):
            problems.append(f"{what} \"{n}\" appears more than once")
    return {"hard": [p for p in pairs if p["hard"]], "soft": [p for p in pairs if not p["hard"]],
            "headings": problems}


def describe_duplicate(p):
    return f"{p['a']} and {p['b']} {p['why']}: \"{p['a_text'][:70]}\" / \"{p['b_text'][:70]}\""


def docx_rows(path):
    """Rows and headings of a finished .docx, read from its XML (the file that was submitted, not
    the content dict). Returns (rows, headings) in the shapes duplicate_pairs and
    duplicate_headings take. Role and date lines (they carry a tab) and short fragments are skipped."""
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    rows, heads, n = [], [], 0
    for p in root.iter(ns + "p"):
        ppr = p.find(ns + "pPr")
        numbered = ppr is not None and ppr.find(ns + "numPr") is not None
        heading = ppr is not None and ppr.find(ns + "pBdr") is not None
        runs = []
        for r in p.iter(ns + "r"):
            rpr = r.find(ns + "rPr")
            bold = rpr is not None and rpr.find(ns + "b") is not None
            runs.append((bold, "".join(t.text or "" for t in r.iter(ns + "t")), r.find(ns + "tab") is not None))
        text = "".join(t for _, t, _ in runs)
        if heading:
            heads.append(text.strip())
            continue
        if not text.strip() or any(tab for _, _, tab in runs) or len(_words(text)) < 5:
            continue
        label = ""
        for bold, t, _ in runs:
            if not bold:
                break
            label += t
        rest = text[len(label):]
        n += 1
        if numbered:
            rows.append((f"bullet {n}", label, rest, "bullet"))
        elif label.strip() and rest.strip():
            rows.append((f"skills line {n}", label, rest, "skill"))
    return rows, heads


def audit_docx(path):
    """find_duplicates for a finished .docx. Same return shape as find_duplicates."""
    rows, heads = docx_rows(path)
    pairs = duplicate_pairs(rows)
    return {"hard": [p for p in pairs if p["hard"]], "soft": [p for p in pairs if not p["hard"]],
            "headings": [f"section heading \"{h}\" appears more than once" for h in duplicate_headings(heads)]}


# ── check ────────────────────────────────────────────────────────────────────

_NUM =re.compile(r"(?<![\w.])(?:[$€£¥]\s?)?\d[\d,]*(?:\.\d+)?\s?(?:%|[KkMmLl]\+?|\+)?(?![\w])")


def _numbers(text):
    out = set()
    for m in _NUM.finditer(text):
        tok = m.group(0).replace(",", "").replace(" ", "").lower().rstrip("+")
        tok = re.sub(r"^[$€£¥]", "", tok)
        if re.fullmatch(r"(19|20)\d\d", tok):
            continue                      # years are dates, not claims
        out.add(tok)
    return out


def check(content, sources):
    """sources: list of texts every number must be found in (profile, answers, base version).
    Returns {"ok", "problems": [...], "unverified_numbers": [...], "warnings": [...]}."""
    problems, warnings = [], []
    texts = []
    for _, _, _, bs in content["experience"]:
        texts += bs
    texts += [(lbl or "") + t for lbl, t in (content.get("builds") or {}).get("items") or []]
    texts += [(lbl or "") + t for lbl, t in content.get("projects") or []]
    texts += [(lbl or "") + t for lbl, t in content.get("skills") or []]
    joined = "\n".join(texts)
    if "—" in joined:
        problems.append("em dash in body text")
    low = joined.lower()
    for b in banned_phrases():
        if b in low:
            problems.append(f"banned phrase: {b}")
    done = ", ".join(d.get("name") or "degree" for d in up.completed_degrees())
    for ph in future_grad_phrases():
        if ph in low:
            problems.append(f"finished, not in progress ({done}): \"{ph}\"")
    order_ref = role_order()
    companies = [c for c, _, _, _ in content["experience"]]
    if order_ref:
        known = [c for c in companies if c in order_ref]
        if known != [c for c in order_ref if c in known]:
            problems.append("roles out of reverse chronological order: " + " > ".join(companies))
        missing = [c for c in order_ref if c not in companies]
        if missing:
            msg = "roles missing: " + ", ".join(missing)
            (problems if up.get().get("keep_every_role", True) else warnings).append(msg)
    lo, hi = bullets_per_role()
    for c, _, _, bs in content["experience"]:
        if not lo <= len(bs) <= hi:
            problems.append(f"{c}: {len(bs)} bullets (allowed {lo} to {hi})")
    dups = find_duplicates(content)
    problems += ["duplicate content, delete or merge one: " + describe_duplicate(p) for p in dups["hard"]]
    problems += dups["headings"]
    warnings += ["similar items, check they are not the same claim twice: " + describe_duplicate(p) for p in dups["soft"]]
    pool =" ".join(sources).lower().replace(",", "")
    pool_nums = _numbers(pool)
    unverified = []
    for t in texts[: sum(len(bs) for _, _, _, bs in content["experience"]) + len(content.get("projects") or [])]:
        for n in _numbers(t):
            core = n.rstrip("%kml")
            if n not in pool_nums and core not in pool_nums and core not in pool:
                unverified.append({"number": n, "text": t[:80]})
    return {"ok": not problems, "problems": problems, "warnings": warnings, "unverified_numbers": unverified}


# ── content helpers ──────────────────────────────────────────────────────────

def content_from_base(version=None):
    """A base version from the profile's base_versions.yaml as a fresh content dict. None or an
    unknown key gives the profile's default version."""
    versions = up.base_versions()
    if not versions:
        raise KeyError("no base versions in the profile: run onboarding to write base_versions.yaml")
    key = str(version) if version is not None and str(version) in versions else up.default_version()
    v = versions.get(key) or next(iter(versions.values()))
    v = v["content"]

    def labelled(rows):
        return [[_base_label(lbl), t] for lbl, t in rows]
    return {"education": [list(e) for e in v["education"]],
            "experience": [[c, r, d, list(bs)] for c, r, d, bs in v["experience"]],
            "builds": ({"title": v["builds"]["title"],
                        "items": labelled(v["builds"]["items"])} if (v.get("builds") or {}).get("items") else None),
            "skills_title": v.get("skills_title") or "SKILLS", "skills": labelled(v.get("skills") or []),
            "projects": labelled(v.get("projects") or [])}


def _base_label(s):
    """A label as typed in base_versions.yaml -> as printed: "Tools" -> "Tools: ", "Model." -> "Model. ".
    The label and the text are separate runs, so without this they print joined."""
    s = s or ""
    if not s.strip() or s[-1].isspace():
        return s
    return s + (": " if s[-1].isalnum() or s[-1] == ")" else " ")


def apply_edits(content, out):
    """Apply an edits-only answer onto the current content, in place on a copy. Each bullet edit
    names the company and the bullet's index in the current list; an index past the end appends,
    an empty text deletes. Skills and projects edit the same way by index. Education, company
    names, titles and dates never change."""
    c = json.loads(json.dumps(content))
    roles = {r[0].strip().lower(): r for r in c["experience"]}
    per = {}
    for e in out.get("bullet_edits") or []:
        role = roles.get((e.get("company") or "").strip().lower())
        if role is None:
            continue
        per.setdefault(id(role), (role, []))[1].append((int(e.get("index", len(role[3]))), strip_dashes(e.get("text") or "")))
    for role, edits in per.values():
        bs = list(role[3])
        appends = []
        for i, text in edits:
            if i < len(bs):
                bs[i] = text                      # replace, or delete when empty
            elif text.strip():
                appends.append(text)              # every append lands, in the order given
        role[3] = [b for b in bs if b and b.strip()] + appends

    def edit_list(items, edits, with_label=True):
        items = [list(x) for x in items]
        appends = []
        for e in edits:
            i = int(e.get("index", len(items)))
            label = _label(e.get("label")) if with_label else ""
            text = strip_dashes(e.get("text") or "").strip()
            bare = label.strip().rstrip(":").strip().lower()
            if bare and text.lower().startswith(bare):       # the model repeated the label inside the text
                text = text[len(bare):].lstrip(" :").strip()
            row = [label, text]
            if i < len(items):
                items[i] = row
            elif row[1].strip():
                appends.append(row)
        return [x for x in items if x[1] and x[1].strip()] + appends
    if out.get("build_edits") or out.get("builds_title"):
        b = c.get("builds") or {"title": "", "items": []}
        b["items"] = edit_list(b.get("items") or [], out.get("build_edits") or [])
        if out.get("builds_title"):
            b["title"] = strip_dashes(out["builds_title"]).strip().upper()
        c["builds"] = b if b["items"] else None
    if out.get("skill_edits"):
        c["skills"] = edit_list(c.get("skills") or [], out["skill_edits"])
    if out.get("project_edits"):
        c["projects"] = edit_list(c.get("projects") or [], out["project_edits"])
    if out.get("skills_title"):
        c["skills_title"] = strip_dashes(out["skills_title"])
    return c


def content_listing(c):
    """The content as the model should see it: every bullet with its company and index."""
    lines = []
    b = c.get("builds") or {}
    lines.append(f"Builds section above Experience ({b.get('title') or 'none yet'}):")
    for i, (lbl, t) in enumerate(b.get("items") or []):
        lines.append(f"  [{i}] {lbl}{t}")
    if not b.get("items"):
        lines.append("  (none)")
    for company, role, date, bs in c["experience"]:
        lines.append(f"{company} ({role}, {date}):")
        for i, b in enumerate(bs):
            lines.append(f"  [{i}] {b}")
    lines.append(f"Skills ({c.get('skills_title')}):")
    for i, (lbl, t) in enumerate(c.get("skills") or []):
        lines.append(f"  [{i}] {lbl}{t}")
    lines.append("Projects:")
    for i, (lbl, t) in enumerate(c.get("projects") or []):
        lines.append(f"  [{i}] {lbl}{t}")
    if not c.get("projects"):
        lines.append("  (none)")
    return "\n".join(lines)


def _label(s):
    s = (s or "").strip()
    if not s:
        return ""
    return s if s.endswith(" ") else (s if s.endswith(":") else s + ":") + " "


def strip_dashes(s):
    return (s or "").replace(" — ", ", ").replace("—", ", ")


def sources_for_check(folder, version):
    """Texts a number may be traced to: the profile's claims, this job's answers, the base version."""
    texts = [t for t in (up.read_text("profile.md"),) if t]
    try:
        texts.append(open(os.path.join(folder, "ANSWERS.md"), encoding="utf-8").read())
    except OSError:
        pass
    base = content_from_base(version)
    texts.append("\n".join(b for _, _, _, bs in base["experience"] for b in bs))
    texts.append("\n".join(t for _, t in base["projects"]) + "\n".join(t for _, t in base["skills"]))
    return texts


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fit":
        content = json.load(open(sys.argv[2]))
        res = fit(content, os.path.abspath(sys.argv[3]), log=lambda s: print(s, file=sys.stderr))
        res["measure"]["bullets"] = [{k: v for k, v in b.items() if k != "text"} for b in res["measure"]["bullets"]]
        d = find_duplicates(content)
        res["duplicates"] = d
        for p in d["hard"]:
            print("DUPLICATE: " + describe_duplicate(p), file=sys.stderr)
        for p in d["headings"]:
            print("DUPLICATE: " + p, file=sys.stderr)
        print(json.dumps(res, indent=1))
        if d["hard"] or d["headings"]:
            sys.exit(2)
    elif cmd == "dups":
        # python3 engine.py dups file.docx|content.json ...   exit 2 if any file has a hard duplicate
        bad = 0
        for path in sys.argv[2:]:
            d = audit_docx(path) if path.endswith(".docx") else find_duplicates(json.load(open(path)))
            for p in d["hard"]:
                print(f"{path}: DUPLICATE {describe_duplicate(p)}")
            for p in d["headings"]:
                print(f"{path}: DUPLICATE {p}")
            for p in d["soft"]:
                print(f"{path}: similar {describe_duplicate(p)}")
            bad += bool(d["hard"] or d["headings"])
        sys.exit(2 if bad else 0)
    elif cmd == "base":
        print(json.dumps(content_from_base(sys.argv[2]), indent=1, ensure_ascii=False))
    else:
        print(__doc__)
