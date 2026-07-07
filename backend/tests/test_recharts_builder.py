"""
Milestone 4 — RechartsBuilder output validated against the ChartSpecV1 wire
contract (app/visualization/spec.py).

Covers every builder path RechartsBuilder.generate_chart can dispatch to,
plus the internal→contract chartType mapping (horizontal_bar→bar+orientation,
stacked_bar/grouped_bar/comparison/box→groupedBar), the pie >5-slice "Other"
grouping, and the None-on-failure guard for empty/malformed inputs.
"""
import pandas as pd
import pytest
from pydantic import ValidationError

from app.visualization.recharts_builder import RechartsBuilder
from app.visualization.spec import ChartSpecV1


def _validate(spec):
    """Re-validate an already-validated builder output, for test-side belt & braces."""
    assert spec is not None
    return ChartSpecV1.model_validate(spec)


class TestLineChart:
    def test_single_series(self):
        data = pd.DataFrame({
            "round": ["1", "2", "3", "4"],
            "disposals": [20, 25, 22, 30],
        })
        spec = RechartsBuilder.generate_chart(data, "line", {"x_col": "round", "y_col": "disposals"})
        parsed = _validate(spec)
        assert parsed.chartType == "line"
        assert parsed.version == "1"
        assert len(parsed.series) == 1
        assert len(parsed.data) == 4

    def test_grouped_multi_series(self):
        data = pd.DataFrame({
            "round": ["1", "1", "2", "2"],
            "team": ["Collingwood", "Carlton", "Collingwood", "Carlton"],
            "disposals": [20, 18, 25, 22],
        })
        spec = RechartsBuilder.generate_chart(
            data, "line", {"x_col": "round", "y_col": "disposals", "group_col": "team"}
        )
        parsed = _validate(spec)
        assert parsed.chartType == "line"
        assert len(parsed.series) == 2

    def test_trend_alias_maps_to_line(self):
        data = pd.DataFrame({"round": ["1", "2", "3"], "goals": [1, 2, 3]})
        spec = RechartsBuilder.generate_chart(data, "trend", {"x_col": "round", "y_col": "goals"})
        parsed = _validate(spec)
        assert parsed.chartType == "line"


class TestBarChart:
    def test_basic_bar(self):
        data = pd.DataFrame({"team": ["Collingwood", "Carlton", "Essendon"], "wins": [15, 10, 8]})
        spec = RechartsBuilder.generate_chart(data, "bar", {"x_col": "team", "y_col": "wins"})
        parsed = _validate(spec)
        assert parsed.chartType == "bar"
        assert parsed.orientation is None
        assert len(parsed.series) == 1

    def test_horizontal_bar_maps_to_bar_with_orientation(self):
        data = pd.DataFrame({"team": [f"Team{i}" for i in range(15)], "wins": list(range(15))})
        spec = RechartsBuilder.generate_chart(data, "horizontal_bar", {"x_col": "team", "y_col": "wins"})
        parsed = _validate(spec)
        assert parsed.chartType == "bar"
        assert parsed.orientation == "horizontal"
        assert len(parsed.series) == 1


class TestGroupedAndStackedBar:
    def test_grouped_bar_maps_to_groupedBar(self):
        data = pd.DataFrame({
            "season": ["2023", "2023", "2024", "2024"],
            "team": ["Collingwood", "Carlton", "Collingwood", "Carlton"],
            "wins": [15, 10, 18, 12],
        })
        spec = RechartsBuilder.generate_chart(
            data, "grouped_bar", {"x_col": "season", "y_col": "wins", "group_col": "team"}
        )
        parsed = _validate(spec)
        assert parsed.chartType == "groupedBar"
        assert len(parsed.series) == 2
        assert all(s.stackId is None for s in parsed.series)

    def test_stacked_bar_maps_to_groupedBar_with_stackId(self):
        data = pd.DataFrame({
            "season": ["2023", "2023", "2024", "2024"],
            "team": ["Collingwood", "Carlton", "Collingwood", "Carlton"],
            "wins": [15, 10, 18, 12],
        })
        spec = RechartsBuilder.generate_chart(
            data, "stacked_bar", {"x_col": "season", "y_col": "wins", "group_col": "team"}
        )
        parsed = _validate(spec)
        assert parsed.chartType == "groupedBar"
        assert len(parsed.series) == 2
        assert all(s.stackId == "a" for s in parsed.series)

    def test_comparison_maps_to_groupedBar(self):
        data = pd.DataFrame({
            "player": ["Cripps", "Bontempelli"],
            "disposals": [32, 28],
            "goals": [1, 2],
            "tackles": [6, 5],
        })
        spec = RechartsBuilder.generate_chart(
            data, "comparison",
            {"group_col": "player", "metric_cols": ["disposals", "goals", "tackles"]},
        )
        parsed = _validate(spec)
        assert parsed.chartType == "groupedBar"
        assert len(parsed.series) == 3


class TestPieChart:
    def test_small_slice_count_no_other(self):
        data = pd.DataFrame({"source": ["Goals", "Behinds"], "value": [80, 20]})
        spec = RechartsBuilder.generate_chart(data, "pie", {"x_col": "source", "y_col": "value"})
        parsed = _validate(spec)
        assert parsed.chartType == "pie"
        assert len(parsed.data) == 2
        assert len(parsed.series) == 1  # contract requires >=1; pie now emits one
        assert parsed.showSliceLabels in (True, None)
        assert not any(row.get("name") == "Other" for row in parsed.data)

    def test_over_five_slices_grouped_into_other(self):
        data = pd.DataFrame({
            "team": [f"Team{i}" for i in range(8)],
            "value": [40, 20, 15, 10, 8, 4, 2, 1],
        })
        spec = RechartsBuilder.generate_chart(data, "pie", {"x_col": "team", "y_col": "value"})
        parsed = _validate(spec)
        assert parsed.chartType == "pie"
        # top 5 + one "Other" slice
        assert len(parsed.data) == 6
        assert parsed.data[-1]["name"] == "Other"
        assert parsed.data[-1]["value"] == pytest.approx(4 + 2 + 1)
        assert parsed.showSliceLabels is False


class TestBoxAsGroupedBar:
    def test_box_reroutes_to_groupedBar_median_range(self):
        data = pd.DataFrame({
            "team": ["Collingwood"] * 5 + ["Carlton"] * 5,
            "disposals": [18, 20, 22, 24, 26, 15, 17, 19, 21, 23],
        })
        spec = RechartsBuilder.generate_chart(data, "box", {"y_col": "disposals", "group_col": "team"})
        parsed = _validate(spec)
        assert parsed.chartType == "groupedBar"
        keys = {s.key for s in parsed.series}
        assert keys == {"median", "range"}
        for row in parsed.data:
            assert "median" in row and "range" in row
            # extra (non-plotted) quartile fields still present for future use
            assert "q1" in row and "q3" in row and "min" in row and "max" in row

    def test_box_single_group_still_valid(self):
        data = pd.DataFrame({"disposals": [18, 20, 22, 24, 26]})
        spec = RechartsBuilder.generate_chart(data, "box", {"y_col": "disposals"})
        parsed = _validate(spec)
        assert parsed.chartType == "groupedBar"
        assert len(parsed.data) == 1


class TestScatterChart:
    def test_basic_scatter(self):
        data = pd.DataFrame({"disposals": [20, 25, 30, 15, 22], "goals": [1, 2, 3, 0, 1]})
        spec = RechartsBuilder.generate_chart(data, "scatter", {"x_col": "disposals", "y_col": "goals"})
        parsed = _validate(spec)
        assert parsed.chartType == "scatter"
        assert len(parsed.series) == 1

    def test_grouped_scatter(self):
        data = pd.DataFrame({
            "disposals": [20, 25, 30, 15],
            "goals": [1, 2, 3, 0],
            "team": ["A", "A", "B", "B"],
        })
        spec = RechartsBuilder.generate_chart(
            data, "scatter", {"x_col": "disposals", "y_col": "goals", "group_col": "team"}
        )
        parsed = _validate(spec)
        assert len(parsed.series) == 2


class TestNotYetSelectableChartTypes:
    """
    `area` and `table` are part of the ChartSpecV1 wire contract (for the
    frontend's benefit — ChartRenderer implements both) but no current
    RechartsBuilder path or ChartSelector rule ever produces them; they're
    reserved for future chart-selection work. These tests validate the
    contract shape directly rather than through RechartsBuilder.
    """

    def test_area_fixture_is_valid_v1_spec(self):
        fixture = {
            "version": "1",
            "chartType": "area",
            "title": "Cumulative Disposals",
            "data": [{"x": "R1", "disposals": 20}, {"x": "R2", "disposals": 45}],
            "series": [{"key": "disposals", "name": "Disposals", "color": "#C2581C"}],
            "xAxis": {"label": "Round"},
            "yAxis": {"label": "Disposals"},
            "colors": ["#C2581C"],
            "legend": False,
        }
        ChartSpecV1.model_validate(fixture)

    def test_table_fixture_is_valid_v1_spec(self):
        fixture = {
            "version": "1",
            "chartType": "table",
            "title": "Raw Results",
            "data": [{"team": "Collingwood", "wins": 15}],
            "series": [{"key": "wins", "name": "Wins"}],
            "xAxis": {},
            "yAxis": {},
        }
        ChartSpecV1.model_validate(fixture)


class TestFailureModes:
    def test_empty_data_returns_none(self):
        data = pd.DataFrame(columns=["team", "wins"])
        spec = RechartsBuilder.generate_chart(data, "bar", {"x_col": "team", "y_col": "wins"})
        assert spec is None

    def test_malformed_missing_column_returns_none(self):
        data = pd.DataFrame({"team": ["Collingwood", "Carlton"], "wins": [15, 10]})
        # References a column that doesn't exist in `data` — builder raises,
        # generate_chart must catch it and return None rather than propagate.
        spec = RechartsBuilder.generate_chart(data, "bar", {"x_col": "team", "y_col": "nonexistent_col"})
        assert spec is None

    def test_unknown_chart_type_falls_back_to_bar(self):
        data = pd.DataFrame({"team": ["Collingwood", "Carlton"], "wins": [15, 10]})
        spec = RechartsBuilder.generate_chart(data, "totally_unknown_type", {"x_col": "team", "y_col": "wins"})
        parsed = _validate(spec)
        assert parsed.chartType == "bar"


class TestChartSpecV1Contract:
    def test_rejects_empty_data(self):
        with pytest.raises(ValidationError):
            ChartSpecV1.model_validate({
                "version": "1", "chartType": "bar", "data": [],
                "series": [{"key": "x"}],
            })

    def test_rejects_empty_series(self):
        with pytest.raises(ValidationError):
            ChartSpecV1.model_validate({
                "version": "1", "chartType": "bar", "data": [{"x": 1}],
                "series": [],
            })

    def test_rejects_unknown_chart_type(self):
        with pytest.raises(ValidationError):
            ChartSpecV1.model_validate({
                "version": "1", "chartType": "horizontal_bar", "data": [{"x": 1}],
                "series": [{"key": "x"}],
            })

    def test_rejects_unexpected_top_level_field(self):
        with pytest.raises(ValidationError):
            ChartSpecV1.model_validate({
                "version": "1", "chartType": "bar", "data": [{"x": 1}],
                "series": [{"key": "x"}], "error": "boom",
            })
