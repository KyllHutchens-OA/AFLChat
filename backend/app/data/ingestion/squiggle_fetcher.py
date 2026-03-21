"""
Squiggle Predictions Fetcher - Fetch match predictions from Squiggle API.
"""
import requests
from datetime import datetime
from app.data.database import Session
from app.data.models import SquigglePrediction, Match, Team
import logging

logger = logging.getLogger(__name__)


class SquiggleFetcher:
    """Fetch match predictions from Squiggle API (free, no rate limits)."""

    BASE_URL = "https://api.squiggle.com.au"

    @classmethod
    def fetch_current_round_predictions(cls, season: int = None) -> int:
        """
        Fetch predictions for current AFL season.
        
        Args:
            season: Season year (defaults to current year)
            
        Returns:
            int: Number of predictions updated
        """
        if season is None:
            season = datetime.now().year
        
        session = Session()
        updated_count = 0
        
        try:
            # Fetch tips from Squiggle
            url = f"{cls.BASE_URL}/?q=tips&year={season}"
            headers = {"User-Agent": "AFL-Analytics-App/1.0 (kyllhutchens@gmail.com)"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            tips = data.get('tips', [])
            
            for tip in tips:
                try:
                    # Find matching match
                    match = cls._find_match(session, tip, season)
                    if not match:
                        continue
                    
                    # Find predicted winner team
                    winner_team = session.query(Team).filter_by(
                        name=tip.get('tip')
                    ).first()
                    
                    if not winner_team:
                        continue
                    
                    # Calculate probabilities (Squiggle provides confidence as string)
                    confidence = float(tip.get('confidence', 50))
                    margin = float(tip.get('margin', 0))

                    # Determine if home or away is predicted winner
                    is_home_winner = winner_team.id == match.home_team_id
                    home_prob = confidence if is_home_winner else (100 - confidence)
                    away_prob = 100 - home_prob
                    
                    # Check if prediction already exists
                    existing = session.query(SquigglePrediction).filter_by(
                        match_id=match.id,
                        source_model='Squiggle'
                    ).first()
                    
                    if existing:
                        # Update existing prediction
                        existing.predicted_winner_id = winner_team.id
                        existing.predicted_margin = margin
                        existing.home_win_probability = home_prob
                        existing.away_win_probability = away_prob
                        existing.prediction_date = datetime.utcnow()
                    else:
                        # Create new prediction
                        prediction = SquigglePrediction(
                            match_id=match.id,
                            predicted_winner_id=winner_team.id,
                            predicted_margin=margin,
                            home_win_probability=home_prob,
                            away_win_probability=away_prob,
                            source_model='Squiggle',
                            prediction_date=datetime.utcnow()
                        )
                        session.add(prediction)
                    
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing tip: {e}")
                    continue
            
            session.commit()
            logger.info(f"✓ Updated {updated_count} Squiggle predictions")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error fetching Squiggle predictions: {e}")
            raise
        finally:
            session.close()
        
        return updated_count

    @classmethod
    def _find_match(cls, session, tip: dict, season: int):
        """
        Find Match record from Squiggle tip data.
        
        Args:
            session: Database session
            tip: Squiggle tip dictionary
            season: Season year
            
        Returns:
            Match object or None
        """
        # Squiggle provides home team (hteam) and away team (ateam)
        home_team_name = tip.get('hteam')
        away_team_name = tip.get('ateam')
        round_num = tip.get('round')
        
        if not all([home_team_name, away_team_name, round_num]):
            return None
        
        # Find teams
        home_team = session.query(Team).filter_by(name=home_team_name).first()
        away_team = session.query(Team).filter_by(name=away_team_name).first()
        
        if not home_team or not away_team:
            return None
        
        # Find match
        match = session.query(Match).filter_by(
            season=season,
            round=str(round_num),
            home_team_id=home_team.id,
            away_team_id=away_team.id
        ).first()
        
        return match
