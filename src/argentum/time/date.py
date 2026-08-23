"""Immutable dates, IMM helpers, and Excel serial conversion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Union

from argentum.errors import InputError

DateLike = Union["Date", date]


def _as_date(value: DateLike) -> date:
    if isinstance(value, Date):
        return value._d
    if isinstance(value, date):
        return value
    raise InputError(f"expected Date or datetime.date, got {type(value)!r}")


@dataclass(frozen=True, order=True)
class Date:
    """A Gregorian calendar date.

    Ordered, hashable, and interchangeable with ``datetime.date``. Excel serials
    use the Windows 1900-system origin (1899-12-30) so they match Excel and
    QuantLib on Windows.
    """

    year: int
    month: int
    day: int

    @property
    def _d(self) -> date:
        return date(self.year, self.month, self.day)

    @classmethod
    def from_pydate(cls, value: date) -> "Date":
        return cls(value.year, value.month, value.day)

    @classmethod
    def today(cls) -> "Date":
        return cls.from_pydate(date.today())

    @classmethod
    def from_excel(cls, serial: int | float) -> "Date":
        origin = date(1899, 12, 30)
        return cls.from_pydate(origin + timedelta(days=int(serial)))

    @classmethod
    def end_of_month(cls, year: int, month: int) -> "Date":
        if month == 12:
            nxt = date(year + 1, 1, 1)
        else:
            nxt = date(year, month + 1, 1)
        return cls.from_pydate(nxt - timedelta(days=1))

    @classmethod
    def nth_weekday(cls, year: int, month: int, weekday: int, n: int) -> "Date":
        """``weekday`` is ISO (1=Mon … 7=Sun). ``n`` is 1-based; negative from end."""
        if n == 0:
            raise InputError("n must be non-zero")
        first = date(year, month, 1)
        if n > 0:
            offset = (weekday - first.isoweekday()) % 7
            day = 1 + offset + 7 * (n - 1)
            return cls(year, month, day)
        last = cls.end_of_month(year, month).to_pydate()
        offset = (last.isoweekday() - weekday) % 7
        return cls.from_pydate(last - timedelta(days=offset + 7 * (-n - 1)))

    @classmethod
    def imm(cls, year: int, month: int) -> "Date":
        """Third Wednesday of the month (CME IMM)."""
        return cls.nth_weekday(year, month, weekday=3, n=3)

    @classmethod
    def next_imm(cls, as_of: DateLike, *, quarterly: bool = True) -> "Date":
        d = _as_date(as_of)
        months = (3, 6, 9, 12) if quarterly else tuple(range(1, 13))
        year = d.year
        while True:
            for m in months:
                imm = cls.imm(year, m)
                if imm.to_pydate() > d:
                    return imm
            year += 1

    def to_pydate(self) -> date:
        return self._d

    def excel_serial(self) -> int:
        return (self._d - date(1899, 12, 30)).days

    def weekday(self) -> int:
        """ISO weekday: 1=Monday … 7=Sunday."""
        return self._d.isoweekday()

    def is_weekend(self) -> bool:
        return self.weekday() >= 6

    def is_end_of_month(self) -> bool:
        return (self._d + timedelta(days=1)).month != self.month

    def add_days(self, n: int) -> "Date":
        return Date.from_pydate(self._d + timedelta(days=int(n)))

    def add_weeks(self, n: int) -> "Date":
        return self.add_days(7 * int(n))

    def add_months(self, n: int, *, end_of_month: bool = False) -> "Date":
        """Advance by calendar months. Clamps the day; optional EOM rule."""
        month_index = self.year * 12 + (self.month - 1) + int(n)
        year, month0 = divmod(month_index, 12)
        month = month0 + 1
        eom = Date.end_of_month(year, month)
        if end_of_month and self.is_end_of_month():
            return eom
        day = min(self.day, eom.day)
        return Date(year, month, day)

    def add_years(self, n: int, *, end_of_month: bool = False) -> "Date":
        return self.add_months(12 * int(n), end_of_month=end_of_month)

    def __sub__(self, other: object) -> int:
        if isinstance(other, (Date, date)):
            return (self._d - _as_date(other)).days
        return NotImplemented

    def __add__(self, other: object) -> "Date":
        if isinstance(other, int):
            return self.add_days(other)
        from argentum.time.period import Period

        if isinstance(other, Period):
            return other.add_to(self)
        return NotImplemented

    def __str__(self) -> str:
        return self._d.isoformat()

    def __repr__(self) -> str:
        return f"Date({self.year}, {self.month}, {self.day})"


def as_date(value: DateLike) -> Date:
    if isinstance(value, Date):
        return value
    return Date.from_pydate(_as_date(value))


def days_between(d1: DateLike, d2: DateLike) -> int:
    return (as_date(d2) - as_date(d1))
