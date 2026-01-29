#!/bin/bash
# Auto-complete data ingestion after player scraper finishes

echo "=================================================="
echo "Waiting for player scraper to complete..."
echo "=================================================="
echo ""

# Wait for scraper to finish
while pgrep -f "main.py --scrape_players" > /dev/null; do
    CURRENT=$(wc -l < /tmp/player_scraper_full.log 2>/dev/null || echo "0")
    LAST=$(tail -1 /tmp/player_scraper_full.log 2>/dev/null | sed 's/Processing player: //' || echo "Unknown")
    echo "[$(date +%H:%M:%S)] Progress: $CURRENT players | $LAST"
    sleep 120  # Check every 2 minutes
done

echo ""
echo "✅ Player scraper completed!"
echo "Total players: $(wc -l < /tmp/player_scraper_full.log)"
echo ""
echo "=================================================="
echo "Starting automatic data ingestion..."
echo "=================================================="
echo ""

# Change to backend directory
cd "/Users/kyllhutchens/Code/AFL App/backend"

# Activate venv and run player stats ingestion
echo "Step 1: Re-ingesting player stats from updated CSV files..."
echo "This will take 20-30 minutes..."
echo ""

source venv/bin/activate

python3 << 'PYTHON_SCRIPT'
from app.data.ingestion.player_ingester import PlayerDataIngester
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

players_dir = "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players"

print("=" * 60)
print("Re-ingesting player stats from updated CSV files")
print("=" * 60)

with PlayerDataIngester(players_dir) as ingester:
    ingester.ingest_all(batch_size=1000)

print("=" * 60)
print("Player stats ingestion complete!")
print("=" * 60)
PYTHON_SCRIPT

echo ""
echo "Step 2: Verifying data completeness..."
echo ""

python3 << 'PYTHON_SCRIPT'
from app.data.database import Session
from app.data.models import Match, PlayerStat
from sqlalchemy import func

session = Session()

print("=" * 60)
print("Data Completeness Verification")
print("=" * 60)
print("")

# Check overall coverage
total_matches = session.query(Match).count()
matches_with_stats = session.query(func.count(func.distinct(PlayerStat.match_id))).scalar()
coverage_pct = (matches_with_stats / total_matches * 100) if total_matches > 0 else 0

print(f"Total matches in database: {total_matches:,}")
print(f"Matches with player_stats: {matches_with_stats:,}")
print(f"Coverage: {coverage_pct:.1f}%")
print("")

# Check specific years
print("Coverage by year:")
for year in [1994, 2017, 2025]:
    year_matches = session.query(Match).filter(Match.season == year).count()
    year_with_stats = session.query(func.count(func.distinct(PlayerStat.match_id))).join(
        Match, PlayerStat.match_id == Match.id
    ).filter(Match.season == year).scalar()

    year_pct = (year_with_stats / year_matches * 100) if year_matches > 0 else 0
    status = "✅" if year_pct >= 99 else "⚠️"

    print(f"  {status} {year}: {year_with_stats}/{year_matches} matches ({year_pct:.1f}%)")

print("")

# Check for remaining missing matches
matches_without_stats = session.query(Match).filter(
    ~Match.id.in_(session.query(PlayerStat.match_id).distinct())
).count()

if matches_without_stats == 0:
    print("🎉 SUCCESS! All matches now have player_stats!")
else:
    print(f"⚠️  Still missing: {matches_without_stats} matches without player_stats")

    # Show which matches are missing
    missing = session.query(Match).filter(
        ~Match.id.in_(session.query(PlayerStat.match_id).distinct())
    ).all()

    print("\nMissing matches by year:")
    by_year = {}
    for m in missing:
        by_year.setdefault(m.season, []).append(m)

    for year in sorted(by_year.keys()):
        print(f"  {year}: {len(by_year[year])} matches")

session.close()

print("")
print("=" * 60)
print("Verification complete!")
print("=" * 60)
PYTHON_SCRIPT

echo ""
echo "=================================================="
echo "All tasks completed!"
echo "=================================================="
