"""
Check what player data exists using DatabaseTool.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from app.agent.tools import DatabaseTool

async def main():
    # Check Patrick Cripps exists
    result = await DatabaseTool.execute_query(
        "SELECT id, name, team_id FROM players WHERE name ILIKE '%Cripps%'"
    )
    print("Players matching 'Cripps':")
    print(result["data"])
    print("\n" + "=" * 80)

    # Check years available for Patrick Cripps
    result = await DatabaseTool.execute_query("""
        SELECT DISTINCT m.season, COUNT(*) as games
        FROM players p
        INNER JOIN player_stats ps ON ps.player_id = p.id
        INNER JOIN matches m ON ps.match_id = m.id
        WHERE p.name ILIKE 'Patrick Cripps'
        GROUP BY m.season
        ORDER BY m.season
    """)
    print("\nSeasons with data for Patrick Cripps:")
    print(result["data"])
    print("\n" + "=" * 80)

    # Check sample data for most recent season
    result = await DatabaseTool.execute_query("""
        SELECT m.season, m.round, ps.disposals, ps.kicks, ps.handballs, ps.goals
        FROM players p
        INNER JOIN player_stats ps ON ps.player_id = p.id
        INNER JOIN matches m ON ps.match_id = m.id
        WHERE p.name ILIKE 'Patrick Cripps'
        ORDER BY m.season DESC, CAST(REGEXP_REPLACE(m.round, '[^0-9]', '', 'g') AS INTEGER) DESC
        LIMIT 10
    """)
    print("\nMost recent 10 games for Patrick Cripps:")
    print(result["data"])

if __name__ == "__main__":
    asyncio.run(main())
