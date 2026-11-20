"""Discount / forwarding curves with log-discount interpolation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import math
from dataclasses import dataclass

import numpy as np

from argentum.errors import CurveError, InputError
from argentum.math.interpolation import Interpolator, make_interpolator
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount
from argentum.types import Compounding, Frequency

if TYPE_CHECKING:
    from argentum.time.calendar import Calendar


def _rate_from_df(df: float, t: float, compounding: Compounding, frequency: Frequency) -> float:
    if t <= 0.0:
        return 0.0
    if df <= 0.0:
        raise CurveError("non-positive discount factor")
    if compounding is Compounding.CONTINUOUS:
        return -math.log(df) / t
    if compounding is Compounding.SIMPLE:
        return (1.0 / df - 1.0) / t
    n = frequency.periods_per_year()
    if not math.isfinite(n):
        return -math.log(df) / t
    return n * (df ** (-1.0 / (n * t)) - 1.0)


def _df_from_rate(rate: float, t: float, compounding: Compounding, frequency: Frequency) -> float:
    if t <= 0.0:
        return 1.0
    if compounding is Compounding.CONTINUOUS:
        return math.exp(-rate * t)
    if compounding is Compounding.SIMPLE:
        return 1.0 / (1.0 + rate * t)
    n = frequency.periods_per_year()
    if not math.isfinite(n):
        return math.exp(-rate * t)
    return (1.0 + rate / n) ** (-n * t)


@dataclass(frozen=True)
class YieldCurve:
    """A discount curve as of ``as_of``.

    Internally interpolates log-discount vs ACT/365F time by default, which
    yields piecewise-constant instantaneous forwards under linear interpolation
    of log DF — the industry default for swap bootstraps.
    """

    as_of: Date
    times: np.ndarray
    dfs: np.ndarray
    interpolator: Interpolator
    day_count: DayCount = DayCount.ACT_365F
    compounding: Compounding = Compounding.CONTINUOUS
    frequency: Frequency = Frequency.ANNUAL
    interpolation: str = "log_discount"
    calendar: "Calendar | None" = None

    def t(self, d: DateLike) -> float:
        return self.day_count.year_fraction(self.as_of, as_date(d), calendar=self.calendar)

    def df(self, d: DateLike | float) -> float:
        t = float(d) if isinstance(d, (int, float)) else self.t(d)
        if t <= 0.0:
            return 1.0
        if self.interpolation == "log_discount":
            log_df = self.interpolator(t)
            return math.exp(log_df)
        if self.interpolation == "zero":
            z = self.interpolator(t)
            return _df_from_rate(z, t, self.compounding, self.frequency)
        if self.interpolation == "df":
            return float(self.interpolator(t))
        raise CurveError(f"unknown interpolation {self.interpolation}")

    def zero(self, d: DateLike | float) -> float:
        t = float(d) if isinstance(d, (int, float)) else self.t(d)
        return _rate_from_df(self.df(t), t, self.compounding, self.frequency)

    def forward(self, start: DateLike | float, end: DateLike | float, *, simple: bool = True) -> float:
        t1 = float(start) if isinstance(start, (int, float)) else self.t(start)
        t2 = float(end) if isinstance(end, (int, float)) else self.t(end)
        if t2 <= t1:
            raise InputError("forward end must be after start")
        df1, df2 = self.df(t1), self.df(t2)
        if simple:
            return (df1 / df2 - 1.0) / (t2 - t1)
        return math.log(df1 / df2) / (t2 - t1)

    def instantaneous_forward(self, d: DateLike | float, h: float = 1e-5) -> float:
        t = float(d) if isinstance(d, (int, float)) else self.t(d)
        t = max(t, 0.0)
        return self.forward(t, t + h, simple=False)

    @classmethod
    def from_discount_factors(
        cls,
        as_of: DateLike,
        dates: Sequence[DateLike],
        dfs: Sequence[float],
        *,
        day_count: DayCount = DayCount.ACT_365F,
        interpolation: str = "log_discount",
        interpolator_kind: str = "linear",
        compounding: Compounding = Compounding.CONTINUOUS,
        frequency: Frequency = Frequency.ANNUAL,
        calendar: "Calendar | None" = None,
    ) -> "YieldCurve":
        as_of_d = as_date(as_of)
        times = np.array([day_count.year_fraction(as_of_d, as_date(d), calendar=calendar) for d in dates], dtype=np.float64)
        df_arr = np.array(dfs, dtype=float)
        if np.any(df_arr <= 0.0):
            raise CurveError("discount factors must be positive")
        order = np.argsort(times)
        times, df_arr = times[order], df_arr[order]
        if times[0] > 1e-12:
            times = np.insert(times, 0, 0.0)
            df_arr = np.insert(df_arr, 0, 1.0)
        if interpolation == "log_discount":
            interp = make_interpolator(interpolator_kind, times, np.log(df_arr))
        elif interpolation == "zero":
            zeros = np.array(
                [_rate_from_df(df, t, compounding, frequency) if t > 0 else 0.0 for t, df in zip(times, df_arr)]
            )
            if len(zeros) > 1:
                zeros[0] = zeros[1]
            interp = make_interpolator(interpolator_kind, times, zeros)
        else:
            interp = make_interpolator(interpolator_kind, times, df_arr)
        return cls(
            as_of=as_of_d,
            times=times,
            dfs=df_arr,
            interpolator=interp,
            day_count=day_count,
            compounding=compounding,
            frequency=frequency,
            interpolation=interpolation,
            calendar=calendar,
        )

    @classmethod
    def from_zeros(
        cls,
        as_of: DateLike,
        dates: list[DateLike],
        zeros: list[float],
        *,
        day_count: DayCount = DayCount.ACT_365F,
        compounding: Compounding = Compounding.CONTINUOUS,
        frequency: Frequency = Frequency.ANNUAL,
        interpolator_kind: str = "linear",
        calendar: "Calendar | None" = None,
    ) -> "YieldCurve":
        as_of_d = as_date(as_of)
        dfs = []
        for d, z in zip(dates, zeros):
            t = day_count.year_fraction(as_of_d, as_date(d), calendar=calendar)
            dfs.append(_df_from_rate(z, t, compounding, frequency))
        return cls.from_discount_factors(
            as_of_d,
            dates,
            dfs,
            day_count=day_count,
            interpolation="log_discount",
            interpolator_kind=interpolator_kind,
            compounding=compounding,
            frequency=frequency,
            calendar=calendar,
        )

    @classmethod
    def flat(
        cls,
        as_of: DateLike,
        rate: float,
        *,
        day_count: DayCount = DayCount.ACT_365F,
        compounding: Compounding = Compounding.CONTINUOUS,
        years: float = 50.0,
    ) -> "YieldCurve":
        as_of_d = as_date(as_of)
        far = as_of_d.add_years(int(years) + 1)
        df = _df_from_rate(rate, day_count.year_fraction(as_of_d, far), compounding, Frequency.ANNUAL)
        return cls.from_discount_factors(as_of_d, [far], [df], day_count=day_count, compounding=compounding)
