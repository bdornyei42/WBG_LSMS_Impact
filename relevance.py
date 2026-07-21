"""
relevance.py — how likely a matched paper actually USES the survey data
(vs merely citing it). Score 0-3; only 2 and above reach the Papers sheet.

  3  survey term in the TITLE
  2  survey term in the ABSTRACT, explicit data-use language, a fuzzy survey
     match near data-use words, LSMS/World Bank named, or 3+ empirical signals
  1  some evidence, but weak
  0  a review / meta-analysis

flags == "no_strong_signal" means the term never appeared in title or abstract,
no data-use language, no empirical vocabulary, no LSMS/World Bank mention. Only
OpenAlex's full-text index tied the paper to the keyword. These route to backup.
"""

import re

_USE_PATTERNS    = ["using data from","we use","we analyze","we analyse","we employ",
                    "data come from","data are from","data is from","data drawn from",
                    "draw on data","this paper uses","this study uses","this study analyzes",
                    "this paper analyzes","this paper analyses","using the survey",
                    "household-level data","microdata","panel data from","survey data from",
                    "dataset from","we exploit","primary data","nationally representative",
                    "drawing on data","drawing on the","drawn from the","based on data",
                    "based on the survey","relying on data","relies on data","data collected",
                    "data collected by","collected as part of","this data comes from",
                    "utilizing data","utilising data",]
_REVIEW_PATTERNS = [
    # Only TRUE reviews/meta-analyses — NOT viewpoints, overviews, or practice guides
    "systematic review", "meta-analysis", "scoping review", "bibliometric",
    "narrative review", "rapid review",
    "we conducted a review", "this review article",
    "literature review of", "review of the literature",
    # Definitively NOT empirical papers:
    "this paper reviews the", "we survey the literature",
]
# NOTE: "overview of" and generic "this paper reviews" removed — too aggressive.
# A paper that "provides an overview of [LSMS survey results]" is still an LSMS paper.
_EMPIRICAL_SIGNALS = ["regression","estimate","coefficient","ols ","2sls","probit","logit",
                      "instrumental variable","household","consumption","expenditure",
                      "welfare","poverty","income","fixed effect","random effect",]

# Words that, found near a survey-name mention, indicate the paper actually
# uses that survey's data — looser than _USE_PATTERNS since it only has to
# fire within a tight window around a term already known to be present.
_PROXIMITY_DATA_WORDS = [
    "data", "survey", "dataset", "sample", "collected", "fielded",
    "administered", "drawing", "drawn", "based", "utilized", "utilised",
    "used", "using", "employ", "employed", "wave", "panel", "microdata",
    "respondents", "households", "conducted", "representative",
]
_PROXIMITY_WINDOW_CHARS = 175   # characters to each side of the fuzzy match


def _fuzzy_survey_pattern(term: str):
    # Match each word as a prefix so "Ethiopia" also catches "Ethiopian".
    words = [w for w in re.split(r"\s+", term.strip()) if w]
    if not words:
        return None
    parts = [r"\b" + re.escape(w) + r"\w*" for w in words]
    pattern = r"\s+".join(parts)
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def _proximity_data_use_match(terms: list, abstract_original_case: str) -> bool:
    # Fuzzy-match each survey term, then check ~175 chars either side for data
    # words. The name itself is cut from the window first, so words inside the
    # name ("survey", "panel") can't satisfy the check on their own.
    if not abstract_original_case:
        return False
    for term in terms:
        if len(term.strip()) <= 4:
            continue
        pattern = _fuzzy_survey_pattern(term)
        if not pattern:
            continue
        m = pattern.search(abstract_original_case)
        if not m:
            continue
        left  = abstract_original_case[max(0, m.start() - _PROXIMITY_WINDOW_CHARS):m.start()]
        right = abstract_original_case[m.end():m.end() + _PROXIMITY_WINDOW_CHARS]
        window = (left + " " + right).lower()
        if any(re.search(r"\b" + re.escape(w) + r"\b", window)
               for w in _PROXIMITY_DATA_WORDS):
            return True
    return False


def _worldbank_url_signal(urls) -> str:
    # Returns "microdata" if a worldbank microdata-catalog URL is present,
    # "worldbank" for any other worldbank.org / World Bank repository URL, else "".
    joined = " ".join(u for u in (urls or []) if u).lower()
    if "microdata.worldbank.org" in joined:
        return "microdata"
    if ("worldbank.org" in joined
            or "openknowledge.worldbank.org" in joined
            or "hdl.handle.net/10986" in joined):   # 10986 = World Bank repository
        return "worldbank"
    return ""


def relevance_score(title: str, abstract: str, survey_terms_matched: str,
                    *, wb_affiliation: bool = False, urls=None) -> tuple:
    """
    Returns (score 0-3, flags str). See module docstring.

    Optional keyword-only signals (both default off, so the 3-argument call is
    byte-for-byte the yesterday behaviour):
      wb_affiliation  a World Bank author affiliation was detected
      urls            the paper's OpenAlex location URLs, checked for a
                      worldbank.org / microdata.worldbank.org signal
    A World Bank microdata URL, any worldbank.org/repository URL, or a WB author
    affiliation each lift the score to at least 2 — these are strong evidence the
    paper actually uses the microdata rather than merely citing it.
    """
    t     = (title or "").lower()
    a     = (abstract or "").lower()
    full  = t + " " + a
    terms = [s.strip().lower() for s in (survey_terms_matched or "").split(";")
             if len(s.strip()) > 4]

    score = 1
    flags = []

    # (1) Survey term appears in the TITLE — strongest possible signal
    if any(term in t for term in terms):
        score = 3
        flags.append("survey_in_title")

    # (2) Survey term appears in the ABSTRACT — very strong signal
    elif any(term in a for term in terms):
        score = max(score, 2)
        flags.append("survey_in_abstract")

    # (3) Explicit data-use language in the abstract
    if any(p in a for p in _USE_PATTERNS):
        score = max(score, 2)
        flags.append("use_language_in_abstract")

    # (3b) Fuzzy survey match near data-use vocabulary in the abstract
    if "survey_in_abstract" not in flags and "use_language_in_abstract" not in flags:
        if _proximity_data_use_match(terms, abstract or ""):
            score = max(score, 2)
            flags.append("proximity_data_use_match")

    # (4) The programme itself is named (LSMS / World Bank survey work)
    if any(p in full for p in ("lsms", "living standards measurement",
                               "world bank")):
        score = max(score, 2)
        flags.append("lsms_or_worldbank_named")

    # (5) Empirical-paper vocabulary
    emp = sum(1 for e in _EMPIRICAL_SIGNALS if e in full)
    if emp >= 3:
        score = max(score, 2)
        flags.append(f"empirical_signals_{emp}")

    # (6) Review / meta-analysis penalty
    if any(r in full for r in _REVIEW_PATTERNS):
        score = max(0, score - 2)
        flags.append("review_or_meta_analysis")

    # (7) External evidence of real data use (World Bank affiliation / URLs).
    # Applied after the base score so a bare, signal-less abstract on a genuine
    # World Bank data paper is no longer stranded at 1.
    if wb_affiliation:
        score = max(score, 2)
        flags.append("wb_affiliation")
    _wb_url = _worldbank_url_signal(urls)
    if _wb_url == "microdata":
        score = max(score, 2)
        flags.append("worldbank_microdata_url")
    elif _wb_url == "worldbank":
        score = max(score, 2)
        flags.append("worldbank_url")

    return max(0, min(3, score)), (",".join(flags) if flags else "no_strong_signal")
