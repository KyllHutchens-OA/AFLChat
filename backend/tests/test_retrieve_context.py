"""
Unit tests for the retrieve_context node (Milestone 3b, app/agent/retrieve_context.py).

No LLM calls and no DB access — retrieve_context is pure/deterministic by design.

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_retrieve_context.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.retrieve_context import retrieve_context, _heuristic_intent_guess


class TestHeuristicIntentGuess:
    def test_comparison_keyword(self):
        assert _heuristic_intent_guess("Compare Cripps and Oliver in 2024", {}) == "player_comparison"

    def test_trend_keyword(self):
        assert _heuristic_intent_guess("Show Geelong's scoring trend since 2018", {}) == "trend_analysis"

    def test_tipping_keyword(self):
        assert _heuristic_intent_guess("Who should I tip this week?", {}) == "tipping_advice"

    def test_injury_keyword(self):
        assert _heuristic_intent_guess("Any injuries for Collingwood?", {}) == "injury_news"

    def test_news_keyword(self):
        assert _heuristic_intent_guess("What's the latest AFL news?", {}) == "afl_news"

    def test_default_falls_back_to_simple_stat(self):
        assert _heuristic_intent_guess("How many goals did Hawkins kick in 2024?", {}) == "simple_stat"

    def test_two_named_entities_without_keywords_guesses_comparison(self):
        entities = {"players": ["Cripps"], "teams": ["Carlton"]}
        assert _heuristic_intent_guess("Cripps and Carlton in 2024", entities) == "player_comparison"


class TestRetrieveContext:
    def test_returns_expected_keys(self):
        updates = retrieve_context(
            user_query="How many goals did Hawkins kick in 2024?",
            entities={"players": ["Hawkins"], "seasons": ["2024"]},
            conversation_history=[],
        )
        assert set(updates.keys()) == {"retrieved_schema_docs", "retrieved_examples", "conversation_snippet"}
        assert updates["retrieved_schema_docs"]
        assert isinstance(updates["retrieved_examples"], list)
        assert len(updates["retrieved_examples"]) > 0

    def test_conversation_snippet_built_from_history(self):
        history = [
            {"role": "user", "content": "How many wins did Collingwood have in 2024?"},
            {"role": "assistant", "content": "Collingwood had 15 wins."},
        ]
        updates = retrieve_context(user_query="What about 2023?", entities={}, conversation_history=history)
        assert "Collingwood" in updates["conversation_snippet"]

    def test_no_history_produces_empty_snippet(self):
        updates = retrieve_context(user_query="x", entities={}, conversation_history=None)
        assert updates["conversation_snippet"] == ""

    def test_top_k_respected(self):
        updates = retrieve_context(
            user_query="How many goals did Hawkins kick in 2024?",
            entities={},
            conversation_history=[],
            top_k=2,
        )
        assert len(updates["retrieved_examples"]) == 2

    def test_does_not_crash_with_empty_entities_and_no_query(self):
        updates = retrieve_context(user_query="", entities={}, conversation_history=[])
        assert updates["retrieved_schema_docs"]
