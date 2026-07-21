"""
matching.py — tier filter that decides whether a keyword hit is real.

Two tiers, set as data in keywords.py:

  A   unambiguous survey name. A full-text hit is accepted as-is.
  C   short/ambiguous acronym. Requires a case-sensitive hit, a country or
      context word somewhere in the document, and an allowed OpenAlex field.

For Tier C the context requirement is built into the OpenAlex search query
itself ("IHPS" AND ("Malawi" OR "Malawian")) so the server checks the full
text, not just the title/abstract we get back. That catches papers naming
the country only in the body. The local context check below is kept only as
a light confirmation/confidence signal — it is no longer a hard gate.
"""

import re
from typing import Optional

TIER_A = "A"
TIER_C = "C"

# Tier C keeps a paper only when its OpenAlex FIELD is one of these. This is the
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


def _flexible_term_pattern(term: str) -> str:
    # Inter-word gaps may be a space, newline, other whitespace, or nothing,
    # so a term still matches across line breaks and inside brackets.
    words = term.split()
    if len(words) <= 1:
        return re.escape(term)
    return r"\s*".join(re.escape(w) for w in words)


def build_search_query(term: str, tier: str, context_hints: Optional[list] = None) -> str:
    # Tier A: a bare quoted phrase. Tier C: fold the context requirement into
    # the query so OpenAlex enforces it against the full text —
    # "IHPS" AND ("Malawi" OR "Malawian"). Booleans upper-case, phrases quoted.
    base = '"' + term + '"'
    if tier == TIER_C and context_hints:
        hints = " OR ".join('"' + h + '"' for h in context_hints)
        return f"{base} AND ({hints})"
    return base


def word_present(word: str, text: str, case_sensitive: bool = False) -> bool:
    # Whole-word match. "niger" will not match inside "Nigeria".
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = r"\b" + _flexible_term_pattern(word) + r"\b"
    return bool(re.search(pattern, text, flags))


def has_world_bank_signal(text: str, urls: Optional[list] = None) -> bool:
    # A worldbank.org URL or "world bank" in the text raises Tier C confidence.
    if text and "world bank" in text.lower():
        return True
    for u in (urls or []):
        if u and "worldbank.org" in u.lower():
            return True
    return False


def is_allowed_field(primary_topic: Optional[dict]) -> bool:
    # Tier C field allowlist. Permissive only when OpenAlex has no field at all,
    # so missing metadata does not throw away a real paper.
    if not primary_topic:
        return True
    field = (primary_topic.get("field") or {}).get("display_name", "")
    if not field:
        return True
    return field in _ALLOWED_FIELDS


def passes_filters(title: str, abstract: str, term: str, tier: str,
                   context_hints: Optional[list],
                   primary_topic: Optional[dict],
                   urls: Optional[list] = None) -> tuple:
    """
    Master gate. Returns (passes, tier, reason).

    Tier A: unambiguous. Accepted on the full-text hit.
    Tier C: case-sensitive acronym present locally, plus an allowed field. The
    context requirement itself was already enforced server-side by the search
    query (build_search_query) against the full text — a local hit on
    title/abstract is only noted as extra confidence, not required, since the
    context word may sit only in the body.
    """
    text = title + " " + abstract

    if tier == TIER_A:
        return True, TIER_A, "unambiguous term (fulltext match accepted)"

    if not word_present(term, text, case_sensitive=True):
        return False, TIER_C, "acronym absent (case-sensitive check)"
    if not is_allowed_field(primary_topic):
        return False, TIER_C, "field not in allowlist"

    local_context = bool(context_hints) and any(word_present(h, text) for h in context_hints)
    if has_world_bank_signal(text, urls):
        return True, TIER_C, "acronym + query-enforced context + allowed field + World Bank signal"
    if local_context:
        return True, TIER_C, "acronym + context confirmed locally + allowed field"
    return True, TIER_C, "acronym + context enforced by query (not in title/abstract) + allowed field"
