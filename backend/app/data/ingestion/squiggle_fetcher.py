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

            # Preload teams and matches in bulk to avoid N×5 per-tip DB queries.
            team_by_name = {t.name: t for t in session.query(Team).all()}
            match_by_key = {
                (m.season, m.round, m.home_team_id, m.away_team_id): m
                for m in session.query(Match).filter_by(season=season).all()
            }
            existing_preds = {
                p.match_id: p
                for p in session.query(SquigglePrediction).filter_by(
                    source_model='Squiggle'
                ).all()
            }

            now = datetime.utcnow()
            for tip in tips:
                try:
                    home_team = team_by_name.get(tip.get('hteam'))
                    away_team = team_by_name.get(tip.get('ateam'))
                    winner_team = team_by_name.get(tip.get('tip'))
                    round_num = tip.get('round')

                    if not all([home_team, away_team, winner_team, round_num]):
                        continue

                    match = match_by_key.get(
                        (season, str(round_num), home_team.id, away_team.id)
                    )
                    if not match:
                        continue

                    confidence = float(tip.get('confidence', 50))
                    margin = float(tip.get('margin', 0))
                    is_home_winner = winner_team.id == match.home_team_id
                    home_prob = confidence if is_home_winner else (100 - confidence)
                    away_prob = 100 - home_prob

                    existing = existing_preds.get(match.id)
                    if existing:
                        existing.predicted_winner_id = winner_team.id
                        existing.predicted_margin = margin
                        existing.home_win_probability = home_prob
                        existing.away_win_probability = away_prob
                        existing.prediction_date = now
                    else:
                        prediction = SquigglePrediction(
                            match_id=match.id,
                            predicted_winner_id=winner_team.id,
                            predicted_margin=margin,
                            home_win_probability=home_prob,
                            away_win_probability=away_prob,
                            source_model='Squiggle',
                            prediction_date=now,
                        )
                        session.add(prediction)
                        existing_preds[match.id] = prediction

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
