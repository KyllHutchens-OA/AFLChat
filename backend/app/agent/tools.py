"""
AFL Analytics Agent - Tools

Tools that the LangGraph agent can use to accomplish tasks.
"""
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from sqlalchemy import text
from decimal import Decimal
import logging
from scipy import stats as scipy_stats

from app.data.database import Session
from app.analytics.validators import SQLValidator
from app.analytics.data_quality import DataQualityChecker

logger = logging.getLogger(__name__)


class DatabaseTool:
    """
    Tool for querying the AFL database.

    Security: All SQL queries are validated before execution to prevent injection.
    """

    @staticmethod
    def query_database(sql: str) -> Dict[str, Any]:
        """
        Execute a validated SQL query and return results.

        Args:
            sql: SQL query string

        Returns:
            Dictionary with:
            - success: bool
            - data: DataFrame (if successful)
            - error: str (if failed)
            - rows_returned: int
        """
        try:
            logger.info(f"DatabaseTool.query_database called with SQL length={len(sql)}")
            logger.info(f"SQL preview: {sql[:300]}...")

            # Validate SQL
            is_valid, error_message = SQLValidator.validate(sql)
            logger.info(f"SQL validation result: is_valid={is_valid}, error={error_message}")

            if not is_valid:
                logger.warning(f"SQL validation failed: {error_message}")
                return {
                    "success": False,
                    "error": f"Query validation failed: {error_message}",
                    "data": None,
                    "rows_returned": 0
                }

            # Execute query
            logger.info("DatabaseTool: Creating database session...")
            session = Session()
            logger.info("DatabaseTool: Session created, executing query...")

            try:
                result = session.execute(text(sql))
                logger.info("DatabaseTool: Query executed, fetching results...")
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                logger.info(f"DatabaseTool: Results fetched, {len(df)} rows")

                # Convert Decimal types to float for JSON serialization
                if len(df) > 0:
                    for col in df.columns:
                        if df[col].dtype == 'object':
                            # Check if column contains Decimal objects
                            first_non_null = df[col].dropna().head(1)
                            if len(first_non_null) > 0 and isinstance(first_non_null.iloc[0], Decimal):
                                df[col] = df[col].apply(lambda x: float(x) if isinstance(x, Decimal) else x)

                logger.info(f"Query executed successfully: {len(df)} rows returned")

                return {
                    "success": True,
                    "data": df,
                    "error": None,
                    "rows_returned": len(df)
                }

            finally:
                session.close()

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"Database query error ({error_type}): {error_msg}\n{tb}")

            # Check for common database errors
            if "connection" in error_msg.lower() or "connect" in error_msg.lower():
                error_msg = f"Database connection error: {error_msg}"
            elif "timeout" in error_msg.lower():
                error_msg = f"Database timeout: {error_msg}"
            elif "permission" in error_msg.lower() or "denied" in error_msg.lower():
                error_msg = f"Database permission denied: {error_msg}"
            elif "ssl" in error_msg.lower():
                error_msg = f"Database SSL error: {error_msg}"
            else:
                error_msg = f"Database error ({error_type}): {error_msg}"

            return {
                "success": False,
                "error": error_msg,
                "data": None,
                "rows_returned": 0
            }


class StatisticsTool:
    """
    Tool for computing statistics on data.

    Supports: averages, trends, comparisons, rankings.
    """

    @staticmethod
    def compute_statistics(
        data: pd.DataFrame,
        analysis_type: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compute statistics on the provided data.

        Args:
            data: Pandas DataFrame
            analysis_type: Type of analysis ("average", "trend", "comparison", "rank")
            params: Optional parameters for the analysis

        Returns:
            Dictionary with computed statistics
        """
        if params is None:
            params = {}

        try:
            if analysis_type == "average":
                return StatisticsTool._compute_averages(data, params)

            elif analysis_type == "trend":
                return StatisticsTool._compute_trends(data, params)

            elif analysis_type == "comparison":
                return StatisticsTool._compute_comparison(data, params)

            elif analysis_type == "rank":
                return StatisticsTool._compute_rankings(data, params)

            else:
                return {
                    "success": False,
                    "error": f"Unknown analysis type: {analysis_type}"
                }

        except Exception as e:
            logger.error(f"Statistics computation error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def _compute_averages(data: pd.DataFrame, params: Dict) -> Dict[str, Any]:
        """Compute averages for specified columns."""
        numeric_cols = data.select_dtypes(include=['number']).columns.tolist()

        averages = {}
        for col in numeric_cols:
            averages[col] = {
                "mean": float(data[col].mean()),
                "median": float(data[col].median()),
                "std": float(data[col].std()),
                "min": float(data[col].min()),
                "max": float(data[col].max())
            }

        return {
            "success": True,
            "averages": averages,
            "row_count": len(data)
        }

    @staticmethod
    def _compute_trends(data: pd.DataFrame, params: Dict) -> Dict[str, Any]:
        """
        Compute comprehensive trend analysis.

        Features:
        - Direction (improving/declining/stable) using linear regression
        - Percent change (overall and recent)
        - Best/worst periods identification
        - Rolling averages (3, 5, 10 game windows)
        - Momentum indicators (recent vs historical)
        - Volatility (coefficient of variation)
        - Confidence level based on sample size

        Args:
            data: DataFrame with time-series data
            params: Optional parameters (metric_col, time_col, recent_window)

        Returns:
            Dictionary with trend analysis
        """
        # Assess data quality first
        quality = DataQualityChecker.assess_quality(data, "trend", params)

        if not quality["can_proceed"]:
            return {
                "success": False,
                "error": quality["warnings"][0] if quality["warnings"] else "Insufficient data",
                "confidence": quality["confidence"],
                "sample_size": quality["sample_size"],
                "data_quality": quality
            }

        # Identify numeric columns for analysis
        numeric_cols = data.select_dtypes(include=['number']).columns.tolist()

        if not numeric_cols:
            return {
                "success": False,
                "error": "No numeric columns found for trend analysis"
            }

        # Get parameters
        metric_col = params.get("metric_col", numeric_cols[0])
        recent_window = params.get("recent_window", 5)

        if metric_col not in numeric_cols:
            metric_col = numeric_cols[0]

        # Extract series for analysis
        series = data[metric_col].dropna()

        if len(series) < 3:
            return {
                "success": False,
                "error": f"Insufficient non-null data for {metric_col}",
                "confidence": "none"
            }

        # Calculate all trend metrics
        direction_info = StatisticsTool._calculate_direction(series)
        momentum_info = StatisticsTool._calculate_momentum(series, recent_window)
        rolling_info = StatisticsTool._calculate_rolling_averages(series)
        periods_info = StatisticsTool._identify_best_worst_periods(data, metric_col)
        volatility_info = StatisticsTool._calculate_volatility(series)
        confidence = StatisticsTool._assess_confidence(len(series))

        # Overall percent change
        first_value = series.iloc[0]
        last_value = series.iloc[-1]
        overall_change = ((last_value - first_value) / first_value * 100) if first_value != 0 else 0

        # Recent percent change (last N vs previous N)
        recent_change = 0
        if len(series) >= recent_window * 2:
            recent_avg = series.iloc[-recent_window:].mean()
            previous_avg = series.iloc[-recent_window*2:-recent_window].mean()
            recent_change = ((recent_avg - previous_avg) / previous_avg * 100) if previous_avg != 0 else 0

        return {
            "success": True,
            "metric": metric_col,
            "sample_size": len(series),
            "confidence": confidence,
            "direction": direction_info,
            "change": {
                "overall_percent": round(overall_change, 2),
                "recent_percent": round(recent_change, 2) if len(series) >= recent_window * 2 else None,
                "absolute_change": round(last_value - first_value, 2)
            },
            "momentum": momentum_info,
            "rolling_averages": rolling_info,
            "periods": periods_info,
            "volatility": volatility_info,
            "data_quality": quality,
            "summary": StatisticsTool._generate_trend_summary(
                direction_info, momentum_info, overall_change, confidence
            )
        }

    @staticmethod
    def _calculate_direction(series: pd.Series) -> Dict[str, Any]:
        """
        Calculate trend direction using linear regression.

        Returns:
            Direction classification and slope details
        """
        x = np.arange(len(series))
        y = series.values

        # Linear regression
        slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, y)

        # Classify direction
        # Use p-value and slope to determine significance
        is_significant = p_value < 0.05
        slope_threshold = abs(series.mean() * 0.01)  # 1% of mean per data point

        if not is_significant or abs(slope) < slope_threshold:
            direction = "stable"
        elif slope > 0:
            direction = "improving"
        else:
            direction = "declining"

        return {
            "classification": direction,
            "slope": round(slope, 4),
            "r_squared": round(r_value ** 2, 4),
            "p_value": round(p_value, 4),
            "is_significant": is_significant
        }

    @staticmethod
    def _calculate_momentum(series: pd.Series, window: int = 5) -> Dict[str, Any]:
        """
        Calculate momentum indicators comparing recent performance to historical.

        Args:
            series: Time series data
            window: Window size for recent period (default 5)

        Returns:
            Momentum classification and metrics
        """
        if len(series) < window:
            return {
                "classification": "unknown",
                "recent_avg": None,
                "historical_avg": None,
                "difference_percent": None
            }

        recent_avg = series.iloc[-window:].mean()
        historical_avg = series.mean()

        diff_percent = ((recent_avg - historical_avg) / historical_avg * 100) if historical_avg != 0 else 0

        # Classify momentum
        if abs(diff_percent) < 5:
            classification = "neutral"
        elif diff_percent > 0:
            classification = "hot"
        else:
            classification = "cold"

        return {
            "classification": classification,
            "recent_avg": round(recent_avg, 2),
            "historical_avg": round(historical_avg, 2),
            "difference_percent": round(diff_percent, 2),
            "recent_window": window
        }

    @staticmethod
    def _calculate_rolling_averages(series: pd.Series) -> Dict[str, Any]:
        """
        Calculate rolling averages for multiple window sizes.

        Args:
            series: Time series data

        Returns:
            Rolling averages for 3, 5, 10 game windows
        """
        rolling_avgs = {}

        for window in [3, 5, 10]:
            if len(series) >= window:
                rolling = series.rolling(window=window).mean()
                rolling_avgs[f"window_{window}"] = {
                    "current": round(rolling.iloc[-1], 2) if not pd.isna(rolling.iloc[-1]) else None,
                    "min": round(rolling.min(), 2) if not rolling.isna().all() else None,
                    "max": round(rolling.max(), 2) if not rolling.isna().all() else None
                }

        return rolling_avgs

    @staticmethod
    def _identify_best_worst_periods(data: pd.DataFrame, metric_col: str) -> Dict[str, Any]:
        """
        Identify best and worst performing periods.

        Args:
            data: Full DataFrame (may contain time indicators)
            metric_col: Metric column to analyze

        Returns:
            Best and worst periods with context
        """
        series = data[metric_col].dropna()

        if len(series) == 0:
            return {}

        best_idx = series.idxmax()
        worst_idx = series.idxmin()

        # Try to get contextual information (season, round, etc.)
        best_context = {}
        worst_context = {}

        for col in ['season', 'round', 'match_date', 'opponent']:
            if col in data.columns:
                best_context[col] = str(data.loc[best_idx, col])
                worst_context[col] = str(data.loc[worst_idx, col])

        return {
            "best": {
                "value": round(series.max(), 2),
                "index": int(best_idx),
                "context": best_context
            },
            "worst": {
                "value": round(series.min(), 2),
                "index": int(worst_idx),
                "context": worst_context
            }
        }

    @staticmethod
    def _calculate_volatility(series: pd.Series) -> Dict[str, Any]:
        """
        Calculate volatility metrics.

        Args:
            series: Time series data

        Returns:
            Coefficient of variation and consistency classification
        """
        mean = series.mean()
        std = series.std()

        # Coefficient of variation (CV)
        cv = (std / mean * 100) if mean != 0 else 0

        # Classify consistency
        if cv < 10:
            consistency = "very_consistent"
        elif cv < 20:
            consistency = "consistent"
        elif cv < 30:
            consistency = "moderate"
        else:
            consistency = "inconsistent"

        return {
            "coefficient_of_variation": round(cv, 2),
            "standard_deviation": round(std, 2),
            "consistency": consistency
        }

    @staticmethod
    def _assess_confidence(sample_size: int) -> str:
        """
        Assess confidence level based on sample size.

        Args:
            sample_size: Number of data points

        Returns:
            Confidence level: high, medium, or low
        """
        if sample_size >= 20:
            return "high"
        elif sample_size >= 10:
            return "medium"
        else:
            return "low"

    @staticmethod
    def _generate_trend_summary(
        direction_info: Dict,
        momentum_info: Dict,
        overall_change: float,
        confidence: str
    ) -> str:
        """
        Generate human-readable trend summary.

        Args:
            direction_info: Direction analysis results
            momentum_info: Momentum analysis results
            overall_change: Overall percent change
            confidence: Confidence level

        Returns:
            Natural language summary
        """
        direction = direction_info["classification"]
        momentum = momentum_info["classification"]

        summary_parts = []

        # Direction
        if direction == "improving":
            summary_parts.append(f"Trending upward (+{abs(overall_change):.1f}%)")
        elif direction == "declining":
            summary_parts.append(f"Trending downward (-{abs(overall_change):.1f}%)")
        else:
            summary_parts.append("Relatively stable")

        # Momentum
        if momentum == "hot":
            summary_parts.append("recent momentum is positive")
        elif momentum == "cold":
            summary_parts.append("recent momentum is negative")
        else:
            summary_parts.append("recent form is steady")

        # Confidence
        summary_parts.append(f"({confidence} confidence)")

        return ", ".join(summary_parts)

    @staticmethod
    def _compute_comparison(data: pd.DataFrame, params: Dict) -> Dict[str, Any]:
        """
        Compare entities (players, teams) across metrics.

        Features:
        - Head-to-head metrics across all numeric columns
        - Leader/laggard identification per metric
        - Absolute and percentage differences
        - Statistical significance (t-test p-values)
        - Sample sizes and confidence indicators

        Args:
            data: DataFrame with entities to compare
            params: Optional parameters (group_col to identify entities)

        Returns:
            Dictionary with comparison analysis
        """
        # Identify group column (first non-numeric column, or specified)
        non_numeric_cols = data.select_dtypes(exclude=['number']).columns.tolist()
        numeric_cols = data.select_dtypes(include=['number']).columns.tolist()

        if not numeric_cols:
            return {
                "success": False,
                "error": "No numeric columns found for comparison"
            }

        group_col = params.get("group_col")

        # Auto-detect group column if not specified
        if not group_col:
            for col in ['name', 'team', 'player', 'team_name', 'player_name']:
                if col in non_numeric_cols:
                    group_col = col
                    break

            # Fallback to first non-numeric column
            if not group_col and non_numeric_cols:
                group_col = non_numeric_cols[0]

        if not group_col or group_col not in data.columns:
            return {
                "success": False,
                "error": "Could not identify group column for comparison"
            }

        # Get unique entities
        entities = data[group_col].unique()

        if len(entities) < 2:
            return {
                "success": False,
                "error": "Need at least 2 entities to compare"
            }

        # Assess data quality
        params["group_col"] = group_col  # Ensure group_col is in params for quality check
        quality = DataQualityChecker.assess_quality(data, "comparison", params)

        if not quality["can_proceed"]:
            return {
                "success": False,
                "error": quality["warnings"][0] if quality["warnings"] else "Insufficient data",
                "confidence": quality["confidence"],
                "sample_size": quality["sample_size"],
                "data_quality": quality
            }

        # Perform pairwise comparisons
        comparisons = {}

        for metric in numeric_cols:
            metric_comparison = StatisticsTool._compare_metric(
                data, group_col, metric, entities
            )
            comparisons[metric] = metric_comparison

        # Identify overall leaders and laggards
        leaders = {}
        laggards = {}

        for metric, comp in comparisons.items():
            if comp.get("leader"):
                leaders[metric] = comp["leader"]
            if comp.get("laggard"):
                laggards[metric] = comp["laggard"]

        # Generate summary
        summary = StatisticsTool._generate_comparison_summary(
            entities, comparisons, leaders, laggards
        )

        return {
            "success": True,
            "group_column": group_col,
            "entities": list(entities),
            "entity_count": len(entities),
            "metrics_compared": len(numeric_cols),
            "comparisons": comparisons,
            "leaders": leaders,
            "laggards": laggards,
            "data_quality": quality,
            "summary": summary
        }

    @staticmethod
    def _compare_metric(
        data: pd.DataFrame,
        group_col: str,
        metric: str,
        entities: np.ndarray
    ) -> Dict[str, Any]:
        """
        Compare a single metric across entities.

        Args:
            data: Full DataFrame
            group_col: Column containing entity identifiers
            metric: Metric column to compare
            entities: Array of unique entities

        Returns:
            Comparison results for this metric
        """
        # Calculate stats for each entity
        entity_stats = {}

        for entity in entities:
            entity_data = data[data[group_col] == entity][metric].dropna()

            if len(entity_data) > 0:
                entity_stats[str(entity)] = {
                    "mean": float(entity_data.mean()),
                    "median": float(entity_data.median()),
                    "std": float(entity_data.std()) if len(entity_data) > 1 else 0,
                    "sample_size": len(entity_data),
                    "data": entity_data.values
                }

        if len(entity_stats) < 2:
            return {"error": "Insufficient data for comparison"}

        # Identify leader and laggard
        means = {entity: stats["mean"] for entity, stats in entity_stats.items()}
        leader = max(means, key=means.get)
        laggard = min(means, key=means.get)

        leader_mean = means[leader]
        laggard_mean = means[laggard]

        # Calculate differences
        absolute_diff = leader_mean - laggard_mean
        percent_diff = (absolute_diff / laggard_mean * 100) if laggard_mean != 0 else 0

        # Statistical significance (t-test) if we have 2 entities
        significance = None
        if len(entity_stats) == 2:
            entity_list = list(entity_stats.keys())
            group1 = entity_stats[entity_list[0]]["data"]
            group2 = entity_stats[entity_list[1]]["data"]

            if len(group1) >= 2 and len(group2) >= 2:
                t_stat, p_value = scipy_stats.ttest_ind(group1, group2)

                significance = {
                    "p_value": round(p_value, 4),
                    "is_significant": p_value < 0.05,
                    "significance_level": "high" if p_value < 0.01 else "moderate" if p_value < 0.05 else "low",
                    "interpretation": StatisticsTool._interpret_significance(p_value)
                }

        # Pairwise differences (for all pairs if >2 entities)
        pairwise = []
        entity_list = list(entity_stats.keys())

        for i, entity1 in enumerate(entity_list):
            for entity2 in entity_list[i+1:]:
                diff = entity_stats[entity1]["mean"] - entity_stats[entity2]["mean"]
                pct = (diff / entity_stats[entity2]["mean"] * 100) if entity_stats[entity2]["mean"] != 0 else 0

                pairwise.append({
                    "entity1": entity1,
                    "entity2": entity2,
                    "difference": round(diff, 2),
                    "percent_difference": round(pct, 2)
                })

        return {
            "entity_stats": {k: {key: val for key, val in v.items() if key != "data"}
                           for k, v in entity_stats.items()},
            "leader": {
                "entity": leader,
                "value": round(leader_mean, 2)
            },
            "laggard": {
                "entity": laggard,
                "value": round(laggard_mean, 2)
            },
            "difference": {
                "absolute": round(absolute_diff, 2),
                "percent": round(percent_diff, 2)
            },
            "significance": significance,
            "pairwise": pairwise
        }

    @staticmethod
    def _interpret_significance(p_value: float) -> str:
        """
        Interpret p-value for statistical significance.

        Args:
            p_value: P-value from statistical test

        Returns:
            Human-readable interpretation
        """
        if p_value < 0.01:
            return "Highly significant - very strong evidence of difference"
        elif p_value < 0.05:
            return "Significant - strong evidence of difference"
        elif p_value < 0.10:
            return "Marginally significant - moderate evidence of difference"
        else:
            return "Not significant - difference may be due to chance"

    @staticmethod
    def _generate_comparison_summary(
        entities: np.ndarray,
        comparisons: Dict,
        leaders: Dict,
        laggards: Dict
    ) -> str:
        """
        Generate human-readable comparison summary.

        Args:
            entities: Array of entities being compared
            comparisons: Full comparison results
            leaders: Leader entities per metric
            laggards: Laggard entities per metric

        Returns:
            Natural language summary
        """
        entity_list = ", ".join([str(e) for e in entities[:3]])
        if len(entities) > 3:
            entity_list += f" (+{len(entities) - 3} more)"

        summary_parts = [
            f"Comparing {len(entities)} entities: {entity_list}",
            f"Analyzed {len(comparisons)} metrics"
        ]

        # Count wins per entity
        wins = {}
        for entity in entities:
            entity_str = str(entity)
            wins[entity_str] = sum(1 for leader in leaders.values() if leader["entity"] == entity_str)

        if wins:
            top_performer = max(wins, key=wins.get)
            summary_parts.append(f"Top performer: {top_performer} (leads in {wins[top_performer]} metrics)")

        return "; ".join(summary_parts)

    @staticmethod
    def _compute_rankings(data: pd.DataFrame, params: Dict) -> Dict[str, Any]:
        """
        Rank entities by specified metric.

        Features:
        - Sorted rankings by metric
        - Percentile calculations
        - Gap analysis (to leader, to next)
        - Top 3 and bottom 3 identification

        Args:
            data: DataFrame with entities to rank
            params: Optional parameters (metric_col, group_col, ascending)

        Returns:
            Dictionary with ranking analysis
        """
        # Identify columns
        numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
        non_numeric_cols = data.select_dtypes(exclude=['number']).columns.tolist()

        if not numeric_cols:
            return {
                "success": False,
                "error": "No numeric columns found for ranking"
            }

        # Get parameters
        metric_col = params.get("metric_col", numeric_cols[0])
        ascending = params.get("ascending", False)  # Default: higher is better

        # Auto-detect group column
        group_col = params.get("group_col")

        if not group_col:
            for col in ['name', 'team', 'player', 'team_name', 'player_name']:
                if col in non_numeric_cols:
                    group_col = col
                    break

            if not group_col and non_numeric_cols:
                group_col = non_numeric_cols[0]

        # If we have a group column, aggregate by group first
        if group_col and group_col in data.columns:
            # Group and aggregate (use mean)
            grouped = data.groupby(group_col)[metric_col].agg(['mean', 'count']).reset_index()
            grouped.columns = [group_col, metric_col, 'sample_size']
            rank_data = grouped
            entity_col = group_col
        else:
            # Rank individual rows
            rank_data = data[[metric_col]].copy()
            rank_data['entity'] = range(len(rank_data))
            rank_data['sample_size'] = 1
            entity_col = 'entity'

        # Remove null values
        rank_data = rank_data.dropna(subset=[metric_col])

        if len(rank_data) == 0:
            return {
                "success": False,
                "error": f"No valid data for ranking by {metric_col}"
            }

        # Assess data quality
        params["metric_col"] = metric_col
        quality = DataQualityChecker.assess_quality(rank_data, "rank", params)

        if not quality["can_proceed"]:
            return {
                "success": False,
                "error": quality["warnings"][0] if quality["warnings"] else "Insufficient data",
                "confidence": quality["confidence"],
                "sample_size": quality["sample_size"],
                "data_quality": quality
            }

        # Sort and rank
        rank_data = rank_data.sort_values(metric_col, ascending=ascending).reset_index(drop=True)
        rank_data['rank'] = range(1, len(rank_data) + 1)

        # Calculate percentiles
        rank_data['percentile'] = rank_data[metric_col].rank(pct=True) * 100

        # Calculate gaps
        gaps = []
        for i in range(len(rank_data)):
            gap_to_leader = None
            gap_to_next = None
            gap_to_prev = None

            if i > 0:
                if ascending:
                    gap_to_leader = rank_data.iloc[i][metric_col] - rank_data.iloc[0][metric_col]
                    gap_to_prev = rank_data.iloc[i][metric_col] - rank_data.iloc[i-1][metric_col]
                else:
                    gap_to_leader = rank_data.iloc[0][metric_col] - rank_data.iloc[i][metric_col]
                    gap_to_prev = rank_data.iloc[i-1][metric_col] - rank_data.iloc[i][metric_col]

            if i < len(rank_data) - 1:
                if ascending:
                    gap_to_next = rank_data.iloc[i+1][metric_col] - rank_data.iloc[i][metric_col]
                else:
                    gap_to_next = rank_data.iloc[i][metric_col] - rank_data.iloc[i+1][metric_col]

            gaps.append({
                "to_leader": round(gap_to_leader, 2) if gap_to_leader is not None else None,
                "to_next": round(gap_to_next, 2) if gap_to_next is not None else None,
                "to_prev": round(gap_to_prev, 2) if gap_to_prev is not None else None
            })

        # Build rankings list
        rankings = []
        for i, row in rank_data.iterrows():
            rankings.append({
                "rank": int(row['rank']),
                "entity": str(row[entity_col]),
                "value": round(row[metric_col], 2),
                "percentile": round(row['percentile'], 1),
                "sample_size": int(row['sample_size']),
                "gaps": gaps[i]
            })

        # Identify top 3 and bottom 3
        top_3 = rankings[:min(3, len(rankings))]
        bottom_3 = rankings[-min(3, len(rankings)):][::-1]  # Reverse for ascending order

        # Statistics
        values = rank_data[metric_col].values
        stats = {
            "mean": round(float(np.mean(values)), 2),
            "median": round(float(np.median(values)), 2),
            "std": round(float(np.std(values)), 2),
            "min": round(float(np.min(values)), 2),
            "max": round(float(np.max(values)), 2),
            "range": round(float(np.max(values) - np.min(values)), 2)
        }

        # Generate summary
        summary = StatisticsTool._generate_rankings_summary(
            metric_col, rankings, top_3, bottom_3, ascending
        )

        return {
            "success": True,
            "metric": metric_col,
            "entity_column": entity_col,
            "total_entities": len(rankings),
            "ascending": ascending,
            "rankings": rankings,
            "top_3": top_3,
            "bottom_3": bottom_3,
            "statistics": stats,
            "data_quality": quality,
            "summary": summary
        }

    @staticmethod
    def _generate_rankings_summary(
        metric: str,
        rankings: list,
        top_3: list,
        bottom_3: list,
        ascending: bool
    ) -> str:
        """
        Generate human-readable rankings summary.

        Args:
            metric: Metric being ranked
            rankings: Full rankings list
            top_3: Top 3 entities
            bottom_3: Bottom 3 entities
            ascending: Whether lower is better

        Returns:
            Natural language summary
        """
        direction = "lowest" if ascending else "highest"
        leader = top_3[0] if top_3 else None

        if not leader:
            return f"No entities to rank by {metric}"

        summary_parts = [
            f"Ranked {len(rankings)} entities by {metric}",
            f"{direction}: {leader['entity']} ({leader['value']})"
        ]

        # Gap to second place
        if len(top_3) > 1:
            gap = abs(top_3[0]['value'] - top_3[1]['value'])
            summary_parts.append(f"leads by {gap:.2f}")

        return "; ".join(summary_parts)
