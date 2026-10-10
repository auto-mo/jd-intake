#!/usr/bin/env python3
"""Block a commit that would publish personal data or a secret.

Two checks over every file git would commit (or every file under the repo with --all):
  1. Secret shapes: API keys, tokens and private keys that should only ever live in .env.
  2. Your own identifiers: a list of regular expressions you keep OUTSIDE the repo (your name, email,
     phone, employers, people you have written to). Point JDI_DENYLIST at it. The list is never committed,
     because the list itself is personal. A line "!path" in that list exempts one file from the identifier
     check on purpose (for example "!LICENSE", where your name belongs); secret shapes are still checked.

Usage:
  python3 scripts/privacy_scan.py            # files staged for commit
  python3 scripts/privacy_scan.py --all      # every file in the working tree (respecting .gitignore)
As a pre-commit hook:  ln -s ../../scripts/privacy_scan.py .git/hooks/pre-commit
Exit code 1 when anything is found, so the commit stops.
"""
import os
import re
import subprocess
import sys

SECRET_PATTERNS = {
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "Apify token": r"apify_api_[A-Za-z0-9]{20,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "AWS key id": r"AKIA[0-9A-Z]{16}",
    "Telegram bot token": r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b",
    "Private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "Google API key": r"AIza[0-9A-Za-z_\-]{35}",
    "Slack token": r"xox[baprs]-[A-Za-z0-9\-]{10,}",
}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf"}


def files(all_files):
    if all_files:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, text=True).stdout
    else:
        out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                             capture_output=True, text=True).stdout
    return [f for f in out.splitlines() if f and os.path.isfile(f)]


def text_of(path):
    if os.path.splitext(path)[1].lower() in SKIP_EXT:
        return ""
    data = open(path, "rb").read()
    if path.endswith(".docx"):
        import zipfile
        import io
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            return "\n".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xml") or n.endswith(".rels"))
        except zipfile.BadZipFile:
            return ""
    return data.decode("utf-8", "ignore")


def denylist():
    """(patterns, files exempt from them)."""
    p = os.environ.get("JDI_DENYLIST")
    if not p:
        return [], set()
    pats, allow = [], set()
    for line in open(os.path.expanduser(p), encoding="utf-8"):
        line = line.strip()
        if line.startswith("!"):
            allow.add(os.path.normpath(line[1:].strip()))
        elif line and not line.startswith("#"):
            pats.append(re.compile(line, re.I))
    return pats, allow


def main():
    deny, allow = denylist()
    if not deny:
        print("privacy_scan: JDI_DENYLIST is not set, so only secret shapes are checked.", file=sys.stderr)
    me = os.path.normpath(__file__)
    hits = 0
    for f in files("--all" in sys.argv):
        if os.path.normpath(os.path.abspath(f)) == os.path.abspath(me):
            continue
        for n, line in enumerate(text_of(f).splitlines(), 1):
            for label, pat in SECRET_PATTERNS.items():
                if re.search(pat, line):
                    print(f"{f}:{n}: looks like a {label}")
                    hits += 1
            for rx in ([] if os.path.normpath(f) in allow else deny):
                if rx.search(line):
                    print(f"{f}:{n}: matches a personal identifier ({rx.pattern})")
                    hits += 1
    if hits:
        print(f"\nprivacy_scan: {hits} finding(s). Nothing should be committed until these are gone.", file=sys.stderr)
        return 1
    print("privacy_scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
