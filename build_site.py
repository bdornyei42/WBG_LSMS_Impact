"""
build_site.py: regenerate docs/data.json and docs/papers.json from the
latest exported workbook, so the GitHub Pages dashboard in docs/ always
mirrors the newest run. Called by save.bat before every commit.

Reads whichever LSMS_papers_*.xlsx is newest in the project root. Falls back
to the matching .csv (Papers sheet only, no excluded-paper breakdown) if the
workbook isn't there.
"""

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd

from fiscal_year import current_and_prior_fy, fy_to_year
from relevance import IDENTITY_MIN, USE_MIN

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

# LSMS-ISA, the current phase of the survey program, began in FY09; the
# headline stats, the flow/share charts, and the papers table all cover that
# same FY09-present window so the numbers on the page agree with each other.
ANALYSIS_FY_START = 2009

TIER_ORDER = [
    "1 — Top General or Top Field", "2 — Quality Field",
    "3 — Other Peer-Reviewed", "WP — Working Paper / Non-Journal",
]
TIER_LABELS = [
    "Tier 1: Top General or Top Field", "Tier 2: Quality Field",
    "Tier 3: Other Peer-Reviewed", "Working Paper / Non-Journal",
]

# metadata.py's tier labels/numbering have changed a few times (Tier 1 and
# Tier 2 used to be separate "Top General Econ" / "Top Field" buckets before
# merging into one). The chart reads journal_tier straight from whichever
# .xlsx was last exported, which may predate the current scheme, so map old
# label spellings onto the current TIER_ORDER instead of silently dropping
# them (they'd just fail the `if jt in tier_counts` check otherwise).
_LEGACY_TIER_LABELS = {
    "1 — Top General Econ": "1 — Top General or Top Field",
    "1 — Top General": "1 — Top General or Top Field",
    "2 — Top Field": "1 — Top General or Top Field",
    "3 — Quality Field": "2 — Quality Field",
    "4 — Other Peer-Reviewed": "3 — Other Peer-Reviewed",
}


def _current_tier(jt: str) -> str:
    return _LEGACY_TIER_LABELS.get(jt, jt)

PAPER_COLS = [
    "title", "doi", "year", "fy", "pub_type", "journal_tier",
    "peer_reviewed_auto", "venue", "authors", "first_author", "link",
    "open_access", "wb_affiliation_auto", "multilateral_affiliation",
    "geography_clean", "is_any_author_africa", "is_first_author_africa",
    "survey_family", "citation_count", "dataset_country",
]


def _newest(pattern):
    matches = glob.glob(os.path.join(HERE, pattern))
    return max(matches, key=os.path.getmtime) if matches else None


def _bool(series):
    return series.astype(str).str.strip().str.lower().isin(["true", "yes", "1"])


def _best_tier(match_tier: str) -> str:
    t = match_tier or ""
    return "A" if "A" in t else "B" if "B" in t else "C" if "C" in t else ""


def load_papers():
    """(papers_df, excluded_df|None, source_filename)"""
    xlsx = _newest("LSMS_papers_*.xlsx")
    if xlsx and not os.path.basename(xlsx).startswith("~$"):
        papers = pd.read_excel(xlsx, sheet_name="Papers")
        try:
            excluded = pd.read_excel(xlsx, sheet_name="Not Relevant (Backup)")
        except ValueError:
            excluded = None
        return papers, excluded, os.path.basename(xlsx)
    csv = _newest("LSMS_papers_*.csv")
    if not csv:
        sys.exit("[build_site] No LSMS_papers_*.xlsx or .csv found in project root.")
    return pd.read_csv(csv), None, os.path.basename(csv)


def build_flow(papers, current_fy, completed_fys):
    fy_labels = [f"FY{str(y)[-2:]}" for y in range(ANALYSIS_FY_START, fy_to_year(current_fy) + 1)]
    rows = []
    for fy in fy_labels:
        fp = papers[papers["fy"] == fy]
        n = len(fp)
        if n == 0 and fy != current_fy:
            continue
        any_a = int(_bool(fp["is_any_author_africa"]).sum()) if n else 0
        first_a = int(_bool(fp["is_first_author_africa"]).sum()) if n else 0
        rows.append({
            "fy": fy, "total": n,
            "africa_any": any_a, "africa_first": first_a,
            "africa_any_share": (any_a / n) if n else 0,
            "africa_first_share": (first_a / n) if n else 0,
            "is_current": fy == current_fy,
        })
    return rows


def build_metrics(papers, excluded, current_fy, completed_fys):
    total = len(papers)
    pct = lambda n: (n / total) if total else 0

    peer = int((papers["peer_reviewed_auto"].astype(str) == "Yes").sum())
    wb = int((papers["wb_affiliation_auto"].astype(str) == "Yes").sum())
    mult_vals = papers["multilateral_affiliation"].astype(str).str.strip()
    mult = int((~mult_vals.isin(["", "nan", "None"])).sum())

    af_any = int(_bool(papers["is_any_author_africa"]).sum())
    af_first = int(_bool(papers["is_first_author_africa"]).sum())
    af_strict = int(_bool(papers["is_africa_institution_strict"]).sum())
    unk = int((papers["geography_clean"] == "Unclassified").sum())

    fy0 = completed_fys[0]
    fy0_papers = papers[papers["fy"] == fy0]
    fy0_total = len(fy0_papers)
    af_any_fy0 = int(_bool(fy0_papers["is_any_author_africa"]).sum())
    af_first_fy0 = int(_bool(fy0_papers["is_first_author_africa"]).sum())

    best_tiers = papers["match_tier"].fillna("").map(_best_tier)
    tA, tB, tC = (int((best_tiers == t).sum()) for t in ("A", "B", "C"))
    t_multi = int(papers["match_tier"].fillna("").map(
        lambda t: len([x for x in t.split(";") if x.strip()]) > 1).sum())

    r_border = int(((papers["identity_score"].fillna(0) == IDENTITY_MIN) &
                     (papers["use_score"].fillna(0) == USE_MIN)).sum())
    r_use = int((papers["use_score"].fillna(0) > USE_MIN).sum())

    tier_counts = {t: 0 for t in TIER_ORDER}
    for jt in papers["journal_tier"].fillna(""):
        jt = _current_tier(jt)
        if jt in tier_counts:
            tier_counts[jt] += 1

    excl = {"no_use": None, "no_identity": None, "vetoed": None, "total_retrieved": None}
    if excluded is not None and len(excluded):
        n_no_use = int(((excluded["use_score"].fillna(0) < USE_MIN) &
                         (excluded["identity_score"].fillna(0) >= IDENTITY_MIN)).sum())
        n_no_ident = int((excluded["identity_score"].fillna(0) < IDENTITY_MIN).sum())
        n_vetoed = int(excluded["relevance_flags"].fillna("").str.contains("excluded_pub_type").sum())
        excl = {
            "no_use": n_no_use, "no_identity": n_no_ident, "vetoed": n_vetoed,
            "total_retrieved": total + len(excluded),
        }

    return {
        "total_papers": total,
        "total_retrieved": excl["total_retrieved"],
        "excluded_no_use": excl["no_use"],
        "excluded_no_identity": excl["no_identity"],
        "excluded_vetoed": excl["vetoed"],
        "peer_reviewed": {"count": peer, "share": pct(peer)},
        "wb_affiliated": {"count": wb, "share": pct(wb)},
        "multilateral": {"count": mult, "share": pct(mult)},
        "current_fy": current_fy,
        "current_fy_count": int((papers["fy"] == current_fy).sum()),
        "most_recent_completed_fy": fy0,
        "most_recent_completed_fy_count": fy0_total,
        "gate1": {
            "tier_a": {"count": tA, "share": pct(tA)},
            "tier_b": {"count": tB, "share": pct(tB)},
            "tier_c": {"count": tC, "share": pct(tC)},
            "multi_tier": {"count": t_multi, "share": pct(t_multi)},
        },
        "gate2": {
            "borderline": {"count": r_border, "share": pct(r_border)},
            "well_backed": {"count": total - r_border, "share": pct(total - r_border)},
            "strong_use": {"count": r_use, "share": pct(r_use)},
        },
        "geography": {
            "any_author_africa": {"count": af_any, "share": pct(af_any)},
            "any_author_africa_recent_fy": {"count": af_any_fy0,
                                             "share": (af_any_fy0 / fy0_total) if fy0_total else 0},
            "first_author_africa": {"count": af_first, "share": pct(af_first)},
            "first_author_africa_recent_fy": {"count": af_first_fy0,
                                               "share": (af_first_fy0 / fy0_total) if fy0_total else 0},
            "all_authors_ssa": {"count": af_strict, "share": pct(af_strict)},
            "unclassified": {"count": unk, "share": pct(unk)},
        },
        "journal_tiers": [
            {"label": lbl, "count": tier_counts[key]}
            for key, lbl in zip(TIER_ORDER, TIER_LABELS)
        ],
    }


_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_TIER_DASH = re.compile(r"\s+—\s+")


def _strip_tags(v):
    return _TAG.sub("", v) if isinstance(v, str) else v


def _clean_tier_label(v):
    # journal_tier values are our own labels (e.g. "4 — Other Peer-Reviewed"),
    # not bibliographic data, so the display copy on the page can drop the
    # dash without misrepresenting anything the pipeline actually found.
    return _TIER_DASH.sub(": ", v) if isinstance(v, str) else v


def build_papers_json(papers):
    df = papers.copy()
    for c in PAPER_COLS:
        if c not in df.columns:
            df[c] = None
    df = df[PAPER_COLS]
    df["is_any_author_africa"] = _bool(df["is_any_author_africa"])
    df["is_first_author_africa"] = _bool(df["is_first_author_africa"])
    # OpenAlex titles sometimes carry <b>…</b> highlight markup from the
    # search match; this is a public page, so strip it for display.
    for c in ("title", "venue", "authors", "first_author"):
        df[c] = df[c].map(_strip_tags)
    df["journal_tier"] = df["journal_tier"].map(_clean_tier_label)

    def _fy_key(row):
        return (-fy_to_year(row["fy"] or ""), str(row["title"] or "").lower())

    df = df.where(pd.notna(df), None)
    records = df.to_dict(orient="records")
    records.sort(key=lambda r: (-fy_to_year(r.get("fy") or ""), str(r.get("title") or "").lower()))
    return records


def main():
    os.makedirs(DOCS, exist_ok=True)
    papers, excluded, source_file = load_papers()
    current_fy, completed_fys = current_and_prior_fy()

    recent = papers[papers["fy"].map(fy_to_year) >= ANALYSIS_FY_START]
    recent_excluded = (excluded[excluded["fy"].map(fy_to_year) >= ANALYSIS_FY_START]
                        if excluded is not None else None)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_file": source_file,
        "analysis_fy_start": f"FY{str(ANALYSIS_FY_START)[-2:]}",
        "metrics": build_metrics(recent, recent_excluded, current_fy, completed_fys),
        "flow": build_flow(papers, current_fy, completed_fys),
    }

    with open(os.path.join(DOCS, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    with open(os.path.join(DOCS, "papers.json"), "w", encoding="utf-8") as f:
        json.dump(build_papers_json(recent), f, ensure_ascii=False, indent=None, separators=(",", ":"))

    print(f"[build_site] {len(recent)} papers -> docs/data.json, docs/papers.json (source: {source_file})")


if __name__ == "__main__":
    main()
