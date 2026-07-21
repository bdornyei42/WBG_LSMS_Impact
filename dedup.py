"""
dedup.py — merge duplicates within a run, then dedup against a prior run.
"""

import difflib
from pathlib import Path
from typing import Optional

import pandas as pd

from normalize import norm_title, norm_doi


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
            old_terms = set((existing.get("survey_terms_matched") or "").split("; "))
            new_terms = set((p.get("survey_terms_matched") or "").split("; "))
            existing["survey_terms_matched"] = "; ".join(sorted(old_terms | new_terms))
            old_fam = set((existing.get("survey_family") or "").split("; "))
            new_fam = set((p.get("survey_family") or "").split("; "))
            existing["survey_family"] = "; ".join(sorted(old_fam | new_fam))
            old_dc = set(x.strip() for x in (existing.get("dataset_country") or "").split(";") if x.strip())
            new_dc = set(x.strip() for x in (p.get("dataset_country") or "").split(";") if x.strip())
            existing["dataset_country"] = "; ".join(sorted(old_dc | new_dc))
            continue

        if oa:  by_oaid[oa]   = p
        if doi: by_doi[doi]   = p
        if ttl: by_title[ttl] = p
        order.append(p)

    # A paper matching 2+ distinct families is almost certainly using LSMS
    # microdata. With A/C already flooring at 2 this rarely fires, but it stays
    # as a backstop for any weak match that slipped through.
    for p in order:
        fams = [x for x in (p.get("survey_family") or "").split("; ") if x.strip()]
        if len(set(fams)) >= 2 and (p.get("relevance_score") or 0) < 2:
            p["relevance_score"] = 2
            existing_flags = p.get("relevance_flags") or ""
            add = f"multi_survey_match_{len(set(fams))}"
            p["relevance_flags"] = (
                add if existing_flags in ("", "no_strong_signal")
                else f"{existing_flags},{add}")

    review: list = []
    if existing_df is None or existing_df.empty:
        return order, review

    ex_dois, ex_titles = set(), []
    if "doi" in existing_df.columns:
        ex_dois = {norm_doi(str(v)) for v in existing_df["doi"].dropna()}
    for col in ("title", "Document Info"):
        if col in existing_df.columns:
            ex_titles = [norm_title(str(v)) for v in existing_df[col].dropna()]
            break

    ex_title_set = set(ex_titles)
    clean: list = []
    for p in order:
        doi = norm_doi(p.get("doi", ""))
        ttl = norm_title(p.get("title", ""))
        if doi and doi in ex_dois:
            continue
        if ttl and ttl in ex_title_set:
            continue
        if ttl and ex_titles:
            best = max(
                (difflib.SequenceMatcher(None, ttl, et).ratio()
                 for et in ex_titles if abs(len(et) - len(ttl)) < 40),
                default=0.0)
            if best >= fuzzy_threshold:
                p["_fuzzy_score"] = round(best, 3)
                review.append(p)
                continue
        clean.append(p)

    return clean, review


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
