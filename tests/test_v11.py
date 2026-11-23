from argentum.book import Book, VanillaPosition
from argentum.models.barriers import barrier_price
from argentum.models.black_scholes import price as bs
from argentum.models.dividends import escrowed_price
from argentum.models.lookback import floating_lookback
from argentum.models.quanto import quanto_price
from argentum.models.variance import black_variance_strike, log_contract_fair_variance
from argentum.report import text_ticket
from argentum.studio import bond_payload, extras_payload, health_payload, smile_payload, vanilla_payload
from argentum.time import Canada, Switzerland, calendar
from argentum.time.date import Date
from argentum.types import OptionType


def test_barrier_in_out_parity():
    args = dict(spot=100, strike=100, barrier=90, rate=0.05, div=0.0, vol=0.2, texp=1.0, option_type=OptionType.CALL)
    out = barrier_price(**args, knock="out", barrier_type="down")
    inn = barrier_price(**args, knock="in", barrier_type="down")
    van = bs(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    assert out < van
    assert abs(out + inn - van) < 0.05


def test_far_down_barrier_near_vanilla():
    van = bs(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    far = barrier_price(100, 100, 1.0, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, knock="out", barrier_type="down")
    assert abs(far - van) < 0.15


def test_floating_lookback_call_beats_vanilla():
    van = bs(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    look = floating_lookback(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    assert look > van


def test_quanto_positive_corr_cheapens_call():
    plain = bs(100, 100, 0.03, 0.0, 0.2, 1.0, OptionType.CALL)
    q = quanto_price(100, 100, 0.03, 0.0, 0.2, 1.0, rho=0.4, vol_fx=0.12)
    assert 0 < q < plain


def test_escrowed_dividend_lowers_call():
    plain = bs(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    div = escrowed_price(100, 100, 0.05, 0.2, 1.0, [(0.5, 3.0)])
    assert div < plain


def test_variance_flat_near_sigma_sq():
    flat = black_variance_strike(0.2)
    replica = log_contract_fair_variance(100, 0.05, 0.0, 1.0, lambda _k: 0.2)
    assert abs(replica - flat) / flat < 0.15


def test_book_aggregates():
    book = Book()
    book.add(VanillaPosition(1, 100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "core"))
    book.add(VanillaPosition(-1, 100, 110, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "core"))
    res = book.price()
    assert res.npv > 0
    assert res.greeks is not None
    assert "NPV" in text_ticket(res)


def test_studio_vanilla_atm():
    data = vanilla_payload({"spot": 100, "strike": 100, "rate": 0.05, "vol": 0.2, "texp": 1, "type": "call"})
    assert abs(data["npv"] - 10.45058357) < 1e-6
    assert "delta" in data["greeks"]
    assert len(data["grid"]["spot"]) == 21


def test_studio_smile_and_bond():
    smile = smile_payload({"forward": 0.03, "texp": 5, "alpha": 0.04, "beta": 0.5, "rho": -0.3, "nu": 0.5})
    assert len(smile["grid"]) == 25
    bond = bond_payload({"coupon": 0.05, "ytm": 0.05, "years": 10, "freq": 2, "as_of": "2025-01-15"})
    assert 90 < bond["dirty"] < 110
    assert bond["as_of"] == "2025-01-15"


def test_health_and_extras():
    h = health_payload()
    assert h["ok"] and h["version"].startswith("1.")
    extra = extras_payload({})
    assert extra["floating_lookback_call"] > extra["vanilla"]


def test_new_calendars():
    assert calendar("ch").name == "Switzerland"
    assert calendar("ca").name == "Canada"
    assert Switzerland().is_holiday(Date(2026, 4, 3))
    assert Canada().is_holiday(Date(2026, 7, 1))
