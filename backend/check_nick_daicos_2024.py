"""Check Nick Daicos 2024 goals."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.data.database import Session
from sqlalchemy import text

session = Session()

# Check if Nick Daicos has any data in 2024
query = text("""
    SELECT
        p.name,
        m.season,
        COUNT(*) as match_count,
        SUM(ps.goals) as total_goals
    FROM players p
    JOIN player_stats ps ON ps.player_id = p.id
    JOIN matches m ON m.id = ps.match_id
    WHERE p.name ILIKE '%Nick Daicos%'
    AND m.season = 2024
    GROUP BY p.name, m.season
    ORDER BY p.name
""")

results = session.execute(query).fetchall()

print("=" * 80)
print("NICK DAICOS - 2024 DATA")
print("=" * 80)

if results:
    for row in results:
        print(f"\nPlayer: {row[0]}")
        print(f"Season: {row[1]}")
        print(f"Matches: {row[2]}")
        print(f"Total Goals: {row[3]}")
else:
    print("\n❌ No data found for Nick Daicos in 2024")

# Also check what seasons we have for Nick Daicos
query2 = text("""
    SELECT
        p.name,
        m.season,
        COUNT(*) as match_count,
        SUM(ps.goals) as total_goals
    FROM players p
    JOIN player_stats ps ON ps.player_id = p.id
    JOIN matches m ON m.id = ps.match_id
    WHERE p.name ILIKE '%Nick Daicos%'
    GROUP BY p.name, m.season
    ORDER BY m.season DESC
""")

results2 = session.execute(query2).fetchall()

print("\n" + "=" * 80)
print("NICK DAICOS - ALL SEASONS")
print("=" * 80)

for row in results2:
    print(f"Season {row[1]}: {row[2]} matches, {row[3]} goals")

session.close()
