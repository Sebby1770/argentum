"""Market-data adapters: demo book, Stooq, or a user's own HTTP JSON venue.

A custom venue is any HTTPS (or HTTP) URL that returns a quote. Put ``{symbol}``
in the path or query. Argentum looks for a last/spot/price/close field, then
hands that number to the pricing engines. This is a mark, not an order gateway.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from argentum.errors import InputError, MarketError

_SPOT_KEYS = ("spot", "last", "price", "close", "px", "mid", "ltp", "trade")


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
    raw: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("raw", None)
        return payload


def demo_quote(symbol: str) -> Quote:
    """Offline deterministic book so the desk works with no network."""
    sym = (symbol or "DEMO").strip().upper() or "DEMO"
    digest = hashlib.sha256(sym.encode("utf-8")).hexdigest()
    n = int(digest[:8], 16)
    spot = 15.0 + (n % 48_500) / 100.0
    vol = 0.12 + (int(digest[8:12], 16) % 400) / 1000.0
    return Quote(symbol=sym, spot=round(spot, 4), source="demo", name=f"Demo {sym}", vol=round(vol, 4), asof="session")


def parse_stooq_csv(text: str, symbol: str) -> Quote:
    reader = csv.DictReader(io.StringIO(text.strip()))
    row = next(reader, None)
    if not row:
        raise MarketError("Stooq returned an empty table")
    close = row.get("Close") or row.get("close")
    if close in (None, "", "N/D"):
        raise MarketError(f"Stooq has no close for {symbol!r}")
    return Quote(
        symbol=(row.get("Symbol") or symbol).upper(),
        spot=float(close),
        source="stooq",
        asof=(row.get("Date") or ""),
        name=symbol.upper(),
    )


def _dig(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def extract_spot(payload: Any, field: str | None = None) -> float:
    if isinstance(payload, (int, float)):
        return float(payload)
    if not isinstance(payload, dict):
        raise MarketError("quote payload must be a JSON object")
    if field:
        value = _dig(payload, field)
        if value not in (None, ""):
            return float(value)
    for key in _SPOT_KEYS:
        if key in payload and payload[key] not in (None, ""):
            return float(payload[key])
        nested = payload.get("data") or payload.get("quote") or payload.get("result")
        if isinstance(nested, dict) and key in nested:
            return float(nested[key])
    raise MarketError("could not find spot/last/price/close in the JSON quote")


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def parse_json_quote(payload: Any, symbol: str, *, field: str | None = None, source: str = "http") -> Quote:
    spot = extract_spot(payload, field)
    data = payload if isinstance(payload, dict) else {}
    vol = _first_present(data.get("vol"), data.get("iv"), data.get("implied_vol"))
    rate = _first_present(data.get("rate"), data.get("r"))
    div = _first_present(data.get("div"), data.get("dividend"), data.get("q"))
    return Quote(
        symbol=str(data.get("symbol") or symbol).upper(),
        spot=float(spot),
        source=source,
        currency=str(data.get("currency") or "USD"),
        name=str(data.get("name") or str(symbol).upper()),
        asof=str(data.get("asof") or data.get("time") or data.get("date") or ""),
        vol=float(vol) if vol not in (None, "") else None,
        rate=float(rate) if rate not in (None, "") else None,
        div=float(div) if div not in (None, "") else None,
        raw=data if isinstance(data, dict) else None,
    )


_SAFE_SCHEMES = {"http", "https"}


def validate_feed_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise InputError("feed URL is empty")
    parsed = urlparse(text.replace("{symbol}", "TEST"))
    if parsed.scheme not in _SAFE_SCHEMES:
        raise MarketError("feed URL must be http or https")
    if not parsed.netloc:
        raise MarketError("feed URL is missing a host")
    return text


def render_url(template: str, symbol: str) -> str:
    validate_feed_url(template)
    if "{symbol}" in template:
        return template.replace("{symbol}", symbol)
    sep = "&" if "?" in template else "?"
    return f"{template}{sep}symbol={symbol}"


def fetch_bytes(url: str, *, headers: dict[str, str] | None = None, timeout: float = 8.0) -> bytes:
    validate_feed_url(url)
    req_headers = {"User-Agent": "ArgentumStudio/1.3"}
    if headers:
        req_headers.update({k: v for k, v in headers.items() if k and v})
    request = Request(url, headers=req_headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            final = urlparse(response.geturl())
            if final.scheme not in _SAFE_SCHEMES:
                raise MarketError("refusing a redirected non-http feed")
            data = response.read(1_000_001)
    except HTTPError as exc:
        raise MarketError(f"feed HTTP {exc.code}") from exc
    except URLError as exc:
        raise MarketError(f"feed unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise MarketError("feed timed out") from exc
    if len(data) > 1_000_000:
        raise MarketError("feed response too large")
    return data


def stooq_url(symbol: str) -> str:
    sym = symbol.strip().lower()
    if not re.search(r"\.[a-z]{1,4}$", sym):
        sym = f"{sym}.us"
    return f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"


def fetch_quote(
    symbol: str,
    *,
    source: str = "demo",
    url: str | None = None,
    field: str | None = None,
    header_name: str | None = None,
    header_value: str | None = None,
) -> Quote:
    source = (source or "demo").strip().lower()
    symbol = (symbol or "").strip()
    if not symbol:
        raise InputError("symbol is required")
    if source == "demo":
        return demo_quote(symbol)
    if source == "stooq":
        raw = fetch_bytes(stooq_url(symbol)).decode("utf-8", errors="replace")
        return parse_stooq_csv(raw, symbol)
    if source in {"http", "custom", "own"}:
        if not url:
            raise InputError("custom market needs a URL with {symbol}")
        headers = {}
        if header_name and header_value:
            headers[header_name] = header_value
        body = fetch_bytes(render_url(url, symbol), headers=headers)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MarketError("custom market did not return JSON") from exc
        return parse_json_quote(payload, symbol, field=field or None, source="http")
    raise InputError(f"unknown feed source {source!r}")
