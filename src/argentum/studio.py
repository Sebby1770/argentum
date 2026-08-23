"""Argentum Studio — a local web desk over the pricing library."""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from argentum import __version__
from argentum.errors import ArgentumError
from argentum.instruments.bond import Bond
from argentum.instruments.swap import InterestRateSwap
from argentum.models.barriers import barrier_price
from argentum.models.binomial import leisen_reimer_price
from argentum.models.black_scholes import greeks, implied_vol, price
from argentum.models.heston import HestonParams, heston_price
from argentum.models.lookback import floating_lookback
from argentum.models.sabr import sabr_smile
from argentum.models.variance import black_variance_strike, log_contract_fair_variance
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date
from argentum.types import ExerciseStyle, Frequency, OptionType

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "web" / "static"
RATE_LIMIT = 60
RATE_WINDOW = 60.0
_started = time.monotonic()
_rate_lock = threading.Lock()
_rate_buckets: dict[str, list[float]] = {}


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
    tree = leisen_reimer_price(spot, strike, rate, div, vol, texp, 201, opt, ExerciseStyle.EUROPEAN)
    # payoff samples
    ks = [strike * (0.6 + 0.04 * i) for i in range(21)]
    payoff = [max(k - strike, 0.0) if opt is OptionType.CALL else max(strike - k, 0.0) for k in ks]
    values_path = [price(k, strike, rate, div, vol, texp, opt) for k in ks]
    return {
        "npv": npv,
        "tree": tree,
        "intrinsic": max(spot - strike, 0.0) if opt is OptionType.CALL else max(strike - spot, 0.0),
        "greeks": g.as_dict(),
        "spot": spot,
        "strike": strike,
        "vol": vol,
        "texp": texp,
        "type": opt.value,
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


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "version": __version__,
        "uptime_s": round(time.monotonic() - _started, 3),
        "name": "Argentum Studio",
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
                else:
                    self._json({"error": "not found"}, 404)
            except (ArgentumError, ValueError, ZeroDivisionError, OverflowError) as exc:
                self._json({"error": str(exc)}, 400)
            return
        self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/vanilla":
            self._json({"error": "not found"}, 404)
            return
        if _rate_limited(self.client_address[0]):
            self._json({"error": "rate limited"}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        try:
            self._json(vanilla_payload(self._read_json()))
        except (ArgentumError, ValueError) as exc:
            self._json({"error": str(exc)}, 400)

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
