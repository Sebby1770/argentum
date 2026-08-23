"""Holiday calendars and business-day adjustments.

Calendars are deterministic functions of the Gregorian year. TARGET follows the
ECB TARGET2 calendar. US variants follow SIFMA / NYSE / Federal Reserve
observance rules (Saturday → Friday, Sunday → Monday) unless noted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from calendar import monthrange
from datetime import date, timedelta
from functools import lru_cache

from argentum.errors import CalendarError
from argentum.time.date import Date, DateLike, as_date
from argentum.types import BusinessDayConvention as BDC


def easter_gregorian(year: int) -> date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day0 = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day0 + 1)


def _observed_us(d: date) -> date:
    wd = d.isoweekday()
    if wd == 6:
        return d - timedelta(days=1)
    if wd == 7:
        return d + timedelta(days=1)
    return d


def _observed_uk(d: date) -> date:
    wd = d.isoweekday()
    if wd == 6:
        return d + timedelta(days=2)
    if wd == 7:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    return Date.nth_weekday(year, month, weekday, n).to_pydate()


def _last_weekday(year: int, month: int, weekday: int) -> date:
    return Date.nth_weekday(year, month, weekday, -1).to_pydate()


class Calendar(ABC):
    name: str = "Calendar"

    def is_holiday(self, d: DateLike) -> bool:
        py = as_date(d).to_pydate()
        if py.isoweekday() >= 6:
            return True
        return py in self.holidays(py.year) or (
            # New Year observed into previous year (US)
            py.year + 1 >= 1900 and py in self.holidays(py.year + 1)
        )

    def is_business_day(self, d: DateLike) -> bool:
        return not self.is_holiday(d)

    @abstractmethod
    def holidays(self, year: int) -> frozenset[date]:
        raise NotImplementedError

    def adjust(self, d: DateLike, convention: BDC = BDC.MODIFIED_FOLLOWING) -> Date:
        current = as_date(d)
        if convention is BDC.UNADJUSTED or self.is_business_day(current):
            return current
        if convention is BDC.FOLLOWING:
            return self._advance_bd(current, 1)
        if convention is BDC.PRECEDING:
            return self._advance_bd(current, -1)
        if convention is BDC.MODIFIED_FOLLOWING:
            nxt = self._advance_bd(current, 1)
            if nxt.month != current.month:
                return self._advance_bd(current, -1)
            return nxt
        if convention is BDC.MODIFIED_PRECEDING:
            prev = self._advance_bd(current, -1)
            if prev.month != current.month:
                return self._advance_bd(current, 1)
            return prev
        if convention is BDC.NEAREST:
            fwd = self._advance_bd(current, 1)
            back = self._advance_bd(current, -1)
            if (fwd - current) < (current - back):
                return fwd
            return back
        raise CalendarError(f"unknown convention {convention}")

    def advance(
        self,
        d: DateLike,
        n: int,
        *,
        unit: str = "D",
        convention: BDC = BDC.FOLLOWING,
        end_of_month: bool = False,
    ) -> Date:
        start = as_date(d)
        unit = unit.upper()
        if unit == "D" and n != 0 and self._is_business_day_count(n):
            return self._advance_bd(start, n)
        from argentum.time.period import Period

        raw = Period(n, unit if unit != "B" else "D").add_to(start, end_of_month=end_of_month)
        if unit == "B":
            return self._advance_bd(start, n)
        return self.adjust(raw, convention)

    def _is_business_day_count(self, n: int) -> bool:
        return True

    def _advance_bd(self, start: Date, n: int) -> Date:
        if n == 0:
            return start if self.is_business_day(start) else self.adjust(start, BDC.FOLLOWING)
        step = 1 if n > 0 else -1
        left = abs(int(n))
        current = start.to_pydate()
        while left:
            current = current + timedelta(days=step)
            if not self.is_holiday(Date.from_pydate(current)):
                left -= 1
        return Date.from_pydate(current)

    def business_days_between(self, start: DateLike, end: DateLike) -> int:
        a = as_date(start).to_pydate()
        b = as_date(end).to_pydate()
        if a == b:
            return 0
        sign = 1
        if a > b:
            a, b, sign = b, a, -1
        n = 0
        current = a
        while current < b:
            current = current + timedelta(days=1)
            if not self.is_holiday(Date.from_pydate(current)):
                n += 1
        return sign * n

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class WeekendsOnly(Calendar):
    name = "WeekendsOnly"

    def holidays(self, year: int) -> frozenset[date]:
        return frozenset()


class NullCalendar(Calendar):
    """Every day is a business day, including weekends."""

    name = "Null"

    def is_holiday(self, d: DateLike) -> bool:
        return False

    def holidays(self, year: int) -> frozenset[date]:
        return frozenset()


class TARGET(Calendar):
    """TARGET2: Sat/Sun, 1 Jan, Good Friday, Easter Monday, 1 May, 25/26 Dec."""

    name = "TARGET"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        easter = easter_gregorian(year)
        days = {
            date(year, 1, 1),
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            date(year, 5, 1),
            date(year, 12, 25),
            date(year, 12, 26),
        }
        if year >= 2000:
            days.add(date(year, 12, 31))  # not TARGET2; keep Christmas cluster only
            days.discard(date(year, 12, 31))
        return frozenset(d for d in days if d.isoweekday() < 6)


class UnitedStatesSettlement(Calendar):
    """US Federal Reserve / settlement (SIFMA-like federal holidays)."""

    name = "US Settlement"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        days = {
            _observed_us(date(year, 1, 1)),
            _nth_weekday(year, 1, 1, 3),  # MLK
            _nth_weekday(year, 2, 1, 3),  # Presidents
            _last_weekday(year, 5, 1),  # Memorial
            _observed_us(date(year, 7, 4)),
            _nth_weekday(year, 9, 1, 1),  # Labor
            _nth_weekday(year, 10, 1, 2),  # Columbus
            _observed_us(date(year, 11, 11)),  # Veterans
            _nth_weekday(year, 11, 4, 4),  # Thanksgiving
            _observed_us(date(year, 12, 25)),
        }
        if year >= 2021:
            days.add(_observed_us(date(year, 6, 19)))
        return frozenset(days)


class UnitedStatesNYSE(Calendar):
    name = "US NYSE"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        easter = easter_gregorian(year)
        days = {
            _observed_us(date(year, 1, 1)),
            _nth_weekday(year, 1, 1, 3),
            _nth_weekday(year, 2, 1, 3),
            easter - timedelta(days=2),  # Good Friday
            _last_weekday(year, 5, 1),
            _observed_us(date(year, 7, 4)),
            _nth_weekday(year, 9, 1, 1),
            _nth_weekday(year, 11, 4, 4),
            _observed_us(date(year, 12, 25)),
        }
        if year >= 2022:
            days.add(_observed_us(date(year, 6, 19)))
        return frozenset(days)


class UnitedStatesGovernmentBond(Calendar):
    name = "US Government Bond"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        # SIFMA: federal plus Good Friday. Columbus/Veterans included.
        base = set(UnitedStatesSettlement().holidays(year))
        easter = easter_gregorian(year)
        gf = easter - timedelta(days=2)
        if gf.isoweekday() < 6:
            base.add(gf)
        return frozenset(base)


class UnitedKingdom(Calendar):
    name = "UK"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        easter = easter_gregorian(year)
        days = {
            _observed_uk(date(year, 1, 1)),
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            _nth_weekday(year, 5, 1, 1),  # Early May
            _last_weekday(year, 5, 1),  # Spring
            _last_weekday(year, 8, 1),  # Summer
            _observed_uk(date(year, 12, 25)),
            _observed_uk(date(year, 12, 26)),
        }
        # Boxing Day / Christmas clustering
        xmas = date(year, 12, 25)
        boxing = date(year, 12, 26)
        if xmas.isoweekday() == 6:  # Sat
            days.add(date(year, 12, 28))
        elif xmas.isoweekday() == 7:  # Sun
            days.add(date(year, 12, 27))
            days.add(date(year, 12, 28))
        elif boxing.isoweekday() == 6:
            days.add(date(year, 12, 28))
        elif boxing.isoweekday() == 7:
            days.add(date(year, 12, 28))
        return frozenset(days)


class Japan(Calendar):
    """Japanese national holidays with Happy Monday and substitute Sundays."""

    name = "Japan"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        days: set[date] = {
            date(year, 1, 1),
            _nth_weekday(year, 1, 1, 2),  # Coming of Age
            date(year, 2, 11),
            date(year, 2, 23),  # Emperor
            date(year, 4, 29),
            date(year, 5, 3),
            date(year, 5, 4),
            date(year, 5, 5),
            _nth_weekday(year, 7, 1, 3),  # Marine
            date(year, 8, 11),
            _nth_weekday(year, 9, 1, 3),  # Respect for the Aged
            _nth_weekday(year, 10, 1, 2),  # Sports
            date(year, 11, 3),
            date(year, 11, 23),
        }
        # Equinoxes: approximate (Meeus). Good to the correct civil day 2000–2099.
        vernal = date(year, 3, int(20.8431 + 0.242194 * (year - 1851) - (year - 1851) // 4))
        autumnal = date(year, 9, int(23.2488 + 0.242194 * (year - 1851) - (year - 1851) // 4))
        days.add(vernal)
        days.add(autumnal)
        # Golden Week / substitute: a Sunday holiday moves to the next open weekday.
        closed = set(days)
        extra: set[date] = set()
        for h in list(closed):
            if h.isoweekday() == 7:
                n = h + timedelta(days=1)
                while n in closed or n.isoweekday() >= 6:
                    n += timedelta(days=1)
                extra.add(n)
        closed |= extra
        # Jan 2–3 bank holidays commonly observed by JSDA
        closed.add(date(year, 1, 2))
        closed.add(date(year, 1, 3))
        return frozenset(d for d in closed if d.isoweekday() < 6 or d in {date(year, 1, 1)})


class Australia(Calendar):
    name = "Australia"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        easter = easter_gregorian(year)
        days = {
            _observed_uk(date(year, 1, 1)),
            _observed_uk(date(year, 1, 26)),
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            _observed_uk(date(year, 4, 25)),  # Anzac
            _nth_weekday(year, 6, 1, 2),  # King's Birthday (most states)
            _observed_uk(date(year, 12, 25)),
            _observed_uk(date(year, 12, 26)),
        }
        return frozenset(days)


class Switzerland(Calendar):
    """SIX / Zurich: New Year, Good Friday, Easter Monday, Ascension, Whit Monday, 1 Aug, Christmas."""

    name = "Switzerland"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        easter = easter_gregorian(year)
        days = {
            date(year, 1, 1),
            date(year, 1, 2),  # Berchtoldstag
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            easter + timedelta(days=39),  # Ascension
            easter + timedelta(days=50),  # Whit Monday
            date(year, 8, 1),
            date(year, 12, 25),
            date(year, 12, 26),
        }
        return frozenset(d for d in days if d.isoweekday() < 6)


class Canada(Calendar):
    """TSX-style: New Year, Family Day (3rd Mon Feb, ON), Good Friday, Victoria Day, Canada Day, Labour, Thanksgiving, Christmas."""

    name = "Canada"

    @lru_cache(maxsize=256)
    def holidays(self, year: int) -> frozenset[date]:  # type: ignore[override]
        easter = easter_gregorian(year)
        days = {
            _observed_uk(date(year, 1, 1)),
            _nth_weekday(year, 2, 1, 3),  # Family Day (ON)
            easter - timedelta(days=2),
            _observed_uk(date(year, 7, 1)),
            _nth_weekday(year, 9, 1, 1),
            _nth_weekday(year, 10, 1, 2),
            _observed_uk(date(year, 12, 25)),
            _observed_uk(date(year, 12, 26)),
        }
        # Victoria Day: Monday on or before 24 May
        may24 = date(year, 5, 24)
        while may24.isoweekday() != 1:
            may24 -= timedelta(days=1)
        days.add(may24)
        return frozenset(days)


class JointCalendar(Calendar):
    """Holiday if *any* constituent calendar is on holiday (join = union)."""

    def __init__(self, *calendars: Calendar, name: str | None = None) -> None:
        if not calendars:
            raise CalendarError("JointCalendar needs at least one calendar")
        self._cals = calendars
        self.name = name or "+".join(c.name for c in calendars)

    def holidays(self, year: int) -> frozenset[date]:
        acc: set[date] = set()
        for cal in self._cals:
            acc |= set(cal.holidays(year))
        return frozenset(acc)

    def is_holiday(self, d: DateLike) -> bool:
        return any(c.is_holiday(d) for c in self._cals)


_REGISTRY: dict[str, type[Calendar] | Calendar] = {
    "null": NullCalendar,
    "weekends": WeekendsOnly,
    "target": TARGET,
    "target2": TARGET,
    "us": UnitedStatesSettlement,
    "us-settlement": UnitedStatesSettlement,
    "us-nyse": UnitedStatesNYSE,
    "us-govt": UnitedStatesGovernmentBond,
    "uk": UnitedKingdom,
    "gb": UnitedKingdom,
    "jp": Japan,
    "japan": Japan,
    "au": Australia,
    "australia": Australia,
    "ch": Switzerland,
    "switzerland": Switzerland,
    "ca": Canada,
    "canada": Canada,
}


def calendar(name: str) -> Calendar:
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise CalendarError(f"unknown calendar {name!r}; known: {sorted(_REGISTRY)}")
    spec = _REGISTRY[key]
    return spec() if isinstance(spec, type) else spec
