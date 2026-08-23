from argentum.models.black import black_price
from argentum.models.sabr import sabr_implied_vol, sabr_price
from argentum.models.svi import RawSVI, svi_from_atm
from argentum.types import OptionType


def test_sabr_atm_positive_and_smile():
    f, t, alpha, beta, rho, nu = 0.03, 5.0, 0.04, 0.5, -0.3, 0.5
    atm = sabr_implied_vol(f, f, t, alpha, beta, rho, nu)
    otm = sabr_implied_vol(f, f * 1.2, t, alpha, beta, rho, nu)
    itm = sabr_implied_vol(f, f * 0.8, t, alpha, beta, rho, nu)
    assert atm > 0 and otm > 0 and itm > 0
    # typical negative-rho equity/rates skew: low strike vol > high strike vol
    assert itm > otm


def test_sabr_zero_nu_is_cev_like_flatish_when_beta_1():
    f, t, alpha = 100.0, 1.0, 0.2
    v1 = sabr_implied_vol(f, f, t, alpha, 1.0, 0.0, 0.0)
    v2 = sabr_implied_vol(f, 90.0, t, alpha, 1.0, 0.0, 0.0)
    assert abs(v1 - 0.2) < 0.01
    assert abs(v2 - 0.2) < 0.03


def test_sabr_price_matches_black_of_implied():
    f, k, t = 100.0, 100.0, 1.0
    vol = sabr_implied_vol(f, k, t, 0.2, 1.0, 0.0, 0.0)
    a = sabr_price(f, k, t, 0.2, 1.0, 0.0, 0.0, df=1.0)
    b = black_price(f, k, vol, t, 1.0, OptionType.CALL)
    assert abs(a - b) < 1e-12


def test_svi_total_variance_positive_and_butterfly():
    svi = svi_from_atm(0.2, 1.0, b=0.2, rho=-0.4, m=0.0, sigma=0.15)
    assert svi.total_variance(0.0) > 0
    assert svi.implied_vol(0.0, 1.0) > 0
    assert svi.butterfly_ok()
