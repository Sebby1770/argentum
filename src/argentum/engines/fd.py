"""One-factor Black–Scholes finite-difference engine (Crank–Nicolson).

Log-spot grid, Rannacher startup (two fully implicit half-steps) to damp
the discontinuity at the strike, Dirichlet boundaries.
"""

from __future__ import annotations

import math

import numpy as np

from argentum.math.linalg import thomas
from argentum.types import ExerciseStyle, OptionType, require_non_negative, require_positive


def fd_price(
    spot: float,
    strike: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    option_type: OptionType | str = OptionType.CALL,
    style: ExerciseStyle | str = ExerciseStyle.EUROPEAN,
    *,
    n_space: int = 200,
    n_time: int = 100,
    n_sigma: float = 4.0,
) -> float:
    spot = require_positive("spot", spot)
    strike = require_positive("strike", strike)
    vol = require_non_negative("vol", vol)
    texp = require_non_negative("texp", texp)
    opt = OptionType(option_type)
    style = ExerciseStyle(style)
    if texp == 0.0 or vol == 0.0:
        if opt is OptionType.CALL:
            return max(spot - strike, 0.0)
        return max(strike - spot, 0.0)

    x0 = math.log(spot)
    dx = (2.0 * n_sigma * vol * math.sqrt(texp)) / n_space
    x = x0 + dx * np.arange(-n_space // 2, n_space // 2 + 1, dtype=np.float64)
    s = np.exp(x)
    n = x.size
    dt = texp / n_time

    if opt is OptionType.CALL:
        v = np.maximum(s - strike, 0.0)
        lower = lambda t, smin: 0.0
    else:
        v = np.maximum(strike - s, 0.0)
        lower = lambda t, smin: strike * math.exp(-rate * t) - smin * math.exp(-div * t)

    mu = rate - div - 0.5 * vol * vol
    sig2 = vol * vol
    # CN coefficients on log-grid: v_t = -μ v_x - ½σ² v_xx + r v
    # implicit: (I + θ dt L) v^{n} = (I - (1-θ) dt L) v^{n+1}
    theta = 0.5

    def assemble(th: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # L v = -μ D1 - ½σ² D2 + r I   on interior
        sub = np.zeros(n)
        diag = np.zeros(n)
        sup = np.zeros(n)
        a_x = mu / (2.0 * dx)
        a_xx = 0.5 * sig2 / (dx * dx)
        for i in range(1, n - 1):
            # L V = -μ V_x - ½σ² V_xx + r V  (calendar-time generator)
            l_minus = a_x - a_xx
            l_zero = 2.0 * a_xx + rate
            l_plus = -a_x - a_xx
            sub[i] = th * dt * l_minus
            diag[i] = 1.0 + th * dt * l_zero
            sup[i] = th * dt * l_plus
        diag[0] = 1.0
        diag[-1] = 1.0
        return sub, diag, sup

    def rhs_from(v_now: np.ndarray, th_exp: float) -> np.ndarray:
        a_x = mu / (2.0 * dx)
        a_xx = 0.5 * sig2 / (dx * dx)
        rhs = np.zeros(n)
        for i in range(1, n - 1):
            l_minus = a_x - a_xx
            l_zero = 2.0 * a_xx + rate
            l_plus = -a_x - a_xx
            lv = l_minus * v_now[i - 1] + l_zero * v_now[i] + l_plus * v_now[i + 1]
            rhs[i] = v_now[i] - (1.0 - th_exp) * dt * lv
        return rhs

    t_remain = texp
    for step in range(n_time):
        th = 1.0 if step < 2 else theta  # Rannacher
        sub, diag, sup = assemble(th)
        rhs = rhs_from(v, th)
        t_remain -= dt
        tau = max(t_remain, 0.0)
        rhs[0] = max(lower(texp - tau, s[0]), 0.0) if opt is OptionType.PUT else 0.0
        if opt is OptionType.CALL:
            rhs[0] = 0.0
            rhs[-1] = max(s[-1] * math.exp(-div * tau) - strike * math.exp(-rate * tau), 0.0)
        else:
            rhs[0] = max(strike * math.exp(-rate * tau) - s[0] * math.exp(-div * tau), 0.0)
            rhs[-1] = 0.0
        v = thomas(sub, diag, sup, rhs)
        if style is ExerciseStyle.AMERICAN:
            if opt is OptionType.CALL:
                v = np.maximum(v, s - strike)
            else:
                v = np.maximum(v, strike - s)
    # interpolate at spot
    return float(np.interp(x0, x, v))
