"""Fixed-rate, zero, and floating-rate bonds: dirty/clean, YTM, duration, Z-spread."""

from __future__ import annotations

from typing import TYPE_CHECKING

import math
from dataclasses import dataclass

from argentum.errors import InstrumentError
from argentum.math.solvers import brent, newton
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.calendar import WeekendsOnly
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount
from argentum.time.period import Period
from argentum.time.schedule import Schedule, make_schedule
from argentum.types import BusinessDayConvention as BDC
from argentum.types import Compounding, Frequency

if TYPE_CHECKING:
    from argentum.time.calendar import Calendar


@dataclass(frozen=True, slots=True)
class CashFlow:
    date: Date
    amount: float
    accrual_start: Date | None = None
    accrual_end: Date | None = None
    rate: float | None = None


@dataclass(frozen=True)
class Bond:
    face: float
    issue: Date
    maturity: Date
    coupon: float
    frequency: Frequency
    day_count: DayCount = DayCount.THIRTY_360_BOND
    calendar: "Calendar | None" = None
    convention: BDC = BDC.UNADJUSTED
    settlement_days: int = 0
    compounding: Compounding = Compounding.COMPOUNDED

    @classmethod
    def fixed(
        cls,
        coupon: float,
        maturity: DateLike,
        *,
        issue: DateLike | None = None,
        as_of: DateLike | None = None,
        frequency: Frequency = Frequency.SEMIANNUAL,
        face: float = 100.0,
        day_count: DayCount = DayCount.THIRTY_360_BOND,
    ) -> "Bond":
        mat = as_date(maturity)
        if issue is None:
            if as_of is None:
                raise InstrumentError("provide issue or as_of")
            # walk back coupon periods from maturity until before as_of, then one more for issue
            as_of_d = as_date(as_of)
            period = Period.from_frequency(frequency)
            d = mat
            while d > as_of_d:
                d = (-period).add_to(d)
            issue_d = d
        else:
            issue_d = as_date(issue)
        return cls(face, issue_d, mat, coupon, frequency, day_count)

    @classmethod
    def zero(cls, maturity: DateLike, *, issue: DateLike, face: float = 100.0) -> "Bond":
        return cls(face, as_date(issue), as_date(maturity), 0.0, Frequency.ONCE, DayCount.ACT_ACT_ISDA)

    def schedule(self) -> Schedule:
        cal = self.calendar or WeekendsOnly()
        if self.frequency is Frequency.ONCE:
            return make_schedule(self.issue, self.maturity, tenor=Period(1, "Y"), generation="zero", calendar=cal)
        return make_schedule(
            self.issue,
            self.maturity,
            tenor=self.frequency,
            calendar=cal,
            convention=self.convention,
            generation="backward",
        )

    def cashflows(self, as_of: DateLike | None = None) -> list[CashFlow]:
        sched = self.schedule()
        flows: list[CashFlow] = []
        for start, end in sched.periods():
            tau = self.day_count.year_fraction(start, end, ref_start=start, ref_end=end)
            amount = self.face * self.coupon * tau
            if end == self.maturity:
                amount += self.face
            flows.append(CashFlow(end, amount, start, end, self.coupon))
        if as_of is not None:
            d = as_date(as_of)
            flows = [f for f in flows if f.date > d]
        return flows

    def accrued(self, as_of: DateLike) -> float:
        d = as_date(as_of)
        if d >= self.maturity or self.coupon == 0.0:
            return 0.0
        sched = self.schedule()
        for start, end in sched.periods():
            if start <= d < end:
                tau_acc = self.day_count.year_fraction(start, d, ref_start=start, ref_end=end)
                tau_full = self.day_count.year_fraction(start, end, ref_start=start, ref_end=end)
                return self.face * self.coupon * tau_acc if tau_full else 0.0
        return 0.0

    def dirty_price_from_ytm(self, as_of: DateLike, ytm: float) -> float:
        d = as_date(as_of)
        freq = self.frequency.periods_per_year() if self.frequency is not Frequency.ONCE else 1.0
        pv = 0.0
        for flow in self.cashflows(as_of):
            t = self.day_count.year_fraction(d, flow.date, ref_start=d, ref_end=flow.date)
            if self.compounding is Compounding.CONTINUOUS:
                df = math.exp(-ytm * t)
            elif self.compounding is Compounding.SIMPLE:
                df = 1.0 / (1.0 + ytm * t)
            else:
                df = (1.0 + ytm / freq) ** (-freq * t)
            pv += flow.amount * df
        return pv

    def clean_price_from_ytm(self, as_of: DateLike, ytm: float) -> float:
        return self.dirty_price_from_ytm(as_of, ytm) - self.accrued(as_of)

    def ytm(self, as_of: DateLike, dirty_price: float) -> float:
        def obj(y: float) -> float:
            return self.dirty_price_from_ytm(as_of, y) - dirty_price

        try:
            return newton(obj, 0.05, lower=-0.5, upper=2.0)
        except Exception:
            return brent(obj, -0.2, 1.5)

    def macaulay_duration(self, as_of: DateLike, ytm: float) -> float:
        d = as_date(as_of)
        dirty = self.dirty_price_from_ytm(as_of, ytm)
        freq = self.frequency.periods_per_year() if self.frequency is not Frequency.ONCE else 1.0
        acc = 0.0
        for flow in self.cashflows(as_of):
            t = self.day_count.year_fraction(d, flow.date)
            if self.compounding is Compounding.CONTINUOUS:
                df = math.exp(-ytm * t)
            else:
                df = (1.0 + ytm / freq) ** (-freq * t)
            acc += t * flow.amount * df
        return acc / dirty if dirty else 0.0

    def modified_duration(self, as_of: DateLike, ytm: float) -> float:
        mac = self.macaulay_duration(as_of, ytm)
        freq = self.frequency.periods_per_year() if self.frequency is not Frequency.ONCE else 1.0
        if self.compounding is Compounding.CONTINUOUS:
            return mac
        return mac / (1.0 + ytm / freq)

    def convexity(self, as_of: DateLike, ytm: float) -> float:
        d = as_date(as_of)
        dirty = self.dirty_price_from_ytm(as_of, ytm)
        freq = self.frequency.periods_per_year() if self.frequency is not Frequency.ONCE else 1.0
        acc = 0.0
        for flow in self.cashflows(as_of):
            t = self.day_count.year_fraction(d, flow.date)
            df = (1.0 + ytm / freq) ** (-freq * t) if self.compounding is not Compounding.CONTINUOUS else math.exp(-ytm * t)
            acc += t * (t + 1.0 / freq) * flow.amount * df
        return acc / dirty / (1.0 + ytm / freq) ** 2 if dirty else 0.0

    def npv(self, as_of: DateLike, curve: YieldCurve) -> float:
        return sum(flow.amount * curve.df(flow.date) for flow in self.cashflows(as_of))

    def z_spread(self, as_of: DateLike, dirty_price: float, curve: YieldCurve) -> float:
        """Constant spread s on the discount curve: DF_mkt(t) * exp(-s t)."""
        flows = self.cashflows(as_of)

        def obj(s: float) -> float:
            pv = 0.0
            for flow in flows:
                t = curve.t(flow.date)
                pv += flow.amount * curve.df(flow.date) * math.exp(-s * t)
            return pv - dirty_price

        try:
            return newton(obj, 0.0, lower=-0.5, upper=0.5)
        except Exception:
            return brent(obj, -0.2, 0.2)
