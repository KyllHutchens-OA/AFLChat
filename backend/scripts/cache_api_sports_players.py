"""
Pre-cache all AFL players from API-Sports for the 2024 season.
This creates a local cache of player ID -> name mappings for fast lookups
during live games.

Run with: python -m scripts.cache_api_sports_players
"""
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Cache all players from API-Sports."""
    from app.services.api_sports_service import APISportsService

    logger.info("=" * 60)
    logger.info("Pre-caching AFL Players from API-Sports")
    logger.info("=" * 60)

    # First run the migration to ensure tables exist
    logger.info("\n1. Running migration to create tables...")
    try:
        from app.data.migrations.add_api_sports_players import migrate
        migrate()
    except Exception as e:
        logger.warning(f"Migration note: {e}")

    # Cache all team rosters
    logger.info("\n2. Caching all team rosters (18 teams)...")
    logger.info("   This will use 18 API calls (one per team)")

    total = APISportsService.cache_all_teams(season=2024)

    logger.info("\n" + "=" * 60)
    logger.info(f"✓ Successfully cached {total} players!")
    logger.info("=" * 60)
    logger.info("\nPlayers are now available for live game scoring attribution.")


if __name__ == "__main__":
    main()
