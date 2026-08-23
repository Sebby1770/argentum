"""Geske (1979) compound options and Rubinstein simple choosers."""

from __future__ import annotations

import math

from argentum.math.solvers import newton
from argentum.math.special import bivariate_cdf, black_d1_d2, norm_cdf
from argentum.models.black_scholes import price as vanilla
from argentum.types import OptionType, require_non_negative, require_positive


def _critical_spot(k1: float, k2: float, rate: float, div: float, vol: float, tau: float, on_call: bool) -> float:
    """Spot at the compound expiry that makes the underlying option worth ``k1``."""
    opt = OptionType.CALL if on_call else OptionType.PUT

    def obj(s: float) -> float:
        return vanilla(max(s, 1e-8), k2, rate, div, vol, tau, opt) - k1

    seed = k2 * math.exp(-(rate - div) * tau)
    return newton(obj, max(seed, k1), lower=1e-6, upper=max(k2, k1) * 20.0, tol=1e-10)


def geske_compound(
    spot: float,
    k1: float,
    k2: float,
    rate: float,
    div: float,
    vol: float,
    t1: float,
    t2: float,
    *,
    on_call: bool = True,
    compound_call: bool = True,
) -> float:
    """European compound: option (expiry ``t1``, strike ``k1``) on a vanilla (expiry ``t2``, strike ``k2``)."""
    spot = require_positive("spot", spot)
    k1 = require_positive("k1", k1)
    k2 = require_positive("k2", k2)
    vol = require_non_negative("vol", vol)
    t1 = require_non_negative("t1", t1)
    t2 = require_non_negative("t2", t2)
    if t2 < t1:
        raise ValueError("underlying expiry t2 must be >= compound expiry t1")
    if t1 == 0.0:
        inner = vanilla(spot, k2, rate, div, vol, t2, OptionType.CALL if on_call else OptionType.PUT)
        return max(inner - k1, 0.0) if compound_call else max(k1 - inner, 0.0)
    tau = t2 - t1
    s_star = _critical_spot(k1, k2, rate, div, vol, tau, on_call)
    rho = math.sqrt(t1 / t2) if t2 > 0 else 1.0
    a1, a2 = black_d1_d2(spot * math.exp((rate - div) * t1), s_star, vol, t1)
    b1, b2 = black_d1_d2(spot * math.exp((rate - div) * t2), k2, vol, t2)
    df_r1 = math.exp(-rate * t1)
    df_r2 = math.exp(-rate * t2)
    df_q2 = math.exp(-div * t2)
    sign_u = 1.0 if on_call else -1.0
    sign_c = 1.0 if compound_call else -1.0
    # Call-on-call (Geske): S e^{-qT2} M(a1,b1;ρ) - K2 e^{-rT2} M(a2,b2;ρ) - K1 e^{-rT1} N(a2)
    m_a = bivariate_cdf(sign_c * a1, sign_u * b1, sign_c * sign_u * rho)
    m_b = bivariate_cdf(sign_c * a2, sign_u * b2, sign_c * sign_u * rho)
    return sign_c * (
        sign_u * spot * df_q2 * m_a
        - sign_u * k2 * df_r2 * m_b
        - k1 * df_r1 * norm_cdf(sign_c * a2)
    )


def simple_chooser(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    choose_at: float,
    expiry: float,
) -> float:
    """Rubinstein simple chooser: at ``choose_at`` pick a call or put with strike ``K`` and expiry ``expiry``."""
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    t = require_non_negative("choose_at", choose_at)
    t2 = require_non_negative("expiry", expiry)
    if t2 < t:
        raise ValueError("chooser expiry must be >= choose date")
    call = vanilla(spot, strike, rate, div, vol, t2, OptionType.CALL)
    if t == 0.0:
        put = vanilla(spot, strike, rate, div, vol, t2, OptionType.PUT)
        return max(call, put)
    d, _ = black_d1_d2(spot * math.exp((rate - div) * t), strike * math.exp(-(rate - div) * (t2 - t)), vol, t)
    y = (math.log(spot / strike) + (rate - div) * t2 + 0.5 * vol * vol * t) / (vol * math.sqrt(t)) if vol * t > 0 else 0.0
    return (
        call
        - spot * math.exp(-div * t2) * norm_cdf(-y)
        + strike * math.exp(-rate * t2) * norm_cdf(-y + vol * math.sqrt(t))
    )


def forward_start(
    spot: float,
    rate: float,
    div: float,
    vol: float,
    start: float,
    tenor: float,
    option_type: OptionType | str = OptionType.CALL,
    moneyness: float = 1.0,
) -> float:
    """Forward-starting vanilla: strike is set to ``moneyness * S_start`` at ``start``."""
    spot = require_positive("spot", spot)
    start = require_non_negative("start", start)
    tenor = require_non_negative("tenor", tenor)
    k = require_positive("moneyness", moneyness) * spot
    # The e^{-q start} factor is the probability-weighted spot at start under the stock measure.
    inner = vanilla(spot, k, rate, div, vol, tenor, option_type)
    return math.exp(-div * start) * inner
