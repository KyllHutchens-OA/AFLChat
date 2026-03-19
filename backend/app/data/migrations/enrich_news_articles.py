"""
Migration: Add LLM enrichment columns to news_articles table.

New columns:
- is_afl (boolean) - LLM-determined AFL relevance
- category (varchar) - article category (match_result, injury, trade, etc.)
- summary (varchar) - LLM-generated one-line summary
- injury_details (jsonb) - structured injury info
- enriched_at (timestamp) - when enrichment ran
"""
from sqlalchemy import text
from app.data.database import engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Add LLM enrichment columns to news_articles."""
    with engine.connect() as conn:
        # Add new columns (IF NOT EXISTS prevents errors on re-run)
        columns = [
            ("is_afl", "BOOLEAN DEFAULT TRUE"),
            ("category", "VARCHAR(50)"),
            ("summary", "VARCHAR(500)"),
            ("injury_details", "JSONB"),
            ("enriched_at", "TIMESTAMP"),
        ]

        for col_name, col_type in columns:
            try:
                conn.execute(text(
                    f"ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                logger.info(f"  ✓ Added column: {col_name}")
            except Exception as e:
                logger.warning(f"  Column {col_name} may already exist: {e}")

        # Add index on category + published_date
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_news_category_published "
                "ON news_articles (category, published_date)"
            ))
            logger.info("  ✓ Added index: idx_news_category_published")
        except Exception as e:
            logger.warning(f"  Index may already exist: {e}")

        # Add index on is_afl
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_news_is_afl "
                "ON news_articles (is_afl)"
            ))
            logger.info("  ✓ Added index: idx_news_is_afl")
        except Exception as e:
            logger.warning(f"  Index may already exist: {e}")

        # Backfill existing articles: set is_afl=True, summary=title for articles
        # that predate the enrichment system
        conn.execute(text(
            "UPDATE news_articles SET is_afl = TRUE, summary = title "
            "WHERE enriched_at IS NULL"
        ))
        logger.info("  ✓ Backfilled existing articles with is_afl=TRUE and summary=title")

        conn.commit()
        logger.info("✓ Migration complete: news_articles enrichment columns added")


if __name__ == "__main__":
    migrate()
