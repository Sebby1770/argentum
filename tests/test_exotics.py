from argentum.models.asian import geometric_asian_price, turnbull_wakeman_price
from argentum.models.black import bachelier_implied_vol, bachelier_price, black_implied_vol, black_price
from argentum.models.black_scholes import price as bs_price
from argentum.types import OptionType


def test_black76_matches_bs_on_forward():
    import math

    s, r, q, sig, t, k = 100.0, 0.05, 0.01, 0.2, 1.0, 100.0
    f = s * math.exp((r - q) * t)
    df = math.exp(-r * t)
    bs = bs_price(s, k, r, q, sig, t, OptionType.CALL)
    blk = black_price(f, k, sig, t, df, OptionType.CALL)
    assert abs(bs - blk) < 1e-12


def test_black_iv_roundtrip():
    px = black_price(100, 90, 0.25, 0.5, 0.95, OptionType.CALL)
    iv = black_implied_vol(px, 100, 90, 0.5, 0.95, OptionType.CALL)
    assert abs(iv - 0.25) < 1e-8


def test_bachelier_atm_and_iv():
    px = bachelier_price(0.03, 0.03, 0.005, 1.0, 1.0, OptionType.CALL)
    assert px > 0
    iv = bachelier_implied_vol(px, 0.03, 0.03, 1.0, 1.0, OptionType.CALL)
    assert abs(iv - 0.005) < 1e-8


def test_geometric_asian_cheaper_than_vanilla():
    van = bs_price(100, 100, 0.05, 0.0, 0.3, 1.0, OptionType.CALL)
    geo = geometric_asian_price(100, 100, 0.05, 0.0, 0.3, 1.0, OptionType.CALL)
    arith = turnbull_wakeman_price(100, 100, 0.05, 0.0, 0.3, 1.0, OptionType.CALL)
    assert 0 < geo < van
    assert geo < arith  # arithmetic >= geometric by AM-GM in expectation of payoff
