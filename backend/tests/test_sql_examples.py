"""
Unit tests for SQL example retrieval scoring (app/agent/sql_examples.py, Milestone 3b).

Does NOT hit the database — see tests/test_sql_examples_integration.py for the
DB-executing validation of every example (marked `integration`).

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_sql_examples.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.sql_examples import SQL_EXAMPLES, get_examples, get_example_count


class TestExampleLibraryShape:
    def test_every_example_has_required_fields(self):
        for ex in SQL_EXAMPLES:
            assert set(ex.keys()) >= {"id", "question", "sql", "tags"}
            assert ex["question"].strip()
            assert ex["sql"].strip()
            assert len(ex["tags"]) > 0

    def test_ids_are_unique(self):
        ids = [ex["id"] for ex in SQL_EXAMPLES]
        assert len(ids) == len(set(ids))

    def test_every_example_is_a_select_or_cte(self):
        for ex in SQL_EXAMPLES:
            sql_upper = ex["sql"].upper().strip()
            assert sql_upper.startswith("SELECT") or sql_upper.startswith("WITH"), ex["id"]

    def test_at_least_15_examples_harvested(self):
        # Plan calls for ~16 fast_path templates plus a handful of consolidated_llm
        # few-shot examples merged/deduped in.
        assert get_example_count() >= 15


class TestRetrievalScoring:
    def test_head_to_head_since_ranks_top_for_matching_question(self):
        results = get_examples(
            "What's Carlton's win-loss record against Essendon since 1990?",
            intent="team_analysis",
            entities={"teams": ["Carlton", "Essendon"], "seasons": ["1990"]},
            top_k=3,
        )
        ids = [r["id"] for r in results]
        assert "head_to_head_since" in ids
        assert ids[0] == "head_to_head_since"

    def test_top_n_goal_question_surfaces_top_goal_kickers_example(self):
        results = get_examples(
            "Who were the top goal kickers in 2024?",
            intent="simple_stat",
            entities={"seasons": ["2024"]},
            top_k=5,
        )
        ids = [r["id"] for r in results]
        assert "top_goal_kickers" in ids

    def test_player_comparison_intent_surfaces_comparison_example(self):
        results = get_examples(
            "Compare Bontempelli and Cripps",
            intent="player_comparison",
            entities={"players": ["Bontempelli", "Cripps"]},
            top_k=5,
        )
        ids = [r["id"] for r in results]
        assert "player_comparison" in ids

    def test_top_k_is_respected(self):
        results = get_examples("goals", intent=None, entities={}, top_k=2)
        assert len(results) == 2

    def test_determinism_same_inputs_same_order(self):
        first = get_examples("Carlton vs Essendon since 1990", "team_analysis", {"teams": ["Carlton", "Essendon"]})
        second = get_examples("Carlton vs Essendon since 1990", "team_analysis", {"teams": ["Carlton", "Essendon"]})
        assert [e["id"] for e in first] == [e["id"] for e in second]

    def test_empty_question_and_entities_does_not_crash(self):
        results = get_examples("", None, {}, top_k=3)
        assert len(results) == 3
