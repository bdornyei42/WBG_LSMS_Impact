"""
fetchers.py — OpenAlex (primary) and Crossref (optional) fetchers.
"""

import time
from datetime import date
from typing import Optional

import requests

from fiscal_year import fiscal_year
from geography import classify_geography
import keywords
from matching import (build_search_query, passes_filters,
                      SEARCH_PARAM, FULLTEXT_SEARCH_PARAM)
from metadata import (detect_wb, detect_multilat, auto_topics,
                      dataset_countries, detect_pub_type, detect_journal_tier)
import relevance

OPENALEX_BASE = "https://api.openalex.org"
CROSSREF_BASE = "https://api.crossref.org"

PAGE_SIZE      = 200      # OpenAlex max per page
BATCH_SIZE     = 8        # terms per OR query
MAX_PAGES      = 25       # 25 x 200 = 5000 results/term cap
RATE_DELAY     = 0.11     # polite pool is about 10 req/s
CR_MAX_RESULTS = 100      # Crossref cap when --crossref is on

SESSION_SPEND_LIMIT = 4.50   # USD, hard stop w/ buffer under the $5 session cap
BROAD_TERM_WARN = 5000       # a single survey keyword matching more than this is a bug

# ── Gate 2b: full-text evidence that the data was USED ───────────────────────
# Everything here asks the same question in OpenAlex's full-text index: does
# the paper's OWN matched survey name sit within FULLTEXT_PROXIMITY_WINDOW
# words of language that describes working with the data? Proximity is what
# ties the evidence to OUR survey specifically -- an abstract saying "we use
# panel data" proves nothing about which panel.
#
# Bare nouns ("data", "survey data", "panel survey", "using the") were tried
# as a third group and are deliberately absent: a bibliography entry sits
# within 40 words of the word "data" in essentially every empirical paper, so
# they fired on 14 known-good exclusions in the 36-DOI validation set (17/32
# vs 22/32) without distinguishing a citation from genuine use. That is
# exactly the "mentions it but doesn't use it" failure this gate exists to
# prevent, so the word lists below stay restricted to phrasing a citation
# cannot structurally produce.
#
# Window is 40 words, not 20 -- genuine use-language often lands one sentence
# after the survey name, and 20 cuts that off at the boundary. 100 was tried:
# isolated per-row testing predicted a clean 2-gain/1-loss trade, but the full
# batched run came back net negative (21/32 vs 22/32) -- reverted. The full
# run is what counts, not the isolated forecast.

# These three lists were PICKED FROM EVIDENCE, not intuition: every candidate
# phrase was run against the 36-DOI flagged set and scored on how many
# intended-include vs intended-exclude papers it hit (scratch script
# wordpick.py). Net separation per phrase, include/exclude:
#   using data from 8/1   data from the 8/2   using the 12/7   we use 3/0
#   we used 3/0   collected by 4/1   sample of 5/2   conducted by 2/0
#   wave 2/0   round 2/0   survey data 7/5   microdata 1/0   obtained from 1/0
#   supported by 2/2   funded by 2/2   implemented by 2/2
#   based on the 2/4   this study uses 1/3   this paper uses 0/2
# The last three are NEGATIVE discriminators and are deliberately absent --
# they hit more citations than real uses. Several phrases that sound like
# obvious wins ("we draw on", "our analysis", "our sample", "we obtained",
# "drawn from", "we rely on") scored ZERO hits and are also gone; academic
# prose overwhelmingly prefers "using data from"/"data from the".

# Strong: the author working with the data. Worth a STRONG use point, and
# +1 identity too -- a data-use phrase sitting this close to the survey name
# also corroborates that it's the right survey, not a name collision.
FULLTEXT_USE_STRONG = [
    "using data from", "data from the", "we use", "we used",
    "we collected", "collected by", "conducted by", "obtained from",
]

# Weak: data-object language near the name. Real but noisier -- "using the"
# alone catches 12 of the includes and 7 of the excludes, so it corroborates
# rather than decides.
FULLTEXT_USE_WEAK = [
    "using the", "sample of", "survey data", "microdata", "wave", "round",
]

# Who ran/paid for the survey. Describes provenance, not the authors' own
# analysis, and measured 2/2 on its own -- kept separate and weak so it can
# stack with the list above rather than carry a paper by itself. This is what
# rescues the pastoralism/HFPS Uganda paper (s13570-022-00230-y), which has
# "supported by"/"funded by" within 40 words of "High-Frequency Phone Survey".
FULLTEXT_PROVENANCE_WORDS = ["supported by", "funded by", "implemented by"]

# Searched in the paper's TEXT, not against where the paper is hosted -- a
# worldbank.org landing page only means the World Bank published it, which
# says nothing about whether it used LSMS microdata.
#
# REPORTED BUT NOT SCORED. Measured 2 includes / 2 excludes on the flagged
# set: citing the catalogue does not actually separate genuine use from a
# reference-list mention, which was a surprise -- the assumption going in was
# that you only cite the catalogue when you downloaded the files. Scoring it
# STRONG made the set worse (22/32), scoring it WEAK still cost a false
# positive (23/32 vs 24/32 without). So the probe runs and the flag is written
# to the workbook, because knowing the catalogue is cited is genuinely useful
# when reviewing a paper by hand -- it just doesn't get a vote.
MICRODATA_CATALOG_PHRASES = ["microdata.worldbank.org", "world bank microdata"]

FULLTEXT_PROXIMITY_WINDOW = 40   # words
# 100 is OpenAlex's hard cap for values in one ids.openalex filter (101+ is a
# 400). Halving the batch count halves the query count, and Gate 2b queries
# are the expensive kind -- search calls bill at $1/1000 vs $0.10/1000 for a
# plain filter, and the probe is ~80% of a run's spend.
FULLTEXT_BATCH = 100
# OpenAlex documents a ~4 KB URL limit and recommends splitting big OR lists
# into chunks and unioning the returned ids client-side, which is what
# _proximity_hits does.
MAX_QUERY_URL = 4000
FULLTEXT_WORD_CHUNK = 8
# Separate, undocumented-but-enforced cap: more than 3 quoted phrases longer
# than LONG_PHRASE_CHARS OR'd together is a hard 400 ("Lots of long-phrase OR
# searches are not supported"). The longest survey names trip this as soon as
# a word is appended.
LONG_PHRASE_CHARS = 80
LONG_PHRASE_CHUNK = 3

_OA_SELECT = ",".join([
    "id", "doi", "display_name", "publication_date", "publication_year",
    "type", "open_access", "authorships", "primary_location", "locations",
    "cited_by_count", "abstract_inverted_index", "language", "primary_topic",
])


class BudgetExceeded(RuntimeError):
    pass


class QueryError(RuntimeError):
    """We sent OpenAlex something it won't accept -- a bug in us, not a blip."""


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
                # A 4xx means WE built a bad request -- retrying sends the same
                # broken query twice more and then swallows it as a warning, so
                # the run finishes "successfully" with zero results. That is
                # exactly how the publication_date.gte filter bug stayed hidden.
                if 400 <= r.status_code < 500:
                    raise QueryError(
                        f"OpenAlex rejected the request ({r.status_code}): "
                        f"{r.text[:300]}\n  params: {params}")
                r.raise_for_status()
                self._track_spend(r.headers)
                return r.json()
            except (BudgetExceeded, QueryError):
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

        return {
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
            # all filled by the post-dedup Gate 2 pass
            "identity_score":      0,
            "use_score":           0,
            "relevance_score":     0,
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

    def search_family(self, family: dict,
                      since_date: Optional[str] = None,
                      family_index: int = 0,
                      total_families: int = 54,
                      verbose: bool = True) -> list[dict]:
        label  = family["label"]
        region = family["region"]
        terms  = family["terms"]

        # oa_id -> the parsed record already in results. When a LATER term in
        # this same family matches a work we've already seen, we add that
        # term to the existing record's survey_terms_matched instead of
        # dropping the match -- otherwise a paper that genuinely matches
        # several of a family's term variants (e.g. "Living Standards
        # Measurement Study" AND "LSMS-ISA") only ever gets credit for
        # whichever term happened to be searched first, and Gate 2's
        # multi-term signal never sees it.
        seen: dict = {}
        results: list = []

        if verbose:
            print(f"[{family_index}/{total_families}] {label} ({len(terms)} terms)", flush=True)

        for term, term_tier, term_hints, term_excl in keywords.iter_terms(family):
            if verbose:
                print(f"  >> {term[:60]}", flush=True)

            params_query: dict = {
                SEARCH_PARAM: build_search_query(term, term_tier, term_hints, term_excl),
                "select":   _OA_SELECT,
                "per_page": PAGE_SIZE,
            }
            if since_date:
                # NOT "publication_date.gte" -- OpenAlex rejects that with a
                # 400 and the whole run silently returns nothing.
                params_query["filter"] = f"from_publication_date:{since_date}"

            cursor = "*"
            pages  = 0
            n_rejected = 0
            n_merged = 0
            term_results: list = []

            while True:
                data = self._get({**params_query, "cursor": cursor})
                if not data:
                    break

                meta  = data.get("meta", {})
                items = data.get("results", [])

                if pages == 0:
                    n_found = meta.get("count") or 0
                    if verbose:
                        print(f"     {n_found} results", flush=True)
                    # A survey keyword matching this much means the gate isn't
                    # gating -- OpenAlex stems server-side, so a short acronym
                    # with a wide country list quietly turns into a different
                    # word ("LSMS"->"LSM") across a huge literature. Left
                    # unchecked it burns the whole daily budget on one term.
                    if n_found > BROAD_TERM_WARN:
                        print(f"     [warn] {term!r} matched {n_found:,} works — the "
                              "context gate is too loose for this term. Give it its "
                              "own narrower context_hints in keywords.py.", flush=True)
                if not items:
                    break

                for w in items:
                    oa_id = w.get("id", "")

                    if oa_id and oa_id in seen:
                        existing = seen[oa_id]
                        matched = {x.strip() for x in
                                  (existing.get("survey_terms_matched") or "").split(";") if x.strip()}
                        if term not in matched:
                            matched.add(term)
                            existing["survey_terms_matched"] = "; ".join(sorted(matched))
                            # tier travels with the term: a paper admitted on a
                            # generic phrase AND an unambiguous name deserves
                            # the credit for the unambiguous one at Gate 2.
                            tiers = {x.strip() for x in
                                    (existing.get("match_tier") or "").split(";") if x.strip()}
                            tiers.add(term_tier)
                            existing["match_tier"] = "; ".join(sorted(tiers))
                            n_merged += 1
                        continue

                    inv = w.get("abstract_inverted_index") or {}
                    if inv:
                        abstract_txt = " ".join(
                            wd for _, wd in sorted(
                                (p, wd) for wd, ps in inv.items() for p in ps))
                    else:
                        abstract_txt = ""
                    title_txt = w.get("display_name") or ""

                    ok, tier, reason = passes_filters(
                        title_txt, abstract_txt, term, term_tier,
                        context_hints=term_hints,
                        primary_topic=w.get("primary_topic"),
                    )
                    if not ok:
                        n_rejected += 1
                        continue

                    parsed = self._parse(w, label, region, [term])
                    parsed["match_tier"]   = tier
                    parsed["match_reason"] = reason
                    term_results.append(parsed)
                    if oa_id:
                        seen[oa_id] = parsed

                cursor = meta.get("next_cursor")
                pages += 1
                if pages > 1 and verbose:
                    print(f"     page {pages} ...", flush=True)
                if pages >= MAX_PAGES and cursor:
                    # silently truncating a term's results is the kind of thing
                    # that looks like a scoring bug months later
                    print(f"     [warn] hit the {MAX_PAGES}-page cap "
                          f"({MAX_PAGES * PAGE_SIZE} results) on {term!r} — "
                          "results truncated", flush=True)
                    break
                if not cursor:
                    break

            if verbose and (term_results or n_rejected or n_merged):
                msg = f"     kept {len(term_results)}"
                if n_merged:
                    msg += f"  (+{n_merged} merged into earlier matches)"
                if n_rejected:
                    msg += f"  (filtered out {n_rejected})"
                print(msg, flush=True)
            results.extend(term_results)

        if verbose:
            print(f"  --> {len(results)} total for {label}", flush=True)
            print(f"     session spend so far: ${self.session_spend:.4f}", flush=True)
        return results

    def _ids_matching(self, query: str, short_ids: list) -> set:
        """Which of these work IDs match the query? One call per id-batch."""
        hits: set = set()
        for i in range(0, len(short_ids), FULLTEXT_BATCH):
            batch = short_ids[i:i + FULLTEXT_BATCH]
            data = self._get({
                FULLTEXT_SEARCH_PARAM: query,
                "filter":   f"ids.openalex:{'|'.join(batch)}",
                "select":   "id",
                "per_page": FULLTEXT_BATCH,
            })
            for w in (data.get("results") or []):
                sid = (w.get("id") or "").rsplit("/", 1)[-1]
                if sid:
                    hits.add(sid)
        return hits

    def _proximity_hits(self, term: str, words: list, short_ids: list) -> set:
        """IDs where `term` sits within the window of any of `words`."""
        # OpenAlex refuses more than 3 quoted phrases of >80 chars OR'd
        # together ("Lots of long-phrase OR searches are not supported"). The
        # longest survey names blow past 80 as soon as a word is appended, so
        # those go out 3 at a time.
        longest = max((len(w) for w in words), default=0)
        chunk_size = (LONG_PHRASE_CHUNK
                      if len(term) + 1 + longest > LONG_PHRASE_CHARS
                      else FULLTEXT_WORD_CHUNK)
        hits: set = set()
        for i in range(0, len(words), chunk_size):
            chunk = words[i:i + chunk_size]
            clauses = " OR ".join(
                f'"{term} {w}"~{FULLTEXT_PROXIMITY_WINDOW}' for w in chunk)
            hits |= self._ids_matching(f"({clauses})", short_ids)
        return hits

    def fulltext_data_use_probe(self, papers: list[dict], verbose: bool = True,
                                skip_ids: Optional[set] = None) -> int:
        """
        Gate 2b: the full-text half of the use axis. Runs for every paper whose
        USE score is still short of relevance.USE_MIN -- note that's the use
        axis, not the total. A paper can be sitting on a mountain of identity
        evidence and still have no idea whether the data was used; that's
        exactly the paper this pass exists for.

        Four probes, graded by what each actually proved against the flagged
        set (see the word lists above -- every phrase was measured, not
        guessed):
          strong use near the term  -> STRONG use, +1 identity
          weak use near the term    -> WEAK use
          provenance near the term  -> WEAK use
          microdata catalogue cited -> flag only, no points (measured 2/2)

        Adds points and flags, never subtracts. No citation-format voiding --
        first-person phrasing is citation-immune by construction (a
        bibliography entry can't say "we use"). An earlier version voided a hit
        whenever the paper also cited the LSMS methodology paper, which is just
        normal practice for a good LSMS paper; it was confirmed cancelling real
        hits (ag.econ.258112) and was removed.
        """
        # Only papers that could still change verdict. Two exclusions:
        #  - use axis already met -> more evidence changes nothing
        #  - identity so low that even the +1 a strong hit grants can't reach
        #    IDENTITY_MIN -> the paper fails whatever the full text says
        skip_ids = skip_ids or set()
        candidates = [p for p in papers
                     if p.get("openalex_id")
                     and p.get("openalex_id") not in skip_ids
                     and (p.get("use_score") or 0) < relevance.USE_MIN
                     and (p.get("identity_score") or 0) + relevance.WEAK >= relevance.IDENTITY_MIN]
        if not candidates:
            return 0

        by_id = {p["openalex_id"].rsplit("/", 1)[-1]: p for p in candidates}

        # a paper sits in several term-groups if it matched several terms
        term_to_ids: dict = {}
        for short_id, p in by_id.items():
            for term in (s.strip() for s in
                        (p.get("survey_terms_matched") or "").split(";")):
                if term:
                    term_to_ids.setdefault(term, []).append(short_id)

        strong_hits: set = set()
        for term, term_ids in term_to_ids.items():
            strong_hits |= self._proximity_hits(term, FULLTEXT_USE_STRONG, term_ids)

        # A strong hit already clears the use axis on its own, so the weaker
        # probes below would only pile on points that change no verdict. Skip
        # them for those papers -- on a full run that's most of the calls.
        weak_hits: set = set()
        prov_hits: set = set()
        for term, term_ids in term_to_ids.items():
            # weak + provenance stack (1 + 1 = enough), so both still run for
            # every non-strong paper
            todo = [i for i in term_ids if i not in strong_hits]
            if not todo:
                continue
            weak_hits |= self._proximity_hits(term, FULLTEXT_USE_WEAK, todo)
            prov_hits |= self._proximity_hits(term, FULLTEXT_PROVENANCE_WORDS, todo)

        # catalogue citation is about the paper, not any one term -- one query
        # for the whole candidate set rather than per-term
        catalog_q = " OR ".join(f'"{p}"' for p in MICRODATA_CATALOG_PHRASES)
        catalog_hits = self._ids_matching(f"({catalog_q})", list(by_id))

        boosted = strong_hits | weak_hits | prov_hits | catalog_hits
        for short_id in boosted:
            p = by_id[short_id]
            flags = [f for f in (p.get("relevance_flags") or "").split(",") if f]
            gain = 0
            if short_id in strong_hits:
                gain += relevance.STRONG
                # proximity also confirms WHICH survey, so it corroborates identity
                p["identity_score"] = (p.get("identity_score") or 0) + relevance.WEAK
                flags.append("fulltext_first_person_use")
            if short_id in weak_hits:
                gain += relevance.WEAK; flags.append("fulltext_data_language")
            if short_id in prov_hits:
                gain += relevance.WEAK; flags.append("fulltext_provenance")
            if short_id in catalog_hits:
                flags.append("microdata_catalog_cited")   # reported, not scored
            p["use_score"] = (p.get("use_score") or 0) + gain
            p["relevance_flags"] = ",".join(flags)

        if verbose:
            print(f"  [fulltext probe] {len(boosted)}/{len(candidates)} candidates gained "
                  f"use evidence ({len(strong_hits)} strong, {len(weak_hits)} data-language, "
                  f"{len(prov_hits)} provenance, {len(catalog_hits)} catalogue) "
                  f"-- session spend: ${self.session_spend:.4f}", flush=True)
        return len(boosted)


class CrossrefFetcher:
    """
    Only when --crossref is set. Title index only, hard cap CR_MAX_RESULTS per
    term, terms >= 18 chars, to avoid the flood of false positives that a
    full-field query produces.

    Crossref gives no full text and no OpenAlex id, so Gate 2b can never run
    on these records -- their use axis has to come entirely from the abstract.
    Crossref abstracts are frequently missing outright, so expect most of
    these to land in the backup sheet. That's honest rather than broken: we
    genuinely can't tell whether the data was used from a title alone.
    """

    def __init__(self, api_key: str = ""):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "LSMS-Tracker/2.0"

    def _parse(self, item: dict, family_label: str, family_region: str,
               term: str, tier: str = "A") -> Optional[dict]:
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
            "peer_reviewed_auto": "Yes" if peer else "No",
            "open_access": False, "oa_url": "",
            "link": doi,
            "citation_count": item.get("is-referenced-by-count", 0),
            "abstract": item.get("abstract", ""),
            "language": "",
            "openalex_id": "",
            "authors": "; ".join(names),
            "first_author": names[0] if names else "",
            "n_authors": len(names),
            "affiliations": "",
            "affiliation_countries": "",
            # Crossref has no affiliation data we can trust, so this is "No"
            # rather than unknown -- Gate 2 must not read a missing field as
            # a signal either way.
            "wb_affiliation_auto": "No",
            "multilateral_affiliation": "",
            # the term was found in the TITLE (checked above), so admission is
            # as solid as tier A gets; keep the term's real tier though
            "match_tier": tier,
            "match_reason": "term present in title (Crossref title index)",
            "identity_score": 0, "use_score": 0,
            "relevance_score": 0, "relevance_flags": "",
            "survey_family": family_label,
            "survey_region": family_region,
            "survey_terms_matched": term,
            "source": "Crossref",
            "date_discovered": date.today().isoformat(),
            **geo,
        }

    def search_term(self, term: str, family: dict, tier: str = "A") -> list[dict]:
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
                parsed = self._parse(item, label, region, term, tier)
                if parsed:
                    results.append(parsed)
            offset += len(items)
            if len(items) < 100:
                break
        return results
