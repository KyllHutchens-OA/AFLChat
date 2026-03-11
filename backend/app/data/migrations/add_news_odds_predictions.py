"""
Migration: Add NewsArticle, BettingOdds, SquigglePrediction, APIRequestLog tables
"""
from app.data.database import engine, Base
from app.data.models import NewsArticle, BettingOdds, SquigglePrediction, APIRequestLog
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Create news, odds, predictions, and API log tables."""
    try:
        logger.info("Creating news, odds, predictions, and API log tables...")

        # Create only the new tables
        Base.metadata.create_all(
            engine,
            tables=[
                NewsArticle.__table__,
                BettingOdds.__table__,
                SquigglePrediction.__table__,
                APIRequestLog.__table__,
            ]
        )

        logger.info("✓ Tables created successfully!")
        logger.info("  - news_articles")
        logger.info("  - betting_odds")
        logger.info("  - squiggle_predictions")
        logger.info("  - api_request_logs")

    except Exception as e:
        logger.error(f"✗ Error creating tables: {e}")
        raise


if __name__ == "__main__":
    migrate()
