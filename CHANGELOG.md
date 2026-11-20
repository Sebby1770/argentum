# Changelog

## 1.6.0 — 2026-11-20

### Added
- `argentum.models.charfn`: one COS (Fang–Oosterlee) engine for Black–Scholes,
  Merton jumps, Variance Gamma, NIG, Heston and Bates, vectorised over strikes;
  `model_smile` turns any of them into an implied-vol smile.
- `argentum.models.vectorized`: `price_array`, `greeks_array`,
  `implied_vol_array` (safeguarded Newton, `errors="nan"` for bad quotes) and
  `chain` for whole strike × expiry grids.
- `Greeks.theta_per_day`.
- CI gates: ruff (bug rules), mypy, coverage floor.

### Fixed
- `heston_price` was 4.5e-5 off Fang–Oosterlee's reference 5.785155435; it now
  uses the shared engine and matches to nine digits.
- `require_positive` / `require_non_negative` let NaN and infinity through, so
  Studio answered `{"npv": NaN}` (invalid JSON). Inputs are now rejected with a
  400 and the server never emits NaN tokens.
- Theta was documented as per calendar day but is per year; docs corrected and
  the Lab shows theta per day.
- `price()` claimed NumPy array support but rejected arrays; it now broadcasts.
- 11 mypy errors and dead code found by lint.

## 1.5.0 — 2026-08-24

- Added validated CSV/JSON portfolio loading and deterministic text, JSON, and
  CSV scenario reports with normalized inputs, version, engine, and input digest.
- Added Portfolio import/export to Studio.
- Packaged Studio assets inside the wheel so installed deployments work.
- Moved feed configuration to the user's operating-system config directory with
  atomic mode-`0600` writes and redacted secrets.
- Removed wildcard CORS, added Host validation, per-process browser CSRF,
  opt-in origins, disabled-by-default push ingest, request-size/type checks,
  strict response headers, and untrusted-feed DOM sanitisation.
- Added explicit calibration non-convergence diagnostics.
- Added a separate GitHub Pages launch site with transparent support pricing,
  reproducible proof, FAQ schema, privacy/consent controls, custom 404,
  breadcrumbs, social metadata, maker disclosure, and brand-risk notes.
- Version **1.5.0**

## 1.4.0 — 2026-08-24

### Added
- Vendor quote parsers: Polygon, Finnhub, IEX, Alpha Vantage, Yahoo chart, bid/ask mid, CSV
- Feed runtime: retries with backoff, TTL cache, stale-on-failure, per-host circuit breaker
- Watchlist batch (`fetch_quotes` / `GET|POST /api/watch`), probe (`/api/probe`), session tape
- Ingest path so a matching engine can push ticks (`POST /api/ingest`, CORS)
- Venue presets (own_market, Polygon, Finnhub, IEX, Alpha Vantage)
- `argentum quote` CLI; `Book.remap_spots`; `Market.apply_quotes`
- Front: bid/ask, watch board, probe, session tape, richer desk brief

### Changed
- Version **1.4.0**
- Metadata/link-local feed hosts refused; still allows localhost and private venues

## 1.3.0 — 2026-08-23

### Added
- **Market feeds** — demo book, Stooq daily close, or a user’s own HTTP JSON venue (`{symbol}` URL, optional auth header)
- Front page rewritten as a desk brief: what the site is, what it does, how it helps, how to connect a market, a four-step session
- Sample venue `examples/own_market.py` so a matching engine can be faked in one command
- Lab “Pull last print” uses the saved feed and marks ATM on that spot
- `/api/quote`, `/api/feed`, `/api/mark`
- Saved API keys are not replayed as the `••••` placeholder; demo/Stooq saves clear secrets

### Changed
- Version **1.3.0**

## 1.2.0 — 2026-08-23

### Added
- Margrabe exchange, Kirk spread, Geske compound, Rubinstein chooser, forward-start
- One-touch / no-touch, Dupire local vol (Gatheral) from a SABR slice
- Piecewise hazard bootstrap from par CDS quotes
- Book scenario engine (spot / vol / rate shocks)
- Studio pages: Heston, credit, blotter, SABR surface heatmap
- Lab now reports analytic, tree, FD, MC and an American mark; shareable query string
- Command palette (K), PWA, `argentum heston`

### Changed
- Version **1.2.0**

## 1.1.0 — 2026-08-23

### Added
- **Argentum Studio** — local web desk (`python -m argentum studio`) with a front page, vanilla lab, SABR smile, IRS, and bond calculators wired to the real engines
- Lookbacks (Goldman–Sosin–Gatto floating, Conze–Viswanathan fixed)
- Variance-swap fair strike via the Carr–Madan log-contract integral
- Quanto vanillas and escrowed cash dividends
- Reiner–Rubinstein barriers rewritten against the Haug table, with in-out parity tests
- Trading `Book` / `VanillaPosition`, `Market` snapshot, text/HTML tickets
- Switzerland and Canada calendars
- `sabr_smile` grid helper and `argentum smile` CLI
- Lab engine compare: analytic vs Leisen–Reimer

### Changed
- Version **1.1.0**

## 1.0.0 — 2026-08-23

First public release of the Argentum Python derivatives library.

### Time
- ISDA day counts: Act/365F, Act/360, Act/Act ISDA, Act/Act ICMA, Act/Act AFB, 30/360, 30E/360, 30E/360 ISDA, Bus/252
- Calendars: TARGET2, US settlement / NYSE / govt bond, UK, Japan, Australia, joint calendars
- Schedules: forward/backward/IMM generation, stubs, business-day conventions

### Curves
- Log-discount interpolation (linear, cubic, Hyman monotone cubic)
- Dual-curve bootstrap from deposits, FRAs, and par swaps
- Piecewise-constant hazard curves and Black vol surfaces

### Models
- Black–Scholes–Merton with a full greek suite and robust implied vol
- Black-76 and Bachelier (normal)
- CRR and Leisen–Reimer trees; Bjerksund–Stensland 2002 Americans
- SABR (Hagan 2002) lognormal and normal, shifted SABR
- Raw SVI with butterfly test
- Heston COS (Fang–Oosterlee, little Heston trap CF)
- Hull–White 1F zero-bond options
- Geometric and Turnbull–Wakeman Asians; Reiner–Rubinstein barriers

### Engines
- Crank–Nicolson FD with Rannacher startup
- GBM Monte Carlo (Sobol + antithetic) and Heston QE (Andersen)

### Instruments
- Fixed bonds: dirty/clean, YTM, Mac/Mod duration, convexity, Z-spread
- Vanilla IRS with dual-curve NPV, par, DV01
- Caps/floors, European swaptions (Black / Bachelier / SABR)
- ISDA-style CDS (protection, risky PV01, par, upfront)
- FX Garman–Kohlhagen vanillas

### Risk & calibration
- Parallel DV01, key-rate buckets, parametric/historical VaR
- Levenberg–Marquardt calibration of SABR, SVI, Heston

### Tooling
- `argentum` CLI, typed package, pytest suite, GitHub Actions CI
