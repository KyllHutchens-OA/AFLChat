"""
Backfill player names for existing live game events using API-Sports data.
This script attempts to match events to players based on their goal/behind counts.

Run with: python -m scripts.backfill_event_players
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def backfill_events():
    """Backfill player names for events in the current live game."""
    from app.data.database import get_session
    from app.data.models import LiveGame, LiveGameEvent, Team
    from app.services.api_sports_service import APISportsService

    # Get the current live game info first
    with get_session() as session:
        live_game = session.query(LiveGame).filter(
            LiveGame.status.in_(['live', 'completed'])
        ).order_by(LiveGame.last_updated.desc()).first()

        if not live_game:
            logger.info("No active live game found")
            return

        # Extract all needed info before session closes
        game_id = live_game.id
        home_team_id = live_game.home_team_id
        away_team_id = live_game.away_team_id
        home_team_name = live_game.home_team.name
        away_team_name = live_game.away_team.name
        home_team_abbr = live_game.home_team.abbreviation
        away_team_abbr = live_game.away_team.abbreviation

    logger.info(f"Backfilling events for: {home_team_name} vs {away_team_name}")
    logger.info(f"Game ID: {game_id}")

    # Get API-Sports game
    api_game = APISportsService.get_game_by_teams(home_team_abbr, away_team_abbr)

    if not api_game:
        logger.error("Could not find game in API-Sports")
        return

    api_game_id = api_game['game']['id']
    logger.info(f"API-Sports Game ID: {api_game_id}")

    # Get player stats
    stats = APISportsService.get_game_player_stats(api_game_id)
    if not stats:
        logger.error("Could not get player stats")
        return

    # Build scorer lookup: team_id -> list of {player_id, name, goals, behinds}
    home_api_id = APISportsService.get_team_api_id(home_team_abbr)
    away_api_id = APISportsService.get_team_api_id(away_team_abbr)

    scorers = {
        home_team_id: [],
        away_team_id: [],
    }

    for team_data in stats.get('teams', []):
        team_api_id = team_data['team']['id']
        team_db_id = home_team_id if team_api_id == home_api_id else away_team_id

        for player in team_data.get('players', []):
            goals = player.get('goals', {}).get('total', 0)
            behinds = player.get('behinds', 0)

            if goals > 0 or behinds > 0:
                player_id = player['player']['id']
                cached = APISportsService.get_cached_player(player_id)
                name = cached.get('name', 'Unknown') if cached else 'Unknown'

                scorers[team_db_id].append({
                    'player_id': player_id,
                    'name': name,
                    'goals': goals,
                    'behinds': behinds,
                    'assigned_goals': 0,
                    'assigned_behinds': 0,
                })

    # Sort scorers by total scoring (goals first, then behinds)
    for tid in scorers:
        scorers[tid].sort(key=lambda x: (x['goals'], x['behinds']), reverse=True)

    logger.info(f"\nHome team scorers: {[s['name'] for s in scorers[home_team_id]]}")
    logger.info(f"Away team scorers: {[s['name'] for s in scorers[away_team_id]]}")

    # Now update events in a new session
    with get_session() as session:
        # Get events ordered by timestamp (oldest first for assignment)
        events = session.query(LiveGameEvent).filter_by(
            game_id=game_id
        ).order_by(LiveGameEvent.timestamp.asc()).all()

        logger.info(f"\nProcessing {len(events)} events...")

        updated_count = 0
        for event in events:
            if event.player_name:
                continue  # Already has player name

            if event.event_type not in ['goal', 'behind']:
                continue

            team_scorers = scorers.get(event.team_id, [])
            if not team_scorers:
                continue

            # Find a player who still has unassigned goals/behinds
            assigned = False
            for scorer in team_scorers:
                if event.event_type == 'goal':
                    if scorer['assigned_goals'] < scorer['goals']:
                        event.player_name = scorer['name']
                        event.player_api_sports_id = scorer['player_id']
                        scorer['assigned_goals'] += 1
                        assigned = True
                        break
                else:  # behind
                    if scorer['assigned_behinds'] < scorer['behinds']:
                        event.player_name = scorer['name']
                        event.player_api_sports_id = scorer['player_id']
                        scorer['assigned_behinds'] += 1
                        assigned = True
                        break

            if assigned:
                updated_count += 1
                logger.info(f"  {event.event_type}: {event.player_name} ({event.team.abbreviation})")

        session.commit()
        logger.info(f"\nUpdated {updated_count} events with player names")


if __name__ == "__main__":
    backfill_events()
