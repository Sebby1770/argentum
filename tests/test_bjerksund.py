import pytest

from argentum import price
from argentum.models.binomial import crr_price
from argentum.models.bjerksund_stensland import bjerksund_stensland

CASES = [
    (100.0, 100.0, 0.05, 0.0, 0.2, 1.0),
    (100.0, 100.0, 0.05, 0.03, 0.2, 1.0),
    (42.0, 40.0, 0.04, 0.08, 0.35, 0.75),
    (90.0, 100.0, 0.08, 0.12, 0.3, 0.5),
    (110.0, 100.0, 0.1, 0.1, 0.25, 0.25),
    (36.0, 40.0, 0.06, 0.0, 0.4, 2.0),
]


def test_1993_reproduces_haugs_worked_example():
    # Haug (2007) §3.1.4: S=42, X=40, T=0.75, r=0.04, b=-0.04, σ=0.35 -> 5.2704.
    assert bjerksund_stensland(42, 40, 0.04, 0.08, 0.35, 0.75, "call", version=1993) == pytest.approx(5.2704, abs=5e-5)


@pytest.mark.parametrize("args", CASES)
@pytest.mark.parametrize("kind", ["call", "put"])
def test_2002_is_a_tight_lower_bound_above_1993(args, kind):
    tree = crr_price(*args, 2001, kind, "american")
    v93 = bjerksund_stensland(*args, kind, version=1993)
    v02 = bjerksund_stensland(*args, kind)
    euro = price(*args, kind)
    assert euro - 1e-9 <= v93 <= v02 + 1e-9  # 2002's two-step trigger dominates 1993's flat one
    assert v02 <= tree + 2e-3  # an exercise-rule value cannot beat the optimal rule
    assert v02 >= tree - 0.015 * tree  # ...and gives up at most ~1.5% (ATM puts are the worst case)


def test_regression_atm_american_put_is_no_longer_overpriced():
    # 1.x returned 6.5535 here: the φ exponent used γ² for γ(γ-1), κ used 2(r-b)/σ²
    # for 2b/σ², and the trigger used q·T for b·T. The 2001-step tree says 6.0906.
    value = bjerksund_stensland(100, 100, 0.05, 0.0, 0.2, 1.0, "put")
    assert 5.98 < value < 6.0906


def test_no_early_exercise_cases_collapse_to_european():
    assert bjerksund_stensland(100, 100, 0.05, 0.0, 0.2, 1.0, "call") == pytest.approx(price(100, 100, 0.05, 0.0, 0.2, 1.0, "call"))
    assert bjerksund_stensland(100, 100, 0.0, 0.03, 0.2, 1.0, "put") == pytest.approx(price(100, 100, 0.0, 0.03, 0.2, 1.0, "put"))


def test_deep_itm_exercises_immediately_and_bad_version_rejected():
    assert bjerksund_stensland(100, 80, 0.03, 0.07, 0.15, 3.0, "call") == pytest.approx(20.0)
    with pytest.raises(ValueError):
        bjerksund_stensland(100, 100, 0.05, 0.02, 0.2, 1.0, "call", version=1999)
