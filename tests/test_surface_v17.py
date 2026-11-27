import math

import numpy as np
import pytest

from argentum import InputError, price
from argentum.calibration import levenberg_marquardt
from argentum.calibration.cos import FAMILIES, calibrate_model, model_prices
from argentum.chain import chain_from_rows, check_arbitrage, demo_chain
from argentum.errors import ConvergenceError
from argentum.models.dupire import gatheral_local_var
from argentum.models.ssvi import SSVISurface, fit_ssvi, local_vol_grid, ssvi_from_params

TRUE = ssvi_from_params(-0.6, 1.1, 0.35, [0.1, 0.25, 0.5, 1.0, 2.0], [0.004, 0.0095, 0.019, 0.039, 0.08])


def _grid(surface: SSVISurface):
    k, t = np.meshgrid(np.linspace(-0.6, 0.4, 15), surface.expiries)
    return k.ravel(), t.ravel()


# ---------------------------------------------------------------- SSVI
def test_ssvi_fit_recovers_known_parameters():
    k, t = _grid(TRUE)
    fit = fit_ssvi(k, t, TRUE.implied_vol(k, t))
    assert fit.rho == pytest.approx(-0.6, abs=1e-5)
    assert fit.eta == pytest.approx(1.1, abs=1e-5)
    assert fit.gamma == pytest.approx(0.35, abs=1e-5)
    np.testing.assert_allclose(fit.thetas, TRUE.thetas, rtol=1e-5)
    assert fit.meta["rmse_vol"] < 1e-7


def test_ssvi_certificate_and_atm_slice():
    report = TRUE.no_arbitrage()
    assert report["butterfly_condition"] and report["calendar_condition"] and report["arbitrage_free"]
    assert report["eta_one_plus_abs_rho"] == pytest.approx(1.1 * 1.6)
    # At k = 0 the total variance is exactly θ_t.
    np.testing.assert_allclose(TRUE.total_variance(0.0, np.array(TRUE.expiries)), TRUE.thetas, rtol=1e-14)


def test_ssvi_flags_butterfly_arbitrage_when_eta_is_too_large():
    wild = ssvi_from_params(-0.9, 8.0, 0.5, [0.5, 1.0], [0.02, 0.04])
    report = wild.no_arbitrage()
    assert not report["butterfly_condition"]
    assert report["min_density_factor"] < 0.0 and not report["arbitrage_free"]
    with pytest.raises(InputError):
        wild.local_vol(np.linspace(-1.5, 1.5, 61), 0.5)


def test_constrained_fit_stays_arbitrage_free_on_noisy_skewed_data():
    fit = fit_ssvi(demo_chain().log_moneyness, demo_chain().texp, demo_chain().iv)
    assert fit.eta * (1 + abs(fit.rho)) <= 2.0 + 1e-12 and 0 < fit.gamma <= 0.5
    assert fit.no_arbitrage()["arbitrage_free"]
    assert fit.meta["rmse_vol"] < 0.015  # a 3-parameter shape on a jump-model chain


@pytest.mark.parametrize("k,t", [(-0.3, 0.4), (0.1, 0.7), (0.0, 1.5), (0.3, 0.12)])
def test_closed_form_local_vol_matches_finite_difference_dupire(k, t):
    numeric = math.sqrt(gatheral_local_var(k, t, lambda kk, tt: float(TRUE.total_variance(kk, tt))))
    assert float(TRUE.local_vol(k, t)) == pytest.approx(numeric, rel=1e-6)


def test_local_vol_grid_shape_and_validation():
    grid = local_vol_grid(TRUE, [-0.2, 0.0, 0.2], [0.25, 1.0])
    assert np.array(grid["local_vol"]).shape == (2, 3)
    with pytest.raises(InputError):
        ssvi_from_params(0.0, 1.0, 0.4, [1.0, 0.5], [0.01, 0.02])  # expiries out of order
    with pytest.raises(InputError):
        ssvi_from_params(0.0, 1.0, 0.4, [0.5, 1.0], [0.02, 0.01])  # calendar arbitrage
    with pytest.raises(InputError):
        fit_ssvi([0.0], [1.0], [0.2])


# ---------------------------------------------------------------- chain
def test_chain_from_rows_accepts_prices_mids_ivs_and_days_and_reports_drops():
    rows = [
        {"texp": 0.5, "strike": 100, "type": "call", "price": price(100, 100, 0.02, 0.0, 0.25, 0.5, "call")},
        {"days": 182.5, "strike": 90, "type": "put", "bid": 1.9, "ask": 2.1},
        {"texp": 0.5, "strike": 110, "type": "call", "iv": 0.22},
        {"texp": 0.5, "strike": 120, "type": "call", "price": 500.0},  # above the upper bound
        {"texp": 0.5, "type": "call", "price": 1.0},  # no strike
        {"texp": 0.5, "strike": 95, "type": "straddle", "price": 1.0},
    ]
    chain = chain_from_rows(rows, spot=100.0, rate=0.02)
    assert chain.size == 3
    assert chain.iv[chain.strike == 100][0] == pytest.approx(0.25, abs=1e-10)
    assert chain.price[chain.strike == 110][0] == pytest.approx(price(100, 110, 0.02, 0.0, 0.22, 0.5, "call"))
    reasons = " ".join(d["reason"] for d in chain.dropped)
    assert len(chain.dropped) == 3 and "bounds" in reasons and "strike" in reasons and "straddle" in reasons
    assert sorted(d["row"] for d in chain.dropped) == [4, 5, 6]
    with pytest.raises(InputError):
        chain_from_rows([], spot=100.0)


def test_arbitrage_scan_is_clean_on_a_model_chain_and_finds_planted_violations():
    chain = demo_chain(noise_vol=0.0)
    assert check_arbitrage(chain)["arbitrage_free"]
    rows = chain.rows()
    for r in rows:
        r.pop("iv")
    mid = len(rows) // 2
    rows[mid]["price"] *= 1.5  # a bump in the middle of a slice: butterfly
    found = check_arbitrage(chain_from_rows(rows, spot=100.0, rate=0.03, div=0.01))
    assert found["counts"]["butterfly"] >= 1 and not found["arbitrage_free"]


def test_calendar_arbitrage_is_detected():
    rows = [
        {"texp": t, "strike": k, "type": "call", "iv": v}
        for t, v in ((0.5, 0.30), (1.0, 0.15))  # 1y total variance 0.0225 < 6m 0.045
        for k in (90.0, 100.0, 110.0)
    ]
    report = check_arbitrage(chain_from_rows(rows, spot=100.0))
    assert report["counts"]["calendar"] == 3


def test_demo_chain_is_seeded_and_synthetic():
    a, b = demo_chain(), demo_chain()
    np.testing.assert_array_equal(a.iv, b.iv)
    assert a.size == 75 and a.otm().all()


# ---------------------------------------------------------------- calibration
def test_bates_calibration_recovers_the_generating_model():
    result = calibrate_model(demo_chain(), "bates")
    p = result.params
    assert p["rho"] == pytest.approx(-0.75, abs=0.03)
    assert p["v0"] == pytest.approx(0.025, abs=0.002)
    assert p["mu_j"] == pytest.approx(-0.12, abs=0.02)
    assert result.rmse_vol < 0.0025  # the injected noise is 0.2 vol points
    assert result.n_below_precision == 0


def test_model_ranking_on_a_bates_chain():
    chain = demo_chain()
    rmse = {fam: calibrate_model(chain, fam).rmse_vol for fam in ("black_scholes", "heston", "bates")}
    assert rmse["bates"] < rmse["heston"] < rmse["black_scholes"]


def test_black_scholes_calibration_on_a_flat_chain_is_exact():
    rows = [
        {"texp": t, "strike": k, "type": "call" if k >= 100 else "put", "price": price(100, k, 0.01, 0.0, 0.27, t, "call" if k >= 100 else "put")}
        for t in (0.25, 1.0)
        for k in (80.0, 90.0, 100.0, 110.0, 125.0)
    ]
    result = calibrate_model(chain_from_rows(rows, spot=100.0, rate=0.01), "black_scholes")
    assert result.params["vol"] == pytest.approx(0.27, abs=1e-6)
    assert result.rmse_vol < 1e-6


def test_model_prices_match_quote_types_and_unknown_family_is_rejected():
    chain = demo_chain()
    prices = model_prices(FAMILIES["bates"].build(FAMILIES["bates"].x0), chain)
    assert prices.shape == chain.price.shape and np.all(prices >= 0.0)
    with pytest.raises(InputError):
        calibrate_model(chain, "sabr")
    with pytest.raises(InputError):
        calibrate_model(chain, "heston", x0=[1.0])


def test_levenberg_marquardt_non_strict_returns_best_iterate():
    def residual(x):
        return np.array([x[0] - 3.0, 10.0 * (x[1] - x[0] ** 2)])

    with pytest.raises(ConvergenceError):
        levenberg_marquardt(residual, np.array([0.0, 0.0]), maxiter=1, ftol=0.0, xtol=0.0)
    x = levenberg_marquardt(residual, np.array([0.0, 0.0]), maxiter=1, ftol=0.0, xtol=0.0, strict=False)
    assert np.all(np.isfinite(x))


def test_load_chain_reads_csv_with_bom_and_json(tmp_path):
    from argentum.chain import load_chain

    csv_path = tmp_path / "chain.csv"
    csv_path.write_text("﻿Texp,Strike,Type,IV\n0.5,90,put,0.24\n0.5,100,call,0.2\n0.5,110,call,0.19\n", encoding="utf-8")
    chain = load_chain(csv_path, spot=100.0)
    assert chain.size == 3 and chain.iv.tolist() == [0.24, 0.2, 0.19]
    json_path = tmp_path / "chain.json"
    json_path.write_text('{"rows": [{"texp": 1, "strike": 100, "type": "call", "iv": 0.3}]}', encoding="utf-8")
    assert load_chain(json_path, spot=100.0).size == 1
    with pytest.raises(InputError):
        load_chain(tmp_path / "chain.txt", spot=100.0)


def test_chain_cli_text_json_and_errors(capsys):
    from argentum.cli import main

    args = ["chain", "examples/sample_chain.csv", "--spot", "100", "--rate", "0.03", "--div", "0.01", "--models", "bates"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "arbitrage  none" in out and "arbitrage-free" in out and "bates" in out
    assert main([*args, "--json"]) == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["fits"][0]["family"] == "bates" and payload["n_quotes"] == 75
    assert main(["chain", "missing.csv", "--spot", "100"]) == 1
    assert main(["chain", "examples/sample_chain.csv", "--spot", "100", "--models", "sabr"]) == 1
