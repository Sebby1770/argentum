import argentum
import json

import pytest

from argentum.cli import main
from argentum.errors import InputError
from argentum.portfolio import book_from_rows, load_portfolio, portfolio_report, report_csv


ROWS = [
    {"tag": "core", "quantity": 2, "spot": 100, "strike": 100, "rate": 0.05, "div": 0, "vol": 0.2, "texp": 1, "type": "call"},
    {"tag": "hedge", "qty": 1, "spot": 100, "strike": 90, "rate": 0.05, "div": 0, "vol": 0.25, "texp": 0.5, "type": "put"},
]


def test_portfolio_report_groups_and_scenarios():
    report = portfolio_report(book_from_rows(ROWS))
    assert report["schema"] == "argentum.portfolio-risk.v1"
    assert report["argentum_version"] == argentum.__version__
    assert report["model_engine"] == "black_scholes"
    assert len(report["input_sha256"]) == 64
    assert report["input_positions"][0]["tag"] == "core"
    assert report["positions"] == 2
    assert set(report["by_tag"]) == {"core", "hedge"}
    assert report["summary"]["npv"] > 0
    assert report["scenarios"][0]["label"] == "base"
    assert "scenario,npv,pnl,delta,vega" in report_csv(report)


def test_load_csv_and_json(tmp_path):
    csv_path = tmp_path / "book.csv"
    csv_path.write_text(
        "tag,quantity,spot,strike,rate,div,vol,texp,type\ncore,2,100,100,.05,0,.2,1,call\n",
        encoding="utf-8",
    )
    json_path = tmp_path / "book.json"
    json_path.write_text(json.dumps({"positions": ROWS}), encoding="utf-8")
    assert len(load_portfolio(csv_path).positions) == 1
    assert len(load_portfolio(json_path).positions) == 2


@pytest.mark.parametrize(
    "row, message",
    [
        ({"spot": 100, "strike": 100, "vol": 0.2}, "texp"),
        ({"spot": 100, "strike": 100, "vol": -0.2, "texp": 1}, "positive"),
        ({"spot": 100, "strike": 100, "vol": 0.2, "texp": 1, "type": "straddle"}, "call or put"),
        ({"spot": "nan", "strike": 100, "vol": 0.2, "texp": 1}, "finite"),
    ],
)
def test_portfolio_rejects_bad_rows(row, message):
    with pytest.raises(InputError, match=message):
        book_from_rows([row])


def test_cli_portfolio_json(tmp_path, capsys):
    path = tmp_path / "book.json"
    path.write_text(json.dumps(ROWS), encoding="utf-8")
    assert main(["portfolio", str(path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["positions"] == 2
    assert payload["summary"]["engine"] == "book"
