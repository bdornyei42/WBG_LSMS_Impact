"""
geography.py — Africa authorship flags from institution country codes.

Institution-based detection undercounts African researchers: those at the World
Bank or US/EU universities read as non-African, and OpenAlex institution data is
sparse for many African universities. The Analysis sheet reports this openly with
an Unclassified count. Treat the figure as a lower bound.
"""

from keywords import AFRICA_COUNTRY_CODES, SSA_COUNTRY_CODES


def classify_geography(country_codes: list, first_author_codes: list) -> dict:
    codes = {c.upper() for c in country_codes if c}
    fa_codes = {c.upper() for c in first_author_codes if c}

    is_fa_africa = bool(fa_codes & AFRICA_COUNTRY_CODES)
    is_any_africa = bool(codes & AFRICA_COUNTRY_CODES)

    if not codes:
        geo, strict = "Unclassified", False
    elif codes <= SSA_COUNTRY_CODES:
        geo, strict = "Sub-Saharan Africa", True
    elif codes & AFRICA_COUNTRY_CODES:
        geo, strict = "Mixed", False
    elif len(codes) > 1:
        geo, strict = "Mixed", False
    else:
        geo, strict = "Other", False

    return {
        "geography_clean": geo,
        "is_first_author_africa": is_fa_africa,
        "is_any_author_africa": is_any_africa,
        "is_africa_institution_strict": strict,
    }
