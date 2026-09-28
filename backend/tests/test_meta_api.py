from datetime import date, datetime

from app.api.meta_api import season_status


def test_after_grand_final_season_is_complete():
    s = season_status(2026, datetime(2026, 9, 26, 14, 30), 1, date(2026, 9, 28))
    assert s == {"current_season": 2026, "latest_completed_season": 2026, "in_season": False}


def test_mid_season_uses_previous_completed_season():
    s = season_status(2026, datetime(2026, 6, 1), 9, date(2026, 6, 3))
    assert s["in_season"] is True
    assert s["latest_completed_season"] == 2025


def test_finals_week_one_is_still_in_season():
    s = season_status(2026, datetime(2026, 9, 6), 4, date(2026, 9, 7))
    assert s["in_season"] is True


def test_off_season_new_year_before_first_match():
    s = season_status(2026, datetime(2026, 9, 26), 1, date(2027, 2, 1))
    assert s["latest_completed_season"] == 2026
    assert s["in_season"] is False
