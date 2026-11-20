import math

import numpy as np
import pytest

from argentum import InputError, price
from argentum.models.charfn import (
    BatesCF,
    BlackScholesCF,
    HestonCF,
    MertonJumpCF,
    NIGCF,
    VarianceGammaCF,
    cos_price,
    cumulants,
    model_smile,
)
from argentum.models.heston import HestonParams, heston_price

FO_HESTON = HestonCF(kappa=1.5768, theta=0.0398, sigma=0.5751, rho=-0.5711, v0=0.0175)


@pytest.mark.parametrize("strike", [40.0, 80.0, 100.0, 125.0, 250.0])
@pytest.mark.parametrize("kind", ["call", "put"])
def test_black_scholes_cf_reproduces_the_analytic_price(strike, kind):
    got = cos_price(BlackScholesCF(0.25), 100.0, strike, 0.04, 0.015, 1.3, kind)
    assert got == pytest.approx(price(100.0, strike, 0.04, 0.015, 0.25, 1.3, kind), abs=1e-11)


def test_heston_matches_fang_oosterlee_reference():
    # Fang & Oosterlee (2008), Table 4: reference value 5.785155435.
    assert cos_price(FO_HESTON, 100.0, 100.0, 0.0, 0.0, 1.0, "call") == pytest.approx(5.785155435, abs=2e-9)
    legacy_api = heston_price(100.0, 100.0, 0.0, 0.0, 1.0, HestonParams(1.5768, 0.0398, 0.5751, -0.5711, 0.0175))
    assert legacy_api == pytest.approx(5.785155435, abs=2e-9)


def test_variance_gamma_matches_fang_oosterlee_reference():
    # Fang & Oosterlee (2008), VG with K=90, r=0.1, σ=0.12, θ=-0.14, ν=0.2, T=1.
    vg = VarianceGammaCF(sigma=0.12, nu=0.2, theta=-0.14)
    assert cos_price(vg, 100.0, 90.0, 0.1, 0.0, 1.0, "call") == pytest.approx(19.099354724, abs=1e-8)
    # T=0.1 has a kinked density: COS converges algebraically, so ask for more terms.
    short = cos_price(vg, 100.0, 90.0, 0.1, 0.0, 0.1, "call", n_terms=2048)
    assert short == pytest.approx(10.993703187, abs=5e-7)


def test_merton_matches_the_poisson_series_of_black_scholes_prices():
    s, lam, mu, dl, rate, div, texp = 0.15, 0.6, -0.12, 0.18, 0.05, 0.02, 0.75
    strikes = np.array([70.0, 100.0, 130.0])
    kbar = math.exp(mu + 0.5 * dl * dl) - 1.0
    series = np.zeros_like(strikes)
    for n in range(80):
        vol_n = math.sqrt(s * s + n * dl * dl / texp)
        rate_n = rate - lam * kbar + n * (mu + 0.5 * dl * dl) / texp
        weight = math.exp(-lam * (1 + kbar) * texp) * (lam * (1 + kbar) * texp) ** n / math.factorial(n)
        series += weight * price(100.0, strikes, rate_n, div, vol_n, texp, "call")
    got = cos_price(MertonJumpCF(s, lam, mu, dl), 100.0, strikes, rate, div, texp, "call")
    np.testing.assert_allclose(got, series, atol=1e-10)


def test_nig_agrees_with_a_seeded_monte_carlo():
    a, b, d, texp, rate = 15.0, -5.0, 0.5, 0.5, 0.03
    gamma = math.sqrt(a * a - b * b)
    omega = d * (math.sqrt(a * a - (b + 1) ** 2) - gamma)
    rng = np.random.default_rng(7)
    n = 400_000
    z = rng.wald(d * texp / gamma, (d * texp) ** 2, n)
    x = omega * texp + b * z + np.sqrt(z) * rng.standard_normal(n)
    fwd = 100.0 * math.exp(rate * texp)
    pay = np.maximum(fwd * np.exp(x) - 100.0, 0.0) * math.exp(-rate * texp)
    se = pay.std() / math.sqrt(n)
    got = cos_price(NIGCF(a, b, d), 100.0, 100.0, rate, 0.0, texp, "call")
    assert abs(got - pay.mean()) < 4.0 * se


def test_bates_without_jumps_is_heston_and_jumps_lift_the_wings():
    plain = cos_price(FO_HESTON, 100.0, [80.0, 100.0], 0.02, 0.0, 1.0, "put")
    no_jumps = cos_price(BatesCF(FO_HESTON, lam=0.0, mu_j=-0.1, delta_j=0.2), 100.0, [80.0, 100.0], 0.02, 0.0, 1.0, "put")
    np.testing.assert_allclose(no_jumps, plain, atol=1e-12)
    crashy = cos_price(BatesCF(FO_HESTON, lam=0.5, mu_j=-0.15, delta_j=0.1), 100.0, 80.0, 0.02, 0.0, 1.0, "put")
    assert crashy > plain[0]


@pytest.mark.parametrize(
    "model",
    [
        BlackScholesCF(0.3),
        MertonJumpCF(0.2, 0.4, -0.05, 0.1),
        VarianceGammaCF(0.2, 0.3, -0.1),
        NIGCF(12.0, -3.0, 0.4),
        FO_HESTON,
        BatesCF(FO_HESTON, 0.3, -0.08, 0.12),
    ],
    ids=lambda m: m.name,
)
def test_every_model_is_a_martingale_and_satisfies_parity(model):
    phi_at_minus_i = model.cf(np.array([-1j]), 0.8)[0]
    assert abs(phi_at_minus_i - 1.0) < 1e-10  # E[e^{X_T}] = 1
    strikes = np.array([60.0, 95.0, 100.0, 105.0, 150.0])
    calls = cos_price(model, 100.0, strikes, 0.03, 0.01, 0.8, "call")
    puts = cos_price(model, 100.0, strikes, 0.03, 0.01, 0.8, "put")
    parity = 100.0 * math.exp(-0.01 * 0.8) - strikes * math.exp(-0.03 * 0.8)
    np.testing.assert_allclose(calls - puts, parity, atol=1e-9)
    assert np.all(np.diff(calls) < 0.0) and np.all(np.diff(puts) > 0.0)
    c1, c2, c4 = cumulants(model, 0.8)
    assert c2 > 0.0 and c4 >= 0.0


def test_model_smile_shows_the_negative_skew_of_downward_jumps():
    smile = model_smile(MertonJumpCF(0.15, 0.8, -0.1, 0.1), 100.0, [80.0, 100.0, 120.0], 0.02, 0.0, 0.5)
    vols = smile["implied_vol"]
    assert np.all(np.isfinite(vols))
    assert vols[0] > vols[1]


def test_scalar_and_array_strikes_and_expiry_edge():
    assert isinstance(cos_price(FO_HESTON, 100.0, 100.0, 0.0, 0.0, 1.0), float)
    assert cos_price(FO_HESTON, 100.0, [90.0, 110.0], 0.0, 0.0, 0.0, "call").tolist() == [10.0, 0.0]


def test_invalid_parameters_are_rejected():
    with pytest.raises(InputError):
        VarianceGammaCF(sigma=0.2, nu=5.0, theta=0.5)
    with pytest.raises(InputError):
        NIGCF(alpha=1.0, beta=0.5, delta=0.2)
    with pytest.raises(InputError):
        HestonCF(1.0, 0.04, 0.3, -1.5, 0.04)
    with pytest.raises(InputError):
        cos_price(BlackScholesCF(0.2), 100.0, -5.0, 0.0, 0.0, 1.0)
