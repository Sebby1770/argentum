"""Vanilla interest-rate swaps (fixed vs Ibor/OIS) with dual-curve NPV and DV01."""

from __future__ import annotations

from dataclasses import dataclass

from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.calendar import TARGET, Calendar
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount
from argentum.time.period import Period
from argentum.time.schedule import make_schedule
from argentum.types import BusinessDayConvention as BDC
from argentum.types import Frequency


@dataclass(frozen=True)
class InterestRateSwap:
    start: Date
    end: Date
    notional: float
    fixed_rate: float
    pay_fixed: bool = True
    fixed_frequency: Frequency = Frequency.ANNUAL
    float_frequency: Frequency = Frequency.SEMIANNUAL
    fixed_day_count: DayCount = DayCount.THIRTY_360_BOND
    float_day_count: DayCount = DayCount.ACT_360
    calendar: Calendar = None  # type: ignore[assignment]
    convention: BDC = BDC.MODIFIED_FOLLOWING

    def __post_init__(self) -> None:
        if self.calendar is None:
            object.__setattr__(self, "calendar", TARGET())

    @classmethod
    def vanilla(
        cls,
        as_of: DateLike,
        tenor: Period | str,
        fixed_rate: float,
        *,
        notional: float = 1_000_000.0,
        spot_lag: int = 2,
        calendar: Calendar | None = None,
        **kwargs,
    ) -> "InterestRateSwap":
        cal = calendar or TARGET()
        start = cal.advance(as_date(as_of), spot_lag, unit="B")
        end = cal.adjust(Period.parse(tenor).add_to(start), BDC.MODIFIED_FOLLOWING)
        return cls(start, end, notional, fixed_rate, calendar=cal, **kwargs)

    def fixed_schedule(self):
        return make_schedule(self.start, self.end, tenor=self.fixed_frequency, calendar=self.calendar, convention=self.convention)

    def float_schedule(self):
        return make_schedule(self.start, self.end, tenor=self.float_frequency, calendar=self.calendar, convention=self.convention)

    def annuity(self, discount: YieldCurve) -> float:
        total = 0.0
        for a, b in self.fixed_schedule().periods():
            aa, bb = self.calendar.adjust(a, self.convention), self.calendar.adjust(b, self.convention)
            tau = self.fixed_day_count.year_fraction(aa, bb)
            total += tau * discount.df(bb)
        return total * self.notional

    def pv_fixed(self, discount: YieldCurve) -> float:
        return self.annuity(discount) * self.fixed_rate

    def pv_float(self, forecast: YieldCurve, discount: YieldCurve | None = None) -> float:
        dcurve = discount or forecast
        total = 0.0
        for a, b in self.float_schedule().periods():
            aa, bb = self.calendar.adjust(a, self.convention), self.calendar.adjust(b, self.convention)
            tau = self.float_day_count.year_fraction(aa, bb)
            fwd = (forecast.df(aa) / forecast.df(bb) - 1.0) / tau
            total += tau * fwd * dcurve.df(bb)
        return total * self.notional

    def npv(self, forecast: YieldCurve, discount: YieldCurve | None = None) -> float:
        dcurve = discount or forecast
        float_pv = self.pv_float(forecast, dcurve)
        fixed_pv = self.pv_fixed(dcurve)
        payer = 1.0 if self.pay_fixed else -1.0
        return payer * (float_pv - fixed_pv)

    def par_rate(self, forecast: YieldCurve, discount: YieldCurve | None = None) -> float:
        dcurve = discount or forecast
        ann = self.annuity(dcurve)
        if ann == 0.0:
            return 0.0
        return self.pv_float(forecast, dcurve) / ann

    def dv01(self, forecast: YieldCurve, discount: YieldCurve | None = None, bump: float = 1e-4) -> float:
        """Bump-and-revalue 1bp parallel on both curves (or forecast if single)."""
        dcurve = discount or forecast
        base = self.npv(forecast, dcurve)
        bumped_f = _bump_curve(forecast, bump)
        bumped_d = _bump_curve(dcurve, bump) if discount is not None else bumped_f
        return (self.npv(bumped_f, bumped_d) - base) / (bump * 10_000.0)


def _bump_curve(curve: YieldCurve, bp_rate: float) -> YieldCurve:
    """Approximate a parallel zero bump via DF * exp(-bp * t)."""
    import math

    from argentum.termstructures.yield_curve import YieldCurve as YC

    dates = []
    dfs = []
    as_of = curve.as_of
    for t, df in zip(curve.times, curve.dfs):
        dates.append(as_of.add_days(int(round(t * 365.0))))
        dfs.append(df * math.exp(-bp_rate * t))
    # first pillar t=0
    return YC.from_discount_factors(
        as_of,
        dates[1:] if dates and curve.times[0] == 0 else dates,
        dfs[1:] if dates and curve.times[0] == 0 else dfs,
        day_count=curve.day_count,
        interpolation=curve.interpolation,
        interpolator_kind="linear",
        compounding=curve.compounding,
        frequency=curve.frequency,
    )
