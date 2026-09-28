"""
v3 tool tests against the dev DB (afl_dev). Facts were checked against the
DB and the spot-check table in docs/reviews/2026-09-28/6_eval_accuracy.md.

    venv/bin/python -m pytest tests/test_v3_tools.py -m integration
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.v3.tools import execute
from app.agent.v3.tools.base import ResultStore

pytestmark = pytest.mark.integration


def run(name, store=None, **args):
    r = execute(name, json.dumps(args), store or ResultStore())
    assert r["error"] is None, r["error"]
    return r["output"]


PS = dict(stats=[], season_from=None, season_to=None, round_name=None, opponent=None, venue=None,
          finals="include", per="season", agg="total")
LB = dict(agg="total", season_from=None, season_to=None, round_name=None, finals="include", team=None,
          opponent=None, min_games=None, limit=5, order="desc")
ML = dict(season=None, round_name=None, round_number=None, date=None, teams=[], finals="include",
          order_by="date", include_quarters=False, limit=5)


# ── resolve_entities ────────────────────────────────────────────────────────

def test_resolve_player_nicknames():
    out = run("resolve_entities", names=["Dusty", "Buddy", "Bont"], kind="auto", season=None)
    assert [r["name"] for r in out["rows"]] == ["Dustin Martin", "Lance Franklin", "Marcus Bontempelli"]


def test_resolve_team_nickname_and_typo():
    out = run("resolve_entities", names=["Cats", "Collingwod"], kind="auto", season=None)
    assert [(r["kind"], r["name"]) for r in out["rows"]] == [("team", "Geelong"), ("team", "Collingwood")]


def test_resolve_namesakes_return_candidates():
    out = run("resolve_entities", names=["Josh Kennedy"], kind="player", season=None)
    assert out["row_count"] >= 2
    assert any("ambiguous" in n or "matches" in n for n in out["notes"])


# ── player_stats ────────────────────────────────────────────────────────────

def test_player_career_goals_by_nickname():
    out = run("player_stats", **{**PS, "players": ["Dusty Martin"], "stats": ["goals"], "per": "career"})
    assert out["rows"][0]["goals"] == 338 and out["rows"][0]["games"] == 302


def test_player_season_average_counts_every_game():
    out = run("player_stats", **{**PS, "players": ["Patrick Cripps"], "stats": ["goals"], "season_from": 2024,
                                 "season_to": 2024, "agg": "average"})
    assert out["rows"][0]["goals_avg"] == pytest.approx(0.71, abs=0.01)


def test_player_before_debut_explains_why():
    out = run("player_stats", **{**PS, "players": ["Nick Daicos"], "season_from": 2019, "season_to": 2019})
    assert out["row_count"] == 0 and "2022" in out["why_empty"]


# ── leaderboard ─────────────────────────────────────────────────────────────

def test_leaderboard_groups_by_player_and_keeps_ties():
    out = run("leaderboard", **{**LB, "stat": "goals", "season_from": 2025, "season_to": 2025})
    assert out["rows"][0]["player"] == "Jeremy Cameron"
    assert out["row_count"] >= 5


def test_coleman_excludes_finals():
    out = run("leaderboard", **{**LB, "stat": "goals", "season_from": 2023, "season_to": 2023,
                                "finals": "exclude", "limit": 1})
    assert out["rows"][0]["player"] == "Charlie Curnow" and out["rows"][0]["goals"] == 78


def test_leaderboard_out_of_range_season():
    out = run("leaderboard", **{**LB, "stat": "goals", "season_from": 1985, "season_to": 1985})
    assert out["row_count"] == 0 and "1990" in out["why_empty"]


# ── team tools ──────────────────────────────────────────────────────────────

def test_ladder_ranks_all_teams_then_filters():
    out = run("ladder", season=2024, after_round=None, teams=["Cats"])
    assert out["rows"] == [pytest.approx(out["rows"][0])] and out["rows"][0]["position"] == 3


def test_head_to_head_since_1990():
    out = run("head_to_head", team_a="Carlton", team_b="Essendon", season_from=1990, season_to=2025, finals="include")
    s = out["summary"]
    assert (s["carlton_wins"], s["essendon_wins"], s["draws"]) == (30, 34, 4)  # 2026 R13 adds a 31st Carlton win


def test_team_results_per_season():
    out = run("team_results", teams=["Richmond"], season_from=2023, season_to=2023, opponent=None, venue=None,
              finals="include", per="season")
    row = out["rows"][0]
    assert (row["wins"], row["losses"], row["draws"]) == (10, 12, 1)


def test_team_results_total_with_goals_and_behinds():
    out = run("team_results", teams=["Sydney"], season_from=2024, season_to=2024, opponent=None, venue=None,
              finals="include", per="total")
    assert out["row_count"] == 1 and out["rows"][0]["goals"] > 300


def test_match_lookup_grand_final_score_format():
    out = run("match_lookup", **{**ML, "season": 2023, "round_name": "GF"})
    row = out["rows"][0]
    assert row["winner"] == "Collingwood" and row["home_score"] == "12.18 (90)"


def test_match_lookup_highest_total_ever():
    out = run("match_lookup", **{**ML, "order_by": "highest_total", "limit": 1})
    assert out["rows"][0]["home_points"] == 229


# ── run_sql / make_chart / news ─────────────────────────────────────────────

def test_run_sql_rejects_multiple_statements():
    r = execute("run_sql", json.dumps({"sql": "select 1; select 2", "purpose": "x"}), ResultStore())
    assert "one statement" in r["error"]


def test_run_sql_caps_rows():
    out = run("run_sql", sql="select id from player_stats", purpose="cap")
    assert out["row_count"] == 500


def test_make_chart_builds_valid_spec_and_reports_errors():
    store = ResultStore()
    data = run("player_stats", store, **{**PS, "players": ["Marcus Bontempelli"], "stats": ["disposals"]})
    ok = run("make_chart", store, result_id=data["result_id"], chart_type="line", x="season", y=["disposals"],
             series_by=None, title="Bontempelli disposals by season")
    assert ok["ok"] and store.charts[0]["chartType"] == "line"
    bad = execute("make_chart", json.dumps({"result_id": data["result_id"], "chart_type": "line", "x": "season",
                                            "y": ["nope"], "series_by": None, "title": "x"}), store)
    assert "not in result" in bad["output"]["error"]


def test_make_chart_pie_from_one_row_of_totals():
    store = ResultStore()
    data = run("team_results", store, teams=["Sydney"], season_from=2024, season_to=2024, opponent=None, venue=None,
               finals="include", per="total")
    run("make_chart", store, result_id=data["result_id"], chart_type="pie", x="team", y=["goals", "behinds"],
        series_by=None, title="Sydney scoring sources 2024")
    assert sorted(d["name"] for d in store.charts[0]["data"]) == ["Behinds", "Goals"]


def test_make_chart_player_series_highlights_by_most_common_club():
    # 2A #4: a player series_by resolves each player's club via the DB
    # (most_common_team), unlike the team case which just echoes the key.
    store = ResultStore()
    data = run("player_stats", store, **{**PS, "players": ["Patrick Cripps", "Marcus Bontempelli"],
                                         "stats": ["disposals"], "season_from": 2024, "season_to": 2024})
    run("make_chart", store, result_id=data["result_id"], chart_type="line", x="season", y=["disposals"],
        series_by="player", title="Cripps vs Bontempelli disposals, 2024")
    highlights = {s["key"]: s.get("highlight") for s in store.charts[0]["series"]}
    assert highlights.get("Patrick Cripps") == "Carlton"
    assert highlights.get("Marcus Bontempelli") == "Western Bulldogs"


def test_news_returns_rows_or_reason():
    out = run("news", query=None, teams=[], injury_only=False, days_back=60)
    assert out["row_count"] > 0 or out["why_empty"]


def test_invalid_arguments_go_back_to_model():
    r = execute("ladder", json.dumps({"season": "not a year"}), ResultStore())
    assert r["error"].startswith("invalid arguments")
