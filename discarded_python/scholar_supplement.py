"""
scholar_supplement.py — Google Scholar supplement via the `scholarly` library

WHY THIS IS A SUPPLEMENT, NOT THE PRIMARY SOURCE:
- Google Scholar has no official API. `scholarly` is an unofficial scraper.
- Google will CAPTCHA-block automated requests after a few hundred queries.
- For a quarterly pipeline, OpenAlex + Crossref will find ~95% of what Scholar
  finds, with zero CAPTCHA risk and structured author/affiliation data.

WHEN TO USE THIS:
- To catch very recent preprints (last 1–4 weeks) not yet indexed by OpenAlex.
- To catch grey literature (policy briefs, conference papers, government reports)
  not in Crossref/OpenAlex.
- Recommended: run manually on a laptop once a quarter, not in CI/cron.

CAPTCHA MITIGATION OPTIONS (pick one):
  1. Residential proxies via ScrapeOps (paid, ~$30/mo, reliable):
       pip install scrapeops-scrapy
       Set SCRAPEOPS_API_KEY env var, pass --scrapeops-key flag
  2. Tor + stem (free, slower, unreliable for high-volume):
       See https://github.com/scholarly-python-package/scholarly?tab=readme-ov-file#using-tor-as-a-proxy
  3. Just run interactively (no automation): scholarly will pause and ask you
     to solve a CAPTCHA in a browser when blocked.
  4. scholarly cloud proxy (built-in, deprecated but sometimes works):
       scholarly.use_proxy(scholarly.ProxyGenerator())

USAGE (standalone):
    python scholar_supplement.py --output gs_papers.csv
    python scholar_supplement.py --since-year 2024 --max-per-term 50

USAGE (as a module, append to existing discovery results):
    from scholar_supplement import search_scholar_batch
    papers = search_scholar_batch(terms=["LSMS-ISA", "GHS-Panel Nigeria"],
                                   max_per_term=100)
"""

import os
import time
import re
import unicodedata
from datetime import date
from typing import Optional

try:
    from scholarly import scholarly, ProxyGenerator
    HAS_SCHOLARLY = True
except ImportError:
    HAS_SCHOLARLY = False

import pandas as pd

from keywords import SURVEY_FAMILIES, SSA_COUNTRY_NAMES


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower().strip())


def _parse_scholarly_result(pub: dict, term: str, survey_family: str) -> Optional[dict]:
    """Convert scholarly publication dict to our output schema."""
    bib = pub.get("bib", {})
    title = bib.get("title", "")
    if not title:
        return None

    # Date extraction: scholarly gives pub_year as string
    pub_year_raw = bib.get("pub_year") or bib.get("year")
    year = None
    month = None
    if pub_year_raw:
        try:
            year = int(str(pub_year_raw)[:4])
        except ValueError:
            pass

    # scholarly rarely gives month; it's not in the basic API response
    # We record it as None (unlike OpenAlex which nearly always has a date)
    fy = None
    if year and month:
        fy_end = year + 1 if month >= 7 else year
        fy = f"FY{str(fy_end)[-2:]}"

    authors_str = bib.get("author", "")
    authors_list = [a.strip() for a in re.split(r" and |,", authors_str) if a.strip()]
    first_author = authors_list[0] if authors_list else ""

    venue = bib.get("venue") or bib.get("journal") or bib.get("conference") or ""
    abstract = bib.get("abstract", "")

    url = pub.get("pub_url", "") or ""
    doi = ""
    if "doi.org" in url:
        doi = re.sub(r".*doi\.org/", "", url).rstrip("/")

    # scholarly doesn't give institution country codes
    # We can heuristically check abstract/venue for SSA country names
    text = (title + " " + abstract + " " + venue).lower()
    africa_heuristic = any(c in text for c in SSA_COUNTRY_NAMES)

    return {
        "title": title,
        "doi": doi,
        "year": year,
        "month": month,             # usually None from Scholar
        "pub_date": str(year) if year else "",
        "fy": fy,                   # None if no month
        "authors": authors_str,
        "first_author": first_author,
        "n_authors": len(authors_list),
        "affiliations": "",
        "affiliation_countries": "",
        "geography_clean": "Unclassified",  # can't determine without institution data
        "is_ssa_strict": False,
        "is_africa_inclusive": africa_heuristic,  # heuristic only
        "publication_type": "unknown",
        "venue": venue,
        "published_peer_reviewed": bool(venue),
        "open_access": False,
        "oa_url": url,
        "citation_count": pub.get("num_citations", 0),
        "abstract": abstract,
        "language": "",
        "openalex_id": "",
        "survey_family": survey_family,
        "survey_term_matched": term,
        "source": "GoogleScholar",
        "date_discovered": date.today().isoformat(),
        "lsms_primary": None,
        "lsms_methods": None,
        "lsms_references": None,
        "notes": "month/FY not available from Google Scholar; geography is heuristic only",
    }


def search_scholar_batch(
    terms: Optional[list[str]] = None,
    survey_families_filter: Optional[list[str]] = None,
    max_per_term: int = 100,
    since_year: Optional[int] = None,
    scrapeops_key: Optional[str] = None,
    inter_term_delay: float = 5.0,
) -> list[dict]:
    """
    Search Google Scholar for each term and return parsed paper dicts.

    Args:
        terms                   : explicit list of terms to search; if None, uses
                                  all terms from keywords.py
        survey_families_filter  : if set, only search these family labels
        max_per_term            : max results to retrieve per term
        since_year              : only return papers from this year onward
        scrapeops_key           : ScrapeOps API key for residential proxy rotation
        inter_term_delay        : seconds to sleep between terms
    """
    if not HAS_SCHOLARLY:
        raise ImportError(
            "scholarly not installed. Run: pip install scholarly"
        )

    # Set up proxy if key provided
    if scrapeops_key:
        pg = ProxyGenerator()
        pg.ScrapeOps(api_key=scrapeops_key)
        scholarly.use_proxy(pg)
        print("[scholar] Using ScrapeOps proxy")

    # Build term → family mapping
    term_to_family: dict[str, str] = {}
    if terms:
        for t in terms:
            term_to_family[t] = "User-specified"
    else:
        for fam in SURVEY_FAMILIES:
            if survey_families_filter and fam["label"] not in survey_families_filter:
                continue
            for t in fam["terms"]:
                term_to_family[t] = fam["label"]

    results: list[dict] = []

    for term, family in term_to_family.items():
        print(f"[scholar] Searching: '{term}'")
        query = term
        if since_year:
            query = scholarly.search_pubs(term, year_low=since_year)
        else:
            query = scholarly.search_pubs(term)

        count = 0
        try:
            for pub in query:
                parsed = _parse_scholarly_result(pub, term, family)
                if parsed:
                    if since_year and parsed.get("year") and parsed["year"] < since_year:
                        continue
                    results.append(parsed)
                count += 1
                if count >= max_per_term:
                    break
        except Exception as e:
            print(f"  [warn] Scholar error on '{term}': {e}")

        time.sleep(inter_term_delay)

    print(f"[scholar] {len(results)} results from {len(term_to_family)} terms")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default="gs_supplement.csv")
    ap.add_argument("--since-year", type=int)
    ap.add_argument("--max-per-term", type=int, default=100)
    ap.add_argument("--scrapeops-key", default=os.getenv("SCRAPEOPS_API_KEY"))
    ap.add_argument("--families", nargs="+",
                    help="Restrict to these survey family labels")
    args = ap.parse_args()

    papers = search_scholar_batch(
        survey_families_filter=args.families,
        max_per_term=args.max_per_term,
        since_year=args.since_year,
        scrapeops_key=args.scrapeops_key,
    )

    if papers:
        df = pd.DataFrame(papers)
        df.to_csv(args.output, index=False)
        print(f"Saved {len(df)} papers to {args.output}")
    else:
        print("No results.")


if __name__ == "__main__":
    main()
