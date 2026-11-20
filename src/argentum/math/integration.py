"""Quadrature: Gauss–Legendre, tanh-sinh, and Simpson."""

from __future__ import annotations

import math
from collections.abc import Callable


from argentum.errors import InputError


# Gauss-Legendre nodes/weights on [-1, 1] for n = 8, 16, 32 (computed via Golub-Welsch offline).
_GL: dict[int, tuple[tuple[float, ...], tuple[float, ...]]] = {
    8: (
        (
            -0.9602898564975363,
            -0.7966664774136267,
            -0.5255324099163290,
            -0.1834346424956498,
            0.1834346424956498,
            0.5255324099163290,
            0.7966664774136267,
            0.9602898564975363,
        ),
        (
            0.1012285362903763,
            0.2223810344533745,
            0.3137066458778873,
            0.3626837833783620,
            0.3626837833783620,
            0.3137066458778873,
            0.2223810344533745,
            0.1012285362903763,
        ),
    ),
    16: (
        (
            -0.9894009349916499,
            -0.9445750230732326,
            -0.8656312023878318,
            -0.7554044083550030,
            -0.6178762444026438,
            -0.4580167776572274,
            -0.2816035507792589,
            -0.0950125098376374,
            0.0950125098376374,
            0.2816035507792589,
            0.4580167776572274,
            0.6178762444026438,
            0.7554044083550030,
            0.8656312023878318,
            0.9445750230732326,
            0.9894009349916499,
        ),
        (
            0.0271524594117541,
            0.0622535239386479,
            0.0951585116824928,
            0.1246289712555339,
            0.1495959888165768,
            0.1691565193950025,
            0.1826034150449236,
            0.1894506104550685,
            0.1894506104550685,
            0.1826034150449236,
            0.1691565193950025,
            0.1495959888165768,
            0.1246289712555339,
            0.0951585116824928,
            0.0622535239386479,
            0.0271524594117541,
        ),
    ),
}


def gauss_legendre(f: Callable[[float], float], a: float, b: float, n: int = 16) -> float:
    if n not in _GL:
        raise InputError(f"gauss_legendre n must be one of {sorted(_GL)}")
    nodes, weights = _GL[n]
    mid = 0.5 * (a + b)
    half = 0.5 * (b - a)
    total = 0.0
    for x, w in zip(nodes, weights):
        total += w * f(mid + half * x)
    return total * half


def simpson(f: Callable[[float], float], a: float, b: float, n: int = 200) -> float:
    if n % 2:
        n += 1
    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        x = a + i * h
        total += 4.0 * f(x) if i % 2 else 2.0 * f(x)
    return total * h / 3.0


def tanh_sinh(f: Callable[[float], float], a: float, b: float, n: int = 40) -> float:
    """Tanh-sinh (double exponential) on a finite interval."""
    # map [a,b] to [-1,1]
    half = 0.5 * (b - a)
    mid = 0.5 * (a + b)
    h = 3.0 / n
    total = 0.0
    for k in range(-n, n + 1):
        t = k * h
        # x = tanh(π/2 sinh t)
        sinh = math.sinh(t)
        cosh = math.cosh(t)
        arg = (math.pi / 2.0) * sinh
        th = math.tanh(arg)
        # dx/dt
        sech2 = 1.0 / (math.cosh(arg) ** 2)
        w = (math.pi / 2.0) * cosh * sech2
        x = mid + half * th
        total += w * f(x)
    return total * half * h
