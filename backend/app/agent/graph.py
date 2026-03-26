"""
AFL Analytics Agent - LangGraph Workflow

Defines the agent workflow: UNDERSTAND → ANALYZE_DEPTH → PLAN → EXECUTE → VISUALIZE → RESPOND
"""
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from openai import OpenAI
import httpx
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

# Import config for model selection
from app.config import get_config
config_obj = get_config()

# Initialize OpenAI client with timeout for production reliability
# 60s total timeout, 10s connect timeout
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(60.0, connect=10.0)
)


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

        # ── Fast-path: answer simple queries without any LLM calls ──────────
        from app.agent.fast_path import FastPathRouter
        fast_result = FastPathRouter.try_fast_path(
            user_query=user_query,
            conversation_history=conversation_history,
            socketio_emit=socketio_emit,
        )
        if fast_result is not None:
            fast_result["conversation_id"] = conversation_id
            logger.info(f"FAST-PATH answered: {user_query[:60]}")
            return fast_result
        # ────────────────────────────────────────────────────────────────────

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

            # ── Consolidated single LLM call: intent + entities + SQL ──────────
            # This replaces both the old standalone intent call here AND the
            # QueryBuilder.generate_sql() call in execute_node, saving one
            # full OpenAI round-trip per query.
            from app.agent.consolidated_llm import ConsolidatedQueryUnderstanding
            logger.info("UNDERSTAND: Calling consolidated LLM (intent + SQL in one call)...")

            consolidated = ConsolidatedQueryUnderstanding.understand_and_generate_sql(
                user_query=state["user_query"],
                conversation_history=conversation_history,
            )

            if consolidated["success"]:
                # Off-topic detection — LLM classified as non-AFL query
                # But check if this is a follow-up to a previous tool-based query
                if consolidated["intent"] == "off_topic":
                    # Tool-based intents that support follow-up questions
                    TOOL_INTENTS = {"injury_news", "afl_news", "tipping_advice", "betting_odds"}

                    # Check conversation history for context
                    previous_tool_intent = None
                    if conversation_history:
                        for msg in reversed(conversation_history[-4:]):
                            if msg.get("role") == "assistant":
                                prev_intent = msg.get("intent", "")
                                # Check if previous intent was a tool-based intent
                                if prev_intent in TOOL_INTENTS:
                                    previous_tool_intent = prev_intent
                                    break

                    if previous_tool_intent:
                        # This looks like a follow-up - use the same intent type
                        logger.info(f"UNDERSTAND: Detected follow-up to {previous_tool_intent}, overriding off_topic")
                        consolidated["intent"] = previous_tool_intent
                        consolidated["sql"] = None
                    else:
                        logger.info("UNDERSTAND: LLM flagged query as off-topic")
                        from app.data.database import get_data_recency
                        recency = get_data_recency()
                        earliest = recency["earliest_season"]
                        hist_season = recency["historical_latest_season"]
                        state["needs_clarification"] = True
                        state["clarification_question"] = (
                            f"That doesn't seem to be an AFL question. I can help with Australian Football League "
                            f"statistics and data from {earliest} to {hist_season}, including match results, player stats, "
                            f"team performance, betting odds, and tipping predictions.\n\n"
                            f"Try something like: \"How many goals did Hawkins kick in 2024?\" or "
                            f"\"What are the odds for this week's games?\""
                        )
                        return state

                understanding = {
                    "intent": consolidated["intent"],
                    "entities": consolidated["entities"],
                    "requires_visualization": consolidated["requires_visualization"],
                }
                # Store the pre-generated SQL so execute_node skips its own SQL call
                state["pre_generated_sql"] = consolidated["sql"]
                # Store chart hints for visualize_node (avoids separate chart LLM call)
                state["llm_chart_type_hint"] = consolidated.get("chart_type")
                state["llm_chart_config_hint"] = consolidated.get("chart_config", {})
                sql_preview = consolidated['sql'][:60] if consolidated['sql'] else "(no SQL needed)"
                logger.info(
                    f"UNDERSTAND: Consolidated call OK — intent={consolidated['intent']}, "
                    f"chart_hint={consolidated.get('chart_type')}, "
                    f"sql_preview={sql_preview}..."
                )
            else:
                # Consolidated call failed — use lightweight heuristic intent instead of another LLM call
                logger.warning(
                    f"UNDERSTAND: Consolidated call failed ({consolidated['error']}), "
                    f"using heuristic intent classification"
                )

                query_lower = state["user_query"].lower()
                import re as _re

                # Heuristic intent classification
                # Check tool-based intents first (no SQL needed)
                if any(kw in query_lower for kw in ["tip", "predict", "who will win", "who's going to win", "who should i"]):
                    heuristic_intent = "tipping_advice"
                    heuristic_viz = False
                elif any(kw in query_lower for kw in ["odds", "betting", "bet on", "favourite", "favorite"]):
                    heuristic_intent = "betting_odds"
                    heuristic_viz = False
                elif any(kw in query_lower for kw in ["injur", "out this week", "ruled out", "hamstring", "knee"]):
                    heuristic_intent = "injury_news"
                    heuristic_viz = False
                elif any(kw in query_lower for kw in ["news", "latest", "headlines", "article"]):
                    heuristic_intent = "afl_news"
                    heuristic_viz = False
                # Database query intents
                elif any(kw in query_lower for kw in ["over time", "across time", "trend", "historical", "evolution", "year by year", "since"]):
                    heuristic_intent = "trend_analysis"
                    heuristic_viz = True
                elif any(kw in query_lower for kw in ["compare", " vs ", "versus", "against"]):
                    heuristic_intent = "player_comparison"
                    heuristic_viz = True
                elif any(kw in query_lower for kw in ["performance", "record", "season", "how did"]):
                    heuristic_intent = "team_analysis"
                    heuristic_viz = True
                else:
                    heuristic_intent = "simple_stat"
                    heuristic_viz = False

                # Extract years with regex
                years = _re.findall(r'\b((?:19|20)\d{2})\b', state["user_query"])

                understanding = {
                    "intent": heuristic_intent,
                    "entities": {
                        "teams": [],
                        "players": [],
                        "seasons": years,
                        "metrics": [],
                        "rounds": []
                    },
                    "requires_visualization": heuristic_viz,
                }
                # No pre_generated_sql — execute_node will call QueryBuilder as before

            logger.info(f"UNDERSTAND: Parsed understanding: intent={understanding.get('intent')}, entities={understanding.get('entities')}")

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
            import traceback
            tb = traceback.format_exc()
            logger.error(f"UNDERSTAND: Exception caught: {type(e).__name__}: {str(e)}")
            logger.error(f"UNDERSTAND: Exception details: {repr(e)}")
            logger.error(f"UNDERSTAND: Full traceback:\n{tb}")
            # Check for specific OpenAI errors
            if hasattr(e, 'status_code'):
                logger.error(f"UNDERSTAND: OpenAI status_code: {e.status_code}")
            if hasattr(e, 'response'):
                logger.error(f"UNDERSTAND: OpenAI response: {e.response}")
            state["errors"].append(f"Understanding error: {type(e).__name__}")

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

        # Only emit progress for in-depth queries (summary queries are too fast to show)
        if analysis_mode == "in_depth":
            self._emit_progress(state, "analyze_depth", "Analyzing query complexity...")

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

        intent = state.get('intent', QueryIntent.SIMPLE_STAT)

        # Only emit progress for non-simple intents
        if intent != QueryIntent.SIMPLE_STAT:
            self._emit_progress(state, "plan", "Planning the analysis...")
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
            state["errors"].append(f"Planning error: {type(e).__name__}")

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
        intent = state.get("intent")

        # Route to appropriate tool based on intent
        # NEWS QUERIES
        if intent in [QueryIntent.AFL_NEWS, QueryIntent.INJURY_NEWS]:
            from app.agent.tools import NewsTool

            state["thinking_message"] = "📰 Searching for AFL news..."
            self._emit_progress(state, "execute", "📰 Searching for AFL news...")

            teams = state.get("entities", {}).get("teams", [])
            filters = {
                'injury_only': intent == QueryIntent.INJURY_NEWS,
                'teams': teams,
                'days_back': 7
            }

            # Don't pass user's raw query as search text - team filters are sufficient
            # Passing "any Sydney injuries?" would require exact text match which won't work
            search_query = ""  # Let team and injury filters do the work
            result = NewsTool.search_news(search_query, filters, max_results=5)
            state["query_results"] = result.get("articles", [])
            state["requires_visualization"] = False
            state["thinking_message"] = f"Found {len(state['query_results'])} news articles"
            self._emit_progress(state, "execute", state["thinking_message"])
            return state

        # BETTING ODDS
        elif intent == QueryIntent.BETTING_ODDS:
            from app.agent.tools import BettingTool

            state["thinking_message"] = "💰 Fetching betting odds..."
            self._emit_progress(state, "execute", "💰 Fetching betting odds...")

            entities = state.get("entities", {})
            result = BettingTool.get_odds(
                team_name=entities.get("teams", [None])[0] if entities.get("teams") else None,
                round_num=entities.get("rounds", [None])[0] if entities.get("rounds") else None,
                season=entities.get("seasons", [None])[0] if entities.get("seasons") else None
            )
            state["query_results"] = result.get("matches", [])
            state["requires_visualization"] = False
            state["thinking_message"] = f"Found odds for {len(state['query_results'])} matches"
            self._emit_progress(state, "execute", state["thinking_message"])
            return state

        # TIPPING ADVICE
        elif intent == QueryIntent.TIPPING_ADVICE:
            from app.agent.tools import TippingTool

            state["thinking_message"] = "🎯 Getting tipping predictions..."
            self._emit_progress(state, "execute", "🎯 Getting tipping predictions...")

            entities = state.get("entities", {})
            result = TippingTool.get_tips(
                teams=entities.get("teams"),
                round_num=entities.get("rounds", [None])[0] if entities.get("rounds") else None,
                season=entities.get("seasons", [None])[0] if entities.get("seasons") else None
            )
            state["query_results"] = result.get("predictions", [])
            state["requires_visualization"] = False
            state["thinking_message"] = f"Found predictions for {len(state['query_results'])} matches"
            self._emit_progress(state, "execute", state["thinking_message"])
            return state

        # DATABASE QUERIES (existing flow)
        state["thinking_message"] = "🔨 Generating SQL query..."
        self._emit_progress(state, "execute", "🔨 Generating SQL query...")

        logger.info("EXECUTE: Generating and running SQL query")

        try:
            # Step 1: Get SQL — use pre-generated SQL from consolidated LLM call if available,
            # otherwise generate via QueryBuilder (fallback to separate LLM call).
            pre_sql = state.get("pre_generated_sql")
            if pre_sql:
                logger.info(f"EXECUTE: Using pre-generated SQL from consolidated call: {pre_sql[:80]}...")
                sql_result = {"success": True, "sql": pre_sql, "error": None}
            else:
                logger.info(f"EXECUTE: Calling QueryBuilder.generate_sql with query='{state['user_query'][:100]}', entities={state.get('entities')}")
                sql_result = QueryBuilder.generate_sql(
                    state["user_query"],
                    context=state["entities"],  # These are now validated/normalized
                    conversation_history=state.get("conversation_history", [])
                )
                logger.info(f"EXECUTE: SQL generation result: success={sql_result.get('success')}, error={sql_result.get('error')}")

            if not sql_result["success"]:
                error_msg = f"SQL generation failed: {sql_result['error']}"
                logger.error(f"EXECUTE: {error_msg}")
                state["execution_error"] = error_msg
                state["errors"].append(error_msg)
                state["thinking_message"] = "Couldn't process that query, retrying..."
                return state

            state["sql_query"] = sql_result["sql"]

            # Fix common LLM SQL mistake: ILIKE 'Name%' should be ILIKE '%Name%'
            # because player names are stored as "First Last"
            import re as _re
            state["sql_query"] = _re.sub(
                r"ILIKE\s+'([^%'])",
                r"ILIKE '%\1",
                state["sql_query"]
            )

            logger.info(f"Generated SQL: {state['sql_query']}")

            # Step 2: Execute query (check cache first)
            from app.utils.cache import get_cached_result, set_cached_result
            cached = get_cached_result(state["sql_query"])
            if cached is not None:
                logger.info("EXECUTE: Returning cached query result")
                state["sql_validated"] = True
                state["query_results"] = cached
                state["thinking_message"] = f"Found {len(cached)} results (cached)"
                self._emit_progress(state, "execute", f"Found {len(cached)} results")
            else:
                state["thinking_message"] = "⚡ Querying AFL database (6,243 matches)..."
                self._emit_progress(state, "execute", "⚡ Querying AFL database (6,243 matches)...")
                logger.info(f"EXECUTE: Calling DatabaseTool.query_database with SQL: {state['sql_query'][:200]}...")
                db_result = DatabaseTool.query_database(state["sql_query"])
                logger.info(f"EXECUTE: Database query result: success={db_result.get('success')}, rows={db_result.get('rows_returned')}, error={db_result.get('error')}")

                if not db_result["success"]:
                    error_msg = f"Database query failed: {db_result['error']}"
                    logger.error(f"{error_msg} | SQL: {state.get('sql_query', 'N/A')}")
                    state["execution_error"] = error_msg
                    state["errors"].append(error_msg)
                    state["thinking_message"] = "Couldn't retrieve data, retrying..."
                    return state

                state["sql_validated"] = True
                state["query_results"] = db_result["data"]
                set_cached_result(state["sql_query"], db_result["data"])

                logger.info(f"Query returned {db_result['rows_returned']} rows")
                state["thinking_message"] = f"Found {db_result['rows_returned']} results"
                self._emit_progress(state, "execute", f"Found {db_result['rows_returned']} results")

            # Step 3: Compute statistics if needed
            if len(state["query_results"]) > 0 and state.get("intent") != QueryIntent.SIMPLE_STAT:
                state["thinking_message"] = "Calculating statistics..."
                self._emit_progress(state, "execute", "Calculating statistics...")

                # Get analysis types from analyze_depth node
                analysis_types = state.get("analysis_types", ["average"])
                combined_stats = {"success": True, "mode": state.get("analysis_mode", "summary")}

                # Run all requested analysis types
                for analysis_type in analysis_types:
                    logger.info(f"Running {analysis_type} analysis")
                    stats_result = StatisticsTool.compute_statistics(
                        state["query_results"],
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
                                data=state["query_results"],
                                season=season
                            )

                            # Calculate efficiency metrics
                            efficiency = EfficiencyCalculator.calculate_all_efficiency_metrics(
                                state["query_results"]
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
            state["thinking_message"] = "Couldn't process that query, retrying..."

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

            # FIX ROUND ORDERING: round is VARCHAR so SQL sorts lexicographically.
            # Sort numerics first (ascending), then finals in correct AFL order.
            if "round" in data.columns:
                _FINALS_ORDER = {
                    "Qualifying Final": 100, "Elimination Final": 101,
                    "Semi Final": 102, "Preliminary Final": 103, "Grand Final": 104,
                }
                def _round_sort_key(r):
                    r_str = str(r).strip()
                    if r_str in _FINALS_ORDER:
                        return _FINALS_ORDER[r_str]
                    try:
                        return int(r_str)
                    except ValueError:
                        return 999
                data = data.iloc[data["round"].map(_round_sort_key).argsort()].reset_index(drop=True)
                state["query_results"] = data

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
                entities=entities,
                llm_chart_type_hint=state.get("llm_chart_type_hint"),
                llm_chart_config_hint=state.get("llm_chart_config_hint", {}),
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

            # AUTO-AGGREGATE: If charting by season but data has multiple rows per season
            # (e.g., per-game stats for a career trend), aggregate to season averages.
            # This prevents spaghetti charts with 300+ individual game data points.
            if (chart_type == "line" and x_col == "season" and isinstance(y_col, str)
                    and x_col in data.columns and y_col in data.columns):
                rows_per_season = len(data) / max(data["season"].nunique(), 1)
                if rows_per_season > 2:
                    agg_cols = {y_col: "mean"}
                    # Also aggregate other numeric columns for tooltip context
                    for nc in data.select_dtypes(include=["number"]).columns:
                        if nc != "season" and nc != y_col and "id" not in nc.lower():
                            agg_cols[nc] = "mean"
                    group_keys = ["season"]
                    if group_col and group_col in data.columns:
                        group_keys.append(group_col)
                    data = data.groupby(group_keys, as_index=False).agg(agg_cols)
                    # Round averages for readability
                    for c in agg_cols:
                        if c in data.columns:
                            data[c] = data[c].round(1)
                    state["query_results"] = data
                    logger.info(f"VISUALIZE: Aggregated per-game data to season averages ({len(data)} rows)")

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
                # BUT skip for temporal/sequential x-axes — line charts are correct for
                # round-by-round or season-by-season progression even with count metrics.
                temporal_x_cols = {"round", "season", "year", "match_date", "date", "round_number", "round_num"}
                x_is_temporal = x_col and x_col.lower().strip() in temporal_x_cols
                if recommendations.get("prefer_bar_chart") and chart_type == "line" and not x_is_temporal:
                    logger.info(f"Overriding chart type: line → bar (count metric detected: {y_col})")
                    chart_type = "bar"
                elif recommendations.get("prefer_bar_chart") and chart_type == "line" and x_is_temporal:
                    logger.info(f"Keeping line chart despite count metric ({y_col}) — x-axis is temporal ({x_col})")

            # Generate smart title (pass x/y_col so the title uses the actual plotted axes)
            params["title"] = ChartHelper.generate_chart_title(
                intent=str(intent),
                entities=entities,
                metrics=entities.get("metrics", []),
                data_cols=data.columns.tolist(),
                y_col=y_col if isinstance(y_col, str) else None,
                x_col=x_col if isinstance(x_col, str) else None
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
            state["thinking_message"] = "Skipping chart generation"

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

    @staticmethod
    def _try_template_response(state: AgentState) -> Optional[str]:
        """
        Try to generate a response from templates without an LLM call.

        Returns a response string, or None to fall through to LLM.

        Handles:
        - Single-row simple_stat results (1 fact/number)
        - Top-N list results (ranking tables)
        - Chart-accompaniment one-liners
        """
        intent = state.get("intent")
        data = state.get("query_results")
        entities = state.get("entities", {})
        has_chart = state.get("visualization_spec") is not None
        analysis_mode = state.get("analysis_mode", "summary")

        teams = entities.get("teams", [])
        players = entities.get("players", [])
        seasons = entities.get("seasons", [])

        # Handle empty results for tool-based intents with helpful messages
        if data is None or len(data) == 0:
            if intent in [QueryIntent.AFL_NEWS, QueryIntent.INJURY_NEWS]:
                if teams:
                    team_str = " or ".join(teams)
                    if intent == QueryIntent.INJURY_NEWS:
                        return f"I don't have any recent injury news for {team_str}. No major injuries reported in my current news feed."
                    return f"I don't have any recent news about {team_str} in my current feed."
                return "I couldn't find any recent news matching your query."
            if intent == QueryIntent.BETTING_ODDS:
                return "I couldn't find betting odds for those matches. Odds may not be available yet."
            if intent == QueryIntent.TIPPING_ADVICE:
                return "I don't have predictions available for those matches yet."
            # Check if user asked about remaining/upcoming games
            query_lower = state.get("user_query", "").lower()
            remaining_keywords = ["left", "remaining", "upcoming", "scheduled", "still to play", "yet to play"]
            if any(kw in query_lower for kw in remaining_keywords):
                return "All games this round have been completed — no remaining games to play."
            return None

        # Complex in-depth queries without charts still use LLM
        if analysis_mode == "in_depth" and not has_chart:
            return None

        # --- NEWS RESPONSE ---
        if intent in [QueryIntent.AFL_NEWS, QueryIntent.INJURY_NEWS]:
            if not data:
                return "I couldn't find any recent news matching your query."

            # Injury news — use pre-extracted injury details from ingestion
            if intent == QueryIntent.INJURY_NEWS:
                injury_lines = []
                for a in data[:5]:
                    if a.get('injury_details'):
                        for inj in a['injury_details']:
                            player = inj.get('player', 'Unknown')
                            inj_type = inj.get('type', 'unknown injury')
                            severity = inj.get('severity', '')
                            severity_str = f" ({severity})" if severity else ""
                            injury_lines.append(f"- {player}: {inj_type}{severity_str}")
                    elif a.get('summary'):
                        injury_lines.append(f"- {a['summary']}")
                if injury_lines:
                    return "Recent injury news:\n" + "\n".join(injury_lines)
                return "No specific injuries reported in recent news."

            # General AFL news — use LLM-generated summaries
            lines = []
            for a in data[:3]:
                summary = a.get('summary') or a.get('title', '')
                lines.append(f"- {summary}")
            return "Latest AFL news:\n" + "\n".join(lines)

        # --- BETTING ODDS RESPONSE ---
        if intent == QueryIntent.BETTING_ODDS:
            if not data:
                return "I couldn't find betting odds for the specified matches."

            lines = []
            for match in data[:7]:
                home_odds = match.get('home_odds')
                away_odds = match.get('away_odds')

                lines.append(f"\n**{match['home_team']} vs {match['away_team']}**")
                lines.append(f"📅 {match['match_date'][:10]} • Round {match['round']} • {match['venue']}")

                if home_odds and away_odds:
                    # Determine favourite
                    if home_odds < away_odds:
                        fav = match['home_team']
                        fav_odds = home_odds
                    else:
                        fav = match['away_team']
                        fav_odds = away_odds
                    lines.append(f"  💰 {match['home_team']} ${home_odds:.2f} | {match['away_team']} ${away_odds:.2f}")
                    lines.append(f"  ⭐ Favourite: {fav}")
                else:
                    lines.append("  Odds not yet available")

            return "Current betting odds:\n" + "\n".join(lines)

        # --- TIPPING ADVICE RESPONSE ---
        if intent == QueryIntent.TIPPING_ADVICE:
            if not data:
                return "I don't have predictions available for those matches."

            lines = []
            for pred in data[:5]:
                match = pred['match']
                prediction = pred['prediction']

                winner = prediction.get('predicted_winner', 'Unknown')
                margin = prediction.get('predicted_margin', 0)
                prob = prediction.get('home_win_probability', 50)

                # Determine if home or away team is predicted winner
                is_home_winner = prob > 50
                confidence_pct = prob if is_home_winner else (100 - prob)

                lines.append(
                    f"**{match['home_team']} vs {match['away_team']}**\n"
                    f"  💡 Tip: **{winner}** by {abs(margin):.1f} points\n"
                    f"  📊 Confidence: {confidence_pct:.0f}%\n"
                    f"  📅 {match['match_date'][:10]} • Round {match['round']}"
                )

            return "Tipping recommendations from Squiggle:\n\n" + "\n\n".join(lines)

        # --- PATTERN 1: Single-row result (simple_stat) ---
        if intent == QueryIntent.SIMPLE_STAT and len(data) == 1:
            row = data.iloc[0]

            # Special case: Match result (has winner, home_team, away_team, scores)
            if 'winner' in data.columns and 'home_team' in data.columns and 'away_team' in data.columns:
                home_team = row['home_team']
                away_team = row['away_team']
                home_score = int(row['home_score']) if 'home_score' in row else 0
                away_score = int(row['away_score']) if 'away_score' in row else 0
                winner = row['winner']
                margin = int(row['margin']) if 'margin' in row else abs(home_score - away_score)
                venue = row['venue'] if 'venue' in row else ''
                round_str = row['round'] if 'round' in row else ''

                venue_text = f" at {venue}" if venue else ""
                round_text = f" (Round {round_str})" if round_str else ""

                return f"{winner} defeated {away_team if winner == home_team else home_team} {max(home_score, away_score)}-{min(home_score, away_score)} by {margin} points{venue_text}{round_text}."

            numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
            # Check for name columns in the result (player_name, winner, team, name)
            name_cols = [c for c in data.columns if c.lower() in ['name', 'player', 'player_name', 'team', 'team_name', 'winner']]

            def _fmt_val(v):
                if isinstance(v, float) and v == int(v):
                    return str(int(v))
                elif isinstance(v, float):
                    return f"{v:.1f}"
                return str(v)

            if len(numeric_cols) == 1:
                col = numeric_cols[0]
                value = row[col]
                col_label = col.replace("_", " ")

                # Try to get subject from: 1) name column in result, 2) entities, 3) empty
                subject = ""
                if name_cols:
                    subject = str(row[name_cols[0]])
                elif players:
                    subject = players[0]
                elif teams:
                    subject = teams[0]

                season_str = f" in {seasons[0]}" if seasons else ""

                if subject:
                    return f"{subject} had {_fmt_val(value)} {col_label}{season_str}."
                else:
                    return f"The result is {_fmt_val(value)} {col_label}{season_str}."

            elif 2 <= len(numeric_cols) <= 5:
                # Try to get subject from: 1) name column in result, 2) entities, 3) empty
                subject = ""
                if name_cols:
                    subject = str(row[name_cols[0]])
                elif players:
                    subject = players[0]
                elif teams:
                    subject = teams[0]

                season_str = f" in {seasons[0]}" if seasons else ""
                parts = []
                for col in numeric_cols:
                    parts.append(f"{_fmt_val(row[col])} {col.replace('_', ' ')}")
                stats_str = ", ".join(parts)
                if subject:
                    return f"{subject}{season_str}: {stats_str}."
                else:
                    return f"Results{season_str}: {stats_str}."

        # --- PATTERN 1.5: Multiple rows (2-20 rows) — format as markdown tables ---
        if 2 <= len(data) <= 20:
            # Match results with winner/scores → markdown table
            if 'winner' in data.columns and 'home_team' in data.columns and 'away_team' in data.columns:
                lines = ["| Winner | Score | Loser | Margin | Venue |", "|--------|-------|-------|--------|-------|"]
                for _, row in data.iterrows():
                    home_team = row['home_team']
                    away_team = row['away_team']
                    home_score = int(row['home_score']) if 'home_score' in row else 0
                    away_score = int(row['away_score']) if 'away_score' in row else 0
                    winner = row['winner']
                    loser = away_team if winner == home_team else home_team
                    margin = int(row['margin']) if 'margin' in row else abs(home_score - away_score)
                    venue = row['venue'] if 'venue' in row else ''
                    lines.append(f"| {winner} | {max(home_score, away_score)}-{min(home_score, away_score)} | {loser} | {margin} | {venue} |")

                return "\n".join(lines)

            # Fixture/upcoming games (has teams but no scores AND no other stat columns)
            if 'home_team' in data.columns and 'away_team' in data.columns:
                has_scores = 'home_score' in data.columns and data['home_score'].notna().any() and (data['home_score'] != 0).any()
                # Only use fixture format if there are no meaningful stat columns
                stat_numeric = [c for c in data.select_dtypes(include=['number']).columns
                                if 'id' not in c.lower() and c not in ('season', 'year')]
                if not has_scores and not stat_numeric:
                    header_cols = ["Match", "Date", "Venue", "Round"]
                    lines = ["| " + " | ".join(header_cols) + " |", "| " + " | ".join(["---"] * len(header_cols)) + " |"]
                    for _, row in data.iterrows():
                        match_str = f"{row['home_team']} vs {row['away_team']}"
                        date_str = str(row.get('match_date', ''))[:10] if 'match_date' in row.index else ''
                        venue_str = str(row.get('venue', '')) if 'venue' in row.index else ''
                        round_str = str(row.get('round', '')) if 'round' in row.index else ''
                        lines.append(f"| {match_str} | {date_str} | {venue_str} | {round_str} |")
                    return "\n".join(lines)

            name_cols = [c for c in data.columns if c.lower() in ['name', 'player', 'player_name', 'team', 'winner']]
            numeric_cols = data.select_dtypes(include=['number']).columns.tolist()
            # Filter out ID columns
            numeric_cols = [c for c in numeric_cols if 'id' not in c.lower()]

            if name_cols and numeric_cols:
                name_col = name_cols[0]
                season_str = f" in {seasons[0]}" if seasons else ""

                # Detect team column for context
                team_col = next((c for c in data.columns if c.lower() == 'team' and c != name_col), None)

                # Build markdown table with all numeric columns
                display_cols = [name_col]
                if team_col:
                    display_cols.append(team_col)
                display_cols.extend(numeric_cols)

                headers = [c.replace("_", " ").title() for c in display_cols]
                lines = ["| # | " + " | ".join(headers) + " |", "| --- | " + " | ".join(["---"] * len(headers)) + " |"]

                for i, (_, row) in enumerate(data.iterrows()):
                    vals = []
                    for c in display_cols:
                        v = row[c]
                        if isinstance(v, float) and v == int(v):
                            vals.append(str(int(v)))
                        elif isinstance(v, float):
                            vals.append(f"{v:.1f}")
                        else:
                            vals.append(str(v))
                    lines.append(f"| {i+1} | " + " | ".join(vals) + " |")

                metric_label = numeric_cols[0].replace("_", " ")
                header = f"Top {metric_label}{season_str}:\n\n"
                return header + "\n".join(lines)

            # Fallback: any multi-row DataFrame with 3+ columns → auto markdown table
            if len(data.columns) >= 3:
                cols = [c for c in data.columns if 'id' not in c.lower()]
                # Drop columns that are entirely empty/null/blank
                cols = [c for c in cols if not (data[c].isna().all() or (data[c].astype(str).str.strip() == '').all())]
                # Merge home_team + away_team into a single "Match" column if both exist
                has_match_merge = 'home_team' in cols and 'away_team' in cols
                if has_match_merge:
                    cols = [c for c in cols if c not in ('home_team', 'away_team')]
                    cols.insert(0, '_match')
                # Truncate long timestamps to date only
                date_cols = [c for c in cols if 'date' in c.lower()]
                if cols:
                    headers = []
                    for c in cols:
                        if c == '_match':
                            headers.append("Match")
                        else:
                            headers.append(c.replace("_", " ").title())
                    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
                    for _, row in data.iterrows():
                        vals = []
                        for c in cols:
                            if c == '_match':
                                vals.append(f"{row['home_team']} vs {row['away_team']}")
                            elif c in date_cols:
                                vals.append(str(row[c])[:10])
                            else:
                                v = row[c]
                                if isinstance(v, float) and v == int(v):
                                    vals.append(str(int(v)))
                                elif isinstance(v, float):
                                    vals.append(f"{v:.1f}")
                                else:
                                    vals.append(str(v))
                        lines.append("| " + " | ".join(vals) + " |")
                    return "\n".join(lines)

        # --- PATTERN 3: Chart accompaniment (very brief text) ---
        if has_chart:
            subject = players[0] if players else teams[0] if teams else "the data"
            season_str = f" ({seasons[0]})" if seasons else ""
            intent_str = str(intent).upper() if intent else ""

            if "TREND" in intent_str:
                # Distinguish per-game (round-level) from multi-season trends
                has_round_col = state.get("query_results") is not None and "round" in state["query_results"].columns
                season_count = state["query_results"]["season"].nunique() if (state.get("query_results") is not None and "season" in state["query_results"].columns) else 0
                if has_round_col and season_count <= 1:
                    return f"Here's {subject}'s game-by-game stats{season_str}."
                return f"Here's {subject}'s trend over time{season_str}."
            elif "COMPARISON" in intent_str:
                compared = " and ".join(players[:3]) if players else "the players"
                return f"Here's a comparison of {compared}{season_str}. See the chart for the full breakdown."
            elif "TEAM" in intent_str:
                return f"Here's {subject}'s performance breakdown{season_str}."
            else:
                return f"Here are the results for {subject}{season_str}."

        return None

    async def respond_node(self, state: AgentState) -> AgentState:
        """
        RESPOND node: Format natural language response.

        Updates:
        - natural_language_summary
        - confidence
        - thinking_message
        """
        state["current_step"] = WorkflowStep.RESPOND
        state["thinking_message"] = "Writing response..."
        self._emit_progress(state, "respond", "Writing response...")

        logger.info("RESPOND: Generating natural language response")

        try:
            # Check for clarification needed (player disambiguation, etc.)
            if state.get("needs_clarification"):
                clarification_q = state.get("clarification_question", "Could you provide more details?")
                state["natural_language_summary"] = clarification_q
                state["confidence"] = 0.5
                return state

            # Check for errors
            logger.info(f"RESPOND: Checking state - execution_error={state.get('execution_error')}, query_results type={type(state.get('query_results'))}, errors={state.get('errors')}")
            if state.get("execution_error"):
                error_detail = state.get("execution_error", "Unknown error")
                logger.error(f"RESPOND: execution_error detected: {error_detail}")

                state["natural_language_summary"] = (
                    "I wasn't able to find an answer for that query. "
                    "Try rephrasing your question, or if you think this data should be available, "
                    "raise a request using the report button and I'll look into it."
                )
                state["confidence"] = 0.0
                logger.info(f"RESPOND: Returning error response with debug info")
                return state

            # Check if we have results
            if state.get("query_results") is None or len(state["query_results"]) == 0:
                raw_query = state.get("user_query", "")
                suggestions = []

                if state.get("needs_clarification"):
                    suggestions.append(state.get("clarification_question", ""))

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
                    "\n\nIf you think this data should be available, raise a request using the report button and I'll look into it."
                )
                state["confidence"] = 0.3
                return state

            # Check if results are all NULL (query succeeded but no data for that filter)
            data = state["query_results"]

            # Handle list results from tools (BettingTool, NewsTool, TippingTool)
            # vs DataFrame results from database queries
            if isinstance(data, list):
                all_null = len(data) == 0
                logger.info(f"NULL check (list): len(data)={len(data)}, all_null={all_null}")
            else:
                all_null = data.isnull().all().all() if len(data) > 0 else False
                logger.info(f"NULL check (DataFrame): len(data)={len(data)}, all_null={all_null}, data=\n{data}")

            if all_null:
                entities = state.get("entities", {})
                players = entities.get("players", [])
                seasons = entities.get("seasons", [])

                if players and seasons:
                    player_name = players[0] if players else "this player"
                    season = seasons[0] if seasons else "this season"

                    from app.data.database import get_data_recency
                    recency = get_data_recency()
                    earliest = recency["earliest_season"]
                    hist_season = recency["historical_latest_season"]
                    hist_round = recency["historical_latest_round"]
                    state["natural_language_summary"] = (
                        f"I couldn't find any data for {player_name} in {season}. "
                        f"I have match and player data from {earliest} through Round {hist_round} of {hist_season}. "
                        f"Try a different season or player."
                        "\n\nIf you think this data should be available, raise a request using the report button and I'll look into it."
                    )
                else:
                    state["natural_language_summary"] = (
                        "I found matching records but they don't contain any data values. "
                        "Try asking about a different time period or entity."
                        "\n\nIf you think this data should be available, raise a request using the report button and I'll look into it."
                    )

                state["confidence"] = 0.4
                return state

            # Try template response first (avoids LLM call for simple queries)
            template_response = self._try_template_response(state)
            if template_response is not None:
                state["natural_language_summary"] = template_response
                state["confidence"] = 0.9
                from app.data.database import get_data_recency
                _r = get_data_recency()
                state["sources"] = [f"AFL Tables ({_r['earliest_season']}-{_r['historical_latest_season']})"]
                state["thinking_message"] = "Response complete"
                self._emit_progress(state, "respond", "Response complete")
                logger.info("RESPOND: Used template response (no LLM call)")
                return state

            # Format statistics for GPT consumption
            stats_summary = self._format_stats_for_gpt(state.get("statistical_analysis", {}))

            # Determine response style based on analysis mode (needed for context filter)
            analysis_mode = state.get("analysis_mode", "summary")
            intent = state.get("intent")

            # Format context insights — only for in-depth team/trend analysis
            context_insights = state.get("context_insights", {})
            context_text = ""
            if context_insights and analysis_mode == "in_depth" and intent in [QueryIntent.TREND_ANALYSIS, QueryIntent.TEAM_ANALYSIS]:
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
            from app.data.database import get_data_recency
            recency = get_data_recency()
            _earliest = recency["earliest_season"]
            _hist_season = recency["historical_latest_season"]
            capability_constraints = f"""
SYSTEM CAPABILITIES:
✓ CAN DO: Query AFL statistics ({_earliest}-{_hist_season}), match results, player stats, team performance
✓ CAN DO: Generate visualizations and charts
✓ CAN DO: Compare players, teams, and seasons
✓ CAN DO: Provide betting odds and tipping predictions
✓ CAN DO: Show live/recent game scores and results

✗ CANNOT DO: Export data to CSV, Excel, or files
✗ CANNOT DO: Download or email reports
✗ CANNOT DO: Access non-AFL sports data
"""

            # Build prompt based on mode
            if analysis_mode == "summary" or intent == QueryIntent.SIMPLE_STAT:
                # SUMMARY MODE: Direct, concise answers
                prompt = f"""You are an AFL analytics expert. Answer the user's question directly and concisely.

CRITICAL RULES:
- Answer in 1-2 sentences MAX
- State the number/fact directly
- DO NOT mention what additional analysis you could do
- DO NOT mention limitations or missing data unless the query CANNOT be answered
- DO NOT offer follow-up analysis unprompted
- When presenting multiple rows of data, format as a markdown table

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

CRITICAL: Keep your response VERY SHORT (2-3 sentences max).
- Briefly state what the chart shows
- Mention 1-2 key insights or standout data points
- Do NOT describe every data point - the chart shows that

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
- Only include information directly relevant to what was asked
- Use Australian football terminology correctly
- Never mention SQL, databases, or technical details
- When presenting multiple rows of data, format as a markdown table

{conversation_context_text}Current user query: {state['user_query']}

Query results:
{results_text}

Statistical Insights:
{stats_summary}{context_text}

Provide a concise analysis (3-5 sentences):"""

            # Generate response using a more capable model for better NL quality
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_RESPONSE", "gpt-5-mini"),
                messages=[{"role": "user", "content": prompt}],
                reasoning_effort="low",
            )

            state["natural_language_summary"] = (response.choices[0].message.content or "").strip()
            state["confidence"] = 0.9
            state["sources"] = [f"AFL Tables ({_earliest}-{_hist_season})"]
            state["thinking_message"] = "Response complete"
            self._emit_progress(state, "respond", "Response complete")

            logger.info("Response generated successfully")

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"RESPOND: Exception caught: {type(e).__name__}: {str(e)}")
            logger.error(f"RESPOND: Full traceback:\n{tb}")
            state["natural_language_summary"] = (
                "I encountered an issue generating a response for that query. "
                "Try rephrasing your question, or if you think this data should be available, "
                "raise a request using the report button and I'll look into it."
            )
            state["confidence"] = 0.0
            state["errors"].append(f"Response error: {str(e)}")

        return state


# Global agent instance
agent = AFLAnalyticsAgent()
