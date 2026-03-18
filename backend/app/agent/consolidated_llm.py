"""
AFL Analytics Agent - Consolidated LLM Call

Merges the UNDERSTAND (intent + entity extraction) and EXECUTE (SQL generation)
steps into a single OpenAI API call, saving one full round-trip (~500ms-1s)
for every complex query that doesn't match the fast-path.

Falls back gracefully: if this call fails, graph.py runs the two steps
independently (existing behaviour preserved).
"""
import json
import logging
import os
from typing import Dict, Any, List, Optional

from openai import OpenAI
import httpx
from dotenv import load_dotenv

import hashlib

load_dotenv()

logger = logging.getLogger(__name__)

# Import config for model selection
from app.config import get_config
config = get_config()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(60.0, connect=10.0)
)

# ── LLM Response Cache ───────────────────────────────────────────────────────
# Cache identical (query, context) pairs to avoid repeat LLM calls.
# TTL-style: stores up to 128 recent queries in memory.
_llm_cache: Dict[str, Dict[str, Any]] = {}
_LLM_CACHE_MAX = 128


def _cache_key(user_query: str, conv_ctx: str) -> str:
    """Deterministic cache key from query + conversation context."""
    raw = f"{user_query.strip().lower()}|{conv_ctx.strip()}"
    return hashlib.md5(raw.encode()).hexdigest()

# ── Prompts ────────────────────────────────────────────────────────────────────

_INTENT_AND_SQL_PROMPT = """\
You are an AFL analytics expert. In ONE step:
1. Parse the user's question (intent, entities).
2. Generate a valid PostgreSQL SELECT query.

## Intent Classification
⚠️ CRITICAL: NEVER classify match/game queries as off_topic!

Questions about matches ARE AFL queries:
- "who played last night" → simple_stat ✓
- "who won yesterday" → simple_stat ✓
- "what was the score last night" → simple_stat ✓
- "games yesterday" → simple_stat ✓

off_topic is ONLY for non-AFL topics:
- "what's the weather" → off_topic ✗
- "how to cook pasta" → off_topic ✗
- "tell me a joke" → off_topic ✗

- "simple_stat": Single number/fact, including match results (e.g., "How many goals did X kick?", "Who won last night?", "Who played yesterday?", "What was the score last night?")
- "player_comparison": Comparing multiple players
- "team_analysis": One team's performance in a single season/period
- "trend_analysis": Change over TIME (keywords: "over time", "across time", "year by year", "historical", "trend", "evolution", "since")
- "afl_news": Latest AFL news or articles (e.g., "What's the latest AFL news?", "Show me recent news")
- "injury_news": Injury reports or player availability (e.g., "Any injuries for Collingwood?", "Who's out this week?")
- "betting_odds": Betting odds or lines (e.g., "What are the odds for next round?", "Show me betting odds")
- "tipping_advice": Tipping recommendations (e.g., "Who should I tip?", "Predictions for this round")
- "off_topic": Query is NOT about AFL football (e.g. recipes, weather, general knowledge). Return this intent with sql="" for any non-AFL question.

CRITICAL: "Who played last night/yesterday" is a simple_stat AFL query, NOT off_topic!

**IMPORTANT**: For news, injury, betting, or tipping queries, set sql="" (empty string) as these queries do NOT require database SQL queries.

## Entity Extraction Rules
- **Teams**: AFL club names (use canonical names: Adelaide, Brisbane Lions, Carlton, Collingwood, Essendon, Fremantle, Geelong, Gold Coast, Greater Western Sydney, Hawthorn, Melbourne, North Melbourne, Port Adelaide, Richmond, St Kilda, Sydney, West Coast, Western Bulldogs)
- **Players**: Surnames or full names (single-word surnames are ALWAYS players, never teams)
- **Seasons**: Years e.g. "2022", "last year" → infer current (2026)
- **Temporal References**: Convert to actual dates
  - "today" → 2026-03-14
  - "yesterday", "last night" → 2026-03-13
  - "this week" → last 7 days from 2026-03-14
  - "last round", "this round" → most recent round number
- **Metrics**: goals, disposals, marks, tackles, wins, losses, score, etc.

## SQL Generation Rules

Database Schema:

### teams: id, name, abbreviation, stadium
Use EXACT team names: Adelaide (NOT "Adelaide Crows"), Geelong (NOT "Geelong Cats"), Greater Western Sydney (NOT "GWS Giants"), Sydney (NOT "Sydney Swans"), West Coast (NOT "West Coast Eagles")

### matches: id, season (INTEGER), round (VARCHAR), match_date (TIMESTAMP), home_team_id, away_team_id, home_score, away_score, venue, attendance
- round values: regular rounds "0","1".."24"; finals: "Qualifying Final","Elimination Final","Semi Final","Preliminary Final","Grand Final"
- ALWAYS include finals in round-by-round season queries
- Contains historical data (1990-2025)

### live_games: id, season, round, match_date (TIMESTAMP), home_team_id, away_team_id, home_score, away_score, home_goals, home_behinds, away_goals, away_behinds, venue, status, current_quarter
- Contains live/recent games (2026+) with real-time scores
- CRITICAL: For queries about recent games (last night, yesterday, today, this week) in 2026, query live_games NOT matches
- Use same JOIN pattern as matches: JOIN teams t_home ON lg.home_team_id = t_home.id

### players: id, name, team_id (CURRENT team only — WARNING: wrong for traded players), position, height, weight, debut_year

### player_stats: match_id, player_id, team_id (team player played FOR — correct for trades!), disposals, kicks, handballs, marks, tackles, goals, behinds, hitouts, clearances, inside_50s, rebound_50s, contested_possessions, uncontested_possessions, contested_marks, marks_inside_50, one_percenters, bounces, goal_assist, clangers, free_kicks_for, free_kicks_against, fantasy_points, brownlow_votes, time_on_ground_pct

CRITICAL RULES:
1. Only SELECT statements (no INSERT/UPDATE/DELETE/DROP)
2. When filtering team matches: WHERE (m.home_team_id = t.id OR m.away_team_id = t.id)
3. For team-aggregated player stats: use player_stats.team_id NOT players.team_id
4. GROUP BY must include all non-aggregated SELECT columns
5. ORDER BY with DESC: add NULLS LAST
6. For temporal/trend queries: return ONE ROW PER SEASON, GROUP BY season
7. For single-season performance: return ONE ROW PER MATCH (round-by-round)
8. NEVER use CROSS JOIN
9. CRITICAL: For "who won" or "who played" queries, SELECT must include:
   - Both team names (home_team, away_team)
   - Both scores (home_score, away_score)
   - Winner calculation (CASE statement)
   - Margin (ABS difference)
   - Match context (venue, match_date, round)
   Do NOT return only partial data like just margin or just one team!

Common patterns:
- Team season record: JOIN teams t, filter (home_team_id=t.id OR away_team_id=t.id), CASE for wins/losses
- Player stats: JOIN player_stats ps, players p, matches m ON ps.match_id=m.id
- Grand Final: WHERE m.round = 'Grand Final' AND m.season = <year>
- Player name matching: ALWAYS use p.name ILIKE '%Surname%' (with leading %) because names are stored as "First Last"
- Temporal queries: Use match_date for date filtering
  - "last night", "yesterday" (2026-03-13): Query live_games table with WHERE DATE(lg.match_date) = '2026-03-13'
  - "today" (2026-03-14): Query live_games with WHERE DATE(lg.match_date) = '2026-03-14'
  - Recent games (last 7 days): Query live_games with WHERE lg.match_date >= '2026-03-07'
  - Latest game: ORDER BY lg.match_date DESC, lg.id DESC LIMIT 1 from live_games
  - IMPORTANT: Recent queries (2026) use live_games, historical queries (≤2025) use matches
- Match winner queries ("who won"): ALWAYS include teams, scores, and calculated winner.
  For 2026 dates (recent games), use live_games table:
  SELECT
    t_home.name as home_team,
    t_away.name as away_team,
    lg.home_score,
    lg.away_score,
    CASE
      WHEN lg.home_score > lg.away_score THEN t_home.name
      WHEN lg.away_score > lg.home_score THEN t_away.name
      ELSE 'Draw'
    END as winner,
    ABS(lg.home_score - lg.away_score) as margin,
    lg.round,
    lg.venue
  FROM live_games lg
  JOIN teams t_home ON lg.home_team_id = t_home.id
  JOIN teams t_away ON lg.away_team_id = t_away.id
  WHERE DATE(lg.match_date) = '2026-03-13'

  For historical dates (pre-2026), use matches table (replace lg with m, live_games with matches)

- "Who played" queries: Same pattern - use live_games for 2026+, matches for historical
  Example for "Who played last night?":
  SELECT t_home.name as home_team, t_away.name as away_team, lg.home_score, lg.away_score, CASE WHEN lg.home_score > lg.away_score THEN t_home.name WHEN lg.away_score > lg.home_score THEN t_away.name ELSE 'Draw' END as winner, ABS(lg.home_score - lg.away_score) as margin, lg.round, lg.venue FROM live_games lg JOIN teams t_home ON lg.home_team_id = t_home.id JOIN teams t_away ON lg.away_team_id = t_away.id WHERE DATE(lg.match_date) = '2026-03-13' ORDER BY lg.id

{conversation_context}

## Output Format (JSON only, no markdown)
{{
  "intent": "simple_stat"|"player_comparison"|"team_analysis"|"trend_analysis",
  "entities": {{
    "teams": [...],
    "players": [...],
    "seasons": [...],
    "metrics": [...],
    "rounds": [...]
  }},
  "requires_visualization": true|false,
  "chart_type": "line"|"bar"|"grouped_bar"|"scatter"|null,
  "chart_config": {{
    "x_col_hint": "expected x-axis column name from the SQL (e.g. 'season', 'name')",
    "y_col_hint": "expected y-axis column name from the SQL (e.g. 'total_goals', 'avg_disposals')"
  }},
  "sql": "SELECT ..."
}}

Chart type rules:
- trend_analysis or temporal queries -> "line"
- player_comparison -> "grouped_bar" (multiple metrics) or "bar"
- top-N / ranking queries -> "bar"
- simple_stat with single number -> null (no chart)
- If unsure, set chart_type to null

User question: {user_query}"""


def _build_conversation_context(conversation_history: Optional[List[Dict]]) -> str:
    """Build a compact conversation context section for the prompt."""
    if not conversation_history or len(conversation_history) < 2:
        return ""

    recent = conversation_history[-6:]  # Last 3 exchanges
    lines = ["## Previous Conversation Context", "Resolve pronouns/references using this context:"]

    for msg in recent:
        role = msg.get("role", "")
        content = msg.get("content", "")[:150]
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            entities = msg.get("entities", {})
            teams = entities.get("teams", [])
            players = entities.get("players", [])
            seasons = entities.get("seasons", [])
            if players:
                desc = ", ".join(players)
                if seasons:
                    desc += f" in {', '.join(str(s) for s in seasons)}"
                lines.append(f"Assistant discussed: {desc}")
            elif teams:
                desc = ", ".join(teams)
                if seasons:
                    desc += f" in {', '.join(str(s) for s in seasons)}"
                lines.append(f"Assistant discussed: {desc}")

    lines.append("---")
    return "\n".join(lines)


class ConsolidatedQueryUnderstanding:
    """
    Single OpenAI call that returns intent, entities, visualization flag, AND SQL.

    Replaces the separate UNDERSTAND call + QueryBuilder.generate_sql() call.
    """

    @staticmethod
    def understand_and_generate_sql(
        user_query: str,
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Make one LLM call that understands the query AND generates SQL.

        Returns:
            {
                "success": bool,
                "intent": str,
                "entities": dict,
                "requires_visualization": bool,
                "sql": str,
                "error": str or None,
            }
        """
        try:
            conv_ctx = _build_conversation_context(conversation_history)

            # Check cache first
            key = _cache_key(user_query, conv_ctx)
            if key in _llm_cache:
                logger.info("CONSOLIDATED-LLM: Cache HIT — skipping API call")
                return _llm_cache[key]

            prompt = _INTENT_AND_SQL_PROMPT.format(
                user_query=user_query,
                conversation_context=conv_ctx,
            )

            logger.info("CONSOLIDATED-LLM: Calling OpenAI (single intent+SQL call)...")
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_FAST", "gpt-5-nano"),
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                reasoning_effort="low",
            )

            raw = (response.choices[0].message.content or "").strip()
            logger.info(f"CONSOLIDATED-LLM: Raw response length={len(raw)}")

            data = json.loads(raw)

            intent = data.get("intent", "unknown")
            entities = data.get("entities", {})
            requires_viz = bool(data.get("requires_visualization", False))
            sql = data.get("sql", "").strip()
            chart_type = data.get("chart_type")  # May be null/None
            chart_config = data.get("chart_config", {})

            # Off-topic queries don't need SQL
            if intent == "off_topic":
                logger.info("CONSOLIDATED-LLM: Off-topic query detected by LLM")
                return {
                    "success": True,
                    "intent": "off_topic",
                    "entities": entities,
                    "requires_visualization": False,
                    "sql": None,
                    "chart_type": None,
                    "chart_config": {},
                    "error": None,
                }

            # Basic validation
            if not sql or not sql.upper().startswith("SELECT"):
                raise ValueError(f"LLM returned invalid SQL: {sql[:100]}")

            # Clean up SQL (strip markdown if model added it anyway)
            if "```sql" in sql:
                sql = sql.split("```sql")[1].split("```")[0]
            elif "```" in sql:
                sql = sql.split("```")[1].split("```")[0]

            # Replace literal escaped newlines and tabs with spaces
            sql = sql.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")

            # Normalize all whitespace to single spaces
            sql = " ".join(sql.split())

            logger.info(
                f"CONSOLIDATED-LLM: OK — intent={intent}, "
                f"entities={entities}, viz={requires_viz}, sql={sql[:80]}..."
            )

            result = {
                "success": True,
                "intent": intent,
                "entities": entities,
                "requires_visualization": requires_viz,
                "sql": sql,
                "chart_type": chart_type,
                "chart_config": chart_config,
                "error": None,
            }

            # Store in cache (evict oldest if full)
            if len(_llm_cache) >= _LLM_CACHE_MAX:
                _llm_cache.pop(next(iter(_llm_cache)))
            _llm_cache[key] = result

            return result

        except Exception as e:
            logger.error(f"CONSOLIDATED-LLM: Failed — {type(e).__name__}: {e}")
            return {
                "success": False,
                "intent": "unknown",
                "entities": {},
                "requires_visualization": False,
                "sql": None,
                "error": str(e),
            }
