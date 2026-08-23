"""1-D interpolation: linear, log-linear, natural cubic, Hyman monotone cubic."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from argentum.errors import CurveError, InputError
from argentum.math.linalg import thomas


def _prep(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.ndim != 1 or y.ndim != 1 or x.size != y.size or x.size < 2:
        raise InputError("interpolation requires 1-D x, y of equal length >= 2")
    if np.any(np.diff(x) <= 0.0):
        raise InputError("interpolation knots must be strictly increasing")
    return x, y


def _locate(x: np.ndarray, t: float) -> int:
    if t <= x[0]:
        return 0
    if t >= x[-1]:
        return int(x.size - 2)
    return int(np.searchsorted(x, t, side="right") - 1)


@dataclass(frozen=True, slots=True)
class Interpolator:
    x: np.ndarray
    y: np.ndarray
    kind: str
    extra: dict

    def __call__(self, t: float) -> float:
        return float(self.evaluate(np.array([t], dtype=np.float64))[0])

    def evaluate(self, t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=np.float64)
        out = np.empty_like(t)
        for i, ti in np.ndenumerate(t):
            out[i] = self._one(float(ti))
        return out

    def _one(self, t: float) -> float:
        x, y = self.x, self.y
        i = _locate(x, t)
        w = (t - x[i]) / (x[i + 1] - x[i])
        kind = self.kind
        if kind == "linear":
            return (1.0 - w) * y[i] + w * y[i + 1]
        if kind == "log_linear":
            if y[i] <= 0.0 or y[i + 1] <= 0.0:
                raise CurveError("log-linear interpolation requires positive values")
            return math_exp((1.0 - w) * math_log(y[i]) + w * math_log(y[i + 1]))
        if kind in {"cubic", "monotone_cubic"}:
            a, b, c, d = self.extra["coef"][i]
            dx = t - x[i]
            return ((a * dx + b) * dx + c) * dx + d
        raise CurveError(f"unknown interpolator {kind}")


def math_log(v: float) -> float:
    return float(np.log(v))


def math_exp(v: float) -> float:
    return float(np.exp(v))


def linear(x, y) -> Interpolator:
    x, y = _prep(x, y)
    return Interpolator(x, y, "linear", {})


def log_linear(x, y) -> Interpolator:
    x, y = _prep(x, y)
    if np.any(y <= 0.0):
        raise CurveError("log-linear interpolation requires positive values")
    return Interpolator(x, y, "log_linear", {})


def _cubic_slopes(x: np.ndarray, y: np.ndarray, monotone: bool) -> np.ndarray:
    n = x.size
    h = np.diff(x)
    delta = np.diff(y) / h
    # natural cubic second-derivative system on interior
    sub = np.zeros(n)
    diag = np.ones(n)
    sup = np.zeros(n)
    rhs = np.zeros(n)
    for i in range(1, n - 1):
        sub[i] = h[i - 1] / 6.0
        diag[i] = (h[i - 1] + h[i]) / 3.0
        sup[i] = h[i] / 6.0
        rhs[i] = delta[i] - delta[i - 1]
    m = thomas(sub, diag, sup, rhs)  # second derivatives
    # convert to first derivatives at knots
    d = np.empty(n)
    d[0] = delta[0] - h[0] * (2.0 * m[0] + m[1]) / 6.0
    d[-1] = delta[-1] + h[-1] * (m[-2] + 2.0 * m[-1]) / 6.0
    for i in range(1, n - 1):
        d[i] = delta[i] - h[i] * (2.0 * m[i] + m[i + 1]) / 6.0
    if monotone:
        d = _hyman_filter(d, delta)
    return d


def _hyman_filter(d: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """Hyman 1983 monotonicity filter on nodal derivatives."""
    n = d.size
    out = d.copy()
    for i in range(n):
        if i == 0:
            s = delta[0]
        elif i == n - 1:
            s = delta[-1]
        else:
            if delta[i - 1] * delta[i] <= 0.0:
                out[i] = 0.0
                continue
            s = 0.5 * (delta[i - 1] + delta[i])
        if s == 0.0:
            out[i] = 0.0
            continue
        # limit
        if i == 0:
            out[0] = _sign_limit(out[0], delta[0], 3.0 * delta[0])
        elif i == n - 1:
            out[-1] = _sign_limit(out[-1], delta[-1], 3.0 * delta[-1])
        else:
            a = 3.0 * min(abs(delta[i - 1]), abs(delta[i]))
            if abs(out[i]) > a:
                out[i] = math_copysign(a, out[i])
    return out


def math_copysign(mag: float, sgn: float) -> float:
    return mag if sgn >= 0 else -mag


def _sign_limit(value: float, neighbour: float, cap: float) -> float:
    if neighbour == 0.0:
        return 0.0
    if value * neighbour < 0.0:
        return 0.0
    if abs(value) > abs(cap):
        return cap
    return value


def _hermite_coefs(x: np.ndarray, y: np.ndarray, d: np.ndarray) -> list[tuple[float, float, float, float]]:
    coefs = []
    for i in range(x.size - 1):
        h = x[i + 1] - x[i]
        y0, y1 = y[i], y[i + 1]
        d0, d1 = d[i], d[i + 1]
        # y = a dx^3 + b dx^2 + c dx + d  with dx = t-x_i
        a = (2.0 * (y0 - y1) + (d0 + d1) * h) / (h * h * h)
        b = (3.0 * (y1 - y0) - (2.0 * d0 + d1) * h) / (h * h)
        c = d0
        dd = y0
        coefs.append((a, b, c, dd))
    return coefs


def cubic(x, y) -> Interpolator:
    x, y = _prep(x, y)
    d = _cubic_slopes(x, y, monotone=False)
    return Interpolator(x, y, "cubic", {"coef": _hermite_coefs(x, y, d)})


def monotone_cubic(x, y) -> Interpolator:
    x, y = _prep(x, y)
    d = _cubic_slopes(x, y, monotone=True)
    return Interpolator(x, y, "monotone_cubic", {"coef": _hermite_coefs(x, y, d)})


def make_interpolator(kind: str, x, y) -> Interpolator:
    kind = kind.lower().replace("-", "_")
    if kind in {"linear"}:
        return linear(x, y)
    if kind in {"log_linear", "loglinear"}:
        return log_linear(x, y)
    if kind in {"cubic", "natural_cubic"}:
        return cubic(x, y)
    if kind in {"monotone_cubic", "hyman", "pchip"}:
        return monotone_cubic(x, y)
    raise InputError(f"unknown interpolator {kind!r}")
