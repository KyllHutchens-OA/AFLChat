"""
AFL Analytics Agent - Generate SQL Node (Milestone 3b)

Third stage of the v2 pipeline (AGENT_PIPELINE=v2): takes the pruned schema
docs + verified examples from `retrieve_context` and the resolved
entities/turn_type from `classify_resolve`, and makes ONE LLM call that
classifies the final intent (including non-SQL tool intents, so
`execute_node`'s existing routing is untouched) and generates focused SQL —
replacing the ~300-line embedded mega-prompt call in `consolidated_llm.py`
that v2 used to fall through to via `understand_node`.

For turn_type == "correction", the prompt is augmented with the prior turn's
SQL/answer + the user's complaint (see classify_resolve.py, which loaded
these from conversation history), with an explicit instruction to produce
different SQL, and `reasoning_effort` is bumped from "low" to "medium".

A deterministic GROUP BY auto-fix pre-pass (reusing
`DatabaseTool._auto_fix_group_by`, the same helper `execute_node` falls back
to reactively on a Postgres error) is applied to the LLM's SQL before it's
handed to `execute_node`, so a common, mechanically-fixable LLM mistake never
even reaches the database.

`state["sql_attempts"]` is incremented on every call so Milestone 3c's
self-correction retry loop can key off it.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from app.agent.prompts.generate_sql import (
    GENERATE_SQL_PROMPT,
    build_conversation_section,
    build_correction_section,
    build_error_retry_section,
    build_diagnosis_retry_section,
)
from app.agent.state import QueryIntent

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(60.0, connect=10.0),
)

# Intents that are answered by dedicated tools in execute_node, never by SQL.
NO_SQL_INTENTS = {"afl_news", "injury_news", "betting_odds", "tipping_advice"}

# Tool-based intents that support follow-up questions (mirrors understand_node's
# off-topic-but-actually-a-followup handling in graph.py).
_TOOL_FOLLOWUP_INTENTS = {"injury_news", "afl_news", "tipping_advice", "betting_odds"}

_SHAPE_TO_CHART = {
    "temporal_trend": "line",
    "top_n_ranking": "bar",
    "comparison": "grouped_bar",
    "single_value": None,
    "distribution": "box",
}

_AGGREGATE_FUNCS = ("SUM(", "COUNT(", "AVG(", "MAX(", "MIN(")


def _accumulate_usage(state: Dict[str, Any], usage: Any) -> None:
    """Merge real OpenAI token usage into the per-request state accumulator."""
    if not usage:
        return
    totals = state.setdefault("token_usage", {"input_tokens": 0, "output_tokens": 0})
    totals["input_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
    totals["output_tokens"] += getattr(usage, "completion_tokens", 0) or 0


def _format_examples(examples: Optional[List[Dict[str, Any]]]) -> str:
    if not examples:
        return "(no closely-matching examples found)"
    lines = []
    for ex in examples:
        lines.append(f"Q: {ex['question']}\nSQL: {ex['sql']}")
    return "\n\n".join(lines)


def _maybe_fix_group_by(sql: str) -> str:
    """
    Deterministic pre-pass: proactively apply the existing GROUP BY auto-fix
    (app/agent/tools.py DatabaseTool._auto_fix_group_by) BEFORE the query ever
    reaches the database, instead of only reactively after a Postgres error.

    Guarded to only fire when it's very likely safe: the query has at least one
    aggregate function, no GROUP BY already, isn't a CTE, and has no window
    function — `_auto_fix_group_by`'s column-splitting logic only looks at the
    first SELECT ... FROM span and doesn't know about OVER (...), so applying it
    to a CTE/window-function query (e.g. the ladder-position examples) could
    corrupt an otherwise-correct query.
    """
    if not sql:
        return sql

    sql_upper = sql.upper()
    if "GROUP BY" in sql_upper:
        return sql
    if sql_upper.strip().startswith("WITH"):
        return sql
    if " OVER (" in sql_upper or " OVER(" in sql_upper:
        return sql
    if not any(func in sql_upper for func in _AGGREGATE_FUNCS):
        return sql

    try:
        from app.agent.tools import DatabaseTool
        fixed = DatabaseTool._auto_fix_group_by(sql)
        if fixed and fixed != sql:
            logger.info("GENERATE_SQL: Proactively applied GROUP BY auto-fix pre-pass")
            return fixed
    except Exception as e:
        logger.warning(f"GENERATE_SQL: GROUP BY pre-pass failed, leaving SQL unchanged: {e}")
    return sql


def _clean_sql(sql: str) -> str:
    if "```sql" in sql:
        sql = sql.split("```sql")[1].split("```")[0]
    elif "```" in sql:
        sql = sql.split("```")[1].split("```")[0]
    sql = sql.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")
    return " ".join(sql.split())


def _check_followup_tool_intent(
    conversation_history: Optional[List[Dict[str, Any]]],
) -> Optional[str]:
    """Mirrors understand_node's off_topic-but-actually-a-followup override."""
    if not conversation_history:
        return None
    for msg in reversed(conversation_history[-4:]):
        if msg.get("role") == "assistant":
            prev_intent = msg.get("intent", "")
            if prev_intent in _TOOL_FOLLOWUP_INTENTS:
                return prev_intent
    return None


def generate_sql(
    user_query: str,
    entities: Dict[str, Any],
    turn_type: Optional[str],
    retrieved_schema_docs: str,
    retrieved_examples: List[Dict[str, Any]],
    conversation_snippet: str,
    conversation_history: Optional[List[Dict[str, Any]]],
    state: Dict[str, Any],
    prior_sql: Optional[str] = None,
    prior_answer: Optional[str] = None,
    complaint_summary: Optional[str] = None,
    failed_sql: Optional[str] = None,
    sql_error: Optional[str] = None,
    diagnosis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the generate_sql LLM call.

    Args:
        state: The in-flight AgentState — used only so token usage can be
            accumulated via state["token_usage"]; not mutated otherwise (the
            caller merges the returned dict into state itself).
        failed_sql, sql_error: Set (both) when this call is a Milestone 3c
            self-correct retry after `execute` hit a database error — the
            exact failed SQL + Postgres error are fed back into the prompt.
        diagnosis: Set when this call is a Milestone 3c diagnose_empty-driven
            retry (execute returned 0 rows and diagnose_empty judged it
            obviously fixable) — the diagnosis facts are fed back into the
            prompt. Consumed (cleared) via the returned updates.

    Returns:
        Dict of state updates: intent, requires_visualization, pre_generated_sql,
        sql_query, llm_chart_type_hint, llm_chart_config_hint, sql_attempts
        (incremented), and — for off-topic non-follow-ups — needs_clarification/
        clarification_question instead.
    """
    updates: Dict[str, Any] = {
        "sql_attempts": (state.get("sql_attempts") or 0) + 1,
    }
    if diagnosis is not None:
        # Consumed by this call — clear so a later retry in the same turn
        # (e.g. a subsequent DB-error self-correct) doesn't re-send stale facts.
        updates["diagnosis"] = None

    is_correction = turn_type == "correction"
    is_retry = is_correction or bool(failed_sql and sql_error) or bool(diagnosis)
    reasoning_effort = "medium" if is_retry else "low"

    try:
        entities_json = json.dumps(entities or {})
        examples_text = _format_examples(retrieved_examples)
        conversation_section = build_conversation_section(conversation_snippet or "")
        correction_section = (
            build_correction_section(prior_sql, prior_answer, complaint_summary)
            if is_correction else ""
        )
        error_retry_section = build_error_retry_section(failed_sql, sql_error)
        diagnosis_retry_section = build_diagnosis_retry_section(diagnosis)

        prompt = GENERATE_SQL_PROMPT.format(
            entities_json=entities_json,
            schema_docs=retrieved_schema_docs or "(no schema retrieved)",
            examples_text=examples_text,
            conversation_section=conversation_section,
            correction_section=correction_section,
            error_retry_section=error_retry_section,
            diagnosis_retry_section=diagnosis_retry_section,
            user_query=user_query,
        )

        logger.info(
            f"GENERATE_SQL: Calling OpenAI (turn_type={turn_type}, "
            f"reasoning_effort={reasoning_effort})..."
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL_FAST", "gpt-5-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            reasoning_effort=reasoning_effort,
        )
        _accumulate_usage(state, response.usage)

        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)

        intent = data.get("intent", "unknown")
        requires_viz = bool(data.get("requires_visualization", False))
        sql = (data.get("sql") or "").strip()
        data_shape = data.get("data_shape_hint")
        chart_type = _SHAPE_TO_CHART.get(data_shape)
        chart_config = data.get("chart_config", {}) or {}

        # ── off_topic handling (mirrors understand_node in graph.py) ──────────
        if intent == "off_topic":
            followup_intent = _check_followup_tool_intent(conversation_history)
            if followup_intent:
                logger.info(f"GENERATE_SQL: Detected follow-up to {followup_intent}, overriding off_topic")
                intent = followup_intent
                sql = ""
            else:
                logger.info("GENERATE_SQL: LLM flagged query as off-topic")
                from app.data.database import get_data_recency
                recency = get_data_recency()
                earliest = recency["earliest_season"]
                hist_season = recency["historical_latest_season"]
                updates["needs_clarification"] = True
                updates["clarification_question"] = (
                    f"That doesn't seem to be an AFL question. I can help with Australian Football League "
                    f"statistics and data from {earliest} to {hist_season}, including match results, player stats, "
                    f"team performance, betting odds, and tipping predictions.\n\n"
                    f"Try something like: \"How many goals did Hawkins kick in 2024?\" or "
                    f"\"What are the odds for this week's games?\""
                )
                return updates

        if intent in NO_SQL_INTENTS:
            logger.info(f"GENERATE_SQL: {intent} query - no SQL needed")
            updates["intent"] = QueryIntent(intent)
            updates["requires_visualization"] = False
            updates["pre_generated_sql"] = None
            updates["sql_query"] = None
            updates["llm_chart_type_hint"] = None
            updates["llm_chart_config_hint"] = {}
            return updates

        # ── SQL-requiring intents ──────────────────────────────────────────────
        sql_upper = sql.upper().strip() if sql else ""
        if not sql or not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            raise ValueError(f"LLM returned invalid SQL: {sql[:200]!r}")

        sql = _clean_sql(sql)

        # Fix common LLM SQL mistake: ILIKE 'Name%' should be ILIKE '%Name%'
        sql = re.sub(r"ILIKE\s+'([^%'])", r"ILIKE '%\1", sql)

        # Deterministic GROUP BY pre-pass (see module docstring).
        sql = _maybe_fix_group_by(sql)

        try:
            resolved_intent = QueryIntent(intent)
        except ValueError:
            logger.warning(f"GENERATE_SQL: unknown intent '{intent}', defaulting to simple_stat")
            resolved_intent = QueryIntent.SIMPLE_STAT

        updates["intent"] = resolved_intent
        updates["requires_visualization"] = requires_viz
        updates["pre_generated_sql"] = sql
        updates["sql_query"] = sql
        updates["llm_chart_type_hint"] = chart_type
        updates["llm_chart_config_hint"] = chart_config

        logger.info(
            f"GENERATE_SQL: OK — intent={intent}, viz={requires_viz}, "
            f"chart_hint={chart_type}, sql={sql[:80]}..."
        )

    except Exception as e:
        # Mirrors understand_node's consolidated-call-failure fallback in graph.py:
        # do NOT set state["execution_error"] here — that field is scoped to
        # execute_node's own DB/SQL failures and respond_node treats its mere
        # presence as "show an error response", even if execute_node goes on to
        # succeed via its QueryBuilder fallback (pre_generated_sql=None). Falling
        # back to a plain simple_stat guess with no pre-generated SQL lets
        # execute_node's existing QueryBuilder fallback path take over, exactly as
        # it already does today when the v1 consolidated call fails.
        logger.error(f"GENERATE_SQL: LLM call failed ({type(e).__name__}: {e}), falling back to heuristic intent")
        updates["intent"] = QueryIntent.SIMPLE_STAT
        updates["requires_visualization"] = False
        updates["pre_generated_sql"] = None
        updates["sql_query"] = None

    return updates
