import math

from argentum.book import Book, VanillaPosition
from argentum.math.special import bivariate_cdf, norm_cdf
from argentum.models.black import black_price
from argentum.models.black_scholes import price as bs
from argentum.models.compound import forward_start, geske_compound
from argentum.models.dupire import local_vol, sabr_total_variance
from argentum.models.multiasset import kirk_spread, margrabe
from argentum.models.touch import no_touch, one_touch
from argentum.scenario import Shock, apply_shock, default_shocks, scenario_table
from argentum.studio import book_payload, credit_payload, surface_payload, vanilla_payload
from argentum.termstructures.hazard import HazardCurve, bootstrap_hazard, par_cds_spread
from argentum.termstructures.yield_curve import YieldCurve
from argentum.time.date import Date
from argentum.types import OptionType


def test_bivariate_independence():
    x, y = 0.3, -0.2
    got = bivariate_cdf(x, y, 0.0)
    assert abs(got - norm_cdf(x) * norm_cdf(y)) < 5e-4


def test_margrabe_identical_assets_worth_zero():
    assert margrabe(100, 100, 0.2, 0.2, 1.0, 1.0) == 0.0
    assert margrabe(120, 100, 0.25, 0.2, 0.3, 1.0) > 0.0


def test_kirk_reduces_to_black_when_second_leg_zero():
    k = kirk_spread(100, 0.0, 100.0, 0.2, 0.1, 0.0, 1.0, df=1.0)
    b = black_price(100, 100, 0.2, 1.0, 1.0, OptionType.CALL)
    assert abs(k - b) < 1e-10


def test_geske_at_expiry_is_vanilla_less_strike():
    inner = bs(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    g0 = geske_compound(100, 5.0, 100, 0.05, 0.0, 0.2, 0.0, 1.0)
    assert abs(g0 - max(inner - 5.0, 0.0)) < 1e-8
    g = geske_compound(100, 5.0, 100, 0.05, 0.0, 0.2, 0.5, 1.0)
    assert 0 < g < inner


def test_forward_start_at_zero_is_vanilla():
    van = bs(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    fs = forward_start(100, 0.05, 0.0, 0.2, 0.0, 1.0)
    assert abs(fs - van) < 1e-12
    assert forward_start(100, 0.05, 0.0, 0.2, 0.25, 1.0) == van


def test_touch_complements_discounted_cash():
    df = math.exp(-0.05)
    ot = one_touch(100, 90, 0.05, 0.0, 0.2, 1.0, cash=1.0, pay_at_hit=False)
    nt = no_touch(100, 90, 0.05, 0.0, 0.2, 1.0, cash=1.0)
    assert abs(ot + nt - df) < 0.02
    assert 0 < ot < 1


def test_dupire_flat_sabr_near_implied():
    w = sabr_total_variance(100.0, 1.0, 0.2, 1.0, 0.0, 0.0)
    loc = local_vol(0.0, 1.0, w)
    assert abs(loc - 0.2) < 0.03


def test_hazard_bootstrap_recovers_flat():
    as_of = Date(2026, 8, 24)
    disc = YieldCurve.flat(as_of, 0.02)
    hz = HazardCurve.flat(as_of, 0.015, recovery=0.4)
    quotes = []
    for t in (1.0, 3.0, 5.0):
        quotes.append((t, par_cds_spread(hz, disc, t)))
    boot = bootstrap_hazard(as_of, disc, quotes, recovery=0.4)
    for t, h in zip(boot.times, boot.hazards):
        assert abs(h - 0.015) < 0.003


def test_scenario_spot_up_helps_long_call():
    book = Book()
    book.add(VanillaPosition(1, 100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, "c"))
    up = apply_shock(book, Shock(0.05, 0.0, 0.0, "up")).price()
    assert up.npv > book.price().npv
    rows = scenario_table(book, default_shocks())
    assert len(rows) == 8
    assert rows[0]["pnl"] == 0.0


def test_studio_surface_and_book():
    surf = surface_payload({"forward": 0.03})
    assert len(surf["grid"]) == 6 * 7
    book = book_payload({})
    assert book["n"] == 3
    assert "scenarios" in book
    cred = credit_payload({"hazard": 0.01})
    assert cred["par"] > 0
    van = vanilla_payload({"spot": 100, "strike": 100, "rate": 0.05, "vol": 0.2, "texp": 1})
    assert "fd" in van and "mc" in van
    assert abs(van["npv"] - van["tree"]) < 0.02
