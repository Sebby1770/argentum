"""Characteristic-function pricing: one COS engine, six models.

Every model here is described by the characteristic function of the
martingale log-return ``X_T = ln(S_T / F_T)`` (so ``E[e^{X_T}] = 1``).
:func:`cos_price` prices European calls and puts on any of them with the
Fang–Oosterlee (2008) COS expansion, vectorised over strikes: the
characteristic function is evaluated once per expiry and reused for the
whole strike strip.

Models
------
- :class:`BlackScholesCF` — geometric Brownian motion (a sanity anchor).
- :class:`MertonJumpCF` — Merton (1976) log-normal jumps.
- :class:`VarianceGammaCF` — Madan, Carr & Chang (1998).
- :class:`NIGCF` — Barndorff-Nielsen (1997) normal inverse Gaussian.
- :class:`HestonCF` — Heston (1993), Albrecher "little trap" form.
- :class:`BatesCF` — Bates (1996): Heston plus Merton jumps.

The truncation range uses the first, second and fourth cumulants of the
log-return, obtained by finite differences of ``log φ`` near zero, which is
plenty for choosing ``[a, b]`` (prices themselves converge exponentially in
the number of terms for these smooth densities).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from argentum.errors import InputError
from argentum.types import OptionType, require_finite, require_non_negative, require_positive


class CharacteristicModel(Protocol):
    """A model given by ``φ(u, T) = E[exp(i u X_T)]`` of the martingale log-return."""

    @property
    def name(self) -> str: ...

    def cf(self, u: np.ndarray, texp: float) -> np.ndarray: ...


def _check_prob(name: str, value: float) -> float:
    value = require_finite(name, value)
    if not -1.0 <= value <= 1.0:
        raise InputError(f"{name} must be in [-1, 1]")
    return value


@dataclass(frozen=True, slots=True)
class BlackScholesCF:
    vol: float
    name: str = "black_scholes"

    def __post_init__(self) -> None:
        require_positive("vol", self.vol)

    def cf(self, u: np.ndarray, texp: float) -> np.ndarray:
        return np.exp(-0.5 * self.vol**2 * texp * (u * u + 1j * u))


@dataclass(frozen=True, slots=True)
class MertonJumpCF:
    """Diffusion ``vol`` plus Poisson(``lam``) jumps with ``ln J ~ N(mu_j, delta_j²)``."""

    vol: float
    lam: float
    mu_j: float
    delta_j: float
    name: str = "merton"

    def __post_init__(self) -> None:
        require_non_negative("vol", self.vol)
        require_non_negative("lam", self.lam)
        require_finite("mu_j", self.mu_j)
        require_non_negative("delta_j", self.delta_j)
        if self.vol == 0.0 and (self.lam == 0.0 or self.delta_j == 0.0):
            raise InputError("Merton model needs diffusion or jump-size variance")

    def _jump_exponent(self, u: np.ndarray) -> np.ndarray:
        jump = np.exp(1j * u * self.mu_j - 0.5 * self.delta_j**2 * u * u) - 1.0
        compensator = math.exp(self.mu_j + 0.5 * self.delta_j**2) - 1.0
        return self.lam * (jump - 1j * u * compensator)

    def cf(self, u: np.ndarray, texp: float) -> np.ndarray:
        diffusion = -0.5 * self.vol**2 * (u * u + 1j * u)
        return np.exp(texp * (diffusion + self._jump_exponent(u)))


@dataclass(frozen=True, slots=True)
class VarianceGammaCF:
    """VG with volatility ``sigma``, variance rate ``nu`` and drift ``theta``."""

    sigma: float
    nu: float
    theta: float
    name: str = "variance_gamma"

    def __post_init__(self) -> None:
        require_positive("sigma", self.sigma)
        require_positive("nu", self.nu)
        require_finite("theta", self.theta)
        if 1.0 - self.theta * self.nu - 0.5 * self.sigma**2 * self.nu <= 0.0:
            raise InputError("VG parameters give E[S_T] = infinity (need 1 - θν - σ²ν/2 > 0)")

    def cf(self, u: np.ndarray, texp: float) -> np.ndarray:
        s2, nu, th = self.sigma**2, self.nu, self.theta
        omega = math.log(1.0 - th * nu - 0.5 * s2 * nu) / nu
        base = 1.0 - 1j * th * nu * u + 0.5 * s2 * nu * u * u
        return np.exp(1j * u * omega * texp) * base ** (-texp / nu)


@dataclass(frozen=True, slots=True)
class NIGCF:
    """NIG with tail ``alpha``, skew ``beta`` (|β| < α, β+1 < α) and scale ``delta``."""

    alpha: float
    beta: float
    delta: float
    name: str = "nig"

    def __post_init__(self) -> None:
        require_positive("alpha", self.alpha)
        require_finite("beta", self.beta)
        require_positive("delta", self.delta)
        if not (abs(self.beta) < self.alpha and abs(self.beta + 1.0) < self.alpha):
            raise InputError("NIG needs |β| < α and |β + 1| < α for a finite forward")

    def cf(self, u: np.ndarray, texp: float) -> np.ndarray:
        a2 = self.alpha**2
        root = math.sqrt(a2 - self.beta**2)
        omega = self.delta * (math.sqrt(a2 - (self.beta + 1.0) ** 2) - root)
        expo = -self.delta * (np.sqrt(a2 - (self.beta + 1j * u) ** 2) - root)
        return np.exp(texp * (1j * u * omega + expo))


@dataclass(frozen=True, slots=True)
class HestonCF:
    kappa: float
    theta: float
    sigma: float
    rho: float
    v0: float
    name: str = "heston"

    def __post_init__(self) -> None:
        for field_name in ("kappa", "theta", "sigma", "v0"):
            require_positive(field_name, getattr(self, field_name))
        _check_prob("rho", self.rho)

    def cf(self, u: np.ndarray, texp: float) -> np.ndarray:
        k, th, s, r, v0 = self.kappa, self.theta, self.sigma, self.rho, self.v0
        iu = 1j * u
        beta = k - r * s * iu
        d = np.sqrt(beta * beta + s * s * (iu + u * u))
        g = (beta - d) / (beta + d)
        e = np.exp(-d * texp)
        c = (k * th / (s * s)) * ((beta - d) * texp - 2.0 * np.log((1.0 - g * e) / (1.0 - g)))
        dterm = ((beta - d) / (s * s)) * ((1.0 - e) / (1.0 - g * e))
        return np.exp(c + dterm * v0)


@dataclass(frozen=True, slots=True)
class BatesCF:
    """Heston stochastic variance with independent Merton jumps."""

    heston: HestonCF
    lam: float
    mu_j: float
    delta_j: float
    name: str = "bates"

    def __post_init__(self) -> None:
        require_non_negative("lam", self.lam)
        require_finite("mu_j", self.mu_j)
        require_non_negative("delta_j", self.delta_j)

    def cf(self, u: np.ndarray, texp: float) -> np.ndarray:
        jump = np.exp(1j * u * self.mu_j - 0.5 * self.delta_j**2 * u * u) - 1.0
        compensator = math.exp(self.mu_j + 0.5 * self.delta_j**2) - 1.0
        return self.heston.cf(u, texp) * np.exp(texp * self.lam * (jump - 1j * u * compensator))


def cumulants(model: CharacteristicModel, texp: float, h: float = 0.02) -> tuple[float, float, float]:
    """``(c1, c2, c4)`` of ``X_T`` from central differences of ``log φ`` at 0."""
    steps = np.array([-2.0, -1.0, 0.0, 1.0, 2.0]) * h
    phi = model.cf(steps.astype(np.complex128), texp)
    if not np.all(np.isfinite(phi)) or np.any(phi == 0.0):
        raise InputError(f"{model.name}: characteristic function is not finite near 0")
    f = np.log(phi)
    c1 = float(np.imag(f[3] - f[1]) / (2.0 * h))
    c2 = float(-np.real(f[3] - 2.0 * f[2] + f[1]) / (h * h))
    c4 = float(np.real(f[4] - 4.0 * f[3] + 6.0 * f[2] - 4.0 * f[1] + f[0]) / h**4)
    return c1, max(c2, 1e-14), max(c4, 0.0)


def cos_price(
    model: CharacteristicModel,
    spot: float,
    strike: Any,
    rate: float,
    div: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    *,
    n_terms: int = 512,
    width: float = 12.0,
) -> Any:
    """European price by the COS method. ``strike`` may be a scalar or an array.

    Puts are expanded directly (their payoff is bounded, so truncation error
    stays small) and calls follow from put–call parity.
    """
    spot = require_positive("spot", spot)
    rate = require_finite("rate", rate)
    div = require_finite("div", div)
    texp = require_non_negative("texp", texp)
    if n_terms < 16:
        raise InputError("n_terms must be at least 16")
    opt = OptionType(option_type)
    scalar = np.ndim(strike) == 0
    k = np.atleast_1d(np.asarray(strike, dtype=np.float64))
    if not np.all(np.isfinite(k)) or np.any(k <= 0.0):
        raise InputError("strike must be positive and finite")
    df = math.exp(-rate * texp)
    fwd = spot * math.exp((rate - div) * texp)
    if texp == 0.0:
        payoff = np.maximum(opt.omega * (spot - k), 0.0)
        return float(payoff[0]) if scalar else payoff

    c1, c2, c4 = cumulants(model, texp)
    half = width * math.sqrt(c2 + math.sqrt(c4))
    x = np.log(fwd / k)  # y = ln(S_T / K) = x + X_T
    a = x + c1 - half
    b = x + c1 + half
    # One interval for the whole strip keeps a single φ evaluation: take the union.
    lo, hi = float(np.min(a)), float(np.max(b))
    span = hi - lo
    j = np.arange(n_terms, dtype=np.float64)
    u = j * math.pi / span
    phi = model.cf(u.astype(np.complex128), texp)
    if not np.all(np.isfinite(phi)):
        raise InputError(f"{model.name}: characteristic function overflowed; reduce width or check parameters")

    # Put payoff K (1 - e^y)^+ on [lo, 0]: V_j = 2K/(b-a) (ψ_j(lo, 0) - χ_j(lo, 0)).
    top = min(0.0, hi)
    if top <= lo:
        v = np.zeros_like(u)  # every strike's put is out of the truncated range
    else:
        chi, psi = _chi_psi(j, lo, hi, lo, top)
        v = (2.0 / span) * (psi - chi)
        v[0] *= 0.5
    # Re[φ(u) e^{iu(x - lo)}] for every strike at once.
    phase = np.exp(1j * np.outer(x - lo, u))
    put = df * k * np.real(phase @ (phi * v))
    put = np.maximum(put, 0.0)
    value = put if opt is OptionType.PUT else put + df * (fwd - k)
    value = np.maximum(value, 0.0)
    return float(value[0]) if scalar else value


def _chi_psi(j: np.ndarray, a: float, b: float, c: float, d: float) -> tuple[np.ndarray, np.ndarray]:
    w = j * math.pi / (b - a)
    ed, ec = math.exp(d), math.exp(c)
    chi = (
        np.cos(w * (d - a)) * ed
        - np.cos(w * (c - a)) * ec
        + w * (np.sin(w * (d - a)) * ed - np.sin(w * (c - a)) * ec)
    ) / (1.0 + w * w)
    psi = np.empty_like(w)
    psi[0] = d - c
    psi[1:] = (np.sin(w[1:] * (d - a)) - np.sin(w[1:] * (c - a))) / w[1:]
    return chi, psi


def model_smile(
    model: CharacteristicModel,
    spot: float,
    strikes: Any,
    rate: float,
    div: float,
    texp: float,
    *,
    n_terms: int = 512,
) -> dict[str, np.ndarray]:
    """Model prices and the Black–Scholes implied vols they imply, per strike.

    Out-of-the-money options are inverted (puts below the forward, calls
    above), where the implied vol is best conditioned.
    """
    from argentum.models.vectorized import implied_vol_array

    k = np.asarray(strikes, dtype=np.float64)
    fwd = spot * math.exp((rate - div) * texp)
    calls = cos_price(model, spot, k, rate, div, texp, OptionType.CALL, n_terms=n_terms)
    puts = cos_price(model, spot, k, rate, div, texp, OptionType.PUT, n_terms=n_terms)
    otm_is_call = k >= fwd
    otm = np.where(otm_is_call, calls, puts)
    vols = implied_vol_array(
        otm, spot, k, rate, div, texp, np.where(otm_is_call, "call", "put"), errors="nan"
    )
    return {"strike": k, "call": np.asarray(calls), "put": np.asarray(puts), "implied_vol": vols}
