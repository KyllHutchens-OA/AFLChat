"""
AFL Analytics Agent - Text-to-SQL Generator

Converts natural language queries into validated SQL using GPT-5-nano.
"""
from typing import Dict, Any, Optional
from openai import OpenAI
import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class QueryBuilder:
    """
    Generates SQL queries from natural language using GPT-4.

    Provides schema context to GPT-4 for accurate query generation.
    """

    # Database schema for GPT-4 context
    SCHEMA_CONTEXT = """
# AFL Database Schema

## Tables

### teams
- id (INTEGER, PRIMARY KEY)
- name (VARCHAR) - Full team name
- abbreviation (VARCHAR) - 3-letter code
- stadium (VARCHAR)

**Team Names (use exact names for matching)**:
- Adelaide (ADE) - NOT "Adelaide Crows"
- Brisbane Lions (BRI)
- Carlton (CAR)
- Collingwood (COL)
- Essendon (ESS)
- Fremantle (FRE)
- Geelong (GEE) - "Geelong Cats" should use "Geelong"
- Gold Coast (GCS)
- Greater Western Sydney (GWS) - "GWS Giants" should use "Greater Western Sydney"
- Hawthorn (HAW)
- Melbourne (MEL)
- North Melbourne (NM) - NOT "Kangaroos"
- Port Adelaide (PA) - NOT "Port Adelaide Power"
- Richmond (RIC) - "Richmond Tigers" should use "Richmond"
- St Kilda (STK)
- Sydney (SYD) - "Sydney Swans" should use "Sydney"
- West Coast (WCE) - "West Coast Eagles" should use "West Coast"
- Western Bulldogs (WB)

### matches
- id (INTEGER, PRIMARY KEY)
- season (INTEGER) - Year (e.g., 2024)
- round (VARCHAR) - Round number as string. Regular rounds: "0", "1", "2", ... "24" (numeric strings WITHOUT "Round " prefix). Finals rounds: "Qualifying Final", "Elimination Final", "Semi Final", "Preliminary Final", "Grand Final". CRITICAL: When querying round-by-round data for a season, ALWAYS include both regular AND finals rounds - do NOT filter to only numeric rounds.
- match_date (TIMESTAMP) - **IMPORTANT: Use match_date, not date**
- home_team_id (INTEGER, FOREIGN KEY -> teams.id)
- away_team_id (INTEGER, FOREIGN KEY -> teams.id)
- home_score (INTEGER) - Total points
- away_score (INTEGER) - Total points
- venue (VARCHAR)
- attendance (INTEGER)
- match_status (VARCHAR)
- home_q1_goals, home_q1_behinds (INTEGER) - Quarter 1 scoring
- home_q2_goals, home_q2_behinds (INTEGER) - Quarter 2 scoring
- home_q3_goals, home_q3_behinds (INTEGER) - Quarter 3 scoring
- home_q4_goals, home_q4_behinds (INTEGER) - Quarter 4 scoring
- away_q1_goals, away_q1_behinds (INTEGER) - Quarter 1 scoring
- away_q2_goals, away_q2_behinds (INTEGER) - Quarter 2 scoring
- away_q3_goals, away_q3_behinds (INTEGER) - Quarter 3 scoring
- away_q4_goals, away_q4_behinds (INTEGER) - Quarter 4 scoring
- created_at, updated_at (TIMESTAMP)

### players
- id (INTEGER, PRIMARY KEY)
- name (VARCHAR)
- team_id (INTEGER, FOREIGN KEY -> teams.id)
- position (VARCHAR)
- height (INTEGER) - in cm
- weight (INTEGER) - in kg
- debut_year (INTEGER)
- created_at, updated_at (TIMESTAMP)

### player_stats
- match_id (INTEGER, FOREIGN KEY -> matches.id)
- player_id (INTEGER, FOREIGN KEY -> players.id)
- disposals (INTEGER)
- kicks (INTEGER)
- handballs (INTEGER)
- marks (INTEGER)
- tackles (INTEGER)
- goals (INTEGER)
- behinds (INTEGER)
- hitouts (INTEGER)
- clearances (INTEGER)
- inside_50s (INTEGER)
- rebound_50s (INTEGER)
- contested_possessions (INTEGER)
- uncontested_possessions (INTEGER)
- contested_marks (INTEGER)
- marks_inside_50 (INTEGER)
- one_percenters (INTEGER)
- clangers (INTEGER)
- free_kicks_for (INTEGER)
- free_kicks_against (INTEGER)
- brownlow_votes (INTEGER)
- time_on_ground_pct (FLOAT)

### team_stats (currently empty - will be populated in future)
- match_id (INTEGER, FOREIGN KEY -> matches.id)
- team_id (INTEGER, FOREIGN KEY -> teams.id)
- score (INTEGER)
- inside_50s (INTEGER)
- clearances (INTEGER)
- tackles (INTEGER)

## Important Notes
- **Data Availability**:
  * Match-level data: 1990-2025 (6,000+ matches)
  * Player statistics: 1990-2024 (excluding 1994, 2017) + very limited 2025 (12,615 players, 230,000+ match-level stats)
  * **2025 data is VERY LIMITED** - only 1-2 matches available, warn users that 2025 season data is incomplete
- **Team Names**: Use the teams table to get correct team names and IDs
- **Finals**: Finals rounds have string names like "Qualifying Final", "Grand Final". ALWAYS include finals in round-by-round queries for a season - they are part of the season data.
- **Scoring**: home_score and away_score are total points (goals × 6 + behinds)
- **Player Queries**: Join players and player_stats with matches to get per-match player performance
"""

    SYSTEM_PROMPT = """You are an expert SQL query generator for an AFL (Australian Football League) database.

Your task is to convert natural language questions into valid PostgreSQL SELECT queries.

Guidelines:
1. Generate ONLY SELECT queries (no INSERT, UPDATE, DELETE, DROP)
2. Use proper JOIN syntax when combining tables (INNER JOIN, LEFT JOIN - NEVER use CROSS JOIN)
3. CRITICAL: When filtering for a specific team's matches, ALWAYS add: WHERE (m.home_team_id = team.id OR m.away_team_id = team.id)
4. Include appropriate WHERE clauses for filtering
5. Use aggregate functions (COUNT, AVG, SUM, MAX, MIN) when needed
6. Order results meaningfully (e.g., by match_date DESC, by score DESC)
7. Limit results to reasonable amounts (use LIMIT when appropriate)
8. CRITICAL: Use EXACT team names from the schema (e.g., "Adelaide" NOT "Adelaide Crows", "Geelong" NOT "Geelong Cats")
9. Handle team names case-insensitively with ILIKE, but use the correct base name
10. Player queries: Join players and player_stats tables with matches to get player performance data
11. NEVER use CROSS JOIN - it creates a Cartesian product and returns wrong results
12. CRITICAL: When using GROUP BY, ALL non-aggregated columns in SELECT must appear in GROUP BY clause
13. For win/loss ratios, use direct aggregation without subqueries when possible

Common Patterns:
- Team's season stats: Filter matches with WHERE (home_team_id = X OR away_team_id = X)
- Use CASE statements to calculate team-specific stats from home/away columns
- Win/loss ratios: Use SUM with CASE for wins/losses, then calculate ratio directly (no subquery needed)

IMPORTANT - For "team performance" or "by round" queries:
- Return ROUND-BY-ROUND data (one row per match), NOT season aggregates
- Include: round, match_date, opponent, score, result (Win/Loss/Draw), margin
- This allows visualization of performance trends over the season
- Example: "Show me Richmond's performance in 2024" should return ~24 rows (one per round)

CRITICAL - ALWAYS INCLUDE FINALS when querying round-by-round data for a season:
- Regular rounds are stored as: '0', '1', '2', ... '24'
- Finals rounds are stored as: 'Qualifying Final', 'Elimination Final', 'Semi Final', 'Preliminary Final', 'Grand Final'
- When user asks for "by round", "each round", "round breakdown" for a season, INCLUDE ALL ROUNDS (regular + finals)
- Do NOT filter to only numeric rounds - include finals rounds in results
- Example: For "goals by round in 2024", return rounds 0-24 AND any finals that exist
- Finals are part of the season and should always be included in round-by-round breakdowns

CRITICAL - For TEMPORAL/TREND queries (over time, across time, year-by-year, historical):
- ALWAYS return ONE ROW PER TIME PERIOD (year, season, etc.)
- Keywords triggering temporal queries: "over time", "across time", "year by year", "historical", "trend", "evolution", "since"
- Example: "Adelaide's win/loss ratio over time" → SELECT season, wins, losses FROM ... GROUP BY season ORDER BY season
- NEVER aggregate multiple years into a single row for temporal queries
- Each year should be a separate row to enable proper time-series visualization
- Minimum data points for useful charts: At least 3-5 time periods

Example for team performance:
SELECT
  m.round,
  m.match_date,
  opponent.name AS opponent,
  CASE WHEN home THEN home_score ELSE away_score END AS team_score,
  CASE WHEN home THEN away_score ELSE home_score END AS opponent_score,
  CASE WHEN won THEN 'Win' ELSE 'Loss' END AS result
FROM matches m
WHERE team matches
ORDER BY m.match_date

Return ONLY the SQL query, no explanations or markdown formatting."""

    @staticmethod
    def generate_sql(user_query: str, context: Optional[Dict[str, Any]] = None, conversation_history: Optional[list] = None) -> Dict[str, Any]:
        """
        Generate SQL query from natural language.

        Args:
            user_query: Natural language question
            context: Optional context (entities, intent, etc.)
            conversation_history: Optional previous conversation messages for resolving references

        Returns:
            Dictionary with:
            - success: bool
            - sql: str (if successful)
            - error: str (if failed)
            - explanation: str (what the query does)
        """
        try:
            # Build prompt with schema context
            prompt_text = f"""{QueryBuilder.SYSTEM_PROMPT}

Database Schema:
{QueryBuilder.SCHEMA_CONTEXT}

Question: {user_query}"""

            # Add conversation context for follow-up queries
            if conversation_history and len(conversation_history) > 0:
                recent_messages = conversation_history[-4:]  # Last 2 exchanges

                prompt_text += "\n\n## Previous Conversation Context\n"
                prompt_text += "Use this context to resolve ambiguous references (e.g., 'this', 'them', 'by year'):\n"

                for msg in recent_messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")[:150]  # Truncate long messages

                    if role == "user":
                        prompt_text += f"User asked: {content}\n"
                    elif role == "assistant":
                        # Include assistant entities for context
                        entities = msg.get("entities", {})
                        if entities:
                            teams = entities.get("teams", [])
                            players = entities.get("players", [])
                            seasons = entities.get("seasons", [])
                            if players:
                                prompt_text += f"(Was discussing: {', '.join(players)}"
                                if seasons:
                                    prompt_text += f" in {', '.join(str(s) for s in seasons)}"
                                prompt_text += ")\n"
                            elif teams:
                                prompt_text += f"(Was discussing: {', '.join(teams)}"
                                if seasons:
                                    prompt_text += f" in {', '.join(str(s) for s in seasons)}"
                                prompt_text += ")\n"

                prompt_text += "\nFor the current query, resolve references using the context above.\n"

            # Add context if provided (these are VALIDATED entities with canonical team names)
            if context and any(context.values()):
                prompt_text += f"\n\nValidated Entities (use these exact names in SQL):"
                if context.get("teams"):
                    prompt_text += f"\n- Teams: {', '.join(context['teams'])}"
                if context.get("seasons"):
                    prompt_text += f"\n- Seasons: {', '.join(str(s) for s in context['seasons'])}"
                if context.get("players"):
                    prompt_text += f"\n- Players: {', '.join(context['players'])}"
                if context.get("rounds"):
                    # Normalize round names to match database format
                    # Database has: '0', '1', '2', ... for regular rounds
                    # Entity extraction gives: 'Round 1', 'Round 2', ...
                    normalized_rounds = []
                    for r in context['rounds']:
                        r_str = str(r)
                        # Strip "Round " prefix if present
                        if r_str.startswith("Round "):
                            r_str = r_str.replace("Round ", "")
                        normalized_rounds.append(r_str)
                    prompt_text += f"\n- Rounds: {', '.join(normalized_rounds)}"

            prompt_text += "\n\nGenerate the SQL query:"

            # Call GPT-5-nano (cheapest and fastest) using Responses API
            response = client.responses.create(
                model="gpt-5-nano",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt_text
                            }
                        ]
                    }
                ]
            )

            sql = response.output_text.strip()

            # Log raw SQL before cleaning for debugging
            logger.info(f"Raw SQL from GPT-5-nano: {sql[:200]}")

            # Clean up the SQL (remove markdown code blocks if present)
            sql = QueryBuilder._clean_sql(sql)

            logger.info(f"Cleaned SQL: {sql[:200]}")
            logger.info(f"Generated SQL for query: {user_query[:50]}...")

            # Generate explanation
            explanation = QueryBuilder._generate_explanation(sql)

            return {
                "success": True,
                "sql": sql,
                "error": None,
                "explanation": explanation
            }

        except Exception as e:
            logger.error(f"SQL generation error: {e}")
            return {
                "success": False,
                "sql": None,
                "error": str(e),
                "explanation": None
            }

    @staticmethod
    def _clean_sql(sql: str) -> str:
        """Clean SQL query (remove markdown formatting, extra whitespace)."""
        # Remove markdown code blocks
        if "```sql" in sql:
            sql = sql.split("```sql")[1].split("```")[0]
        elif "```" in sql:
            sql = sql.split("```")[1].split("```")[0]

        # Remove extra whitespace
        sql = " ".join(sql.split())

        return sql.strip()

    @staticmethod
    def _generate_explanation(sql: str) -> str:
        """Generate a simple explanation of what the SQL query does."""
        sql_upper = sql.upper()

        # Basic pattern matching for explanation
        if "COUNT(*)" in sql_upper:
            return "Counting records"
        elif "AVG(" in sql_upper:
            return "Calculating averages"
        elif "SUM(" in sql_upper:
            return "Summing values"
        elif "MAX(" in sql_upper:
            return "Finding maximum values"
        elif "MIN(" in sql_upper:
            return "Finding minimum values"
        elif "GROUP BY" in sql_upper:
            return "Grouping and aggregating data"
        elif "JOIN" in sql_upper:
            return "Combining data from multiple tables"
        else:
            return "Retrieving data"
