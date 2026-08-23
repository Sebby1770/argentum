"""Low-discrepancy Sobol' sequences and inverse-normal mapping.

Direction numbers are Joe–Kuo (up to 32 dimensions). Combined with
``norm_inv`` this is the standard path generator for QMC option pricing.
"""

from __future__ import annotations

import numpy as np

from argentum.errors import InputError
from argentum.math.special import norm_inv

# (s, a, m1..ms) Joe-Kuo d=1..32. d=1 is the van der Corput base-2 sequence.
# Source: https://web.maths.unsw.edu.au/~fkuo/sobol/ (new-joe-kuo-6.21201)
_JOE_KUO: list[tuple[int, int, tuple[int, ...]]] = [
    (0, 0, ()),  # dummy dim 0
    (1, 0, (1,)),
    (2, 1, (1, 3)),
    (3, 1, (1, 3, 1)),
    (3, 2, (1, 1, 1)),
    (4, 1, (1, 1, 3, 3)),
    (4, 4, (1, 3, 5, 13)),
    (5, 2, (1, 1, 5, 5, 17)),
    (5, 4, (1, 1, 5, 5, 5)),
    (5, 7, (1, 1, 7, 11, 19)),
    (5, 11, (1, 1, 5, 1, 1)),
    (5, 13, (1, 1, 1, 3, 11)),
    (5, 14, (1, 3, 5, 5, 31)),
    (6, 1, (1, 3, 3, 9, 7, 49)),
    (6, 13, (1, 1, 1, 15, 21, 21)),
    (6, 16, (1, 3, 1, 13, 27, 49)),
    (6, 19, (1, 1, 1, 15, 7, 5)),
    (6, 22, (1, 3, 1, 15, 13, 25)),
    (6, 25, (1, 1, 5, 5, 19, 61)),
    (7, 1, (1, 3, 7, 11, 23, 15, 103)),
    (7, 4, (1, 3, 7, 13, 13, 15, 69)),
    (7, 7, (1, 1, 3, 13, 7, 35, 63)),
    (7, 8, (1, 3, 1, 3, 5, 45, 61)),
    (7, 14, (1, 3, 1, 21, 1, 47, 9)),
    (7, 19, (1, 3, 5, 3, 29, 15, 51)),
    (7, 21, (1, 3, 1, 1, 1, 33, 73)),
    (7, 28, (1, 1, 7, 15, 29, 27, 85)),
    (8, 1, (1, 1, 3, 1, 23, 13, 37, 89)),
    (8, 4, (1, 1, 5, 21, 1, 47, 27, 157)),
    (8, 5, (1, 1, 3, 15, 1, 7, 63, 101)),
    (8, 9, (1, 3, 3, 11, 23, 5, 53, 173)),
    (8, 12, (1, 1, 7, 13, 11, 1, 15, 45)),
    (8, 16, (1, 3, 5, 1, 9, 7, 63, 101)),
]


def _direction_numbers(dim: int, bits: int = 32) -> np.ndarray:
    if not 1 <= dim <= 32:
        raise InputError("Sobol dimension must be in 1..32")
    v = np.zeros((dim, bits), dtype=np.uint32)
    # dim 0: v_{0,j} = 1 << (31-j)
    for j in range(bits):
        v[0, j] = np.uint32(1 << (bits - 1 - j))
    for d in range(1, dim):
        s, a, m = _JOE_KUO[d + 1] if d + 1 < len(_JOE_KUO) else _JOE_KUO[-1]
        # pad m to s
        mm = list(m) + [1] * max(0, s - len(m))
        for j in range(s):
            v[d, j] = np.uint32(mm[j] << (bits - 1 - j))
        for j in range(s, bits):
            v[d, j] = v[d, j - s]
            bits_a = a
            for k in range(1, s):
                if bits_a & (1 << (s - 1 - k)):
                    v[d, j] ^= v[d, j - k]
            v[d, j] ^= v[d, j - s] >> np.uint32(s)
    return v


class SobolEngine:
    """Joe–Kuo Sobol' generator. Skip 0th point (the origin)."""

    def __init__(self, dimension: int, *, scramble: bool = False, seed: int | None = None) -> None:
        self.dimension = int(dimension)
        self._v = _direction_numbers(self.dimension)
        self._x = np.zeros(self.dimension, dtype=np.uint32)
        self._n = 0
        self._scramble = None
        if scramble:
            rng = np.random.default_rng(seed)
            self._scramble = rng.integers(0, 2**32, size=self.dimension, dtype=np.uint32)

    def reset(self) -> None:
        self._x[:] = 0
        self._n = 0

    def random(self, n: int) -> np.ndarray:
        out = np.empty((n, self.dimension), dtype=np.float64)
        bits = 32
        scale = 2.0 ** (-bits)
        for i in range(n):
            self._n += 1
            c = _ctz(self._n)
            self._x ^= self._v[:, c]
            vals = self._x.copy()
            if self._scramble is not None:
                vals ^= self._scramble
            out[i] = vals.astype(np.float64) * scale
        return np.clip(out, 1e-12, 1.0 - 1e-12)


def _ctz(n: int) -> int:
    """Count trailing zeros of n (n >= 1)."""
    c = 0
    while n & 1 == 0:
        n >>= 1
        c += 1
    return c


def sobol_normal(n_paths: int, n_steps: int, *, scramble: bool = False, seed: int | None = 0) -> np.ndarray:
    """Shape ``(n_paths, n_steps)`` standard normals via Sobol + inverse CDF."""
    if n_steps > 32:
        raise InputError("sobol_normal supports at most 32 steps (Joe–Kuo table)")
    engine = SobolEngine(n_steps, scramble=scramble, seed=seed)
    u = engine.random(n_paths)
    # vectorized inverse via Python loop over unique? use list comp — n_steps small
    inv = np.vectorize(norm_inv, otypes=[float])
    return inv(u)
