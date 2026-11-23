"""CRR and Leisen–Reimer binomial trees (European and American)."""

from __future__ import annotations

import math

import numpy as np

from argentum.errors import InputError
from argentum.types import ExerciseStyle, OptionType, require_non_negative, require_positive


def _leisen_preizer_pp(z: float, n: int) -> float:
    """Peizer–Pratt inversion used by Leisen–Reimer."""
    if n % 2 == 0:
        n = n + 1
    # n is odd
    term = (z / (n + 1.0 / 3.0 + 0.1 / (n + 1))) ** 2 * (n + 1.0 / 6.0)
    return 0.5 + math.copysign(0.5, z) * math.sqrt(1.0 - math.exp(-term))


def crr_price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    steps: int = 401,
    option_type: OptionType | str = OptionType.CALL,
    style: ExerciseStyle | str = ExerciseStyle.EUROPEAN,
) -> float:
    """Cox–Ross–Rubinstein tree."""
    return _tree(
        spot, strike, rate, div, vol, texp, steps, OptionType(option_type), ExerciseStyle(style), method="crr"
    )


def leisen_reimer_price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    steps: int = 401,
    option_type: OptionType | str = OptionType.CALL,
    style: ExerciseStyle | str = ExerciseStyle.EUROPEAN,
) -> float:
    """Leisen–Reimer tree (odd steps; even is bumped). Second-order ATM convergence."""
    if steps % 2 == 0:
        steps += 1
    return _tree(
        spot, strike, rate, div, vol, texp, steps, OptionType(option_type), ExerciseStyle(style), method="lr"
    )


def _tree(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    steps: int,
    opt: OptionType,
    style: ExerciseStyle,
    method: str,
) -> float:
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    if steps < 1:
        raise InputError("steps must be >= 1")
    if texp == 0.0:
        return max(spot - strike, 0.0) if opt is OptionType.CALL else max(strike - spot, 0.0)
    dt = texp / steps
    df = math.exp(-rate * dt)
    drift = math.exp((rate - div) * dt)
    if method == "crr":
        u = math.exp(vol * math.sqrt(dt))
        d = 1.0 / u
        p = (drift - d) / (u - d)
    else:
        d1 = (math.log(spot / strike) + (rate - div + 0.5 * vol * vol) * texp) / (vol * math.sqrt(texp))
        d2 = d1 - vol * math.sqrt(texp)
        p = _leisen_preizer_pp(d2, steps)
        p_star = _leisen_preizer_pp(d1, steps)
        u = drift * p_star / p
        d = (drift - p * u) / (1.0 - p)
    p = min(max(p, 0.0), 1.0)
    # terminal spots: j up moves, steps-j down
    j = np.arange(steps + 1, dtype=np.float64)
    spots = spot * (u**j) * (d ** (steps - j))
    if opt is OptionType.CALL:
        values = np.maximum(spots - strike, 0.0)
    else:
        values = np.maximum(strike - spots, 0.0)
    pu, pd = df * p, df * (1.0 - p)
    for step in range(steps - 1, -1, -1):
        values = pu * values[1 : step + 2] + pd * values[0 : step + 1]
        if style is ExerciseStyle.AMERICAN:
            spots = spot * (u ** np.arange(step + 1)) * (d ** (step - np.arange(step + 1)))
            if opt is OptionType.CALL:
                exercise = np.maximum(spots - strike, 0.0)
            else:
                exercise = np.maximum(strike - spots, 0.0)
            values = np.maximum(values, exercise)
    return float(values[0])
