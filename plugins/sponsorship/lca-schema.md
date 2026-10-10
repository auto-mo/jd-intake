# LCA data for the sponsorship plug-in

The lookup reads the U.S. Department of Labor's public H-1B Labor Condition Application (LCA)
disclosure files. Nothing is shipped in the repository: you download the files yourself.

## Where the files go

`plugins/sponsorship/data/` (git-ignored). Put one disclosure file per fiscal year there, either with

```bash
python3 plugins/sponsorship/download_lca.py            # the last two complete fiscal years
python3 plugins/sponsorship/download_lca.py 2024 2025  # chosen years (the Q4 file of each)
```

or by hand from the DOL Office of Foreign Labor Certification performance data page:
https://www.dol.gov/agencies/eta/foreign-labor/performance (section "LCA Programs (H-1B, H-1B1, E-3)").

Each quarter's file is cumulative for its fiscal year, so keep only the latest quarter of each year;
two files for one year would count it twice. The year is read from `FY<year>` in the file name.
`.xlsx` and `.csv` both work. The files are large (100 to 300 MB each).

## Columns the lookup uses

From each disclosure file (DOL's names; older files differ slightly and both spellings are accepted):

| Column | Use |
|---|---|
| `EMPLOYER_NAME` | the employer, matched against the company name on a posting |
| `CASE_STATUS` | `Certified` (and `Certified - Withdrawn`) count as certified |
| `VISA_CLASS` | only `H-1B` rows are counted (`H-1B1` and `E-3` are skipped) |
| `H_1B_DEPENDENT` (or `H1B_DEPENDENT`) | `Y` on any row marks the employer H-1B dependent |

## The cache

The first lookup after a download builds `data/lca.db` (SQLite, a minute or two), one row per employer:

| Field | Meaning |
|---|---|
| `name` | employer name as filed, upper case |
| `filings` | H-1B LCAs across all files in `data/` |
| `certified` | of those, how many were certified |
| `dependent` | `Y` when the employer is H-1B dependent |
| `fy_prev`, `fy_last` | filings in the two most recent fiscal years present |
| `trend` | `GROWING`, `STEADY`, `SHRINKING`, `NEW`, `DROPPED`, `NONE RECENT`, or `ONE YEAR` with a single year |

The cache is rebuilt automatically when a file in `data/` is newer than it. Delete `data/lca.db` to force a rebuild.

## What it says when the data is missing

With no files in `data/`, the job's `JD.md` header says the LCA data is not downloaded and nothing is guessed
from the company's name. A filing count is evidence that an employer has sponsored before, not a promise that
it will sponsor you.
