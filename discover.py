"""
discover.py — LSMS paper discovery runner.

Ties the modules together and exposes the command line. All the real work lives
in the imported modules: fetchers, dedup, relevance, matching, metadata,
geography, fiscal_year, excel_export.

USAGE:
    python discover.py --api-key YOUR_FREE_KEY                  # full run (~5 min)
    python discover.py --api-key YOUR_FREE_KEY --test           # 2 families
    python discover.py --api-key YOUR_FREE_KEY --since-fy FY25   # FY25 onward
    python discover.py --api-key YOUR_FREE_KEY \
        --merge-existing LSMS_papers_20260101.xlsx              # dedup vs existing

DEPENDENCIES:
    pip install requests openpyxl pandas tqdm
"""

import argparse
import sys
from datetime import date
from typing import Optional

import pandas as pd

# Windows consoles default to cp1252 and hard-crash on the arrows/≥ in the
# progress output. Do this before anything prints.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import keywords
from keywords import SURVEY_FAMILIES
from fiscal_year import fy_start_date, current_and_prior_fy
from fetchers import OpenAlexFetcher, CrossrefFetcher, BudgetExceeded
from dedup import deduplicate, load_existing, _split
from relevance import rank, passes, IDENTITY_MIN, USE_MIN
from excel_export import export_excel


def run_discovery(
    api_key: str = "",
    since_fy: Optional[str] = None,
    min_year: int = 1980,
    min_relevance_score: int = 0,
    use_crossref: bool = False,
    merge_existing: Optional[str] = None,
    output_path: Optional[str] = None,
    fuzzy_threshold: float = 0.88,
    verbose: bool = True,
    test_mode: bool = False,
) -> list:

    since_date = None
    if not api_key:
        print("[warn] No --api-key supplied. Free budget is only 100 searches/day without a key.")
        print("[warn] Get a FREE key in 30s at: https://openalex.org/settings/api", flush=True)
    if since_fy:
        since_date = fy_start_date(since_fy).isoformat()
        if verbose:
            print(f"[info] Filtering papers ≥ {since_date} ({since_fy} start)")

    if output_path is None:
        sfx = f"_since_{since_fy}" if since_fy else ""
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"LSMS_papers{sfx}_{stamp}.xlsx"

    existing_df = load_existing(merge_existing) if merge_existing else pd.DataFrame()

    oa_fetcher = OpenAlexFetcher(api_key=api_key)
    cr_fetcher = CrossrefFetcher(api_key=api_key) if use_crossref else None

    all_papers: list = []
    search_log: list = []

    families = SURVEY_FAMILIES[:2] if test_mode else SURVEY_FAMILIES
    n_families = len(families)

    for f_idx, family in enumerate(families, 1):
        label = family["label"]
        oa_results = oa_fetcher.search_family(
            family, since_date,
            family_index=f_idx, total_families=n_families, verbose=verbose)
        all_papers.extend(oa_results)
        search_log.append({
            "survey_family": label, "source": "OpenAlex",
            "n_terms": len(family["terms"]), "n_results_raw": len(oa_results),
            "run_date": date.today().isoformat(), "since_date": since_date or "all",
        })
        if verbose:
            print(f"  Running total (raw): {len(all_papers):,}", flush=True)

        if cr_fetcher:
            cr_total = 0
            for term, tier, _hints, _x in keywords.iter_terms(family):
                cr = cr_fetcher.search_term(term, family, tier)
                all_papers.extend(cr)
                cr_total += len(cr)
            if cr_total and verbose:
                print(f"  CR supplement: +{cr_total}")
            search_log.append({
                "survey_family": label, "source": "Crossref",
                "n_terms": len(family["terms"]), "n_results_raw": cr_total,
                "run_date": date.today().isoformat(), "since_date": since_date or "all",
            })

    # Drop pre-1980 and impossible future years. OpenAlex sometimes carries a
    # placeholder date ahead of now; one year of headroom covers forthcoming work.
    CURRENT_YEAR = date.today().year
    MAX_VALID_YEAR = CURRENT_YEAR + 1
    n_before = len(all_papers)
    all_papers = [p for p in all_papers
                  if min_year <= (p.get("year") or 0) <= MAX_VALID_YEAR]
    if verbose and len(all_papers) < n_before:
        print(f"  Dropped {n_before - len(all_papers)} papers outside "
              f"{min_year}\u2013{MAX_VALID_YEAR}", flush=True)

    # Dedup before the relevance gate, so a paper's separate matches (several
    # terms, several families) merge into one record before it's scored --
    # multi-family/multi-term are Gate 2 signals and need that merge to exist.
    if verbose:
        print(f"\n[dedup] {len(all_papers)} raw → deduplicating...")
    clean_all, review = deduplicate(all_papers, existing_df, fuzzy_threshold)

    # Gate 2a: one scoring pass for every deduped paper. Only place the two
    # axes get set from scratch.
    if verbose:
        print(f"\n[rank] scoring {len(clean_all)} deduped papers...")
    for p in clean_all:
        score = rank(
            title=p.get("title", ""),
            abstract=p.get("abstract", ""),
            oa_type=p.get("publication_type", ""),
            wb_affiliation=(p.get("wb_affiliation_auto") == "Yes"),
            survey_families=_split(p.get("survey_family")),
            survey_terms=_split(p.get("survey_terms_matched")),
            match_tiers=_split(p.get("match_tier")),
        )
        p["identity_score"] = score.identity
        p["use_score"]      = score.use
        p["relevance_flags"] = ",".join(score.flags)

    # Gate 2b: full-text pass. Targets the USE axis specifically -- a paper
    # can have overwhelming identity evidence and still nothing showing the
    # data was used, and that's precisely the paper worth spending a call on.
    if verbose:
        n_need = sum(1 for p in clean_all if (p.get("use_score") or 0) < USE_MIN)
        print(f"\n[fulltext] Gate 2b: checking use evidence for {n_need} papers...")
    oa_fetcher.fulltext_data_use_probe(clean_all, verbose=verbose)

    excluded_low_relevance, kept = [], []
    for p in clean_all:
        ident, use = p.get("identity_score") or 0, p.get("use_score") or 0
        p["relevance_score"] = ident + use          # sorting/triage only
        ok = passes(ident, use, (p.get("relevance_flags") or "").split(","))
        if ok and p["relevance_score"] >= min_relevance_score:
            kept.append(p)
        else:
            excluded_low_relevance.append(p)
    clean = kept

    if verbose and excluded_low_relevance:
        no_use   = sum(1 for p in excluded_low_relevance
                      if (p.get("use_score") or 0) < USE_MIN
                      and (p.get("identity_score") or 0) >= IDENTITY_MIN)
        no_ident = sum(1 for p in excluded_low_relevance
                      if (p.get("identity_score") or 0) < IDENTITY_MIN)
        print(f"  Set aside {len(excluded_low_relevance):,} papers "
              f"(mentions it but no evidence of use: {no_use:,} | "
              f"not confidently our survey: {no_ident:,}) "
              f"-> 'Not Relevant (Backup)' sheet", flush=True)

    if verbose:
        current_fy, completed_fys = current_and_prior_fy()
        total = len(clean)
        no_fy = sum(1 for p in clean if not p.get("fy"))
        af_fa  = sum(1 for p in clean if p.get("is_first_author_africa"))
        af_any = sum(1 for p in clean if p.get("is_any_author_africa"))
        af_str = sum(1 for p in clean if p.get("is_africa_institution_strict"))
        # both axes are at their minimum = it just barely cleared; anything
        # above that has corroborating evidence on at least one axis
        borderline  = sum(1 for p in clean
                         if (p.get("identity_score") or 0) == IDENTITY_MIN
                         and (p.get("use_score") or 0) == USE_MIN)
        well_backed = total - borderline
        strong_use  = sum(1 for p in clean if (p.get("use_score") or 0) > USE_MIN)
        print("\n=== RESULTS ===")
        print(f"Unique papers (≥ 1980):            {total:,}")
        for fy in completed_fys:
            n = sum(1 for p in clean if p.get("fy") == fy)
            tag = "  ← most recently completed" if fy == completed_fys[0] else ""
            print(f"FLOW {fy}: {n}{tag}")
        print(f"FLOW {current_fy} (in progress): {sum(1 for p in clean if p.get('fy') == current_fy)}")
        if total:
            print(f"SHARE Africa (first author):        {af_fa}/{total} = {af_fa/total:.1%}")
            print(f"SHARE Africa (any author):          {af_any}/{total} = {af_any/total:.1%}")
            print(f"SHARE Africa (strict/all-SSA):      {af_str}/{total} = {af_str/total:.1%}")
            print(f"Borderline (both axes exactly at minimum): "
                  f"{borderline:,} = {borderline/total:.1%}")
            print(f"Well-backed (corroborated beyond the minimum): "
                  f"{well_backed:,} = {well_backed/total:.1%}")
            print(f"Strong data-use evidence (use > {USE_MIN}): "
                  f"{strong_use:,} = {strong_use/total:.1%}")
        print(f"Papers without month (FY blank):    {no_fy}")
        print(f"Fuzzy review candidates:            {len(review)}")

    export_excel(clean, review, search_log, output_path, min_year=min_year,
                 excluded=excluded_low_relevance)
    return clean


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-key", default="",
                    help="OpenAlex API key (FREE at openalex.org/settings/api).")
    ap.add_argument("--since-fy", metavar="FYxx",
                    help="Only fetch papers since this FY start, e.g. FY24")
    ap.add_argument("--min-relevance", type=int, default=0,
                    help="Extra floor on identity+use combined. Both axes must clear "
                         "their own minimum regardless; this only tightens further.")
    ap.add_argument("--min-year", type=int, default=1980,
                    help="Exclude papers before this year (default 1980)")
    ap.add_argument("--merge-existing", metavar="FILE",
                    help="Existing Excel/CSV; new papers deduped against it")
    ap.add_argument("--output", metavar="FILE", help="Output Excel path")
    ap.add_argument("--crossref", action="store_true",
                    help="Also search Crossref (title-only, slower)")
    ap.add_argument("--fuzzy-threshold", type=float, default=0.88)
    ap.add_argument("--test", action="store_true", help="Quick run: 2 families only")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    try:
        run_discovery(
            api_key=args.api_key, min_year=args.min_year,
            min_relevance_score=args.min_relevance, since_fy=args.since_fy,
            use_crossref=args.crossref, merge_existing=args.merge_existing,
            output_path=args.output, fuzzy_threshold=args.fuzzy_threshold,
            verbose=not args.quiet, test_mode=args.test)
    except BudgetExceeded as e:
        print(f"\n[budget] {e}\nRun stopped before hitting the session spend limit.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
