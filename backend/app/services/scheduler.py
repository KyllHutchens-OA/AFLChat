"""
Background Scheduler - Lightweight cleanup tasks for live games.
SSE handles real-time updates, so this just manages housekeeping.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import logging
import atexit

from app.data.database import get_session
from app.data.models import LiveGame

logger = logging.getLogger(__name__)


class LiveGameScheduler:
    """Manages background jobs for live game system."""

    def __init__(self, sse_listener=None):
        """
        Initialize scheduler.

        Args:
            sse_listener: SSE listener instance to monitor
        """
        self.scheduler = BackgroundScheduler(daemon=True)
        self.sse_listener = sse_listener
        self.is_running = False

    def start(self):
        """Start background scheduler."""
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        # Job 1: Cleanup old completed games (daily at 3 AM)
        self.scheduler.add_job(
            func=self._cleanup_old_games,
            trigger=CronTrigger(hour=3, minute=0),
            id="cleanup_old_games",
            name="Cleanup old completed games",
            replace_existing=True,
        )

        # Job 2: Poll for live games (every 20 seconds)
        self.scheduler.add_job(
            func=self._poll_live_games,
            trigger=IntervalTrigger(seconds=20),
            id="poll_live_games",
            name="Poll Squiggle for live games",
            replace_existing=True,
        )

        # Job 3: Health check SSE connection (every 5 minutes)
        self.scheduler.add_job(
            func=self._health_check,
            trigger=IntervalTrigger(minutes=5),
            id="sse_health_check",
            name="SSE connection health check",
            replace_existing=True,
        )

        # Job 4: Fetch RSS news (every 6 hours)
        self.scheduler.add_job(
            func=self._fetch_rss_news,
            trigger=IntervalTrigger(hours=6),
            id="fetch_rss_news",
            name="Fetch and enrich RSS news feeds",
            replace_existing=True,
        )

        # Job 5a: Update betting odds (morning at 9 AM AEST)
        self.scheduler.add_job(
            func=self._update_betting_odds,
            trigger=CronTrigger(hour=9, minute=0, timezone='Australia/Melbourne'),
            id="update_betting_odds_morning",
            name="Update betting odds (morning)",
            replace_existing=True,
        )

        # Job 5b: Update betting odds (evening at 5 PM AEST)
        self.scheduler.add_job(
            func=self._update_betting_odds,
            trigger=CronTrigger(hour=17, minute=0, timezone='Australia/Melbourne'),
            id="update_betting_odds_evening",
            name="Update betting odds (evening)",
            replace_existing=True,
        )

        # Job 6: Update Squiggle predictions (daily at 8 AM AEST)
        self.scheduler.add_job(
            func=self._update_squiggle_predictions,
            trigger=CronTrigger(hour=8, minute=0, timezone='Australia/Melbourne'),
            id="update_squiggle_predictions",
            name="Update Squiggle predictions",
            replace_existing=True,
        )

        # Job 6: Ingest current season match results (daily at 11 PM AEST)
        # Runs after evening games finish — inserts new matches and updates
        # any previously-scheduled games that have since completed.
        self.scheduler.add_job(
            func=self._update_current_season_matches,
            trigger=CronTrigger(hour=23, minute=0, timezone='Australia/Melbourne'),
            id="update_current_season_matches",
            name="Ingest current season match results",
            replace_existing=True,
        )

        self.scheduler.start()
        self.is_running = True

        # Register shutdown handler
        atexit.register(lambda: self.scheduler.shutdown(wait=False))

        logger.info("✓ Background scheduler started")

    def stop(self):
        """Stop scheduler gracefully."""
        if not self.is_running:
            return

        self.scheduler.shutdown(wait=False)
        self.is_running = False
        logger.info("✓ Background scheduler stopped")

    def _poll_live_games(self):
        """Poll Squiggle API for live games and update database."""
        try:
            import requests
            from app.services.live_game_service import LiveGameService
            from app import socketio

            # Fetch games from Squiggle API
            current_year = datetime.now().year
            response = requests.get(
                f"https://api.squiggle.com.au/?q=games;year={current_year}",
                headers={"User-Agent": "AFL-Analytics-App/1.0"},
                timeout=10
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch games from Squiggle: {response.status_code}")
                return

            data = response.json()
            games = data.get('games', [])

            # Filter for active games (0 < complete <= 100)
            # Include games at 99%+ to ensure they get properly closed out
            active_games = [g for g in games if 0 < g.get('complete', 0) <= 100]

            if active_games:
                logger.info(f"Found {len(active_games)} active games, updating...")
                for game in active_games:
                    LiveGameService.process_game_update(game, socketio=socketio)
            else:
                logger.debug("No active games found")

        except Exception as e:
            logger.error(f"Error polling live games: {e}")

    def _cleanup_old_games(self):
        """Remove completed games older than 7 days."""
        try:
            cutoff = datetime.utcnow() - timedelta(days=7)

            with get_session() as session:
                deleted_count = (
                    session.query(LiveGame)
                    .filter(
                        LiveGame.status == "completed", LiveGame.last_updated < cutoff
                    )
                    .delete()
                )

                session.commit()

                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old completed games")

        except Exception as e:
            logger.error(f"Error in cleanup job: {e}")

    def _health_check(self):
        """Verify SSE listener is running, restart if needed."""
        try:
            if not self.sse_listener:
                return

            if not self.sse_listener.is_running:
                logger.warning("SSE listener not running, restarting...")
                self.sse_listener.start()

        except Exception as e:
            logger.error(f"Error in health check: {e}")

    def _fetch_rss_news(self):
        """Hourly: Fetch RSS feeds."""
        try:
            from app.data.ingestion.rss_news_fetcher import RSSNewsFetcher

            articles_added = RSSNewsFetcher.fetch_all_feeds()
            logger.info(f"RSS job complete: {articles_added} new articles")
        except Exception as e:
            logger.error(f"RSS job failed: {e}")

    def _update_betting_odds(self):
        """Update odds with single efficient API call."""
        try:
            from app.data.ingestion.odds_fetcher import OddsFetcher

            requests_made = OddsFetcher.update_upcoming_matches(days_ahead=7)
            logger.info(f"Odds job complete: {requests_made} API request(s)")
        except Exception as e:
            logger.error(f"Odds job failed: {e}")

    def _update_squiggle_predictions(self):
        """Daily: Update predictions."""
        try:
            from app.data.ingestion.squiggle_fetcher import SquiggleFetcher

            predictions = SquiggleFetcher.fetch_current_round_predictions()
            logger.info(f"Predictions job complete: {predictions} updated")
        except Exception as e:
            logger.error(f"Predictions job failed: {e}")

    def _update_current_season_matches(self):
        """Daily 11 PM AEST: Fetch current season results from Squiggle API.

        Inserts any new matches (e.g. upcoming rounds added to schedule) and
        updates scores for games that were previously 'scheduled' but are now
        complete. Squiggle is free with no rate limits so this is safe to run
        nightly.
        """
        try:
            from app.data.ingestion.afl_tables import AFLTablesIngester

            current_year = datetime.utcnow().year
            ingester = AFLTablesIngester()
            ingester._scrape_season_from_squiggle(current_year)
            logger.info(f"Match results job complete: {current_year} season synced from Squiggle")
        except Exception as e:
            logger.error(f"Match results job failed: {e}")


# Global singleton
_scheduler_instance = None


def get_scheduler(sse_listener=None):
    """Get or create global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = LiveGameScheduler(sse_listener=sse_listener)
    return _scheduler_instance
