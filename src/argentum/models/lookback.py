"""Continuous lookback options (Goldman–Sosin–Gatto 1979, Conze–Viswanathan 1991)."""

from __future__ import annotations

import math

from argentum.math.special import black_d1_d2, norm_cdf
from argentum.types import OptionType, require_non_negative, require_positive


def _n(x: float) -> float:
    return norm_cdf(x)


def floating_lookback(
    spot: float,
    extremum: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Floating-strike lookback. Call pays ``S_T - m``, put pays ``M - S_T``.

    ``extremum`` is the running min (call) or max (put) observed so far.
    At inception pass ``extremum=spot``.
    """
    s = require_positive("spot", spot)
    ext = require_positive("extremum", extremum)
    vol = require_non_negative("vol", vol)
    t = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    if t == 0.0:
        return max(s - ext, 0.0) if opt is OptionType.CALL else max(ext - s, 0.0)
    b = rate - div
    if abs(b) < 1e-12:
        b = 1e-12
    sig_t = vol * math.sqrt(t)
    df_r = math.exp(-rate * t)
    df_b = math.exp((b - rate) * t)
    if opt is OptionType.CALL:
        m = min(ext, s)
        a1 = (math.log(s / m) + (b + 0.5 * vol * vol) * t) / sig_t
        a2 = a1 - sig_t
        term = (vol * vol) / (2.0 * b)
        return (
            s * df_b * _n(a1)
            - m * df_r * _n(a2)
            + s * df_r * term * ((s / m) ** (-2.0 * b / (vol * vol)) * _n(-a1 + 2.0 * b * math.sqrt(t) / vol) - math.exp(b * t) * _n(-a1))
        )
    m = max(ext, s)
    a1 = (math.log(m / s) + (-b + 0.5 * vol * vol) * t) / sig_t
    a2 = a1 - sig_t
    term = (vol * vol) / (2.0 * b)
    return (
        m * df_r * _n(a1)
        - s * df_b * _n(a2)
        - s * df_r * term * ((m / s) ** (2.0 * b / (vol * vol)) * _n(-a1 - 2.0 * b * math.sqrt(t) / vol) - math.exp(b * t) * _n(-a2))
    )


def fixed_lookback(
    spot: float,
    strike: float,
    extremum: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Fixed-strike lookback. Call on the running max, put on the running min."""
    s = require_positive("spot", spot)
    k = require_positive("strike", strike)
    ext = require_positive("extremum", extremum)
    vol = require_non_negative("vol", vol)
    t = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    if t == 0.0:
        if opt is OptionType.CALL:
            return max(max(ext, s) - k, 0.0)
        return max(k - min(ext, s), 0.0)
    # Conze–Viswanathan: if the extremum is already past the strike, add the
    # intrinsic on the observed extremum plus a floating remainder.
    if opt is OptionType.CALL:
        m = max(ext, s)
        if m <= k:
            return _fixed_call_no_hit(s, k, rate, div, vol, t)
        return math.exp(-rate * t) * (m - k) + floating_lookback(s, m, rate, div, vol, t, OptionType.CALL)
    m = min(ext, s)
    if m >= k:
        return _fixed_put_no_hit(s, k, rate, div, vol, t)
    return math.exp(-rate * t) * (k - m) + floating_lookback(s, m, rate, div, vol, t, OptionType.PUT)


def _fixed_call_no_hit(s: float, k: float, r: float, q: float, vol: float, t: float) -> float:
    b = r - q
    d1, d2 = black_d1_d2(s * math.exp(b * t), k, vol, t)
    df_r = math.exp(-r * t)
    df_q = math.exp(-q * t)
    e = (s / k) ** (-2.0 * b / (vol * vol)) if vol > 0 else 0.0
    y = (math.log(k / s) + (b + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    return (
        s * df_q * _n(d1)
        - k * df_r * _n(d2)
        - s * df_q * (vol * vol) / (2.0 * b) * (_n(-d1) - e * _n(-y))
    )


def _fixed_put_no_hit(s: float, k: float, r: float, q: float, vol: float, t: float) -> float:
    # put-call symmetry on the lookback
    return _fixed_call_no_hit(k, s, q, r, vol, t)
