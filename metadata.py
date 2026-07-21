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


def detect_pub_type(oa_type: str, venue: str) -> str:
    """Classify the real output type. OpenAlex's own `type` alone is not enough."""
    v = (venue or "").lower()
    t = (oa_type or "").lower()

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
        "research papers in economics", "econstor", "ssrn", "cepr", "iza",
        "policy research working paper", "opengrey", "opendocs", "hal",
        "open science framework", "osf", "preprint", "arxiv", "philpapers",
        "contributions to economics", "research series", "series",
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


# Standard field rankings for development economics. Swap in the WBG-approved
# list here when it arrives; nothing else needs to change.
_JOURNAL_TIERS = {
    "american economic review": "1 — Top General Econ",
    "quarterly journal of economics": "1 — Top General Econ",
    "journal of political economy": "1 — Top General Econ",
    "review of economic studies": "1 — Top General Econ",
    "econometrica": "1 — Top General Econ",
    "journal of development economics": "2 — Top Field",
    "world development": "2 — Top Field",
    "american economic journal applied economics": "2 — Top Field",
    "american economic journal economic policy": "2 — Top Field",
    "review of economics and statistics": "2 — Top Field",
    "economic journal": "2 — Top Field",
    "journal of economic growth": "2 — Top Field",
    "economic development and cultural change": "2 — Top Field",
    "world bank economic review": "2 — Top Field",
    "journal of the european economic association": "2 — Top Field",
    "rand journal of economics": "2 — Top Field",
    "journal of public economics": "2 — Top Field",
    "journal of international economics": "2 — Top Field",
    "journal of human resources": "2 — Top Field",
    "journal of economic perspectives": "2 — Top Field",
    "journal of urban economics": "2 — Top Field",
    "food policy": "3 — Quality Field",
    "journal of agricultural economics": "3 — Quality Field",
    "agricultural economics": "3 — Quality Field",
    "american journal of agricultural economics": "3 — Quality Field",
    "journal of african economies": "3 — Quality Field",
    "african development review": "3 — Quality Field",
    "oxford development studies": "3 — Quality Field",
    "health economics": "3 — Quality Field",
    "journal of health economics": "3 — Quality Field",
    "demography": "3 — Quality Field",
    "land economics": "3 — Quality Field",
    "european review of agricultural economics": "3 — Quality Field",
    "world bank research observer": "3 — Quality Field",
    "journal of rural studies": "3 — Quality Field",
    "global food security": "3 — Quality Field",
    "applied economic perspectives and policy": "3 — Quality Field",
    "economics of education review": "3 — Quality Field",
    "labour economics": "3 — Quality Field",
    "journal of development studies": "3 — Quality Field",
    "canadian journal of development studies": "3 — Quality Field",
    "international food and agribusiness management review": "3 — Quality Field",
    "food security": "3 — Quality Field",
    "agriculture & food security": "3 — Quality Field",
    "public health nutrition": "3 — Quality Field",
    "journal of health population and nutrition": "3 — Quality Field",
    "health policy and planning": "3 — Quality Field",
    "educational research review": "3 — Quality Field",
    "world development perspectives": "3 — Quality Field",
    "the european journal of development research": "3 — Quality Field",
    "review of development economics": "3 — Quality Field",
    "journal of international development": "3 — Quality Field",
    "agricultural and food economics": "3 — Quality Field",
    "food and energy security": "3 — Quality Field",
    "population and development review": "3 — Quality Field",
    "social science & medicine": "3 — Quality Field",
    "american journal of epidemiology": "3 — Quality Field",
    "maternal & child nutrition": "3 — Quality Field",
    "journal of nutrition": "3 — Quality Field",
    "plos one": "4 — Other Peer-Reviewed",
    "plos global public health": "4 — Other Peer-Reviewed",
    "sustainability": "4 — Other Peer-Reviewed",
    "nutrients": "4 — Other Peer-Reviewed",
    "heliyon": "4 — Other Peer-Reviewed",
    "scientific reports": "4 — Other Peer-Reviewed",
    "bmc public health": "4 — Other Peer-Reviewed",
    "bmc global and public health": "4 — Other Peer-Reviewed",
    "frontiers in public health": "4 — Other Peer-Reviewed",
    "frontiers in health services": "4 — Other Peer-Reviewed",
    "annals of global health": "4 — Other Peer-Reviewed",
    "aids care": "4 — Other Peer-Reviewed",
    "obesity reviews": "4 — Other Peer-Reviewed",
    "springerplus": "4 — Other Peer-Reviewed",
    "people and nature": "4 — Other Peer-Reviewed",
    "emerging infectious diseases": "4 — Other Peer-Reviewed",
    "revista panamericana de salud publica": "4 — Other Peer-Reviewed",
    "salud publica de mexico": "4 — Other Peer-Reviewed",
    "journal of korean medical science": "4 — Other Peer-Reviewed",
    "journal of nepal health research council": "4 — Other Peer-Reviewed",
    "journal of water sanitation and hygiene for development": "4 — Other Peer-Reviewed",
    "statistical journal of the iaos": "4 — Other Peer-Reviewed",
    "statistics in transition new series": "4 — Other Peer-Reviewed",
    "international journal of environmental research and public health": "4 — Other Peer-Reviewed",
    "nber": "WP — Working Paper",
    "iza": "WP — Working Paper",
    "ssrn": "WP — Working Paper",
    "cepr": "WP — Working Paper",
    "world bank policy research": "WP — Working Paper",
    "ifpri discussion": "WP — Working Paper",
}


def detect_journal_tier(venue: str, pub_type: str) -> str:
    """
    1. Working papers / repositories / theses / preprints / eBooks -> WP
    2. Exact or substring match in the tier list -> that tier
    3. Any remaining journal article -> Tier 4, never blank
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
        for key, tier in _JOURNAL_TIERS.items():
            if key in v:
                return tier

    if "Journal Article" in pt:
        return "4 — Other Peer-Reviewed"
    if v:
        return "4 — Other Peer-Reviewed"
    return ""
