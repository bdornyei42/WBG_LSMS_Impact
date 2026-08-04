"""
dedup.py — merge duplicates within a run, then dedup against a prior run.
"""

import difflib
from pathlib import Path
from typing import Optional

import pandas as pd

from normalize import norm_title, norm_doi


def _split(v) -> set:
    return {x.strip() for x in (v or "").split(";") if x.strip()}


def deduplicate(papers: list[dict],
                existing_df: Optional[pd.DataFrame] = None,
                fuzzy_threshold: float = 0.88) -> tuple[list, list]:
    """
    1) Within-run merge by OpenAlex ID -> DOI -> exact title, keeping every
       survey family/term/country the paper matched.
    2) Against a prior master: exact DOI/title, then fuzzy title.
    Returns (clean_list, review_list).
    """
    by_oaid, by_doi, by_title = {}, {}, {}
    order: list = []

    for p in papers:
        oa  = p.get("openalex_id", "")
        doi = norm_doi(p.get("doi", ""))
        ttl = norm_title(p.get("title", ""))

        existing = None
        if oa and oa in by_oaid:
            existing = by_oaid[oa]
        elif doi and doi in by_doi:
            existing = by_doi[doi]
        elif ttl and ttl in by_title:
            existing = by_title[ttl]

        if existing:
            # split on ";" not "; " and drop blanks -- an empty field used to
            # merge in as a stray "" entry and come out as a leading "; "
            for col in ("survey_terms_matched", "survey_family",
                        "dataset_country", "match_tier"):
                merged = _split(existing.get(col)) | _split(p.get(col))
                existing[col] = "; ".join(sorted(merged))
            continue

        if oa:  by_oaid[oa]   = p
        if doi: by_doi[doi]   = p
        if ttl: by_title[ttl] = p
        order.append(p)

    # Scoring (including the multi-family/multi-term signals) happens in a
    # single pass in relevance.rank(), called once by discover.py after this
    # function returns -- dedup only merges records, it never touches score.

    review: list = []
    if existing_df is None or existing_df.empty:
        # nothing to compare against, so nothing can be called "new"
        for p in order:
            p["is_new"] = ""
        return order, review

    ex_dois, ex_titles = set(), []
    if "doi" in existing_df.columns:
        ex_dois = {norm_doi(str(v)) for v in existing_df["doi"].dropna()}
    for col in ("title", "Document Info"):
        if col in existing_df.columns:
            ex_titles = [norm_title(str(v)) for v in existing_df[col].dropna()]
            break

    # Every paper this run found stays in the output. The prior file decides
    # what gets MARKED as new, it never decides what gets dropped -- the point
    # of comparing against it is a complete, current dataset in which this
    # run's additions are visible, not an incremental diff that has to be
    # stitched back together by hand.
    ex_title_set = set(ex_titles)
    for p in order:
        doi = norm_doi(p.get("doi", ""))
        ttl = norm_title(p.get("title", ""))
        if (doi and doi in ex_dois) or (ttl and ttl in ex_title_set):
            p["is_new"] = "No"
            continue
        if ttl and ex_titles:
            # A DOI the previous export doesn't have is strong evidence this is
            # a genuinely different paper, so a mere family resemblance in the
            # title shouldn't override it -- only a near-exact one should.
            # Without that, titles in this literature are formulaic enough
            # ("X and household consumption in rural Uganda") that roughly half
            # of real additions got flagged for review against a corpus of any
            # size, which makes the flag useless.
            threshold = 0.95 if (doi and ex_dois) else fuzzy_threshold
            best = max(
                (difflib.SequenceMatcher(None, ttl, et).ratio()
                 for et in ex_titles if abs(len(et) - len(ttl)) < 40),
                default=0.0)
            if best >= threshold:
                # close but not identical: probably the same paper with a
                # reworded title, so flag it for a human rather than guessing
                p["_fuzzy_score"] = round(best, 3)
                p["is_new"] = "Review"
                review.append(p)
                continue
        p["is_new"] = "Yes"

    return order, review


def load_existing(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        print(f"[warn] --merge-existing file not found: {path}")
        return pd.DataFrame()
    if p.suffix.lower() == ".csv":
        return pd.read_csv(path)
    for sheet in ("Papers", "List of pubs."):
        try:
            return pd.read_excel(path, sheet_name=sheet)
        except Exception:
            continue
    return pd.DataFrame()
