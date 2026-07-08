# AFL Analytics Agent - Quick Start Guide

## Prerequisites

- Python 3.11+ (currently using Python 3.14)
- OpenAI API key
- All dependencies installed (see below)

## Setup Steps

### 1. Add OpenAI API Key

The `.env` file is already symlinked to the parent directory. Add your OpenAI API key:

```bash
# Edit .env file (in the parent "AFL App" directory)
echo "OPENAI_API_KEY=sk-your-api-key-here" >> ../.env
```

Or manually edit `.env` and add:
```
OPENAI_API_KEY=sk-your-api-key-here
DB_STRING='postgresql://...' # Already there
```

### 2. Verify Dependencies

All dependencies should already be installed. If not:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Start the Flask Server

```bash
source venv/bin/activate
python run.py
```

You should see:
```
================================================================================
AFL Analytics Agent - Starting Server
================================================================================
Server running at: http://localhost:5000
Health check: http://localhost:5000/api/health
================================================================================
```

**Note**: If port 5000 is in use (macOS AirPlay Receiver), edit `run.py` to use port 5001.

### 4. Test the Health Check

In a new terminal:
```bash
curl http://localhost:5000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "matches": 6243,
  "teams": 18
}
```

### 5. Test the Agent (REST API)

```bash
curl -X POST http://localhost:5000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Who won the 2025 grand final?"}'
```

### 6. Test with Frontend

Start the React frontend:
```bash
cd ../frontend
npm install  # First time only
npm run dev
```

Open http://localhost:3000 and chat with the agent!

## Example Queries

**Match-Level Queries** (currently supported):
- "Who won the 2025 grand final?"
- "Show me Richmond's win-loss record in 2024"
- "Which teams had the most wins in 2023?"
- "How many matches did Collingwood win in 2022?"

**Player Queries** (now supported):
- "How many disposals did Patrick Cripps average in 2024?"
- "Compare Clayton Oliver and Marcus Bontempelli"
- "Who are the top 5 goal scorers in 2024?"

## Architecture

```
User Query → WebSocket → LangGraph Agent → gpt-5-mini → SQL → Database → ChartSpecV1 (Recharts) → Frontend
                ↓
[CLASSIFY_RESOLVE → RETRIEVE_CONTEXT → GENERATE_SQL → EXECUTE
        → (self-correct / diagnose_empty / review loops) → VISUALIZE → RESPOND]
```

## Troubleshooting

### "OpenAI API key not found"
- Make sure you added `OPENAI_API_KEY` to the `.env` file
- The `.env` file should be in the parent "AFL App" directory (symlinked to backend/.env)

### "Port 5000 already in use"
- On macOS, disable AirPlay Receiver in System Settings > Sharing
- Or edit `run.py` to use a different port

### "Database connection failed"
- Check that `DB_STRING` in `.env` is correct
- Verify Supabase connection is active

### "Agent returns no results"
- Verify the team or player name is spelled correctly (use exact names: "Richmond" not "Richmond Tigers")
- Check the year range - match data: 1990-2026 (player stats coverage varies by player)
- Try rephrasing your question to be more specific

## Development

### Project Structure
```
backend/
├── app/
│   ├── agent/          # LangGraph workflow
│   │   ├── graph.py    # Main agent workflow
│   │   ├── state.py    # Agent state schema
│   │   └── tools.py    # Agent tools
│   ├── analytics/      # Entity resolution + validation
│   │   ├── entity_resolver.py # Team/player name resolution
│   │   └── validators.py      # SQL validation
│   ├── api/            # Flask routes
│   │   ├── routes.py   # REST endpoints
│   │   └── websocket.py # WebSocket handlers
│   ├── data/           # Database
│   │   ├── models.py   # SQLAlchemy models
│   │   └── ingestion/  # Data scrapers
│   └── visualization/  # Recharts chart specs
│       ├── recharts_builder.py # Builds ChartSpecV1 specs
│       └── spec.py             # ChartSpecV1 pydantic contract
├── run.py              # Entry point
└── requirements.txt
```

## Next Steps

1. **Test the Agent**: Add OPENAI_API_KEY and test queries
2. **Customize**: Modify the agent workflow in `app/agent/graph.py`
3. **Add Features**: Implement conversation memory, chart export, etc.
4. **Deploy**: Set up Docker Compose for production

## Resources

- Main README: `../README.md`
- Progress Tracker: `../PROGRESS.md`
- Project Plan: `~/.claude/plans/rustling-enchanting-acorn.md`
