"""
AFL Analytics Agent - Intelligent Chart Selector

Uses LLM to intelligently select optimal chart type, columns, and configuration
based on user query and data characteristics.
"""
from typing import Dict, Any, Optional, List
import pandas as pd
import logging
import json
from openai import OpenAI
import os

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class ChartSelector:
    """
    Intelligently selects chart type and configuration using LLM + heuristics.

    Decision flow:
    1. Quick heuristics check for obvious cases (single value, empty data)
    2. LLM analysis for complex/ambiguous cases
    3. Validation and fallback to sensible defaults
    """

    # Chart type descriptions for LLM
    CHART_TYPES = {
        "line": "Shows trends over time or sequential data. Best for temporal analysis.",
        "bar": "Compares values across categories. Best for rankings, top N, or category comparison.",
        "horizontal_bar": "Like bar but horizontal. Best for long category names or rankings.",
        "grouped_bar": "Compares multiple metrics across categories side-by-side.",
        "stacked_bar": "Shows composition/parts of a whole across categories.",
        "scatter": "Shows relationship/correlation between two numeric variables.",
        "pie": "Shows proportions of a whole. Best for 3-7 categories only.",
        "box": "Shows distribution and outliers. Best for statistical analysis.",
    }

    @classmethod
    def select_chart_configuration(
        cls,
        user_query: str,
        data: pd.DataFrame,
        intent: str,
        entities: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Intelligently select optimal chart configuration.

        Args:
            user_query: Original user question
            data: Query results DataFrame
            intent: Classified intent (TREND_ANALYSIS, etc.)
            entities: Extracted entities (teams, metrics, etc.)
            **kwargs: Optional llm_chart_type_hint, llm_chart_config_hint

        Returns:
            Dictionary with:
            - chart_type: str
            - x_col: str
            - y_col: str or List[str]
            - group_col: Optional[str]
            - reasoning: str (why this chart was chosen)
        """
        try:
            # Quick heuristics for obvious cases (covers ~90% of queries)
            quick_result = cls._quick_heuristics(data, intent, entities, user_query)
            if quick_result:
                logger.info(f"Chart selection via quick heuristics: {quick_result['chart_type']}")
                return quick_result

            # Check if consolidated LLM provided a chart type hint
            llm_hint = kwargs.get("llm_chart_type_hint")
            hint_config = kwargs.get("llm_chart_config_hint", {})
            if llm_hint:
                validated_hint = cls._validate_llm_hint(llm_hint, hint_config, data)
                if validated_hint:
                    logger.info(f"Chart selection via consolidated LLM hint: {validated_hint['chart_type']}")
                    return validated_hint

            # Use LLM for intelligent selection (rare fallback)
            llm_result = cls._llm_chart_selection(user_query, data, intent, entities)

            if llm_result:
                validated = cls._validate_and_enhance(llm_result, data)
                logger.info(f"Chart selection via LLM: {validated['chart_type']}")
                return validated

            logger.warning("LLM chart selection failed, using fallback")
            return cls._fallback_selection(data, intent)

        except Exception as e:
            logger.error(f"Error in chart selection: {e}")
            return cls._fallback_selection(data, intent)

    @classmethod
    def _quick_heuristics(
        cls,
        data: pd.DataFrame,
        intent: str,
        entities: Dict[str, Any] = None,
        user_query: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Quick heuristics for obvious cases to avoid LLM call.

        Handles ~90% of AFL chart queries based on intent + data shape.
        Returns None only for genuinely ambiguous cases.
        """
        if len(data) <= 1:
            return None

        numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
        # Filter out ID and temporal-identifier columns from numeric
        numeric_cols = [c for c in numeric_cols if 'id' not in c.lower() and c not in ('season', 'year')]
        non_numeric = data.select_dtypes(exclude=['number']).columns.tolist()
        temporal_cols = [col for col in data.columns if col in ['season', 'year', 'match_date', 'round']]
        intent_upper = str(intent).upper() if intent else ""

        # Helper: detect grouping column (non-numeric, non-temporal, with >1 unique value)
        # Excludes team columns — SQL often JOINs home_team/away_team as context, not as chart dimension
        TEAM_COLS = {'home_team', 'away_team', 'team', 'team_name', 'opponent'}
        def _find_group_col():
            candidates = [c for c in non_numeric
                          if c not in ['season', 'year', 'match_date', 'round']
                          and c.lower() not in TEAM_COLS]
            for c in candidates:
                if 1 < data[c].nunique() <= 20:
                    return c
            return None

        # Rule 1: Single numeric + single temporal -> line chart (existing)
        if len(numeric_cols) == 1 and len(temporal_cols) == 1:
            return {
                "chart_type": "line",
                "x_col": temporal_cols[0],
                "y_col": numeric_cols[0],
                "group_col": _find_group_col(),
                "reasoning": "Single metric over time - line chart",
                "confidence": "high"
            }

        # Rule 2: 2-5 rows, no temporal -> bar chart (existing, extended to 20)
        if 2 <= len(data) <= 20 and not temporal_cols and non_numeric and numeric_cols:
            return {
                "chart_type": "bar",
                "x_col": non_numeric[0],
                "y_col": numeric_cols[0],
                "group_col": None,
                "reasoning": "Category comparison - bar chart",
                "confidence": "high"
            }

        # Rule 3: TREND_ANALYSIS -> always line chart
        if "TREND" in intent_upper:
            # Prefer round for per-match data (single season), season for multi-year
            has_round = 'round' in data.columns
            has_season = 'season' in data.columns
            season_count = data['season'].nunique() if has_season else 0

            if has_round and season_count <= 1:
                temporal_col = 'round'
            elif has_season and season_count > 1:
                temporal_col = 'season'
            else:
                temporal_col = next(
                    (c for c in data.columns if c in ['round', 'season', 'year', 'match_date']),
                    data.columns[0]
                )

            y_candidates = [c for c in numeric_cols if c != temporal_col]

            # Prefer a column matching the user's requested metrics
            requested_metrics = [m.lower().replace(' ', '_') for m in (entities or {}).get("metrics", [])]
            y_col = None
            if requested_metrics:
                for candidate in y_candidates:
                    if candidate.lower() in requested_metrics or any(m in candidate.lower() for m in requested_metrics):
                        y_col = candidate
                        break
            if not y_col:
                y_col = y_candidates[0] if y_candidates else (numeric_cols[0] if numeric_cols else data.columns[-1])

            return {
                "chart_type": "line",
                "x_col": temporal_col,
                "y_col": y_col,
                "group_col": _find_group_col(),
                "reasoning": "Trend analysis - line chart over time",
                "confidence": "high"
            }

        # Rule 4: PLAYER_COMPARISON -> grouped_bar or bar
        if "COMPARISON" in intent_upper or "PLAYER_COMPARISON" in intent_upper:
            name_col = next(
                (c for c in data.columns if c.lower() in ['name', 'player', 'player_name']),
                non_numeric[0] if non_numeric else data.columns[0]
            )
            if len(numeric_cols) > 2:
                return {
                    "chart_type": "grouped_bar",
                    "x_col": name_col,
                    "y_col": numeric_cols[:6],
                    "group_col": name_col,
                    "reasoning": "Player comparison with multiple metrics - grouped bar",
                    "confidence": "high"
                }
            else:
                y_col = numeric_cols[0] if numeric_cols else data.columns[-1]
                return {
                    "chart_type": "bar",
                    "x_col": name_col,
                    "y_col": y_col,
                    "group_col": None,
                    "reasoning": "Player comparison - bar chart",
                    "confidence": "high"
                }

        # Rule 5: Top-N / ranking queries -> bar chart
        query_lower = user_query.lower()
        is_top_n = any(kw in query_lower for kw in ['top', 'most', 'best', 'highest', 'leading', 'rank', 'lowest', 'worst', 'fewest'])
        if is_top_n and 2 <= len(data) <= 20 and non_numeric and numeric_cols:
            return {
                "chart_type": "bar",
                "x_col": non_numeric[0],
                "y_col": numeric_cols[0],
                "group_col": None,
                "reasoning": "Top-N ranking query - bar chart",
                "confidence": "high"
            }

        # Rule 6: TEAM_ANALYSIS with temporal column -> line chart
        if "TEAM" in intent_upper:
            if temporal_cols and len(data) > 3:
                # Same temporal priority: round for single season, season for multi-year
                has_round = 'round' in data.columns
                has_season = 'season' in data.columns
                season_count = data['season'].nunique() if has_season else 0
                if has_round and season_count <= 1:
                    t_col = 'round'
                else:
                    t_col = temporal_cols[0]

                # Prefer metric matching user request
                requested_metrics = [m.lower().replace(' ', '_') for m in (entities or {}).get("metrics", [])]
                y_col = None
                if requested_metrics:
                    for candidate in numeric_cols:
                        if candidate.lower() in requested_metrics or any(m in candidate.lower() for m in requested_metrics):
                            y_col = candidate
                            break
                if not y_col:
                    y_col = numeric_cols[0] if numeric_cols else data.columns[-1]

                return {
                    "chart_type": "line",
                    "x_col": t_col,
                    "y_col": y_col,
                    "group_col": None,
                    "reasoning": "Team analysis over time - line chart",
                    "confidence": "high"
                }
            elif non_numeric and numeric_cols:
                return {
                    "chart_type": "bar",
                    "x_col": non_numeric[0],
                    "y_col": numeric_cols[0],
                    "group_col": None,
                    "reasoning": "Team analysis - bar chart",
                    "confidence": "high"
                }

        # Rule 7: General fallback - many data points with temporal -> line
        if temporal_cols and len(data) > 5 and numeric_cols:
            has_round = 'round' in data.columns
            has_season = 'season' in data.columns
            season_count = data['season'].nunique() if has_season else 0
            if has_round and season_count <= 1:
                t_col = 'round'
            else:
                t_col = temporal_cols[0]

            # Prefer metric matching user request
            requested_metrics = [m.lower().replace(' ', '_') for m in (entities or {}).get("metrics", [])]
            y_col = None
            if requested_metrics:
                for candidate in numeric_cols:
                    if candidate.lower() in requested_metrics or any(m in candidate.lower() for m in requested_metrics):
                        y_col = candidate
                        break
            if not y_col:
                y_col = numeric_cols[0]

            return {
                "chart_type": "line",
                "x_col": t_col,
                "y_col": y_col,
                "group_col": _find_group_col(),
                "reasoning": "Time series data - line chart",
                "confidence": "medium"
            }

        # Rule 8: General fallback - categorical data -> bar
        if 2 <= len(data) <= 30 and non_numeric and numeric_cols:
            return {
                "chart_type": "bar",
                "x_col": non_numeric[0],
                "y_col": numeric_cols[0],
                "group_col": None,
                "reasoning": "Category data - bar chart",
                "confidence": "medium"
            }

        # Genuinely ambiguous - fall through to LLM
        return None

    @classmethod
    def _llm_chart_selection(
        cls,
        user_query: str,
        data: pd.DataFrame,
        intent: str,
        entities: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to intelligently select chart configuration.

        Args:
            user_query: Original question
            data: Query results
            intent: Classified intent
            entities: Extracted entities

        Returns:
            Chart configuration dict or None if LLM fails
        """
        try:
            # Prepare data summary for LLM
            data_summary = cls._summarize_data_for_llm(data)

            # Available chart types
            chart_types_desc = "\n".join([
                f"- {name}: {desc}"
                for name, desc in cls.CHART_TYPES.items()
            ])

            prompt = f"""You are a data visualization expert. Analyze the user's question and data to select the optimal chart type and configuration.

User Question: "{user_query}"

Query Intent: {intent}

Data Summary:
- Rows: {len(data)}
- Columns: {', '.join(data.columns.tolist())}
- Numeric columns: {', '.join(data.select_dtypes(include=['number']).columns.tolist())}
- Non-numeric columns: {', '.join(data.select_dtypes(exclude=['number']).columns.tolist())}

Sample Data (first 3 rows):
{data.head(3).to_string()}

Available Chart Types:
{chart_types_desc}

Task: Select the BEST chart type and configuration for this query. Consider:
1. What is the user trying to understand? (trend, comparison, correlation, distribution, composition)
2. What type of data do we have? (time series, categories, continuous variables)
3. How many data points? (affects chart readability)
4. Are there multiple metrics to compare?
5. Is there a natural grouping variable?

Return a JSON object with:
{{
  "chart_type": "line|bar|horizontal_bar|grouped_bar|scatter|pie",
  "x_col": "column name for x-axis",
  "y_col": "column name(s) for y-axis (string or list)",
  "group_col": "optional column to group/color by",
  "reasoning": "2-3 sentence explanation of why this chart is optimal",
  "confidence": "high|medium|low",
  "alternative": "optional alternative chart type if user wants different view"
}}

Important:
- Choose chart type that directly answers the user's question
- Prefer simpler charts when appropriate (don't over-complicate)
- For "over time" queries, use line charts
- For "top N" or "compare" queries, use bar charts
- For "correlation" or "relationship" queries, use scatter plots
- Consider readability (don't chart 20 metrics on one chart)
"""

            # Call GPT-5-nano for fast decision
            response = client.chat.completions.create(
                model="gpt-5-nano",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                reasoning_effort="low",
            )

            # Parse LLM response
            result = json.loads(response.choices[0].message.content or "{}")

            logger.info(f"LLM chart selection: {result.get('chart_type')} (confidence: {result.get('confidence')})")
            logger.info(f"Reasoning: {result.get('reasoning')}")

            return result

        except Exception as e:
            logger.error(f"LLM chart selection error: {e}")
            return None

    @classmethod
    def _summarize_data_for_llm(cls, data: pd.DataFrame) -> Dict[str, Any]:
        """Create concise data summary for LLM."""
        return {
            "rows": len(data),
            "columns": data.columns.tolist(),
            "numeric_columns": data.select_dtypes(include=['number']).columns.tolist(),
            "categorical_columns": data.select_dtypes(exclude=['number']).columns.tolist(),
            "sample": data.head(3).to_dict()
        }

    @classmethod
    def _validate_and_enhance(
        cls,
        llm_result: Dict[str, Any],
        data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Validate LLM result and add missing fields.

        Args:
            llm_result: Raw LLM output
            data: Query results

        Returns:
            Validated and enhanced configuration
        """
        # Ensure required fields exist
        chart_type = llm_result.get("chart_type", "bar")
        x_col = llm_result.get("x_col")
        y_col = llm_result.get("y_col")

        # Validate columns exist in data
        if x_col and x_col not in data.columns:
            logger.warning(f"X column '{x_col}' not found, using first column")
            x_col = data.columns[0]

        if isinstance(y_col, str) and y_col not in data.columns:
            logger.warning(f"Y column '{y_col}' not found, using first numeric")
            numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
            y_col = numeric_cols[0] if numeric_cols else data.columns[1]

        # Validate group column
        group_col = llm_result.get("group_col")
        if group_col and group_col not in data.columns:
            logger.warning(f"Group column '{group_col}' not found, ignoring")
            group_col = None

        return {
            "chart_type": chart_type,
            "x_col": x_col,
            "y_col": y_col,
            "group_col": group_col,
            "reasoning": llm_result.get("reasoning", ""),
            "confidence": llm_result.get("confidence", "medium"),
            "alternative": llm_result.get("alternative")
        }

    @classmethod
    def _validate_llm_hint(
        cls,
        chart_type: str,
        hint_config: Dict[str, Any],
        data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """
        Validate a chart type hint from the consolidated LLM call.

        Returns validated config or None if hint is invalid.
        """
        if not chart_type or chart_type not in cls.CHART_TYPES:
            return None

        x_col = hint_config.get("x_col_hint")
        y_col = hint_config.get("y_col_hint")

        # Validate columns exist
        if x_col and x_col not in data.columns:
            x_col = None
        if isinstance(y_col, str) and y_col not in data.columns:
            y_col = None

        # If columns are missing, try to infer them
        if not x_col:
            temporal = [c for c in data.columns if c in ['season', 'year', 'match_date', 'round']]
            non_numeric = data.select_dtypes(exclude=['number']).columns.tolist()
            x_col = temporal[0] if temporal else (non_numeric[0] if non_numeric else data.columns[0])

        if not y_col:
            numeric = data.select_dtypes(include=['number']).columns.tolist()
            numeric = [c for c in numeric if 'id' not in c.lower()]
            y_col = numeric[0] if numeric else data.columns[-1]

        return {
            "chart_type": chart_type,
            "x_col": x_col,
            "y_col": y_col,
            "group_col": None,
            "reasoning": "Chart type from consolidated LLM hint",
            "confidence": "medium"
        }

    @classmethod
    def _fallback_selection(
        cls,
        data: pd.DataFrame,
        intent: str
    ) -> Dict[str, Any]:
        """
        Fallback to simple rule-based selection.

        Used when LLM fails or for safety.
        """
        numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
        non_numeric_cols = data.select_dtypes(exclude=['number']).columns.tolist()

        # Default: bar chart with first non-numeric as X, first numeric as Y
        x_col = non_numeric_cols[0] if non_numeric_cols else numeric_cols[0] if numeric_cols else data.columns[0]
        y_col = numeric_cols[0] if numeric_cols else data.columns[1] if len(data.columns) > 1 else data.columns[0]

        # Check for temporal dimension
        temporal_cols = ['season', 'year', 'match_date', 'round']
        has_temporal = any(col in data.columns for col in temporal_cols)

        chart_type = "line" if (has_temporal and len(data) > 3) else "bar"

        return {
            "chart_type": chart_type,
            "x_col": x_col,
            "y_col": y_col,
            "group_col": None,
            "reasoning": "Fallback selection - basic heuristics applied",
            "confidence": "low"
        }
