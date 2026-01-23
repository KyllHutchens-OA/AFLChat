"""
Check what player data exists in the database.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

engine = create_engine(os.getenv("DB_STRING"))

with engine.connect() as conn:
    # Check Patrick Cripps exists
    result = conn.execute(text("SELECT id, name, team_id FROM players WHERE name ILIKE '%Cripps%'"))
    print("Players matching 'Cripps':")
    for row in result:
        print(f"  ID: {row[0]}, Name: {row[1]}, Team ID: {row[2]}")

    print("\n" + "=" * 80)

    # Check years available for Patrick Cripps
    result = conn.execute(text("""
        SELECT DISTINCT m.season, COUNT(*) as games
        FROM players p
        INNER JOIN player_stats ps ON ps.player_id = p.id
        INNER JOIN matches m ON ps.match_id = m.id
        WHERE p.name ILIKE 'Patrick Cripps'
        GROUP BY m.season
        ORDER BY m.season
    """))
    print("\nSeasons with data for Patrick Cripps:")
    for row in result:
        print(f"  {row[0]}: {row[1]} games")

    print("\n" + "=" * 80)

    # Check sample data for most recent season
    result = conn.execute(text("""
        SELECT m.season, m.round, ps.disposals, ps.kicks, ps.handballs, ps.goals
        FROM players p
        INNER JOIN player_stats ps ON ps.player_id = p.id
        INNER JOIN matches m ON ps.match_id = m.id
        WHERE p.name ILIKE 'Patrick Cripps'
        ORDER BY m.season DESC, m.round DESC
        LIMIT 10
    """))
    print("\nMost recent 10 games for Patrick Cripps:")
    print(f"{'Season':<8} {'Round':<15} {'Disposals':<12} {'Kicks':<8} {'Handballs':<12} {'Goals':<8}")
    for row in result:
        print(f"{row[0]:<8} {str(row[1]):<15} {row[2] if row[2] else 'NULL':<12} {row[3] if row[3] else 'NULL':<8} {row[4] if row[4] else 'NULL':<12} {row[5] if row[5] else 'NULL':<8}")
