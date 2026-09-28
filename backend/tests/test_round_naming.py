from types import SimpleNamespace

from app.services.round_naming import fallback_round_name, resolve_round_display


def test_2026_finals_get_real_names():
    assert fallback_round_name(2026, "25") == ("Wildcard Round", True, 25)
    assert fallback_round_name(2026, "26") == ("Elimination/Qualifying Final", True, 26)
    assert fallback_round_name(2026, "27") == ("Semi Final", True, 27)
    assert fallback_round_name(2026, "28") == ("Preliminary Final", True, 28)
    assert fallback_round_name(2026, "29") == ("Grand Final", True, 29)


def test_home_and_away_round_is_not_a_final():
    name, is_final, number = fallback_round_name(2026, "10")
    assert name == "Round 10"
    assert is_final is False
    assert number == 10


def test_unknown_season_finals_get_a_generic_label():
    name, is_final, _ = fallback_round_name(2020, "26")
    assert name == "Finals Week 2"
    assert is_final is True


def test_non_numeric_round_is_passed_through():
    name, is_final, number = fallback_round_name(2026, "Grand Final")
    assert name == "Grand Final"
    assert is_final is True
    assert number is None


def test_resolve_prefers_the_migrated_match_row():
    match = SimpleNamespace(round_name="Grand Final", is_final=True, round_number=29)
    assert resolve_round_display(2026, "29", match) == ("Grand Final", True, 29)


def test_resolve_falls_back_when_no_match_row_yet():
    assert resolve_round_display(2026, "26", None) == ("Elimination/Qualifying Final", True, 26)
