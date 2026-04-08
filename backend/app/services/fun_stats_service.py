"""
Fun Stats Service — returns 2-3 surprising stats about a team.

Pure SQL queries, no LLM calls. Results are cached for 24 hours.
Used for first-interaction greeting when a user selects a team.
"""
import time
import logging
from sqlalchemy import text
from app.data.database import get_session

logger = logging.getLogger(__name__)

_fun_stats_cache = {}
_CACHE_TTL = 86400  # 24 hours


def get_fun_stats(team_name: str) -> list[dict]:
    """
    Return 2-3 surprising/fun stats about a team.

    Each stat is a dict with:
        - headline: punchy one-liner (e.g. "Biggest win: 128-point demolition of Fremantle")
        - detail: extra context (e.g. "Round 5, 2019 at the MCG")
        - stat_type: category key (e.g. "biggest_win", "goal_record", etc.)

    Args:
        team_name: Canonical team name (e.g. "Richmond")

    Returns:
        List of 2-3 stat dicts, ranked by impressiveness.
    """
    now = time.time()
    cache_key = team_name.lower()
    if cache_key in _fun_stats_cache and (now - _fun_stats_cache[cache_key]["ts"]) < _CACHE_TTL:
        return _fun_stats_cache[cache_key]["data"]

    try:
        stats = _compute_fun_stats(team_name)
    except Exception as e:
        logger.error(f"Failed to compute fun stats for {team_name}: {e}")
        stats = []

    _fun_stats_cache[cache_key] = {"data": stats, "ts": now}
    return stats


def _compute_fun_stats(team_name: str) -> list[dict]:
    """Run all stat queries and return top 2-3 by impressiveness."""
    with get_session() as session:
        # Resolve team_id
        row = session.execute(
            text("SELECT id FROM teams WHERE name = :name"),
            {"name": team_name}
        ).fetchone()
        if not row:
            logger.warning(f"Team not found in DB: {team_name}")
            return []
        team_id = row[0]

        candidates = []

        # 1. Biggest win
        stat = _biggest_win(session, team_id)
        if stat:
            candidates.append(stat)

        # 2. Individual goal record
        stat = _goal_record(session, team_id)
        if stat:
            candidates.append(stat)

        # 3. Longest winning streak
        stat = _longest_winning_streak(session, team_id)
        if stat:
            candidates.append(stat)

        # 4. Biggest comeback
        stat = _biggest_comeback(session, team_id)
        if stat:
            candidates.append(stat)

        # 5. Fantasy monster
        stat = _fantasy_monster(session, team_id)
        if stat:
            candidates.append(stat)

        # 6. Disposal king
        stat = _disposal_king(session, team_id)
        if stat:
            candidates.append(stat)

        # 7. Home fortress
        stat = _home_fortress(session, team_id)
        if stat:
            candidates.append(stat)

    # Normalize scores to 0-1 and pick top 3
    if not candidates:
        return []

    max_score = max(c["_raw_score"] for c in candidates)
    if max_score > 0:
        for c in candidates:
            c["_norm_score"] = c["_raw_score"] / max_score
    else:
        for c in candidates:
            c["_norm_score"] = 0

    candidates.sort(key=lambda c: c["_norm_score"], reverse=True)
    top = candidates[:3]

    # Strip internal scoring fields
    return [
        {"headline": s["headline"], "detail": s["detail"], "stat_type": s["stat_type"]}
        for s in top
    ]


def _biggest_win(session, team_id: int) -> dict | None:
    """Largest margin victory for the team."""
    row = session.execute(text("""
        SELECT
            ABS(m.home_score - m.away_score) AS margin,
            m.season, m.round, m.venue,
            CASE WHEN m.home_team_id = :tid THEN opp.name ELSE home_t.name END AS opponent,
            m.home_score, m.away_score,
            CASE WHEN m.home_team_id = :tid THEN m.home_score ELSE m.away_score END AS team_score,
            CASE WHEN m.home_team_id = :tid THEN m.away_score ELSE m.home_score END AS opp_score
        FROM matches m
        JOIN teams home_t ON m.home_team_id = home_t.id
        JOIN teams opp ON (
            CASE WHEN m.home_team_id = :tid THEN m.away_team_id ELSE m.home_team_id END = opp.id
        )
        WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
          AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
          AND (
              (m.home_team_id = :tid AND m.home_score > m.away_score)
              OR (m.away_team_id = :tid AND m.away_score > m.home_score)
          )
        ORDER BY ABS(m.home_score - m.away_score) DESC
        LIMIT 1
    """), {"tid": team_id}).fetchone()

    if not row:
        return None

    margin = row[0]
    season = row[1]
    rnd = row[2]
    opponent = row[4]
    team_score = row[7]
    opp_score = row[8]

    return {
        "headline": f"Biggest win: {margin}-point demolition of {opponent} ({team_score}-{opp_score})",
        "detail": f"Round {rnd}, {season}",
        "stat_type": "biggest_win",
        "_raw_score": margin / 100,  # 100-point win = 1.0
    }


def _goal_record(session, team_id: int) -> dict | None:
    """Most goals in a single game by a player on the team."""
    row = session.execute(text("""
        SELECT ps.goals, p.name, m.season, m.round,
               CASE WHEN m.home_team_id = :tid THEN opp.name ELSE home_t.name END AS opponent
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams home_t ON m.home_team_id = home_t.id
        JOIN teams opp ON (
            CASE WHEN m.home_team_id = :tid THEN m.away_team_id ELSE m.home_team_id END = opp.id
        )
        WHERE ps.team_id = :tid
          AND ps.goals IS NOT NULL AND ps.goals > 0
        ORDER BY ps.goals DESC
        LIMIT 1
    """), {"tid": team_id}).fetchone()

    if not row:
        return None

    goals = row[0]
    player = row[1]
    season = row[2]
    rnd = row[3]
    opponent = row[4]

    return {
        "headline": f"Individual goal record: {goals} goals by {player} vs {opponent}",
        "detail": f"Round {rnd}, {season}",
        "stat_type": "goal_record",
        "_raw_score": goals / 10,  # 10 goals = 1.0
    }


def _longest_winning_streak(session, team_id: int) -> dict | None:
    """Longest consecutive winning streak using window functions."""
    row = session.execute(text("""
        WITH team_matches AS (
            SELECT
                m.id, m.season, m.round, m.match_date,
                CASE
                    WHEN (m.home_team_id = :tid AND m.home_score > m.away_score)
                      OR (m.away_team_id = :tid AND m.away_score > m.home_score)
                    THEN 1 ELSE 0
                END AS won
            FROM matches m
            WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
              AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
              AND m.home_score > 0
            ORDER BY m.match_date
        ),
        streaks AS (
            SELECT *,
                   SUM(CASE WHEN won = 0 THEN 1 ELSE 0 END) OVER (ORDER BY match_date) AS grp
            FROM team_matches
        ),
        streak_lengths AS (
            SELECT grp, COUNT(*) AS streak_len,
                   MIN(season) AS start_season, MAX(season) AS end_season,
                   MIN(round) AS start_round, MAX(round) AS end_round
            FROM streaks
            WHERE won = 1
            GROUP BY grp
        )
        SELECT streak_len, start_season, end_season, start_round, end_round
        FROM streak_lengths
        ORDER BY streak_len DESC
        LIMIT 1
    """), {"tid": team_id}).fetchone()

    if not row:
        return None

    streak = row[0]
    start_season = row[1]
    end_season = row[2]

    if start_season == end_season:
        detail = f"During the {start_season} season"
    else:
        detail = f"From {start_season} to {end_season}"

    return {
        "headline": f"Longest winning streak: {streak} games in a row",
        "detail": detail,
        "stat_type": "winning_streak",
        "_raw_score": streak / 20,  # 20-game streak = 1.0
    }


def _biggest_comeback(session, team_id: int) -> dict | None:
    """Biggest halftime deficit that the team overcame to win."""
    row = session.execute(text("""
        SELECT
            deficit, season, round, opponent, venue
        FROM (
            SELECT
                CASE
                    WHEN m.home_team_id = :tid THEN
                        ((m.away_q1_goals + m.away_q2_goals) * 6 + m.away_q1_behinds + m.away_q2_behinds)
                        - ((m.home_q1_goals + m.home_q2_goals) * 6 + m.home_q1_behinds + m.home_q2_behinds)
                    ELSE
                        ((m.home_q1_goals + m.home_q2_goals) * 6 + m.home_q1_behinds + m.home_q2_behinds)
                        - ((m.away_q1_goals + m.away_q2_goals) * 6 + m.away_q1_behinds + m.away_q2_behinds)
                END AS deficit,
                m.season, m.round, m.venue,
                CASE WHEN m.home_team_id = :tid THEN opp.name ELSE home_t.name END AS opponent
            FROM matches m
            JOIN teams home_t ON m.home_team_id = home_t.id
            JOIN teams opp ON (
                CASE WHEN m.home_team_id = :tid THEN m.away_team_id ELSE m.home_team_id END = opp.id
            )
            WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
              AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
              AND m.home_q1_goals IS NOT NULL AND m.away_q1_goals IS NOT NULL
              AND m.home_q2_goals IS NOT NULL AND m.away_q2_goals IS NOT NULL
              AND (
                  (m.home_team_id = :tid AND m.home_score > m.away_score)
                  OR (m.away_team_id = :tid AND m.away_score > m.home_score)
              )
        ) sub
        WHERE deficit > 0
        ORDER BY deficit DESC
        LIMIT 1
    """), {"tid": team_id}).fetchone()

    if not row:
        return None

    deficit = row[0]
    season = row[1]
    rnd = row[2]
    opponent = row[3]

    return {
        "headline": f"Biggest comeback: overcame {deficit}-point halftime deficit vs {opponent}",
        "detail": f"Round {rnd}, {season}",
        "stat_type": "biggest_comeback",
        "_raw_score": deficit / 60,  # 60-point comeback = 1.0
    }


def _fantasy_monster(session, team_id: int) -> dict | None:
    """Highest fantasy_points game by a player on the team."""
    row = session.execute(text("""
        SELECT ps.fantasy_points, p.name, m.season, m.round,
               CASE WHEN m.home_team_id = :tid THEN opp.name ELSE home_t.name END AS opponent
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams home_t ON m.home_team_id = home_t.id
        JOIN teams opp ON (
            CASE WHEN m.home_team_id = :tid THEN m.away_team_id ELSE m.home_team_id END = opp.id
        )
        WHERE ps.team_id = :tid
          AND ps.fantasy_points IS NOT NULL AND ps.fantasy_points > 0
        ORDER BY ps.fantasy_points DESC
        LIMIT 1
    """), {"tid": team_id}).fetchone()

    if not row:
        return None

    points = row[0]
    player = row[1]
    season = row[2]
    rnd = row[3]
    opponent = row[4]

    return {
        "headline": f"Fantasy monster: {points} points by {player} vs {opponent}",
        "detail": f"Round {rnd}, {season}",
        "stat_type": "fantasy_monster",
        "_raw_score": points / 200,  # 200 fantasy points = 1.0
    }


def _disposal_king(session, team_id: int) -> dict | None:
    """Most disposals in a single game by a player on the team."""
    row = session.execute(text("""
        SELECT ps.disposals, p.name, m.season, m.round,
               CASE WHEN m.home_team_id = :tid THEN opp.name ELSE home_t.name END AS opponent
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams home_t ON m.home_team_id = home_t.id
        JOIN teams opp ON (
            CASE WHEN m.home_team_id = :tid THEN m.away_team_id ELSE m.home_team_id END = opp.id
        )
        WHERE ps.team_id = :tid
          AND ps.disposals IS NOT NULL AND ps.disposals > 0
        ORDER BY ps.disposals DESC
        LIMIT 1
    """), {"tid": team_id}).fetchone()

    if not row:
        return None

    disposals = row[0]
    player = row[1]
    season = row[2]
    rnd = row[3]
    opponent = row[4]

    return {
        "headline": f"Most disposals in a game: {disposals} by {player} vs {opponent}",
        "detail": f"Round {rnd}, {season}",
        "stat_type": "disposal_king",
        "_raw_score": disposals / 50,  # 50 disposals = 1.0
    }


def _home_fortress(session, team_id: int) -> dict | None:
    """Win percentage at the team's most-played home venue."""
    row = session.execute(text("""
        WITH home_venues AS (
            SELECT venue, COUNT(*) AS games,
                   SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END) AS wins
            FROM matches
            WHERE home_team_id = :tid
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND home_score > 0
            GROUP BY venue
            HAVING COUNT(*) >= 20
            ORDER BY COUNT(*) DESC
            LIMIT 1
        )
        SELECT venue, games, wins,
               ROUND(100.0 * wins / games, 1) AS win_pct
        FROM home_venues
    """), {"tid": team_id}).fetchone()

    if not row:
        return None

    venue = row[0]
    games = row[1]
    wins = row[2]
    win_pct = float(row[3])

    return {
        "headline": f"Home fortress: {win_pct}% win rate at {venue}",
        "detail": f"{wins} wins from {games} home games",
        "stat_type": "home_fortress",
        "_raw_score": win_pct / 100,  # 100% = 1.0
    }
