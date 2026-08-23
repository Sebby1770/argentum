"""Deposit / FRA / swap bootstrap onto a log-discount curve.

Dual-curve: pass ``discounting`` to price the floating leg with a separate
OIS curve while bootstrapping a forwarding curve from par swap rates.
"""

from __future__ import annotations

from dataclasses import dataclass

from argentum.errors import CurveError, InputError
from argentum.math.solvers import newton
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.calendar import TARGET, Calendar
from argentum.time.date import Date, DateLike, as_date
from argentum.time.daycount import DayCount
from argentum.time.period import Period
from argentum.time.schedule import make_schedule
from argentum.types import BusinessDayConvention as BDC
from argentum.types import Frequency


@dataclass(frozen=True, slots=True)
class DepositQuote:
    tenor: Period | str
    rate: float
    day_count: DayCount = DayCount.ACT_360
    spot_lag: int = 2


@dataclass(frozen=True, slots=True)
class FRAQuote:
    start: Period | str
    end: Period | str
    rate: float
    day_count: DayCount = DayCount.ACT_360
    spot_lag: int = 2


@dataclass(frozen=True, slots=True)
class SwapQuote:
    tenor: Period | str
    rate: float
    fixed_frequency: Frequency = Frequency.ANNUAL
    fixed_day_count: DayCount = DayCount.THIRTY_360_BOND
    float_frequency: Frequency = Frequency.SEMIANNUAL
    float_day_count: DayCount = DayCount.ACT_360
    spot_lag: int = 2


def _spot(as_of: Date, cal: Calendar, lag: int) -> Date:
    return cal.advance(as_of, lag, unit="B")


def bootstrap_yield_curve(
    as_of: DateLike,
    *,
    deposits: list[DepositQuote] | None = None,
    fras: list[FRAQuote] | None = None,
    swaps: list[SwapQuote] | None = None,
    calendar: Calendar | None = None,
    discounting: YieldCurve | None = None,
    interpolator_kind: str = "linear",
) -> YieldCurve:
    """Bootstrap a single (or dual-curve forwarding) curve.

    Instruments must be given in increasing maturity order.
    """
    as_of_d = as_date(as_of)
    cal = calendar or TARGET()
    deposits = list(deposits or [])
    fras = list(fras or [])
    swaps = list(swaps or [])
    if not deposits and not fras and not swaps:
        raise InputError("bootstrap needs at least one instrument")

    pillars: list[Date] = []
    dfs: list[float] = []

    def curve_now() -> YieldCurve:
        if not pillars:
            raise CurveError("no pillars yet")
        return YieldCurve.from_discount_factors(as_of_d, pillars, dfs, interpolator_kind=interpolator_kind)

    def set_pillar(date: Date, df: float) -> None:
        date = cal.adjust(date, BDC.MODIFIED_FOLLOWING)
        for i, p in enumerate(pillars):
            if p == date:
                dfs[i] = df
                return
            if p > date:
                pillars.insert(i, date)
                dfs.insert(i, df)
                return
        pillars.append(date)
        dfs.append(df)

    disc = discounting

    for dep in deposits:
        tenor = Period.parse(dep.tenor)
        start = _spot(as_of_d, cal, dep.spot_lag)
        end = cal.adjust(tenor.add_to(start), BDC.MODIFIED_FOLLOWING)
        tau = dep.day_count.year_fraction(start, end, calendar=cal)
        df_start = 1.0 if start <= as_of_d else (curve_now().df(start) if pillars else 1.0)
        df_end = df_start / (1.0 + dep.rate * tau)
        set_pillar(end, df_end)

    for fra in fras:
        start_p, end_p = Period.parse(fra.start), Period.parse(fra.end)
        spot = _spot(as_of_d, cal, fra.spot_lag)
        start = cal.adjust(start_p.add_to(spot), BDC.MODIFIED_FOLLOWING)
        end = cal.adjust(end_p.add_to(spot), BDC.MODIFIED_FOLLOWING)
        tau = fra.day_count.year_fraction(start, end, calendar=cal)
        df_start = curve_now().df(start) if pillars else 1.0
        df_end = df_start / (1.0 + fra.rate * tau)
        set_pillar(end, df_end)

    for swap in swaps:
        tenor = Period.parse(swap.tenor)
        spot = _spot(as_of_d, cal, swap.spot_lag)
        end = cal.adjust(tenor.add_to(spot), BDC.MODIFIED_FOLLOWING)
        fixed_sched = make_schedule(
            spot, end, tenor=swap.fixed_frequency, calendar=cal, convention=BDC.MODIFIED_FOLLOWING
        )
        float_sched = make_schedule(
            spot, end, tenor=swap.float_frequency, calendar=cal, convention=BDC.MODIFIED_FOLLOWING
        )

        def objective(df_last: float, swap=swap, end=end, fixed_sched=fixed_sched, float_sched=float_sched) -> float:
            set_pillar(end, df_last)
            fwd_curve = curve_now()
            dcurve = disc or fwd_curve
            # par swap: PV_fixed(K) = PV_float  => annuity * K = PV_float
            annuity = 0.0
            for a, b in fixed_sched.periods():
                acc_a = cal.adjust(a, BDC.MODIFIED_FOLLOWING)
                acc_b = cal.adjust(b, BDC.MODIFIED_FOLLOWING)
                tau = swap.fixed_day_count.year_fraction(acc_a, acc_b)
                annuity += tau * dcurve.df(acc_b)
            pv_float = 0.0
            for a, b in float_sched.periods():
                acc_a = cal.adjust(a, BDC.MODIFIED_FOLLOWING)
                acc_b = cal.adjust(b, BDC.MODIFIED_FOLLOWING)
                tau = swap.float_day_count.year_fraction(acc_a, acc_b)
                l = fwd_curve.forward(acc_a, acc_b, simple=True)
                # convert ACT/365F simple forward of the interpolator into the
                # float day-count simply by using DF ratio on actual dates:
                l = (fwd_curve.df(acc_a) / fwd_curve.df(acc_b) - 1.0) / tau
                pv_float += tau * l * dcurve.df(acc_b)
            return pv_float - annuity * swap.rate

        guess = dfs[-1] if dfs else 0.9
        df_star = newton(objective, guess, lower=1e-8, upper=1.5, tol=1e-12)
        set_pillar(end, df_star)

    return curve_now()
