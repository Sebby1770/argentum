# Argentum

A production-grade derivatives pricing library in Python, with a local Studio desk.

Argentum is what you reach for when QuantLib is too heavy to install and a
notebook full of Black–Scholes one-liners is not enough. It is typed,
tested against published identities, dual-curve native, and has no
dependency except NumPy.

```python
from argentum import OptionType, price, greeks, implied_vol

npv = price(100, 100, 0.05, 0.0, 0.20, 1.0, OptionType.CALL)
# 10.45058357
g = greeks(100, 100, 0.05, 0.0, 0.20, 1.0, OptionType.CALL)
vol = implied_vol(npv, 100, 100, 0.05, 0.0, 1.0)  # 0.20
```

## Why this exists

Most Python “pricing” code is a Black–Scholes function and a dream. A desk
library has to get the boring things right: TARGET2 holidays, 30E/360 ISDA
on a February termination, log-discount interpolation so instantaneous
forwards stay piecewise constant, OIS discounting of a Libor projection,
implied vol that does not explode at 1e-8 time value, and a CDS that
accrues on default.

Argentum implements those, then the models desks actually run: SABR,
SVI, Heston (COS), Hull–White 1F, Bachelier, trees, finite difference,
and QMC.

## Install

```bash
pip install -e ".[dev]"
```

Python 3.10+. The only runtime dependency is `numpy>=1.24`.

```bash
pytest -q
argentum vanilla --spot 100 --strike 100 --rate 0.05 --vol 0.2 --texp 1
argentum studio --port 8787
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787). The front page is the desk
brief: what the site is, what it does, how it helps, and a panel to **connect
your own stock market**. Sources:

- **Demo book** — offline, deterministic last print (no network)
- **Stooq** — public daily close
- **Your venue** — `GET https://your-exchange/api/quote/{symbol}` returning JSON
  with `spot` / `last` / `price` / `close` (nested fields like `data.last` work).
  Optional auth header. Localhost is welcome.

```bash
python3 examples/own_market.py --port 8791
# Studio → Market → Your venue
# URL: http://127.0.0.1:8791/quote/{symbol}
# Header: Authorization  /  Bearer desk
```

The lab then marks options on that last print. Press `K` for the jump palette.

## What you can price

| Book | Instruments | Engines |
|------|-------------|---------|
| Equity / FX / commodity | European vanilla, digital, barrier, lookback, geometric & arithmetic Asian, American, quanto, Geske, Margrabe, Kirk, chooser, forward-start, one-touch | BSM analytics, CRR / Leisen–Reimer, Bjerksund–Stensland 2002, Crank–Nicolson, Sobol MC |
| Rates | Deposits, FRAs, vanilla IRS (dual curve), caps/floors, European swaptions | Log-discount bootstrap, Black-76, Bachelier, SABR |
| Credit | CDS (protection, risky PV01, par, SNAC-style upfront) | Piecewise-constant hazard |
| Bonds | Fixed, zero; dirty/clean, YTM, Mac/Mod duration, convexity, Z-spread | Discount curve + analytic YTM |
| Vol | Sticky-strike surface, SABR smile, raw SVI, Heston | Hagan 2002, Gatheral, Fang–Oosterlee COS |
| IR exotics | European ZBO under Hull–White 1F | Jamshidian |

## Design rules

1. **No silent NaNs.** Domain errors raise `InputError` / `CurveError` / `ConvergenceError`.
2. **Evaluation date is an argument**, never a process-global.
3. **Discounting and forecasting are separate curves.** Single-curve is `discount is forecast`.
4. **Greeks are analytic where the model is analytic.** Vega is per 1.0 of volatility, not per vol-point. Theta is calendar-day (`/365`).
5. **Day counts follow the 2006 ISDA Definitions.** Act/Act ICMA requires a reference period.
6. **Implied vol is a round-trip.** `iv(price(σ)) = σ` to `1e-10` on a wide moneyness grid.

## A rates book in thirty lines

```python
from argentum import (
    Date, TARGET, DepositQuote, SwapQuote, bootstrap_yield_curve,
    InterestRateSwap, YieldCurve,
)

as_of = Date(2026, 8, 24)
proj = bootstrap_yield_curve(
    as_of,
    deposits=[DepositQuote("3M", 0.032), DepositQuote("6M", 0.033)],
    swaps=[SwapQuote("2Y", 0.035), SwapQuote("5Y", 0.037), SwapQuote("10Y", 0.039)],
    calendar=TARGET(),
)
ois = YieldCurve.flat(as_of, 0.031)          # discounting
swap = InterestRateSwap.vanilla(as_of, "5Y", 0.037, notional=10_000_000)
print(swap.par_rate(proj, ois), swap.npv(proj, ois), swap.dv01(proj, ois))
```

## A vol book

```python
from argentum.models.sabr import sabr_implied_vol
from argentum.models.heston import HestonParams, heston_price
from argentum.models.svi import svi_from_atm
from argentum.types import OptionType

vol = sabr_implied_vol(forward=0.03, strike=0.025, texp=5.0,
                       alpha=0.04, beta=0.5, rho=-0.3, nu=0.5)
svi = svi_from_atm(0.20, texp=1.0)
assert svi.butterfly_ok()

params = HestonParams(kappa=1.5, theta=0.04, sigma=0.4, rho=-0.5, v0=0.04)
print(heston_price(100, 100, 0.01, 0.0, 1.0, params, OptionType.CALL))
```

## CLI

```text
argentum vanilla --spot 100 --strike 100 --rate 0.05 --vol 0.2 --texp 1
argentum iv --price 10.45058357 --spot 100 --strike 100 --rate 0.05 --texp 1
argentum bond --coupon 0.06 --ytm 0.05 --as-of 2016-08-15 --maturity 2026-08-15
argentum swap --as-of 2026-08-24 --tenor 5Y --rate 0.04 --curve 0.04
argentum heston --spot 100 --strike 100 --texp 1
argentum studio --port 8787
```

## Layout

```text
src/argentum/
  time/             Date, Period, calendars, ISDA day counts, schedules
  math/             N(x), solvers, interpolation, Sobol, Thomas, quadrature
  termstructures/   yield curve, bootstrap, vol surface, hazard
  models/           BSM, Black, Bachelier, SABR, SVI, Heston, HW, trees, exotics
  engines/          finite difference, Monte Carlo
  instruments/      bond, swap, option, cap/floor, swaption, CDS, FX
  risk/             DV01, key-rate buckets, VaR
  calibration/      Levenberg–Marquardt for SABR / SVI / Heston
  feeds.py          demo book, Stooq, your HTTP JSON venue
  studio.py         local desk (Front, lab, smile, book, …)
```

## Accuracy notes

- ATM Black–Scholes (`S=K=100`, `r=5%`, `σ=20%`, `T=1`) prices at
  `10.450583572185565`, matching the closed form with `d1=0.35`, `d2=0.15`.
- Day-count tests include the ISDA 2003-11-01 / 2004-05-01 Act/Act split.
- Easter is the Anonymous Gregorian algorithm (2026-04-05, 2024-03-31).
- Heston uses the *little Heston trap* characteristic function so the
  complex logarithm stays on the principal branch.
- Finite difference uses Rannacher startup (two fully implicit steps) to
  kill the strike discontinuity before Crank–Nicolson.

This is not a substitute for a validated model-risk framework. Numbers
are for research, teaching, and desk prototyping. Read `docs/THEORY.md`
before putting a formula into production.

## License

MIT
