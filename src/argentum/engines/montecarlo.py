"""Monte Carlo engines: GBM, Heston QE (Andersen), with Sobol and antithetic."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from argentum.math.random import SobolEngine
from argentum.math.special import norm_inv
from argentum.models.heston import HestonParams
from argentum.types import OptionType, require_non_negative, require_positive


@dataclass(frozen=True, slots=True)
class MCResult:
    npv: float
    std_error: float
    n_paths: int
    engine: str = "mc_gbm"


def gbm_european(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    *,
    n_paths: int = 50_000,
    antithetic: bool = True,
    sobol: bool = True,
    seed: int = 7,
) -> MCResult:
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    if texp == 0.0:
        val = max(spot - strike, 0.0) if opt is OptionType.CALL else max(strike - spot, 0.0)
        return MCResult(val, 0.0, 0)
    drift = (rate - div - 0.5 * vol * vol) * texp
    vol_t = vol * math.sqrt(texp)
    n = n_paths
    if sobol:
        engine = SobolEngine(1, scramble=True, seed=seed)
        u = engine.random(n).reshape(-1)
        z = np.array([norm_inv(float(ui)) for ui in u])
    else:
        rng = np.random.default_rng(seed)
        z = rng.standard_normal(n)
    if antithetic:
        z = np.concatenate([z, -z])
    st = spot * np.exp(drift + vol_t * z)
    if opt is OptionType.CALL:
        payoff = np.maximum(st - strike, 0.0)
    else:
        payoff = np.maximum(strike - st, 0.0)
    disc = math.exp(-rate * texp) * payoff
    mean = float(disc.mean())
    se = float(disc.std(ddof=1) / math.sqrt(disc.size))
    return MCResult(mean, se, int(disc.size), "mc_gbm")


def heston_qe(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    texp: float,
    params: HestonParams,
    option_type: OptionType | str = OptionType.CALL,
    *,
    n_paths: int = 20_000,
    n_steps: int = 64,
    seed: int = 7,
) -> MCResult:
    """Andersen QE discretisation of Heston."""
    opt = OptionType(option_type)
    dt = texp / n_steps
    kappa, theta, sigma, rho, v0 = params.kappa, params.theta, params.sigma, params.rho, params.v0
    rng = np.random.default_rng(seed)
    x: np.ndarray = np.full(n_paths, math.log(spot))
    v: np.ndarray = np.full(n_paths, v0)
    psi_c = 1.5
    for _ in range(n_steps):
        z1 = rng.standard_normal(n_paths)
        z2 = rng.standard_normal(n_paths)
        z_s = rho * z1 + math.sqrt(max(1.0 - rho * rho, 0.0)) * z2
        m = theta + (v - theta) * math.exp(-kappa * dt)
        s2 = (
            v * sigma * sigma * math.exp(-kappa * dt) / kappa * (1.0 - math.exp(-kappa * dt))
            + theta * sigma * sigma / (2.0 * kappa) * (1.0 - math.exp(-kappa * dt)) ** 2
        )
        psi = np.divide(s2, m * m, out=np.ones_like(m), where=m > 1e-16)
        v_next = np.empty_like(v)
        mask = psi <= psi_c
        # quadratic
        inv = 1.0 / psi[mask]
        b2 = 2.0 * inv - 1.0 + np.sqrt(2.0 * inv) * np.sqrt(2.0 * inv - 1.0)
        a = m[mask] / (1.0 + b2)
        v_next[mask] = a * (np.sqrt(b2) + z1[mask]) ** 2
        # exponential
        other = ~mask
        p = (psi[other] - 1.0) / (psi[other] + 1.0)
        beta = (1.0 - p) / m[other]
        u = rng.random(np.count_nonzero(other))
        v_next[other] = np.where(u <= p, 0.0, np.log((1.0 - p) / np.maximum(1.0 - u, 1e-16)) / beta)
        v_next = np.maximum(v_next, 0.0)
        x = x + (rate - div - 0.5 * v) * dt + np.sqrt(np.maximum(v, 0.0) * dt) * z_s
        v = v_next
    st = np.exp(x)
    payoff = np.maximum(st - strike, 0.0) if opt is OptionType.CALL else np.maximum(strike - st, 0.0)
    disc = math.exp(-rate * texp) * payoff
    return MCResult(float(disc.mean()), float(disc.std(ddof=1) / math.sqrt(n_paths)), n_paths, "mc_heston_qe")
