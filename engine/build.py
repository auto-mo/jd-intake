#!/usr/bin/env python3
"""Resume XML helpers, the profile hookup, and a small command-line build.

Format spec is fixed: US Letter, 0.39 in margins, the profile's resume font (Times New Roman by
default) at 10 pt, centred name and contact line, ruled section headings. engine.py renders
through these helpers; this file is also a quick way to render one base version by hand:

  python3 build.py [version] [out.docx]      default version from base_versions.yaml,
                                             default file <file_stem>_Company.docx here
  then: soffice --headless --convert-to pdf --outdir . <docx>

Everything personal (name, contact line, links, file names, base content) comes from the profile
through server/userprofile.py. Nothing about any one person is written in this file.
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.docx")


def _find_server():
    """server/ holds userprofile.py. The engine runs from <repo>/engine, and the server also copies
    these scripts into <data>/applications/<job>/_build/, so walk up until server/ is found."""
    d = HERE
    for _ in range(8):
        cand = os.path.join(d, "server")
        if os.path.isfile(os.path.join(cand, "userprofile.py")):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    raise ImportError("server/userprofile.py not found above " + HERE + "; run the engine from inside the repo")


try:
    import userprofile as up  # already importable (the server passes PYTHONPATH, or it is loaded)
except ImportError:
    sys.path.insert(0, _find_server())
    import userprofile as up  # noqa: E402

# The generator may live in <application folder>/_build/; the finished files belong one level up,
# next to JD.md, so the application folder stays readable.
OUT_DIR = os.path.dirname(HERE) if os.path.basename(HERE) == "_build" else HERE
OUT_NAME = up.file_stem() + "_Company.docx"   # set per application
OUT = os.path.join(OUT_DIR, OUT_NAME)

# Fixed relationship ids for the contact-line links. The template carries no hyperlink
# relationships; render time adds one per link the profile has.
LINK_IDS = {"linkedin": "rIdLinkedIn", "website": "rIdWebsite"}


def font():
    return (up.get().get("resume") or {}).get("font") or "Times New Roman"


def _rfonts():
    f = esc(font())
    return f'<w:rFonts w:ascii="{f}" w:cs="{f}" w:eastAsia="{f}" w:hAnsi="{f}"/>'


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace("'", "&apos;").replace('"', "&quot;"))


def run(text, bold=False, size=20, style=None):
    rpr = "<w:rPr>"
    if style:
        rpr += f'<w:rStyle w:val="{style}"/>'
    rpr += _rfonts()
    if bold:
        rpr += "<w:b/><w:bCs/>"
    rpr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
    return f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def link(text, rid):
    return (f'<w:hyperlink w:history="1" r:id="{rid}">'
            f'{run(text, style="Hyperlink")}</w:hyperlink>')


def name_line(text=None):
    """The name header. Without an argument it is the profile's name in capitals."""
    if text is None:
        text = (up.get()["identity"].get("name") or "").upper()
    return ('<w:p><w:pPr><w:spacing w:after="20"/><w:jc w:val="center"/></w:pPr>'
            + run(text, bold=True, size=28) + "</w:p>")


def profile_links():
    """[(label, url, rel id)] for the links the profile has, in page order."""
    ident = up.get()["identity"]
    out = []
    for key, label in (("linkedin", "LinkedIn"), ("website", "Website")):
        url = (ident.get(key) or "").strip()
        if url:
            if "://" not in url:
                url = "https://" + url
            out.append((label, url, LINK_IDS[key]))
    return out


def contact_line():
    """Location | phone | email from the profile, then a LinkedIn and a Website link for each one
    the profile has. A missing piece is left out, separators included."""
    parts = [run(up.contact_line())] if up.contact_line() else []
    for label, _, rid in profile_links():
        parts.append(link(label, rid))
    body = run(" | ").join(parts)
    return ('<w:p><w:pPr><w:spacing w:after="60"/><w:jc w:val="center"/></w:pPr>'
            + body + "</w:p>")


def rels_with_links(rels_xml):
    """The template's document.xml.rels with one external hyperlink relationship per profile link."""
    add = "".join(
        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        f'hyperlink" Target="{esc(url)}" TargetMode="External"/>' for _, url, rid in profile_links())
    return rels_xml.replace("</Relationships>", add + "</Relationships>")


def write_docx(body_xml, out_docx):
    """Template + body -> out_docx, with the profile's links set in the relationships."""
    with zipfile.ZipFile(TEMPLATE) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        others = {n: z.read(n) for n in z.namelist() if n != "word/document.xml"}
    head = doc[:doc.index("<w:body>") + len("<w:body>")]
    tail = doc[doc.index("<w:sectPr"):]
    rels = "word/_rels/document.xml.rels"
    others[rels] = rels_with_links(others[rels].decode("utf-8")).encode("utf-8")
    if os.path.exists(out_docx):
        os.remove(out_docx)
    with zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in others.items():
            z.writestr(n, data)
        z.writestr("word/document.xml", head + body_xml + tail)
    return out_docx


def section(title):
    return ('<w:p><w:pPr><w:pBdr>'
            '<w:bottom w:val="single" w:color="000000" w:sz="6" w:space="1"/>'
            '</w:pBdr><w:spacing w:after="60" w:before="120"/>'
            '<w:jc w:val="center"/></w:pPr>'
            + run(title, bold=True) + "</w:p>")


def tabbed(left, right, bold_left=True, indent=0):
    ind = f'<w:ind w:left="{indent}"/>' if indent else ""
    return ('<w:p><w:pPr><w:tabs><w:tab w:val="right" w:pos="11088"/></w:tabs>'
            f'<w:spacing w:after="0"/>{ind}</w:pPr>'
            + run(left, bold=bold_left) + run("\t" + right, bold=bold_left)
            + "</w:p>")


def plain(text, bold=False, indent=0, after=0):
    ind = f'<w:ind w:left="{indent}"/>' if indent else ""
    return (f'<w:p><w:pPr><w:spacing w:after="{after}"/>{ind}</w:pPr>'
            + run(text, bold=bold) + "</w:p>")


def bullet(text):
    return ('<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr>'
            '<w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>'
            '<w:spacing w:after="0" w:line="230" w:lineRule="auto"/>'
            '<w:jc w:val="both"/></w:pPr>' + run(text) + "</w:p>")


def labelled_bullet(label, text):
    """Bullet whose leading label is bold, e.g. 'Demand model: ...'."""
    return ('<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr>'
            '<w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>'
            '<w:spacing w:after="0" w:line="230" w:lineRule="auto"/>'
            '<w:jc w:val="both"/></w:pPr>'
            + run(label, bold=True) + run(text) + "</w:p>")


def skill_line(label, text):
    return ('<w:p><w:pPr><w:spacing w:after="0" w:line="230" w:lineRule="auto"/>'
            '<w:jc w:val="both"/></w:pPr>'
            + run(label, bold=True) + run(text) + "</w:p>")


def report(content):
    """Character audit against the one-line / two-line targets for 10 pt text on this page."""
    print(f"{'chars':>6}  {'verdict':<12} text")
    print("-" * 78)
    rows = [b for _, _, _, bs in content["experience"] for b in bs]
    rows += [(lbl or "") + t for lbl, t in content.get("projects") or []]
    for full in rows:
        n = len(full)
        if 135 <= n <= 148:
            v = "1 line OK"
        elif 255 <= n <= 280:
            v = "2 lines OK"
        elif n < 135:
            v = f"SHORT {135-n}"
        elif n < 255:
            v = f"DEAD +{255-n}"
        else:
            v = f"OVER -{n-280}"
        print(f"{n:>6}  {v:<12} {full[:52]}...{'' if 'OK' in v else '  <<<'}")
    verbs = [b.split()[0] for _, _, _, bs in content["experience"] for b in bs if b.split()]
    dupes = {v for v in verbs if verbs.count(v) > 1}
    print("\nlead verbs:", ", ".join(verbs))
    print("duplicates:", dupes or "none")
    alltext = " ".join(rows) + " ".join(t for _, t in content.get("skills") or [])
    if "—" in alltext:
        print("WARNING: em dash in body text")


def main(argv):
    import engine
    version = argv[1] if len(argv) > 1 else up.default_version()
    out = os.path.abspath(argv[2]) if len(argv) > 2 else OUT
    content = engine.content_from_base(version)
    engine.render(content, out)
    print(f"wrote {out}\n")
    report(content)


if __name__ == "__main__":
    main(sys.argv)
