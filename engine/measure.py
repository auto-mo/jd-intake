#!/usr/bin/env python3
"""Measure rendered line fill from the PDF, so bullets can be tuned to full lines.

Reports, for every text line on the page, the fraction of the text column it fills,
and flags any line under 70% that is not the last line of a section-ending block.

Usage: python3 measure.py resume.pdf
"""
import re
import subprocess
import sys

if len(sys.argv) < 2:
    sys.exit("usage: python3 measure.py resume.pdf")
PDF = sys.argv[1]

xml = subprocess.run(["pdftotext", "-bbox-layout", PDF, "-"],
                     capture_output=True, text=True).stdout

lines = []
for lm in re.finditer(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" '
                      r'yMax="([\d.]+)">(.*?)</line>', xml, re.S):
    xmin, ymin, xmax, ymax, inner = lm.groups()
    words = re.findall(r'>([^<]*)</word>', inner)
    lines.append({"xmin": float(xmin), "xmax": float(xmax), "y": float(ymin),
                  "text": " ".join(words)})

lines.sort(key=lambda l: l["y"])

# text column: page is 612pt, margins 567 DXA = 28.35pt
LEFT, RIGHT = 28.35, 612 - 28.35
WIDTH = RIGHT - LEFT

print(f"text column {LEFT:.1f} to {RIGHT:.1f} pt, width {WIDTH:.1f}\n")
print(f"{'y':>6} {'fill%':>6}  text")
print("-" * 100)
for l in lines:
    fill = (l["xmax"] - LEFT) / WIDTH * 100
    flag = "  <<< STUB" if fill < 70 else ""
    print(f"{l['y']:>6.0f} {fill:>6.1f}  {l['text'][:78]}{flag}")

last = max(l["y"] for l in lines)
bottom_margin_y = 792 - 28.35
print(f"\nlast baseline y={last:.1f}pt, bottom margin at {bottom_margin_y:.1f}pt")
print(f"trailing whitespace: {(bottom_margin_y - last)/72:.2f} in "
      f"(target: under 0.40 in)")
