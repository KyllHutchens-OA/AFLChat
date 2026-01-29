"""
Comprehensive investigation of missing player_stats data for 1994, 2017, and 2025
"""
from app.data.database import Session
from sqlalchemy import text

session = Session()

print("=" * 100)
print("COMPREHENSIVE PLAYER_STATS DATA AUDIT - 1994, 2017, 2025")
print("=" * 100)

target_seasons = [1994, 2017, 2025]

for season in target_seasons:
    print(f"\n{'=' * 100}")
    print(f"SEASON {season} ANALYSIS")
    print("=" * 100)

    # 1. Check matches data
    result = session.execute(text("""
        SELECT
            COUNT(*) as total_matches,
            COUNT(DISTINCT round) as unique_rounds,
            MIN(match_date) as first_match,
            MAX(match_date) as last_match
        FROM matches
        WHERE season = :season
    """), {"season": season})

    match_data = result.fetchone()
    print(f"\n📊 MATCHES DATA:")
    print(f"   Total matches: {match_data[0]}")
    print(f"   Unique rounds: {match_data[1]}")
    print(f"   Date range: {match_data[2]} to {match_data[3]}")

    # 2. Check player_stats data
    result = session.execute(text("""
        SELECT
            COUNT(DISTINCT ps.match_id) as matches_with_stats,
            COUNT(DISTINCT ps.player_id) as unique_players,
            COUNT(*) as total_stat_records
        FROM player_stats ps
        JOIN matches m ON ps.match_id = m.id
        WHERE m.season = :season
    """), {"season": season})

    stats_data = result.fetchone()
    print(f"\n📈 PLAYER_STATS DATA:")
    print(f"   Matches with player_stats: {stats_data[0]}")
    print(f"   Unique players: {stats_data[1]}")
    print(f"   Total stat records: {stats_data[2]}")

    # 3. Calculate coverage
    matches_total = match_data[0]
    matches_with_stats = stats_data[0] or 0
    coverage_pct = (matches_with_stats / matches_total * 100) if matches_total > 0 else 0

    print(f"\n🎯 COVERAGE ANALYSIS:")
    print(f"   Coverage: {matches_with_stats}/{matches_total} matches ({coverage_pct:.1f}%)")

    if coverage_pct < 100:
        missing_count = matches_total - matches_with_stats
        print(f"   ⚠️  MISSING: {missing_count} matches have NO player_stats!")

        # Find which matches are missing player_stats
        result = session.execute(text("""
            SELECT m.id, m.round, m.match_date,
                   t_home.name as home_team, t_away.name as away_team
            FROM matches m
            LEFT JOIN player_stats ps ON ps.match_id = m.id
            JOIN teams t_home ON m.home_team_id = t_home.id
            JOIN teams t_away ON m.away_team_id = t_away.id
            WHERE m.season = :season
              AND ps.match_id IS NULL
            ORDER BY m.match_date
        """), {"season": season})

        missing_matches = result.fetchall()
        if missing_matches:
            print(f"\n   Matches WITHOUT player_stats:")
            for match in missing_matches[:20]:
                print(f"     Round {match[1]:>15} ({match[2].date()}) - {match[3]} vs {match[4]}")
            if len(missing_matches) > 20:
                print(f"     ... and {len(missing_matches) - 20} more")
    else:
        print(f"   ✅ COMPLETE: All matches have player_stats!")

    # 4. Check data quality for matches that have stats
    if stats_data[2] > 0:
        result = session.execute(text("""
            SELECT
                AVG(player_count) as avg_players_per_match,
                MIN(player_count) as min_players,
                MAX(player_count) as max_players
            FROM (
                SELECT m.id, COUNT(DISTINCT ps.player_id) as player_count
                FROM matches m
                JOIN player_stats ps ON ps.match_id = m.id
                WHERE m.season = :season
                GROUP BY m.id
            ) as match_counts
        """), {"season": season})

        quality_data = result.fetchone()
        print(f"\n📋 DATA QUALITY (for matches with stats):")
        print(f"   Avg players per match: {quality_data[0]:.1f}")
        print(f"   Min players: {quality_data[1]}")
        print(f"   Max players: {quality_data[2]}")
        print(f"   Expected: ~36-44 players per match (2 teams × 18-22 players)")

        if quality_data[1] < 30:
            print(f"   ⚠️  WARNING: Some matches have suspiciously few players!")

print(f"\n{'=' * 100}")
print("SUMMARY")
print("=" * 100)

# Overall summary
result = session.execute(text("""
    SELECT
        m.season,
        COUNT(DISTINCT m.id) as total_matches,
        COUNT(DISTINCT ps.match_id) as matches_with_stats,
        COUNT(DISTINCT ps.player_id) as unique_players,
        COUNT(ps.player_id) as total_records
    FROM matches m
    LEFT JOIN player_stats ps ON ps.match_id = m.id
    WHERE m.season IN (1994, 2017, 2025)
    GROUP BY m.season
    ORDER BY m.season
"""))

summary = result.fetchall()
print(f"\n{'Season':<10} {'Matches':<12} {'With Stats':<15} {'Coverage':<12} {'Players':<10} {'Records':<12}")
print("-" * 100)
for row in summary:
    season = row[0]
    total_matches = row[1]
    with_stats = row[2] or 0
    players = row[3] or 0
    records = row[4] or 0
    coverage = (with_stats / total_matches * 100) if total_matches > 0 else 0
    status = "✅" if coverage == 100 else "❌"
    print(f"{season:<10} {total_matches:<12} {with_stats:<15} {coverage:>6.1f}% {status:<5} {players:<10} {records:<12}")

session.close()
