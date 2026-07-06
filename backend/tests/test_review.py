"""
Unit tests for the review node (Milestone 3d, app/agent/review.py) and its
routing/wiring in app/agent/graph.py.

Covers:
  - should_skip_review: the deterministic "trivial template answer" skip heuristic.
  - review_results: verdict parsing (YES/NO + reason), malformed-output
    fallback (defaults to a pass-through YES so a flaky review call never
    blocks an otherwise-successful answer), and row sampling.
  - _route_after_review: routing decision (generate_sql on NO vs
    visualize/respond), gated by the review_should_regenerate flag.
  - review_node: end-to-end node behaviour — skip path, regenerate path, cap
    enforcement, once-only regen.
  - generate_sql's review_critique integration: prompt assembly + reasoning
    effort + review_verdict clearing.

Uses mocked OpenAI calls throughout — no live API or DB access.

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_review.py -v
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.review import review_results, should_skip_review, _sample_rows
from app.agent.generate_sql import generate_sql
from app.agent.prompts.generate_sql import build_review_critique_section
from app.agent.graph import AFLAnalyticsAgent, SQL_ATTEMPT_CAP
from app.agent.state import QueryIntent


def _run(coro):
    return asyncio.run(coro)


def _fake_response(payload: dict, prompt_tokens: int = 50, completion_tokens: int = 10):
    message = SimpleNamespace(content=json.dumps(payload))
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


class TestShouldSkipReview:
    def test_single_row_simple_stat_summary_mode_skips(self):
        assert should_skip_review(QueryIntent.SIMPLE_STAT, "summary", 1) is True

    def test_multi_row_simple_stat_does_not_skip(self):
        assert should_skip_review(QueryIntent.SIMPLE_STAT, "summary", 5) is False

    def test_in_depth_mode_does_not_skip_even_single_row(self):
        assert should_skip_review(QueryIntent.SIMPLE_STAT, "in_depth", 1) is False

    def test_comparison_intent_does_not_skip(self):
        assert should_skip_review(QueryIntent.PLAYER_COMPARISON, "summary", 1) is False

    def test_trend_analysis_does_not_skip(self):
        assert should_skip_review(QueryIntent.TREND_ANALYSIS, "summary", 1) is False

    def test_zero_rows_does_not_skip(self):
        # Defensive — review_node should never be reached with 0 rows anyway
        # (that routes to diagnose_empty), but the heuristic itself shouldn't
        # accidentally treat 0 as "trivial".
        assert should_skip_review(QueryIntent.SIMPLE_STAT, "summary", 0) is False


class TestSampleRows:
    def test_dataframe_sampled_and_counted(self):
        df = pd.DataFrame({"a": range(15)})
        sample, total = _sample_rows(df, limit=10)
        assert total == 15
        assert len(sample) == 10
        assert sample[0] == {"a": 0}

    def test_dataframe_smaller_than_limit(self):
        df = pd.DataFrame({"a": [1, 2]})
        sample, total = _sample_rows(df, limit=10)
        assert total == 2
        assert len(sample) == 2

    def test_list_sampled_and_counted(self):
        data = [{"x": i} for i in range(12)]
        sample, total = _sample_rows(data, limit=10)
        assert total == 12
        assert len(sample) == 10

    def test_none_returns_empty(self):
        sample, total = _sample_rows(None)
        assert sample == []
        assert total == 0


class TestReviewResultsVerdictParsing:
    def test_yes_verdict_parsed(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"verdict": "YES", "reason": "Matches the question."}
        with patch("app.agent.review.client.chat.completions.create", return_value=_fake_response(payload)):
            result = review_results(
                user_query="How many goals did Hawkins kick in 2024?",
                sql_query="SELECT SUM(goals) FROM player_stats",
                query_results=pd.DataFrame({"sum": [45]}),
                state=state,
            )
        assert result == {"verdict": "YES", "reason": "Matches the question."}
        assert state["token_usage"]["input_tokens"] == 50
        assert state["token_usage"]["output_tokens"] == 10

    def test_no_verdict_parsed(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"verdict": "NO", "reason": "Grouped by team instead of player."}
        with patch("app.agent.review.client.chat.completions.create", return_value=_fake_response(payload)):
            result = review_results(
                user_query="Who is the best defender this season?",
                sql_query="SELECT team, COUNT(*) FROM player_stats GROUP BY team",
                query_results=pd.DataFrame({"team": ["Carlton"], "count": [10]}),
                state=state,
            )
        assert result["verdict"] == "NO"
        assert "Grouped by team" in result["reason"]

    def test_verdict_is_case_insensitive(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"verdict": "no", "reason": "wrong shape"}
        with patch("app.agent.review.client.chat.completions.create", return_value=_fake_response(payload)):
            result = review_results(
                user_query="x", sql_query="SELECT 1", query_results=pd.DataFrame({"a": [1]}), state=state,
            )
        assert result["verdict"] == "NO"

    def test_malformed_verdict_defaults_to_yes_passthrough(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"verdict": "MAYBE", "reason": "unclear"}
        with patch("app.agent.review.client.chat.completions.create", return_value=_fake_response(payload)):
            result = review_results(
                user_query="x", sql_query="SELECT 1", query_results=pd.DataFrame({"a": [1]}), state=state,
            )
        assert result["verdict"] == "YES"

    def test_missing_verdict_key_defaults_to_yes_passthrough(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"reason": "no verdict field at all"}
        with patch("app.agent.review.client.chat.completions.create", return_value=_fake_response(payload)):
            result = review_results(
                user_query="x", sql_query="SELECT 1", query_results=pd.DataFrame({"a": [1]}), state=state,
            )
        assert result["verdict"] == "YES"

    def test_malformed_json_defaults_to_yes_passthrough(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        bad_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
        with patch("app.agent.review.client.chat.completions.create", return_value=bad_response):
            result = review_results(
                user_query="x", sql_query="SELECT 1", query_results=pd.DataFrame({"a": [1]}), state=state,
            )
        assert result["verdict"] == "YES"

    def test_llm_exception_defaults_to_yes_passthrough(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        with patch("app.agent.review.client.chat.completions.create", side_effect=RuntimeError("API down")):
            result = review_results(
                user_query="x", sql_query="SELECT 1", query_results=pd.DataFrame({"a": [1]}), state=state,
            )
        assert result["verdict"] == "YES"
        assert "failed" in result["reason"].lower()

    def test_uses_low_reasoning_effort(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"verdict": "YES", "reason": "ok"}
        with patch(
            "app.agent.review.client.chat.completions.create", return_value=_fake_response(payload)
        ) as mock_create:
            review_results(
                user_query="x", sql_query="SELECT 1", query_results=pd.DataFrame({"a": [1]}), state=state,
            )
        _, call_kwargs = mock_create.call_args
        assert call_kwargs["reasoning_effort"] == "low"

    def test_prompt_includes_question_sql_and_row_count(self):
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}}
        payload = {"verdict": "YES", "reason": "ok"}
        with patch(
            "app.agent.review.client.chat.completions.create", return_value=_fake_response(payload)
        ) as mock_create:
            review_results(
                user_query="Who scored the most goals?",
                sql_query="SELECT name, SUM(goals) FROM player_stats GROUP BY name",
                query_results=pd.DataFrame({"name": ["Hawkins"], "sum": [50]}),
                state=state,
            )
        _, call_kwargs = mock_create.call_args
        sent_prompt = call_kwargs["messages"][0]["content"]
        assert "Who scored the most goals?" in sent_prompt
        assert "SELECT name, SUM(goals) FROM player_stats GROUP BY name" in sent_prompt
        assert "1 row(s)" in sent_prompt
        assert "Hawkins" in sent_prompt


class TestRouteAfterReview:
    def test_should_regenerate_true_routes_to_generate_sql(self):
        assert AFLAnalyticsAgent._route_after_review({"review_should_regenerate": True}) == "generate_sql"

    def test_should_regenerate_false_falls_through_to_respond(self):
        state = {"review_should_regenerate": False, "query_results": pd.DataFrame({"a": [1]}), "requires_visualization": False}
        assert AFLAnalyticsAgent._route_after_review(state) == "respond"

    def test_should_regenerate_false_falls_through_to_visualize(self):
        state = {
            "review_should_regenerate": False,
            "query_results": pd.DataFrame({"a": [1, 2]}),
            "requires_visualization": True,
        }
        assert AFLAnalyticsAgent._route_after_review(state) == "visualize"

    def test_missing_key_defaults_to_fallthrough(self):
        state = {"query_results": pd.DataFrame({"a": [1]}), "requires_visualization": False}
        assert AFLAnalyticsAgent._route_after_review(state) == "respond"


def _base_review_state(**overrides):
    state = {
        "user_query": "Who is the best defender this season?",
        "sql_query": "SELECT team, COUNT(*) AS n FROM player_stats GROUP BY team",
        "query_results": pd.DataFrame({"team": ["Carlton"], "n": [10]}),
        "intent": QueryIntent.SIMPLE_STAT,
        "analysis_mode": "summary",
        "sql_attempts": 1,
        "review_regenerated": False,
        "token_usage": {"input_tokens": 0, "output_tokens": 0},
    }
    state.update(overrides)
    return state


class TestReviewNode:
    def test_skips_llm_for_trivial_single_row_simple_stat(self):
        agent = AFLAnalyticsAgent()
        state = _base_review_state(query_results=pd.DataFrame({"goals": [45]}))
        with patch("app.agent.review.review_results") as mock_review:
            result = _run(agent.review_node(state))
        mock_review.assert_not_called()
        assert result["review_verdict"]["verdict"] == "YES"
        assert result["review_should_regenerate"] is False

    def test_no_verdict_under_cap_regenerates_once(self):
        agent = AFLAnalyticsAgent()
        state = _base_review_state(
            intent=QueryIntent.TEAM_ANALYSIS, sql_attempts=1, review_regenerated=False
        )
        fake_verdict = {"verdict": "NO", "reason": "Grouped by team, not defensive metric."}
        with patch("app.agent.review.review_results", return_value=fake_verdict):
            result = _run(agent.review_node(state))
        assert result["review_verdict"] == fake_verdict
        assert result["review_should_regenerate"] is True
        assert result["review_regenerated"] is True

    def test_yes_verdict_does_not_regenerate(self):
        agent = AFLAnalyticsAgent()
        state = _base_review_state(intent=QueryIntent.TEAM_ANALYSIS)
        fake_verdict = {"verdict": "YES", "reason": "Looks right."}
        with patch("app.agent.review.review_results", return_value=fake_verdict):
            result = _run(agent.review_node(state))
        assert result["review_should_regenerate"] is False
        assert result["review_regenerated"] is False

    def test_already_regenerated_does_not_fire_twice(self):
        agent = AFLAnalyticsAgent()
        state = _base_review_state(
            intent=QueryIntent.TEAM_ANALYSIS, sql_attempts=2, review_regenerated=True
        )
        fake_verdict = {"verdict": "NO", "reason": "still wrong"}
        with patch("app.agent.review.review_results", return_value=fake_verdict):
            result = _run(agent.review_node(state))
        # verdict is NO, but we already used our one review-triggered regen this turn.
        assert result["review_should_regenerate"] is False

    def test_no_verdict_at_cap_does_not_regenerate(self):
        agent = AFLAnalyticsAgent()
        state = _base_review_state(
            intent=QueryIntent.TEAM_ANALYSIS, sql_attempts=SQL_ATTEMPT_CAP, review_regenerated=False
        )
        fake_verdict = {"verdict": "NO", "reason": "still wrong"}
        with patch("app.agent.review.review_results", return_value=fake_verdict):
            result = _run(agent.review_node(state))
        assert result["review_should_regenerate"] is False


class TestGenerateSqlReviewCritiqueIntegration:
    def test_review_critique_included_in_prompt_and_uses_medium_effort(self):
        payload = {"intent": "team_analysis", "sql": "SELECT name, tackles FROM player_stats", "requires_visualization": False}
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 1}
        with patch(
            "app.agent.generate_sql.client.chat.completions.create",
            return_value=_fake_response(payload),
        ) as mock_create:
            updates = generate_sql(
                user_query="Who is the best defender this season?",
                entities={}, turn_type="new_question",
                retrieved_schema_docs="", retrieved_examples=[], conversation_snippet="",
                conversation_history=[], state=state,
                review_critique="Grouped by team instead of a per-player defensive metric.",
            )
        _, call_kwargs = mock_create.call_args
        assert call_kwargs["reasoning_effort"] == "medium"
        sent_prompt = call_kwargs["messages"][0]["content"]
        assert "Grouped by team instead of a per-player defensive metric." in sent_prompt
        assert "did NOT answer the question" in sent_prompt
        # Consumed — cleared so a later retry this turn doesn't resend a stale critique.
        assert updates["review_verdict"] is None

    def test_no_review_critique_leaves_review_verdict_unset(self):
        payload = {"intent": "simple_stat", "sql": "SELECT 1", "requires_visualization": False}
        state = {"token_usage": {"input_tokens": 0, "output_tokens": 0}, "sql_attempts": 0}
        with patch(
            "app.agent.generate_sql.client.chat.completions.create",
            return_value=_fake_response(payload),
        ):
            updates = generate_sql(
                user_query="x", entities={}, turn_type="new_question",
                retrieved_schema_docs="", retrieved_examples=[], conversation_snippet="",
                conversation_history=[], state=state,
            )
        assert "review_verdict" not in updates


class TestReviewCritiqueSectionBuilder:
    def test_empty_when_no_critique(self):
        assert build_review_critique_section(None) == ""
        assert build_review_critique_section("") == ""

    def test_includes_reason_when_present(self):
        section = build_review_critique_section("Grouped by team, not player.")
        assert "Grouped by team, not player." in section
        assert "did NOT answer the question" in section
