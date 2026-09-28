"""
AFL Analytics Agent - Retrieve Context Node (Milestone 3b)

Second stage of the pipeline, runs immediately after
`classify_resolve` and before `generate_sql`. Pure/deterministic — makes NO
LLM calls and NO database calls: it just prunes the curated schema docs
(app/agent/schema_docs.py) and picks the top few verified SQL examples
(app/agent/sql_examples.py) relevant to this turn, so `generate_sql`'s
prompt only carries what's actually relevant instead of the old ~300-line
embedded mega-prompt schema block.

`schema_docs.get_schema_docs`/`sql_examples.get_examples` both accept an
`intent` parameter for pruning, but a real QueryIntent doesn't exist yet at
this point in the v2 graph (that's `generate_sql`'s job, mirroring what the
old consolidated LLM call used to do). So this module derives a cheap,
deterministic HEURISTIC intent guess from keyword matching (no LLM) purely
to drive retrieval pruning/scoring — `generate_sql` makes the real
classification afterwards and is free to disagree with this guess.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from app.agent.schema_docs import get_schema_docs
from app.agent.sql_examples import get_examples

logger = logging.getLogger(__name__)


# Same shape as graph.py's UNDERSTAND-node heuristic fallback classifier, kept in sync
# in spirit (not imported, to keep this module dependency-free/no-LLM) — used only to
# steer retrieval pruning, never surfaced as the final intent.
_TIPPING_KEYWORDS = ("tip", "predict", "who will win", "who's going to win", "who should i")
_INJURY_KEYWORDS = ("injur", "out this week", "ruled out", "hamstring", "knee")
_NEWS_KEYWORDS = ("news", "latest", "headlines", "article")
_TREND_KEYWORDS = ("over time", "across time", "trend", "historical", "evolution", "year by year", "since")
_COMPARISON_KEYWORDS = ("compare", " vs ", "versus", "against")
_TEAM_KEYWORDS = ("performance", "record", "season", "how did", "ladder", "bye")


def _heuristic_intent_guess(user_query: str, entities: Dict[str, Any]) -> str:
    """Cheap, deterministic (no LLM) intent guess used ONLY to steer retrieval pruning."""
    query_lower = (user_query or "").lower()

    if any(kw in query_lower for kw in _TIPPING_KEYWORDS):
        return "tipping_advice"
    if any(kw in query_lower for kw in _INJURY_KEYWORDS):
        return "injury_news"
    if any(kw in query_lower for kw in _NEWS_KEYWORDS):
        return "afl_news"
    if any(kw in query_lower for kw in _TREND_KEYWORDS):
        return "trend_analysis"
    if any(kw in query_lower for kw in _COMPARISON_KEYWORDS):
        return "player_comparison"

    players = entities.get("players") or []
    teams = entities.get("teams") or []
    if len(players) + len(teams) >= 2:
        return "player_comparison"
    if any(kw in query_lower for kw in _TEAM_KEYWORDS):
        return "team_analysis"

    return "simple_stat"


def _build_conversation_snippet(conversation_history: Optional[List[Dict[str, Any]]]) -> str:
    """Cheap textual summary of the last couple of exchanges for the generate_sql prompt."""
    if not conversation_history:
        return ""
    recent = conversation_history[-4:]
    lines = []
    for msg in recent:
        role = msg.get("role", "unknown")
        content = (msg.get("content", "") or "")[:300]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def retrieve_context(
    user_query: str,
    entities: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Build the retrieved context for `generate_sql`: pruned schema docs + top-k
    verified SQL examples + a short conversation snippet, all keyed off a cheap
    heuristic intent guess (no LLM, no DB access).

    Returns a dict of state updates: retrieved_schema_docs, retrieved_examples,
    conversation_snippet.
    """
    entities = entities or {}
    heuristic_intent = _heuristic_intent_guess(user_query, entities)

    schema_docs = get_schema_docs(heuristic_intent, entities)
    examples = get_examples(user_query, heuristic_intent, entities, top_k=top_k)
    conversation_snippet = _build_conversation_snippet(conversation_history)

    logger.info(
        f"RETRIEVE_CONTEXT: heuristic_intent={heuristic_intent}, "
        f"schema_tables={len(schema_docs.split(chr(10)+chr(10)))}, examples={len(examples)}"
    )

    return {
        "retrieved_schema_docs": schema_docs,
        "retrieved_examples": examples,
        "conversation_snippet": conversation_snippet,
    }
