"""
Add LiveGame and LiveGameEvent tables for real-time match tracking.
Run with: python -m app.data.migrations.add_live_games
"""
from app.data.database import engine, Base
from app.data.models import LiveGame, LiveGameEvent
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Create live games tables."""
    try:
        logger.info("Creating live games tables...")

        # Create only the LiveGame and LiveGameEvent tables
        Base.metadata.create_all(
            engine,
            tables=[LiveGame.__table__, LiveGameEvent.__table__]
        )

        logger.info("✓ Live games tables created successfully!")
        logger.info("  - live_games")
        logger.info("  - live_game_events")

    except Exception as e:
        logger.error(f"✗ Error creating tables: {e}")
        raise


if __name__ == "__main__":
    migrate()
