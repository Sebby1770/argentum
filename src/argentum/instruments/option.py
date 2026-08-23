"""Vanilla equity / FX / futures options wrapping the analytic engines."""

from __future__ import annotations

from dataclasses import dataclass

from argentum.engines.fd import fd_price
from argentum.engines.montecarlo import gbm_european
from argentum.models.bjerksund_stensland import bjerksund_stensland
from argentum.models.black import black_price
from argentum.models.black_scholes import greeks as bs_greeks
from argentum.models.black_scholes import implied_vol, price as bs_price
from argentum.models.binomial import leisen_reimer_price
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount
from argentum.types import ExerciseStyle, Greeks, OptionType, PriceResult


@dataclass(frozen=True)
class VanillaOption:
    strike: float
    expiry: Date
    option_type: OptionType = OptionType.CALL
    style: ExerciseStyle = ExerciseStyle.EUROPEAN
    day_count: DayCount = DayCount.ACT_365F

    @classmethod
    def european_call(cls, strike: float, expiry: DateLike) -> "VanillaOption":
        return cls(strike, as_date(expiry), OptionType.CALL, ExerciseStyle.EUROPEAN)

    @classmethod
    def european_put(cls, strike: float, expiry: DateLike) -> "VanillaOption":
        return cls(strike, as_date(expiry), OptionType.PUT, ExerciseStyle.EUROPEAN)

    @classmethod
    def american_put(cls, strike: float, expiry: DateLike) -> "VanillaOption":
        return cls(strike, as_date(expiry), OptionType.PUT, ExerciseStyle.AMERICAN)

    def texp(self, as_of: DateLike) -> float:
        return max(self.day_count.year_fraction(as_date(as_of), self.expiry), 0.0)

    def price(
        self,
        as_of: DateLike,
        *,
        spot: float,
        rate: float,
        div: float = 0.0,
        vol: float,
        engine: str = "analytic",
    ) -> PriceResult:
        t = self.texp(as_of)
        if self.style is ExerciseStyle.EUROPEAN and engine in {"analytic", "bs", "black_scholes"}:
            npv = bs_price(spot, self.strike, rate, div, vol, t, self.option_type)
            g = bs_greeks(spot, self.strike, rate, div, vol, t, self.option_type)
            return PriceResult(npv=npv, greeks=g, engine="black_scholes")
        if engine in {"binomial", "lr"}:
            npv = leisen_reimer_price(
                spot, self.strike, rate, div, vol, t, 401, self.option_type, self.style
            )
            return PriceResult(npv=npv, engine="leisen_reimer")
        if engine in {"fd", "crank_nicolson"}:
            npv = fd_price(spot, self.strike, rate, div, vol, t, self.option_type, self.style)
            return PriceResult(npv=npv, engine="fd_cn")
        if engine in {"mc", "montecarlo"}:
            res = gbm_european(spot, self.strike, rate, div, vol, t, self.option_type)
            return PriceResult(npv=res.npv, error=res.std_error, engine=res.engine)
        if self.style is ExerciseStyle.AMERICAN:
            npv = bjerksund_stensland(spot, self.strike, rate, div, vol, t, self.option_type)
            return PriceResult(npv=npv, engine="bjerksund_stensland_2002")
        npv = bs_price(spot, self.strike, rate, div, vol, t, self.option_type)
        g = bs_greeks(spot, self.strike, rate, div, vol, t, self.option_type)
        return PriceResult(npv=npv, greeks=g, engine="black_scholes")

    def implied_vol(
        self,
        as_of: DateLike,
        premium: float,
        *,
        spot: float,
        rate: float,
        div: float = 0.0,
    ) -> float:
        return implied_vol(premium, spot, self.strike, rate, div, self.texp(as_of), self.option_type)
