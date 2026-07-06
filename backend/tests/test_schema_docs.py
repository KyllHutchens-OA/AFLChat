"""
Unit tests for schema pruning (app/agent/schema_docs.py, Milestone 3b).

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_schema_docs.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.schema_docs import get_schema_docs, get_all_table_names, SCHEMA_DOCS


class TestSchemaDocsContent:
    def test_all_documented_tables_have_nonempty_docs(self):
        for table, doc in SCHEMA_DOCS.items():
            assert doc.strip(), f"{table} has an empty doc string"

    def test_get_all_table_names_matches_schema_docs_keys(self):
        assert get_all_table_names() == frozenset(SCHEMA_DOCS.keys())


class TestPruningPlayerQueries:
    """Player queries -> players + player_stats + matches (per the milestone spec)."""

    def test_player_named_pulls_in_player_tables(self):
        docs = get_schema_docs("simple_stat", {"players": ["Patrick Cripps"], "seasons": ["2023"]})
        assert "### players" in docs
        assert "### player_stats" in docs
        assert "### matches" in docs

    def test_player_comparison_intent_pulls_in_player_tables_even_without_named_players(self):
        docs = get_schema_docs("player_comparison", {"seasons": ["2023"]})
        assert "### players" in docs
        assert "### player_stats" in docs

    def test_player_metric_keyword_pulls_in_player_tables(self):
        docs = get_schema_docs("simple_stat", {"metrics": ["disposals"], "seasons": ["2023"]})
        assert "### player_stats" in docs


class TestPruningTeamRecordQueries:
    """Team record queries -> matches + teams (per the milestone spec), no player tables."""

    def test_team_record_query_excludes_player_tables(self):
        docs = get_schema_docs("team_analysis", {"teams": ["Carlton"], "seasons": ["2019"]})
        assert "### matches" in docs
        assert "### teams" in docs
        assert "### players" not in docs
        assert "### player_stats" not in docs

    def test_team_analysis_with_advanced_metric_pulls_in_team_stats(self):
        docs = get_schema_docs("team_analysis", {"teams": ["Carlton"], "metrics": ["inside 50s"]})
        assert "### team_stats" in docs

    def test_team_analysis_without_advanced_metric_excludes_team_stats(self):
        docs = get_schema_docs("team_analysis", {"teams": ["Carlton"], "seasons": ["2019"]})
        assert "### team_stats" not in docs


class TestPruningLiveGames:
    def test_no_season_specified_includes_live_games(self):
        docs = get_schema_docs("simple_stat", {"teams": ["Richmond"]})
        assert "### live_games" in docs

    def test_old_season_excludes_live_games(self):
        docs = get_schema_docs("simple_stat", {"teams": ["Richmond"], "seasons": ["2015"]})
        assert "### live_games" not in docs

    def test_current_season_includes_live_games(self):
        docs = get_schema_docs("simple_stat", {"teams": ["Richmond"], "seasons": ["2026"]})
        assert "### live_games" in docs


class TestPruningToolIntents:
    def test_betting_odds_intent_pulls_in_betting_odds_table(self):
        docs = get_schema_docs("betting_odds", {})
        assert "### betting_odds" in docs

    def test_tipping_advice_intent_pulls_in_squiggle_predictions(self):
        docs = get_schema_docs("tipping_advice", {})
        assert "### squiggle_predictions" in docs

    def test_simple_stat_intent_excludes_betting_and_tipping_tables(self):
        docs = get_schema_docs("simple_stat", {"teams": ["Carlton"], "seasons": ["2019"]})
        assert "### betting_odds" not in docs
        assert "### squiggle_predictions" not in docs


class TestPruningDeterminism:
    def test_same_inputs_produce_identical_output(self):
        entities = {"players": ["Cripps"], "seasons": ["2023"]}
        first = get_schema_docs("simple_stat", entities)
        second = get_schema_docs("simple_stat", entities)
        assert first == second

    def test_none_intent_and_empty_entities_does_not_crash(self):
        docs = get_schema_docs(None, None)
        assert "### matches" in docs
        assert "### teams" in docs

    def test_queryintent_enum_style_string_is_normalized(self):
        # Real callers may pass a QueryIntent enum whose str() looks like
        # "QueryIntent.TEAM_ANALYSIS" — must normalize the same as "team_analysis".
        docs_enum_style = get_schema_docs("QueryIntent.team_analysis", {"teams": ["Carlton"], "metrics": ["clearances"]})
        docs_plain = get_schema_docs("team_analysis", {"teams": ["Carlton"], "metrics": ["clearances"]})
        assert docs_enum_style == docs_plain
