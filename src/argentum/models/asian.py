"""Geometric Asian closed form (Kemna–Vorst 1990) and arithmetic Turnbull–Wakeman."""

from __future__ import annotations

import math

from argentum.math.special import black_d1_d2, norm_cdf
from argentum.types import OptionType, require_non_negative, require_positive


def geometric_asian_price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    *,
    n_obs: int = 0,
) -> float:
    """Continuous geometric average (n_obs=0) or discrete equally spaced."""
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    if texp == 0.0:
        return max(spot - strike, 0.0) if opt is OptionType.CALL else max(strike - spot, 0.0)
    if n_obs and n_obs > 1:
        b = 0.5 * (rate - div - vol * vol / 6.0)  # still use continuous limit as baseline
        vol_a = vol / math.sqrt(3.0)
        # discrete adjustment: var of log-average of n lognormals
        dt = texp / n_obs
        var = vol * vol * dt * (n_obs + 1) * (2 * n_obs + 1) / (6.0 * n_obs)
        vol_a = math.sqrt(var / texp)
        mu = (rate - div - 0.5 * vol * vol) * dt * (n_obs + 1) / 2.0
        fwd = spot * math.exp(mu + 0.5 * var)
    else:
        vol_a = vol / math.sqrt(3.0)
        b = 0.5 * (rate + (rate - div) - vol * vol / 6.0)  # cost of carry of the average
        # Kemna-Vorst: S_A has r_a = 0.5 (r+q) wait:
        # drift of geometric average = (r - q - σ²/6)/2  relative to log S? Standard:
        b = 0.5 * (rate - div - vol * vol / 6.0)
        fwd = spot * math.exp(b * texp)
        vol_a = vol / math.sqrt(3.0)
    df = math.exp(-rate * texp)
    d1, d2 = black_d1_d2(fwd, strike, vol_a, texp)
    if opt is OptionType.CALL:
        return df * (fwd * norm_cdf(d1) - strike * norm_cdf(d2))
    return df * (strike * norm_cdf(-d2) - fwd * norm_cdf(-d1))


def turnbull_wakeman_price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Arithmetic Asian moment-matching (Turnbull–Wakeman / Levy)."""
    opt = OptionType(option_type)
    b = rate - div
    if abs(b) < 1e-14:
        m1 = spot * texp
        m2 = 2.0 * spot * spot / (vol**4) * (math.exp(vol * vol * texp) - 1.0 - vol * vol * texp)
    else:
        m1 = spot / b * (math.exp(b * texp) - 1.0)
        m2 = (
            2.0
            * spot
            * spot
            / (b + vol * vol)
            * ((math.exp((2.0 * b + vol * vol) * texp) - 1.0) / (2.0 * b + vol * vol) - (math.exp(b * texp) - 1.0) / b)
        )
    # average = M1/T
    ea = m1 / texp
    # variance of average
    var = m2 / (texp * texp) - ea * ea
    if var <= 0.0:
        df = math.exp(-rate * texp)
        intrinsic = max(ea - strike, 0.0) if opt is OptionType.CALL else max(strike - ea, 0.0)
        return df * intrinsic
    vol_a = math.sqrt(math.log(1.0 + var / (ea * ea)) / texp)
    df = math.exp(-rate * texp)
    d1, d2 = black_d1_d2(ea, strike, vol_a, texp)
    if opt is OptionType.CALL:
        return df * (ea * norm_cdf(d1) - strike * norm_cdf(d2))
    return df * (strike * norm_cdf(-d2) - ea * norm_cdf(-d1))
