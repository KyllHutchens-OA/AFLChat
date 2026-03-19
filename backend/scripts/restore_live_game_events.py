#!/usr/bin/env python3
"""
Restore missing events for live game by querying API-Sports player statistics.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data.database import Session
from app.data.models import LiveGame, LiveGameEvent
from app.services.api_sports_service import APISportsService
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def restore_events_for_live_game():
    """Restore events for the current live game."""
    session = Session()

    try:
        # Get live game
        live_game = session.query(LiveGame).filter(LiveGame.status == 'live').first()

        if not live_game:
            logger.info("No live games found")
            return

        home_abbr = live_game.home_team.abbreviation
        away_abbr = live_game.away_team.abbreviation

        logger.info(f"Restoring events for {home_abbr} vs {away_abbr}")
        logger.info(f"Current score: {live_game.home_score}-{live_game.away_score}")

        # Get API-Sports game
        game_date = live_game.match_date.strftime("%Y-%m-%d")
        game = APISportsService.get_game_by_teams(home_abbr, away_abbr, game_date=game_date)

        if not game:
            logger.error("Could not find game in API-Sports")
            return

        api_game_id = game.get("game", {}).get("id")
        stats = APISportsService.get_game_player_stats(api_game_id)

        if not stats or "teams" not in stats:
            logger.error("Could not get player stats")
            return

        # Get current event count
        current_events = session.query(LiveGameEvent).filter(
            LiveGameEvent.game_id == live_game.id,
            LiveGameEvent.event_type == 'goal'
        ).count()

        logger.info(f"Current goal events: {current_events}")

        # Process each team's players
        events_created = 0

        for team_data in stats.get("teams", []):
            team_id = team_data.get("team", {}).get("id")
            team_abbr = None
            is_home = False

            # Determine which team this is
            home_api_id = APISportsService.get_team_api_id(home_abbr)
            away_api_id = APISportsService.get_team_api_id(away_abbr)

            if team_id == home_api_id:
                team_abbr = home_abbr
                is_home = True
                db_team_id = live_game.home_team_id
            elif team_id == away_api_id:
                team_abbr = away_abbr
                is_home = False
                db_team_id = live_game.away_team_id
            else:
                continue

            logger.info(f"\nProcessing {team_abbr} players:")

            # Get players with goals
            for player in team_data.get("players", []):
                goals = player.get("goals", {}).get("total") or 0

                if goals > 0:
                    player_id = player.get("player", {}).get("id")
                    player_obj = APISportsService.get_cached_player(player_id)
                    player_name = player_obj.get("name", "Unknown") if player_obj else "Unknown"

                    logger.info(f"  {player_name}: {goals} goals")

                    # Create an event for each goal (we don't know the exact order/time)
                    # We'll create them as a batch with estimated scores
                    for goal_num in range(1, goals + 1):
                        # Create event
                        event = LiveGameEvent(
                            game_id=live_game.id,
                            event_type='goal',
                            team_id=db_team_id,
                            player_name=player_name,
                            player_api_sports_id=player_id,
                            home_score_after=None,  # We don't know exact progression
                            away_score_after=None,
                            quarter=live_game.current_quarter or 1,
                            time_str=f"Q{live_game.current_quarter or 1}",
                            timestamp=live_game.match_date
                        )
                        session.add(event)
                        events_created += 1

        session.commit()
        logger.info(f"\n✓ Created {events_created} goal events")

    except Exception as e:
        logger.error(f"Error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    restore_events_for_live_game()
