#!/usr/bin/env python3
"""Download the U.S. Department of Labor's H-1B LCA disclosure files into plugins/sponsorship/data/.

Source: the DOL Office of Foreign Labor Certification "Performance Data" page,
    https://www.dol.gov/agencies/eta/foreign-labor/performance
which publishes one LCA disclosure spreadsheet per fiscal-year quarter (each quarter's file is cumulative
for the year, so the Q4 file is the whole year). The files are large (100 to 300 MB each).

The download address follows this pattern (check it on the page above if a download fails; DOL renames
files now and then, and you can always download by hand into the data folder instead):
    https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY{year}_Q{quarter}.xlsx

Usage:
    python3 plugins/sponsorship/download_lca.py                 # the last two complete fiscal years, Q4 files
    python3 plugins/sponsorship/download_lca.py 2024 2025       # these fiscal years (Q4)
    python3 plugins/sponsorship/download_lca.py 2026:Q2         # one quarter's file

The lookup (lca_lookup.py) rebuilds data/lca.db from whatever files are in data/ the next time it runs.
Only the latest file of each fiscal year should be kept there, or a year is counted twice.
"""
import os
import sys
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
URL = "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY{year}_Q{quarter}.xlsx"


def wanted(args):
    if not args:
        # The federal fiscal year ends on 30 September; the last complete one is this year's or last year's.
        today = date.today()
        last = today.year if today.month >= 11 else today.year - 1
        return [(last - 1, 4), (last, 4)]
    out = []
    for a in args:
        y, _, q = a.partition(":")
        out.append((int(y), int(q.upper().lstrip("Q") or 4)))
    return out


def download(year, quarter):
    os.makedirs(DATA_DIR, exist_ok=True)
    url = URL.format(year=year, quarter=quarter)
    dest = os.path.join(DATA_DIR, os.path.basename(url))
    if os.path.exists(dest):
        print(f"have {os.path.basename(dest)}")
        return dest
    print(f"downloading {url}")
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "jd-intake/0.3 (LCA download)"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    print(f"saved {dest}")
    return dest


if __name__ == "__main__":
    failed = 0
    for y, q in wanted(sys.argv[1:]):
        try:
            download(y, q)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FY{y} Q{q} failed: {e}. Download it by hand from "
                  "https://www.dol.gov/agencies/eta/foreign-labor/performance into " + DATA_DIR)
    sys.exit(1 if failed else 0)
