"""
Layout Config for Recharts Visualizations

Simplified layout configuration — Recharts handles responsive sizing via <ResponsiveContainer>.
This module only outputs axis config hints (tick rotation, y-axis domain, integer ticks).
"""
import pandas as pd
import math
from typing import Dict, Any, Optional


class LayoutConfig:
    """Calculates axis configuration hints for Recharts charts."""

    @staticmethod
    def calculate(
        data: pd.DataFrame,
        chart_type: str,
        x_col: str,
        y_col: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Calculate axis configuration based on data characteristics.

        Returns:
            Dict with xaxis and yaxis config hints.
        """
        metadata = metadata or {}

        xaxis_config = LayoutConfig._configure_xaxis(data, x_col)
        yaxis_config = LayoutConfig._configure_yaxis(data, y_col, metadata)

        return {
            "xaxis": xaxis_config,
            "yaxis": yaxis_config,
        }

    @staticmethod
    def _configure_xaxis(data: pd.DataFrame, x_col: str) -> Dict[str, Any]:
        """Configure X-axis: tick rotation when labels are long or numerous."""
        config = {}

        if x_col not in data.columns:
            return config

        num_points = data[x_col].nunique()
        max_label_length = data[x_col].astype(str).str.len().max()

        if num_points > 15 or max_label_length > 10:
            config["tickangle"] = -45

        return config

    @staticmethod
    def _configure_yaxis(
        data: pd.DataFrame,
        y_col: str,
        metadata: Dict
    ) -> Dict[str, Any]:
        """Configure Y-axis: domain zoom and integer ticks."""
        config = {}

        if y_col not in data.columns:
            return config

        y_data = data[y_col].dropna()
        if len(y_data) == 0:
            return config

        min_val = y_data.min()
        max_val = y_data.max()
        data_range = max_val - min_val
        is_count = metadata.get("is_count_metric", False)

        # Count metrics: always start at 0, integer ticks
        if is_count:
            padding = max(1, max_val * 0.2)
            config["range"] = [0.0, float(max_val + padding)]
            config["dtick"] = 1
            return config

        # Continuous metrics: zoom for small ranges
        variance = y_data.var() if len(y_data) > 1 else 0
        mean_val = y_data.mean()
        is_small_range = data_range < 5 or (variance < mean_val / 3 if mean_val > 0 else False)

        if is_small_range and data_range > 0:
            padding = data_range * 0.1
            range_min = 0 if min_val < data_range * 0.2 else float(min_val - padding)
            range_max = float(max_val + padding)
            config["range"] = [float(range_min), float(range_max)]

        return config
