-- V7: conversation owner tokens + per-request grouping of api_usage rows (security 1A).
-- Run as the table owner BEFORE deploying the app version that reads these columns.

-- sha256 hex of the random owner token issued at conversation creation.
-- NULL for pre-existing conversations: those can no longer be read or appended to via the public API.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS owner_token_hash VARCHAR(64);

-- One chat turn may call several models; its rows share a request_id so quotas count turns.
ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS request_id VARCHAR(36);
CREATE INDEX IF NOT EXISTS ix_api_usage_request_id ON api_usage (request_id);
