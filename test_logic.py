"""
test_logic.py — sanity checks for the matching/scoring logic. No network.

    python test_logic.py

Covers the things that have actually broken before: tier gating, acronym
collisions, accent variants, and the identity-vs-use separation that stops a
paper which only mentions the survey from being counted as using it.
"""

import requests

import keywords
import relevance
from matching import (build_search_query, passes_filters, word_present,
                      strip_accents, TIER_A, TIER_B, TIER_C)
from dedup import deduplicate

ECON = {"field": {"display_name": "Economics, Econometrics and Finance"}}
CHEM = {"field": {"display_name": "Chemistry"}}

_MALAWI = ["malawi", "malawian"]


def check(label, cond):
    if not cond:
        raise AssertionError(label)
    print(f"  ok  {label}")


# ── word matching ────────────────────────────────────────────────────────────
def test_word_present():
    check("niger does not match inside Nigeria",
          not word_present("niger", "a study of Nigeria"))
    check("niger matches standalone",
          word_present("niger", "a study of Niger and its neighbours"))
    check("accents are ignored both ways",
          word_present("Enquête Agricole", "the Enquete Agricole was fielded"))
    check("term ending in punctuation still matches",
          word_present("ECVM/A", "we use the ECVM/A rounds"))
    check("case-sensitive rejects wrong case",
          not word_present("LSMS", "land surface models (LSMs) are", case_sensitive=True))
    check("case-sensitive accepts right case",
          word_present("LSMS", "the LSMS survey", case_sensitive=True))
    check("strip_accents is a no-op on ascii", strip_accents("abc") == "abc")


# ── gate 1 ───────────────────────────────────────────────────────────────────
def test_queries():
    # stemming is the single most important setting here: stemmed, "LSMS"
    # collapses to "LSM" and drags in land-surface-model papers
    from matching import SEARCH_PARAM
    check("queries go out unstemmed via search.exact",
          SEARCH_PARAM == "search.exact")
    check("tier A query is a bare phrase",
          build_search_query("LSMS-ISA", TIER_A, _MALAWI) == '"LSMS-ISA"')
    q_b = build_search_query("National Panel Survey", TIER_B, _MALAWI)
    check("tier B query ANDs the country context",
          q_b == '"National Panel Survey" AND ("malawi" OR "malawian")')
    check("tier C query ANDs the country context too",
          "AND" in build_search_query("IHPS", TIER_C, _MALAWI))

    # search.exact stops stemming but is still case-INsensitive, so "LSMs"
    # (land-surface models) is the same token as "LSMS" -- excluded by query
    q_x = build_search_query("LSMS", TIER_C, _MALAWI, keywords.TERM_EXCLUSIONS["LSMS"])
    check("colliding acronym gets a NOT clause",
          "NOT" in q_x and "land surface model" in q_x)
    check("a term with no exclusions gets no NOT clause",
          "NOT" not in build_search_query("IHPS", TIER_C, _MALAWI, []))


def test_admission():
    ok, tier, _ = passes_filters("A title", "an abstract", "LSMS-ISA", TIER_A, _MALAWI, CHEM)
    check("tier A ignores the field allowlist", ok and tier == TIER_A)

    ok, _, why = passes_filters("t", "a", "IHPS", TIER_C, _MALAWI, CHEM)
    check("tier C rejects a disallowed field", not ok and "field" in why)

    # the acronym is right there but cased differently -> collision, not us
    ok, _, why = passes_filters("Ihps in infants", "Ihps again", "IHPS", TIER_C, _MALAWI, ECON)
    check("tier C rejects a wrong-case acronym", not ok and "wrong case" in why)

    # not in title/abstract at all: can't refute, query already enforced it
    ok, _, why = passes_filters("Farm study", "no acronym here", "IHPS", TIER_C, _MALAWI, ECON)
    check("tier C accepts a fulltext-only acronym", ok and "fulltext only" in why)

    ok, _, _ = passes_filters("Malawi IHPS work", "uses IHPS", "IHPS", TIER_C, _MALAWI, ECON)
    check("tier C accepts acronym + country locally", ok)


def test_registry():
    # a hint appearing inside its own term makes the gate self-satisfying;
    # keywords._check_registry() runs at import, so getting here means it held
    check("registry passes its own self-check", keywords.SURVEY_FAMILIES)
    check("every term has a known tier",
          all(t in ("A", "B", "C") for f in keywords.SURVEY_FAMILIES
              for _, t, _h, _x in keywords.iter_terms(f)))
    check("Living Standards Survey is gated, not tier A",
          keywords.term_tier("Living Standards Survey") == TIER_B)
    check("Ghana is a recognised LSMS country",
          "ghana" in keywords.LSMS_COUNTRY_HINTS)

    # every gated term must actually have hints, else it's admitted ungated
    for f in keywords.SURVEY_FAMILIES:
        for term, tier, hints, _x in keywords.iter_terms(f):
            if tier != TIER_A and not hints:
                raise AssertionError(f"{term!r} is tier {tier} with no context hints")
    check("every tier B/C term has context hints", True)

    # countries come from the World Bank's own LSMS catalog collection, so the
    # first two LSMS countries ever surveyed have to be in there
    for c in ("cote d'ivoire", "peru", "ghana", "vietnam", "albania"):
        if c not in keywords.LSMS_COUNTRY_HINTS:
            raise AssertionError(f"{c!r} missing from LSMS_COUNTRY_HINTS")
    check("classic LSMS countries are covered", True)
    check("ISA countries are a subset of the full LSMS list",
          set(keywords.ISA_COUNTRY_HINTS) <= set(keywords.LSMS_COUNTRY_HINTS))


def test_query_url_length():
    # widest family x longest term is the one that can overrun
    worst = 0
    for f in keywords.SURVEY_FAMILIES:
        for term, tier, hints, _x in keywords.iter_terms(f):
            q = build_search_query(term, tier, hints)
            url = requests.Request("GET", "https://api.openalex.org/works", params={
                "search.exact": q, "per_page": 200, "cursor": "*",
                "select": "id,doi,display_name,publication_date,publication_year,type,"
                          "open_access,authorships,primary_location,locations,"
                          "cited_by_count,abstract_inverted_index,language,primary_topic",
                "api_key": "x" * 24,
            }).prepare().url
            worst = max(worst, len(url))
    check(f"worst-case query URL stays under the 4KB limit ({worst})", worst < 4000)


# ── gate 2 ───────────────────────────────────────────────────────────────────
def _rank(title="", abstract="", oa_type="article", wb=False,
          fams=("Uganda UNPS",), terms=("Uganda National Panel Survey",), tiers=("A",)):
    return relevance.rank(title=title, abstract=abstract, oa_type=oa_type,
                          wb_affiliation=wb, survey_families=list(fams),
                          survey_terms=list(terms), match_tiers=list(tiers))


def test_mention_vs_use():
    # the case Amparo flagged: names the survey everywhere, never uses it
    mention = _rank(
        title="Uganda National Panel Survey: a programme overview",
        abstract="The Uganda National Panel Survey is a World Bank effort in Uganda. "
                 "It has run for many years and is widely cited.",
        wb=True)
    check("pure mention has identity", mention.identity >= relevance.IDENTITY_MIN)
    check("pure mention has no use evidence", mention.use < relevance.USE_MIN)
    check("pure mention does NOT pass",
          not relevance.passes(mention.identity, mention.use, mention.flags))

    used = _rank(
        title="Shocks and consumption in Uganda",
        abstract="We use the Uganda National Panel Survey to estimate the effect of "
                 "rainfall shocks on household consumption and poverty in Uganda.")
    check("real use passes",
          relevance.passes(used.identity, used.use, used.flags))
    check("real use is tied to the survey",
          "use_language_tied_strong" in used.flags)


def test_untied_use_is_capped():
    # empirical paper, uses SOME data, but never names the survey in the
    # abstract -- untied evidence must not be able to carry the use axis
    untied = _rank(
        title="Rainfall and welfare",
        abstract="We use household survey data to estimate a regression of consumption "
                 "on rainfall. Poverty and expenditure outcomes are examined.")
    check("untied use evidence is capped below the threshold",
          untied.use < relevance.USE_MIN)
    check("untied flag is recorded", "use_language_untied" in untied.flags)


def test_review_needs_strong_evidence():
    weak_review = _rank(
        title="Agricultural input subsidies: a review",
        abstract="This study reviews the evidence on input subsidies. Data come from "
                 "the Uganda National Panel Survey and other sources, covering poverty, "
                 "consumption and household welfare.")
    check("review language is flagged", "review_language" in weak_review.flags)
    check("review with only weak use evidence does not pass",
          not relevance.passes(weak_review.identity, weak_review.use, weak_review.flags))

    strong_review = _rank(
        title="Input subsidies reviewed",
        abstract="This paper reviews the literature. We use the Uganda National Panel "
                 "Survey microdata to re-estimate household consumption and poverty.")
    check("review that re-analyses the data does pass",
          relevance.passes(strong_review.identity, strong_review.use, strong_review.flags))


def test_pub_type_veto():
    s = _rank(title="Uganda National Panel Survey", abstract="We use the data.",
              oa_type="dataset")
    check("vetoed pub type scores zero on both axes", s.identity == 0 and s.use == 0)
    check("vetoed pub type never passes",
          not relevance.passes(s.identity, s.use, s.flags))
    check("editorial is NOT vetoed", not relevance.is_excluded_pub_type("editorial"))


def test_identity_needs_more_than_affiliation():
    # a World Bank author writing about something unrelated shouldn't clear
    # identity on the affiliation alone
    s = _rank(title="Urban transport pricing", abstract="A theoretical model.",
              wb=True, fams=(), terms=(), tiers=())
    check("wb affiliation alone does not establish identity",
          s.identity < relevance.IDENTITY_MIN)


def test_tier_a_beats_bc_on_identity():
    a  = _rank(title="x", abstract="y", tiers=("A",))
    bc = _rank(title="x", abstract="y", tiers=("C",))
    check("tier A admission scores higher identity than tier C", a.identity > bc.identity)


# ── dedup ────────────────────────────────────────────────────────────────────
def test_dedup_merges_without_blanks():
    a = {"openalex_id": "W1", "doi": "10.1/x", "title": "T",
         "survey_terms_matched": "LSMS-ISA", "survey_family": "LSMS Core Program",
         "match_tier": "A", "dataset_country": ""}
    b = {"openalex_id": "W1", "doi": "10.1/x", "title": "T",
         "survey_terms_matched": "LSMS", "survey_family": "LSMS Core Program",
         "match_tier": "C", "dataset_country": "Uganda"}
    clean, _ = deduplicate([a, b])
    check("duplicates collapse to one record", len(clean) == 1)
    check("terms merge", clean[0]["survey_terms_matched"] == "LSMS; LSMS-ISA")
    check("tiers merge", clean[0]["match_tier"] == "A; C")
    check("an empty field doesn't leave a stray separator",
          clean[0]["dataset_country"] == "Uganda")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        print(f"\n{fn.__name__}")
        fn()
    print("\nall checks passed")
