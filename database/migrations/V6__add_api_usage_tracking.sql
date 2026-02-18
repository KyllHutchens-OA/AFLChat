-- Migration: Add API usage tracking table for cost monitoring and rate limiting
-- This table tracks OpenAI API calls to enforce per-visitor and global daily limits

CREATE TABLE IF NOT EXISTS api_usage (
    id SERIAL PRIMARY KEY,
    visitor_id VARCHAR(100) NOT NULL,
    ip_address VARCHAR(45),
    endpoint VARCHAR(100),
    model VARCHAR(50),
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost_usd NUMERIC(10, 6),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_api_usage_visitor_id ON api_usage(visitor_id);
CREATE INDEX IF NOT EXISTS idx_api_usage_ip_address ON api_usage(ip_address);
CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp ON api_usage(timestamp);

-- Composite index for daily limit checks (visitor + date)
CREATE INDEX IF NOT EXISTS idx_api_usage_visitor_date ON api_usage(visitor_id, timestamp);

COMMENT ON TABLE api_usage IS 'Tracks OpenAI API usage for cost monitoring and rate limiting';
COMMENT ON COLUMN api_usage.visitor_id IS 'Unique visitor identifier from frontend';
COMMENT ON COLUMN api_usage.estimated_cost_usd IS 'Estimated cost in USD based on token counts and model pricing';
