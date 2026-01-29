"""Check if round 27 in 2020-2022 is the Grand Final."""
from app.data.database import Session
from sqlalchemy import text

session = Session()
try:
    # Check round 27 matches for 2020-2022
    result = session.execute(text("""
        SELECT m.season, m.round, m.match_date,
               t1.name as home_team, t2.name as away_team,
               m.home_score, m.away_score, m.venue
        FROM matches m
        JOIN teams t1 ON m.home_team_id = t1.id
        JOIN teams t2 ON m.away_team_id = t2.id
        WHERE m.season BETWEEN 2020 AND 2022
          AND m.round = '27'
        ORDER BY m.season DESC, m.match_date
    """))

    print('Round 27 Matches (2020-2022):')
    print('=' * 120)
    for row in result:
        print(f'{row.season} | Round {row.round} | {row.match_date} | {row.venue}')
        print(f'  {row.home_team} {row.home_score} vs {row.away_team} {row.away_score}')
        print()

    # Compare with known Grand Finals from 2019 and earlier
    print('\nKnown Grand Finals for comparison:')
    print('=' * 120)
    result2 = session.execute(text("""
        SELECT m.season, m.round, m.match_date,
               t1.name as home_team, t2.name as away_team,
               m.home_score, m.away_score, m.venue
        FROM matches m
        JOIN teams t1 ON m.home_team_id = t1.id
        JOIN teams t2 ON m.away_team_id = t2.id
        WHERE m.season BETWEEN 2017 AND 2022
          AND m.round ILIKE '%grand%final%'
        ORDER BY m.season DESC
    """))
    for row in result2:
        print(f'{row.season} | {row.round} | {row.match_date} | {row.venue}')
        print(f'  {row.home_team} {row.home_score} vs {row.away_team} {row.away_score}')
        print()

finally:
    session.close()
