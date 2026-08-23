"""ISDA-style credit default swap: par spread, upfront, risky PV01.

Premium leg: quarterly ACT/360, accrued on default (mid-period approximation).
Protection leg: (1-R) ∫ h(t) S(t) DF(t) dt.
"""

from __future__ import annotations

from dataclasses import dataclass

from argentum.termstructures.hazard import HazardCurve
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount
from argentum.time.schedule import make_schedule
from argentum.types import Frequency


@dataclass(frozen=True)
class CreditDefaultSwap:
    start: Date
    end: Date
    coupon: float  # running spread, e.g. 0.01 or 0.05
    recovery: float = 0.4
    notional: float = 1.0
    frequency: Frequency = Frequency.QUARTERLY
    day_count: DayCount = DayCount.ACT_360
    pay_accrual_on_default: bool = True

    def risky_annuity(self, discount: YieldCurve, hazard: HazardCurve) -> float:
        sched = make_schedule(self.start, self.end, tenor=self.frequency)
        total = 0.0
        for a, b in sched.periods():
            tau = self.day_count.year_fraction(a, b)
            surv = hazard.survival(b)
            df = discount.df(b)
            total += tau * surv * df
            if self.pay_accrual_on_default:
                # mid-period default approximation
                t0, t1 = discount.t(a), discount.t(b)
                s0, s1 = hazard.survival(a), hazard.survival(b)
                default_prob = max(s0 - s1, 0.0)
                t_mid = 0.5 * (t0 + t1)
                df_mid = discount.df(t_mid)
                total += 0.5 * tau * default_prob * df_mid
        return total * self.notional

    def protection_leg(self, discount: YieldCurve, hazard: HazardCurve, n_steps: int = 200) -> float:
        t_end = discount.t(self.end)
        t_start = max(discount.t(self.start), 0.0)
        dt = (t_end - t_start) / n_steps
        acc = 0.0
        for i in range(n_steps):
            t0 = t_start + i * dt
            t1 = t0 + dt
            s0, s1 = hazard.survival(t0), hazard.survival(t1)
            df = discount.df(0.5 * (t0 + t1))
            acc += max(s0 - s1, 0.0) * df
        return (1.0 - self.recovery) * self.notional * acc

    def npv(self, discount: YieldCurve, hazard: HazardCurve, *, buy_protection: bool = True) -> float:
        prot = self.protection_leg(discount, hazard)
        prem = self.coupon * self.risky_annuity(discount, hazard)
        sign = 1.0 if buy_protection else -1.0
        return sign * (prot - prem)

    def par_spread(self, discount: YieldCurve, hazard: HazardCurve) -> float:
        ann = self.risky_annuity(discount, hazard)
        if ann == 0.0:
            return 0.0
        return self.protection_leg(discount, hazard) / ann

    def upfront(self, discount: YieldCurve, hazard: HazardCurve) -> float:
        """Standard SNAC-style upfront (buy protection) as a fraction of notional."""
        return self.npv(discount, hazard, buy_protection=True) / self.notional
