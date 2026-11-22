import math

import numpy as np
import pytest

from argentum import InputError, OptionType, greeks, implied_vol, price
from argentum.models.vectorized import chain, greeks_array, implied_vol_array, price_array
from argentum.types import Greeks, require_non_negative, require_positive

GRID = [
    (s, k, r, q, v, t, typ)
    for s in (100.0,)
    for k in (40.0, 80.0, 100.0, 125.0, 300.0)
    for r in (-0.01, 0.05)
    for q in (0.0, 0.03)
    for v in (0.05, 0.2, 1.5)
    for t in (1 / 365, 0.5, 10.0)
    for typ in ("call", "put")
]


def test_price_array_matches_scalar_engine_everywhere():
    cols = list(zip(*GRID))
    got = price_array(*[np.array(c) for c in cols[:6]], np.array(cols[6]))
    want = np.array([price(*row) for row in GRID])
    np.testing.assert_allclose(got, want, rtol=1e-12, atol=1e-12)


def test_scalar_price_now_really_accepts_arrays():
    strikes = np.array([90.0, 100.0, 110.0])
    got = price(100.0, strikes, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    assert isinstance(got, np.ndarray) and got.shape == (3,)
    assert got[1] == pytest.approx(10.450583572185565, abs=1e-12)


def test_zero_variance_and_expiry_limits():
    got = price_array(100.0, [90.0, 110.0], 0.05, 0.0, 0.0, [1.0, 0.0], ["call", "put"])
    assert got[0] == pytest.approx(price(100, 90, 0.05, 0.0, 0.0, 1.0, "call"))
    assert got[1] == pytest.approx(10.0)


def test_greeks_array_matches_scalar_greeks():
    for s, k, r, q, v, t, typ in GRID[::7]:
        g = greeks(s, k, r, q, v, t, typ)
        a = greeks_array(s, k, r, q, v, t, typ)
        for name in ("delta", "gamma", "vega", "theta", "rho", "vanna", "volga"):
            assert float(a[name]) == pytest.approx(getattr(g, name), rel=1e-9, abs=1e-12), name


def test_implied_vol_array_round_trips_a_wide_grid():
    cols = list(zip(*GRID))
    vols = np.array(cols[4])
    prices = price_array(*[np.array(c) for c in cols[:6]], np.array(cols[6]))
    got = implied_vol_array(prices, *[np.array(c) for c in cols[:4]], np.array(cols[5]), np.array(cols[6]), errors="nan")
    # Quotes whose time value underflows carry no vol information; skip those.
    tv = prices - price_array(*[np.array(c) for c in cols[:4]], 0.0, np.array(cols[5]), np.array(cols[6]))
    informative = tv > 1e-8 * np.array(cols[0])
    assert informative.sum() > 0.6 * len(GRID)
    np.testing.assert_allclose(got[informative], vols[informative], rtol=1e-7)


def test_implied_vol_array_errors_modes():
    with pytest.raises(InputError):
        implied_vol_array([1.0, 500.0], 100.0, 100.0, 0.0, 0.0, 1.0)
    out = implied_vol_array([price(100, 100, 0.0, 0.0, 0.3, 1.0), 500.0], 100.0, 100.0, 0.0, 0.0, 1.0, errors="nan")
    assert out[0] == pytest.approx(0.3, abs=1e-10) and math.isnan(out[1])


def test_chain_shape_and_put_call_parity():
    out_c = chain(100.0, [80, 100, 120], [0.25, 1.0], 0.03, 0.01, 0.25, "call")
    out_p = chain(100.0, [80, 100, 120], [0.25, 1.0], 0.03, 0.01, 0.25, "put")
    assert out_c["price"].shape == (2, 3)
    k, t = out_c["strike"], out_c["texp"]
    parity = 100.0 * np.exp(-0.01 * t) - k * np.exp(-0.03 * t)
    np.testing.assert_allclose(out_c["price"] - out_p["price"], parity, atol=1e-10)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "x"])
def test_validators_reject_non_finite(bad):
    with pytest.raises(InputError):
        require_non_negative("vol", bad)
    with pytest.raises(InputError):
        require_positive("spot", bad)
    with pytest.raises(InputError):
        price_array(100.0, 100.0, 0.0, 0.0, bad if bad != "x" else float("nan"), 1.0)


def test_scalar_engine_rejects_nan_vol_instead_of_returning_nan():
    with pytest.raises(InputError):
        price(100, 100, 0.05, 0.0, float("nan"), 1.0)
    with pytest.raises(InputError):
        implied_vol(10.0, 100, 100, 0.05, 0.0, float("inf"))


def test_theta_per_day_is_year_theta_over_365():
    g = greeks(100, 100, 0.05, 0.0, 0.2, 1.0)
    assert isinstance(g, Greeks)
    assert g.theta_per_day == pytest.approx(g.theta / 365.0)
    # The per-year theta is -dV/dT: check against a one-day bump.
    bumped = price(100, 100, 0.05, 0.0, 0.2, 1.0 - 1 / 365)
    assert (bumped - price(100, 100, 0.05, 0.0, 0.2, 1.0)) == pytest.approx(g.theta_per_day, rel=2e-3)


@pytest.mark.parametrize("field", ["vol", "texp", "spot", "rate"])
@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "abc"])
def test_studio_rejects_non_finite_query_values(field, raw):
    from argentum.studio import vanilla_payload

    with pytest.raises(InputError):
        vanilla_payload({field: raw})


def test_expired_quote_at_intrinsic_has_zero_vol_not_the_seed():
    out = implied_vol_array([10.0, 0.0], [110.0, 90.0], 100.0, 0.0, 0.0, 0.0, "call", errors="nan")
    assert out.tolist() == [0.0, 0.0]


def test_option_type_enum_members_broadcast():
    got = price_array(100.0, [100.0, 100.0], 0.0, 0.0, 0.2, 1.0, [OptionType.CALL, OptionType.PUT])
    np.testing.assert_allclose(got, [price(100, 100, 0, 0, 0.2, 1, "call"), price(100, 100, 0, 0, 0.2, 1, "put")])
    with pytest.raises(InputError):
        price_array(100.0, 100.0, 0.0, 0.0, 0.2, 1.0, np.array([None], dtype=object))
