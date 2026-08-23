"""Bump-and-revalue risk: DV01, key-rate buckets, parametric VaR."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date


@dataclass(frozen=True, slots=True)
class BucketDelta:
    tenor_years: float
    delta: float


@dataclass(frozen=True, slots=True)
class RiskReport:
    npv: float
    dv01: float
    gamma_1bp: float
    buckets: tuple[BucketDelta, ...]
    cs01: float | None = None


def _scale_curve(curve: YieldCurve, shift: float) -> YieldCurve:
    dates = []
    dfs = []
    for t, df in zip(curve.times, curve.dfs):
        dates.append(curve.as_of.add_days(max(int(round(t * 365.0)), 0)))
        dfs.append(df * math.exp(-shift * t))
    if curve.times.size and curve.times[0] == 0.0:
        dates, dfs = dates[1:], dfs[1:]
    return YieldCurve.from_discount_factors(
        curve.as_of,
        dates,
        dfs,
        day_count=curve.day_count,
        interpolation=curve.interpolation,
        interpolator_kind="linear",
        compounding=curve.compounding,
        frequency=curve.frequency,
    )


def parallel_dv01(npv_fn: Callable[[YieldCurve], float], curve: YieldCurve, bump: float = 1e-4) -> float:
    base = npv_fn(curve)
    up = npv_fn(_scale_curve(curve, bump))
    return (up - base) / (bump * 10_000.0)


def key_rate_dv01(
    npv_fn: Callable[[YieldCurve], float],
    curve: YieldCurve,
    tenors: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    bump: float = 1e-4,
) -> list[BucketDelta]:
    """Triangle key-rate bumps on log-discount around the given tenors."""
    base = npv_fn(curve)
    times = curve.times
    log_df = np.log(np.maximum(curve.dfs, 1e-16))
    out: list[BucketDelta] = []
    for k, t_k in enumerate(tenors):
        bump_vec = np.zeros_like(times)
        t_left = tenors[k - 1] if k else 0.0
        t_right = tenors[k + 1] if k + 1 < len(tenors) else tenors[k] * 2.0
        for i, t in enumerate(times):
            if t_left < t <= t_k:
                w = (t - t_left) / (t_k - t_left) if t_k != t_left else 1.0
            elif t_k < t < t_right:
                w = (t_right - t) / (t_right - t_k) if t_right != t_k else 0.0
            elif abs(t - t_k) < 1e-12:
                w = 1.0
            else:
                w = 0.0
            bump_vec[i] = w * bump
        log_bumped = log_df - bump_vec * times  # DF *= exp(-bump * t * w)
        dfs_b = np.exp(log_bumped)
        dates = [curve.as_of.add_days(max(int(round(t * 365.0)), 0)) for t in times]
        if times.size and times[0] == 0.0:
            dates, dfs_use = dates[1:], dfs_b[1:]
        else:
            dfs_use = dfs_b
        bumped = YieldCurve.from_discount_factors(
            curve.as_of, dates, list(dfs_use), day_count=curve.day_count, interpolator_kind="linear"
        )
        out.append(BucketDelta(t_k, (npv_fn(bumped) - base) / (bump * 10_000.0)))
    return out


def parametric_var(
    pnls: np.ndarray | list[float],
    *,
    alpha: float = 0.99,
    horizon_days: int = 1,
) -> dict[str, float]:
    """Gaussian VaR / ES plus historical percentile on a PnL sample."""
    x = np.asarray(pnls, dtype=float)
    mu = float(x.mean())
    sig = float(x.std(ddof=1)) if x.size > 1 else 0.0
    from argentum.math.special import norm_inv

    z = abs(norm_inv(1.0 - alpha))
    var_g = -(mu - z * sig)
    es_g = -(mu - sig * math.exp(-0.5 * z * z) / (math.sqrt(2 * math.pi) * (1.0 - alpha)))
    hist = -float(np.quantile(x, 1.0 - alpha))
    return {
        "mean": mu,
        "stdev": sig,
        "var_gaussian": var_g * math.sqrt(horizon_days),
        "es_gaussian": es_g * math.sqrt(horizon_days),
        "var_historical": hist,
        "alpha": alpha,
        "n": float(x.size),
    }
