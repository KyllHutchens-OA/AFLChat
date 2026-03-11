# Plan: Token Usage Tracking & Notifications

## Overview
Surface real token/cost data in the admin dashboard and send proactive notifications
when spending approaches or exceeds thresholds.

---

## What Already Exists (Don't Rebuild)
- `APIUsage` table — has `input_tokens`, `output_tokens`, `estimated_cost_usd` columns
- `UsageTracker` service — cost calculation logic, daily limit enforcement ($5/day global, 50 req/visitor)
- `APIRequestLog` table — already tracks external API costs (Tavily, Odds API)
- Admin dashboard at `/api/admin/` — page views, visitor, conversation data already shown
- Model pricing dict in `usage_tracker.py` — includes `gpt-5-nano` rates

---

## Step 1 — Extract Real Token Counts from OpenAI

**File:** `backend/app/agent/consolidated_llm.py`

The `response` object from `client.chat.completions.create()` contains a `usage` attribute
that is currently ignored. Extract it and return alongside the parsed result:

- Read `response.usage.prompt_tokens` and `response.usage.completion_tokens`
- Return token counts from `understand_and_generate_sql()` so callers can log them

**File:** `backend/app/api/websocket.py`

Replace the hardcoded estimates:
```python
# Current (wrong):
input_tokens=500,
output_tokens=200,
```
With the actual values returned from the consolidated LLM call.

---

## Step 2 — Add Cost & Token Section to Admin Dashboard

**File:** `backend/app/api/analytics.py`

Add a new section to the `/api/admin/data` JSON response:

```json
{
  "usage": {
    "today": {
      "total_requests": 42,
      "total_input_tokens": 18500,
      "total_output_tokens": 6200,
      "total_cost_usd": 0.87,
      "unique_visitors": 12,
      "budget_remaining_usd": 4.13,
      "budget_used_pct": 17.4
    },
    "by_model": [
      { "model": "gpt-5-nano", "requests": 40, "cost_usd": 0.85 }
    ],
    "external_apis": {
      "tavily": { "requests": 2, "cost_usd": 0.01 },
      "theoddsapi": { "requests": 1, "cost_usd": 0.001 }
    }
  }
}
```

Add a "Cost & Usage" card to the dashboard HTML showing:
- Daily spend vs budget (progress bar, colour-coded: green < 50%, orange < 80%, red > 80%)
- Total tokens today (input / output split)
- External API spend breakdown (Tavily, Odds API)
- 7-day spend trend (small table or chart)

---

## Step 3 — Notification System

### Trigger Points (in `UsageTracker.check_limits()`)
Send a notification when:
| Threshold | Message |
|---|---|
| Global daily cost > 80% of limit ($4.00) | Warning: approaching daily budget |
| Global daily cost > 100% of limit ($5.00) | Alert: daily budget exceeded, requests blocked |
| Single visitor > 40 requests (80% of 50) | Warning: high usage from one visitor |
| Tavily monthly spend > $0.80 (80% of ~$1.00 estimate) | Warning: Tavily approaching free tier |

### Notification Channel — Email via Resend
**Why Resend:** Free tier is 3,000 emails/month, no credit card required, simple REST API,
no SDK needed (plain `requests` call).

**New env var required:** `RESEND_API_KEY`, `ALERT_EMAIL` (your address)

**New file:** `backend/app/services/notifier.py`

```python
class Notifier:
    @staticmethod
    def send_alert(subject: str, body: str) -> bool:
        """Send email alert via Resend API. Fire-and-forget, never raises."""

    @staticmethod
    def _already_sent_today(alert_key: str) -> bool:
        """Prevent duplicate alerts — one alert per threshold per day."""
```

Use a simple in-memory set (or Redis if available) to deduplicate: don't send the same
alert type more than once per day.

**Integration point:** Call `Notifier.send_alert()` inside `UsageTracker.check_limits()`
after logging the warning — no other files need to change.

---

## Step 4 — Tavily Monthly Budget Guard

**File:** `backend/app/agent/tools.py` (`NewsTool._search_web`)

Before calling Tavily, check `APIRequestLog` for the current calendar month:
- Count successful Tavily requests this month
- If >= 950 (out of 1,000 free credits), skip the web fallback and log a warning
- This prevents accidentally going into paid tier

---

## Files to Change Summary

| File | Change |
|---|---|
| `backend/app/agent/consolidated_llm.py` | Return actual `response.usage` token counts |
| `backend/app/api/websocket.py` | Use real token counts instead of hardcoded estimates |
| `backend/app/api/analytics.py` | Add cost/usage data to `/api/admin/data` and dashboard HTML |
| `backend/app/middleware/usage_tracker.py` | Call `Notifier.send_alert()` at threshold points |
| `backend/app/agent/tools.py` | Add Tavily monthly budget guard |
| `backend/app/services/notifier.py` | **New file** — Resend email alerts |
| `backend/requirements.txt` | No new packages needed (uses `requests` which is already listed) |

## New Env Vars Required
```
RESEND_API_KEY=re_...
ALERT_EMAIL=you@example.com
```

---

## Out of Scope
- SMS notifications
- Slack integration (can be added later by changing `notifier.py` only)
- Per-conversation cost breakdown in chat UI
- Changing the $5/day or 50 req/visitor limits (already configurable via env vars in `usage_tracker.py`)
