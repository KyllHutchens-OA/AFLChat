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
_LLM_CACHE_MAX = 512


_PROMPT_VERSION = "v3"  # Bump when prompt template changes to invalidate cache


def _cache_key(user_query: str, conv_ctx: str) -> str:
    """Deterministic cache key from query + conversation context + prompt version."""
    raw = f"{_PROMPT_VERSION}|{user_query.strip().lower()}|{conv_ctx.strip()}"
    return hashlib.md5(raw.encode()).hexdigest()

# ── Prompts ────────────────────────────────────────────────────────────────────

_INTENT_AND_SQL_PROMPT = """\
You are an AFL analytics expert. In ONE step:
1. Parse the user's question (intent, entities).
2. Generate a valid PostgreSQL SELECT query.

## CRITICAL: Follow-up Question Handling
⚠️ If conversation context is provided below, the user may be asking a FOLLOW-UP question.
- Resolve pronouns: "he" → player from context, "they" → team from context, "that" → event/stat from context
- Follow-up examples that are NOT off_topic:
  - After discussing Tony Lockett: "What year did he achieve that?" → simple_stat about Tony Lockett
  - After discussing Richmond: "Who was their best player?" → simple_stat about Richmond
  - After discussing 2024 Grand Final: "Who came second?" → simple_stat about 2024 Grand Final
  - After discussing a player: "What about his career average?" → simple_stat about same player
  - After discussing 2025 wins: "What about just regular season?" → same query but for 2025 regular season only
  - After discussing 2023 stats: "Exclude finals" → same query but for 2023 excluding finals
- ALWAYS use conversation context to identify the subject of follow-up questions
- CRITICAL: If user asks to modify a previous query (e.g., "just regular season", "exclude finals"), KEEP the season from context!

## Intent Classification
⚠️ NEVER classify AFL follow-up questions as off_topic!

- "simple_stat": Single number/fact, including match results, follow-up questions about players/teams
- "player_comparison": Comparing multiple players
- "team_analysis": One team's performance in a single season/period
- "trend_analysis": Change over TIME (keywords: "over time", "across time", "year by year", "historical", "trend", "evolution", "since")
- "afl_news": Latest AFL news or articles
- "injury_news": Injury reports or player availability
- "betting_odds": Betting odds or lines
- "tipping_advice": AFL tipping/predictions
- "off_topic": ONLY for truly non-AFL questions (recipes, weather, other sports). NEVER for follow-ups about AFL topics!

Examples of off_topic (truly unrelated to AFL):
- "what's the weather" → off_topic
- "how to cook pasta" → off_topic
- "tell me about cricket" → off_topic

**IMPORTANT**: For news, injury, betting, or tipping queries, set sql="" (empty string) as these queries do NOT require database SQL queries.

## Entity Extraction Rules
- **CRITICAL**: For follow-up questions, extract entities from CONVERSATION CONTEXT:
  - "he", "his" → player from previous exchange
  - "they", "their" → team from previous exchange
  - "that year", "same season" → season from previous exchange
  - "that game", "the final" → match from previous exchange
- **Teams**: AFL club names (use canonical names: Adelaide, Brisbane Lions, Carlton, Collingwood, Essendon, Fremantle, Geelong, Gold Coast, Greater Western Sydney, Hawthorn, Melbourne, North Melbourne, Port Adelaide, Richmond, St Kilda, Sydney, West Coast, Western Bulldogs)
- **Players**: Surnames or full names (single-word surnames are ALWAYS players, never teams)
- **Seasons**: Years e.g. "2022", "last year" → infer current (2026)
- **Temporal References**: Convert to actual dates (current date: use server time)
  - "today" → current date
  - "yesterday", "last night" → current date - 1 day
  - "this week" → last 7 days from current date
  - "this round", "current round" → {current_round_hint}
  - "last round", "previous round" → {last_round_hint}
- **Metrics**: goals, disposals, marks, tackles, wins, losses, score, etc.

## SQL Generation Rules

The ONLY tables in this database are: `matches`, `teams`, `players`, `player_stats`, `team_stats`, `live_games`, `betting_odds`, `squiggle_predictions`, `news_articles`. Do NOT reference any other tables.

Database Schema:

### teams: id, name, abbreviation, stadium
Use EXACT team names: Adelaide (NOT "Adelaide Crows"), Geelong (NOT "Geelong Cats"), Greater Western Sydney (NOT "GWS Giants"), Sydney (NOT "Sydney Swans"), West Coast (NOT "West Coast Eagles")

Common venue aliases (use the DB canonical name in SQL):
- MCG / Melbourne Cricket Ground → 'M.C.G.'
- Marvel Stadium / Docklands / Etihad Stadium / Colonial Stadium / Telstra Dome → 'Marvel Stadium'
- GMHBA Stadium / Kardinia Park / Simonds Stadium / Skilled Stadium → 'GMHBA Stadium'
- The Gabba / Woolloongabba / Brisbane Cricket Ground → 'Gabba'
- SCG / Sydney Cricket Ground → 'S.C.G.'
- Optus Stadium / Perth Stadium → 'Optus Stadium'
- Adelaide Oval → 'Adelaide Oval'
- People First Stadium / Metricon Stadium / Carrara → 'People First Stadium'
- Blundstone Arena / Bellerive Oval → 'Blundstone Arena'
- UNSW Canberra Oval / Manuka Oval → 'UNSW Canberra Oval'
- TIO Traeger Park / Traeger Park → 'TIO Traeger Park'
When filtering by venue, use ILIKE for fuzzy matching: WHERE m.venue ILIKE '%MCG%' or WHERE m.venue ILIKE '%Marvel%'

### matches: id, season (INTEGER), round (VARCHAR), match_date (TIMESTAMP), home_team_id, away_team_id, home_score, away_score, venue, attendance, home_q1_goals, home_q1_behinds, home_q2_goals, home_q2_behinds, home_q3_goals, home_q3_behinds, home_q4_goals, home_q4_behinds, away_q1_goals, away_q1_behinds, away_q2_goals, away_q2_behinds, away_q3_goals, away_q3_behinds, away_q4_goals, away_q4_behinds
- Quarter scores are stored IN this table. Do NOT look for a separate `quarter_scores` table.
- Quarter score formula: Q1 score = q1_goals * 6 + q1_behinds. Cumulative: Q2 total = q1 + q2, etc.
- round values: regular rounds "0","1".."24"; finals: "Qualifying Final","Elimination Final","Semi Final","Preliminary Final","Grand Final"
- ALWAYS include finals in round-by-round season queries
- FIXTURE/UPCOMING GAMES: The matches table contains scheduled future fixtures with home_score=0 and away_score=0. For "who do they play next", "next game", "upcoming fixture", "next week" queries, use: WHERE m.match_date > NOW() AND m.home_score = 0 AND m.away_score = 0 ORDER BY m.match_date ASC LIMIT 1 (filter by team as needed)
- Contains historical data ({data_range})

### live_games: id, season, round, match_date (TIMESTAMP), home_team_id, away_team_id, home_score, away_score, home_goals, home_behinds, away_goals, away_behinds, venue, status, current_quarter
- Contains live/recent games (2026+) with real-time scores
- status values: 'scheduled' (not started), 'playing' (in progress), 'completed', 'post_match'
- CRITICAL: For queries about recent games (last night, yesterday, today, this week, this round, current round) in 2026, query live_games NOT matches
- "this round" / "current round" → WHERE lg.round = '{current_round_hint_round}' AND lg.season = {current_round_hint_season}
- "last round" / "previous round" → Round {last_round_hint_round} of {last_round_hint_season}. This round is fully completed.
  - For TEAM totals (team goals, team score, who won): use live_games table with lg.round = '{last_round_hint_round}'. live_games has home_goals, away_goals, home_behinds, away_behinds, home_score, away_score.
  - For PLAYER-LEVEL stats (individual disposals, marks, tackles): use player_stats JOIN matches with m.round = '{last_round_hint_round}'
  - NEVER estimate goals by dividing scores by 6 — always use actual goal columns (home_goals/away_goals from live_games, or ps.goals from player_stats)
- "games left" / "remaining" / "upcoming" / "scheduled" → add WHERE lg.status NOT IN ('completed', 'post_match')
- "results so far" / "scores" → add WHERE lg.status IN ('completed', 'post_match')
- Use same JOIN pattern as matches: JOIN teams t_home ON lg.home_team_id = t_home.id

### players: id, name, team_id (CURRENT team only — WARNING: wrong for traded players), height, weight, debut_year

### player_stats: match_id, player_id, team_id (team player played FOR — correct for trades!), disposals, kicks, handballs, marks, tackles, goals, behinds, hitouts, clearances, inside_50s, rebound_50s, contested_possessions, uncontested_possessions, contested_marks, marks_inside_50, one_percenters, bounces, goal_assist, clangers, free_kicks_for, free_kicks_against, fantasy_points, brownlow_votes, time_on_ground_pct
- IMPORTANT: fantasy_points is PRE-COMPUTED in the database using official AFL Fantasy scoring. For fantasy queries, SELECT fantasy_points directly — do NOT ask the user which scoring system to use.

CRITICAL RULES:
1. Only SELECT statements (no INSERT/UPDATE/DELETE/DROP)
2. When filtering team matches: WHERE (m.home_team_id = t.id OR m.away_team_id = t.id)
3. For team-aggregated player stats: use player_stats.team_id NOT players.team_id
4. GROUP BY must include all non-aggregated SELECT columns
5. ORDER BY with DESC: add NULLS LAST
6. For temporal/trend queries: return ONE ROW PER SEASON, GROUP BY season
7. For single-season performance: return ONE ROW PER MATCH (round-by-round)
8. NEVER use CROSS JOIN
9. CRITICAL — PLAYER IDENTITY: Multiple players share the same name (e.g. 4 Josh Kennedys, 3 Nathan Browns, 2 Gary Abletts, 2 Tom Lynches, 2 Scott Thompsons). ALWAYS GROUP BY p.id, p.name (not just p.name) when aggregating player stats. NEVER GROUP BY p.name alone — this merges different players and produces wrong totals. Example: GROUP BY p.name gives Josh Kennedy 571 games (wrong — combines 4 players), GROUP BY p.id, p.name gives 427 (correct — just the Sydney one).
10. CRITICAL: For "who won" or "who played" queries, SELECT must include:
   - Both team names (home_team, away_team)
   - Both scores (home_score, away_score)
   - Winner calculation (CASE statement)
   - Margin (ABS difference)
   - Match context (venue, match_date, round)
   Do NOT return only partial data like just margin or just one team!

## CURRENT ROUND FALLBACK:
For the CURRENT ROUND of the current season (where match data may not yet be in the `matches` table), use `live_games` with `status IN ('completed', 'post_match')` for scores, results, and game-level stats. For all prior rounds of the current season, use `matches` as normal — that data is ingested from AFL Tables weekly. The `player_stats` table only has rows for ingested matches, so current-round player stats may not be available yet.

## DO NOT (common LLM mistakes):
- DO NOT use round numbers like WHERE m.round = 1. Round is VARCHAR — use WHERE m.round = '1'
- DO NOT join players.team_id for historical stats — it only stores CURRENT team. Use player_stats.team_id
- DO NOT use CROSS JOIN or cartesian products
- DO NOT generate INSERT/UPDATE/DELETE/DROP statements
- DO NOT estimate goals by dividing scores by 6 — use actual goal columns
- DO NOT use LIMIT without ORDER BY
- DO NOT GROUP BY p.name alone for player stats — always include p.id to distinguish same-name players (e.g. Josh Kennedy played for both Sydney and West Coast)
- DO NOT filter by player position (`p.position`) — this column is not populated. If asked for 'midfielders' or 'forwards', suggest filtering by relevant stats instead (high disposals for mids, high goals for forwards).
- DO NOT reference tables that don't exist. Awards, draft picks, and ladder tables do NOT exist. Brownlow votes per game are in `player_stats.brownlow_votes`.

## Few-shot SQL examples (error-prone patterns):

Q: "How many goals did Hawkins kick in 2024?"
SQL: SELECT p.name, SUM(ps.goals) AS total_goals FROM player_stats ps JOIN players p ON ps.player_id = p.id JOIN matches m ON ps.match_id = m.id WHERE p.name ILIKE '%Hawkins%' AND m.season = 2024 GROUP BY p.id, p.name

Q: "Carlton's win-loss record in 2023"
SQL: SELECT t.name, SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score > m.away_score) OR (m.away_team_id = t.id AND m.away_score > m.home_score) THEN 1 ELSE 0 END) AS wins, SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score < m.away_score) OR (m.away_team_id = t.id AND m.away_score < m.home_score) THEN 1 ELSE 0 END) AS losses, COUNT(*) AS games FROM matches m JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) WHERE t.name = 'Carlton' AND m.season = 2023 GROUP BY t.name

Q: "Top 5 disposal getters in 2024"
SQL: SELECT p.name, SUM(ps.disposals) AS total_disposals, t.name AS team FROM player_stats ps JOIN players p ON ps.player_id = p.id JOIN matches m ON ps.match_id = m.id JOIN teams t ON ps.team_id = t.id WHERE m.season = 2024 AND ps.disposals IS NOT NULL GROUP BY p.id, p.name, t.id, t.name ORDER BY total_disposals DESC NULLS LAST LIMIT 5

Q: "Geelong's scoring trend from 2018 to 2024"
SQL: SELECT m.season, ROUND(AVG(CASE WHEN m.home_team_id = t.id THEN m.home_score ELSE m.away_score END), 1) AS avg_score FROM matches m JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) WHERE t.name = 'Geelong' AND m.season BETWEEN 2018 AND 2024 GROUP BY m.season ORDER BY m.season

Common patterns:
- Team season record: JOIN teams t, filter (home_team_id=t.id OR away_team_id=t.id), CASE for wins/losses
- Player stats: JOIN player_stats ps, players p, matches m ON ps.match_id=m.id
- Grand Final: WHERE m.round = 'Grand Final' AND m.season = <year>
- Bye rounds: To find bye rounds for a team, look for numeric rounds where the team has no match but other teams do. A team had a bye in round R if they have no row in matches for that round but other matches exist in that round.
- Player name matching:
  - Surname only (e.g. "Ashcroft"): p.name ILIKE '%Ashcroft%'
  - Full name given (e.g. "Will Ashcroft"): p.name ILIKE 'Will%Ashcroft%' — include BOTH parts so you don't return other players with the same surname (e.g. Levi Ashcroft, Marcus Ashcroft)
  - CRITICAL: When the user names ONE specific player, your WHERE clause MUST return exactly one player. If the full name is given, match first AND last name.
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
- Current round results ("results this round", "scores so far"):
  SELECT t_home.name as home_team, t_away.name as away_team, lg.home_score, lg.away_score,
    CASE WHEN lg.home_score > lg.away_score THEN t_home.name WHEN lg.away_score > lg.home_score THEN t_away.name ELSE 'Draw' END as winner,
    ABS(lg.home_score - lg.away_score) as margin, lg.venue
  FROM live_games lg JOIN teams t_home ON lg.home_team_id = t_home.id JOIN teams t_away ON lg.away_team_id = t_away.id
  WHERE lg.round = '{current_round_hint_round}' AND lg.season = {current_round_hint_season} AND lg.status IN ('completed', 'post_match')
- Games remaining ("what games are left", "upcoming games"):
  SELECT t_home.name as home_team, t_away.name as away_team, lg.match_date, lg.venue, lg.round
  FROM live_games lg JOIN teams t_home ON lg.home_team_id = t_home.id JOIN teams t_away ON lg.away_team_id = t_away.id
  WHERE lg.round = '{current_round_hint_round}' AND lg.season = {current_round_hint_season} AND lg.status NOT IN ('completed', 'post_match')
  Example for "Who played last night?":
  SELECT t_home.name as home_team, t_away.name as away_team, lg.home_score, lg.away_score, CASE WHEN lg.home_score > lg.away_score THEN t_home.name WHEN lg.away_score > lg.home_score THEN t_away.name ELSE 'Draw' END as winner, ABS(lg.home_score - lg.away_score) as margin, lg.round, lg.venue FROM live_games lg JOIN teams t_home ON lg.home_team_id = t_home.id JOIN teams t_away ON lg.away_team_id = t_away.id WHERE DATE(lg.match_date) = '2026-03-13' ORDER BY lg.id
- HOME/AWAY game queries (CRITICAL - don't confuse these!):
  - "home wins" = wins when team was HOME team: WHERE m.home_team_id = t.id AND m.home_score > m.away_score
  - "away wins" = wins when team was AWAY team: WHERE m.away_team_id = t.id AND m.away_score > m.home_score
  - "home games" = games where team was home: WHERE m.home_team_id = t.id
  - "away games" = games where team was away: WHERE m.away_team_id = t.id
  - "home record" = wins/losses/draws in HOME games only (filter to home_team_id = t.id first!)
  - Do NOT count away wins as home wins! Filter by venue (home_team_id) BEFORE counting wins.
  Example for "Collingwood home record in 2023":
  SELECT SUM(CASE WHEN m.home_score > m.away_score THEN 1 ELSE 0 END) AS home_wins,
         SUM(CASE WHEN m.home_score < m.away_score THEN 1 ELSE 0 END) AS home_losses,
         COUNT(*) AS home_games
  FROM matches m JOIN teams t ON t.name = 'Collingwood'
  WHERE m.season = 2023 AND m.home_team_id = t.id

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
  "data_shape_hint": "temporal_trend"|"top_n_ranking"|"comparison"|"single_value"|"distribution"|null,
  "chart_config": {{
    "x_col_hint": "expected x-axis column name from the SQL (e.g. 'season', 'name')",
    "y_col_hint": "expected y-axis column name from the SQL (e.g. 'total_goals', 'avg_disposals')"
  }},
  "sql": "SELECT ..."
}}

requires_visualization rules:
- true: trends over time, comparisons of 3+ entities, top-N rankings (N≥3), round-by-round data
- false: single facts/numbers, yes/no answers, match results, 1-2 row results, news/odds/tips

Data shape hint rules (describes the SHAPE of the expected result, NOT the chart type):
- temporal_trend: data has a time dimension (season, round) — one row per time period
- top_n_ranking: data is a ranked list of items (players, teams) — ordered by a metric
- comparison: side-by-side comparison of 2-5 entities across metrics
- single_value: query returns a single number/fact — no chart needed
- distribution: statistical spread of values (e.g., score distributions)
- null: if unsure

User question: {user_query}"""


def _build_conversation_context(conversation_history: Optional[List[Dict]]) -> str:
    """Build conversation context that enables follow-up question handling."""
    if not conversation_history or len(conversation_history) < 2:
        return ""

    recent = conversation_history[-6:]  # Last 3 exchanges
    lines = [
        "## Conversation Context (CRITICAL for follow-up questions)",
        "⚠️ IMPORTANT: If the user's question contains pronouns (he, she, they, it, that, this) or references",
        "(\"the same\", \"what about\", \"and for\", \"who else\"), resolve them using this context.",
        "Follow-up questions about previous topics are NEVER off_topic!",
        ""
    ]

    for msg in recent:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"User asked: {content[:200]}")
        elif role == "assistant":
            # Include BOTH the response content AND extracted entities
            lines.append(f"Assistant answered: {content[:250]}")
            entities = msg.get("entities", {})
            players = entities.get("players", [])
            teams = entities.get("teams", [])
            seasons = entities.get("seasons", [])
            if players or teams or seasons:
                entity_parts = []
                if players:
                    entity_parts.append(f"players: {', '.join(players)}")
                if teams:
                    entity_parts.append(f"teams: {', '.join(teams)}")
                if seasons:
                    entity_parts.append(f"seasons: {', '.join(str(s) for s in seasons)}")
                lines.append(f"  → Entities: {'; '.join(entity_parts)}")
        lines.append("")

    lines.append("---")
    lines.append("Use the above context to resolve any pronouns or references in the current question.")
    lines.append("")
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

            # Inject dynamic data recency
            from app.data.database import get_data_recency
            recency = get_data_recency()
            earliest = recency["earliest_season"]
            hist_season = recency["historical_latest_season"]
            hist_round = recency["historical_latest_round"]
            live_season = recency.get("live_latest_season")
            live_round = recency.get("live_latest_round")

            # Determine the most recently completed round and the current/upcoming round
            # "last round" = most recently completed round
            # "this round" / "current round" = next round (upcoming or in-progress)
            if live_season and live_round:
                completed_round = int(live_round)
                completed_season = str(live_season)
            else:
                try:
                    completed_round = int(hist_round)
                except (ValueError, TypeError):
                    completed_round = 0
                completed_season = str(hist_season)

            # "this round" is the next one after the last completed round
            current_round_hint_round = str(completed_round + 1)
            current_round_hint_season = completed_season
            current_round_hint = f"Round {current_round_hint_round} of {current_round_hint_season}"

            # "last round" is the most recently completed round
            last_round_hint_round = str(completed_round)
            last_round_hint_season = completed_season
            last_round_hint = f"Round {last_round_hint_round} of {last_round_hint_season}"

            data_range = f"{earliest}-{hist_season}"

            prompt = _INTENT_AND_SQL_PROMPT.format(
                user_query=user_query,
                conversation_context=conv_ctx,
                current_round_hint=current_round_hint,
                current_round_hint_round=current_round_hint_round,
                current_round_hint_season=current_round_hint_season,
                last_round_hint=last_round_hint,
                last_round_hint_round=last_round_hint_round,
                last_round_hint_season=last_round_hint_season,
                data_range=data_range,
            )

            logger.info("CONSOLIDATED-LLM: Calling OpenAI (single intent+SQL call)...")
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_FAST", "gpt-5-mini"),
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
            # Map data_shape_hint to chart_type for downstream consumers
            data_shape = data.get("data_shape_hint")
            _SHAPE_TO_CHART = {
                "temporal_trend": "line",
                "top_n_ranking": "bar",
                "comparison": "grouped_bar",
                "single_value": None,
                "distribution": "box",
            }
            chart_type = _SHAPE_TO_CHART.get(data_shape, data.get("chart_type"))
            chart_config = data.get("chart_config", {})

            # Intents that don't require SQL (handled by specialized tools)
            NO_SQL_INTENTS = {"off_topic", "afl_news", "injury_news", "betting_odds", "tipping_advice"}

            if intent in NO_SQL_INTENTS:
                logger.info(f"CONSOLIDATED-LLM: {intent} query - no SQL needed")
                return {
                    "success": True,
                    "intent": intent,
                    "entities": entities,
                    "requires_visualization": False,
                    "sql": None,
                    "chart_type": None,
                    "chart_config": {},
                    "error": None,
                }

            # Basic validation for SQL-requiring intents
            # Accept both SELECT and WITH (CTE) statements
            sql_upper = sql.upper().strip() if sql else ""
            if not sql or not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
                raise ValueError("LLM returned invalid SQL")

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
                "error": "Failed to process query — try rephrasing your question.",
            }
