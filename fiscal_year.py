"""
fiscal_year.py — World Bank fiscal year math.

WBG FY runs 1 July to 30 June: FY26 is Jul 2025 through Jun 2026.
"""

from datetime import date
from typing import Optional


def fiscal_year(year: int, month: int) -> str:
    return f"FY{str(year + (1 if month >= 7 else 0))[-2:]}"


def fy_start_date(fy_label: str) -> date:
    end_year = 2000 + int(fy_label[2:])
    return date(end_year - 1, 7, 1)


def current_and_prior_fy(today: Optional[date] = None):
    # (current running FY, the 5 most recently completed FYs)
    today = today or date.today()
    running_end = today.year + 1 if today.month >= 7 else today.year
    running = f"FY{str(running_end)[-2:]}"
    completed = [f"FY{str(running_end - i)[-2:]}" for i in range(1, 6)]
    return running, completed


def fy_to_year(fy: str) -> int:
    # 'FY27' -> 2027, 'FY99' -> 1999, 'FY00' -> 2000. Bad/missing -> 0 (sorts last).
    if not fy or not str(fy).startswith("FY"):
        return 0
    try:
        n = int(str(fy)[2:])
    except ValueError:
        return 0
    return 2000 + n if n < 70 else 1900 + n
