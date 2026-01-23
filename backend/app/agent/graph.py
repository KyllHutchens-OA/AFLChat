"""
AFL Analytics Agent - LangGraph Workflow

Defines the agent workflow: UNDERSTAND → ANALYZE_DEPTH → PLAN → EXECUTE → VISUALIZE → RESPOND
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from openai import OpenAI
import os
import logging
from dotenv import load_dotenv

from app.agent.state import AgentState, WorkflowStep, QueryIntent
from app.agent.tools import DatabaseTool, StatisticsTool
from app.analytics.query_builder import QueryBuilder
from app.analytics.entity_resolver import EntityResolver, MetricResolver
from app.analytics.context_enrichment import ContextEnricher
from app.analytics.statistics import EfficiencyCalculator
from app.visualization import PlotlyBuilder
from app.visualization.plotly_builder import ChartHelper

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AFLAnalyticsAgent:
    """
    LangGraph-based agent for AFL analytics queries.

    Workflow:
    1. UNDERSTAND - Parse user query, extract intent and entities
    2. ANALYZE_DEPTH - Determine summary vs in-depth analysis mode
    3. PLAN - Determine analysis steps required
    4. EXECUTE - Run SQL queries and compute statistics
    5. VISUALIZE - Generate chart specifications (if needed)
    6. RESPOND - Format natural language response
    """

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("understand", self.understand_node)
        workflow.add_node("analyze_depth", self.analyze_depth_node)
        workflow.add_node("plan", self.plan_node)
        workflow.add_node("execute", self.execute_node)
        workflow.add_node("visualize", self.visualize_node)
        workflow.add_node("respond", self.respond_node)

        # Add edges
        workflow.add_edge("understand", "analyze_depth")
        workflow.add_edge("analyze_depth", "plan")
        workflow.add_edge("plan", "execute")

        # Conditional edge: visualize if needed, otherwise go to respond
        workflow.add_conditional_edges(
            "execute",
            lambda state: "visualize" if state.get("requires_visualization") and state.get("query_results") is not None and len(state.get("query_results", [])) > 0 else "respond",
            {
                "visualize": "visualize",
                "respond": "respond"
            }
        )

        workflow.add_edge("visualize", "respond")
        workflow.add_edge("respond", END)

        # Set entry point
        workflow.set_entry_point("understand")

        return workflow.compile()

    async def run(self, user_query: str, conversation_id: str = None) -> AgentState:
        """
        Run the agent workflow on a user query.

        Args:
            user_query: Natural language question
            conversation_id: Optional conversation ID

        Returns:
            Final agent state with response
        """
        initial_state = AgentState(
            user_query=user_query,
            conversation_id=conversation_id,
            entities={},
            needs_clarification=False,
            analysis_plan=[],
            requires_visualization=False,
            sql_validated=False,
            statistical_analysis={},
            errors=[],
            current_step=WorkflowStep.UNDERSTAND,
            analysis_types=[],
            context_insights={},
            data_quality={},
            stats_summary={}
        )

        final_state = await self.graph.ainvoke(initial_state)
        return final_state

    # ==================== WORKFLOW NODES ====================

    async def understand_node(self, state: AgentState) -> AgentState:
        """
        UNDERSTAND node: Parse user query and extract intent/entities.

        Updates:
        - intent
        - entities
        - thinking_message
        """
        state["current_step"] = WorkflowStep.UNDERSTAND
        state["thinking_message"] = "🔍 Understanding your question..."

        logger.info(f"UNDERSTAND: Processing query: {state['user_query']}")

        try:
            # Use GPT-5-nano to understand the query (Responses API)
            response = client.responses.create(
                model="gpt-5-nano",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"""You are an AFL analytics query analyzer. Parse the user's question and extract:
1. Intent: What type of analysis are they asking for?
2. Entities: What teams, players, seasons, or metrics are mentioned?

Intent Classification:
- "simple_stat": Single number/fact (e.g., "How many wins?", "What was the score?")
- "player_comparison": Comparing multiple players
- "team_analysis": Single team's performance over a SINGLE season/period
- "trend_analysis": TEMPORAL queries showing change over TIME (keywords: "over time", "across time", "year by year", "historical", "trend", "evolution", "since joining", "throughout history")

CRITICAL: If the query contains temporal keywords (over time, across time, year-by-year, historical, trend, since, evolution), the intent MUST be "trend_analysis".

Return a JSON object with:
{{
  "intent": "simple_stat" | "player_comparison" | "team_analysis" | "trend_analysis",
  "entities": {{
    "teams": [...],
    "players": [...],
    "seasons": [...],
    "metrics": [...],
    "rounds": [...]
  }},
  "requires_visualization": true/false
}}

User question: {state["user_query"]}"""
                            }
                        ]
                    }
                ],
                text={"format": {"type": "json_object"}}
            )

            import json
            understanding = json.loads(response.output_text)

            state["intent"] = QueryIntent(understanding.get("intent", "unknown"))
            raw_entities = understanding.get("entities", {})

            # VALIDATE AND NORMALIZE ENTITIES using EntityResolver
            validation_result = EntityResolver.validate_entities(raw_entities)

            # Use corrected entities
            state["entities"] = validation_result["corrected_entities"]

            # Log warnings about entity resolution
            if validation_result["warnings"]:
                for warning in validation_result["warnings"]:
                    logger.warning(f"Entity resolution: {warning}")

            # If validation failed completely, set clarification flag
            if not validation_result["is_valid"] and validation_result["suggestions"]:
                state["needs_clarification"] = True
                state["clarification_question"] = validation_result["suggestions"][0]

            state["requires_visualization"] = understanding.get("requires_visualization", False)

            logger.info(f"Intent: {state['intent']}, Raw entities: {raw_entities}, Resolved entities: {state['entities']}")

        except Exception as e:
            logger.error(f"Error in UNDERSTAND node: {e}")
            state["errors"].append(f"Understanding error: {str(e)}")

        return state

    async def analyze_depth_node(self, state: AgentState) -> AgentState:
        """
        ANALYZE_DEPTH node: Determine summary vs in-depth analysis mode.

        Scoring system:
        - Intent type: TREND_ANALYSIS +3, PLAYER_COMPARISON +3, TEAM_ANALYSIS +2
        - Entity count: ≥2 teams/players +2
        - Keywords: compare, vs, over time, trend, historical, analyze +1 each
        - Negative keywords: who won, what was -2 each

        Threshold: score ≥3 → in_depth, else summary

        Updates:
        - analysis_mode ("summary" or "in_depth")
        - analysis_types (list of analysis types to run)
        - thinking_message
        """
        state["current_step"] = WorkflowStep.ANALYZE_DEPTH
        state["thinking_message"] = "🎯 Analyzing query complexity..."

        logger.info(f"ANALYZE_DEPTH: Determining analysis mode for intent={state.get('intent')}")

        score = 0
        query_lower = state["user_query"].lower()
        intent = state.get("intent")
        entities = state.get("entities", {})

        # Score by intent
        if intent == QueryIntent.TREND_ANALYSIS:
            score += 3
        elif intent == QueryIntent.PLAYER_COMPARISON:
            score += 3
        elif intent == QueryIntent.TEAM_ANALYSIS:
            score += 2

        # Score by entity count
        teams = entities.get("teams", [])
        players = entities.get("players", [])
        total_entities = len(teams) + len(players)
        if total_entities >= 2:
            score += 2

        # Positive keywords
        positive_keywords = [
            "compare", "vs", "versus", "over time", "across time",
            "trend", "historical", "analyze", "deep dive", "tell me about",
            "performance", "evolution", "progression", "trajectory"
        ]
        for keyword in positive_keywords:
            if keyword in query_lower:
                score += 1

        # Negative keywords (simple questions)
        negative_keywords = [
            "who won", "what was", "when did", "how many",
            "which team", "what score"
        ]
        for keyword in negative_keywords:
            if keyword in query_lower:
                score -= 2

        # Determine mode
        analysis_mode = "in_depth" if score >= 3 else "summary"

        # Determine analysis types based on mode
        if analysis_mode == "in_depth":
            analysis_types = ["average"]

            # Add trend analysis for temporal queries
            if intent == QueryIntent.TREND_ANALYSIS or any(
                kw in query_lower for kw in ["over time", "across time", "trend", "historical", "evolution"]
            ):
                analysis_types.append("trend")

            # Add comparison for multi-entity queries
            if intent == QueryIntent.PLAYER_COMPARISON or total_entities >= 2:
                analysis_types.append("comparison")

            # Add rankings for competitive analysis
            if any(kw in query_lower for kw in ["best", "worst", "top", "rank", "leader"]):
                analysis_types.append("rank")
        else:
            # Summary mode: just averages
            analysis_types = ["average"]

        state["analysis_mode"] = analysis_mode
        state["analysis_types"] = analysis_types

        logger.info(
            f"Analysis mode: {analysis_mode} (score={score}), "
            f"types={analysis_types}"
        )

        return state

    async def plan_node(self, state: AgentState) -> AgentState:
        """
        PLAN node: Determine analysis steps required.

        Updates:
        - analysis_plan
        - chart_type (if visualization needed)
        - thinking_message
        """
        state["current_step"] = WorkflowStep.PLAN
        state["thinking_message"] = "📋 Planning the analysis..."

        intent = state.get('intent', QueryIntent.SIMPLE_STAT)
        logger.info(f"PLAN: Creating analysis plan for intent: {intent}")

        try:
            # Simple rule-based planning for MVP
            # Can be enhanced with LLM-based planning later

            plan = []

            # Step 1: Query database
            plan.append("Query AFL database for relevant data")

            # Step 2: Analysis based on intent
            if intent == QueryIntent.PLAYER_COMPARISON:
                plan.append("Compare player statistics")
                state["requires_visualization"] = True  # Force visualization for comparisons

            elif intent == QueryIntent.TEAM_ANALYSIS:
                plan.append("Analyze team performance")
                state["requires_visualization"] = True  # Force visualization for team analysis

            elif intent == QueryIntent.TREND_ANALYSIS:
                plan.append("Calculate trends over time")
                state["requires_visualization"] = True  # Force visualization for trends

            else:  # simple_stat
                plan.append("Extract requested statistics")

            # Step 3: Visualization if needed
            if state.get("requires_visualization", False):
                plan.append("Generate visualization")

            state["analysis_plan"] = plan

            logger.info(f"Analysis plan: {plan}")

        except Exception as e:
            logger.error(f"Error in PLAN node: {e}")
            state["errors"].append(f"Planning error: {str(e)}")

        return state

    async def execute_node(self, state: AgentState) -> AgentState:
        """
        EXECUTE node: Run SQL queries and compute statistics.

        Updates:
        - sql_query
        - sql_validated
        - query_results
        - statistical_analysis
        - thinking_message
        """
        state["current_step"] = WorkflowStep.EXECUTE
        state["thinking_message"] = "🔨 Generating SQL query..."

        logger.info("EXECUTE: Generating and running SQL query")

        try:
            # Step 1: Generate SQL from natural language
            # Use RESOLVED entities (normalized team names, validated seasons, etc.)
            sql_result = QueryBuilder.generate_sql(
                state["user_query"],
                context=state["entities"]  # These are now validated/normalized
            )

            if not sql_result["success"]:
                state["execution_error"] = sql_result["error"]
                state["errors"].append(sql_result["error"])
                state["thinking_message"] = f"❌ Error: {sql_result['error']}"
                return state

            state["sql_query"] = sql_result["sql"]
            logger.info(f"Generated SQL: {state['sql_query']}")

            # Step 2: Execute query
            state["thinking_message"] = "⚡ Querying AFL database (6,243 matches)..."
            db_result = DatabaseTool.query_database(state["sql_query"])

            if not db_result["success"]:
                state["execution_error"] = db_result["error"]
                state["errors"].append(db_result["error"])
                state["thinking_message"] = f"❌ Query failed: {db_result['error']}"
                return state

            state["sql_validated"] = True
            state["query_results"] = db_result["data"]

            logger.info(f"Query returned {db_result['rows_returned']} rows")
            state["thinking_message"] = f"✅ Found {db_result['rows_returned']} results"

            # Step 3: Compute statistics if needed
            if len(db_result["data"]) > 0 and state.get("intent") != QueryIntent.SIMPLE_STAT:
                state["thinking_message"] = "📊 Calculating statistics..."

                # Get analysis types from analyze_depth node
                analysis_types = state.get("analysis_types", ["average"])
                combined_stats = {"success": True, "mode": state.get("analysis_mode", "summary")}

                # Run all requested analysis types
                for analysis_type in analysis_types:
                    logger.info(f"Running {analysis_type} analysis")
                    stats_result = StatisticsTool.compute_statistics(
                        db_result["data"],
                        analysis_type=analysis_type,
                        params={}
                    )

                    if stats_result.get("success"):
                        combined_stats[analysis_type] = stats_result
                    else:
                        logger.warning(f"{analysis_type} analysis failed: {stats_result.get('error')}")

                state["statistical_analysis"] = combined_stats
                logger.info(f"Computed statistics for {len(analysis_types)} analysis types")

                # Step 4: Add context enrichment for in-depth mode
                if state.get("analysis_mode") == "in_depth":
                    state["thinking_message"] = "🔍 Enriching context..."
                    entities = state.get("entities", {})
                    teams = entities.get("teams", [])
                    seasons = entities.get("seasons", [])

                    # Enrich team context if we have a team
                    if teams and len(teams) > 0:
                        team_name = teams[0]
                        season = int(seasons[0]) if seasons and len(seasons) > 0 else None

                        try:
                            context = ContextEnricher.enrich_team_context(
                                team_name=team_name,
                                current_stats=combined_stats.get("average", {}),
                                data=db_result["data"],
                                season=season
                            )

                            # Calculate efficiency metrics
                            efficiency = EfficiencyCalculator.calculate_all_efficiency_metrics(
                                db_result["data"]
                            )

                            if context:
                                state["context_insights"] = context
                            if efficiency:
                                state["context_insights"]["efficiency"] = efficiency

                            logger.info(f"Added context enrichment for {team_name}")
                        except Exception as enrichment_error:
                            logger.error(f"Error enriching context: {enrichment_error}")
                            # Don't fail the whole request if enrichment fails

        except Exception as e:
            logger.error(f"Error in EXECUTE node: {e}")
            state["execution_error"] = str(e)
            state["errors"].append(f"Execution error: {str(e)}")
            state["thinking_message"] = f"❌ Error: {str(e)}"

        return state

    async def visualize_node(self, state: AgentState) -> AgentState:
        """
        VISUALIZE node: Generate Plotly chart specification.

        Updates:
        - visualization_spec
        - thinking_message
        """
        state["current_step"] = WorkflowStep.VISUALIZE
        state["thinking_message"] = "📈 Creating visualization..."

        logger.info("VISUALIZE: Generating chart")

        try:
            # Get data and intent
            data = state["query_results"]
            intent = state.get("intent")
            entities = state.get("entities", {})

            # VALIDATION: Check if we have enough data points for a useful chart
            MIN_DATA_POINTS = 2  # Need at least 2 points for a trend
            if len(data) < MIN_DATA_POINTS:
                logger.warning(f"Insufficient data for visualization: {len(data)} rows (need at least {MIN_DATA_POINTS})")
                state["thinking_message"] = f"⚠️ Not enough data points for chart ({len(data)} rows)"
                # Skip visualization - will go to respond node without chart
                return state

            # Auto-detect x and y columns
            numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
            non_numeric_cols = data.select_dtypes(exclude=['number']).columns.tolist()
            all_cols = data.columns.tolist()

            # INTELLIGENT CHART TYPE SELECTION
            chart_type = PlotlyBuilder._select_chart_type(data, intent, all_cols)

            params = {}

            # Smart column detection based on common AFL data patterns
            # Priority for X-axis:
            # - For TREND queries: season > year > match_date > round
            # - For PERFORMANCE queries: round > match_date > season
            x_col = None

            if intent == QueryIntent.TREND_ANALYSIS:
                # Temporal queries prioritize time periods
                if 'season' in all_cols:
                    x_col = 'season'
                elif 'year' in all_cols:
                    x_col = 'year'
                elif 'match_date' in all_cols:
                    x_col = 'match_date'
                elif 'round' in all_cols:
                    x_col = 'round'
                elif len(non_numeric_cols) > 0:
                    x_col = non_numeric_cols[0]
            else:
                # Performance/single-season queries prioritize rounds
                if 'round' in all_cols:
                    x_col = 'round'
                elif 'match_date' in all_cols:
                    x_col = 'match_date'
                elif 'season' in all_cols:
                    x_col = 'season'
                elif len(non_numeric_cols) > 0:
                    x_col = non_numeric_cols[0]

            # Priority for Y-axis: margin > team_score > wins > first numeric
            y_col = None
            if 'margin' in all_cols:
                y_col = 'margin'
            elif 'team_score' in all_cols:
                y_col = 'team_score'
            elif 'wins' in all_cols:
                y_col = 'wins'
            elif len(numeric_cols) > 0:
                y_col = numeric_cols[0]

            if x_col and y_col:
                params["x_col"] = x_col
                params["y_col"] = y_col

                # Group by result (Win/Loss) if available
                if 'result' in all_cols and chart_type == 'line':
                    params["group_col"] = 'result'

            # Generate smart title
            params["title"] = ChartHelper.generate_chart_title(
                intent=str(intent),
                entities=entities,
                metrics=entities.get("metrics", []),
                data_cols=all_cols
            )

            # Generate chart
            chart_spec = PlotlyBuilder.generate_chart(data, chart_type, params)

            state["visualization_spec"] = chart_spec

            logger.info(f"Chart generated: {chart_type}")
            state["thinking_message"] = f"✅ Chart created ({chart_type})"

        except Exception as e:
            logger.error(f"Error in VISUALIZE node: {e}")
            state["errors"].append(f"Visualization error: {str(e)}")
            state["thinking_message"] = f"⚠️ Skipping visualization: {str(e)}"

        return state

    def _format_stats_for_gpt(self, stats: Dict[str, Any]) -> str:
        """
        Format statistical analysis into readable text for GPT consumption.

        Args:
            stats: Statistical analysis dictionary from execute_node

        Returns:
            Formatted string with statistical insights
        """
        if not stats or not stats.get("success"):
            return "No statistical analysis available."

        parts = []
        mode = stats.get("mode", "summary")

        parts.append(f"Analysis Mode: {mode}")

        # Format averages
        if "average" in stats:
            avg_stats = stats["average"]
            if avg_stats.get("success") and "averages" in avg_stats:
                parts.append("\n**Basic Statistics:**")
                for metric, values in list(avg_stats["averages"].items())[:5]:  # Limit to 5 metrics
                    parts.append(
                        f"- {metric}: mean={values['mean']:.2f}, "
                        f"median={values['median']:.2f}, "
                        f"range=[{values['min']:.2f}, {values['max']:.2f}]"
                    )

        # Format trends
        if "trend" in stats:
            trend_stats = stats["trend"]
            if trend_stats.get("success"):
                parts.append("\n**Trend Analysis:**")
                parts.append(f"- Summary: {trend_stats.get('summary', 'N/A')}")

                direction = trend_stats.get("direction", {})
                parts.append(
                    f"- Direction: {direction.get('classification', 'unknown')} "
                    f"(p={direction.get('p_value', 'N/A')}, R²={direction.get('r_squared', 'N/A')})"
                )

                momentum = trend_stats.get("momentum", {})
                if momentum.get("classification"):
                    recent_avg = momentum.get('recent_avg')
                    historical_avg = momentum.get('historical_avg')

                    recent_str = f"{recent_avg:.2f}" if recent_avg is not None else "N/A"
                    historical_str = f"{historical_avg:.2f}" if historical_avg is not None else "N/A"

                    parts.append(
                        f"- Momentum: {momentum['classification']} "
                        f"(recent avg: {recent_str}, historical avg: {historical_str})"
                    )

                change = trend_stats.get("change", {})
                if change.get("overall_percent") is not None:
                    parts.append(f"- Overall change: {change['overall_percent']:+.2f}%")

                parts.append(f"- Confidence: {trend_stats.get('confidence', 'unknown')}")

        # Format comparison
        if "comparison" in stats:
            comp_stats = stats["comparison"]
            if comp_stats.get("success"):
                parts.append("\n**Comparison Analysis:**")
                parts.append(f"- Comparing {comp_stats.get('entity_count', 0)} entities")
                parts.append(f"- Summary: {comp_stats.get('summary', 'N/A')}")

                # Show top leaders
                leaders = comp_stats.get("leaders", {})
                if leaders:
                    parts.append("- Leaders:")
                    for metric, leader_info in list(leaders.items())[:3]:  # Top 3
                        parts.append(
                            f"  * {metric}: {leader_info.get('entity')} "
                            f"({leader_info.get('value', 'N/A')})"
                        )

        # Format rankings
        if "rank" in stats:
            rank_stats = stats["rank"]
            if rank_stats.get("success"):
                parts.append("\n**Rankings:**")
                parts.append(f"- Summary: {rank_stats.get('summary', 'N/A')}")

                # Show top 3
                top_3 = rank_stats.get("top_3", [])
                if top_3:
                    parts.append("- Top 3:")
                    for item in top_3:
                        parts.append(
                            f"  {item['rank']}. {item['entity']}: {item['value']} "
                            f"({item['percentile']}th percentile)"
                        )

        # Add data quality warnings from any analysis type
        quality_warnings = []
        for analysis_type in ["average", "trend", "comparison", "rank"]:
            if analysis_type in stats:
                analysis_stats = stats[analysis_type]
                if "data_quality" in analysis_stats:
                    warnings = analysis_stats["data_quality"].get("warnings", [])
                    quality_warnings.extend(warnings)

        if quality_warnings:
            parts.append("\n**Data Quality Considerations:**")
            for warning in list(set(quality_warnings))[:3]:  # Unique warnings, limit 3
                parts.append(f"⚠️  {warning}")

        return "\n".join(parts)

    async def respond_node(self, state: AgentState) -> AgentState:
        """
        RESPOND node: Format natural language response.

        Updates:
        - natural_language_summary
        - confidence
        - thinking_message
        """
        state["current_step"] = WorkflowStep.RESPOND
        state["thinking_message"] = "✍️ Writing response..."

        logger.info("RESPOND: Generating natural language response")

        try:
            # Check for errors
            if state.get("execution_error"):
                state["natural_language_summary"] = (
                    "I encountered an issue while analyzing your query. "
                    "Could you rephrase your question?"
                )
                state["confidence"] = 0.0
                return state

            # Check if we have results
            if state.get("query_results") is None or len(state["query_results"]) == 0:
                # Provide helpful suggestions based on what went wrong
                raw_query = state.get("user_query", "")
                suggestions = []

                # Check if there were entity resolution issues
                if state.get("needs_clarification"):
                    suggestions.append(state.get("clarification_question", ""))

                # Suggest checking team names
                if "entities" in state and "teams" in state["entities"]:
                    if not state["entities"]["teams"]:
                        suggestions.append(
                            f"Available teams: Adelaide, Brisbane Lions, Carlton, Collingwood, Essendon, "
                            f"Fremantle, Geelong, Gold Coast, GWS, Hawthorn, Melbourne, North Melbourne, "
                            f"Port Adelaide, Richmond, St Kilda, Sydney, West Coast, Western Bulldogs"
                        )

                # Check if query asked for player stats
                if "player" in raw_query.lower() or "stats" in raw_query.lower():
                    suggestions.append(
                        "Note: Player statistics are not yet available - only match-level data (1990-2025) is currently loaded."
                    )

                suggestion_text = " ".join(suggestions) if suggestions else (
                    "Note: Player statistics are not yet available - only match-level data (1990-2025) is currently loaded."
                )

                state["natural_language_summary"] = (
                    f"I couldn't find any data matching your query. {suggestion_text}"
                )
                state["confidence"] = 0.3
                return state

            # Format statistics for GPT consumption
            stats_summary = self._format_stats_for_gpt(state.get("statistical_analysis", {}))

            # Format context insights if available
            context_insights = state.get("context_insights", {})
            context_text = ""
            if context_insights:
                context_text = "\n\nContextual Insights:"

                # Form analysis
                if "form_analysis" in context_insights:
                    form = context_insights["form_analysis"]
                    context_text += f"\n- Recent form: {form.get('momentum', 'N/A')}"

                # Venue splits
                if "venue_splits" in context_insights:
                    splits = context_insights["venue_splits"]
                    home_adv = splits.get("home_advantage_pct")
                    if home_adv:
                        context_text += f"\n- Home advantage: {home_adv:+.1f}%"

                # Historical percentiles
                if "historical_percentiles" in context_insights:
                    percentiles = context_insights["historical_percentiles"]
                    if "win_rate" in percentiles:
                        context_text += f"\n- Historical percentile (win rate): {percentiles['win_rate']}th"

                # Efficiency metrics
                if "efficiency" in context_insights:
                    efficiency = context_insights["efficiency"]
                    if "shooting" in efficiency:
                        shooting = efficiency["shooting"]
                        context_text += f"\n- Shooting accuracy: {shooting['accuracy_percent']:.1f}%"
                    if "margins" in efficiency:
                        margins = efficiency["margins"]
                        context_text += f"\n- Close game percentage: {margins.get('close_game_pct', 0):.1f}%"

            # Generate response using GPT-5-nano (Responses API)
            response = client.responses.create(
                model="gpt-5-nano",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"""You are an AFL analytics expert. Generate a natural language summary of the query results.

Guidelines:
- Be concise but insightful
- Use Australian football terminology correctly
- Include specific numbers from both query results AND statistical insights
- Highlight patterns, trends, and meaningful insights from the statistical analysis
- If confidence is low or sample size is small, mention it
- If analysis mode is "in_depth", provide richer context and deeper insights
- Include contextual insights like form, home advantage, historical rankings when available
- Never mention SQL, databases, or technical details
- Write in a friendly, conversational tone

User asked: {state['user_query']}

Query results:
{state['query_results'].to_string() if len(state['query_results']) < 20 else state['query_results'].head(10).to_string()}

Statistical Insights:
{stats_summary}{context_text}

Generate a comprehensive summary using these insights:"""
                            }
                        ]
                    }
                ]
            )

            state["natural_language_summary"] = response.output_text.strip()
            state["confidence"] = 0.9
            state["sources"] = ["AFL Tables (1990-2025)"]
            state["thinking_message"] = "✅ Response complete!"

            logger.info("Response generated successfully")

        except Exception as e:
            logger.error(f"Error in RESPOND node: {e}")
            state["natural_language_summary"] = "I encountered an issue generating the response."
            state["confidence"] = 0.0
            state["errors"].append(f"Response error: {str(e)}")

        return state


# Global agent instance
agent = AFLAnalyticsAgent()
