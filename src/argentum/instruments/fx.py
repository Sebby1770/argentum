"""FX vanillas (Garman–Kohlhagen) and a thin wrapper around barriers."""

from __future__ import annotations

from dataclasses import dataclass

from argentum.models.barriers import barrier_price
from argentum.models.black_scholes import greeks, price
from argentum.types import OptionType, PriceResult


@dataclass(frozen=True)
class FxVanilla:
    """Domestic/foreign rates: ``rate`` is r_d, ``div`` is r_f."""

    spot: float
    strike: float
    texp: float
    option_type: OptionType = OptionType.CALL

    def price(self, rd: float, rf: float, vol: float) -> PriceResult:
        npv = price(self.spot, self.strike, rd, rf, vol, self.texp, self.option_type)
        g = greeks(self.spot, self.strike, rd, rf, vol, self.texp, self.option_type)
        return PriceResult(npv=npv, greeks=g, engine="garman_kohlhagen")


@dataclass(frozen=True)
class FxBarrier:
    spot: float
    strike: float
    barrier: float
    texp: float
    option_type: OptionType = OptionType.CALL
    knock: str = "out"
    barrier_type: str = "down"

    def price(self, rd: float, rf: float, vol: float) -> float:
        return barrier_price(
            self.spot,
            self.strike,
            self.barrier,
            rd,
            rf,
            vol,
            self.texp,
            self.option_type,
            knock=self.knock,
            barrier_type=self.barrier_type,
        )
