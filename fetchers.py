"""
fetchers.py — OpenAlex (primary) and Crossref (optional) fetchers.
"""

import time
from datetime import date
from typing import Optional

import requests

from fiscal_year import fiscal_year
from geography import classify_geography
from matching import build_search_query, passes_filters
from metadata import (detect_wb, detect_multilat, auto_topics,
                      dataset_countries, detect_pub_type, detect_journal_tier)
from relevance import relevance_score

OPENALEX_BASE = "https://api.openalex.org"
CROSSREF_BASE = "https://api.crossref.org"

PAGE_SIZE      = 200      # OpenAlex max per page
BATCH_SIZE     = 8        # terms per OR query (keeps URL < 2048 chars)
MAX_PAGES      = 25       # 25 x 200 = 5000 results/term cap
RATE_DELAY     = 0.11     # polite pool is about 10 req/s
CR_MAX_RESULTS = 100      # Crossref cap when --crossref is on

SESSION_SPEND_LIMIT = 4.50   # USD, hard stop w/ buffer under the $5 session cap

# Tier A companion pass: does "living standards measurement study" sit near
# data-use language anywhere in the full text? Proximity form first (tighter),
# then the broader AND form as a second, independent probe.
FULLTEXT_PROBE_QUERIES = [
    '"living standards measurement study data"~20',
    '"living standards measurement study" AND (data OR "we use" OR "using data" OR "survey data")',
]
FULLTEXT_BATCH = 50   # max work IDs per ids.openalex pipe filter

_OA_SELECT = ",".join([
    "id", "doi", "display_name", "publication_date", "publication_year",
    "type", "open_access", "authorships", "primary_location", "locations",
    "cited_by_count", "abstract_inverted_index", "language", "primary_topic",
])


class BudgetExceeded(RuntimeError):
    pass


class OpenAlexFetcher:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "LSMS-Tracker/2.0"
        self.session_spend = 0.0

    def _track_spend(self, headers) -> None:
        # OpenAlex reports per-call cost and remaining daily budget in USD.
        cost = headers.get("X-RateLimit-Cost-USD")
        if cost is not None:
            try:
                self.session_spend += float(cost)
            except ValueError:
                pass
        if self.session_spend >= SESSION_SPEND_LIMIT:
            raise BudgetExceeded(
                f"session spend ${self.session_spend:.4f} reached the "
                f"${SESSION_SPEND_LIMIT:.2f} limit — aborting.")

        remaining = headers.get("X-RateLimit-Remaining-USD")
        if remaining is not None:
            try:
                if float(remaining) < 0.10:
                    print(f"  [warn] OpenAlex daily budget low: ${remaining} remaining", flush=True)
            except ValueError:
                pass

    def _get(self, params: dict) -> dict:
        if self.api_key:
            params["api_key"] = self.api_key
        for attempt in range(3):
            try:
                time.sleep(RATE_DELAY)
                r = self.s.get(f"{OPENALEX_BASE}/works", params=params, timeout=60)
                if r.status_code == 429:
                    print("  [rate limit] 429 — waiting 30s. Add --api-key for the free 10x budget.", flush=True)
                    time.sleep(30)
                    continue
                r.raise_for_status()
                self._track_spend(r.headers)
                return r.json()
            except BudgetExceeded:
                raise
            except Exception as e:
                if attempt == 2:
                    print(f"  [warn] OpenAlex error: {e}")
                    return {}
                time.sleep(5 * (attempt + 1))
        return {}

    @staticmethod
    def _abstract(inv) -> str:
        if not inv:
            return ""
        return " ".join(w for _, w in sorted(
            ((p, w) for w, ps in inv.items() for p in ps)
        ))

    @staticmethod
    def _authors(authorships: list) -> dict:
        names, countries, insts = [], [], []
        fa_countries = []
        for idx, a in enumerate(authorships):
            n = (a.get("author") or {}).get("display_name", "")
            if n:
                names.append(n)
            inst_codes = []
            for inst in a.get("institutions", []):
                c = inst.get("country_code", "")
                if c:
                    countries.append(c)
                    inst_codes.append(c)
                iname = inst.get("display_name", "")
                if iname:
                    insts.append(iname)
            if idx == 0:
                fa_countries = inst_codes
        return {
            "authors":               "; ".join(names),
            "first_author":          names[0] if names else "",
            "second_author":         names[1] if len(names) > 1 else "",
            "n_authors":             len(names),
            "affiliations":          "; ".join(dict.fromkeys(insts)),
            "university_affiliation":"; ".join(dict.fromkeys(insts)),
            "affiliation_countries": "; ".join(dict.fromkeys(countries)),
            "_codes":                list(dict.fromkeys(countries)),
            "_fa_codes":             list(dict.fromkeys(fa_countries)),
        }

    def _parse(self, w: dict, family_label: str, family_region: str,
               terms_matched: list) -> dict:
        doi = w.get("doi") or ""
        pd_raw = w.get("publication_date") or ""
        year = month = None
        parts = pd_raw.split("-") if pd_raw else []
        try:
            year = int(parts[0]) if parts else w.get("publication_year")
            month = int(parts[1]) if len(parts) > 1 else None
        except (ValueError, IndexError):
            year = w.get("publication_year")

        fy = fiscal_year(year, month) if (year and month) else None

        ainfo    = self._authors(w.get("authorships", []))
        codes    = ainfo.pop("_codes", [])
        fa_codes = ainfo.pop("_fa_codes", [])
        geo      = classify_geography(codes, fa_codes)
        loc = w.get("primary_location") or {}
        peer = w.get("type") == "article" or loc.get("is_published", False)

        oa = w.get("open_access") or {}
        abstract_text = self._abstract(w.get("abstract_inverted_index"))
        title_text    = w.get("display_name") or ""
        authorships   = w.get("authorships", [])
        venue_name    = (loc.get("source") or {}).get("display_name", "")
        pub_type_det  = detect_pub_type(w.get("type", ""), venue_name)
        journal_tier  = detect_journal_tier(venue_name, pub_type_det)
        topics_auto   = auto_topics(title_text, abstract_text)
        countries_auto = dataset_countries(family_label, "; ".join(terms_matched))

        result = {
            "title":               title_text,
            "doi":                 doi,
            "year":                year,
            "month":               month,
            "pub_date":            pd_raw,
            "fy":                  fy,
            "publication_type":    w.get("type", ""),
            "pub_type":            pub_type_det,
            "journal_tier":        journal_tier,
            "peer_reviewed_auto":  "Yes" if peer else "No",
            "venue":               venue_name,
            **ainfo,
            "link":                oa.get("oa_url") or doi,
            "open_access":         oa.get("is_oa", False),
            "oa_url":              oa.get("oa_url") or "",
            "wb_affiliation_auto":       detect_wb(authorships),
            "multilateral_affiliation":  detect_multilat(authorships),
            **geo,
            "relevance_score":     0,    # filled below
            "relevance_flags":     "",
            "dataset_country":     "; ".join(c for c, v in countries_auto.items() if v == "Yes"),
            "research_topics":     ", ".join(k for k, v in topics_auto.items() if v == "Auto"),
            "abstract":            abstract_text,
            "citation_count":      w.get("cited_by_count", 0),
            "language":            w.get("language") or "",
            "survey_family":       family_label,
            "survey_region":       family_region,
            "survey_terms_matched":"; ".join(terms_matched),
            "openalex_id":         w.get("id", ""),
            "source":              "OpenAlex",
            "date_discovered":     date.today().isoformat(),
        }
        # Gather every URL OpenAlex gives us for this work (all locations, not
        # just the primary), so a worldbank.org / microdata.worldbank.org host
        # is caught wherever it sits.
        wb_urls = [doi, oa.get("oa_url") or ""]
        for L in ([loc] + (w.get("locations") or [])):
            if not L:
                continue
            wb_urls.append(L.get("landing_page_url") or "")
            wb_urls.append(L.get("pdf_url") or "")
        _rscore, _rflags = relevance_score(
            result.get("title", ""), result.get("abstract", ""),
            result.get("survey_terms_matched", ""),
            wb_affiliation=(result.get("wb_affiliation_auto") == "Yes"),
            urls=wb_urls)
        result["relevance_score"] = _rscore
        result["relevance_flags"] = _rflags
        return result

    def search_family(self, family: dict,
                      since_date: Optional[str] = None,
                      family_index: int = 0,
                      total_families: int = 54,
                      verbose: bool = True) -> list[dict]:
        label  = family["label"]
        region = family["region"]
        terms  = family["terms"]

        seen_ids: set = set()
        results: list = []

        if verbose:
            print(f"[{family_index}/{total_families}] {label} ({len(terms)} terms)", flush=True)

        for term, term_tier in terms:
            if verbose:
                print(f"  >> {term[:60]}", flush=True)

            params_query: dict = {
                "search":   build_search_query(term, term_tier, family.get("context_hints")),
                "select":   _OA_SELECT,
                "per_page": PAGE_SIZE,
            }
            if since_date:
                params_query["filter"] = f"publication_date.gte:{since_date}"

            cursor = "*"
            pages  = 0
            n_rejected = 0
            term_results: list = []

            while True:
                data = self._get({**params_query, "cursor": cursor})
                if not data:
                    break

                meta  = data.get("meta", {})
                items = data.get("results", [])

                if pages == 0 and verbose:
                    print(f"     {meta.get('count', '?')} results", flush=True)
                if not items:
                    break

                for w in items:
                    oa_id = w.get("id", "")
                    if oa_id and oa_id in seen_ids:
                        continue

                    inv = w.get("abstract_inverted_index") or {}
                    if inv:
                        abstract_txt = " ".join(
                            wd for _, wd in sorted(
                                (p, wd) for wd, ps in inv.items() for p in ps))
                    else:
                        abstract_txt = ""
                    title_txt = w.get("display_name") or ""

                    oa = w.get("open_access") or {}
                    ploc = w.get("primary_location") or {}
                    urls = [w.get("doi") or "", oa.get("oa_url") or "",
                            ploc.get("landing_page_url") or "",
                            ploc.get("pdf_url") or ""]

                    ok, tier, reason = passes_filters(
                        title_txt, abstract_txt, term, term_tier,
                        context_hints=family.get("context_hints") or [],
                        primary_topic=w.get("primary_topic"),
                        urls=urls,
                    )
                    if not ok:
                        n_rejected += 1
                        continue

                    if oa_id:
                        seen_ids.add(oa_id)
                    parsed = self._parse(w, label, region, [term])
                    parsed["match_tier"]   = tier
                    parsed["match_reason"] = reason
                    # No abstract on OpenAlex + Tier A match: don't let a data
                    # gap masquerade as low relevance.
                    if tier == "A" and not (parsed.get("abstract") or "").strip():
                        if (parsed.get("relevance_score") or 0) < 2:
                            parsed["relevance_score"] = 2
                            old_flags = parsed.get("relevance_flags") or ""
                            add = "tierA_match_no_abstract_available"
                            parsed["relevance_flags"] = (
                                add if old_flags in ("", "no_strong_signal")
                                else f"{old_flags},{add}")
                    term_results.append(parsed)

                cursor = meta.get("next_cursor")
                pages += 1
                if pages > 1 and verbose:
                    print(f"     page {pages} ...", flush=True)
                if not cursor or pages >= MAX_PAGES:
                    break

            if verbose and (term_results or n_rejected):
                msg = f"     kept {len(term_results)}"
                if n_rejected:
                    msg += f"  (filtered out {n_rejected})"
                print(msg, flush=True)
            results.extend(term_results)

        if verbose:
            print(f"  --> {len(results)} total for {label}", flush=True)
            print(f"     session spend so far: ${self.session_spend:.4f}", flush=True)
        return results

    def fulltext_data_use_probe(self, papers: list[dict], verbose: bool = True) -> int:
        """
        Tier A companion pass. Tier A already preserved recall on the survey
        name alone; this asks OpenAlex's full-text index whether "living
        standards measurement study" sits near data-use language for the
        specific works that matched but scored low (no abstract-level signal).
        Boost-only: raises relevance_score to >= 2 with a new
        fulltext_data_use flag, never lowers anything.

        Two probes (proximity + AND-language) batched at up to 50 work IDs
        per call via the ids.openalex pipe filter — cheap ($0.001/call).
        """
        candidates = [p for p in papers
                     if p.get("match_tier") == "A" and p.get("openalex_id")
                     and (p.get("relevance_score") or 0) < 2]
        if not candidates:
            return 0

        by_id = {p["openalex_id"].rsplit("/", 1)[-1]: p for p in candidates}
        ids = list(by_id.keys())
        hit_ids: set = set()

        for query in FULLTEXT_PROBE_QUERIES:
            for i in range(0, len(ids), FULLTEXT_BATCH):
                batch = ids[i:i + FULLTEXT_BATCH]
                data = self._get({
                    "search":   query,
                    "filter":   f"ids.openalex:{'|'.join(batch)}",
                    "select":   "id",
                    "per_page": FULLTEXT_BATCH,
                })
                for w in (data.get("results") or []):
                    short_id = (w.get("id") or "").rsplit("/", 1)[-1]
                    if short_id:
                        hit_ids.add(short_id)

        for short_id in hit_ids:
            p = by_id[short_id]
            p["relevance_score"] = max(p.get("relevance_score") or 0, 2)
            old_flags = p.get("relevance_flags") or ""
            add = "fulltext_data_use"
            p["relevance_flags"] = (
                add if old_flags in ("", "no_strong_signal") else f"{old_flags},{add}")

        if verbose:
            print(f"  [fulltext probe] boosted {len(hit_ids)}/{len(candidates)} "
                  f"Tier A matches -- session spend: ${self.session_spend:.4f}", flush=True)
        return len(hit_ids)


class CrossrefFetcher:
    """
    Only when --crossref is set. Title index only, hard cap CR_MAX_RESULTS per
    term, terms >= 18 chars, to avoid the flood of false positives that a
    full-field query produces.
    """

    def __init__(self, api_key: str = ""):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "LSMS-Tracker/2.0"

    def _parse(self, item: dict, family_label: str, family_region: str,
               term: str) -> Optional[dict]:
        title_list = item.get("title", [])
        title = title_list[0] if title_list else ""
        if not title:
            return None
        if term.lower().rstrip(".") not in title.lower():
            return None

        doi = item.get("DOI", "")
        pub = (item.get("published") or item.get("published-print")
               or item.get("published-online") or {})
        dp    = (pub.get("date-parts") or [[]])[0]
        year  = dp[0] if dp else None
        month = dp[1] if len(dp) > 1 else None
        pub_date = f"{year}-{month:02d}" if (year and month) else (str(year) if year else "")
        fy = fiscal_year(year, month) if (year and month) else None

        names = [f"{a.get('given','')} {a.get('family','')}".strip()
                 for a in item.get("author", [])]
        venue = (item.get("container-title") or [""])[0]
        peer  = item.get("type") in ("journal-article",)
        geo   = classify_geography([], [])

        return {
            "title": title, "doi": doi,
            "year": year, "month": month, "pub_date": pub_date, "fy": fy,
            "publication_type": item.get("type", ""),
            "venue": venue,
            "published_peer_reviewed": peer,
            "open_access": False, "oa_url": "",
            "citation_count": item.get("is-referenced-by-count", 0),
            "abstract": item.get("abstract", ""),
            "language": "",
            "openalex_id": "",
            "authors": "; ".join(names),
            "first_author": names[0] if names else "",
            "n_authors": len(names),
            "affiliations": "",
            "affiliation_countries": "",
            "survey_family": family_label,
            "survey_region": family_region,
            "survey_terms_matched": term,
            "source": "Crossref",
            "date_discovered": date.today().isoformat(),
            **geo,
        }

    def search_term(self, term: str, family: dict) -> list[dict]:
        if len(term) < 18:
            return []
        label, region = family["label"], family["region"]
        results, offset = [], 0
        while offset < CR_MAX_RESULTS:
            try:
                time.sleep(RATE_DELAY)
                r = self.s.get(f"{CROSSREF_BASE}/works", params={
                    "query.title": term,
                    "rows": min(100, CR_MAX_RESULTS - offset),
                    "offset": offset,
                    "select": "DOI,title,author,published,published-print,"
                              "container-title,type,is-referenced-by-count,abstract",
                }, timeout=20)
                r.raise_for_status()
                items = r.json().get("message", {}).get("items", [])
            except Exception:
                break
            if not items:
                break
            for item in items:
                parsed = self._parse(item, label, region, term)
                if parsed:
                    results.append(parsed)
            offset += len(items)
            if len(items) < 100:
                break
        return results
