"""
Migration: Add post_game_analysis column to live_games table.
Stores AI-generated post-game stats analysis from web search.
"""
import logging
from app.data.database import engine

logger = logging.getLogger(__name__)


def run_migration():
    """Add post_game_analysis TEXT column to live_games."""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(
            __import__('sqlalchemy').text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'live_games' AND column_name = 'post_game_analysis'"
            )
        )
        if result.fetchone():
            logger.info("Column post_game_analysis already exists, skipping migration")
            return

        conn.execute(
            __import__('sqlalchemy').text(
                "ALTER TABLE live_games ADD COLUMN post_game_analysis TEXT"
            )
        )
        conn.commit()
        logger.info("Added post_game_analysis column to live_games table")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
