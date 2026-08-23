"""Dupire local volatility from a total-variance function (Gatheral).

``w(k, t)`` is Black total implied variance at log-moneyness ``k = ln(K/F)``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from argentum.errors import InputError
from argentum.models.sabr import sabr_implied_vol


def gatheral_local_var(
    k: float,
    t: float,
    w: Callable[[float, float], float],
    *,
    dk: float = 1e-4,
    dt: float = 1e-5,
) -> float:
    """Local variance σ_loc²(k, t) from Gatheral's formula. Returns 0 at t=0."""
    t = max(t, dt)
    w0 = w(k, t)
    if w0 <= 1e-16:
        return 0.0
    wp = w(k, t + dt)
    wm = w(k, max(t - dt, dt * 0.5))
    dw_dt = (wp - wm) / ((t + dt) - max(t - dt, dt * 0.5))
    wk = (w(k + dk, t) - w(k - dk, t)) / (2.0 * dk)
    wkk = (w(k + dk, t) - 2.0 * w0 + w(k - dk, t)) / (dk * dk)
    den = (1.0 - k * wk / (2.0 * w0)) ** 2 - 0.25 * (wk * wk) * (1.0 / w0 + 0.25) + 0.5 * wkk
    if den <= 1e-16:
        raise InputError("Dupire denominator non-positive (butterfly arb in the slice)")
    return max(dw_dt / den, 0.0)


def local_vol(k: float, t: float, w: Callable[[float, float], float]) -> float:
    return math.sqrt(gatheral_local_var(k, t, w))


def sabr_total_variance(
    forward: float,
    texp: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
) -> Callable[[float, float], float]:
    """Calendar-linear total variance from a SABR smile (sticky in k)."""

    def w(k: float, t: float) -> float:
        t = max(t, 1e-8)
        strike = forward * math.exp(k)
        iv = sabr_implied_vol(forward, max(strike, 1e-12), texp, alpha, beta, rho, nu)
        return iv * iv * t

    return w
