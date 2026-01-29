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
from app.visualization.chart_selector import ChartSelector
from app.visualization.layout_optimizer import LayoutOptimizer
from app.visualization.data_preprocessor import DataPreprocessor

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

    @staticmethod
    def _emit_progress(state: AgentState, step: str, message: str):
        """
        Emit WebSocket progress update if callback is available.

        Args:
            state: Current agent state
            step: Step identifier (e.g., "understand", "execute")
            message: User-facing progress message
        """
        if state.get("socketio_emit"):
            try:
                state["socketio_emit"]('thinking', {
                    'step': message,
                    'current_step': step
                })
            except Exception as e:
                logger.warning(f"Failed to emit WebSocket progress: {e}")

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

        # Add edges with conditional routing
        # After understand: if needs clarification, skip to respond
        workflow.add_conditional_edges(
            "understand",
            lambda state: "respond" if state.get("needs_clarification") else "analyze_depth",
            {
                "respond": "respond",
                "analyze_depth": "analyze_depth"
            }
        )
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

    async def run(
        self,
        user_query: str,
        conversation_id: str = None,
        socketio_emit: Any = None,
        conversation_history: List[Dict[str, Any]] = None
    ) -> AgentState:
        """
        Run the agent workflow on a user query.

        Args:
            user_query: Natural language question
            conversation_id: Optional conversation ID
            socketio_emit: Optional WebSocket emit callback for real-time updates
            conversation_history: Optional previous conversation messages for context

        Returns:
            Final agent state with response
        """
        from typing import List, Any

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
            stats_summary={},
            socketio_emit=socketio_emit,
            conversation_history=conversation_history or []
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
        state["thinking_message"] = "Understanding your question..."
        self._emit_progress(state, "understand", "Understanding your question...")

        logger.info(f"UNDERSTAND: Processing query: {state['user_query']}")

        try:
            # Check if this is a response to a clarification question
            conversation_history = state.get("conversation_history", [])
            logger.info(f"UNDERSTAND: conversation_history length = {len(conversation_history) if conversation_history else 0}")

            # Debug: Log all messages in history
            if conversation_history:
                for i, msg in enumerate(conversation_history):
                    role = msg.get("role")
                    content = msg.get("content", "")[:50]
                    has_clarification = msg.get("needs_clarification", False)
                    candidates = msg.get("clarification_candidates")
                    logger.info(f"  Message {i}: {role} - '{content}...' needs_clarification={has_clarification}, candidates={candidates}")

            if conversation_history and len(conversation_history) >= 2:
                # Get the last assistant message (most recent)
                last_assistant_msg = None
                for msg in reversed(conversation_history):
                    if msg.get("role") == "assistant":
                        last_assistant_msg = msg
                        break

                # Check if last message was a clarification question
                if last_assistant_msg:
                    content = last_assistant_msg.get("content", "")
                    was_clarification = last_assistant_msg.get("needs_clarification", False)
                    candidates = last_assistant_msg.get("clarification_candidates")

                    logger.info(f"UNDERSTAND: Last assistant message: {content[:100]}...")
                    logger.info(f"UNDERSTAND: was_clarification={was_clarification}, candidates={candidates}")

                    # Check if this was a clarification question
                    if was_clarification and candidates:
                        logger.info(f"UNDERSTAND: Detected clarification question with candidates: {candidates}")

                        # Try to match user's response against candidates
                        user_response = state['user_query'].lower().strip()

                        # Remove common filler words
                        user_response_cleaned = user_response
                        for filler in [' please', ' thanks', ' pls', ' thx', ',', '.', ' ?']:
                            user_response_cleaned = user_response_cleaned.replace(filler, '')
                        user_response_cleaned = user_response_cleaned.strip()

                        # Try to find matches
                        potential_matches = []
                        for candidate in candidates:
                            candidate_lower = candidate.lower()

                            # Check exact match
                            if user_response_cleaned == candidate_lower:
                                potential_matches.append(candidate)
                                continue

                            # Check if all words in user response are in candidate
                            user_words = user_response_cleaned.split()
                            candidate_words = candidate_lower.split()

                            # If user response is a single word, check if it matches any part of candidate name
                            if len(user_words) == 1:
                                if user_words[0] in candidate_words:
                                    potential_matches.append(candidate)
                            else:
                                # Multiple words: check if all are in candidate
                                if all(word in candidate_words for word in user_words):
                                    potential_matches.append(candidate)

                        # Only use match if exactly one candidate matches
                        logger.info(f"UNDERSTAND: Potential matches for '{user_response_cleaned}': {potential_matches}")
                        matched_candidate = None
                        if len(potential_matches) == 1:
                            matched_candidate = potential_matches[0]
                            logger.info(f"UNDERSTAND: Successfully matched to '{matched_candidate}'")
                        elif len(potential_matches) > 1:
                            logger.warning(f"Ambiguous clarification response: '{user_response}' matches multiple candidates: {potential_matches}")
                        else:
                            logger.warning(f"No matches found for clarification response: '{user_response}' among candidates: {candidates}")

                        if matched_candidate:
                            logger.info(f"Matched clarification response '{user_response}' to '{matched_candidate}'")

                            # Get the original query intent from conversation history
                            # Find the user message before the clarification
                            original_user_msg = None
                            found_clarification = False
                            for msg in reversed(conversation_history):
                                if msg.get("role") == "assistant" and msg.get("needs_clarification"):
                                    found_clarification = True
                                elif found_clarification and msg.get("role") == "user":
                                    original_user_msg = msg
                                    break

                            # Set entities directly without GPT call
                            state["entities"] = {
                                "players": [matched_candidate],
                                "teams": [],
                                "seasons": [],
                                "metrics": [],
                                "rounds": []
                            }

                            # Copy season/metric from original query if available
                            if original_user_msg:
                                original_entities = original_user_msg.get("entities", {})
                                if original_entities.get("seasons"):
                                    state["entities"]["seasons"] = original_entities["seasons"]
                                if original_entities.get("metrics"):
                                    state["entities"]["metrics"] = original_entities["metrics"]

                            # Set intent to simple_stat (most common for player stats)
                            state["intent"] = QueryIntent.SIMPLE_STAT
                            state["requires_visualization"] = False
                            state["needs_clarification"] = False

                            logger.info(f"Resolved clarification: entities={state['entities']}")

                            # Skip the rest of entity extraction and return
                            return state

            # Build conversation context for follow-up questions
            conversation_context = ""

            if conversation_history and len(conversation_history) > 0:
                # Get last few exchanges for context
                recent_messages = conversation_history[-6:]  # Last 3 exchanges (user + assistant)

                conversation_context = "\n## Previous Conversation Context\n"
                for msg in recent_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")

                    if role == "user":
                        conversation_context += f"User: {content}\n"
                    elif role == "assistant":
                        # Include assistant entities if available
                        entities = msg.get("entities", {})
                        if entities:
                            teams = entities.get("teams", [])
                            players = entities.get("players", [])
                            if teams:
                                conversation_context += f"Assistant discussed: Teams: {', '.join(teams)}\n"
                            if players:
                                conversation_context += f"Assistant discussed: Players: {', '.join(players)}\n"

                conversation_context += "\nUse this context to resolve ambiguous references (e.g., 'What about 2023?' or 'Compare them').\n---\n\n"

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

Entity Classification Rules:
- **Players**: Surnames (e.g., "Dangerfield", "Cripps", "Bontempelli"), full names (e.g., "Patrick Dangerfield"), or nicknames
- **Teams**: AFL club names (e.g., "Richmond", "Collingwood", "Geelong", "Brisbane Lions", "Greater Western Sydney")
- **Metrics**: Statistics like "goals", "disposals", "marks", "tackles", "wins", "losses", "score"
- **Seasons**: Years (e.g., "2022", "2023", "last year", "this year")

CRITICAL Rules:
- If the query contains temporal keywords (over time, across time, year-by-year, historical, trend, since, evolution), the intent MUST be "trend_analysis"
- Single surnames (e.g., "Dangerfield", "Cripps") are ALWAYS players, NEVER teams
- If uncertain whether something is a player or team, prefer "players" for single-word surnames

{conversation_context}Return a JSON object with:
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

Current user question: {state["user_query"]}"""
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
        self._emit_progress(state, "analyze_depth", "🎯 Analyzing query complexity...")

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
        self._emit_progress(state, "plan", "📋 Planning the analysis...")

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
        self._emit_progress(state, "execute", "🔨 Generating SQL query...")

        logger.info("EXECUTE: Generating and running SQL query")

        try:
            # Step 1: Generate SQL from natural language
            # Use RESOLVED entities (normalized team names, validated seasons, etc.)
            # Pass conversation history to resolve ambiguous references like "this", "them", etc.
            sql_result = QueryBuilder.generate_sql(
                state["user_query"],
                context=state["entities"],  # These are now validated/normalized
                conversation_history=state.get("conversation_history", [])
            )

            if not sql_result["success"]:
                error_msg = f"SQL generation failed: {sql_result['error']}"
                logger.error(error_msg)
                state["execution_error"] = error_msg
                state["errors"].append(error_msg)
                state["thinking_message"] = f"❌ Error: {error_msg}"
                return state

            state["sql_query"] = sql_result["sql"]
            logger.info(f"Generated SQL: {state['sql_query']}")

            # Step 2: Execute query
            state["thinking_message"] = "⚡ Querying AFL database (6,243 matches)..."
            self._emit_progress(state, "execute", "⚡ Querying AFL database (6,243 matches)...")
            db_result = DatabaseTool.query_database(state["sql_query"])

            if not db_result["success"]:
                error_msg = f"Database query failed: {db_result['error']}"
                logger.error(f"{error_msg} | SQL: {state.get('sql_query', 'N/A')}")
                state["execution_error"] = error_msg
                state["errors"].append(error_msg)
                state["thinking_message"] = f"❌ Query failed: {error_msg}"
                return state

            state["sql_validated"] = True
            state["query_results"] = db_result["data"]

            logger.info(f"Query returned {db_result['rows_returned']} rows")
            state["thinking_message"] = f"Found {db_result['rows_returned']} results"
            self._emit_progress(state, "execute", f"Found {db_result['rows_returned']} results")

            # Step 3: Compute statistics if needed
            if len(db_result["data"]) > 0 and state.get("intent") != QueryIntent.SIMPLE_STAT:
                state["thinking_message"] = "Calculating statistics..."
                self._emit_progress(state, "execute", "Calculating statistics...")

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
                    state["thinking_message"] = "Enriching context..."
                    self._emit_progress(state, "execute", "Enriching context...")
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
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Error in EXECUTE node: {e}\n{tb}")
            error_msg = f"Execution error: {str(e)}"
            state["execution_error"] = error_msg
            state["errors"].append(error_msg)
            state["thinking_message"] = f"❌ Error: {error_msg}"

        return state

    async def visualize_node(self, state: AgentState) -> AgentState:
        """
        VISUALIZE node: Generate Plotly chart specification.

        Updates:
        - visualization_spec
        - thinking_message
        """
        state["current_step"] = WorkflowStep.VISUALIZE
        state["thinking_message"] = "Creating visualization..."
        self._emit_progress(state, "visualize", "Creating visualization...")

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

            # Use intelligent ChartSelector to determine optimal chart configuration
            user_query = state.get("user_query", "")

            chart_config = ChartSelector.select_chart_configuration(
                user_query=user_query,
                data=data,
                intent=str(intent),
                entities=entities
            )

            logger.info(f"ChartSelector recommendation: {chart_config.get('chart_type')} "
                       f"(confidence: {chart_config.get('confidence', 'unknown')})")
            logger.info(f"Reasoning: {chart_config.get('reasoning', 'N/A')}")

            # Extract configuration
            chart_type = chart_config.get("chart_type", "bar")
            x_col = chart_config.get("x_col")
            y_col = chart_config.get("y_col")
            group_col = chart_config.get("group_col")

            # Handle multiple y columns (list) - use comparison chart or take first
            if isinstance(y_col, list):
                if len(y_col) > 1:
                    # Multiple metrics - use comparison chart
                    chart_type = "comparison"
                    params = {
                        "group_col": x_col,  # X becomes the grouping dimension
                        "metric_cols": y_col  # Y columns become metrics to compare
                    }
                else:
                    # Single metric in list
                    y_col = y_col[0]
                    params = {}
                    if x_col:
                        params["x_col"] = x_col
                    if y_col:
                        params["y_col"] = y_col
                    if group_col:
                        params["group_col"] = group_col
            else:
                # Single y column (string)
                params = {}
                if x_col:
                    params["x_col"] = x_col
                if y_col:
                    params["y_col"] = y_col
                if group_col:
                    params["group_col"] = group_col

            # PHASE 1: PREPROCESS DATA - Analyze data characteristics
            # Only preprocess for standard chart types (not comparison charts)
            if chart_type != "comparison" and x_col and y_col:
                logger.info(f"Preprocessing data for {chart_type} chart (x={x_col}, y={y_col})")
                preprocessing_result = DataPreprocessor.preprocess_for_chart(
                    data=data,
                    chart_type=chart_type,
                    x_col=x_col,
                    y_col=y_col,
                    params=params
                )

                # Update data with processed version (may include moving averages)
                data = preprocessing_result["data"]

                # Extract metadata and recommendations
                metadata = preprocessing_result.get("metadata", {})
                recommendations = preprocessing_result.get("recommendations", {})
                annotations = preprocessing_result.get("annotations", [])

                logger.info(f"Data analysis: sparse={metadata.get('is_sparse')}, "
                           f"variance={metadata.get('variance_level')}, "
                           f"gaps={metadata.get('has_gaps')}")

                # PHASE 2: OPTIMIZE LAYOUT - Calculate optimal layout parameters
                logger.info("Calculating optimal layout parameters")
                layout_config = LayoutOptimizer.optimize_layout(
                    data=data,
                    chart_type=chart_type,
                    x_col=x_col,
                    y_col=y_col,
                    metadata=metadata
                )

                # Add preprocessing results to params for PlotlyBuilder
                params["metadata"] = metadata
                params["recommendations"] = recommendations
                params["annotations"] = annotations
                params["layout_config"] = layout_config

                logger.info(f"Layout optimized: height={layout_config.get('height')}, "
                           f"x_rotation={layout_config.get('xaxis', {}).get('tickangle')}")

                # OVERRIDE: If preprocessor recommends bar chart (e.g., for count metrics), use it
                if recommendations.get("prefer_bar_chart") and chart_type == "line":
                    logger.info(f"Overriding chart type: line → bar (count metric detected: {y_col})")
                    chart_type = "bar"

            # Generate smart title
            params["title"] = ChartHelper.generate_chart_title(
                intent=str(intent),
                entities=entities,
                metrics=entities.get("metrics", []),
                data_cols=data.columns.tolist()
            )

            # Generate chart
            chart_spec = PlotlyBuilder.generate_chart(data, chart_type, params)

            state["visualization_spec"] = chart_spec

            logger.info(f"Chart generated: {chart_type}")
            state["thinking_message"] = f"Chart created ({chart_type})"
            self._emit_progress(state, "visualize", f"Chart created ({chart_type})")

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
        self._emit_progress(state, "respond", "✍️ Writing response...")

        logger.info("RESPOND: Generating natural language response")

        try:
            # Check for clarification needed (player disambiguation, etc.)
            if state.get("needs_clarification"):
                clarification_q = state.get("clarification_question", "Could you provide more details?")
                state["natural_language_summary"] = clarification_q
                state["confidence"] = 0.5
                return state

            # Check for errors
            if state.get("execution_error"):
                error_detail = state.get("execution_error", "Unknown error")
                logger.error(f"RESPOND node detected execution_error: {error_detail}")

                # Include error details for debugging (helps diagnose deployment issues)
                state["natural_language_summary"] = (
                    f"I encountered an issue while analyzing your query.\n\n"
                    f"**Debug info:** {error_detail}\n\n"
                    f"Please check your query or try rephrasing."
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

                suggestion_text = " ".join(suggestions) if suggestions else (
                    "Try rephrasing your question or check that team/player names are correct."
                )

                state["natural_language_summary"] = (
                    f"I couldn't find any data matching your query. {suggestion_text}"
                )
                state["confidence"] = 0.3
                return state

            # Check if results are all NULL (query succeeded but no data for that filter)
            data = state["query_results"]

            # Check if ALL columns are NULL (indicates no data for this query)
            all_null = data.isnull().all().all() if len(data) > 0 else False
            logger.info(f"NULL check: len(data)={len(data)}, all_null={all_null}, data=\n{data}")

            if all_null:
                # All columns are NULL - no data exists for this query
                entities = state.get("entities", {})
                players = entities.get("players", [])
                seasons = entities.get("seasons", [])

                # Build helpful message
                if players and seasons:
                    player_name = players[0] if players else "this player"
                    season = seasons[0] if seasons else "this season"

                    state["natural_language_summary"] = (
                        f"I couldn't find any data for {player_name} in {season}. "
                        f"Player statistics are available for most seasons from 1990-2023 (excluding 1994, 2017, 2024) "
                        f"and partial 2025 data. Try asking about a different season or player."
                    )
                else:
                    state["natural_language_summary"] = (
                        "I found matching records but they don't contain any data values. "
                        "Try asking about a different time period or entity."
                    )

                state["confidence"] = 0.4
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

            # Build conversation context for continuity
            conversation_context_text = ""
            conversation_history = state.get("conversation_history", [])

            if conversation_history and len(conversation_history) > 0:
                recent_messages = conversation_history[-4:]  # Last 2 exchanges

                conversation_context_text = "\n\n## Previous Conversation\n"
                for msg in recent_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")[:200]  # Truncate long messages

                    if role == "user":
                        conversation_context_text += f"User: {content}\n"
                    elif role == "assistant":
                        conversation_context_text += f"Assistant: {content}\n"

                conversation_context_text += "\nYour response should build on this conversation naturally.\n---\n"

            # Determine response style based on analysis mode
            analysis_mode = state.get("analysis_mode", "summary")
            intent = state.get("intent")

            # Format query results - show more data for round-by-round or breakdown queries
            # These queries need full data to generate accurate summaries
            query_lower = state['user_query'].lower()
            is_breakdown_query = any(term in query_lower for term in ['by round', 'round by round', 'each round', 'per round', 'breakdown', 'by game', 'by match'])

            results_df = state['query_results']
            if is_breakdown_query or len(results_df) <= 50:
                # Show all results for breakdown queries or smaller result sets
                results_text = results_df.to_string()
            elif len(results_df) <= 100:
                # For medium result sets, show first 50
                results_text = results_df.head(50).to_string() + f"\n... ({len(results_df)} total rows)"
            else:
                # For large result sets, show first 30 with note
                results_text = results_df.head(30).to_string() + f"\n... ({len(results_df)} total rows)"

            # Capability constraints to prevent hallucinations
            capability_constraints = """
SYSTEM CAPABILITIES (be honest about what you can and cannot do):
✓ CAN DO: Query AFL statistics from the database (1990-2025), show match results, player stats, team performance
✓ CAN DO: Generate visualizations and charts displayed in the chat interface
✓ CAN DO: Compare players, teams, and seasons
✓ CAN DO: Answer questions about historical AFL data

✗ CANNOT DO: Export data to CSV, Excel, or any file format
✗ CANNOT DO: Download or email reports
✗ CANNOT DO: Access live/real-time data or external websites
✗ CANNOT DO: Make predictions about future games
✗ CANNOT DO: Access data outside of AFL statistics (no other sports, no betting odds)

NEVER claim you can do something not listed above. If asked about unsupported features, politely explain what IS possible instead.
"""

            # Build prompt based on mode
            if analysis_mode == "summary" or intent == QueryIntent.SIMPLE_STAT:
                # SUMMARY MODE: Direct, concise answers
                prompt = f"""You are an AFL analytics expert. Answer the user's question directly and concisely.

{capability_constraints}

CRITICAL RULES for simple stat queries:
- Answer in 1-2 sentences MAX
- State the number/fact directly
- DO NOT mention what additional analysis you could do
- DO NOT mention limitations or missing data unless the query CANNOT be answered
- DO NOT offer follow-up analysis unprompted
- Just answer the question asked, nothing more

{conversation_context_text}User asked: {state['user_query']}

Query results:
{results_text}

Provide a direct, concise answer (1-2 sentences):"""

            else:
                # Check if we're showing a chart
                has_chart = state.get("visualization_spec") is not None

                if has_chart:
                    # CHART MODE: Very brief text, let the chart do the talking
                    prompt = f"""You are an AFL analytics expert. A chart is being displayed to the user.

{capability_constraints}

CRITICAL: Keep your response VERY SHORT (2-3 sentences max).
- Briefly state what the chart shows
- Mention 1-2 key insights or standout data points
- Do NOT describe every data point - the chart shows that
- Do NOT write paragraphs of analysis

{conversation_context_text}User query: {state['user_query']}

Key stats: {stats_summary}

Write a brief 2-3 sentence summary to accompany the chart:"""
                else:
                    # IN-DEPTH MODE: Concise but informative analysis
                    prompt = f"""You are an AFL analytics expert. Provide a focused analysis of the query results.

{capability_constraints}

Guidelines:
- Keep response to 3-5 sentences MAX
- Lead with the key finding or answer
- Include 2-3 specific numbers that matter most
- Mention one interesting insight or pattern
- Use Australian football terminology correctly
- Never mention SQL, databases, or technical details
- Be conversational but concise

{conversation_context_text}Current user query: {state['user_query']}

Query results:
{results_text}

Statistical Insights:
{stats_summary}{context_text}

Provide a concise analysis (3-5 sentences):"""

            # Generate response using GPT-5-nano (Responses API)
            response = client.responses.create(
                model="gpt-5-nano",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            state["natural_language_summary"] = response.output_text.strip()
            state["confidence"] = 0.9
            state["sources"] = ["AFL Tables (1990-2025)"]
            state["thinking_message"] = "Response complete"
            self._emit_progress(state, "respond", "Response complete")

            logger.info("Response generated successfully")

        except Exception as e:
            logger.error(f"Error in RESPOND node: {e}")
            state["natural_language_summary"] = "I encountered an issue generating the response."
            state["confidence"] = 0.0
            state["errors"].append(f"Response error: {str(e)}")

        return state


# Global agent instance
agent = AFLAnalyticsAgent()
