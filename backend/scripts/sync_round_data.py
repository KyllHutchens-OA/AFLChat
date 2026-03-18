#!/usr/bin/env python3
"""
AFL Round Data Sync Script

Comprehensive script to sync match and player statistics from API-Sports.
Run this at the end of each round to ensure the database is complete.

Features:
- Fetches all games for a round/season from API-Sports
- Populates Match table with final scores
- Populates PlayerStat table with detailed player statistics
- Populates TeamStat table with team-level statistics
- Creates Player records for new players
- Idempotent - safe to run multiple times

Usage:
    # Sync current round of current season
    python scripts/sync_round_data.py

    # Sync specific round(s)
    python scripts/sync_round_data.py --season 2026 --rounds 1,2

    # Sync all completed rounds for a season
    python scripts/sync_round_data.py --season 2026 --all-rounds

    # Dry run to see what would be synced
    python scripts/sync_round_data.py --season 2026 --rounds 1 --dry-run
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
import os
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Set, Tuple
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / '.env')

from app.data.database import get_session
from app.data.models import (
    Team, Player, Match, PlayerStat, TeamStat, LiveGame, APISportsPlayer
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API-Sports configuration
API_SPORTS_BASE_URL = "https://v1.afl.api-sports.io"
API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")

# Team ID mapping: API-Sports ID -> Team abbreviation
API_SPORTS_TEAM_MAP = {
    1: "ADE",   # Adelaide Crows
    2: "BRL",   # Brisbane Lions - Note: may need adjustment
    3: "CAR",   # Carlton Blues
    4: "COL",   # Collingwood Magpies
    5: "ESS",   # Essendon Bombers
    6: "FRE",   # Fremantle Dockers
    7: "GEE",   # Geelong Cats
    8: "HAW",   # Hawthorn Hawks
    9: "MEL",   # Melbourne Demons
    10: "NTH",  # North Melbourne Kangaroos
    11: "PTA",  # Port Adelaide Power
    12: "RIC",  # Richmond Tigers
    13: "STK",  # St Kilda Saints
    14: "SYD",  # Sydney Swans
    15: "WCE",  # West Coast Eagles
    16: "WBD",  # Western Bulldogs
    17: "GCS",  # Gold Coast Suns
    18: "GWS",  # Greater Western Sydney Giants
}

# Reverse mapping
ABBR_TO_API_SPORTS = {v: k for k, v in API_SPORTS_TEAM_MAP.items()}

# Alternative abbreviations that might exist in DB
TEAM_ABBR_ALIASES = {
    "BRL": ["BRI", "BRL"],
    "NTH": ["NM", "NTH"],
    "PTA": ["PA", "PTA"],
    "WBD": ["WB", "WBD"],
}


class APISportsClient:
    """Client for API-Sports AFL API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = API_SPORTS_BASE_URL
        self.requests_made = 0

    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a request to the API-Sports API."""
        if not self.api_key:
            logger.error("API_SPORTS_KEY not configured")
            return None

        headers = {"x-apisports-key": self.api_key}
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            self.requests_made += 1

            # Log rate limit info
            remaining = response.headers.get('x-ratelimit-requests-remaining', 'unknown')
            logger.debug(f"API request to {endpoint}, remaining calls: {remaining}")

            response.raise_for_status()
            data = response.json()

            if data.get("errors") and any(data["errors"].values()):
                logger.warning(f"API-Sports errors: {data['errors']}")
                return None

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"API-Sports request failed: {e}")
            return None

    def get_games(self, season: int, round_num: int = None, date: str = None) -> List[Dict]:
        """
        Fetch games from API-Sports.

        Args:
            season: AFL season year
            round_num: Optional round number to filter (filtered client-side via 'week' field)
            date: Optional date string (YYYY-MM-DD)

        Returns:
            List of game data
        """
        params = {"league": 1, "season": season}
        if date:
            params["date"] = date

        data = self._make_request("games", params)
        if not data or not data.get("response"):
            return []

        games = data["response"]

        # Filter by round number client-side (API-Sports uses 'week' field)
        if round_num is not None:
            games = [g for g in games if g.get("week") == round_num]

        return games

    def get_game_by_id(self, game_id: int) -> Optional[Dict]:
        """Fetch a specific game by ID."""
        data = self._make_request("games", {"id": game_id})
        if data and data.get("response"):
            return data["response"][0] if data["response"] else None
        return None

    def get_game_player_stats(self, game_id: int) -> Optional[Dict]:
        """Fetch player statistics for a game."""
        data = self._make_request("games/statistics/players", {"id": game_id})
        if data and data.get("response"):
            return data["response"][0] if data["response"] else None
        return None

    def get_game_team_stats(self, game_id: int) -> Optional[Dict]:
        """Fetch team statistics for a game."""
        data = self._make_request("games/statistics/teams", {"id": game_id})
        if data and data.get("response"):
            return data["response"]
        return None


class RoundDataSyncer:
    """Syncs round data from API-Sports to the database."""

    def __init__(self, api_client: APISportsClient, dry_run: bool = False):
        self.api = api_client
        self.dry_run = dry_run
        self.team_cache: Dict[str, int] = {}  # abbreviation -> team_id
        self.player_cache: Dict[int, int] = {}  # api_sports_id -> player_id
        self.stats = {
            "matches_created": 0,
            "matches_updated": 0,
            "player_stats_created": 0,
            "player_stats_updated": 0,
            "players_created": 0,
            "team_stats_created": 0,
            "errors": 0,
        }

    def _load_team_cache(self, session):
        """Load team ID cache from database."""
        teams = session.query(Team).all()
        for team in teams:
            self.team_cache[team.abbreviation] = team.id
            # Also cache by name for backup matching
            self.team_cache[team.name] = team.id
        logger.info(f"Loaded {len(teams)} teams into cache")

    def _get_team_id(self, api_sports_team_id: int) -> Optional[int]:
        """Get our team ID from API-Sports team ID."""
        abbr = API_SPORTS_TEAM_MAP.get(api_sports_team_id)
        if not abbr:
            return None

        # Try direct match
        if abbr in self.team_cache:
            return self.team_cache[abbr]

        # Try aliases
        for alias in TEAM_ABBR_ALIASES.get(abbr, []):
            if alias in self.team_cache:
                return self.team_cache[alias]

        return None

    def _get_or_create_player(
        self, session, api_sports_id: int, name: str, team_id: int = None
    ) -> Optional[int]:
        """Get or create a player record."""
        # Check cache first
        if api_sports_id in self.player_cache:
            return self.player_cache[api_sports_id]

        # Check if player exists by API-Sports ID in our cache table
        api_player = session.query(APISportsPlayer).filter_by(
            api_sports_id=api_sports_id
        ).first()

        if api_player:
            # Find matching player in players table
            player = session.query(Player).filter(
                Player.name.ilike(api_player.name)
            ).first()

            if player:
                self.player_cache[api_sports_id] = player.id
                return player.id

        # Try to find player by name
        player = session.query(Player).filter(
            Player.name.ilike(name)
        ).first()

        if player:
            self.player_cache[api_sports_id] = player.id

            # Cache the API-Sports mapping
            if not api_player:
                api_player = APISportsPlayer(
                    api_sports_id=api_sports_id,
                    name=name,
                    team_id=team_id
                )
                session.add(api_player)

            return player.id

        # Create new player if not found
        if self.dry_run:
            logger.info(f"  [DRY RUN] Would create player: {name}")
            return None

        # Parse name into first/last
        name_parts = name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        player = Player(
            name=name,
            first_name=first_name,
            last_name=last_name,
            team_id=team_id,
            is_active=True
        )
        session.add(player)
        session.flush()

        self.player_cache[api_sports_id] = player.id
        self.stats["players_created"] += 1
        logger.info(f"  Created new player: {name} (ID: {player.id})")

        # Also cache in API-Sports player table
        api_player = APISportsPlayer(
            api_sports_id=api_sports_id,
            name=name,
            team_id=team_id
        )
        session.add(api_player)

        return player.id

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _parse_game_date(self, date_str: str) -> datetime:
        """Parse date string from API-Sports."""
        # Format: "2024-03-14T09:40:00+00:00" or similar
        try:
            # Try ISO format with timezone
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            # Try simple date format
            return datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return datetime.utcnow()

    def _extract_round_number(self, round_str: str) -> str:
        """Extract round number from API-Sports round string."""
        # Format: "Regular Season - 1" or just "1"
        if not round_str:
            return "0"

        if " - " in round_str:
            return round_str.split(" - ")[-1]

        # Handle finals
        finals_map = {
            "Qualifying Final": "QF",
            "Elimination Final": "EF",
            "Semi Final": "SF",
            "Preliminary Final": "PF",
            "Grand Final": "GF",
        }
        for key, value in finals_map.items():
            if key in round_str:
                return value

        return round_str

    def sync_game(self, session, game: Dict) -> bool:
        """
        Sync a single game and its statistics.

        Returns True if successful.
        """
        # API-Sports nests game ID inside 'game' object
        game_id = game.get("game", {}).get("id")
        if not game_id:
            logger.warning("Game missing ID, skipping")
            return False

        # Check game status - only sync completed games
        status = game.get("status", {})
        if status.get("short") not in ["FT", "AOT", "AET"]:  # Full Time, After Over Time, After Extra Time
            logger.debug(f"Game {game_id} not completed (status: {status.get('short')}), skipping")
            return False

        # Extract game info
        teams_data = game.get("teams", {})
        home_api_id = teams_data.get("home", {}).get("id")
        away_api_id = teams_data.get("away", {}).get("id")

        home_team_id = self._get_team_id(home_api_id)
        away_team_id = self._get_team_id(away_api_id)

        if not home_team_id or not away_team_id:
            logger.warning(f"Could not map teams for game {game_id}: {home_api_id} vs {away_api_id}")
            self.stats["errors"] += 1
            return False

        # Get scores - API-Sports uses 'score' not 'total'
        scores = game.get("scores", {})
        home_score = self._safe_int(scores.get("home", {}).get("score"))
        away_score = self._safe_int(scores.get("away", {}).get("score"))

        # Get goals/behinds from scores
        home_goals = self._safe_int(scores.get("home", {}).get("goals"))
        home_behinds = self._safe_int(scores.get("home", {}).get("behinds"))
        away_goals = self._safe_int(scores.get("away", {}).get("goals"))
        away_behinds = self._safe_int(scores.get("away", {}).get("behinds"))

        # Get quarter scores if available (may be in a separate structure)
        home_quarters = scores.get("home", {}).get("quarters", {})
        away_quarters = scores.get("away", {}).get("quarters", {})

        # Parse other fields - season is in league object, round is 'week'
        season = game.get("league", {}).get("season") or game.get("season")
        round_num = str(game.get("week", 0))  # API-Sports uses 'week' for round number
        venue = game.get("venue")  # venue is a string, not an object
        match_date = self._parse_game_date(game.get("date", ""))

        home_team_name = teams_data.get("home", {}).get("name", "")
        away_team_name = teams_data.get("away", {}).get("name", "")

        logger.info(f"Syncing: R{round_num} {home_team_name} {home_score} vs {away_team_name} {away_score}")

        if self.dry_run:
            logger.info(f"  [DRY RUN] Would create/update match and stats")
            return True

        # Find or create Match record
        match = session.query(Match).filter_by(
            season=season,
            round=round_num,
            home_team_id=home_team_id,
            away_team_id=away_team_id
        ).first()

        if match:
            # Update existing match
            match.home_score = home_score
            match.away_score = away_score
            match.match_status = "completed"
            match.venue = venue or match.venue
            match.match_date = match_date or match.match_date

            # Update quarter scores if available
            if home_quarters:
                match.home_q1_goals = self._safe_int(home_quarters.get("1", {}).get("goals"))
                match.home_q1_behinds = self._safe_int(home_quarters.get("1", {}).get("behinds"))
                match.home_q2_goals = self._safe_int(home_quarters.get("2", {}).get("goals"))
                match.home_q2_behinds = self._safe_int(home_quarters.get("2", {}).get("behinds"))
                match.home_q3_goals = self._safe_int(home_quarters.get("3", {}).get("goals"))
                match.home_q3_behinds = self._safe_int(home_quarters.get("3", {}).get("behinds"))
                match.home_q4_goals = self._safe_int(home_quarters.get("4", {}).get("goals"))
                match.home_q4_behinds = self._safe_int(home_quarters.get("4", {}).get("behinds"))
            elif home_goals is not None:
                # No quarter breakdown, but we have final goals/behinds - store in Q4
                match.home_q4_goals = home_goals
                match.home_q4_behinds = home_behinds

            if away_quarters:
                match.away_q1_goals = self._safe_int(away_quarters.get("1", {}).get("goals"))
                match.away_q1_behinds = self._safe_int(away_quarters.get("1", {}).get("behinds"))
                match.away_q2_goals = self._safe_int(away_quarters.get("2", {}).get("goals"))
                match.away_q2_behinds = self._safe_int(away_quarters.get("2", {}).get("behinds"))
                match.away_q3_goals = self._safe_int(away_quarters.get("3", {}).get("goals"))
                match.away_q3_behinds = self._safe_int(away_quarters.get("3", {}).get("behinds"))
                match.away_q4_goals = self._safe_int(away_quarters.get("4", {}).get("goals"))
                match.away_q4_behinds = self._safe_int(away_quarters.get("4", {}).get("behinds"))
            elif away_goals is not None:
                # No quarter breakdown, but we have final goals/behinds - store in Q4
                match.away_q4_goals = away_goals
                match.away_q4_behinds = away_behinds

            self.stats["matches_updated"] += 1
            logger.info(f"  Updated match (ID: {match.id})")
        else:
            # Create new match
            match = Match(
                season=season,
                round=round_num,
                match_date=match_date,
                venue=venue,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_score=home_score,
                away_score=away_score,
                match_status="completed",
            )

            # Add quarter scores if available
            if home_quarters:
                match.home_q1_goals = self._safe_int(home_quarters.get("1", {}).get("goals"))
                match.home_q1_behinds = self._safe_int(home_quarters.get("1", {}).get("behinds"))
                match.home_q2_goals = self._safe_int(home_quarters.get("2", {}).get("goals"))
                match.home_q2_behinds = self._safe_int(home_quarters.get("2", {}).get("behinds"))
                match.home_q3_goals = self._safe_int(home_quarters.get("3", {}).get("goals"))
                match.home_q3_behinds = self._safe_int(home_quarters.get("3", {}).get("behinds"))
                match.home_q4_goals = self._safe_int(home_quarters.get("4", {}).get("goals"))
                match.home_q4_behinds = self._safe_int(home_quarters.get("4", {}).get("behinds"))
            elif home_goals is not None:
                # No quarter breakdown - store final goals/behinds in Q4
                match.home_q4_goals = home_goals
                match.home_q4_behinds = home_behinds

            if away_quarters:
                match.away_q1_goals = self._safe_int(away_quarters.get("1", {}).get("goals"))
                match.away_q1_behinds = self._safe_int(away_quarters.get("1", {}).get("behinds"))
                match.away_q2_goals = self._safe_int(away_quarters.get("2", {}).get("goals"))
                match.away_q2_behinds = self._safe_int(away_quarters.get("2", {}).get("behinds"))
                match.away_q3_goals = self._safe_int(away_quarters.get("3", {}).get("goals"))
                match.away_q3_behinds = self._safe_int(away_quarters.get("3", {}).get("behinds"))
                match.away_q4_goals = self._safe_int(away_quarters.get("4", {}).get("goals"))
                match.away_q4_behinds = self._safe_int(away_quarters.get("4", {}).get("behinds"))
            elif away_goals is not None:
                # No quarter breakdown - store final goals/behinds in Q4
                match.away_q4_goals = away_goals
                match.away_q4_behinds = away_behinds

            session.add(match)
            session.flush()
            self.stats["matches_created"] += 1
            logger.info(f"  Created match (ID: {match.id})")

        # Sync player statistics
        self._sync_player_stats(session, game_id, match.id, home_team_id, away_team_id)

        # Sync team statistics
        self._sync_team_stats(session, game_id, match.id, home_team_id, away_team_id)

        # Update LiveGame if exists
        live_game = session.query(LiveGame).filter(
            LiveGame.season == season,
            LiveGame.round == round_num,
            LiveGame.home_team_id == home_team_id,
            LiveGame.away_team_id == away_team_id
        ).first()

        if live_game and not live_game.match_id:
            live_game.match_id = match.id
            live_game.status = "completed"
            logger.info(f"  Linked LiveGame {live_game.id} to Match {match.id}")

        return True

    def _sync_player_stats(
        self, session, api_game_id: int, match_id: int,
        home_team_id: int, away_team_id: int
    ):
        """Sync player statistics for a game."""
        stats_data = self.api.get_game_player_stats(api_game_id)
        if not stats_data:
            logger.warning(f"  No player stats available for game {api_game_id}")
            return

        teams_data = stats_data.get("teams", [])

        for team_data in teams_data:
            api_team_id = team_data.get("team", {}).get("id")
            team_id = self._get_team_id(api_team_id)

            if not team_id:
                continue

            players = team_data.get("players", [])
            logger.info(f"  Processing {len(players)} players for team {api_team_id}")

            for player_data in players:
                player_info = player_data.get("player", {})
                api_player_id = player_info.get("id")
                player_name = player_info.get("name", "Unknown")

                if not api_player_id:
                    continue

                # Get or create player
                player_id = self._get_or_create_player(
                    session, api_player_id, player_name, team_id
                )

                if not player_id:
                    continue

                # Extract statistics - API-Sports structure:
                # Most stats are top-level numbers, some are nested
                goals_data = player_data.get("goals", {})
                frees_data = player_data.get("free_kicks", {})

                # Check if player stat already exists
                existing_stat = session.query(PlayerStat).filter_by(
                    match_id=match_id,
                    player_id=player_id
                ).first()

                stat_values = {
                    # Goals are nested: goals.total
                    "goals": self._safe_int(goals_data.get("total") if isinstance(goals_data, dict) else goals_data),
                    # Behinds is top-level number
                    "behinds": self._safe_int(player_data.get("behinds")),
                    # These are all top-level numbers
                    "disposals": self._safe_int(player_data.get("disposals")),
                    "kicks": self._safe_int(player_data.get("kicks")),
                    "handballs": self._safe_int(player_data.get("handballs")),
                    "marks": self._safe_int(player_data.get("marks")),
                    "tackles": self._safe_int(player_data.get("tackles")),
                    "hitouts": self._safe_int(player_data.get("hitouts")),
                    "clearances": self._safe_int(player_data.get("clearances")),
                    # Free kicks are nested: free_kicks.for, free_kicks.against
                    "free_kicks_for": self._safe_int(frees_data.get("for") if isinstance(frees_data, dict) else None),
                    "free_kicks_against": self._safe_int(frees_data.get("against") if isinstance(frees_data, dict) else None),
                    # These may or may not be available
                    "contested_possessions": self._safe_int(player_data.get("contested_possessions")),
                    "uncontested_possessions": self._safe_int(player_data.get("uncontested_possessions")),
                    "inside_50s": self._safe_int(player_data.get("inside_50s")),
                    "rebound_50s": self._safe_int(player_data.get("rebound_50s")),
                    "contested_marks": self._safe_int(player_data.get("contested_marks")),
                    "marks_inside_50": self._safe_int(player_data.get("marks_inside_50")),
                    "clangers": self._safe_int(player_data.get("clangers")),
                    "one_percenters": self._safe_int(player_data.get("one_percenters")),
                    "bounces": self._safe_int(player_data.get("bounces")),
                    "goal_assist": self._safe_int(goals_data.get("assists") if isinstance(goals_data, dict) else None),
                    "time_on_ground_pct": self._safe_float(player_data.get("time_on_ground")),
                }

                if existing_stat:
                    # Update existing stat
                    for key, value in stat_values.items():
                        if value is not None:
                            setattr(existing_stat, key, value)
                    existing_stat.team_id = team_id
                    self.stats["player_stats_updated"] += 1
                else:
                    # Create new stat
                    player_stat = PlayerStat(
                        match_id=match_id,
                        player_id=player_id,
                        team_id=team_id,
                        **{k: v for k, v in stat_values.items() if v is not None}
                    )
                    session.add(player_stat)
                    self.stats["player_stats_created"] += 1

    def _sync_team_stats(
        self, session, api_game_id: int, match_id: int,
        home_team_id: int, away_team_id: int
    ):
        """Sync team statistics for a game."""
        stats_data = self.api.get_game_team_stats(api_game_id)
        if not stats_data:
            logger.debug(f"  No team stats available for game {api_game_id}")
            return

        # API-Sports returns: response[0].teams[]
        if isinstance(stats_data, list) and stats_data:
            teams_container = stats_data[0] if stats_data else {}
            teams_list = teams_container.get("teams", [])
        else:
            teams_list = stats_data.get("teams", []) if isinstance(stats_data, dict) else []

        for team_stat_data in teams_list:
            api_team_id = team_stat_data.get("team", {}).get("id")
            team_id = self._get_team_id(api_team_id)

            if not team_id:
                continue

            is_home = (team_id == home_team_id)

            # Extract stats - nested structure
            stats = team_stat_data.get("statistics", {})
            disposals_data = stats.get("disposals", {})
            stoppages_data = stats.get("stoppages", {})
            scoring_data = stats.get("scoring", {})
            defence_data = stats.get("defence", {})

            # Calculate score from goals/behinds
            goals = self._safe_int(scoring_data.get("goals")) or 0
            behinds = self._safe_int(scoring_data.get("behinds")) or 0
            score = goals * 6 + behinds

            # Check if team stat already exists
            existing = session.query(TeamStat).filter_by(
                match_id=match_id,
                team_id=team_id
            ).first()

            stat_values = {
                "score": score,
                "is_home": is_home,
                "clearances": self._safe_int(stoppages_data.get("clearances")),
                "tackles": self._safe_int(defence_data.get("tackles")),
                "marks": self._safe_int(stats.get("marks")),
                "hitouts": self._safe_int(stoppages_data.get("hitouts")),
                "free_kicks_for": self._safe_int(disposals_data.get("free_kicks")),
                # These may not be available in team stats
                "inside_50s": self._safe_int(stats.get("inside_50s")),
                "contested_possessions": self._safe_int(stats.get("contested_possessions")),
                "uncontested_possessions": self._safe_int(stats.get("uncontested_possessions")),
            }

            if existing:
                for key, value in stat_values.items():
                    if value is not None:
                        setattr(existing, key, value)
            else:
                team_stat = TeamStat(
                    match_id=match_id,
                    team_id=team_id,
                    **{k: v for k, v in stat_values.items() if v is not None}
                )
                session.add(team_stat)
                self.stats["team_stats_created"] += 1

    def sync_round(self, season: int, round_num: int):
        """Sync all games for a specific round."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Syncing {season} Round {round_num}")
        logger.info(f"{'='*60}")

        games = self.api.get_games(season, round_num)
        logger.info(f"Found {len(games)} games from API-Sports")

        if not games:
            logger.warning(f"No games found for {season} Round {round_num}")
            return

        with get_session() as session:
            self._load_team_cache(session)

            for game in games:
                try:
                    self.sync_game(session, game)
                except Exception as e:
                    logger.error(f"Error syncing game {game.get('id')}: {e}")
                    self.stats["errors"] += 1
                    continue

            if not self.dry_run:
                session.commit()
                logger.info("Changes committed to database")

    def sync_rounds(self, season: int, rounds: List[int]):
        """Sync multiple rounds."""
        for round_num in rounds:
            self.sync_round(season, round_num)

    def get_current_round(self, season: int) -> int:
        """Determine the current/latest round with completed games."""
        games = self.api.get_games(season)
        if not games:
            return 0

        completed_rounds = set()
        for game in games:
            status = game.get("status", {}).get("short")
            if status in ["FT", "AOT", "AET"]:
                # API-Sports uses 'week' for round number
                week = game.get("week")
                if week is not None:
                    completed_rounds.add(int(week))

        return max(completed_rounds) if completed_rounds else 0

    def print_summary(self):
        """Print sync summary."""
        logger.info("\n" + "=" * 60)
        logger.info("SYNC COMPLETE - Summary")
        logger.info("=" * 60)
        logger.info(f"API requests made: {self.api.requests_made}")
        logger.info(f"Matches created:   {self.stats['matches_created']}")
        logger.info(f"Matches updated:   {self.stats['matches_updated']}")
        logger.info(f"Players created:   {self.stats['players_created']}")
        logger.info(f"Player stats created: {self.stats['player_stats_created']}")
        logger.info(f"Player stats updated: {self.stats['player_stats_updated']}")
        logger.info(f"Team stats created:   {self.stats['team_stats_created']}")
        logger.info(f"Errors:            {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Sync AFL round data from API-Sports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Sync current round
    python scripts/sync_round_data.py

    # Sync specific rounds
    python scripts/sync_round_data.py --season 2026 --rounds 1,2,3

    # Sync all completed rounds for a season
    python scripts/sync_round_data.py --season 2026 --all-rounds

    # Dry run
    python scripts/sync_round_data.py --dry-run
        """
    )
    parser.add_argument(
        "--season", type=int, default=datetime.now().year,
        help="Season year (default: current year)"
    )
    parser.add_argument(
        "--rounds", type=str, default=None,
        help="Comma-separated list of rounds (e.g., '1,2,3')"
    )
    parser.add_argument(
        "--all-rounds", action="store_true",
        help="Sync all completed rounds for the season"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not API_SPORTS_KEY:
        logger.error("API_SPORTS_KEY not found in environment")
        logger.error("Set it in your .env file or environment")
        sys.exit(1)

    api_client = APISportsClient(API_SPORTS_KEY)
    syncer = RoundDataSyncer(api_client, dry_run=args.dry_run)

    logger.info("=" * 60)
    logger.info(f"AFL Round Data Sync - Season {args.season}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    if args.rounds:
        # Sync specific rounds
        rounds = [int(r.strip()) for r in args.rounds.split(",")]
        syncer.sync_rounds(args.season, rounds)
    elif args.all_rounds:
        # Sync all completed rounds
        current_round = syncer.get_current_round(args.season)
        logger.info(f"Latest completed round: {current_round}")
        rounds = list(range(1, current_round + 1))
        syncer.sync_rounds(args.season, rounds)
    else:
        # Sync current round only
        current_round = syncer.get_current_round(args.season)
        syncer.sync_round(args.season, current_round)

    syncer.print_summary()


if __name__ == "__main__":
    main()
