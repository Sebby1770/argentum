"""Black vol surface: sticky-strike grid with bilinear interpolation in (T, k)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from argentum.errors import CurveError, InputError
from argentum.math.interpolation import linear
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount


@dataclass(frozen=True)
class BlackVolSurface:
    as_of: Date
    expiries: np.ndarray  # times
    strikes: np.ndarray
    vols: np.ndarray  # shape (n_exp, n_k)
    day_count: DayCount = DayCount.ACT_365F

    def t(self, d: DateLike | float) -> float:
        if isinstance(d, (int, float)):
            return float(d)
        return self.day_count.year_fraction(self.as_of, as_date(d))

    def vol(self, expiry: DateLike | float, strike: float) -> float:
        t = self.t(expiry)
        if t <= 0.0:
            return float(self.vols[0, 0])
        # interpolate in total variance along each strike, then across strikes
        w = np.empty(self.strikes.size)
        for j, k in enumerate(self.strikes):
            interp = linear(self.expiries, (self.vols[:, j] ** 2) * self.expiries)
            wj = interp(t)
            w[j] = max(wj, 0.0)
        # linear in strike on implied vol
        vols_t = np.sqrt(w / t) if t > 0 else self.vols[0]
        k_interp = linear(self.strikes, vols_t)
        # clamp strike to grid
        k = min(max(strike, float(self.strikes[0])), float(self.strikes[-1]))
        return float(k_interp(k))

    @classmethod
    def from_grid(
        cls,
        as_of: DateLike,
        expiries: list[DateLike | float],
        strikes: list[float],
        vols: list[list[float]],
        *,
        day_count: DayCount = DayCount.ACT_365F,
    ) -> "BlackVolSurface":
        as_of_d = as_date(as_of)
        times = np.array(
            [e if isinstance(e, (int, float)) else day_count.year_fraction(as_of_d, as_date(e)) for e in expiries],
            dtype=float,
        )
        k = np.array(strikes, dtype=float)
        v = np.array(vols, dtype=float)
        if v.shape != (times.size, k.size):
            raise InputError(f"vol grid shape {v.shape} != {(times.size, k.size)}")
        if np.any(v < 0.0):
            raise CurveError("negative vols")
        order = np.argsort(times)
        times, v = times[order], v[order]
        k_order = np.argsort(k)
        k, v = k[k_order], v[:, k_order]
        return cls(as_of_d, times, k, v, day_count)
