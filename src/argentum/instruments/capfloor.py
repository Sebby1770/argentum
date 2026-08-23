"""Caps, floors, and European swaptions (Black / Bachelier / SABR)."""

from __future__ import annotations

from dataclasses import dataclass

from argentum.models.black import bachelier_price, black_price
from argentum.models.sabr import sabr_implied_vol
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.calendar import TARGET
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount
from argentum.time.schedule import make_schedule
from argentum.types import BusinessDayConvention as BDC
from argentum.types import Frequency, OptionType


@dataclass(frozen=True)
class CapFloor:
    start: Date
    end: Date
    strike: float
    is_cap: bool = True
    frequency: Frequency = Frequency.QUARTERLY
    day_count: DayCount = DayCount.ACT_360
    notional: float = 1.0

    def npv(
        self,
        as_of: DateLike,
        forecast: YieldCurve,
        discount: YieldCurve,
        vol: float,
        *,
        normal: bool = False,
    ) -> float:
        opt = OptionType.CALL if self.is_cap else OptionType.PUT
        total = 0.0
        sched = make_schedule(self.start, self.end, tenor=self.frequency, calendar=TARGET(), convention=BDC.MODIFIED_FOLLOWING)
        as_of_d = as_date(as_of)
        for a, b in sched.periods():
            if b <= as_of_d:
                continue
            tau = self.day_count.year_fraction(a, b)
            df = discount.df(b)
            fwd = (forecast.df(a) / forecast.df(b) - 1.0) / tau
            texp = max(forecast.t(a), 0.0)
            if texp <= 0.0:
                payoff = max(fwd - self.strike, 0.0) if self.is_cap else max(self.strike - fwd, 0.0)
                total += self.notional * tau * df * payoff
                continue
            if normal:
                caplet = bachelier_price(fwd, self.strike, vol, texp, df, opt)
            else:
                caplet = black_price(fwd, self.strike, vol, texp, df, opt)
            total += self.notional * tau * caplet / df * df  # caplet already df'd
        return total


@dataclass(frozen=True)
class Swaption:
    expiry: Date
    swap_end: Date
    strike: float
    notional: float = 1.0
    option_type: OptionType = OptionType.CALL  # call = payer
    fixed_frequency: Frequency = Frequency.ANNUAL
    fixed_day_count: DayCount = DayCount.THIRTY_360_BOND

    def annuity(self, discount: YieldCurve) -> float:
        sched = make_schedule(
            self.expiry, self.swap_end, tenor=self.fixed_frequency, calendar=TARGET(), convention=BDC.MODIFIED_FOLLOWING
        )
        ann = 0.0
        for a, b in sched.periods():
            tau = self.fixed_day_count.year_fraction(a, b)
            ann += tau * discount.df(b)
        return ann * self.notional

    def forward_swap_rate(self, forecast: YieldCurve, discount: YieldCurve) -> float:
        # level = annuity; float PV ≈ df(expiry) - df(end) under single curve,
        # dual-curve: sum of forward * tau * df
        sched = make_schedule(
            self.expiry, self.swap_end, tenor=Frequency.SEMIANNUAL, calendar=TARGET(), convention=BDC.MODIFIED_FOLLOWING
        )
        pv_float = 0.0
        for a, b in sched.periods():
            tau = DayCount.ACT_360.year_fraction(a, b)
            fwd = (forecast.df(a) / forecast.df(b) - 1.0) / tau
            pv_float += tau * fwd * discount.df(b)
        ann = self.annuity(discount) / self.notional
        return pv_float / ann if ann else 0.0

    def npv(
        self,
        as_of: DateLike,
        forecast: YieldCurve,
        discount: YieldCurve,
        vol: float,
        *,
        normal: bool = False,
        sabr: tuple[float, float, float, float] | None = None,
    ) -> float:
        texp = max(discount.t(self.expiry), 0.0)
        fwd = self.forward_swap_rate(forecast, discount)
        ann = self.annuity(discount)
        if sabr is not None:
            alpha, beta, rho, nu = sabr
            vol = sabr_implied_vol(fwd, self.strike, texp, alpha, beta, rho, nu)
            normal = False
        if texp == 0.0:
            intrinsic = max(fwd - self.strike, 0.0) if self.option_type is OptionType.CALL else max(self.strike - fwd, 0.0)
            return ann * intrinsic
        if normal:
            return ann * bachelier_price(fwd, self.strike, vol, texp, 1.0, self.option_type)
        return ann * black_price(fwd, self.strike, vol, texp, 1.0, self.option_type)
