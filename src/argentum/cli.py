"""Command-line interface for one-off prices, implied vols, bonds, and swaps."""

from __future__ import annotations

import argparse
import json
import os
import sys

from argentum import __version__
from argentum.instruments.bond import Bond
from argentum.instruments.swap import InterestRateSwap
from argentum.models.black_scholes import greeks, implied_vol, price
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date
from argentum.types import Frequency, OptionType


def _date(text: str) -> Date:
    y, m, d = (int(p) for p in text.split("-"))
    return Date(y, m, d)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="argentum", description="Argentum derivatives pricing")
    p.add_argument("--version", action="version", version=f"argentum {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    van = sub.add_parser("vanilla", help="Black–Scholes European vanilla")
    van.add_argument("--spot", type=float, required=True)
    van.add_argument("--strike", type=float, required=True)
    van.add_argument("--rate", type=float, required=True)
    van.add_argument("--div", type=float, default=0.0)
    van.add_argument("--vol", type=float, required=True)
    van.add_argument("--texp", type=float, required=True)
    van.add_argument("--put", action="store_true")
    van.add_argument("--json", action="store_true")

    iv = sub.add_parser("iv", help="Black–Scholes implied volatility")
    iv.add_argument("--price", type=float, required=True)
    iv.add_argument("--spot", type=float, required=True)
    iv.add_argument("--strike", type=float, required=True)
    iv.add_argument("--rate", type=float, required=True)
    iv.add_argument("--div", type=float, default=0.0)
    iv.add_argument("--texp", type=float, required=True)
    iv.add_argument("--put", action="store_true")

    bond = sub.add_parser("bond", help="Fixed-rate bond from YTM")
    bond.add_argument("--coupon", type=float, required=True)
    bond.add_argument("--ytm", type=float, required=True)
    bond.add_argument("--as-of", dest="as_of", type=_date, required=True)
    bond.add_argument("--maturity", type=_date, required=True)
    bond.add_argument("--issue", type=_date, default=None)
    bond.add_argument("--freq", type=int, default=2, help="coupons per year")
    bond.add_argument("--face", type=float, default=100.0)

    swap = sub.add_parser("swap", help="Par swap on a flat curve")
    swap.add_argument("--as-of", dest="as_of", type=_date, required=True)
    swap.add_argument("--tenor", required=True)
    swap.add_argument("--rate", type=float, required=True)
    swap.add_argument("--curve", type=float, required=True, help="flat continuous zero")
    swap.add_argument("--notional", type=float, default=1_000_000.0)

    smile = sub.add_parser("smile", help="SABR implied-vol grid")
    smile.add_argument("--forward", type=float, required=True)
    smile.add_argument("--texp", type=float, required=True)
    smile.add_argument("--alpha", type=float, required=True)
    smile.add_argument("--beta", type=float, default=0.5)
    smile.add_argument("--rho", type=float, default=-0.3)
    smile.add_argument("--nu", type=float, default=0.5)
    smile.add_argument("--json", action="store_true")

    studio = sub.add_parser("studio", help="Open the Argentum Studio web desk")
    studio.add_argument("--host", default="127.0.0.1")
    studio.add_argument("--port", type=int, default=8787)
    studio.add_argument("--allow-origin", action="append", default=[], help="exact browser origin to allow (repeatable)")
    studio.add_argument("--ingest-token", default=None, help="token required in X-Argentum-Ingest-Token")
    studio.add_argument("--trusted-host", action="append", default=[], help="additional accepted Host name (repeatable)")
    studio.add_argument("--allow-unauthenticated-ingest", action="store_true", help="allow tokenless loopback push ingest")

    heston = sub.add_parser("heston", help="Heston COS European call")
    heston.add_argument("--spot", type=float, default=100.0)
    heston.add_argument("--strike", type=float, default=100.0)
    heston.add_argument("--rate", type=float, default=0.03)
    heston.add_argument("--texp", type=float, default=1.0)
    heston.add_argument("--kappa", type=float, default=1.5)
    heston.add_argument("--theta", type=float, default=0.04)
    heston.add_argument("--sigma", type=float, default=0.4)
    heston.add_argument("--rho", type=float, default=-0.5)
    heston.add_argument("--v0", type=float, default=0.04)

    quote = sub.add_parser("quote", help="Pull a last print from demo, Stooq, or a venue URL")
    quote.add_argument("symbol")
    quote.add_argument("--source", default="demo", help="demo | stooq | http")
    quote.add_argument("--url", default="", help="JSON venue with {symbol}")
    quote.add_argument("--field", default="", help="dotted path, e.g. data.last")
    quote.add_argument("--header-name", default="", dest="header_name")
    quote.add_argument("--header-value", default="", dest="header_value")
    quote.add_argument("--preset", default="", help="own | polygon | finnhub | alphavantage | iex")
    quote.add_argument("--json", action="store_true")

    portfolio = sub.add_parser("portfolio", help="Price a CSV/JSON vanilla book and run desk scenarios")
    portfolio.add_argument("path", help="UTF-8 .csv or .json portfolio")
    portfolio.add_argument("--format", choices=("text", "json", "csv"), default="text")
    portfolio.add_argument("--output", default="-", help="report path, or - for stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "vanilla":
        opt = OptionType.PUT if args.put else OptionType.CALL
        npv = price(args.spot, args.strike, args.rate, args.div, args.vol, args.texp, opt)
        g = greeks(args.spot, args.strike, args.rate, args.div, args.vol, args.texp, opt)
        payload = {"npv": npv, **g.as_dict()}
        if args.json:
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"npv     {npv:.8f}")
            print(f"delta   {g.delta:.8f}")
            print(f"gamma   {g.gamma:.8f}")
            print(f"vega    {g.vega:.8f}")
            print(f"theta   {g.theta:.8f}")
            print(f"rho     {g.rho:.8f}")
            print(f"vanna   {g.vanna:.8f}")
            print(f"volga   {g.volga:.8f}")
        return 0
    if args.cmd == "iv":
        opt = OptionType.PUT if args.put else OptionType.CALL
        vol = implied_vol(args.price, args.spot, args.strike, args.rate, args.div, args.texp, opt)
        print(f"{vol:.10f}")
        return 0
    if args.cmd == "bond":
        freq = Frequency.SEMIANNUAL if args.freq == 2 else Frequency.ANNUAL if args.freq == 1 else Frequency.QUARTERLY
        issue = args.issue or args.as_of
        bond = Bond.fixed(args.coupon, args.maturity, issue=issue, frequency=freq, face=args.face)
        dirty = bond.dirty_price_from_ytm(args.as_of, args.ytm)
        clean = bond.clean_price_from_ytm(args.as_of, args.ytm)
        print(f"dirty     {dirty:.8f}")
        print(f"clean     {clean:.8f}")
        print(f"accrued   {bond.accrued(args.as_of):.8f}")
        print(f"mac       {bond.macaulay_duration(args.as_of, args.ytm):.8f}")
        print(f"mod       {bond.modified_duration(args.as_of, args.ytm):.8f}")
        print(f"convexity {bond.convexity(args.as_of, args.ytm):.8f}")
        return 0
    if args.cmd == "swap":
        curve = YieldCurve.flat(args.as_of, args.curve)
        swap = InterestRateSwap.vanilla(args.as_of, args.tenor, args.rate, notional=args.notional)
        print(f"npv       {swap.npv(curve):.6f}")
        print(f"par       {swap.par_rate(curve):.8f}")
        print(f"dv01      {swap.dv01(curve):.6f}")
        return 0
    if args.cmd == "smile":
        from argentum.models.sabr import sabr_smile

        grid = sabr_smile(args.forward, args.texp, args.alpha, args.beta, args.rho, args.nu)
        if args.json:
            json.dump(grid, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"{'K':>12} {'vol':>10}")
            for row in grid:
                print(f"{row['strike']:12.6f} {row['vol']:10.4%}")
        return 0
    if args.cmd == "studio":
        from argentum.studio import serve

        serve(
            args.host,
            args.port,
            allowed_origins=tuple(args.allow_origin),
            ingest_token=args.ingest_token or os.environ.get("ARGENTUM_INGEST_TOKEN"),
            trusted_hosts=tuple(args.trusted_host),
            allow_unauthenticated_ingest=args.allow_unauthenticated_ingest,
        )
        return 0
    if args.cmd == "heston":
        from argentum.models.heston import HestonParams, heston_price
        from argentum.types import OptionType as OT

        params = HestonParams(args.kappa, args.theta, args.sigma, args.rho, args.v0)
        print(f"{heston_price(args.spot, args.strike, args.rate, 0.0, args.texp, params, OT.CALL):.8f}")
        return 0
    if args.cmd == "quote":
        from argentum.feeds import fetch_quote

        quoted = fetch_quote(
            args.symbol,
            source=args.source,
            url=args.url or None,
            field=args.field or None,
            header_name=args.header_name or None,
            header_value=args.header_value or None,
            preset=args.preset or None,
        )
        if args.json:
            json.dump(quoted.as_dict(), sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"{quoted.symbol:8} {quoted.spot:12.4f}  {quoted.source}")
            if quoted.bid is not None and quoted.ask is not None:
                print(f"bid/ask  {quoted.bid:.4f} / {quoted.ask:.4f}")
        return 0
    if args.cmd == "portfolio":
        from pathlib import Path

        from argentum.portfolio import load_portfolio, portfolio_report, report_csv, report_text

        report = portfolio_report(load_portfolio(args.path))
        if args.format == "json":
            rendered = json.dumps(report, indent=2) + "\n"
        elif args.format == "csv":
            rendered = report_csv(report)
        else:
            rendered = report_text(report)
        if args.output == "-":
            sys.stdout.write(rendered)
        else:
            Path(args.output).write_text(rendered, encoding="utf-8")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
