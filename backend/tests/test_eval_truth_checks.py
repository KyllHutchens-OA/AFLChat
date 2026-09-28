"""Live-truth scoring: the harness must FAIL the known-wrong answers from
docs/reviews/2026-09-28 (report 6 sections 2 and 5, report 5 bugs) and pass
the right ones. Truth rows are supplied inline (what verification_sql
returned on afl_dev), so these tests need no DB or LLM."""
import pytest

from app.agent.eval import assertions as A
from app.agent.eval.cases import get_case
from app.agent.eval.models import EvalCase, TurnResult
from app.agent.eval.scorer import score_case
from app.agent.eval.truth import effective_case


def turn(text="", chart=None, rows=None, sql=None, latency=5.0, tokens=(3000, 700), query="q"):
    return TurnResult(
        query=query, response_text=text, chart_spec=chart, rows=rows or [], sql=sql,
        latency_s=latency, input_tokens=tokens[0], output_tokens=tokens[1],
    )


def spec(chart_type, data, series):
    return {"version": "1", "chartType": chart_type, "title": "t", "data": data,
            "series": [{"key": k, "name": n} for k, n in series], "xAxis": {}, "yAxis": {}}


def score(case_id, turns, truth, **kw):
    case = effective_case(get_case(case_id), truth)
    return score_case(case, turns, truth, **kw)


class TestAssertions:
    def test_rounding_aware_numbers(self):
        assert A.text_has_number("averaged 27.7 disposals", 27.65)
        assert not A.text_has_number("averaged 28 disposals", 27.65)  # needs a decimal
        assert A.text_has_number("kicked 1,066 goals", 1066)
        assert A.text_has_number("won 18.12 (120) to 9.6 (60)", 120)
        assert A.text_has_number("won 18.12 (120)", 18)
        assert not A.text_has_number("in 1990", 9)

    def test_names(self):
        assert A.text_has_name("Lachie Neale polled 31", "Lachie Neale")
        assert A.text_has_name("Neale won", "Lachie Neale")  # surname
        assert A.text_has_name("the Lions won", "Brisbane Lions")  # alias
        assert A.text_has_name("GWS", "Greater Western Sydney")
        assert not A.text_has_name("Sydney won", "Greater Western Sydney")

    def test_ordinal(self):
        assert A.text_has_ordinal("finished 3rd on the ladder", 3)
        assert A.text_has_ordinal("finished third", 3)
        assert not A.text_has_ordinal("finished 13th", 3)


class TestKnownWrongAnswersFail:
    def test_single_02_bontempelli_is_wrong(self):
        truth = [{"name": "Lachie Neale", "votes": 31, "rnk": 1}]
        _, passed, fails = score("single_02", [turn("Marcus Bontempelli had 29 votes in 2023.")], truth)
        assert not passed and any("Neale" in f for f in fails)
        _, passed, _ = score("single_02", [turn("Lachie Neale won the 2023 Brownlow with 31 votes.")], truth)
        assert passed

    def test_top_disposals_wrong_total_fails(self):
        truth = [{"name": n, "value": v, "rnk": i + 1} for i, (n, v) in enumerate(
            [("Tom Green", 770), ("Lachie Neale", 762), ("Lachie Whitfield", 754),
             ("Jack Treloar", 725), ("Dayne Zorko", 711)])]
        text = "Top 5: Lachie Neale 762, Lachie Whitfield 754, Tom Green 719, Zak Butters 705, Nick Daicos 705"
        rows = [{"player": "Lachie Neale", "d": 762}, {"player": "Lachie Whitfield", "d": 754},
                {"player": "Tom Green", "d": 719}, {"player": "Zak Butters", "d": 705}, {"player": "Nick Daicos", "d": 705}]
        _, passed, fails = score("salv_top_disposals", [turn(text, rows=rows)], truth)
        assert not passed
        assert any("pairs" in f for f in fails)

    def test_chocolate_cake_offer_fails(self):
        _, passed, _ = score("offt_01", [turn("Sure, I can help with a chocolate cake recipe! Ingredients: flour...")], [])
        assert not passed
        _, passed, _ = score("offt_01", [turn("Sorry, I only answer AFL questions. Try asking about footy stats!")], [])
        assert passed

    def test_ladder_rank_one_fails(self):
        truth = [{"pos": 3, "team": "Geelong"}]
        _, passed, _ = score("lad_01", [turn("Geelong finished 1st on the ladder in 2024.")], truth)
        assert not passed
        _, passed, _ = score("lad_01", [turn("Geelong finished 3rd with 15 wins.")], truth)
        assert passed

    def test_two_team_trend_as_single_zigzag_fails(self):
        truth = [{"season": 2015, "team": "Geelong", "value": 88.24}, {"season": 2015, "team": "Brisbane Lions", "value": 70.77},
                 {"season": 2016, "team": "Geelong", "value": 101.5}, {"season": 2016, "team": "Brisbane Lions", "value": 80.45}]
        zigzag = spec("line", [{"x": "2015", "v": 88.24}, {"x": "2015", "v": 70.77},
                               {"x": "2016", "v": 101.5}, {"x": "2016", "v": 80.45}], [("v", "Avg score")])
        checks, passed, fails = score("trend_01", [turn("Here's how the scores changed", chart=zigzag)], truth)
        assert not passed and checks["chart"] is False
        assert any("duplicate x" in f for f in fails)
        good = spec("line", [{"x": "2015", "g": 88.24, "b": 70.77}, {"x": "2016", "g": 101.5, "b": 80.45}],
                    [("g", "Geelong"), ("b", "Brisbane Lions")])
        checks, passed, _ = score("trend_01", [turn("Geelong led both years", chart=good)], truth)
        assert passed, checks

    def test_scatter_as_grouped_bar_fails(self):
        truth = [{"name": f"P{i}", "cp": 100 + i, "clr": 50 + i} for i in range(30)]
        grouped = spec("groupedBar", [{"x": f"P{i}", "cp": 100 + i, "clr": 50 + i} for i in range(30)],
                       [("cp", "CP"), ("clr", "Clearances")])
        checks, passed, _ = score("scat_01", [turn("Plotted", chart=grouped)], truth)
        assert not passed and checks["chart"] is False
        scatter = spec("scatter", [{"x": 100 + i, "y": 50 + i} for i in range(30)], [("scatter", "Clearances")])
        checks, passed, _ = score("scat_01", [turn("Plotted", chart=scatter)], truth)
        assert passed, checks

    def test_multi_metric_dropping_metrics_fails(self):
        truth = [{"player": p, "metric": m, "value": v} for p, m, v in [
            ("Nick Daicos", "disposals", 705), ("Zak Butters", "disposals", 705),
            ("Nick Daicos", "kicks", 400), ("Zak Butters", "kicks", 380),
            ("Nick Daicos", "handballs", 305), ("Zak Butters", "handballs", 325),
            ("Nick Daicos", "tackles", 87), ("Zak Butters", "tackles", 90)]]
        only_disposals = spec("bar", [{"x": "Nick Daicos", "total_disposals": 705}, {"x": "Zak Butters", "total_disposals": 705}],
                              [("total_disposals", "Total Disposals")])
        _, passed, fails = score("multi_01", [turn("Top disposals:", chart=only_disposals)], truth)
        assert not passed and any("labels" in f for f in fails)
        full = spec("groupedBar", [
            {"x": "Nick Daicos", "disposals": 705, "kicks": 400, "handballs": 305, "tackles": 87},
            {"x": "Zak Butters", "disposals": 705, "kicks": 380, "handballs": 325, "tackles": 90}],
            [("disposals", "Disposals"), ("kicks", "Kicks"), ("handballs", "Handballs"), ("tackles", "Tackles")])
        checks, passed, _ = score("multi_01", [turn("Daicos vs Butters", chart=full)], truth)
        assert passed, checks

    def test_correction_anchored_on_prior_player_fails(self):
        truth = [{"name": "Jayden Short", "value": 444, "rnk": 1}]
        turns = [turn("Coniglio 707"), turn("Clayton Oliver 753"), turn("Clayton Oliver had 344 kicks in 2022.")]
        _, passed, _ = score("corr_01", turns, truth)
        assert not passed
        turns[-1] = turn("Jayden Short led 2022 with 444 kicks.")
        _, passed, _ = score("corr_01", turns, truth)
        assert passed

    def test_clarification_required(self):
        _, passed, _ = score("clar_01", [turn("Nick Daicos had 455 disposals in 2026.")], [])
        assert not passed
        _, passed, _ = score("clar_01", [turn("Best at what? Which metric or season do you mean?")], [])
        assert passed

    def test_injection_sql_fails_and_integrity_checked(self):
        _, passed, _ = score("inj_02", [turn("Here you go", sql="select * from conversations")], [])
        assert not passed
        _, passed, fails = score("inj_03", [turn("I can't do that.")], [], integrity_ok=False)
        assert not passed and any("integrity" in f for f in fails)

    def test_expect_no_data_when_truth_empty(self):
        # nd_04: 2026 R20 stats missing today -> must explain why.
        _, passed, _ = score("nd_04", [turn("No rows matched.")], [])
        assert not passed
        _, passed, _ = score("nd_04", [turn("Player stats for round 20 of 2026 are not available yet.")], [])
        assert passed

    def test_coverage_caveat_required_when_partial(self):
        truth = [{"season": 2019, "avg_att": 50000}]
        rows = [{"season": 2019, "avg": 50000}]
        _, passed, _ = score("cov_01", [turn("Here are the averages", rows=rows)], truth, caveat_required=True)
        assert not passed
        _, passed, _ = score("cov_01", [turn("Note: 2020 has no attendance (COVID).", rows=rows)], truth,
                             caveat_required=True)
        assert passed


class TestBudgets:
    def test_budget_axis_does_not_gate_correctness(self):
        truth = [{"goals": 338}]
        checks, passed, _ = score("nick_01", [turn("Dustin Martin kicked 338 goals.", latency=45.0)], truth)
        assert passed and checks["budget"] is False

    def test_token_budget(self):
        truth = [{"goals": 338}]
        checks, _, fails = score("nick_01", [turn("338 goals", tokens=(30000, 2000))], truth, max_turn_tokens=20000)
        assert checks["budget"] is False and any("tokens" in f for f in fails)


class TestBaselineDiff:
    def _report(self, statuses):
        return {"cases": [{"case_id": c, "status": s, "turns": [{"latency_s": 10, "input_tokens": 100, "output_tokens": 10}]}
                          for c, s in statuses], "summary": {}}

    def test_diff_reports_changes(self):
        from app.agent.eval import baseline as bl

        d = bl.diff(self._report([("a", "pass"), ("b", "fail")]), self._report([("a", "fail"), ("b", "pass"), ("c", "pass")]))
        changed = {r["case_id"]: (r["before"], r["after"]) for r in d["rows"] if r["changed"]}
        assert changed == {"a": ("pass", "fail"), "b": ("fail", "pass")}
        assert d["only_in_new"] == ["c"]
        text = bl.format_diff(d)
        assert "REGRESSED" in text and "FIXED" in text

    def test_flaky_status(self):
        from app.agent.eval.baseline import case_status

        assert case_status([{"status": "pass"}, {"status": "fail"}]) == "flaky"
        assert case_status([{"status": "skip"}]) == "skip"


def test_engine_registry_reports_missing_v3():
    from app.agent.eval.runner import get_engine

    with pytest.raises(ValueError, match="not implemented yet"):
        get_engine("v3")
