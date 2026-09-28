"""
Unit tests for the classify_resolve node (Milestone 3a, app/agent/classify_resolve.py)
and the v2 turn_type routing logic in app/agent/graph.py.

Uses a mocked OpenAI client — no live API calls or DB access. Entity fixtures
intentionally only use "teams" (resolved purely in-memory by EntityResolver)
so these tests don't need a database connection either.

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_classify_resolve.py -v
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

# Ensure `backend/` is importable as the project root when running this file
# directly rather than via `-m pytest`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.classify_resolve import classify_and_resolve


def _fake_response(payload: dict, prompt_tokens: int = 100, completion_tokens: int = 20):
    """Fake llm.LLMResult (text + usage)."""
    usage = SimpleNamespace(input_tokens=prompt_tokens, output_tokens=completion_tokens)
    return SimpleNamespace(text=json.dumps(payload), usage=usage)


class TestClassifyAndResolveHappyPath:
    """Basic turn_type + entity extraction plumbing."""

    def test_new_question_parses_and_resolves_entities(self):
        payload = {
            "turn_type": "new_question",
            "entities": {"teams": ["Cats"], "players": [], "seasons": ["2024"], "metrics": ["goals"]},
            "complaint_summary": None,
            "chitchat_reply": None,
        }
        state = {}
        with patch("app.agent.classify_resolve.llm_complete", return_value=_fake_response(payload)):
            updates = classify_and_resolve(
                user_query="How many goals did Geelong kick in 2024?",
                conversation_history=[],
                state=state,
            )

        assert updates["turn_type"] == "new_question"
        # "Cats" must be resolved to the canonical team name by EntityResolver
        assert updates["entities"]["teams"] == ["Geelong"]
        assert "complaint_summary" not in updates
        assert "natural_language_summary" not in updates
        assert "bypass_cache" not in updates

    def test_token_usage_accumulated_into_state(self):
        payload = {"turn_type": "new_question", "entities": {}, "complaint_summary": None, "chitchat_reply": None}
        state = {"token_usage": {"input_tokens": 5, "output_tokens": 1}}
        with patch(
            "app.agent.classify_resolve.llm_complete",
            return_value=_fake_response(payload, prompt_tokens=42, completion_tokens=8),
        ):
            classify_and_resolve(user_query="hi", conversation_history=[], state=state)

        assert state["token_usage"]["input_tokens"] == 47
        assert state["token_usage"]["output_tokens"] == 9

    def test_unknown_turn_type_defaults_to_new_question(self):
        payload = {"turn_type": "something_bogus", "entities": {}, "complaint_summary": None, "chitchat_reply": None}
        state = {}
        with patch("app.agent.classify_resolve.llm_complete", return_value=_fake_response(payload)):
            updates = classify_and_resolve(user_query="???", conversation_history=[], state=state)

        assert updates["turn_type"] == "new_question"

    def test_llm_exception_falls_back_gracefully(self):
        state = {}
        with patch(
            "app.agent.classify_resolve.llm_complete",
            side_effect=RuntimeError("API down"),
        ):
            updates = classify_and_resolve(user_query="anything", conversation_history=[], state=state)

        assert updates["turn_type"] == "new_question"
        assert updates["entities"] == {}


class TestChitchat:
    def test_chitchat_sets_natural_language_summary(self):
        payload = {
            "turn_type": "chitchat",
            "entities": {},
            "complaint_summary": None,
            "chitchat_reply": "Hey! Ask me anything about AFL stats.",
        }
        state = {}
        with patch("app.agent.classify_resolve.llm_complete", return_value=_fake_response(payload)):
            updates = classify_and_resolve(user_query="hey there", conversation_history=[], state=state)

        assert updates["turn_type"] == "chitchat"
        assert updates["natural_language_summary"] == "Hey! Ask me anything about AFL stats."
        assert updates["confidence"] == 0.9


class TestCorrectionPlumbing:
    """Deliverable #2: bypass_cache + prior_sql/prior_row_count/prior_answer."""

    def test_correction_sets_bypass_cache_and_loads_prior_turn(self):
        payload = {
            "turn_type": "correction",
            "entities": {"teams": ["Magpies"]},
            "complaint_summary": "The user says the season should have been 2023, not 2024.",
            "chitchat_reply": None,
        }
        conversation_history = [
            {"role": "user", "content": "How many wins did Collingwood have in 2024?"},
            {
                "role": "assistant",
                "content": "Collingwood had 15 wins in 2024.",
                "sql": "SELECT COUNT(*) FROM matches WHERE season = 2024",
                "row_count": 1,
            },
        ]
        state = {}
        with patch("app.agent.classify_resolve.llm_complete", return_value=_fake_response(payload)):
            updates = classify_and_resolve(
                user_query="No, I meant 2023",
                conversation_history=conversation_history,
                state=state,
            )

        assert updates["turn_type"] == "correction"
        assert updates["bypass_cache"] is True
        assert updates["complaint_summary"] == "The user says the season should have been 2023, not 2024."
        assert updates["prior_sql"] == "SELECT COUNT(*) FROM matches WHERE season = 2024"
        assert updates["prior_row_count"] == 1
        assert updates["prior_answer"] == "Collingwood had 15 wins in 2024."
        assert updates["entities"]["teams"] == ["Collingwood"]

    def test_correction_without_prior_assistant_message_does_not_crash(self):
        payload = {
            "turn_type": "correction",
            "entities": {},
            "complaint_summary": "Unclear what was wrong.",
            "chitchat_reply": None,
        }
        state = {}
        with patch("app.agent.classify_resolve.llm_complete", return_value=_fake_response(payload)):
            updates = classify_and_resolve(user_query="that's wrong", conversation_history=[], state=state)

        assert updates["turn_type"] == "correction"
        assert updates["bypass_cache"] is True
        assert "prior_sql" not in updates


class TestTurnTypeRouting:
    """Deliverable #5: v2 graph routing after classify_resolve."""

    def test_chitchat_routes_to_respond(self):
        from app.agent.graph import AFLAnalyticsAgent

        assert AFLAnalyticsAgent._route_after_classify({"turn_type": "chitchat"}) == "respond"

    def test_non_chitchat_routes_to_retrieve_context(self):
        # Milestone 3b: classify_resolve -> retrieve_context -> generate_sql replaces
        # the old classify_resolve -> understand entry point for non-chitchat turns.
        from app.agent.graph import AFLAnalyticsAgent

        for turn_type in ["new_question", "follow_up", "correction", "clarification_answer"]:
            assert AFLAnalyticsAgent._route_after_classify({"turn_type": turn_type}) == "retrieve_context"

    def test_missing_turn_type_routes_to_retrieve_context(self):
        from app.agent.graph import AFLAnalyticsAgent

        assert AFLAnalyticsAgent._route_after_classify({}) == "retrieve_context"
