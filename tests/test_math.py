import math

import numpy as np

from argentum.math import brent, cubic, linear, log_linear, monotone_cubic, newton, simpson, thomas


def test_newton_sqrt():
    root = newton(lambda x: x * x - 2.0, 1.0, fprime=lambda x: 2 * x)
    assert abs(root - math.sqrt(2)) < 1e-12


def test_brent_cosine():
    root = brent(math.cos, 1.0, 2.0)
    assert abs(root - math.pi / 2) < 1e-12


def test_linear_interp():
    f = linear([0.0, 1.0, 2.0], [0.0, 2.0, 2.0])
    assert abs(f(0.5) - 1.0) < 1e-15
    assert abs(f(1.5) - 2.0) < 1e-15


def test_log_linear_positive():
    f = log_linear([1.0, 2.0], [math.e, math.e**2])
    assert abs(f(1.5) - math.exp(1.5)) < 1e-12


def test_monotone_cubic_does_not_overshoot():
    x = [0.0, 1.0, 2.0, 3.0]
    y = [0.0, 0.0, 1.0, 1.0]
    f = monotone_cubic(x, y)
    # Hyman should keep the interpolant between neighbouring values on a step
    for t in (0.25, 0.75):
        assert -1e-8 <= f(t) <= 1e-2 + 1e-8


def test_cubic_reproduces_knots():
    x = [0.0, 1.0, 2.0, 3.0]
    y = [0.0, 1.0, 0.0, 1.0]
    f = cubic(x, y)
    for xi, yi in zip(x, y):
        assert abs(f(xi) - yi) < 1e-10


def test_thomas_identity():
    n = 5
    sub = np.zeros(n)
    diag = np.ones(n)
    sup = np.zeros(n)
    rhs = np.arange(n, dtype=float)
    x = thomas(sub, diag, sup, rhs)
    np.testing.assert_allclose(x, rhs)


def test_simpson_quadratic():
    val = simpson(lambda x: x * x, 0.0, 1.0, n=20)
    assert abs(val - 1.0 / 3.0) < 1e-6
