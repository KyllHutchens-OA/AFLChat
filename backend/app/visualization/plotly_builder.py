"""
AFL Analytics Agent - Plotly Chart Builder

Generates Hex-quality Plotly chart specifications.
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging
import re

logger = logging.getLogger(__name__)


class ChartHelper:
    """Helper functions for chart generation."""

    @staticmethod
    def humanize_column_name(col_name: str) -> str:
        """
        Convert database column names to human-readable labels.

        Examples:
            "win_loss_ratio" -> "Win/Loss Ratio"
            "avg_score_per_game" -> "Avg Score Per Game"
            "season" -> "Season"
        """
        # Special cases first
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

        # Generic humanization: replace underscores with spaces and title case
        human = col_name.replace("_", " ").title()
        return human

    @staticmethod
    def generate_chart_title(
        intent: str,
        entities: Dict[str, Any],
        metrics: List[str],
        data_cols: List[str]
    ) -> str:
        """
        Generate a descriptive chart title based on query intent and entities.

        Args:
            intent: Query intent (TREND_ANALYSIS, TEAM_ANALYSIS, etc.)
            entities: Extracted entities (teams, seasons, players)
            metrics: Key metrics being visualized
            data_cols: All column names in the data

        Returns:
            Human-readable chart title
        """
        teams = entities.get("teams", [])
        seasons = entities.get("seasons", [])
        players = entities.get("players", [])

        # Determine subject (player takes priority, then team)
        if players:
            subject = players[0] if len(players) == 1 else " vs ".join(players[:2]) if len(players) > 1 else ""
            subject_type = "player"
        elif teams:
            subject = teams[0] if len(teams) == 1 else " vs ".join(teams[:2]) if len(teams) > 1 else ""
            subject_type = "team"
        else:
            subject = ""
            subject_type = None

        # Build season string
        season_str = ""
        if seasons:
            if len(seasons) == 1:
                season_str = str(seasons[0])
            elif len(seasons) == 2:
                season_str = f"{seasons[0]}-{seasons[-1]}"
            else:
                season_str = f"{seasons[0]}-{seasons[-1]}"

        # Metric mapping - check data columns for the primary metric
        metric_map = {
            "goals": "Goals",
            "disposals": "Disposals",
            "kicks": "Kicks",
            "handballs": "Handballs",
            "marks": "Marks",
            "tackles": "Tackles",
            "clearances": "Clearances",
            "inside_50s": "Inside 50s",
            "contested_possessions": "Contested Possessions",
            "uncontested_possessions": "Uncontested Possessions",
            "brownlow_votes": "Brownlow Votes",
            "behinds": "Behinds",
            "hitouts": "Hitouts",
            "win_loss_ratio": "Win/Loss Ratio",
            "win_rate": "Win Rate",
            "win_percentage": "Win Rate",
            "wins": "Wins",
            "losses": "Losses",
            "avg_score_per_game": "Scoring",
            "avg_score": "Average Score",
            "margin": "Margin",
            "total_score": "Total Score",
            "home_score": "Score",
            "away_score": "Score",
            "score": "Score",
            "total_goals": "Goals",
            "total_disposals": "Disposals",
        }

        # Find the metric from data columns
        metric = None
        for col in data_cols:
            col_lower = col.lower()
            if col_lower in metric_map:
                metric = metric_map[col_lower]
                break

        # Also check the metrics list passed in
        if not metric:
            for m in metrics:
                m_lower = m.lower()
                if m_lower in metric_map:
                    metric = metric_map[m_lower]
                    break

        # Check if this is a "by round" query (has round column)
        by_round = "round" in [c.lower() for c in data_cols]

        # Build dynamic title
        parts = []

        # Add subject
        if subject:
            parts.append(subject)

        # Add metric
        if metric:
            parts.append(metric)
        elif subject_type == "player":
            parts.append("Stats")
        elif subject_type == "team":
            parts.append("Performance")

        # Add time context
        if by_round and season_str:
            parts.append(f"by Round ({season_str})")
        elif by_round:
            parts.append("by Round")
        elif season_str:
            if len(seasons) > 1:
                parts.append(f"({season_str})")
            else:
                parts.append(season_str)

        # Fallback
        if not parts:
            return "AFL Statistics"

        return " ".join(parts)


class PlotlyBuilder:
    """
    Builds Plotly chart specifications with Hex-quality theming.

    Design Principles:
    - Clean, professional appearance
    - Consistent color palette
    - Clear labels and titles
    - Interactive tooltips
    - Responsive design
    """

    # Hex-inspired color palette
    COLORS = {
        "primary": "#3b82f6",  # Blue
        "secondary": "#ef4444",  # Red
        "success": "#10b981",  # Green
        "warning": "#f59e0b",  # Orange
        "purple": "#8b5cf6",  # Purple
        "teal": "#14b8a6",  # Teal
        "gray": "#6b7280",  # Gray
    }

    COLOR_SEQUENCE = [
        COLORS["primary"],
        COLORS["secondary"],
        COLORS["success"],
        COLORS["warning"],
        COLORS["purple"],
        COLORS["teal"],
    ]

    # Professional theme system
    THEMES = {
        "professional": {
            "primary": "#2563eb",      # Deep blue
            "secondary": "#dc2626",    # Crimson
            "success": "#059669",      # Emerald
            "accent": "#7c3aed",       # Purple
            "neutral": "#475569",      # Slate
            "background": "#ffffff",
            "paper": "#ffffff",
            "grid": "#f1f5f9",         # Light slate
            "text": "#0f172a"          # Dark slate
        },
        "high_contrast": {
            "primary": "#0ea5e9",      # Sky blue
            "secondary": "#f43f5e",    # Rose
            "success": "#10b981",      # Emerald
            "accent": "#a855f7",       # Purple
            "neutral": "#64748b",      # Slate
            "background": "#ffffff",
            "paper": "#ffffff",
            "grid": "#e2e8f0",
            "text": "#020617"
        }
    }

    # Typography hierarchy
    FONTS = {
        "title": {
            "family": "Inter, sans-serif",
            "size": 18,
            "weight": 600,
            "color": "#0f172a"
        },
        "axis_label": {
            "family": "Inter, sans-serif",
            "size": 13,
            "weight": 500,
            "color": "#334155"
        },
        "tick_label": {
            "family": "SF Mono, Consolas, Monaco, monospace",  # Monospace for numbers
            "size": 11,
            "color": "#64748b"
        },
        "annotation": {
            "family": "Inter, sans-serif",
            "size": 10,
            "color": "#64748b"
        },
        "legend": {
            "family": "Inter, sans-serif",
            "size": 12,
            "color": "#475569"
        }
    }

    # Base layout configuration (enhanced)
    BASE_LAYOUT = {
        "font": {
            "family": FONTS["axis_label"]["family"],
            "size": 14,
            "color": THEMES["professional"]["text"]
        },
        "plot_bgcolor": "#fafafa",      # Slight off-white for better contrast
        "paper_bgcolor": "#ffffff",
        "hovermode": "x unified",
        "showlegend": True,
        "legend": {
            "orientation": "h",
            "yanchor": "top",
            "y": -0.15,
            "xanchor": "center",
            "x": 0.5,
            "font": {
                "family": FONTS["legend"]["family"],
                "size": FONTS["legend"]["size"],
                "color": FONTS["legend"]["color"]
            },
            "bgcolor": "rgba(255,255,255,0.9)",
            "bordercolor": "#e5e7eb",
            "borderwidth": 1
        },
        "margin": {"l": 80, "r": 40, "t": 100, "b": 100},
        "xaxis": {
            "showgrid": True,
            "gridwidth": 1,
            "gridcolor": "#e2e8f0",     # Light gray grid
            "zeroline": True,
            "zerolinewidth": 2,
            "zerolinecolor": "#cbd5e1",  # Slightly darker zero line
            "title": {
                "font": {
                    "family": FONTS["axis_label"]["family"],
                    "size": FONTS["axis_label"]["size"],
                    "color": FONTS["axis_label"]["color"]
                },
                "standoff": 15
            },
            "tickfont": {
                "family": FONTS["tick_label"]["family"],
                "size": FONTS["tick_label"]["size"],
                "color": FONTS["tick_label"]["color"]
            }
        },
        "yaxis": {
            "showgrid": True,
            "gridwidth": 1,
            "gridcolor": "#e2e8f0",
            "zeroline": False,
            "title": {
                "font": {
                    "family": FONTS["axis_label"]["family"],
                    "size": FONTS["axis_label"]["size"],
                    "color": FONTS["axis_label"]["color"]
                },
                "standoff": 15
            },
            "tickfont": {
                "family": FONTS["tick_label"]["family"],
                "size": FONTS["tick_label"]["size"],
                "color": FONTS["tick_label"]["color"]
            }
        }
    }

    @staticmethod
    def _select_chart_type(data: pd.DataFrame, intent: str, columns: List[str]) -> str:
        """
        Intelligently select chart type based on intent and data characteristics.

        Args:
            data: DataFrame with chart data
            intent: Query intent
            columns: Column names in the data

        Returns:
            Chart type string ("line", "bar", "scatter", "comparison")
        """
        # Convert intent to string for comparison (handles both string and enum)
        intent_str = str(intent)

        # TREND_ANALYSIS -> Line chart (time series)
        if "TREND_ANALYSIS" in intent_str:
            return "line"

        # PLAYER_COMPARISON or TEAM_ANALYSIS with multiple teams -> Comparison bar chart
        if "PLAYER_COMPARISON" in intent_str:
            # If we have multiple numeric columns, use grouped bar (comparison)
            numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
            if len(numeric_cols) > 2:
                return "comparison"
            return "bar"

        # TEAM_ANALYSIS -> Check if it's time series or single value
        if "TEAM_ANALYSIS" in intent_str:
            # If we have season/round column and multiple rows, use line
            if ('season' in columns or 'round' in columns) and len(data) > 5:
                return "line"
            # Otherwise use bar
            return "bar"

        # Default: Use data shape to decide
        # Many rows (>5) with time dimension -> line chart
        if len(data) > 5 and any(col in columns for col in ['season', 'round', 'match_date', 'year']):
            return "line"

        # Few rows (<= 5) -> bar chart for comparison
        if len(data) <= 5:
            return "bar"

        # Default fallback
        return "bar"

    @staticmethod
    def generate_chart(
        data: pd.DataFrame,
        chart_type: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a Plotly chart specification.

        Args:
            data: DataFrame with chart data
            chart_type: Type of chart ("line", "bar", "scatter", "heatmap", "pie")
            params: Optional parameters (title, x_col, y_col, group_col, etc.)

        Returns:
            Plotly chart specification (JSON-serializable dict)
        """
        if params is None:
            params = {}

        try:
            if chart_type == "line":
                return PlotlyBuilder._build_line_chart(data, params)

            elif chart_type == "bar":
                return PlotlyBuilder._build_bar_chart(data, params)

            elif chart_type == "scatter":
                return PlotlyBuilder._build_scatter_chart(data, params)

            elif chart_type == "comparison":
                return PlotlyBuilder._build_comparison_chart(data, params)

            elif chart_type == "trend":
                return PlotlyBuilder._build_trend_chart(data, params)

            else:
                logger.warning(f"Unknown chart type: {chart_type}, defaulting to bar chart")
                return PlotlyBuilder._build_bar_chart(data, params)

        except Exception as e:
            logger.error(f"Error generating chart: {e}")
            return {
                "error": str(e),
                "data": [],
                "layout": PlotlyBuilder.BASE_LAYOUT
            }

    @staticmethod
    def _build_line_chart(data: pd.DataFrame, params: Dict) -> Dict:
        """Build a line chart for trends over time."""
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        group_col = params.get("group_col")
        title = params.get("title", "Trend Over Time")

        # Get preprocessing results
        metadata = params.get("metadata", {})
        recommendations = params.get("recommendations", {})
        annotations = params.get("annotations", [])
        layout_config = params.get("layout_config", {})

        # If x_col is 'round', try to convert to numeric for proper sorting
        # Handle both numeric rounds (0, 1, 2...) and finals ("Qualifying Final", etc.)
        if x_col == 'round' and 'match_date' in data.columns:
            # Use match_date for sorting, but keep round for display
            data = data.sort_values('match_date').reset_index(drop=True)
            # Create a numeric index for X-axis to maintain order
            data['_plot_order'] = range(len(data))
            x_col_for_plot = '_plot_order'
            # Store round labels for custom tick labels
            round_labels = data['round'].tolist()
        else:
            x_col_for_plot = x_col
            round_labels = None

        traces = []

        if group_col and group_col in data.columns:
            # Multiple lines (one per group)
            for i, group in enumerate(data[group_col].unique()):
                group_data = data[data[group_col] == group].copy()
                traces.append(go.Scatter(
                    x=group_data[x_col_for_plot].tolist(),
                    y=group_data[y_col].tolist(),
                    mode="lines+markers",
                    name=str(group),
                    line={"color": PlotlyBuilder.COLOR_SEQUENCE[i % len(PlotlyBuilder.COLOR_SEQUENCE)], "width": 3},
                    marker={"size": 8}
                ))
        else:
            # Single line
            traces.append(go.Scatter(
                x=data[x_col_for_plot].tolist(),
                y=data[y_col].tolist(),
                mode="lines+markers",
                name=y_col,
                line={"color": PlotlyBuilder.COLORS["primary"], "width": 3},
                marker={"size": 8}
            ))

        # Add moving average trace if recommended and available
        if recommendations.get("show_moving_avg") and "moving_avg_3" in data.columns:
            from app.visualization.data_preprocessor import DataPreprocessor
            ma_trace_dict = DataPreprocessor.add_moving_average_trace(
                data=data,
                x_col=x_col_for_plot,
                y_col=y_col,
                window=3
            )
            if ma_trace_dict:
                traces.append(go.Scatter(**ma_trace_dict))
                logger.info("Added 3-game moving average to line chart")

        layout = PlotlyBuilder.BASE_LAYOUT.copy()
        layout["title"] = {
            "text": title,
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 18},
            "pad": {"b": 20}
        }
        layout["xaxis"]["title"] = {"text": ChartHelper.humanize_column_name(x_col)}
        layout["yaxis"]["title"] = {"text": ChartHelper.humanize_column_name(y_col)}

        # Apply layout optimizations
        if layout_config:
            # Update margins
            if "margin" in layout_config:
                layout["margin"] = layout_config["margin"]

            # Update height
            if "height" in layout_config:
                layout["height"] = layout_config["height"]

            # Update x-axis configuration
            if "xaxis" in layout_config:
                layout["xaxis"].update(layout_config["xaxis"])

            # Update y-axis configuration
            if "yaxis" in layout_config:
                layout["yaxis"].update(layout_config["yaxis"])

        # If we created custom ordering, set tick labels to show round names
        if round_labels is not None:
            layout["xaxis"]["tickmode"] = "array"
            layout["xaxis"]["tickvals"] = list(range(len(round_labels)))
            layout["xaxis"]["ticktext"] = round_labels
        # For season/year columns, ensure integer-only ticks (no 2020.5)
        elif x_col in ['season', 'year'] or x_col_for_plot in ['season', 'year']:
            layout["xaxis"]["tickmode"] = "linear"
            layout["xaxis"]["dtick"] = 1  # Force integer steps
            layout["xaxis"]["tickformat"] = "d"  # Integer format (no decimals)

        # Add peak/trough annotations if recommended
        if recommendations.get("show_peaks"):
            from app.visualization.data_preprocessor import DataPreprocessor
            peak_annotations = DataPreprocessor.add_peak_annotations(
                data=data,
                x_col=x_col_for_plot,
                y_col=y_col
            )
            annotations.extend(peak_annotations)
            logger.info(f"Added {len(peak_annotations)} peak/trough annotations")

        # Add all annotations to layout
        if annotations:
            layout["annotations"] = annotations

        # Create figure and convert to JSON-serializable dict
        fig = go.Figure(data=traces, layout=layout)
        fig_dict = fig.to_dict()

        # Clean NaN values (not JSON-serializable) - replace with None
        import json
        import math

        def clean_nan(obj):
            """Recursively replace NaN with None for JSON serialization"""
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, float) and math.isnan(obj):
                return None
            else:
                return obj

        return clean_nan(fig_dict)

    @staticmethod
    def _build_bar_chart(data: pd.DataFrame, params: Dict) -> Dict:
        """Build a bar chart for comparisons."""
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        title = params.get("title", "Comparison")
        orientation = params.get("orientation", "v")  # v or h

        # Get preprocessing results
        metadata = params.get("metadata", {})
        recommendations = params.get("recommendations", {})
        annotations = params.get("annotations", [])
        layout_config = params.get("layout_config", {})

        traces = [go.Bar(
            x=data[x_col].tolist() if orientation == "v" else data[y_col].tolist(),
            y=data[y_col].tolist() if orientation == "v" else data[x_col].tolist(),
            orientation=orientation,
            marker={"color": PlotlyBuilder.COLORS["primary"]},
            text=data[y_col].tolist() if orientation == "v" else data[x_col].tolist(),
            textposition="outside"
        )]

        layout = PlotlyBuilder.BASE_LAYOUT.copy()
        layout["title"] = {
            "text": title,
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 18},
            "pad": {"b": 20}
        }
        layout["xaxis"]["title"] = {"text": ChartHelper.humanize_column_name(x_col if orientation == "v" else y_col)}
        layout["yaxis"]["title"] = {"text": ChartHelper.humanize_column_name(y_col if orientation == "v" else x_col)}
        layout["showlegend"] = False

        # Apply layout optimizations
        if layout_config:
            # Update margins
            if "margin" in layout_config:
                layout["margin"] = layout_config["margin"]

            # Update height
            if "height" in layout_config:
                layout["height"] = layout_config["height"]

            # Update x-axis configuration
            if "xaxis" in layout_config:
                layout["xaxis"].update(layout_config["xaxis"])

            # Update y-axis configuration
            if "yaxis" in layout_config:
                layout["yaxis"].update(layout_config["yaxis"])

        # For season/year columns, ensure integer-only ticks (no 2020.5)
        if x_col in ['season', 'year']:
            layout["xaxis"]["tickmode"] = "linear"
            layout["xaxis"]["dtick"] = 1  # Force integer steps
            layout["xaxis"]["tickformat"] = "d"  # Integer format (no decimals)

        # Add all annotations to layout
        if annotations:
            layout["annotations"] = annotations

        # Create figure and convert to JSON-serializable dict
        fig = go.Figure(data=traces, layout=layout)
        fig_dict = fig.to_dict()

        # Clean NaN values (not JSON-serializable) - replace with None
        import json
        import math

        def clean_nan(obj):
            """Recursively replace NaN with None for JSON serialization"""
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, float) and math.isnan(obj):
                return None
            else:
                return obj

        return clean_nan(fig_dict)

    @staticmethod
    def _build_scatter_chart(data: pd.DataFrame, params: Dict) -> Dict:
        """Build a scatter plot for correlations."""
        x_col = params.get("x_col", data.columns[0])
        y_col = params.get("y_col", data.columns[1])
        title = params.get("title", "Correlation Analysis")
        group_col = params.get("group_col")

        # Get preprocessing results
        metadata = params.get("metadata", {})
        recommendations = params.get("recommendations", {})
        annotations = params.get("annotations", [])
        layout_config = params.get("layout_config", {})

        traces = []

        if group_col and group_col in data.columns:
            # Color by group
            for i, group in enumerate(data[group_col].unique()):
                group_data = data[data[group_col] == group]
                traces.append(go.Scatter(
                    x=group_data[x_col].tolist(),
                    y=group_data[y_col].tolist(),
                    mode="markers",
                    name=str(group),
                    marker={
                        "color": PlotlyBuilder.COLOR_SEQUENCE[i % len(PlotlyBuilder.COLOR_SEQUENCE)],
                        "size": 10,
                        "opacity": 0.7
                    }
                ))
        else:
            # Single scatter
            traces.append(go.Scatter(
                x=data[x_col].tolist(),
                y=data[y_col].tolist(),
                mode="markers",
                marker={"color": PlotlyBuilder.COLORS["primary"], "size": 10, "opacity": 0.7}
            ))

        layout = PlotlyBuilder.BASE_LAYOUT.copy()
        layout["title"] = {
            "text": title,
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 18},
            "pad": {"b": 20}
        }
        layout["xaxis"]["title"] = {"text": ChartHelper.humanize_column_name(x_col)}
        layout["yaxis"]["title"] = {"text": ChartHelper.humanize_column_name(y_col)}

        # Apply layout optimizations
        if layout_config:
            # Update margins
            if "margin" in layout_config:
                layout["margin"] = layout_config["margin"]

            # Update height
            if "height" in layout_config:
                layout["height"] = layout_config["height"]

            # Update x-axis configuration
            if "xaxis" in layout_config:
                layout["xaxis"].update(layout_config["xaxis"])

            # Update y-axis configuration
            if "yaxis" in layout_config:
                layout["yaxis"].update(layout_config["yaxis"])

        # Add all annotations to layout
        if annotations:
            layout["annotations"] = annotations

        # Create figure and convert to JSON-serializable dict
        fig = go.Figure(data=traces, layout=layout)
        fig_dict = fig.to_dict()

        # Clean NaN values (not JSON-serializable) - replace with None
        import json
        import math

        def clean_nan(obj):
            """Recursively replace NaN with None for JSON serialization"""
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, float) and math.isnan(obj):
                return None
            else:
                return obj

        return clean_nan(fig_dict)

    @staticmethod
    def _build_comparison_chart(data: pd.DataFrame, params: Dict) -> Dict:
        """Build a grouped bar chart for comparing entities."""
        group_col = params.get("group_col", data.columns[0])
        metric_cols = params.get("metric_cols", data.select_dtypes(include=['number']).columns.tolist())
        title = params.get("title", "Comparison")

        traces = []

        for i, metric in enumerate(metric_cols[:6]):  # Limit to 6 metrics for readability
            traces.append(go.Bar(
                x=data[group_col].tolist(),
                y=data[metric].tolist(),
                name=metric,
                marker={"color": PlotlyBuilder.COLOR_SEQUENCE[i % len(PlotlyBuilder.COLOR_SEQUENCE)]}
            ))

        layout = PlotlyBuilder.BASE_LAYOUT.copy()
        layout["title"] = {
            "text": title,
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 18},
            "pad": {"b": 20}
        }
        layout["barmode"] = "group"
        layout["xaxis"]["title"] = {"text": ChartHelper.humanize_column_name(group_col)}
        layout["yaxis"]["title"] = {"text": "Value"}

        # Create figure and convert to JSON-serializable dict
        fig = go.Figure(data=traces, layout=layout)
        fig_dict = fig.to_dict()

        # Clean NaN values (not JSON-serializable) - replace with None
        import json
        import math

        def clean_nan(obj):
            """Recursively replace NaN with None for JSON serialization"""
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan(item) for item in obj]
            elif isinstance(obj, float) and math.isnan(obj):
                return None
            else:
                return obj

        return clean_nan(fig_dict)

    @staticmethod
    def _build_trend_chart(data: pd.DataFrame, params: Dict) -> Dict:
        """Build a line chart with trend analysis (moving average, etc.)."""
        # For now, delegate to line chart (can enhance with moving averages later)
        return PlotlyBuilder._build_line_chart(data, params)
