"""
AFL Analytics Agent - LangGraph Workflow

Defines the agent workflow (Milestone 3):
CLASSIFY_RESOLVE → RETRIEVE_CONTEXT → GENERATE_SQL → ANALYZE_DEPTH → PLAN →
EXECUTE → (DIAGNOSE_EMPTY | REVIEW) → VISUALIZE → RESPOND,
with self-correct loops (DB error / fixable empty result / review NO verdict)
feeding back into GENERATE_SQL under a shared per-turn attempt cap.
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
from app.analytics.context_enrichment import ContextEnricher
from app.analytics.statistics import EfficiencyCalculator
from app.visualization import RechartsBuilder
from app.visualization.recharts_builder import ChartHelper
from app.visualization.chart_selector import ChartSelector
from app.visualization.layout_config import LayoutConfig
from app.visualization.data_preprocessor import DataPreprocessor

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Milestone 3c: global cap on total generate_sql invocations per turn,
# shared across ALL retry sources — the initial call, DB-error self-correct
# retries, and the diagnose_empty-driven regen (review-driven regen joins this
# same cap in M3d). Keyed off state["sql_attempts"], incremented inside
# generate_sql() itself on every invocation.
SQL_ATTEMPT_CAP = 3

# Import config for model selection
from app.config import get_config
config_obj = get_config()

# Initialize OpenAI client with timeout for production reliability
# 60s total timeout, 10s connect timeout
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(60.0, connect=10.0)
)

def _accumulate_usage(state: "AgentState", usage: Optional[Any]) -> None:
    """
    Merge real OpenAI token usage into the per-request state accumulator.

    Accepts either an OpenAI `response.usage` object (with prompt_tokens /
    completion_tokens attributes) or a plain dict with input_tokens/output_tokens
    (used by helper functions that return usage explicitly).
    """
    if not usage:
        return

    totals = state.setdefault("token_usage", {"input_tokens": 0, "output_tokens": 0})

    if isinstance(usage, dict):
        totals["input_tokens"] += usage.get("input_tokens", 0) or 0
        totals["output_tokens"] += usage.get("output_tokens", 0) or 0
    else:
        # OpenAI SDK CompletionUsage object
        totals["input_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        totals["output_tokens"] += getattr(usage, "completion_tokens", 0) or 0


class AFLAnalyticsAgent:
    """
    LangGraph-based agent for AFL analytics queries.

    Workflow:
    1. CLASSIFY_RESOLVE - Cheap LLM turn-type classification + deterministic entity resolution
    2. RETRIEVE_CONTEXT - Deterministic pruning of schema docs + verified SQL examples
    3. GENERATE_SQL - One focused LLM call: final intent + SQL (with retry loops feeding back here)
    4. ANALYZE_DEPTH - Determine summary vs in-depth analysis mode
    5. PLAN - Determine analysis steps required
    6. EXECUTE - Run SQL queries (or news/tips tools) and compute statistics
    7. DIAGNOSE_EMPTY / REVIEW - Explain 0-row results / sanity-check non-empty results
    8. VISUALIZE - Generate chart specifications (if needed)
    9. RESPOND - Format natural language response
    """

    def __init__(self):
        self.graph = self._build_graph()

    @staticmethod
    def _emit_progress(state: AgentState, step: str, message: str):
        """
        Emit WebSocket progress update if callback is available.

        Args:
            state: Current agent state
            step: Step identifier (e.g., "classify_resolve", "execute")
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

    @staticmethod
    def _route_after_generate_sql(state: AgentState) -> str:
        """Routing decision after `generate_sql`: clarification short-circuits to respond."""
        return "respond" if state.get("needs_clarification") else "analyze_depth"

    @staticmethod
    def _route_after_execute(state: AgentState) -> str:
        """Base visualize-vs-respond decision (final fallthrough of _route_after_execute_v2)."""
        return (
            "visualize"
            if state.get("requires_visualization")
            and state.get("query_results") is not None
            and len(state.get("query_results", [])) > 0
            else "respond"
        )

    @staticmethod
    def _route_after_execute_v2(state: AgentState) -> str:
        """
        Routing after `execute` (Milestone 3c, extended in 3d).

        - `sql_error` set (by execute_node, only when under SQL_ATTEMPT_CAP) →
          self-correct: loop back to generate_sql with the exact failed SQL +
          DB error baked into the retry prompt.
        - 0 rows, no error, and a DB-backed intent (not a news/tips tool
          call) → diagnose_empty (deterministic, no LLM) figures out why.
        - Non-empty rows from a SQL-backed intent → review (Milestone 3d): a
          cheap LLM sanity-check that the rows actually answer the question.
          Tool intents (news/tips) have no SQL to review, so they skip
          straight through to the base visualize/respond decision.
        - Otherwise (tool intents, or anything else) falls through to the
          base visualize/respond decision (_route_after_execute).
        """
        if state.get("sql_error"):
            return "generate_sql"

        results = state.get("query_results")
        no_sql_intents = {
            QueryIntent.AFL_NEWS,
            QueryIntent.INJURY_NEWS,
            QueryIntent.TIPPING_ADVICE,
        }
        no_error = not state.get("execution_error")
        intent_is_sql_backed = state.get("intent") not in no_sql_intents

        if no_error and results is not None and len(results) == 0 and intent_is_sql_backed:
            return "diagnose_empty"

        if no_error and results is not None and len(results) > 0 and intent_is_sql_backed:
            return "review"

        return AFLAnalyticsAgent._route_after_execute(state)

    @staticmethod
    def _route_after_diagnose_empty(state: AgentState) -> str:
        """
        Routing after `diagnose_empty` (Milestone 3c).

        diagnose_empty_node itself decides (and records in
        `diagnose_should_regenerate`) whether the diagnosis is obviously
        fixable AND we haven't already used our one diagnose-triggered regen
        this turn AND we're still under SQL_ATTEMPT_CAP — this router just
        reads that decision.
        """
        return "generate_sql" if state.get("diagnose_should_regenerate") else "respond"

    @staticmethod
    def _route_after_review(state: AgentState) -> str:
        """
        Routing after `review` (Milestone 3d).

        review_node itself decides (and records in `review_should_regenerate`)
        whether the verdict is NO AND we haven't already used our one
        review-triggered regen this turn AND we're still under
        SQL_ATTEMPT_CAP — this router just reads that decision. Otherwise
        falls through to the base visualize/respond decision (rows are
        guaranteed present — review only runs when execute returned rows).
        """
        if state.get("review_should_regenerate"):
            return "generate_sql"
        return AFLAnalyticsAgent._route_after_execute(state)

    @staticmethod
    def _route_after_classify(state: AgentState) -> str:
        """
        Routing decision after `classify_resolve`.

        chitchat → straight to respond (classify_resolve already produced the
        reply text). Everything else → retrieve_context (Milestone 3b+):
        classify_resolve → retrieve_context → generate_sql.
        """
        return "respond" if state.get("turn_type") == "chitchat" else "retrieve_context"

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow (Milestone 3 pipeline).

        classify_resolve → retrieve_context → generate_sql → analyze_depth →
        plan → execute → (diagnose_empty | review) → (visualize) → respond,
        with three self-correct loops feeding back into generate_sql:
          - Milestone 3c: execute hits a DB error → generate_sql (max 2
            retries, global cap of 3 total generate_sql calls this turn via
            sql_attempts).
          - Milestone 3c: execute returns 0 rows → diagnose_empty
            (deterministic, no LLM) → generate_sql ONCE if obviously fixable,
            else respond.
          - Milestone 3d: execute returns non-empty rows for a SQL-backed
            intent → review (cheap LLM sanity-check, skipped for trivial
            template answers) → generate_sql ONCE if the verdict is NO, else
            visualize/respond. All three loops share the same
            SQL_ATTEMPT_CAP.
        """
        workflow = StateGraph(AgentState)

        workflow.add_node("classify_resolve", self.classify_resolve_node)
        workflow.add_node("retrieve_context", self.retrieve_context_node)
        workflow.add_node("generate_sql", self.generate_sql_node)
        workflow.add_node("analyze_depth", self.analyze_depth_node)
        workflow.add_node("plan", self.plan_node)
        workflow.add_node("execute", self.execute_node)
        workflow.add_node("diagnose_empty", self.diagnose_empty_node)
        workflow.add_node("review", self.review_node)
        workflow.add_node("visualize", self.visualize_node)
        workflow.add_node("respond", self.respond_node)

        workflow.add_conditional_edges(
            "classify_resolve",
            self._route_after_classify,
            {
                "respond": "respond",
                "retrieve_context": "retrieve_context",
            }
        )

        workflow.add_edge("retrieve_context", "generate_sql")

        workflow.add_conditional_edges(
            "generate_sql",
            self._route_after_generate_sql,
            {
                "respond": "respond",
                "analyze_depth": "analyze_depth"
            }
        )
        workflow.add_edge("analyze_depth", "plan")
        workflow.add_edge("plan", "execute")

        workflow.add_conditional_edges(
            "execute",
            self._route_after_execute_v2,
            {
                "generate_sql": "generate_sql",
                "diagnose_empty": "diagnose_empty",
                "review": "review",
                "visualize": "visualize",
                "respond": "respond"
            }
        )

        workflow.add_conditional_edges(
            "diagnose_empty",
            self._route_after_diagnose_empty,
            {
                "generate_sql": "generate_sql",
                "respond": "respond"
            }
        )

        workflow.add_conditional_edges(
            "review",
            self._route_after_review,
            {
                "generate_sql": "generate_sql",
                "visualize": "visualize",
                "respond": "respond"
            }
        )

        workflow.add_edge("visualize", "respond")
        workflow.add_edge("respond", END)

        workflow.set_entry_point("classify_resolve")

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
        initial_state = AgentState(
            user_query=user_query,
            conversation_id=conversation_id,
            entities={},
            needs_clarification=False,
            warnings=[],
            analysis_plan=[],
            requires_visualization=False,
            sql_validated=False,
            statistical_analysis={},
            errors=[],
            current_step=WorkflowStep.CLASSIFY_RESOLVE,
            analysis_types=[],
            context_insights={},
            data_quality={},
            stats_summary={},
            socketio_emit=socketio_emit,
            conversation_history=conversation_history or [],
            token_usage={"input_tokens": 0, "output_tokens": 0},
            # Milestone 3a fields
            turn_type=None,
            bypass_cache=False,
            sql_attempts=0,
            prior_sql=None,
            prior_row_count=None,
            prior_answer=None,
            complaint_summary=None,
            diagnosis=None,
            review_verdict=None,
            review_regenerated=False,
            review_should_regenerate=False,
            # Milestone 3b fields
            retrieved_schema_docs=None,
            retrieved_examples=[],
            conversation_snippet=None,
            # Milestone 3c fields
            sql_error=None,
            failed_sql=None,
            diagnose_regenerated=False,
            diagnose_should_regenerate=False,
        )

        final_state = await self.graph.ainvoke(initial_state)
        return final_state

    # ==================== WORKFLOW NODES ====================

    async def classify_resolve_node(self, state: AgentState) -> AgentState:
        """
        CLASSIFY_RESOLVE node (Milestone 3a).

        First node in the graph. Runs a small LLM call to classify the
        turn (turn_type) and extract entities, then resolves those entities
        deterministically via EntityResolver. For turn_type == "correction",
        also sets bypass_cache and loads the prior turn's persisted
        sql/row_count/answer from conversation history.

        See app/agent/classify_resolve.py for the implementation and
        app/agent/prompts/classify.py for the prompt.

        Updates:
        - turn_type, entities, warnings
        - complaint_summary (correction only)
        - natural_language_summary, confidence (chitchat only)
        - bypass_cache, prior_sql, prior_row_count, prior_answer (correction only)
        """
        state["current_step"] = WorkflowStep.CLASSIFY_RESOLVE
        state["thinking_message"] = "Reading your question..."
        self._emit_progress(state, "classify_resolve", "Reading your question...")

        logger.info(f"CLASSIFY_RESOLVE: Processing query: {state['user_query']}")

        from app.agent.classify_resolve import classify_and_resolve

        updates = classify_and_resolve(
            user_query=state["user_query"],
            conversation_history=state.get("conversation_history", []),
            state=state,
        )
        state.update(updates)

        logger.info(
            f"CLASSIFY_RESOLVE: turn_type={state.get('turn_type')}, "
            f"entities={state.get('entities')}, bypass_cache={state.get('bypass_cache')}"
        )

        return state

    async def retrieve_context_node(self, state: AgentState) -> AgentState:
        """
        RETRIEVE_CONTEXT node (Milestone 3b).

        Second node in the graph, runs immediately after classify_resolve.
        Deterministic — makes NO LLM calls and NO database calls: prunes the
        curated schema docs (app/agent/schema_docs.py) and picks the top few
        verified SQL examples (app/agent/sql_examples.py) relevant to this
        turn's entities/question, so generate_sql's prompt only carries what's
        actually relevant.

        See app/agent/retrieve_context.py for the implementation.

        Updates:
        - retrieved_schema_docs, retrieved_examples, conversation_snippet
        """
        state["current_step"] = WorkflowStep.RETRIEVE_CONTEXT
        state["thinking_message"] = "Looking up relevant AFL data..."
        self._emit_progress(state, "retrieve_context", "Looking up relevant AFL data...")

        logger.info(f"RETRIEVE_CONTEXT: Processing query: {state['user_query']}")

        from app.agent.retrieve_context import retrieve_context

        updates = retrieve_context(
            user_query=state["user_query"],
            entities=state.get("entities", {}),
            conversation_history=state.get("conversation_history", []),
        )
        state.update(updates)

        return state

    async def generate_sql_node(self, state: AgentState) -> AgentState:
        """
        GENERATE_SQL node (Milestone 3b).

        Third node in the graph. Makes ONE LLM call — using the schema docs
        + examples retrieved by retrieve_context, plus the entities/turn_type
        already resolved by classify_resolve — that classifies the final
        intent (including non-SQL tool intents, so execute_node's existing
        routing is untouched) and generates focused SQL. For turn_type ==
        "correction", the prompt is augmented with
        prior_sql/prior_answer/complaint_summary and asked to produce different
        SQL addressing the complaint.

        See app/agent/generate_sql.py for the implementation and
        app/agent/prompts/generate_sql.py for the prompt.

        Updates:
        - intent, requires_visualization, pre_generated_sql, sql_query,
          llm_chart_type_hint, llm_chart_config_hint, sql_attempts (incremented)
        - needs_clarification, clarification_question (off-topic, non-follow-up only)
        """
        state["current_step"] = WorkflowStep.GENERATE_SQL
        state["thinking_message"] = "🔨 Generating SQL query..."
        self._emit_progress(state, "generate_sql", "🔨 Generating SQL query...")

        logger.info(f"GENERATE_SQL: Processing query: {state['user_query']}")

        from app.agent.generate_sql import generate_sql

        diagnosis = state.get("diagnosis")
        # Milestone 3d: review-driven retry context, if this call was routed
        # here from review (verdict NO). review_verdict is only meaningful as
        # a retry signal when its verdict is actually "NO" — a lingering YES
        # verdict from an earlier hop must never be replayed into a later,
        # unrelated retry.
        review_verdict = state.get("review_verdict") or {}
        review_critique = review_verdict.get("reason") if review_verdict.get("verdict") == "NO" else None

        updates = generate_sql(
            user_query=state["user_query"],
            entities=state.get("entities", {}),
            turn_type=state.get("turn_type"),
            retrieved_schema_docs=state.get("retrieved_schema_docs", ""),
            retrieved_examples=state.get("retrieved_examples", []),
            conversation_snippet=state.get("conversation_snippet", ""),
            conversation_history=state.get("conversation_history", []),
            state=state,
            prior_sql=state.get("prior_sql"),
            prior_answer=state.get("prior_answer"),
            complaint_summary=state.get("complaint_summary"),
            # Milestone 3c: self-correct retry context, if this call was routed
            # here from execute (DB error) or diagnose_empty (fixable 0-row diagnosis).
            failed_sql=state.get("failed_sql"),
            sql_error=state.get("sql_error"),
            diagnosis=diagnosis,
            review_critique=review_critique,
        )
        was_retry = bool(state.get("failed_sql") or state.get("sql_error") or diagnosis or review_critique)
        state.update(updates)

        logger.info(
            f"GENERATE_SQL: intent={state.get('intent')}, "
            f"sql_attempts={state.get('sql_attempts')}, "
            f"needs_clarification={state.get('needs_clarification')}, "
            f"was_retry={was_retry}"
        )

        return state

    async def diagnose_empty_node(self, state: AgentState) -> AgentState:
        """
        DIAGNOSE_EMPTY node (Milestone 3c).

        Runs when `execute` returned 0 rows for a DB-backed intent. Purely
        deterministic — no LLM call. Delegates to app/agent/diagnose_empty.py,
        which first consumes any M1 EntityResolver warnings already in
        state["warnings"] (season-out-of-range, player-season-mismatch), and
        only hits the DB with fresh probes (entity exists? which seasons does
        it have data for?) if no warning already answers the question.

        Also decides (and records via diagnose_should_regenerate) whether the
        diagnosis is obviously fixable AND we haven't already used our one
        diagnose-triggered regen this turn AND we're still under
        SQL_ATTEMPT_CAP — _route_after_diagnose_empty just reads that decision.

        Updates:
        - diagnosis: {reason_code, human_reason, fixable, suggestion}
        - diagnose_should_regenerate (ephemeral, read by the router)
        - diagnose_regenerated (sticky, set once we decide to regenerate)
        """
        state["current_step"] = WorkflowStep.DIAGNOSE_EMPTY
        state["thinking_message"] = "Checking why that came back empty..."
        self._emit_progress(state, "diagnose_empty", "Checking why that came back empty...")

        from app.agent.diagnose_empty import diagnose_empty

        diagnosis = diagnose_empty(
            user_query=state["user_query"],
            entities=state.get("entities", {}),
            warnings=state.get("warnings", []),
        )
        state["diagnosis"] = diagnosis

        attempts = state.get("sql_attempts") or 0
        already_used = state.get("diagnose_regenerated", False)
        should_regenerate = bool(diagnosis.get("fixable")) and not already_used and attempts < SQL_ATTEMPT_CAP
        state["diagnose_should_regenerate"] = should_regenerate
        if should_regenerate:
            state["diagnose_regenerated"] = True

        logger.info(
            f"DIAGNOSE_EMPTY: reason_code={diagnosis.get('reason_code')}, "
            f"fixable={diagnosis.get('fixable')}, should_regenerate={should_regenerate}"
        )

        return state

    async def review_node(self, state: AgentState) -> AgentState:
        """
        REVIEW node (Milestone 3d).

        Runs when `execute` returns NON-EMPTY rows for a SQL-backed intent —
        the sibling case to diagnose_empty's 0-row check. A cheap LLM call
        (see app/agent/review.py) sample-checks whether those rows actually
        answer the user's question, catching a query that ran successfully
        but grouped/filtered/joined on the wrong thing.

        Skips the LLM call entirely for trivial template answers (a
        single-row simple_stat result in summary mode — see
        `should_skip_review` in app/agent/review.py) and records a
        pass-through YES verdict directly.

        Also decides (and records via review_should_regenerate) whether the
        verdict is NO AND we haven't already used our one review-triggered
        regen this turn AND we're still under SQL_ATTEMPT_CAP —
        _route_after_review just reads that decision.

        Updates:
        - review_verdict: {"verdict": "YES"|"NO", "reason": str}
        - review_should_regenerate (ephemeral, read by the router)
        - review_regenerated (sticky, set once we decide to regenerate)
        """
        state["current_step"] = WorkflowStep.REVIEW
        state["thinking_message"] = "Double-checking the results..."
        self._emit_progress(state, "review", "Double-checking the results...")

        from app.agent.review import review_results, should_skip_review

        query_results = state.get("query_results")
        row_count = len(query_results) if query_results is not None else 0

        if should_skip_review(state.get("intent"), state.get("analysis_mode"), row_count):
            logger.info("REVIEW: Skipped — trivial single-row template answer")
            state["review_verdict"] = {
                "verdict": "YES",
                "reason": "Skipped review — trivial single-row result.",
            }
            state["review_should_regenerate"] = False
            return state

        verdict = review_results(
            user_query=state["user_query"],
            sql_query=state.get("sql_query"),
            query_results=query_results,
            state=state,
        )
        state["review_verdict"] = verdict

        attempts = state.get("sql_attempts") or 0
        already_used = state.get("review_regenerated", False)
        should_regenerate = verdict.get("verdict") == "NO" and not already_used and attempts < SQL_ATTEMPT_CAP
        state["review_should_regenerate"] = should_regenerate
        if should_regenerate:
            state["review_regenerated"] = True

        logger.info(
            f"REVIEW: verdict={verdict.get('verdict')}, reason={verdict.get('reason')!r}, "
            f"should_regenerate={should_regenerate}"
        )

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

    def _signal_v2_sql_failure(
        self, state: AgentState, raw_error: str, failed_sql: Optional[str]
    ) -> AgentState:
        """
        Milestone 3c: record a retryable SQL failure.

        If still under SQL_ATTEMPT_CAP, sets sql_error/failed_sql so
        `_route_after_execute_v2` sends this turn back to generate_sql with the
        exact error + failed SQL baked into the retry prompt (self-correct
        loop). Once the cap is reached, falls through to an honest
        execution_error instead of retrying again — respond_node's existing
        error path picks this up.
        """
        attempts = state.get("sql_attempts") or 0
        if attempts < SQL_ATTEMPT_CAP:
            state["sql_error"] = raw_error
            state["failed_sql"] = failed_sql
            state["thinking_message"] = "Query failed, retrying with a corrected query..."
            self._emit_progress(state, "execute", "Query failed, retrying with a corrected query...")
        else:
            error_msg = f"Database query failed after {attempts} attempts: {raw_error}"
            logger.error(f"EXECUTE: {error_msg}")
            state["execution_error"] = error_msg
            state["errors"].append(error_msg)
            state["sql_error"] = None
            state["failed_sql"] = None
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

        # Milestone 3c: reset the self-correct signal fields at the start of
        # every fresh attempt so a successful retry doesn't leave a stale
        # sql_error lying around and loop forever.
        state["sql_error"] = None
        state["failed_sql"] = None

        try:
            # Step 1: Get SQL — generate_sql already produced it. A missing
            # pre_generated_sql is a retryable signal that routes back to
            # generate_sql (Milestone 3c self-correct loop).
            pre_sql = state.get("pre_generated_sql")
            if not pre_sql:
                logger.warning(
                    "EXECUTE: no pre_generated_sql available (generate_sql produced none) — "
                    "signalling self-correct retry"
                )
                return self._signal_v2_sql_failure(
                    state,
                    raw_error="SQL generation failed to produce a query for this question.",
                    failed_sql=None,
                )

            logger.info(f"EXECUTE: Using pre-generated SQL from generate_sql: {pre_sql[:80]}...")
            state["sql_query"] = pre_sql

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
            # Corrections (turn_type == "correction" → bypass_cache, set by
            # classify_resolve) skip READING the cache so we don't re-serve a
            # stale cached result — but still WRITE the fresh result below.
            from app.utils.cache import get_cached_result, set_cached_result
            cached = None if state.get("bypass_cache") else get_cached_result(state["sql_query"])
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
                    raw_error = db_result.get("raw_error", db_result["error"])
                    # Milestone 3c self-correct loop: route back to generate_sql
                    # with the exact failed SQL + DB error.
                    logger.warning(f"EXECUTE: SQL failed, signalling self-correct retry. Error: {raw_error}")
                    return self._signal_v2_sql_failure(state, raw_error, state["sql_query"])

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
                return state

            # VALIDATION: Skip chart if every row has the same x-axis value (e.g., all "Charlie Cameron")
            # — a bar chart with duplicate x labels is meaningless; the table is better
            non_numeric = data.select_dtypes(exclude=['number']).columns.tolist()
            temporal_cols_present = [c for c in data.columns if c in ['season', 'year', 'match_date', 'round']]
            if non_numeric and not temporal_cols_present:
                likely_x = non_numeric[0]
                if data[likely_x].nunique() == 1 and len(data) <= 10:
                    logger.info(f"VISUALIZE: Skipping chart — x-axis '{likely_x}' has only 1 unique value across {len(data)} rows")
                    state["thinking_message"] = "Table is more useful than a chart for this data"
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
            _accumulate_usage(state, chart_config.get("_usage"))

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

            # ── POST-VALIDATION: sanity-check chart_type vs data shape ────────
            # Skip type-changing overrides if user explicitly requested a chart type
            user_explicit = chart_config.get("user_explicit", False)
            if not user_explicit:
                chart_type, x_col, y_col = self._validate_chart_selection(
                    chart_type, x_col, y_col, data, user_query
                )
            # Update params after validation may have changed x/y_col
            if isinstance(y_col, str):
                params["x_col"] = x_col
                params["y_col"] = y_col

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
                layout_config = LayoutConfig.calculate(
                    data=data,
                    chart_type=chart_type,
                    x_col=x_col,
                    y_col=y_col,
                    metadata=metadata
                )

                # Add preprocessing results to params for RechartsBuilder
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

            # Generate chart — RechartsBuilder validates the output against the
            # ChartSpecV1 wire contract internally and returns None (logging
            # loudly) if the builder errored or produced a non-conforming spec.
            # Guard here too so an invalid/absent spec never gets attached to
            # state (websocket.py only emits 'visualization' when this is set).
            chart_spec = RechartsBuilder.generate_chart(data, chart_type, params)

            if chart_spec is None:
                logger.warning(
                    f"VISUALIZE: chart spec generation/validation failed for "
                    f"chart_type={chart_type}; skipping chart"
                )
                state["thinking_message"] = "Skipping chart generation"
            else:
                state["visualization_spec"] = chart_spec
                logger.info(f"Chart generated: {chart_type}")
                state["thinking_message"] = f"Chart created ({chart_type})"
                self._emit_progress(state, "visualize", f"Chart created ({chart_type})")

        except Exception as e:
            logger.error(f"Error in VISUALIZE node: {e}")
            state["errors"].append(f"Visualization error: {str(e)}")
            state["thinking_message"] = "Skipping chart generation"

        return state

    @staticmethod
    def _validate_chart_selection(
        chart_type: str,
        x_col: Optional[str],
        y_col: Any,
        data: Any,
        user_query: str,
    ) -> tuple:
        """Post-validate chart type vs actual data shape. Returns (chart_type, x_col, y_col)."""
        import pandas as pd

        if not isinstance(data, pd.DataFrame) or len(data) == 0:
            return chart_type, x_col, y_col

        n_rows = len(data)

        # Rule: Line charts need at least 3 data points to show a trend
        if chart_type == "line" and n_rows < 3:
            logger.info(f"CHART-VALIDATE: line→bar (only {n_rows} rows, need ≥3 for trend)")
            chart_type = "bar"

        # Rule: Vertical bar charts — cap at 12 categories for readability
        if chart_type == "bar" and n_rows > 12:
            logger.info(f"CHART-VALIDATE: bar→horizontal_bar ({n_rows} categories exceeds 12)")
            chart_type = "horizontal_bar"

        # Rule: Pie charts — only valid for 2-7 categories
        if chart_type == "pie":
            if n_rows > 7:
                logger.info(f"CHART-VALIDATE: pie→bar ({n_rows} categories too many for pie)")
                chart_type = "bar"
            elif n_rows < 2:
                logger.info(f"CHART-VALIDATE: pie→bar (only {n_rows} category)")
                chart_type = "bar"

        # Rule: Scatter needs at least 5 points to be useful
        if chart_type == "scatter" and n_rows < 5:
            logger.info(f"CHART-VALIDATE: scatter→bar (only {n_rows} points)")
            chart_type = "bar"

        # Rule: Validate x_col and y_col actually exist in data
        if x_col and x_col not in data.columns:
            fallback_x = data.columns[0]
            logger.info(f"CHART-VALIDATE: x_col '{x_col}' not in data, using '{fallback_x}'")
            x_col = fallback_x

        if isinstance(y_col, str) and y_col not in data.columns:
            numeric_cols = data.select_dtypes(include=["number"]).columns.tolist()
            numeric_cols = [c for c in numeric_cols if "id" not in c.lower()]
            if numeric_cols:
                fallback_y = numeric_cols[0]
                logger.info(f"CHART-VALIDATE: y_col '{y_col}' not in data, using '{fallback_y}'")
                y_col = fallback_y

        return chart_type, x_col, y_col

    @staticmethod
    def _build_error_response(state: Dict[str, Any]) -> str:
        """Build a helpful, conversational error response using gpt-5-nano."""
        error_detail = state.get("execution_error", "")

        # Connection/timeout errors don't need an LLM call
        if error_detail and ("connection" in error_detail.lower() or "timeout" in error_detail.lower()):
            return (
                "I'm having trouble reaching the database right now. "
                "Please try again in a moment."
            )

        return AFLAnalyticsAgent._generate_llm_error_response(state, error_type="execution_error")

    @staticmethod
    def _build_empty_results_response(state: Dict[str, Any]) -> str:
        """Build a helpful, conversational response when no results found using gpt-5-nano."""
        return AFLAnalyticsAgent._generate_llm_error_response(state, error_type="no_results")

    @staticmethod
    def _build_diagnosis_response(state: Dict[str, Any]) -> str:
        """
        Milestone 3c: build the empty-results response directly from
        diagnose_empty's structured facts (state["diagnosis"]) instead of
        asking an LLM to guess why — this guarantees the response NAMES the
        actual reason (e.g. "Nick Daicos has no 2015 stats — his data covers
        2022-2026") rather than a plausible-sounding hallucinated guess.

        Falls back to the generic LLM-based guess if diagnose_empty didn't
        produce a usable human_reason for some reason (defensive only — the
        pipeline always runs diagnose_empty before reaching this branch).
        """
        diagnosis = state.get("diagnosis") or {}
        human_reason = diagnosis.get("human_reason")
        if not human_reason:
            return AFLAnalyticsAgent._build_empty_results_response(state)

        parts = [human_reason]
        suggestion = diagnosis.get("suggestion")
        if suggestion:
            parts.append(suggestion)

        # The out-of-range/no-data reason strings already state the data
        # coverage explicitly — don't repeat it again in a second sentence.
        if diagnosis.get("reason_code") not in ("season_out_of_range",) and not suggestion:
            from app.data.database import get_data_recency
            try:
                recency = get_data_recency()
                parts.append(
                    f"Let me know if you'd like to try a different season or player — "
                    f"our database covers {recency['earliest_season']}-{recency['historical_latest_season']}."
                )
            except Exception:
                pass

        return " ".join(parts)

    @staticmethod
    def _generate_llm_error_response(state: Dict[str, Any], error_type: str = "no_results") -> str:
        """Generate a conversational error response via gpt-5-nano.

        Cheap and fast — provides context-aware suggestions based on what the user asked.
        """
        try:
            from app.data.database import get_data_recency
            recency = get_data_recency()
            earliest = recency["earliest_season"]
            hist_season = recency["historical_latest_season"]
            hist_round = recency["historical_latest_round"]

            user_query = state.get("user_query", "")
            entities = state.get("entities", {})
            players = entities.get("players", [])
            teams = entities.get("teams", [])
            seasons = entities.get("seasons", [])
            error_detail = state.get("execution_error", "") if error_type == "execution_error" else ""

            context_parts = []
            if players:
                context_parts.append(f"Players mentioned: {', '.join(players)}")
            if teams:
                context_parts.append(f"Teams mentioned: {', '.join(teams)}")
            if seasons:
                context_parts.append(f"Seasons mentioned: {', '.join(str(s) for s in seasons)}")
            if error_detail:
                # Sanitise — don't leak SQL or stack traces
                clean_error = error_detail.split('\n')[0][:200]
                context_parts.append(f"Error: {clean_error}")

            context_str = "\n".join(context_parts) if context_parts else "No specific entities detected."

            prompt = f"""The user asked an AFL statistics question but we couldn't find results. Write a helpful, casual response.

User's question: "{user_query}"

Detected context:
{context_str}

Our database covers: {earliest} to Round {hist_round} of {hist_season} (match results, player stats, team stats).
We also have: upcoming fixtures, Squiggle tipping predictions, and AFL news.

{'The query failed to execute — likely a spelling issue, wrong season, or the data doesnt exist.' if error_type == 'execution_error' else 'The query ran but returned zero rows — the data may not exist for this specific filter.'}

Rules:
- Be conversational and brief (2-4 sentences max)
- Explain WHY it might have failed based on what they asked (wrong spelling? season out of range? player didn't play that year?)
- Suggest 2-3 alternative queries they could try that ARE answerable — make them specific to what the user was asking about, not generic examples
- Format suggestions naturally, not as a bulleted list of raw queries
- End with a note that they can report an issue if they think the data should exist"""

            response = client.chat.completions.create(
                model=os.getenv("NEWS_ENRICHMENT_MODEL", "gpt-5-nano"),
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=300,
            )
            _accumulate_usage(state, response.usage)

            result = (response.choices[0].message.content or "").strip()
            if result:
                return result

            # LLM returned empty — fall through to static fallback
            logger.warning("LLM error response was empty, using static fallback")

        except Exception as e:
            logger.warning(f"LLM error response generation failed: {e}")

        # Fallback to basic static message
        from app.data.database import get_data_recency
        try:
            recency = get_data_recency()
            user_query = state.get("user_query", "your question")
            return (
                f"I had trouble finding an answer for \"{user_query[:80]}\". "
                f"I have AFL data from {recency['earliest_season']} to {recency['historical_latest_season']} "
                f"covering match results, player stats, and team performance. "
                f"Try rephrasing or being more specific — and if you think this should work, "
                f"hit the report button so we can look into it."
            )
        except Exception:
            return (
                "I had trouble answering that one. Try rephrasing your question, "
                "or hit the report button if you think this should work."
            )

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
    def _humanize_value_label(col_name: str) -> str:
        """Convert database column names to natural response labels."""
        _LABEL_MAP = {
            "total_goals": "goals",
            "total_disposals": "disposals",
            "total_marks": "marks",
            "total_tackles": "tackles",
            "total_kicks": "kicks",
            "total_handballs": "handballs",
            "total_votes": "votes",
            "total_fantasy": "fantasy points",
            "total_score": "points",
            "win_count": "wins",
            "loss_count": "losses",
            "draw_count": "draws",
            "top4_count": "top-four finishes",
            "games_played": "games",
            "avg_disposals": "average disposals per game",
            "avg_goals": "average goals per game",
            "avg_score": "average score",
            "avg_margin": "average margin",
            "avg_fantasy": "average fantasy points per game",
            "career_goals": "career goals",
            "career_disposals": "career disposals",
            "win_rate": "win rate",
            "win_percentage": "win percentage",
            "home_wins": "home wins",
            "away_wins": "away wins",
            "attendance": "attendance",
        }
        lower = col_name.lower()
        if lower in _LABEL_MAP:
            return _LABEL_MAP[lower]
        # Strip common prefixes
        for prefix in ("total_", "avg_", "count_", "sum_", "num_"):
            if lower.startswith(prefix):
                return lower[len(prefix):].replace("_", " ")
        return lower.replace("_", " ")

    @staticmethod
    def _strip_id_columns(data):
        """Remove id and *_id columns from DataFrame to prevent leaking DB IDs in responses."""
        import pandas as pd
        if isinstance(data, pd.DataFrame) and len(data) > 0:
            id_cols = [c for c in data.columns if c.lower() == 'id' or c.lower().endswith('_id')]
            if id_cols:
                data = data.drop(columns=id_cols, errors='ignore')
        return data

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

        # Strip ID columns to prevent leaking DB IDs in responses
        import pandas as pd
        if isinstance(data, pd.DataFrame):
            data = AFLAnalyticsAgent._strip_id_columns(data)

        # Handle empty results for tool-based intents with helpful messages
        if data is None or len(data) == 0:
            if intent in [QueryIntent.AFL_NEWS, QueryIntent.INJURY_NEWS]:
                if teams:
                    team_str = " or ".join(teams)
                    if intent == QueryIntent.INJURY_NEWS:
                        return f"I don't have any recent injury news for {team_str}. No major injuries reported in my current news feed."
                    return f"I don't have any recent news about {team_str} in my current feed."
                return "I couldn't find any recent news matching your query."
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
            name_cols = [c for c in data.columns if c.lower() in ['name', 'player', 'player_name', 'team', 'team_name', 'winner']]

            def _fmt_val(v):
                if isinstance(v, float) and v == int(v):
                    return str(int(v))
                elif isinstance(v, float):
                    return f"{v:.1f}"
                return str(v)

            # Get subject from: 1) name column in result, 2) entities, 3) empty
            subject = ""
            if name_cols:
                subject = str(row[name_cols[0]])
            elif players:
                subject = players[0]
            elif teams:
                subject = teams[0]

            season_str = f" in {seasons[0]}" if seasons else ""

            if len(numeric_cols) == 1:
                col = numeric_cols[0]
                value = row[col]
                label = AFLAnalyticsAgent._humanize_value_label(col)

                if subject:
                    # Natural phrasing based on the metric type
                    val_str = _fmt_val(value)
                    if any(w in label for w in ["wins", "losses", "finishes", "games"]):
                        return f"{subject} had {val_str} {label}{season_str}."
                    elif "average" in label or "avg" in label:
                        return f"{subject} averaged {val_str} {label.replace('average ', '')}{season_str}."
                    elif "rate" in label or "percentage" in label:
                        return f"{subject} had a {val_str}% {label}{season_str}."
                    else:
                        return f"{subject} had {val_str} {label}{season_str}."
                else:
                    label = AFLAnalyticsAgent._humanize_value_label(col)
                    return f"The {label}{season_str} is {_fmt_val(value)}."

            elif 2 <= len(numeric_cols) <= 5:
                parts = []
                for col in numeric_cols:
                    label = AFLAnalyticsAgent._humanize_value_label(col)
                    parts.append(f"{_fmt_val(row[col])} {label}")
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

                metric_label = AFLAnalyticsAgent._humanize_value_label(numeric_cols[0])
                # Try to derive a meaningful header from the query context
                # Check if all rows are the same player (per-game breakdown, not a ranking)
                unique_names = data[name_col].nunique() if name_col in data.columns else 0
                if unique_names == 1:
                    player_name = str(data.iloc[0][name_col])
                    header = f"{player_name}'s game-by-game stats{season_str}:\n\n"
                elif players and len(players) >= 2:
                    header = f"{' vs '.join(players[:3])}{season_str}:\n\n"
                elif teams and len(teams) >= 2:
                    header = f"{' vs '.join(teams[:3])}{season_str}:\n\n"
                else:
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
            subject = players[0] if players else teams[0] if teams else None
            intent_str = str(intent).upper() if intent else ""
            chart_data = state.get("query_results")

            # Try to extract time range from the data
            time_range = ""
            if chart_data is not None and "season" in chart_data.columns:
                seasons_in_data = sorted(chart_data["season"].unique())
                if len(seasons_in_data) > 1:
                    time_range = f" from {int(seasons_in_data[0])} to {int(seasons_in_data[-1])}"
                elif len(seasons_in_data) == 1:
                    time_range = f" in {int(seasons_in_data[0])}"
            elif seasons:
                time_range = f" in {seasons[0]}" if len(seasons) == 1 else f" from {seasons[0]} to {seasons[-1]}"

            # Detect the chart type for a more descriptive accompaniment
            viz_spec = state.get("visualization_spec", {})
            viz_traces = viz_spec.get("data", []) if isinstance(viz_spec, dict) else []
            chart_type_name = viz_traces[0].get("type", "") if viz_traces else ""

            if "TREND" in intent_str:
                has_round_col = chart_data is not None and "round" in chart_data.columns
                season_count = chart_data["season"].nunique() if (chart_data is not None and "season" in chart_data.columns) else 0
                if subject:
                    if has_round_col and season_count <= 1:
                        return f"Here's {subject}'s game-by-game performance{time_range}."
                    return f"Here's how {subject}'s numbers have changed{time_range}."
                else:
                    return f"Here's the trend{time_range}."
            elif "COMPARISON" in intent_str:
                compared = " and ".join(players[:3]) if players else "the players"
                return f"Here's a head-to-head comparison of {compared}{time_range}."
            elif "TEAM" in intent_str:
                if subject:
                    return f"Here's {subject}'s performance breakdown{time_range}."
                return f"Here's the performance breakdown{time_range}."
            elif chart_type_name == "pie":
                numeric_cols = chart_data.select_dtypes(include=['number']).columns.tolist() if chart_data is not None else []
                metric = AFLAnalyticsAgent._humanize_value_label(numeric_cols[0]) if numeric_cols else "breakdown"
                if subject:
                    return f"Here's {subject}'s {metric} breakdown{time_range}."
                return f"Here's the {metric} breakdown{time_range}."
            elif chart_type_name == "box":
                if subject:
                    return f"Here's the distribution of {subject}'s stats{time_range}."
                return f"Here's the stat distribution{time_range}."
            else:
                if subject:
                    return f"Here's {subject}'s data{time_range}."
                return f"Here's what I found{time_range}."

        return None

    @staticmethod
    def _needs_data_range_disclaimer(state: Dict[str, Any]) -> bool:
        """Check if the response should include a data range disclaimer."""
        entities = state.get("entities", {})
        seasons = entities.get("seasons", [])
        user_query = state.get("user_query", "").lower()

        # If user specified a season, no disclaimer needed
        if seasons:
            return False

        # Check for all-time/historical indicators
        all_time_keywords = ["all-time", "all time", "ever", "most", "record", "history",
                             "career", "total", "highest ever", "best ever", "worst ever"]
        return any(kw in user_query for kw in all_time_keywords)

    @staticmethod
    def _generate_follow_up(state: Dict[str, Any]) -> Optional[str]:
        """Generate contextual follow-up suggestions based on the query result."""
        import pandas as pd

        data = state.get("query_results")
        entities = state.get("entities", {})
        intent = state.get("intent")
        teams = entities.get("teams", [])
        players = entities.get("players", [])
        seasons = entities.get("seasons", [])

        if not isinstance(data, pd.DataFrame) or len(data) < 2:
            return None

        # Only add follow-ups for list/table results
        name_cols = [c for c in data.columns if c.lower() in ['name', 'player', 'player_name']]
        team_cols = [c for c in data.columns if c.lower() in ['team', 'team_name']]

        import random

        # Top-N player list → suggest comparing top 2
        if name_cols and len(data) >= 2:
            p1 = str(data.iloc[0][name_cols[0]])
            p2 = str(data.iloc[1][name_cols[0]])
            season_str = f" in {seasons[0]}" if seasons else ""
            prompts = [
                f"Curious how {p1} and {p2} compare{season_str}? Just ask.",
                f"Want to dig deeper? You could compare {p1} and {p2}, or check out {p1}'s full career.",
                f"You could also compare {p1} and {p2} head-to-head{season_str}.",
            ]
            return random.choice(prompts)

        # Team record → suggest comparison or previous season
        if teams and len(teams) == 1:
            team = teams[0]
            if seasons:
                prev_year = str(int(seasons[0]) - 1)
                prompts = [
                    f"Want to see how {team} went in {prev_year} for comparison?",
                    f"I can also show you {team}'s scoring trend over time if you're interested.",
                    f"You could also look at {team}'s {prev_year} season to compare.",
                ]
            else:
                prompts = [
                    f"I can also chart {team}'s performance over time if you'd like.",
                    f"Want to see {team}'s scoring trend across seasons?",
                ]
            return random.choice(prompts)

        # Player stats → suggest career or comparison
        if players and len(players) == 1:
            player = players[0]
            if seasons:
                prompts = [
                    f"I can also pull up {player}'s full career numbers if you're interested.",
                    f"Want to see how {player} stacks up against the rest of the league in {seasons[0]}?",
                ]
            else:
                prompts = [
                    f"Want to see {player}'s season-by-season breakdown?",
                    f"I can also compare {player} against other players if you'd like.",
                ]
            return random.choice(prompts)

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
            # Chitchat turns already have their reply generated by
            # classify_resolve (single LLM call, no DB/SQL work needed) — just
            # pass it through.
            if state.get("turn_type") == "chitchat" and state.get("natural_language_summary"):
                state.setdefault("confidence", 0.9)
                state["thinking_message"] = "Response complete"
                self._emit_progress(state, "respond", "Response complete")
                logger.info("RESPOND: Passed through chitchat reply from classify_resolve")
                return state

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

                state["natural_language_summary"] = self._build_error_response(state)
                state["confidence"] = 0.0
                logger.info(f"RESPOND: Returning error response")
                return state

            # Check if we have results
            if state.get("query_results") is None or len(state["query_results"]) == 0:
                # diagnose_empty already ran and worked out WHY for DB-backed
                # intents — use its facts directly instead of asking an LLM to
                # guess (M3c). Tool intents never set state["diagnosis"].
                if state.get("diagnosis"):
                    state["natural_language_summary"] = self._build_diagnosis_response(state)
                else:
                    state["natural_language_summary"] = self._build_empty_results_response(state)
                state["confidence"] = 0.3
                return state

            # Check if results are all NULL (query succeeded but no data for that filter)
            data = state["query_results"]

            # Handle list results from tools (NewsTool, TippingTool)
            # vs DataFrame results from database queries
            if isinstance(data, list):
                all_null = len(data) == 0
                logger.info(f"NULL check (list): len(data)={len(data)}, all_null={all_null}")
            else:
                all_null = data.isnull().all().all() if len(data) > 0 else False
                logger.info(f"NULL check (DataFrame): len(data)={len(data)}, all_null={all_null}, data=\n{data}")

            if all_null:
                if state.get("diagnosis"):
                    state["natural_language_summary"] = self._build_diagnosis_response(state)
                else:
                    state["natural_language_summary"] = self._build_empty_results_response(state)
                state["confidence"] = 0.4
                return state

            # Try template response first (avoids LLM call for simple queries)
            template_response = self._try_template_response(state)
            if template_response is not None:
                # Add data range disclaimer for all-time queries
                if self._needs_data_range_disclaimer(state):
                    from app.data.database import get_data_recency
                    _dr = get_data_recency()
                    template_response += f"\n\n*Based on data from {_dr['earliest_season']} to present.*"
                # Add follow-up suggestions for list/table responses (not charts — the chart speaks for itself)
                if not state.get("visualization_spec"):
                    follow_up = self._generate_follow_up(state)
                    if follow_up:
                        template_response += f"\n\n{follow_up}"
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

            results_df = self._strip_id_columns(state['query_results'])
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
✓ CAN DO: Provide tipping predictions
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
- After answering, you may suggest 1 brief follow-up the user might find interesting. Keep it casual and conversational — NOT "Try: 'query'" format. Instead, something like "I can also show you X if you're interested." or "Want to see how that compares to Y?"
- When presenting multiple rows of data, format as a markdown table
- ONLY present data from the query results below as your primary answer. Our database covers {_earliest}-present.
- If the results seem incomplete for historical/all-time questions, you MAY add well-known historical context from your own knowledge BUT you MUST clearly separate it. Present database results first, then add a clearly labelled section like "**For historical context:**" or "**Beyond our database:**" so the user knows what came from data vs general knowledge. Never mix the two together.
- NEVER invent, calculate, or fabricate metrics/ratings that are not in the query results. If the user asks about a metric that doesn't appear in the results (e.g. "pressure factor", "rating", "index"), say you don't have that specific metric and show what related data you DO have instead.

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
- ONLY reference data from the query results as your primary answer. Our database covers {_earliest}-present. If adding historical context from your own knowledge, clearly label it as separate from the data.
- NEVER invent, calculate, or fabricate metrics/ratings that are not in the query results.

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
- ONLY present data from the query results below as your primary answer. Our database covers {_earliest}-present.
- If the results seem incomplete for historical/all-time questions, you MAY add well-known historical context from your own knowledge BUT you MUST clearly separate it. Present database results first, then add a clearly labelled section like "**For historical context:**" or "**Beyond our database:**" so the user knows what came from data vs general knowledge. Never mix the two together.
- NEVER invent, calculate, or fabricate metrics/ratings that are not in the query results. If the user asks about a metric that doesn't appear in the results (e.g. "pressure factor", "rating", "index"), say you don't have that specific metric and show what related data you DO have instead.

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
            _accumulate_usage(state, response.usage)

            llm_response = (response.choices[0].message.content or "").strip()
            # Add data range disclaimer for all-time queries
            if self._needs_data_range_disclaimer(state):
                llm_response += f"\n\n*Based on data from {_earliest} to present.*"
            state["natural_language_summary"] = llm_response
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
