"""Scalar root finders used by implied vol, YTM, and curve bootstrap."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from argentum.errors import ConvergenceError, InputError


@dataclass(frozen=True, slots=True)
class SolverResult:
    root: float
    iterations: int
    residual: float
    converged: bool


def newton(
    f: Callable[[float], float],
    x0: float,
    *,
    fprime: Callable[[float], float] | None = None,
    tol: float = 1e-12,
    maxiter: int = 50,
    min_step: float = 1e-16,
    lower: float | None = None,
    upper: float | None = None,
    fd_step: float = 1e-6,
) -> float:
    """Newton with optional finite-difference derivative and projection."""
    x = float(x0)
    last_f = 0.0
    for i in range(1, maxiter + 1):
        fx = f(x)
        last_f = fx
        if abs(fx) < tol:
            return x
        if fprime is None:
            h = fd_step * max(1.0, abs(x))
            df = (f(x + h) - fx) / h
        else:
            df = fprime(x)
        if abs(df) < min_step:
            raise ConvergenceError("Newton derivative vanished", iterations=i, residual=fx)
        step = fx / df
        x_new = x - step
        if lower is not None and x_new < lower:
            x_new = 0.5 * (x + lower)
        if upper is not None and x_new > upper:
            x_new = 0.5 * (x + upper)
        if abs(x_new - x) < min_step and abs(fx) < 1e4 * tol:
            return x_new
        x = x_new
    raise ConvergenceError("Newton failed to converge", iterations=maxiter, residual=last_f)


def brent(
    f: Callable[[float], float],
    a: float,
    b: float,
    *,
    tol: float = 1e-14,
    maxiter: int = 100,
) -> float:
    """Brent's method (Dekker + inverse quadratic) on a bracket [a, b]."""
    fa, fb = f(a), f(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0.0:
        raise InputError(f"Brent: f(a) and f(b) must change sign (got {fa}, {fb})")
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc = a, fa
    d = b - a
    mflag = True
    for i in range(1, maxiter + 1):
        if fb == 0.0 or abs(b - a) < tol:
            return b
        if fa != fc and fb != fc:
            # inverse quadratic interpolation
            s = (
                a * fb * fc / ((fa - fb) * (fa - fc))
                + b * fa * fc / ((fb - fa) * (fb - fc))
                + c * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            s = b - fb * (b - a) / (fb - fa)
        cond1 = not ((3.0 * a + b) / 4.0 <= s <= b or b <= s <= (3.0 * a + b) / 4.0)
        cond2 = mflag and abs(s - b) >= abs(b - c) / 2.0
        cond3 = (not mflag) and abs(s - b) >= abs(c - d) / 2.0
        cond4 = mflag and abs(b - c) < tol
        cond5 = (not mflag) and abs(c - d) < tol
        if cond1 or cond2 or cond3 or cond4 or cond5:
            s = 0.5 * (a + b)
            mflag = True
        else:
            mflag = False
        fs = f(s)
        d, c, fc = c, b, fb
        if fa * fs < 0.0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa
    raise ConvergenceError("Brent failed to converge", iterations=maxiter, residual=fb)


def bracket_and_solve(
    f: Callable[[float], float],
    x0: float,
    *,
    lower: float = 1e-12,
    upper: float = 10.0,
    factor: float = 1.6,
    max_expand: int = 40,
    tol: float = 1e-12,
) -> float:
    """Expand a bracket around ``x0`` then Brent."""
    a = max(lower, x0 / factor if x0 != 0 else lower)
    b = min(upper, x0 * factor if x0 != 0 else min(upper, 1.0))
    if a == b:
        a, b = lower, min(upper, lower * 4 + 1e-4)
    fa, fb = f(a), f(b)
    for _ in range(max_expand):
        if fa * fb <= 0.0:
            return brent(f, a, b, tol=tol)
        if abs(fa) < abs(fb):
            a = max(lower, a / factor)
            fa = f(a)
        else:
            b = min(upper, b * factor)
            fb = f(b)
    # last-ditch Newton
    return newton(f, x0, lower=lower, upper=upper, tol=tol)


def halley(
    f: Callable[[float], float],
    f1: Callable[[float], float],
    f2: Callable[[float], float],
    x0: float,
    *,
    tol: float = 1e-12,
    maxiter: int = 30,
    lower: float | None = None,
    upper: float | None = None,
) -> float:
    x = float(x0)
    fx = 0.0
    for i in range(1, maxiter + 1):
        fx = f(x)
        if abs(fx) < tol:
            return x
        fp = f1(x)
        fpp = f2(x)
        denom = 2.0 * fp * fp - fx * fpp
        if abs(denom) < 1e-18:
            step = fx / fp if abs(fp) > 1e-18 else 0.0
        else:
            step = 2.0 * fx * fp / denom
        x_new = x - step
        if lower is not None:
            x_new = max(lower, x_new)
        if upper is not None:
            x_new = min(upper, x_new)
        x = x_new
    raise ConvergenceError("Halley failed to converge", iterations=maxiter, residual=fx)
