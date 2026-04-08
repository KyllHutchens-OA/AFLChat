"""
AFL Analytics Agent - Recharts Chart Builder

Generates library-agnostic chart specifications rendered by Recharts on the frontend.
Output format: {chartType, title, data, series, xAxis, yAxis, annotations, legend, colors}
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import math
import logging

logger = logging.getLogger(__name__)

# AFL warm color palette
AFL_COLORS = ["#C2581C", "#2D7A6F", "#D4794D", "#246359", "#8C7B6B", "#A30046", "#D4001A", "#002B5C"]


class ChartHelper:
    """Helper functions for chart generation."""

    @staticmethod
    def humanize_column_name(col_name: str) -> str:
        """Convert database column names to human-readable labels."""
        special_cases = {
            "win_loss_ratio": "Win/Loss Ratio",
            "win_rate": "Win Rate",
            "avg_score_per_game": "Average Score",
            "total_score": "Total Score",
            "team_score": "Team Score",
            "opponent_score": "Opponent Score",
            "home_score": "Home Score",
            "away_score": "Away Score",
            "match_date": "Date",
            "season": "Season",
            "round": "Round",
            "wins": "Wins",
            "losses": "Losses",
            "draws": "Draws",
            "matches": "Matches Played",
            "games": "Games",
            "margin": "Margin",
            "opponent": "Opponent",
            "result": "Result"
        }

        if col_name.lower() in special_cases:
            return special_cases[col_name.lower()]

        return col_name.replace("_", " ").title()

    @staticmethod
    def generate_chart_title(
        intent: str,
        entities: Dict[str, Any],
        metrics: List[str],
        data_cols: List[str],
        y_col: str = None,
        x_col: str = None
    ) -> str:
        """Generate a descriptive chart title based on query intent and entities."""
        teams = entities.get("teams", [])
        seasons = entities.get("seasons", [])
        players = entities.get("players", [])

        if players:
            subject = players[0] if len(players) == 1 else " vs ".join(players[:2]) if len(players) > 1 else ""
            subject_type = "player"
        elif teams:
            subject = teams[0] if len(teams) == 1 else " vs ".join(teams[:2]) if len(teams) > 1 else ""
            subject_type = "team"
        else:
            subject = ""
            subject_type = None

        season_str = ""
        if seasons:
            if len(seasons) == 1:
                season_str = str(seasons[0])
            else:
                season_str = f"{seasons[0]}-{seasons[-1]}"

        metric_map = {
            "goals": "Goals", "disposals": "Disposals", "kicks": "Kicks",
            "handballs": "Handballs", "marks": "Marks", "tackles": "Tackles",
            "clearances": "Clearances", "inside_50s": "Inside 50s",
            "contested_possessions": "Contested Possessions",
            "uncontested_possessions": "Uncontested Possessions",
            "brownlow_votes": "Brownlow Votes", "behinds": "Behinds",
            "hitouts": "Hitouts", "win_loss_ratio": "Win/Loss Ratio",
            "win_rate": "Win Rate", "win_percentage": "Win Rate",
            "wins": "Wins", "losses": "Losses",
            "avg_score_per_game": "Scoring", "avg_score": "Average Score",
            "margin": "Margin", "total_score": "Total Score",
            "home_score": "Score", "away_score": "Score", "score": "Score",
            "total_goals": "Goals", "total_disposals": "Disposals",
            "fantasy_points": "Fantasy Points", "avg_fantasy": "Avg Fantasy Points",
            "total_fantasy": "Total Fantasy Points",
        }

        metric = None
        if y_col and y_col.lower() in metric_map:
            metric = metric_map[y_col.lower()]
        if not metric:
            for col in data_cols:
                if col.lower() in metric_map:
                    metric = metric_map[col.lower()]
                    break
        if not metric:
            for m in metrics:
                if m.lower() in metric_map:
                    metric = metric_map[m.lower()]
                    break

        if x_col:
            by_round = x_col.lower() == "round"
        else:
            by_round = "round" in [c.lower() for c in data_cols]

        parts = []
        if subject:
            parts.append(subject)
        if metric:
            parts.append(metric)
        elif subject_type == "player":
            parts.append("Stats")
        elif subject_type == "team":
            parts.append("Performance")

        if by_round and season_str:
            parts.append(f"by Round ({season_str})")
        elif by_round:
            parts.append("by Round")
        elif season_str:
            if len(seasons) > 1:
                parts.append(f"({season_str})")
            else:
                parts.append(season_str)

        if not parts:
            return "AFL Statistics"

        return " ".join(parts)


def _clean_value(v):
    """Convert a value to JSON-safe type."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, 'item'):  # numpy scalar
        return v.item()
    return v


def _clean_row(row: dict) -> dict:
    """Clean all values in a row dict for JSON serialization."""
    return {k: _clean_value(v) for k, v in row.items()}


class RechartsBuilder:
    """
    Builds library-agnostic chart specs rendered by Recharts on the frontend.

    Output format:
    {
        chartType: str,
        title: str,
        data: list[dict],   # flat row dicts [{x: "R1", Goals: 14}, ...]
        series: list[dict],  # [{key, name, color, dashed?}, ...]
        xAxis: {label, tickAngle?},
        yAxis: {label, domain?, integerOnly?},
        annotations: list[dict],  # [{x, y, label, color}, ...]
        legend: bool,
        colors: list[str],
    }
    """

    @staticmethod
    def generate_chart(
        data: pd.DataFrame,
        chart_type: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate a Recharts-compatible chart specification."""
        if params is None:
            params = {}

        try:
            builders = {
                "line": RechartsBuilder._build_line_chart,
                "bar": RechartsBuilder._build_bar_chart,
                "horizontal_bar": RechartsBuilder._build_horizontal_bar_chart,
                "scatter": RechartsBuilder._build_scatter_chart,
                "pie": RechartsBuilder._build_pie_chart,
                "box": RechartsBuilder._build_box_chart,
                "stacked_bar": lambda d, p: RechartsBuilder._build_multi_bar_chart(d, p, stacked=True),
                "grouped_bar": lambda d, p: RechartsBuilder._build_multi_bar_chart(d, p, stacked=False),
                "comparison": RechartsBuilder._build_comparison_chart,
                "trend": RechartsBuilder._build_line_chart,
            }

            builder = builders.get(chart_type)
            if builder is None:
                logger.warning(f"Unknown chart type: {chart_type}, defaulting to bar")
                builder = RechartsBuilder._build_bar_chart

            return builder(data, params)

        except Exception as e:
            logger.error(f"Error generating chart: {e}")
            return {"error": str(e), "chartType": "bar", "data": [], "series": []}

    # ── Line Chart ──────────────────────────────────────────────

    @staticmethod
    def _build_line_chart(data: pd.DataFrame, params: Dict) -> Dict:
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        group_col = params.get("group_col")
        title = params.get("title", "Trend Over Time")
        recommendations = params.get("recommendations", {})
        annotations_in = params.get("annotations", [])
        layout_config = params.get("layout_config", {})

        _FINALS_ABBREV = {
            "Qualifying Final": "QF", "Elimination Final": "EF",
            "Semi Final": "SF", "Preliminary Final": "PF", "Grand Final": "GF",
        }

        series = []
        chart_data = []

        if group_col and group_col in data.columns:
            # Multiple lines — pivot to flat format
            groups = list(data[group_col].unique())
            # Build x values from all groups
            x_values = data[x_col].unique().tolist()
            for x_val in x_values:
                row = {"x": _FINALS_ABBREV.get(str(x_val).strip(), str(x_val))}
                for group in groups:
                    mask = (data[group_col] == group) & (data[x_col] == x_val)
                    vals = data.loc[mask, y_col]
                    row[str(group)] = _clean_value(vals.iloc[0]) if len(vals) > 0 else None
                chart_data.append(_clean_row(row))

            for i, group in enumerate(groups):
                series.append({
                    "key": str(group),
                    "name": str(group),
                    "color": AFL_COLORS[i % len(AFL_COLORS)],
                })
        else:
            # Single line
            for _, r in data.iterrows():
                x_val = r[x_col]
                x_label = _FINALS_ABBREV.get(str(x_val).strip(), str(x_val))
                row = {"x": x_label, y_col: _clean_value(r[y_col])}
                # Include moving average if present
                if "moving_avg_3" in data.columns:
                    row["moving_avg_3"] = _clean_value(r["moving_avg_3"])
                chart_data.append(_clean_row(row))

            series.append({
                "key": y_col,
                "name": ChartHelper.humanize_column_name(y_col),
                "color": AFL_COLORS[0],
            })

            # Add moving average series if available
            if recommendations.get("show_moving_avg") and "moving_avg_3" in data.columns:
                series.append({
                    "key": "moving_avg_3",
                    "name": "3-Game Average",
                    "color": AFL_COLORS[1],
                    "dashed": True,
                })
                logger.info("Added 3-game moving average to line chart")

        annotations = _convert_annotations(annotations_in)

        # Axis config
        x_axis = {"label": ChartHelper.humanize_column_name(x_col)}
        y_axis = {"label": ChartHelper.humanize_column_name(y_col)}

        _apply_layout_config(x_axis, y_axis, layout_config)

        # Integer ticks for season/year
        if x_col in ["season", "year"]:
            x_axis["integerOnly"] = True

        return {
            "chartType": "line",
            "title": title,
            "data": chart_data,
            "series": series,
            "xAxis": x_axis,
            "yAxis": y_axis,
            "annotations": annotations,
            "legend": len(series) > 1,
            "colors": AFL_COLORS,
        }

    # ── Bar Chart ───────────────────────────────────────────────

    @staticmethod
    def _build_bar_chart(data: pd.DataFrame, params: Dict) -> Dict:
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        title = params.get("title", "Comparison")
        annotations_in = params.get("annotations", [])
        layout_config = params.get("layout_config", {})

        chart_data = []
        for _, r in data.iterrows():
            chart_data.append(_clean_row({
                "x": str(r[x_col]),
                y_col: _clean_value(r[y_col]),
            }))

        series = [{
            "key": y_col,
            "name": ChartHelper.humanize_column_name(y_col),
            "color": AFL_COLORS[0],
        }]

        x_axis = {"label": ChartHelper.humanize_column_name(x_col)}
        y_axis = {"label": ChartHelper.humanize_column_name(y_col)}
        _apply_layout_config(x_axis, y_axis, layout_config)

        if x_col in ["season", "year"]:
            x_axis["integerOnly"] = True

        return {
            "chartType": "bar",
            "title": title,
            "data": chart_data,
            "series": series,
            "xAxis": x_axis,
            "yAxis": y_axis,
            "annotations": _convert_annotations(annotations_in),
            "legend": False,
            "colors": AFL_COLORS,
        }

    # ── Horizontal Bar Chart ────────────────────────────────────

    @staticmethod
    def _build_horizontal_bar_chart(data: pd.DataFrame, params: Dict) -> Dict:
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        title = params.get("title", "Comparison")
        layout_config = params.get("layout_config", {})

        chart_data = []
        for _, r in data.iterrows():
            chart_data.append(_clean_row({
                "x": str(r[x_col]),
                y_col: _clean_value(r[y_col]),
            }))

        series = [{
            "key": y_col,
            "name": ChartHelper.humanize_column_name(y_col),
            "color": AFL_COLORS[0],
        }]

        x_axis = {"label": ChartHelper.humanize_column_name(y_col)}
        y_axis = {"label": ChartHelper.humanize_column_name(x_col)}
        _apply_layout_config(x_axis, y_axis, layout_config)

        return {
            "chartType": "horizontal_bar",
            "title": title,
            "data": chart_data,
            "series": series,
            "xAxis": x_axis,
            "yAxis": y_axis,
            "annotations": [],
            "legend": False,
            "colors": AFL_COLORS,
        }

    # ── Scatter Chart ───────────────────────────────────────────

    @staticmethod
    def _build_scatter_chart(data: pd.DataFrame, params: Dict) -> Dict:
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        group_col = params.get("group_col")
        title = params.get("title", "Correlation Analysis")
        annotations_in = params.get("annotations", [])
        layout_config = params.get("layout_config", {})

        chart_data = []
        series = []

        if group_col and group_col in data.columns:
            groups = list(data[group_col].unique())
            for _, r in data.iterrows():
                row = {
                    "x": _clean_value(r[x_col]),
                    "y": _clean_value(r[y_col]),
                    "group": str(r[group_col]),
                }
                chart_data.append(_clean_row(row))
            for i, group in enumerate(groups):
                series.append({
                    "key": str(group),
                    "name": str(group),
                    "color": AFL_COLORS[i % len(AFL_COLORS)],
                })
        else:
            for _, r in data.iterrows():
                chart_data.append(_clean_row({
                    "x": _clean_value(r[x_col]),
                    "y": _clean_value(r[y_col]),
                }))
            series.append({
                "key": "scatter",
                "name": ChartHelper.humanize_column_name(y_col),
                "color": AFL_COLORS[0],
            })

        x_axis = {"label": ChartHelper.humanize_column_name(x_col)}
        y_axis = {"label": ChartHelper.humanize_column_name(y_col)}
        _apply_layout_config(x_axis, y_axis, layout_config)

        return {
            "chartType": "scatter",
            "title": title,
            "data": chart_data,
            "series": series,
            "xAxis": x_axis,
            "yAxis": y_axis,
            "annotations": _convert_annotations(annotations_in),
            "legend": len(series) > 1,
            "colors": AFL_COLORS,
        }

    # ── Pie Chart ───────────────────────────────────────────────

    @staticmethod
    def _build_pie_chart(data: pd.DataFrame, params: Dict) -> Dict:
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        title = params.get("title", "Distribution")

        chart_data = []
        for _, r in data.iterrows():
            chart_data.append(_clean_row({
                "name": str(r[x_col]),
                "value": _clean_value(r[y_col]),
            }))

        return {
            "chartType": "pie",
            "title": title,
            "data": chart_data,
            "series": [],
            "xAxis": {},
            "yAxis": {},
            "annotations": [],
            "legend": True,
            "colors": AFL_COLORS,
        }

    # ── Box Chart (median + IQR as error bars) ─────────────────

    @staticmethod
    def _build_box_chart(data: pd.DataFrame, params: Dict) -> Dict:
        y_col = params.get("y_col", data.columns[-1])
        group_col = params.get("group_col") or params.get("x_col")
        title = params.get("title", "Distribution Analysis")

        chart_data = []

        if group_col and group_col in data.columns and data[group_col].nunique() <= 20:
            for group in data[group_col].unique():
                group_data = data[data[group_col] == group][y_col].dropna()
                if len(group_data) == 0:
                    continue
                q1 = float(group_data.quantile(0.25))
                median = float(group_data.median())
                q3 = float(group_data.quantile(0.75))
                chart_data.append(_clean_row({
                    "x": str(group),
                    "median": median,
                    "q1": q1,
                    "q3": q3,
                    "min": float(group_data.min()),
                    "max": float(group_data.max()),
                }))
        else:
            y_data = data[y_col].dropna()
            if len(y_data) > 0:
                chart_data.append(_clean_row({
                    "x": ChartHelper.humanize_column_name(y_col),
                    "median": float(y_data.median()),
                    "q1": float(y_data.quantile(0.25)),
                    "q3": float(y_data.quantile(0.75)),
                    "min": float(y_data.min()),
                    "max": float(y_data.max()),
                }))

        series = [{"key": "median", "name": "Median", "color": AFL_COLORS[0]}]

        return {
            "chartType": "box",
            "title": title,
            "data": chart_data,
            "series": series,
            "xAxis": {"label": ChartHelper.humanize_column_name(group_col) if group_col else ""},
            "yAxis": {"label": ChartHelper.humanize_column_name(y_col)},
            "annotations": [],
            "legend": False,
            "colors": AFL_COLORS,
        }

    # ── Multi Bar (stacked / grouped) ──────────────────────────

    @staticmethod
    def _build_multi_bar_chart(data: pd.DataFrame, params: Dict, stacked: bool = False) -> Dict:
        x_col = params.get("x_col", data.columns[0])
        group_col = params.get("group_col")
        title = params.get("title", "Comparison")
        layout_config = params.get("layout_config", {})

        numeric_cols = [c for c in data.select_dtypes(include=['number']).columns.tolist()
                        if 'id' not in c.lower()]

        series = []
        chart_data = []

        if group_col and group_col in data.columns:
            y_col = params.get("y_col", numeric_cols[0] if numeric_cols else data.columns[-1])
            groups = list(data[group_col].unique())
            x_values = data[x_col].unique().tolist()

            for x_val in x_values:
                row = {"x": str(x_val)}
                for group in groups:
                    mask = (data[group_col] == group) & (data[x_col] == x_val)
                    vals = data.loc[mask, y_col]
                    row[str(group)] = _clean_value(vals.iloc[0]) if len(vals) > 0 else None
                chart_data.append(_clean_row(row))

            for i, group in enumerate(groups):
                s = {
                    "key": str(group),
                    "name": str(group),
                    "color": AFL_COLORS[i % len(AFL_COLORS)],
                }
                if stacked:
                    s["stackId"] = "a"
                series.append(s)
        else:
            for _, r in data.iterrows():
                row = {"x": str(r[x_col])}
                for col in numeric_cols[:6]:
                    row[col] = _clean_value(r[col])
                chart_data.append(_clean_row(row))

            for i, col in enumerate(numeric_cols[:6]):
                s = {
                    "key": col,
                    "name": ChartHelper.humanize_column_name(col),
                    "color": AFL_COLORS[i % len(AFL_COLORS)],
                }
                if stacked:
                    s["stackId"] = "a"
                series.append(s)

        x_axis = {"label": ChartHelper.humanize_column_name(x_col)}
        y_axis = {"label": "Value"}
        _apply_layout_config(x_axis, y_axis, layout_config)

        return {
            "chartType": "stacked_bar" if stacked else "grouped_bar",
            "title": title,
            "data": chart_data,
            "series": series,
            "xAxis": x_axis,
            "yAxis": y_axis,
            "annotations": [],
            "legend": True,
            "colors": AFL_COLORS,
        }

    # ── Comparison Chart ────────────────────────────────────────

    @staticmethod
    def _build_comparison_chart(data: pd.DataFrame, params: Dict) -> Dict:
        group_col = params.get("group_col", data.columns[0])
        metric_cols = params.get("metric_cols", data.select_dtypes(include=['number']).columns.tolist())
        title = params.get("title", "Comparison")

        chart_data = []
        for _, r in data.iterrows():
            row = {"x": str(r[group_col])}
            for col in metric_cols[:6]:
                row[col] = _clean_value(r[col])
            chart_data.append(_clean_row(row))

        series = []
        for i, col in enumerate(metric_cols[:6]):
            series.append({
                "key": col,
                "name": ChartHelper.humanize_column_name(col),
                "color": AFL_COLORS[i % len(AFL_COLORS)],
            })

        return {
            "chartType": "grouped_bar",
            "title": title,
            "data": chart_data,
            "series": series,
            "xAxis": {"label": ChartHelper.humanize_column_name(group_col)},
            "yAxis": {"label": "Value"},
            "annotations": [],
            "legend": True,
            "colors": AFL_COLORS,
        }


# ── Helpers ─────────────────────────────────────────────────────

def _convert_annotations(plotly_annotations: List[Dict]) -> List[Dict]:
    """Convert Plotly-format annotations to simplified {x, y, label, color} format."""
    result = []
    for ann in plotly_annotations:
        # Skip paper-ref annotations (missing rounds, etc.) — they don't map to data points
        if ann.get("xref") == "paper":
            continue
        result.append({
            "x": ann.get("x"),
            "y": ann.get("y"),
            "label": ann.get("text", ""),
            "color": ann.get("font", {}).get("color", "#059669"),
        })
    return result


def _apply_layout_config(x_axis: Dict, y_axis: Dict, layout_config: Dict):
    """Apply layout optimizer config to axis dicts."""
    if not layout_config:
        return

    xaxis_cfg = layout_config.get("xaxis", {})
    yaxis_cfg = layout_config.get("yaxis", {})

    # Tick angle
    if "tickangle" in xaxis_cfg:
        x_axis["tickAngle"] = xaxis_cfg["tickangle"]

    # Y-axis domain (range)
    if "range" in yaxis_cfg:
        y_axis["domain"] = yaxis_cfg["range"]

    # Integer ticks for count data
    if "dtick" in yaxis_cfg and yaxis_cfg["dtick"] >= 1:
        y_axis["integerOnly"] = True
