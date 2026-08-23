"""Escrowed-dividend Europeans: strip PV of known cash dividends off the spot."""

from __future__ import annotations

from collections.abc import Sequence

from argentum.models.black_scholes import greeks as bs_greeks
from argentum.models.black_scholes import price as bs_price
from argentum.types import Greeks, OptionType, require_non_negative, require_positive


def escrowed_spot(spot: float, rate: float, dividends: Sequence[tuple[float, float]]) -> float:
    """``dividends`` is a sequence of ``(time, cash_amount)`` with ``time`` in years."""
    spot = require_positive("spot", spot)
    pv = 0.0
    for t, cash in dividends:
        t = require_non_negative("dividend time", t)
        if t <= 0.0:
            continue
        pv += cash * __import__("math").exp(-rate * t)
    stripped = spot - pv
    if stripped <= 0.0:
        from argentum.errors import InputError

        raise InputError("PV of dividends exceeds spot")
    return stripped


def escrowed_price(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    texp: float,
    dividends: Sequence[tuple[float, float]],
    option_type: OptionType | str = OptionType.CALL,
) -> float:
    s = escrowed_spot(spot, rate, [(t, c) for t, c in dividends if t < texp])
    return bs_price(s, strike, rate, 0.0, vol, texp, option_type)


def escrowed_greeks(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    texp: float,
    dividends: Sequence[tuple[float, float]],
    option_type: OptionType | str = OptionType.CALL,
) -> Greeks:
    s = escrowed_spot(spot, rate, [(t, c) for t, c in dividends if t < texp])
    return bs_greeks(s, strike, rate, 0.0, vol, texp, option_type)
