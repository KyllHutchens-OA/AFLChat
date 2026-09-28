"""
AFL Analytics Agent - Generate SQL Prompt (Milestone 3b)

Replaces the ~300-line embedded mega-prompt in the old (removed)
`consolidated_llm.py` with a
much smaller prompt built from RETRIEVED context: pruned schema docs
(app/agent/schema_docs.py) + a handful of verified SQL examples
(app/agent/sql_examples.py) relevant to this specific question, instead of
dumping the full schema + every few-shot example into every call.

This prompt still does double duty as the old `understand_node` did for v2:
classify the turn into a final QueryIntent bucket (including the non-SQL
tool intents so `execute_node`'s existing routing keeps working unchanged)
AND generate the SQL, in one LLM call — `retrieve_context`/`classify_resolve`
already did entity extraction/resolution, so this call is told to trust
those entities rather than re-deriving them from scratch.
"""

GENERATE_SQL_PROMPT = """\
You are an AFL analytics expert. Using the schema documentation and verified \
example queries below, do TWO things for the user's question:
1. Classify its intent.
2. If it needs a database query, write ONE valid PostgreSQL SELECT (or WITH ... SELECT) \
statement that answers it.

## Intent classification (pick exactly one)
- "simple_stat": a single fact/number, match result, or short follow-up about a \
player/team/match already established in conversation.
- "player_comparison": comparing 2+ players.
- "team_analysis": one team's performance in a season/period (including ladder \
position, bye rounds, venue splits).
- "trend_analysis": change over TIME — keywords like "over time", "trend", "since", \
"year by year", "historical", "evolution".
- "afl_news": latest AFL news/articles. Set sql to "".
- "injury_news": injury reports/availability. Set sql to "".
- "tipping_advice": tipping/predictions. Set sql to "".
- "off_topic": genuinely non-AFL question (weather, recipes, other sports) — but a \
follow-up about an AFL topic already in the conversation is NEVER off_topic.

## Resolved entities (already extracted + normalized upstream — trust these; only \
override if the conversation snippet below clearly implies something more specific)
{entities_json}

## Relevant schema (pruned to this question)
{schema_docs}

## Verified example queries (similar shape to this question)
{examples_text}

## SQL rules
1. Only SELECT (or WITH ... SELECT) statements — no INSERT/UPDATE/DELETE/DROP.
2. GROUP BY must include every non-aggregated SELECT column (a deterministic pass \
fixes simple cases automatically afterwards, but try to get it right).
3. ORDER BY ... DESC should add NULLS LAST.
4. Never use CROSS JOIN.
5. Quote `round` values as strings: WHERE m.round = '5', not = 5.
6. For "since <year>" / "all-time" phrasing, use `season >= <year>` (a range) — not \
`season = <year>`. Double-check every named team/player/opponent actually appears in \
the WHERE clause; don't silently drop a filter to make the query simpler.
7. When a query is about a specific team's score/opponent, use the CASE pattern shown \
in the examples above — never assume the team is always home or always away.

{conversation_section}
{correction_section}
{error_retry_section}
{diagnosis_retry_section}
{review_critique_section}
## User's current question
{user_query}

## Output (JSON only, no markdown)
{{
  "intent": "simple_stat"|"player_comparison"|"team_analysis"|"trend_analysis"|"afl_news"|"injury_news"|"tipping_advice"|"off_topic",
  "requires_visualization": true|false,
  "data_shape_hint": "temporal_trend"|"top_n_ranking"|"comparison"|"single_value"|"distribution"|null,
  "chart_config": {{"x_col_hint": "column name for x-axis, or null", "y_col_hint": "column name for y-axis, or null"}},
  "sql": "SELECT ... (or empty string for afl_news/injury_news/tipping_advice/off_topic)"
}}

requires_visualization: true for trends over time, comparisons of 3+ entities, top-N \
rankings (N>=3), round-by-round data. false for single facts, yes/no answers, match \
results, 1-2 row results, news/tips.
"""


CORRECTION_SECTION_TEMPLATE = """\
## This is a CORRECTION turn
The user says the previous answer was wrong. Produce DIFFERENT SQL that addresses \
their complaint — do not just repeat the prior query.

Prior SQL:
{prior_sql}

Prior answer given to the user:
{prior_answer}

What the user says was wrong:
{complaint_summary}

"""


def build_conversation_section(conversation_snippet: str) -> str:
    if not conversation_snippet or not conversation_snippet.strip():
        return ""
    return f"## Recent conversation (for resolving follow-up context)\n{conversation_snippet}\n\n"


def build_correction_section(
    prior_sql: str = None,
    prior_answer: str = None,
    complaint_summary: str = None,
) -> str:
    if not (prior_sql or prior_answer or complaint_summary):
        return ""
    return CORRECTION_SECTION_TEMPLATE.format(
        prior_sql=prior_sql or "(not available)",
        prior_answer=prior_answer or "(not available)",
        complaint_summary=complaint_summary or "(not specified)",
    )


# ── Milestone 3c: self-correct-on-error retry + diagnose_empty-driven retry ──

ERROR_RETRY_SECTION_TEMPLATE = """\
## This SQL FAILED — produce corrected SQL
The SQL below failed when executed against the database with the exact \
PostgreSQL error shown. Produce corrected SQL that fixes the problem — do \
not just repeat the same query.

SQL that failed:
{failed_sql}

Database error:
{sql_error}

"""

DIAGNOSIS_RETRY_SECTION_TEMPLATE = """\
## Previous query returned ZERO rows — diagnosis below
{human_reason}

{suggestion}

"""


def build_error_retry_section(failed_sql: str = None, sql_error: str = None) -> str:
    """Self-correct-on-DB-error retry section (Milestone 3c). Empty unless both are present."""
    if not (failed_sql and sql_error):
        return ""
    return ERROR_RETRY_SECTION_TEMPLATE.format(
        failed_sql=failed_sql,
        sql_error=sql_error,
    )


def build_diagnosis_retry_section(diagnosis: dict = None) -> str:
    """diagnose_empty-driven retry section (Milestone 3c). Only meaningful when fixable."""
    if not diagnosis or not diagnosis.get("fixable"):
        return ""
    return DIAGNOSIS_RETRY_SECTION_TEMPLATE.format(
        human_reason=diagnosis.get("human_reason") or "",
        suggestion=diagnosis.get("suggestion") or "Produce corrected SQL that returns rows.",
    )


# ── Milestone 3d: review-driven retry (SQL ran, returned rows, but the ──────
# review node judged those rows don't actually answer the question) ─────────

REVIEW_CRITIQUE_SECTION_TEMPLATE = """\
## Previous query returned data that did NOT answer the question
The previous SQL ran successfully and returned rows, but a review pass \
judged that those rows do not answer the user's question, because: \
{reason}

Produce corrected SQL that actually answers the user's question — do not \
just repeat the same query.

"""


def build_review_critique_section(review_critique: str = None) -> str:
    """Review-driven retry section (Milestone 3d). Empty unless a critique reason is present."""
    if not review_critique:
        return ""
    return REVIEW_CRITIQUE_SECTION_TEMPLATE.format(reason=review_critique)
