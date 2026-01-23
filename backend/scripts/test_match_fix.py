"""
Test if the round offset fix works.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.tools import DatabaseTool

def get_team_id(team_name: str) -> int:
    """Get team ID from database."""
    result = DatabaseTool.query_database(
        f"SELECT id FROM teams WHERE name ILIKE '{team_name}' LIMIT 1"
    )
    if result["success"] and len(result["data"]) > 0:
        return result["data"].iloc[0]["id"]
    return None

def get_match_id_fixed(team_id: int, opponent: str, season: int, round_num: str) -> int:
    """Get match ID with round offset fix."""
    opponent_id = get_team_id(opponent)
    if not opponent_id:
        return None

    # Try exact round first
    result = DatabaseTool.query_database(f"""
        SELECT id FROM matches
        WHERE season = {season}
        AND round = '{round_num}'
        AND ((home_team_id = {team_id} AND away_team_id = {opponent_id})
             OR (away_team_id = {team_id} AND home_team_id = {opponent_id}))
        LIMIT 1
    """)

    if result["success"] and len(result["data"]) > 0:
        return result["data"].iloc[0]["id"]

    # Try round - 1
    try:
        adjusted_round = str(int(round_num) - 1)
        result = DatabaseTool.query_database(f"""
            SELECT id FROM matches
            WHERE season = {season}
            AND round = '{adjusted_round}'
            AND ((home_team_id = {team_id} AND away_team_id = {opponent_id})
                 OR (away_team_id = {team_id} AND home_team_id = {opponent_id}))
            LIMIT 1
        """)

        if result["success"] and len(result["data"]) > 0:
            return result["data"].iloc[0]["id"]
    except (ValueError, TypeError):
        pass

    return None

# Test cases from CSV
print("Testing match lookup with round offset fix:")
print("=" * 80)

hawthorn_id = get_team_id("Hawthorn")
print(f"Hawthorn ID: {hawthorn_id}")

test_cases = [
    ("Essendon", 2024, "2", "Should find Hawthorn vs Essendon in Round 1"),
    ("Melbourne", 2024, "3", "Should find Hawthorn vs Melbourne in Round 2"),
    ("North Melbourne", 2024, "7", "Should find Hawthorn vs North Melbourne in Round 6"),
]

for opponent, season, csv_round, description in test_cases:
    match_id = get_match_id_fixed(hawthorn_id, opponent, season, csv_round)
    status = "✅ FOUND" if match_id else "❌ NOT FOUND"
    print(f"{status}: CSV Round {csv_round} vs {opponent} - {description}")
    if match_id:
        print(f"         Match ID: {match_id}")
