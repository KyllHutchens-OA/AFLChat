"""
Unit tests for the Milestone 3c self-correct loop and diagnose_empty wiring in
app/agent/graph.py:
  - execute -> generate_sql on DB error (self-correct)
  - execute -> diagnose_empty on 0 rows -> generate_sql once if fixable, else respond
  - the shared SQL_ATTEMPT_CAP (3 total generate_sql calls/turn) enforced across both loops
  - respond_node consumes diagnose_empty's facts instead of guessing via LLM

Uses mocked OpenAI/DB calls throughout — no live API or DB access.

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_self_correct.py -v
"""
import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.graph import AFLAnalyticsAgent, SQL_ATTEMPT_CAP
from app.agent.state import QueryIntent


def _base_state(**overrides):
    state = {
        "user_query": "How many goals did Hawkins kick in 2024?",
        "entities": {"players": ["Tom Hawkins"], "seasons": ["2024"]},
        "intent": QueryIntent.SIMPLE_STAT,
        "requires_visualization": False,
        "analysis_mode": "summary",
        "analysis_types": ["average"],
        "conversation_history": [],
        "bypass_cache": True,  # skip real cache reads in tests
        "sql_attempts": 1,
        "errors": [],
        "token_usage": {"input_tokens": 0, "output_tokens": 0},
        "warnings": [],
    }
    state.update(overrides)
    return state


def _run(coro):
    return asyncio.run(coro)


class TestRouteAfterExecuteV2:
    def test_sql_error_routes_to_generate_sql(self):
        state = {"sql_error": "syntax error", "query_results": None}
        assert AFLAnalyticsAgent._route_after_execute_v2(state) == "generate_sql"

    def test_zero_rows_db_intent_routes_to_diagnose_empty(self):
        import pandas as pd
        state = {
            "sql_error": None,
            "execution_error": None,
            "query_results": pd.DataFrame(),
            "intent": QueryIntent.SIMPLE_STAT,
        }
        assert AFLAnalyticsAgent._route_after_execute_v2(state) == "diagnose_empty"

    def test_zero_rows_tool_intent_does_not_diagnose(self):
        state = {
            "sql_error": None,
            "execution_error": None,
            "query_results": [],
            "intent": QueryIntent.AFL_NEWS,
            "requires_visualization": False,
        }
        assert AFLAnalyticsAgent._route_after_execute_v2(state) == "respond"

    def test_execution_error_present_skips_diagnose(self):
        import pandas as pd
        state = {
            "sql_error": None,
            "execution_error": "Database query failed after 3 attempts",
            "query_results": pd.DataFrame(),
            "intent": QueryIntent.SIMPLE_STAT,
            "requires_visualization": False,
        }
        assert AFLAnalyticsAgent._route_after_execute_v2(state) == "respond"

    def test_nonempty_results_for_sql_backed_intent_routes_to_review(self):
        # Milestone 3d: non-empty rows from a SQL-backed intent go through
        # `review` (a cheap LLM sanity-check) before visualize/respond — this
        # replaces the old direct-to-visualize routing tested here pre-3d.
        import pandas as pd
        state = {
            "sql_error": None,
            "execution_error": None,
            "query_results": pd.DataFrame({"a": [1, 2]}),
            "intent": QueryIntent.TREND_ANALYSIS,
            "requires_visualization": True,
        }
        assert AFLAnalyticsAgent._route_after_execute_v2(state) == "review"

    def test_nonempty_results_for_tool_intent_skips_review(self):
        # Tool intents (news/odds/tips) have no SQL to review — they fall
        # straight through to the same visualize/respond decision v1 uses.
        state = {
            "sql_error": None,
            "execution_error": None,
            "query_results": [{"headline": "AFL news"}],
            "intent": QueryIntent.AFL_NEWS,
            "requires_visualization": False,
        }
        assert AFLAnalyticsAgent._route_after_execute_v2(state) == "respond"


class TestRouteAfterDiagnoseEmpty:
    def test_should_regenerate_true_routes_to_generate_sql(self):
        assert AFLAnalyticsAgent._route_after_diagnose_empty({"diagnose_should_regenerate": True}) == "generate_sql"

    def test_should_regenerate_false_routes_to_respond(self):
        assert AFLAnalyticsAgent._route_after_diagnose_empty({"diagnose_should_regenerate": False}) == "respond"

    def test_missing_key_defaults_to_respond(self):
        assert AFLAnalyticsAgent._route_after_diagnose_empty({}) == "respond"


class TestSignalV2SqlFailureCapEnforcement:
    def test_under_cap_sets_retryable_signal(self):
        agent = AFLAnalyticsAgent()
        state = _base_state(sql_attempts=1)
        result = agent._signal_v2_sql_failure(state, raw_error="syntax error near FROM", failed_sql="SELECT * FRM x")
        assert result["sql_error"] == "syntax error near FROM"
        assert result["failed_sql"] == "SELECT * FRM x"
        assert "execution_error" not in result or result.get("execution_error") is None

    def test_at_cap_falls_through_to_honest_failure(self):
        agent = AFLAnalyticsAgent()
        state = _base_state(sql_attempts=SQL_ATTEMPT_CAP)
        result = agent._signal_v2_sql_failure(state, raw_error="syntax error near FROM", failed_sql="SELECT * FRM x")
        assert result["sql_error"] is None
        assert result["failed_sql"] is None
        assert result["execution_error"] is not None
        assert "3 attempts" in result["execution_error"]

    def test_one_under_cap_still_retries(self):
        agent = AFLAnalyticsAgent()
        state = _base_state(sql_attempts=SQL_ATTEMPT_CAP - 1)
        result = agent._signal_v2_sql_failure(state, raw_error="boom", failed_sql="SELECT 1")
        assert result["sql_error"] == "boom"


class TestExecuteNodeMissingSql:
    """Milestone 3c: a missing pre_generated_sql is a retryable self-correct signal."""

    def test_missing_pre_generated_sql_signals_retry(self):
        state = _base_state(pre_generated_sql=None)
        agent = AFLAnalyticsAgent()

        result = _run(agent.execute_node(state))

        assert result["sql_error"] is not None
        assert result.get("query_results") is None


class TestExecuteNodeDbErrorSelfCorrect:
    def test_db_error_sets_sql_error(self):
        state = _base_state(pre_generated_sql="SELECT * FROM bad_table", sql_attempts=1)
        agent = AFLAnalyticsAgent()

        with patch(
            "app.agent.graph.DatabaseTool.query_database",
            return_value={"success": False, "error": "safe message", "raw_error": 'relation "bad_table" does not exist', "data": None, "rows_returned": 0},
        ):
            result = _run(agent.execute_node(state))

        assert result["sql_error"] == 'relation "bad_table" does not exist'
        assert result["failed_sql"] == "SELECT * FROM bad_table"

    def test_db_error_at_cap_produces_honest_failure(self):
        state = _base_state(pre_generated_sql="SELECT * FROM bad_table", sql_attempts=SQL_ATTEMPT_CAP)
        agent = AFLAnalyticsAgent()

        with patch(
            "app.agent.graph.DatabaseTool.query_database",
            return_value={"success": False, "error": "safe message", "raw_error": "still broken", "data": None, "rows_returned": 0},
        ):
            result = _run(agent.execute_node(state))

        assert result["sql_error"] is None
        assert result["execution_error"] is not None


class TestDiagnoseEmptyNode:
    def test_fixable_diagnosis_under_cap_regenerates_once(self):
        state = _base_state(sql_attempts=1, diagnose_regenerated=False)
        agent = AFLAnalyticsAgent()

        fake_diagnosis = {
            "reason_code": "player_season_mismatch",
            "human_reason": "Tom Hawkins has no 2030 stats.",
            "fixable": True,
            "suggestion": "Re-run without the season filter.",
        }
        with patch("app.agent.diagnose_empty.diagnose_empty", return_value=fake_diagnosis):
            result = _run(agent.diagnose_empty_node(state))

        assert result["diagnosis"] == fake_diagnosis
        assert result["diagnose_should_regenerate"] is True
        assert result["diagnose_regenerated"] is True

    def test_not_fixable_diagnosis_does_not_regenerate(self):
        state = _base_state(sql_attempts=1, diagnose_regenerated=False)
        agent = AFLAnalyticsAgent()

        fake_diagnosis = {
            "reason_code": "season_out_of_range",
            "human_reason": "2030 is outside the data we have.",
            "fixable": False,
            "suggestion": None,
        }
        with patch("app.agent.diagnose_empty.diagnose_empty", return_value=fake_diagnosis):
            result = _run(agent.diagnose_empty_node(state))

        assert result["diagnose_should_regenerate"] is False
        assert result["diagnose_regenerated"] is False

    def test_already_regenerated_does_not_fire_twice(self):
        state = _base_state(sql_attempts=2, diagnose_regenerated=True)
        agent = AFLAnalyticsAgent()

        fake_diagnosis = {
            "reason_code": "player_season_mismatch",
            "human_reason": "still empty",
            "fixable": True,
            "suggestion": "try again",
        }
        with patch("app.agent.diagnose_empty.diagnose_empty", return_value=fake_diagnosis):
            result = _run(agent.diagnose_empty_node(state))

        # fixable=True, but we already used our one diagnose-triggered regen this turn.
        assert result["diagnose_should_regenerate"] is False

    def test_fixable_but_at_cap_does_not_regenerate(self):
        state = _base_state(sql_attempts=SQL_ATTEMPT_CAP, diagnose_regenerated=False)
        agent = AFLAnalyticsAgent()

        fake_diagnosis = {
            "reason_code": "player_season_mismatch",
            "human_reason": "still empty",
            "fixable": True,
            "suggestion": "try again",
        }
        with patch("app.agent.diagnose_empty.diagnose_empty", return_value=fake_diagnosis):
            result = _run(agent.diagnose_empty_node(state))

        assert result["diagnose_should_regenerate"] is False


class TestRespondNodeConsumesDiagnosis:
    def test_diagnosis_response_uses_human_reason_directly(self):
        state = {
            "diagnosis": {
                "reason_code": "player_season_mismatch",
                "human_reason": "Nick Daicos has no 2015 stats — their data covers 2022–2026.",
                "fixable": False,
                "suggestion": None,
            }
        }
        response = AFLAnalyticsAgent._build_diagnosis_response(state)
        assert "Nick Daicos has no 2015 stats" in response
        assert "2022" in response and "2026" in response

    def test_falls_back_to_llm_guess_when_no_human_reason(self):
        state = {"diagnosis": {}, "user_query": "x", "entities": {}}
        with patch(
            "app.agent.graph.AFLAnalyticsAgent._build_empty_results_response",
            return_value="fallback text",
        ) as mock_fallback:
            response = AFLAnalyticsAgent._build_diagnosis_response(state)
        mock_fallback.assert_called_once()
        assert response == "fallback text"
