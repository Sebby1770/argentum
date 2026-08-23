"""Quanto vanillas: foreign asset, domestic cash settlement.

The quanto adjustment replaces the dividend yield with
``q + ρ σ_asset σ_fx`` so a domestic Black–Scholes engine applies.
"""

from __future__ import annotations

from argentum.models.black_scholes import greeks as bs_greeks
from argentum.models.black_scholes import price as bs_price
from argentum.types import Greeks, OptionType, PriceResult, require_finite


def quanto_div(div: float, rho: float, vol_asset: float, vol_fx: float) -> float:
    require_finite("rho", rho)
    if not -1.0 <= rho <= 1.0:
        from argentum.errors import InputError

        raise InputError("quanto rho must be in [-1, 1]")
    return div + rho * vol_asset * vol_fx


def quanto_price(
    spot: float,
    strike: float,
    rate_dom: float,
    div: float,
    vol_asset: float,
    texp: float,
    rho: float,
    vol_fx: float,
    option_type: OptionType | str = OptionType.CALL,
    multiplier: float = 1.0,
) -> float:
    """Domestic-currency price of a quanto vanilla (spot already in foreign units)."""
    q = quanto_div(div, rho, vol_asset, vol_fx)
    return multiplier * bs_price(spot, strike, rate_dom, q, vol_asset, texp, option_type)


def quanto_greeks(
    spot: float,
    strike: float,
    rate_dom: float,
    div: float,
    vol_asset: float,
    texp: float,
    rho: float,
    vol_fx: float,
    option_type: OptionType | str = OptionType.CALL,
    multiplier: float = 1.0,
) -> Greeks:
    q = quanto_div(div, rho, vol_asset, vol_fx)
    return bs_greeks(spot, strike, rate_dom, q, vol_asset, texp, option_type).scale(multiplier)


def quanto_result(**kwargs) -> PriceResult:
    g = quanto_greeks(**{k: v for k, v in kwargs.items() if k != "multiplier"}, multiplier=kwargs.get("multiplier", 1.0))
    npv = quanto_price(**kwargs)
    return PriceResult(npv=npv, greeks=g, engine="quanto_bs")
