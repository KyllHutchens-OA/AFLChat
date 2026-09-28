"""
AFL Analytics Agent - Classify & Resolve Node (Milestone 3a)

First stage of the pipeline. Runs BEFORE any SQL/DB
work:
  1. One small LLM call classifies the turn (turn_type) and does a best-effort
     entity extraction pass.
  2. A deterministic EntityResolver pass resolves the raw entity strings to
     canonical DB values (team nicknames, player disambiguation, season range
     checks) — same resolver used by the v1 `understand_node`.
  3. For turn_type == "correction", sets `bypass_cache` and loads the prior
     turn's persisted SQL/row_count/answer from conversation history so the
     downstream nodes can use them (self-correction, M3b+).

Falls back gracefully on LLM failure: turn_type defaults to "new_question"
with empty entities, so a classify failure degrades to "treat it like any
other new question" rather than blocking the pipeline.

NOTE: `_accumulate_usage` is intentionally duplicated (not imported) from
graph.py to avoid a circular import — graph.py imports this module to wire
the v2 node, so this module must not import graph.py back.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from app.agent.prompts.classify import CLASSIFY_PROMPT
from app.analytics.entity_resolver import EntityResolver

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(60.0, connect=10.0),
)

VALID_TURN_TYPES = {
    "new_question",
    "follow_up",
    "correction",
    "clarification_answer",
    "chitchat",
}


def _accumulate_usage(state: Dict[str, Any], usage: Any, model: Optional[str] = None) -> None:
    """Merge real OpenAI token usage (per model) into the per-request state accumulator."""
    from app.middleware.usage_tracker import record_llm_usage
    record_llm_usage(state, usage, model)


def _build_recent_context(conversation_history: Optional[List[Dict[str, Any]]]) -> str:
    """Cheap textual summary of the last couple of exchanges for the classify prompt."""
    if not conversation_history:
        return "(no previous conversation)"

    recent = conversation_history[-4:]
    lines = []
    for msg in recent:
        role = msg.get("role", "unknown")
        content = (msg.get("content", "") or "")[:300]
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no previous conversation)"


def _find_prior_assistant_message(
    conversation_history: Optional[List[Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """Return the most recent assistant message dict, or None if there isn't one."""
    if not conversation_history:
        return None
    for msg in reversed(conversation_history):
        if msg.get("role") == "assistant":
            return msg
    return None


def classify_and_resolve(
    user_query: str,
    conversation_history: Optional[List[Dict[str, Any]]],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run the classify LLM call, resolve entities, and (for corrections) load
    prior-turn context.

    Args:
        user_query: Current user message.
        conversation_history: Recent conversation messages (role/content/metadata dicts).
        state: The in-flight AgentState — used only so token usage can be
            accumulated via state["token_usage"]; not mutated otherwise (the
            caller merges the returned dict into state itself).

    Returns:
        Dict of state updates: turn_type, entities, warnings (appended),
        complaint_summary, natural_language_summary + confidence (chitchat
        only), bypass_cache/prior_sql/prior_row_count/prior_answer (correction
        only).
    """
    updates: Dict[str, Any] = {}

    try:
        conversation_context = _build_recent_context(conversation_history)
        prompt = CLASSIFY_PROMPT.format(
            conversation_context=conversation_context,
            user_query=user_query,
        )

        logger.info("CLASSIFY: Calling OpenAI (turn_type + entity extraction)...")
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            reasoning_effort="low",
        )
        _accumulate_usage(state, response.usage, getattr(response, "model", None))

        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)

        turn_type = data.get("turn_type") or "new_question"
        if turn_type not in VALID_TURN_TYPES:
            logger.warning(f"CLASSIFY: unknown turn_type '{turn_type}', defaulting to new_question")
            turn_type = "new_question"
        updates["turn_type"] = turn_type

        complaint_summary = data.get("complaint_summary") or None
        if turn_type == "correction" and complaint_summary:
            updates["complaint_summary"] = complaint_summary

        # ── Deterministic entity resolution (same resolver v1's understand_node uses) ──
        raw_entities = data.get("entities") or {}
        validation_result = EntityResolver.validate_entities(raw_entities)
        updates["entities"] = validation_result["corrected_entities"]
        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                logger.warning(f"CLASSIFY entity resolution: {warning}")
            existing_warnings = list(state.get("warnings", []) or [])
            existing_warnings.extend(validation_result["warnings"])
            updates["warnings"] = existing_warnings

        # ── Chitchat: answer directly, no DB/SQL work needed ──────────────────
        if turn_type == "chitchat":
            chitchat_reply = data.get("chitchat_reply") or None
            if chitchat_reply:
                updates["natural_language_summary"] = chitchat_reply
                updates["confidence"] = 0.9

        # ── Correction plumbing: bypass cache + load prior turn context ───────
        if turn_type == "correction":
            updates["bypass_cache"] = True
            prior_msg = _find_prior_assistant_message(conversation_history)
            if prior_msg:
                updates["prior_sql"] = prior_msg.get("sql")
                updates["prior_row_count"] = prior_msg.get("row_count")
                updates["prior_answer"] = prior_msg.get("content")
            else:
                logger.info("CLASSIFY: turn_type=correction but no prior assistant message found in history")

        logger.info(f"CLASSIFY: turn_type={turn_type}")
        logger.debug(
            f"CLASSIFY: entities={updates.get('entities')}, complaint_summary={complaint_summary!r}"
        )

    except Exception as e:
        logger.error(f"CLASSIFY: LLM call failed ({type(e).__name__}: {e}), defaulting to new_question")
        updates["turn_type"] = "new_question"
        updates["entities"] = {}

    return updates
