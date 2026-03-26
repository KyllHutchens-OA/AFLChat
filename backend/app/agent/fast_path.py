"""
AFL Analytics Agent - Fast-Path Router

Intercepts simple, common queries BEFORE the full LangGraph pipeline.
Uses regex pattern matching + parameterized SQL templates + string response templates.
Zero LLM calls for matched queries — reduces latency from ~3-5s to ~100-300ms.

Falls through (returns None) for:
- Queries that don't match any pattern
- Follow-up queries ("what about 2023?")
- Entity resolution failures (unknown team/player)
- DB returning 0 rows
"""
import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)

# Follow-up / ambiguous query indicators — skip fast-path for these
_FOLLOWUP_PATTERNS = re.compile(
    r"\b(what about|how about|and them|and they|and their|compare|vs|versus|"
    r"their|they|them|those|these|that team|last year|this year|last season|"
    r"this season)\b",
    re.IGNORECASE
)

# ── Off-topic detection ──────────────────────────────────────────────────────
# AFL-related keywords — if the query contains ANY of these, it's likely on-topic.
_AFL_KEYWORDS = re.compile(
    r"\b(afl|footy|football|aussie rules|round|season|grand final|finals|"
    r"preliminary|elimination|qualifying|brownlow|coleman|norm smith|"
    r"goal|goals|kick|kicks|handball|handballs|disposal|disposals|"
    r"mark|marks|tackle|tackles|hitout|hitouts|clearance|clearances|"
    r"inside.?50|rebound.?50|contested|uncontested|clanger|clangers|"
    r"free.?kick|one.?percenter|bounces?|fantasy.?points?|"
    r"win|wins|loss|losses|draw|draws|score|scores|scoring|"
    r"played|game|games|match|matches|last.?night|yesterday|today|"
    r"ladder|premiership|flag|wooden spoon|percentage|"
    r"player|team|club|match|game|quarter|half.?time|"
    r"captain|coach|debut|traded?|draft|"
    r"mcg|marvel|gabba|scg|optus|adelaide oval|"
    r"stat|stats|statistics|average|total|record|"
    r"top\s?\d+|best|worst|most|least|highest|lowest|compare|comparison|"
    r"trend|over time|year by year|historical|performance|"
    r"bye|byes|home|away|attendance|venue|stadium|"
    r"news|latest|current|happening|update|updates)\b",
    re.IGNORECASE
)

# Team names and common nicknames for quick detection
from app.analytics.entity_resolver import EntityResolver as _ER
_ALL_TEAM_VARIATIONS = set()
for _variations in _ER.TEAM_NICKNAMES.values():
    for _v in _variations:
        _ALL_TEAM_VARIATIONS.add(_v.lower())

def _get_off_topic_response():
    """Generate dynamic off-topic response with current data range."""
    from app.data.database import get_data_recency
    recency = get_data_recency()
    earliest = recency["earliest_season"]
    hist_season = recency["historical_latest_season"]
    return (
        f"That doesn't seem to be an AFL question. I can help with Australian Football League "
        f"statistics and data from {earliest} to {hist_season}, including match results, player stats, "
        f"team performance, betting odds, and tipping predictions.\n\n"
        f"Try something like: \"How many goals did Hawkins kick in 2024?\" or "
        f"\"What are the odds for this week's games?\""
    )


def _is_off_topic(query: str) -> bool:
    """Return True if the query is clearly not AFL-related."""
    q_lower = query.strip().lower()

    # Short queries (1-3 words) that are greetings or generic — let them through
    # to get a friendly redirect from the LLM
    words = q_lower.split()
    if len(words) <= 2:
        logger.debug(f"OFF-TOPIC CHECK: Short query ({len(words)} words) - allowing through: {q_lower[:50]}")
        return False

    # Check for AFL keywords
    kw_match = _AFL_KEYWORDS.search(q_lower)
    if kw_match:
        logger.debug(f"OFF-TOPIC CHECK: Found AFL keyword '{kw_match.group()}' in: {q_lower[:50]}")
        return False

    # Check for team names / nicknames in query
    for team_var in _ALL_TEAM_VARIATIONS:
        if team_var in q_lower:
            logger.debug(f"OFF-TOPIC CHECK: Found team '{team_var}' in: {q_lower[:50]}")
            return False

    # Check for player-like patterns (capitalized words that could be surnames)
    # Don't filter these — they might be player name queries
    # e.g. "Cripps 2024" has no AFL keyword but is valid
    if re.search(r'\b(19|20)\d{2}\b', q_lower):
        logger.debug(f"OFF-TOPIC CHECK: Found year pattern in: {q_lower[:50]}")
        return False

    # No AFL signals found — likely off-topic
    logger.info(f"OFF-TOPIC CHECK: No AFL signals found in query: {q_lower[:80]}")
    return True


@dataclass
class QueryPattern:
    """A fast-path query pattern with SQL template and response formatter."""
    name: str
    regex: re.Pattern
    sql_template: str
    response_formatter: Callable  # fn(df) -> str
    requires_team: bool = False
    requires_season: bool = True


class FastPathRouter:
    """
    Pre-pipeline router for simple AFL queries.

    Usage:
        result = FastPathRouter.try_fast_path(user_query, conversation_history)
        if result is not None:
            return result  # Skip the full pipeline
        # else: run full LangGraph pipeline
    """

    # ── SQL Templates ──────────────────────────────────────────────────────────

    _GF_WINNER_SQL = """
        SELECT
            CASE WHEN m.home_score > m.away_score THEN ht.name ELSE at.name END AS winner,
            CASE WHEN m.home_score > m.away_score THEN at.name ELSE ht.name END AS loser,
            GREATEST(m.home_score, m.away_score) AS winning_score,
            LEAST(m.home_score, m.away_score) AS losing_score,
            m.home_score,
            m.away_score,
            ht.name AS home_team,
            at.name AS away_team
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        WHERE m.season = {year} AND m.round = 'Grand Final'
        LIMIT 1
    """

    _TEAM_RECORD_SQL = """
        SELECT
            t.name AS team,
            SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score > m.away_score)
                       OR (m.away_team_id = t.id AND m.away_score > m.home_score)
                     THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score < m.away_score)
                       OR (m.away_team_id = t.id AND m.away_score < m.home_score)
                     THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN m.home_score = m.away_score THEN 1 ELSE 0 END) AS draws,
            COUNT(*) AS total_matches,
            ROUND(AVG(
                CASE WHEN m.home_team_id = t.id
                     THEN m.home_score - m.away_score
                     ELSE m.away_score - m.home_score END
            ), 1) AS avg_margin
        FROM matches m
        JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
        WHERE t.name = '{team}' AND m.season = {year}
        GROUP BY t.name
    """

    _TOP_GOALS_SQL = """
        SELECT p.name, SUM(ps.goals) AS total_goals, t.name AS team
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams t ON ps.team_id = t.id
        WHERE m.season = {year} AND ps.goals IS NOT NULL
        GROUP BY p.name, t.name
        ORDER BY total_goals DESC NULLS LAST
        LIMIT 5
    """

    _TOP_DISPOSALS_SQL = """
        SELECT p.name, SUM(ps.disposals) AS total_disposals, t.name AS team
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams t ON ps.team_id = t.id
        WHERE m.season = {year} AND ps.disposals IS NOT NULL
        GROUP BY p.name, t.name
        ORDER BY total_disposals DESC NULLS LAST
        LIMIT 5
    """

    # AFL Fantasy scoring (official): Kick×3, Handball×2, Mark×3, Tackle×4, Goal×6,
    # Behind×1, Hitout×1, Free for×1, Free against×−3
    _AFL_FANTASY_SQL = """
        SELECT
            p.name,
            t.name AS team,
            ROUND(AVG(
                COALESCE(ps.kicks, 0) * 3 +
                COALESCE(ps.handballs, 0) * 2 +
                COALESCE(ps.marks, 0) * 3 +
                COALESCE(ps.tackles, 0) * 4 +
                COALESCE(ps.goals, 0) * 6 +
                COALESCE(ps.behinds, 0) * 1 +
                COALESCE(ps.hitouts, 0) * 1 +
                COALESCE(ps.free_kicks_for, 0) * 1 +
                COALESCE(ps.free_kicks_against, 0) * -3
            ), 1) AS avg_fantasy,
            SUM(
                COALESCE(ps.kicks, 0) * 3 +
                COALESCE(ps.handballs, 0) * 2 +
                COALESCE(ps.marks, 0) * 3 +
                COALESCE(ps.tackles, 0) * 4 +
                COALESCE(ps.goals, 0) * 6 +
                COALESCE(ps.behinds, 0) * 1 +
                COALESCE(ps.hitouts, 0) * 1 +
                COALESCE(ps.free_kicks_for, 0) * 1 +
                COALESCE(ps.free_kicks_against, 0) * -3
            ) AS total_fantasy,
            COUNT(*) AS games_played
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams t ON ps.team_id = t.id
        WHERE m.season = {year}
        GROUP BY p.name, t.name
        HAVING COUNT(*) >= 5
        ORDER BY avg_fantasy DESC NULLS LAST
        LIMIT 5
    """

    _BROWNLOW_SQL = """
        SELECT p.name, SUM(ps.brownlow_votes) AS total_votes, t.name AS team
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams t ON ps.team_id = t.id
        WHERE m.season = {year} AND ps.brownlow_votes IS NOT NULL AND ps.brownlow_votes > 0
        GROUP BY p.name, t.name
        ORDER BY total_votes DESC NULLS LAST
        LIMIT 1
    """

    _PLAYER_SEASON_STATS_SQL = """
        SELECT p.name, t.name AS team,
               COUNT(*) AS games,
               SUM(ps.goals) AS goals,
               SUM(ps.disposals) AS disposals,
               SUM(ps.kicks) AS kicks,
               SUM(ps.handballs) AS handballs,
               SUM(ps.marks) AS marks,
               SUM(ps.tackles) AS tackles,
               ROUND(AVG(ps.disposals), 1) AS avg_disposals,
               ROUND(AVG(ps.goals), 1) AS avg_goals
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams t ON ps.team_id = t.id
        WHERE LOWER(p.name) LIKE LOWER('%{player}%') AND m.season = {year}
        GROUP BY p.name, t.name
    """

    _TEAM_LADDER_SQL = """
        SELECT t.name AS team,
               SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score > m.away_score)
                          OR (m.away_team_id = t.id AND m.away_score > m.home_score)
                        THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score < m.away_score)
                          OR (m.away_team_id = t.id AND m.away_score < m.home_score)
                        THEN 1 ELSE 0 END) AS losses,
               COUNT(*) AS games,
               SUM(CASE WHEN m.home_team_id = t.id THEN m.home_score - m.away_score
                        ELSE m.away_score - m.home_score END) AS points_diff
        FROM matches m
        JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
        WHERE m.season = {year}
        GROUP BY t.name
        ORDER BY wins DESC, points_diff DESC
    """

    _HEAD_TO_HEAD_SQL = """
        SELECT ht.name AS home_team, at.name AS away_team,
               m.home_score, m.away_score, m.round, m.venue
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        WHERE m.season = {year}
          AND ((ht.name = '{team1}' AND at.name = '{team2}')
               OR (ht.name = '{team2}' AND at.name = '{team1}'))
        ORDER BY m.match_date
    """

    # Bye round queries — find rounds where a team has no match
    _TEAM_BYE_ROUNDS_SQL = """
        SELECT DISTINCT m2.round
        FROM matches m2
        WHERE m2.season = {year}
          AND m2.round ~ '^[0-9]+$'
          AND m2.round NOT IN (
              SELECT m.round FROM matches m
              JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
              WHERE m.season = {year} AND t.name = '{team}'
          )
        ORDER BY CAST(m2.round AS INTEGER)
    """

    _ROUND_BYES_SQL = """
        SELECT t.name AS team
        FROM teams t
        WHERE t.id NOT IN (
            SELECT m.home_team_id FROM matches m
            WHERE m.season = {year} AND m.round = '{round}'
            UNION
            SELECT m.away_team_id FROM matches m
            WHERE m.season = {year} AND m.round = '{round}'
        )
        AND t.id IN (
            SELECT m.home_team_id FROM matches m WHERE m.season = {year}
            UNION
            SELECT m.away_team_id FROM matches m WHERE m.season = {year}
        )
        ORDER BY t.name
    """

    _HIGHEST_SCORE_SQL = """
        SELECT ht.name AS home_team, at.name AS away_team,
               m.home_score, m.away_score,
               GREATEST(m.home_score, m.away_score) AS highest_score,
               ABS(m.home_score - m.away_score) AS margin,
               m.round, m.venue
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        WHERE m.season = {year}
        ORDER BY highest_score DESC NULLS LAST
        LIMIT 1
    """

    # ── Response formatters ────────────────────────────────────────────────────

    @staticmethod
    def _fmt_gf_winner(df, year: int, **_) -> str:
        if df is None or len(df) == 0:
            return None
        row = df.iloc[0]
        home, away = row["home_team"], row["away_team"]
        hs, aws = int(row["home_score"]), int(row["away_score"])
        if hs == aws:
            return (f"The {year} AFL Grand Final between {home} and {away} "
                    f"ended in a draw ({hs} points each). A replay was held.")
        winner, loser = str(row["winner"]), str(row["loser"])
        ws, ls = int(row["winning_score"]), int(row["losing_score"])
        return f"{winner} won the {year} AFL Grand Final, defeating {loser} {ws} to {ls}."

    @staticmethod
    def _fmt_team_record(df, team: str, year: int, **_) -> str:
        if df is None or len(df) == 0:
            return None
        row = df.iloc[0]
        wins, losses, draws = int(row["wins"]), int(row["losses"]), int(row["draws"])
        total, margin = int(row["total_matches"]), float(row["avg_margin"])
        record = f"{wins} wins, {losses} losses"
        if draws:
            record += f", {draws} {'draw' if draws == 1 else 'draws'}"
        direction = "ahead" if margin >= 0 else "behind"
        margin_abs = abs(margin)
        return (f"{team} finished the {year} season with {record} "
                f"from {total} games (average margin: {margin_abs:.1f} points {direction}).")

    @staticmethod
    def _fmt_top_goals(df, year: int, **_) -> str:
        if df is None or len(df) == 0:
            return None
        lines = []
        for i, row in df.iterrows():
            lines.append(f"{i+1}. {row['name']} ({row['team']}) — {int(row['total_goals'])} goals")
        return f"Top goal kickers in {year}:\n" + "\n".join(lines)

    @staticmethod
    def _fmt_top_disposals(df, year: int, **_) -> str:
        if df is None or len(df) == 0:
            return None
        lines = []
        for i, row in df.iterrows():
            lines.append(f"{i+1}. {row['name']} ({row['team']}) — {int(row['total_disposals'])} disposals")
        return f"Top disposal getters in {year}:\n" + "\n".join(lines)

    @staticmethod
    def _fmt_afl_fantasy(df, year: int, **_) -> str:
        if df is None or len(df) == 0:
            return None
        lines = []
        for i, row in df.iterrows():
            avg = float(row["avg_fantasy"])
            games = int(row["games_played"])
            lines.append(
                f"{i+1}. {row['name']} ({row['team']}) — {avg:.1f} avg fantasy pts ({games} games)"
            )
        return (
            f"Top AFL Fantasy scorers in {year} (avg pts per game, min. 5 games):\n"
            + "\n".join(lines)
        )

    @staticmethod
    def _fmt_brownlow(df, year: int, **_) -> str:
        if df is None or len(df) == 0:
            return None
        row = df.iloc[0]
        return (f"{row['name']} ({row['team']}) won the {year} Brownlow Medal "
                f"with {int(row['total_votes'])} votes.")

    @staticmethod
    def _fmt_player_season_stats(df, year: int, player: str = "", **_) -> str:
        if df is None or len(df) == 0:
            return None
        if len(df) > 1:
            # Multiple players matched — fall through for disambiguation
            return None
        row = df.iloc[0]
        name = row["name"]
        team = row["team"]
        games = int(row["games"])
        goals = int(row["goals"]) if row["goals"] else 0
        disposals = int(row["disposals"]) if row["disposals"] else 0
        avg_disp = float(row["avg_disposals"]) if row["avg_disposals"] else 0
        marks = int(row["marks"]) if row["marks"] else 0
        tackles = int(row["tackles"]) if row["tackles"] else 0
        return (
            f"{name} ({team}) in {year}: {games} games, "
            f"{disposals} disposals (avg {avg_disp:.1f}/game), "
            f"{goals} goals, {marks} marks, {tackles} tackles."
        )

    @staticmethod
    def _fmt_team_bye_rounds(df, year: int, team: str = "", **_) -> str:
        if df is None or len(df) == 0:
            return f"{team} did not have any bye rounds in {year}."
        rounds = [str(row["round"]) for _, row in df.iterrows()]
        if len(rounds) == 1:
            return f"{team} had a bye in Round {rounds[0]} in {year}."
        return f"{team} had byes in Rounds {', '.join(rounds)} in {year}."

    @staticmethod
    def _fmt_round_byes(df, year: int, round: str = "", **_) -> str:
        if df is None or len(df) == 0:
            return f"No teams had a bye in Round {round} of {year}."
        teams = [str(row["team"]) for _, row in df.iterrows()]
        if len(teams) == 1:
            return f"{teams[0]} had the bye in Round {round} of {year}."
        return f"Teams with a bye in Round {round} of {year}: {', '.join(teams)}."

    @staticmethod
    def _fmt_team_ladder(df, year: int, team: str = "", **_) -> str:
        if df is None or len(df) == 0:
            return None
        # Find the requested team's rank
        if team:
            for i, (_, row) in enumerate(df.iterrows()):
                if row["team"].lower() == team.lower():
                    wins = int(row["wins"])
                    losses = int(row["losses"])
                    games = int(row["games"])
                    diff = int(row["points_diff"])
                    position = i + 1
                    suffix = {1: "st", 2: "nd", 3: "rd"}.get(position if position < 20 else position % 10, "th")
                    return (
                        f"{team} finished {position}{suffix} on the {year} ladder with "
                        f"{wins} wins, {losses} losses from {games} games "
                        f"(percentage diff: {diff:+d} points)."
                    )
            return None
        # No specific team — show top 8
        lines = []
        for i, (_, row) in enumerate(df.head(8).iterrows()):
            lines.append(
                f"{i+1}. {row['team']} — {int(row['wins'])} wins, "
                f"{int(row['losses'])} losses"
            )
        return f"{year} AFL Ladder (Top 8):\n" + "\n".join(lines)

    @staticmethod
    def _fmt_head_to_head(df, year: int, team1: str = "", team2: str = "", **_) -> str:
        if df is None or len(df) == 0:
            return None
        lines = []
        for _, row in df.iterrows():
            home = row["home_team"]
            away = row["away_team"]
            hs, aws = int(row["home_score"]), int(row["away_score"])
            rd = row["round"]
            winner = home if hs > aws else away if aws > hs else "Draw"
            margin = abs(hs - aws)
            if winner == "Draw":
                lines.append(f"Round {rd}: {home} {hs} drew with {away} {aws}")
            else:
                loser = away if winner == home else home
                lines.append(f"Round {rd}: {winner} def. {loser} by {margin} pts ({hs}-{aws})")
        header = f"{team1} vs {team2} in {year}:"
        return header + "\n" + "\n".join(lines)

    @staticmethod
    def _fmt_highest_score(df, year: int, **_) -> str:
        if df is None or len(df) == 0:
            return None
        row = df.iloc[0]
        home = row["home_team"]
        away = row["away_team"]
        hs, aws = int(row["home_score"]), int(row["away_score"])
        high = int(row["highest_score"])
        margin = int(row["margin"])
        rd = row["round"]
        winner = home if hs >= aws else away
        loser = away if winner == home else home
        return (
            f"The highest score in {year} was {high} points by {winner} against {loser} "
            f"in Round {rd} ({hs}-{aws}, winning by {margin} points)."
        )

    # ── Pattern registry ───────────────────────────────────────────────────────

    # Built lazily on first use
    _PATTERNS: Optional[List[QueryPattern]] = None

    @classmethod
    def _build_patterns(cls) -> List[QueryPattern]:
        return [
            # Grand Final winner — "who won the GF in 2022" / "2022 grand final winner"
            QueryPattern(
                name="grand_final_winner",
                regex=re.compile(
                    r"(?:who\s+won|winner\s+of|who\s+won\s+the|result\s+of(?:\s+the)?)"
                    r"(?:\s+the)?\s*(?:gf|grand\s+final|granny|premiership)"
                    r"(?:\s+in)?\s*(\d{4})"
                    r"|(\d{4})\s*(?:gf|grand\s+final|granny|premiership)\s*(?:winner|result|score)?",
                    re.IGNORECASE
                ),
                sql_template=cls._GF_WINNER_SQL,
                response_formatter=cls._fmt_gf_winner,
                requires_team=False,
                requires_season=True,
            ),

            # Team season record — "how many wins did Geelong have in 2023" / "Geelong's record in 2023"
            QueryPattern(
                name="team_season_record",
                regex=re.compile(
                    r"(?:how\s+many\s+(?:wins|losses|games)|(?:win[s]?|loss(?:es)?)\s+record|"
                    r"record|season\s+record|how\s+did\s+.+?\s+(?:go|do|perform))\b"
                    r".{0,40}?(\d{4})",
                    re.IGNORECASE
                ),
                sql_template=cls._TEAM_RECORD_SQL,
                response_formatter=cls._fmt_team_record,
                requires_team=True,
                requires_season=True,
            ),

            # Top goal kicker — "top goal scorer in 2024" / "most goals kicked in 2023"
            QueryPattern(
                name="top_goal_kickers",
                regex=re.compile(
                    r"(?:who\s+kicked|top\s+goal\s+(?:kicker|scorer|scorer)s?|"
                    r"most\s+goals?\s+(?:kicked|scored|in)|leading\s+goal\s+kicker)"
                    r".{0,20}?(\d{4})"
                    r"|(\d{4}).{0,20}?(?:top\s+goal|most\s+goals?|leading\s+goal)",
                    re.IGNORECASE
                ),
                sql_template=cls._TOP_GOALS_SQL,
                response_formatter=cls._fmt_top_goals,
                requires_team=False,
                requires_season=True,
            ),

            # Top disposal getter
            QueryPattern(
                name="top_disposal_getters",
                regex=re.compile(
                    r"(?:who\s+(?:had|got|averaged)|top|most|leading)\s+"
                    r"(?:the\s+)?(?:most\s+)?disposals?"
                    r".{0,20}?(\d{4})"
                    r"|(\d{4}).{0,20}?(?:most|top|leading)\s+disposals?",
                    re.IGNORECASE
                ),
                sql_template=cls._TOP_DISPOSALS_SQL,
                response_formatter=cls._fmt_top_disposals,
                requires_team=False,
                requires_season=True,
            ),

            # AFL Fantasy top scorers — "top fantasy scorer in 2024" / "who had the most fantasy points in 2023"
            QueryPattern(
                name="afl_fantasy_top_scorers",
                regex=re.compile(
                    r"(?:top|best|highest|most|who\s+(?:had|scored|averaged?)(?:\s+the)?)"
                    r"(?:\s+afl)?\s*fantasy(?:\s+(?:scorer|score|points?|pts|player))?"
                    r".{0,20}?(\d{4})"
                    r"|(\d{4}).{0,20}?(?:top|best|highest|most)\s+(?:afl\s+)?fantasy",
                    re.IGNORECASE
                ),
                sql_template=cls._AFL_FANTASY_SQL,
                response_formatter=cls._fmt_afl_fantasy,
                requires_team=False,
                requires_season=True,
            ),

            # Brownlow Medal — "who won the brownlow in 2024"
            QueryPattern(
                name="brownlow_winner",
                regex=re.compile(
                    r"(?:who\s+won|winner\s+of(?:\s+the)?)\s+(?:the\s+)?brownlow"
                    r"(?:\s+medal)?(?:\s+in)?\s*(\d{4})"
                    r"|(\d{4})\s*brownlow(?:\s+medal)?\s*(?:winner|medallist)?",
                    re.IGNORECASE
                ),
                sql_template=cls._BROWNLOW_SQL,
                response_formatter=cls._fmt_brownlow,
                requires_team=False,
                requires_season=True,
            ),

            # Player season stats — "Cripps stats 2024" / "How did Dangerfield go in 2023"
            QueryPattern(
                name="player_season_stats",
                regex=re.compile(
                    r"(?:(.+?)(?:'s|s)\s+(?:stats?|statistics|season|numbers)|"
                    r"(?:how\s+(?:did|was)\s+(.+?)\s+(?:go|perform)(?:\s+in)?)|"
                    r"(?:stats?\s+(?:for|of)\s+(.+?)))"
                    r"\s*(?:in\s+)?(\d{4})",
                    re.IGNORECASE
                ),
                sql_template=cls._PLAYER_SEASON_STATS_SQL,
                response_formatter=cls._fmt_player_season_stats,
                requires_team=False,
                requires_season=True,
            ),

            # Team ladder position — "Where did Richmond finish in 2023"
            QueryPattern(
                name="team_ladder_position",
                regex=re.compile(
                    r"(?:where\s+did\s+.+?\s+finish|"
                    r"(?:ladder|standings?|final\s+(?:position|standing))|"
                    r".+?\s+(?:ladder|finish)\s+(?:position|in))"
                    r"\s*(?:in\s+)?(\d{4})"
                    r"|(\d{4})\s*(?:ladder|standings?|final\s+standings?)",
                    re.IGNORECASE
                ),
                sql_template=cls._TEAM_LADDER_SQL,
                response_formatter=cls._fmt_team_ladder,
                requires_team=True,
                requires_season=True,
            ),

            # Team bye rounds — "when is Geelong's bye in 2025" / "did Carlton have a bye in 2024"
            QueryPattern(
                name="team_bye_rounds",
                regex=re.compile(
                    r"(?:when\s+(?:is|was|are)|did\s+.+?\s+have|does\s+.+?\s+have|"
                    r".+?(?:'s|s)\s+bye)"
                    r".*?\bbye\b"
                    r".*?(\d{4})"
                    r"|(\d{4}).*?\bbye\b",
                    re.IGNORECASE
                ),
                sql_template=cls._TEAM_BYE_ROUNDS_SQL,
                response_formatter=cls._fmt_team_bye_rounds,
                requires_team=True,
                requires_season=True,
            ),

            # Round byes — "which teams have a bye in round 13 2025"
            QueryPattern(
                name="round_byes",
                regex=re.compile(
                    r"(?:which|what)\s+teams?\s+(?:have|had|has|get|got)\s+(?:a\s+|the\s+)?bye"
                    r".*?(?:round|r)\s*(\d{1,2})"
                    r".*?(\d{4})",
                    re.IGNORECASE
                ),
                sql_template=cls._ROUND_BYES_SQL,
                response_formatter=cls._fmt_round_byes,
                requires_team=False,
                requires_season=True,
            ),

            # Highest score — "highest score in 2024" / "biggest win in 2023"
            QueryPattern(
                name="highest_score",
                regex=re.compile(
                    r"(?:highest|biggest|largest|record)\s+(?:score|win|margin|total)"
                    r"(?:\s+in)?\s*(\d{4})"
                    r"|(\d{4}).{0,20}?(?:highest|biggest|largest|record)\s+(?:score|win|margin)",
                    re.IGNORECASE
                ),
                sql_template=cls._HIGHEST_SCORE_SQL,
                response_formatter=cls._fmt_highest_score,
                requires_team=False,
                requires_season=True,
            ),
        ]

    @classmethod
    def _get_patterns(cls) -> List[QueryPattern]:
        if cls._PATTERNS is None:
            cls._PATTERNS = cls._build_patterns()
        return cls._PATTERNS

    # ── Team extraction helper ─────────────────────────────────────────────────

    @classmethod
    def _extract_team(cls, query: str) -> Optional[str]:
        """
        Find an AFL team name in the query text using EntityResolver.
        Returns canonical team name or None.
        """
        from app.analytics.entity_resolver import EntityResolver
        # Try progressively shorter substrings to find team mentions
        words = query.split()
        # Try 3-word, 2-word, 1-word sequences
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                chunk = " ".join(words[i:i+n])
                resolved = EntityResolver.resolve_team(chunk)
                if resolved:
                    return resolved
        return None

    @classmethod
    def _extract_player_name(cls, query: str) -> Optional[str]:
        """
        Extract a player surname from the query for fast-path patterns.
        Returns the raw name string for SQL ILIKE matching, or None.
        """
        # Common AFL stop words to exclude
        stop_words = {
            'how', 'did', 'was', 'what', 'who', 'where', 'when', 'the', 'in',
            'for', 'of', 'and', 'top', 'best', 'most', 'stats', 'statistics',
            'season', 'go', 'perform', 'goals', 'disposals', 'marks', 'tackles',
            'kicks', 'handballs', 'numbers', 'afl', 'record', 'average', 'total'
        }
        # Try to find capitalized words that aren't stop words or team names
        words = re.findall(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b', query)
        candidates = []
        for w in words:
            if w.lower() in stop_words:
                continue
            # Check if it's a team name
            if cls._extract_team(w) is not None:
                continue
            candidates.append(w)
        return candidates[0] if len(candidates) == 1 else None

    @classmethod
    def _is_followup(cls, query: str) -> bool:
        """Return True if query looks like a follow-up to a previous message."""
        return bool(_FOLLOWUP_PATTERNS.search(query))

    @classmethod
    def _is_range_query(cls, query: str) -> bool:
        """Return True if query spans multiple seasons (e.g. '2010 to 2020')."""
        years = re.findall(r'\b(19|20)\d{2}\b', query)
        return len(years) >= 2

    @classmethod
    def _validate_year(cls, year_str: str) -> Optional[int]:
        """Validate and return year as int, or None if out of range."""
        try:
            year = int(year_str)
            if 1990 <= year <= 2026:
                return year
        except (ValueError, TypeError):
            pass
        return None

    # ── Main entry point ───────────────────────────────────────────────────────

    @classmethod
    def try_fast_path(
        cls,
        user_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        socketio_emit=None,
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to answer query via fast-path (no LLM calls).

        Returns an AgentState-compatible dict on success, or None to fall
        through to the full LangGraph pipeline.
        """
        from app.agent.state import QueryIntent, WorkflowStep
        from app.agent.tools import DatabaseTool
        from app.utils.cache import get_cached_result, set_cached_result

        # Off-topic detection — reject clearly non-AFL queries immediately
        # BUT: If there's conversation history, the query might be a follow-up
        # that doesn't contain AFL keywords (e.g., "Who came second?" after asking about Grand Final)
        # In that case, fall through to the full pipeline which has conversation context
        if _is_off_topic(user_query):
            if conversation_history and len(conversation_history) >= 2:
                # There's conversation history - this might be a contextual follow-up
                # Fall through to the full pipeline which can use conversation context
                logger.info(f"FAST-PATH: Query looks off-topic but has conversation history, falling through: {user_query[:80]}")
                return None

            logger.info(f"FAST-PATH: Off-topic query rejected: {user_query[:80]}")
            return {
                "user_query": user_query,
                "intent": QueryIntent.SIMPLE_STAT,
                "entities": {},
                "needs_clarification": False,
                "clarification_question": None,
                "analysis_plan": ["Off-topic detection"],
                "requires_visualization": False,
                "chart_type": None,
                "fallback_approach": None,
                "analysis_mode": "summary",
                "analysis_types": [],
                "context_insights": {},
                "data_quality": {},
                "stats_summary": {},
                "sql_query": None,
                "sql_validated": False,
                "query_results": None,
                "statistical_analysis": {},
                "execution_error": None,
                "visualization_spec": None,
                "natural_language_summary": _get_off_topic_response(),
                "confidence": 1.0,
                "sources": [],
                "current_step": WorkflowStep.RESPOND,
                "thinking_message": "Done",
                "errors": [],
                "socketio_emit": socketio_emit,
                "conversation_history": conversation_history or [],
                "conversation_id": None,
            }

        # Skip if query looks like a follow-up or spans multiple seasons
        if cls._is_followup(user_query):
            logger.debug(f"FAST-PATH: Skipping follow-up query: {user_query[:60]}")
            return None
        if cls._is_range_query(user_query):
            logger.debug(f"FAST-PATH: Skipping multi-season range query: {user_query[:60]}")
            return None

        patterns = cls._get_patterns()

        for pattern in patterns:
            match = pattern.regex.search(user_query)
            if not match:
                continue

            logger.info(f"FAST-PATH: Pattern '{pattern.name}' matched: {user_query[:80]}")

            # Extract year from whichever capture group matched
            year_str = next((g for g in match.groups() if g and g.isdigit() and len(g) == 4), None)
            if not year_str:
                logger.debug(f"FAST-PATH: No year found in match groups {match.groups()}")
                continue

            year = cls._validate_year(year_str)
            if year is None:
                logger.debug(f"FAST-PATH: Year {year_str} out of valid range")
                continue

            # Extract team if required
            team = None
            if pattern.requires_team:
                team = cls._extract_team(user_query)
                if team is None:
                    logger.debug(f"FAST-PATH: Pattern '{pattern.name}' requires team but none found")
                    continue  # Try next pattern

            # Extract round number for round_byes pattern
            round_num = None
            if pattern.name == "round_byes":
                # Group 1 is round number, group 2 is year
                round_num = match.group(1)
                if not round_num:
                    logger.debug(f"FAST-PATH: round_byes requires round but none found")
                    continue

            # Extract player if needed (for player_season_stats pattern)
            player = None
            if pattern.name == "player_season_stats":
                # Try to get player name from regex capture groups (groups 1-3 are player name)
                player = next((g for g in match.groups()[:3] if g and not g.isdigit()), None)
                if player:
                    player = player.strip()
                else:
                    player = cls._extract_player_name(user_query)
                if not player:
                    logger.debug(f"FAST-PATH: player_season_stats requires player but none found")
                    continue

            # Emit progress to WebSocket
            if socketio_emit:
                socketio_emit("thinking", {
                    "step": "Looking up AFL data...",
                    "current_step": "execute"
                })

            # Build and execute SQL
            try:
                sql = pattern.sql_template.format(
                    year=year, team=team or "", player=player or "",
                    round=round_num or ""
                )
                sql = " ".join(sql.split())  # Normalise whitespace

                # Check cache first
                df = get_cached_result(sql)
                if df is not None:
                    logger.info(f"FAST-PATH: Cache hit for '{pattern.name}'")
                else:
                    db_result = DatabaseTool.query_database(sql)
                    if not db_result.get("success") or db_result.get("data") is None:
                        logger.warning(f"FAST-PATH: DB query failed for '{pattern.name}': {db_result.get('error')}")
                        return None
                    df = db_result["data"]
                    if len(df) > 0:
                        set_cached_result(sql, df)

                if df is None or len(df) == 0:
                    # Bye queries can legitimately return 0 rows (no byes)
                    if pattern.name in ("team_bye_rounds", "round_byes"):
                        import pandas as pd
                        df = pd.DataFrame()
                    else:
                        logger.info(f"FAST-PATH: Empty result for '{pattern.name}', falling through")
                        return None

                # Format response
                fmt_kwargs = {"year": year, "team": team, "player": player, "round": round_num}
                response_text = pattern.response_formatter(df, **fmt_kwargs)

                if response_text is None:
                    logger.info(f"FAST-PATH: Formatter returned None for '{pattern.name}', falling through")
                    return None

                logger.info(f"FAST-PATH: Successfully answered via '{pattern.name}': {response_text[:80]}")

                # Build AgentState-compatible result
                entities: Dict[str, Any] = {
                    "teams": [team] if team else [],
                    "players": [],
                    "seasons": [str(year)],
                    "metrics": [],
                    "rounds": [],
                }

                return {
                    "user_query": user_query,
                    "intent": QueryIntent.SIMPLE_STAT,
                    "entities": entities,
                    "needs_clarification": False,
                    "clarification_question": None,
                    "analysis_plan": [f"Fast-path: {pattern.name}"],
                    "requires_visualization": False,
                    "chart_type": None,
                    "fallback_approach": None,
                    "analysis_mode": "summary",
                    "analysis_types": [],
                    "context_insights": {},
                    "data_quality": {},
                    "stats_summary": {},
                    "sql_query": sql,
                    "sql_validated": True,
                    "query_results": df,
                    "statistical_analysis": {},
                    "execution_error": None,
                    "visualization_spec": None,
                    "natural_language_summary": response_text,
                    "confidence": 0.95,
                    "sources": ["AFL Tables"],
                    "current_step": WorkflowStep.RESPOND,
                    "thinking_message": "Done",
                    "errors": [],
                    "socketio_emit": socketio_emit,
                    "conversation_history": conversation_history or [],
                    "conversation_id": None,  # Set by caller
                }

            except Exception as e:
                logger.warning(f"FAST-PATH: Error in '{pattern.name}': {e}")
                return None  # Fall through to full pipeline

        logger.debug(f"FAST-PATH: No pattern matched for: {user_query[:80]}")
        return None
