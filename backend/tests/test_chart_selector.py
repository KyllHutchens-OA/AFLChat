"""
2A: ChartSelector._quick_heuristics team-pivot fix. A team column is normally
SQL join context (home_team/away_team), but when 2+ teams share duplicate x
values (e.g. two teams' scores per season) it IS the series to pivot on —
otherwise the line/bar builder overwrites points into one zig-zag series (B1).
"""
import pandas as pd

from app.visualization.chart_selector import ChartSelector


def test_two_teams_duplicate_season_pivots_on_team():
    data = pd.DataFrame({
        "season": [2023, 2023, 2024, 2024],
        "team": ["Geelong", "Brisbane Lions", "Geelong", "Brisbane Lions"],
        "avg_score": [88.0, 82.0, 90.0, 85.0],
    })
    config = ChartSelector._quick_heuristics(data, "", {}, "Geelong vs Brisbane avg score per season")
    assert config is not None
    assert config["group_col"] == "team"
    assert config["x_col"] == "season"


def test_single_team_column_not_pivoted_without_duplicate_x():
    # One row per season for one team: x doesn't repeat, so team stays context.
    data = pd.DataFrame({
        "season": [2023, 2024],
        "team": ["Geelong", "Geelong"],
        "avg_score": [88.0, 90.0],
    })
    config = ChartSelector._quick_heuristics(data, "", {}, "Geelong avg score per season")
    assert config is not None
    assert config["group_col"] is None


def test_too_many_teams_not_pivoted():
    # >8 distinct "teams" sharing an x isn't a sane chart dimension either.
    data = pd.DataFrame({
        "season": list(range(2015, 2025)) * 9,
        "team": [f"Team{i}" for i in range(9) for _ in range(10)],
        "value": list(range(90)),
    })
    config = ChartSelector._quick_heuristics(data, "", {}, "compare teams per season")
    assert config is not None
    assert config["group_col"] is None
