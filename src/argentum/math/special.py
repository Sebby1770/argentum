"""Normal distribution, Black d1/d2, and numerically stable helpers.

``norm_cdf`` uses ``math.erf`` (IEEE) for scalars and a vectorized path for
arrays. ``norm_inv`` is Peter J. Acklam's rational approximation with a
Halley polish; relative error is below 1e-15 on (1e-16, 1-1e-16).
"""

from __future__ import annotations

import math
from typing import overload

import numpy as np

from argentum.errors import InputError

SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)
INV_SQRT2PI = 1.0 / SQRT2PI
_ERF = np.vectorize(math.erf, otypes=[float])
_ERFC = np.vectorize(math.erfc, otypes=[float])


def _is_array(x: object) -> bool:
    return isinstance(x, (list, tuple, np.ndarray))


@overload
def norm_pdf(x: float) -> float: ...
@overload
def norm_pdf(x: np.ndarray) -> np.ndarray: ...


def norm_pdf(x):  # type: ignore[no-untyped-def]
    if _is_array(x):
        z = np.asarray(x, dtype=np.float64)
        return INV_SQRT2PI * np.exp(-0.5 * z * z)
    z = float(x)
    return INV_SQRT2PI * math.exp(-0.5 * z * z)


@overload
def norm_cdf(x: float) -> float: ...
@overload
def norm_cdf(x: np.ndarray) -> np.ndarray: ...


def norm_cdf(x):  # type: ignore[no-untyped-def]
    if _is_array(x):
        z = np.asarray(x, dtype=np.float64)
        return 0.5 * _ERFC(-z / SQRT2)
    z = float(x)
    return 0.5 * math.erfc(-z / SQRT2)


@overload
def norm_sf(x: float) -> float: ...
@overload
def norm_sf(x: np.ndarray) -> np.ndarray: ...


def norm_sf(x):  # type: ignore[no-untyped-def]
    """Survival function 1 - Φ(x) computed from the right tail."""
    if _is_array(x):
        z = np.asarray(x, dtype=np.float64)
        return 0.5 * _ERFC(z / SQRT2)
    z = float(x)
    return 0.5 * math.erfc(z / SQRT2)


def norm_inv(p: float) -> float:
    """Inverse standard normal CDF (Acklam + Halley)."""
    if not 0.0 < p < 1.0:
        if p == 0.0:
            return -math.inf
        if p == 1.0:
            return math.inf
        raise InputError(f"norm_inv argument must be in (0,1), got {p}")
    # Coefficients from Acklam's approximation.
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577509590705e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    elif p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    else:
        q = p - 0.5
        r = q * q
        x = (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    # Halley: x <- x - u / (pdf) / (1 + x u / (2 pdf))  with u = Φ(x)-p
    for _ in range(2):
        cdf = norm_cdf(x)
        pdf = norm_pdf(x)
        if pdf == 0.0:
            break
        u = cdf - p
        x = x - u / pdf / (1.0 + x * u / (2.0 * pdf))
    return x


def black_d1_d2(
    forward: float,
    strike: float,
    vol: float,
    texp: float,
) -> tuple[float, float]:
    if texp < 0.0:
        raise InputError("time to expiry must be >= 0")
    if forward <= 0.0 or strike <= 0.0:
        raise InputError("forward and strike must be positive for lognormal d1/d2")
    if texp == 0.0 or vol == 0.0:
        # intrinsic limit
        if forward > strike:
            return math.inf, math.inf
        if forward < strike:
            return -math.inf, -math.inf
        return 0.0, 0.0
    vol_sqrt_t = vol * math.sqrt(texp)
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * texp) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def discount_factor(rate: float, texp: float, compounding: str = "continuous") -> float:
    if texp == 0.0:
        return 1.0
    if compounding == "continuous":
        return math.exp(-rate * texp)
    if compounding == "simple":
        return 1.0 / (1.0 + rate * texp)
    raise InputError(f"unknown compounding {compounding}")
