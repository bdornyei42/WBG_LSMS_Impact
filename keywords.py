"""
keywords.py — LSMS Survey Keyword Registry

Keywords reviewed and classified by the LSMS team, organised by survey family.
Each term carries its own match tier:

  A — globally unique. The name contains a country, or an acronym that can't
      plausibly mean anything else ("LSMS-ISA", "TZNPS"). A full-text hit is
      accepted on its own.
  B — real survey name, but a GENERIC one: the words describe the survey
      rather than identify it, and other countries/programs use the same
      phrase ("National Panel Survey", "High-Frequency Phone Survey",
      "Living Standards Survey"). Needs a country context word in the
      document + an allowed field. Case-insensitive -- it's a phrase, casing
      carries no information.
  C — short acronym ("IHPS", "LSMS", "UNPS"). Same country + field gating as
      B, plus case-sensitivity where we can check it: OpenAlex stems and
      case-folds server-side ("LSMS" also retrieves "LSM"), so casing is the
      only local defence against an acronym collision.

`context_hints` are the country words that satisfy B/C gating for a family.
A hint must NEVER appear inside the term it gates -- that makes the gate
self-satisfying and therefore useless (gating "Living Standards Survey" on
"living standards", or "High-Frequency Phone Survey" on "phone survey").
_check_registry() enforces this at import.

A term may override the family list with its own third element,
(term, tier, hints), for the case where collision risk is a property of the
TERM rather than the family. No term needs it right now -- turning stemming off
(matching.SEARCH_PARAM) removed the reason it was introduced -- but the hook
stays because the next colliding acronym will want it.

TERM_EXCLUSIONS below handles the other half of that problem: spellings that
collide no matter what the country gate says.
"""

# LSMS-ISA countries -- the 8 with an active Integrated Surveys on Agriculture
# panel. Adjective forms included b/c the local check doesn't stem.
ISA_COUNTRY_HINTS = [
    "burkina", "burkinabe", "burkina faso",
    "ethiopia", "ethiopian",
    "malawi", "malawian",
    "mali", "malian", "malien",
    "niger", "nigerien",
    "nigeria", "nigerian",
    "tanzania", "tanzanian",
    "uganda", "ugandan",
]

# Every country in the World Bank's own LSMS catalog collection
# (microdata.worldbank.org/index.php/catalog/lsms), not a guess. The core
# programme is global and long-running -- Côte d'Ivoire (1985) and Peru
# (1985-86) were the first two LSMS surveys ever fielded -- so gating
# core-programme terms on the ISA-8 alone silently drops decades of genuine
# papers.
#
# Adjective forms matter here: queries go out with search.exact, which does
# NOT stem, so "ethiopia" will not retrieve "ethiopian" by itself.
LSMS_COUNTRY_HINTS = ISA_COUNTRY_HINTS + [
    "albania", "albanian",
    "armenia", "armenian",
    "azerbaijan", "azerbaijani",
    "benin", "beninese",
    "bosnia", "herzegovina",
    "brazil", "brazilian",
    "bulgaria", "bulgarian",
    "cambodia", "cambodian",
    "china", "chinese",
    "cote d'ivoire", "côte d'ivoire", "ivory coast", "ivorian",
    "ecuador", "ecuadorian",
    "ghana", "ghanaian",
    "guatemala", "guatemalan",
    "guinea-bissau",
    "guyana", "guyanese",
    "india", "indian",
    "iraq", "iraqi",
    "jamaica", "jamaican",
    "kazakhstan", "kosovo", "kyrgyz",
    "liberia", "liberian",
    "nepal", "nepalese",
    "nicaragua", "nicaraguan",
    "pakistan", "pakistani",
    "panama", "panamanian",
    "peru", "peruvian",
    "senegal", "senegalese",
    "serbia", "serbian", "montenegro",
    "south africa", "south african",
    "tajikistan", "tajik",
    "timor-leste", "timor",
    "togo", "togolese",
    "vietnam", "viet nam", "vietnamese",
]

# Phrases that identify a DIFFERENT thing sharing a term's spelling. Compiled
# into the query as a NOT clause, so the collision never gets retrieved at all.
#
# Only needed where an acronym genuinely collides. "LSMS" is the bad one:
# search.exact stops the stemmed "LSM" match, but it's still
# case-INsensitive, so "LSMs" (plural of land-surface model, and of
# log-structured merge-tree) is the same token to the server. Those papers
# routinely mention China/India/Brazil, so the country gate doesn't stop them
# either -- 11 of them reached the Papers sheet in a single-FY test run.
#
# Safe because it only narrows the BARE acronym query: a remote-sensing paper
# that genuinely uses LSMS microdata alongside land-surface data will almost
# always also name "LSMS-ISA" or the full survey name, and gets admitted on
# that Tier A term instead.
TERM_EXCLUSIONS = {
    "LSMS": [
        "land surface model", "land-surface model", "land surface temperature",
        "soil moisture", "merge-tree", "log-structured", "fuel cell", "cathode",
    ],
}

SURVEY_FAMILIES = [

    # ── LSMS CORE PROGRAM ───────────────────────────────────────────
    {
        "label": "LSMS Core Program",
        "region": "Global",
        "context_hints": LSMS_COUNTRY_HINTS,
        "terms": [
            ("Living Standards Measurement Study", "A"),
            ("Living Standards Measurement Survey", "A"),
            ("Living Standards Measurement Study - Integrated Surveys on Agriculture", "A"),
            ("Living Standard Measurement Study - Integrated Surveys on Agriculture", "A"),
            ("LSMS - Integrated Surveys on Agriculture", "A"),
            ("LSMS-ISA", "A"),
            # Generic on its own -- "living standards survey" is ordinary
            # prose and the name of plenty of non-LSMS national surveys.
            # Only counts w/ an LSMS country nearby (this is what pulls in
            # Ghana GLSS, Vietnam VLSS, Peru etc. without pulling in every
            # paper that uses the phrase descriptively).
            ("Living Standards Survey", "B"),
            # Bare acronym. Safe on the full country list now that queries go
            # out unstemmed -- stemmed, "LSMS" collapses to "LSM" and drags in
            # the land-surface-model and LSM-tree literature (13,506 hits for
            # one FY); with search.exact the same query returns 709.
            ("LSMS", "C"),
        ],
    },

    # ── BURKINA FASO EMC / EHCVM ────────────────────────────────────
    {
        "label": "Burkina Faso EMC / EHCVM",
        "region": "Sub-Saharan Africa",
        "context_hints": ["burkina", "burkinabe", "burkina faso"],
        "terms": [
            ("Burkina Faso Enquête Multisectorielle Continue", "A"),
            ("BFA EHCVM", "A"),
            ("Enquête Multisectorielle Continue", "B"),
            # EHCVM is the harmonised WAEMU survey -- Burkina, Mali, Niger,
            # Senegal, Benin, Togo and Côte d'Ivoire all run one, so the
            # acronym alone doesn't identify a country.
            ("EHCVM", "C"),
            ("EHCVM 2018", "C"),
            ("EHCVM 2021", "C"),
            ("Enquete Harmonisee sur les Conditions de Vie des Menages", "B"),
            ("Enquête Harmonisée sur les Conditions de Vie des Ménages", "B"),
            ("EMC 2013", "C"),
            ("EMC 2014", "C"),
        ],
    },

    # ── ETHIOPIA ESS / ESPS ─────────────────────────────────────────
    {
        "label": "Ethiopia ESS / ESPS",
        "region": "Sub-Saharan Africa",
        "context_hints": ["ethiopia", "ethiopian", "addis"],
        "terms": [
            ("Ethiopia Rural Socioeconomic Survey", "A"),
            ("Ethiopia Socioeconomic Survey", "A"),
            ("Ethiopian Socioeconomic Survey", "A"),
            ("Ethiopia Socioeconomic Panel Survey", "A"),
            ("Ethiopia Socioeconomic Survey (ESS) 2012, 2014 and 2016 data", "A"),
            ("Ethiopia Socioeconomic Panel Survey (ESPS) 2019 and 2022", "A"),
            ("Ethiopia Socioeconomic Panel Survey (ESPS) Wave 4 and Wave 5", "A"),
            # bare "ESS" is deliberately absent -- European Social Survey.
            ("ESS-1", "C"), ("ESS-2", "C"), ("ESS-3", "C"),
            ("ESS1", "C"), ("ESS2", "C"), ("ESS3", "C"),
            ("ESS4", "C"), ("ESS5", "C"),
            ("ESPS-4", "C"), ("ESPS-5", "C"),
            ("ESPS4", "C"), ("ESPS5", "C"),
        ],
    },

    # ── MALAWI IHS / IHPS ───────────────────────────────────────────
    {
        "label": "Malawi IHS / IHPS",
        "region": "Sub-Saharan Africa",
        "context_hints": ["malawi", "malawian"],
        "terms": [
            ("Malawi Second Integrated Household Survey", "A"),
            ("Malawi Third Integrated Household Survey", "A"),
            ("Malawi Third Integrated Household Survey-Panel Subcomponent", "A"),
            ("Malawi Integrated Household Panel Survey", "A"),
            ("Malawi Fourth Integrated Household Survey", "A"),
            ("Malawi Fifth Integrated Household Survey", "A"),
            # "Nth Integrated Household Survey" is a naming convention, not a
            # unique title -- Malawi, Uganda, Zambia, Tajikistan and others
            # all have one. Country gate required.
            ("Second Integrated Household Survey", "B"),
            ("Third Integrated Household Survey", "B"),
            ("Third Integrated Household Survey-Panel Subcomponent", "B"),
            ("Fourth Integrated Household Survey", "B"),
            ("Integrated Household Panel Survey", "B"),
            ("IHS", "C"), ("IHS2", "C"), ("IHS3", "C"),
            ("IHS4", "C"), ("IHS5", "C"),
            ("IHPS", "C"),
        ],
    },

    # ── MALI EACI ───────────────────────────────────────────────────
    {
        "label": "Mali EACI",
        "region": "Sub-Saharan Africa",
        "context_hints": ["mali", "malian", "malien"],
        "terms": [
            ("Mali Enquête Agricole de Conjoncture Intégrée aux Conditions de Vie des Ménages", "A"),
            ("Enquête Agricole de Conjoncture Intégrée aux Conditions de Vie des Ménages", "B"),
            ("Enquête Agricole de Conjoncture Intégrée", "B"),
            ("EACI", "C"), ("EAC-I", "C"),
            ("EACI 2014", "C"), ("EACI 2017", "C"),
            ("EHCVM", "C"),   # Mali runs the WAEMU harmonised survey too
        ],
    },

    # ── NIGER ECVMA ─────────────────────────────────────────────────
    {
        "label": "Niger ECVMA",
        "region": "Sub-Saharan Africa",
        "context_hints": ["niger", "nigerien"],
        "terms": [
            ("Niger Enquête Nationale sur les Conditions de Vie des Ménages et l'Agriculture", "A"),
            ("Enquête Nationale sur les Conditions de Vie des Ménages et l'Agriculture", "B"),
            ("ECVMA", "C"), ("ECVM/A", "C"),
            ("ECVMA 2011", "C"), ("ECVMA 2014", "C"),
            ("EHCVM", "C"),
        ],
    },

    # ── NIGERIA GHS-PANEL ───────────────────────────────────────────
    {
        "label": "Nigeria GHS-Panel",
        "region": "Sub-Saharan Africa",
        "context_hints": ["nigeria", "nigerian"],
        "terms": [
            ("Nigeria General Household Survey Panel", "A"),
            ("Nigeria General Household Survey-Panel", "A"),
            ("Nigeria General Household Survey (Panel)", "A"),
            # "General Household Survey" is also South Africa's and the UK's.
            ("General Household Survey Panel", "B"),
            ("General Household Survey-Panel", "B"),
            ("General Household Survey (Panel)", "B"),
            ("GHS-Panel Survey", "C"), ("GHS Panel Survey", "C"),
            ("GHS-Panel", "C"), ("GHS-P", "C"), ("GHSP", "C"),
        ],
    },

    # ── TANZANIA NPS ────────────────────────────────────────────────
    {
        "label": "Tanzania NPS",
        "region": "Sub-Saharan Africa",
        "context_hints": ["tanzania", "tanzanian"],
        "terms": [
            ("Tanzania National Panel Survey", "A"),
            ("Tanzania - National Panel Survey", "A"),
            ("Tanzania National Panel Survey 2014-2016", "A"),
            ("Tanzania Panel Survey 2020-2021, Wave 5", "A"),
            ("Tanzania NPS", "A"),
            ("TZNPS", "A"),
            ("National Panel Survey 2012-2013: Wave 3 (Tanzania)", "A"),   # names the country itself
            # Uganda runs a "National Panel Survey" too -- the bare phrase and
            # the undated catalogue titles need the country gate to keep the
            # two families apart.
            ("National Panel Survey", "B"),
            ("National Panel Survey 2019-2020 - Extended Panel with Sex Disaggregated Data", "B"),
            ("National Panel Survey 2008-2015, Uniform Panel Dataset", "B"),
            ("National Panel Survey- Universal Panel Questionnaire, 2008-2015", "B"),
            ("National Panel Survey 2008-2009, Wave 1", "B"),
            ("National Panel Survey 2010-2011", "B"),
            ("National Panel Survey 2014-2015, Wave 4", "B"),
            ("TNPS", "C"),
        ],
    },

    # ── UGANDA UNPS ─────────────────────────────────────────────────
    {
        "label": "Uganda UNPS",
        "region": "Sub-Saharan Africa",
        "context_hints": ["uganda", "ugandan"],
        "terms": [
            ("Uganda National Panel Survey", "A"),
            ("Uganda - National Panel Survey", "A"),
            ("Uganda National Panel Survey 2018-2019", "A"),
            ("Uganda NPS", "A"),
            ("National Panel Survey 2005-2009", "B"),
            ("National Panel Survey 2011-2012, Wave III", "B"),
            ("National Panel Survey 2013-2014", "B"),
            ("National Panel Survey 2015-2016", "B"),
            ("National Panel Survey 2019-2020", "B"),
            ("UNPS", "C"),
        ],
    },

    # ── LSMS HIGH-FREQUENCY PHONE SURVEYS (HFPS) ────────────────────
    {
        "label": "LSMS High-Frequency Phone Surveys (HFPS)",
        "region": "Sub-Saharan Africa",
        # Countries only. "high-frequency"/"phone survey" used to sit here,
        # which made the gate on the term "High-Frequency Phone Survey"
        # self-satisfying -- it matched its own words.
        "context_hints": ISA_COUNTRY_HINTS,
        "terms": [
            ("LSMS-HFPS", "A"),
            # Everyone ran a high-frequency phone survey during COVID (WFP,
            # UNICEF, national statistics offices, universities). Generic.
            ("High-Frequency Phone Survey", "B"),
            ("HFPS", "C"), ("HFPS-HH", "C"),
        ],
    },

]

# ── GEO CONSTANTS ────────────────────────────────────────────────────────────
AFRICA_COUNTRY_CODES = {
    "AO","BJ","BW","BF","BI","CM","CV","CF","TD","KM","CD","CG","CI","DJ",
    "EG","GQ","ER","ET","GA","GM","GH","GN","GW","KE","LS","LR","LY","MG",
    "MW","ML","MR","MU","MA","MZ","NA","NE","NG","RW","ST","SN","SL","SO",
    "ZA","SS","SD","SZ","TZ","TG","TN","UG","ZM","ZW","DZ","SC","EH",
}
SSA_COUNTRY_CODES = AFRICA_COUNTRY_CODES - {"EG","LY","MA","TN","DZ","EH"}
SSA_COUNTRY_NAMES = {
    "angola","benin","botswana","burkina faso","burundi","cameroon","cape verde",
    "central african republic","chad","comoros","congo","democratic republic of the congo",
    "cote d'ivoire","ivory coast","djibouti","equatorial guinea","eritrea","ethiopia",
    "gabon","gambia","ghana","guinea","guinea-bissau","kenya","lesotho","liberia",
    "madagascar","malawi","mali","mauritania","mauritius","mozambique","namibia",
    "niger","nigeria","rwanda","sao tome and principe","senegal","sierra leone",
    "somalia","south africa","south sudan","sudan","swaziland","eswatini","tanzania",
    "togo","uganda","zambia","zimbabwe","seychelles",
}
AFRICA_REGIONS = {"Sub-Saharan Africa"}


def iter_terms(family: dict):
    """
    Yield (term, tier, hints, exclusions) for a family, normalising the
    optional per-term hints override. Always use this instead of iterating
    family["terms"] -- entries are either 2- or 3-tuples.
    """
    fam_hints = family.get("context_hints") or []
    for entry in family["terms"]:
        if len(entry) == 3:
            term, tier, hints = entry
        else:
            (term, tier), hints = entry, fam_hints
        yield term, tier, hints, TERM_EXCLUSIONS.get(term, [])


def all_terms() -> list[str]:
    """Every keyword string across all families (tier stripped), de-duplicated."""
    seen, out = set(), []
    for f in SURVEY_FAMILIES:
        for term, _tier, _h, _x in iter_terms(f):
            if term not in seen:
                seen.add(term)
                out.append(term)
    return out


def term_tier(term: str) -> str | None:
    """Tier assigned to a keyword, or None. First hit wins if reused across families."""
    for f in SURVEY_FAMILIES:
        for t, tier, _h, _x in iter_terms(f):
            if t == term:
                return tier
    return None


def terms_by_tier(tier: str) -> list[str]:
    """Every term at a given tier, de-duplicated, original casing preserved."""
    seen, out = set(), []
    for f in SURVEY_FAMILIES:
        for term, t, _h, _x in iter_terms(f):
            if t == tier and term not in seen:
                seen.add(term)
                out.append(term)
    return out


def _check_registry() -> None:
    # A context hint that appears inside the term it gates makes the query
    # "TERM AND (hint)" trivially true for every hit. Cheap to check, silent
    # and expensive to miss, so it runs at import.
    for f in SURVEY_FAMILIES:
        for term, tier, hints, _x in iter_terms(f):
            if tier == "A":
                continue
            if not hints:
                raise ValueError(
                    f"{f['label']}: tier-{tier} term {term!r} has no context hints "
                    "-- it would be admitted with no country gate at all.")
            t = term.lower()
            for h in hints:
                if h.lower() in t:
                    raise ValueError(
                        f"{f['label']}: context hint {h!r} appears inside its own "
                        f"tier-{tier} term {term!r} -- the gate would be self-satisfying.")


_check_registry()
