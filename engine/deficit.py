#!/usr/bin/env python3
"""For every bullet, report how many characters to add or cut to reach full lines.

Usage: python3 deficit.py resume.pdf [content.json]
Without content.json the profile's default base version is assumed to be what the PDF shows.
The numbers come from engine.measure, the same measurement the fit loop uses.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402

if len(sys.argv) < 2:
    sys.exit("usage: python3 deficit.py resume.pdf [content.json]")
pdf = sys.argv[1]
content = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else engine.content_from_base(None)
m = engine.measure(pdf, content)

print(f"{'#':>3} {'lines':>5} {'chars':>6} {'last%':>6} {'delta':>6}  text")
print("-" * 96)
for i, b in enumerate(m["bullets"]):
    if b["lines"] >= 2 and b["last_fill"] >= 92:
        verdict = "ok"
    elif b["lines"] >= 3:
        verdict = f"{b['cut_to_drop_line']:+d}"
    else:
        verdict = f"{b['add_to_fill']:+d}"
    print(f"{i:>3} {b['lines']:>5} {b['chars']:>6} {b['last_fill']:>6.1f} {verdict:>6}  {b['text'][:46]}"
          + ("  <<< orphan" if b["orphan"] else ""))
print(f"\npages {m['pages']}, trailing {m['trailing_in']} in, fill {m['fill_pct']}%")
