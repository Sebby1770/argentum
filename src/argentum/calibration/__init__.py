"""Levenberg–Marquardt-style least squares for SABR / SVI / Heston."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from argentum.errors import ConvergenceError
from argentum.models.heston import HestonParams, heston_price
from argentum.models.sabr import sabr_implied_vol
from argentum.models.svi import RawSVI
from argentum.types import OptionType


def levenberg_marquardt(
    residual: Callable[[np.ndarray], np.ndarray],
    x0: np.ndarray,
    *,
    bounds: list[tuple[float, float]] | None = None,
    maxiter: int = 80,
    ftol: float = 1e-12,
    xtol: float = 1e-10,
    gtol: float = 1e-10,
    lambda0: float = 1e-3,
) -> np.ndarray:
    """Finite-difference LM. Raise rather than return an unconverged iterate."""
    if maxiter <= 0:
        raise ValueError("maxiter must be positive")
    x = np.array(x0, dtype=float)
    if x.ndim != 1 or x.size == 0 or not np.all(np.isfinite(x)):
        raise ValueError("x0 must be a non-empty finite vector")
    if bounds is not None and len(bounds) != x.size:
        raise ValueError("bounds must contain one (lo, hi) pair per parameter")
    lam = lambda0

    def evaluate(point: np.ndarray, iteration: int) -> np.ndarray:
        values = np.asarray(residual(point), dtype=float)
        if values.ndim != 1 or values.size == 0:
            raise ConvergenceError("residual must return a non-empty vector", iterations=iteration)
        if not np.all(np.isfinite(values)):
            raise ConvergenceError("residual returned NaN or infinity", iterations=iteration)
        return values

    r = evaluate(x, 0)
    cost = float(r @ r)
    if cost <= ftol:
        return x
    n = x.size
    for iteration in range(1, maxiter + 1):
        # Jacobian
        j = np.zeros((r.size, n))
        for i in range(n):
            h = 1e-6 * max(1.0, abs(x[i]))
            xp = x.copy()
            xp[i] += h
            if bounds is not None:
                xp[i] = min(max(xp[i], bounds[i][0]), bounds[i][1])
            rp = evaluate(xp, iteration)
            j[:, i] = (rp - r) / (xp[i] - x[i] if xp[i] != x[i] else h)
        a = j.T @ j
        g = j.T @ r
        if float(np.linalg.norm(g, ord=np.inf)) <= gtol:
            return x
        stepped = False
        previous_cost = cost
        accepted_delta = np.zeros_like(x)
        for _try in range(8):
            try:
                delta = np.linalg.solve(a + lam * np.eye(n), -g)
            except np.linalg.LinAlgError:
                lam = min(lam * 10.0, 1e12)
                continue
            x_new = x + delta
            if bounds is not None:
                for i, (lo, hi) in enumerate(bounds):
                    x_new[i] = min(max(x_new[i], lo), hi)
            r_new = evaluate(x_new, iteration)
            cost_new = float(r_new @ r_new)
            if cost_new < cost:
                x, r, cost = x_new, r_new, cost_new
                accepted_delta = delta
                lam = max(lam / 3.0, 1e-12)
                stepped = True
                break
            lam = min(lam * 3.0, 1e8)
        if not stepped:
            raise ConvergenceError(
                "Levenberg–Marquardt could not find a descent step",
                iterations=iteration,
                residual=cost**0.5,
            )
        if cost <= ftol:
            return x
        if float(np.linalg.norm(accepted_delta)) <= xtol * (xtol + float(np.linalg.norm(x))):
            return x
        if previous_cost - cost <= ftol * max(1.0, previous_cost):
            return x
    raise ConvergenceError(
        "Levenberg–Marquardt reached maxiter without convergence",
        iterations=maxiter,
        residual=cost**0.5,
    )


def calibrate_sabr(
    forwards_strikes_texp_vols: list[tuple[float, float, float, float]],
    *,
    beta: float = 0.5,
    x0: tuple[float, float, float] | None = None,
) -> tuple[float, float, float, float]:
    """Calibrate (alpha, rho, nu) with frozen β. Quotes are (F, K, T, black_vol)."""
    if x0 is None:
        atm = [v for f, k, t, v in forwards_strikes_texp_vols if abs(f - k) < 1e-8 * max(1.0, f)]
        alpha0 = (atm[0] * (forwards_strikes_texp_vols[0][0] ** (1.0 - beta))) if atm else 0.2
        x0 = (max(alpha0, 1e-4), -0.2, 0.5)

    def res(x: np.ndarray) -> np.ndarray:
        alpha, rho, nu = float(x[0]), float(x[1]), float(x[2])
        out = []
        for f, k, t, v in forwards_strikes_texp_vols:
            try:
                model = sabr_implied_vol(f, k, t, alpha, beta, rho, nu)
            except Exception:
                model = 1e3
            out.append(model - v)
        return np.array(out)

    sol = levenberg_marquardt(res, np.array(x0), bounds=[(1e-6, 5.0), (-0.999, 0.999), (1e-6, 10.0)])
    return float(sol[0]), beta, float(sol[1]), float(sol[2])


def calibrate_svi(
    k_w: list[tuple[float, float]],
    x0: tuple[float, float, float, float, float] | None = None,
) -> RawSVI:
    """Calibrate raw SVI to (log-moneyness k, total variance w) quotes."""
    if x0 is None:
        w0 = float(np.mean([w for _, w in k_w]))
        x0 = (max(w0 * 0.5, 1e-4), 0.2, -0.3, 0.0, 0.1)

    def res(x: np.ndarray) -> np.ndarray:
        a, b, rho, m, sig = (float(v) for v in x)
        try:
            svi = RawSVI(a, max(b, 0.0), min(max(rho, -0.999), 0.999), m, max(sig, 1e-6))
        except Exception:
            return np.ones(len(k_w)) * 1e2
        return np.array([svi.total_variance(k) - w for k, w in k_w])

    sol = levenberg_marquardt(
        res,
        np.array(x0),
        bounds=[(-2.0, 2.0), (0.0, 5.0), (-0.999, 0.999), (-2.0, 2.0), (1e-4, 5.0)],
    )
    return RawSVI(float(sol[0]), float(sol[1]), float(sol[2]), float(sol[3]), float(sol[4]))


def calibrate_heston(
    quotes: list[tuple[float, float, float, float, float, float]],
    x0: HestonParams | None = None,
) -> HestonParams:
    """Quotes are (spot, strike, rate, div, texp, price) European calls."""
    if x0 is None:
        x0 = HestonParams(kappa=1.5, theta=0.04, sigma=0.4, rho=-0.5, v0=0.04)

    def res(x: np.ndarray) -> np.ndarray:
        try:
            p = HestonParams(float(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]))
        except Exception:
            return np.ones(len(quotes))
        out = []
        for spot, k, r, q, t, px in quotes:
            try:
                model = heston_price(spot, k, r, q, t, p, OptionType.CALL)
            except Exception:
                model = 1e3
            out.append(model - px)
        return np.array(out)

    sol = levenberg_marquardt(
        res,
        np.array([x0.kappa, x0.theta, x0.sigma, x0.rho, x0.v0]),
        bounds=[(0.05, 10.0), (1e-4, 1.0), (0.05, 2.0), (-0.999, 0.999), (1e-4, 1.0)],
        maxiter=40,
    )
    return HestonParams(float(sol[0]), float(sol[1]), float(sol[2]), float(sol[3]), float(sol[4]))
