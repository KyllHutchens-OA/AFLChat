"""
2A: make_chart / fallback_chart chart-logic rules. No DB or network — these
build ResultStore frames directly, except the (excluded) player-highlight
lookup which needs the DB and is covered in tests/test_v3_tools.py instead.
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.v3.tools import execute
from app.agent.v3.tools.base import ResultStore
from app.agent.v3.tools.misc import fallback_chart


def run(name, store, **args):
    r = execute(name, json.dumps(args), store)
    assert r["error"] is None, r["error"]
    return r["output"]


# ── make_chart: diverging_bar (win/loss by season) ──────────────────────────

def test_diverging_bar_wins_positive_losses_negative():
    store = ResultStore()
    rid = store.put(pd.DataFrame({"season": [2023, 2024], "wins": [15, 18], "losses": [7, 4]}))
    out = run("make_chart", store, result_id=rid, chart_type="diverging_bar", x="season",
              y=["wins", "losses"], series_by=None, title="Carlton wins and losses, 2023-2024")
    assert out["chart_type"] == "groupedBar"
    row = next(r for r in store.charts[0]["data"] if r["x"] == "2023")
    assert row["wins"] == 15 and row["losses"] == -7


def test_diverging_bar_rejects_series_by():
    store = ResultStore()
    rid = store.put(pd.DataFrame({"season": [2023, 2024], "wins": [15, 18], "losses": [7, 4]}))
    r = execute("make_chart", json.dumps({"result_id": rid, "chart_type": "diverging_bar", "x": "season",
                                          "y": ["wins", "losses"], "series_by": "season", "title": "x"}), store)
    assert "series_by" in r["output"]["error"]


def test_diverging_bar_requires_exactly_two_columns():
    store = ResultStore()
    rid = store.put(pd.DataFrame({"season": [2023, 2024], "wins": [15, 18]}))
    r = execute("make_chart", json.dumps({"result_id": rid, "chart_type": "diverging_bar", "x": "season",
                                          "y": ["wins"], "series_by": None, "title": "x"}), store)
    assert "exactly 2" in r["output"]["error"]


# ── make_chart: categorical cap (2A #1) ─────────────────────────────────────

def test_bar_rejects_more_than_25_categories():
    store = ResultStore()
    df = pd.DataFrame({"player": [f"Player{i}" for i in range(30)], "disposals": list(range(30))})
    rid = store.put(df)
    r = execute("make_chart", json.dumps({"result_id": rid, "chart_type": "bar", "x": "player",
                                          "y": ["disposals"], "series_by": None, "title": "x"}), store)
    assert "too many categories" in r["output"]["error"]


# ── make_chart: highlight metadata (2A #4) ──────────────────────────────────

def test_series_by_team_highlights_each_series_with_itself():
    store = ResultStore()
    df = pd.DataFrame({
        "season": [2023, 2024, 2023, 2024], "team": ["Geelong", "Geelong", "Carlton", "Carlton"],
        "avg_score": [88.0, 90.0, 80.0, 82.0],
    })
    rid = store.put(df)
    run("make_chart", store, result_id=rid, chart_type="line", x="season", y=["avg_score"],
        series_by="team", title="Geelong vs Carlton avg score, 2023-2024")
    highlights = {s["key"]: s.get("highlight") for s in store.charts[0]["series"]}
    assert highlights == {"Geelong": "Geelong", "Carlton": "Carlton"}


def test_single_team_chart_highlights_all_series():
    store = ResultStore()
    df = pd.DataFrame({"season": [2023, 2024], "team": ["Geelong", "Geelong"], "wins": [15, 18], "losses": [7, 4]})
    rid = store.put(df)
    run("make_chart", store, result_id=rid, chart_type="diverging_bar", x="season", y=["wins", "losses"],
        series_by=None, title="Geelong wins and losses, 2023-2024")
    assert all(s.get("highlight") == "Geelong" for s in store.charts[0]["series"])


def test_single_valued_series_by_falls_back_to_multi_metric():
    # A model sometimes passes series_by='team' out of habit even for a
    # single team's own wins/losses — a second y column must not be silently
    # dropped just because the grouping column has only one distinct value.
    store = ResultStore()
    df = pd.DataFrame({
        "season": [2023, 2024], "team": ["Carlton", "Carlton"], "wins": [15, 18], "losses": [7, 4],
    })
    rid = store.put(df)
    run("make_chart", store, result_id=rid, chart_type="line", x="season", y=["wins", "losses"],
        series_by="team", title="Carlton wins and losses by season")
    spec = store.charts[0]
    assert len(spec["series"]) == 2
    assert all(s.get("highlight") == "Carlton" for s in spec["series"])


def test_no_team_or_player_column_leaves_highlight_unset():
    store = ResultStore()
    df = pd.DataFrame({"season": [2023, 2024], "disposals": [500, 520]})
    rid = store.put(df)
    run("make_chart", store, result_id=rid, chart_type="line", x="season", y=["disposals"],
        series_by=None, title="x")
    assert all("highlight" not in s for s in store.charts[0]["series"])


# ── fallback_chart: "A vs B" scatter for many rows (2A #1) ──────────────────

def test_fallback_scatter_for_vs_pattern_many_rows():
    store = ResultStore()
    df = pd.DataFrame({
        "name": [f"Player{i}" for i in range(30)],
        "contested_possessions": list(range(30)),
        "clearances": list(range(0, 60, 2)),
    })
    store.put(df)
    spec = fallback_chart("Plot contested possessions vs clearances for midfielders in 2024", store)
    assert spec is not None and spec["chartType"] == "scatter"


def test_fallback_does_not_scatter_two_teams_over_seasons():
    # "vs" here means two teams' own trend, not a many-entity scatter — the
    # team-pivot line/bar path below should win instead.
    store = ResultStore()
    df = pd.DataFrame({
        "season": list(range(2010, 2025)) * 2,
        "team": ["Geelong"] * 15 + ["Brisbane Lions"] * 15,
        "avg_score": list(range(80, 95)) + list(range(75, 90)),
    })
    store.put(df)
    spec = fallback_chart("Compare Geelong vs Brisbane average score per season", store)
    assert spec is not None and spec["chartType"] != "scatter"


# ── fallback_chart: specific titles include the season range (2A #3) ───────

def test_fallback_title_includes_season_range():
    store = ResultStore()
    df = pd.DataFrame({"season": list(range(2015, 2025)), "wins": list(range(10, 20))})
    store.put(df)
    spec = fallback_chart("Chart Collingwood's wins per season", store)
    assert spec is not None and "2015-2024" in spec["title"]
