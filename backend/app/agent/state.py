"""
AFL Analytics Agent - State Schema

Defines the state that flows through the LangGraph workflow.
"""
from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class WorkflowStep(str, Enum):
    """Agent workflow steps."""
    UNDERSTAND = "understand"
    ANALYZE_DEPTH = "analyze_depth"
    PLAN = "plan"
    EXECUTE = "execute"
    VISUALIZE = "visualize"
    RESPOND = "respond"


class QueryIntent(str, Enum):
    """Types of queries the agent can handle."""
    SIMPLE_STAT = "simple_stat"  # "Who won the 2024 grand final?"
    PLAYER_COMPARISON = "player_comparison"  # "Compare Cripps vs Oliver"
    TEAM_ANALYSIS = "team_analysis"  # "Show Collingwood's scoring trend"
    TREND_ANALYSIS = "trend_analysis"  # "Max Gawn's hitout average over time"
    UNKNOWN = "unknown"


class AgentState(TypedDict, total=False):
    """
    State object that flows through the LangGraph workflow.

    Workflow progression:
    1. UNDERSTAND: Parse user query, extract intent and entities
    2. PLAN: Determine analysis steps required
    3. EXECUTE: Run SQL queries and calculations
    4. VISUALIZE: Generate chart specifications (if needed)
    5. RESPOND: Format natural language response
    """
    # Input
    user_query: str
    conversation_id: Optional[str]

    # Understanding phase
    intent: Optional[QueryIntent]
    entities: Dict[str, Any]  # {players: [...], teams: [...], seasons: [...], metrics: [...]}
    needs_clarification: bool
    clarification_question: Optional[str]

    # Planning phase
    analysis_plan: List[str]  # Step-by-step plan
    requires_visualization: bool
    chart_type: Optional[str]  # "line", "bar", "scatter", etc.
    fallback_approach: Optional[str]  # Simplified approach if complex query

    # Enhanced statistics
    analysis_mode: Optional[str]  # "summary" or "in_depth"
    analysis_types: List[str]  # ["average", "trend", "comparison", "rank"]
    context_insights: Dict[str, Any]  # Historical context, form analysis, venue splits
    data_quality: Dict[str, Any]  # Sample size, confidence, warnings
    stats_summary: Dict[str, Any]  # Formatted statistics for GPT consumption

    # Execution phase
    sql_query: Optional[str]
    sql_validated: bool
    query_results: Optional[Any]  # Pandas DataFrame
    statistical_analysis: Dict[str, Any]
    execution_error: Optional[str]

    # Visualization phase
    visualization_spec: Optional[Dict]  # Plotly JSON spec

    # Response phase
    natural_language_summary: str
    confidence: float  # 0.0 to 1.0
    sources: List[str]  # Data source references

    # Metadata
    current_step: WorkflowStep
    thinking_message: Optional[str]  # User-facing status update
    errors: List[str]
    socketio_emit: Optional[Any]  # Callback for emitting WebSocket progress updates
    conversation_history: Optional[List[Dict[str, Any]]]  # Recent conversation messages for context
