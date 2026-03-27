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

        # Job 2: Poll for live games (every 15 seconds)
        self.scheduler.add_job(
            func=self._poll_live_games,
            trigger=IntervalTrigger(seconds=15),
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

        # Job 7: Pre-fetch player stats for live and recently completed games (every 2 minutes)
        self.scheduler.add_job(
            func=self._prefetch_stats,
            trigger=IntervalTrigger(minutes=2),
            id="prefetch_stats",
            name="Pre-fetch player stats for live and recent games",
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

        # Job 9: Sync team stats from API-Sports (Tuesday at 6 AM AEST)
        self.scheduler.add_job(
            func=self._sync_round_team_stats,
            trigger=CronTrigger(day_of_week='tue', hour=6, minute=0, timezone='Australia/Melbourne'),
            id="sync_round_team_stats",
            name="Sync team stats from API-Sports",
            replace_existing=True,
        )

        # Job 11: Save preview context for upcoming matches (7 AM and 5 PM AEST)
        # Fetches Squiggle games + weather + DB context, saves pending rows
        # for the Claude cloud scheduled task to fill in with preview text.
        self.scheduler.add_job(
            func=self._save_preview_context,
            trigger=CronTrigger(hour=7, minute=0, timezone='Australia/Melbourne'),
            id="save_preview_context_morning",
            name="Save preview context (morning)",
            replace_existing=True,
        )
        self.scheduler.add_job(
            func=self._save_preview_context,
            trigger=CronTrigger(hour=17, minute=0, timezone='Australia/Melbourne'),
            id="save_preview_context_evening",
            name="Save preview context (evening)",
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
            import time
            from app.services.live_game_service import LiveGameService
            from app import socketio

            # Fetch games from Squiggle API (retry once on failure)
            current_year = datetime.now().year
            response = None
            for attempt in range(2):
                try:
                    response = requests.get(
                        f"https://api.squiggle.com.au/?q=games;year={current_year}",
                        headers={"User-Agent": "AFL-Analytics-App/1.0 (kyllhutchens@gmail.com)"},
                        timeout=10
                    )
                    if response.status_code == 200:
                        break
                    logger.warning(f"Squiggle returned {response.status_code} (attempt {attempt + 1}/2)")
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Squiggle request failed (attempt {attempt + 1}/2): {e}")
                if attempt == 0:
                    time.sleep(2)

            if not response or response.status_code != 200:
                logger.error(f"Failed to fetch games from Squiggle after 2 attempts")
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

    def _sync_round_team_stats(self):
        """Tuesday 6 AM AEST: Sync team stats from API-Sports for the most recent completed round."""
        try:
            import subprocess
            import sys

            current_year = datetime.now().year
            result = subprocess.run(
                [sys.executable, "scripts/sync_round_data.py", "--season", str(current_year)],
                capture_output=True, text=True, timeout=600,
                cwd=str(__import__('pathlib').Path(__file__).parent.parent.parent)
            )

            if result.returncode == 0:
                logger.info(f"Team stats sync complete for {current_year}")
            else:
                logger.error(f"Team stats sync failed: {result.stderr[-500:] if result.stderr else 'no output'}")

        except Exception as e:
            logger.error(f"Team stats sync job failed: {e}")

    def _save_preview_context(self):
        """Save context for upcoming match previews to DB (pending rows for cloud task)."""
        try:
            import subprocess
            import sys

            result = subprocess.run(
                [sys.executable, "scripts/generate_match_previews.py", "save"],
                capture_output=True, text=True, timeout=120,
                cwd=str(__import__('pathlib').Path(__file__).parent.parent.parent)
            )

            if result.returncode == 0:
                logger.info(f"Preview context save complete")
                if result.stderr:
                    # Log last few lines of stderr (contains info logs)
                    for line in result.stderr.strip().split('\n')[-3:]:
                        logger.info(f"  {line.split(' ', 3)[-1] if ' ' in line else line}")
            else:
                logger.error(f"Preview context save failed: {result.stderr[-500:] if result.stderr else 'no output'}")

        except Exception as e:
            logger.error(f"Preview context save job failed: {e}")

    def _prefetch_stats(self):
        """Pre-fetch and cache player stats for live and recently completed games.

        Optimized: batches API-Sports game lookups by date to minimize HTTP requests.
        """
        try:
            from app.services.api_sports_service import APISportsService
            from app.data.models import LiveGame
            from sqlalchemy.orm.attributes import flag_modified
            from sqlalchemy.orm import joinedload
            from collections import defaultdict

            with get_session() as session:
                games = session.query(LiveGame).options(
                    joinedload(LiveGame.home_team),
                    joinedload(LiveGame.away_team)
                ).filter(
                    (LiveGame.status == 'live') |
                    ((LiveGame.status == 'completed') & (LiveGame.stats_cache == None))
                ).all()

                if not games:
                    return

                now = datetime.utcnow()

                # Filter out live games refreshed recently
                games_to_fetch = []
                for game in games:
                    if game.status == 'live' and game.stats_cache_updated_at:
                        if (now - game.stats_cache_updated_at).total_seconds() < 120:
                            continue
                    games_to_fetch.append(game)

                if not games_to_fetch:
                    return

                # Group games by date and batch-fetch from API-Sports
                games_by_date = defaultdict(list)
                for game in games_to_fetch:
                    if game.match_date:
                        date_str = game.match_date.strftime('%Y-%m-%d')
                        games_by_date[date_str].append(game)

                # Build reverse lookup: abbreviation -> API-Sports ID
                from app.services.api_sports_service import API_SPORTS_TEAM_MAP
                abbr_to_api_id = {v: k for k, v in API_SPORTS_TEAM_MAP.items()}

                refreshed = 0
                for date_str, date_games in games_by_date.items():
                    try:
                        # One API call per date (not per game)
                        api_games = APISportsService.get_live_games(date=date_str)
                    except Exception as e:
                        logger.warning(f"Failed to fetch API-Sports games for {date_str}: {e}")
                        continue

                    # Index API-Sports games by (home_id, away_id) for fast lookup
                    api_game_index = {}
                    for ag in api_games:
                        teams = ag.get('teams', {})
                        key = (teams.get('home', {}).get('id'), teams.get('away', {}).get('id'))
                        api_game_index[key] = ag

                    for game in date_games:
                        try:
                            home_api_id = abbr_to_api_id.get(game.home_team.abbreviation)
                            away_api_id = abbr_to_api_id.get(game.away_team.abbreviation)
                            api_game = api_game_index.get((home_api_id, away_api_id))

                            if not api_game:
                                continue

                            api_game_id = api_game.get('game', {}).get('id') or api_game.get('id')
                            stats_data = APISportsService.get_game_player_stats(api_game_id)
                            if not stats_data:
                                continue

                            # Process stats inline (avoid re-fetching game)
                            home_team_name = api_game.get('teams', {}).get('home', {}).get('name', 'Home')
                            away_team_name = api_game.get('teams', {}).get('away', {}).get('name', 'Away')

                            all_players = []
                            for idx, team_data in enumerate(stats_data.get('teams', [])):
                                team_name = home_team_name if idx == 0 else away_team_name
                                for player in team_data.get('players', []):
                                    player_info = player.get('player', {})
                                    player_id = player_info.get('id')
                                    player_name = 'Unknown'
                                    if player_id:
                                        cached = APISportsService.get_cached_player(player_id)
                                        if cached:
                                            player_name = cached.get('name', 'Unknown')
                                    goals = player.get('goals', {}).get('total', 0) or 0
                                    behinds = player.get('behinds', 0) or 0
                                    kicks = player.get('kicks', 0) or 0
                                    handballs = player.get('handballs', 0) or 0
                                    marks = player.get('marks', 0) or 0
                                    tackles = player.get('tackles', 0) or 0
                                    hitouts = player.get('hitouts', 0) or 0
                                    free_kicks = player.get('free_kicks', {})
                                    free_for = free_kicks.get('for', 0) or 0
                                    free_against = free_kicks.get('against', 0) or 0
                                    disposals = kicks + handballs
                                    fantasy = (kicks * 3) + (handballs * 2) + (marks * 3) + (tackles * 4) + (goals * 6) + (behinds * 1) + (hitouts * 1) + (free_for * 1) + (free_against * -3)
                                    all_players.append({'name': player_name, 'team': team_name, 'goals': goals, 'disposals': disposals, 'fantasy': fantasy})

                            top_goals = [p for p in sorted(all_players, key=lambda x: x['goals'], reverse=True)[:3] if p['goals'] > 0]
                            top_disposals = [p for p in sorted(all_players, key=lambda x: x['disposals'], reverse=True)[:3] if p['disposals'] > 0]
                            top_fantasy = [p for p in sorted(all_players, key=lambda x: x['fantasy'], reverse=True)[:3] if p['fantasy'] > 0]

                            stats = {
                                'top_goal_kickers': [{'name': p['name'], 'team': p['team'], 'goals': p['goals']} for p in top_goals],
                                'top_disposals': [{'name': p['name'], 'team': p['team'], 'disposals': p['disposals']} for p in top_disposals],
                                'top_fantasy': [{'name': p['name'], 'team': p['team'], 'points': p['fantasy']} for p in top_fantasy],
                            }

                            game.stats_cache = stats
                            game.stats_cache_updated_at = now
                            flag_modified(game, 'stats_cache')
                            refreshed += 1

                        except Exception as e:
                            logger.warning(f"Failed to prefetch stats for game {game.id}: {e}")

                if refreshed:
                    logger.info(f"Pre-fetched stats for {refreshed} game(s)")

        except Exception as e:
            logger.error(f"Error in prefetch_stats job: {e}")


# Global singleton
_scheduler_instance = None


def get_scheduler(sse_listener=None):
    """Get or create global scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = LiveGameScheduler(sse_listener=sse_listener)
    return _scheduler_instance
