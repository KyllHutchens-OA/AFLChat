"""Verify 2020-2022 Grand Finals."""
from app.data.database import Session
from sqlalchemy import text

session = Session()
try:
    # Check 2020 round 27
    print('2020 Season Finals:')
    print('=' * 120)
    result = session.execute(text("""
        SELECT m.season, m.round, m.match_date,
               t1.name as home_team, t2.name as away_team,
               m.home_score, m.away_score, m.venue
        FROM matches m
        JOIN teams t1 ON m.home_team_id = t1.id
        JOIN teams t2 ON m.away_team_id = t2.id
        WHERE m.season = 2020
          AND m.round IN ('25', '26', '27', '28')
        ORDER BY m.match_date
    """))
    for row in result:
        print(f'Round {row.round} | {row.match_date} | {row.home_team} {row.home_score} vs {row.away_team} {row.away_score}')

    print('\n\nSummary - What IS the Grand Final in each season:')
    print('=' * 120)

    # Check the LAST match of each finals series
    result2 = session.execute(text("""
        WITH finals_matches AS (
            SELECT m.season, m.round, m.match_date,
                   t1.name as home_team, t2.name as away_team,
                   m.home_score, m.away_score,
                   ROW_NUMBER() OVER (PARTITION BY m.season ORDER BY m.match_date DESC) as rn
            FROM matches m
            JOIN teams t1 ON m.home_team_id = t1.id
            JOIN teams t2 ON m.away_team_id = t2.id
            WHERE m.season BETWEEN 2020 AND 2024
              AND (m.round IN ('25', '26', '27', '28') OR m.round ILIKE '%grand%final%')
        )
        SELECT season, round, match_date, home_team, home_score, away_team, away_score
        FROM finals_matches
        WHERE rn = 1
        ORDER BY season DESC
    """))

    for row in result2:
        print(f'{row.season} | Round {row.round:20} | {str(row.match_date)[:10]} | {row.home_team} {row.home_score} vs {row.away_team} {row.away_score}')

finally:
    session.close()
