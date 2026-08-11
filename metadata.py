"""
metadata.py — auto-detected columns computed from OpenAlex records.

Nothing here needs manual coding: affiliations, topics, dataset country,
publication type, and journal tier are all derived from what OpenAlex returns.
"""

_WB_NAMES = {
    "world bank", "world bank group", "international finance corporation",
    "ibrd", "ida ", "international development association",
}

_MULTILAT_MAP = {
    "IFPRI":  ["international food policy research", "ifpri"],
    "FAO":    ["food and agriculture organization", "fao"],
    "IFAD":   ["international fund for agricultural development", "ifad"],
    "CGIAR":  ["cgiar", "cimmyt", "cip ", "ilri", "cifor", "bioversity",
               "worldfish", "iita", "icarda", "icrisat", "iwmi"],
    "WFP":    ["world food programme", "wfp"],
    "UNICEF": ["unicef"],
    "WHO":    ["world health organization", "who "],
    "UNDP":   ["undp", "united nations development programme"],
    "IMF":    ["international monetary fund", "imf"],
    "AfDB":   ["african development bank", "afdb"],
    "UN":     ["united nations"],
}

_TOPIC_KEYWORDS = {
    "Agricultural Prod":        ["crop", "yield", "harvest", "farm production", "agricultural output",
                                 "maize", "rice", "wheat", "sorghum", "cassava", "groundnut", "livestock"],
    "Agricultural Inputs":      ["fertilizer", "seed", "input", "pesticide", "irrigation", "extension"],
    "Market & Value Chain":     ["market", "value chain", "price transmission", "trade"],
    "Env. & Climate Change":    ["climate", "rainfall", "drought", "temperature", "flood",
                                 "environment", "deforestation"],
    "Other Livelihoods":        ["livelihood", "off-farm", "diversification", "non-farm"],
    "Labor & Time Use":         ["labor", "labour", "employment", "wage", "work", "time use"],
    "Finance":                  ["credit", "loan", "microfinance", "savings", "financial inclusion",
                                 "remittance", "mobile money"],
    "Health":                   ["health", "mortality", "disease", "malaria", "hiv", "stunting",
                                 "maternal", "child health", "morbidity"],
    "Nutrition & Food Security":["nutrition", "food security", "hunger", "dietary", "malnutrition",
                                 "wasting", "anaemia", "anemia"],
    "Gender":                   ["gender", "women", "female", "girl", "empowerment", "intrahousehold"],
    "Poverty, Income, & Welfare":["poverty", "welfare", "consumption", "expenditure", "income",
                                  "living standard", "inequality", "wealth"],
    "Education & Training":     ["education", "school", "learning", "literacy", "dropout", "enrolment"],
}

_FAMILY_COUNTRY = {
    "Burkina Faso EMC / EHCVM": "Burkina Faso",
    "Ethiopia ESS / ESPS":      "Ethiopia",
    "Malawi IHS / IHPS":        "Malawi",
    "Mali EACI":                "Mali",
    "Niger ECVMA":              "Niger",
    "Nigeria GHS-Panel":        "Nigeria",
    "Tanzania NPS":             "Tanzania",
    "Uganda UNPS":              "Uganda",
}
_HFPS_COUNTRY_TERMS = {
    "Burkina Faso": "burkina", "Mali": "mali", "Nigeria": "nigeria",
    "Niger": "niger", "Ethiopia": "ethiopia", "Uganda": "uganda",
    "Malawi": "malawi", "Tanzania": "tanzania",
}
_ISA_COUNTRIES = ["Burkina Faso", "Ethiopia", "Malawi", "Mali", "Niger",
                  "Nigeria", "Tanzania", "Uganda"]


def detect_wb(authorships: list) -> str:
    for a in authorships:
        for inst in a.get("institutions", []):
            name = inst.get("display_name", "").lower()
            if any(wb in name for wb in _WB_NAMES):
                return "Yes"
    return "No"


def detect_multilat(authorships: list) -> str:
    found = []
    for org_label, patterns in _MULTILAT_MAP.items():
        for a in authorships:
            for inst in a.get("institutions", []):
                name = inst.get("display_name", "").lower()
                if any(p in name for p in patterns):
                    if org_label not in found:
                        found.append(org_label)
    return "; ".join(found) if found else ""


def auto_topics(title: str, abstract: str) -> dict:
    text = (title + " " + abstract).lower()
    return {topic: ("Auto" if any(k in text for k in kws) else "")
            for topic, kws in _TOPIC_KEYWORDS.items()}


def dataset_countries(survey_family: str, survey_terms_matched: str) -> dict:
    out = {c: "" for c in _ISA_COUNTRIES}
    country = _FAMILY_COUNTRY.get(survey_family)
    if country:
        out[country] = "Yes"
    # HFPS carries its country in the term name.
    if "HFPS" in survey_family or "High-Frequency" in survey_family:
        for term in (survey_terms_matched or "").split(";"):
            term_l = term.strip().lower()
            for c, hint in _HFPS_COUNTRY_TERMS.items():
                if hint in term_l:
                    out[c] = "Yes"
    # Multi-family papers carry several families joined by "; ".
    for fam in survey_family.split("; "):
        c2 = _FAMILY_COUNTRY.get(fam.strip())
        if c2:
            out[c2] = "Yes"
    return out


# Real journal names that happen to contain a repo/working-paper marker as a
# substring (e.g. "Organization" contains "iza", "Archives of Public Health"
# contains "archive"). Checked before the marker loops so these never get
# swept into the WP/repository bucket. Add here, not by widening the markers.
_VENUE_TYPE_OVERRIDES = {
    "bulletin of the world health organization",
    "journal of economic behavior & organization",
    "journal of agricultural & food industrial organization",
    "globalization and health",
    "environment and urbanization asia",
    "journal of social & organizational matters",
    "journal of organizational behavior research",
    "research in globalization",
    "international journal of organizational analysis",
    "archives of public health",
    "archives of trauma and emergency medicine",
    "journal of the royal statistical society series a (statistics in society)",
    "journal of the royal statistical society series b (statistical methodology)",
    "cephalalgia",
    "bmj open ophthalmology",
    "bmc ophthalmology",
    "socioeconomic challenges",
    "challenges",
}


def detect_pub_type(oa_type: str, venue: str) -> str:
    """Classify the real output type. OpenAlex's own `type` alone is not enough."""
    v = (venue or "").lower()
    t = (oa_type or "").lower()

    if v.strip() in _VENUE_TYPE_OVERRIDES:
        return "Journal Article"

    _REPO_MARKERS = (
        "repository", "repositories", "archive", "eprints", "escholarship",
        "scholarship", "research online", "research commons", "open research",
        "digital commons", "academic commons", "brage", "dash", "dspace",
        "udspace", "tspace", "vtechworks", "deep blue", "doria", "duo research",
        "epsilon", "figshare", "mendeley data", "dataverse", "harvard dataverse",
        "icpsr", "swedish national data", "networked services", "dans",
        "institutional repository", "knowledge repository", "open knowledge",
        "research archive", "publications explorer", "research portal",
        "research product catalog", "researchspace", "scholarspace",
        "open repository", "doctoral", "theses", "thesis", "dissertation",
        "etd", "phd", "e-zone", "runde", "macau", "refubium", "bibsys",
        "agecon search", "agecon", "core (", "semantic scholar", "openalex",
        "zenodo", "preprints.org", "research square", "ssoar", "munich personal repec",
        "mpra", "ageconsearch", "knowledge for policy", "opendata",
    )
    _EBOOK_MARKERS = (
        "ebooks", "ebook", "university press", "press ebooks", "elsevier",
        "springer", "palgrave", "edward elgar", "mit press", "intechopen",
        "cambridge university press", "oxford university press", "sage encyclopedia",
        "lambert academic", "ecorfan", "practical action publishing",
        "in-house reproduction", "umi ebooks", "united nations ebooks",
        "world bank ebooks", "fao ebooks", "ilo ebooks", "cifor ebooks",
        "world bank publications", "world bank open knowledge",
    )
    _WP_MARKERS = (
        "working paper", "discussion paper", "technical paper",
        "national bureau of economic research", "nber", "repec",
        "research papers in economics", "econstor", "ssrn", "cepr",
        "policy research working paper", "opengrey", "opendocs",
        # "hal" and "iza" alone are too generic (they're substrings of
        # "Ophthalmology", "Cephalalgia", "Organization", etc.) — matched
        # by their specific archive names instead. Same for bare "series",
        # a substring of many real journal titles (Journal of the Royal
        # Statistical Society *Series* A, Marine Ecology Progress *Series*).
        "hal (le centre pour la communication scientifique directe",
        "archives-ouvertes", "halshs",
        "iza discussion", "iza dp",
        "open science framework", "osf", "preprint", "arxiv", "philpapers",
        "contributions to economics", "research series",
        "staff country report", "staff discussion note",
    )

    if t == "book-chapter" or any(x in v for x in _EBOOK_MARKERS):
        return "Book / eBook"
    if t == "report":
        return "Report"
    if t == "dissertation" or any(x in v for x in ("theses", "thesis", "dissertation", "doctoral", "etd")):
        return "Thesis / Dissertation"
    if t == "preprint" or "arxiv" in v or "preprint" in v:
        return "Preprint / Working Paper"
    if any(x in v for x in _WP_MARKERS):
        return "Working Paper"
    if any(x in v for x in _REPO_MARKERS):
        return "Repository / Working Paper"
    if t == "article":
        return "Journal Article"
    if t in ("proceedings-article", "conference-paper"):
        return "Conference Paper"
    if t in ("editorial", "letter"):
        return "Editorial / Letter"
    return "Other"


# Standard field rankings, covering every discipline LSMS-linked papers
# actually get published in (economics, health, nutrition, agriculture,
# demography, statistics, environment) — not economics alone. An earlier
# version only ranked econ journals, which meant a nutrition or public-health
# paper in a genuinely top journal for its field still fell into Tier 4 by
# default. Swap in the WBG-approved list here when it arrives; nothing else
# needs to change.
_JOURNAL_TIERS = {
    # --- Tier 1: top general-interest OR top-of-field, any discipline ----
    "american economic review": "1 — Top General or Top Field",
    "quarterly journal of economics": "1 — Top General or Top Field",
    "journal of political economy": "1 — Top General or Top Field",
    "review of economic studies": "1 — Top General or Top Field",
    "econometrica": "1 — Top General or Top Field",
    "nature": "1 — Top General or Top Field",
    "science": "1 — Top General or Top Field",
    "proceedings of the national academy of sciences": "1 — Top General or Top Field",
    "the lancet": "1 — Top General or Top Field",
    "new england journal of medicine": "1 — Top General or Top Field",
    "jama": "1 — Top General or Top Field",
    "bmj": "1 — Top General or Top Field",

    "journal of development economics": "1 — Top General or Top Field",
    "world development": "1 — Top General or Top Field",
    "american economic journal applied economics": "1 — Top General or Top Field",
    "american economic journal economic policy": "1 — Top General or Top Field",
    "review of economics and statistics": "1 — Top General or Top Field",
    "economic journal": "1 — Top General or Top Field",
    "journal of economic growth": "1 — Top General or Top Field",
    "economic development and cultural change": "1 — Top General or Top Field",
    "world bank economic review": "1 — Top General or Top Field",
    "journal of the european economic association": "1 — Top General or Top Field",
    "rand journal of economics": "1 — Top General or Top Field",
    "journal of public economics": "1 — Top General or Top Field",
    "journal of international economics": "1 — Top General or Top Field",
    "journal of human resources": "1 — Top General or Top Field",
    "journal of economic perspectives": "1 — Top General or Top Field",
    "journal of urban economics": "1 — Top General or Top Field",
    "american journal of agricultural economics": "1 — Top General or Top Field",
    "demography": "1 — Top General or Top Field",
    "population and development review": "1 — Top General or Top Field",
    "the lancet global health": "1 — Top General or Top Field",
    "the lancet planetary health": "1 — Top General or Top Field",
    "bmj global health": "1 — Top General or Top Field",
    "bulletin of the world health organization": "1 — Top General or Top Field",
    "health affairs": "1 — Top General or Top Field",
    "american journal of clinical nutrition": "1 — Top General or Top Field",
    "journal of the royal statistical society": "1 — Top General or Top Field",
    "global environmental change": "1 — Top General or Top Field",
    "journal of environmental economics and management": "1 — Top General or Top Field",
    "plos medicine": "1 — Top General or Top Field",
    "jama internal medicine": "1 — Top General or Top Field",
    "jama network open": "1 — Top General or Top Field",

    # --- Tier 2: quality, indexed, peer-reviewed field journal -----------
    "food policy": "2 — Quality Field",
    "journal of agricultural economics": "2 — Quality Field",
    "agricultural economics": "2 — Quality Field",
    "journal of african economies": "2 — Quality Field",
    "african development review": "2 — Quality Field",
    "oxford development studies": "2 — Quality Field",
    "health economics": "2 — Quality Field",
    "journal of health economics": "2 — Quality Field",
    "land economics": "2 — Quality Field",
    "european review of agricultural economics": "2 — Quality Field",
    "world bank research observer": "2 — Quality Field",
    "journal of rural studies": "2 — Quality Field",
    "global food security": "2 — Quality Field",
    "applied economic perspectives and policy": "2 — Quality Field",
    "economics of education review": "2 — Quality Field",
    "labour economics": "2 — Quality Field",
    "journal of development studies": "2 — Quality Field",
    "canadian journal of development studies": "2 — Quality Field",
    "international food and agribusiness management review": "2 — Quality Field",
    "food security": "2 — Quality Field",
    "agriculture & food security": "2 — Quality Field",
    "public health nutrition": "2 — Quality Field",
    "journal of health population and nutrition": "2 — Quality Field",
    "health policy and planning": "2 — Quality Field",
    "educational research review": "2 — Quality Field",
    "world development perspectives": "2 — Quality Field",
    "the european journal of development research": "2 — Quality Field",
    "european journal of development research": "2 — Quality Field",
    "applied economics": "2 — Quality Field",
    "tobacco control": "2 — Quality Field",
    "globalization and health": "2 — Quality Field",
    "current developments in nutrition": "2 — Quality Field",
    "review of development economics": "2 — Quality Field",
    "journal of international development": "2 — Quality Field",
    "journal of economic behavior & organization": "2 — Quality Field",
    "agricultural and food economics": "2 — Quality Field",
    "food and energy security": "2 — Quality Field",
    "social science & medicine": "2 — Quality Field",
    "american journal of epidemiology": "2 — Quality Field",
    "maternal & child nutrition": "2 — Quality Field",
    "maternal and child nutrition": "2 — Quality Field",
    "journal of nutrition": "2 — Quality Field",
    "bmc public health": "2 — Quality Field",
    "international journal for equity in health": "2 — Quality Field",
    "bmc health services research": "2 — Quality Field",
    "global health science and practice": "2 — Quality Field",
    "social indicators research": "2 — Quality Field",
    "land use policy": "2 — Quality Field",
    "international journal of social economics": "2 — Quality Field",
    "health economics review": "2 — Quality Field",
    "agricultural systems": "2 — Quality Field",
    "demographic research": "2 — Quality Field",
    "african journal of food agriculture nutrition and development": "2 — Quality Field",
    "malaria journal": "2 — Quality Field",
    "cogent food & agriculture": "2 — Quality Field",
    "development southern africa": "2 — Quality Field",
    "journal of global health": "2 — Quality Field",
    "population and environment": "2 — Quality Field",
    "environment and development economics": "2 — Quality Field",
    "african journal of agricultural and resource economics": "2 — Quality Field",
    "energy economics": "2 — Quality Field",
    "african journal of agricultural research": "2 — Quality Field",
    "journal of agriculture and food research": "2 — Quality Field",
    "development policy review": "2 — Quality Field",
    "studies in family planning": "2 — Quality Field",
    "international journal of educational development": "2 — Quality Field",
    "review of economics of the household": "2 — Quality Field",
    "review of income and wealth": "2 — Quality Field",
    "agribusiness": "2 — Quality Field",
    "feminist economics": "2 — Quality Field",
    "journal of development effectiveness": "2 — Quality Field",
    "journal of agricultural and applied economics": "2 — Quality Field",
    "child indicators research": "2 — Quality Field",
    "ecological economics": "2 — Quality Field",
    "energy policy": "2 — Quality Field",
    "agricultural and resource economics review": "2 — Quality Field",
    "international journal of agricultural economics": "2 — Quality Field",
    "health research policy and systems": "2 — Quality Field",
    "asian development review": "2 — Quality Field",
    "ssm - population health": "2 — Quality Field",
    "american journal of tropical medicine and hygiene": "2 — Quality Field",
    "forest policy and economics": "2 — Quality Field",
    "journal of comparative economics": "2 — Quality Field",
    "economics & human biology": "2 — Quality Field",
    "environmental research letters": "2 — Quality Field",
    "journal of asian economics": "2 — Quality Field",
    "ghana journal of development studies": "2 — Quality Field",
    "agrekon": "2 — Quality Field",
    "plos one": "3 — Other Peer-Reviewed",
    "plos global public health": "3 — Other Peer-Reviewed",
    "sustainability": "3 — Other Peer-Reviewed",
    "nutrients": "3 — Other Peer-Reviewed",
    "heliyon": "3 — Other Peer-Reviewed",
    "scientific reports": "3 — Other Peer-Reviewed",
    "bmc global and public health": "3 — Other Peer-Reviewed",
    "frontiers in public health": "3 — Other Peer-Reviewed",
    "frontiers in health services": "3 — Other Peer-Reviewed",
    "annals of global health": "3 — Other Peer-Reviewed",
    "aids care": "3 — Other Peer-Reviewed",
    "obesity reviews": "3 — Other Peer-Reviewed",
    "springerplus": "3 — Other Peer-Reviewed",
    "people and nature": "3 — Other Peer-Reviewed",
    "emerging infectious diseases": "3 — Other Peer-Reviewed",
    "revista panamericana de salud publica": "3 — Other Peer-Reviewed",
    "salud publica de mexico": "3 — Other Peer-Reviewed",
    "journal of korean medical science": "3 — Other Peer-Reviewed",
    "journal of nepal health research council": "3 — Other Peer-Reviewed",
    "journal of water sanitation and hygiene for development": "3 — Other Peer-Reviewed",
    "statistical journal of the iaos": "3 — Other Peer-Reviewed",
    "statistics in transition new series": "3 — Other Peer-Reviewed",
    "international journal of environmental research and public health": "3 — Other Peer-Reviewed",
    "bmj open": "3 — Other Peer-Reviewed",
    # Nature-brand family, listed by exact full name rather than matched
    # off a bare "nature" substring, which would also catch unrelated
    # titles like "Human Nature Journal of Social Sciences".
    "nature medicine": "1 — Top General or Top Field",
    "nature communications": "1 — Top General or Top Field",
    "nature ecology & evolution": "1 — Top General or Top Field",
    "nature food": "1 — Top General or Top Field",
    "nature human behaviour": "1 — Top General or Top Field",
    "nature plants": "1 — Top General or Top Field",
    "nature sustainability": "1 — Top General or Top Field",
    # Same idea for the Lancet family: the flagship is caught by the bare
    # "the lancet" entry above. The regional spin-offs are newer and
    # broader in scope, so they get their own entry a tier down rather
    # than inheriting the flagship's tier; the specialty journals
    # (Infectious Diseases, Public Health) are as selective as the
    # flagship and stay at Tier 1.
    "the lancet regional health": "2 — Quality Field",
    "the lancet infectious diseases": "1 — Top General or Top Field",
    "the lancet public health": "1 — Top General or Top Field",

    # These used to sit here mapped to "WP", duplicating (and, via loose
    # substring matching, actively undermining) the working-paper detection
    # `detect_pub_type()` already does. A genuine working paper never
    # reaches this dict — `detect_journal_tier()` returns "WP" from
    # `pub_type` before ever looking at `venue` (see below). Keeping them
    # here only meant a real journal whose name happened to contain "iza"
    # (Journal of Economic Behavior & *Organization*) or "cepr" etc. as a
    # substring got silently mislabeled as a working paper.
}


def detect_journal_tier(venue: str, pub_type: str) -> str:
    """
    1. Working papers / repositories / theses / preprints / eBooks -> WP
    2. Exact match in the tier list -> that tier; failing that, the longest
       (most specific) key that's a substring of the venue -> its tier
    3. Any remaining journal article -> Tier 3, never blank
    4. No venue -> blank
    """
    pt = pub_type or ""

    if any(x in pt for x in ("Working Paper", "Repository", "Preprint",
                             "Thesis", "Dissertation", "Report",
                             "Book", "eBook", "Conference")):
        return "WP — Working Paper / Non-Journal"

    v = (venue or "").lower().strip()
    if v:
        if v in _JOURNAL_TIERS:
            return _JOURNAL_TIERS[v]
        # Substring fallback, for venue strings OpenAlex decorates with
        # extra text. Keys under 10 chars are skipped here (still usable
        # for the exact match above) since a short key is too likely to be
        # a coincidental substring of an unrelated journal's name — this is
        # what let "iza" match "...Organization" and "hal" match
        # "Ophthalmology". Among the keys that do match, the longest one
        # wins, so a specific entry (e.g. "the lancet regional health")
        # always beats a shorter, more general one it's nested inside
        # (e.g. "the lancet") regardless of dict order.
        candidates = [(key, tier) for key, tier in _JOURNAL_TIERS.items()
                      if len(key) >= 10 and key in v]
        if candidates:
            return max(candidates, key=lambda kt: len(kt[0]))[1]

    if "Journal Article" in pt:
        return "3 — Other Peer-Reviewed"
    if v:
        return "3 — Other Peer-Reviewed"
    return ""
