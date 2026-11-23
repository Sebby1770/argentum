import numpy as np
import pytest

from argentum.calibration import levenberg_marquardt
from argentum.errors import ConvergenceError


def test_lm_converges_on_linear_least_squares():
    result = levenberg_marquardt(lambda x: np.array([x[0] - 3.0, 2.0 * (x[1] + 2.0)]), np.array([0.0, 0.0]))
    assert result == pytest.approx([3.0, -2.0], abs=1e-8)


def test_lm_raises_when_iteration_budget_is_exhausted():
    with pytest.raises(ConvergenceError, match="maxiter") as caught:
        levenberg_marquardt(lambda x: np.array([np.exp(x[0]) - 10.0]), np.array([0.0]), maxiter=1)
    assert caught.value.iterations == 1
    assert caught.value.residual is not None


def test_lm_rejects_non_finite_residuals():
    with pytest.raises(ConvergenceError, match="NaN or infinity"):
        levenberg_marquardt(lambda _x: np.array([np.nan]), np.array([0.0]))
