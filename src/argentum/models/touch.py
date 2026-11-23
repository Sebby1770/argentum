"""Cash-at-hit one-touch and no-touch (Reiner–Rubinstein / Haug)."""

from __future__ import annotations

import math

from argentum.math.special import norm_cdf
from argentum.types import require_non_negative, require_positive


def one_touch(
    spot: float,
    barrier: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    cash: float = 1.0,
    *,
    pay_at_hit: bool = True,
) -> float:
    """Cash paid if the barrier is touched. Down if ``barrier < spot``, else up."""
    s = require_positive("spot", spot)
    h = require_positive("barrier", barrier)
    vol = require_non_negative("vol", vol)
    t = require_non_negative("texp", texp)
    cash = require_non_negative("cash", cash)
    if t == 0.0 or vol == 0.0:
        hit = (s <= h) if h < s else (s >= h)
        # at t=0, already on the right side of the barrier without having "hit" unless equal
        return cash if s == h else 0.0 if not hit else 0.0
    if (h < s and s <= h) or (h > s and s >= h):
        return cash
    b = rate - div
    mu = (b - 0.5 * vol * vol) / (vol * vol)
    lam = math.sqrt(mu * mu + 2.0 * rate / (vol * vol))
    eta = 1.0 if h < s else -1.0
    z = math.log(h / s) / (vol * math.sqrt(t)) + lam * vol * math.sqrt(t)
    hs = h / s
    if pay_at_hit:
        return cash * (hs ** (mu + lam) * norm_cdf(eta * z) + hs ** (mu - lam) * norm_cdf(eta * z - 2.0 * eta * lam * vol * math.sqrt(t)))
    # cash at expiry if touched
    x2 = math.log(s / h) / (vol * math.sqrt(t)) + (1.0 + mu) * vol * math.sqrt(t)
    y2 = math.log(h / s) / (vol * math.sqrt(t)) + (1.0 + mu) * vol * math.sqrt(t)
    df = math.exp(-rate * t)
    return cash * df * (norm_cdf(eta * x2 - eta * mu * vol * math.sqrt(t)) - hs ** (2.0 * mu) * norm_cdf(eta * y2 - eta * mu * vol * math.sqrt(t)))


def no_touch(
    spot: float,
    barrier: float,
    rate: float,
    div: float,
    vol: float,
    texp: float,
    cash: float = 1.0,
) -> float:
    """Cash at expiry if the barrier is never touched. Complements the expiry-paid one-touch."""
    df = math.exp(-rate * texp)
    ot = one_touch(spot, barrier, rate, div, vol, texp, cash=cash, pay_at_hit=False)
    return max(cash * df - ot, 0.0)
