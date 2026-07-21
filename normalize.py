"""
normalize.py — title/DOI normalisation for dedup, and Excel cell cleaning.
"""

import re
import unicodedata
import html as html_module

_ILLEGAL_XML = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def norm_title(raw) -> str:
    if not raw:
        return ""
    s = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def norm_doi(raw) -> str:
    if not raw:
        return ""
    s = str(raw).lower().strip()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", s).rstrip("/")


def clean_cell(v):
    # Decode HTML entities, strip XML control chars, space out a leading
    # formula trigger, cap at Excel's length limit.
    if not isinstance(v, str):
        return v
    v = html_module.unescape(v)
    v = _ILLEGAL_XML.sub('', v)
    if v and v[0] in ('=', '+', '-', '@'):
        v = ' ' + v
    return v[:32000] + '\u2026' if len(v) > 32000 else v
