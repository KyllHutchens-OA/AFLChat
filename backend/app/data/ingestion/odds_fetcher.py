"""
Betting Odds Fetcher - Fetch odds from The Odds API with smart budget management.
"""
import requests
import os
from datetime import datetime, timedelta
from app.data.database import Session
from app.data.models import BettingOdds, APIRequestLog, Match, Team
import logging

logger = logging.getLogger(__name__)


class OddsFetcher:
    """Fetch betting odds with smart budget management."""

    API_KEY = os.getenv("THEODDSAPI_KEY")
    BASE_URL = "https://api.the-odds-api.com/v4"
    SPORT = "aussierules_afl"
    DAILY_REQUEST_LIMIT = 16  # Max 16 requests/day (480/month with buffer for 500 limit)

    @classmethod
    def update_upcoming_matches(cls, days_ahead: int = 7) -> int:
        """
        Update odds for upcoming matches using a single API request.

        Args:
            days_ahead: Only update odds for matches within this many days

        Returns:
            int: Number of API requests made (0 or 1)
        """
        if not cls.API_KEY:
            logger.warning("THEODDSAPI_KEY not set, skipping odds fetch")
            return 0

        session = Session()

        try:
            # Check if we can make requests (daily budget)
            if not cls._can_make_request(session):
                logger.warning(f"Daily request limit ({cls.DAILY_REQUEST_LIMIT}) reached, skipping")
                return 0

            # Make ONE API request to get all AFL odds
            start_time = datetime.utcnow()
            url = f"{cls.BASE_URL}/sports/{cls.SPORT}/odds"
            params = {
                'apiKey': cls.API_KEY,
                'regions': 'au',
                'markets': 'h2h',
                'oddsFormat': 'decimal'
            }

            response = requests.get(url, params=params, timeout=10)
            response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Log the single API request
            cls._log_api_request(
                session,
                endpoint='/sports/aussierules_afl/odds',
                status_code=response.status_code,
                success=response.status_code == 200,
                response_time_ms=response_time
            )

            response.raise_for_status()
            api_games = response.json()

            logger.info(f"Fetched {len(api_games)} games from The Odds API")

            # Find upcoming matches in our database
            cutoff_date = datetime.now()
            future_date = cutoff_date + timedelta(days=days_ahead)

            matches = session.query(Match).filter(
                Match.match_date >= cutoff_date,
                Match.match_date <= future_date
            ).order_by(Match.match_date).all()

            logger.info(f"Found {len(matches)} upcoming matches in next {days_ahead} days")

            # Match API data to our matches and store odds
            matches_updated = 0
            for match in matches:
                match_data = cls._find_match_in_response(api_games, match)
                if not match_data:
                    continue

                odds_count = cls._store_match_odds(session, match, match_data)
                if odds_count > 0:
                    matches_updated += 1

            session.commit()
            logger.info(f"✓ Updated odds for {matches_updated} matches (1 API request)")

            return 1  # We made exactly 1 API request

        except Exception as e:
            session.rollback()
            logger.error(f"Error in update_upcoming_matches: {e}")
            raise
        finally:
            session.close()

    @classmethod
    def _store_match_odds(cls, session, match, match_data: dict) -> int:
        """
        Store odds for a match from API response data.

        Args:
            session: Database session
            match: Match object
            match_data: API response data for this match

        Returns:
            int: Number of odds records stored
        """
        bookmakers = match_data.get('bookmakers', [])
        odds_count = 0

        for bookmaker in bookmakers:
            bookmaker_name = bookmaker.get('key')
            markets = bookmaker.get('markets', [])

            for market in markets:
                if market.get('key') != 'h2h':
                    continue

                outcomes = market.get('outcomes', [])
                if len(outcomes) != 2:
                    continue

                # Map outcomes to home/away
                home_odds = None
                away_odds = None

                for outcome in outcomes:
                    team_name = outcome.get('name')
                    odds = outcome.get('price')

                    # Handle team name variations (API uses "Hawks" vs DB uses "Hawthorn")
                    if cls._teams_match(team_name, match.home_team.name):
                        home_odds = odds
                    elif cls._teams_match(team_name, match.away_team.name):
                        away_odds = odds

                if home_odds and away_odds:
                    betting_odds = BettingOdds(
                        match_id=match.id,
                        bookmaker=bookmaker_name,
                        home_odds=home_odds,
                        away_odds=away_odds,
                        odds_fetched_at=datetime.utcnow()
                    )
                    session.add(betting_odds)
                    odds_count += 1

        if odds_count > 0:
            logger.debug(f"Stored {odds_count} odds for match {match.id}")

        return odds_count

    # Team name mappings: API name -> DB name
    TEAM_NAME_MAP = {
        'Adelaide Crows': 'Adelaide',
        'Brisbane Lions': 'Brisbane Lions',
        'Carlton Blues': 'Carlton',
        'Collingwood Magpies': 'Collingwood',
        'Essendon Bombers': 'Essendon',
        'Fremantle Dockers': 'Fremantle',
        'Geelong Cats': 'Geelong',
        'Gold Coast Suns': 'Gold Coast',
        'Greater Western Sydney Giants': 'Greater Western Sydney',
        'GWS Giants': 'Greater Western Sydney',
        'Hawthorn Hawks': 'Hawthorn',
        'Melbourne Demons': 'Melbourne',
        'North Melbourne Kangaroos': 'North Melbourne',
        'Port Adelaide Power': 'Port Adelaide',
        'Richmond Tigers': 'Richmond',
        'St Kilda Saints': 'St Kilda',
        'Sydney Swans': 'Sydney',
        'West Coast Eagles': 'West Coast',
        'Western Bulldogs': 'Western Bulldogs',
    }

    @classmethod
    def _teams_match(cls, api_name: str, db_name: str) -> bool:
        """Check if API team name matches database team name."""
        if not api_name or not db_name:
            return False
        # Direct match
        if api_name == db_name:
            return True
        # Check mapping
        mapped_name = cls.TEAM_NAME_MAP.get(api_name)
        if mapped_name and mapped_name == db_name:
            return True
        # Partial match (e.g., "Hawthorn" in "Hawthorn Hawks")
        if db_name in api_name or api_name in db_name:
            return True
        return False

    @classmethod
    def _find_match_in_response(cls, api_data: list, match) -> dict:
        """Find match in API response by comparing team names."""
        for game in api_data:
            home_team = game.get('home_team')
            away_team = game.get('away_team')

            if (cls._teams_match(home_team, match.home_team.name) and
                cls._teams_match(away_team, match.away_team.name)):
                return game

        return None

    @classmethod
    def _can_make_request(cls, session) -> bool:
        """
        Check if within daily budget (16 requests).
        
        Args:
            session: Database session
            
        Returns:
            bool: True if under limit
        """
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        count = session.query(APIRequestLog).filter(
            APIRequestLog.api_name == 'theoddsapi',
            APIRequestLog.request_timestamp >= today_start,
            APIRequestLog.success == True
        ).count()
        
        return count < cls.DAILY_REQUEST_LIMIT

    @classmethod
    def _log_api_request(cls, session, endpoint: str, status_code: int, 
                        success: bool, response_time_ms: int):
        """Log API request for monitoring."""
        log = APIRequestLog(
            api_name='theoddsapi',
            endpoint=endpoint,
            request_timestamp=datetime.utcnow(),
            status_code=status_code,
            success=success,
            response_time_ms=response_time_ms,
            estimated_cost=0.001  # Rough estimate per request
        )
        session.add(log)
