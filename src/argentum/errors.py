"""Library error types. Numerical routines raise these instead of returning NaN."""

from __future__ import annotations


class ArgentumError(Exception):
    """Base class for all library errors."""


class ArgentumWarning(UserWarning):
    """Non-fatal numerical or market-data warning."""


class ConvergenceError(ArgentumError):
    """A root finder or calibrator failed to converge."""

    def __init__(self, message: str, *, iterations: int | None = None, residual: float | None = None) -> None:
        super().__init__(message)
        self.iterations = iterations
        self.residual = residual


class CalendarError(ArgentumError):
    """Unknown calendar, holiday, or business-day adjustment."""


class CurveError(ArgentumError):
    """Yield, vol, or hazard curve construction / interpolation failed."""


class MarketError(ArgentumError):
    """Missing or inconsistent market data for an instrument."""


class InstrumentError(ArgentumError):
    """Invalid instrument specification."""


class InputError(ArgentumError):
    """A scalar or array input is outside the model's domain."""
