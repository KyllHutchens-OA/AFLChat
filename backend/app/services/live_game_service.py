"""
Live Game Service - Database operations and business logic for live AFL matches.
Handles SSE event processing, score updates, and WebSocket broadcasting.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.data.database import get_session
from app.data.models import LiveGame, LiveGameEvent, Team, Match

logger = logging.getLogger(__name__)


class LiveGameService:
    """Business logic for live game tracking."""

    @staticmethod
    def process_game_update(game_data: Dict[str, Any], socketio=None):
        """
        Process a game update from Squiggle SSE.

        Args:
            game_data: Game data from Squiggle API
            socketio: Flask-SocketIO instance for broadcasting
        """
        squiggle_id = game_data.get("id")
        if not squiggle_id:
            logger.warning("Game data missing 'id' field")
            return

        with get_session() as session:
            # Get or create live game record
            live_game = LiveGameService._get_or_create_game(session, game_data)
            if not live_game:
                return

            # Track previous scores for event detection
            prev_home_score = live_game.home_score or 0
            prev_away_score = live_game.away_score or 0

            # Update game state
            LiveGameService._update_game_state(live_game, game_data)

            session.commit()

            # Detect and create scoring events
            LiveGameService._detect_scoring_events(
                session,
                live_game,
                prev_home_score,
                prev_away_score,
                socketio
            )

            # Broadcast update to WebSocket clients
            if socketio:
                LiveGameService._broadcast_game_update(socketio, live_game)

            # If game completed, migrate to Match table
            if live_game.status == "completed" and not live_game.match_id:
                LiveGameService._migrate_to_match(session, live_game)
                session.commit()

    @staticmethod
    def _get_or_create_game(session: Session, game_data: Dict) -> Optional[LiveGame]:
        """Get existing or create new LiveGame from Squiggle data."""
        squiggle_id = game_data.get("id")

        # Try to find existing game
        live_game = session.query(LiveGame).filter_by(
            squiggle_game_id=squiggle_id
        ).first()

        if live_game:
            return live_game

        # Create new game
        home_team_name = game_data.get("hteam")
        away_team_name = game_data.get("ateam")

        # Try to find teams by name first, then by abbreviation (Squiggle uses full names)
        home_team = session.query(Team).filter_by(name=home_team_name).first()
        if not home_team:
            home_team = session.query(Team).filter_by(abbreviation=home_team_name).first()

        away_team = session.query(Team).filter_by(name=away_team_name).first()
        if not away_team:
            away_team = session.query(Team).filter_by(abbreviation=away_team_name).first()

        if not home_team or not away_team:
            logger.warning(f"Teams not found: {home_team_name} vs {away_team_name}")
            return None

        # Parse date
        date_str = game_data.get("date")
        if date_str:
            try:
                match_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                match_date = datetime.utcnow()
        else:
            match_date = datetime.utcnow()

        live_game = LiveGame(
            squiggle_game_id=squiggle_id,
            season=game_data.get("year"),
            round=str(game_data.get("round", "")),
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            venue=game_data.get("venue"),
            match_date=match_date,
            status="scheduled",
        )

        session.add(live_game)
        session.flush()

        logger.info(
            f"Created new live game: {home_team.abbreviation} vs {away_team.abbreviation}"
        )

        return live_game

    @staticmethod
    def _update_game_state(live_game: LiveGame, game_data: Dict):
        """Update live game state from Squiggle data."""
        # Scores
        live_game.home_score = game_data.get("hscore", 0)
        live_game.away_score = game_data.get("ascore", 0)
        live_game.home_goals = game_data.get("hgoals", 0)
        live_game.home_behinds = game_data.get("hbehinds", 0)
        live_game.away_goals = game_data.get("agoals", 0)
        live_game.away_behinds = game_data.get("abehinds", 0)

        # Game state
        complete = game_data.get("complete", 0)
        live_game.complete_percent = complete

        if complete == 0:
            live_game.status = "scheduled"
        elif complete == 100:
            live_game.status = "completed"
        else:
            live_game.status = "live"

        live_game.time_str = game_data.get("timestr")

        # Parse current quarter from timestr (e.g., "Q2 15:32")
        if live_game.time_str and live_game.time_str.startswith("Q"):
            try:
                live_game.current_quarter = int(live_game.time_str[1])
            except (IndexError, ValueError):
                pass

        # Winner
        winner_abbr = game_data.get("winner")
        if winner_abbr and live_game.status == "completed":
            if winner_abbr == game_data.get("hteam"):
                live_game.winner_team_id = live_game.home_team_id
            elif winner_abbr == game_data.get("ateam"):
                live_game.winner_team_id = live_game.away_team_id

        live_game.last_updated = datetime.utcnow()

    @staticmethod
    def _detect_scoring_events(
        session: Session,
        live_game: LiveGame,
        prev_home_score: int,
        prev_away_score: int,
        socketio=None
    ):
        """Detect and create scoring events based on score changes."""
        home_diff = live_game.home_score - prev_home_score
        away_diff = live_game.away_score - prev_away_score

        # Home team scored
        if home_diff > 0:
            event_type = "goal" if home_diff == 6 else "behind"
            event = LiveGameEvent(
                game_id=live_game.id,
                event_type=event_type,
                team_id=live_game.home_team_id,
                home_score_after=live_game.home_score,
                away_score_after=live_game.away_score,
                quarter=live_game.current_quarter,
                time_str=live_game.time_str,
            )
            session.add(event)
            logger.info(
                f"🎯 {event_type.upper()}: {live_game.home_team.abbreviation} - "
                f"{live_game.home_score} - {live_game.away_score}"
            )

            # Broadcast event
            if socketio:
                LiveGameService._broadcast_scoring_event(
                    socketio, live_game, event_type, "home"
                )

        # Away team scored
        if away_diff > 0:
            event_type = "goal" if away_diff == 6 else "behind"
            event = LiveGameEvent(
                game_id=live_game.id,
                event_type=event_type,
                team_id=live_game.away_team_id,
                home_score_after=live_game.home_score,
                away_score_after=live_game.away_score,
                quarter=live_game.current_quarter,
                time_str=live_game.time_str,
            )
            session.add(event)
            logger.info(
                f"🎯 {event_type.upper()}: {live_game.away_team.abbreviation} - "
                f"{live_game.home_score} - {live_game.away_score}"
            )

            # Broadcast event
            if socketio:
                LiveGameService._broadcast_scoring_event(
                    socketio, live_game, event_type, "away"
                )

    @staticmethod
    def _broadcast_game_update(socketio, live_game: LiveGame):
        """Broadcast game state update to WebSocket room."""
        try:
            room = f"live_game_{live_game.id}"
            socketio.emit(
                "live_game_update",
                {
                    "game_id": live_game.id,
                    "home_score": live_game.home_score,
                    "away_score": live_game.away_score,
                    "status": live_game.status,
                    "complete_percent": live_game.complete_percent,
                    "time_str": live_game.time_str,
                    "current_quarter": live_game.current_quarter,
                },
                room=room,
            )
        except Exception as e:
            logger.error(f"Error broadcasting game update: {e}")

    @staticmethod
    def _broadcast_scoring_event(socketio, live_game: LiveGame, event_type: str, team_side: str):
        """Broadcast scoring event to all clients (for popup notifications)."""
        try:
            team = live_game.home_team if team_side == "home" else live_game.away_team

            socketio.emit(
                "live_game_event",
                {
                    "game_id": live_game.id,
                    "event_type": event_type,
                    "team_side": team_side,
                    "team_name": team.name,
                    "team_abbreviation": team.abbreviation,
                    "home_score": live_game.home_score,
                    "away_score": live_game.away_score,
                    "time_str": live_game.time_str,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                namespace="/",  # Broadcast to all clients
            )
        except Exception as e:
            logger.error(f"Error broadcasting scoring event: {e}")

    @staticmethod
    def _migrate_to_match(session: Session, live_game: LiveGame):
        """Migrate completed live game to Match table."""
        try:
            # Check if match already exists
            existing_match = session.query(Match).filter_by(
                season=live_game.season,
                round=live_game.round,
                home_team_id=live_game.home_team_id,
                away_team_id=live_game.away_team_id,
            ).first()

            if existing_match:
                # Update existing match
                existing_match.home_score = live_game.home_score
                existing_match.away_score = live_game.away_score
                existing_match.match_status = "completed"
                live_game.match_id = existing_match.id
                logger.info(f"Updated existing match {existing_match.id}")
            else:
                # Create new match
                match = Match(
                    season=live_game.season,
                    round=live_game.round,
                    match_date=live_game.match_date,
                    venue=live_game.venue,
                    home_team_id=live_game.home_team_id,
                    away_team_id=live_game.away_team_id,
                    home_score=live_game.home_score,
                    away_score=live_game.away_score,
                    match_status="completed",
                )
                session.add(match)
                session.flush()
                live_game.match_id = match.id
                logger.info(f"Created new match {match.id} from live game {live_game.id}")

        except Exception as e:
            logger.error(f"Error migrating live game to match: {e}")

    @staticmethod
    def get_active_games(hours=2) -> list:
        """
        Get all active games (live or recently completed).

        Args:
            hours: How many hours back to look for completed games

        Returns:
            List of LiveGame objects
        """
        from sqlalchemy.orm import joinedload

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with get_session() as session:
            games = (
                session.query(LiveGame)
                .options(joinedload(LiveGame.home_team))
                .options(joinedload(LiveGame.away_team))
                .filter(LiveGame.last_updated >= cutoff)
                .order_by(LiveGame.match_date.desc())
                .all()
            )

            # Detach from session for safe return
            session.expunge_all()
            return games
