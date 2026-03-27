"""
API-Sports Service - Integration with API-Sports AFL API for player statistics.
Handles player caching, team mappings, and live game statistics.
"""
import logging
import os
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.data.database import get_session
from app.data.models import APISportsPlayer, APISportsTeamMapping, Team

logger = logging.getLogger(__name__)

# In-memory player name cache to avoid repeated DB round-trips
_player_name_cache: Dict[int, Dict] = {}  # api_sports_id -> player dict

# API-Sports configuration
API_SPORTS_BASE_URL = "https://v1.afl.api-sports.io"
API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")

# Team ID mapping: API-Sports ID -> Team abbreviation
# This maps API-Sports team IDs to our database team abbreviations
API_SPORTS_TEAM_MAP = {
    1: "ADE",   # Adelaide Crows
    2: "BRI",   # Brisbane Lions
    3: "CAR",   # Carlton Blues
    4: "COL",   # Collingwood Magpies
    5: "ESS",   # Essendon Bombers
    6: "FRE",   # Fremantle Dockers
    7: "GEE",   # Geelong Cats
    8: "HAW",   # Hawthorn Hawks
    9: "MEL",   # Melbourne Demons
    10: "NM",   # North Melbourne Kangaroos
    11: "PA",   # Port Adelaide Power
    12: "RIC",  # Richmond Tigers
    13: "STK",  # St Kilda Saints
    14: "SYD",  # Sydney Swans
    15: "WCE",  # West Coast Eagles
    16: "WB",   # Western Bulldogs
    17: "GCS",  # Gold Coast Suns
    18: "GWS",  # Greater Western Sydney Giants
}


class APISportsService:
    """Service for interacting with API-Sports AFL API."""

    @staticmethod
    def _make_request(endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a request to the API-Sports API."""
        if not API_SPORTS_KEY:
            logger.error("API_SPORTS_KEY not configured")
            return None

        headers = {"x-apisports-key": API_SPORTS_KEY}
        url = f"{API_SPORTS_BASE_URL}/{endpoint}"

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("errors") and any(data["errors"].values()):
                logger.warning(f"API-Sports errors: {data['errors']}")

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"API-Sports request failed: {e}")
            return None

    @staticmethod
    def get_player_by_id(player_id: int) -> Optional[Dict]:
        """Fetch a single player by ID from API-Sports."""
        data = APISportsService._make_request("players", {"id": player_id})
        if data and data.get("response"):
            return data["response"][0]
        return None

    @staticmethod
    def get_team_players(team_id: int, season: int = 2024) -> List[Dict]:
        """Fetch all players for a team from API-Sports."""
        data = APISportsService._make_request("players", {"team": team_id, "season": season})
        if data and data.get("response"):
            return data["response"]
        return []

    @staticmethod
    def get_live_games(date: Optional[str] = None) -> List[Dict]:
        """Fetch games from API-Sports for a specific date.

        Args:
            date: Date string in YYYY-MM-DD format. Defaults to today.
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        data = APISportsService._make_request("games", {"date": date})
        if data and data.get("response"):
            return data["response"]
        return []

    @staticmethod
    def get_game_player_stats(game_id: int) -> Optional[Dict]:
        """Fetch player statistics for a specific game."""
        data = APISportsService._make_request("games/statistics/players", {"id": game_id})
        if data and data.get("response"):
            return data["response"][0] if data["response"] else None
        return None

    @staticmethod
    def cache_player(player_id: int, name: str = None, team_api_id: int = None) -> Optional[Dict]:
        """
        Cache a player in the database. If name not provided, fetch from API.

        Args:
            player_id: API-Sports player ID
            name: Player name (optional, will fetch if not provided)
            team_api_id: API-Sports team ID (optional)

        Returns:
            Dict with player info or None
        """
        with get_session() as session:
            # Check if already cached
            existing = session.query(APISportsPlayer).filter_by(
                api_sports_id=player_id
            ).first()

            if existing:
                return {
                    "id": existing.id,
                    "api_sports_id": existing.api_sports_id,
                    "name": existing.name,
                    "team_id": existing.team_id,
                }

            # Fetch name from API if not provided
            if not name:
                player_data = APISportsService.get_player_by_id(player_id)
                if not player_data:
                    logger.warning(f"Could not fetch player {player_id}")
                    return None
                name = player_data.get("name", "Unknown")

            # Map API-Sports team to our team
            team_id = None
            if team_api_id:
                team_abbr = API_SPORTS_TEAM_MAP.get(team_api_id)
                if team_abbr:
                    team = session.query(Team).filter_by(abbreviation=team_abbr).first()
                    if team:
                        team_id = team.id

            try:
                player = APISportsPlayer(
                    api_sports_id=player_id,
                    name=name,
                    team_api_sports_id=team_api_id,
                    team_id=team_id,
                )
                session.add(player)
                session.flush()
            except Exception:
                # Concurrent request already inserted this player — re-fetch
                session.rollback()
                player = session.query(APISportsPlayer).filter_by(
                    api_sports_id=player_id
                ).first()
                if not player:
                    return None

            result = {
                "id": player.id,
                "api_sports_id": player.api_sports_id,
                "name": player.name,
                "team_id": player.team_id,
            }

            session.commit()
            logger.info(f"Cached player: {name} (ID: {player_id})")
            return result

    @staticmethod
    def get_cached_player(player_id: int) -> Optional[Dict]:
        """Get a player from cache, fetching and caching if not found.

        Returns a dict with player info to avoid session detachment issues.
        Uses in-memory cache to avoid repeated DB round-trips.
        """
        global _player_name_cache

        # Check in-memory cache first (avoids DB round-trip)
        if player_id in _player_name_cache:
            return _player_name_cache[player_id]

        with get_session() as session:
            player = session.query(APISportsPlayer).filter_by(
                api_sports_id=player_id
            ).first()

            if player:
                result = {
                    "id": player.id,
                    "api_sports_id": player.api_sports_id,
                    "name": player.name,
                    "team_id": player.team_id,
                }
                _player_name_cache[player_id] = result
                return result

        # Not in cache, fetch and cache (cache_player now returns a dict)
        result = APISportsService.cache_player(player_id)
        if result:
            _player_name_cache[player_id] = result
        return result

    @staticmethod
    def get_player_name(player_id: int) -> str:
        """Get player name by ID, using cache or fetching from API."""
        player = APISportsService.get_cached_player(player_id)
        return player.get("name", "Unknown") if player else "Unknown"

    @staticmethod
    def cache_all_teams(season: int = 2024) -> int:
        """
        Cache all players from all teams for a given season.

        Args:
            season: AFL season year

        Returns:
            Number of players cached
        """
        total_cached = 0

        for api_team_id, team_abbr in API_SPORTS_TEAM_MAP.items():
            logger.info(f"Caching players for {team_abbr} (API ID: {api_team_id})...")

            players = APISportsService.get_team_players(api_team_id, season)

            with get_session() as session:
                # Get our team ID
                team = session.query(Team).filter_by(abbreviation=team_abbr).first()
                team_id = team.id if team else None

                for player_data in players:
                    player_api_id = player_data.get("id")
                    player_name = player_data.get("name")

                    # Check if already exists
                    existing = session.query(APISportsPlayer).filter_by(
                        api_sports_id=player_api_id
                    ).first()

                    if existing:
                        continue

                    player = APISportsPlayer(
                        api_sports_id=player_api_id,
                        name=player_name,
                        team_api_sports_id=api_team_id,
                        team_id=team_id,
                    )
                    session.add(player)
                    total_cached += 1

                session.commit()

            logger.info(f"  Cached {len(players)} players for {team_abbr}")

        logger.info(f"Total players cached: {total_cached}")
        return total_cached

    @staticmethod
    def find_goal_scorer(
        game_stats: Dict,
        team_api_id: int,
        prev_goals: int,
        current_goals: int
    ) -> Optional[Dict]:
        """
        Find the player who scored a goal by comparing goal counts.

        Args:
            game_stats: Player statistics for the game
            team_api_id: API-Sports team ID
            prev_goals: Previous team goals count
            current_goals: Current team goals count

        Returns:
            Dict with player info or None
        """
        if not game_stats or "teams" not in game_stats:
            return None

        # Find the team's players
        for team_data in game_stats.get("teams", []):
            if team_data.get("team", {}).get("id") != team_api_id:
                continue

            # Look for player with goals matching the increase
            # This is a heuristic - we find players with goals > 0
            # and return the one most likely to have just scored
            goal_scorers = []
            for player in team_data.get("players", []):
                goals = player.get("goals", {}).get("total", 0)
                if goals > 0:
                    goal_scorers.append({
                        "player_id": player.get("player", {}).get("id"),
                        "jersey_number": player.get("player", {}).get("number"),
                        "goals": goals,
                    })

            # Sort by goals descending - most goals likely includes recent scorer
            goal_scorers.sort(key=lambda x: x["goals"], reverse=True)

            if goal_scorers:
                # Get player name
                scorer = goal_scorers[0]
                player = APISportsService.get_cached_player(scorer["player_id"])
                if player:
                    return {
                        "player_id": scorer["player_id"],
                        "player_name": player.get("name", "Unknown"),
                        "jersey_number": scorer["jersey_number"],
                        "total_goals": scorer["goals"],
                    }

        return None

    @staticmethod
    def get_game_by_teams(home_team_abbr: str, away_team_abbr: str, game_date: Optional[str] = None) -> Optional[Dict]:
        """
        Find game by team abbreviations and date.

        Args:
            home_team_abbr: Home team abbreviation (e.g., "CAR")
            away_team_abbr: Away team abbreviation (e.g., "RIC")
            game_date: Date string in YYYY-MM-DD format. Defaults to today.

        Returns:
            Game data or None
        """
        # Reverse lookup: abbreviation -> API-Sports ID
        abbr_to_api_id = {v: k for k, v in API_SPORTS_TEAM_MAP.items()}

        home_api_id = abbr_to_api_id.get(home_team_abbr)
        away_api_id = abbr_to_api_id.get(away_team_abbr)

        if not home_api_id or not away_api_id:
            return None

        games = APISportsService.get_live_games(date=game_date)
        for game in games:
            teams = game.get("teams", {})
            if (teams.get("home", {}).get("id") == home_api_id and
                teams.get("away", {}).get("id") == away_api_id):
                return game

        return None

    @staticmethod
    def get_team_api_id(team_abbr: str) -> Optional[int]:
        """Get API-Sports team ID from our team abbreviation."""
        abbr_to_api_id = {v: k for k, v in API_SPORTS_TEAM_MAP.items()}
        return abbr_to_api_id.get(team_abbr)

    @staticmethod
    def fetch_game_stats(game) -> Optional[Dict]:
        """Fetch and process player stats for a LiveGame ORM object.

        Args:
            game: LiveGame ORM object with home_team and away_team relationships loaded.

        Returns:
            Dict with top_goal_kickers, top_disposals, top_fantasy lists, or None if unavailable.
        """
        try:
            game_date = game.match_date.strftime('%Y-%m-%d') if game.match_date else None

            api_game = APISportsService.get_game_by_teams(
                game.home_team.abbreviation,
                game.away_team.abbreviation,
                game_date,
            )

            if not api_game:
                return None

            api_game_id = api_game.get('game', {}).get('id') or api_game.get('id')
            stats_data = APISportsService.get_game_player_stats(api_game_id)

            if not stats_data:
                return None

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
                        cached_player = APISportsService.get_cached_player(player_id)
                        if cached_player:
                            player_name = cached_player.get('name', 'Unknown')
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

            return {
                'top_goal_kickers': [{'name': p['name'], 'team': p['team'], 'goals': p['goals']} for p in top_goals],
                'top_disposals': [{'name': p['name'], 'team': p['team'], 'disposals': p['disposals']} for p in top_disposals],
                'top_fantasy': [{'name': p['name'], 'team': p['team'], 'points': p['fantasy']} for p in top_fantasy],
            }

        except Exception as e:
            logger.error(f"Error in fetch_game_stats for game {getattr(game, 'id', '?')}: {e}")
            return None
