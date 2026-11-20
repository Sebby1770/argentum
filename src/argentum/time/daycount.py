"""ISDA day-count conventions.

Formulas follow the 2006 ISDA Definitions (and ICMA for ACT/ACT ICMA). Year
fractions are signed: ``year_fraction(d2, d1) == -year_fraction(d1, d2)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from calendar import isleap, monthrange
from datetime import date
from enum import Enum

from argentum.errors import InputError
from argentum.time.date import Date, DateLike, as_date

if TYPE_CHECKING:
    from argentum.time.calendar import Calendar


def _py(d: DateLike) -> date:
    return as_date(d).to_pydate()


def _days(d1: date, d2: date) -> int:
    return (d2 - d1).days


def _is_last_day_of_february(d: date) -> bool:
    return d.month == 2 and d.day == monthrange(d.year, 2)[1]


def _is_eom(d: date) -> bool:
    return d.day == monthrange(d.year, d.month)[1]


class DayCount(str, Enum):
    ACT_365F = "act/365f"
    ACT_365L = "act/365l"
    ACT_360 = "act/360"
    ACT_364 = "act/364"
    ACT_ACT_ISDA = "act/act-isda"
    ACT_ACT_AFB = "act/act-afb"
    ACT_ACT_ICMA = "act/act-icma"
    THIRTY_360_BOND = "30/360"
    THIRTY_360_US = "30/360-us"
    THIRTY_E_360 = "30e/360"
    THIRTY_E_360_ISDA = "30e/360-isda"
    THIRTY_EPLUS_360 = "30e+/360"
    BUS_252 = "bus/252"

    def year_fraction(
        self,
        start: DateLike,
        end: DateLike,
        *,
        ref_start: DateLike | None = None,
        ref_end: DateLike | None = None,
        calendar: "Calendar | None" = None,
        termination: DateLike | None = None,
    ) -> float:
        d1 = _py(start)
        d2 = _py(end)
        if d1 == d2:
            return 0.0
        if d1 > d2:
            return -self.year_fraction(
                end,
                start,
                ref_start=ref_start,
                ref_end=ref_end,
                calendar=calendar,
                termination=termination,
            )
        if self is DayCount.ACT_365F:
            return _days(d1, d2) / 365.0
        if self is DayCount.ACT_360:
            return _days(d1, d2) / 360.0
        if self is DayCount.ACT_364:
            return _days(d1, d2) / 364.0
        if self is DayCount.ACT_365L:
            return _days(d1, d2) / (366.0 if _feb29_in_range(d1, d2) else 365.0)
        if self is DayCount.ACT_ACT_ISDA:
            return _act_act_isda(d1, d2)
        if self is DayCount.ACT_ACT_AFB:
            return _act_act_afb(d1, d2)
        if self is DayCount.ACT_ACT_ICMA:
            if ref_start is None or ref_end is None:
                raise InputError("ACT/ACT ICMA requires ref_start and ref_end")
            return _act_act_icma(d1, d2, _py(ref_start), _py(ref_end))
        if self is DayCount.THIRTY_360_BOND or self is DayCount.THIRTY_360_US:
            return _thirty_360_us(d1, d2)
        if self is DayCount.THIRTY_E_360:
            return _thirty_e_360(d1, d2)
        if self is DayCount.THIRTY_E_360_ISDA:
            term = _py(termination) if termination is not None else d2
            return _thirty_e_360_isda(d1, d2, term)
        if self is DayCount.THIRTY_EPLUS_360:
            return _thirty_eplus_360(d1, d2)
        if self is DayCount.BUS_252:
            if calendar is None:
                raise InputError("BUS/252 requires a calendar")
            n = calendar.business_days_between(Date.from_pydate(d1), Date.from_pydate(d2))
            return n / 252.0
        raise InputError(f"unhandled day count {self}")

    def name(self) -> str:  # type: ignore[override]
        return {
            DayCount.ACT_365F: "Actual/365 (Fixed)",
            DayCount.ACT_365L: "Actual/365L",
            DayCount.ACT_360: "Actual/360",
            DayCount.ACT_364: "Actual/364",
            DayCount.ACT_ACT_ISDA: "Actual/Actual (ISDA)",
            DayCount.ACT_ACT_AFB: "Actual/Actual (AFB)",
            DayCount.ACT_ACT_ICMA: "Actual/Actual (ICMA)",
            DayCount.THIRTY_360_BOND: "30/360 (Bond Basis)",
            DayCount.THIRTY_360_US: "30U/360 (US NASD)",
            DayCount.THIRTY_E_360: "30E/360 (Eurobond)",
            DayCount.THIRTY_E_360_ISDA: "30E/360 (ISDA)",
            DayCount.THIRTY_EPLUS_360: "30E+/360",
            DayCount.BUS_252: "Business/252",
        }[self]


def _feb29_in_range(d1: date, d2: date) -> bool:
    y = d1.year
    while y <= d2.year:
        if isleap(y):
            leap = date(y, 2, 29)
            if d1 <= leap < d2:
                return True
        y += 1
    return False


def _act_act_isda(d1: date, d2: date) -> float:
    y1, y2 = d1.year, d2.year
    if y1 == y2:
        den = 366.0 if isleap(y1) else 365.0
        return _days(d1, d2) / den
    total = 0.0
    first_end = date(y1 + 1, 1, 1)
    total += _days(d1, first_end) / (366.0 if isleap(y1) else 365.0)
    for year in range(y1 + 1, y2):
        total += 1.0
    last_start = date(y2, 1, 1)
    total += _days(last_start, d2) / (366.0 if isleap(y2) else 365.0)
    return total


def _act_act_afb(d1: date, d2: date) -> float:
    """AFB: if the interval contains 29 Feb, divide by 366 else 365. Split at years."""
    if d1.year == d2.year or (d1.year + 1 == d2.year and (d1.month, d1.day) >= (d2.month, d2.day)):
        den = 366.0 if _feb29_in_range(d1, d2) else 365.0
        return _days(d1, d2) / den
    # remaining years counted as 1 each, leftover as above
    end_1y = date(d1.year + (d2.year - d1.year), d1.month, min(d1.day, monthrange(d1.year + (d2.year - d1.year), d1.month)[1]))
    if end_1y > d2:
        end_1y = date(d2.year - 1, d1.month, min(d1.day, monthrange(d2.year - 1, d1.month)[1]))
    years = end_1y.year - d1.year
    den = 366.0 if _feb29_in_range(end_1y, d2) else 365.0
    return years + _days(end_1y, d2) / den


def _coupon_frequency_from_ref(ref_start: date, ref_end: date) -> int:
    days = _days(ref_start, ref_end)
    if days <= 0:
        raise InputError("empty ICMA reference period")
    target = 365.25 / days
    for freq in (1, 2, 4, 6, 12):
        if abs(target - freq) < 0.6:
            return freq
    return max(1, round(target))


def _act_act_icma(start: date, end: date, ref_start: date, ref_end: date) -> float:
    """ICMA: YF = days(start,end) / (days(ref) * frequency)."""
    if ref_end <= ref_start:
        raise InputError("ICMA reference period must be positive")
    freq = _coupon_frequency_from_ref(ref_start, ref_end)
    return _days(start, end) / (_days(ref_start, ref_end) * freq)


def _thirty_360_us(d1: date, d2: date) -> float:
    """US (NASD / ISDA 2006 30U/360, also Bond Basis with EOM February rule)."""
    y1, m1, dd1 = d1.year, d1.month, d1.day
    y2, m2, dd2 = d2.year, d2.month, d2.day
    if _is_last_day_of_february(d1):
        dd1 = 30
        if _is_last_day_of_february(d2):
            dd2 = 30
    if dd1 == 31:
        dd1 = 30
    if dd2 == 31 and dd1 >= 30:
        dd2 = 30
    return (360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)) / 360.0


def _thirty_e_360(d1: date, d2: date) -> float:
    y1, m1, dd1 = d1.year, d1.month, min(d1.day, 30)
    y2, m2, dd2 = d2.year, d2.month, min(d2.day, 30)
    return (360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)) / 360.0


def _thirty_e_360_isda(d1: date, d2: date, termination: date) -> float:
    y1, m1, dd1 = d1.year, d1.month, d1.day
    y2, m2, dd2 = d2.year, d2.month, d2.day
    if _is_eom(d1):
        dd1 = 30
    if _is_eom(d2) and not (d2.month == 2 and d2 == termination):
        dd2 = 30
    return (360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)) / 360.0


def _thirty_eplus_360(d1: date, d2: date) -> float:
    y1, m1, dd1 = d1.year, d1.month, min(d1.day, 30)
    y2, m2, dd2 = d2.year, d2.month, d2.day
    if dd2 == 31:
        m2 += 1
        if m2 == 13:
            m2 = 1
            y2 += 1
        dd2 = 1
    return (360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)) / 360.0
