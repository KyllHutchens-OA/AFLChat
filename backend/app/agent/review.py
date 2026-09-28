"""
AFL Analytics Agent - Review Node (Milestone 3d)

Runs when `execute` returns NON-EMPTY rows for a SQL-backed intent (v2
pipeline only). `diagnose_empty` (M3c) only catches the "SQL ran and returned
ZERO rows" failure mode; this catches the sibling failure mode where the SQL
ran successfully and returned rows, but grouped/filtered/joined on the wrong
thing so those rows don't actually answer what the user asked (e.g. "who is
the best defender this season?" resolving to a metric that doesn't capture
defensive contribution).

Deliberately cheap, by design:
- `reasoning_effort="low"`.
- The prompt carries only the user's question, the executed SQL, and a
  sample of <=10 result rows (+ the total row count) — no schema docs, no
  retrieved examples, no conversation history.
- Skipped entirely for trivial template answers (see `should_skip_review`)
  where there's no meaningful grouping/aggregation choice worth
  second-guessing.

Parses a strict YES/NO + one-line reason. ANY parse failure — malformed JSON,
a missing/unrecognized verdict field, or an LLM/network exception — defaults
to a pass-through YES verdict: a flaky review call must never block an
otherwise-successful answer from reaching the user.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from app.agent.prompts.review import REVIEW_PROMPT
from app.agent.state import QueryIntent
from app.utils.json_serialization import make_json_serializable

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(60.0, connect=10.0),
)

SAMPLE_ROW_LIMIT = 10

# ── Skip heuristic (Milestone 3d, "skip for trivial template answers") ──────
# A single-row simple_stat result — e.g. "How many goals did Hawkins kick in
# 2024?" — is exactly respond_node's `_try_template_response` Pattern 1
# (graph.py): one subject, one or a handful of numeric columns, no
# aggregation/grouping/join choice left for the SQL to have gotten subtly
# wrong. Reviewing it would just spend an LLM call re-confirming arithmetic
# that was never ambiguous. Comparisons, trends, team analysis, and
# multi-row rankings are NOT trivial — those are exactly the shapes where a
# subtly-wrong SQL query (wrong GROUP BY column, wrong aggregation, wrong
# join, wrong entity) still returns non-empty rows that don't actually answer
# the question, so they always go through review.
_TRIVIAL_INTENTS = {QueryIntent.SIMPLE_STAT}


def should_skip_review(
    intent: Optional[Any],
    analysis_mode: Optional[str],
    row_count: int,
) -> bool:
    """
    Deterministic skip heuristic — True when review should be bypassed
    entirely (no LLM call) because the result is a trivial template answer:
    exactly one result row, intent == SIMPLE_STAT, and analysis_mode ==
    "summary" (an in_depth SIMPLE_STAT is not expected, but summary-mode is
    required defensively so a scored-as-in-depth turn never skips review).
    """
    return (
        analysis_mode == "summary"
        and intent in _TRIVIAL_INTENTS
        and row_count == 1
    )


def _sample_rows(query_results: Any, limit: int = SAMPLE_ROW_LIMIT) -> Tuple[List[Dict[str, Any]], int]:
    """Return (sampled rows as JSON-safe dicts, total row count)."""
    if query_results is None:
        return [], 0
    if isinstance(query_results, pd.DataFrame):
        total = len(query_results)
        records = query_results.head(limit).to_dict(orient="records")
        return make_json_serializable(records), total
    if isinstance(query_results, list):
        total = len(query_results)
        return make_json_serializable(query_results[:limit]), total
    return [], 0


def _accumulate_usage(state: Dict[str, Any], usage: Any, model: Optional[str] = None) -> None:
    """Merge real OpenAI token usage (per model) into the per-request state accumulator."""
    from app.middleware.usage_tracker import record_llm_usage
    record_llm_usage(state, usage, model)


def _default_verdict(reason: str) -> Dict[str, Any]:
    """Pass-through verdict used whenever the review call itself can't be trusted."""
    return {"verdict": "YES", "reason": reason}


def review_results(
    user_query: str,
    sql_query: Optional[str],
    query_results: Any,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run the review LLM call.

    Args:
        user_query: The current user question.
        sql_query: The SQL that was executed to produce query_results.
        query_results: The DataFrame (or list, for tool-based results —
            though those never reach this node, see _route_after_execute_v2)
            returned by execute.
        state: The in-flight AgentState — used only so token usage can be
            accumulated via state["token_usage"]; not mutated otherwise (the
            caller merges the returned dict into state itself).

    Returns:
        {"verdict": "YES"|"NO", "reason": str}
    """
    sample_rows, total_rows = _sample_rows(query_results)

    try:
        prompt = REVIEW_PROMPT.format(
            user_query=user_query,
            sql_query=sql_query or "(no SQL)",
            row_count=total_rows,
            sample_rows_json=json.dumps(sample_rows, indent=2),
        )

        logger.info("REVIEW: Calling OpenAI (results sanity check)...")
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL_FAST", "gpt-5-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            reasoning_effort="low",
        )
        _accumulate_usage(state, response.usage, getattr(response, "model", None))

        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)

        verdict = str(data.get("verdict", "")).strip().upper()
        reason = data.get("reason") or ""

        if verdict not in ("YES", "NO"):
            logger.warning(f"REVIEW: unrecognized verdict {verdict!r}, defaulting to YES (pass-through)")
            return _default_verdict("Review returned an unrecognized verdict; proceeding with the results.")

        logger.info(f"REVIEW: verdict={verdict}, reason={reason!r}")
        return {"verdict": verdict, "reason": reason}

    except Exception as e:
        logger.error(f"REVIEW: LLM call failed ({type(e).__name__}: {e}), defaulting to YES (pass-through)")
        return _default_verdict("Review call failed; proceeding with the results.")
