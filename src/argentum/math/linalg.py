"""Small dense linear algebra used by finite-difference engines."""

from __future__ import annotations

import numpy as np

from argentum.errors import InputError


def thomas(sub: np.ndarray, diag: np.ndarray, sup: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Solve a tridiagonal system. ``sub[0]`` and ``sup[-1]`` are ignored."""
    n = diag.shape[0]
    if sub.shape[0] != n or sup.shape[0] != n or rhs.shape[0] != n:
        raise InputError("thomas: shape mismatch")
    ac = np.array(sub, dtype=np.float64, copy=True)
    bc = np.array(diag, dtype=np.float64, copy=True)
    cc = np.array(sup, dtype=np.float64, copy=True)
    dc = np.array(rhs, dtype=np.float64, copy=True)
    for i in range(1, n):
        if bc[i - 1] == 0.0:
            raise InputError("thomas: zero pivot")
        w = ac[i] / bc[i - 1]
        bc[i] -= w * cc[i - 1]
        dc[i] -= w * dc[i - 1]
    x = np.empty(n, dtype=np.float64)
    if bc[-1] == 0.0:
        raise InputError("thomas: zero pivot")
    x[-1] = dc[-1] / bc[-1]
    for i in range(n - 2, -1, -1):
        x[i] = (dc[i] - cc[i] * x[i + 1]) / bc[i]
    return x
