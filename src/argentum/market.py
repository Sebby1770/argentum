"""A snapshot of the curves and spots a book is marked against."""

from __future__ import annotations

from dataclasses import dataclass, field

from argentum.termstructures.hazard import HazardCurve
from argentum.termstructures.vol_surface import BlackVolSurface
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date


@dataclass
class Market:
    as_of: Date
    discount: YieldCurve
    forecast: YieldCurve | None = None
    vol: BlackVolSurface | None = None
    hazard: HazardCurve | None = None
    spots: dict[str, float] = field(default_factory=dict)

    @property
    def forwarding(self) -> YieldCurve:
        return self.forecast if self.forecast is not None else self.discount

    def spot(self, name: str, default: float | None = None) -> float:
        if name in self.spots:
            return self.spots[name]
        if default is not None:
            return default
        from argentum.errors import MarketError

        raise MarketError(f"no spot for {name!r}")

    def apply_quotes(self, quotes: list[object]) -> None:
        """Write last prints onto the snapshot. A feed supplies spots, not models."""
        for quote in quotes:
            symbol = getattr(quote, "symbol", None)
            spot = getattr(quote, "spot", None)
            if symbol and spot is not None:
                self.spots[str(symbol)] = float(spot)
