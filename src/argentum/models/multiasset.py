"""Margrabe exchange and Kirk spread options."""

from __future__ import annotations

import math

from argentum.errors import InputError
from argentum.math.special import black_d1_d2, norm_cdf
from argentum.models.black import black_price
from argentum.types import OptionType, require_non_negative, require_positive


def margrabe(
    s1: float,
    s2: float,
    vol1: float,
    vol2: float,
    rho: float,
    texp: float,
    q1: float = 0.0,
    q2: float = 0.0,
) -> float:
    """Price of the right to exchange asset 2 for asset 1: ``(S1_T - S2_T)+``."""
    s1 = require_positive("s1", s1)
    s2 = require_positive("s2", s2)
    vol1 = require_non_negative("vol1", vol1)
    vol2 = require_non_negative("vol2", vol2)
    texp = require_non_negative("texp", texp)
    if not -1.0 <= rho <= 1.0:
        raise InputError("rho must be in [-1, 1]")
    if texp == 0.0:
        return max(s1 - s2, 0.0)
    sig = math.sqrt(max(vol1 * vol1 + vol2 * vol2 - 2.0 * rho * vol1 * vol2, 0.0))
    if sig == 0.0:
        fwd = s1 * math.exp(-q1 * texp) - s2 * math.exp(-q2 * texp)
        return max(fwd, 0.0)
    d1, d2 = black_d1_d2(s1 * math.exp(-q1 * texp), s2 * math.exp(-q2 * texp), sig, texp)
    return s1 * math.exp(-q1 * texp) * norm_cdf(d1) - s2 * math.exp(-q2 * texp) * norm_cdf(d2)


def kirk_spread(
    f1: float,
    f2: float,
    strike: float,
    vol1: float,
    vol2: float,
    rho: float,
    texp: float,
    df: float = 1.0,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Kirk (1995) approximation for an option on ``F1 - F2`` vs ``K``."""
    f1 = require_positive("f1", f1)
    f2 = require_non_negative("f2", f2)
    strike = require_non_negative("strike", strike)
    texp = require_non_negative("texp", texp)
    if not -1.0 <= rho <= 1.0:
        raise InputError("rho must be in [-1, 1]")
    opt = OptionType(option_type)
    if texp == 0.0:
        spread = f1 - f2
        return df * (max(spread - strike, 0.0) if opt is OptionType.CALL else max(strike - spread, 0.0))
    f2k = f2 + strike
    if f2k <= 0.0:
        raise InputError("F2 + K must be positive for Kirk")
    var = vol1 * vol1 + (vol2 * f2 / f2k) ** 2 - 2.0 * rho * vol1 * vol2 * f2 / f2k
    vol = math.sqrt(max(var, 0.0))
    return black_price(f1, f2k, vol, texp, df, opt)
