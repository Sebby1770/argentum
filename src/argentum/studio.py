"""Argentum Studio — a local web desk over the pricing library."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from argentum import __version__
from argentum.errors import ArgentumError, MarketError
from argentum.feeds import (
    PRESETS,
    Quote,
    fetch_quote,
    fetch_quotes,
    ingest_quote,
    probe_feed,
    split_symbols,
)
from argentum.instruments.bond import Bond
from argentum.instruments.swap import InterestRateSwap
from argentum.book import Book, VanillaPosition
from argentum.engines.fd import fd_price
from argentum.engines.montecarlo import gbm_european
from argentum.instruments.cds import CreditDefaultSwap
from argentum.models.barriers import barrier_price
from argentum.models.binomial import leisen_reimer_price
from argentum.models.bjerksund_stensland import bjerksund_stensland
from argentum.models.black_scholes import greeks, implied_vol, price
from argentum.models.compound import forward_start, geske_compound
from argentum.models.heston import HestonParams, heston_price
from argentum.models.lookback import floating_lookback
from argentum.models.multiasset import kirk_spread, margrabe
from argentum.models.sabr import sabr_smile, sabr_surface
from argentum.models.touch import no_touch, one_touch
from argentum.models.variance import black_variance_strike, log_contract_fair_variance
from argentum.scenario import default_shocks, scenario_table
from argentum.termstructures.hazard import HazardCurve, bootstrap_hazard
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date
from argentum.types import ExerciseStyle, Frequency, OptionType

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "web" / "static"
FEED_FILE = ROOT / "data" / "feed.json"
RATE_LIMIT = 120
RATE_WINDOW = 60.0
_started = time.monotonic()
_rate_lock = threading.Lock()
_rate_buckets: dict[str, list[float]] = {}
_tape: deque[dict[str, Any]] = deque(maxlen=48)
_tape_lock = threading.Lock()


def _f(values: dict[str, Any], key: str, default: float) -> float:
    raw = values.get(key, default)
    if isinstance(raw, list):
        raw = raw[0] if raw else default
    if raw is None or raw == "":
        return float(default)
    return float(raw)


def _s(values: dict[str, Any], key: str, default: str) -> str:
    raw = values.get(key, default)
    if isinstance(raw, list):
        raw = raw[0] if raw else default
    return str(raw if raw is not None else default)


def vanilla_payload(values: dict[str, Any]) -> dict[str, Any]:
    spot = _f(values, "spot", 100.0)
    strike = _f(values, "strike", 100.0)
    rate = _f(values, "rate", 0.05)
    div = _f(values, "div", 0.0)
    vol = _f(values, "vol", 0.20)
    texp = _f(values, "texp", 1.0)
    opt = OptionType.PUT if _s(values, "type", "call").lower().startswith("p") else OptionType.CALL
    npv = price(spot, strike, rate, div, vol, texp, opt)
    g = greeks(spot, strike, rate, div, vol, texp, opt)
    style = ExerciseStyle.AMERICAN if _s(values, "style", "european").lower().startswith("a") else ExerciseStyle.EUROPEAN
    tree = leisen_reimer_price(spot, strike, rate, div, vol, texp, 201, opt, style)
    fd = fd_price(spot, strike, rate, div, vol, texp, opt, style, n_space=81, n_time=60)
    mc = gbm_european(spot, strike, rate, div, vol, texp, opt, n_paths=4000, sobol=False, antithetic=True)
    american = bjerksund_stensland(spot, strike, rate, div, vol, texp, opt)
    ks = [strike * (0.6 + 0.04 * i) for i in range(21)]
    payoff = [max(k - strike, 0.0) if opt is OptionType.CALL else max(strike - k, 0.0) for k in ks]
    values_path = [price(k, strike, rate, div, vol, texp, opt) for k in ks]
    return {
        "npv": npv,
        "tree": tree,
        "fd": fd,
        "mc": mc.npv,
        "mc_error": mc.std_error,
        "american": american,
        "intrinsic": max(spot - strike, 0.0) if opt is OptionType.CALL else max(strike - spot, 0.0),
        "greeks": g.as_dict(),
        "spot": spot,
        "strike": strike,
        "vol": vol,
        "texp": texp,
        "type": opt.value,
        "style": style.value,
        "grid": {"spot": ks, "payoff": payoff, "value": values_path},
    }


def smile_payload(values: dict[str, Any]) -> dict[str, Any]:
    fwd = _f(values, "forward", 0.03)
    texp = _f(values, "texp", 5.0)
    alpha = _f(values, "alpha", 0.04)
    beta = _f(values, "beta", 0.5)
    rho = _f(values, "rho", -0.3)
    nu = _f(values, "nu", 0.5)
    grid = sabr_smile(fwd, texp, alpha, beta, rho, nu, n=25, lo=fwd * 0.4, hi=fwd * 1.8)
    return {"forward": fwd, "texp": texp, "alpha": alpha, "beta": beta, "rho": rho, "nu": nu, "grid": grid}


def bond_payload(values: dict[str, Any]) -> dict[str, Any]:
    coupon = _f(values, "coupon", 0.05)
    ytm = _f(values, "ytm", 0.045)
    years = int(_f(values, "years", 10))
    freq_n = int(_f(values, "freq", 2))
    face = _f(values, "face", 100.0)
    as_of = Date(2026, 8, 15)
    mat = as_of.add_years(years)
    freq = {1: Frequency.ANNUAL, 2: Frequency.SEMIANNUAL, 4: Frequency.QUARTERLY}.get(freq_n, Frequency.SEMIANNUAL)
    bond = Bond.fixed(coupon, mat, issue=as_of, frequency=freq, face=face)
    dirty = bond.dirty_price_from_ytm(as_of, ytm)
    return {
        "dirty": dirty,
        "clean": bond.clean_price_from_ytm(as_of, ytm),
        "accrued": bond.accrued(as_of),
        "macaulay": bond.macaulay_duration(as_of, ytm),
        "modified": bond.modified_duration(as_of, ytm),
        "convexity": bond.convexity(as_of, ytm),
        "as_of": str(as_of),
        "maturity": str(mat),
    }


def swap_payload(values: dict[str, Any]) -> dict[str, Any]:
    as_of = Date(2026, 8, 24)
    tenor = _s(values, "tenor", "5Y")
    fixed = _f(values, "rate", 0.04)
    curve_rate = _f(values, "curve", 0.04)
    notional = _f(values, "notional", 1_000_000.0)
    curve = YieldCurve.flat(as_of, curve_rate)
    swap = InterestRateSwap.vanilla(as_of, tenor, fixed, notional=notional)
    return {
        "npv": swap.npv(curve),
        "par": swap.par_rate(curve),
        "dv01": swap.dv01(curve),
        "annuity": swap.annuity(curve),
        "tenor": tenor,
        "notional": notional,
    }


def heston_payload(values: dict[str, Any]) -> dict[str, Any]:
    spot = _f(values, "spot", 100.0)
    strike = _f(values, "strike", 100.0)
    rate = _f(values, "rate", 0.03)
    texp = _f(values, "texp", 1.0)
    params = HestonParams(
        kappa=_f(values, "kappa", 1.5),
        theta=_f(values, "theta", 0.04),
        sigma=_f(values, "sigma", 0.4),
        rho=_f(values, "rho", -0.5),
        v0=_f(values, "v0", 0.04),
    )
    npv = heston_price(spot, strike, rate, 0.0, texp, params, OptionType.CALL)
    bs = price(spot, strike, rate, 0.0, params.v0**0.5, texp, OptionType.CALL)
    return {"npv": npv, "black_scholes": bs, "feller": params.feller, "feller_ok": params.feller_ok}


def extras_payload(values: dict[str, Any]) -> dict[str, Any]:
    spot = _f(values, "spot", 100.0)
    strike = _f(values, "strike", 100.0)
    rate = _f(values, "rate", 0.05)
    vol = _f(values, "vol", 0.2)
    texp = _f(values, "texp", 1.0)
    barrier = _f(values, "barrier", 90.0)
    look = floating_lookback(spot, spot, rate, 0.0, vol, texp, OptionType.CALL)
    doc = barrier_price(spot, strike, barrier, rate, 0.0, vol, texp, OptionType.CALL, knock="out", barrier_type="down")
    van = price(spot, strike, rate, 0.0, vol, texp, OptionType.CALL)
    fair_var = log_contract_fair_variance(spot, rate, 0.0, texp, lambda _k: vol)
    return {
        "vanilla": van,
        "down_out_call": doc,
        "floating_lookback_call": look,
        "variance_fair": fair_var,
        "variance_flat": black_variance_strike(vol),
        "one_touch": one_touch(spot, barrier, rate, 0.0, vol, texp, cash=1.0),
        "no_touch": no_touch(spot, barrier, rate, 0.0, vol, texp, cash=1.0),
        "margrabe": margrabe(spot, strike, vol, vol, 0.4, texp),
        "geske": geske_compound(spot, 8.0, strike, rate, 0.0, vol, 0.5, texp),
        "forward_start": forward_start(spot, rate, 0.0, vol, 0.25, texp),
        "kirk": kirk_spread(spot, 90.0, 5.0, vol, vol, 0.5, texp, df=math.exp(-rate * texp)),
    }


def implied_payload(values: dict[str, Any]) -> dict[str, Any]:
    prem = _f(values, "price", 10.45058357)
    spot = _f(values, "spot", 100.0)
    strike = _f(values, "strike", 100.0)
    rate = _f(values, "rate", 0.05)
    div = _f(values, "div", 0.0)
    texp = _f(values, "texp", 1.0)
    opt = OptionType.PUT if _s(values, "type", "call").lower().startswith("p") else OptionType.CALL
    return {"vol": implied_vol(prem, spot, strike, rate, div, texp, opt)}


def surface_payload(values: dict[str, Any]) -> dict[str, Any]:
    fwd = _f(values, "forward", 0.03)
    alpha = _f(values, "alpha", 0.04)
    beta = _f(values, "beta", 0.5)
    rho = _f(values, "rho", -0.3)
    nu = _f(values, "nu", 0.5)
    tenors = [0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
    strikes = [fwd * m for m in (0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4)]
    grid = sabr_surface(fwd, tenors, strikes, alpha, beta, rho, nu)
    return {"forward": fwd, "tenors": tenors, "strikes": strikes, "grid": grid}


def credit_payload(values: dict[str, Any]) -> dict[str, Any]:
    as_of = Date(2026, 8, 24)
    hazard_rate = _f(values, "hazard", 0.012)
    recovery = _f(values, "recovery", 0.4)
    coupon = _f(values, "coupon", 0.01)
    curve_rate = _f(values, "curve", 0.02)
    years = _f(values, "years", 5.0)
    disc = YieldCurve.flat(as_of, curve_rate)
    hz = HazardCurve.flat(as_of, hazard_rate, recovery=recovery)
    start = as_of.add_days(27)
    end = as_of.add_years(int(years))
    cds = CreditDefaultSwap(start, end, coupon=coupon, recovery=recovery, notional=10_000_000.0)
    quotes = [(1.0, hazard_rate * (1.0 - recovery) * 0.95), (3.0, hazard_rate * (1.0 - recovery)), (5.0, hazard_rate * (1.0 - recovery) * 1.05)]
    boot = bootstrap_hazard(as_of, disc, quotes, recovery=recovery)
    return {
        "par": cds.par_spread(disc, hz),
        "npv": cds.npv(disc, hz),
        "upfront": cds.upfront(disc, hz),
        "protection": cds.protection_leg(disc, hz),
        "annuity": cds.risky_annuity(disc, hz),
        "boot_hazards": [{"t": float(t), "h": float(h)} for t, h in zip(boot.times, boot.hazards)],
        "recovery": recovery,
        "hazard": hazard_rate,
    }


def book_payload(values: dict[str, Any]) -> dict[str, Any]:
    raw = values.get("positions")
    book = Book()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, list) or not raw:
        book.add(VanillaPosition(1, 100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "atm"))
        book.add(VanillaPosition(-1, 100, 110, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "call-spread"))
        book.add(VanillaPosition(1, 100, 90, 0.05, 0.0, 0.2, 1.0, OptionType.PUT, "put"))
    else:
        for row in raw:
            if not isinstance(row, dict):
                continue
            kind = OptionType.PUT if str(row.get("type", "call")).lower().startswith("p") else OptionType.CALL
            book.add(
                VanillaPosition(
                    quantity=_f(row, "qty", 1.0),
                    spot=_f(row, "spot", 100.0),
                    strike=_f(row, "strike", 100.0),
                    rate=_f(row, "rate", 0.05),
                    div=_f(row, "div", 0.0),
                    vol=_f(row, "vol", 0.2),
                    texp=_f(row, "texp", 1.0),
                    option_type=kind,
                    tag=_s(row, "tag", ""),
                )
            )
    marked = book.price()
    shocks = default_shocks()
    return {
        "npv": marked.npv,
        "greeks": marked.greeks.as_dict() if marked.greeks else {},
        "n": len(book.positions),
        "scenarios": scenario_table(book, shocks),
    }


def default_feed_config() -> dict[str, Any]:
    return {
        "source": "demo",
        "url": "https://your-exchange.example/api/quote/{symbol}",
        "field": "",
        "header_name": "",
        "header_value": "",
        "symbol": "AAPL",
        "preset": "",
        "watchlist": "AAPL,MSFT,NVDA,GOOG",
    }


def record_print(quote: Quote) -> None:
    with _tape_lock:
        _tape.appendleft({"ts": round(time.time(), 3), **quote.as_dict()})


def tape_payload(limit: int = 16) -> dict[str, Any]:
    n = max(1, min(int(limit), 48))
    with _tape_lock:
        prints = list(_tape)[:n]
    return {"ok": True, "n": len(prints), "prints": prints}


def load_feed_config() -> dict[str, Any]:
    cfg = default_feed_config()
    if FEED_FILE.is_file():
        try:
            stored = json.loads(FEED_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stored = {}
        if isinstance(stored, dict):
            cfg.update({k: stored[k] for k in cfg if k in stored})
    return cfg


def public_feed_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(cfg or load_feed_config())
    stored = str(data.get("header_value") or "").strip()
    secret = bool(stored) and stored != "••••"
    data["header_value"] = "••••" if secret else ""
    data["has_secret"] = secret
    return data


def save_feed_config(values: dict[str, Any]) -> dict[str, Any]:
    cfg = load_feed_config()
    for key in cfg:
        if key in values and values[key] is not None:
            incoming = values[key]
            if key == "header_value" and str(incoming) == "••••":
                continue
            cfg[key] = incoming
    cfg["source"] = str(cfg.get("source") or "demo").lower()
    if cfg["source"] not in {"http", "custom", "own"}:
        cfg["header_name"] = ""
        cfg["header_value"] = ""
    FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEED_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return public_feed_config(cfg)


def _resolve_header(values: dict[str, Any], cfg: dict[str, Any]) -> tuple[str | None, str | None]:
    """Use a newly typed secret; treat the UI placeholder as 'keep the stored one'."""
    name = _s(values, "header_name", cfg.get("header_name") or "") or None
    incoming = _s(values, "header_value", "")
    stored = str(cfg.get("header_value") or "")
    if incoming in {"", "••••"}:
        value = stored
    else:
        value = incoming
    if value in {"", "••••"}:
        value = ""
    return name, (value or None)


def _feed_kwargs(values: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    source = _s(values, "source", cfg.get("source") or "demo")
    url = _s(values, "url", cfg.get("url") or "") or None
    field = _s(values, "field", cfg.get("field") or "") or None
    header_name, header_value = _resolve_header(values, cfg)
    preset = _s(values, "preset", cfg.get("preset") or "") or None
    return {
        "source": source,
        "url": url,
        "field": field,
        "header_name": header_name,
        "header_value": header_value,
        "preset": preset,
    }


def quote_payload(values: dict[str, Any]) -> dict[str, Any]:
    cfg = load_feed_config()
    symbol = _s(values, "symbol", cfg.get("symbol") or "AAPL")
    quote = fetch_quote(symbol, **_feed_kwargs(values, cfg))
    record_print(quote)
    return {"ok": True, "quote": quote.as_dict()}


def probe_payload(values: dict[str, Any]) -> dict[str, Any]:
    cfg = load_feed_config()
    symbol = _s(values, "symbol", cfg.get("symbol") or "AAPL")
    return probe_feed(symbol, **_feed_kwargs(values, cfg))


def watch_payload(values: dict[str, Any]) -> dict[str, Any]:
    cfg = load_feed_config()
    raw = _s(values, "symbols", values.get("watchlist") or cfg.get("watchlist") or cfg.get("symbol") or "AAPL")
    symbols = split_symbols(str(raw))
    quotes, errors = fetch_quotes(symbols, **_feed_kwargs(values, cfg))
    for quote in quotes:
        record_print(quote)
    return {
        "ok": True,
        "quotes": [quote.as_dict() for quote in quotes],
        "errors": errors,
        "symbols": symbols,
    }


def ingest_payload(values: dict[str, Any]) -> dict[str, Any]:
    quote = ingest_quote(values, source=_s(values, "source", "push"))
    record_print(quote)
    return {"ok": True, "quote": quote.as_dict()}


def presets_payload() -> dict[str, Any]:
    return {"ok": True, "presets": PRESETS}


def mark_market_payload(values: dict[str, Any]) -> dict[str, Any]:
    quoted = quote_payload(values)
    q = quoted["quote"]
    strike = _f(values, "strike", q["spot"])
    texp = _f(values, "texp", 1.0)
    vol = _f(values, "vol", q.get("vol") or 0.20)
    rate = _f(values, "rate", q.get("rate") or 0.05)
    div = _f(values, "div", q.get("div") or 0.0)
    marked = vanilla_payload(
        {
            "spot": q["spot"],
            "strike": strike,
            "rate": rate,
            "div": div,
            "vol": vol,
            "texp": texp,
            "type": _s(values, "type", "call"),
            "style": _s(values, "style", "european"),
        }
    )
    marked["quote"] = q
    marked["atm"] = True if abs(strike - q["spot"]) < 1e-9 * max(1.0, q["spot"]) else False
    return marked


def health_payload() -> dict[str, Any]:
    feed = public_feed_config()
    with _tape_lock:
        last = _tape[0] if _tape else None
    return {
        "ok": True,
        "version": __version__,
        "uptime_s": round(time.monotonic() - _started, 3),
        "name": "Argentum Studio",
        "feed": {"source": feed.get("source"), "symbol": feed.get("symbol"), "preset": feed.get("preset")},
        "last": last,
    }


def _qs(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(urlparse(handler.path).query).items()}


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(ip, [])
        bucket[:] = [t for t in bucket if now - t < RATE_WINDOW]
        if len(bucket) >= RATE_LIMIT:
            return True
        bucket.append(now)
        return False


class StudioHandler(BaseHTTPRequestHandler):
    server_version = f"ArgentumStudio/{__version__}"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("[studio] %s - %s\n" % (self.address_string(), fmt % args))

    def _headers(self, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self._headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self._headers(content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 1_000_000))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ArgentumError(str(exc)) from exc
        return payload if isinstance(payload, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            if _rate_limited(self.client_address[0]):
                self._json({"error": "rate limited"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            qs = _qs(self)
            try:
                if path == "/api/health":
                    self._json(health_payload())
                elif path == "/api/vanilla":
                    self._json(vanilla_payload(qs))
                elif path == "/api/smile":
                    self._json(smile_payload(qs))
                elif path == "/api/bond":
                    self._json(bond_payload(qs))
                elif path == "/api/swap":
                    self._json(swap_payload(qs))
                elif path == "/api/heston":
                    self._json(heston_payload(qs))
                elif path == "/api/extras":
                    self._json(extras_payload(qs))
                elif path == "/api/iv":
                    self._json(implied_payload(qs))
                elif path == "/api/surface":
                    self._json(surface_payload(qs))
                elif path == "/api/credit":
                    self._json(credit_payload(qs))
                elif path == "/api/book":
                    self._json(book_payload(qs))
                elif path == "/api/quote":
                    self._json(quote_payload(qs))
                elif path == "/api/feed":
                    self._json({"ok": True, "feed": public_feed_config()})
                elif path == "/api/mark":
                    self._json(mark_market_payload(qs))
                elif path == "/api/watch":
                    self._json(watch_payload(qs))
                elif path == "/api/tape":
                    self._json(tape_payload(int(_f(qs, "limit", 16))))
                elif path == "/api/presets":
                    self._json(presets_payload())
                elif path == "/api/probe":
                    self._json(probe_payload(qs))
                else:
                    self._json({"error": "not found"}, 404)
            except (ArgentumError, MarketError, ValueError, ZeroDivisionError, OverflowError) as exc:
                self._json({"error": str(exc)}, 400)
            return
        self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if _rate_limited(self.client_address[0]):
            self._json({"error": "rate limited"}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        try:
            body = self._read_json()
            if parsed.path == "/api/vanilla":
                self._json(vanilla_payload(body))
            elif parsed.path == "/api/book":
                self._json(book_payload(body))
            elif parsed.path == "/api/quote":
                self._json(quote_payload(body))
            elif parsed.path == "/api/feed":
                self._json({"ok": True, "feed": save_feed_config(body)})
            elif parsed.path == "/api/mark":
                self._json(mark_market_payload(body))
            elif parsed.path == "/api/watch":
                self._json(watch_payload(body))
            elif parsed.path == "/api/probe":
                self._json(probe_payload(body))
            elif parsed.path == "/api/ingest":
                self._json(ingest_payload(body))
            else:
                self._json({"error": "not found"}, 404)
        except (ArgentumError, MarketError, ValueError) as exc:
            self._json({"error": str(exc)}, 400)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def _static(self, path: str) -> None:
        rel = "index.html" if path in {"", "/"} else path.lstrip("/")
        if rel.endswith("/"):
            rel = rel + "index.html"
        aliases = {
            "lab": "lab.html",
            "smile": "smile.html",
            "rates": "rates.html",
            "bond": "bond.html",
            "docs": "docs.html",
            "heston": "heston.html",
            "credit": "credit.html",
            "book": "book.html",
            "surface": "surface.html",
            "connect": "index.html",
            "manifest.json": "manifest.json",
            "sw.js": "sw.js",
        }
        rel = aliases.get(rel, rel)
        target = (STATIC / rel).resolve()
        try:
            target.relative_to(STATIC.resolve())
        except ValueError:
            self._bytes(b"forbidden", "text/plain", 403)
            return
        if not target.is_file():
            self._bytes(b"not found", "text/plain", 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".svg":
            ctype = "image/svg+xml"
        self._bytes(target.read_bytes(), ctype)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), StudioHandler)
    print(f"Argentum Studio {__version__}  http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Argentum Studio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
