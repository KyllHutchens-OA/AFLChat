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
    def update_upcoming_matches(cls, days_ahead: int = 7, max_requests: int = 16) -> int:
        """
        Update odds for upcoming matches with rate limiting.
        
        Args:
            days_ahead: Only fetch odds for matches within this many days
            max_requests: Maximum API requests to make
            
        Returns:
            int: Number of API requests made
        """
        if not cls.API_KEY:
            logger.warning("THEODDSAPI_KEY not set, skipping odds fetch")
            return 0
        
        session = Session()
        requests_made = 0
        
        try:
            # Check if we can make requests (daily budget)
            if not cls._can_make_request(session):
                logger.warning(f"Daily request limit ({cls.DAILY_REQUEST_LIMIT}) reached, skipping")
                return 0
            
            # Find upcoming matches needing odds
            cutoff_date = datetime.now()
            future_date = cutoff_date + timedelta(days=days_ahead)
            
            matches = session.query(Match).filter(
                Match.match_date >= cutoff_date,
                Match.match_date <= future_date
            ).order_by(Match.match_date).all()
            
            logger.info(f"Found {len(matches)} upcoming matches in next {days_ahead} days")
            
            for match in matches:
                # Check if we've hit request limit
                if requests_made >= max_requests:
                    logger.info(f"Reached max requests ({max_requests}), stopping")
                    break
                
                # Skip if odds fetched recently (<12 hours ago)
                latest_odds = session.query(BettingOdds).filter_by(
                    match_id=match.id
                ).order_by(BettingOdds.odds_fetched_at.desc()).first()
                
                if latest_odds:
                    hours_since = (datetime.utcnow() - latest_odds.odds_fetched_at).total_seconds() / 3600
                    if hours_since < 12:
                        logger.debug(f"Skipping match {match.id} (odds fetched {hours_since:.1f}h ago)")
                        continue
                
                # Fetch odds for this match
                try:
                    success = cls._fetch_match_odds(session, match)
                    requests_made += 1
                    
                    if success:
                        logger.info(f"✓ Fetched odds for match {match.id}")
                    
                except Exception as e:
                    logger.error(f"Error fetching odds for match {match.id}: {e}")
                    continue
            
            session.commit()
            logger.info(f"Completed odds fetch: {requests_made} API requests made")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error in update_upcoming_matches: {e}")
            raise
        finally:
            session.close()
        
        return requests_made

    @classmethod
    def _fetch_match_odds(cls, session, match) -> bool:
        """
        Fetch odds for a specific match.
        
        Args:
            session: Database session
            match: Match object
            
        Returns:
            bool: True if successful
        """
        start_time = datetime.utcnow()
        
        try:
            # Make API request
            url = f"{cls.BASE_URL}/sports/{cls.SPORT}/odds"
            params = {
                'apiKey': cls.API_KEY,
                'regions': 'au',  # Australian bookmakers
                'markets': 'h2h',  # Head-to-head odds
                'oddsFormat': 'decimal'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Log API request
            cls._log_api_request(
                session,
                endpoint='/sports/aussierules_afl/odds',
                status_code=response.status_code,
                success=response.status_code == 200,
                response_time_ms=response_time
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Find this match in the response
            match_data = cls._find_match_in_response(data, match)
            if not match_data:
                logger.warning(f"Match {match.id} not found in API response")
                return False
            
            # Extract and store odds
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
                        
                        if team_name == match.home_team.name:
                            home_odds = odds
                        elif team_name == match.away_team.name:
                            away_odds = odds
                    
                    if home_odds and away_odds:
                        # Store odds
                        betting_odds = BettingOdds(
                            match_id=match.id,
                            bookmaker=bookmaker_name,
                            home_odds=home_odds,
                            away_odds=away_odds,
                            odds_fetched_at=datetime.utcnow()
                        )
                        session.add(betting_odds)
                        odds_count += 1
            
            logger.info(f"Stored {odds_count} odds for match {match.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error fetching match odds: {e}")
            return False

    @classmethod
    def _find_match_in_response(cls, api_data: list, match) -> dict:
        """Find match in API response by comparing team names."""
        for game in api_data:
            home_team = game.get('home_team')
            away_team = game.get('away_team')
            
            if (home_team == match.home_team.name and 
                away_team == match.away_team.name):
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
