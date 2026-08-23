"""Gatheral raw SVI and the g-function butterfly test.

    w(k) = a + b ( ρ (k-m) + sqrt((k-m)^2 + σ^2) )

``w`` is total implied variance σ²T. Calendar arbitrage is ``∂_T w >= 0``.
Butterfly arbitrage is ``g(k) >= 0`` (Gatheral–Jacquier).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from argentum.errors import InputError


@dataclass(frozen=True, slots=True)
class RawSVI:
    a: float
    b: float
    rho: float
    m: float
    sigma: float

    def __post_init__(self) -> None:
        if self.b < 0.0:
            raise InputError("SVI b must be >= 0")
        if not -1.0 <= self.rho <= 1.0:
            raise InputError("SVI rho must be in [-1, 1]")
        if self.sigma < 0.0:
            raise InputError("SVI sigma must be >= 0")
        if self.a + self.b * self.sigma * math.sqrt(1.0 - self.rho * self.rho) < -1e-12:
            raise InputError("SVI total variance would be negative at the trough")

    def total_variance(self, k: float) -> float:
        x = k - self.m
        return self.a + self.b * (self.rho * x + math.sqrt(x * x + self.sigma * self.sigma))

    def implied_vol(self, k: float, texp: float) -> float:
        if texp <= 0.0:
            return 0.0
        w = self.total_variance(k)
        if w < 0.0:
            raise InputError("negative SVI total variance")
        return math.sqrt(w / texp)

    def g(self, k: float) -> float:
        """Butterfly density factor. Need g(k) >= 0 for no butterfly arb."""
        x = k - self.m
        s = math.sqrt(x * x + self.sigma * self.sigma)
        w = self.a + self.b * (self.rho * x + s)
        if w <= 0.0:
            return -1.0
        dw = self.b * (self.rho + x / s)
        d2 = self.b * self.sigma * self.sigma / (s**3)
        return (1.0 - 0.5 * k * dw / w) ** 2 - 0.25 * (dw * dw) * (1.0 / w + 0.25) + 0.5 * d2

    def butterfly_ok(self, k_min: float = -3.0, k_max: float = 3.0, n: int = 81) -> bool:
        step = (k_max - k_min) / (n - 1)
        return all(self.g(k_min + i * step) >= -1e-10 for i in range(n))


def svi_from_atm(
    atm_vol: float,
    texp: float,
    *,
    b: float = 0.15,
    rho: float = -0.3,
    m: float = 0.0,
    sigma: float = 0.1,
) -> RawSVI:
    """Pick ``a`` so that w(0) matches ``atm_vol**2 * texp``."""
    w_atm = atm_vol * atm_vol * texp
    a = w_atm - b * (rho * (0.0 - m) + math.sqrt(m * m + sigma * sigma))
    return RawSVI(a=a, b=b, rho=rho, m=m, sigma=sigma)
