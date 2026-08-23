from argentum.models.black_scholes import price as bs_price
from argentum.models.heston import HestonParams, heston_price
from argentum.types import OptionType


def test_heston_reduces_to_bs_when_volvol_small():
    params = HestonParams(kappa=2.0, theta=0.04, sigma=0.01, rho=0.0, v0=0.04)
    heston = heston_price(100, 100, 0.05, 0.0, 1.0, params, OptionType.CALL)
    bs = bs_price(100, 100, 0.05, 0.0, 0.20, 1.0, OptionType.CALL)
    assert abs(heston - bs) < 0.15


def test_heston_put_call_parity():
    params = HestonParams(kappa=1.5, theta=0.04, sigma=0.3, rho=-0.4, v0=0.04)
    call = heston_price(100, 100, 0.03, 0.0, 1.0, params, OptionType.CALL)
    put = heston_price(100, 100, 0.03, 0.0, 1.0, params, OptionType.PUT)
    import math

    rhs = 100 - 100 * math.exp(-0.03)
    assert abs((call - put) - rhs) < 0.25


def test_feller_flag():
    ok = HestonParams(kappa=2.0, theta=0.04, sigma=0.1, rho=0.0, v0=0.04)
    bad = HestonParams(kappa=0.5, theta=0.04, sigma=1.0, rho=0.0, v0=0.04)
    assert ok.feller_ok
    assert not bad.feller_ok
