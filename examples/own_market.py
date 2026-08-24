"""A tiny JSON venue so you can point Argentum at a market you control.

Run::

    PYTHONPATH=src python3 examples/own_market.py --port 8791 --no-auth

Then in Studio → Market:

    URL    http://127.0.0.1:8791/quote/{symbol}
    Batch  http://127.0.0.1:8791/quotes?symbols=AAPL,MSFT

Push a print into Studio (from your matching engine)::

    curl -X POST http://127.0.0.1:8787/api/ingest \\
         -H 'Content-Type: application/json' \\
         -d '{"symbol":"AAPL","last":227.1,"bid":227.05,"ask":227.15}'
"""

from __future__ import annotations

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def quote_for(symbol: str) -> dict[str, object]:
    sym = (symbol or "DEMO").strip().upper() or "DEMO"
    digest = hashlib.sha256(sym.encode("utf-8")).hexdigest()
    n = int(digest[:8], 16)
    spot = 15.0 + (n % 48_500) / 100.0
    last = round(spot, 4)
    vol = 0.12 + (int(digest[8:12], 16) % 400) / 1000.0
    bid = round(last * 0.9992, 4)
    ask = round(last * 1.0008, 4)
    prev = round(last * 0.997, 4)
    return {
        "symbol": sym,
        "name": f"Own {sym}",
        "spot": last,
        "last": last,
        "bid": bid,
        "ask": ask,
        "prev_close": prev,
        "change": round(last - prev, 4),
        "volume": 10_000 + n % 90_000,
        "vol": round(vol, 4),
        "rate": 0.05,
        "div": 0.0,
        "currency": "USD",
        "asof": "session",
        "source": "own-market",
    }


class Venue(BaseHTTPRequestHandler):
    server_version = "ArgentumOwnMarket/1.4"

    def log_message(self, fmt: str, *args: object) -> None:
        print("[own-market] " + (fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        auth = self.headers.get("Authorization", "")
        expected = getattr(self.server, "token", "")
        if expected and auth != expected:
            self._send(401, {"error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        qs = parse_qs(parsed.query)
        if parts and parts[0] == "quotes":
            raw = (qs.get("symbols") or qs.get("symbol") or [""])[0]
            symbols = [s.strip() for s in raw.split(",") if s.strip()] or ["AAPL"]
            self._send(200, {"quotes": [quote_for(s) for s in symbols[:16]]})
            return
        symbol = ""
        if len(parts) >= 2 and parts[0] == "quote":
            symbol = parts[1]
        if not symbol:
            symbol = (qs.get("symbol") or [""])[0]
        if not symbol:
            self._send(400, {"error": "symbol required"})
            return
        self._send(200, quote_for(symbol))

    def _send(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = "127.0.0.1", port: int = 8791, token: str = "Bearer desk") -> None:
    httpd = ThreadingHTTPServer((host, port), Venue)
    httpd.token = token  # type: ignore[attr-defined]
    print(f"Own market  http://{host}:{port}/quote/{{symbol}}")
    print(f"Batch       http://{host}:{port}/quotes?symbols=AAPL,MSFT")
    if token:
        print(f"Authorization: {token}")
    httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Argentum sample JSON venue")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--token", default="Bearer desk")
    parser.add_argument("--no-auth", action="store_true")
    args = parser.parse_args()
    serve(args.host, args.port, "" if args.no_auth else args.token)
