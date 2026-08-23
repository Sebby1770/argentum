"""Argentum — a production-grade derivatives pricing library.

Public surface is intentionally small. Import models, instruments, and
term structures from the subpackages when you need the full toolkit.

Quick start::

    from argentum import Date, black_scholes, VanillaOption, OptionType

    call = black_scholes.price(100, 100, 0.05, 0.0, 0.20, 1.0, OptionType.CALL)
    opt = VanillaOption.european_call(100, Date(2027, 8, 23))
    res = opt.price(Date(2026, 8, 23), spot=100, rate=0.05, vol=0.20)
"""

from argentum.book import Book, VanillaPosition
from argentum.errors import ArgentumError, ConvergenceError, CurveError, InputError, InstrumentError, MarketError
from argentum.instruments import Bond, CapFloor, CreditDefaultSwap, InterestRateSwap, Swaption, VanillaOption
from argentum.market import Market
from argentum.models import black_scholes
from argentum.models.black_scholes import greeks, implied_vol, price, result
from argentum.report import text_ticket
from argentum.termstructures import (
    DepositQuote,
    FRAQuote,
    HazardCurve,
    SwapQuote,
    YieldCurve,
    bootstrap_yield_curve,
)
from argentum.time import TARGET, Date, DayCount, Period, calendar, make_schedule, tenor
from argentum.types import Compounding, ExerciseStyle, Frequency, Greeks, OptionType, PriceResult

__version__ = "1.3.0"

__all__ = [
    "TARGET",
    "ArgentumError",
    "Bond",
    "Book",
    "CapFloor",
    "Compounding",
    "ConvergenceError",
    "CreditDefaultSwap",
    "CurveError",
    "Date",
    "DayCount",
    "DepositQuote",
    "ExerciseStyle",
    "FRAQuote",
    "Frequency",
    "Greeks",
    "HazardCurve",
    "InputError",
    "InstrumentError",
    "InterestRateSwap",
    "Market",
    "MarketError",
    "OptionType",
    "Period",
    "PriceResult",
    "SwapQuote",
    "Swaption",
    "VanillaOption",
    "VanillaPosition",
    "YieldCurve",
    "black_scholes",
    "bootstrap_yield_curve",
    "calendar",
    "greeks",
    "implied_vol",
    "make_schedule",
    "price",
    "result",
    "tenor",
    "text_ticket",
    "__version__",
]
