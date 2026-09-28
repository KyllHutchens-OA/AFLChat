# AFL Sports Analytics Agent

> An AFL analytics agent demonstrating agentic AI capabilities through a chat interface with interactive visualizations.

## Overview

This project showcases an AI agent that autonomously analyzes Australian Football League (AFL) statistics, performs multi-step reasoning, and provides insights through natural language conversation with embedded interactive visualizations.

**Tech Stack**: Flask + Flask-SocketIO (backend) · React + Vite (frontend) · LangGraph (agent framework) · OpenAI `gpt-6-luna` (LLM) · Supabase PostgreSQL · Recharts (visualizations)

## Features

- **Natural Language Queries**: Ask questions in plain English about AFL match and player statistics
- **Multi-Step Reasoning**: Agent autonomously classifies intent, generates SQL, and formats responses
- **Interactive Visualizations**: Recharts charts (line, bar, grouped bar) embedded in chat with heuristic chart selection
- **Real-time Streaming**: WebSocket status updates showing the agent's progress through the pipeline
- **35 Years of Data**: Complete AFL match and player statistics from 1990-2025 (6,243 matches, 273k+ player stat rows)
- **Fast-Path Queries**: Regex-matched common patterns bypass the LLM entirely (~200ms response)
- **Entity Resolution**: Fuzzy team name matching, player disambiguation, and metric normalization
- **LLM Response Cache**: In-memory cache for identical queries avoids repeat API calls
- **Template Responses**: Simple stats and top-N queries use direct formatting instead of a second LLM call

### Example Queries

```
"Who won the 2024 grand final?"
"Show me Richmond's win-loss record in 2022"
"Which teams had the most wins in 2023?"
"Show me Collingwood's scoring trend across 2024"
"Rankine fantasy points 2024"
"Compare Cripps and Petracca disposals in 2023"
"Top 10 goal kickers in 2024"
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Supabase account (free tier) or local PostgreSQL
- OpenAI API key

### Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd "AFL App"
   ```

2. **Backend**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with your Supabase and OpenAI credentials
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python run.py
   ```

3. **Frontend**
   ```bash
   cd frontend
   cp .env.example .env
   npm install
   npm run dev
   ```

4. **Run data ingestion** (first time only)
   ```bash
   cd backend
   python -m scripts.ingest_data
   ```

5. **Open the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:5001

## Project Structure

```
├── backend/              # Flask API and LangGraph agent
│   ├── app/
│   │   ├── agent/        # LangGraph workflow, fast-path router, consolidated LLM
│   │   ├── api/          # REST endpoints, WebSocket handlers, admin analytics
│   │   ├── analytics/    # Query builder, entity resolver, metric normalization
│   │   ├── data/         # SQLAlchemy models, database connection, ingestion
│   │   ├── middleware/   # Rate limiting, security, cost controls
│   │   ├── services/     # Business logic services
│   │   ├── utils/        # Shared utilities
│   │   └── visualization/# Recharts chart builder, chart selector, data preprocessing
│   └── run.py
│
├── frontend/             # React + Vite chat interface
│   ├── src/
│   │   ├── components/   # Chat UI, chart renderer, message components
│   │   ├── hooks/        # WebSocket streaming logic
│   │   ├── pages/        # Page-level components
│   │   ├── services/     # API clients
│   │   ├── types/        # TypeScript type definitions
│   │   └── utils/        # Frontend utilities
│   └── vite.config.ts
│
├── database/             # Schema and migrations
│   └── migrations/       # Versioned SQL migrations (V1-V6)
│
├── scripts/              # Data ingestion and utility scripts
│
└── docs/
    └── BENCHMARK_BEFORE_AFTER.md  # Eval results, before/after the pipeline rebuild
```

## Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py              # Starts on port 5001
```

### Frontend

```bash
cd frontend
npm install
npm run dev                # Starts on port 3000
```

## Architecture

The agent uses **LangGraph** to orchestrate a multi-step workflow:

```
User Query
    │
    ├─→ Fast-Path Router (regex patterns, ~200ms, no LLM)
    │       ├─ Team wins/losses
    │       ├─ Grand final winner
    │       ├─ Player season stats
    │       ├─ Highest score
    │       └─ (more patterns...)
    │
    └─→ LangGraph Pipeline (complex queries)
         1. UNDERSTAND → Consolidated LLM call (intent + entities + SQL in one call)
         2. ANALYZE_DEPTH → Determine if in-depth analysis needed
         3. PLAN → Analysis strategy (skipped for simple queries)
         4. EXECUTE → Run SQL against PostgreSQL
         5. VISUALIZE → Heuristic chart selection + Recharts spec generation
         6. RESPOND → Template response or LLM-generated summary
```

**Performance optimizations**:
- Consolidated LLM call merges intent classification + SQL generation (saves one round-trip)
- Chart type selection uses heuristics for ~90% of queries (no LLM needed)
- Template responses handle simple stats and top-N lists directly
- `reasoning_effort='low'` on `gpt-6-luna` reduces reasoning tokens
- In-memory LLM response cache for repeat queries

**Key Design Principles**:
- No code visible to users (SQL, Python, or errors)
- Streaming status updates via WebSocket
- Graceful degradation — consolidated call failures fall back to separate steps

## Database Schema

Core tables:
- `teams` — 18 AFL teams with canonical names, abbreviations, stadiums
- `players` — Player metadata (name, position, height, weight, debut year)
- `matches` — Match results 1990-2025 (6,243 matches, quarter-by-quarter scores)
- `player_stats` — Per-match player statistics (disposals, goals, marks, tackles, fantasy points, brownlow votes, etc.)
- `team_stats` — Per-match team aggregates
- `match_lineups` — Selected players per match
- `match_weather` — Weather conditions during matches
- `conversations` — Chat history (AFL and resume chat types)
- `page_views` — Analytics tracking
- `api_usage` — API cost monitoring

## Contributing

This is a portfolio project. Contributions welcome!

## License

MIT

---

**Built with**: LangGraph · OpenAI `gpt-6-luna` · Flask · React · Supabase · Recharts · Railway
