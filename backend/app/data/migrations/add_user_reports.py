"""
Add UserReport table for in-app issue reporting.
Run with: python -m app.data.migrations.add_user_reports
"""
from app.data.database import engine, Base
from app.data.models import UserReport
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Create user_reports table."""
    try:
        logger.info("Creating user_reports table...")
        Base.metadata.create_all(engine, tables=[UserReport.__table__])
        logger.info("✓ user_reports table created")
    except Exception as e:
        logger.error(f"✗ Error running migration: {e}")
        raise


if __name__ == "__main__":
    migrate()
