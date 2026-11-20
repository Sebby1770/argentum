"""Piecewise-constant hazard (credit) curves."""

from __future__ import annotations

from typing import TYPE_CHECKING

import math
from dataclasses import dataclass

import numpy as np

from argentum.errors import CurveError
from argentum.math.solvers import newton
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount

if TYPE_CHECKING:
    from argentum.termstructures.yield_curve import YieldCurve


@dataclass(frozen=True)
class HazardCurve:
    """Survival ``S(t) = exp(-∫ h)`` with piecewise-constant hazard on ``times``."""

    as_of: Date
    times: np.ndarray
    hazards: np.ndarray  # hazard on (t_{i-1}, t_i], times[0] > 0
    day_count: DayCount = DayCount.ACT_365F
    recovery: float = 0.4

    def t(self, d: DateLike | float) -> float:
        if isinstance(d, (int, float)):
            return float(d)
        return self.day_count.year_fraction(self.as_of, as_date(d))

    def hazard(self, d: DateLike | float) -> float:
        t = self.t(d)
        if t <= 0.0:
            return float(self.hazards[0])
        i = int(np.searchsorted(self.times, t, side="left"))
        i = min(i, self.hazards.size - 1)
        return float(self.hazards[i])

    def survival(self, d: DateLike | float) -> float:
        t = self.t(d)
        if t <= 0.0:
            return 1.0
        total = 0.0
        t0 = 0.0
        for ti, h in zip(self.times, self.hazards):
            t1 = min(ti, t)
            if t1 > t0:
                total += h * (t1 - t0)
            t0 = ti
            if t0 >= t:
                break
        if t > t0:
            total += float(self.hazards[-1]) * (t - t0)
        return math.exp(-total)

    @classmethod
    def flat(cls, as_of: DateLike, hazard: float, recovery: float = 0.4, years: float = 50.0) -> "HazardCurve":
        as_of_d = as_date(as_of)
        if hazard < 0.0:
            raise CurveError("hazard must be >= 0")
        return cls(as_of_d, np.array([years], dtype=float), np.array([hazard], dtype=float), recovery=recovery)


def par_cds_spread(
    hazard: HazardCurve,
    discount: "YieldCurve",
    maturity: DateLike | float,
    *,
    recovery: float | None = None,
    coupon_freq: int = 4,
) -> float:
    """Continuous-limit par CDS spread: (1-R) ∫ λ S df / ∫ S df."""
    r = hazard.recovery if recovery is None else recovery
    t_end = hazard.t(maturity)
    n = max(int(coupon_freq * t_end * 8), 40)
    dt = t_end / n
    num = den = 0.0
    for i in range(1, n + 1):
        t = i * dt
        s = hazard.survival(t)
        h = hazard.hazard(t)
        df = discount.df(t)
        num += df * s * h * dt
        den += df * s * dt
    if den == 0.0:
        return 0.0
    return (1.0 - r) * num / den


def bootstrap_hazard(
    as_of: DateLike,
    discount: "YieldCurve",
    quotes: list[tuple[float, float]],
    *,
    recovery: float = 0.4,
) -> HazardCurve:
    """Boot a piecewise-constant hazard from ``(maturity_years, par_spread)`` quotes."""
    as_of_d = as_date(as_of)
    if not quotes:
        raise CurveError("need at least one CDS quote")
    times: list[float] = []
    hazards: list[float] = []
    for maturity, spread in quotes:
        if maturity <= 0.0 or spread < 0.0:
            raise CurveError("CDS quotes must have positive maturity and non-negative spread")

        def obj(h: float, t=maturity, s=spread, ts=tuple(times), hs=tuple(hazards)) -> float:
            curve = HazardCurve(
                as_of_d,
                np.array(ts + (t,), dtype=float),
                np.array(hs + (max(h, 0.0),), dtype=float),
                recovery=recovery,
            )
            return par_cds_spread(curve, discount, t, recovery=recovery) - s

        guess = spread / max(1.0 - recovery, 0.05)
        h_star = newton(obj, max(guess, 1e-6), lower=0.0, upper=5.0, tol=1e-10)
        times.append(maturity)
        hazards.append(max(h_star, 0.0))
    return HazardCurve(as_of_d, np.array(times, dtype=float), np.array(hazards, dtype=float), recovery=recovery)
