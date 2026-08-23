"""5y vanilla swap on a bootstrapped curve: par, NPV, DV01."""

from argentum import Date, DepositQuote, InterestRateSwap, SwapQuote, bootstrap_yield_curve
from argentum.time import TARGET

as_of = Date(2026, 8, 24)
curve = bootstrap_yield_curve(
    as_of,
    deposits=[DepositQuote("3M", 0.032), DepositQuote("6M", 0.033)],
    swaps=[
        SwapQuote("1Y", 0.034),
        SwapQuote("2Y", 0.035),
        SwapQuote("5Y", 0.037),
        SwapQuote("10Y", 0.039),
    ],
    calendar=TARGET(),
)
swap = InterestRateSwap.vanilla(as_of, "5Y", 0.037, notional=10_000_000)
print(f"par   {swap.par_rate(curve):.6%}")
print(f"npv   {swap.npv(curve):,.2f}")
print(f"dv01  {swap.dv01(curve):,.2f}")
