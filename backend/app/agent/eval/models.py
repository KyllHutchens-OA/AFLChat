"""
Eval harness data models.

`EvalCase` describes one evaluation scenario (single query or a multi-turn
sequence such as a correction pair) together with its deterministic
expectations. `TurnResult` / `EvalResult` capture what actually happened when
the case was driven through the agent (in-process or over WebSocket) plus the
per-axis check outcomes attached by the scorer.

Check semantics (see scorer.py):
  - Every check is tri-state: True (passed), False (failed), or None
    (not applicable to this case — e.g. `chart` when no chart was expected).
  - A case "passes" iff every applicable (non-None) check is True.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# Names of the deterministic check axes, in reporting order.
CHECK_NAMES = [
    "facts",  # all expected_facts + >=1 expected_any + no forbidden strings
    "chart",  # expects_chart -> present & ChartSpecV1-valid; expects_no_chart -> absent
    "no_data",  # expects_no_data -> response explains WHY (not a generic fallback)
    "correction",  # is_correction -> final turn materially changed the answer
    "sql",  # expected_sql_substrings all appear in the final turn's SQL
]


class EvalCase(BaseModel):
    """One evaluation scenario: a query (or multi-turn queries) + expectations."""

    id: str
    queries: List[str] = Field(min_length=1)
    tags: List[str] = Field(default_factory=list)
    description: str = ""
    # Where this case came from: "m0_benchmark" | "salvaged" | "eval_queries"
    source: str = "eval_queries"

    # ── Deterministic expectations (all substring checks are case-insensitive
    #    and run against the FINAL turn's response text + serialized chart) ──
    expected_facts: List[str] = Field(default_factory=list)  # ALL must appear
    expected_any: List[str] = Field(default_factory=list)  # at least ONE must appear
    forbidden: List[str] = Field(default_factory=list)  # NONE may appear
    expects_chart: bool = False
    expects_no_chart: bool = False
    expects_no_data: bool = False
    is_correction: bool = False  # multi-turn pair whose last turn corrects the first
    # All must appear (case-insensitive) in the final turn's executed SQL.
    expected_sql_substrings: List[str] = Field(default_factory=list)

    # Synthetic conversation history injected BEFORE the first turn (message
    # dicts shaped like ConversationService messages: role/content/+metadata).
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Audit trail: how the expected facts were established (not used to score).
    verification_sql: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("queries")
    @classmethod
    def _non_empty_queries(cls, v: List[str]) -> List[str]:
        if any(not q.strip() for q in v):
            raise ValueError("queries must be non-empty strings")
        return v

    @property
    def multi_turn(self) -> bool:
        return len(self.queries) > 1


class TurnResult(BaseModel):
    """What one driven turn produced."""

    query: str
    response_text: str = ""
    latency_s: Optional[float] = None
    chart_spec: Optional[Dict[str, Any]] = None
    sql: Optional[str] = None
    row_count: Optional[int] = None
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


class EvalResult(BaseModel):
    """Scored outcome of driving one EvalCase end-to-end."""

    case_id: str
    tags: List[str] = Field(default_factory=list)
    source: str = ""
    turns: List[TurnResult] = Field(default_factory=list)
    # Tri-state per-axis outcomes, keyed by CHECK_NAMES entries.
    checks: Dict[str, Optional[bool]] = Field(default_factory=dict)
    passed: bool = False
    # Optional LLM judge verdict: {"verdict": ..., "reason": ...}
    judge: Optional[Dict[str, Any]] = None
    # Harness-level failure (exception while driving the case), distinct from
    # the agent returning a bad answer.
    error: Optional[str] = None

    @property
    def total_latency_s(self) -> float:
        return round(sum(t.latency_s or 0.0 for t in self.turns), 3)

    @property
    def total_tokens(self) -> Dict[str, int]:
        return {
            "input_tokens": sum(t.input_tokens for t in self.turns),
            "output_tokens": sum(t.output_tokens for t in self.turns),
        }
