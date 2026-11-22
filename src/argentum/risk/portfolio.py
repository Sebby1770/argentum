"""Book-level market risk: full-revaluation VaR / ES and P&L explain.

Positions are grouped into *underlyings*: by ``VanillaPosition.underlying``
when it is set, otherwise by spot level (positions marked at the same spot
are taken to be on the same asset). Each underlying has one spot factor and
one implied-vol factor. Tags stay what they are elsewhere — strategy labels. Every scenario revalues every position with the
vectorised Black–Scholes engine — no delta-normal shortcut — and the
delta–gamma–vega–theta Taylor estimate is reported alongside, so the gap
between the two (the non-linearity a Greeks report hides) is visible.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from argentum.book import Book, VanillaPosition
from argentum.errors import InputError
from argentum.models.vectorized import greeks_array, price_array
from argentum.types import OptionType

TRADING_DAYS = 252.0


@dataclass(frozen=True, slots=True)
class _Vectors:
    qty: np.ndarray
    spot: np.ndarray
    strike: np.ndarray
    rate: np.ndarray
    div: np.ndarray
    vol: np.ndarray
    texp: np.ndarray
    omega: np.ndarray
    factor: np.ndarray  # index of each position's underlying
    names: tuple[str, ...]


def _vectors(book: Book) -> _Vectors:
    if not book.positions:
        raise InputError("book has no positions")
    names: list[str] = []
    factor = []
    for pos in book.positions:
        key = pos.underlying or f"spot={pos.spot:g}"
        if key not in names:
            names.append(key)
        factor.append(names.index(key))
    col = lambda attr: np.array([float(getattr(p, attr)) for p in book.positions])  # noqa: E731
    return _Vectors(
        qty=col("quantity"),
        spot=col("spot"),
        strike=col("strike"),
        rate=col("rate"),
        div=col("div"),
        vol=col("vol"),
        texp=col("texp"),
        omega=np.array([float(OptionType(p.option_type).omega) for p in book.positions]),
        factor=np.array(factor, dtype=int),
        names=tuple(names),
    )


def _tail(pnl: np.ndarray, alpha: float) -> tuple[float, float]:
    """VaR and expected shortfall as positive loss numbers at confidence ``alpha``."""
    q = float(np.quantile(pnl, 1.0 - alpha, method="lower"))
    tail = pnl[pnl <= q]
    return -q, -float(tail.mean())


def _histogram(pnl: np.ndarray, bins: int = 40) -> dict[str, list[float]]:
    counts, edges = np.histogram(pnl, bins=bins)
    return {"edges": edges.tolist(), "counts": counts.astype(float).tolist()}


def _revalue(v: _Vectors, spot_ret: np.ndarray, dvol: np.ndarray, dt: float) -> np.ndarray:
    """Book NPV for each scenario row. ``spot_ret`` / ``dvol`` are (n_scen, n_factors)."""
    s = v.spot * np.exp(spot_ret[:, v.factor])
    sig = np.maximum(v.vol + dvol[:, v.factor], 1e-4)
    t = np.maximum(v.texp - dt, 0.0)
    px = price_array(s, v.strike, v.rate, v.div, sig, t, v.omega)
    return np.asarray(px @ v.qty)


def _taylor(v: _Vectors, spot_ret: np.ndarray, dvol: np.ndarray, dt: float) -> np.ndarray:
    """Second-order Greeks estimate of the same scenarios (delta, gamma, vega, vanna, volga, theta)."""
    g = greeks_array(v.spot, v.strike, v.rate, v.div, v.vol, v.texp, v.omega)
    ds = v.spot * (np.exp(spot_ret[:, v.factor]) - 1.0)
    dv = dvol[:, v.factor]
    per = (
        g["delta"] * ds
        + 0.5 * g["gamma"] * ds * ds
        + g["vega"] * dv
        + g["vanna"] * ds * dv
        + 0.5 * g["volga"] * dv * dv
        + g["theta"] * np.minimum(dt, v.texp)
    )
    return np.asarray(per @ v.qty)


def monte_carlo_var(
    book: Book,
    *,
    alpha: float = 0.99,
    horizon_days: float = 1.0,
    n_scenarios: int = 20_000,
    spot_vols: Mapping[str, float] | None = None,
    correlation: float = 0.5,
    vol_of_vol: float = 0.8,
    spot_vol_correlation: float = -0.5,
    seed: int = 7,
) -> dict[str, Any]:
    """Monte Carlo VaR / ES of a vanilla book by full revaluation.

    Each underlying's log-return is normal with annual volatility from
    ``spot_vols`` (default: the mean implied vol of its positions); every
    pair of underlyings has correlation ``correlation``. Implied vols move
    additively with annual stdev ``vol_of_vol × implied vol`` and correlation
    ``spot_vol_correlation`` to their own spot (the leverage effect).
    Time decays by the horizon, so theta is in the P&L.
    """
    if not 0.5 < alpha < 1.0:
        raise InputError("alpha must be in (0.5, 1)")
    if horizon_days <= 0.0 or not math.isfinite(horizon_days):
        raise InputError("horizon_days must be positive")
    if n_scenarios < 500:
        raise InputError("n_scenarios must be at least 500")
    if not -1.0 < correlation < 1.0 or not -1.0 < spot_vol_correlation < 1.0:
        raise InputError("correlations must be in (-1, 1)")
    if vol_of_vol < 0.0:
        raise InputError("vol_of_vol must be >= 0")
    v = _vectors(book)
    m = len(v.names)
    sv = np.array(
        [
            float((spot_vols or {}).get(name, np.mean(v.vol[v.factor == j])))
            for j, name in enumerate(v.names)
        ]
    )
    if np.any(sv < 0.0) or not np.all(np.isfinite(sv)):
        raise InputError("spot_vols must be finite and >= 0")
    h = horizon_days / TRADING_DAYS
    # Correlation over 2m factors: [spot_1..spot_m, vol_1..vol_m].
    c = np.full((m, m), correlation)
    np.fill_diagonal(c, 1.0)
    big = np.block([[c, spot_vol_correlation * np.eye(m)], [spot_vol_correlation * np.eye(m), c]])
    w, vecs = np.linalg.eigh(big)
    root = vecs * np.sqrt(np.clip(w, 0.0, None))
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_scenarios, 2 * m)) @ root.T
    mean_iv = np.array([np.mean(v.vol[v.factor == j]) for j in range(m)])
    spot_ret = -0.5 * sv * sv * h + sv * math.sqrt(h) * z[:, :m]
    dvol = vol_of_vol * mean_iv * math.sqrt(h) * z[:, m:]

    base = float(price_array(v.spot, v.strike, v.rate, v.div, v.vol, v.texp, v.omega) @ v.qty)
    pnl = _revalue(v, spot_ret, dvol, h) - base
    approx = _taylor(v, spot_ret, dvol, h)
    var, es = _tail(pnl, alpha)
    var_t, es_t = _tail(approx, alpha)
    worst = np.argsort(pnl)[:5]
    return {
        "method": "monte_carlo_full_revaluation",
        "alpha": alpha,
        "horizon_days": horizon_days,
        "n_scenarios": n_scenarios,
        "npv": base,
        "var": var,
        "es": es,
        "var_taylor": var_t,
        "es_taylor": es_t,
        "mean_pnl": float(pnl.mean()),
        "stdev_pnl": float(pnl.std(ddof=1)),
        "underlyings": list(v.names),
        "spot_vols": sv.tolist(),
        "worst": [
            {
                "pnl": float(pnl[i]),
                "spot_moves": (np.exp(spot_ret[i]) - 1.0).tolist(),
                "vol_moves": dvol[i].tolist(),
            }
            for i in worst
        ],
        "histogram": _histogram(pnl),
        "seed": seed,
    }


def historical_var(
    book: Book,
    returns: Mapping[str, Sequence[float]],
    *,
    alpha: float = 0.99,
    vol_changes: Mapping[str, Sequence[float]] | None = None,
    horizon_days: float = 1.0,
) -> dict[str, Any]:
    """Historical-simulation VaR / ES: replay aligned daily log-returns.

    ``returns[name]`` is one series per underlying name (same length for all,
    day ``i`` of every series applied together); unnamed positions are keyed
    ``"spot=<level>"``. Missing names get zero moves. Optional
    ``vol_changes[name]`` replays additive implied-vol changes.
    """
    if not 0.5 < alpha < 1.0:
        raise InputError("alpha must be in (0.5, 1)")
    v = _vectors(book)
    lengths = {len(r) for r in returns.values()} | {len(r) for r in (vol_changes or {}).values()}
    if not lengths or 0 in lengths:
        raise InputError("returns must contain at least one non-empty series")
    if len(lengths) != 1:
        raise InputError("every return / vol-change series must have the same length")
    n = lengths.pop()
    spot_ret = np.zeros((n, len(v.names)))
    dvol = np.zeros((n, len(v.names)))
    for j, name in enumerate(v.names):
        if name in returns:
            spot_ret[:, j] = np.asarray(returns[name], dtype=float)
        if vol_changes and name in vol_changes:
            dvol[:, j] = np.asarray(vol_changes[name], dtype=float)
    if not (np.all(np.isfinite(spot_ret)) and np.all(np.isfinite(dvol))):
        raise InputError("return series must be finite")
    h = horizon_days / TRADING_DAYS
    base = float(price_array(v.spot, v.strike, v.rate, v.div, v.vol, v.texp, v.omega) @ v.qty)
    pnl = _revalue(v, spot_ret * math.sqrt(horizon_days), dvol * math.sqrt(horizon_days), h) - base
    var, es = _tail(pnl, alpha)
    return {
        "method": "historical_full_revaluation",
        "alpha": alpha,
        "n_scenarios": n,
        "npv": base,
        "var": var,
        "es": es,
        "histogram": _histogram(pnl, bins=min(40, max(5, n // 5))),
    }


def pnl_explain(before: Book, after: Book) -> dict[str, Any]:
    """Attribute the P&L between two marks of the same book to its Greeks.

    ``after`` must hold the same contracts (quantity, strike, type) in the
    same order, re-marked with new spot / vol / rate / time to expiry. The
    Taylor legs use the *before* Greeks; ``unexplained`` is what they miss.
    """
    if len(before.positions) != len(after.positions):
        raise InputError("before and after books must have the same positions")
    rows = []
    totals = dict.fromkeys(
        ("actual", "delta", "gamma", "vega", "theta", "rho", "vanna", "volga", "unexplained"), 0.0
    )
    for a, b in zip(before.positions, after.positions):
        _same_contract(a, b)
        g0 = a.value().greeks
        assert g0 is not None
        actual = b.value().npv - a.value().npv
        ds, dv, dr = b.spot - a.spot, b.vol - a.vol, b.rate - a.rate
        dt = a.texp - b.texp
        legs = {
            "delta": g0.delta * ds,
            "gamma": 0.5 * g0.gamma * ds * ds,
            "vega": g0.vega * dv,
            "theta": g0.theta * dt,
            "rho": g0.rho * dr,
            "vanna": g0.vanna * ds * dv,
            "volga": 0.5 * g0.volga * dv * dv,
        }
        explained = sum(legs.values())
        row = {"tag": a.tag, "actual": actual, **legs, "unexplained": actual - explained}
        rows.append(row)
        for key in totals:
            totals[key] += float(row[key])  # type: ignore[arg-type]
    return {"positions": rows, "total": totals}


def _same_contract(a: VanillaPosition, b: VanillaPosition) -> None:
    if (
        a.quantity != b.quantity
        or a.strike != b.strike
        or OptionType(a.option_type) is not OptionType(b.option_type)
    ):
        raise InputError("pnl_explain needs the same contracts in both books")
    if b.texp > a.texp:
        raise InputError("the after-mark cannot be earlier than the before-mark")
