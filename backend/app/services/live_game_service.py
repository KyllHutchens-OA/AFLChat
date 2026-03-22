"""
Live Game Service - Database operations and business logic for live AFL matches.
Handles SSE event processing, score updates, and WebSocket broadcasting.
"""
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, Set
from sqlalchemy.orm import Session

from sqlalchemy.orm.attributes import flag_modified

from app.data.database import get_session
from app.data.models import LiveGame, LiveGameEvent, Team, Match, QuarterSnapshot

logger = logging.getLogger(__name__)

# Track previous goal/behind counts per team for scorer attribution
_previous_goal_counts: Dict[int, Dict[str, Dict[int, int]]] = {}  # game_id -> team_side -> player_id -> goals
_previous_behind_counts: Dict[int, Dict[str, Dict[int, int]]] = {}  # game_id -> team_side -> player_id -> behinds

# Track previous quarter per game for quarter transition detection
_previous_quarters: Dict[int, int] = {}  # game_id -> last known quarter

# Track emitted milestones per game to prevent duplicates
_emitted_milestones: Dict[int, set] = {}  # game_id -> set of milestone keys

# Track polling cycles per game for milestone detection frequency
_polling_cycles: Dict[int, int] = {}  # game_id -> cycle count

# Cache for API-Sports stats responses (shared between scoring + milestone detection)
_stats_cache: Dict[int, Tuple[Any, float]] = {}  # api_game_id -> (stats_data, timestamp)
_STATS_CACHE_TTL = 30  # seconds


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

            # Use the CURRENT stored scores as baseline (before updating)
            # This is more reliable than using the last event's scores
            prev_home_score = live_game.home_score or 0
            prev_away_score = live_game.away_score or 0

            # Pre-fetch team data before commit (to avoid detached instance issues)
            home_team_id = live_game.home_team_id
            away_team_id = live_game.away_team_id
            home_team_abbr = live_game.home_team.abbreviation
            away_team_abbr = live_game.away_team.abbreviation
            home_team_name = live_game.home_team.name
            away_team_name = live_game.away_team.name

            # Update game state (this sets new scores)
            LiveGameService._update_game_state(live_game, game_data)

            session.commit()

            # Refresh live_game to ensure relationships are loaded
            session.refresh(live_game)

            # Detect and create scoring events
            LiveGameService._detect_scoring_events(
                session,
                live_game,
                prev_home_score,
                prev_away_score,
                socketio,
                home_team_abbr,
                away_team_abbr,
                home_team_name,
                away_team_name
            )

            # Detect quarter transitions
            LiveGameService._detect_quarter_transition(
                session, live_game, home_team_abbr, away_team_abbr, socketio
            )

            # Broadcast update to WebSocket clients
            if socketio:
                LiveGameService._broadcast_game_update(socketio, live_game)

            # If game completed, migrate to Match table and generate AI summary
            if live_game.status == "completed" and not live_game.match_id:
                # Generate Q4 summary if missing (quarter transition only catches Q1-Q3)
                q4_missing = not live_game.quarter_summaries or "4" not in (live_game.quarter_summaries or {})
                if q4_missing:
                    live_game.home_q4_score = live_game.home_score
                    live_game.away_q4_score = live_game.away_score
                    LiveGameService._snapshot_quarter_stats(
                        session, live_game, 4,
                        home_team_abbr, away_team_abbr, socketio
                    )

                LiveGameService._migrate_to_match(session, live_game)

                # Generate AI summary if not already done
                if not live_game.ai_summary:
                    LiveGameService._generate_ai_summary(session, live_game)

                session.commit()

                # Launch post-game stats analysis in background (delayed)
                if not live_game.post_game_analysis:
                    game_id = live_game.id
                    home_name = live_game.home_team.name
                    away_name = live_game.away_team.name

                    def _run_post_game_analysis():
                        try:
                            # Wait for Footywire to publish stats
                            time.sleep(120)
                            from app.services.game_summary_service import game_summary_service
                            analysis = game_summary_service.generate_post_game_analysis(
                                home_team=home_name,
                                away_team=away_name,
                            )
                            if analysis:
                                from app.data.database import get_session as get_db_session
                                with get_db_session() as s:
                                    lg = s.query(LiveGame).filter_by(id=game_id).first()
                                    if lg:
                                        lg.post_game_analysis = analysis
                                if socketio:
                                    socketio.emit(
                                        "post_game_analysis",
                                        {"game_id": game_id, "analysis": analysis},
                                        namespace="/",
                                    )
                                    logger.info(f"Emitted post_game_analysis for game {game_id}")
                        except Exception as e:
                            logger.error(f"Error generating post-game analysis for game {game_id}: {e}")

                    thread = threading.Thread(target=_run_post_game_analysis, daemon=True)
                    thread.start()

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
    def _detect_scoring_events(
        session: Session,
        live_game: LiveGame,
        prev_home_score: int,
        prev_away_score: int,
        socketio=None,
        home_team_abbr: str = None,
        away_team_abbr: str = None,
        home_team_name: str = None,
        away_team_name: str = None
    ):
        """
        Detect and create scoring events based on score changes.

        Creates events for single goals (6 points) or behinds (1 point).
        For larger gaps (backend restart), creates one event per team with the new score.
        """
        home_diff = live_game.home_score - prev_home_score
        away_diff = live_game.away_score - prev_away_score

        if home_diff <= 0 and away_diff <= 0:
            return  # No scoring changes

        # Use pre-fetched team data if available, otherwise fetch now
        if not home_team_abbr:
            home_team_abbr = live_game.home_team.abbreviation
        if not away_team_abbr:
            away_team_abbr = live_game.away_team.abbreviation
        if not home_team_name:
            home_team_name = live_game.home_team.name
        if not away_team_name:
            away_team_name = live_game.away_team.name

        events_created = []

        # Use final scores for all events (ensures consistent baseline for next update)
        final_home_score = live_game.home_score
        final_away_score = live_game.away_score

        # Home team scored
        if home_diff > 0:
            # Determine event type: 6 = goal, 1 = behind, other = multiple events missed
            if home_diff == 6:
                event_type = "goal"
            elif home_diff == 1:
                event_type = "behind"
            else:
                # Multiple events missed - create a single "catch-up" goal event
                event_type = "goal"

            event = LiveGameEvent(
                game_id=live_game.id,
                event_type=event_type,
                team_id=live_game.home_team_id,
                home_score_after=final_home_score,
                away_score_after=final_away_score,
                quarter=live_game.current_quarter,
                time_str=live_game.time_str,
            )
            session.add(event)
            events_created.append((event_type, "home", None))
            logger.info(
                f"🎯 {event_type.upper()}: {home_team_abbr}"
                f" - {final_home_score} - {final_away_score}"
            )

        # Away team scored
        if away_diff > 0:
            if away_diff == 6:
                event_type = "goal"
            elif away_diff == 1:
                event_type = "behind"
            else:
                event_type = "goal"

            event = LiveGameEvent(
                game_id=live_game.id,
                event_type=event_type,
                team_id=live_game.away_team_id,
                home_score_after=final_home_score,
                away_score_after=final_away_score,
                quarter=live_game.current_quarter,
                time_str=live_game.time_str,
            )
            session.add(event)
            events_created.append((event_type, "away", None))
            logger.info(
                f"🎯 {event_type.upper()}: {away_team_abbr}"
                f" - {final_home_score} - {final_away_score}"
            )

        session.commit()

        # Refresh events to get their IDs for backfill tracking
        session.flush()

        # Broadcast each event
        if events_created and socketio:
            for event_type, team_side, scorer_info in events_created:
                team_name = home_team_name if team_side == "home" else away_team_name
                team_abbr = home_team_abbr if team_side == "home" else away_team_abbr
                LiveGameService._broadcast_scoring_event_with_data(
                    socketio, live_game.id, event_type, team_side, team_name, team_abbr,
                    final_home_score, final_away_score, live_game.time_str, scorer_info
                )

    @staticmethod
    def _backfill_missing_players(
        session: Session,
        live_game: LiveGame,
        home_team_abbr: str,
        away_team_abbr: str
    ):
        """
        Try to backfill player names for events that are missing them.

        This handles the case where API-Sports data wasn't available when the
        event was first detected, but may be available now.

        Uses a pool-based approach: if a player has 3 goals, they can be assigned
        to 3 different goal events.
        """
        try:
            from app.services.api_sports_service import APISportsService

            # Get ALL goal events ordered by timestamp
            all_goal_events = (
                session.query(LiveGameEvent)
                .filter(
                    LiveGameEvent.game_id == live_game.id,
                    LiveGameEvent.event_type == "goal"
                )
                .order_by(LiveGameEvent.timestamp.asc())
                .all()
            )

            # Check if any events need backfilling
            events_without_player = [e for e in all_goal_events if not e.player_name]
            if not events_without_player:
                return

            # Get current scorer list from API-Sports
            date_str = live_game.match_date.strftime("%Y-%m-%d") if live_game.match_date else None
            game = APISportsService.get_game_by_teams(home_team_abbr, away_team_abbr, game_date=date_str)

            if not game:
                return

            api_game_id = game.get("game", {}).get("id")
            if not api_game_id:
                return

            stats = APISportsService.get_game_player_stats(api_game_id)
            if not stats or "teams" not in stats:
                return

            # Build scorer pools: one entry per goal scored
            home_team_api_id = APISportsService.get_team_api_id(home_team_abbr)
            away_team_api_id = APISportsService.get_team_api_id(away_team_abbr)

            team_scorer_pool = {}  # team_id -> [(player_name, player_id), ...]

            for team_data in stats.get("teams", []):
                api_team_id = team_data.get("team", {}).get("id")

                if api_team_id == home_team_api_id:
                    our_team_id = live_game.home_team_id
                elif api_team_id == away_team_api_id:
                    our_team_id = live_game.away_team_id
                else:
                    continue

                pool = []
                for player in team_data.get("players", []):
                    goals = player.get("goals", {}).get("total", 0) or 0
                    if goals > 0:
                        player_id = player.get("player", {}).get("id")
                        player_obj = APISportsService.get_cached_player(player_id)
                        player_name = player_obj.get("name", "Unknown") if player_obj else "Unknown"
                        # Add one entry per goal
                        for _ in range(goals):
                            pool.append((player_name, player_id))

                team_scorer_pool[our_team_id] = pool

            # Track pool index per team (how many scorers we've used)
            team_pool_index = {team_id: 0 for team_id in team_scorer_pool}

            # Go through ALL events in order and assign/verify scorers
            for event in all_goal_events:
                team_id = event.team_id
                if team_id not in team_scorer_pool:
                    continue

                pool = team_scorer_pool[team_id]
                idx = team_pool_index[team_id]

                if event.player_name:
                    # Event already has a player - just advance the index
                    team_pool_index[team_id] = idx + 1
                elif idx < len(pool):
                    # Event needs a player and we have one available
                    player_name, player_id = pool[idx]
                    event.player_name = player_name
                    event.player_api_sports_id = player_id
                    team_pool_index[team_id] = idx + 1
                    logger.info(f"✓ Backfilled scorer: {player_name} for {home_team_abbr if team_id == live_game.home_team_id else away_team_abbr}")

            session.commit()

        except Exception as e:
            logger.warning(f"Error backfilling player info: {e}")

    @staticmethod
    def _get_scorer_from_api_sports(live_game: LiveGame, team_side: str) -> Optional[Dict]:
        """
        Get the most likely scorer from API-Sports player statistics.

        Uses goal count tracking to identify who just scored by comparing
        current goal counts with previous counts.
        """
        global _previous_goal_counts

        try:
            from app.services.api_sports_service import APISportsService

            # Get team abbreviation and API-Sports team ID
            team = live_game.home_team if team_side == "home" else live_game.away_team
            team_api_id = APISportsService.get_team_api_id(team.abbreviation)

            if not team_api_id:
                return None

            # Find the API-Sports game
            game = APISportsService.get_game_by_teams(
                live_game.home_team.abbreviation,
                live_game.away_team.abbreviation
            )

            if not game:
                return None

            api_game_id = game.get("game", {}).get("id")
            if not api_game_id:
                return None

            # Get player stats
            stats = APISportsService.get_game_player_stats(api_game_id)
            if not stats or "teams" not in stats:
                return None

            # Initialize tracking for this game if needed
            if live_game.id not in _previous_goal_counts:
                _previous_goal_counts[live_game.id] = {"home": {}, "away": {}}

            prev_counts = _previous_goal_counts[live_game.id][team_side]

            # Find the team's players
            for team_data in stats.get("teams", []):
                if team_data.get("team", {}).get("id") != team_api_id:
                    continue

                new_scorer = None
                current_counts = {}

                for player in team_data.get("players", []):
                    player_id = player.get("player", {}).get("id")
                    goals = player.get("goals", {}).get("total", 0)
                    current_counts[player_id] = goals

                    # Check if this player's goals increased
                    prev_goals = prev_counts.get(player_id, 0)
                    if goals > prev_goals:
                        # This player scored!
                        player_obj = APISportsService.get_cached_player(player_id)
                        new_scorer = {
                            "player_id": player_id,
                            "player_name": player_obj.get("name", "Unknown") if player_obj else "Unknown",
                            "jersey_number": player.get("player", {}).get("number"),
                            "total_goals": goals,
                        }

                # Update tracking
                _previous_goal_counts[live_game.id][team_side] = current_counts

                if new_scorer:
                    return new_scorer

        except Exception as e:
            logger.warning(f"Error getting scorer from API-Sports: {e}")

        return None

    @staticmethod
    def _get_scorer_from_api_sports_safe(
        home_team_abbr: str,
        away_team_abbr: str,
        team_side: str,
        game_date: Optional[datetime] = None
    ) -> Optional[Dict]:
        """
        Get the most likely scorer from API-Sports player statistics.
        Safe version that takes team abbreviations directly (no ORM objects).

        Uses goal count tracking to identify which player just scored.

        Args:
            home_team_abbr: Home team abbreviation
            away_team_abbr: Away team abbreviation
            team_side: "home" or "away"
            game_date: Date of the game (optional, defaults to today)
        """
        global _previous_goal_counts

        try:
            from app.services.api_sports_service import APISportsService

            # Get team API ID
            team_abbr = home_team_abbr if team_side == "home" else away_team_abbr
            team_api_id = APISportsService.get_team_api_id(team_abbr)

            if not team_api_id:
                return None

            # Format game date for API-Sports (YYYY-MM-DD)
            date_str = None
            if game_date:
                date_str = game_date.strftime("%Y-%m-%d")

            # Find the API-Sports game
            game = APISportsService.get_game_by_teams(home_team_abbr, away_team_abbr, game_date=date_str)

            if not game:
                return None

            api_game_id = game.get("game", {}).get("id")
            if not api_game_id:
                return None

            # Get player stats
            stats = APISportsService.get_game_player_stats(api_game_id)
            if not stats or "teams" not in stats:
                return None

            # Initialize tracking for this game if needed
            if api_game_id not in _previous_goal_counts:
                _previous_goal_counts[api_game_id] = {"home": {}, "away": {}}

            prev_counts = _previous_goal_counts[api_game_id][team_side]

            # Find which player's goal count increased
            for team_data in stats.get("teams", []):
                if team_data.get("team", {}).get("id") != team_api_id:
                    continue

                new_scorer = None
                current_counts = {}

                for player in team_data.get("players", []):
                    player_id = player.get("player", {}).get("id")
                    goals = player.get("goals", {}).get("total", 0) or 0
                    current_counts[player_id] = goals

                    # Check if this player's goals increased
                    prev_goals = prev_counts.get(player_id, 0)
                    if goals > prev_goals:
                        # This player scored!
                        player_obj = APISportsService.get_cached_player(player_id)
                        new_scorer = {
                            "player_id": player_id,
                            "player_name": player_obj.get("name", "Unknown") if player_obj else "Unknown",
                            "jersey_number": player.get("player", {}).get("number"),
                            "total_goals": goals,
                        }
                        logger.info(f"✓ Detected scorer: {new_scorer['player_name']} ({prev_goals} → {goals} goals) for {team_abbr}")
                        # Don't break - keep checking to build full current_counts

                if new_scorer:
                    # Only update tracking when we found someone — avoids
                    # the race where API-Sports hasn't updated yet and we'd
                    # lock in stale counts, misattributing the goal later.
                    _previous_goal_counts[api_game_id][team_side] = current_counts
                    return new_scorer

                # No goal increase detected — DON'T update tracking counts.
                # The backfill logic will fix this event later when API-Sports catches up.
                logger.warning(f"No goal increase detected for {team_abbr} (API-Sports may not be updated yet)")
                return None

        except Exception as e:
            logger.warning(f"Error getting scorer from API-Sports (safe): {e}")

        return None

    @staticmethod
    def _get_behind_kicker_from_api_sports(
        home_team_abbr: str,
        away_team_abbr: str,
        team_side: str,
        game_date: Optional[datetime] = None
    ) -> Optional[Dict]:
        """
        Get the player who kicked a behind by tracking per-player behind counts.
        Same approach as goal detection but using the behinds stat.
        """
        global _previous_behind_counts

        try:
            from app.services.api_sports_service import APISportsService

            team_abbr = home_team_abbr if team_side == "home" else away_team_abbr
            team_api_id = APISportsService.get_team_api_id(team_abbr)

            if not team_api_id:
                return None

            date_str = None
            if game_date:
                date_str = game_date.strftime("%Y-%m-%d")

            game = APISportsService.get_game_by_teams(home_team_abbr, away_team_abbr, game_date=date_str)
            if not game:
                return None

            api_game_id = game.get("game", {}).get("id")
            if not api_game_id:
                return None

            stats = APISportsService.get_game_player_stats(api_game_id)
            if not stats or "teams" not in stats:
                return None

            if api_game_id not in _previous_behind_counts:
                _previous_behind_counts[api_game_id] = {"home": {}, "away": {}}

            prev_counts = _previous_behind_counts[api_game_id][team_side]

            for team_data in stats.get("teams", []):
                if team_data.get("team", {}).get("id") != team_api_id:
                    continue

                new_kicker = None
                current_counts = {}

                for player in team_data.get("players", []):
                    player_id = player.get("player", {}).get("id")
                    behinds = player.get("behinds", 0) or 0
                    current_counts[player_id] = behinds

                    prev_behinds = prev_counts.get(player_id, 0)
                    if behinds > prev_behinds:
                        player_obj = APISportsService.get_cached_player(player_id)
                        new_kicker = {
                            "player_id": player_id,
                            "player_name": player_obj.get("name", "Unknown") if player_obj else "Unknown",
                            "jersey_number": player.get("player", {}).get("number"),
                        }
                        logger.info(f"✓ Detected behind kicker: {new_kicker['player_name']} ({prev_behinds} → {behinds} behinds) for {team_abbr}")

                if new_kicker:
                    # Only update tracking when we found someone
                    _previous_behind_counts[api_game_id][team_side] = current_counts
                    return new_kicker

                return None

        except Exception as e:
            logger.warning(f"Error getting behind kicker from API-Sports: {e}")

        return None

    @staticmethod
    def _get_cached_stats(api_game_id: int):
        """Get cached stats or return None if expired."""
        if api_game_id in _stats_cache:
            data, ts = _stats_cache[api_game_id]
            if time.time() - ts < _STATS_CACHE_TTL:
                return data
        return None

    @staticmethod
    def _cache_stats(api_game_id: int, data):
        """Cache stats response."""
        _stats_cache[api_game_id] = (data, time.time())

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
        """Snapshot player stats at quarter break and trigger summary generation."""
        try:
            from app.services.api_sports_service import APISportsService

            # Check if snapshot already exists
            existing = session.query(QuarterSnapshot).filter_by(
                game_id=live_game.id, quarter=quarter
            ).first()
            if existing:
                return

            date_str = live_game.match_date.strftime("%Y-%m-%d") if live_game.match_date else None
            game = APISportsService.get_game_by_teams(home_team_abbr, away_team_abbr, game_date=date_str)
            if not game:
                return

            api_game_id = game.get("game", {}).get("id")
            if not api_game_id:
                return

            stats = APISportsService.get_game_player_stats(api_game_id)
            if not stats or "teams" not in stats:
                return

            # Cache the stats for milestone detection
            LiveGameService._cache_stats(api_game_id, stats)

            # Build player stats array
            player_stats_list = []
            for team_data in stats.get("teams", []):
                team_name = team_data.get("team", {}).get("name", "Unknown")
                for player in team_data.get("players", []):
                    player_id = player.get("player", {}).get("id")
                    player_obj = APISportsService.get_cached_player(player_id)
                    player_name = player_obj.get("name", "Unknown") if player_obj else "Unknown"

                    goals = player.get("goals", {}).get("total", 0) or 0
                    behinds = player.get("behinds", 0) or 0
                    kicks = player.get("kicks", 0) or 0
                    handballs = player.get("handballs", 0) or 0
                    marks = player.get("marks", 0) or 0
                    tackles = player.get("tackles", 0) or 0

                    disposals = kicks + handballs

                    player_stats_list.append({
                        "player_id": player_id,
                        "name": player_name,
                        "team": team_name,
                        "goals": goals,
                        "behinds": behinds,
                        "disposals": disposals,
                        "kicks": kicks,
                        "handballs": handballs,
                        "marks": marks,
                        "tackles": tackles,
                    })

            # Create snapshot
            snapshot = QuarterSnapshot(
                game_id=live_game.id,
                quarter=quarter,
                player_stats=player_stats_list,
            )
            session.add(snapshot)
            session.commit()

            logger.info(f"Created Q{quarter} snapshot for game {live_game.id} with {len(player_stats_list)} players")

            # Generate quarter summary in background thread
            game_id = live_game.id
            home_score = live_game.home_score
            away_score = live_game.away_score
            home_name = live_game.home_team.name
            away_name = live_game.away_team.name

            def generate_summary():
                try:
                    from app.services.game_summary_service import game_summary_service

                    # Get top performers for this quarter
                    top_performers = sorted(
                        player_stats_list,
                        key=lambda x: x.get("disposals", 0),
                        reverse=True
                    )[:5]

                    summary = game_summary_service.generate_quarter_summary(
                        quarter=quarter,
                        home_team=home_name,
                        away_team=away_name,
                        home_score=home_score,
                        away_score=away_score,
                        quarter_stats=top_performers,
                    )

                    if summary:
                        from app.data.database import get_session as get_db_session
                        with get_db_session() as s:
                            snap = s.query(QuarterSnapshot).filter_by(
                                game_id=game_id, quarter=quarter
                            ).first()
                            if snap:
                                snap.quarter_summary = summary

                            lg = s.query(LiveGame).filter_by(id=game_id).first()
                            if lg:
                                summaries = dict(lg.quarter_summaries or {})
                                summaries[str(quarter)] = summary
                                lg.quarter_summaries = summaries
                                flag_modified(lg, 'quarter_summaries')

                        # Emit WebSocket event
                        if socketio:
                            socketio.emit(
                                "quarter_summary",
                                {
                                    "game_id": game_id,
                                    "quarter": quarter,
                                    "summary": summary,
                                },
                                namespace="/",
                            )
                            logger.info(f"Emitted quarter_summary for game {game_id} Q{quarter}")

                except Exception as e:
                    logger.error(f"Error generating quarter summary: {e}")

            thread = threading.Thread(target=generate_summary, daemon=True)
            thread.start()

        except Exception as e:
            logger.error(f"Error creating quarter snapshot: {e}")

    @staticmethod
    def _detect_milestone_events(
        session: Session,
        live_game: LiveGame,
        home_team_abbr: str,
        away_team_abbr: str,
        socketio=None
    ):
        """Detect player milestone events (goal hauls, disposal counts, fantasy scores)."""
        global _emitted_milestones, _polling_cycles

        if live_game.status != "live":
            return

        # Only run every 3rd polling cycle (~60s)
        cycle = _polling_cycles.get(live_game.id, 0) + 1
        _polling_cycles[live_game.id] = cycle
        if cycle % 3 != 0:
            return

        try:
            from app.services.api_sports_service import APISportsService

            date_str = live_game.match_date.strftime("%Y-%m-%d") if live_game.match_date else None
            game = APISportsService.get_game_by_teams(home_team_abbr, away_team_abbr, game_date=date_str)
            if not game:
                return

            api_game_id = game.get("game", {}).get("id")
            if not api_game_id:
                return

            # Try cached stats first
            stats = LiveGameService._get_cached_stats(api_game_id)
            if not stats:
                stats = APISportsService.get_game_player_stats(api_game_id)
                if stats:
                    LiveGameService._cache_stats(api_game_id, stats)
            if not stats or "teams" not in stats:
                return

            if live_game.id not in _emitted_milestones:
                _emitted_milestones[live_game.id] = set()

            home_team_api_id = APISportsService.get_team_api_id(home_team_abbr)
            away_team_api_id = APISportsService.get_team_api_id(away_team_abbr)

            for team_data in stats.get("teams", []):
                api_team_id = team_data.get("team", {}).get("id")
                if api_team_id == home_team_api_id:
                    our_team_id = live_game.home_team_id
                    team_name = live_game.home_team.name
                    team_abbr = home_team_abbr
                elif api_team_id == away_team_api_id:
                    our_team_id = live_game.away_team_id
                    team_name = live_game.away_team.name
                    team_abbr = away_team_abbr
                else:
                    continue

                for player in team_data.get("players", []):
                    player_id = player.get("player", {}).get("id")
                    player_obj = APISportsService.get_cached_player(player_id)
                    player_name = player_obj.get("name", "Unknown") if player_obj else "Unknown"

                    goals = player.get("goals", {}).get("total", 0) or 0
                    behinds_val = player.get("behinds", 0) or 0
                    kicks = player.get("kicks", 0) or 0
                    handballs = player.get("handballs", 0) or 0
                    marks = player.get("marks", 0) or 0
                    tackles = player.get("tackles", 0) or 0
                    hitouts = player.get("hitouts", 0) or 0
                    free_kicks = player.get("free_kicks", {})
                    free_for = free_kicks.get("for", 0) or 0
                    free_against = free_kicks.get("against", 0) or 0

                    disposals = kicks + handballs
                    fantasy = (
                        (kicks * 3) + (handballs * 2) + (marks * 3) +
                        (tackles * 4) + (goals * 6) + (behinds_val * 1) +
                        (hitouts * 1) + (free_for * 1) + (free_against * -3)
                    )

                    # Check goal milestones
                    goal_milestones = {2: "2nd goal", 3: "3 goals!", 4: "4-goal haul!", 5: "5+ goals!"}
                    for threshold, desc in goal_milestones.items():
                        if goals >= threshold:
                            key = f"player_{player_id}_goals_{threshold}"
                            if key not in _emitted_milestones[live_game.id]:
                                _emitted_milestones[live_game.id].add(key)
                                LiveGameService._create_milestone_event(
                                    session, live_game, "milestone_goals",
                                    our_team_id, player_name, player_id,
                                    f"{player_name} - {desc}",
                                    team_name, team_abbr, socketio
                                )

                    # Check disposal milestones
                    disp_milestones = {20: "20 disposals", 30: "30 disposals - dominating", 40: "40 disposals!", 50: "50 disposals!"}
                    for threshold, desc in disp_milestones.items():
                        if disposals >= threshold:
                            key = f"player_{player_id}_disposals_{threshold}"
                            if key not in _emitted_milestones[live_game.id]:
                                _emitted_milestones[live_game.id].add(key)
                                LiveGameService._create_milestone_event(
                                    session, live_game, "milestone_disposals",
                                    our_team_id, player_name, player_id,
                                    f"{player_name} - {desc}",
                                    team_name, team_abbr, socketio
                                )

                    # Check fantasy milestones
                    fantasy_milestones = {100: "100 fantasy pts", 150: "150 fantasy - elite game!"}
                    for threshold, desc in fantasy_milestones.items():
                        if fantasy >= threshold:
                            key = f"player_{player_id}_fantasy_{threshold}"
                            if key not in _emitted_milestones[live_game.id]:
                                _emitted_milestones[live_game.id].add(key)
                                LiveGameService._create_milestone_event(
                                    session, live_game, "milestone_fantasy",
                                    our_team_id, player_name, player_id,
                                    f"{player_name} - {desc}",
                                    team_name, team_abbr, socketio
                                )

                    # Check behind milestones
                    if behinds_val >= 5:
                        key = f"player_{player_id}_behinds_5"
                        if key not in _emitted_milestones[live_game.id]:
                            _emitted_milestones[live_game.id].add(key)
                            LiveGameService._create_milestone_event(
                                session, live_game, "milestone_behinds",
                                our_team_id, player_name, player_id,
                                f"{player_name} - 5 behinds - can't buy a goal!",
                                team_name, team_abbr, socketio
                            )

            session.commit()

        except Exception as e:
            logger.warning(f"Error detecting milestones: {e}")

    @staticmethod
    def _create_milestone_event(
        session: Session,
        live_game: LiveGame,
        event_type: str,
        team_id: int,
        player_name: str,
        player_api_sports_id: int,
        description: str,
        team_name: str,
        team_abbr: str,
        socketio=None
    ):
        """Create a milestone LiveGameEvent and broadcast it."""
        event = LiveGameEvent(
            game_id=live_game.id,
            event_type=event_type,
            team_id=team_id,
            player_name=player_name,
            player_api_sports_id=player_api_sports_id,
            home_score_after=live_game.home_score,
            away_score_after=live_game.away_score,
            quarter=live_game.current_quarter,
            time_str=live_game.time_str,
            description=description,
        )
        session.add(event)

        logger.info(f"🏆 Milestone: {description} ({team_abbr})")

        if socketio:
            socketio.emit(
                "live_game_event",
                {
                    "game_id": live_game.id,
                    "event_type": event_type,
                    "team_side": "home" if team_id == live_game.home_team_id else "away",
                    "team_name": team_name,
                    "team_abbreviation": team_abbr,
                    "home_score": live_game.home_score,
                    "away_score": live_game.away_score,
                    "time_str": live_game.time_str,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "player_name": player_name,
                    "is_milestone": True,
                    "milestone_type": event_type.replace("milestone_", ""),
                    "description": description,
                },
                namespace="/",
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
    def _broadcast_scoring_event(
        socketio,
        live_game: LiveGame,
        event_type: str,
        team_side: str,
        scorer_info: Optional[Dict] = None
    ):
        """Broadcast scoring event to all clients (for popup notifications)."""
        try:
            team = live_game.home_team if team_side == "home" else live_game.away_team

            event_data = {
                "game_id": live_game.id,
                "event_type": event_type,
                "team_side": team_side,
                "team_name": team.name,
                "team_abbreviation": team.abbreviation,
                "home_score": live_game.home_score,
                "away_score": live_game.away_score,
                "time_str": live_game.time_str,
                "timestamp": datetime.utcnow().isoformat() + "Z",  # UTC timestamp
            }

            # Add player info if available
            if scorer_info:
                event_data["player_name"] = scorer_info.get("player_name")
                event_data["player_id"] = scorer_info.get("player_id")
                event_data["jersey_number"] = scorer_info.get("jersey_number")
                event_data["player_total_goals"] = scorer_info.get("total_goals")

            socketio.emit(
                "live_game_event",
                event_data,
                namespace="/",  # Broadcast to all clients
            )
        except Exception as e:
            logger.error(f"Error broadcasting scoring event: {e}")

    @staticmethod
    def _broadcast_scoring_event_with_data(
        socketio,
        game_id: int,
        event_type: str,
        team_side: str,
        team_name: str,
        team_abbr: str,
        home_score: int,
        away_score: int,
        time_str: str,
        scorer_info: Optional[Dict] = None
    ):
        """Broadcast scoring event with pre-extracted data (avoids detached instance issues)."""
        try:
            event_data = {
                "game_id": game_id,
                "event_type": event_type,
                "team_side": team_side,
                "team_name": team_name,
                "team_abbreviation": team_abbr,
                "home_score": home_score,
                "away_score": away_score,
                "time_str": time_str,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            if scorer_info:
                event_data["player_name"] = scorer_info.get("player_name")
                event_data["player_id"] = scorer_info.get("player_id")
                event_data["jersey_number"] = scorer_info.get("jersey_number")
                event_data["player_total_goals"] = scorer_info.get("total_goals")

            logger.info(f"📡 Broadcasting event: {event_type} {team_abbr} {home_score}-{away_score}")
            socketio.emit(
                "live_game_event",
                event_data,
                namespace="/",
            )
            logger.info(f"📡 Broadcast complete")
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
    def _generate_ai_summary(session: Session, live_game: LiveGame):
        """
        Generate an AI summary for a completed game.

        Fetches player stats from API-Sports and uses OpenAI to generate
        a casual match summary with team nicknames.
        """
        try:
            from app.services.api_sports_service import APISportsService
            from app.services.game_summary_service import game_summary_service

            logger.info(f"Generating AI summary for game {live_game.id}")

            # Get player stats from API-Sports
            player_stats = None
            try:
                home_team_abbr = live_game.home_team.abbreviation
                away_team_abbr = live_game.away_team.abbreviation
                date_str = live_game.match_date.strftime("%Y-%m-%d") if live_game.match_date else None

                game = APISportsService.get_game_by_teams(home_team_abbr, away_team_abbr, game_date=date_str)
                if game:
                    api_game_id = game.get("game", {}).get("id")
                    if api_game_id:
                        stats = APISportsService.get_game_player_stats(api_game_id)
                        if stats and "teams" in stats:
                            player_stats = LiveGameService._format_player_stats_for_summary(
                                stats, live_game, home_team_abbr, away_team_abbr
                            )
            except Exception as e:
                logger.warning(f"Could not fetch player stats for summary: {e}")

            # Generate the summary
            summary = game_summary_service.generate_summary(live_game, player_stats)
            if summary:
                live_game.ai_summary = summary
                logger.info(f"AI summary generated for game {live_game.id}")
            else:
                logger.warning(f"Failed to generate AI summary for game {live_game.id}")

        except Exception as e:
            logger.error(f"Error generating AI summary: {e}")

    @staticmethod
    def _format_player_stats_for_summary(
        stats: Dict,
        live_game: LiveGame,
        home_team_abbr: str,
        away_team_abbr: str
    ) -> Dict:
        """
        Format API-Sports player stats for the summary generator.

        Returns a dict with top_goal_kickers, top_disposals, and top_fantasy.
        """
        from app.services.api_sports_service import APISportsService

        home_team_api_id = APISportsService.get_team_api_id(home_team_abbr)
        away_team_api_id = APISportsService.get_team_api_id(away_team_abbr)

        all_players = []

        for team_data in stats.get("teams", []):
            api_team_id = team_data.get("team", {}).get("id")
            team_name = team_data.get("team", {}).get("name", "Unknown")

            for player in team_data.get("players", []):
                player_id = player.get("player", {}).get("id")
                player_obj = APISportsService.get_cached_player(player_id)
                player_name = player_obj.get("name", "Unknown") if player_obj else "Unknown"

                # Extract stats (direct integers, not nested)
                goals = player.get("goals", {}).get("total", 0) or 0
                behinds = player.get("behinds", 0) or 0
                kicks = player.get("kicks", 0) or 0
                handballs = player.get("handballs", 0) or 0
                marks = player.get("marks", 0) or 0
                tackles = player.get("tackles", 0) or 0
                hitouts = player.get("hitouts", 0) or 0
                free_kicks = player.get("free_kicks", {})
                free_for = free_kicks.get("for", 0) or 0
                free_against = free_kicks.get("against", 0) or 0

                disposals = kicks + handballs

                # AFL Fantasy scoring formula (official):
                # Kick: 3, Handball: 2, Mark: 3, Tackle: 4, Goal: 6,
                # Behind: 1, Hitout: 1, Free For: 1, Free Against: -3
                fantasy = (
                    (kicks * 3) +
                    (handballs * 2) +
                    (marks * 3) +
                    (tackles * 4) +
                    (goals * 6) +
                    (behinds * 1) +
                    (hitouts * 1) +
                    (free_for * 1) +
                    (free_against * -3)
                )

                all_players.append({
                    "name": player_name,
                    "team": team_name,
                    "goals": goals,
                    "disposals": disposals,
                    "points": fantasy,
                })

        # Sort and extract top performers
        result = {
            "top_goal_kickers": sorted(
                [p for p in all_players if p["goals"] > 0],
                key=lambda x: x["goals"],
                reverse=True
            )[:3],
            "top_disposals": sorted(
                all_players,
                key=lambda x: x["disposals"],
                reverse=True
            )[:3],
            "top_fantasy": sorted(
                all_players,
                key=lambda x: x["points"],
                reverse=True
            )[:3],
        }

        return result

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

            if live_games:
                # Live games exist - only show completed games from current round within last 30 minutes
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
                games = live_games + completed_games
            else:
                # No live games - show all games from current round within time window
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                games = (
                    session.query(LiveGame)
                    .options(joinedload(LiveGame.home_team))
                    .options(joinedload(LiveGame.away_team))
                    .filter(
                        LiveGame.season == current_season,
                        LiveGame.round == current_round,
                        LiveGame.last_updated >= cutoff
                    )
                    .order_by(LiveGame.match_date.desc())
                    .all()
                )

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
