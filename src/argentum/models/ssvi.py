"""SSVI: an arbitrage-free implied-volatility surface (Gatheral & Jacquier 2014).

Total implied variance at log-moneyness ``k = ln(K/F_T)`` and expiry ``t``::

    w(k, t) = θ_t / 2 · (1 + ρ φ k + sqrt((φ k + ρ)² + 1 − ρ²)),   φ = φ(θ_t)

with the power-law curvature ``φ(θ) = η / (θ^γ (1 + θ)^(1−γ))``.

``θ_t`` is the at-the-money total variance, stored at the fitted expiries and
interpolated linearly in ``t`` (``θ_0 = 0``). The surface is free of static
arbitrage when:

- calendar: ``θ_t`` is non-decreasing (guaranteed by construction here) and
  ``θ φ(θ)`` is non-decreasing in θ (true for ``0 ≤ γ ≤ 1``);
- butterfly: ``η (1 + |ρ|) ≤ 2`` with ``0 < γ ≤ ½`` (their Remark 4.4).

:meth:`SSVISurface.no_arbitrage` checks those conditions and also scans the
density factor ``g(k)`` numerically. Local volatility follows in closed form
from Gatheral's Dupire formula in total variance (:meth:`local_vol`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from argentum.errors import InputError


@dataclass(frozen=True)
class SSVISurface:
    rho: float
    eta: float
    gamma: float
    expiries: tuple[float, ...]
    thetas: tuple[float, ...]
    meta: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not -1.0 < self.rho < 1.0:
            raise InputError("SSVI rho must be in (-1, 1)")
        if not self.eta > 0.0:
            raise InputError("SSVI eta must be positive")
        if not 0.0 <= self.gamma <= 1.0:
            raise InputError("SSVI gamma must be in [0, 1]")
        t = np.asarray(self.expiries, dtype=float)
        th = np.asarray(self.thetas, dtype=float)
        if t.size == 0 or t.size != th.size:
            raise InputError("SSVI needs one ATM total variance per expiry")
        if not (np.all(np.isfinite(t)) and np.all(np.isfinite(th))):
            raise InputError("SSVI expiries and thetas must be finite")
        if np.any(t <= 0.0) or np.any(np.diff(t) <= 0.0):
            raise InputError("SSVI expiries must be positive and strictly increasing")
        if np.any(th <= 0.0) or np.any(np.diff(th) < -1e-14):
            raise InputError("SSVI ATM total variance must be positive and non-decreasing")

    # -- the ATM term structure ---------------------------------------------
    def theta(self, t: Any) -> np.ndarray:
        """ATM total variance θ_t, linear in t through the origin, linear beyond."""
        tt = np.asarray(t, dtype=float)
        xs = np.concatenate([[0.0], self.expiries])
        ys = np.concatenate([[0.0], self.thetas])
        out = np.interp(tt, xs, ys)
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return np.where(tt > xs[-1], ys[-1] + slope * (tt - xs[-1]), out)

    def _dtheta_dt(self, t: Any) -> np.ndarray:
        tt = np.asarray(t, dtype=float)
        xs = np.concatenate([[0.0], self.expiries])
        ys = np.concatenate([[0.0], self.thetas])
        slopes = np.diff(ys) / np.diff(xs)
        idx = np.clip(np.searchsorted(xs, tt, side="right") - 1, 0, slopes.size - 1)
        return slopes[idx]

    def phi(self, theta: Any) -> np.ndarray:
        th = np.asarray(theta, dtype=float)
        return self.eta / (th**self.gamma * (1.0 + th) ** (1.0 - self.gamma))

    # -- the surface ---------------------------------------------------------
    def total_variance(self, k: Any, t: Any) -> np.ndarray:
        th = self.theta(t)
        ph = self.phi(th)
        kk = np.asarray(k, dtype=float)
        return 0.5 * th * (1.0 + self.rho * ph * kk + np.sqrt((ph * kk + self.rho) ** 2 + 1.0 - self.rho**2))

    def implied_vol(self, k: Any, t: Any) -> np.ndarray:
        tt = np.asarray(t, dtype=float)
        if np.any(tt <= 0.0):
            raise InputError("implied vol needs t > 0")
        return np.sqrt(self.total_variance(k, tt) / tt)

    def _derivatives(self, k: Any, t: Any) -> tuple[np.ndarray, ...]:
        """w, ∂w/∂k, ∂²w/∂k², ∂w/∂t — all in closed form."""
        kk = np.asarray(k, dtype=float)
        th = self.theta(t)
        ph = self.phi(th)
        rho = self.rho
        z = ph * kk + rho
        s = np.sqrt(z * z + 1.0 - rho * rho)
        w = 0.5 * th * (1.0 + rho * ph * kk + s)
        wk = 0.5 * th * ph * (rho + z / s)
        wkk = 0.5 * th * ph * ph * (1.0 - rho * rho) / s**3
        dphi = ph * (-self.gamma / th + (self.gamma - 1.0) / (1.0 + th))
        dw_dtheta = 0.5 * (1.0 + rho * ph * kk + s) + 0.5 * th * kk * dphi * (rho + z / s)
        wt = dw_dtheta * self._dtheta_dt(t)
        return w, wk, wkk, wt

    def density_factor(self, k: Any, t: Any) -> np.ndarray:
        """Gatheral–Jacquier g(k): the risk-neutral density is ≥ 0 iff g ≥ 0."""
        w, wk, wkk, _ = self._derivatives(k, t)
        kk = np.asarray(k, dtype=float)
        return (1.0 - kk * wk / (2.0 * w)) ** 2 - 0.25 * wk * wk * (1.0 / w + 0.25) + 0.5 * wkk

    def local_vol(self, k: Any, t: Any) -> np.ndarray:
        """Dupire local volatility σ_loc(k, t) from Gatheral's total-variance formula."""
        _, _, _, wt = self._derivatives(k, t)
        g = self.density_factor(k, t)
        if np.any(g <= 0.0):
            raise InputError("surface has butterfly arbitrage here: local vol undefined")
        return np.sqrt(np.maximum(wt, 0.0) / g)

    # -- certificate ---------------------------------------------------------
    def no_arbitrage(self, k_range: tuple[float, float] = (-1.5, 1.5), n: int = 121) -> dict[str, Any]:
        """Sufficient theoretical conditions plus a numerical scan of g(k) and ∂w/∂t."""
        butterfly_bound = self.eta * (1.0 + abs(self.rho))
        ks = np.linspace(k_range[0], k_range[1], n)
        ts = np.unique(np.concatenate([np.asarray(self.expiries), np.linspace(1e-3, self.expiries[-1], 24)]))
        kg, tg = np.meshgrid(ks, ts)
        g_min = float(np.min(self.density_factor(kg, tg)))
        # Calendar: total variance must not fall as t rises, at every k.
        w = self.total_variance(kg, tg)
        cal_min = float(np.min(np.diff(w, axis=0))) if ts.size > 1 else 0.0
        return {
            "butterfly_condition": butterfly_bound <= 2.0 + 1e-12 and 0.0 < self.gamma <= 0.5,
            "eta_one_plus_abs_rho": butterfly_bound,
            "calendar_condition": bool(np.all(np.diff(self.thetas) >= -1e-14)) and 0.0 <= self.gamma <= 1.0,
            "min_density_factor": g_min,
            "min_calendar_step": cal_min,
            "arbitrage_free": g_min >= -1e-10 and cal_min >= -1e-12,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "rho": self.rho,
            "eta": self.eta,
            "gamma": self.gamma,
            "expiries": list(self.expiries),
            "thetas": list(self.thetas),
            **self.meta,
        }


def ssvi_from_params(
    rho: float, eta: float, gamma: float, expiries: Sequence[float], thetas: Sequence[float]
) -> SSVISurface:
    return SSVISurface(float(rho), float(eta), float(gamma), tuple(map(float, expiries)), tuple(map(float, thetas)))


def fit_ssvi(
    k: Sequence[float] | np.ndarray,
    t: Sequence[float] | np.ndarray,
    iv: Sequence[float] | np.ndarray,
    *,
    weights: Sequence[float] | np.ndarray | None = None,
    enforce_no_arbitrage: bool = True,
) -> SSVISurface:
    """Fit SSVI to implied vols at log-moneyness ``k`` and expiry ``t``.

    All parameters are fitted jointly by Levenberg–Marquardt on implied-vol
    errors: ``(ρ, η, γ)`` plus the ATM total variances, parametrised as
    non-negative increments so ``θ_t`` is non-decreasing by construction.
    With ``enforce_no_arbitrage`` the butterfly condition ``η(1+|ρ|) ≤ 2`` is
    imposed by a penalty and ``γ`` is kept in ``(0, ½]``, so the result
    carries the Gatheral–Jacquier certificate.
    """
    from argentum.calibration import levenberg_marquardt

    kk = np.asarray(k, dtype=float)
    tt = np.asarray(t, dtype=float)
    vv = np.asarray(iv, dtype=float)
    if not (kk.shape == tt.shape == vv.shape) or kk.ndim != 1 or kk.size < 5:
        raise InputError("fit_ssvi needs at least 5 matching (k, t, iv) quotes")
    if not (np.all(np.isfinite(kk)) and np.all(np.isfinite(tt)) and np.all(np.isfinite(vv))):
        raise InputError("quotes must be finite")
    if np.any(tt <= 0.0) or np.any(vv <= 0.0):
        raise InputError("expiries and implied vols must be positive")
    wts = np.ones_like(vv) if weights is None else np.asarray(weights, dtype=float)
    if wts.shape != vv.shape or np.any(wts < 0.0):
        raise InputError("weights must be non-negative and match the quotes")
    expiries = np.unique(tt)
    slot = np.searchsorted(expiries, tt)

    # ATM total variance seed per expiry: quadratic in k through the nearest quotes.
    seeds: list[float] = []
    for i, te in enumerate(expiries):
        sel = slot == i
        ks, ws = kk[sel], vv[sel] ** 2 * te
        if ks.size >= 3:
            coef = np.polyfit(ks, ws, 2)
            seeds.append(max(float(np.polyval(coef, 0.0)), 1e-6))
        else:
            seeds.append(float(np.mean(ws)))
    theta0 = np.maximum.accumulate(np.asarray(seeds))
    incr0 = np.diff(np.concatenate([[0.0], theta0]))
    incr0 = np.maximum(incr0, 1e-8)
    gamma_hi = 0.5 if enforce_no_arbitrage else 1.0
    x0 = np.concatenate([[-0.3, 0.8, 0.4], incr0])
    bounds = [(-0.995, 0.995), (1e-4, 10.0), (1e-3, gamma_hi)] + [(1e-10, 10.0)] * expiries.size

    def build(x: np.ndarray) -> SSVISurface:
        thetas = np.cumsum(x[3:])
        return SSVISurface(float(x[0]), float(x[1]), float(x[2]), tuple(expiries.tolist()), tuple(thetas.tolist()))

    def residual(x: np.ndarray) -> np.ndarray:
        surf = build(x)
        err = (surf.implied_vol(kk, tt) - vv) * np.sqrt(wts)
        if enforce_no_arbitrage:
            excess = max(0.0, float(x[1]) * (1.0 + abs(float(x[0]))) - 2.0)
            err = np.concatenate([err, [1e3 * excess]])
        return np.asarray(err)

    x = levenberg_marquardt(residual, x0, bounds=bounds, maxiter=200, strict=False)
    if enforce_no_arbitrage and x[1] * (1.0 + abs(x[0])) > 2.0:
        x[1] = 2.0 / (1.0 + abs(x[0]))  # land exactly on the boundary
    surf = build(x)
    fitted = surf.implied_vol(kk, tt)
    rmse = float(np.sqrt(np.average((fitted - vv) ** 2, weights=np.maximum(wts, 1e-300))))
    return SSVISurface(
        surf.rho,
        surf.eta,
        surf.gamma,
        surf.expiries,
        surf.thetas,
        meta={"rmse_vol": rmse, "n_quotes": int(vv.size), "max_abs_vol_error": float(np.max(np.abs(fitted - vv)))},
    )


def local_vol_grid(surface: SSVISurface, ks: Sequence[float], ts: Sequence[float]) -> dict[str, Any]:
    """Local and implied vol on a (t, k) grid, for charts and tables."""
    kg, tg = np.meshgrid(np.asarray(ks, dtype=float), np.asarray(ts, dtype=float))
    return {
        "k": list(map(float, ks)),
        "t": list(map(float, ts)),
        "local_vol": surface.local_vol(kg, tg).tolist(),
        "implied_vol": surface.implied_vol(kg, tg).tolist(),
    }
