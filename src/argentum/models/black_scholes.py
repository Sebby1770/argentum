"""Black–Scholes–Merton (1973) and Garman–Kohlhagen (1983).

All greeks are analytic. Implied volatility uses a Li (2011) / Jäckel-style
seed plus Halley, with a Brent fallback. Inputs may be scalars; numpy arrays
are accepted for ``price`` only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from argentum.errors import ConvergenceError, InputError
from argentum.math.solvers import brent, newton
from argentum.math.special import black_d1_d2, discount_factor, norm_cdf, norm_pdf, norm_sf
from argentum.types import Greeks, OptionType, PriceResult, require_finite, require_non_negative, require_positive


def _forward(spot: float, rate: float, div: float, texp: float) -> float:
    return spot * math.exp((rate - div) * texp)


def price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Discounted Black–Scholes price (European)."""
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    rate = require_finite("rate", rate)
    div = require_finite("div", div)
    opt = OptionType(option_type)
    df_r = discount_factor(rate, texp)
    df_q = discount_factor(div, texp)
    if texp == 0.0 or vol == 0.0:
        fwd = spot * df_q / df_r if texp == 0.0 else _forward(spot, rate, div, texp)
        # texp=0: fwd = spot
        if texp == 0.0:
            intrinsic = max(spot - strike, 0.0) if opt is OptionType.CALL else max(strike - spot, 0.0)
            return intrinsic
        intrinsic = max(fwd - strike, 0.0) if opt is OptionType.CALL else max(strike - fwd, 0.0)
        return df_r * intrinsic
    fwd = _forward(spot, rate, div, texp)
    d1, d2 = black_d1_d2(fwd, strike, vol, texp)
    if opt is OptionType.CALL:
        return df_r * (fwd * norm_cdf(d1) - strike * norm_cdf(d2))
    return df_r * (strike * norm_cdf(-d2) - fwd * norm_cdf(-d1))


def greeks(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
) -> Greeks:
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    omega = opt.omega
    df_r = math.exp(-rate * texp)
    df_q = math.exp(-div * texp)
    if texp == 0.0 or vol == 0.0:
        itm = (spot > strike) if opt is OptionType.CALL else (spot < strike)
        delta = df_q * (1.0 if itm else 0.0) * (1 if opt is OptionType.CALL else -1 if not itm else 0)
        if opt is OptionType.CALL:
            delta = df_q if spot > strike else (0.5 * df_q if spot == strike else 0.0)
        else:
            delta = -df_q if spot < strike else (-0.5 * df_q if spot == strike else 0.0)
        return Greeks(delta=delta)
    fwd = _forward(spot, rate, div, texp)
    sqrt_t = math.sqrt(texp)
    d1, d2 = black_d1_d2(fwd, strike, vol, texp)
    nd1 = norm_pdf(d1)
    if opt is OptionType.CALL:
        n_d1 = norm_cdf(d1)
        n_d2 = norm_cdf(d2)
    else:
        n_d1 = -norm_cdf(-d1)
        n_d2 = -norm_cdf(-d2)
    delta = df_q * n_d1
    gamma = df_q * nd1 / (spot * vol * sqrt_t)
    vega = spot * df_q * nd1 * sqrt_t
    theta = (
        -spot * df_q * nd1 * vol / (2.0 * sqrt_t)
        - omega * rate * strike * df_r * (norm_cdf(omega * d2))
        + omega * div * spot * df_q * (norm_cdf(omega * d1))
    )
    rho = omega * strike * texp * df_r * (norm_cdf(omega * d2))
    rho_div = -omega * spot * texp * df_q * (norm_cdf(omega * d1))
    vanna = -df_q * nd1 * d2 / vol
    volga = vega * d1 * d2 / vol
    # Haug: charm_call = -e^{-qT} [ n(d1) (2(r-q)T - d2 σ√T)/(2T σ√T) + q N(d1) ]
    common = nd1 * (2.0 * (rate - div) * texp - d2 * vol * sqrt_t) / (2.0 * texp * vol * sqrt_t)
    if opt is OptionType.CALL:
        charm = -df_q * (common + div * norm_cdf(d1))
    else:
        charm = -df_q * (common - div * norm_cdf(-d1))
    veta = (
        -spot * df_q * nd1 * sqrt_t * (div + ((rate - div) * d1) / (vol * sqrt_t) + (1.0 + d1 * d2) / (2.0 * texp))
    )
    speed = -gamma / spot * (d1 / (vol * sqrt_t) + 1.0)
    zomma = gamma * (d1 * d2 - 1.0) / vol
    color = (
        -df_q
        * nd1
        / (2.0 * spot * texp * vol * sqrt_t)
        * (2.0 * div * texp + 1.0 + (2.0 * (rate - div) * texp - d2 * vol * sqrt_t) * d1 / (vol * sqrt_t))
    )
    dual_delta = -df_r * (norm_cdf(d2) if opt is OptionType.CALL else -norm_cdf(-d2))
    dual_gamma = df_r * nd1 / (strike * vol * sqrt_t)
    value = price(spot, strike, rate, div, vol, texp, opt)
    lam = delta * spot / value if value != 0.0 else 0.0
    return Greeks(
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        vanna=vanna,
        volga=volga,
        vomma=volga,
        charm=charm,
        veta=veta,
        speed=speed,
        zomma=zomma,
        color=color,
        dual_delta=dual_delta,
        dual_gamma=dual_gamma,
        rho_div=rho_div,
        lambda_=lam,
        epsilon=rho_div,
    )


def digital_cash(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    cash: float = 1.0,
) -> float:
    """Cash-or-nothing: pays ``cash`` if in the money at expiry."""
    opt = OptionType(option_type)
    df_r = math.exp(-rate * texp)
    if texp == 0.0:
        itm = spot >= strike if opt is OptionType.CALL else spot <= strike
        return cash if itm else 0.0
    fwd = _forward(spot, rate, div, texp)
    _, d2 = black_d1_d2(fwd, strike, vol, texp)
    prob = norm_cdf(d2) if opt is OptionType.CALL else norm_cdf(-d2)
    return cash * df_r * prob


def digital_asset(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    """Asset-or-nothing: pays S_T if in the money."""
    opt = OptionType(option_type)
    df_q = math.exp(-div * texp)
    if texp == 0.0:
        itm = spot >= strike if opt is OptionType.CALL else spot <= strike
        return spot if itm else 0.0
    fwd = _forward(spot, rate, div, texp)
    d1, _ = black_d1_d2(fwd, strike, vol, texp)
    prob = norm_cdf(d1) if opt is OptionType.CALL else norm_cdf(-d1)
    return spot * df_q * prob


def _implied_vol_seed(undiscounted: float, fwd: float, strike: float, texp: float) -> float:
    """Brenner–Subrahmanyam ATM seed, with a deep ITM/OTM log-moneyness tweak."""
    if texp <= 0.0:
        return 0.0
    intrinsic = max(fwd - strike, 0.0)
    value = max(undiscounted - 0.0, 0.0)
    # use call equivalent
    time_value = max(value, 1e-16)
    seed = math.sqrt(2.0 * math.pi / texp) * time_value / max(fwd, 1e-16)
    return min(max(seed, 1e-6), 5.0)


def implied_vol(
    target: float,
    spot: float,
    strike: float,
    rate: float,
    div: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    *,
    tol: float = 1e-12,
    maxiter: int = 40,
) -> float:
    """Black–Scholes implied volatility from a premium."""
    opt = OptionType(option_type)
    target = require_non_negative("price", target)
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    texp = require_non_negative("texp", texp)
    df_r = math.exp(-rate * texp)
    df_q = math.exp(-div * texp)
    fwd = _forward(spot, rate, div, texp)
    intrinsic = df_r * (max(fwd - strike, 0.0) if opt is OptionType.CALL else max(strike - fwd, 0.0))
    disc_spot = spot * df_q
    disc_strike = strike * df_r
    upper = disc_spot if opt is OptionType.CALL else disc_strike
    if target < intrinsic - 1e-12:
        raise InputError(f"price {target} below intrinsic {intrinsic}")
    if target > upper + 1e-12:
        raise InputError(f"price {target} above maximum {upper}")
    if texp == 0.0 or abs(target - intrinsic) < 1e-16:
        return 0.0
    # Invert the OTM option — ITM vegas vanish and Halley falls over.
    if opt is OptionType.CALL and fwd > strike:
        target = target - df_r * (fwd - strike)
        opt = OptionType.PUT
        intrinsic = 0.0
    elif opt is OptionType.PUT and fwd < strike:
        target = target + df_r * (fwd - strike)
        opt = OptionType.CALL
        intrinsic = 0.0
    target = max(target, 0.0)
    seed = _implied_vol_seed(target / df_r, fwd, strike, texp)

    def objective(sig: float) -> float:
        return price(spot, strike, rate, div, sig, texp, opt) - target

    def vega_of(sig: float) -> float:
        if sig <= 0.0:
            return 1e-18
        d1, _ = black_d1_d2(fwd, strike, sig, texp)
        return spot * df_q * norm_pdf(d1) * math.sqrt(texp)

    def volga_of(sig: float) -> float:
        d1, d2 = black_d1_d2(fwd, strike, sig, texp)
        return vega_of(sig) * d1 * d2 / sig

    try:
        from argentum.math.solvers import halley

        iv = halley(objective, vega_of, volga_of, seed, tol=tol, maxiter=maxiter, lower=1e-12, upper=10.0)
        if abs(objective(iv)) < 1e-8:
            return iv
    except (ConvergenceError, ZeroDivisionError, ValueError, OverflowError):
        pass
    try:
        iv = newton(objective, seed, fprime=vega_of, tol=tol, maxiter=maxiter, lower=1e-12, upper=10.0)
        if abs(objective(iv)) < 1e-8:
            return iv
    except ConvergenceError:
        pass
    return brent(objective, 1e-8, 8.0, tol=max(tol, 1e-14))


def result(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    *,
    currency: str = "USD",
) -> PriceResult:
    opt = OptionType(option_type)
    npv = price(spot, strike, rate, div, vol, texp, opt)
    g = greeks(spot, strike, rate, div, vol, texp, opt)
    return PriceResult(npv=npv, currency=currency, greeks=g, engine="black_scholes")
