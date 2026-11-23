"""Heston (1993) stochastic volatility.

Pricing delegates to the shared COS engine in :mod:`argentum.models.charfn`,
whose characteristic function uses the "little Heston trap" (Albrecher et
al.) so the complex logarithm stays on the principal branch.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def heston_price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    texp: float,
    params: HestonParams,
    option_type: OptionType | str = OptionType.CALL,
    *,
    n_cos: int = 512,
    l_trunc: float = 12.0,
) -> float:
    """European Heston price via COS inversion (see :mod:`argentum.models.charfn`).

    With the defaults this reproduces Fang & Oosterlee's (2008) reference
    5.785155435 to nine digits; the 1.x engine (160 terms, cumulant-only
    range) was 4.5e-5 out on the same case.
    """
    from argentum.models.charfn import HestonCF, cos_price

    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    texp = require_non_negative("texp", texp)
    model = HestonCF(params.kappa, params.theta, params.sigma, params.rho, params.v0)
    return float(cos_price(model, spot, strike, rate, div, texp, option_type, n_terms=n_cos, width=l_trunc))
