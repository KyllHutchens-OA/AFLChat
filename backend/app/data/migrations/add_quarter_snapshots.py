"""
Add QuarterSnapshot table, description column to LiveGameEvent,
and quarter_summaries JSONB column to LiveGame.
Run with: python -m app.data.migrations.add_quarter_snapshots
"""
from sqlalchemy import text
from app.data.database import engine, Base
from app.data.models import QuarterSnapshot
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Create quarter snapshots table and add new columns."""
    try:
        # Create the QuarterSnapshot table
        logger.info("Creating quarter_snapshots table...")
        Base.metadata.create_all(
            engine,
            tables=[QuarterSnapshot.__table__]
        )
        logger.info("  - quarter_snapshots table created")

        # Add new columns to existing tables
        with engine.connect() as conn:
            # Add description column to live_game_events
            try:
                conn.execute(text(
                    "ALTER TABLE live_game_events ADD COLUMN description VARCHAR(200)"
                ))
                conn.commit()
                logger.info("  - Added description column to live_game_events")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    logger.info("  - description column already exists on live_game_events")
                else:
                    raise

            # Add quarter_summaries JSONB column to live_games
            try:
                conn.execute(text(
                    "ALTER TABLE live_games ADD COLUMN quarter_summaries JSONB DEFAULT '{}'"
                ))
                conn.commit()
                logger.info("  - Added quarter_summaries column to live_games")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    logger.info("  - quarter_summaries column already exists on live_games")
                else:
                    raise

        logger.info("✓ Migration completed successfully!")

    except Exception as e:
        logger.error(f"✗ Error running migration: {e}")
        raise


if __name__ == "__main__":
    migrate()
