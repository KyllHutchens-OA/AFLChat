"""Unit tests for the eval scorer's deterministic checks (no LLM, no DB)."""
from app.agent.eval.models import EvalCase, TurnResult
from app.agent.eval.scorer import _contains, score_case


VALID_CHART_SPEC = {
    "version": "1",
    "chartType": "line",
    "title": "Melbourne Wins",
    "data": [{"x": "2018", "wins": 16}, {"x": "2019", "wins": 5}],
    "series": [{"key": "wins", "name": "Wins"}],
    "xAxis": {"label": "Season"},
    "yAxis": {"label": "Wins"},
}

# Missing required `series` entry and carrying a forbidden top-level key.
INVALID_CHART_SPEC = {
    "version": "1",
    "chartType": "line",
    "data": [{"x": "2018", "wins": 16}],
    "series": [],
    "bogus_top_level_key": True,
}


def turn(text="", chart=None, sql=None, **kw):
    return TurnResult(query="q", response_text=text, chart_spec=chart, sql=sql, **kw)


class TestContains:
    def test_word_boundary_number_matching(self):
        assert _contains("Collingwood: 9 wins, 16 games.", "9")
        assert not _contains("data covers 1990 to 2026", "9")  # not inside 1990
        assert _contains("won 120-60 by 60 points", "60")

    def test_case_insensitive(self):
        assert _contains("BRISBANE Lions won", "brisbane")

    def test_multiword(self):
        assert _contains("Marcus Bontempelli had 29 votes", "marcus bontempelli")


class TestFactsCheck:
    def test_all_facts_present_passes(self):
        case = EvalCase(id="c", queries=["q"], expected_facts=["geelong", "133", "52"])
        checks, passed, _ = score_case(case, [turn("Geelong defeated Sydney 133-52.")])
        assert checks["facts"] is True
        assert passed

    def test_missing_fact_fails(self):
        case = EvalCase(id="c", queries=["q"], expected_facts=["geelong", "133"])
        checks, passed, _ = score_case(case, [turn("Geelong won comfortably.")])
        assert checks["facts"] is False
        assert not passed

    def test_expected_any_needs_only_one(self):
        case = EvalCase(id="c", queries=["q"], expected_any=["bontempelli", "neale"])
        checks, _, _ = score_case(case, [turn("Lachie Neale polled 31 votes.")])
        assert checks["facts"] is True

    def test_expected_any_none_present_fails(self):
        case = EvalCase(id="c", queries=["q"], expected_any=["bontempelli", "neale"])
        checks, _, _ = score_case(case, [turn("Nick Daicos polled well.")])
        assert checks["facts"] is False

    def test_forbidden_string_fails(self):
        case = EvalCase(
            id="c", queries=["q"], expected_facts=["collingwood"], forbidden=["i could also"]
        )
        checks, _, _ = score_case(
            case, [turn("Collingwood won. I could also run additional analysis.")]
        )
        assert checks["facts"] is False

    def test_facts_found_in_chart_spec(self):
        # 366 only appears in the chart data, not the prose.
        spec = dict(VALID_CHART_SPEC, data=[{"name": "Goals", "value": 366}])
        case = EvalCase(id="c", queries=["q"], expected_facts=["366"])
        checks, _, _ = score_case(case, [turn("Here's the breakdown.", chart=spec)])
        assert checks["facts"] is True

    def test_not_applicable_when_no_expectations(self):
        case = EvalCase(id="c", queries=["q"])
        checks, passed, _ = score_case(case, [turn("Some answer.")])
        assert checks["facts"] is None
        assert passed  # non-empty response, no applicable checks

    def test_bare_case_with_empty_response_fails(self):
        case = EvalCase(id="c", queries=["q"])
        _, passed, _ = score_case(case, [turn("")])
        assert not passed


class TestChartCheck:
    def test_valid_chart_passes(self):
        case = EvalCase(id="c", queries=["q"], expects_chart=True)
        checks, passed, _ = score_case(case, [turn("Here", chart=VALID_CHART_SPEC)])
        assert checks["chart"] is True
        assert passed

    def test_missing_chart_fails(self):
        case = EvalCase(id="c", queries=["q"], expects_chart=True)
        checks, passed, _ = score_case(case, [turn("Here")])
        assert checks["chart"] is False
        assert not passed

    def test_invalid_spec_fails(self):
        case = EvalCase(id="c", queries=["q"], expects_chart=True)
        checks, _, _ = score_case(case, [turn("Here", chart=INVALID_CHART_SPEC)])
        assert checks["chart"] is False

    def test_expects_no_chart(self):
        case = EvalCase(id="c", queries=["q"], expects_no_chart=True, expected_facts=["23"])
        checks, _, _ = score_case(case, [turn("Melbourne played 23 games.")])
        assert checks["chart"] is True
        checks, _, _ = score_case(
            case, [turn("Melbourne played 23 games.", chart=VALID_CHART_SPEC)]
        )
        assert checks["chart"] is False

    def test_not_applicable_by_default(self):
        case = EvalCase(id="c", queries=["q"], expected_facts=["x"])
        checks, _, _ = score_case(case, [turn("x")])
        assert checks["chart"] is None


class TestNoDataCheck:
    def test_explanatory_response_passes(self):
        case = EvalCase(id="c", queries=["q"], expects_no_data=True)
        checks, passed, _ = score_case(
            case,
            [turn("Nick Daicos has no 2015 stats — the data covers 2022 onwards.")],
        )
        assert checks["no_data"] is True
        assert passed

    def test_generic_fallback_fails(self):
        case = EvalCase(id="c", queries=["q"], expects_no_data=True)
        checks, passed, _ = score_case(
            case,
            [turn("I had trouble finding an answer to that. Try rephrasing your question.")],
        )
        assert checks["no_data"] is False
        assert not passed

    def test_keyword_without_year_passes(self):
        case = EvalCase(id="c", queries=["q"], expects_no_data=True)
        checks, _, _ = score_case(
            case, [turn("That player has no recorded stats in our database.")]
        )
        assert checks["no_data"] is True

    def test_vague_nonanswer_fails(self):
        case = EvalCase(id="c", queries=["q"], expects_no_data=True)
        checks, _, _ = score_case(case, [turn("Hmm, nothing came up for that.")])
        assert checks["no_data"] is False


class TestCorrectionCheck:
    def _pair_case(self, **kw):
        return EvalCase(id="c", queries=["q1", "q2"], is_correction=True, **kw)

    def test_changed_answer_passes(self):
        case = self._pair_case(expected_facts=["geelong"])
        turns = [
            turn("Collingwood defeated Brisbane Lions 90-86."),
            turn("Geelong defeated Sydney 133-52."),
        ]
        checks, passed, _ = score_case(case, turns)
        assert checks["correction"] is True
        assert passed

    def test_unchanged_answer_fails(self):
        case = self._pair_case()
        same = "Collingwood defeated Brisbane Lions 90-86."
        checks, passed, _ = score_case(case, [turn(same), turn(same)])
        assert checks["correction"] is False
        assert not passed

    def test_whitespace_only_difference_is_unchanged(self):
        case = self._pair_case()
        checks, _, _ = score_case(
            case, [turn("Geelong  won."), turn("geelong won.")]
        )
        assert checks["correction"] is False

    def test_single_turn_fails(self):
        case = self._pair_case()
        checks, _, _ = score_case(case, [turn("Only one turn happened.")])
        assert checks["correction"] is False

    def test_not_applicable_for_singles(self):
        case = EvalCase(id="c", queries=["q"], expected_facts=["x"])
        checks, _, _ = score_case(case, [turn("x")])
        assert checks["correction"] is None


class TestSqlCheck:
    def test_all_fragments_present_passes(self):
        case = EvalCase(id="c", queries=["q"], expected_sql_substrings=["group by", "geelong"])
        checks, _, _ = score_case(
            case,
            [turn("ans", sql="SELECT season, count(*) FROM matches WHERE name ILIKE '%Geelong%' GROUP BY season")],
        )
        assert checks["sql"] is True

    def test_missing_fragment_fails(self):
        case = EvalCase(id="c", queries=["q"], expected_sql_substrings=["limit 5"])
        checks, _, _ = score_case(case, [turn("ans", sql="SELECT 1")])
        assert checks["sql"] is False

    def test_no_sql_captured_is_not_applicable(self):
        # --ws mode doesn't carry SQL over the wire.
        case = EvalCase(id="c", queries=["q"], expected_sql_substrings=["limit 5"])
        checks, _, _ = score_case(case, [turn("ans", sql=None)])
        assert checks["sql"] is None


class TestDeterminism:
    def test_scoring_is_pure_and_repeatable(self):
        case = EvalCase(
            id="c",
            queries=["q1", "q2"],
            is_correction=True,
            expected_facts=["geelong", "133"],
            expects_chart=True,
        )
        turns = [
            turn("Collingwood 90-86."),
            turn("Geelong won 133-52.", chart=VALID_CHART_SPEC),
        ]
        first = score_case(case, turns)
        for _ in range(5):
            assert score_case(case, turns) == first
