"""
dedup.py — merge duplicates within a run, then dedup against a prior run.
"""

from pathlib import Path
from typing import Optional

import pandas as pd

from normalize import norm_title, norm_doi


def _split(v) -> set:
    return {x.strip() for x in (v or "").split(";") if x.strip()}




def deduplicate(papers: list[dict],
                existing_df: Optional[pd.DataFrame] = None,
                fuzzy_threshold: float = 0.88) -> tuple[list, list]:
    # fuzzy_threshold is accepted for CLI compatibility and no longer used
    """
    1) Within-run merge by OpenAlex ID -> DOI -> exact title, keeping every
       survey family/term/country the paper matched.
    2) Against the previous export: marks each paper new or already known,
       matching on OpenAlex id, then DOI, then exact title. Nothing is
       dropped -- the output is the complete current dataset.
    Returns (papers, review_list). review_list is retained for the workbook's
    Dedup Review sheet and is empty now that matching is exact.
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

    # OpenAlex ids first: the same paper keeps the same id across runs, so
    # against our own exports this is an exact, instant answer. DOI and exact
    # title are fallbacks for older hand-maintained files that have no ids.
    ex_ids, ex_dois, ex_titles = set(), set(), set()
    if "openalex_id" in existing_df.columns:
        ex_ids = {str(v).strip() for v in existing_df["openalex_id"].dropna()}
        ex_ids.discard("")
    if "doi" in existing_df.columns:
        ex_dois = {norm_doi(str(v)) for v in existing_df["doi"].dropna()}
    for col in ("title", "Document Info"):
        if col in existing_df.columns:
            ex_titles = {norm_title(str(v)) for v in existing_df[col].dropna()}
            break

    # Every paper this run found stays in the output. The prior file decides
    # what gets MARKED as new, it never decides what gets dropped -- the point
    # of comparing against it is a complete, current dataset in which this
    # run's additions are visible, not an incremental diff that has to be
    # stitched back together by hand.
    # All three checks are exact set lookups, so this is linear in the number
    # of papers. It replaced a fuzzy title comparison that ran every new title
    # against every old one: 200 papers against a 7,600-row export did not
    # finish in five minutes, so a real run never reached the export step at
    # all. Nothing is lost by dropping it -- a paper carries the same OpenAlex
    # id from one run to the next, which is a stronger answer than any
    # similarity score.
    for p in order:
        oa  = str(p.get("openalex_id") or "").strip()
        doi = norm_doi(p.get("doi", ""))
        ttl = norm_title(p.get("title", ""))
        known = ((oa and oa in ex_ids)
                 or (doi and doi in ex_dois)
                 or (ttl and ttl in ex_titles))
        p["is_new"] = "No" if known else "Yes"

    return order, review


def load_previous_scores(path: str) -> dict:
    """
    openalex_id -> the scores a previous run already worked out.

    Reads BOTH result sheets: a paper the last run rejected is still a paper we
    have already paid to check, and re-probing it would defeat the point of an
    update run.
    """
    p = Path(path)
    if not p.exists():
        return {}
    want = ("identity_score", "use_score", "relevance_flags")
    frames = []
    if p.suffix.lower() == ".csv":
        frames.append(pd.read_csv(path))
    else:
        for sheet in ("Papers", "Not Relevant (Backup)"):
            try:
                frames.append(pd.read_excel(path, sheet_name=sheet))
            except Exception:
                continue
    out: dict = {}
    for df in frames:
        if "openalex_id" not in df.columns or not any(c in df.columns for c in want):
            continue
        for rec in df.to_dict("records"):
            oa = str(rec.get("openalex_id") or "").strip()
            if not oa or oa.lower() == "nan":
                continue
            out[oa] = {k: rec.get(k) for k in want}
    return out


def load_existing(path: str) -> pd.DataFrame:
    """
    Everything the previous run already saw, both kept and rejected.

    The backup sheet matters as much as the results sheet here: a paper that
    run set aside is still one we have seen before, and reading only "Papers"
    would relabel the entire backup set as new on every single run.
    """
    p = Path(path)
    if not p.exists():
        print(f"[warn] previous export not found: {path}")
        return pd.DataFrame()
    if p.suffix.lower() == ".csv":
        return pd.read_csv(path)
    frames = []
    for sheet in ("Papers", "Not Relevant (Backup)", "List of pubs."):
        try:
            frames.append(pd.read_excel(path, sheet_name=sheet))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
