import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from argentum import studio as studio_mod
from argentum.errors import MarketError
from argentum.feeds import (
    demo_quote,
    extract_spot,
    fetch_quote,
    parse_json_quote,
    parse_stooq_csv,
    render_url,
    validate_feed_url,
)
from argentum.studio import mark_market_payload, quote_payload, save_feed_config


@pytest.fixture(autouse=True)
def isolated_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(studio_mod, "FEED_FILE", tmp_path / "feed.json")


def test_demo_quote_is_deterministic():
    a = demo_quote("aapl")
    b = demo_quote("AAPL")
    assert a.spot == b.spot
    assert a.spot > 0
    assert demo_quote("MSFT").spot != a.spot


def test_stooq_csv_parse():
    csv = "Symbol,Date,Time,Open,High,Low,Close,Volume\nAAPL.US,2026-08-21,16:00:00,220.1,221,218.5,219.4,1000\n"
    q = parse_stooq_csv(csv, "AAPL")
    assert q.spot == 219.4
    assert q.source == "stooq"


def test_json_spot_aliases():
    assert extract_spot({"last": 10.5}) == 10.5
    assert extract_spot({"data": {"price": 11}}) == 11
    q = parse_json_quote({"spot": 99.1, "vol": 0.3, "symbol": "xyz"}, "abc")
    assert q.spot == 99.1 and q.vol == 0.3 and q.symbol == "XYZ"
    zero = parse_json_quote({"last": 10, "div": 0.0, "name": "Own X"}, "x")
    assert zero.div == 0.0
    assert zero.name == "Own X"


def test_nested_field_path():
    assert extract_spot({"data": {"last": 7.25}}, "data.last") == 7.25


def test_url_must_be_http():
    try:
        validate_feed_url("file:///etc/passwd")
        assert False, "should have rejected file"
    except MarketError:
        pass
    url = render_url("https://venue.test/q/{symbol}", "MSFT")
    assert url.endswith("/q/MSFT")


def test_studio_demo_quote_and_mark():
    q = quote_payload({"source": "demo", "symbol": "IBM"})
    assert q["ok"] and q["quote"]["spot"] > 0
    marked = mark_market_payload({"source": "demo", "symbol": "IBM"})
    assert marked["quote"]["symbol"] == "IBM"
    assert marked["npv"] > 0
    assert marked["spot"] == q["quote"]["spot"]


def test_save_feed_preserves_http_secret_and_clears_on_demo():
    public = save_feed_config(
        {
            "source": "http",
            "symbol": "AAA",
            "url": "https://venue.test/q/{symbol}",
            "header_name": "Authorization",
            "header_value": "secret-token",
        }
    )
    assert public["has_secret"] is True
    assert public["header_value"] == "••••"
    kept = save_feed_config({"source": "http", "symbol": "BBB", "header_value": "••••"})
    assert kept["symbol"] == "BBB"
    assert kept["has_secret"] is True
    raw = json.loads(studio_mod.FEED_FILE.read_text(encoding="utf-8"))
    assert raw["header_value"] == "secret-token"
    cleared = save_feed_config({"source": "demo", "symbol": "CCC"})
    assert cleared["has_secret"] is False
    assert cleared["header_value"] == ""


def _serve_quotes(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_own_http_json_venue():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            symbol = self.path.rsplit("/", 1)[-1]
            body = json.dumps({"symbol": symbol, "last": 321.5, "vol": 0.22}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = _serve_quotes(Handler)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/quote/{{symbol}}"
        q = fetch_quote("XYZ", source="http", url=url)
        assert q.spot == 321.5
        assert q.symbol == "XYZ"
        assert q.vol == 0.22
        marked = mark_market_payload({"source": "http", "symbol": "XYZ", "url": url})
        assert marked["spot"] == 321.5
        assert marked["npv"] > 0
    finally:
        server.shutdown()
        server.server_close()


def test_quote_payload_uses_saved_secret_not_placeholder():
    class Handler(BaseHTTPRequestHandler):
        seen = []

        def do_GET(self):  # noqa: N802
            Handler.seen.append(self.headers.get("Authorization"))
            if self.headers.get("Authorization") != "Bearer desk":
                self.send_error(401)
                return
            body = json.dumps({"spot": 50.25}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = _serve_quotes(Handler)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/quote/{{symbol}}"
        save_feed_config(
            {
                "source": "http",
                "symbol": "OWN",
                "url": url,
                "header_name": "Authorization",
                "header_value": "Bearer desk",
            }
        )
        quoted = quote_payload({"source": "http", "symbol": "OWN", "url": url, "header_value": "••••"})
        assert quoted["quote"]["spot"] == 50.25
        assert Handler.seen == ["Bearer desk"]
    finally:
        server.shutdown()
        server.server_close()
