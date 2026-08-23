"""Reiner–Rubinstein (1991) barrier options under Black–Scholes.

Eight knock-out contracts (call/put × up/down × K ≷ H) plus knock-in via
in-out parity. Discrete monitoring uses the Broadie–Glasserman–Kou
continuity correction ``0.5826 σ √Δt``.
"""

from __future__ import annotations

import math

from argentum.errors import InputError
from argentum.math.special import norm_cdf
from argentum.models.black_scholes import price as vanilla_price
from argentum.types import OptionType, require_non_negative, require_positive


def _n(x: float) -> float:
    return norm_cdf(x)


def barrier_price(
    spot: float,
    strike: float,
    barrier: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    *,
    knock: str = "out",
    barrier_type: str = "down",
    rebate: float = 0.0,
    discrete_steps: int | None = None,
) -> float:
    """European barrier. ``knock`` is ``in`` or ``out``; ``barrier_type`` is ``up`` or ``down``."""
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    barrier = require_positive("barrier", barrier)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    rebate = require_non_negative("rebate", rebate)
    opt = OptionType(option_type)
    knock = knock.lower()
    barrier_type = barrier_type.lower()
    if knock not in {"in", "out"} or barrier_type not in {"up", "down"}:
        raise InputError("knock must be in/out and barrier_type up/down")

    if discrete_steps is not None and discrete_steps > 0 and texp > 0.0 and vol > 0.0:
        barrier = _continuity_correct(barrier, vol, texp, discrete_steps, barrier_type)

    if barrier_type == "down" and spot <= barrier:
        if knock == "out":
            return rebate * math.exp(-rate * texp)
        return vanilla_price(spot, strike, rate, div, vol, texp, opt)
    if barrier_type == "up" and spot >= barrier:
        if knock == "out":
            return rebate * math.exp(-rate * texp)
        return vanilla_price(spot, strike, rate, div, vol, texp, opt)

    if texp == 0.0 or vol == 0.0:
        van = vanilla_price(spot, strike, rate, div, vol, texp, opt)
        return van if knock == "in" else 0.0

    out = _knock_out(spot, strike, barrier, rate, div, vol, texp, opt, barrier_type, rebate)
    if knock == "out":
        return max(out, 0.0)
    van = vanilla_price(spot, strike, rate, div, vol, texp, opt)
    # Rebate is paid on knock for an out; an in with rebate-at-expiry-if-never-hit is not modelled.
    return max(van - out + rebate * 0.0, 0.0)


def _knock_out(
    s: float,
    k: float,
    h: float,
    r: float,
    q: float,
    sigma: float,
    t: float,
    opt: OptionType,
    barrier_type: str,
    rebate: float,
) -> float:
    """Haug (2007) table for continuously monitored knock-outs."""
    b = r - q
    sig_t = sigma * math.sqrt(t)
    mu = (b - 0.5 * sigma * sigma) / (sigma * sigma)
    lam = math.sqrt(mu * mu + 2.0 * r / (sigma * sigma))
    x1 = math.log(s / k) / sig_t + (1.0 + mu) * sig_t
    x2 = math.log(s / h) / sig_t + (1.0 + mu) * sig_t
    y1 = math.log(h * h / (s * k)) / sig_t + (1.0 + mu) * sig_t
    y2 = math.log(h / s) / sig_t + (1.0 + mu) * sig_t
    z = math.log(h / s) / sig_t + lam * sig_t
    eta = 1.0 if barrier_type == "down" else -1.0
    phi = 1.0 if opt is OptionType.CALL else -1.0
    hs = h / s
    df_r = math.exp(-r * t)
    df_b = math.exp((b - r) * t)

    def a(ph: float) -> float:
        return ph * s * df_b * _n(ph * x1) - ph * k * df_r * _n(ph * x1 - ph * sig_t)

    def b_term(ph: float) -> float:
        return ph * s * df_b * _n(ph * x2) - ph * k * df_r * _n(ph * x2 - ph * sig_t)

    def c(ph: float, et: float) -> float:
        return ph * s * df_b * hs ** (2.0 * (mu + 1.0)) * _n(et * y1) - ph * k * df_r * hs ** (2.0 * mu) * _n(
            et * y1 - et * sig_t
        )

    def d(ph: float, et: float) -> float:
        return ph * s * df_b * hs ** (2.0 * (mu + 1.0)) * _n(et * y2) - ph * k * df_r * hs ** (2.0 * mu) * _n(
            et * y2 - et * sig_t
        )

    def e(et: float) -> float:
        return rebate * df_r * (_n(et * x2 - et * mu * sig_t) - hs ** (2.0 * mu) * _n(et * y2 - et * mu * sig_t))

    def f(et: float) -> float:
        return rebate * (
            hs ** (mu + lam) * _n(et * z) + hs ** (mu - lam) * _n(et * z - 2.0 * et * lam * sig_t)
        )

    kh = k >= h
    if opt is OptionType.CALL and barrier_type == "down":
        core = (a(phi) - c(phi, eta)) if kh else (b_term(phi) - d(phi, eta))
        return core + f(eta) if rebate else core
    if opt is OptionType.CALL and barrier_type == "up":
        if kh:
            return f(eta) if rebate else 0.0
        core = a(phi) - b_term(phi) + c(phi, eta) - d(phi, eta)
        return core + f(eta) if rebate else core
    if opt is OptionType.PUT and barrier_type == "down":
        if not kh:
            return f(eta) if rebate else 0.0
        core = a(phi) - b_term(phi) + c(phi, eta) - d(phi, eta)
        return core + f(eta) if rebate else core
    # up-and-out put
    core = (b_term(phi) - d(phi, eta)) if kh else (a(phi) - c(phi, eta))
    return core + f(eta) if rebate else core


def _continuity_correct(barrier: float, vol: float, texp: float, steps: int, barrier_type: str) -> float:
    adj = 0.5826 * vol * math.sqrt(texp / steps)
    if barrier_type == "down":
        return barrier * math.exp(-adj)
    return barrier * math.exp(adj)
