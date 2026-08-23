"""Tenor arithmetic: ``Period(3, 'M')`` or ``Period.parse('18M')``."""

from __future__ import annotations

import re
from dataclasses import dataclass

from argentum.errors import InputError
from argentum.time.date import Date, DateLike, as_date
from argentum.types import Frequency

_PERIOD_RE = re.compile(r"^\s*([+-]?\d+)\s*([DWMYdwmy])\s*$")

_UNIT_DAYS = {"D": 1, "W": 7}


@dataclass(frozen=True, slots=True)
class Period:
    n: int
    unit: str  # D, W, M, Y

    def __post_init__(self) -> None:
        unit = self.unit.upper()
        if unit not in {"D", "W", "M", "Y"}:
            raise InputError(f"unknown period unit {self.unit!r}")
        object.__setattr__(self, "unit", unit)

    @classmethod
    def parse(cls, text: str | "Period") -> "Period":
        if isinstance(text, Period):
            return text
        match = _PERIOD_RE.match(str(text))
        if not match:
            raise InputError(f"cannot parse period {text!r}; expected e.g. '3M', '1Y', '7D'")
        return cls(int(match.group(1)), match.group(2).upper())

    @classmethod
    def from_frequency(cls, frequency: Frequency, n: int = 1) -> "Period":
        if frequency is Frequency.DAILY:
            return cls(n, "D")
        if frequency is Frequency.WEEKLY:
            return cls(n, "W")
        if frequency is Frequency.CONTINUOUS or frequency is Frequency.ONCE:
            raise InputError(f"no period for {frequency}")
        return cls(frequency.months() * n, "M")

    def years(self) -> float:
        if self.unit == "D":
            return self.n / 365.0
        if self.unit == "W":
            return self.n * 7.0 / 365.0
        if self.unit == "M":
            return self.n / 12.0
        return float(self.n)

    def add_to(self, d: DateLike, *, end_of_month: bool = False) -> Date:
        start = as_date(d)
        if self.unit == "D":
            return start.add_days(self.n)
        if self.unit == "W":
            return start.add_weeks(self.n)
        if self.unit == "M":
            return start.add_months(self.n, end_of_month=end_of_month)
        return start.add_years(self.n, end_of_month=end_of_month)

    def __neg__(self) -> "Period":
        return Period(-self.n, self.unit)

    def __mul__(self, k: int) -> "Period":
        return Period(self.n * int(k), self.unit)

    __rmul__ = __mul__

    def __str__(self) -> str:
        return f"{self.n}{self.unit}"

    def __repr__(self) -> str:
        return f"Period({self.n}, {self.unit!r})"


def tenor(text: str | Period) -> Period:
    return Period.parse(text)
