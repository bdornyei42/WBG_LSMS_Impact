"""
validate_flagged.py — check the Tier A fulltext companion pass against Talip's
flagged review set (the "Notes" column in the Not Relevant (Backup) (2) sheet
of LSMS_papers_20260716_131337 - Talip Feedbacks 2.xlsx).

Validates ONLY these ~36 flagged works, never the full corpus. Prints a table:
doi, Ben's intended verdict, old score, new score, new sheet, agree?

USAGE:
    python validate_flagged.py --api-key YOUR_KEY
"""

import argparse
import json

import openpyxl

from fetchers import OpenAlexFetcher, BudgetExceeded
from relevance import relevance_score

FEEDBACK_XLSX = "LSMS_papers_20260716_131337 - Talip Feedbacks 2.xlsx"
FEEDBACK_SHEET = "Not Relevant (Backup) (2)"

# Ben's intended verdict per flagged row, read off the Notes column by hand.
# Keyed by row position in sheet order (0-indexed among flagged rows only).
# "ambiguous" rows (Talip wrote "IDK"/"not sure"/no clear call) are reported
# but not scored as agree/disagree.
INTENDED_VERDICTS = [
    "exclude",    # 0  reference only
    "exclude",    # 1  UNPS in references only
    "include",    # 2  Methods + footnotes, real use
    "exclude",    # 3  feedback only, no data use
    "exclude",    # 4  citing an LSMS working paper only
    "exclude",    # 5  mentions LSMS, no data use
    "exclude",    # 6  reference only / unclear use
    "exclude",    # 7  reference only, no data use
    "include",    # 8  Ghana LSS dataset used
    "exclude",    # 9  reference only
    "include",    # 10 adds 2019 LSMS round data, genuine use
    "exclude",    # 11 mentions ESS, doesn't use data
    "exclude",    # 12 guest editorial, no data use
    "exclude",    # 13 reference only
    "include",    # 14 HFPS results used + worldbank.org url
    "exclude",    # 15 reference only
    "include",    # 16 explicit data use, Data section
    "ambiguous",  # 17 World Bank survey brief -- own report, unclear if "paper"
    "include",    # 18 explicit Dataset section use
    "include",    # 19 explicit LSMS data use + worldbank.org
    "ambiguous",  # 20 visual report, Talip flagged "(?)"
    "include",    # 21 explicit Datasets section
    "include",    # 22 Methods: data from LSMS
    "exclude",    # 23 "MAYBE? ok to exclude"
    "include",    # 24 uses dataset, WB in intro
    "include",    # 25 uses LSMS data, Table 1
    "exclude",    # 26 citing papers only, no data
    "include",    # 27 "we use ... data" in Data section
    "include",    # 28 visual report, clearly uses LSMS data
    "include",    # 29 Data Collection section, uses LSMS data
    "include",    # 30 uses LSMS-ISA labour data
    "ambiguous",  # 31 "IDK"
    "include",    # 32 "IN CASE IT SHOULD BE INCLUDED"
    "include",    # 33 uses LSMS data + worldbank.org
    "exclude",    # 34 refers to it, does not use data
    "ambiguous",  # 35 no clear call ("Life Sciences --")
]


def load_flagged_rows() -> list[dict]:
    wb = openpyxl.load_workbook(FEEDBACK_XLSX, read_only=True, data_only=True)
    ws = wb[FEEDBACK_SHEET]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}
    flagged = []
    for r in rows[1:]:
        note = r[idx["Notes"]]
        if note and str(note).strip():
            flagged.append({h: r[i] for h, i in idx.items()})
    return flagged


def new_sheet_for(score: int) -> str:
    return "Papers" if score >= 2 else "Not Relevant (Backup)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default="", help="OpenAlex API key")
    args = ap.parse_args()

    api_key = args.api_key
    if not api_key:
        with open("pipeline_config.json") as f:
            api_key = json.load(f).get("api_key", "")

    flagged = load_flagged_rows()
    if len(flagged) != len(INTENDED_VERDICTS):
        raise ValueError(
            f"flagged rows ({len(flagged)}) != INTENDED_VERDICTS ({len(INTENDED_VERDICTS)}) "
            "-- the sheet's Notes column changed, re-derive verdicts before trusting this table.")

    fetcher = OpenAlexFetcher(api_key=api_key)

    # Recompute relevance_score with the restored WB-affiliation/url signals,
    # for every flagged row (all match_tier "A" except one legacy "AND" row).
    papers = []
    for row in flagged:
        wb_affil = row.get("wb_affiliation_auto") == "Yes"
        urls = [row.get("doi") or "", row.get("oa_url") or "", row.get("link") or ""]
        score, flags = relevance_score(
            row.get("title", ""), row.get("abstract", ""),
            row.get("survey_terms_matched", ""),
            wb_affiliation=wb_affil, urls=urls)
        row["_old_score"] = row.get("relevance_score")
        # overwrite w/ the recomputed (WB/url-aware) score -- the probe below
        # boosts further on top of this, never below it.
        row["relevance_score"] = score
        row["relevance_flags"] = flags
        papers.append(row)

    # Only match_tier "A" rows are eligible for the fulltext companion probe.
    eligible = [p for p in papers if p.get("match_tier") == "A"]
    try:
        fetcher.fulltext_data_use_probe(eligible, verbose=True)
    except BudgetExceeded as e:
        print(f"\n[budget] {e}")
        raise SystemExit(1)

    print(f"\n{'doi':<55} {'intended':<10} {'old':>3} {'new':>3} {'new sheet':<24} agree?")
    print("-" * 115)
    n_scored, n_agree = 0, 0
    for row, verdict in zip(papers, INTENDED_VERDICTS):
        doi = (row.get("doi") or row.get("title") or "")[:55]
        old = row.get("_old_score")
        new = row.get("relevance_score")
        sheet = new_sheet_for(new)
        if verdict == "ambiguous":
            agree = "n/a"
        else:
            wants_papers = verdict == "include"
            got_papers = new >= 2
            agree = "YES" if wants_papers == got_papers else "NO"
            n_scored += 1
            n_agree += agree == "YES"
        print(f"{doi:<55} {verdict:<10} {old:>3} {new:>3} {sheet:<24} {agree}")

    print(f"\n{n_agree}/{n_scored} scored rows agree with Ben's intended verdict "
          f"({len(papers) - n_scored} ambiguous, not scored)")
    print(f"\nSESSION_SPEND: ${fetcher.session_spend:.4f} "
          f"({'OK, under $5' if fetcher.session_spend < 5 else 'OVER BUDGET'})")


if __name__ == "__main__":
    main()
