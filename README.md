# Argentum

A typed derivatives pricing and portfolio-risk library in Python, with a local Studio desk.

Argentum is for research, teaching, and desk prototyping when QuantLib is too
heavy to install and a notebook full of Black–Scholes one-liners is not
enough. It is typed, tested against published identities, dual-curve native,
and has no dependency except NumPy.

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
your market-data endpoint**. Sources:

- **Demo book** — offline, deterministic last / bid / ask (no network)
- **Stooq** — public daily close
- **Your venue** — `GET` JSON (or CSV). `spot` / `last` / `price` / `close`,
  Polygon `results.p`, Finnhub `c`, IEX `latestPrice`, Yahoo chart, or a
  bid/ask mid. `{symbol}` in the URL, `{key}` for a token. Optional auth
  header. Localhost is welcome; cloud metadata hosts are not.
- **Push** — authenticated `POST /api/ingest` from a matching engine.

The adapter retries, caches a few seconds, and will serve a stale print if
the venue blinks — it will not invent a number. Probe, watchlist, session tape
are on Front.

```bash
python3 examples/own_market.py --port 8791 --no-auth
argentum quote AAPL --source http --url http://127.0.0.1:8791/quote/{symbol}
# Studio → Market → Your venue
# URL: http://127.0.0.1:8791/quote/{symbol}
```

The lab then marks options on that last print. Press `K` for the jump palette.

### A reproducible portfolio report

Keep a small vanilla book in UTF-8 CSV or JSON and export normalized inputs,
the Argentum version, input digest, aggregate Greeks, tag groups, and a
deterministic scenario ladder:

```bash
argentum portfolio examples/sample_portfolio.csv --format text
argentum portfolio examples/sample_portfolio.csv --format json --output risk-report.json
```

Studio's Portfolio page can load the same file locally and export the JSON
report. Required fields are `spot`, `strike`, `vol`, and `texp`; optional fields
are `tag`, `quantity` (or `qty`), `rate`, `div`, and `type`.

### Local security defaults

Studio binds to `127.0.0.1`, validates the Host header, denies cross-site
browser traffic, and requires a per-process session token for feed operations.
Feed configuration lives in the current user's operating-system config
directory, not the checkout or installed package, and is written with mode
`0600` where the platform supports it.

Push ingest is disabled unless you configure a token:

```bash
ARGENTUM_INGEST_TOKEN='replace-with-a-long-random-token' argentum studio
curl -H 'Content-Type: application/json' \
  -H 'X-Argentum-Ingest-Token: replace-with-a-long-random-token' \
  -d '{"symbol":"AAPL","last":227.14}' http://127.0.0.1:8787/api/ingest
```

For a disposable loopback-only demonstration, the explicit
`--allow-unauthenticated-ingest` flag restores tokenless push. Cross-origin
browser access and additional Host names remain opt-in.

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
argentum quote AAPL
argentum portfolio examples/sample_portfolio.csv --format json
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
  feeds.py          demo, Stooq, vendor JSON, cache, circuit, ingest
  portfolio.py      validated CSV/JSON books and reproducible risk reports
  studio.py         local desk (Front, lab, smile, book, watch, tape)
  static/           packaged Studio HTML, CSS, JavaScript, and media
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

Outputs are estimates for research, teaching, and desk prototyping. Argentum
is not a broker, data provider, validated risk system, investment advice, or a
substitute for an independent model-risk framework. Read `docs/THEORY.md`
before putting a formula into production.

## Optional setup and support

The MIT core remains free. Proposed paid setup and implementation-support
offers are documented on the [public project site](https://sebby1770.github.io/argentum/pricing.html).
Every engagement is subject to availability, a written scope, and an agreed
quote; the repository itself contains no payment or secret-gated features.

## License

MIT
