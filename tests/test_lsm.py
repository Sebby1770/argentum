import math

import numpy as np
import pytest

from argentum import InputError, price
from argentum.engines.lsm import gbm_paths, lsm_american, lsm_price
from argentum.models.binomial import crr_price

# Longstaff & Schwartz (2001), Table 1: K=40, r=0.06, 50 exercise dates per year.
PAPER_ROWS = [(36.0, 0.2, 1.0), (36.0, 0.4, 1.0), (40.0, 0.2, 1.0), (44.0, 0.4, 2.0)]


@pytest.mark.parametrize("spot,vol,texp", PAPER_ROWS)
def test_american_put_brackets_the_tree_value(spot, vol, texp):
    res = lsm_american(spot, 40.0, 0.06, 0.0, vol, texp, "put", n_paths=60_000, n_steps=int(50 * texp))
    tree = crr_price(spot, 40.0, 0.06, 0.0, vol, texp, 1501, "put", "american")
    # Out-of-sample LSM is a lower bound for the (continuously exercisable) American value...
    assert res.npv <= tree + 3.0 * res.std_error
    # ...and a tight one: a Bermudan with 50 dates/yr gives up only a few cents.
    assert res.npv >= tree - 0.05 - 3.0 * res.std_error
    assert res.early_exercise_premium > 0.2
    assert res.std_error < 0.03


def test_no_early_exercise_for_a_call_without_dividends():
    res = lsm_american(100.0, 100.0, 0.05, 0.0, 0.2, 1.0, "call", n_paths=60_000)
    assert abs(res.npv - price(100.0, 100.0, 0.05, 0.0, 0.2, 1.0, "call")) < 4.0 * res.std_error + 1e-9


def test_dividends_create_call_early_exercise_value():
    res = lsm_american(100.0, 90.0, 0.03, 0.08, 0.25, 2.0, "call", n_paths=60_000, n_steps=40)
    euro = price(100.0, 90.0, 0.03, 0.08, 0.25, 2.0, "call")
    assert res.npv > euro + 5.0 * res.std_error


def test_in_sample_estimate_is_reported_and_close():
    res = lsm_american(36.0, 40.0, 0.06, 0.0, 0.2, 1.0, "put", n_paths=40_000)
    assert abs(res.in_sample - res.npv) < 0.05


def test_deep_itm_put_is_at_least_intrinsic_and_degenerate_inputs():
    deep = lsm_american(10.0, 40.0, 0.06, 0.0, 0.2, 1.0, "put", n_paths=4_000, n_steps=10)
    assert deep.npv >= 30.0 - 1e-12
    flat = lsm_american(36.0, 40.0, 0.06, 0.0, 0.0, 1.0, "put")
    assert flat.npv == pytest.approx(4.0)  # zero vol: exercise now beats a discounted 4
    expired = lsm_american(36.0, 40.0, 0.06, 0.0, 0.2, 0.0, "put")
    assert expired.npv == pytest.approx(4.0)


def test_lsm_price_accepts_custom_paths_and_validates():
    rng = np.random.default_rng(3)
    fit = gbm_paths(36.0, 0.06, 0.0, 0.2, 1.0, 20_000, 25, rng)
    test = gbm_paths(36.0, 0.06, 0.0, 0.2, 1.0, 20_000, 25, rng)
    lower, se, in_sample = lsm_price(
        fit, test, lambda s: np.maximum(40.0 - s, 0.0), math.exp(-0.06 / 25), scale=40.0
    )
    assert 4.3 < lower < 4.55 and se > 0.0 and in_sample > 4.3
    with pytest.raises(InputError):
        lsm_price(fit, test[:, :5], lambda s: s, 1.0)
    with pytest.raises(InputError):
        lsm_american(36.0, 40.0, 0.06, 0.0, 0.2, 1.0, n_paths=10)
