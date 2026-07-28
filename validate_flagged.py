"""
validate_flagged.py — check Gate 2 against the flagged review set (the "Notes"
column in the Not Relevant (Backup) (2) sheet of
LSMS_papers_20260716_131337 - Talip Feedbacks 2.xlsx). Talip asked Ben to
verify those links; the Notes are Ben's own working assessments from doing
that, not Talip's verdicts.

Validates ONLY these ~36 works, never the full corpus.

CAVEAT: reads frozen title/abstract/terms off the old export, so it exercises
Gate 2 (rank + the fulltext probe) but NOT Gate 1 admission — keyword/tier
changes don't show up here, they need a live search to test.

    python validate_flagged.py --api-key YOUR_KEY
"""

import argparse
import json

import openpyxl

import keywords
import relevance
from fetchers import OpenAlexFetcher, BudgetExceeded

FEEDBACK_XLSX = "LSMS_papers_20260716_131337 - Talip Feedbacks 2.xlsx"
FEEDBACK_SHEET = "Not Relevant (Backup) (2)"

# Ben's intended verdict per flagged row, read off his own Notes column by
# hand. Keyed by row position in sheet order (0-indexed among flagged rows
# only). "ambiguous" rows (Ben wrote "IDK"/"not sure"/no clear call) are
# reported but not scored.
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
    "ambiguous",  # 20 visual report, Ben flagged "(?)"
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
    idx = {h: i for i, h in enumerate(rows[0])}
    for need in ("Notes", "survey_terms_matched", "title", "abstract"):
        if need not in idx:
            raise ValueError(f"{FEEDBACK_SHEET} has no {need!r} column")
    return [{h: r[i] for h, i in idx.items()}
            for r in rows[1:]
            if r[idx["Notes"]] and str(r[idx["Notes"]]).strip()]


def split(v) -> list:
    return [x.strip() for x in (v or "").split(";") if x.strip()]


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
            "-- the sheet's Notes column changed, re-derive verdicts before trusting this.")

    fetcher = OpenAlexFetcher(api_key=api_key)

    for row in flagged:
        terms = split(row.get("survey_terms_matched"))
        # tiers come from TODAY's registry, not whatever the old export said --
        # that's what a live run would produce for these same terms
        tiers = [t for t in (keywords.term_tier(x) for x in terms) if t]
        score = relevance.rank(
            title=row.get("title", ""), abstract=row.get("abstract", ""),
            oa_type=row.get("publication_type", ""),
            wb_affiliation=row.get("wb_affiliation_auto") == "Yes",
            survey_families=split(row.get("survey_family")),
            survey_terms=terms, match_tiers=tiers)
        row["identity_score"] = score.identity
        row["use_score"] = score.use
        row["relevance_flags"] = ",".join(score.flags)

    try:
        fetcher.fulltext_data_use_probe(flagged, verbose=True)
    except BudgetExceeded as e:
        print(f"\n[budget] {e}")
        raise SystemExit(1)

    print(f"\n{'doi':<52} {'intended':<10} {'id':>3} {'use':>4} {'verdict':<9} agree?")
    print("-" * 100)
    n_scored = n_agree = 0
    misses = []
    for row, want in zip(flagged, INTENDED_VERDICTS):
        doi = (row.get("doi") or row.get("title") or "")[:52]
        ident, use = row["identity_score"], row["use_score"]
        got = relevance.passes(ident, use, row["relevance_flags"].split(","))
        verdict = "Papers" if got else "Backup"
        if want == "ambiguous":
            agree = "n/a"
        else:
            agree = "YES" if (want == "include") == got else "NO"
            n_scored += 1
            n_agree += agree == "YES"
            if agree == "NO":
                misses.append((doi, want, ident, use, row["relevance_flags"]))
        print(f"{doi:<52} {want:<10} {ident:>3} {use:>4} {verdict:<9} {agree}")

    print(f"\n{n_agree}/{n_scored} agree ({len(flagged) - n_scored} ambiguous, not scored)")
    if misses:
        print("\ndisagreements:")
        for doi, want, ident, use, flags in misses:
            print(f"  {doi}\n    wanted {want}, identity={ident} use={use}\n    {flags}")
    print(f"\nSESSION_SPEND: ${fetcher.session_spend:.4f} "
          f"({'OK, under $5' if fetcher.session_spend < 5 else 'OVER BUDGET'})")


if __name__ == "__main__":
    main()
