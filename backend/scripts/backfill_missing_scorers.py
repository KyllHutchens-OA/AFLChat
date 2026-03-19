"""
Backfill missing player names for scoring events in live games.
This script will find all scoring events without player names and attempt
to fetch the player information from API-Sports using the correct game date.

Run with: python -m scripts.backfill_missing_scorers
"""
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Backfill missing player names for scoring events."""
    from app.data.database import get_session
    from app.data.models import LiveGameEvent, LiveGame
    from app.services.api_sports_service import APISportsService

    logger.info("=" * 60)
    logger.info("Backfilling Missing Player Names for Scoring Events")
    logger.info("=" * 60)

    with get_session() as session:
        # Find all scoring events without player names
        events = session.query(LiveGameEvent).filter(
            LiveGameEvent.player_name == None,
            LiveGameEvent.event_type.in_(['goal', 'behind'])
        ).all()

        logger.info(f"\nFound {len(events)} scoring events without player names")

        if not events:
            logger.info("No events to backfill!")
            return

        updated_count = 0
        failed_count = 0

        for event in events:
            # Get the game
            game = session.query(LiveGame).filter_by(id=event.game_id).first()
            if not game:
                logger.warning(f"Game {event.game_id} not found for event {event.id}")
                failed_count += 1
                continue

            # Get team abbreviations
            home_abbr = game.home_team.abbreviation
            away_abbr = game.away_team.abbreviation
            team_side = "home" if event.team_id == game.home_team_id else "away"

            # Format game date
            game_date = game.match_date.strftime("%Y-%m-%d")

            logger.info(f"\nEvent {event.id}: {home_abbr} vs {away_abbr} on {game_date}")
            logger.info(f"  Type: {event.event_type}, Team: {team_side}")

            try:
                # Get team API ID
                team_abbr = home_abbr if team_side == "home" else away_abbr
                team_api_id = APISportsService.get_team_api_id(team_abbr)

                if not team_api_id:
                    logger.warning(f"  ✗ Team {team_abbr} not found in API-Sports mapping")
                    failed_count += 1
                    continue

                # Find the game in API-Sports
                api_game = APISportsService.get_game_by_teams(
                    home_abbr, away_abbr, game_date=game_date
                )

                if not api_game:
                    logger.warning(f"  ✗ Game not found in API-Sports for {game_date}")
                    failed_count += 1
                    continue

                api_game_id = api_game.get("game", {}).get("id")
                if not api_game_id:
                    logger.warning(f"  ✗ No API game ID found")
                    failed_count += 1
                    continue

                # Get player stats
                stats = APISportsService.get_game_player_stats(api_game_id)
                if not stats or "teams" not in stats:
                    logger.warning(f"  ✗ No player stats found for game {api_game_id}")
                    failed_count += 1
                    continue

                # Find top scorer for the team
                scorer_info = None
                for team_data in stats.get("teams", []):
                    if team_data.get("team", {}).get("id") != team_api_id:
                        continue

                    # Get player with most goals who scored
                    for player in team_data.get("players", []):
                        player_id = player.get("player", {}).get("id")
                        goals = player.get("goals", {}).get("total", 0)

                        if goals > 0:
                            player_obj = APISportsService.get_cached_player(player_id)
                            scorer_info = {
                                "player_id": player_id,
                                "player_name": player_obj.get("name", "Unknown") if player_obj else "Unknown",
                                "jersey_number": player.get("player", {}).get("number"),
                                "total_goals": goals,
                            }
                            break  # Take first scorer found

                if scorer_info:
                    # Update event with player info
                    event.player_name = scorer_info["player_name"]
                    event.player_api_sports_id = scorer_info["player_id"]
                    session.flush()  # Flush to mark as dirty
                    session.commit()  # Commit immediately after each update
                    session.refresh(event)  # Refresh to ensure it's persisted
                    logger.info(f"  ✓ Updated event {event.id} with player: {scorer_info['player_name']} (ID: {event.player_api_sports_id})")
                    updated_count += 1
                else:
                    logger.warning(f"  ✗ No scorers found in stats")
                    failed_count += 1

            except Exception as e:
                logger.error(f"  ✗ Error processing event {event.id}: {e}")
                session.rollback()  # Rollback on error
                failed_count += 1

        logger.info("\n" + "=" * 60)
        logger.info(f"Backfill complete!")
        logger.info(f"  Updated: {updated_count}")
        logger.info(f"  Failed: {failed_count}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
