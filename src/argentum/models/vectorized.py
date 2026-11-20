"""Vectorised Black–Scholes–Merton for whole option chains.

Every function broadcasts NumPy arrays (or scalars) against each other, so a
chain of 10,000 strikes × expiries prices in one call. Inputs are validated
element-wise with the same rules as the scalar engine: no silent NaNs.

``option_type`` may be ``"call"`` / ``"put"``, an :class:`OptionType`, or an
array of those strings (or of ``+1`` / ``-1``).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from argentum.errors import InputError
from argentum.math.special import norm_cdf, norm_pdf
from argentum.types import OptionType

ArrayLike = Any


def _omega(option_type: ArrayLike) -> np.ndarray:
    if isinstance(option_type, OptionType):
        return np.asarray(float(option_type.omega))
    arr = np.asarray(option_type)
    if arr.dtype.kind in "iuf":
        out = np.sign(arr.astype(np.float64))
        if np.any(out == 0.0):
            raise InputError("numeric option_type must be +1 (call) or -1 (put)")
        return out
    lowered = np.char.lower(arr.astype(str))
    is_call = np.char.startswith(lowered, "c")
    is_put = np.char.startswith(lowered, "p")
    if not np.all(is_call | is_put):
        raise InputError("option_type entries must be 'call' or 'put'")
    return np.where(is_call, 1.0, -1.0)


def _check(name: str, x: ArrayLike, *, positive: bool = False, non_negative: bool = False) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise InputError(f"{name} must be finite")
    if positive and np.any(arr <= 0.0):
        raise InputError(f"{name} must be positive")
    if non_negative and np.any(arr < 0.0):
        raise InputError(f"{name} must be >= 0")
    return arr


def _inputs(spot, strike, rate, div, vol, texp, option_type):  # type: ignore[no-untyped-def]
    s = _check("spot", spot, positive=True)
    k = _check("strike", strike, positive=True)
    r = _check("rate", rate)
    q = _check("div", div)
    v = _check("vol", vol, non_negative=True)
    t = _check("texp", texp, non_negative=True)
    w = _omega(option_type)
    return np.broadcast_arrays(s, k, r, q, v, t, w)


def price_array(
    spot: ArrayLike,
    strike: ArrayLike,
    rate: ArrayLike,
    div: ArrayLike,
    vol: ArrayLike,
    texp: ArrayLike,
    option_type: ArrayLike = "call",
) -> np.ndarray:
    """Discounted European prices, broadcast over every argument."""
    s, k, r, q, v, t, w = _inputs(spot, strike, rate, div, vol, texp, option_type)
    df_r = np.exp(-r * t)
    fwd = s * np.exp((r - q) * t)
    sig_t = v * np.sqrt(t)
    live = sig_t > 0.0
    safe = np.where(live, sig_t, 1.0)
    d1 = np.where(live, np.log(fwd / k) / safe + 0.5 * safe, 0.0)
    d2 = d1 - np.where(live, safe, 0.0)
    value = df_r * w * (fwd * norm_cdf(w * d1) - k * norm_cdf(w * d2))
    # Zero variance: discounted intrinsic on the forward (spot when t == 0).
    intrinsic = df_r * np.maximum(w * (fwd - k), 0.0)
    return np.asarray(np.where(live, np.maximum(value, 0.0), intrinsic), dtype=np.float64)


def greeks_array(
    spot: ArrayLike,
    strike: ArrayLike,
    rate: ArrayLike,
    div: ArrayLike,
    vol: ArrayLike,
    texp: ArrayLike,
    option_type: ArrayLike = "call",
) -> dict[str, np.ndarray]:
    """Delta, gamma, vega, theta (per year), rho and vanna as broadcast arrays.

    Conventions match :func:`argentum.models.black_scholes.greeks`. Where the
    total variance is zero the second-order greeks are reported as 0.
    """
    s, k, r, q, v, t, w = _inputs(spot, strike, rate, div, vol, texp, option_type)
    df_r = np.exp(-r * t)
    df_q = np.exp(-q * t)
    fwd = s * np.exp((r - q) * t)
    sqrt_t = np.sqrt(t)
    sig_t = v * sqrt_t
    live = sig_t > 0.0
    safe = np.where(live, sig_t, 1.0)
    d1 = np.where(live, np.log(fwd / k) / safe + 0.5 * safe, np.where(fwd > k, np.inf, -np.inf))
    d2 = np.where(live, d1 - safe, d1)
    pdf = np.where(live, norm_pdf(np.where(live, d1, 0.0)), 0.0)
    nd1 = norm_cdf(w * d1)
    nd2 = norm_cdf(w * d2)
    safe_v = np.where(v > 0.0, v, 1.0)
    safe_sqrt = np.where(sqrt_t > 0.0, sqrt_t, 1.0)
    delta = w * df_q * nd1
    gamma = np.where(live, df_q * pdf / (s * safe), 0.0)
    vega = s * df_q * pdf * sqrt_t
    theta = (
        -np.where(live, s * df_q * pdf * v / (2.0 * safe_sqrt), 0.0)
        - w * r * k * df_r * nd2
        + w * q * s * df_q * nd1
    )
    rho = w * k * t * df_r * nd2
    vanna = np.where(live, -df_q * pdf * np.where(live, d2, 0.0) / safe_v, 0.0)
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho, "vanna": vanna}


def implied_vol_array(
    target: ArrayLike,
    spot: ArrayLike,
    strike: ArrayLike,
    rate: ArrayLike,
    div: ArrayLike,
    texp: ArrayLike,
    option_type: ArrayLike = "call",
    *,
    tol: float = 1e-12,
    maxiter: int = 100,
    errors: str = "raise",
) -> np.ndarray:
    """Implied vols for a whole chain by safeguarded Newton on the OTM option.

    Each quote keeps its own bracket ``[lo, hi]``; a Newton step that leaves the
    bracket (or stalls on a vanishing vega) is replaced by bisection, so every
    element converges. ``errors="raise"`` rejects quotes outside the no-arbitrage
    band ``[intrinsic, upper]``; ``errors="nan"`` marks them NaN instead, so one
    stale print does not sink a 2,000-strike chain.
    """
    if errors not in {"raise", "nan"}:
        raise InputError("errors must be 'raise' or 'nan'")
    p = _check("price", target, non_negative=True)
    s, k, r, q, t, w, p = np.broadcast_arrays(
        _check("spot", spot, positive=True),
        _check("strike", strike, positive=True),
        _check("rate", rate),
        _check("div", div),
        _check("texp", texp, non_negative=True),
        _omega(option_type),
        p,
    )
    df_r = np.exp(-r * t)
    fwd = s * np.exp((r - q) * t)
    intrinsic = df_r * np.maximum(w * (fwd - k), 0.0)
    upper = np.where(w > 0.0, s * np.exp(-q * t), k * df_r)
    bad = (p < intrinsic - 1e-12) | (p > upper + 1e-12) | (t <= 0.0)
    if errors == "raise" and np.any(bad & ~((t <= 0.0) & (np.abs(p - intrinsic) <= 1e-12))):
        idx = int(np.argmax(bad))
        raise InputError(
            f"quote {idx} ({float(p.flat[idx])!r}) is outside [intrinsic, upper] or has texp=0"
        )
    # Convert to the out-of-the-money side via put-call parity: ITM vegas vanish.
    otm_w = np.where(fwd >= k, -1.0, 1.0)
    otm_p = p - np.where(w == otm_w, 0.0, w * df_r * (fwd - k))
    otm_p = np.maximum(otm_p, 0.0)
    flat = otm_p <= 0.0

    lo = np.full(p.shape, 1e-9)
    hi = np.full(p.shape, 10.0)
    # Brenner–Subrahmanyam seed, clipped into the bracket.
    sig = np.clip(np.sqrt(2.0 * np.pi / np.maximum(t, 1e-300)) * otm_p / (df_r * fwd), 1e-4, 5.0)
    sqrt_t = np.sqrt(np.maximum(t, 0.0))
    active = ~(bad | flat)
    for _ in range(maxiter):
        if not np.any(active):
            break
        model = price_array(s, k, r, q, sig, np.where(active, t, 0.0), otm_w)
        diff = model - otm_p
        hi = np.where(active & (diff > 0.0), sig, hi)
        lo = np.where(active & (diff <= 0.0), sig, lo)
        d1 = np.log(fwd / k) / (sig * np.where(sqrt_t > 0, sqrt_t, 1.0)) + 0.5 * sig * sqrt_t
        vega = s * np.exp(-q * t) * norm_pdf(d1) * sqrt_t
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            newton = sig - diff / vega
        inside = np.isfinite(newton) & (newton > lo) & (newton < hi)
        step = np.where(inside, newton, 0.5 * (lo + hi))
        hit = active & (np.abs(diff) <= tol * np.maximum(1.0, otm_p))
        moved = active & ~hit
        sig_next = np.where(moved, step, sig)
        stalled = moved & (np.abs(sig_next - sig) <= tol * sig)
        sig = sig_next
        active &= ~(hit | stalled)
    out = np.where(flat & ~bad, 0.0, sig)
    return np.asarray(np.where(bad & ~((t <= 0.0) & flat), np.nan, out), dtype=np.float64)


def chain(
    spot: float,
    strikes: ArrayLike,
    expiries: ArrayLike,
    rate: float,
    div: float,
    vol: ArrayLike,
    option_type: ArrayLike = "call",
) -> dict[str, np.ndarray]:
    """Price and risk a strike × expiry grid. ``vol`` may be a scalar or a grid."""
    k = np.asarray(strikes, dtype=np.float64)[None, :]
    t = np.asarray(expiries, dtype=np.float64)[:, None]
    out = {"price": price_array(spot, k, rate, div, vol, t, option_type)}
    out.update(greeks_array(spot, k, rate, div, vol, t, option_type))
    out["strike"] = np.broadcast_to(k, out["price"].shape).copy()
    out["texp"] = np.broadcast_to(t, out["price"].shape).copy()
    return out
