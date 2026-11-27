"""Calibrate characteristic-function models to an option chain.

Each family is a parameter vector with bounds and a builder for its
:mod:`argentum.models.charfn` model. The objective is the vega-weighted
price error of the out-of-the-money quotes — a first-order implied-vol
error that needs no root-finding per iteration — and the reported fit
quality is the exact implied-vol RMSE of the calibrated prices.

One characteristic-function evaluation per expiry prices every strike of
that expiry (COS is vectorised over strikes), so a five-parameter Heston
fit to a 75-quote chain takes well under a second.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from argentum.chain import OptionChain
from argentum.errors import InputError
from argentum.models.charfn import (
    BatesCF,
    BlackScholesCF,
    CharacteristicModel,
    HestonCF,
    MertonJumpCF,
    NIGCF,
    VarianceGammaCF,
    cos_price,
)
from argentum.models.vectorized import implied_vol_array


PRICE_FLOOR = 1e-9  # premiums below this fraction of spot are numerically zero under COS


@dataclass(frozen=True)
class Family:
    names: tuple[str, ...]
    x0: tuple[float, ...]
    bounds: tuple[tuple[float, float], ...]
    build: Callable[[Any], CharacteristicModel]  # takes a parameter vector


FAMILIES: dict[str, Family] = {
    "black_scholes": Family(("vol",), (0.2,), ((0.01, 3.0),), lambda x: BlackScholesCF(x[0])),
    "merton": Family(
        ("vol", "lam", "mu_j", "delta_j"),
        (0.15, 0.3, -0.1, 0.1),
        ((0.01, 2.0), (0.0, 5.0), (-1.0, 1.0), (0.01, 1.0)),
        lambda x: MertonJumpCF(x[0], x[1], x[2], x[3]),
    ),
    "variance_gamma": Family(
        ("sigma", "nu", "theta"),
        (0.2, 0.2, -0.1),
        ((0.01, 2.0), (0.01, 2.0), (-1.0, 1.0)),
        lambda x: VarianceGammaCF(x[0], x[1], x[2]),
    ),
    "nig": Family(
        ("alpha", "beta", "delta"),
        (10.0, -3.0, 0.2),
        ((0.5, 100.0), (-50.0, 50.0), (0.01, 5.0)),
        lambda x: NIGCF(x[0], x[1], x[2]),
    ),
    "heston": Family(
        ("kappa", "theta", "sigma", "rho", "v0"),
        (1.5, 0.04, 0.5, -0.6, 0.04),
        ((0.05, 15.0), (1e-3, 1.0), (0.05, 3.0), (-0.99, 0.99), (1e-3, 1.0)),
        lambda x: HestonCF(x[0], x[1], x[2], x[3], x[4]),
    ),
    "bates": Family(
        ("kappa", "theta", "sigma", "rho", "v0", "lam", "mu_j", "delta_j"),
        (1.5, 0.04, 0.5, -0.6, 0.04, 0.2, -0.1, 0.1),
        (
            (0.05, 15.0),
            (1e-3, 1.0),
            (0.05, 3.0),
            (-0.99, 0.99),
            (1e-3, 1.0),
            (0.0, 3.0),
            (-0.6, 0.3),
            (0.01, 0.6),
        ),
        lambda x: BatesCF(HestonCF(x[0], x[1], x[2], x[3], x[4]), x[5], x[6], x[7]),
    ),
}


@dataclass(frozen=True)
class CalibrationResult:
    family: str
    params: dict[str, float]
    model: CharacteristicModel
    rmse_vol: float
    max_abs_vol_error: float
    model_iv: np.ndarray = field(repr=False)
    n_quotes: int = 0
    n_below_precision: int = 0  # quotes whose model premium is too small to invert

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "params": self.params,
            "rmse_vol": self.rmse_vol,
            "max_abs_vol_error": self.max_abs_vol_error,
            "n_quotes": self.n_quotes,
            "n_below_precision": self.n_below_precision,
        }


def model_prices(model: CharacteristicModel, chain: OptionChain, *, n_terms: int = 256) -> np.ndarray:
    """Model premiums for every quote of the chain (its own call/put type)."""
    out = np.empty(chain.size)
    for te in chain.expiries:
        sel = np.flatnonzero(chain.texp == te)
        calls = np.asarray(cos_price(model, chain.spot, chain.strike[sel], chain.rate, chain.div, float(te), "call", n_terms=n_terms))
        df = np.exp(-chain.rate * te)
        puts = calls - df * (chain.forward(te) - chain.strike[sel])
        out[sel] = np.where(chain.omega[sel] > 0, calls, np.maximum(puts, 0.0))
    return out


def calibrate_model(
    chain: OptionChain,
    family: str,
    *,
    x0: Sequence[float] | None = None,
    n_terms: int = 256,
    maxiter: int = 80,
    otm_only: bool = True,
) -> CalibrationResult:
    """Fit ``family`` (one of :data:`FAMILIES`) to ``chain``; report exact IV errors."""
    from argentum.calibration import levenberg_marquardt

    if family not in FAMILIES:
        raise InputError(f"unknown model family {family!r}; choose from {sorted(FAMILIES)}")
    fam = FAMILIES[family]
    start = np.array(fam.x0 if x0 is None else x0, dtype=float)
    if start.size != len(fam.names):
        raise InputError(f"{family} needs {len(fam.names)} starting values")
    mask = chain.otm() if otm_only else np.ones(chain.size, dtype=bool)
    if np.count_nonzero(mask) < len(fam.names):
        raise InputError("not enough quotes to calibrate this model")
    sub = _subset(chain, mask)
    # Vega floor keeps deep-OTM wings from dominating through tiny vegas.
    vega = np.maximum(sub.vega, 1e-3 * sub.spot * np.sqrt(sub.texp))

    def residual(x: np.ndarray) -> np.ndarray:
        try:
            model = fam.build(x)
            prices = model_prices(model, sub, n_terms=n_terms)
        except InputError:
            return np.full(sub.size, 10.0)
        err = (prices - sub.price) / vega
        return np.where(np.isfinite(err), err, 10.0)

    x = levenberg_marquardt(residual, start, bounds=list(fam.bounds), maxiter=maxiter, strict=False)
    model = fam.build(x)
    prices = model_prices(model, sub, n_terms=n_terms)
    ivs = implied_vol_array(np.maximum(prices, 0.0), sub.spot, sub.strike, sub.rate, sub.div, sub.texp, sub.omega, errors="nan")
    # A model premium below double-precision resolution (COS returns ~0) has no
    # recoverable implied vol: inverting it would report a fictitious 0 vol.
    unresolved = prices <= PRICE_FLOOR * sub.spot
    ivs = np.where(unresolved, np.nan, ivs)
    err = ivs - sub.iv
    finite = np.isfinite(err)
    rmse = float(np.sqrt(np.mean(err[finite] ** 2))) if np.any(finite) else float("inf")
    worst = float(np.max(np.abs(err[finite]))) if np.any(finite) else float("inf")
    return CalibrationResult(
        family,
        {name: float(v) for name, v in zip(fam.names, x)},
        model,
        rmse,
        worst,
        ivs,
        int(sub.size),
        int(np.count_nonzero(unresolved)),
    )


def _subset(chain: OptionChain, mask: np.ndarray) -> OptionChain:
    return OptionChain(
        chain.spot,
        chain.rate,
        chain.div,
        chain.texp[mask],
        chain.strike[mask],
        chain.omega[mask],
        chain.price[mask],
        chain.iv[mask],
        chain.dropped,
    )
