"""Coupon and payment date schedules."""

from __future__ import annotations

from dataclasses import dataclass

from argentum.errors import InputError
from argentum.time.calendar import Calendar, WeekendsOnly
from argentum.time.date import Date, DateLike, as_date
from argentum.time.period import Period
from argentum.types import BusinessDayConvention as BDC
from argentum.types import Frequency


class DateGeneration(str):
    FORWARD = "forward"
    BACKWARD = "backward"
    ZERO = "zero"
    IMM = "imm"


@dataclass(frozen=True, slots=True)
class Schedule:
    """An ordered list of unadjusted or adjusted period dates.

    ``dates[0]`` is the effective / start date, ``dates[-1]`` the termination.
    Payment dates are ``dates[1:]`` after convention adjustment.
    """

    dates: tuple[Date, ...]
    calendar: Calendar
    convention: BDC
    tenor: Period
    end_of_month: bool = False

    def __len__(self) -> int:
        return len(self.dates)

    def __getitem__(self, idx: int) -> Date:
        return self.dates[idx]

    @property
    def start(self) -> Date:
        return self.dates[0]

    @property
    def end(self) -> Date:
        return self.dates[-1]

    def periods(self) -> list[tuple[Date, Date]]:
        return list(zip(self.dates[:-1], self.dates[1:]))

    def payment_dates(self) -> list[Date]:
        return [self.calendar.adjust(d, self.convention) for d in self.dates[1:]]


def make_schedule(
    start: DateLike,
    end: DateLike | None = None,
    *,
    tenor: Period | str | Frequency = Frequency.SEMIANNUAL,
    calendar: Calendar | None = None,
    convention: BDC = BDC.MODIFIED_FOLLOWING,
    generation: str = DateGeneration.BACKWARD,
    end_of_month: bool = False,
    stub: str = "short",
    n_periods: int | None = None,
) -> Schedule:
    """Build a regular schedule.

    ``stub`` is ``short`` or ``long`` and only applies when the tenor does not
    divide the interval exactly.
    """
    cal = calendar or WeekendsOnly()
    start_d = as_date(start)
    if isinstance(tenor, Frequency):
        period = Period.from_frequency(tenor)
    else:
        period = Period.parse(tenor) if not isinstance(tenor, Period) else tenor
    if period.n <= 0:
        raise InputError("schedule tenor must be positive")

    if end is None:
        if n_periods is None:
            raise InputError("provide end or n_periods")
        end_d = period.add_to(start_d, end_of_month=end_of_month)
        for _ in range(n_periods - 1):
            end_d = period.add_to(end_d, end_of_month=end_of_month)
    else:
        end_d = as_date(end)

    if end_d <= start_d:
        raise InputError("schedule end must be after start")

    if generation == DateGeneration.ZERO:
        zero: tuple[Date, ...] = (start_d, end_d)
        return Schedule(zero, cal, convention, period, end_of_month)

    if generation == DateGeneration.IMM:
        dates = _imm_schedule(start_d, end_d)
        return Schedule(dates, cal, convention, period, end_of_month)

    dates_list: list[Date]
    if generation == DateGeneration.FORWARD:
        dates_list = [start_d]
        current = start_d
        while True:
            nxt = period.add_to(current, end_of_month=end_of_month)
            if nxt >= end_d:
                break
            dates_list.append(nxt)
            current = nxt
        if dates_list[-1] != end_d:
            if stub == "long" and len(dates_list) >= 2:
                dates_list[-1] = end_d
            else:
                dates_list.append(end_d)
    else:
        dates_list = [end_d]
        current = end_d
        while True:
            prev = (-period).add_to(current, end_of_month=end_of_month)
            if prev <= start_d:
                break
            dates_list.append(prev)
            current = prev
        if dates_list[-1] != start_d:
            if stub == "long" and len(dates_list) >= 2:
                dates_list[-1] = start_d
            else:
                dates_list.append(start_d)
        dates_list.reverse()

    # de-duplicate in case of EOM collapse
    cleaned: list[Date] = []
    for d in dates_list:
        if not cleaned or d != cleaned[-1]:
            cleaned.append(d)
    if cleaned[0] != start_d:
        cleaned.insert(0, start_d)
    if cleaned[-1] != end_d:
        cleaned.append(end_d)
    return Schedule(tuple(cleaned), cal, convention, period, end_of_month)


def _imm_schedule(start: Date, end: Date) -> tuple[Date, ...]:
    dates = [start]
    # first IMM strictly after start
    while True:
        imm = Date.next_imm(dates[-1], quarterly=True)
        if imm >= end:
            break
        dates.append(imm)
        if len(dates) > 512:
            raise InputError("IMM schedule overflow")
        _year, _month = imm.year, imm.month
    if dates[-1] != end:
        dates.append(end)
    return tuple(dates)
