"""File-driven vanilla portfolio risk reports.

The format is intentionally small and deterministic so a desk can review it,
put it in version control, and reproduce a mark without a database.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from argentum._version import VERSION
from argentum.book import Book, VanillaPosition
from argentum.errors import InputError
from argentum.scenario import Shock, default_shocks, scenario_table
from argentum.types import OptionType

MAX_POSITIONS = 10_000
_REQUIRED = ("spot", "strike", "vol", "texp")


def _number(row: Mapping[str, Any], key: str, default: float | None = None) -> float:
    raw = row.get(key, default)
    if raw is None or raw == "":
        if default is None:
            raise InputError(f"portfolio row is missing {key!r}")
        raw = default
    if isinstance(raw, bool):
        raise InputError(f"portfolio {key!r} must be a number, got {raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise InputError(f"portfolio {key!r} must be a number, got {raw!r}") from exc
    if not math.isfinite(value):
        raise InputError(f"portfolio {key!r} must be finite, got {raw!r}")
    return value


def position_from_mapping(row: Mapping[str, Any], *, row_number: int | None = None) -> VanillaPosition:
    """Validate one CSV/JSON row and turn it into a priced position."""
    where = f"row {row_number}: " if row_number is not None else ""
    try:
        for key in _REQUIRED:
            if row.get(key) is None or row.get(key) == "":
                raise InputError(f"portfolio row is missing {key!r}")
        spot = _number(row, "spot")
        strike = _number(row, "strike")
        vol = _number(row, "vol")
        texp = _number(row, "texp")
        if spot <= 0 or strike <= 0 or vol <= 0 or texp <= 0:
            raise InputError("spot, strike, vol, and texp must all be positive")
        kind_raw = str(row.get("type", row.get("option_type", "call"))).strip().lower()
        if kind_raw in {"call", "c"}:
            kind = OptionType.CALL
        elif kind_raw in {"put", "p"}:
            kind = OptionType.PUT
        else:
            raise InputError(f"option type must be call or put, got {kind_raw!r}")
        tag = str(row.get("tag", "")).strip()
        if len(tag) > 128:
            raise InputError("tag must be at most 128 characters")
        raw_quantity = row.get("quantity")
        quantity = (
            _number(row, "quantity")
            if raw_quantity is not None and raw_quantity != ""
            else _number(row, "qty", 1.0)
        )
        return VanillaPosition(
            quantity=quantity,
            spot=spot,
            strike=strike,
            rate=_number(row, "rate", 0.0),
            div=_number(row, "div", 0.0),
            vol=vol,
            texp=texp,
            option_type=kind,
            tag=tag,
        )
    except InputError as exc:
        raise InputError(f"{where}{exc}") from exc


def book_from_rows(rows: Iterable[Mapping[str, Any]]) -> Book:
    book = Book()
    for number, row in enumerate(rows, start=1):
        if number > MAX_POSITIONS:
            raise InputError(f"portfolio exceeds the {MAX_POSITIONS:,}-position limit")
        if not isinstance(row, Mapping):
            raise InputError(f"row {number}: expected an object")
        book.add(position_from_mapping(row, row_number=number))
    if not book.positions:
        raise InputError("portfolio contains no positions")
    return book


def load_portfolio(path: str | Path) -> Book:
    """Load a UTF-8 ``.csv`` or ``.json`` vanilla portfolio."""
    source = Path(path)
    if not source.is_file():
        raise InputError(f"portfolio file not found: {source}")
    try:
        text = source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("portfolio must be UTF-8 text") from exc
    suffix = source.suffix.lower()
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise InputError("portfolio CSV needs a header row")
        return book_from_rows(reader)
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError(f"invalid portfolio JSON: {exc.msg} at line {exc.lineno}") from exc
        rows = payload.get("positions") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise InputError("portfolio JSON must be a list or an object with a positions list")
        return book_from_rows(rows)
    raise InputError("portfolio file must end in .csv or .json")


def portfolio_report(book: Book, shocks: list[Shock] | None = None) -> dict[str, Any]:
    """Return a stable, JSON-serialisable desk summary and scenario ladder."""
    marked = book.price()
    by_tag = book.by_tag()
    inputs = [
        {
            "tag": pos.tag,
            "quantity": pos.quantity,
            "spot": pos.spot,
            "strike": pos.strike,
            "rate": pos.rate,
            "div": pos.div,
            "vol": pos.vol,
            "texp": pos.texp,
            "type": OptionType(pos.option_type).value,
        }
        for pos in book.positions
    ]
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {
        "schema": "argentum.portfolio-risk.v1",
        "argentum_version": VERSION,
        "model_engine": "black_scholes",
        "input_sha256": hashlib.sha256(canonical).hexdigest(),
        "input_positions": inputs,
        "positions": len(book.positions),
        "summary": {
            "npv": marked.npv,
            "currency": marked.currency,
            "engine": marked.engine,
            "greeks": marked.greeks.as_dict() if marked.greeks else {},
        },
        "by_tag": {
            tag: {
                "npv": result.npv,
                "greeks": result.greeks.as_dict() if result.greeks else {},
            }
            for tag, result in sorted(by_tag.items())
        },
        "scenarios": scenario_table(book, shocks if shocks is not None else default_shocks()),
        "disclaimer": "Research and desk prototyping only; validate models and market data before production use.",
    }


def report_text(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    greeks = summary["greeks"]
    lines = [
        "Argentum portfolio risk",
        "=======================",
        f"positions  {report['positions']}",
        f"NPV        {summary['npv']:,.8f} {summary['currency']}",
        f"delta      {greeks.get('delta', 0.0):,.8f}",
        f"gamma      {greeks.get('gamma', 0.0):,.8f}",
        f"vega       {greeks.get('vega', 0.0):,.8f}",
        "",
        f"{'scenario':<20} {'NPV':>16} {'PnL':>16} {'delta':>14} {'vega':>14}",
        "-" * 84,
    ]
    for row in report["scenarios"]:
        lines.append(
            f"{str(row['label']):<20.20} {row['npv']:>16,.6f} {row['pnl']:>16,.6f} "
            f"{row['delta']:>14,.6f} {row['vega']:>14,.6f}"
        )
    lines.extend(["", str(report["disclaimer"])])
    return "\n".join(lines) + "\n"


def report_csv(report: Mapping[str, Any]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["scenario", "npv", "pnl", "delta", "vega"])
    for row in report["scenarios"]:
        writer.writerow([row["label"], row["npv"], row["pnl"], row["delta"], row["vega"]])
    return stream.getvalue()
