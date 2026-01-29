"""
Ingest newly scraped match data for 1994, 2017, and 2025.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from app.data.ingestion.csv_match_ingester import CSVMatchIngester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    csv_dir = "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/matches"

    logger.info("=" * 60)
    logger.info("Ingesting newly scraped match data")
    logger.info("=" * 60)

    # Ingest 1994 (including finals)
    logger.info("\n--- 1994 Season ---")
    with CSVMatchIngester(csv_dir) as ingester:
        ingester.ingest_season(1994, dry_run=False)

    # Ingest 2017 (including finals)
    logger.info("\n--- 2017 Season ---")
    with CSVMatchIngester(csv_dir) as ingester:
        ingester.ingest_season(2017, dry_run=False)

    # Ingest 2025 (full season)
    logger.info("\n--- 2025 Season ---")
    with CSVMatchIngester(csv_dir) as ingester:
        ingester.ingest_season(2025, dry_run=False)

    logger.info("=" * 60)
    logger.info("Match ingestion complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
