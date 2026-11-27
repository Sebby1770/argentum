import json

import pytest

from argentum import InputError
from argentum.studio import models_payload, risk_payload, vanilla_payload


def test_models_payload_returns_six_finite_smiles_with_skew():
    out = models_payload({})
    assert [m["name"] for m in out["models"]] == ["black_scholes", "merton", "variance_gamma", "nig", "heston", "bates"]
    json.dumps(out, allow_nan=False)
    bs = out["models"][0]["vols"]
    assert max(bs) - min(bs) < 1e-8  # Black–Scholes is flat
    heston = out["models"][4]["vols"]
    assert heston[0] > heston[10]  # negative rho skews the smile down to the right


def test_models_payload_filters_and_validates():
    out = models_payload({"models": "heston,bates", "texp": "1"})
    assert [m["name"] for m in out["models"]] == ["heston", "bates"]
    for bad in ({"texp": "0"}, {"models": "nope"}, {"heston_rho": "2"}, {"vg_nu": "nan"}):
        with pytest.raises(InputError):
            models_payload(bad)


def test_risk_payload_demo_and_posted_book():
    demo = risk_payload({})
    assert demo["underlyings"] == ["spot=100"] and demo["var"] > 0
    posted = risk_payload(
        {
            "positions": [
                {"spot": 50, "strike": 50, "vol": 0.3, "texp": 0.5, "quantity": -3, "underlying": "XYZ"},
            ],
            "alpha": "0.95",
            "horizon": "5",
            "n": "2000",
        }
    )
    assert posted["underlyings"] == ["XYZ"] and posted["alpha"] == 0.95 and posted["n_scenarios"] == 2000
    json.dumps(posted, allow_nan=False)
    with pytest.raises(InputError):
        risk_payload({"n": "10"})


def test_lab_payload_carries_an_lsm_mark_close_to_the_tree():
    out = vanilla_payload({"type": "put", "style": "american"})
    assert abs(out["lsm"] - out["tree"]) < 4 * out["lsm_error"] + 0.05
    assert out["american"] < out["tree"] + 2e-3  # BS2002 is a lower bound now


def test_risk_payload_caps_scenarios_times_positions():
    rows = [{"spot": 100, "strike": 100 + i % 7, "vol": 0.2, "texp": 1} for i in range(50)]
    with pytest.raises(InputError, match="exceeds the Studio limit"):
        risk_payload({"positions": rows, "n": "100000"})


def test_chain_payload_demo_fits_and_is_valid_json():
    from argentum.studio import chain_payload

    out = chain_payload({"models": ["heston", "bates"]})
    json.dumps(out, allow_nan=False)
    assert out["n_quotes"] == 75 and out["arbitrage"]["arbitrage_free"]
    assert out["ssvi"]["certificate"]["arbitrage_free"]
    assert [f["family"] for f in out["fits"]] == ["bates", "heston"]  # sorted by RMSE
    first = out["slices"][0]
    assert len(first["k"]) == len(first["ssvi_iv"]) == len(first["models"]["bates"])
    # Each slice is drawn over its own quoted range, not the whole chain's.
    assert min(first["k"]) > min(out["slices"][-1]["k"])


def test_chain_payload_validates_uploads():
    from argentum.studio import CHAIN_QUOTE_LIMIT, chain_payload

    with pytest.raises(InputError):
        chain_payload({"models": ["sabr"]})
    with pytest.raises(InputError):
        chain_payload({"rows": [{"texp": 1, "strike": 100, "iv": 0.2}] * (CHAIN_QUOTE_LIMIT + 1)})
    small = chain_payload(
        {
            "rows": [{"texp": 0.5, "strike": k, "type": "call", "iv": 0.2 + 0.0005 * (100 - k)} for k in range(80, 125, 5)],
            "spot": "100",
            "models": "black_scholes",
        }
    )
    assert small["n_quotes"] == 9 and small["fits"][0]["family"] == "black_scholes"
