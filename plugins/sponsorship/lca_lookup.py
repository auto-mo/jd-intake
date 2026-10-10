#!/usr/bin/env python3
"""Deterministic H-1B LCA lookup: how often an employer filed Labor Condition Applications. No LLM.

Part of the optional sponsorship plug-in (features.sponsorship in profile/profile.yaml; docs/sponsorship.md).

Data: the U.S. Department of Labor's LCA disclosure files, which you download yourself with
download_lca.py into plugins/sponsorship/data/ (git-ignored; the files are large). The first lookup
after a download aggregates them into data/lca.db (a minute or two); every lookup after that is instant.
With no data the lookup says so plainly instead of guessing.

Usage:  python3 lca_lookup.py "Northbridge Logistics" "Copperleaf Health"
"""
import difflib
import glob
import os
import re
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
DB = os.path.join(DATA_DIR, "lca.db")
SOURCES = ("*.xlsx", "*.csv")
STOP = {"inc", "llc", "corp", "corporation", "co", "company", "ltd", "limited", "lp", "llp",
        "plc", "group", "holdings", "us", "usa", "america", "the", "of", "and", "&"}


def norm(s):
    return " ".join(w for w in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split() if w not in STOP)


def source_files():
    out = []
    for pat in SOURCES:
        out += glob.glob(os.path.join(DATA_DIR, pat))
    return sorted(out)


def missing_message():
    return ("LCA data is not downloaded, so sponsorship history was not checked. Run "
            "`python3 plugins/sponsorship/download_lca.py` (docs/sponsorship.md).")


def _fy(path):
    m = re.search(r"FY\s*_?(\d{4})", os.path.basename(path), re.I)
    return int(m.group(1)) if m else 0


def _rows(path):
    """(employer, status, h1b_dependent, visa_class) per row of one DOL disclosure file."""
    if path.lower().endswith(".csv"):
        import csv
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            rd = csv.reader(f)
            header = [h.strip().upper() for h in next(rd)]
            yield from _pick(header, rd)
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        rows = wb.worksheets[0].iter_rows(values_only=True)
        header = [str(h or "").strip().upper() for h in next(rows)]
        yield from _pick(header, rows)


def _pick(header, rows):
    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None
    e, s = col("EMPLOYER_NAME"), col("CASE_STATUS")
    d, v = col("H_1B_DEPENDENT", "H1B_DEPENDENT", "H-1B_DEPENDENT"), col("VISA_CLASS")
    if e is None or s is None:
        raise ValueError("not an LCA disclosure file: no EMPLOYER_NAME or CASE_STATUS column")
    for r in rows:
        if not r or e >= len(r):
            continue
        yield (r[e], r[s], r[d] if d is not None and d < len(r) else None,
               r[v] if v is not None and v < len(r) else "H-1B")


def _trend(prev_year, p, last):
    if not prev_year:
        return "ONE YEAR"
    if p == 0 and last == 0:
        return "NONE RECENT"
    if p == 0:
        return "NEW"
    if last == 0:
        return "DROPPED"
    return "GROWING" if last > p * 1.1 else "SHRINKING" if last < p * 0.9 else "STEADY"


def build_db():
    """Aggregate every disclosure file in data/ into one row per employer: (name, filings, certified,
    dependent, filings in the second-latest year, filings in the latest year, trend). None with no files."""
    files = source_files()
    if not files:
        return None
    years = sorted({_fy(p) for p in files if _fy(p)})
    last, prev = (years[-1] if years else 0), (years[-2] if len(years) > 1 else 0)
    agg = {}
    for path in files:
        fy = _fy(path)
        for emp, status, dep, visa in _rows(path):
            if not emp or "H-1B" not in str(visa or "H-1B").upper():
                continue
            a = agg.setdefault(str(emp).strip().upper(), [0, 0, "N", 0, 0])
            a[0] += 1
            if str(status or "").lower().startswith("certified"):
                a[1] += 1
            if str(dep or "").strip().upper() in ("Y", "YES"):
                a[2] = "Y"
            if fy and fy == prev:
                a[3] += 1
            if fy and fy == last:
                a[4] += 1
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS emp")
    con.execute("CREATE TABLE emp(name TEXT, filings INT, certified INT, dependent TEXT, fy_prev INT, fy_last INT, trend TEXT)")
    con.execute("DROP TABLE IF EXISTS meta")
    con.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
    con.executemany("INSERT INTO emp VALUES(?,?,?,?,?,?,?)",
                    ((n, a[0], a[1], a[2], a[3], a[4], _trend(prev, a[3], a[4])) for n, a in agg.items()))
    con.executemany("INSERT INTO meta VALUES(?,?)", (("fy_prev", str(prev)), ("fy_last", str(last)),
                                                    ("sources", "|".join(os.path.basename(p) for p in files))))
    con.commit()
    return con


def _fresh():
    """True when lca.db exists and is newer than every source file."""
    if not os.path.exists(DB):
        return False
    t = os.path.getmtime(DB)
    return all(os.path.getmtime(p) <= t for p in source_files())


def load_index():
    """{normalized name: [rows]}, or {} when no data has been downloaded (see missing_message())."""
    if not source_files() and not os.path.exists(DB):
        return {}
    con = sqlite3.connect(DB) if _fresh() else build_db()
    if con is None:
        return {}
    idx = {}
    for r in con.execute("SELECT name, filings, certified, dependent, fy_prev, fy_last, trend FROM emp"):
        idx.setdefault(norm(r[0]), []).append(r)
    con.close()
    return idx


def year_labels():
    """['FY2024', 'FY2025'] for the two yearly columns, from the last build."""
    try:
        con = sqlite3.connect(DB)
        m = dict(con.execute("SELECT k, v FROM meta").fetchall())
        con.close()
        return [f"FY{m.get('fy_prev') or '?'}", f"FY{m.get('fy_last') or '?'}"]
    except Exception:  # noqa: BLE001
        return ["previous year", "latest year"]


def lookup(idx, company):
    k = norm(company)
    if not k or not idx:
        return "none", []
    # Exact and prefix/contains matches are ranked together by filings, so a tiny entity that
    # happens to share the bare name cannot outrank the real employer.
    hits, how = list(idx.get(k) or []), "exact"
    cands = [x for x in idx if x != k and (x.startswith(k + " ") or (" " + k + " ") in (" " + x + " "))]
    for x in cands:
        hits += idx[x]
    if cands and not idx.get(k):
        how = "contains"
    if not hits:
        for x in difflib.get_close_matches(k, idx.keys(), n=2, cutoff=0.9):
            hits += idx[x]
        how = "fuzzy"
    hits.sort(key=lambda r: -(r[1] or 0))
    return how, hits[:3]


if __name__ == "__main__":
    t = time.time()
    idx = load_index()
    if not idx:
        sys.exit(missing_message())
    print(f"index: {sum(len(v) for v in idx.values())} employers, {time.time() - t:.1f}s")
    ys = year_labels()
    for q in sys.argv[1:] or ["Northbridge Logistics"]:
        t0 = time.time()
        how, hits = lookup(idx, q)
        print(f"\n{q} [{how}, {(time.time() - t0) * 1000:.0f} ms]")
        for h in hits:
            print(f"    {h[0]} | filings {h[1]} | certified {h[2]} | dependent {h[3]} | {ys[0]} {h[4]} {ys[1]} {h[5]} {h[6]}")
        if not hits:
            print("    NO LCA RECORD")
