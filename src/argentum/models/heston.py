"""Heston (1993) via the Fang–Oosterlee COS method.

The characteristic function uses the "little Heston trap" (Albrecher et al.)
so the complex logarithm stays on the principal branch.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

import numpy as np

from argentum.errors import InputError
from argentum.types import OptionType, require_non_negative, require_positive


@dataclass(frozen=True, slots=True)
class HestonParams:
    kappa: float
    theta: float
    sigma: float
    rho: float
    v0: float

    def __post_init__(self) -> None:
        if self.kappa <= 0.0 or self.theta <= 0.0 or self.sigma <= 0.0 or self.v0 <= 0.0:
            raise InputError("Heston kappa, theta, sigma, v0 must be positive")
        if not -1.0 <= self.rho <= 1.0:
            raise InputError("Heston rho must be in [-1, 1]")

    @property
    def feller(self) -> float:
        return 2.0 * self.kappa * self.theta - self.sigma * self.sigma

    @property
    def feller_ok(self) -> bool:
        return self.feller >= 0.0


def _cf_log_s(u: complex, t: float, params: HestonParams, r: float, q: float, s0: float) -> complex:
    kappa, theta, sigma, rho, v0 = params.kappa, params.theta, params.sigma, params.rho, params.v0
    i = 1j
    iu = i * u
    d = cmath.sqrt((rho * sigma * iu - kappa) ** 2 + (sigma**2) * (iu + u * u))
    g = (kappa - rho * sigma * iu - d) / (kappa - rho * sigma * iu + d)
    exp_dt = cmath.exp(-d * t)
    g_exp = (1.0 - g * exp_dt) / (1.0 - g)
    c = (r - q) * iu * t + (kappa * theta / (sigma**2)) * ((kappa - rho * sigma * iu - d) * t - 2.0 * cmath.log(g_exp))
    dterm = ((kappa - rho * sigma * iu - d) / (sigma**2)) * ((1.0 - exp_dt) / (1.0 - g * exp_dt))
    return cmath.exp(c + dterm * v0 + iu * math.log(s0))


def _cumulants(t: float, params: HestonParams, r: float, q: float, s0: float) -> tuple[float, float]:
    kappa, theta, sigma, rho, v0 = params.kappa, params.theta, params.sigma, params.rho, params.v0
    c1 = math.log(s0) + (r - q) * t + (1.0 - math.exp(-kappa * t)) * (theta - v0) / (2.0 * kappa) - 0.5 * theta * t
    c2 = (
        (sigma * t * kappa * math.exp(-kappa * t) * (v0 - theta) * (8.0 * kappa * rho - 4.0 * sigma)
         + kappa * rho * sigma * (1.0 - math.exp(-kappa * t)) * (16.0 * theta - 8.0 * v0)
         + 2.0 * theta * kappa * t * (-4.0 * kappa * rho * sigma + sigma**2 + 4.0 * kappa**2)
         + sigma**2 * ((theta - 2.0 * v0) * math.exp(-2.0 * kappa * t) + theta * (6.0 * math.exp(-kappa * t) - 7.0) + 2.0 * v0)
         + 8.0 * kappa**2 * (v0 - theta) * (1.0 - math.exp(-kappa * t)))
        / (8.0 * kappa**3)
    )
    return c1, max(abs(c2), 1e-10)


def heston_price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    texp: float,
    params: HestonParams,
    option_type: OptionType | str = OptionType.CALL,
    *,
    n_cos: int = 160,
    l_trunc: float = 12.0,
) -> float:
    """European Heston price via COS inversion on x = log S."""
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    texp = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    if texp == 0.0:
        return max(spot - strike, 0.0) if opt is OptionType.CALL else max(strike - spot, 0.0)

    c1, c2 = _cumulants(texp, params, rate, div, spot)
    a = c1 - l_trunc * math.sqrt(c2)
    b = c1 + l_trunc * math.sqrt(c2)
    log_k = math.log(strike)

    k = np.arange(n_cos, dtype=np.float64)
    u = k * math.pi / (b - a)
    phi = np.array([_cf_log_s(complex(uk), texp, params, rate, div, spot) for uk in u], dtype=np.complex128)

    # Put coefficients for G(x)=(K - e^x)+ on [a, min(log K, b)]
    c_put, d_put = a, min(log_k, b)
    chi = _chi(k, a, b, c_put, d_put)
    psi = _psi(k, a, b, c_put, d_put)
    uk = (2.0 / (b - a)) * (strike * psi - chi)
    uk[0] *= 0.5

    total = np.real(np.sum(phi * np.exp(-1j * u * a) * uk))
    put = math.exp(-rate * texp) * float(total)
    fwd = spot * math.exp((rate - div) * texp)
    call = put + math.exp(-rate * texp) * (fwd - strike)
    value = call if opt is OptionType.CALL else put
    return max(value, 0.0)


def _chi(k: np.ndarray, a: float, b: float, c: float, d: float) -> np.ndarray:
    if d <= c:
        return np.zeros_like(k)
    rng = b - a
    chi = k * math.pi / rng
    exp_d, exp_c = math.exp(d), math.exp(c)
    num = (
        np.cos(chi * (d - a)) * exp_d
        - np.cos(chi * (c - a)) * exp_c
        + chi * (np.sin(chi * (d - a)) * exp_d - np.sin(chi * (c - a)) * exp_c)
    )
    den = 1.0 + chi * chi
    den = np.where(den == 0.0, 1.0, den)
    return num / den


def _psi(k: np.ndarray, a: float, b: float, c: float, d: float) -> np.ndarray:
    if d <= c:
        return np.zeros_like(k)
    rng = b - a
    chi = k * math.pi / rng
    out = np.empty_like(k, dtype=np.float64)
    out[0] = d - c
    mask = k != 0
    out[mask] = (np.sin(chi[mask] * (d - a)) - np.sin(chi[mask] * (c - a))) / chi[mask]
    return out
