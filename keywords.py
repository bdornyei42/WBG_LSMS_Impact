"""
keywords.py — LSMS Survey Keyword Registry

The exact 124 keywords reviewed and classified by the LSMS team, organised
by survey family. Each term carries its own match tier directly:

  A   — unambiguous. Full-text match accepted, no title/abstract requirement,
        no discipline filter.
  B   — medium. Must appear in the title or abstract (case-insensitive).
  C   — short/ambiguous. Case-sensitive match required, plus a country/
        context word nearby, plus a relevant discipline.
  AND — compound. Split into two parts on " and "; both parts must
        independently match.

Each family also has `context_hints`: the country/survey words required
alongside a Tier C term (e.g. "IHPS" needs "malawi" nearby to rule out the
unrelated medical term IHP).
"""

SURVEY_FAMILIES = [

    # ── LSMS CORE PROGRAM ───────────────────────────────────────────
    {
        "label": "LSMS Core Program",
        "region": "Global",
        "context_hints": ["lsms", "living standards", "household survey"],
        "terms": [
            ("Living Standards Measurement Study", "A"),
            ("Living Standards Measurement Survey", "A"),
            ("Living Standards Survey", "A"),
            ("Living Standards Measurement Study - Integrated Surveys on Agriculture", "A"),
            ("Living Standard Measurement Study - Integrated Surveys on Agriculture", "A"),
            ("LSMS - Integrated Surveys on Agriculture", "A"),
            ("LSMS-ISA", "A"),
            ("LSMS Data", "A"),
        ],
    },

    # ── BURKINA FASO EMC / EHCVM ────────────────────────────────────
    {
        "label": "Burkina Faso EMC / EHCVM",
        "region": "Sub-Saharan Africa",
        "context_hints": ["burkina", "burkinabe", "burkina faso"],
        "terms": [
            ("Burkina Faso Enquête Multisectorielle Continue", "A"),
            ("Enquête Multisectorielle Continue", "A"),
            ("EMC 2013", "C"),
            ("EMC 2014", "C"),
            ("EHCVM", "A"),
            ("BFA EHCVM", "A"),
            ("Enquete Harmonisee sur les Conditions de Vie des Menages", "A"),
            ("Enquête Harmonisée sur les Conditions de Vie des Ménages", "A"),
            ("EHCVM 2018", "A"),
            ("EHCVM 2021", "A"),
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
            ("ESS-1", "C"),
            ("ESS-2", "C"),
            ("ESS-3", "C"),
            ("ESPS-4", "C"),
            ("ESPS-5", "C"),
            ("ESS1", "C"),
            ("ESS2", "C"),
            ("ESS3", "C"),
            ("ESPS4", "C"),
            ("ESPS5", "C"),
            ("ESS4", "C"),
            ("ESS5", "C"),
        ],
    },

    # ── MALAWI IHS / IHPS ───────────────────────────────────────────
    {
        "label": "Malawi IHS / IHPS",
        "region": "Sub-Saharan Africa",
        "context_hints": ["malawi", "malawian"],
        "terms": [
            ("Malawi Second Integrated Household Survey", "A"),
            ("Second Integrated Household Survey", "B"),
            ("IHS", "C"),
            ("IHS2", "C"),
            ("Malawi Third Integrated Household Survey", "A"),
            ("Third Integrated Household Survey", "A"),
            ("IHS3", "C"),
            ("Malawi Third Integrated Household Survey-Panel Subcomponent", "A"),
            ("Third Integrated Household Survey-Panel Subcomponent", "A"),
            ("IHS3 and Panel", "AND"),
            ("Malawi Integrated Household Panel Survey", "A"),
            ("Integrated Household Panel Survey", "C"),
            ("IHPS", "C"),
            ("Fourth Integrated Household Survey", "A"),
            ("Malawi Fourth Integrated Household Survey", "A"),
            ("IHS4", "C"),
            ("Malawi Fifth Integrated Household Survey", "A"),
            ("IHS5", "C"),
        ],
    },

    # ── MALI EACI ───────────────────────────────────────────────────
    {
        "label": "Mali EACI",
        "region": "Sub-Saharan Africa",
        "context_hints": ["mali", "malian", "malien"],
        "terms": [
            ("Mali Enquête Agricole de Conjoncture Intégrée aux Conditions de Vie des Ménages", "A"),
            ("Enquête Agricole de Conjoncture Intégrée aux Conditions de Vie des Ménages", "A"),
            ("Enquête Agricole de Conjoncture Intégrée", "A"),
            ("EACI", "C"),
            ("EAC-I", "C"),
            ("EACI 2014", "C"),
            ("EACI 2017", "C"),
        ],
    },

    # ── NIGER ECVMA ─────────────────────────────────────────────────
    {
        "label": "Niger ECVMA",
        "region": "Sub-Saharan Africa",
        "context_hints": ["niger"],
        "terms": [
            ("Niger Enquête Nationale sur les Conditions de Vie des Ménages et l'Agriculture", "A"),
            ("Enquête Nationale sur les Conditions de Vie des Ménages et l'Agriculture", "A"),
            ("ECVMA", "C"),
            ("ECVM/A", "C"),
            ("ECVMA 2011", "B"),
            ("ECVMA 2014", "B"),
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
            ("General Household Survey Panel", "C"),
            ("General Household Survey-Panel", "C"),
            ("GHS-Panel Survey", "C"),
            ("GHS Panel Survey", "C"),
            ("GHS and Panel", "C"),
            ("GHS-Panel", "C"),
            ("GHS-P", "C"),
            ("GHSP", "C"),
            ("General Household Survey (Panel)", "C"),
            ("Nigeria General Household Survey (Panel)", "A"),
        ],
    },

    # ── TANZANIA NPS ────────────────────────────────────────────────
    {
        "label": "Tanzania NPS",
        "region": "Sub-Saharan Africa",
        "context_hints": ["tanzania", "tanzanian"],
        "terms": [
            ("Tanzania National Panel Survey", "A"),
            ("National Panel Survey", "C"),
            ("Tanzania - National Panel Survey", "A"),
            ("Tanzania NPS", "A"),
            ("TZNPS", "A"),
            ("TNPS", "C"),
            ("National Panel Survey 2019-2020 - Extended Panel with Sex Disaggregated Data", "A"),
            ("National Panel Survey 2008-2015, Uniform Panel Dataset", "A"),
            ("Tanzania National Panel Survey 2014-2016", "A"),
            ("National Panel Survey- Universal Panel Questionnaire, 2008-2015", "A"),
            ("National Panel Survey 2008-2009, Wave 1", "A"),
            ("National Panel Survey 2010-2011", "A"),
            ("National Panel Survey 2012-2013: Wave 3 (Tanzania)", "A"),
            ("National Panel Survey 2014-2015, Wave 4", "A"),
            ("Tanzania Panel Survey 2020-2021, Wave 5", "A"),
        ],
    },

    # ── UGANDA UNPS ─────────────────────────────────────────────────
    {
        "label": "Uganda UNPS",
        "region": "Sub-Saharan Africa",
        "context_hints": ["uganda", "ugandan"],
        "terms": [
            ("Uganda National Panel Survey", "A"),
            ("UNPS", "C"),
            ("Uganda NPS", "B"),
            ("Uganda - National Panel Survey", "A"),
            ("The Uganda National Panel survey", "A"),
            ("National Panel Survey 2005-2009", "C"),
            ("National Panel Survey 2011-2012, Wave III", "C"),
            ("National Panel Survey 2013-2014", "C"),
            ("National Panel Survey 2015-2016", "C"),
            ("Uganda National Panel Survey 2018-2019", "A"),
            ("National Panel Survey 2019-2020", "C"),
        ],
    },

    # ── LSMS HIGH-FREQUENCY PHONE SURVEYS (HFPS) ────────────────────
    {
        "label": "LSMS High-Frequency Phone Surveys (HFPS)",
        "region": "Sub-Saharan Africa",
        "context_hints": ["burkina", "mali", "nigeria", "niger", "ethiopia", "uganda", "malawi", "tanzania", "high-frequency", "phone survey"],
        "terms": [
            ("High-Frequency Phone Survey", "A"),
            ("High-Frequency Phone Survey and Burkina Faso", "AND"),
            ("High-Frequency Phone Survey and Mali", "AND"),
            ("High-Frequency Phone Survey and Nigeria", "AND"),
            ("High-Frequency Phone Survey and Niger", "AND"),
            ("High-Frequency Phone Survey and Ethiopia", "AND"),
            ("High-Frequency Phone Survey and Uganda", "AND"),
            ("High-Frequency Phone Survey and Malawi", "AND"),
            ("High-Frequency Phone Survey and Tanzania", "AND"),
            ("HFPS and Burkina Faso", "AND"),
            ("HFPS and Mali", "AND"),
            ("HFPS and Nigeria", "AND"),
            ("HFPS and Niger", "AND"),
            ("HFPS and Ethiopia", "AND"),
            ("HFPS and Uganda", "AND"),
            ("HFPS and Malawi", "AND"),
            ("HFPS and Tanzania", "AND"),
            ("HFPS-HH", "A"),
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


def all_terms():
    """Every keyword string across all families (tier stripped), de-duplicated."""
    seen, out = set(), []
    for f in SURVEY_FAMILIES:
        for term, _tier in f["terms"]:
            if term not in seen:
                seen.add(term)
                out.append(term)
    return out


def term_tier(term):
    """The tier assigned to a specific keyword term, or None if not found."""
    for f in SURVEY_FAMILIES:
        for t, tier in f["terms"]:
            if t == term:
                return tier
    return None
