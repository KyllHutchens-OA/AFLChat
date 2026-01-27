"""
Layout Optimizer for Chart Visualizations

Calculates optimal layout parameters based on data characteristics to ensure:
- Readable axis labels without overlap
- Appropriate spacing and margins
- Data-aware scaling and sizing
"""
import pandas as pd
import math
from typing import Dict, Any, Optional


class LayoutOptimizer:
    """Optimizes chart layout based on data characteristics"""

    # Default configuration
    DEFAULT_MARGINS = {"l": 80, "r": 40, "t": 100, "b": 100}
    DEFAULT_HEIGHT = 450
    MIN_HEIGHT = 350
    MAX_HEIGHT = 800

    @staticmethod
    def optimize_layout(
        data: pd.DataFrame,
        chart_type: str,
        x_col: str,
        y_col: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Calculate optimal layout based on data characteristics

        Args:
            data: DataFrame containing chart data
            chart_type: Type of chart ('line', 'bar', 'scatter', etc.)
            x_col: X-axis column name
            y_col: Y-axis column name
            metadata: Optional metadata from DataPreprocessor

        Returns:
            Dict containing:
            - margin: Dynamic margins
            - height: Optimal chart height
            - xaxis: X-axis configuration
            - yaxis: Y-axis configuration
        """
        metadata = metadata or {}

        # Calculate each component
        margin = LayoutOptimizer._calculate_margins(data, x_col, y_col, chart_type)
        height = LayoutOptimizer._calculate_height(data, y_col, chart_type, metadata)
        xaxis_config = LayoutOptimizer._configure_xaxis(data, x_col, chart_type)
        yaxis_config = LayoutOptimizer._configure_yaxis(data, y_col, metadata)

        return {
            "margin": margin,
            "height": height,
            "xaxis": xaxis_config,
            "yaxis": yaxis_config
        }

    @staticmethod
    def _calculate_margins(
        data: pd.DataFrame,
        x_col: str,
        y_col: str,
        chart_type: str
    ) -> Dict[str, int]:
        """Calculate dynamic margins based on label lengths"""
        margins = LayoutOptimizer.DEFAULT_MARGINS.copy()

        # X-axis labels
        if x_col in data.columns:
            max_x_label_length = data[x_col].astype(str).str.len().max()

            # Increase bottom margin if labels are long or will be rotated
            if max_x_label_length > 10:
                # Labels will be rotated, need more bottom space
                margins["b"] = 100 + 40  # Extra 40px for rotation
            elif max_x_label_length > 6:
                margins["b"] = 100 + 20  # Moderate increase

        # Y-axis labels (based on max value digits)
        if y_col in data.columns:
            max_y_value = data[y_col].max()
            if not math.isnan(max_y_value):
                # Count digits in max value
                num_digits = len(str(int(max_y_value))) if max_y_value > 0 else 1

                # Add 20px per digit beyond 2
                if num_digits > 2:
                    margins["l"] = 60 + ((num_digits - 2) * 20)

        # Chart-specific adjustments
        if chart_type == "horizontal_bar":
            # Swap margins for horizontal orientation
            margins["l"], margins["b"] = margins["b"], margins["l"]

        return margins

    @staticmethod
    def _calculate_height(
        data: pd.DataFrame,
        y_col: str,
        chart_type: str,
        metadata: Dict
    ) -> int:
        """Calculate optimal chart height based on data and chart type"""
        base_height = LayoutOptimizer.DEFAULT_HEIGHT

        # Sparse data gets taller chart to emphasize variation
        if metadata.get("is_sparse", False):
            base_height = 550

        # Bar charts scale with number of categories
        if chart_type == "bar" or chart_type == "horizontal_bar":
            num_categories = len(data)
            if num_categories > 10:
                # Taller for many categories
                base_height = min(400 + (num_categories * 15), LayoutOptimizer.MAX_HEIGHT)

        # Scatter plots use square aspect ratio
        elif chart_type == "scatter":
            base_height = 500

        # Apply bounds
        return max(LayoutOptimizer.MIN_HEIGHT, min(base_height, LayoutOptimizer.MAX_HEIGHT))

    @staticmethod
    def _configure_xaxis(
        data: pd.DataFrame,
        x_col: str,
        chart_type: str
    ) -> Dict[str, Any]:
        """Configure X-axis parameters for optimal readability"""
        config = {
            "automargin": True,  # Let Plotly adjust margins automatically
        }

        if x_col not in data.columns:
            return config

        num_points = len(data[x_col].unique())
        max_label_length = data[x_col].astype(str).str.len().max()

        # Decide on tick rotation
        needs_rotation = num_points > 15 or max_label_length > 10

        if needs_rotation:
            config["tickangle"] = -45
            config["tickfont"] = {"size": 10}

        # Thin ticks if too many data points
        if num_points > 25:
            # Show approximately 15-20 ticks
            config["nticks"] = 20
        elif num_points > 15:
            config["nticks"] = 15

        return config

    @staticmethod
    def _configure_yaxis(
        data: pd.DataFrame,
        y_col: str,
        metadata: Dict
    ) -> Dict[str, Any]:
        """Configure Y-axis for optimal data display"""
        config = {}

        if y_col not in data.columns:
            return config

        # Get data range
        y_data = data[y_col].dropna()
        if len(y_data) == 0:
            return config

        min_val = y_data.min()
        max_val = y_data.max()
        data_range = max_val - min_val

        # For sparse data or small ranges, zoom in with custom range
        variance = y_data.var() if len(y_data) > 1 else 0
        mean_val = y_data.mean()

        # Check if data range is small relative to typical range
        is_small_range = data_range < 5 or (variance < mean_val / 3 if mean_val > 0 else False)

        if is_small_range and data_range > 0:
            # Add 10% padding above and below
            padding = data_range * 0.1

            # Start from 0 if min is close to 0
            range_min = 0 if min_val < data_range * 0.2 else min_val - padding
            range_max = max_val + padding

            config["range"] = [range_min, range_max]

            # Set tick spacing for readability
            if data_range < 5:
                config["dtick"] = 0.5 if data_range < 3 else 1
            elif data_range < 10:
                config["dtick"] = 1
            elif data_range < 50:
                config["dtick"] = 5

        return config

    @staticmethod
    def get_responsive_config(chart_type: str, num_points: int) -> Dict[str, Any]:
        """
        Get Plotly config object for responsive behavior

        Args:
            chart_type: Type of chart
            num_points: Number of data points

        Returns:
            Plotly config dict
        """
        return {
            "responsive": True,
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": [
                "pan2d",
                "lasso2d",
                "select2d",
                "zoomIn2d",
                "zoomOut2d",
                "autoScale2d"
            ],
            "toImageButtonOptions": {
                "format": "png",
                "filename": f"afl_chart_{chart_type}",
                "scale": 2  # Higher resolution export
            }
        }
