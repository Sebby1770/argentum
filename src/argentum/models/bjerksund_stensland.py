"""Bjerksund–Stensland 2002 American approximation.

Accurate for American calls on dividend-paying assets and, via the GBM
put-call transformation ``S ↔ K, r ↔ q``, for American puts.
"""

from __future__ import annotations

import math

from argentum.math.special import norm_cdf
from argentum.models.black_scholes import price as european_price
from argentum.types import OptionType, require_non_negative, require_positive


def _phi(s: float, t: float, gamma: float, h: float, i: float, r: float, q: float, vol: float) -> float:
    """Bjerksund–Stensland φ function."""
    lam = (-r + gamma * (q + 0.5 * gamma * vol * vol)) * t
    d = -(math.log(s / h) + (q + (gamma - 0.5) * vol * vol) * t) / (vol * math.sqrt(t))
    kappa = 2.0 * (r - q) / (vol * vol) + (2.0 * gamma - 1.0)
    if s <= 0.0 or i <= 0.0 or h <= 0.0:
        return 0.0
    return math.exp(lam) * (
        s**gamma * (norm_cdf(d) - (i / s) ** kappa * norm_cdf(d - 2.0 * math.log(i / s) / (vol * math.sqrt(t))))
    )


def bjerksund_stensland_call(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
) -> float:
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    if texp == 0.0:
        return max(spot - strike, 0.0)
    if vol == 0.0:
        # deterministic
        fwd = spot * math.exp((rate - div) * texp)
        euro = math.exp(-rate * texp) * max(fwd - strike, 0.0)
        return max(spot - strike, euro)
    if div <= 0.0:
        # never exercise a call if q=0
        return european_price(spot, strike, rate, div, vol, texp, OptionType.CALL)
    beta = (0.5 - (rate - div) / (vol * vol)) + math.sqrt(
        ((rate - div) / (vol * vol) - 0.5) ** 2 + 2.0 * rate / (vol * vol)
    )
    b_inf = beta / (beta - 1.0) * strike
    b0 = max(strike, rate / div * strike)
    # 2002 trigger
    ht = -(div * texp + 2.0 * vol * math.sqrt(texp)) * (b0 / (b_inf - b0))
    i = b0 + (b_inf - b0) * (1.0 - math.exp(ht))
    if spot >= i:
        return spot - strike
    alpha = (i - strike) * i ** (-beta)
    return (
        alpha * spot**beta
        - alpha * _phi(spot, texp, beta, i, i, rate, rate - div, vol)
        + _phi(spot, texp, 1.0, i, i, rate, rate - div, vol)
        - _phi(spot, texp, 1.0, strike, i, rate, rate - div, vol)
        - strike * _phi(spot, texp, 0.0, i, i, rate, rate - div, vol)
        + strike * _phi(spot, texp, 0.0, strike, i, rate, rate - div, vol)
    )


def bjerksund_stensland(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.PUT,
) -> float:
    opt = OptionType(option_type)
    if opt is OptionType.CALL:
        return max(
            bjerksund_stensland_call(spot, strike, rate, div, vol, texp),
            european_price(spot, strike, rate, div, vol, texp, OptionType.CALL),
        )
    # McDonald symmetry: American put(S,K,r,q) = American call(K,S,q,r)
    return max(
        bjerksund_stensland_call(strike, spot, div, rate, vol, texp),
        european_price(spot, strike, rate, div, vol, texp, OptionType.PUT),
    )
