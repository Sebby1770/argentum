import json
import stat
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

import pytest

from argentum import studio as studio_mod
from argentum.book import Book, VanillaPosition
from argentum.cli import main
from argentum.errors import MarketError
from argentum.feeds import (
    coerce_number,
    demo_quote,
    extract_spot,
    fetch_quote,
    fetch_quotes,
    ingest_quote,
    parse_json_quote,
    parse_stooq_csv,
    probe_feed,
    render_url,
    reset_runtime,
    split_symbols,
    validate_feed_url,
)
from argentum.market import Market
from argentum.studio import ingest_payload, mark_market_payload, probe_payload, quote_payload, save_feed_config, tape_payload, watch_payload
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date
from argentum.types import OptionType


@pytest.fixture(autouse=True)
def isolated_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(studio_mod, "FEED_FILE", tmp_path / "feed.json")
    reset_runtime()


def test_demo_quote_is_deterministic():
    a = demo_quote("aapl")
    b = demo_quote("AAPL")
    assert a.spot == b.spot
    assert a.spot > 0
    assert a.bid is not None and a.ask is not None and a.ask >= a.bid
    assert demo_quote("MSFT").spot != a.spot


def test_stooq_csv_parse():
    csv = "Symbol,Date,Time,Open,High,Low,Close,Volume\nAAPL.US,2026-08-21,16:00:00,220.1,221,218.5,219.4,1000\n"
    q = parse_stooq_csv(csv, "AAPL")
    assert q.spot == 219.4
    assert q.source == "stooq"
    assert q.volume == 1000


def test_json_spot_aliases():
    assert extract_spot({"last": 10.5}) == 10.5
    assert extract_spot({"data": {"price": 11}}) == 11
    q = parse_json_quote({"spot": 99.1, "vol": 0.3, "symbol": "xyz"}, "abc")
    assert q.spot == 99.1 and q.vol == 0.3 and q.symbol == "XYZ"
    zero = parse_json_quote({"last": 10, "div": 0.0, "name": "Own X"}, "x")
    assert zero.div == 0.0
    assert zero.name == "Own X"


def test_quote_units_are_explicit_decimal_fractions():
    with pytest.raises(MarketError, match="decimal fraction"):
        parse_json_quote({"spot": 100, "vol": 20}, "X")
    with pytest.raises(MarketError, match="decimal fraction"):
        parse_json_quote({"spot": 100, "rate": 5}, "X")
    with pytest.raises(MarketError, match="spot must be a positive finite number"):
        parse_json_quote({"spot": -1}, "X")
    with pytest.raises(MarketError, match="spot must be a positive finite number"):
        parse_json_quote(-1, "X")
    with pytest.raises(MarketError, match="spot must be a positive finite number"):
        parse_json_quote(float("inf"), "X")


def test_nested_field_path():
    assert extract_spot({"data": {"last": 7.25}}, "data.last") == 7.25


def test_vendor_quote_shapes():
    assert parse_json_quote({"c": 188.2, "pc": 185.0, "d": 3.2}, "AAPL").spot == 188.2
    assert parse_json_quote({"results": {"p": 12.5}}, "X").spot == 12.5
    assert parse_json_quote({"latestPrice": 9.1}, "IBM").spot == 9.1
    av = {"Global Quote": {"05. price": "123.45", "01. symbol": "MSFT"}}
    assert extract_spot(av, "Global Quote.05. price") == 123.45
    yahoo = {"chart": {"result": [{"meta": {"regularMarketPrice": 44.0}}]}}
    assert extract_spot(yahoo, "chart.result.0.meta.regularMarketPrice") == 44.0
    assert parse_json_quote({"bid": 10.0, "ask": 10.4}, "Y").spot == pytest.approx(10.2)
    assert coerce_number("$1,234.50") == 1234.5
    wrapped = {"quotes": [{"symbol": "AAA", "last": 1}, {"symbol": "BBB", "last": 2}]}
    assert parse_json_quote(wrapped, "BBB").spot == 2


def test_url_must_be_http():
    try:
        validate_feed_url("file:///etc/passwd")
        raise AssertionError("should have rejected file")
    except MarketError:
        pass
    try:
        validate_feed_url("http://169.254.169.254/latest/meta")
        raise AssertionError("should have rejected metadata")
    except MarketError:
        pass
    url = render_url("https://venue.test/q/{symbol}", "MSFT")
    assert url.endswith("/q/MSFT")


def test_studio_demo_quote_and_mark():
    q = quote_payload({"source": "demo", "symbol": "IBM"})
    assert q["ok"] and q["quote"]["spot"] > 0
    assert q["quote"]["bid"] is not None
    marked = mark_market_payload({"source": "demo", "symbol": "IBM"})
    assert marked["quote"]["symbol"] == "IBM"
    assert marked["npv"] > 0
    assert marked["spot"] == q["quote"]["spot"]
    tape = tape_payload()
    assert tape["n"] >= 1
    assert tape["prints"][0]["symbol"] == "IBM"


def test_save_feed_preserves_http_secret_and_clears_on_demo():
    public = save_feed_config(
        {
            "source": "http",
            "symbol": "AAA",
            "url": "https://venue.test/q/{symbol}",
            "header_name": "Authorization",
            "header_value": "secret-token",
            "watchlist": "AAA,BBB",
        }
    )
    assert public["has_secret"] is True
    assert public["header_value"] == "••••"
    assert public["watchlist"] == "AAA,BBB"
    kept = save_feed_config({"source": "http", "symbol": "BBB", "header_value": "••••"})
    assert kept["symbol"] == "BBB"
    assert kept["has_secret"] is True
    raw = json.loads(studio_mod.FEED_FILE.read_text(encoding="utf-8"))
    assert raw["header_value"] == "secret-token"
    assert stat.S_IMODE(studio_mod.FEED_FILE.stat().st_mode) == 0o600
    cleared = save_feed_config({"source": "demo", "symbol": "CCC"})
    assert cleared["has_secret"] is False
    assert cleared["header_value"] == ""


def _serve(handler_cls, threaded=False):
    cls = ThreadingHTTPServer if threaded else HTTPServer
    server = cls(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _studio_server():
    server = _serve(studio_mod.StudioHandler, threaded=True)
    server.allowed_origins = ()
    server.trusted_hosts = ("127.0.0.1", "localhost", "::1")
    server.csrf_token = "test-csrf-token"
    server.ingest_token = ""
    server.allow_unauthenticated_ingest = False
    return server


def _studio_request(server, method, path, *, body=None, headers=None):
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    request_headers = {"Host": f"127.0.0.1:{server.server_address[1]}", **(headers or {})}
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    payload = response.read()
    result = response.status, dict(response.getheaders()), payload
    connection.close()
    return result


def test_studio_rejects_dns_rebinding_and_cross_site_browser_requests():
    server = _studio_server()
    try:
        status, _, _ = _studio_request(server, "GET", "/", headers={"Host": "attacker.example"})
        assert status == 421
        status, _, _ = _studio_request(
            server,
            "GET",
            "/api/quote?source=demo&symbol=AAPL",
            headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
        )
        assert status == 403
        server.allowed_origins = ("https://trusted.example",)
        status, headers, payload = _studio_request(
            server,
            "GET",
            "/api/session",
            headers={"Origin": "https://trusted.example", "Sec-Fetch-Site": "cross-site"},
        )
        assert status == 200 and json.loads(payload)["csrf"] == "test-csrf-token"
        assert headers["Access-Control-Allow-Origin"] == "https://trusted.example"
        status, _, payload = _studio_request(
            server,
            "GET",
            "/api/session",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        assert status == 200 and json.loads(payload)["csrf"] == "test-csrf-token"
    finally:
        server.shutdown()
        server.server_close()


def test_studio_requires_csrf_for_saved_feed_and_token_for_ingest():
    server = _studio_server()
    body = json.dumps({"source": "demo", "symbol": "AAPL"})
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        headers = {"Content-Type": "application/json", "Origin": origin, "Sec-Fetch-Site": "same-origin"}
        status, _, _ = _studio_request(server, "POST", "/api/feed", body=body, headers=headers)
        assert status == 403
        status, _, _ = _studio_request(
            server,
            "POST",
            "/api/feed",
            body=body,
            headers={**headers, "X-Argentum-CSRF": "test-csrf-token"},
        )
        assert status == 200
        ingest = json.dumps({"symbol": "AAPL", "last": 100})
        status, _, _ = _studio_request(
            server, "POST", "/api/ingest", body=ingest, headers={"Content-Type": "application/json"}
        )
        assert status == 403
        server.ingest_token = "push-secret"
        status, _, _ = _studio_request(
            server,
            "POST",
            "/api/ingest",
            body=ingest,
            headers={"Content-Type": "application/json", "X-Argentum-Ingest-Token": "push-secret"},
        )
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_studio_rejects_non_json_and_oversized_posts_and_sets_security_headers():
    server = _studio_server()
    try:
        status, _, _ = _studio_request(server, "POST", "/api/book", body="x", headers={"Content-Type": "text/plain"})
        assert status == 415
        status, _, _ = _studio_request(
            server,
            "POST",
            "/api/book",
            body=b"",
            headers={"Content-Type": "application/json", "Content-Length": "1000001"},
        )
        assert status == 413
        status, headers, _ = _studio_request(server, "GET", "/")
        assert status == 200
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        assert "Access-Control-Allow-Origin" not in headers
    finally:
        server.shutdown()
        server.server_close()


def test_own_http_json_venue():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            symbol = self.path.rsplit("/", 1)[-1]
            body = json.dumps({"symbol": symbol, "last": 321.5, "vol": 0.22, "bid": 321.4, "ask": 321.6}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = _serve(Handler)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/quote/{{symbol}}"
        q = fetch_quote("XYZ", source="http", url=url, cache_ttl=0)
        assert q.spot == 321.5
        assert q.symbol == "XYZ"
        assert q.vol == 0.22
        assert q.bid == 321.4
        marked = mark_market_payload({"source": "http", "symbol": "XYZ", "url": url})
        assert marked["spot"] == 321.5
        assert marked["npv"] > 0
        probed = probe_payload({"source": "http", "symbol": "XYZ", "url": url})
        assert probed["ok"] is True
        assert "spot" in probed["fields"]
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

    server = _serve(Handler)
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


def test_batch_watch_and_cache():
    class Handler(BaseHTTPRequestHandler):
        hits = 0

        def do_GET(self):  # noqa: N802
            Handler.hits += 1
            symbol = self.path.rsplit("/", 1)[-1]
            body = json.dumps({"symbol": symbol, "last": 10.0 + Handler.hits}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = _serve(Handler, threaded=True)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/quote/{{symbol}}"
        quotes, errors = fetch_quotes(["AA", "BB"], source="http", url=url, cache_ttl=0)
        assert not errors and {q.symbol for q in quotes} == {"AA", "BB"}
        first = fetch_quote("AA", source="http", url=url, cache_ttl=30)
        hits = Handler.hits
        second = fetch_quote("AA", source="http", url=url, cache_ttl=30)
        assert second.cached is True
        assert Handler.hits == hits
        assert first.spot == second.spot
        watched = watch_payload({"source": "http", "url": url, "symbols": "AA,BB"})
        assert watched["ok"] and len(watched["quotes"]) == 2
    finally:
        server.shutdown()
        server.server_close()


def test_retries_then_circuit():
    class Handler(BaseHTTPRequestHandler):
        n = 0

        def do_GET(self):  # noqa: N802
            Handler.n += 1
            self.send_error(500)

        def log_message(self, *_args):
            return

    server = _serve(Handler)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/q/{{symbol}}"
        for _ in range(3):
            with pytest.raises(MarketError):
                fetch_quote("Z", source="http", url=url, retries=0, cache_ttl=0, stale_ok=False)
        with pytest.raises(MarketError, match="circuit"):
            fetch_quote("Z", source="http", url=url, retries=0, cache_ttl=0, stale_ok=False)
    finally:
        server.shutdown()
        server.server_close()


def test_ingest_push_and_book_remap():
    pushed = ingest_payload({"symbol": "QQQ", "last": 401.25, "bid": 401.2, "ask": 401.3})
    assert pushed["quote"]["spot"] == 401.25
    q = ingest_quote({"symbol": "SPY", "last": 500.0})
    assert q.source == "push" and q.spot == 500
    book = Book()
    book.add(VanillaPosition(1, 100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, tag="QQQ"))
    live = book.remap_spots({"QQQ": 401.25})
    assert live.positions[0].spot == 401.25
    as_of = Date(2026, 8, 24)
    mkt = Market(as_of, YieldCurve.flat(as_of, 0.03))
    mkt.apply_quotes([q])
    assert mkt.spot("SPY") == 500.0


def test_cli_quote(capsys):
    rc = main(["quote", "AAPL", "--source", "demo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "AAPL" in out


def test_split_symbols_and_probe_demo():
    assert split_symbols("aapl, msft; nvda") == ["AAPL", "MSFT", "NVDA"]
    probed = probe_feed("AAPL", source="demo")
    assert probed["ok"] and probed["quote"]["symbol"] == "AAPL"
