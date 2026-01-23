"""Check if round 0 exists."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.tools import DatabaseTool

result = DatabaseTool.query_database("""
    SELECT round, COUNT(*) as match_count, MIN(match_date) as first_game
    FROM matches
    WHERE season = 2024
    AND round IN ('0', '1')
    GROUP BY round
    ORDER BY round
""")

print("Early 2024 rounds:")
print(result['data'])
