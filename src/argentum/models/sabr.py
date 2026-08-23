"""SABR implied volatility (Hagan et al. 2002) with the β=0 and ATM limits.

The lognormal expansion is the market standard for swaption/cap cubes.
``nu`` is the vol-of-vol, ``rho`` the correlation, ``alpha`` the sabr alpha
(ATM-ish), ``beta`` the CEV exponent in [0, 1].
"""

from __future__ import annotations

import math

from argentum.errors import InputError
from argentum.models.black import bachelier_price, black_price
from argentum.types import OptionType, require_non_negative, require_positive


def sabr_implied_vol(
    forward: float,
    strike: float,
    texp: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
    *,
    shift: float = 0.0,
) -> float:
    """Hagan 2002 lognormal SABR implied vol.

    A displacement ``shift`` implements shifted SABR on ``F+s``, ``K+s``.
    """
    if not 0.0 <= beta <= 1.0:
        raise InputError("SABR beta must be in [0, 1]")
    if not -1.0 <= rho <= 1.0:
        raise InputError("SABR rho must be in [-1, 1]")
    alpha = require_non_negative("alpha", alpha)
    nu = require_non_negative("nu", nu)
    texp = require_non_negative("texp", texp)
    f = forward + shift
    k = strike + shift
    if f <= 0.0 or k <= 0.0:
        raise InputError("SABR forward/strike + shift must be positive")
    if alpha == 0.0:
        return 0.0
    if abs(f - k) < 1e-14 * max(1.0, f):
        return _sabr_atm(f, texp, alpha, beta, rho, nu)
    z = (nu / alpha) * (f * k) ** ((1.0 - beta) / 2.0) * math.log(f / k)
    x = _x(z, rho)
    fk_pow = (f * k) ** ((1.0 - beta) / 2.0)
    log_fk = math.log(f / k)
    # leading term
    denom = fk_pow * (
        1.0
        + ((1.0 - beta) ** 2) / 24.0 * log_fk**2
        + ((1.0 - beta) ** 4) / 1920.0 * log_fk**4
    )
    zx = 1.0 if abs(z) < 1e-12 else z / (x if abs(x) > 1e-16 else 1.0)
    leading = alpha / denom * zx
    correction = (
        ((1.0 - beta) ** 2) / 24.0 * alpha * alpha / ((f * k) ** (1.0 - beta))
        + 0.25 * rho * beta * nu * alpha / fk_pow
        + (2.0 - 3.0 * rho * rho) / 24.0 * nu * nu
    )
    return leading * (1.0 + correction * texp)


def _x(z: float, rho: float) -> float:
    if abs(z) < 1e-12:
        return 1.0
    inner = math.sqrt(1.0 - 2.0 * rho * z + z * z) + z - rho
    if inner <= 0.0:
        inner = 1e-16
    return math.log(inner / (1.0 - rho))


def _sabr_atm(f: float, texp: float, alpha: float, beta: float, rho: float, nu: float) -> float:
    f_pow = f ** (1.0 - beta)
    leading = alpha / f_pow
    correction = (
        ((1.0 - beta) ** 2) / 24.0 * alpha * alpha / (f ** (2.0 - 2.0 * beta))
        + 0.25 * rho * beta * nu * alpha / f_pow
        + (2.0 - 3.0 * rho * rho) / 24.0 * nu * nu
    )
    return leading * (1.0 + correction * texp)


def sabr_normal_vol(
    forward: float,
    strike: float,
    texp: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
) -> float:
    """Hagan 2002 *normal* SABR expansion (β often 0)."""
    if not 0.0 <= beta <= 1.0:
        raise InputError("SABR beta must be in [0, 1]")
    if not -1.0 <= rho <= 1.0:
        raise InputError("SABR rho must be in [-1, 1]")
    f, k = forward, strike
    if abs(f - k) < 1e-14:
        one = alpha * (f**beta)
        corr = (
            -beta * (2.0 - beta) / 24.0 * alpha * alpha / (f ** (2.0 - 2.0 * beta))
            + 0.25 * rho * nu * alpha * beta / (f ** (1.0 - beta))
            + (2.0 - 3.0 * rho * rho) / 24.0 * nu * nu
        )
        return one * (1.0 + corr * texp)
    log_fk = math.log(f / k) if f > 0 and k > 0 else math.log(abs(f) + 1e-16) - math.log(abs(k) + 1e-16)
    z = (nu / alpha) * (f - k) / ((f * k) ** (beta / 2.0)) if beta != 0 else (nu / alpha) * (f - k)
    # A simpler equivalent used in rates: integrate CEV
    mid = 0.5 * (f + k)
    z = nu / alpha * (f - k) / (mid**beta)
    x = _x(z, rho)
    leading = alpha * (mid**beta) * (z / x if abs(x) > 1e-16 else 1.0)
    corr = (
        -beta * (2.0 - beta) / 24.0 * alpha * alpha / (mid ** (2.0 - 2.0 * beta))
        + 0.25 * rho * nu * alpha * beta / (mid ** (1.0 - beta))
        + (2.0 - 3.0 * rho * rho) / 24.0 * nu * nu
    )
    return leading * (1.0 + corr * texp)


def sabr_price(
    forward: float,
    strike: float,
    texp: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
    df: float = 1.0,
    option_type: OptionType | str = OptionType.CALL,
    *,
    shift: float = 0.0,
    normal: bool = False,
) -> float:
    if normal:
        vol = sabr_normal_vol(forward, strike, texp, alpha, beta, rho, nu)
        return bachelier_price(forward, strike, vol, texp, df, option_type)
    vol = sabr_implied_vol(forward, strike, texp, alpha, beta, rho, nu, shift=shift)
    return black_price(forward + shift, strike + shift, vol, texp, df, option_type)


def sabr_smile(
    forward: float,
    texp: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
    *,
    n: int = 21,
    lo: float | None = None,
    hi: float | None = None,
    shift: float = 0.0,
) -> list[dict[str, float]]:
    """Evenly spaced strike grid of Hagan SABR vols around the forward."""
    lo = forward * 0.5 if lo is None else lo
    hi = forward * 1.5 if hi is None else hi
    if n < 2:
        raise InputError("smile grid needs n >= 2")
    out: list[dict[str, float]] = []
    for i in range(n):
        k = lo + (hi - lo) * i / (n - 1)
        vol = sabr_implied_vol(forward, k, texp, alpha, beta, rho, nu, shift=shift)
        out.append({"strike": k, "vol": vol, "moneyness": k / forward if forward else 0.0})
    return out
