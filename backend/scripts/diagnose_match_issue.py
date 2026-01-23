"""
Diagnose why match lookups are failing in the ingestion script.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.tools import DatabaseTool
import pandas as pd

# Check what Hawthorn vs Essendon match looks like in round 2 2024
print("=" * 80)
print("1. Check Hawthorn matches in round 2 of 2024:")
result = DatabaseTool.query_database("""
    SELECT m.id, m.round, m.home_team_id, m.away_team_id,
           ht.name as home_team, at.name as away_team
    FROM matches m
    JOIN teams ht ON m.home_team_id = ht.id
    JOIN teams at ON m.away_team_id = at.id
    WHERE m.season = 2024 AND m.round = '2'
    AND (ht.name ILIKE 'Hawthorn' OR at.name ILIKE 'Hawthorn')
""")
if result['success']:
    print(result['data'])
else:
    print(f"Error: {result['error']}")

print("\n" + "=" * 80)
print("2. Check team IDs:")
result = DatabaseTool.query_database("""
    SELECT id, name FROM teams
    WHERE name IN ('Hawthorn', 'Essendon', 'Melbourne', 'North Melbourne')
    ORDER BY name
""")
if result['success']:
    print(result['data'])

print("\n" + "=" * 80)
print("3. Check what the CSV says for Jack Gunston:")
csv_file = Path("/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players/gunston_jack_26041991_performance_details.csv")
df = pd.read_csv(csv_file)
df_2024 = df[df['year'] == 2024]
print("\nJack Gunston 2024 games (first 5):")
print(df_2024[['team', 'year', 'round', 'opponent', 'result']].head())

print("\n" + "=" * 80)
print("4. Try to find match using ingestion script logic:")
print("   Team: Hawthorn (ID=20)")
print("   Opponent: Essendon (ID=15)")
print("   Round: 2")

result = DatabaseTool.query_database("""
    SELECT id FROM matches
    WHERE season = 2024
    AND round = '2'
    AND ((home_team_id = 20 AND away_team_id = 15)
         OR (away_team_id = 20 AND home_team_id = 15))
    LIMIT 1
""")
if result['success'] and len(result['data']) > 0:
    print(f"   ✅ Match found: ID = {result['data'].iloc[0]['id']}")
else:
    print(f"   ❌ No match found")
    print(f"   Result: {result}")
