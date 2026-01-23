"""
Check what player data exists for Patrick Cripps.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.tools import DatabaseTool

# Check years available for Patrick Cripps
result = DatabaseTool.query_database("""
    SELECT DISTINCT m.season, COUNT(*) as games
    FROM players p
    INNER JOIN player_stats ps ON ps.player_id = p.id
    INNER JOIN matches m ON ps.match_id = m.id
    WHERE p.name ILIKE 'Patrick Cripps'
    GROUP BY m.season
    ORDER BY m.season
""")

if result["success"]:
    print("\nSeasons with data for Patrick Cripps:")
    print(result["data"])
    print(f"\nTotal seasons: {len(result['data'])}")
else:
    print(f"Error: {result['error']}")

print("\n" + "=" * 80)

# Check 2024 data specifically
result = DatabaseTool.query_database("""
    SELECT ps.disposals, m.season, m.round
    FROM players p
    INNER JOIN player_stats ps ON ps.player_id = p.id
    INNER JOIN matches m ON ps.match_id = m.id
    WHERE p.name ILIKE 'Patrick Cripps' AND m.season = 2024
    ORDER BY m.round
    LIMIT 5
""")

if result["success"]:
    print("\n2024 data for Patrick Cripps (first 5 games):")
    print(result["data"])
else:
    print(f"Error: {result['error']}")
