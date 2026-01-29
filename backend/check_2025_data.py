"""
Check 2025 player_stats data in database
"""
import os
from sqlalchemy import create_engine, text
from app.config import get_config

config = get_config()
engine = create_engine(config.DATABASE_URL)

with engine.connect() as conn:
    print("=" * 80)
    print("2025 MATCHES DATA")
    print("=" * 80)

    # Check 2025 matches
    result = conn.execute(text("""
        SELECT COUNT(*) as match_count,
               MIN(match_date) as first_match,
               MAX(match_date) as last_match,
               COUNT(DISTINCT round) as unique_rounds
        FROM matches
        WHERE season = 2025
    """))

    match_data = result.fetchone()
    print(f"Total 2025 matches: {match_data[0]}")
    print(f"Date range: {match_data[1]} to {match_data[2]}")
    print(f"Unique rounds: {match_data[3]}")

    # Get all rounds
    result = conn.execute(text("""
        SELECT DISTINCT round
        FROM matches
        WHERE season = 2025
        ORDER BY
            CASE
                WHEN round ~ '^[0-9]+$' THEN CAST(round AS INTEGER)
                ELSE 999
            END,
            round
    """))
    rounds = [r[0] for r in result.fetchall()]
    print(f"All rounds: {', '.join(map(str, rounds[:20]))}")
    if len(rounds) > 20:
        print(f"... and {len(rounds) - 20} more")

    print("\n" + "=" * 80)
    print("2025 PLAYER_STATS DATA")
    print("=" * 80)

    # Check 2025 player_stats
    result = conn.execute(text("""
        SELECT COUNT(*) as stat_count,
               COUNT(DISTINCT ps.player_id) as unique_players,
               COUNT(DISTINCT ps.match_id) as unique_matches
        FROM player_stats ps
        JOIN matches m ON ps.match_id = m.id
        WHERE m.season = 2025
    """))

    stats_data = result.fetchone()
    print(f"Total 2025 player_stats records: {stats_data[0]}")
    print(f"Unique players with stats: {stats_data[1]}")
    print(f"Matches with player_stats: {stats_data[2]}")

    # Check matches vs player_stats mismatch
    if match_data[0] > 0 and stats_data[2] == 0:
        print("\n⚠️  WARNING: We have 2025 MATCHES but NO player_stats!")
        print("This suggests player_stats data wasn't loaded for 2025.")

    print("\n" + "=" * 80)
    print("NICK DAICOS 2025 DETAILED DATA")
    print("=" * 80)

    # Check Nick Daicos specifically
    result = conn.execute(text("""
        SELECT m.round, m.match_date,
               t_home.name as home_team, t_away.name as away_team,
               ps.goals, ps.disposals, ps.kicks, ps.handballs
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams t_home ON m.home_team_id = t_home.id
        JOIN teams t_away ON m.away_team_id = t_away.id
        WHERE p.name ILIKE 'Nick Daicos'
          AND m.season = 2025
        ORDER BY m.match_date
    """))

    nick_rows = result.fetchall()
    if nick_rows:
        print(f"Nick Daicos played {len(nick_rows)} matches in 2025:\n")
        for row in nick_rows:
            print(f"Round {row[0]:>2} ({row[1].date()}) - {row[2]} vs {row[3]}")
            print(f"         Goals: {row[4]}, Disposals: {row[5]} (K: {row[6]}, H: {row[7]})")
    else:
        print("NO player_stats records found for Nick Daicos in 2025!")

    print("\n" + "=" * 80)
    print("SAMPLE: TOP PLAYERS WITH 2025 STATS")
    print("=" * 80)

    # Check if OTHER players have 2025 stats
    result = conn.execute(text("""
        SELECT p.name, COUNT(*) as matches_played,
               SUM(ps.goals) as total_goals,
               SUM(ps.disposals) as total_disposals
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        WHERE m.season = 2025
        GROUP BY p.name
        ORDER BY SUM(ps.disposals) DESC
        LIMIT 10
    """))

    sample_players = result.fetchall()
    if sample_players:
        print("Top 10 players by disposals in 2025:")
        for row in sample_players:
            print(f"  {row[0]:<30} - {row[1]} matches, {row[2]} goals, {row[3]} disposals")
    else:
        print("NO player_stats data exists for 2025!")
        print("\nThis means the issue is: 2025 MATCHES exist but player_stats weren't loaded.")
