"""Business-day arithmetic for DATE_TOLERANCE rules (P3).

A "business day" excludes weekends and the configured market's holidays. The
distance between two dates is the count of business days strictly after the
earlier date up to and including the later one — so consecutive business days
are 1 apart (Mon->Tue == 1), and a same-day pair is 0.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, Optional, Set


def parse_holidays(rows: Iterable[dict]) -> Dict[str, Set[str]]:
    """Build {market -> {iso_date, ...}} from market_holidays aux rows."""
    out: Dict[str, Set[str]] = {}
    for r in rows:
        market = str(r.get("market", "")).strip()
        day = str(r.get("date", "")).strip()
        if market and day:
            out.setdefault(market, set()).add(day)
    return out


def _to_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none"}:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def business_day_diff(
    a,
    b,
    holidays: Optional[Set[str]] = None,
) -> Optional[int]:
    """Absolute business-day distance between two dates.

    Returns None when either date is unparseable (so a rule treats it as a
    non-match rather than crashing).
    """
    da, db = _to_date(a), _to_date(b)
    if da is None or db is None:
        return None
    holidays = holidays or set()
    lo, hi = (da, db) if da <= db else (db, da)
    count = 0
    cur = lo
    while cur < hi:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur.isoformat() not in holidays:
            count += 1
    return count


def calendar_day_diff(a, b) -> Optional[int]:
    """Absolute calendar-day distance, or None if unparseable."""
    da, db = _to_date(a), _to_date(b)
    if da is None or db is None:
        return None
    return abs((db - da).days)
