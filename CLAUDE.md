# AFL App — CLAUDE.md

This is **Footy-NAC** (Not Another Commentator): an AI-powered AFL analytics platform. Users ask natural-language questions about AFL stats, get interactive Plotly charts, and follow live games in real-time.

---

## Project Structure

```
AFL App/
├── backend/                     # Flask + LangGraph API
│   ├── app/
│   │   ├── agent/               # LangGraph pipeline (fast-path, graph, state, tools)
│   │   ├── api/                 # REST + WebSocket endpoints (routes, websocket, analytics, reports)
│   │   ├── analytics/           # Entity resolver, query builder, stats, validators
│   │   ├── data/                # SQLAlchemy models, database.py, ingestion scripts, migrations
│   │   ├── middleware/          # Rate limiting (Flask-Limiter), usage tracking
│   │   ├── scheduler/           # Background job scheduler
│   │   ├── services/            # Business logic (conversations, live games, summaries, odds)
│   │   ├── utils/               # JSON serialization, validators
│   │   ├── visualization/       # Chart selection, Plotly builder, data preprocessor
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
├── scripts/                     # ingest_data.py, init_db.py
├── docs/                        # CONTEXT.md, plans/
├── TODO.md
└── CLAUDE.md                    # This file
```

---

## Tech Stack

| Layer        | Technology                                      |
|--------------|-------------------------------------------------|
| Backend      | Flask, Flask-SocketIO, LangGraph, SQLAlchemy    |
| LLM          | OpenAI `gpt-5-mini` (main), `gpt-5-nano` (news) |
| Database     | PostgreSQL (Supabase / Railway), psycopg3       |
| Frontend     | React 18, Vite, TypeScript, TailwindCSS         |
| Charts       | Plotly (JSON spec from backend, rendered in frontend) |
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
OPENAI_MODEL=gpt-5-mini          # Main LLM
NEWS_ENRICHMENT_MODEL=gpt-5-nano # Cheap enrichment LLM
API_SPORTS_KEY=...               # Live player stats
THEODDSAPI_KEY=...               # Betting odds (16 req/day budget)
CORS_ORIGINS=http://localhost:3000
FLASK_ENV=development
LOG_LEVEL=INFO
DB_POOL_SIZE=5
```

---

## Agent Pipeline (Backend Core)

The main query flow in `backend/app/agent/graph.py`:

```
User Query
    │
    ▼
Fast-Path Router (fast_path.py)
├── 40+ regex patterns → instant response (~100–300ms, no LLM)
└── No match → LangGraph pipeline:
        │
        ▼
    1. UNDERSTAND  (consolidated_llm.py)
       Single LLM call: intent + entity extraction + SQL generation
        │
        ▼
    2. ANALYZE_DEPTH
       Summary vs in-depth analysis
        │
        ▼
    3. PLAN (in-depth only)
        │
        ▼
    4. EXECUTE
       Run SQL against PostgreSQL, compute statistics
        │
        ▼
    5. VISUALIZE (if applicable)
       Heuristics (~90%) or LLM fallback → Plotly JSON spec
        │
        ▼
    6. RESPOND
       Template (simple) or LLM (complex) → natural language
```

**Key optimisations:**
- `consolidated_llm.py` — merges UNDERSTAND + SQL into one API call (~500ms saved)
- `fast_path.py` — regex for team wins, grand final winners, top-N lists, off-topic detection
- In-memory LRU cache (128 entries) for identical (query, context) pairs
- Chart selection uses heuristics before LLM; LLM only for ambiguous cases

---

## Agent State (`agent/state.py`)

TypedDict flowing through LangGraph nodes:
- `user_query`, `intent`, `entities` (teams, players, seasons, metrics)
- `sql_query`, `query_results` (Pandas DataFrame)
- `visualization_spec` (Plotly JSON)
- `natural_language_summary`, `confidence` (0.0–1.0)

---

## Database Schema

Core tables:
- **teams** — 18 AFL teams with metadata
- **players** — player registry (active and historical)
- **matches** — 6,243 matches (1990–2025), quarter-by-quarter scoring
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
| OpenAI          | LLM for reasoning & SQL          | `OPENAI_API_KEY`    | gpt-5-mini + gpt-5-nano      |
| Squiggle API    | Live games (SSE) + historical    | —                   | `api.squiggle.com.au`        |
| API-Sports      | Live player stats                | `API_SPORTS_KEY`    | 30s cache TTL                |
| The Odds API    | Betting odds                     | `THEODDSAPI_KEY`    | 16 req/day budget            |
| RSS feeds       | AFL news (SMH, The Age, ABC)     | —                   | Enriched with gpt-5-nano     |

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
- **Charts** — `ChartRenderer` renders Plotly JSON spec from backend response
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
- `query_builder.py` — GPT-5-nano text-to-SQL with schema context
- `context_enrichment.py` — adds form analysis, venue stats, historical context
- `data_quality.py` — confidence scoring, outlier detection, sample size validation
- `statistics.py` — fantasy points, disposal efficiency, moving averages

---

## Visualization Module (`visualization/`)

1. `chart_selector.py` — heuristics first (single row → none, time series → line, top-N → bar); LLM fallback
2. `data_preprocessor.py` — aggregation, pivoting, null handling
3. `plotly_builder.py` — builds Plotly JSON spec; Apple-inspired colour palette
4. `layout_optimizer.py` — responsive sizing, axis formatting, legend placement

Supported chart types: `line`, `bar`, `horizontal_bar`, `grouped_bar`, `stacked_bar`, `scatter`, `pie`, `box`

---

## Services (`services/`)

- `conversation_service.py` — JSONB chat history CRUD
- `live_game_service.py` — Squiggle SSE polling, scoring events, WebSocket broadcast
- `game_summary_service.py` — GPT-5-mini narrative summaries per quarter
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

## Current Branch: `feature/live-games-backend`

Active development work:
- Live Games screen redesign (sidebar layout, quarter summaries, live stats, event timeline)
- New files: `backend/app/api/reports.py`, `backend/app/data/migrations/add_user_reports.py`
- Modified: agent graph, consolidated LLM, analytics API, websocket handlers, RSS fetcher, models, chart selector

---

## Common Gotchas

1. **WebSocket worker** — must use `geventwebsocket` worker; standard gunicorn workers break SocketIO
2. **Supabase pooler** — prepared statements must be disabled (`prepare=False` in psycopg3)
3. **React StrictMode** — socket hook uses singleton pattern to prevent double-connect
4. **The Odds API quota** — only 16 req/day; fetcher guards against overcalling
5. **Round field is a string** — rounds can be "1"–"24", "Opening Round", "Qualifying Final", etc. (V3 migration)
6. **LLM model env vars** — always use `OPENAI_MODEL` / `NEWS_ENRICHMENT_MODEL` env vars, never hardcode model strings
7. **Single gunicorn worker** — WebSocket state is in-process; scaling to multiple workers requires Redis adapter
8. **AFL Tables round numbering** — AFL Tables and Squiggle may number rounds differently (Opening Round offset). The stats ingester matches by team IDs + date, not round number
9. **AFL Tables update delay** — player stats appear on afltables.com 1–3 days after a round completes. The 6 AM daily job will pick them up automatically once available
