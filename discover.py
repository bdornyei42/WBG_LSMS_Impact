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
import glob
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
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
from dedup import deduplicate, load_existing, load_previous_scores, _split
from relevance import rank, passes, IDENTITY_MIN, USE_MIN
from excel_export import export_excel, export_csv
import charts


def is_writable(folder) -> bool:
    """Can we actually create a file here? Permissions alone don't tell you."""
    probe = Path(folder) / f".write_test_{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_output_dir(preferred=None) -> tuple[Path, bool]:
    """
    Somewhere the results can actually be written. Returns (folder, moved).

    Prefers the folder the tool is run from, so results sit next to the tool.
    Cloud-synced and managed folders reject writes, though: a WBG OneDrive
    folder returned "Errno 9 Bad file descriptor" on an ordinary open(). Rather
    than refuse to run, fall back to LocalAppData, which sync clients never
    touch, and say loudly where the results went.
    """
    candidates = [Path(preferred) if preferred else Path.cwd()]
    local = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    candidates.append(Path(local) / "LSMS Impact Analysis")

    for i, folder in enumerate(candidates):
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if is_writable(folder):
            return folder, i > 0
    raise SystemExit(
        "\n[error] No writable folder could be found for the results.\n"
        f"        Tried: {', '.join(str(c) for c in candidates)}\n"
        "        Copy the tool somewhere local, such as your Desktop, and retry.")


def latest_previous_export(exclude: Optional[str] = None,
                           folders=None) -> Optional[str]:
    """
    Most recent LSMS_papers_*.xlsx across the folders given.

    Looks in the results folder as well as the working one: when the tool sits
    in a folder it can't write to, results live elsewhere, and previous runs
    have to be found where they were actually saved.
    """
    exclude = os.path.abspath(exclude) if exclude else None
    folders = folders or [Path.cwd()]
    files = []
    for folder in folders:
        for f in glob.glob(str(Path(folder) / "LSMS_papers_*.xlsx")):
            if os.path.basename(f).startswith("~$"):
                continue
            if os.path.abspath(f) == exclude:
                continue
            files.append(f)
    return max(files, key=os.path.getmtime) if files else None


def run_discovery(
    api_key: str = "",
    since_fy: Optional[str] = None,
    min_year: int = 1980,
    min_relevance_score: int = 0,
    use_crossref: bool = False,
    merge_existing: Optional[str] = None,
    no_merge: bool = False,
    update_only: bool = False,
    output_dir: Optional[str] = None,
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

    # Settle where the results go BEFORE spending anything. The export happens
    # at the very end, so an unwritable folder would otherwise burn a whole
    # run's API budget and then throw the results away.
    if output_path is None:
        sfx = f"_since_{since_fy}" if since_fy else ""
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir, moved = resolve_output_dir(output_dir)
        output_path = str(out_dir / f"LSMS_papers{sfx}_{stamp}.xlsx")
        if moved:
            print(f"\n[note] This folder cannot be written to, which usually means "
                  f"OneDrive or\n       a security agent is locking it. Results will "
                  f"be saved to:\n       {out_dir}\n", flush=True)
    elif not is_writable(Path(output_path).parent):
        raise SystemExit(
            f"\n[error] Cannot write results to {Path(output_path).parent.resolve()}\n\n"
            "        Nothing has been searched yet, so no API budget was spent.\n"
            "        The folder is read-only, or a sync client (OneDrive,\n"
            "        SharePoint) or security agent is locking it. Drop the\n"
            "        --output option to let the tool pick a writable folder.")

    # the launcher reads this line to find the workbook afterwards
    print(f"[output] {Path(output_path).resolve()}", flush=True)

    # The methodology is settled, so every run is now checked against the last
    # one by default: papers already known are marked, papers this run added
    # are highlighted. Pass --no-merge for a clean run with no comparison.
    if merge_existing is None and not no_merge:
        search_in = [Path(output_path).parent, Path.cwd()]
        merge_existing = latest_previous_export(output_path, folders=search_in)
        if merge_existing and verbose:
            print(f"[info] Cross-checking against {Path(merge_existing).name} "
                  "(use --no-merge to skip)")
        elif not merge_existing and verbose:
            print("[info] No earlier export found, so nothing is marked as new.")
    existing_df = load_existing(merge_existing) if merge_existing else pd.DataFrame()
    prev_scores = load_previous_scores(merge_existing) if (merge_existing and update_only) else {}
    if update_only and not prev_scores:
        print("[warn] Update mode needs a previous export to build on and none was usable. "
              "Running the full analysis instead.", flush=True)
        update_only = False
    elif update_only and verbose:
        print(f"[info] Update mode: {len(prev_scores):,} papers already scored, so only "
              "new ones cost anything to check.")

    oa_fetcher = OpenAlexFetcher(api_key=api_key)
    cr_fetcher = CrossrefFetcher(api_key=api_key) if use_crossref else None
    if cr_fetcher and verbose:
        # Measured, not guessed: of 9 deduped Crossref records for a real term,
        # 0 could clear Gate 2 and 5 had no abstract at all. Crossref returns no
        # OpenAlex id, so Gate 2b cannot run and the whole use axis has to come
        # from an abstract that is frequently missing. Identity always clears
        # (the term is in the title by construction), so these reliably land in
        # the backup sheet. Kept because it costs nothing when off, but say so.
        print("[warn] --crossref adds title-only matches with no full text. They can "
              "almost never clear the use axis and will mostly land in the backup "
              "sheet. Useful as an audit trail, not as a source of new papers.",
              flush=True)

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

    # UPDATE MODE. Gate 1 still runs in full, so nothing is missed -- OpenAlex
    # indexes papers long after they're published, and its from_created_date
    # filter needs a paid plan, so a date window would silently lose late
    # arrivals forever. What we skip instead is the expensive part: a paper the
    # last run already scored keeps that score and never gets re-probed. Gate 2b
    # is roughly 80% of a run's cost, so this is where the saving comes from.
    reused = 0
    if update_only and prev_scores:
        for p in clean_all:
            prior = prev_scores.get(p.get("openalex_id") or "")
            if not prior:
                continue
            if prior.get("use_score") is not None and str(prior["use_score"]).strip() != "":
                try:
                    p["use_score"] = int(float(prior["use_score"]))
                    p["identity_score"] = int(float(prior["identity_score"]))
                except (TypeError, ValueError):
                    continue
                flags = prior.get("relevance_flags")
                p["relevance_flags"] = "" if flags is None or str(flags) == "nan" else str(flags)
                reused += 1
        if verbose:
            print(f"  Reused scores for {reused:,} papers already checked by a previous run")

    # Gate 2b: full-text pass. Targets the USE axis specifically -- a paper
    # can have overwhelming identity evidence and still nothing showing the
    # data was used, and that's precisely the paper worth spending a call on.
    if verbose:
        n_need = sum(1 for p in clean_all if (p.get("use_score") or 0) < USE_MIN)
        print(f"\n[fulltext] Gate 2b: checking use evidence for {n_need} papers...")
    oa_fetcher.fulltext_data_use_probe(
        clean_all, verbose=verbose,
        skip_ids=set(prev_scores) if update_only else None)

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
        n_new = sum(1 for p in clean if p.get("is_new") == "Yes")
        if any(p.get("is_new") for p in clean):
            print(f"New since the previous export:      {n_new:,}"
                  f"  (highlighted in the workbook)")

    export_excel(clean, review, search_log, output_path, min_year=min_year,
                 excluded=excluded_low_relevance)

    # CSV of the same rows, and the charts are built from that file rather
    # than from memory so what's plotted is provably what was exported.
    csv_path = Path(output_path).with_suffix(".csv")
    export_csv(clean, csv_path)
    if verbose:
        print(f"[export] {len(clean)} papers -> {csv_path.name}")

    current_fy, _ = current_and_prior_fy()
    charts.build_all(csv_path, current_fy=current_fy, verbose=verbose)
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
                    help="Compare against this Excel/CSV instead of auto-picking the "
                         "most recent LSMS_papers_*.xlsx")
    ap.add_argument("--no-merge", action="store_true",
                    help="Don't compare against any earlier export (nothing marked new)")
    ap.add_argument("--update", action="store_true",
                    help="Update run: still searches everything, but only spends full-text "
                         "checks on papers the previous export hasn't already scored. Much "
                         "cheaper, and loses no coverage. Omit to rescore everything.")
    ap.add_argument("--output", metavar="FILE", help="Output Excel path")
    ap.add_argument("--output-dir", metavar="DIR",
                    help="Folder for the results. Defaults to the current folder, "
                         "falling back to LocalAppData if that can't be written to "
                         "(OneDrive and managed folders often can't).")
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
            no_merge=args.no_merge, update_only=args.update,
            output_path=args.output, output_dir=args.output_dir,
            fuzzy_threshold=args.fuzzy_threshold,
            verbose=not args.quiet, test_mode=args.test)
    except BudgetExceeded as e:
        print(f"\n[budget] {e}\nRun stopped before hitting the session spend limit.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
