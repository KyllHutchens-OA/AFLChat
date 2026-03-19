"""
Backfill completed games from Squiggle API.

Use this script when the backend has been offline and missed games.
It fetches completed games from Squiggle and processes them through
LiveGameService to populate both LiveGame and Match tables.

Usage:
    python scripts/backfill_completed_games.py [--year 2026] [--rounds 1,2]
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
import requests
from datetime import datetime

from app.data.database import get_session
from app.data.models import LiveGame, Match
from app.services.live_game_service import LiveGameService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SQUIGGLE_API_URL = "https://api.squiggle.com.au"


def fetch_squiggle_games(year: int, rounds: list[int] = None) -> list[dict]:
    """
    Fetch games from Squiggle API.

    Args:
        year: Season year
        rounds: Optional list of round numbers to filter

    Returns:
        List of game data dictionaries
    """
    url = f"{SQUIGGLE_API_URL}/?q=games;year={year}"

    logger.info(f"Fetching games from Squiggle: {url}")

    response = requests.get(
        url,
        headers={"User-Agent": "AFL-Analytics-App/1.0 (backfill)"},
        timeout=30
    )
    response.raise_for_status()

    data = response.json()
    games = data.get("games", [])

    logger.info(f"Found {len(games)} total games for {year}")

    # Filter by rounds if specified
    if rounds:
        games = [g for g in games if g.get("round") in rounds]
        logger.info(f"Filtered to {len(games)} games in rounds {rounds}")

    return games


def get_existing_games(year: int) -> set[int]:
    """Get set of Squiggle game IDs already in LiveGame table."""
    with get_session() as session:
        existing = session.query(LiveGame.squiggle_game_id).filter(
            LiveGame.season == year
        ).all()
        return {g[0] for g in existing}


def get_existing_matches(year: int) -> set[tuple]:
    """Get set of (round, home_team_id, away_team_id) already in Match table."""
    with get_session() as session:
        existing = session.query(
            Match.round,
            Match.home_team_id,
            Match.away_team_id
        ).filter(Match.season == year).all()
        return {(str(m[0]), m[1], m[2]) for m in existing}


def backfill_games(year: int, rounds: list[int] = None, dry_run: bool = False):
    """
    Backfill completed games from Squiggle.

    Args:
        year: Season year
        rounds: Optional list of round numbers
        dry_run: If True, don't actually insert data
    """
    # Fetch games from Squiggle
    games = fetch_squiggle_games(year, rounds)

    # Filter for completed games only
    completed_games = [g for g in games if g.get("complete", 0) >= 99]
    logger.info(f"Found {len(completed_games)} completed games")

    if not completed_games:
        logger.info("No completed games to backfill")
        return

    # Get existing records to avoid duplicates
    existing_live_games = get_existing_games(year)
    logger.info(f"Found {len(existing_live_games)} existing LiveGame records")

    # Process each completed game
    games_added = 0
    games_updated = 0
    games_skipped = 0

    for game in completed_games:
        squiggle_id = game.get("id")
        round_num = game.get("round")
        home_team = game.get("hteam")
        away_team = game.get("ateam")
        home_score = game.get("hscore", 0)
        away_score = game.get("ascore", 0)

        logger.info(f"\nProcessing: R{round_num} {home_team} {home_score} vs {away_team} {away_score}")

        if squiggle_id in existing_live_games:
            logger.info(f"  → Already exists in LiveGame, updating...")
            action = "update"
        else:
            logger.info(f"  → New game, creating...")
            action = "create"

        if dry_run:
            logger.info(f"  → DRY RUN: Would {action}")
            continue

        try:
            # Use LiveGameService to process - this handles both LiveGame and Match creation
            LiveGameService.process_game_update(game, socketio=None)

            if action == "create":
                games_added += 1
            else:
                games_updated += 1

        except Exception as e:
            logger.error(f"  → Error processing game: {e}")
            games_skipped += 1

    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Games added:   {games_added}")
    logger.info(f"Games updated: {games_updated}")
    logger.info(f"Games skipped: {games_skipped}")


def main():
    parser = argparse.ArgumentParser(description="Backfill completed AFL games from Squiggle")
    parser.add_argument("--year", type=int, default=datetime.now().year,
                        help="Season year (default: current year)")
    parser.add_argument("--rounds", type=str, default=None,
                        help="Comma-separated list of rounds (e.g., '1,2,3')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")

    args = parser.parse_args()

    rounds = None
    if args.rounds:
        rounds = [int(r.strip()) for r in args.rounds.split(",")]

    logger.info("=" * 60)
    logger.info(f"AFL Game Backfill - {args.year}")
    if rounds:
        logger.info(f"Rounds: {rounds}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    backfill_games(args.year, rounds, args.dry_run)


if __name__ == "__main__":
    main()
