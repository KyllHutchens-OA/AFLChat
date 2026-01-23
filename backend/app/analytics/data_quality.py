"""
AFL Analytics Agent - Data Quality Checker

Provides data quality assessment and confidence indicators for statistical analysis.
"""
from typing import Dict, Any, List
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataQualityChecker:
    """
    Assesses data quality and provides confidence indicators.

    Ensures users can trust the analysis by highlighting:
    - Sample size limitations
    - Missing or incomplete data
    - Confidence levels
    - Data quality warnings
    """

    # Sample size thresholds for different analysis types
    THRESHOLDS = {
        "min_sample_trend": 5,          # Minimum for trend analysis
        "min_sample_comparison": 10,    # Minimum for comparison
        "min_sample_ranking": 3,        # Minimum for ranking
        "high_confidence": 20,          # High confidence threshold
        "medium_confidence": 10,        # Medium confidence threshold
        "max_null_percent": 30,         # Maximum acceptable null percentage
        "min_data_completeness": 70     # Minimum data completeness percentage
    }

    @classmethod
    def assess_quality(
        cls,
        data: pd.DataFrame,
        analysis_type: str,
        params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Assess data quality for a given analysis type.

        Args:
            data: DataFrame to assess
            analysis_type: Type of analysis ("average", "trend", "comparison", "rank")
            params: Optional parameters for assessment

        Returns:
            Dictionary with quality assessment:
            - sample_size: int
            - confidence: "high" | "medium" | "low" | "none"
            - warnings: List[str]
            - can_proceed: bool
            - data_completeness: float (0-100)
            - null_percentages: Dict[str, float]
        """
        if params is None:
            params = {}

        sample_size = len(data)
        warnings = []
        can_proceed = True

        # Check minimum sample size based on analysis type
        min_threshold = cls._get_min_threshold(analysis_type)

        if sample_size < min_threshold:
            warnings.append(
                f"Sample size ({sample_size}) is below recommended minimum ({min_threshold}) "
                f"for {analysis_type} analysis"
            )
            if sample_size < 3:  # Absolute minimum
                can_proceed = False
                warnings.append("Insufficient data - cannot proceed with analysis")

        # Calculate confidence level
        confidence = cls._calculate_confidence(sample_size)

        # Check for null values
        null_percentages = {}
        numeric_cols = data.select_dtypes(include=['number']).columns.tolist()

        for col in numeric_cols:
            null_pct = (data[col].isnull().sum() / len(data) * 100) if len(data) > 0 else 0
            null_percentages[col] = round(null_pct, 2)

            if null_pct > cls.THRESHOLDS["max_null_percent"]:
                warnings.append(
                    f"High percentage of missing values in '{col}': {null_pct:.1f}%"
                )

        # Calculate overall data completeness
        if numeric_cols:
            avg_completeness = 100 - (sum(null_percentages.values()) / len(null_percentages))
            data_completeness = round(avg_completeness, 2)

            if data_completeness < cls.THRESHOLDS["min_data_completeness"]:
                warnings.append(
                    f"Low data completeness: {data_completeness:.1f}% "
                    f"(recommended: >{cls.THRESHOLDS['min_data_completeness']}%)"
                )
        else:
            data_completeness = 0
            warnings.append("No numeric columns found for quality assessment")

        # Check for temporal gaps (if date column exists)
        if 'season' in data.columns and len(data) > 1:
            seasons = sorted(data['season'].dropna().unique())
            if len(seasons) > 1:
                expected_seasons = list(range(min(seasons), max(seasons) + 1))
                missing_seasons = set(expected_seasons) - set(seasons)
                if missing_seasons:
                    warnings.append(
                        f"Missing data for seasons: {sorted(missing_seasons)}"
                    )

        # Analysis-specific checks
        if analysis_type == "comparison":
            warnings.extend(cls._check_comparison_quality(data, params))
        elif analysis_type == "trend":
            warnings.extend(cls._check_trend_quality(data, params))
        elif analysis_type == "rank":
            warnings.extend(cls._check_ranking_quality(data, params))

        return {
            "sample_size": sample_size,
            "confidence": confidence,
            "warnings": warnings,
            "can_proceed": can_proceed,
            "data_completeness": data_completeness,
            "null_percentages": null_percentages,
            "assessment": cls._generate_assessment_summary(
                sample_size, confidence, warnings, data_completeness
            )
        }

    @classmethod
    def _get_min_threshold(cls, analysis_type: str) -> int:
        """Get minimum sample size threshold for analysis type."""
        thresholds = {
            "trend": cls.THRESHOLDS["min_sample_trend"],
            "comparison": cls.THRESHOLDS["min_sample_comparison"],
            "rank": cls.THRESHOLDS["min_sample_ranking"],
            "average": 1  # Averages can work with single data point
        }
        return thresholds.get(analysis_type, 3)

    @classmethod
    def _calculate_confidence(cls, sample_size: int) -> str:
        """
        Calculate confidence level based on sample size.

        Args:
            sample_size: Number of data points

        Returns:
            Confidence level: "high", "medium", "low", or "none"
        """
        if sample_size >= cls.THRESHOLDS["high_confidence"]:
            return "high"
        elif sample_size >= cls.THRESHOLDS["medium_confidence"]:
            return "medium"
        elif sample_size >= 3:
            return "low"
        else:
            return "none"

    @classmethod
    def _check_comparison_quality(
        cls,
        data: pd.DataFrame,
        params: Dict[str, Any]
    ) -> List[str]:
        """Check data quality specific to comparison analysis."""
        warnings = []

        # Check if we have enough entities to compare
        group_col = params.get("group_col")
        if group_col and group_col in data.columns:
            unique_entities = data[group_col].nunique()
            if unique_entities < 2:
                warnings.append("Need at least 2 entities for comparison")

            # Check if each entity has sufficient data
            entity_counts = data[group_col].value_counts()
            small_samples = entity_counts[entity_counts < 5]
            if len(small_samples) > 0:
                warnings.append(
                    f"{len(small_samples)} entities have fewer than 5 data points, "
                    "which may affect comparison reliability"
                )

        return warnings

    @classmethod
    def _check_trend_quality(
        cls,
        data: pd.DataFrame,
        params: Dict[str, Any]
    ) -> List[str]:
        """Check data quality specific to trend analysis."""
        warnings = []

        # Check for temporal consistency
        if 'season' in data.columns:
            seasons = data['season'].dropna()
            if len(seasons) > 0:
                season_range = seasons.max() - seasons.min()
                data_points = len(seasons.unique())

                # Warn if data is sparse across time range
                if season_range > 0 and data_points / season_range < 0.5:
                    warnings.append(
                        f"Sparse data across {season_range} seasons "
                        f"({data_points} seasons with data) - trend may be unreliable"
                    )

        # Check for sufficient variance
        metric_col = params.get("metric_col")
        if metric_col and metric_col in data.columns:
            variance = data[metric_col].var()
            if variance == 0:
                warnings.append(
                    f"No variance in {metric_col} - all values are identical"
                )

        return warnings

    @classmethod
    def _check_ranking_quality(
        cls,
        data: pd.DataFrame,
        params: Dict[str, Any]
    ) -> List[str]:
        """Check data quality specific to ranking analysis."""
        warnings = []

        # Check for ties
        metric_col = params.get("metric_col")
        if metric_col and metric_col in data.columns:
            values = data[metric_col].dropna()
            if len(values) > 0:
                unique_values = values.nunique()
                if unique_values < len(values) * 0.5:
                    warnings.append(
                        f"Many tied values in {metric_col} - rankings may be less meaningful"
                    )

        return warnings

    @classmethod
    def _generate_assessment_summary(
        cls,
        sample_size: int,
        confidence: str,
        warnings: List[str],
        data_completeness: float
    ) -> str:
        """
        Generate human-readable quality assessment summary.

        Args:
            sample_size: Number of data points
            confidence: Confidence level
            warnings: List of warnings
            data_completeness: Data completeness percentage

        Returns:
            Natural language summary
        """
        parts = []

        # Confidence statement
        confidence_text = {
            "high": "High confidence",
            "medium": "Moderate confidence",
            "low": "Low confidence - interpret with caution",
            "none": "Insufficient data for reliable analysis"
        }
        parts.append(f"{confidence_text.get(confidence, 'Unknown confidence')}")

        # Sample size
        parts.append(f"based on {sample_size} data points")

        # Data completeness
        if data_completeness < 80:
            parts.append(f"with {data_completeness:.1f}% data completeness")

        # Warnings summary
        if warnings:
            parts.append(f"({len(warnings)} quality warnings)")

        return ", ".join(parts) + "."

    @classmethod
    def format_warnings_for_response(cls, warnings: List[str]) -> str:
        """
        Format warnings for inclusion in natural language responses.

        Args:
            warnings: List of warning messages

        Returns:
            Formatted warning text for user display
        """
        if not warnings:
            return ""

        if len(warnings) == 1:
            return f"⚠️ Note: {warnings[0]}"

        formatted = "⚠️ Data Quality Notes:\n"
        for i, warning in enumerate(warnings, 1):
            formatted += f"  {i}. {warning}\n"

        return formatted.strip()
