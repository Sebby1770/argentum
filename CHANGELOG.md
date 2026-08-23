# Changelog

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

First public release of Argentum, a production-grade Python derivatives library.

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
