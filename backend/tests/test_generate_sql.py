"""
Unit tests for the generate_sql node (Milestone 3b, app/agent/generate_sql.py)
and its prompt assembly (app/agent/prompts/generate_sql.py).

Uses a mocked OpenAI client — no live API calls or DB access.

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_generate_sql.py -v
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.generate_sql import generate_sql, _maybe_fix_group_by
from app.agent.prompts.generate_sql import (
    build_conversation_section,
    build_correction_section,
    build_error_retry_section,
    build_diagnosis_retry_section,
)
from app.agent.state import QueryIntent


def _fake_response(payload: dict, prompt_tokens: int = 100, completion_tokens: int = 20):
    """Fake llm.LLMResult (text + usage)."""
    usage = SimpleNamespace(input_tokens=prompt_tokens, output_tokens=completion_tokens)
    return SimpleNamespace(text=json.dumps(payload), usage=usage)


def _call_generate_sql(payload, **overrides):
    state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 0}
    kwargs = dict(
        user_query="How many goals did Hawkins kick in 2024?",
        entities={"players": ["Tom Hawkins"], "seasons": ["2024"]},
        turn_type="new_question",
        retrieved_schema_docs="### player_stats\n...",
        retrieved_examples=[],
        conversation_snippet="",
        conversation_history=[],
        state=state,
    )
    kwargs.update(overrides)
    with patch("app.agent.generate_sql.llm_complete", return_value=_fake_response(payload)):
        updates = generate_sql(**kwargs)
    return updates, state


class TestPromptAssembly:
    def test_conversation_section_empty_when_no_snippet(self):
        assert build_conversation_section("") == ""
        assert build_conversation_section(None) == ""

    def test_conversation_section_includes_snippet_text(self):
        section = build_conversation_section("user: hi\nassistant: hello")
        assert "user: hi" in section
        assert "Recent conversation" in section

    def test_correction_section_empty_when_nothing_provided(self):
        assert build_correction_section(None, None, None) == ""

    def test_correction_section_includes_all_fields(self):
        section = build_correction_section(
            prior_sql="SELECT 1",
            prior_answer="The answer was 1.",
            complaint_summary="User wanted 2023 not 2024.",
        )
        assert "SELECT 1" in section
        assert "The answer was 1." in section
        assert "User wanted 2023 not 2024." in section
        assert "CORRECTION" in section

    def test_error_retry_section_empty_when_missing_either_field(self):
        assert build_error_retry_section(None, None) == ""
        assert build_error_retry_section("SELECT 1", None) == ""
        assert build_error_retry_section(None, "boom") == ""

    def test_error_retry_section_includes_sql_and_error(self):
        section = build_error_retry_section(
            failed_sql="SELECT * FROM bad_table",
            sql_error='relation "bad_table" does not exist',
        )
        assert "SELECT * FROM bad_table" in section
        assert 'relation "bad_table" does not exist' in section
        assert "FAILED" in section

    def test_diagnosis_retry_section_empty_when_not_fixable(self):
        assert build_diagnosis_retry_section(None) == ""
        assert build_diagnosis_retry_section({"fixable": False, "human_reason": "x"}) == ""

    def test_diagnosis_retry_section_includes_facts_when_fixable(self):
        section = build_diagnosis_retry_section({
            "fixable": True,
            "human_reason": "Nick Daicos has no 2015 stats.",
            "suggestion": "Re-run without the season filter.",
        })
        assert "Nick Daicos has no 2015 stats." in section
        assert "Re-run without the season filter." in section


class TestGenerateSqlHappyPath:
    def test_simple_stat_sets_sql_and_intent(self):
        payload = {
            "intent": "simple_stat",
            "requires_visualization": False,
            "data_shape_hint": "single_value",
            "chart_config": {},
            "sql": "SELECT SUM(goals) FROM player_stats",
        }
        updates, state = _call_generate_sql(payload)

        assert updates["intent"] == QueryIntent.SIMPLE_STAT
        assert updates["sql_query"] == "SELECT SUM(goals) FROM player_stats"
        assert updates["pre_generated_sql"] == "SELECT SUM(goals) FROM player_stats"
        assert updates["requires_visualization"] is False
        assert updates["sql_attempts"] == 1

    def test_token_usage_accumulated(self):
        payload = {"intent": "simple_stat", "sql": "SELECT 1", "requires_visualization": False}
        _, state = _call_generate_sql(payload)
        assert state["token_usage"]["input_tokens"] == 100
        assert state["token_usage"]["output_tokens"] == 20

    def test_sql_attempts_increments_from_existing_value(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 2}
        payload = {"intent": "simple_stat", "sql": "SELECT 1", "requires_visualization": False}
        with patch("app.agent.generate_sql.llm_complete", return_value=_fake_response(payload)):
            updates = generate_sql(
                user_query="x", entities={}, turn_type="new_question",
                retrieved_schema_docs="", retrieved_examples=[], conversation_snippet="",
                conversation_history=[], state=state,
            )
        assert updates["sql_attempts"] == 3

    def test_trend_analysis_maps_data_shape_to_chart_type(self):
        payload = {
            "intent": "trend_analysis",
            "requires_visualization": True,
            "data_shape_hint": "temporal_trend",
            "chart_config": {"x_col_hint": "season", "y_col_hint": "avg_score"},
            "sql": "SELECT season, AVG(score) FROM matches GROUP BY season",
        }
        updates, _ = _call_generate_sql(payload)
        assert updates["intent"] == QueryIntent.TREND_ANALYSIS
        assert updates["llm_chart_type_hint"] == "line"
        assert updates["llm_chart_config_hint"] == {"x_col_hint": "season", "y_col_hint": "avg_score"}

    def test_ilike_prefix_bug_is_fixed(self):
        payload = {
            "intent": "simple_stat",
            "sql": "SELECT * FROM players WHERE name ILIKE 'Hawkins%'",
            "requires_visualization": False,
        }
        updates, _ = _call_generate_sql(payload)
        assert "ILIKE '%Hawkins%'" in updates["sql_query"]


class TestNoSqlIntents:
    def test_afl_news_intent_sets_no_sql(self):
        payload = {"intent": "afl_news", "sql": ""}
        updates, _ = _call_generate_sql(payload)
        assert updates["intent"] == QueryIntent.AFL_NEWS
        assert updates["pre_generated_sql"] is None
        assert updates["sql_query"] is None
        assert updates["requires_visualization"] is False

    def test_legacy_betting_odds_intent_is_off_topic(self):
        # Odds were cut; a stray "betting_odds" intent must not crash.
        payload = {"intent": "betting_odds", "sql": ""}
        updates, _ = _call_generate_sql(payload)
        assert updates["needs_clarification"] is True


class TestOffTopicHandling:
    def test_off_topic_without_followup_sets_needs_clarification(self):
        payload = {"intent": "off_topic", "sql": ""}
        updates, _ = _call_generate_sql(payload, conversation_history=[])
        assert updates["needs_clarification"] is True
        assert "AFL" in updates["clarification_question"]
        assert "intent" not in updates

    def test_off_topic_with_prior_tool_intent_becomes_followup(self):
        payload = {"intent": "off_topic", "sql": ""}
        conversation_history = [
            {"role": "user", "content": "any injuries for Collingwood?"},
            {"role": "assistant", "content": "No major injuries.", "intent": "injury_news"},
        ]
        updates, _ = _call_generate_sql(
            payload,
            user_query="what about now",
            conversation_history=conversation_history,
        )
        assert updates["intent"] == QueryIntent.INJURY_NEWS
        assert "needs_clarification" not in updates


class TestCorrectionTurns:
    def test_correction_uses_medium_reasoning_effort(self):
        payload = {"intent": "simple_stat", "sql": "SELECT 1", "requires_visualization": False}
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 0}
        with patch(
            "app.agent.generate_sql.llm_complete",
            return_value=_fake_response(payload),
        ) as mock_create:
            generate_sql(
                user_query="No, I meant 2023",
                entities={"seasons": ["2023"]},
                turn_type="correction",
                retrieved_schema_docs="",
                retrieved_examples=[],
                conversation_snippet="",
                conversation_history=[],
                state=state,
                prior_sql="SELECT COUNT(*) FROM matches WHERE season = 2024",
                prior_answer="Collingwood had 15 wins in 2024.",
                complaint_summary="User wanted 2023, not 2024.",
            )
        call_args, call_kwargs = mock_create.call_args
        assert call_kwargs["effort"] == "medium"
        # Correction-specific content must appear in the prompt sent to the LLM.
        sent_prompt = call_args[0]
        assert "SELECT COUNT(*) FROM matches WHERE season = 2024" in sent_prompt
        assert "User wanted 2023, not 2024." in sent_prompt
        assert "produce different SQL" in sent_prompt or "DIFFERENT SQL" in sent_prompt

    def test_new_question_uses_low_reasoning_effort(self):
        payload = {"intent": "simple_stat", "sql": "SELECT 1", "requires_visualization": False}
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 0}
        with patch(
            "app.agent.generate_sql.llm_complete",
            return_value=_fake_response(payload),
        ) as mock_create:
            generate_sql(
                user_query="How many goals did Hawkins kick in 2024?",
                entities={}, turn_type="new_question",
                retrieved_schema_docs="", retrieved_examples=[], conversation_snippet="",
                conversation_history=[], state=state,
            )
        call_args, call_kwargs = mock_create.call_args
        assert call_kwargs["effort"] == "low"


class TestErrorFallback:
    def test_llm_exception_falls_back_gracefully(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 0}
        with patch(
            "app.agent.generate_sql.llm_complete",
            side_effect=RuntimeError("API down"),
        ):
            updates = generate_sql(
                user_query="anything", entities={}, turn_type="new_question",
                retrieved_schema_docs="", retrieved_examples=[], conversation_snippet="",
                conversation_history=[], state=state,
            )
        assert updates["intent"] == QueryIntent.SIMPLE_STAT
        assert updates["pre_generated_sql"] is None
        assert updates["sql_query"] is None
        assert "execution_error" not in updates

    def test_invalid_sql_falls_back_gracefully(self):
        payload = {"intent": "simple_stat", "sql": "DROP TABLE matches", "requires_visualization": False}
        updates, _ = _call_generate_sql(payload)
        assert updates["intent"] == QueryIntent.SIMPLE_STAT
        assert updates["pre_generated_sql"] is None


class TestSelfCorrectRetryTurns:
    """Milestone 3c: generate_sql called as a self-correct/diagnose-driven retry."""

    def test_db_error_retry_uses_medium_reasoning_and_includes_error_in_prompt(self):
        payload = {"intent": "simple_stat", "sql": "SELECT 2", "requires_visualization": False}
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 1}
        with patch(
            "app.agent.generate_sql.llm_complete",
            return_value=_fake_response(payload),
        ) as mock_create:
            updates = generate_sql(
                user_query="How many goals did Hawkins kick in 2024?",
                entities={}, turn_type="new_question",
                retrieved_schema_docs="", retrieved_examples=[], conversation_snippet="",
                conversation_history=[], state=state,
                failed_sql="SELECT * FROM bad_table",
                sql_error='relation "bad_table" does not exist',
            )
        call_args, call_kwargs = mock_create.call_args
        assert call_kwargs["effort"] == "medium"
        sent_prompt = call_args[0]
        assert "SELECT * FROM bad_table" in sent_prompt
        assert 'relation "bad_table" does not exist' in sent_prompt
        assert updates["sql_attempts"] == 2

    def test_diagnosis_retry_includes_diagnosis_facts_and_clears_diagnosis(self):
        payload = {"intent": "simple_stat", "sql": "SELECT 3", "requires_visualization": False}
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 1}
        diagnosis = {
            "reason_code": "player_season_mismatch",
            "fixable": True,
            "human_reason": "Nick Daicos has no 2015 stats.",
            "suggestion": "Re-run without pinning the season.",
        }
        with patch(
            "app.agent.generate_sql.llm_complete",
            return_value=_fake_response(payload),
        ) as mock_create:
            updates = generate_sql(
                user_query="What are Nick Daicos's career stats?",
                entities={}, turn_type="new_question",
                retrieved_schema_docs="", retrieved_examples=[], conversation_snippet="",
                conversation_history=[], state=state,
                diagnosis=diagnosis,
            )
        call_args, call_kwargs = mock_create.call_args
        assert call_kwargs["effort"] == "medium"
        sent_prompt = call_args[0]
        assert "Nick Daicos has no 2015 stats." in sent_prompt
        assert "Re-run without pinning the season." in sent_prompt
        # Consumed — cleared so a later retry this turn doesn't resend stale facts.
        assert updates["diagnosis"] is None


class TestGroupByPrePass:
    def test_adds_group_by_when_missing_and_aggregate_present(self):
        sql = "SELECT p.name, SUM(ps.goals) AS total_goals FROM player_stats ps JOIN players p ON ps.player_id = p.id"
        fixed = _maybe_fix_group_by(sql)
        assert "GROUP BY" in fixed.upper()

    def test_leaves_sql_with_existing_group_by_untouched(self):
        sql = "SELECT p.name, SUM(ps.goals) FROM player_stats ps JOIN players p ON ps.player_id = p.id GROUP BY p.name"
        assert _maybe_fix_group_by(sql) == sql

    def test_leaves_cte_untouched(self):
        sql = "WITH x AS (SELECT 1) SELECT SUM(a), b FROM x"
        assert _maybe_fix_group_by(sql) == sql

    def test_leaves_window_function_query_untouched(self):
        sql = "SELECT name, RANK() OVER (ORDER BY wins DESC) AS position FROM ranked"
        assert _maybe_fix_group_by(sql) == sql

    def test_leaves_query_without_aggregate_untouched(self):
        sql = "SELECT name, team FROM players WHERE name ILIKE '%cripps%'"
        assert _maybe_fix_group_by(sql) == sql
