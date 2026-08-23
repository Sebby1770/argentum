from argentum.termstructures import DepositQuote, SwapQuote, YieldCurve, bootstrap_yield_curve
from argentum.time import TARGET, Date, Period
from argentum.types import Compounding


def test_flat_curve_df():
    as_of = Date(2026, 8, 23)
    curve = YieldCurve.flat(as_of, 0.05)
    t = curve.t(Date(2027, 8, 23))
    assert abs(curve.df(Date(2027, 8, 23)) - __import__("math").exp(-0.05 * t)) < 1e-12
    assert abs(curve.zero(Date(2027, 8, 23)) - 0.05) < 1e-10


def test_forward_telescopes():
    as_of = Date(2026, 1, 1)
    curve = YieldCurve.flat(as_of, 0.04)
    d1, d2 = Date(2026, 7, 1), Date(2027, 1, 1)
    f = curve.forward(d1, d2, simple=True)
    # simple forward from DF ratio
    tau = curve.t(d2) - curve.t(d1)
    expected = (curve.df(d1) / curve.df(d2) - 1.0) / tau
    assert abs(f - expected) < 1e-14


def test_bootstrap_deposits_and_par_swap():
    as_of = Date(2026, 8, 24)  # Monday
    deposits = [
        DepositQuote("3M", 0.04),
        DepositQuote("6M", 0.041),
    ]
    swaps = [
        SwapQuote("1Y", 0.042),
        SwapQuote("2Y", 0.043),
        SwapQuote("5Y", 0.045),
    ]
    curve = bootstrap_yield_curve(as_of, deposits=deposits, swaps=swaps, calendar=TARGET())
    from argentum.instruments import InterestRateSwap

    swap = InterestRateSwap.vanilla(as_of, "5Y", 0.045)
    par = swap.par_rate(curve)
    assert abs(par - 0.045) < 1.5e-4


def test_self_consistent_zeros():
    as_of = Date(2026, 1, 2)
    dates = [Date(2027, 1, 4), Date(2028, 1, 3), Date(2031, 1, 2)]
    zeros = [0.03, 0.035, 0.04]
    curve = YieldCurve.from_zeros(as_of, dates, zeros, compounding=Compounding.CONTINUOUS)
    for d, z in zip(dates, zeros):
        assert abs(curve.zero(d) - z) < 5e-4  # interpolation between pillars is exact at knots
