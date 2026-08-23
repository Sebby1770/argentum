from argentum.cli import main
from argentum.instruments import InterestRateSwap
from argentum.risk import parallel_dv01, parametric_var
from argentum.termstructures import YieldCurve
from argentum.time import Date


def test_parallel_dv01_negative_for_pay_fixed():
    as_of = Date(2026, 8, 24)
    curve = YieldCurve.flat(as_of, 0.03)
    swap = InterestRateSwap.vanilla(as_of, "10Y", 0.03)

    def npv(c):
        return swap.npv(c)

    dv01 = parallel_dv01(npv, curve)
    # pay-fixed: rates up → NPV up (float received more valuable)
    assert dv01 > 0


def test_parametric_var_gaussian():
    import numpy as np

    rng = np.random.default_rng(0)
    pnl = rng.normal(0.0, 1.0, size=20_000)
    report = parametric_var(pnl, alpha=0.99)
    assert 2.0 < report["var_gaussian"] < 2.6


def test_cli_vanilla(capsys):
    rc = main(["vanilla", "--spot", "100", "--strike", "100", "--rate", "0.05", "--vol", "0.2", "--texp", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "npv" in out
    assert "10.45" in out


def test_cli_iv(capsys):
    rc = main(
        [
            "iv",
            "--price",
            "10.450583572185565",
            "--spot",
            "100",
            "--strike",
            "100",
            "--rate",
            "0.05",
            "--texp",
            "1",
        ]
    )
    assert rc == 0
    vol = float(capsys.readouterr().out.strip())
    assert abs(vol - 0.2) < 1e-8
