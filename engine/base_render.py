#!/usr/bin/env python3
"""Render a base version from the profile's base_versions.yaml through the standard generator.

Usage: python3 base_render.py [version] /path/to/Your_Name_Company.docx
Writes the docx (and a PDF next to it via LibreOffice) at the default layout, no fitting.
Prints JSON with paths and page count. Without a version, the profile's default one.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa: E402


def render(version, out_docx):
    engine.render(engine.content_from_base(version), out_docx)
    pdf = engine.convert(out_docx)
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
    pages = next((int(l.split()[-1]) for l in info.splitlines() if l.startswith("Pages:")), None)
    return {"docx": out_docx, "pdf": pdf, "pages": pages}


if __name__ == "__main__":
    args = sys.argv[1:]
    version, out = (args[0], args[1]) if len(args) > 1 else (None, args[0])
    print(json.dumps(render(version, os.path.abspath(out))))
