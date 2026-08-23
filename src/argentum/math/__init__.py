"""Numerical primitives: special functions, solvers, interpolation, QMC."""

from argentum.math.integration import gauss_legendre, simpson, tanh_sinh
from argentum.math.interpolation import cubic, linear, log_linear, make_interpolator, monotone_cubic
from argentum.math.linalg import thomas
from argentum.math.random import SobolEngine, sobol_normal
from argentum.math.solvers import brent, bracket_and_solve, halley, newton
from argentum.math.special import bivariate_cdf, black_d1_d2, norm_cdf, norm_inv, norm_pdf, norm_sf

__all__ = [
    "SobolEngine",
    "bivariate_cdf",
    "black_d1_d2",
    "bracket_and_solve",
    "brent",
    "cubic",
    "gauss_legendre",
    "halley",
    "linear",
    "log_linear",
    "make_interpolator",
    "monotone_cubic",
    "newton",
    "norm_cdf",
    "norm_inv",
    "norm_pdf",
    "norm_sf",
    "simpson",
    "sobol_normal",
    "tanh_sinh",
    "thomas",
]
