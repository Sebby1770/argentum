"""Shared enumerations, result objects, and market containers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

from argentum.errors import InputError


class Compounding(str, Enum):
    SIMPLE = "simple"
    COMPOUNDED = "compounded"
    CONTINUOUS = "continuous"
    ANNUAL = "annual"


class Frequency(str, Enum):
    ONCE = "once"
    ANNUAL = "annual"
    SEMIANNUAL = "semiannual"
    QUARTERLY = "quarterly"
    BIMONTHLY = "bimonthly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    CONTINUOUS = "continuous"

    def periods_per_year(self) -> float:
        return {
            Frequency.ONCE: 1.0,
            Frequency.ANNUAL: 1.0,
            Frequency.SEMIANNUAL: 2.0,
            Frequency.QUARTERLY: 4.0,
            Frequency.BIMONTHLY: 6.0,
            Frequency.MONTHLY: 12.0,
            Frequency.WEEKLY: 52.0,
            Frequency.DAILY: 365.0,
            Frequency.CONTINUOUS: float("inf"),
        }[self]

    def months(self) -> int:
        mapping = {
            Frequency.ANNUAL: 12,
            Frequency.SEMIANNUAL: 6,
            Frequency.QUARTERLY: 3,
            Frequency.BIMONTHLY: 2,
            Frequency.MONTHLY: 1,
        }
        if self not in mapping:
            raise InputError(f"{self} has no month stride")
        return mapping[self]


class BusinessDayConvention(str, Enum):
    FOLLOWING = "following"
    MODIFIED_FOLLOWING = "modified_following"
    PRECEDING = "preceding"
    MODIFIED_PRECEDING = "modified_preceding"
    UNADJUSTED = "unadjusted"
    NEAREST = "nearest"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"

    @property
    def omega(self) -> int:
        return 1 if self is OptionType.CALL else -1


class ExerciseStyle(str, Enum):
    EUROPEAN = "european"
    AMERICAN = "american"
    BERMUDAN = "bermudan"


class PayoffType(str, Enum):
    VANILLA = "vanilla"
    DIGITAL_CASH = "digital_cash"
    DIGITAL_ASSET = "digital_asset"


@dataclass(frozen=True, slots=True)
class Greeks:
    """First- and second-order sensitivities.

    Vega is per 1.0 of volatility (not per vol-point). Theta is calendar-day
    (price change for +1 day, year-fraction 1/365). Rho is per 1.0 of rate.
    """

    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    rho: float = 0.0
    vanna: float = 0.0
    volga: float = 0.0
    vomma: float = 0.0
    charm: float = 0.0
    veta: float = 0.0
    speed: float = 0.0
    zomma: float = 0.0
    color: float = 0.0
    dual_delta: float = 0.0
    dual_gamma: float = 0.0
    rho_div: float = 0.0
    lambda_: float = 0.0  # elasticity / gearing
    epsilon: float = 0.0  # dividend-rate sensitivity (alias of rho_div)

    def _field_names(self) -> tuple[str, ...]:
        return tuple(self.__dataclass_fields__)

    def scale(self, notional: float) -> "Greeks":
        return Greeks(**{k: getattr(self, k) * notional for k in self._field_names()})

    def __add__(self, other: object) -> "Greeks":
        if not isinstance(other, Greeks):
            return NotImplemented
        return Greeks(**{k: getattr(self, k) + getattr(other, k) for k in self._field_names()})

    def __mul__(self, scalar: float) -> "Greeks":
        return self.scale(float(scalar))

    __rmul__ = __mul__

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in self._field_names()}


@dataclass(frozen=True, slots=True)
class PriceResult:
    """NPV plus optional risk and solver diagnostics."""

    npv: float
    currency: str = "USD"
    greeks: Greeks | None = None
    implied_vol: float | None = None
    error: float | None = None
    engine: str = ""
    meta: Mapping[str, Any] = field(default_factory=dict)

    def with_greeks(self, greeks: Greeks) -> "PriceResult":
        return replace(self, greeks=greeks)


def require_positive(name: str, value: float) -> float:
    if not (value > 0.0):
        raise InputError(f"{name} must be positive, got {value!r}")
    return float(value)


def require_non_negative(name: str, value: float) -> float:
    if value < 0.0:
        raise InputError(f"{name} must be >= 0, got {value!r}")
    return float(value)


def require_finite(name: str, value: float) -> float:
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise InputError(f"{name} must be finite, got {value!r}")
    return value
