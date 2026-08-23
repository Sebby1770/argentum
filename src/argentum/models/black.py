"""Black (1976) futures/forward options and Bachelier (normal) model."""

from __future__ import annotations

import math

from argentum.errors import InputError
from argentum.math.solvers import brent, newton
from argentum.math.special import black_d1_d2, norm_cdf, norm_pdf
from argentum.types import Greeks, OptionType, require_finite, require_non_negative, require_positive


def black_price(
    forward: float,
    strike: float,
    vol: float,
    texp: float,
    df: float = 1.0,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Black-76 price. ``vol`` is lognormal, ``df`` is the payment discount factor."""
    forward = require_positive("forward", forward)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    df = require_finite("df", df)
    opt = OptionType(option_type)
    if texp == 0.0 or vol == 0.0:
        intrinsic = max(forward - strike, 0.0) if opt is OptionType.CALL else max(strike - forward, 0.0)
        return df * intrinsic
    d1, d2 = black_d1_d2(forward, strike, vol, texp)
    if opt is OptionType.CALL:
        return df * (forward * norm_cdf(d1) - strike * norm_cdf(d2))
    return df * (strike * norm_cdf(-d2) - forward * norm_cdf(-d1))


def black_greeks(
    forward: float,
    strike: float,
    vol: float,
    texp: float,
    df: float = 1.0,
    option_type: OptionType | str = OptionType.CALL,
) -> Greeks:
    opt = OptionType(option_type)
    if texp == 0.0 or vol == 0.0:
        return Greeks()
    d1, d2 = black_d1_d2(forward, strike, vol, texp)
    sqrt_t = math.sqrt(texp)
    nd1 = norm_pdf(d1)
    omega = opt.omega
    delta = df * omega * norm_cdf(omega * d1)  # dPrice / dForward
    gamma = df * nd1 / (forward * vol * sqrt_t)
    vega = df * forward * nd1 * sqrt_t
    return Greeks(delta=delta, gamma=gamma, vega=vega)


def black_implied_vol(
    target: float,
    forward: float,
    strike: float,
    texp: float,
    df: float = 1.0,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    opt = OptionType(option_type)
    target = require_non_negative("price", target)
    undiscounted = target / df if df != 0.0 else target

    def obj(sig: float) -> float:
        return black_price(forward, strike, sig, texp, 1.0, opt) - undiscounted

    intrinsic = max(forward - strike, 0.0) if opt is OptionType.CALL else max(strike - forward, 0.0)
    if undiscounted < intrinsic - 1e-12:
        raise InputError("Black price below intrinsic")
    seed = min(max(math.sqrt(2.0 * math.pi / max(texp, 1e-18)) * max(undiscounted, 1e-16) / forward, 1e-6), 4.0)
    try:
        return newton(obj, seed, lower=1e-12, upper=10.0)
    except Exception:
        return brent(obj, 1e-8, 8.0)


def bachelier_price(
    forward: float,
    strike: float,
    vol_normal: float,
    texp: float,
    df: float = 1.0,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Normal (Bachelier) option. ``vol_normal`` is in the same units as the forward."""
    vol_normal = require_non_negative("vol_normal", vol_normal)
    texp = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    if texp == 0.0 or vol_normal == 0.0:
        intrinsic = max(forward - strike, 0.0) if opt is OptionType.CALL else max(strike - forward, 0.0)
        return df * intrinsic
    std = vol_normal * math.sqrt(texp)
    d = (forward - strike) / std
    omega = opt.omega
    # Call = (F-K) N(d) + σ√T n(d); put by omega
    value = omega * (forward - strike) * norm_cdf(omega * d) + std * norm_pdf(d)
    return df * value


def bachelier_implied_vol(
    target: float,
    forward: float,
    strike: float,
    texp: float,
    df: float = 1.0,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Closed-form ATM plus numerical OTM. Choi–Wu / Li–Lee style ATM seed."""
    opt = OptionType(option_type)
    undiscounted = target / df if df != 0.0 else target
    std_atm = math.sqrt(2.0 * math.pi) * max(undiscounted, 0.0)
    seed = std_atm / math.sqrt(max(texp, 1e-18))

    def obj(sig: float) -> float:
        return bachelier_price(forward, strike, sig, texp, 1.0, opt) - undiscounted

    try:
        return newton(obj, max(seed, 1e-8), lower=1e-12, upper=1e6)
    except Exception:
        return brent(obj, 1e-12, max(1e6, seed * 4))
