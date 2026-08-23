from argentum.instruments import CapFloor, CreditDefaultSwap, InterestRateSwap, Swaption, VanillaOption
from argentum.termstructures import HazardCurve, YieldCurve
from argentum.time import Date
from argentum.types import OptionType


def test_vanilla_option_analytic():
    opt = VanillaOption.european_call(100, Date(2027, 8, 23))
    res = opt.price(Date(2026, 8, 23), spot=100, rate=0.05, vol=0.2)
    assert res.npv > 0
    assert res.greeks is not None
    assert 0.5 < res.greeks.delta < 0.8
    iv = opt.implied_vol(Date(2026, 8, 23), res.npv, spot=100, rate=0.05)
    assert abs(iv - 0.2) < 1e-8


def test_swap_par_on_flat_curve():
    as_of = Date(2026, 8, 24)
    curve = YieldCurve.flat(as_of, 0.04)
    swap = InterestRateSwap.vanilla(as_of, "5Y", 0.04)
    # par rate near the flat zero (day-count / compounding basis residual)
    par = swap.par_rate(curve)
    assert abs(par - 0.04) < 0.003
    npv = swap.npv(curve)
    assert abs(npv) < 8_000  # 1mm notional; residual is day-count vs continuous zero


def test_swaption_positive():
    as_of = Date(2026, 8, 24)
    curve = YieldCurve.flat(as_of, 0.03)
    sw = Swaption(Date(2027, 8, 24), Date(2032, 8, 24), strike=0.03, notional=1_000_000)
    npv = sw.npv(as_of, curve, curve, vol=0.3)
    assert npv > 0


def test_cap_positive():
    as_of = Date(2026, 8, 24)
    curve = YieldCurve.flat(as_of, 0.03)
    cap = CapFloor(Date(2026, 11, 24), Date(2028, 8, 24), strike=0.03, is_cap=True, notional=1_000_000)
    npv = cap.npv(as_of, curve, curve, vol=0.4)
    assert npv > 0


def test_cds_par_spread_scales_with_hazard():
    as_of = Date(2026, 8, 24)
    disc = YieldCurve.flat(as_of, 0.02)
    h_lo = HazardCurve.flat(as_of, 0.01, recovery=0.4)
    h_hi = HazardCurve.flat(as_of, 0.02, recovery=0.4)
    cds = CreditDefaultSwap(Date(2026, 9, 20), Date(2031, 9, 20), coupon=0.01)
    s_lo = cds.par_spread(disc, h_lo)
    s_hi = cds.par_spread(disc, h_hi)
    assert s_hi > s_lo > 0
    # rough: spread ≈ (1-R) λ = 0.6 * 0.01 = 60bp
    assert abs(s_lo - 0.006) < 0.002
