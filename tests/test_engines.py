from argentum.engines import fd_price, gbm_european
from argentum.models.black_scholes import price as bs_price
from argentum.models.bjerksund_stensland import bjerksund_stensland
from argentum.types import ExerciseStyle, OptionType


def test_fd_close_to_bs():
    bs = bs_price(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    fd = fd_price(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, n_space=250, n_time=150)
    assert abs(fd - bs) < 0.08


def test_mc_close_to_bs():
    bs = bs_price(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL)
    mc = gbm_european(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.CALL, n_paths=20_000, seed=1)
    assert abs(mc.npv - bs) < 0.25


def test_american_put_worth_more_than_european():
    euro = bs_price(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.PUT)
    amer = bjerksund_stensland(100, 100, 0.05, 0.0, 0.2, 1.0, OptionType.PUT)
    assert amer >= euro - 1e-8
    # with r>0 american put has early exercise premium
    assert amer > euro + 0.05


def test_fd_american_put_premium():
    euro = fd_price(100, 100, 0.08, 0.0, 0.3, 1.0, OptionType.PUT, ExerciseStyle.EUROPEAN)
    amer = fd_price(100, 100, 0.08, 0.0, 0.3, 1.0, OptionType.PUT, ExerciseStyle.AMERICAN)
    assert amer >= euro - 1e-6
