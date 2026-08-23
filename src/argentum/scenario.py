"""Parallel spot / vol / rate shocks on a vanilla book."""

from __future__ import annotations

from dataclasses import dataclass

from argentum.book import Book, VanillaPosition


@dataclass(frozen=True, slots=True)
class Shock:
    """Relative spot, additive vol, additive rate (e.g. 0.01, 0.01, 0.0001)."""

    d_spot: float = 0.0
    d_vol: float = 0.0
    d_rate: float = 0.0
    label: str = ""


def apply_shock(book: Book, shock: Shock) -> Book:
    out = Book()
    for pos in book.positions:
        out.add(
            VanillaPosition(
                quantity=pos.quantity,
                spot=pos.spot * (1.0 + shock.d_spot),
                strike=pos.strike,
                rate=pos.rate + shock.d_rate,
                div=pos.div,
                vol=max(pos.vol + shock.d_vol, 1e-8),
                texp=pos.texp,
                option_type=pos.option_type,
                tag=pos.tag,
            )
        )
    return out


def scenario_table(book: Book, shocks: list[Shock]) -> list[dict[str, float | str]]:
    base = book.price()
    rows: list[dict[str, float | str]] = []
    for shock in shocks:
        marked = apply_shock(book, shock).price()
        rows.append(
            {
                "label": shock.label or f"s{shock.d_spot:+.2%}/v{shock.d_vol:+.3f}/r{shock.d_rate:+.4f}",
                "npv": marked.npv,
                "pnl": marked.npv - base.npv,
                "delta": marked.greeks.delta if marked.greeks else 0.0,
                "vega": marked.greeks.vega if marked.greeks else 0.0,
            }
        )
    return rows


def default_shocks() -> list[Shock]:
    return [
        Shock(0.0, 0.0, 0.0, "base"),
        Shock(0.01, 0.0, 0.0, "spot +1%"),
        Shock(-0.01, 0.0, 0.0, "spot −1%"),
        Shock(0.0, 0.01, 0.0, "vol +1pt"),
        Shock(0.0, -0.01, 0.0, "vol −1pt"),
        Shock(0.0, 0.0, 0.0001, "rate +1bp"),
        Shock(0.0, 0.0, -0.0001, "rate −1bp"),
        Shock(-0.05, 0.05, 0.0, "crash"),
    ]
