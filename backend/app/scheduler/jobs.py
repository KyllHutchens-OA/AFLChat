"""
Scheduled jobs for fetching news, odds, and predictions.
"""
import logging

logger = logging.getLogger(__name__)


def fetch_rss_news():
    """Hourly: Fetch RSS feeds."""
    try:
        from app.data.ingestion.rss_news_fetcher import RSSNewsFetcher
        
        articles_added = RSSNewsFetcher.fetch_all_feeds()
        logger.info(f"RSS job complete: {articles_added} new articles")
    except Exception as e:
        logger.error(f"RSS job failed: {e}")


def update_betting_odds():
    """Daily: Update odds with rate limiting."""
    try:
        from app.data.ingestion.odds_fetcher import OddsFetcher
        
        requests_made = OddsFetcher.update_upcoming_matches(days_ahead=7, max_requests=16)
        logger.info(f"Odds job complete: {requests_made} API requests")
    except Exception as e:
        logger.error(f"Odds job failed: {e}")


def update_squiggle_predictions():
    """Daily: Update predictions."""
    try:
        from app.data.ingestion.squiggle_fetcher import SquiggleFetcher
        
        predictions = SquiggleFetcher.fetch_current_round_predictions()
        logger.info(f"Predictions job complete: {predictions} updated")
    except Exception as e:
        logger.error(f"Predictions job failed: {e}")
