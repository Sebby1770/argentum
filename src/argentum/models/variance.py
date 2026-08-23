"""Variance-swap fair strike via the log contract (Carr–Madan / Demeterfi).

A pure Black–Scholes world gives ``K_var = σ²``. With a smile ``vol(K)`` the
fair delivery variance is the integral of OTM vanillas against ``2/K²``.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from argentum.math.integration import gauss_legendre
from argentum.models.black_scholes import price
from argentum.types import OptionType, require_positive


def black_variance_strike(vol: float) -> float:
    """Fair variance in a flat-vol world (not multiplied by 100²)."""
    return float(vol) * float(vol)


def log_contract_fair_variance(
    spot: float,
    rate: float,
    div: float,
    texp: float,
    vol_fn: Callable[[float], float],
    *,
    k_min: float | None = None,
    k_max: float | None = None,
    n_gl: int = 16,
) -> float:
    """Replicate ``E[∫ σ² dt] / T`` with a continuum of OTM vanillas.

    ``vol_fn(K)`` returns Black vol at strike K. Split at the forward;
    Gauss–Legendre on each wing. Prices from ``price`` are discounted, so the
    ``e^{rT}`` factor undoes that.
    """
    spot = require_positive("spot", spot)
    texp = require_positive("texp", texp)
    fwd = spot * math.exp((rate - div) * texp)
    lo = k_min if k_min is not None else max(fwd * 0.2, 1e-8)
    hi = k_max if k_max is not None else fwd * 2.5

    def otm(k: float) -> float:
        vol = max(vol_fn(k), 1e-8)
        if k < fwd:
            return price(spot, k, rate, div, vol, texp, OptionType.PUT)
        return price(spot, k, rate, div, vol, texp, OptionType.CALL)

    def integrand(k: float) -> float:
        if k <= 0.0:
            return 0.0
        return otm(k) / (k * k)

    put_leg = gauss_legendre(integrand, lo, fwd, n_gl)
    call_leg = gauss_legendre(integrand, fwd, hi, n_gl)
    return (2.0 * math.exp(rate * texp) / texp) * (put_leg + call_leg)


def variance_swap_payoff(realized_var: float, fair_strike: float, var_notional: float = 1.0) -> float:
    """Payoff of a long variance swap: ``N * (σ_realised² - K_var)``."""
    return var_notional * (realized_var - fair_strike)
