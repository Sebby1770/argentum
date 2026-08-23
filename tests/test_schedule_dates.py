from argentum.time import Date, Period, make_schedule
from argentum.types import Frequency


def test_backward_semiannual_ten_year():
    sched = make_schedule(Date(2016, 8, 15), Date(2026, 8, 15), tenor=Frequency.SEMIANNUAL)
    assert sched.start == Date(2016, 8, 15)
    assert sched.end == Date(2026, 8, 15)
    assert len(sched.dates) == 21  # 20 periods + start


def test_add_months_eom():
    d = Date(2024, 1, 31)
    assert d.add_months(1) == Date(2024, 2, 29)
    assert Date(2024, 2, 29).add_months(1, end_of_month=True) == Date(2024, 3, 31)


def test_imm_third_wednesday():
    assert Date.imm(2026, 3) == Date(2026, 3, 18)
    nxt = Date.next_imm(Date(2026, 3, 1))
    assert nxt == Date(2026, 3, 18)


def test_period_parse():
    assert Period.parse("18M").years() == 1.5
    assert str(Period.parse("7D")) == "7D"


def test_excel_serial_roundtrip():
    d = Date(2026, 8, 23)
    assert Date.from_excel(d.excel_serial()) == d
