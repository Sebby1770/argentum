"""Black–Scholes identities, published values, and implied-vol round-trips."""

import math

from argentum.math.special import norm_cdf, norm_inv, norm_pdf
from argentum.models.black_scholes import digital_cash, greeks, implied_vol, price
from argentum.models.binomial import crr_price, leisen_reimer_price
from argentum.types import OptionType

# S=100, K=100, r=0.05, q=0, σ=0.2, T=1
ATM = dict(spot=100.0, strike=100.0, rate=0.05, div=0.0, vol=0.20, texp=1.0)


def test_norm_cdf_known_values():
    assert abs(norm_cdf(0.0) - 0.5) < 1e-15
    assert abs(norm_cdf(1.0) - 0.8413447460685429) < 1e-12
    assert abs(norm_cdf(-1.0) - 0.15865525393145705) < 1e-12


def test_norm_inv_roundtrip():
    for p in (1e-9, 0.01, 0.5, 0.99, 1 - 1e-9):
        x = norm_inv(p)
        assert abs(norm_cdf(x) - p) < 1e-12


def test_atm_call_haug_style():
    call = price(**ATM, option_type=OptionType.CALL)
    # Independent evaluation: d1=0.35, d2=0.15
    d1, d2 = 0.35, 0.15
    expected = 100 * norm_cdf(d1) - 100 * math.exp(-0.05) * norm_cdf(d2)
    assert abs(call - expected) < 1e-10
    assert abs(call - 10.450583572185565) < 1e-9


def test_put_call_parity():
    call = price(**ATM, option_type=OptionType.CALL)
    put = price(**ATM, option_type=OptionType.PUT)
    rhs = ATM["spot"] * math.exp(-ATM["div"] * ATM["texp"]) - ATM["strike"] * math.exp(-ATM["rate"] * ATM["texp"])
    assert abs((call - put) - rhs) < 1e-12


def test_greeks_finite_difference():
    g = greeks(**ATM, option_type=OptionType.CALL)
    h = 1e-4
    p_up = price(spot=100 + h, **{k: v for k, v in ATM.items() if k != "spot"}, option_type=OptionType.CALL)
    p_dn = price(spot=100 - h, **{k: v for k, v in ATM.items() if k != "spot"}, option_type=OptionType.CALL)
    p0 = price(**ATM, option_type=OptionType.CALL)
    fd_delta = (p_up - p_dn) / (2 * h)
    fd_gamma = (p_up - 2 * p0 + p_dn) / (h * h)
    assert abs(g.delta - fd_delta) < 1e-6
    assert abs(g.gamma - fd_gamma) < 1e-5
    v_up = price(**{**ATM, "vol": 0.20 + h}, option_type=OptionType.CALL)
    fd_vega = (v_up - p0) / h
    assert abs(g.vega - fd_vega) < 1e-3


def test_implied_vol_roundtrip():
    for k in (80.0, 100.0, 120.0):
        for sig in (0.1, 0.2, 0.5):
            px = price(100, k, 0.03, 0.01, sig, 0.75, OptionType.CALL)
            iv = implied_vol(px, 100, k, 0.03, 0.01, 0.75, OptionType.CALL)
            assert abs(iv - sig) < 1e-10


def test_digital_plus_vanilla_decomposition():
    # Vanilla call = asset-or-nothing - K * cash-or-nothing
    from argentum.models.black_scholes import digital_asset

    van = price(**ATM, option_type=OptionType.CALL)
    aon = digital_asset(**ATM, option_type=OptionType.CALL)
    con = digital_cash(**ATM, option_type=OptionType.CALL, cash=ATM["strike"])
    assert abs(van - (aon - con)) < 1e-10


def test_crr_converges_to_bs():
    bs = price(**ATM, option_type=OptionType.CALL)
    tree = crr_price(**ATM, steps=801, option_type=OptionType.CALL)
    assert abs(tree - bs) < 0.02


def test_leisen_reimer_is_tighter():
    bs = price(**ATM, option_type=OptionType.CALL)
    lr = leisen_reimer_price(**ATM, steps=101, option_type=OptionType.CALL)
    assert abs(lr - bs) < 0.005


def test_pdf_integral_approx():
    # n(0) = 1/sqrt(2π)
    assert abs(norm_pdf(0.0) - 1.0 / math.sqrt(2 * math.pi)) < 1e-15
