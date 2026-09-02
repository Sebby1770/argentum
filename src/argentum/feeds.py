"""Market-data adapters: demo book, Stooq, or a user's own venue.

A custom venue is any HTTP(S) URL that returns a quote. Put ``{symbol}``
in the path or query (and ``{key}`` if the vendor wants an API token in the
URL). Argentum accepts last/spot/price/close, Polygon/Finnhub/IEX/Yahoo/
Alpha Vantage shapes, bid/ask mids, and simple CSV. This is a mark, not an
order gateway.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from argentum.errors import InputError, MarketError

_SPOT_KEYS = (
    "spot",
    "last",
    "price",
    "close",
    "px",
    "mid",
    "ltp",
    "trade",
    "latestPrice",
    "regularMarketPrice",
    "mark",
    "lastPrice",
    "last_price",
    "lastSalePrice",
)
_VENDOR_PATHS = (
    "results.p",
    "results.c",
    "last.p",
    "last.price",
    "data.last",
    "data.price",
    "data.close",
    "quote.last",
    "quote.price",
    "quote.close",
    "Global Quote.05. price",
    "chart.result.0.meta.regularMarketPrice",
    "c",
)
_BID_KEYS = ("bid", "b", "bidPrice", "bid_price", "bp")
_ASK_KEYS = ("ask", "a", "askPrice", "ask_price", "ap")
_SAFE_SCHEMES = {"http", "https"}
_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}
_MAX_BYTES = 1_000_000

PRESETS: dict[str, dict[str, str]] = {
    "custom": {
        "label": "Your venue",
        "url": "https://your-venue/api/quote/{symbol}",
        "field": "",
        "header_name": "Authorization",
        "note": "GET JSON. {symbol} in the URL. Localhost is welcome.",
    },
    "own": {
        "label": "Local own_market.py",
        "url": "http://127.0.0.1:8791/quote/{symbol}",
        "field": "",
        "header_name": "",
        "note": "python examples/own_market.py --no-auth",
    },
    "polygon": {
        "label": "Polygon last trade",
        "url": "https://api.polygon.io/v2/last/trade/{symbol}",
        "field": "results.p",
        "header_name": "Authorization",
        "note": "Header value: Bearer YOUR_API_KEY",
    },
    "finnhub": {
        "label": "Finnhub quote",
        "url": "https://finnhub.io/api/v1/quote?symbol={symbol}&token={key}",
        "field": "c",
        "header_name": "",
        "note": "Paste the Finnhub token as the header value; it fills {key}.",
    },
    "alphavantage": {
        "label": "Alpha Vantage global quote",
        "url": "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={key}",
        "field": "Global Quote.05. price",
        "header_name": "",
        "note": "Paste the Alpha Vantage key as the header value; it fills {key}.",
    },
    "iex": {
        "label": "IEX Cloud quote",
        "url": "https://cloud.iexapis.com/stable/stock/{symbol}/quote?token={key}",
        "field": "latestPrice",
        "header_name": "",
        "note": "Paste the IEX token as the header value; it fills {key}.",
    },
}


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    spot: float
    source: str
    currency: str = "USD"
    name: str = ""
    asof: str = ""
    vol: float | None = None
    rate: float | None = None
    div: float | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    prev_close: float | None = None
    open_px: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    change: float | None = None
    change_pct: float | None = None
    latency_ms: float | None = None
    stale: bool = False
    cached: bool = False
    raw: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("raw", None)
        if self.bid is not None and self.ask is not None:
            payload["spread"] = round(self.ask - self.bid, 6)
            payload["mid"] = round(0.5 * (self.bid + self.ask), 6)
        return payload


def coerce_number(value: Any) -> float | None:
    if value is None or value is True or value is False:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number != number or number in {float("inf"), float("-inf")}:
            return None
        return number
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("$", "").replace("%", "")
        if text in {"", "N/D", "null", "None", "-"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _dig(obj: Any, path: str) -> Any:
    """Walk a dotted path. Keys themselves may contain dots (Alpha Vantage)."""
    if isinstance(obj, dict) and path in obj:
        return obj[path]
    cur = obj
    parts = path.split(".")
    i = 0
    n = len(parts)
    while i < n:
        if isinstance(cur, list) and parts[i].isdigit():
            idx = int(parts[i])
            if not 0 <= idx < len(cur):
                return None
            cur = cur[idx]
            i += 1
            continue
        if isinstance(cur, dict):
            found = False
            for j in range(n, i, -1):
                candidate = ".".join(parts[i:j])
                if candidate in cur:
                    cur = cur[candidate]
                    i = j
                    found = True
                    break
            if not found:
                return None
            continue
        return None
    return cur


def _pick(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _unwrap(payload: Any, symbol: str) -> Any:
    if isinstance(payload, list):
        want = (symbol or "").upper()
        if want:
            for item in payload:
                if not isinstance(item, dict):
                    continue
                tag = str(item.get("symbol") or item.get("ticker") or item.get("sym") or "").upper()
                if tag == want:
                    return item
        return payload[0] if payload else payload
    if isinstance(payload, dict):
        for key in ("quotes", "data", "results", "result"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return _unwrap(inner, symbol)
        nested = payload.get("data") or payload.get("quote")
        if isinstance(nested, dict):
            return nested
    return payload


def extract_spot(payload: Any, field: str | None = None) -> float:
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        return float(payload)
    if isinstance(payload, str):
        number = coerce_number(payload)
        if number is None:
            raise MarketError("quote payload must be a JSON object")
        return number
    if not isinstance(payload, dict):
        raise MarketError("quote payload must be a JSON object")
    if field:
        value = coerce_number(_dig(payload, field))
        if value is not None:
            return value
    for key in _SPOT_KEYS:
        value = coerce_number(payload.get(key))
        if value is not None:
            return value
        nested = payload.get("data") or payload.get("quote") or payload.get("result")
        if isinstance(nested, dict):
            value = coerce_number(nested.get(key))
            if value is not None:
                return value
    for path in _VENDOR_PATHS:
        value = coerce_number(_dig(payload, path))
        if value is not None:
            return value
    bid = coerce_number(_pick(payload, _BID_KEYS))
    ask = coerce_number(_pick(payload, _ASK_KEYS))
    if bid is not None and ask is not None and ask >= bid > 0:
        return 0.5 * (bid + ask)
    raise MarketError("could not find spot/last/price/close in the JSON quote")


def parse_json_quote(payload: Any, symbol: str, *, field: str | None = None, source: str = "http") -> Quote:
    data = _unwrap(payload, symbol)
    if not isinstance(data, dict):
        if isinstance(payload, dict):
            data = payload
        else:
            spot = extract_spot(payload, field)
            if not math.isfinite(spot) or spot <= 0:
                raise MarketError(f"spot must be a positive finite number, got {spot!r}")
            return Quote(symbol=symbol.upper(), spot=spot, source=source, last=spot)
    spot = extract_spot(data, field)
    if field and data is not payload and isinstance(payload, dict):
        try:
            spot = extract_spot(payload, field)
            data = payload
        except MarketError:
            pass
    bid = coerce_number(_pick(data, _BID_KEYS))
    ask = coerce_number(_pick(data, _ASK_KEYS))
    last = coerce_number(_first_present(data.get("last"), data.get("price"), data.get("spot"), data.get("c")))
    prev = coerce_number(_first_present(data.get("prev_close"), data.get("previousClose"), data.get("pc"), data.get("previous_close")))
    open_px = coerce_number(_first_present(data.get("open"), data.get("o"), data.get("open_px")))
    high = coerce_number(_first_present(data.get("high"), data.get("h")))
    low = coerce_number(_first_present(data.get("low"), data.get("l")))
    volume = coerce_number(_first_present(data.get("volume"), data.get("v"), data.get("Volume")))
    vol = coerce_number(_first_present(data.get("vol"), data.get("iv"), data.get("implied_vol"), data.get("impliedVolatility")))
    rate = coerce_number(_first_present(data.get("rate"), data.get("r")))
    div = coerce_number(_first_present(data.get("div"), data.get("dividend"), data.get("q")))
    if not math.isfinite(spot) or spot <= 0:
        raise MarketError(f"spot must be a positive finite number, got {spot!r}")
    if bid is not None and bid <= 0:
        raise MarketError(f"bid must be positive, got {bid!r}")
    if ask is not None and ask <= 0:
        raise MarketError(f"ask must be positive, got {ask!r}")
    if bid is not None and ask is not None and ask < bid:
        raise MarketError(f"ask must be greater than or equal to bid ({bid!r}, {ask!r})")
    if vol is not None and not 0 < vol <= 5:
        raise MarketError("vol must be a decimal fraction in (0, 5], e.g. 0.20 for 20%")
    if rate is not None and not -1 <= rate <= 1:
        raise MarketError("rate must be a decimal fraction in [-1, 1], e.g. 0.05 for 5%")
    if div is not None and not -1 <= div <= 1:
        raise MarketError("div must be a decimal fraction in [-1, 1], e.g. 0.02 for 2%")
    change = coerce_number(_first_present(data.get("change"), data.get("d")))
    change_pct = coerce_number(_first_present(data.get("change_pct"), data.get("dp"), data.get("changePercent")))
    if change is None and last is not None and prev is not None:
        change = last - prev
    if change_pct is None and change is not None and prev not in (None, 0):
        change_pct = 100.0 * change / prev
    name = data.get("name") or data.get("shortName") or data.get("description") or symbol
    return Quote(
        symbol=str(data.get("symbol") or data.get("ticker") or symbol).upper(),
        spot=float(spot),
        source=source,
        currency=str(data.get("currency") or data.get("ccy") or "USD"),
        name=str(name),
        asof=str(data.get("asof") or data.get("time") or data.get("date") or data.get("t") or ""),
        vol=vol,
        rate=rate,
        div=div,
        bid=bid,
        ask=ask,
        last=last if last is not None else spot,
        prev_close=prev,
        open_px=open_px,
        high=high,
        low=low,
        volume=volume,
        change=change,
        change_pct=change_pct,
        raw=data if isinstance(data, dict) else None,
    )


def parse_stooq_csv(text: str, symbol: str) -> Quote:
    reader = csv.DictReader(io.StringIO(text.strip()))
    row = next(reader, None)
    if not row:
        raise MarketError("Stooq returned an empty table")
    close = row.get("Close") or row.get("close")
    if close in (None, "", "N/D"):
        raise MarketError(f"Stooq has no close for {symbol!r}")
    last = float(close)
    return Quote(
        symbol=(row.get("Symbol") or symbol).upper(),
        spot=last,
        source="stooq",
        asof=(row.get("Date") or ""),
        name=symbol.upper(),
        last=last,
        open_px=coerce_number(row.get("Open") or row.get("open")),
        high=coerce_number(row.get("High") or row.get("high")),
        low=coerce_number(row.get("Low") or row.get("low")),
        volume=coerce_number(row.get("Volume") or row.get("volume")),
    )


def parse_tabular_quote(text: str, symbol: str) -> Quote:
    if "Symbol" in text and "Close" in text:
        return parse_stooq_csv(text, symbol)
    reader = csv.DictReader(io.StringIO(text.strip()))
    if reader.fieldnames:
        row = next(reader, None)
        if row:
            return parse_json_quote({k.strip(): v for k, v in row.items() if k}, symbol, source="csv")
    raise MarketError("could not parse tabular quote")


def demo_quote(symbol: str) -> Quote:
    """Offline deterministic book so the desk works with no network."""
    sym = (symbol or "DEMO").strip().upper() or "DEMO"
    digest = hashlib.sha256(sym.encode("utf-8")).hexdigest()
    n = int(digest[:8], 16)
    spot = 15.0 + (n % 48_500) / 100.0
    vol = 0.12 + (int(digest[8:12], 16) % 400) / 1000.0
    last = round(spot, 4)
    bid = round(last * 0.9992, 4)
    ask = round(last * 1.0008, 4)
    prev = round(last * 0.997, 4)
    change = round(last - prev, 4)
    return Quote(
        symbol=sym,
        spot=last,
        source="demo",
        name=f"Demo {sym}",
        vol=round(vol, 4),
        asof="session",
        bid=bid,
        ask=ask,
        last=last,
        prev_close=prev,
        change=change,
        change_pct=round(100.0 * change / prev, 4),
        volume=float(10_000 + n % 90_000),
    )


def split_symbols(text: str) -> list[str]:
    parts = re.split(r"[\s,;]+", (text or "").upper())
    out: list[str] = []
    for part in parts:
        if part and part not in out:
            out.append(part)
        if len(out) >= 16:
            break
    return out


def _host_of(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host


def validate_feed_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise InputError("feed URL is empty")
    rendered = text.replace("{symbol}", "TEST").replace("{key}", "KEY")
    parsed = urlparse(rendered)
    if parsed.scheme not in _SAFE_SCHEMES:
        raise MarketError("feed URL must be http or https")
    if not parsed.netloc:
        raise MarketError("feed URL is missing a host")
    host = (parsed.hostname or "").lower()
    if host in _BLOCKED_HOSTS or host.startswith("169.254."):
        raise MarketError("refusing a metadata/link-local feed host")
    return text


def render_url(template: str, symbol: str, *, key: str | None = None) -> str:
    validate_feed_url(template)
    url = template.replace("{symbol}", symbol)
    if "{key}" in url:
        if not key:
            raise InputError("this venue URL needs an API key ({key})")
        url = url.replace("{key}", key)
    if "{symbol}" not in template and "symbol=" not in url.lower():
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}symbol={symbol}"
    return url


def apply_preset(preset: str, *, url: str | None = None, field: str | None = None, header_name: str | None = None) -> dict[str, str]:
    spec = PRESETS.get((preset or "").lower())
    if not spec:
        return {"url": url or "", "field": field or "", "header_name": header_name or ""}
    return {
        "url": url or spec["url"],
        "field": field if field not in (None, "") else spec["field"],
        "header_name": header_name if header_name not in (None, "") else spec["header_name"],
    }


class _Breaker:
    __slots__ = ("fails", "open_until")

    def __init__(self) -> None:
        self.fails: list[float] = []
        self.open_until = 0.0

    def guard(self) -> None:
        if time.monotonic() < self.open_until:
            raise MarketError("feed circuit open; waiting out a failing venue")

    def ok(self) -> None:
        self.fails.clear()
        self.open_until = 0.0

    def fail(self) -> None:
        now = time.monotonic()
        self.fails = [t for t in self.fails if now - t < 30.0]
        self.fails.append(now)
        if len(self.fails) >= 3:
            self.open_until = now + 15.0


_cache: dict[str, tuple[float, Quote]] = {}
_cache_lock = threading.Lock()
_breakers: dict[str, _Breaker] = {}
_breakers_lock = threading.Lock()


def reset_runtime() -> None:
    """Drop cache and circuit state. Used by tests."""
    with _cache_lock:
        _cache.clear()
    with _breakers_lock:
        _breakers.clear()


def _breaker_for(host: str) -> _Breaker:
    with _breakers_lock:
        return _breakers.setdefault(host or "local", _Breaker())


def _cache_get(key: str, ttl: float) -> Quote | None:
    if ttl <= 0:
        return None
    with _cache_lock:
        hit = _cache.get(key)
    if not hit:
        return None
    stored_at, quote = hit
    if time.monotonic() - stored_at <= ttl:
        return replace(quote, cached=True, stale=False)
    return None


def _cache_stale(key: str) -> Quote | None:
    with _cache_lock:
        hit = _cache.get(key)
    if not hit:
        return None
    return replace(hit[1], cached=True, stale=True)


def _cache_put(key: str, quote: Quote) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), quote)


def fetch_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
    retries: int = 2,
) -> bytes:
    validate_feed_url(url)
    host = _host_of(url)
    breaker = _breaker_for(host)
    breaker.guard()
    req_headers = {"User-Agent": "ArgentumStudio/1.5", "Accept": "application/json,text/csv,*/*"}
    if headers:
        req_headers.update({k: v for k, v in headers.items() if k and v})
    last_error: Exception | None = None
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        request = Request(url, headers=req_headers, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                final = urlparse(response.geturl())
                if final.scheme not in _SAFE_SCHEMES:
                    raise MarketError("refusing a redirected non-http feed")
                final_host = (final.hostname or "").lower()
                if final_host in _BLOCKED_HOSTS or final_host.startswith("169.254."):
                    raise MarketError("refusing a redirected metadata host")
                data = response.read(_MAX_BYTES + 1)
        except HTTPError as exc:
            last_error = MarketError(f"feed HTTP {exc.code}")
            if exc.code in {400, 401, 403, 404, 410} or attempt + 1 == attempts:
                breaker.fail()
                raise last_error from exc
        except URLError as exc:
            last_error = MarketError(f"feed unreachable: {exc.reason}")
        except TimeoutError as exc:
            last_error = MarketError("feed timed out")
            last_error.__cause__ = exc
        else:
            if len(data) > _MAX_BYTES:
                breaker.fail()
                raise MarketError("feed response too large")
            breaker.ok()
            return data
        if attempt + 1 < attempts:
            time.sleep(0.12 * (2**attempt))
    breaker.fail()
    if last_error:
        raise last_error
    raise MarketError("feed unreachable")


def stooq_url(symbol: str) -> str:
    sym = symbol.strip().lower()
    if not re.search(r"\.[a-z]{1,4}$", sym):
        sym = f"{sym}.us"
    return f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"


def _decode_body(body: bytes, symbol: str, *, field: str | None, source: str) -> Quote:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        raise MarketError("empty feed body")
    if text[0] in "{[":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MarketError("custom market did not return JSON") from exc
        return parse_json_quote(payload, symbol, field=field or None, source=source)
    return parse_tabular_quote(text, symbol)


def fetch_quote(
    symbol: str,
    *,
    source: str = "demo",
    url: str | None = None,
    field: str | None = None,
    header_name: str | None = None,
    header_value: str | None = None,
    timeout: float = 8.0,
    retries: int = 2,
    cache_ttl: float = 5.0,
    stale_ok: bool = True,
    preset: str | None = None,
) -> Quote:
    source = (source or "demo").strip().lower()
    symbol = (symbol or "").strip()
    if not symbol:
        raise InputError("symbol is required")
    if preset:
        applied = apply_preset(preset, url=url, field=field, header_name=header_name)
        url, field, header_name = applied["url"], applied["field"], applied["header_name"]
    started = time.perf_counter()
    cache_key = f"{source}|{symbol.upper()}|{url or ''}|{field or ''}"
    if source == "demo":
        return replace(demo_quote(symbol), latency_ms=round((time.perf_counter() - started) * 1000, 2))
    cached = _cache_get(cache_key, cache_ttl)
    if cached is not None:
        return cached
    try:
        if source == "stooq":
            raw = fetch_bytes(stooq_url(symbol), timeout=timeout, retries=retries)
            quote = parse_stooq_csv(raw.decode("utf-8", errors="replace"), symbol)
        elif source in {"http", "custom", "own"}:
            if not url:
                raise InputError("custom market needs a URL with {symbol}")
            headers: dict[str, str] = {}
            key = header_value if header_value and header_value != "••••" else None
            rendered = render_url(url, symbol, key=key if "{key}" in url else None)
            if header_name and key and "{key}" not in url:
                headers[header_name] = key
            body = fetch_bytes(rendered, headers=headers or None, timeout=timeout, retries=retries)
            quote = _decode_body(body, symbol, field=field, source="http")
        else:
            raise InputError(f"unknown feed source {source!r}")
    except (MarketError, InputError, OSError, TimeoutError, ValueError):
        stale = _cache_stale(cache_key) if stale_ok else None
        if stale is not None:
            return stale
        raise
    quote = replace(quote, latency_ms=round((time.perf_counter() - started) * 1000, 2))
    _cache_put(cache_key, quote)
    return quote


def fetch_quotes(symbols: list[str], **kwargs: Any) -> tuple[list[Quote], dict[str, str]]:
    names = split_symbols(",".join(symbols) if len(symbols) == 1 and "," in symbols[0] else " ".join(symbols))
    if not names:
        return [], {}
    quotes: list[Quote] = []
    errors: dict[str, str] = {}
    if len(names) == 1:
        try:
            quotes.append(fetch_quote(names[0], **kwargs))
        except (MarketError, InputError, OSError, ValueError) as exc:
            errors[names[0]] = str(exc)
        return quotes, errors
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        futs = {pool.submit(fetch_quote, name, **kwargs): name for name in names}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                quotes.append(fut.result())
            except (MarketError, InputError, OSError, ValueError) as exc:
                errors[name] = str(exc)
    quotes.sort(key=lambda q: names.index(q.symbol) if q.symbol in names else 99)
    return quotes, errors


def probe_feed(symbol: str, **kwargs: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        quote = fetch_quote(symbol, cache_ttl=0, stale_ok=False, **kwargs)
    except (MarketError, InputError, OSError, ValueError) as exc:
        return {
            "ok": False,
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    payload = quote.as_dict()
    fields = [key for key, value in payload.items() if value not in (None, "", False, [])]
    return {
        "ok": True,
        "quote": payload,
        "latency_ms": payload.get("latency_ms") or round((time.perf_counter() - started) * 1000, 1),
        "fields": fields,
    }


def ingest_quote(payload: dict[str, Any], *, source: str = "push") -> Quote:
    symbol = str(payload.get("symbol") or payload.get("ticker") or "").strip()
    if not symbol:
        raise InputError("ingest needs a symbol")
    return parse_json_quote(payload, symbol, field=str(payload.get("field") or "") or None, source=source)
