
from argentum.instruments import Bond
from argentum.termstructures import YieldCurve
from argentum.time import Date
from argentum.types import Frequency


def test_semiannual_bond_closed_form():
    """6% coupon, 5% YTM, 10 years, 30/360, face 100, semi-annual.

    Price = 3 * (1 - 1.025^{-20}) / 0.025 + 100 / 1.025^{20}
    """
    issue = Date(2016, 8, 15)
    mat = Date(2026, 8, 15)
    as_of = Date(2016, 8, 15)
    bond = Bond.fixed(0.06, mat, issue=issue, frequency=Frequency.SEMIANNUAL, face=100.0)
    dirty = bond.dirty_price_from_ytm(as_of, 0.05)
    expected = 3.0 * (1.0 - 1.025 ** (-20)) / 0.025 + 100.0 / (1.025**20)
    assert abs(dirty - expected) < 0.02  # day-count vs exact 1/2-year
    assert dirty > 100.0  # premium bond


def test_ytm_roundtrip():
    issue = Date(2020, 1, 15)
    mat = Date(2030, 1, 15)
    as_of = Date(2020, 1, 15)
    bond = Bond.fixed(0.04, mat, issue=issue, face=100.0)
    y = 0.045
    dirty = bond.dirty_price_from_ytm(as_of, y)
    recovered = bond.ytm(as_of, dirty)
    assert abs(recovered - y) < 1e-10


def test_duration_positive_convexity_positive():
    issue = Date(2020, 1, 15)
    mat = Date(2030, 1, 15)
    as_of = Date(2020, 1, 15)
    bond = Bond.fixed(0.05, mat, issue=issue)
    y = 0.05
    mac = bond.macaulay_duration(as_of, y)
    mod = bond.modified_duration(as_of, y)
    conv = bond.convexity(as_of, y)
    assert 6.0 < mac < 10.0
    assert 0 < mod < mac
    assert conv > 0


def test_npv_on_flat_curve_matches_ytm_price_continuous():
    as_of = Date(2026, 8, 23)
    mat = Date(2031, 8, 23)
    bond = Bond.fixed(0.04, mat, as_of=as_of, frequency=Frequency.ANNUAL, face=100.0)
    curve = YieldCurve.flat(as_of, 0.04)
    npv = bond.npv(as_of, curve)
    # near par
    assert abs(npv - 100.0) < 1.5


def test_z_spread_zero_on_own_curve():
    as_of = Date(2026, 8, 23)
    mat = Date(2031, 8, 23)
    bond = Bond.fixed(0.04, mat, as_of=as_of, frequency=Frequency.ANNUAL, face=100.0)
    curve = YieldCurve.flat(as_of, 0.04)
    dirty = bond.npv(as_of, curve)
    zs = bond.z_spread(as_of, dirty, curve)
    assert abs(zs) < 1e-6
