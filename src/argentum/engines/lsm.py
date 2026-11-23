"""Longstaff–Schwartz (2001) least-squares Monte Carlo for early exercise.

The continuation value at each exercise date is a regression of the
realised, discounted future cash flow on a polynomial basis in moneyness,
fitted on in-the-money paths only (the paper's key refinement).

Two estimates are reported, because the textbook one is biased:

- ``in_sample`` — the exercise rule is fitted and applied on the same paths.
  The rule peeks at the future it is scored on, so it is biased *high*.
- ``npv`` — the rule is fitted on one path set and applied to an
  independent one. Any fixed rule is admissible, so this is a *lower bound*
  on the true American value (up to Monte Carlo noise), with an honest
  standard error.

:func:`lsm_price` works on any simulated paths (GBM, Heston QE, your own);
:func:`lsm_american` is the GBM convenience wrapper.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from argentum.errors import InputError
from argentum.types import OptionType, require_finite, require_non_negative, require_positive


@dataclass(frozen=True, slots=True)
class LSMResult:
    npv: float
    std_error: float
    in_sample: float
    european: float
    n_paths: int
    n_steps: int
    engine: str = "lsm"

    @property
    def early_exercise_premium(self) -> float:
        return self.npv - self.european


def _basis(x: np.ndarray, degree: int) -> np.ndarray:
    """Weighted Laguerre polynomials in moneyness, as in the original paper."""
    w = np.exp(-0.5 * x)
    cols = [np.ones_like(x)]
    lag = [np.ones_like(x), 1.0 - x]
    for n in range(1, degree):
        lag.append(((2 * n + 1 - x) * lag[n] - n * lag[n - 1]) / (n + 1))
    cols.extend(w * lag[i] for i in range(degree))
    return np.column_stack(cols)


def _fit_policy(
    paths: np.ndarray, exercise: Callable[[np.ndarray], np.ndarray], df_step: float, degree: int, scale: float
) -> list[np.ndarray | None]:
    n_steps = paths.shape[1] - 1
    cash = exercise(paths[:, -1])
    coefs: list[np.ndarray | None] = [None] * (n_steps + 1)
    for t in range(n_steps - 1, 0, -1):
        cash = cash * df_step
        intrinsic = exercise(paths[:, t])
        itm = intrinsic > 0.0
        if np.count_nonzero(itm) <= degree + 1:
            continue
        a = _basis(paths[itm, t] / scale, degree)
        beta, *_ = np.linalg.lstsq(a, cash[itm], rcond=None)
        coefs[t] = beta
        cont = a @ beta
        ex = intrinsic[itm] > cont
        idx = np.flatnonzero(itm)[ex]
        cash[idx] = intrinsic[idx]
    return coefs


def _apply_policy(
    paths: np.ndarray,
    exercise: Callable[[np.ndarray], np.ndarray],
    df_step: float,
    degree: int,
    scale: float,
    coefs: list[np.ndarray | None],
) -> np.ndarray:
    """Discounted cash flow per path under a fixed exercise rule (forward in time)."""
    n_paths, n_cols = paths.shape
    n_steps = n_cols - 1
    value = np.zeros(n_paths)
    alive = np.ones(n_paths, dtype=bool)
    for t in range(1, n_steps):
        beta = coefs[t]
        if beta is None:
            continue
        intrinsic = exercise(paths[:, t])
        cand = alive & (intrinsic > 0.0)
        if not np.any(cand):
            continue
        cont = _basis(paths[cand, t] / scale, degree) @ beta
        stop = np.flatnonzero(cand)[intrinsic[cand] > cont]
        value[stop] = intrinsic[stop] * df_step**t
        alive[stop] = False
    final = exercise(paths[:, -1])
    value[alive] = final[alive] * df_step**n_steps
    return value


def lsm_price(
    fit_paths: np.ndarray,
    price_paths: np.ndarray,
    exercise: Callable[[np.ndarray], np.ndarray],
    df_step: float,
    *,
    degree: int = 3,
    scale: float = 1.0,
) -> tuple[float, float, float]:
    """``(lower_bound, std_error, in_sample)`` from two independent path sets.

    ``paths[:, 0]`` is today; columns are equally spaced exercise dates;
    ``exercise(s)`` returns the payoff of exercising at state ``s``;
    ``df_step`` is the one-period discount factor; ``scale`` normalises the
    regression state (use the strike).
    """
    if fit_paths.ndim != 2 or price_paths.ndim != 2 or fit_paths.shape[1] != price_paths.shape[1]:
        raise InputError("path sets must be 2-D with the same number of dates")
    if fit_paths.shape[1] < 2:
        raise InputError("need at least one step")
    if not 1 <= degree <= 6:
        raise InputError("degree must be between 1 and 6")
    coefs = _fit_policy(fit_paths, exercise, df_step, degree, scale)
    in_sample_cash = _apply_policy(fit_paths, exercise, df_step, degree, scale, coefs)
    cash = _apply_policy(price_paths, exercise, df_step, degree, scale, coefs)
    # Exercising today is always available.
    now = float(exercise(price_paths[:1, 0])[0])
    lower = max(float(cash.mean()), now)
    in_sample = max(float(in_sample_cash.mean()), now)
    se = float(cash.std(ddof=1) / math.sqrt(cash.size))
    return lower, se, in_sample


def gbm_paths(
    spot: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    n_paths: int,
    n_steps: int,
    rng: np.random.Generator,
    *,
    antithetic: bool = True,
) -> np.ndarray:
    """Exact log-Euler GBM paths, shape ``(n_paths, n_steps + 1)``."""
    half = n_paths // 2 if antithetic else n_paths
    z = rng.standard_normal((half, n_steps))
    if antithetic:
        z = np.vstack([z, -z])
    dt = texp / n_steps
    incr = (rate - div - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z
    logs = np.cumsum(incr, axis=1)
    return spot * np.exp(np.hstack([np.zeros((z.shape[0], 1)), logs]))


def lsm_american(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.PUT,
    *,
    n_paths: int = 100_000,
    n_steps: int = 50,
    degree: int = 3,
    seed: int = 7,
) -> LSMResult:
    """American (Bermudan with ``n_steps`` dates) vanilla under GBM by LSM."""
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    rate = require_finite("rate", rate)
    div = require_finite("div", div)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    if n_paths < 1000 or n_steps < 1:
        raise InputError("need n_paths >= 1000 and n_steps >= 1")
    opt = OptionType(option_type)
    omega = opt.omega

    def exercise(s: np.ndarray) -> np.ndarray:
        return np.maximum(omega * (s - strike), 0.0)

    intrinsic_now = max(omega * (spot - strike), 0.0)
    if texp == 0.0 or vol == 0.0:
        from argentum.models.black_scholes import price as bs_price

        euro = bs_price(spot, strike, rate, div, vol, texp, opt)
        return LSMResult(max(euro, intrinsic_now), 0.0, max(euro, intrinsic_now), euro, 0, n_steps)

    rng = np.random.default_rng(seed)
    fit = gbm_paths(spot, rate, div, vol, texp, n_paths, n_steps, rng)
    test = gbm_paths(spot, rate, div, vol, texp, n_paths, n_steps, rng)
    df_step = math.exp(-rate * texp / n_steps)
    lower, se, in_sample = lsm_price(fit, test, exercise, df_step, degree=degree, scale=strike)
    european = float((exercise(test[:, -1]) * math.exp(-rate * texp)).mean())
    return LSMResult(lower, se, in_sample, european, int(test.shape[0]), n_steps)
