"""
matching.py — Gate 1. Decides whether a keyword hit is admitted as a candidate.

Admission only. Nothing here scores a paper or judges whether the data was
actually used -- that's Gate 2 (relevance.py). Keeping the two apart is what
stops "we found the name" and "they used the data" from being silently
conflated into one number.

Tiers (assigned per term in keywords.py):

  A  unambiguous name -> accept on the full-text hit.
  B  generic survey name -> needs a country context word + an allowed field.
  C  short acronym -> same gating as B, plus a case check.

For B and C the context requirement is compiled into the OpenAlex query
itself ("IHPS" AND ("malawi" OR "malawian")) so the server enforces it
against the FULL TEXT, not just the title/abstract we get back. That's the
whole point of the tier: a paper that only ever names the survey in its
methods section still matches. The local checks below therefore can't demand
the term sit in the title/abstract -- they only confirm, or in one specific
case (a C acronym present with the wrong casing) refute.

Everything goes out via OpenAlex's `search.exact` parameter (SEARCH_PARAM),
which does NOT stem. That matters more than any other single setting here:
under the default stemmed `search`, "LSMS" collapses to "LSM" and retrieves
the entire land-surface-model and LSM-tree literature -- 13,506 hits for a
single fiscal year against 709 unstemmed. OpenAlex's `.no_stem` filter was
added in May 2024 and then withdrawn as too costly to run (it is still listed
as a valid field name but returns 400), so `search.exact` is the supported
way to do this. Note it is still CASE-INSENSITIVE: "LSMs" and "LSMS" are the
same token to the server, which is exactly the residual collision the Tier C
case check below exists to catch.
"""

import re
import unicodedata
from typing import Optional

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"

# Terms at these tiers get the country + field gate.
GATED_TIERS = (TIER_B, TIER_C)

# Gate 1 searches the whole corpus, so a stem collision is catastrophic --
# unstemmed. Only one search parameter is allowed per request
# (search / search.exact / search.semantic), so this is the single place it's
# named.
SEARCH_PARAM = "search.exact"

# Gate 2b is different, and deliberately stemmed. Its queries always carry an
# `ids.openalex:` filter restricting them to an explicit list of already-
# admitted candidates, so a stem collision physically cannot pull in an
# unrelated paper the way it can at Gate 1. What stemming buys there is verb
# variants -- "supported by" also matching "supports"/"support" -- and that
# matters: unstemmed, the provenance probe went from 89 hits to 0, and the
# flagged-set score dropped 24/32 -> 23/32.
FULLTEXT_SEARCH_PARAM = "search"

# Tier B/C keeps a paper only when its OpenAlex FIELD is one of these. This is the
# `primary_topic.field.display_name` (26-field level), NOT the coarse 4-domain
# level — filtering on domain would be far too blunt. LSMS microdata turns up
# across all of these fields; anything outside is rejected.
_ALLOWED_FIELDS = {
    "Agricultural and Biological Sciences",
    "Business, Management and Accounting",
    "Computer Science",
    "Economics, Econometrics and Finance",
    "Energy",
    "Engineering",
    "Environmental Science",
    "Mathematics",
    "Medicine",
    "Nursing",
    "Social Sciences",
    "Health Professions",
    "Earth and Planetary Sciences",   # remote-sensing / satellite work uses LSMS
}


def strip_accents(s: str) -> str:
    # "Enquête" and "Enquete" have to match each other -- French survey names
    # get typed both ways and OpenAlex stores whichever the publisher sent.
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _flexible_term_pattern(term: str) -> str:
    # Inter-word gaps may be a space, newline, other whitespace, or nothing,
    # so a term still matches across line breaks and inside brackets.
    words = term.split()
    if len(words) <= 1:
        return re.escape(term)
    return r"\s*".join(re.escape(w) for w in words)


def build_search_query(term: str, tier: str, context_hints: Optional[list] = None,
                       exclusions: Optional[list] = None) -> str:
    # Tier A: bare quoted phrase. Tier B/C: fold the context requirement into
    # the query so OpenAlex enforces it against the full text —
    # "IHPS" AND ("malawi" OR "malawian"). Booleans upper-case, phrases quoted.
    # A NOT clause drops known same-spelling collisions (keywords.TERM_EXCLUSIONS)
    # before they're ever retrieved.
    q = '"' + term + '"'
    if tier in GATED_TIERS and context_hints:
        hints = " OR ".join('"' + h + '"' for h in context_hints)
        q = f"{q} AND ({hints})"
    if exclusions:
        nots = " OR ".join('"' + x + '"' for x in exclusions)
        q = f"{q} NOT ({nots})"
    return q


def word_present(word: str, text: str, case_sensitive: bool = False) -> bool:
    # Whole-word, accent-insensitive match. "niger" will not match inside
    # "Nigeria". \b only applies on a side that actually ends in a word
    # character -- \b can never match between two non-word chars, so an
    # unconditional \b...\b silently never matches a term like "ECVM/A" as it
    # appears in running text.
    word, text = strip_accents(word), strip_accents(text)
    flags = 0 if case_sensitive else re.IGNORECASE
    left  = r"\b" if word[:1].isalnum() or word[:1] == "_" else ""
    right = r"\b" if word[-1:].isalnum() or word[-1:] == "_" else ""
    return bool(re.search(left + _flexible_term_pattern(word) + right, text, flags))


def is_allowed_field(primary_topic: Optional[dict]) -> bool:
    # Permissive only when OpenAlex has no field at all, so missing metadata
    # does not throw away a real paper.
    if not primary_topic:
        return True
    field = (primary_topic.get("field") or {}).get("display_name", "")
    if not field:
        return True
    return field in _ALLOWED_FIELDS


def passes_filters(title: str, abstract: str, term: str, tier: str,
                   context_hints: Optional[list],
                   primary_topic: Optional[dict]) -> tuple[bool, str, str]:
    """
    Returns (admitted, tier, reason). The reason is stored on the paper so any
    admission can be traced back to why it happened.
    """
    if tier == TIER_A:
        return True, TIER_A, "unambiguous name (fulltext match accepted)"

    text = title + " " + abstract

    if not is_allowed_field(primary_topic):
        return False, tier, "field not in allowlist"

    # The one local check that can genuinely REFUTE a C hit: if the acronym is
    # sitting right there in the title/abstract but cased differently ("LSMs",
    # "Ihs"), that's a different token which OpenAlex's case-folding merged
    # into ours -- a collision, not our survey. If the acronym isn't in the
    # title/abstract at all we can't tell from here, and the query already
    # enforced acronym + country against the full text, so it stands.
    if tier == TIER_C:
        loose = word_present(term, text, case_sensitive=False)
        exact = word_present(term, text, case_sensitive=True)
        if loose and not exact:
            return False, TIER_C, "acronym present but wrong case (collision)"

    local_term    = word_present(term, text, case_sensitive=(tier == TIER_C))
    local_context = bool(context_hints) and any(word_present(h, text) for h in context_hints)

    if local_term and local_context:
        return True, tier, "name + country confirmed in title/abstract + allowed field"
    if local_term:
        return True, tier, "name in title/abstract, country enforced by query + allowed field"
    if local_context:
        return True, tier, "country in title/abstract, name enforced by query + allowed field"
    return True, tier, "name + country enforced by query (fulltext only) + allowed field"
