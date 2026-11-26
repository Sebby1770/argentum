"""Listed option chains: load quotes, derive implied vols, find static arbitrage.

A chain is a set of European quotes on one underlying (one spot, rate and
dividend yield) across strikes and expiries. Rows carry either a premium
(``price``, ``mid``, or ``bid`` + ``ask``) or an implied vol (``iv``);
expiry is ``texp`` in years or ``days`` (calendar, /365).

:func:`check_arbitrage` converts every quote to a call-equivalent price by
put–call parity and tests the model-free no-arbitrage conditions: price
bounds, vertical spreads (calls non-increasing in strike, slope ≥ −DF),
butterflies (convexity in strike) and calendar spreads (total implied
variance non-decreasing in expiry at fixed log-moneyness).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from argentum.errors import InputError
from argentum.models.vectorized import greeks_array, implied_vol_array, price_array
from argentum.types import require_finite, require_positive

MAX_QUOTES = 20_000


@dataclass(frozen=True)
class OptionChain:
    spot: float
    rate: float
    div: float
    texp: np.ndarray
    strike: np.ndarray
    omega: np.ndarray  # +1 call, -1 put
    price: np.ndarray
    iv: np.ndarray
    dropped: tuple[dict[str, Any], ...] = field(default=(), compare=False)

    @property
    def size(self) -> int:
        return int(self.texp.size)

    @property
    def expiries(self) -> np.ndarray:
        return np.unique(self.texp)

    def forward(self, t: Any) -> np.ndarray:
        return self.spot * np.exp((self.rate - self.div) * np.asarray(t, dtype=float))

    @property
    def log_moneyness(self) -> np.ndarray:
        return np.log(self.strike / self.forward(self.texp))

    @property
    def total_variance(self) -> np.ndarray:
        return self.iv**2 * self.texp

    @property
    def vega(self) -> np.ndarray:
        return greeks_array(self.spot, self.strike, self.rate, self.div, self.iv, self.texp, self.omega)["vega"]

    def otm(self) -> np.ndarray:
        """Mask of out-of-the-money quotes (calls at/above the forward, puts below)."""
        fwd = self.forward(self.texp)
        return ((self.omega > 0) & (self.strike >= fwd)) | ((self.omega < 0) & (self.strike < fwd))

    def call_equivalent(self) -> np.ndarray:
        """Every quote as a call price via parity: C = P + DF (F − K)."""
        df = np.exp(-self.rate * self.texp)
        return np.where(self.omega > 0, self.price, self.price + df * (self.forward(self.texp) - self.strike))

    def rows(self) -> list[dict[str, Any]]:
        return [
            {
                "texp": float(t),
                "strike": float(k),
                "type": "call" if w > 0 else "put",
                "price": float(p),
                "iv": float(v),
                "k": float(lm),
            }
            for t, k, w, p, v, lm in zip(
                self.texp, self.strike, self.omega, self.price, self.iv, self.log_moneyness
            )
        ]


def _num(row: Mapping[str, Any], *names: str) -> float | None:
    for name in names:
        raw = row.get(name)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise InputError(f"{name} must be a number, got {raw!r}") from exc
        if not math.isfinite(value):
            raise InputError(f"{name} must be finite")
        return value
    return None


def chain_from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    spot: float,
    rate: float = 0.0,
    div: float = 0.0,
) -> OptionChain:
    """Build a chain from dict rows (CSV or JSON). Unusable quotes are dropped and reported."""
    spot = require_positive("spot", spot)
    rate = require_finite("rate", rate)
    div = require_finite("div", div)
    parsed: list[tuple[float, float, float, float | None, float | None]] = []
    dropped: list[dict[str, Any]] = []
    for n, row in enumerate(rows, start=1):
        if n > MAX_QUOTES:
            raise InputError(f"a chain is limited to {MAX_QUOTES} quotes")
        try:
            texp = _num(row, "texp", "t", "expiry_years")
            if texp is None:
                days = _num(row, "days", "dte")
                texp = None if days is None else days / 365.0
            strike = _num(row, "strike", "k")
            if texp is None or strike is None:
                raise InputError("needs texp (or days) and strike")
            if texp <= 0.0 or strike <= 0.0:
                raise InputError("texp and strike must be positive")
            kind = str(row.get("type", row.get("option_type", "call"))).strip().lower()
            if kind not in {"call", "c", "put", "p"}:
                raise InputError(f"type must be call or put, got {kind!r}")
            omega = 1.0 if kind.startswith("c") else -1.0
            price = _num(row, "price", "mid", "premium")
            if price is None:
                bid, ask = _num(row, "bid"), _num(row, "ask")
                if bid is not None and ask is not None:
                    if ask < bid:
                        raise InputError("ask is below bid")
                    price = 0.5 * (bid + ask)
            iv = _num(row, "iv", "implied_vol", "vol")
            if price is None and iv is None:
                raise InputError("needs price, mid, bid+ask, or iv")
            if iv is not None and iv <= 0.0:
                raise InputError("iv must be positive")
            parsed.append((texp, strike, omega, price, iv))
        except InputError as exc:
            dropped.append({"row": n, "reason": str(exc)})
    if not parsed:
        raise InputError("no usable quotes in the chain")
    t = np.array([p[0] for p in parsed])
    k = np.array([p[1] for p in parsed])
    w = np.array([p[2] for p in parsed])
    has_iv = np.array([p[4] is not None for p in parsed])
    iv_in = np.array([p[4] if p[4] is not None else np.nan for p in parsed])
    px_in = np.array([p[3] if p[3] is not None else np.nan for p in parsed])
    prices = np.where(has_iv & np.isnan(px_in), price_array(spot, k, rate, div, np.where(has_iv, iv_in, 0.2), t, w), px_in)
    ivs = np.where(has_iv, iv_in, implied_vol_array(np.maximum(prices, 0.0), spot, k, rate, div, t, w, errors="nan"))
    bad = ~np.isfinite(ivs) | (ivs <= 0.0) | (prices < 0.0)
    for i in np.flatnonzero(bad):
        dropped.append({"row": None, "texp": float(t[i]), "strike": float(k[i]), "reason": "price outside no-arbitrage bounds or zero time value"})
    keep = ~bad
    if not np.any(keep):
        raise InputError("no quote in the chain has a valid implied vol")
    order = np.lexsort((w[keep], k[keep], t[keep]))
    return OptionChain(
        spot,
        rate,
        div,
        t[keep][order],
        k[keep][order],
        w[keep][order],
        prices[keep][order],
        ivs[keep][order],
        tuple(dropped),
    )


def check_arbitrage(chain: OptionChain, *, tol: float = 1e-8) -> dict[str, Any]:
    """Model-free static-arbitrage scan of a chain. Amounts are in premium units."""
    violations: list[dict[str, Any]] = []
    calls = chain.call_equivalent()
    for te in chain.expiries:
        sel = chain.texp == te
        ks, cs = chain.strike[sel], calls[sel]
        # Calls and puts at one strike give one call-equivalent each: average them.
        uk, inv = np.unique(ks, return_inverse=True)
        cu = np.bincount(inv, weights=cs) / np.bincount(inv)
        df = math.exp(-chain.rate * te)
        fwd = float(chain.forward(te))
        lower = df * np.maximum(fwd - uk, 0.0)
        upper = df * fwd
        for kk, c, lo in zip(uk, cu, lower):
            if c < lo - tol or c > upper + tol:
                violations.append({"kind": "bounds", "texp": float(te), "strikes": [float(kk)], "amount": float(max(lo - c, c - upper))})
        for i in range(uk.size - 1):
            drop = cu[i] - cu[i + 1]
            width = uk[i + 1] - uk[i]
            if drop < -tol:
                violations.append({"kind": "vertical", "texp": float(te), "strikes": [float(uk[i]), float(uk[i + 1])], "amount": float(-drop)})
            elif drop > df * width + tol:
                violations.append({"kind": "vertical", "texp": float(te), "strikes": [float(uk[i]), float(uk[i + 1])], "amount": float(drop - df * width)})
        for i in range(1, uk.size - 1):
            k1, k2, k3 = uk[i - 1], uk[i], uk[i + 1]
            lam = (k3 - k2) / (k3 - k1)
            excess = cu[i] - (lam * cu[i - 1] + (1.0 - lam) * cu[i + 1])
            if excess > tol:
                violations.append({"kind": "butterfly", "texp": float(te), "strikes": [float(k1), float(k2), float(k3)], "amount": float(excess)})
    # Calendar: total variance at fixed log-moneyness must not fall with expiry.
    exps = chain.expiries
    lm, wv = chain.log_moneyness, chain.total_variance
    for a, b in zip(exps[:-1], exps[1:]):
        sa, sb = chain.texp == a, chain.texp == b
        ka, wa = lm[sa], wv[sa]
        order = np.argsort(ka)
        ka, wa = ka[order], wa[order]
        for kb, wb in zip(lm[sb], wv[sb]):
            if ka[0] <= kb <= ka[-1]:
                w_early = float(np.interp(kb, ka, wa))
                if wb < w_early - 1e-10:
                    violations.append({"kind": "calendar", "texp": [float(a), float(b)], "k": float(kb), "amount": float(w_early - wb)})
    counts = {kind: sum(1 for v in violations if v["kind"] == kind) for kind in ("bounds", "vertical", "butterfly", "calendar")}
    return {"arbitrage_free": not violations, "counts": counts, "violations": violations[:200], "n_violations": len(violations)}


def demo_chain(*, seed: int = 20261126, noise_vol: float = 0.002) -> OptionChain:
    """A synthetic SPX-like chain: Bates prices plus seeded bid/ask noise.

    Generated, not market data — five expiries, OTM puts and calls, roughly
    0.6–1.4 × forward, implied-vol noise of ``noise_vol`` (default 0.2 vol pt).
    """
    from argentum.models.charfn import BatesCF, HestonCF, cos_price

    spot, rate, div = 100.0, 0.03, 0.01
    model = BatesCF(HestonCF(kappa=2.5, theta=0.035, sigma=0.55, rho=-0.75, v0=0.025), lam=0.15, mu_j=-0.12, delta_j=0.1)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for te in (0.08, 0.25, 0.5, 1.0, 2.0):
        fwd = spot * math.exp((rate - div) * te)
        width = 0.35 * math.sqrt(te) + 0.12
        strikes = np.round(fwd * np.exp(np.linspace(-1.6 * width, width, 15)), 1)
        calls = cos_price(model, spot, strikes, rate, div, te, "call")
        puts = cos_price(model, spot, strikes, rate, div, te, "put")
        for kk, c, p in zip(strikes, calls, puts):
            is_call = kk >= fwd
            px = float(c if is_call else p)
            rows.append({"texp": te, "strike": float(kk), "type": "call" if is_call else "put", "price": px})
    clean = chain_from_rows(rows, spot=spot, rate=rate, div=div)
    noisy_iv = clean.iv + noise_vol * rng.standard_normal(clean.size)
    noisy = [
        {"texp": float(t), "strike": float(k), "type": "call" if w > 0 else "put", "iv": float(v)}
        for t, k, w, v in zip(clean.texp, clean.strike, clean.omega, noisy_iv)
    ]
    return chain_from_rows(noisy, spot=spot, rate=rate, div=div)
