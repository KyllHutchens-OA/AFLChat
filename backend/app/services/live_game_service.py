"""
Live Game Service - Database operations and business logic for live AFL matches.
Handles SSE event processing, score updates, and WebSocket broadcasting.
Player stats are sourced from Footywire (scraped at quarter breaks).
"""
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.data.database import get_session
from app.data.models import LiveGame, LiveGameEvent, Team, Match, QuarterSnapshot
from app.analytics.entity_resolver import VenueResolver

logger = logging.getLogger(__name__)

# Track previous quarter per game for quarter transition detection
_previous_quarters: Dict[int, int] = {}  # game_id -> last known quarter


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

            # Pre-fetch team data before commit (to avoid detached instance issues)
            home_team_abbr = live_game.home_team.abbreviation
            away_team_abbr = live_game.away_team.abbreviation

            # Update game state (this sets new scores)
            LiveGameService._update_game_state(live_game, game_data)

            session.commit()

            # Refresh live_game to ensure relationships are loaded
            session.refresh(live_game)

            # Detect quarter transitions
            LiveGameService._detect_quarter_transition(
                session, live_game, home_team_abbr, away_team_abbr, socketio
            )

            # Broadcast update to WebSocket clients
            if socketio:
                LiveGameService._broadcast_game_update(socketio, live_game)

            # If game completed, migrate to Match table.
            # The Q4 snapshot background thread (5 min delay) handles:
            # - Footywire post-game stats scrape
            # - AI summary generation
            # - Post-game analysis generation
            if live_game.status == "completed" and not live_game.match_id:
                # Generate Q4 snapshot if missing (quarter transition only catches Q1-Q3)
                q4_missing = not live_game.quarter_summaries or "4" not in (live_game.quarter_summaries or {})
                if q4_missing:
                    live_game.home_q4_score = live_game.home_score
                    live_game.away_q4_score = live_game.away_score
                    LiveGameService._snapshot_quarter_stats(
                        session, live_game, 4,
                        home_team_abbr, away_team_abbr, socketio
                    )

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
            venue=VenueResolver.normalize_venue(game_data.get("venue", "") or ""),
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
        # Debug: log score changes for live games
        new_score = game_data.get("hscore", 0)
        if live_game.status == 'live' and live_game.home_score != new_score:
            logger.info(f"Updating game {live_game.id} (sqid={game_data.get('id')}): score {live_game.home_score}-{live_game.away_score} -> {new_score}-{game_data.get('ascore', 0)}, complete {live_game.complete_percent} -> {game_data.get('complete', 0)}")

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
        elif complete >= 99:
            # Mark as completed at 99% to avoid waiting for Squiggle's slow 100% update
            # This allows new games to be displayed promptly
            live_game.status = "completed"
            logger.info(f"Game marked completed at {complete}% - {live_game.home_team.abbreviation} vs {live_game.away_team.abbreviation}")
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
    def _detect_quarter_transition(
        session: Session,
        live_game: LiveGame,
        home_team_abbr: str,
        away_team_abbr: str,
        socketio=None
    ):
        """Detect quarter transitions and snapshot stats."""
        global _previous_quarters

        current_quarter = live_game.current_quarter
        if not current_quarter:
            # Try to infer from time_str for break periods
            time_str = live_game.time_str or ""
            if "Half Time" in time_str or "HT" in time_str:
                current_quarter = 2
            elif "3/4 Time" in time_str or "Three Quarter" in time_str:
                current_quarter = 3
            elif "Full Time" in time_str:
                current_quarter = 4

        if not current_quarter:
            return

        # DB-aware initialization: on restart, seed from QuarterSnapshot records
        if live_game.id not in _previous_quarters:
            max_snapshot_q = session.query(
                func.max(QuarterSnapshot.quarter)
            ).filter_by(game_id=live_game.id).scalar() or 0

            if max_snapshot_q > 0:
                # Snapshots exist — seed to the highest one
                _previous_quarters[live_game.id] = max_snapshot_q
                logger.info(f"Initialized quarter tracking for game {live_game.id} from DB: Q{max_snapshot_q}")
            elif current_quarter > 1:
                # Game is past Q1 but no snapshots — backfill missed quarters
                logger.info(f"Backfilling missed quarters 1-{current_quarter - 1} for game {live_game.id}")
                for missed_q in range(1, current_quarter):
                    LiveGameService._snapshot_quarter_stats(
                        session, live_game, missed_q,
                        home_team_abbr, away_team_abbr, socketio
                    )
                _previous_quarters[live_game.id] = current_quarter
            else:
                # Still in Q1 — seed to current quarter, wait for normal transition
                _previous_quarters[live_game.id] = current_quarter

        prev_quarter = _previous_quarters.get(live_game.id, 0)
        _previous_quarters[live_game.id] = current_quarter

        # Quarter transition detected
        if current_quarter > prev_quarter and prev_quarter > 0:
            completed_quarter = prev_quarter
            logger.info(f"Quarter transition detected: Q{prev_quarter} -> Q{current_quarter} for game {live_game.id}")

            # Snapshot quarter scores on LiveGame
            if completed_quarter == 1:
                live_game.home_q1_score = live_game.home_score
                live_game.away_q1_score = live_game.away_score
            elif completed_quarter == 2:
                live_game.home_q2_score = live_game.home_score
                live_game.away_q2_score = live_game.away_score
            elif completed_quarter == 3:
                live_game.home_q3_score = live_game.home_score
                live_game.away_q3_score = live_game.away_score
            elif completed_quarter == 4:
                live_game.home_q4_score = live_game.home_score
                live_game.away_q4_score = live_game.away_score

            # Snapshot player stats for the completed quarter
            LiveGameService._snapshot_quarter_stats(
                session, live_game, completed_quarter,
                home_team_abbr, away_team_abbr, socketio
            )

    @staticmethod
    def _snapshot_quarter_stats(
        session: Session,
        live_game: LiveGame,
        quarter: int,
        home_team_abbr: str,
        away_team_abbr: str,
        socketio=None
    ):
        """
        Create a quarter snapshot record and trigger a delayed Footywire scrape.

        The scrape runs 5 minutes after the quarter ends (mid-break) to give
        Footywire time to publish updated stats. The background thread then:
          - Stores scraped stats in live_game.stats_cache (with quarter label)
          - Populates QuarterSnapshot.player_stats
          - Generates the quarter AI summary
          - For Q4: generates the full-game AI summary and post-game analysis
        """
        try:
            # Idempotency guard
            existing = session.query(QuarterSnapshot).filter_by(
                game_id=live_game.id, quarter=quarter
            ).first()
            if existing:
                return

            # Create empty snapshot now — player_stats populated after Footywire scrape
            snapshot = QuarterSnapshot(
                game_id=live_game.id,
                quarter=quarter,
                player_stats=[],
            )
            session.add(snapshot)
            session.commit()

            logger.info(f"Created Q{quarter} snapshot for game {live_game.id} (Footywire scrape in 5 min)")

            # Capture all values needed by the background thread before session closes
            game_id = live_game.id
            season = live_game.season
            home_name = live_game.home_team.name
            away_name = live_game.away_team.name
            home_score = live_game.home_score
            away_score = live_game.away_score
            is_final_quarter = (quarter == 4)

            def scrape_and_summarize():
                try:
                    time.sleep(300)  # 5 min into the break — Footywire should have updated

                    from app.data.ingestion.footywire_scraper import footywire_scraper
                    fw_stats = footywire_scraper.get_top_performers(season, home_name, away_name)

                    scraped_at = datetime.utcnow().isoformat() + 'Z'

                    with get_session() as s:
                        lg = s.query(LiveGame).filter_by(id=game_id).first()
                        snap = s.query(QuarterSnapshot).filter_by(
                            game_id=game_id, quarter=quarter
                        ).first()

                        if lg and fw_stats:
                            cache = {
                                'top_goal_kickers': fw_stats.get('top_goal_kickers', []),
                                'top_disposals': fw_stats.get('top_disposals', []),
                                'top_fantasy': fw_stats.get('top_fantasy', []),
                                'stats_as_of_quarter': quarter,
                                'stats_scraped_at': scraped_at,
                            }
                            lg.stats_cache = cache
                            lg.stats_cache_updated_at = datetime.utcnow()
                            flag_modified(lg, 'stats_cache')

                            if snap:
                                snap.player_stats = fw_stats.get('all_players', [])

                            if socketio:
                                socketio.emit(
                                    'game_stats_update',
                                    {'game_id': game_id, 'stats': cache},
                                    namespace='/',
                                )

                        # Generate quarter AI summary
                        all_players = fw_stats.get('all_players', []) if fw_stats else []
                        top_performers = sorted(
                            all_players, key=lambda x: x.get('disposals', 0), reverse=True
                        )[:5]

                        from app.services.game_summary_service import game_summary_service

                        q_summary = game_summary_service.generate_quarter_summary(
                            quarter=quarter,
                            home_team=home_name,
                            away_team=away_name,
                            home_score=home_score,
                            away_score=away_score,
                            quarter_stats=top_performers,
                        )

                        if q_summary:
                            if snap:
                                snap.quarter_summary = q_summary
                            if lg:
                                summaries = dict(lg.quarter_summaries or {})
                                summaries[str(quarter)] = q_summary
                                lg.quarter_summaries = summaries
                                flag_modified(lg, 'quarter_summaries')

                            if socketio:
                                socketio.emit(
                                    'quarter_summary',
                                    {'game_id': game_id, 'quarter': quarter, 'summary': q_summary},
                                    namespace='/',
                                )
                                logger.info(f"Emitted quarter_summary for game {game_id} Q{quarter}")

                        # For the final quarter: also generate AI summary + post-game analysis
                        if is_final_quarter and lg and fw_stats:
                            cache_for_summary = lg.stats_cache

                            if not lg.ai_summary:
                                summary = game_summary_service.generate_summary(lg, cache_for_summary)
                                if summary:
                                    lg.ai_summary = summary
                                    logger.info(f"AI summary generated for game {game_id}")

                            if not lg.post_game_analysis:
                                analysis = game_summary_service.generate_post_game_analysis_from_stats(
                                    home_team=home_name,
                                    away_team=away_name,
                                    stats=fw_stats,
                                )
                                if analysis:
                                    lg.post_game_analysis = analysis
                                    if socketio:
                                        socketio.emit(
                                            'post_game_analysis',
                                            {'game_id': game_id, 'analysis': analysis},
                                            namespace='/',
                                        )
                                    logger.info(f"Post-game analysis generated for game {game_id}")

                except Exception as exc:
                    logger.error(f"Error in Footywire scrape thread for game {game_id} Q{quarter}: {exc}")

            thread = threading.Thread(target=scrape_and_summarize, daemon=True)
            thread.start()

        except Exception as exc:
            logger.error(f"Error creating quarter snapshot: {exc}")


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
        Get all active games from the current round only.

        Prioritizes live games over completed ones. Only shows games from the
        most recent round to reduce clutter.

        Args:
            hours: How many hours back to look for completed games when no live games

        Returns:
            List of serialized game dicts (not ORM objects to avoid N+1 queries)
        """
        from sqlalchemy.orm import joinedload

        with get_session() as session:
            # Get the most recent round with any activity
            latest_game = (
                session.query(LiveGame)
                .order_by(LiveGame.match_date.desc())
                .first()
            )

            if not latest_game:
                return []

            current_season = latest_game.season
            current_round = latest_game.round

            # First, check for live games in current round
            live_games = (
                session.query(LiveGame)
                .options(joinedload(LiveGame.home_team))
                .options(joinedload(LiveGame.away_team))
                .filter(
                    LiveGame.status == "live",
                    LiveGame.season == current_season,
                    LiveGame.round == current_round
                )
                .order_by(LiveGame.match_date.desc())
                .all()
            )

            # Always include scheduled (unstarted) games from the current round
            scheduled_games = (
                session.query(LiveGame)
                .options(joinedload(LiveGame.home_team))
                .options(joinedload(LiveGame.away_team))
                .filter(
                    LiveGame.status == "scheduled",
                    LiveGame.season == current_season,
                    LiveGame.round == current_round,
                )
                .order_by(LiveGame.match_date.asc())
                .all()
            )

            if live_games:
                # Live games exist — also show recently completed games (last 30 min)
                recent_cutoff = datetime.utcnow() - timedelta(minutes=30)
                completed_games = (
                    session.query(LiveGame)
                    .options(joinedload(LiveGame.home_team))
                    .options(joinedload(LiveGame.away_team))
                    .filter(
                        LiveGame.status == "completed",
                        LiveGame.season == current_season,
                        LiveGame.round == current_round,
                        LiveGame.last_updated >= recent_cutoff
                    )
                    .order_by(LiveGame.match_date.desc())
                    .all()
                )
                games = live_games + completed_games + scheduled_games
            else:
                # No live games — show all games from current round within time window
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                finished_games = (
                    session.query(LiveGame)
                    .options(joinedload(LiveGame.home_team))
                    .options(joinedload(LiveGame.away_team))
                    .filter(
                        LiveGame.status == "completed",
                        LiveGame.season == current_season,
                        LiveGame.round == current_round,
                        LiveGame.last_updated >= cutoff
                    )
                    .order_by(LiveGame.match_date.desc())
                    .all()
                )
                games = finished_games + scheduled_games

            # Serialize within session to avoid lazy loading after session closes
            result = []
            for game in games:
                result.append({
                    'id': game.id,
                    'squiggle_game_id': game.squiggle_game_id,
                    'season': game.season,
                    'round': game.round,
                    'home_team': {
                        'id': game.home_team.id,
                        'name': game.home_team.name,
                        'abbreviation': game.home_team.abbreviation,
                    },
                    'away_team': {
                        'id': game.away_team.id,
                        'name': game.away_team.name,
                        'abbreviation': game.away_team.abbreviation,
                    },
                    'home_score': game.home_score,
                    'away_score': game.away_score,
                    'home_goals': game.home_goals,
                    'home_behinds': game.home_behinds,
                    'away_goals': game.away_goals,
                    'away_behinds': game.away_behinds,
                    'status': game.status,
                    'complete_percent': game.complete_percent,
                    'time_str': game.time_str,
                    'current_quarter': game.current_quarter,
                    'venue': game.venue,
                    'match_date': game.match_date,
                    'last_updated': game.last_updated,
                })

            return result
