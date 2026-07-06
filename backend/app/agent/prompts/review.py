"""
AFL Analytics Agent - Review Prompt (Milestone 3d)

Small, cheap sanity-check prompt run by `app/agent/review.py` after `execute`
returns non-empty rows. Deliberately thin — no schema docs, no examples, no
re-derivation of SQL: it's just handed the question, the SQL that ran, and a
small sample of the rows it produced, and asked one yes/no question.
"""

REVIEW_PROMPT = """\
You are sanity-checking the result of an AFL analytics SQL query. Answer ONE \
question: does this result set actually answer the user's question? Do not \
re-run or rewrite the SQL yourself — just judge the SQL and sample rows given.

## User's question
{user_query}

## SQL that was executed
{sql_query}

## Result: {row_count} row(s) total, sample below (up to 10 rows)
{sample_rows_json}

Say NO if the SQL clearly grouped, filtered, or joined on the wrong thing, \
answers a different question than what was asked, or the columns returned \
don't match what the question asks for. Say YES if the result plausibly \
answers the question, even if you'd have written the SQL slightly \
differently — default to YES when in doubt.

## Output (JSON only, no markdown)
{{
  "verdict": "YES"|"NO",
  "reason": "one sentence explaining the verdict"
}}"""
