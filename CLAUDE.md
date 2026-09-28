# AFL App — CLAUDE.md

This is **Footy-NAC** (Not Another Commentator): an AI-powered AFL analytics platform. Users ask natural-language questions about AFL stats, get interactive Recharts charts, and follow live games in real-time.

---

## Project Structure

```
AFL App/
├── backend/                     # Flask + LangGraph API
│   ├── app/
│   │   ├── agent/               # v2 LangGraph pipeline (graph, nodes, prompts/, eval/) + v3/ tool-calling loop and llm.py
│   │   ├── api/                 # REST + WebSocket endpoints (routes, websocket, analytics, reports)
│   │   ├── analytics/           # Entity resolver, context enrichment, stats, validators
│   │   ├── data/                # SQLAlchemy models, database.py, ingestion scripts, migrations
│   │   ├── middleware/          # Rate limiting (Flask-Limiter), usage tracking
│   │   ├── scheduler/           # Background job scheduler
│   │   ├── services/            # Business logic (conversations, live games, summaries, odds)
│   │   ├── utils/               # JSON serialization, validators
│   │   ├── visualization/       # Chart selection, Recharts spec builder (ChartSpecV1), preprocessor
│   │   ├── __init__.py          # Flask app factory (CORS, SocketIO, blueprints)
│   │   └── config.py            # Env var config
│   ├── run.py                   # Entry point
│   ├── requirements.txt
│   └── Procfile                 # Railway: gunicorn + geventwebsocket
│
├── frontend/                    # React 18 + Vite + TypeScript + Tailwind
│   ├── src/
│   │   ├── components/          # Chat/, Layout/, LiveGames/, Modal/, Visualization/
│   │   ├── contexts/            # SpoilerContext
│   │   ├── hooks/               # useAgentWebSocket, useLiveGames, useLiveGameDetail, etc.
│   │   ├── pages/               # AFLAgent, AFLChat, LiveGames, Analytics, About
│   │   ├── services/            # API client utilities
│   │   ├── types/               # TypeScript definitions
│   │   ├── App.tsx              # Router config
│   │   └── main.tsx
│   ├── vite.config.ts
│   └── package.json
│
├── database/migrations/         # SQL migrations V1–V6
├── scripts/                     # ingest_data.py, init_db.py, benchmark_chat.py + benchmark_results/
├── docs/                        # CONTEXT.md, BENCHMARK_BEFORE_AFTER.md, plans/
├── eval_queries.txt             # 128 exploratory eval queries (parsed by the eval harness)
├── TODO.md
└── CLAUDE.md                    # This file
```

---

## Tech Stack

| Layer        | Technology                                      |
|--------------|-------------------------------------------------|
| Backend      | Flask, Flask-SocketIO, LangGraph, SQLAlchemy    |
| LLM          | `gpt-6-luna` (OpenAI Responses API) for chat, summaries and news, via the provider-thin `app/agent/v3/llm.py` (OpenAI, Gemini, Anthropic adapters) |
| Database     | PostgreSQL (Supabase / Railway), psycopg3       |
| Frontend     | React 18, Vite, TypeScript, TailwindCSS         |
| Charts       | Recharts (backend emits validated `ChartSpecV1` JSON; frontend renders) |
| Deployment   | Railway (backend + DB), static frontend         |
| WebSockets   | Flask-SocketIO + geventwebsocket                |

---

## Running the App Locally

**Backend** (port 5001):
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py
```

**Frontend** (port 3000):
```bash
cd frontend
npm install
npm run dev
```

**Data ingestion** (one-time / as needed):
```bash
cd backend
python -m scripts.ingest_data
```

---

## Environment Variables

Defined in `backend/.env`. Required:
```
DB_STRING=postgresql://...       # PostgreSQL connection string
OPENAI_API_KEY=...
SECRET_KEY=...
```

Optional:
```
AGENT_ENGINE=v2                  # v2 (LangGraph, default) or v3 (tool-calling loop)
AGENT_MODEL=gpt-6-luna           # Chat model (both engines), reasoning effort low
AGENT_EFFORT=low                 # v3 reasoning effort
SUMMARY_MODEL=gpt-6-luna         # Live game quarter/final summaries
NEWS_ENRICHMENT_MODEL=gpt-6-luna # News enrichment, reasoning off
NEWS_SERVICE_TIER=flex           # OpenAI tier for news enrichment (half price)
GEMINI_API_KEY=...               # Only for gemini-* models (bake-off / fallback)
ANTHROPIC_API_KEY=...            # Only for claude-* models (bake-off)
API_SPORTS_KEY=...               # Live player stats
THEODDSAPI_KEY=...               # Betting odds (16 req/day budget)
CORS_ORIGINS=http://localhost:3000
FLASK_ENV=development
LOG_LEVEL=INFO
DB_POOL_SIZE=5
```

---

## Agent Pipeline (Backend Core)

The main query flow in `backend/app/agent/graph.py` (class `AFLAnalyticsAgent`) — a single LangGraph pipeline, no fast-path/flags:

```
User Query
    │
    ▼
1. CLASSIFY_RESOLVE  (classify_resolve.py)
   Cheap LLM call: turn type (new_question / follow_up / correction /
   clarification_answer / chitchat) + entity extraction, then deterministic
   entity resolution (EntityResolver). Corrections set bypass_cache and load
   the prior turn's persisted sql/row_count/answer. Chitchat short-circuits
   straight to RESPOND.
    │
    ▼
2. RETRIEVE_CONTEXT  (retrieve_context.py)
   Deterministic: prunes per-table schema docs (schema_docs.py) + picks
   top-k verified SQL examples (sql_examples.py) + conversation snippet.
    │
    ▼
3. GENERATE_SQL  (generate_sql.py)
   One focused LLM call: final intent + SQL. All retry loops feed back here.
    │
    ▼
4. ANALYZE_DEPTH → 5. PLAN
   Summary vs in-depth analysis mode; analysis steps.
    │
    ▼
6. EXECUTE
   Run validated SQL against PostgreSQL, compute statistics. Then routes:
   ├── DB error → back to GENERATE_SQL with the exact error + failed SQL
   │   (self-correct loop, shared cap of 3 generate_sql calls per turn)
   ├── 0 rows → DIAGNOSE_EMPTY (diagnose_empty.py, deterministic, no LLM):
   │   explains WHY (season out of range, player debut, bad filter...);
   │   regenerates SQL once if obviously fixable, else responds with the
   │   why-no-data facts
   └── rows → REVIEW (review.py): cheap LLM sanity check that the results
       answer the question (skipped for trivial template answers); a NO
       verdict triggers ONE critique-driven regen under the same cap
    │
    ▼
7. VISUALIZE (if applicable)
   Heuristics first, LLM fallback for ambiguous cases → RechartsBuilder
   emits a `ChartSpecV1` spec (validated; invalid specs are dropped, never sent)
    │
    ▼
8. RESPOND
   Template (simple) or LLM (complex) → natural language
```

**v3 engine (`AGENT_ENGINE=v3`, `app/agent/v3/`)** — one tool-calling loop that replaces the pipeline above once the 1E gate passes:
- `loop.py` `AgentLoop`: system prompt (`prompt.py`, cache-stable) + typed tools (`tools/`: resolve_entities, player_stats, leaderboard, team_results, head_to_head, match_lookup, ladder, news, run_sql, make_chart), max 6 tool calls, parallel tool calls, streamed answer
- every tool returns `{rows, row_count, result_id, columns, why_empty, notes}`; `make_chart` builds a validated ChartSpecV1 and returns errors to the model
- `ws_stream.py`: WS events `received` -> `thinking` (per tool call) -> `response_delta` -> `visualization` -> `response` -> `complete` (with `data_as_of`)
- conversation memory: compact tool calls in message metadata (`history.py`); per-turn trace rows in `chat_traces` (`scripts/db/1e_chat_traces.sql`)
- `runner.py` `run_turn(question, history, model=...)` for evals and scripts; `scripts/v3_latency.py`, `scripts/v3_bakeoff.py`

**Key details:**
- In-memory LRU cache (128 entries) for identical (query, context) pairs; correction turns bypass cache reads
- Real token usage accumulated in `state["token_usage"]` across every LLM call
- Eval harness: `cd backend && venv/bin/python -m app.agent.eval --subset smoke15 [--judge]` (in-process; `--ws` drives a running backend). WS-level benchmark: `backend/venv/bin/python scripts/benchmark_chat.py` + `scripts/score_baseline.py`. Results in `scripts/benchmark_results/`; before/after summary in `docs/BENCHMARK_BEFORE_AFTER.md`

---

## Agent State (`agent/state.py`)

TypedDict flowing through LangGraph nodes:
- `user_query`, `intent`, `entities` (teams, players, seasons, metrics)
- `sql_query`, `query_results` (Pandas DataFrame)
- `visualization_spec` (ChartSpecV1 JSON for Recharts)
- `natural_language_summary`, `confidence` (0.0–1.0)

---

## Database Schema

Core tables:
- **teams** — 18 AFL teams with metadata
- **players** — player registry (active and historical)
- **matches** — 6,946 matches (1990–2026), quarter-by-quarter scoring
- **player_stats** — 273k+ rows of per-match player stats (disposals, kicks, goals, etc.)
- **team_stats** — per-match team aggregates
- **conversations** — JSONB chat history (UUID keyed)
- **news_articles** — LLM-enriched AFL news
- **betting_odds** — upcoming match odds
- **api_usage** — LLM token/cost tracking
- **page_views** — analytics
- **live_games**, **live_game_events**, **live_game_milestones**, **quarter_snapshots** — live match data

Migrations are in `database/migrations/` (V1–V6) and `backend/app/data/migrations/`.

---

## API Endpoints

**REST** (`backend/app/api/routes.py`):
- `GET /api/health` — health check (DB + OpenAI)
- `POST /api/chat/message` — non-streaming chat
- `GET /api/conversations/<id>` — load history
- `GET /api/admin/analytics/*` — admin dashboard

**WebSocket** (`/socket.io` via `api/websocket.py`):
- Event `chat_message` — runs agent, emits `thinking` progress events
- `connect` / `disconnect` — lifecycle
- Rate limited: 10 messages/min per IP; daily per-visitor budget enforced

---

## External APIs

| Service         | Purpose                          | Env Var             | Notes                        |
|-----------------|----------------------------------|---------------------|------------------------------|
| OpenAI          | LLM (chat, summaries, news)      | `OPENAI_API_KEY`    | gpt-6-luna, Responses API    |
| Squiggle API    | Live games (SSE) + historical    | —                   | `api.squiggle.com.au`        |
| API-Sports      | Live player stats                | `API_SPORTS_KEY`    | 30s cache TTL                |
| The Odds API    | Betting odds                     | `THEODDSAPI_KEY`    | 16 req/day budget            |
| RSS feeds       | AFL news (SMH, The Age, ABC)     | —                   | Enriched by NEWS_ENRICHMENT_MODEL |

---

## Frontend Routing (`App.tsx`)

| Path                         | Page            | Purpose                        |
|------------------------------|-----------------|--------------------------------|
| `/` or `/afl`                | AFLAgent        | Main AI chat                   |
| `/aflagent/:conversationId?` | AFLAgent        | Chat with loaded history       |
| `/live`                      | LiveGames       | Live game tracker              |
| `/analytics`                 | Analytics       | Admin analytics dashboard      |
| `/about`                     | About           | About page                     |

---

## Key Frontend Patterns

- **WebSocket** — `useAgentWebSocket` hook; singleton socket to avoid React StrictMode duplicates
- **Streaming** — backend emits `thinking` events; UI shows real-time step progress
- **Charts** — `ChartRenderer` (Recharts) renders the backend's `ChartSpecV1` spec; specs are validated with zod (`types/chartSpec.ts`), wrapped in `ChartErrorBoundary`, and fall back to `DataTable` on invalid/unrenderable specs (no white screens)
- **Conversation persistence** — `conversationId` stored in `localStorage`
- **Spoiler mode** — `SpoilerContext` (global toggle, persisted in `localStorage`); hides scores/results
- **Live games** — polled via `useLiveGames` / `useLiveGameDetail`; `LiveDashboard` shows sidebar + stats + events
- **Mobile** — `visualViewport` API used for keyboard height handling in chat input

**TailwindCSS design system** (Apple-inspired):
- `apple-gray-*` colour palette, `rounded-apple`, `card-apple`
- `btn-apple-primary` / `btn-apple-secondary` button variants
- `glass` class for glassmorphism

---

## Analytics Module (`analytics/`)

- `entity_resolver.py` — maps nicknames ("Cats" → "Geelong"), abbreviations, fuzzy typos to DB values
- `context_enrichment.py` — adds form analysis, venue stats, historical context
- `data_quality.py` — confidence scoring, outlier detection, sample size validation
- `statistics.py` — fantasy points, disposal efficiency, moving averages

---

## Visualization Module (`visualization/`)

1. `chart_selector.py` — heuristics first (single row → none, time series → line, top-N → bar); LLM fallback. Uses the internal chart-type vocabulary (`horizontal_bar`, `stacked_bar`, `box`, `comparison`, `trend`, ...)
2. `data_preprocessor.py` — aggregation, pivoting, null handling
3. `recharts_builder.py` — the single seam that translates internal chart types into the wire contract and builds the spec (e.g. `horizontal_bar` → `bar` + `orientation: "horizontal"`, `stacked_bar` → `groupedBar` + per-series `stackId`, `box` → `groupedBar` median/range)
4. `spec.py` — `ChartSpecV1` pydantic contract (mirrored by zod in `frontend/src/types/chartSpec.ts`). Every spec is validated before emission; on validation failure nothing is sent
5. `layout_config.py` / `layout_optimizer.py` — sizing, axis formatting, legend placement

Wire-format chart types (`ChartSpecV1.chartType`, camelCase): `line`, `bar`, `groupedBar`, `pie`, `scatter`, `area`, `table`

---

## Services (`services/`)

- `conversation_service.py` — JSONB chat history CRUD
- `live_game_service.py` — Squiggle SSE polling, scoring events, WebSocket broadcast
- `game_summary_service.py` — SUMMARY_MODEL narrative summaries per quarter
- `api_sports_service.py` — live player stats with caching
- `scheduler.py` — background jobs (odds refresh, news fetch, live game polling, stats ingestion)

---

## Automated Player Stats Pipeline (`data/ingestion/stats_ingester.py`)

Automatically ingests player-level match statistics into the `player_stats` table so the chat agent always has up-to-date data.

**Data source:** AFL Tables (`afltables.com`) — the authoritative source for comprehensive post-game player stats. Provides all 24 stat fields (kicks, marks, contested possessions, inside 50s, clearances, brownlow votes, time on ground, etc.). Typically updates 1–3 days after a round completes.

**Scheduled job:** Daily at **6 AM AEST** (Job 10 in `scheduler.py`).

**How it works:**
1. Finds completed matches from the last 14 days with no `player_stats` rows (or missing advanced stats)
2. Fetches the season's match page URLs from `afltables.com/afl/seas/{year}.html`
3. Scrapes each match page for player stats, quarter scores, and attendance
4. Matches scraped data to DB matches by season + team IDs + date (handles home/away swaps)
5. Creates `Player` records for any new players not yet in the database
6. Inserts/updates `PlayerStat` rows with all available fields and calculates fantasy points
7. Stops early once all target matches are processed

**Key details:**
- **Idempotent** — safe to re-run; skips existing stats, only updates empty advanced fields
- **Round numbering mismatch** — AFL Tables and Squiggle may number rounds differently (e.g. Opening Round). Matching uses team IDs and date, not round numbers
- **Respectful scraping** — 1.5s delay between requests to `afltables.com`
- **14-day lookback** — only processes recent matches, not the entire season

**Manual one-off run:**
```bash
cd backend
python3 -c "
from app.data.ingestion.stats_ingester import ingest_from_afl_tables
result = ingest_from_afl_tables(season=2026, days_back=30)
print(result)
"
```

**Stats fields populated from AFL Tables:**
kicks, handballs, disposals, marks, tackles, goals, behinds, hitouts, clearances, inside_50s, rebound_50s, contested_possessions, uncontested_possessions, contested_marks, marks_inside_50, one_percenters, bounces, clangers, free_kicks_for, free_kicks_against, brownlow_votes, goal_assist, time_on_ground_pct, fantasy_points

---

## Middleware

- `rate_limiter.py` — Flask-Limiter, 10 req/min per IP, HTTP 429 on limit
- `usage_tracker.py` — daily budget per visitor + global; token counting; cost calculation

---

## Production Deployment (Railway)

```
Procfile: gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind 0.0.0.0:$PORT run:app
```

Single worker required for WebSocket state. DB on Railway PostgreSQL (Supabase-compatible pooler; prepared statements disabled).

---

## Current Branch: `chat-restructure`

Chat pipeline restructure (Milestones 0–5, complete):
- M0: WS-level baseline benchmark (`scripts/benchmark_chat.py` + `scripts/score_baseline.py`)
- M1: backend quick fixes (dynamic season ceiling, word-boundary SQL validator, correction cache-bypass, real token usage)
- M2: frontend crash guards (ChartErrorBoundary, zod chart spec validation, DataTable fallback)
- M3: new pipeline (classify_resolve → retrieve_context → generate_sql → execute with SQL self-correct / diagnose_empty / review loops); legacy fast-path/consolidated-LLM modules deleted
- M4: `ChartSpecV1` contract (backend pydantic + frontend zod), validated-only chart emission
- M5: eval harness (`backend/app/agent/eval/`, `python -m app.agent.eval`) + `docs/BENCHMARK_BEFORE_AFTER.md`

---

## Common Gotchas

1. **WebSocket worker** — must use `geventwebsocket` worker; standard gunicorn workers break SocketIO
2. **Supabase pooler** — prepared statements must be disabled (`prepare=False` in psycopg3)
3. **React StrictMode** — socket hook uses singleton pattern to prevent double-connect
4. **The Odds API quota** — only 16 req/day; fetcher guards against overcalling
5. **Round field is a string** — rounds can be "1"–"24", "Opening Round", "Qualifying Final", etc. (V3 migration)
6. **LLM calls** — go through `app/agent/v3/llm.py` (`chat` / `complete`); model names come only from `AGENT_MODEL` / `SUMMARY_MODEL` / `NEWS_ENRICHMENT_MODEL` (defaults in `llm.MODEL_ENV_DEFAULTS`), prices from `llm.PRICES` (an unknown model raises). Pass `track_endpoint` for background calls so api_usage records real model and cost
7. **Single gunicorn worker** — WebSocket state is in-process; scaling to multiple workers requires Redis adapter
8. **AFL Tables round numbering** — AFL Tables and Squiggle may number rounds differently (Opening Round offset). The stats ingester matches by team IDs + date, not round number
9. **AFL Tables update delay** — player stats appear on afltables.com 1–3 days after a round completes. The 6 AM daily job will pick them up automatically once available
