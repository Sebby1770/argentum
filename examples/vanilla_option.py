"""ATM European call: price, greeks, implied vol round-trip."""

from argentum import Date, OptionType, VanillaOption, greeks, implied_vol, price

spot, strike, rate, div, vol, texp = 100.0, 100.0, 0.05, 0.0, 0.20, 1.0
npv = price(spot, strike, rate, div, vol, texp, OptionType.CALL)
g = greeks(spot, strike, rate, div, vol, texp, OptionType.CALL)
print(f"NPV   {npv:.8f}")
print(f"Δ     {g.delta:.8f}")
print(f"Γ     {g.gamma:.8f}")
print(f"ν     {g.vega:.8f}")
print(f"Θ     {g.theta:.8f}")
print(f"ρ     {g.rho:.8f}")
print(f"vanna {g.vanna:.8f}")
print(f"volga {g.volga:.8f}")
print(f"IV    {implied_vol(npv, spot, strike, rate, div, texp):.10f}")

opt = VanillaOption.european_call(100, Date(2027, 8, 23))
print(opt.price(Date(2026, 8, 23), spot=100, rate=0.05, vol=0.20))
