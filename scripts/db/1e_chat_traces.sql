-- 1E: one row per v3 chat turn (tool calls, SQL, latency, tokens, real cost).
-- Written by the app role (not agent_ro). Apply: psql "$DB_STRING" -f scripts/db/1e_chat_traces.sql
CREATE TABLE IF NOT EXISTS chat_traces (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    conversation_id     UUID,
    visitor_id          VARCHAR(100),
    engine              VARCHAR(10) NOT NULL DEFAULT 'v3',
    question            TEXT NOT NULL,
    answer              TEXT,
    model               VARCHAR(80) NOT NULL,
    tool_calls          JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{name, args, latency_s, error, row_count, why_empty}]
    sql                 JSONB NOT NULL DEFAULT '[]'::jsonb,  -- every statement executed by tools
    llm_calls           JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{model, latency_s, first_text_s, usage, cost_usd, tool_calls}]
    latency_ms          INTEGER,
    ttft_ms             INTEGER,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens    INTEGER NOT NULL DEFAULT 0,
    cost_usd            NUMERIC(12, 8) NOT NULL DEFAULT 0,
    has_chart           BOOLEAN NOT NULL DEFAULT FALSE,
    error               TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_traces_created_at ON chat_traces (created_at);
CREATE INDEX IF NOT EXISTS idx_chat_traces_conversation ON chat_traces (conversation_id);
