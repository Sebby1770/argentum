"""Bjerksund–Stensland American approximations (1993 flat boundary, 2002 two-step).

Both price the American call as the value of exercising at a fixed (1993)
or piecewise-flat (2002) trigger, so they are *lower bounds* on the true
American price; the 2002 version is the tighter one and the default.
American puts use the GBM put–call transformation
``P(S, K, r, b) = C(K, S, r - b, -b)``.

Notation follows Haug, *The Complete Guide to Option Pricing Formulas*
(2nd ed., §3.1): ``b = r - q`` is the cost of carry.
"""

from __future__ import annotations

import math

from argentum.math.special import bivariate_cdf, norm_cdf
from argentum.models.black_scholes import price as european_price
from argentum.types import OptionType, require_finite, require_non_negative, require_positive


def _phi(s: float, t: float, gamma: float, h: float, i: float, r: float, b: float, vol: float) -> float:
    lam = (-r + gamma * b + 0.5 * gamma * (gamma - 1.0) * vol * vol) * t
    sig_t = vol * math.sqrt(t)
    d = -(math.log(s / h) + (b + (gamma - 0.5) * vol * vol) * t) / sig_t
    kappa = 2.0 * b / (vol * vol) + (2.0 * gamma - 1.0)
    return math.exp(lam) * s**gamma * (norm_cdf(d) - (i / s) ** kappa * norm_cdf(d - 2.0 * math.log(i / s) / sig_t))


def _psi(
    s: float, t: float, gamma: float, h: float, i2: float, i1: float, t1: float, r: float, b: float, vol: float
) -> float:
    carry = b + (gamma - 0.5) * vol * vol
    st1, st = vol * math.sqrt(t1), vol * math.sqrt(t)
    e1 = (math.log(s / i1) + carry * t1) / st1
    e2 = (math.log(i2 * i2 / (s * i1)) + carry * t1) / st1
    e3 = (math.log(s / i1) - carry * t1) / st1
    e4 = (math.log(i2 * i2 / (s * i1)) - carry * t1) / st1
    f1 = (math.log(s / h) + carry * t) / st
    f2 = (math.log(i2 * i2 / (s * h)) + carry * t) / st
    f3 = (math.log(i1 * i1 / (s * h)) + carry * t) / st
    f4 = (math.log(s * i1 * i1 / (h * i2 * i2)) + carry * t) / st
    rho = math.sqrt(t1 / t)
    lam = -r + gamma * b + 0.5 * gamma * (gamma - 1.0) * vol * vol
    kappa = 2.0 * b / (vol * vol) + (2.0 * gamma - 1.0)
    return math.exp(lam * t) * s**gamma * (
        bivariate_cdf(-e1, -f1, rho)
        - (i2 / s) ** kappa * bivariate_cdf(-e2, -f2, rho)
        - (i1 / s) ** kappa * bivariate_cdf(-e3, -f3, -rho)
        + (i1 / i2) ** kappa * bivariate_cdf(-e4, -f4, -rho)
    )


def _boundary_inputs(strike: float, r: float, b: float, vol: float) -> tuple[float, float, float]:
    v2 = vol * vol
    beta = (0.5 - b / v2) + math.sqrt((b / v2 - 0.5) ** 2 + 2.0 * r / v2)
    b_inf = beta / (beta - 1.0) * strike
    b0 = max(strike, r / (r - b) * strike)
    return beta, b_inf, b0


def _call_1993(s: float, k: float, t: float, r: float, b: float, vol: float) -> float:
    beta, b_inf, b0 = _boundary_inputs(k, r, b, vol)
    h = -(b * t + 2.0 * vol * math.sqrt(t)) * b0 / (b_inf - b0)
    i = b0 + (b_inf - b0) * (1.0 - math.exp(h))
    if s >= i:
        return s - k
    alpha = (i - k) * i ** (-beta)
    return (
        alpha * s**beta
        - alpha * _phi(s, t, beta, i, i, r, b, vol)
        + _phi(s, t, 1.0, i, i, r, b, vol)
        - _phi(s, t, 1.0, k, i, r, b, vol)
        - k * _phi(s, t, 0.0, i, i, r, b, vol)
        + k * _phi(s, t, 0.0, k, i, r, b, vol)
    )


def _call_2002(s: float, k: float, t: float, r: float, b: float, vol: float) -> float:
    beta, b_inf, b0 = _boundary_inputs(k, r, b, vol)
    t1 = 0.5 * (math.sqrt(5.0) - 1.0) * t
    scale = k * k / ((b_inf - b0) * b0)
    h1 = -(b * t1 + 2.0 * vol * math.sqrt(t1)) * scale
    h2 = -(b * t + 2.0 * vol * math.sqrt(t)) * scale
    i1 = b0 + (b_inf - b0) * (1.0 - math.exp(h1))
    i2 = b0 + (b_inf - b0) * (1.0 - math.exp(h2))
    if s >= i2:
        return s - k
    a1 = (i1 - k) * i1 ** (-beta)
    a2 = (i2 - k) * i2 ** (-beta)
    return (
        a2 * s**beta
        - a2 * _phi(s, t1, beta, i2, i2, r, b, vol)
        + _phi(s, t1, 1.0, i2, i2, r, b, vol)
        - _phi(s, t1, 1.0, i1, i2, r, b, vol)
        - k * _phi(s, t1, 0.0, i2, i2, r, b, vol)
        + k * _phi(s, t1, 0.0, i1, i2, r, b, vol)
        + a1 * _phi(s, t1, beta, i1, i2, r, b, vol)
        - a1 * _psi(s, t, beta, i1, i2, i1, t1, r, b, vol)
        + _psi(s, t, 1.0, i1, i2, i1, t1, r, b, vol)
        - _psi(s, t, 1.0, k, i2, i1, t1, r, b, vol)
        - k * _psi(s, t, 0.0, i1, i2, i1, t1, r, b, vol)
        + k * _psi(s, t, 0.0, k, i2, i1, t1, r, b, vol)
    )


def bjerksund_stensland_call(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    *,
    version: int = 2002,
) -> float:
    """American call with continuous dividend yield ``div``."""
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    rate = require_finite("rate", rate)
    div = require_finite("div", div)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    if version not in (1993, 2002):
        raise ValueError("version must be 1993 or 2002")
    euro = european_price(spot, strike, rate, div, vol, texp, OptionType.CALL)
    if texp == 0.0:
        return max(spot - strike, 0.0)
    if vol == 0.0:
        return max(spot - strike, euro)
    b = rate - div
    if b >= rate:
        # q <= 0: early exercise of a call is never optimal.
        return euro
    approx = (_call_2002 if version == 2002 else _call_1993)(spot, strike, texp, rate, b, vol)
    return max(approx, euro, spot - strike)


def bjerksund_stensland(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.PUT,
    *,
    version: int = 2002,
) -> float:
    """American call or put (Bjerksund–Stensland 2002 by default; ``version=1993`` too)."""
    opt = OptionType(option_type)
    if opt is OptionType.CALL:
        return bjerksund_stensland_call(spot, strike, rate, div, vol, texp, version=version)
    # Put–call transformation: P(S, K, r, q) = C(K, S, q, r) — swap rate and yield.
    put = bjerksund_stensland_call(strike, spot, div, rate, vol, texp, version=version)
    euro = european_price(spot, strike, rate, div, vol, texp, OptionType.PUT)
    return max(put, euro, strike - spot)
