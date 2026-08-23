from argentum.time import TARGET, Date, UnitedKingdom, UnitedStatesNYSE, UnitedStatesSettlement, calendar
from argentum.types import BusinessDayConvention as BDC


def test_target_good_friday_2026():
    cal = TARGET()
    assert cal.is_holiday(Date(2026, 4, 3))  # Good Friday
    assert cal.is_holiday(Date(2026, 4, 6))  # Easter Monday
    assert cal.is_business_day(Date(2026, 4, 7))


def test_target_christmas():
    cal = TARGET()
    assert cal.is_holiday(Date(2026, 12, 25))
    assert cal.is_holiday(Date(2026, 12, 26))
    assert cal.is_holiday(Date(2026, 1, 1))


def test_us_mlk_2026():
    # 3rd Monday of January 2026 = 19 Jan
    cal = UnitedStatesSettlement()
    assert cal.is_holiday(Date(2026, 1, 19))
    assert cal.is_business_day(Date(2026, 1, 20))


def test_modified_following_month_end():
    cal = TARGET()
    # 2026-01-01 is a Thursday holiday → following is Jan 2
    adj = cal.adjust(Date(2026, 1, 1), BDC.MODIFIED_FOLLOWING)
    assert adj == Date(2026, 1, 2)


def test_calendar_factory():
    assert calendar("target").name == "TARGET"
    assert calendar("us-nyse").name == "US NYSE"
    assert isinstance(calendar("uk"), UnitedKingdom)


def test_nyse_good_friday():
    assert UnitedStatesNYSE().is_holiday(Date(2026, 4, 3))


def test_weekend():
    cal = TARGET()
    assert cal.is_holiday(Date(2026, 8, 22))  # Saturday
    assert cal.is_holiday(Date(2026, 8, 23))  # Sunday
