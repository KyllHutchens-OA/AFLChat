"""Check finals structure and labeling consistency."""
from app.data.database import Session
from sqlalchemy import text

session = Session()
try:
    # Check all finals rounds (25-28) for all seasons
    result = session.execute(text("""
        SELECT season, round, COUNT(*) as match_count,
               MIN(match_date) as first_match, MAX(match_date) as last_match
        FROM matches
        WHERE round IN ('25', '26', '27', '28') OR round ILIKE '%final%' OR round ILIKE '%prelim%'
        GROUP BY season, round
        ORDER BY season DESC,
                 CASE
                   WHEN round ILIKE '%qualify%' OR round ILIKE '%elim%' THEN 1
                   WHEN round = '25' THEN 1
                   WHEN round ILIKE '%semi%' THEN 2
                   WHEN round = '26' THEN 2
                   WHEN round ILIKE '%prelim%' THEN 3
                   WHEN round = '27' THEN 3
                   WHEN round ILIKE '%grand%' THEN 4
                   WHEN round = '28' THEN 4
                   ELSE 5
                 END
    """))

    print('Finals Structure by Season:')
    print('=' * 120)
    current_season = None
    for row in result:
        if current_season is None or current_season != row.season:
            if current_season is not None:
                print()
            current_season = row.season
            print(f'\n{row.season}:')
        print(f'  Round {row.round:25} | {row.match_count} matches | {str(row.first_match)[:10]} to {str(row.last_match)[:10]}')
finally:
    session.close()
