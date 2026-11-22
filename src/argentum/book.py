"""A small trading book: vanilla positions, aggregated NPV and greeks."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from argentum.models.black_scholes import greeks as bs_greeks
from argentum.models.black_scholes import price as bs_price
from argentum.types import Greeks, OptionType, PriceResult


@dataclass(frozen=True, slots=True)
class VanillaPosition:
    quantity: float
    spot: float
    strike: float
    rate: float
    div: float
    vol: float
    texp: float
    option_type: OptionType = OptionType.CALL
    tag: str = ""
    underlying: str = ""  # risk factor name; empty means "identified by its spot"

    def value(self) -> PriceResult:
        opt = OptionType(self.option_type)
        npv = self.quantity * bs_price(self.spot, self.strike, self.rate, self.div, self.vol, self.texp, opt)
        g = bs_greeks(self.spot, self.strike, self.rate, self.div, self.vol, self.texp, opt).scale(self.quantity)
        return PriceResult(npv=npv, greeks=g, engine="black_scholes", meta={"tag": self.tag})


@dataclass
class Book:
    positions: list[VanillaPosition] = field(default_factory=list)

    def add(self, position: VanillaPosition) -> None:
        self.positions.append(position)

    def price(self) -> PriceResult:
        npv = 0.0
        greeks = Greeks()
        for pos in self.positions:
            res = pos.value()
            npv += res.npv
            if res.greeks is not None:
                greeks = greeks + res.greeks
        return PriceResult(npv=npv, greeks=greeks, engine="book", meta={"n": len(self.positions)})

    def by_tag(self) -> dict[str, PriceResult]:
        groups: dict[str, Book] = {}
        for pos in self.positions:
            groups.setdefault(pos.tag or "_", Book()).add(pos)
        return {tag: book.price() for tag, book in groups.items()}

    def remap_spots(self, spots: dict[str, float]) -> Book:
        """Rebuild the book using last prints keyed by position tag (or a global '_')."""
        out = Book()
        fallback = spots.get("_")
        for pos in self.positions:
            spot = spots.get(pos.tag, fallback if fallback is not None else pos.spot)
            out.add(replace(pos, spot=spot))
        return out
