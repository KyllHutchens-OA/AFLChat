# Footy-NAC

> Not Another Commentator: an AFL analytics chat app. Ask questions about AFL stats in plain English, get answers with interactive charts, and follow live games.

## Overview

Footy-NAC answers natural-language questions about Australian Football League (AFL) match and player statistics. An LLM agent turns each question into database queries, checks the results, picks a chart when one helps, and writes the answer. The app also tracks live games and AFL news.

**Tech stack**: Flask + Flask-SocketIO (backend) · React 18 + Vite + TypeScript + Tailwind (frontend) · LangGraph (v2 engine) and a tool-calling loop (v3 engine) · OpenAI `gpt-6-luna` via the Responses API · PostgreSQL (Supabase / Railway) · Recharts

## Features

- **Natural-language queries** about AFL match and player stats
- **Two agent engines**: the v2 LangGraph pipeline (default) and the v3 tool-calling loop (`AGENT_ENGINE=v3`)
- **Interactive charts**: the backend emits a validated `ChartSpecV1` spec; the frontend renders it with Recharts and falls back to a table if a spec can't be rendered
- **Streaming progress** over WebSocket while the agent works
- **Data from 1990 to 2026**: 7,000+ matches with quarter-by-quarter scores and 310k+ per-match player stat rows, kept current by a scheduled AFL Tables ingester
- **Entity resolution**: nicknames ("Cats", "Dusty"), abbreviations, surnames and typos map to canonical team and player names
- **Live games**: Squiggle SSE feed, scoring events and LLM quarter/final summaries
- **Spoiler mode**: hides scores and results across the app
- **Eval harness**: live ground-truth evals that run against either engine

### Example queries

```
"Who won the 2024 grand final?"
"Show me Richmond's win-loss record in 2022"
"Which teams had the most wins in 2023?"
"Show me Collingwood's scoring trend across 2024"
"Rankine fantasy points 2024"
"Compare Cripps and Petracca disposals in 2023"
"Top 10 goal kickers in 2024"
```

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (local, Supabase or Railway)
- OpenAI API key

### Backend (port 5001)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# create backend/.env (see Environment variables below)
python run.py
```

### Frontend (port 3000)

```bash
cd frontend
cp .env.example .env      # sets VITE_BACKEND_URL=http://localhost:5001
npm install
npm run dev
```

### Data

Schema migrations live in `database/migrations/` (V1 to V6) and `scripts/db/`; database roles (including the read-only `agent_ro` role) are in `scripts/db/roles.sql`.

```bash
# from the repo root, with the backend venv active
python scripts/init_db.py        # create core tables
python scripts/ingest_data.py    # initial match data load

# player stats from AFL Tables (also runs on a schedule)
cd backend
python -m app.data.ingestion.stats_ingester 2026      # [season] [limit]
```

Then open http://localhost:3000.

## Environment variables

Set in `backend/.env`.

Required:

```
DB_STRING=postgresql://...       # app role, never a superuser
AGENT_DB_STRING=postgresql://... # read-only agent_ro role for LLM SQL (dev falls back to DB_STRING)
OPENAI_API_KEY=...
SECRET_KEY=...                   # also signs visitor tokens; dev-only fallback when FLASK_ENV=development
ANALYTICS_ADMIN_TOKEN=...        # bearer token for /api/analytics/*; unset means every request gets 401
```

Optional:

```
AGENT_ENGINE=v2                  # v2 (LangGraph, default) or v3 (tool-calling loop)
AGENT_MODEL=gpt-6-luna           # chat model for both engines
AGENT_EFFORT=low                 # v3 reasoning effort
SUMMARY_MODEL=gpt-6-luna         # live game quarter/final summaries
NEWS_ENRICHMENT_MODEL=gpt-6-luna # news enrichment
NEWS_SERVICE_TIER=flex           # OpenAI service tier for news enrichment
EVAL_JUDGE_MODEL=...             # eval judge model (defaults to AGENT_MODEL)
GEMINI_API_KEY=...               # only needed for gemini-* models
ANTHROPIC_API_KEY=...            # only needed for claude-* models
RUN_SCHEDULER=false              # true on the one process that runs background jobs
DAILY_LIMIT_PER_VISITOR=50
DAILY_LIMIT_PER_IP=150
GLOBAL_DAILY_LIMIT_USD=5.00
AGENT_STATEMENT_TIMEOUT_MS=5000
AGENT_MAX_ROWS=5000
DB_POOL_SIZE=5
CORS_ORIGINS=http://localhost:3000
FLASK_ENV=development
LOG_LEVEL=INFO
```

Model names come only from `AGENT_MODEL`, `SUMMARY_MODEL` and `NEWS_ENRICHMENT_MODEL` (defaults in `app/agent/v3/llm.py`). Every configured model must have a price in `llm.PRICES`; an unknown model fails at startup.

## Architecture

### Agent engines

The WebSocket handler (`backend/app/api/websocket.py`) picks the engine from `AGENT_ENGINE`. v2 is the default. v3 is meant to replace v2 once it passes the eval gate.

All LLM calls in both engines go through `backend/app/agent/v3/llm.py`, a thin layer with adapters for the OpenAI Responses API, Gemini and Anthropic. It handles streaming, tool calls, token usage and cost tracking.

#### v2: LangGraph pipeline (default)

`backend/app/agent/graph.py`, class `AFLAnalyticsAgent`:

```
User query
    │
    ▼
1. CLASSIFY_RESOLVE   cheap LLM call: turn type (new question, follow-up,
                      correction, clarification, chitchat) + entities, then
                      deterministic entity resolution. Chitchat goes straight
                      to RESPOND.
2. RETRIEVE_CONTEXT   deterministic: relevant schema docs, top-k verified SQL
                      examples, recent conversation
3. GENERATE_SQL       one LLM call: intent + SQL. All retry loops come back here
                      (max 3 calls per turn).
4. ANALYZE_DEPTH → 5. PLAN
6. EXECUTE            run validated SQL, compute statistics
   ├── DB error  → GENERATE_SQL with the error and failed SQL
   ├── 0 rows    → DIAGNOSE_EMPTY (no LLM): explains why there is no data,
   │               regenerates once if the fix is obvious
   └── rows      → REVIEW: cheap LLM check that the rows answer the question;
                   a NO verdict triggers one regeneration
7. VISUALIZE          heuristics first, LLM fallback → ChartSpecV1
8. RESPOND            template for simple answers, LLM otherwise
```

An in-memory LRU cache (128 entries) serves identical (query, context) pairs; correction turns skip it.

#### v3: tool-calling loop (`AGENT_ENGINE=v3`)

`backend/app/agent/v3/`:

- `loop.py`: `AgentLoop` sends the question, history and a cache-stable system prompt (`prompt.py`) to the model with a set of typed tools. The model can call tools in parallel, up to 6 tool calls per turn, then must answer. The answer text streams back.
- `tools/`: `resolve_entities`, `player_stats`, `leaderboard`, `team_results`, `head_to_head`, `match_lookup`, `ladder`, `news`, `run_sql`, `make_chart`. Each returns `{rows, row_count, result_id, columns, why_empty, notes}`. `make_chart` builds a validated `ChartSpecV1` and returns validation errors to the model so it can fix them.
- `ws_stream.py`: WebSocket events `received` → `thinking` (one per tool call) → `response_delta` → `visualization` → `response` → `complete` (with `data_as_of`).
- `history.py`: stores compact tool calls in message metadata so follow-up turns keep context.
- `runner.py`: `run_turn(question, history, model=...)` for evals and scripts (`scripts/v3_latency.py`, `scripts/v3_bakeoff.py`).
- Per-turn traces are written to `chat_traces` (`scripts/db/1e_chat_traces.sql`).

### Charts

`backend/app/visualization/` picks a chart type (heuristics first, LLM fallback), preprocesses the data and builds a `ChartSpecV1` spec (`spec.py`, pydantic). The frontend mirrors the contract with zod (`frontend/src/types/chartSpec.ts`), wraps charts in an error boundary and falls back to `DataTable`. Invalid specs are never sent. Wire chart types: `line`, `bar`, `groupedBar`, `pie`, `scatter`, `area`, `table`.

### Security and limits

- Agent SQL is parsed by `SQLValidator` (sqlglot, full tree) and runs as the `agent_ro` role in a read-only transaction with a statement timeout and row cap. v3 typed tools also use the `agent_ro` engine.
- Visitors get a server-signed token on connect. Conversations need an owner token to load, and history responses contain no SQL.
- WebSocket chat is limited to 10 messages per minute per IP, plus daily per-visitor, per-IP and global USD budgets that fail closed.
- Client IPs come only from `ProxyFix(x_for=1)`.
- SQL, stack traces and internal errors are never shown to users.

### Evals

Run from `backend/`:

```bash
venv/bin/python -m app.agent.eval --subset smoke            # ~20 cases
venv/bin/python -m app.agent.eval --subset full --engine v3 # 121 ground-truth cases (the gate)
venv/bin/python -m app.agent.eval --list-subsets
venv/bin/python -m app.agent.eval --compare v2_2026-09-28   # diff against a saved baseline
```

Other flags: `--engine v2|v2-ws|v3`, `--case id1,id2`, `--repeat N`, `--strict`, `--truth-only` (no LLM), `--judge`, `--save-baseline NAME`, `--diff A B`, `--rescore NAME`. Baselines live in `app/agent/eval/baselines/`. Engine DB connections are read-only during evals unless `--allow-db-writes` is passed. Results before and after the pipeline rebuild are in `docs/BENCHMARK_BEFORE_AFTER.md`.

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── agent/         # v2 LangGraph pipeline (graph, nodes, prompts/), eval/, v3/ tool-calling loop + llm.py
│   │   ├── api/           # REST + WebSocket endpoints, admin analytics
│   │   ├── analytics/     # entity resolver, context enrichment, statistics, SQL validator
│   │   ├── data/          # SQLAlchemy models, database connections, ingestion, migrations
│   │   ├── middleware/    # rate limiting, usage tracking and budgets
│   │   ├── scheduler/     # background jobs
│   │   ├── services/      # conversations, live games, summaries, data health
│   │   ├── utils/
│   │   └── visualization/ # chart selection, preprocessing, ChartSpecV1 builder
│   ├── run.py
│   └── Procfile           # gunicorn + geventwebsocket, single worker
│
├── frontend/
│   └── src/               # components/, contexts/, hooks/, pages/, services/, types/
│
├── database/migrations/   # SQL migrations V1 to V6
├── scripts/               # data setup, db/ SQL, benchmarks, v3 latency and bake-off scripts
└── docs/                  # benchmark results, plans
```

## Database

Core tables:

- `teams`: 18 AFL clubs
- `players`: player registry, active and historical
- `matches`: results from 1990 to 2026 with quarter-by-quarter scores
- `player_stats`: per-match player stats (disposals, kicks, goals, marks, tackles, clearances, fantasy points, Brownlow votes and more)
- `team_stats`: per-match team aggregates
- `conversations`: chat history (JSONB)
- `news_articles`: LLM-enriched AFL news
- `live_games`, `live_game_events`, `live_game_milestones`, `quarter_snapshots`: live match data
- `api_usage`, `page_views`, `chat_traces`: cost tracking, analytics and per-turn agent traces

### Player stats pipeline

`backend/app/data/ingestion/stats_ingester.py` pulls player stats from AFL Tables (afltables.com), usually 1 to 3 days after a round. The scheduler runs it daily at 6 AM AEST with a 3-hourly retry for the current season, syncs live final scores into `matches` every 30 minutes, and runs a data-health check at 7:30 AM. Matches are paired by club pair, finals flag and a 3-day date window, and players by their AFL Tables id, so namesakes never merge.

## Deployment

Railway (backend + PostgreSQL), static frontend. The backend must run a single gunicorn worker with the `geventwebsocket` worker class, since WebSocket state is in-process. The Supabase pooler needs prepared statements disabled.

## License

MIT
