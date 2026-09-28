"""
Eval harness data models.

`EvalCase` describes one evaluation scenario (single query or a multi-turn
sequence such as a correction chain) together with its expectations. Most
expectations are LIVE: the case's `verification_sql` runs against the DB at
eval time and `Fact` / `PairCheck` entries pull expected values out of those
rows (never hard-coded numbers), so cases do not rot as the season moves.

`TurnResult` / `EvalResult` capture what an engine produced and how it scored.

Check semantics (see scorer.py):
  - Every check axis is tri-state: True (passed), False (failed), None (not
    applicable to this case).
  - A case passes iff every applicable correctness axis is True. The
    `budget` axis (latency/tokens) only gates in --strict mode.
  - A case is SKIPPED (not run, not failed) when its ground truth cannot be
    computed: required column missing (pending 1C schema work), truth SQL
    error, or truth returned no rows while facts need them.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Names of the check axes, in reporting order.
CHECK_NAMES = [
    "facts",  # static expected_facts / expected_any / forbidden strings
    "truth_text",  # live truth Facts found in the answer text
    "truth_rows",  # live truth Facts / PairChecks found in the result rows
    "chart",  # chart presence/absence, ChartSpecV1 validity, type, series, unique x
    "chart_values",  # plotted values equal the live DB values
    "no_data",  # expects_no_data -> response explains WHY
    "correction",  # is_correction -> final answer materially changed
    "behaviour",  # refusal / clarification / disambiguation / injection safety
    "sql",  # expected SQL substrings present, forbidden SQL absent
    "budget",  # latency + token budget (gates only with --strict)
]

# Axes that decide pass/fail by default (budget is strict-only).
CORRECTNESS_CHECKS = [c for c in CHECK_NAMES if c != "budget"]

Where = Literal["text", "rows", "chart"]


class Fact(BaseModel):
    """One expected value pulled from the live verification rows.

    Passes if the value is found in ANY of `where` (answer text, the agent's
    result rows, or the plotted chart data). Numbers are matched with a
    tolerance: `tol` if given, else rounding-aware (an answer "27.7" matches a
    truth of 27.65; a non-integer truth needs at least one decimal shown).
    Strings are matched by name (full name, team aliases, or surname).
    """

    col: str
    row: int = 0
    all_rows: bool = False  # assert for every truth row (e.g. tied leaders)
    top: Optional[int] = None  # with all_rows: only the first N truth rows
    alts: List[str] = Field(default_factory=list)  # other truth cols that also satisfy
    where: List[Where] = Field(default_factory=lambda: ["text"])
    tol: Optional[float] = None
    render: Literal["auto", "ordinal"] = "auto"  # ordinal: 3 -> "3rd"/"third"


class PairCheck(BaseModel):
    """Row-level pairing: truth value `value` must sit WITH its key `key`.

    Catches "right name, wrong number" (e.g. Tom Green shown with 719 instead
    of 770). For charts, `key` matches the x label (or a series label, to allow
    either orientation) and `series` (optional) matches the other axis.
    """

    key: str
    value: str
    alts: List[str] = Field(default_factory=list)  # other value cols that also satisfy
    series: Optional[str] = None
    where: Literal["rows", "chart"] = "rows"
    top: Optional[int] = None  # only the first N truth rows
    min_frac: float = 1.0  # fraction of truth rows that must match
    tol: Optional[float] = None
    # Compare |cell| against |truth value|: a diverging-bar chart plots one
    # series negated (e.g. losses below zero), so the sign legitimately differs.
    abs_value: bool = False


class ChartExpect(BaseModel):
    """Structural + value expectations on the final turn's ChartSpecV1."""

    types: List[str] = Field(default_factory=list)  # allowed chartType values; empty = any
    series: Optional[int] = None  # exact series count
    min_series: Optional[int] = None
    max_series: Optional[int] = None
    unique_x: bool = True  # each x appears once (not for pie/scatter)
    min_points: Optional[int] = None
    max_points: Optional[int] = None  # categorical cap (2A): a bar/pie past ~25 x values is unreadable
    # Each label must appear among series keys/names or x values (e.g. every
    # requested metric of a multi-metric comparison).
    labels: List[str] = Field(default_factory=list)
    pairs: List[PairCheck] = Field(default_factory=list)
    # scatter: fraction of plotted (x, y) points that equal a truth (x_col, y_col) pair
    scatter_truth: Optional[Dict[str, str]] = None  # {"x": col, "y": col}
    scatter_min_frac: float = 0.8
    # A missing chart is not a failure (e.g. the model may reasonably answer
    # with a table instead once the categorical cap is hit) — only check the
    # fields above when a chart IS emitted.
    optional: bool = False


class Budget(BaseModel):
    """Per-case overrides of the run-level latency/token budgets."""

    max_turn_s: Optional[float] = None
    max_turn_tokens: Optional[int] = None


class EvalCase(BaseModel):
    """One evaluation scenario: a query (or multi-turn queries) + expectations."""

    id: str
    queries: List[str] = Field(min_length=1)
    tags: List[str] = Field(default_factory=list)
    description: str = ""
    # "m0_benchmark" | "salvaged" | "eval_queries" | "1d"
    source: str = "eval_queries"

    # ── Static string expectations (case-insensitive, word-boundary; final
    #    turn's response text + serialized chart). Use only for behaviour
    #    and names that can never change; numbers belong in `truth`. ──
    expected_facts: List[str] = Field(default_factory=list)  # ALL must appear
    expected_any: List[str] = Field(default_factory=list)  # at least ONE must appear
    forbidden: List[str] = Field(default_factory=list)  # NONE may appear
    expects_chart: bool = False
    expects_no_chart: bool = False
    expects_no_data: bool = False
    is_correction: bool = False
    expected_sql_substrings: List[str] = Field(default_factory=list)
    # NONE may appear (case-insensitive) in ANY turn's executed SQL / tool calls.
    forbidden_sql: List[str] = Field(default_factory=list)

    # ── Live ground truth ──
    verification_sql: Optional[str] = None
    # "table.column" entries that must exist (e.g. 1C's matches.round_name);
    # the case is skipped with a clear reason when one is missing.
    requires_columns: List[str] = Field(default_factory=list)
    truth: List[Fact] = Field(default_factory=list)
    pairs: List[PairCheck] = Field(default_factory=list)  # rows-level pair checks
    chart: Optional[ChartExpect] = None
    # Empty truth -> "skip" the case, or "expect_no_data": the data really is
    # missing today (e.g. 2026 R16-24 stats), so the agent must explain why.
    on_empty_truth: Literal["skip", "expect_no_data"] = "skip"

    # ── Behaviour ──
    expects_refusal: bool = False  # off-topic / injection: decline + redirect to AFL
    expects_clarification: bool = False  # asks a clarifying question
    # All must appear, OR the agent asks a clarifying question instead.
    disambiguate: List[str] = Field(default_factory=list)
    # Run before and after the case; results must be identical (DB untouched).
    integrity_sql: Optional[str] = None
    # When this returns a truthy first cell, the data is known to be partial
    # and the answer must carry a coverage caveat (scored under behaviour).
    caveat_sql: Optional[str] = None

    budget: Budget = Field(default_factory=Budget)

    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
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

    @property
    def has_ground_truth(self) -> bool:
        """True when the case asserts something checkable beyond 'responded'."""
        return bool(
            self.verification_sql
            or self.expects_refusal
            or self.expects_clarification
            or self.disambiguate
            or self.expects_no_data
            or self.forbidden_sql
        )


class ToolCall(BaseModel):
    """One data access the engine made (v2: SQL attempts; v3: tool calls)."""

    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    sql: Optional[str] = None
    row_count: Optional[int] = None
    error: Optional[str] = None


class TurnResult(BaseModel):
    """What one driven turn produced (engine-agnostic)."""

    query: str
    response_text: str = ""
    latency_s: Optional[float] = None
    ttft_s: Optional[float] = None  # time to first streamed token (v3)
    chart_spec: Optional[Dict[str, Any]] = None
    sql: Optional[str] = None  # final SQL that produced `rows`
    tool_calls: List[ToolCall] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)  # capped result rows
    row_count: Optional[int] = None  # uncapped
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    # Engine-specific bits needed to rebuild history (e.g. v2 entities).
    engine_meta: Dict[str, Any] = Field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class EvalResult(BaseModel):
    """Scored outcome of driving one EvalCase end-to-end (one repeat)."""

    case_id: str
    run: int = 0  # repeat index
    tags: List[str] = Field(default_factory=list)
    source: str = ""
    status: Literal["pass", "fail", "skip", "error"] = "fail"
    skip_reason: Optional[str] = None
    turns: List[TurnResult] = Field(default_factory=list)
    checks: Dict[str, Optional[bool]] = Field(default_factory=dict)
    failures: List[str] = Field(default_factory=list)  # human-readable reasons
    truth_rows: List[Dict[str, Any]] = Field(default_factory=list)
    passed: bool = False  # correctness axes only
    budget_ok: Optional[bool] = None
    integrity_ok: Optional[bool] = None  # DB unchanged by the case (integrity_sql)
    judge: Optional[Dict[str, Any]] = None  # triage only, never gates
    error: Optional[str] = None  # harness-level failure

    @property
    def total_latency_s(self) -> float:
        return round(sum(t.latency_s or 0.0 for t in self.turns), 3)

    @property
    def total_tokens(self) -> Dict[str, int]:
        return {
            "input_tokens": sum(t.input_tokens for t in self.turns),
            "output_tokens": sum(t.output_tokens for t in self.turns),
        }
