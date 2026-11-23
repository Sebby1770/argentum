"""Argentum Studio — a local web desk over the pricing library."""

from __future__ import annotations

import argparse
import hmac
import json
import math
import mimetypes
import os
import secrets
import stat
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from argentum import __version__
from argentum.errors import ArgentumError, InputError, MarketError
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
from argentum.portfolio import book_from_rows, portfolio_report
from argentum.termstructures.hazard import HazardCurve, bootstrap_hazard
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date
from argentum.types import ExerciseStyle, Frequency, OptionType

STATIC = Path(__file__).resolve().parent / "static"


def _config_dir() -> Path:
    """Return a user-owned config directory without touching the install tree."""
    override = os.environ.get("ARGENTUM_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        return Path(base).expanduser() / "Argentum" if base else Path.home() / "AppData" / "Roaming" / "Argentum"
    if __import__("sys").platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Argentum"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".config") / "argentum"


FEED_FILE = _config_dir() / "feed.json"
RATE_LIMIT = 120
RATE_WINDOW = 60.0
_CSRF_TOKEN = secrets.token_urlsafe(32)
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


def _date_value(values: dict[str, Any], key: str, default: Date) -> Date:
    raw = _s(values, key, str(default)).strip()
    try:
        year, month, day = (int(part) for part in raw.split("-"))
        return Date(year, month, day)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{key} must be an ISO date (YYYY-MM-DD)") from exc


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
    as_of = _date_value(values, "as_of", Date(2026, 8, 15))
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
    as_of = _date_value(values, "as_of", Date(2026, 8, 24))
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
        "as_of": str(as_of),
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
    as_of = _date_value(values, "as_of", Date(2026, 8, 24))
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
        "as_of": str(as_of),
    }


def book_payload(values: dict[str, Any]) -> dict[str, Any]:
    raw = values.get("positions")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InputError(f"invalid positions JSON: {exc.msg}") from exc
    if not isinstance(raw, list) or not raw:
        book = Book()
        book.add(VanillaPosition(1, 100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "atm"))
        book.add(VanillaPosition(-1, 100, 110, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "call-spread"))
        book.add(VanillaPosition(1, 100, 90, 0.05, 0.0, 0.2, 1.0, OptionType.PUT, "put"))
    else:
        book = book_from_rows(raw)
    report = portfolio_report(book)
    return {
        "npv": report["summary"]["npv"],
        "greeks": report["summary"]["greeks"],
        "n": report["positions"],
        "scenarios": report["scenarios"],
        "report": report,
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
    FEED_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        FEED_FILE.parent.chmod(0o700)
    except OSError:
        pass
    # Write beside the destination, fsync, then atomically replace it.  The
    # temporary mode prevents another local user reading a half-written token.
    tmp = FEED_FILE.with_name(f".{FEED_FILE.name}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(tmp, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, FEED_FILE)
        try:
            FEED_FILE.chmod(0o600)
        except OSError:
            pass
    finally:
        if tmp.exists():
            tmp.unlink()
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

    _CSRF_PATHS = {
        "/api/feed",
        "/api/ingest",
        "/api/mark",
        "/api/probe",
        "/api/quote",
        "/api/watch",
    }

    def log_message(self, fmt: str, *args: Any) -> None:
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("[studio] %s - %s\n" % (self.address_string(), fmt % args))

    def _headers(self, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; connect-src 'self'; font-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; worker-src 'self'",
        )
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=(), payment=()")
        origin = self.headers.get("Origin", "")
        allowed = set(getattr(self.server, "allowed_origins", ()))
        if origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)

    def _csrf_token(self) -> str:
        return str(getattr(self.server, "csrf_token", _CSRF_TOKEN))

    def _request_is_trusted(self) -> bool:
        """Reject cross-site browser traffic unless its exact origin was opted in."""
        origin = self.headers.get("Origin", "")
        fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if fetch_site == "cross-site":
            return origin in set(getattr(self.server, "allowed_origins", ()))
        if not origin:
            return True  # curl, a matching engine, and same-origin navigation
        parsed = urlparse(origin)
        host = self.headers.get("Host", "")
        same_origin = parsed.scheme in {"http", "https"} and parsed.netloc == host
        return same_origin or origin in set(getattr(self.server, "allowed_origins", ()))

    def _host_is_trusted(self) -> bool:
        raw = self.headers.get("Host", "")
        if not raw:
            return False
        try:
            hostname = urlparse(f"//{raw}").hostname
        except ValueError:
            return False
        allowed = {str(host).lower().rstrip(".") for host in getattr(self.server, "trusted_hosts", ())}
        return bool(hostname) and hostname.lower().rstrip(".") in allowed

    def _has_csrf(self) -> bool:
        supplied = self.headers.get("X-Argentum-CSRF", "")
        return bool(supplied) and hmac.compare_digest(supplied, self._csrf_token())

    def _browser_request(self) -> bool:
        return bool(self.headers.get("Origin") or self.headers.get("Sec-Fetch-Site"))

    def _authorize_api(self, path: str, *, state_change: bool = False) -> bool:
        if not self._host_is_trusted():
            self._json({"error": "unrecognised Host header"}, HTTPStatus.MISDIRECTED_REQUEST)
            return False
        if not self._request_is_trusted():
            self._json({"error": "cross-origin request denied"}, HTTPStatus.FORBIDDEN)
            return False
        ingest_authorized = False
        if path == "/api/ingest":
            expected = str(getattr(self.server, "ingest_token", "") or "")
            supplied = self.headers.get("X-Argentum-Ingest-Token", "")
            if expected and not (supplied and hmac.compare_digest(supplied, expected)):
                self._json({"error": "invalid ingest token"}, HTTPStatus.FORBIDDEN)
                return False
            if not expected and not bool(getattr(self.server, "allow_unauthenticated_ingest", False)):
                self._json(
                    {"error": "push ingest is disabled; configure an ingest token to enable it"},
                    HTTPStatus.FORBIDDEN,
                )
                return False
            ingest_authorized = bool(expected)
        needs_csrf = path in self._CSRF_PATHS and (state_change or self._browser_request())
        if path == "/api/ingest" and not self._browser_request():
            needs_csrf = False
        if needs_csrf and not ingest_authorized and not self._has_csrf():
            self._json({"error": "missing or invalid session token"}, HTTPStatus.FORBIDDEN)
            return False
        return True

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
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArgentumError(str(exc)) from exc
        if not isinstance(payload, dict):
            raise InputError("request JSON must be an object")
        return payload

    def _valid_json_body(self) -> bool:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._json({"error": "Content-Type must be application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return False
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            self._json({"error": "invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            return False
        if length <= 0:
            self._json({"error": "JSON request body required"}, HTTPStatus.BAD_REQUEST)
            return False
        if length > 1_000_000:
            self._json({"error": "request body exceeds 1 MB"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_is_trusted():
            self._json({"error": "unrecognised Host header"}, HTTPStatus.MISDIRECTED_REQUEST)
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            if not self._authorize_api(path):
                return
            if _rate_limited(self.client_address[0]):
                self._json({"error": "rate limited"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            qs = _qs(self)
            try:
                if path == "/api/health":
                    self._json(health_payload())
                elif path == "/api/session":
                    self._json({"ok": True, "csrf": self._csrf_token()})
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
        if not self._authorize_api(parsed.path, state_change=parsed.path in self._CSRF_PATHS):
            return
        if not self._valid_json_body():
            return
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
        if not self._host_is_trusted():
            self._json({"error": "unrecognised Host header"}, HTTPStatus.MISDIRECTED_REQUEST)
            return
        if not self._request_is_trusted():
            self._json({"error": "cross-origin request denied"}, HTTPStatus.FORBIDDEN)
            return
        origin = self.headers.get("Origin", "")
        allowed = set(getattr(self.server, "allowed_origins", ()))
        self.send_response(204)
        if origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Argentum-CSRF, X-Argentum-Ingest-Token",
        )
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
            not_found = STATIC / "404.html"
            if not_found.is_file():
                self._bytes(not_found.read_bytes(), "text/html; charset=utf-8", 404)
            else:
                self._bytes(b"not found", "text/plain", 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".svg":
            ctype = "image/svg+xml"
        self._bytes(target.read_bytes(), ctype)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()


def serve(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    allowed_origins: tuple[str, ...] = (),
    ingest_token: str | None = None,
    trusted_hosts: tuple[str, ...] = (),
    allow_unauthenticated_ingest: bool = False,
) -> None:
    httpd = ThreadingHTTPServer((host, port), StudioHandler)
    httpd.allowed_origins = tuple(allowed_origins)  # type: ignore[attr-defined]
    httpd.ingest_token = ingest_token or os.environ.get("ARGENTUM_INGEST_TOKEN", "")  # type: ignore[attr-defined]
    loopback = {"127.0.0.1", "localhost", "::1"}
    configured = set(trusted_hosts)
    if host not in {"0.0.0.0", "::"}:
        configured.add(host)
    httpd.trusted_hosts = tuple(sorted(loopback | configured))  # type: ignore[attr-defined]
    httpd.allow_unauthenticated_ingest = allow_unauthenticated_ingest  # type: ignore[attr-defined]
    httpd.csrf_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
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
    parser.add_argument("--allow-origin", action="append", default=[], help="exact browser origin to allow (repeatable)")
    parser.add_argument("--ingest-token", default=None, help="token required in X-Argentum-Ingest-Token")
    parser.add_argument("--trusted-host", action="append", default=[], help="additional accepted Host name (repeatable)")
    parser.add_argument("--allow-unauthenticated-ingest", action="store_true", help="allow tokenless loopback push ingest")
    args = parser.parse_args()
    serve(
        args.host,
        args.port,
        allowed_origins=tuple(args.allow_origin),
        ingest_token=args.ingest_token,
        trusted_hosts=tuple(args.trusted_host),
        allow_unauthenticated_ingest=args.allow_unauthenticated_ingest,
    )


if __name__ == "__main__":
    main()
