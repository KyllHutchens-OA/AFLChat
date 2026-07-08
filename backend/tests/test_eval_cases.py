"""Unit tests for the eval harness case definitions and eval_queries.txt parsing."""
import pytest

from app.agent.eval.cases import (
    EVAL_QUERIES_PATH,
    SALVAGED,
    SMOKE15,
    build_subsets,
    get_case,
    get_subset,
    parse_eval_queries,
)
from app.agent.eval.models import EvalCase


class TestParseEvalQueries:
    def test_parses_all_128_queries(self):
        cases = parse_eval_queries(EVAL_QUERIES_PATH)
        assert len(cases) == 128

    def test_ids_are_unique_and_sequential(self):
        cases = parse_eval_queries()
        ids = [c.id for c in cases]
        assert len(set(ids)) == len(ids)
        assert ids[0] == "q001"
        assert ids[-1] == "q128"

    def test_chart_queries_are_tagged_and_expect_charts(self):
        cases = {c.id: c for c in parse_eval_queries()}
        # Line 7: "Show me a chart of Melbourne's wins per season since 2018"
        assert cases["q007"].expects_chart
        assert "chart" in cases["q007"].tags
        # Line 21: pie chart query
        assert cases["q021"].expects_chart
        # Line 1: "How many games has Collingwood won this season?" — no chart
        assert not cases["q001"].expects_chart
        assert "chart" not in cases["q001"].tags

    def test_comparison_tagging(self):
        cases = {c.id: c for c in parse_eval_queries()}
        # Line 10: "Compare disposals per game for Marcus Bontempelli and Patrick Cripps..."
        assert "comparison" in cases["q010"].tags

    def test_queries_preserved_verbatim(self):
        cases = parse_eval_queries()
        assert cases[0].queries == ["How many games has Collingwood won this season?"]


class TestSmoke15:
    def test_has_exactly_15_cases(self):
        assert len(SMOKE15) == 15

    def test_mirrors_m0_benchmark_ids(self):
        ids = {c.id for c in SMOKE15}
        for expected in [
            "single_01", "single_02", "single_03", "single_04", "single_05",
            "single_06", "single_07", "pair_01", "pair_02", "pair_03",
            "nodata_01", "nodata_02",
        ]:
            assert expected in ids

    def test_includes_three_correction_pairs(self):
        pairs = [c for c in SMOKE15 if c.is_correction]
        assert len(pairs) == 3
        for c in pairs:
            assert len(c.queries) == 2

    def test_includes_two_no_data_cases(self):
        assert sum(c.expects_no_data for c in SMOKE15) == 2

    def test_includes_chart_cases(self):
        assert sum(c.expects_chart for c in SMOKE15) >= 3

    def test_includes_salvage_derived_cases(self):
        assert sum(c.source == "salvaged" for c in SMOKE15) == 3

    def test_all_cases_have_some_expectation(self):
        for c in SMOKE15:
            assert (
                c.expected_facts
                or c.expected_any
                or c.expects_chart
                or c.expects_no_data
            ), f"{c.id} has no deterministic expectation"


class TestSalvaged:
    def test_salvaged_suite_recovered(self):
        # 19 cases were recovered from test_cases.cpython-314.pyc.
        assert len(SALVAGED) == 19
        ids = {c.id for c in SALVAGED}
        assert "salvaged_grand_final_winner" in ids
        assert "salvaged_followup_pronoun_resolution" in ids

    def test_followup_case_carries_synthetic_history(self):
        case = get_case("salvaged_followup_pronoun_resolution")
        assert case.conversation_history[0]["role"] == "user"
        assert case.conversation_history[1]["role"] == "assistant"
        assert "Hawkins" in case.conversation_history[1]["content"]

    def test_all_tagged_salvaged(self):
        for c in SALVAGED:
            assert "salvaged" in c.tags


class TestSubsets:
    def test_expected_subsets_exist(self):
        subsets = build_subsets()
        for name in ["smoke15", "corrections", "no-data", "charts", "salvaged", "queries", "all"]:
            assert name in subsets

    def test_corrections_subset(self):
        cases = get_subset("corrections")
        assert len(cases) == 3
        assert all(c.is_correction for c in cases)

    def test_no_data_subset(self):
        cases = get_subset("no-data")
        assert all(c.expects_no_data for c in cases)
        assert len(cases) >= 3  # 2 smoke + salvaged nonexistent_player

    def test_charts_subset(self):
        cases = get_subset("charts")
        assert all(c.expects_chart or c.expects_no_chart for c in cases)
        assert len(cases) >= 4

    def test_all_subset_has_unique_ids(self):
        cases = get_subset("all")
        ids = [c.id for c in cases]
        assert len(set(ids)) == len(ids)
        # smoke15 + salvaged + 128 parsed queries
        assert len(cases) == 15 + 19 + 128

    def test_unknown_subset_raises(self):
        with pytest.raises(ValueError, match="Unknown subset"):
            get_subset("nope")

    def test_get_case_by_id(self):
        case = get_case("pair_02")
        assert isinstance(case, EvalCase)
        assert case.is_correction

    def test_unknown_case_raises(self):
        with pytest.raises(ValueError, match="Unknown case id"):
            get_case("does_not_exist")
