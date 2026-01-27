"""
Data Preprocessor for Chart Visualizations

Analyzes data characteristics and prepares it for optimal visualization:
- Detects sparse/missing data
- Identifies outliers
- Recommends enhancements (moving averages, aggregations)
- Generates annotations for context
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple


class DataPreprocessor:
    """Preprocesses and analyzes data for optimal chart visualization"""

    # Thresholds for data quality assessment
    SPARSE_COEFFICIENT_THRESHOLD = 0.3
    SPARSE_RANGE_THRESHOLD = 5
    MIN_MOVING_AVG_POINTS = 5

    # Count/discrete metric names (should use bar charts, not moving averages)
    COUNT_METRICS = {
        'goals', 'behinds', 'goal', 'behind', 'kicks', 'handballs', 'disposals',
        'marks', 'tackles', 'hitouts', 'clearances', 'rebounds', 'inside_50s',
        'clangers', 'turnovers', 'intercepts', 'score_involvements',
        'metres_gained', 'bounces', 'goals_assists', 'goal_assists'
    }

    @staticmethod
    def is_count_metric(y_col: str) -> bool:
        """
        Determine if a metric is a discrete count (goals, disposals, etc.)

        Count metrics should:
        - Use bar charts instead of line charts
        - Not show moving averages (fractional values are meaningless)
        - Always start y-axis at 0
        """
        y_col_lower = y_col.lower().strip()
        return y_col_lower in DataPreprocessor.COUNT_METRICS

    @staticmethod
    def preprocess_for_chart(
        data: pd.DataFrame,
        chart_type: str,
        x_col: str,
        y_col: str,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Analyze and preprocess data for optimal visualization

        Args:
            data: DataFrame containing chart data
            chart_type: Type of chart ('line', 'bar', 'scatter', etc.)
            x_col: X-axis column name
            y_col: Y-axis column name
            params: Optional additional parameters

        Returns:
            Dict containing:
            - data: Processed DataFrame (may include new columns like moving_avg)
            - annotations: List of annotation dicts for Plotly
            - recommendations: Dict of suggested enhancements
            - metadata: Dict with data characteristics
        """
        params = params or {}
        processed_data = data.copy()

        # Detect if this is a count metric (goals, disposals, etc.)
        is_count = DataPreprocessor.is_count_metric(y_col)

        # Replace NaN with 0 for count metrics (0 goals is clearer than a gap)
        # For all metrics, fill NaN with 0 for clearer visualization
        if y_col in processed_data.columns:
            processed_data[y_col] = processed_data[y_col].fillna(0)

        # Analyze data characteristics
        metadata = DataPreprocessor._analyze_data(processed_data, x_col, y_col, chart_type)
        metadata["is_count_metric"] = is_count

        # Generate annotations based on analysis
        annotations = DataPreprocessor._generate_annotations(
            processed_data, x_col, y_col, chart_type, metadata
        )

        # Generate recommendations
        recommendations = DataPreprocessor._generate_recommendations(
            processed_data, y_col, metadata
        )

        # IMPORTANT: Don't add moving average for count metrics (goals, disposals)
        # Fractional counts (1.5 goals) are meaningless and confusing
        if not is_count and recommendations.get("show_moving_avg") and len(processed_data) >= DataPreprocessor.MIN_MOVING_AVG_POINTS:
            processed_data['moving_avg_3'] = processed_data[y_col].rolling(
                window=3, min_periods=1, center=False
            ).mean()

        return {
            "data": processed_data,
            "annotations": annotations,
            "recommendations": recommendations,
            "metadata": metadata
        }

    @staticmethod
    def _analyze_data(
        data: pd.DataFrame,
        x_col: str,
        y_col: str,
        chart_type: str
    ) -> Dict[str, Any]:
        """Analyze data characteristics"""
        metadata = {
            "is_sparse": False,
            "has_gaps": False,
            "variance_level": "medium",
            "missing_points": [],
            "outliers": [],
            "suggested_aggregation": None
        }

        if y_col not in data.columns or len(data) == 0:
            return metadata

        # Analyze Y-column distribution
        y_data = data[y_col].dropna()

        if len(y_data) < 2:
            metadata["is_sparse"] = True
            metadata["variance_level"] = "low"
            return metadata

        # Calculate statistics
        mean_val = y_data.mean()
        variance = y_data.var()
        min_val = y_data.min()
        max_val = y_data.max()
        data_range = max_val - min_val

        # Coefficient of variation
        coeff_variation = (variance / mean_val) if mean_val > 0 else 0

        # Detect sparse data
        is_sparse = (
            coeff_variation < DataPreprocessor.SPARSE_COEFFICIENT_THRESHOLD or
            data_range < DataPreprocessor.SPARSE_RANGE_THRESHOLD
        )

        metadata["is_sparse"] = is_sparse

        # Variance level
        if variance == 0:
            metadata["variance_level"] = "zero"
        elif coeff_variation < 0.2:
            metadata["variance_level"] = "low"
        elif coeff_variation < 0.6:
            metadata["variance_level"] = "medium"
        else:
            metadata["variance_level"] = "high"

        # Detect missing data for time series
        if chart_type == "line" and x_col == "round":
            metadata["has_gaps"], metadata["missing_points"] = DataPreprocessor._detect_missing_rounds(data, x_col)

        # Detect outliers (using IQR method)
        if len(y_data) >= 10:  # Only for sufficient data
            metadata["outliers"] = DataPreprocessor._detect_outliers(y_data)

        return metadata

    @staticmethod
    def _detect_missing_rounds(data: pd.DataFrame, round_col: str) -> Tuple[bool, List[int]]:
        """Detect missing rounds in time series data"""
        try:
            # Extract round numbers (handle strings like "Round 5" or just "5")
            rounds = data[round_col].dropna().astype(str)

            # Convert to integers (extract digits)
            round_nums = []
            for r in rounds:
                # Extract first number from string
                digits = ''.join(filter(str.isdigit, str(r)))
                if digits:
                    round_nums.append(int(digits))

            if not round_nums:
                return False, []

            actual_rounds = set(round_nums)
            min_round = min(actual_rounds)
            max_round = max(actual_rounds)

            # Expected rounds (typically 1-24 for AFL)
            expected_max = min(max_round, 24)
            expected_rounds = set(range(min_round, expected_max + 1))

            missing = sorted(expected_rounds - actual_rounds)

            return len(missing) > 0, missing

        except Exception:
            return False, []

    @staticmethod
    def _detect_outliers(y_data: pd.Series) -> List[int]:
        """Detect outliers using IQR method"""
        try:
            Q1 = y_data.quantile(0.25)
            Q3 = y_data.quantile(0.75)
            IQR = Q3 - Q1

            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            # Find indices of outliers
            outlier_indices = y_data[
                (y_data < lower_bound) | (y_data > upper_bound)
            ].index.tolist()

            return outlier_indices[:5]  # Limit to 5 outliers to avoid clutter

        except Exception:
            return []

    @staticmethod
    def _generate_annotations(
        data: pd.DataFrame,
        x_col: str,
        y_col: str,
        chart_type: str,
        metadata: Dict
    ) -> List[Dict[str, Any]]:
        """Generate Plotly annotations based on data analysis"""
        annotations = []
        is_count = metadata.get("is_count_metric", False)

        # Missing rounds annotation
        # Skip for bar charts and count metrics - gaps are visually obvious
        if not is_count and chart_type != "bar" and metadata.get("has_gaps") and metadata.get("missing_points"):
            missing = metadata["missing_points"]

            # Format missing rounds (group consecutive ones)
            missing_str = DataPreprocessor._format_missing_rounds(missing)

            annotations.append({
                "text": f"Missing: {missing_str}",
                "xref": "paper",
                "yref": "paper",
                "x": 0.02,
                "y": 0.98,
                "showarrow": False,
                "font": {"size": 10, "color": "#6b7280", "family": "Inter, sans-serif"},
                "bgcolor": "rgba(255, 255, 255, 0.8)",
                "bordercolor": "#e5e7eb",
                "borderwidth": 1,
                "borderpad": 4,
                "xanchor": "left",
                "yanchor": "top"
            })

        # Outlier annotations (limit to avoid clutter)
        if metadata.get("outliers") and len(metadata["outliers"]) > 0:
            for idx in metadata["outliers"][:3]:  # Max 3 outlier annotations
                if idx in data.index:
                    row = data.loc[idx]
                    if x_col in row and y_col in row:
                        # Convert to Python native types for JSON serialization
                        x_val = row[x_col]
                        y_val = float(row[y_col])
                        if isinstance(x_val, (int, float)):
                            x_val = float(x_val)

                        annotations.append({
                            "x": x_val,
                            "y": y_val,
                            "text": f"⚠️ {y_val:.1f}",
                            "showarrow": True,
                            "arrowhead": 2,
                            "arrowsize": 1,
                            "arrowcolor": "#f59e0b",
                            "font": {"size": 9, "color": "#f59e0b"},
                            "bgcolor": "rgba(255, 255, 255, 0.9)",
                            "bordercolor": "#f59e0b",
                            "borderwidth": 1
                        })

        return annotations

    @staticmethod
    def _format_missing_rounds(missing: List[int]) -> str:
        """Format missing rounds list into readable string (e.g., 'R3, R5-R7, R11')"""
        if not missing:
            return ""

        groups = []
        start = missing[0]
        end = missing[0]

        for i in range(1, len(missing)):
            if missing[i] == end + 1:
                # Consecutive round
                end = missing[i]
            else:
                # Gap found, save group
                if start == end:
                    groups.append(f"R{start}")
                else:
                    groups.append(f"R{start}-R{end}")
                start = missing[i]
                end = missing[i]

        # Add last group
        if start == end:
            groups.append(f"R{start}")
        else:
            groups.append(f"R{start}-R{end}")

        return ", ".join(groups)

    @staticmethod
    def _generate_recommendations(
        data: pd.DataFrame,
        y_col: str,
        metadata: Dict
    ) -> Dict[str, Any]:
        """Generate recommendations for chart enhancements"""
        is_count = metadata.get("is_count_metric", False)

        recommendations = {
            "show_moving_avg": False,
            "show_peaks": False,
            "suggested_aggregation": None,
            "prefer_bar_chart": False
        }

        # For count metrics (goals, disposals, etc.):
        # - Prefer bar charts over line charts
        # - Don't show moving averages (fractional counts are meaningless)
        # - Always show peaks (even 2 goals is notable)
        if is_count:
            recommendations["prefer_bar_chart"] = True
            recommendations["show_moving_avg"] = False  # Never for counts
            recommendations["show_peaks"] = len(data) >= 3  # Show peaks if we have data
        else:
            # For continuous metrics (percentages, averages, etc.):
            # Recommend moving average for sparse data
            if metadata.get("is_sparse") and len(data) >= DataPreprocessor.MIN_MOVING_AVG_POINTS:
                recommendations["show_moving_avg"] = True

            # Recommend peak/trough annotations for data with variation
            if metadata.get("variance_level") in ["medium", "high"] and len(data) >= 3:
                recommendations["show_peaks"] = True

        return recommendations

    @staticmethod
    def add_moving_average_trace(
        data: pd.DataFrame,
        x_col: str,
        y_col: str,
        window: int = 3
    ) -> Dict[str, Any]:
        """
        Generate Plotly trace for moving average

        Args:
            data: DataFrame with moving_avg_3 column
            x_col: X-axis column
            y_col: Y-axis column (for reference)
            window: Window size for moving average

        Returns:
            Plotly trace dict
        """
        if 'moving_avg_3' not in data.columns:
            return {}

        return {
            "x": data[x_col].tolist(),
            "y": data['moving_avg_3'].tolist(),
            "name": f"{window}-Game Average",
            "mode": "lines",
            "line": {
                "width": 2,
                "dash": "dash",
                "color": "rgba(37, 99, 235, 0.5)"
            },
            "hovertemplate": (
                "<b>%{x}</b><br>"
                f"{window}-Game Avg: <b>%{{y:.1f}}</b>"
                "<extra></extra>"
            )
        }

    @staticmethod
    def add_peak_annotations(
        data: pd.DataFrame,
        x_col: str,
        y_col: str
    ) -> List[Dict[str, Any]]:
        """Generate annotations for peak and trough values"""
        annotations = []

        if y_col not in data.columns or len(data) < 3:
            return annotations

        y_data = data[y_col].dropna()
        if len(y_data) == 0:
            return annotations

        # Find max and min
        max_idx = y_data.idxmax()
        min_idx = y_data.idxmin()

        # Only annotate if there's meaningful variation
        if y_data.max() != y_data.min():
            # Convert to Python native types for JSON serialization
            max_x = data.loc[max_idx, x_col]
            max_y = float(data.loc[max_idx, y_col])
            min_x = data.loc[min_idx, x_col]
            min_y = float(data.loc[min_idx, y_col])

            # Convert x values to native types if they're numeric
            if isinstance(max_x, (int, float)):
                max_x = float(max_x)
            if isinstance(min_x, (int, float)):
                min_x = float(min_x)

            # Peak annotation
            annotations.append({
                "x": max_x,
                "y": max_y,
                "text": f"Best: {max_y:.1f}",
                "showarrow": True,
                "arrowhead": 2,
                "arrowsize": 1,
                "arrowwidth": 2,
                "arrowcolor": "#059669",
                "ax": 0,
                "ay": -40,
                "font": {"size": 10, "color": "#059669", "weight": 600},
                "bgcolor": "rgba(255, 255, 255, 0.9)",
                "bordercolor": "#059669",
                "borderwidth": 1,
                "borderpad": 4
            })

            # Trough annotation (only if different from peak)
            if max_idx != min_idx:
                annotations.append({
                    "x": min_x,
                    "y": min_y,
                    "text": f"Worst: {min_y:.1f}",
                    "showarrow": True,
                    "arrowhead": 2,
                    "arrowsize": 1,
                    "arrowwidth": 2,
                    "arrowcolor": "#dc2626",
                    "ax": 0,
                    "ay": 40,
                    "font": {"size": 10, "color": "#dc2626", "weight": 600},
                    "bgcolor": "rgba(255, 255, 255, 0.9)",
                    "bordercolor": "#dc2626",
                    "borderwidth": 1,
                    "borderpad": 4
                })

        return annotations
