"""Check what round values exist in matches table."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.data.database import Session
from sqlalchemy import text

session = Session()

# Check round values for 2024
query = text("""
    SELECT DISTINCT m.round
    FROM matches m
    WHERE m.season = 2024
    ORDER BY m.round
    LIMIT 30
""")

print("=" * 80)
print("ROUND VALUES IN 2024 MATCHES")
print("=" * 80)

results = session.execute(query).fetchall()
print("\nRound values found:")
for row in results:
    print(f"  '{row[0]}' (Python type: {type(row[0]).__name__})")

session.close()
