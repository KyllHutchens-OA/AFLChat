"""
Fix missing player_stats data for 1994, 2017, and 2025.

Ingests:
1. Matches for 1994, 2017 (already exist for 2025)
2. Player stats for all three seasons
"""
import sys
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.data.ingestion.csv_match_ingester import CSVMatchIngester
from app.data.ingestion.player_ingester import PlayerDataIngester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 80)
    logger.info("FIXING MISSING SEASONS: 1994, 2017, 2025")
    logger.info("=" * 80)

    matches_dir = "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/matches"
    players_dir = "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players"

    # Step 1: Ingest 1994 matches
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Ingesting 1994 matches")
    logger.info("=" * 80)

    with CSVMatchIngester(matches_dir) as ingester:
        ingester.ingest_season(1994, dry_run=False)

    # Step 2: Ingest 2017 matches
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Ingesting 2017 matches")
    logger.info("=" * 80)

    with CSVMatchIngester(matches_dir) as ingester:
        ingester.ingest_season(2017, dry_run=False)

    # Step 3: Ingest player stats for ALL seasons (will skip existing)
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Ingesting player stats for 1994, 2017, 2025")
    logger.info("=" * 80)
    logger.info("This may take 10-15 minutes...")

    with PlayerDataIngester(players_dir) as ingester:
        # Full ingestion - will skip duplicates automatically
        ingester.ingest_all(batch_size=1000)

    logger.info("\n" + "=" * 80)
    logger.info("✅ COMPLETE! All missing data has been ingested.")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
