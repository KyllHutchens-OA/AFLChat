"""
Add MatchPreview table for DB-backed match previews.
Run with: python -m app.data.migrations.add_match_previews
"""
from app.data.database import engine, Base
from app.data.models import MatchPreview
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Create match_previews table."""
    try:
        logger.info("Creating match_previews table...")
        Base.metadata.create_all(engine, tables=[MatchPreview.__table__])
        logger.info("✓ match_previews table created")
    except Exception as e:
        logger.error(f"✗ Error running migration: {e}")
        raise


if __name__ == "__main__":
    migrate()
