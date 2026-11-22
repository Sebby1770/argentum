import math
from dataclasses import replace

import numpy as np
import pytest

from argentum import Book, InputError, OptionType, VanillaPosition, price
from argentum.risk.portfolio import historical_var, monte_carlo_var, pnl_explain
from argentum.math.special import norm_inv


def _book(*positions: VanillaPosition) -> Book:
    book = Book()
    for pos in positions:
        book.add(pos)
    return book


def test_var_of_a_long_forward_proxy_matches_the_lognormal_quantile():
    # Deep ITM call ≈ forward: P&L ≈ S (e^r - 1) with r ~ N(-σ²h/2, σ²h).
    pos = VanillaPosition(1.0, 100.0, 1e-3, 0.0, 0.0, 0.2, 0.5, OptionType.CALL, "fwd", "AAA")
    res = monte_carlo_var(_book(pos), alpha=0.99, horizon_days=10, n_scenarios=200_000, vol_of_vol=0.0)
    h = 10 / 252
    z = norm_inv(0.01)
    exact = -100.0 * (math.exp(-0.5 * 0.04 * h + 0.2 * math.sqrt(h) * z) - 1.0)
    assert res["var"] == pytest.approx(exact, rel=0.02)
    assert res["es"] > res["var"]


def test_short_gamma_book_has_fatter_loss_than_its_taylor_estimate_misses_nothing_big():
    short_straddle = _book(
        VanillaPosition(-10, 100.0, 100.0, 0.02, 0.0, 0.25, 0.1, OptionType.CALL, "straddle", "XYZ"),
        VanillaPosition(-10, 100.0, 100.0, 0.02, 0.0, 0.25, 0.1, OptionType.PUT, "straddle", "XYZ"),
    )
    res = monte_carlo_var(short_straddle, horizon_days=5, n_scenarios=40_000)
    assert res["var"] > 0.0 and res["es"] >= res["var"]
    # Second-order Taylor is close on a 5-day horizon but not identical.
    assert res["var_taylor"] == pytest.approx(res["var"], rel=0.25)
    assert sum(res["histogram"]["counts"]) == 40_000
    assert res["underlyings"] == ["XYZ"]


def test_diversification_between_underlyings_lowers_var():
    a = VanillaPosition(1.0, 100.0, 100.0, 0.0, 0.0, 0.3, 1.0, OptionType.CALL, "long", "A")
    b = replace(a, underlying="B")
    together = monte_carlo_var(_book(a, b), correlation=0.95, vol_of_vol=0.0)["var"]
    apart = monte_carlo_var(_book(a, b), correlation=-0.5, vol_of_vol=0.0)["var"]
    assert apart < together


def test_same_seed_is_reproducible_and_inputs_are_validated():
    book = _book(VanillaPosition(1.0, 100.0, 100.0, 0.0, 0.0, 0.2, 1.0, OptionType.PUT, "P"))
    assert monte_carlo_var(book, seed=11)["var"] == monte_carlo_var(book, seed=11)["var"]
    for bad in ({"alpha": 0.2}, {"horizon_days": 0}, {"n_scenarios": 10}, {"correlation": 1.0}):
        with pytest.raises(InputError):
            monte_carlo_var(book, **bad)
    with pytest.raises(InputError):
        monte_carlo_var(Book())


def test_historical_var_replays_the_worst_day_exactly():
    pos = VanillaPosition(2.0, 100.0, 90.0, 0.01, 0.0, 0.2, 0.25, OptionType.CALL, "spx-call", "SPX")
    rets = [0.01, -0.03, 0.002, -0.08, 0.04] * 20  # 100 days
    res = historical_var(_book(pos), {"SPX": rets}, alpha=0.99)
    base = 2.0 * price(100.0, 90.0, 0.01, 0.0, 0.2, 0.25, "call")
    worst = 2.0 * price(100.0 * math.exp(-0.08), 90.0, 0.01, 0.0, 0.2, 0.25 - 1 / 252, "call") - base
    assert res["var"] == pytest.approx(-worst, rel=1e-12)
    with pytest.raises(InputError):
        historical_var(_book(pos), {"SPX": [0.01], "OTHER": [0.0, 0.0]})


def test_pnl_explain_closes_to_second_order():
    pos = VanillaPosition(5.0, 100.0, 105.0, 0.03, 0.01, 0.22, 0.75, OptionType.CALL, "ABC")
    moved = replace(pos, spot=101.2, vol=0.225, rate=0.0305, texp=0.75 - 1 / 365)
    out = pnl_explain(_book(pos), _book(moved))
    total = out["total"]
    actual = 5.0 * (
        price(101.2, 105.0, 0.0305, 0.01, 0.225, 0.75 - 1 / 365) - price(100.0, 105.0, 0.03, 0.01, 0.22, 0.75)
    )
    assert total["actual"] == pytest.approx(actual, rel=1e-12)
    assert abs(total["unexplained"]) < 0.01 * abs(actual)
    assert total["delta"] > 0.0 and total["theta"] < 0.0 and total["vega"] > 0.0


def test_pnl_explain_rejects_mismatched_books():
    pos = VanillaPosition(1.0, 100.0, 100.0, 0.0, 0.0, 0.2, 1.0, OptionType.CALL, "A")
    with pytest.raises(InputError):
        pnl_explain(_book(pos), _book(replace(pos, strike=90.0)))
    with pytest.raises(InputError):
        pnl_explain(_book(pos), _book(replace(pos, texp=2.0)))
    with pytest.raises(InputError):
        pnl_explain(_book(pos), Book())


def test_vectorised_book_value_matches_scalar_book():
    book = _book(
        VanillaPosition(3.0, 50.0, 55.0, 0.02, 0.0, 0.3, 0.5, OptionType.PUT, "Q"),
        VanillaPosition(-1.0, 50.0, 45.0, 0.02, 0.0, 0.35, 0.5, OptionType.CALL, "Q"),
    )
    res = monte_carlo_var(book, n_scenarios=1000)
    assert res["npv"] == pytest.approx(book.price().npv, rel=1e-12)
    assert np.isfinite(res["mean_pnl"])


def test_untagged_positions_on_one_spot_share_an_underlying_and_strategy_tags_do_not_split_it():
    book = _book(
        VanillaPosition(1, 100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "atm"),
        VanillaPosition(-1, 100, 110, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "call-spread"),
        VanillaPosition(1, 50, 45, 0.05, 0.0, 0.3, 1.0, OptionType.PUT, "other"),
    )
    assert monte_carlo_var(book, n_scenarios=1000)["underlyings"] == ["spot=100", "spot=50"]


def test_portfolio_rows_accept_an_underlying_or_symbol_column():
    from argentum.portfolio import book_from_rows, portfolio_report

    book = book_from_rows(
        [
            {"spot": 100, "strike": 100, "vol": 0.2, "texp": 1, "underlying": "AAPL"},
            {"spot": 100, "strike": 95, "vol": 0.2, "texp": 1, "symbol": "MSFT", "type": "put"},
            {"spot": 100, "strike": 90, "vol": 0.2, "texp": 1},
        ]
    )
    assert [p.underlying for p in book.positions] == ["AAPL", "MSFT", ""]
    inputs = portfolio_report(book)["input_positions"]
    assert inputs[0]["underlying"] == "AAPL" and "underlying" not in inputs[2]
