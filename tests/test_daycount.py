"""Published day-count year fractions (ISDA 2006 examples)."""

from argentum.time import Date, DayCount, easter_gregorian


def test_act_365f():
    yf = DayCount.ACT_365F.year_fraction(Date(2007, 12, 28), Date(2008, 2, 28))
    assert abs(yf - 62 / 365.0) < 1e-15


def test_act_360():
    yf = DayCount.ACT_360.year_fraction(Date(2007, 12, 28), Date(2008, 2, 28))
    assert abs(yf - 62 / 360.0) < 1e-15


def test_act_act_isda_cross_leap():
    # ISDA example: 2003-11-01 to 2004-05-01
    yf = DayCount.ACT_ACT_ISDA.year_fraction(Date(2003, 11, 1), Date(2004, 5, 1))
    expected = 61 / 365.0 + 121 / 366.0
    assert abs(yf - expected) < 1e-14


def test_thirty_360_full_year():
    yf = DayCount.THIRTY_360_BOND.year_fraction(Date(2020, 1, 15), Date(2021, 1, 15))
    assert abs(yf - 1.0) < 1e-15


def test_thirty_e_360():
    yf = DayCount.THIRTY_E_360.year_fraction(Date(2007, 1, 31), Date(2007, 2, 28))
    # D1=30, D2=28 → (0*360 + 30*(2-1) + (28-30))/360 = 28/360
    assert abs(yf - 28 / 360.0) < 1e-15


def test_signed_and_zero():
    a, b = Date(2020, 1, 1), Date(2020, 7, 1)
    assert DayCount.ACT_365F.year_fraction(a, a) == 0.0
    assert abs(DayCount.ACT_365F.year_fraction(a, b) + DayCount.ACT_365F.year_fraction(b, a)) < 1e-15


def test_easter_2026():
    assert easter_gregorian(2026).isoformat() == "2026-04-05"


def test_easter_2024():
    assert easter_gregorian(2024).isoformat() == "2024-03-31"
