"""
relevance.py — Gate 2. Of the papers Gate 1 admitted, which ones actually USED
the survey data?

Two independent axes, both of which must clear their own threshold:

  IDENTITY  is this really one of our surveys, or a name collision / a
            different country's survey that happens to share a phrase?
  USE       did the authors work with the microdata, or do they just mention
            it -- cite it, credit it, list it as related work?

Scoring them as one number is what lets a paper pass on identity alone: name
the survey three times in an abstract, add a World Bank co-author, and a pure
literature review outscores a real empirical paper. Keeping the axes apart
makes "mentions but does not use" structurally impossible to pass, which is
the whole point.

STRONG = 2, WEAK = 1, both axes need 2. So one strong signal clears an axis,
two weak ones clear it, one weak one doesn't.

The one subtlety worth knowing about is TIED vs UNTIED use evidence. "We use
household survey data" in an abstract proves the authors used *some* data --
not that they used *ours*. Only evidence that ties the use language to the
survey itself counts fully: full-text proximity (Gate 2b puts the two within
40 words of each other) or an abstract that names the survey and describes
using data. Untied evidence is capped at UNTIED_CAP so it can never, on its
own, carry the use axis.
"""

from typing import NamedTuple

import keywords
from matching import word_present, TIER_A, TIER_B, TIER_C

STRONG = 2
WEAK = 1

IDENTITY_MIN = 2
USE_MIN = 2

# Generic empiricism ("we estimate", "regression", "household") says the paper
# is empirical, not that it touched OUR data. Capped so it can corroborate a
# real tied signal but never substitute for one.
UNTIED_CAP = 1

# The exact six publication types that can never be a genuine empirical use
# of the survey data. Exhaustive -- do not add without checking first.
# Sourced from OpenAlex's own `type` field. Editorial is deliberately NOT here.
EXCLUDED_PUB_TYPES = {
    "conference-abstract", "dataset", "paratext",
    "erratum", "letter", "software",
}

# A review that genuinely re-analyses the microdata still passes -- it just has
# to show a STRONG tied use signal rather than coasting on weak ones. Reviews
# are the single biggest "mentions but doesn't use" category, so the bar is
# raised rather than the paper being vetoed outright.
_REVIEW_PATTERNS = [
    "systematic review", "meta-analysis", "meta analysis", "scoping review",
    "bibliometric", "narrative review", "rapid review", "umbrella review",
    "we conducted a review", "this review article", "this review",
    "literature review", "review of the literature",
    "this paper reviews", "this article reviews", "this study reviews",
    "we survey the literature", "we review the",
    "reviews the evidence", "synthesis of the evidence", "evidence synthesis",
]

# Author describing their OWN analysis. A bibliography entry can't say "we
# use" -- third person is structural for a citation -- so these are immune to
# the reference-list confound that sinks generic data vocabulary.
_USE_PATTERNS_STRONG = [
    "we use", "we used", "we draw on", "we drew on", "we employ", "we exploit",
    "we analyse", "we analyze", "we estimate", "we obtained", "we collected",
    "this paper uses", "this study uses", "this paper draws on",
    "our analysis", "our sample", "our data", "our estimates",
    "using data from", "data collected", "household-level data", "microdata",
]

# Data-use language that could equally describe someone else's data or the
# method in general.
_USE_PATTERNS_WEAK = [
    "data come from", "data are from", "data is from", "data drawn from",
    "draw on data", "drawing on data", "drawing on the", "drawn from the",
    "based on data", "based on the survey", "relying on data", "relies on data",
    "panel data from", "survey data from", "dataset from", "primary data",
    "nationally representative", "collected as part of",
    "utilizing data", "utilising data", "using the survey",
]

_EMPIRICAL_SIGNALS = [
    "regression", "estimate", "coefficient", "ols ", "2sls", "probit", "logit",
    "instrumental variable", "household", "consumption", "expenditure",
    "welfare", "poverty", "income", "fixed effect", "random effect",
]

# Set here and by Gate 2b (fetchers.fulltext_data_use_probe). Any one of these
# satisfies the "reviews need real evidence" rule.
STRONG_USE_FLAGS = {
    "use_language_tied_strong",
    "fulltext_first_person_use",
    "microdata_catalog_cited",
}

# Every known survey name, across every family -- not just the one that
# admitted this paper. rank() only ever sees papers that already cleared Gate
# 1, so this is not the corpus-wide collision risk that justifies tier gating
# at admission; an author naming a sister survey in their own abstract is
# ordinary and worth crediting. Tier A/B are long phrases (case carries no
# information); Tier C acronyms keep the case discipline.
_TIER_AB_TERMS = [t.lower() for t in
                  keywords.terms_by_tier(TIER_A) + keywords.terms_by_tier(TIER_B)
                  if len(t.strip()) > 4]
_TIER_C_TERMS = keywords.terms_by_tier(TIER_C)

_ALL_COUNTRY_HINTS = keywords.LSMS_COUNTRY_HINTS


class Score(NamedTuple):
    identity: int
    use: int
    flags: list
    veto: str          # "" unless an absolute exclusion fired

    @property
    def total(self) -> int:
        # Sorting/triage in the workbook only -- never pass/fail.
        return self.identity + self.use


def is_excluded_pub_type(oa_type: str) -> bool:
    return (oa_type or "").strip().lower() in EXCLUDED_PUB_TYPES


def has_review_language(text: str) -> bool:
    return any(p in text for p in _REVIEW_PATTERNS)


def names_any_survey(text: str) -> bool:
    low = text.lower()
    if any(t in low for t in _TIER_AB_TERMS):
        return True
    return any(word_present(t, text, case_sensitive=True) for t in _TIER_C_TERMS)


def passes(identity: int, use: int, flags) -> bool:
    """Both axes, plus the raised bar for reviews. Single source of truth."""
    if identity < IDENTITY_MIN or use < USE_MIN:
        return False
    if "review_language" in flags and not (set(flags) & STRONG_USE_FLAGS):
        return False
    return True


def _program_named(abstract: str, survey_families: list) -> bool:
    # "World Bank" is deliberately NOT checked. It shows up in funding lines,
    # acknowledgements and unrelated citations across most of development
    # economics -- as an identity signal for a specific survey it's noise.
    # "LSMS"/"living standards measurement" is real corroboration, but only
    # for families where it isn't the matched term itself (otherwise it just
    # re-detects the string that caused admission).
    a = (abstract or "").lower()
    if "LSMS Core Program" in survey_families:
        return False
    return "lsms" in a or "living standards measurement" in a


def rank(*, title: str, abstract: str, oa_type: str, wb_affiliation: bool,
         survey_families: list, survey_terms: list, match_tiers: list) -> Score:
    """
    Gate 2a: text + metadata only, no network. Gate 2b adds use points later
    for anything whose use axis is still short.
    """
    if is_excluded_pub_type(oa_type):
        return Score(0, 0, [f"excluded_pub_type_{(oa_type or '').strip().lower()}"],
                     veto="excluded_pub_type")

    title = title or ""
    abstract = abstract or ""
    a = abstract.lower()
    full = (title + " " + abstract).lower()

    ident, use, untied = 0, 0, 0
    flags: list = []

    # ── identity ────────────────────────────────────────────────────
    named_in_title    = names_any_survey(title)
    named_in_abstract = names_any_survey(abstract)

    if named_in_title:
        ident += STRONG; flags.append("survey_in_title")
    if named_in_abstract:
        ident += STRONG; flags.append("survey_in_abstract")

    # How it got admitted. An unambiguous name is worth more than a generic
    # phrase or an acronym that needed country gating to be believable.
    if TIER_A in match_tiers:
        ident += STRONG; flags.append("admitted_tier_a")
    elif match_tiers:
        ident += WEAK; flags.append("admitted_tier_bc_only")

    if len(set(survey_families)) >= 2:
        ident += STRONG; flags.append(f"multi_family_{len(set(survey_families))}")

    # Orthographic variants of ONE survey name ("LSMS", "LSMS-ISA", "Living
    # Standards Measurement Study") are the same evidence written three ways,
    # not three independent findings -- weak, and identity-only.
    if len(set(survey_terms)) >= 2:
        ident += WEAK; flags.append(f"multi_term_{len(set(survey_terms))}")

    if any(word_present(h, full) for h in _ALL_COUNTRY_HINTS):
        ident += WEAK; flags.append("country_in_text")

    if _program_named(abstract, survey_families):
        ident += WEAK; flags.append("program_named")

    if wb_affiliation:
        ident += WEAK; flags.append("wb_affiliation")

    # ── use ─────────────────────────────────────────────────────────
    strong_use_words = any(p in a for p in _USE_PATTERNS_STRONG)
    weak_use_words   = any(p in a for p in _USE_PATTERNS_WEAK)

    # Tied only when the same abstract also names the survey -- otherwise all
    # we know is that they used some data, somewhere.
    if named_in_abstract and strong_use_words:
        use += STRONG; flags.append("use_language_tied_strong")
    elif named_in_abstract and weak_use_words:
        use += WEAK; flags.append("use_language_tied_weak")
    elif strong_use_words or weak_use_words:
        untied += WEAK; flags.append("use_language_untied")

    if sum(1 for e in _EMPIRICAL_SIGNALS if e in full) >= 3:
        untied += WEAK; flags.append("empirical_vocabulary")

    use += min(untied, UNTIED_CAP)

    if has_review_language(full):
        flags.append("review_language")

    return Score(ident, use, flags, veto="")
