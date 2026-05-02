"""
Re-scrape Footywire stats for completed games and regenerate AI summaries.

Run from backend/ with:
  python -m scripts.refresh_completed_game_stats

Options:
  --dry-run   Show what would be done without updating the DB
  --game-id N  Only process a specific live_game.id
"""
import logging
import sys
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Silence SQLAlchemy noise
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def run(dry_run: bool = False, game_id: int = None):
    from app import create_app
    app = create_app()

    with app.app_context():
        from app.data.database import get_session
        from app.data.models import LiveGame
        from app.data.ingestion.footywire_scraper import FootywireScraper
        from app.services.game_summary_service import GameSummaryService
        from sqlalchemy.orm import joinedload

        scraper = FootywireScraper()

        with get_session() as session:
            q = session.query(LiveGame).options(
                joinedload(LiveGame.home_team),
                joinedload(LiveGame.away_team),
            ).filter(LiveGame.status == 'completed')

            if game_id:
                q = q.filter(LiveGame.id == game_id)

            games = q.order_by(LiveGame.last_updated.desc()).all()

        logger.info(f"Found {len(games)} completed game(s) to process")

        for game in games:
            home = game.home_team.name
            away = game.away_team.name
            label = f"Game {game.id}: {home} vs {away} ({game.season})"
            logger.info(f"Processing {label}")

            stats = scraper.get_top_performers(game.season, home, away)

            if not stats:
                logger.warning(f"  No stats found for {label} — skipping summary regeneration")
                continue

            logger.info(f"  Scraped {len(stats.get('all_players', []))} players")
            top = stats.get('top_goal_kickers', [])
            if top:
                logger.info(f"  Top scorer: {top[0]['name']} ({top[0]['goals']} goals)")

            if dry_run:
                logger.info(f"  [dry-run] Would update stats_cache and regenerate summaries")
                continue

            # Update stats_cache
            with get_session() as session:
                g = session.query(LiveGame).filter(LiveGame.id == game.id).one()
                cache = dict(stats)
                cache['stats_as_of_quarter'] = 4
                cache['stats_scraped_at'] = datetime.utcnow().isoformat() + 'Z'
                g.stats_cache = cache
                g.stats_cache_updated_at = datetime.utcnow()

                # Regenerate main AI summary
                summary = GameSummaryService.generate_summary(g, player_stats=stats)
                if summary:
                    g.ai_summary = summary
                    logger.info(f"  Summary: {summary[:80]}...")

                # Regenerate post-game analysis
                analysis = GameSummaryService.generate_post_game_analysis_from_stats(home, away, stats)
                if analysis:
                    g.post_game_analysis = analysis
                    logger.info(f"  Analysis: {analysis[:80]}...")

                session.commit()
                logger.info(f"  Saved.")

            # Be a good citizen — pause between games
            time.sleep(2)

    logger.info("Done.")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    game_id = None
    for i, arg in enumerate(sys.argv):
        if arg == '--game-id' and i + 1 < len(sys.argv):
            game_id = int(sys.argv[i + 1])

    run(dry_run=dry_run, game_id=game_id)
