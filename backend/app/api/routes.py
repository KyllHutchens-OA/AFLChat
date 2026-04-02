"""
AFL Analytics Agent - API Routes
"""
from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from app.data.database import Session
from app.data.models import Match, Team, PageView
from app.utils.validators import PageViewRequest, ChatMessageRequest
from app.middleware.rate_limiter import limiter
from datetime import datetime, timedelta
from sqlalchemy import func
import os
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint for Railway."""
    health = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'checks': {}
    }

    # Database check
    try:
        session = Session()
        match_count = session.query(Match).count()
        team_count = session.query(Team).count()
        session.close()
        health['checks']['database'] = {
            'status': 'ok',
            'matches': match_count,
            'teams': team_count
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health['status'] = 'degraded'
        health['checks']['database'] = {'status': 'error', 'message': 'Database unavailable'}

    # OpenAI API key check
    openai_key = os.getenv("OPENAI_API_KEY")
    health['checks']['openai'] = 'configured' if openai_key else 'missing'
    if not openai_key:
        health['status'] = 'degraded'

    # Return appropriate status code
    status_code = 200 if health['status'] == 'healthy' else 503
    return jsonify(health), status_code


@bp.route('/chat/message', methods=['POST'])
@limiter.limit("10 per minute")
async def chat_message():
    """
    Handle chat messages (REST endpoint for non-streaming).
    For streaming, use WebSocket instead.
    """
    try:
        # Validate input
        try:
            data = ChatMessageRequest(**request.get_json())
        except ValidationError as e:
            details = [{'field': '.'.join(str(l) for l in err['loc']), 'message': err['msg']}
                       for err in e.errors()]
            return jsonify({'error': 'Invalid input', 'details': details}), 400

        message = data.message
        conversation_id = data.conversation_id

        # Import agent
        from app.agent import agent

        # Run agent workflow
        final_state = await agent.run(message, conversation_id)

        # Return response
        return jsonify({
            'conversation_id': conversation_id or 'new-conv-id',
            'status': 'complete',
            'response': final_state.get('natural_language_summary', 'Unable to process query'),
            'confidence': final_state.get('confidence', 0.0),
            'sources': final_state.get('sources', [])
        }), 200

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@bp.route('/conversations/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    """Get conversation history."""
    try:
        from app.services.conversation_service import ConversationService

        data = ConversationService.get_conversation(conversation_id)
        if not data:
            return jsonify({'error': 'Conversation not found'}), 404

        return jsonify({
            'conversation_id': data['id'],
            'messages': data['messages'],
            'created_at': data['created_at']
        }), 200

    except Exception as e:
        logger.error(f"Error retrieving conversation: {e}")
        return jsonify({'error': 'Failed to retrieve conversation'}), 500


# ==================== ANALYTICS ENDPOINTS ====================

@bp.route('/analytics/track', methods=['POST'])
@limiter.limit("60 per minute")
def track_page_view():
    """Track a page view with input validation."""
    try:
        # Validate input
        try:
            data = PageViewRequest(**request.get_json())
        except ValidationError as e:
            details = [{'field': '.'.join(str(l) for l in err['loc']), 'message': err['msg']}
                       for err in e.errors()]
            return jsonify({'error': 'Invalid input', 'details': details}), 400

        # Get client IP address (handles proxies via X-Forwarded-For)
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address:
            # X-Forwarded-For can contain multiple IPs; take the first (client IP)
            ip_address = ip_address.split(',')[0].strip()

        session = Session()
        try:
            page_view = PageView(
                visitor_id=data.visitor_id,
                page=data.page,
                referrer=data.referrer,
                user_agent=data.user_agent,
                ip_address=ip_address
            )
            session.add(page_view)
            session.commit()
        finally:
            session.close()

        return jsonify({'status': 'tracked'}), 200

    except Exception as e:
        logger.error(f"Error tracking page view: {e}")
        return jsonify({'error': 'Failed to track'}), 500


@bp.route('/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Get analytics summary."""
    try:
        session = Session()

        # Get date range (default last 30 days)
        days = request.args.get('days', 30, type=int)
        since = datetime.utcnow() - timedelta(days=days)

        # Total page views
        total_views = session.query(PageView).filter(
            PageView.timestamp >= since
        ).count()

        # Unique visitors
        unique_visitors = session.query(
            func.count(func.distinct(PageView.visitor_id))
        ).filter(PageView.timestamp >= since).scalar()

        # Views per page
        views_per_page = session.query(
            PageView.page,
            func.count(PageView.id).label('views')
        ).filter(
            PageView.timestamp >= since
        ).group_by(PageView.page).order_by(func.count(PageView.id).desc()).all()

        # Views per day
        views_per_day = session.query(
            func.date(PageView.timestamp).label('date'),
            func.count(PageView.id).label('views')
        ).filter(
            PageView.timestamp >= since
        ).group_by(func.date(PageView.timestamp)).order_by(func.date(PageView.timestamp)).all()

        session.close()

        return jsonify({
            'period_days': days,
            'total_views': total_views,
            'unique_visitors': unique_visitors,
            'views_per_page': [{'page': p, 'views': v} for p, v in views_per_page],
            'views_per_day': [{'date': str(d), 'views': v} for d, v in views_per_day]
        }), 200

    except Exception as e:
        logger.error(f"Error getting analytics summary: {e}")
        return jsonify({'error': 'Failed to get analytics'}), 500


# ========== LIVE GAMES ENDPOINTS ==========

@bp.route('/live-games', methods=['GET'])
@limiter.exempt  # Exempt from rate limiting (polled frequently)
def get_live_games():
    """Get all currently live or recent games."""
    try:
        from app.services.live_game_service import LiveGameService

        # get_active_games now returns pre-serialized dicts
        games = LiveGameService.get_active_games(hours=2)

        # Convert datetime objects to ISO strings
        for game in games:
            if game.get('match_date'):
                game['match_date'] = game['match_date'].isoformat()
            if game.get('last_updated'):
                game['last_updated'] = game['last_updated'].isoformat()
            # Rename squiggle_game_id to squiggle_id for frontend compatibility
            game['squiggle_id'] = game.pop('squiggle_game_id', None)

        return jsonify({'games': games}), 200

    except Exception as e:
        logger.error(f"Error fetching live games: {e}")
        return jsonify({'error': 'Failed to fetch live games'}), 500


@bp.route('/live-games/<int:game_id>', methods=['GET'])
@limiter.exempt  # Exempt from rate limiting (polled frequently)
def get_live_game_detail(game_id):
    """Get detailed data for a specific live game including events."""
    try:
        from app.data.models import LiveGame, LiveGameEvent

        session = Session()
        game = session.query(LiveGame).filter_by(id=game_id).first()

        if not game:
            session.close()
            return jsonify({'error': 'Game not found'}), 404

        # Get events (last 50)
        events = (
            session.query(LiveGameEvent)
            .filter_by(game_id=game_id)
            .order_by(LiveGameEvent.timestamp.desc())
            .limit(50)
            .all()
        )

        events_data = []
        for event in events:
            events_data.append({
                'id': event.id,
                'event_type': event.event_type,
                'team': {
                    'id': event.team.id,
                    'name': event.team.name,
                    'abbreviation': event.team.abbreviation,
                } if event.team else None,
                'home_score_after': event.home_score_after,
                'away_score_after': event.away_score_after,
                'quarter': event.quarter,
                'time_str': event.time_str,
                'timestamp': event.timestamp.isoformat() + 'Z',  # UTC timestamp
                'player_name': event.player_name,
                'player_api_sports_id': event.player_api_sports_id,
                'description': event.description,
                'is_milestone': event.event_type.startswith('milestone_') if event.event_type else False,
                'milestone_type': event.event_type.replace('milestone_', '') if event.event_type and event.event_type.startswith('milestone_') else None,
            })

        # Game data
        game_data = {
            'id': game.id,
            'squiggle_id': game.squiggle_game_id,
            'season': game.season,
            'round': game.round,
            'home_team': {
                'id': game.home_team.id,
                'name': game.home_team.name,
                'abbreviation': game.home_team.abbreviation,
                'primary_color': game.home_team.primary_color,
                'secondary_color': game.home_team.secondary_color,
            },
            'away_team': {
                'id': game.away_team.id,
                'name': game.away_team.name,
                'abbreviation': game.away_team.abbreviation,
                'primary_color': game.away_team.primary_color,
                'secondary_color': game.away_team.secondary_color,
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
            'match_date': game.match_date.isoformat() if game.match_date else None,
            'last_updated': game.last_updated.isoformat() if game.last_updated else None,
            'events': events_data,
            # AI summary (only for completed games)
            'ai_summary': game.ai_summary if game.status == 'completed' else None,
            # Post-game stats analysis (only for completed games)
            'post_game_analysis': game.post_game_analysis if game.status == 'completed' else None,
            # Quarter summaries
            'quarter_summaries': game.quarter_summaries or {},
            # Quarter scores
            'quarter_scores': {
                'home': [game.home_q1_score, game.home_q2_score, game.home_q3_score, game.home_q4_score],
                'away': [game.away_q1_score, game.away_q2_score, game.away_q3_score, game.away_q4_score],
            },
        }

        session.close()

        return jsonify(game_data), 200

    except Exception as e:
        logger.error(f"Error fetching live game detail: {e}")
        return jsonify({'error': 'Failed to fetch game detail'}), 500


def _attach_predictions(upcoming: list, season: int):
    """Attach Squiggle predictions to upcoming matches."""
    try:
        from app.data.database import get_session
        from app.data.models import Match, Team, SquigglePrediction
        from sqlalchemy import desc

        with get_session() as session:
            for match in upcoming:
                match['prediction'] = None
                home_team = session.query(Team).filter_by(name=match['home_team']).first()
                away_team = session.query(Team).filter_by(name=match['away_team']).first()
                if not home_team or not away_team:
                    continue

                db_match = (
                    session.query(Match)
                    .filter(
                        Match.season == season,
                        Match.home_team_id == home_team.id,
                        Match.away_team_id == away_team.id,
                        Match.round == str(match.get('round', '')),
                    )
                    .first()
                )
                if not db_match:
                    continue

                prediction = (
                    session.query(SquigglePrediction)
                    .filter(
                        SquigglePrediction.match_id == db_match.id,
                        SquigglePrediction.source_model == 'Squiggle',
                    )
                    .order_by(desc(SquigglePrediction.prediction_date))
                    .first()
                )
                if prediction and prediction.predicted_winner:
                    winner = prediction.predicted_winner
                    match['prediction'] = {
                        'winner': winner.name,
                        'margin': float(prediction.predicted_margin) if prediction.predicted_margin else None,
                        'home_prob': float(prediction.home_win_probability) if prediction.home_win_probability else None,
                        'away_prob': float(prediction.away_win_probability) if prediction.away_win_probability else None,
                    }
    except Exception as e:
        logger.debug(f"Failed to attach predictions: {e}")


_upcoming_cache = {"data": None, "expires": 0}

@bp.route('/upcoming-matches', methods=['GET'])
@limiter.exempt  # Exempt from rate limiting (polled frequently)
def get_upcoming_matches():
    """Get upcoming scheduled AFL matches from Squiggle API."""
    import time as _time

    # Return cached data if fresh (2 min TTL)
    if _upcoming_cache["data"] is not None and _time.time() < _upcoming_cache["expires"]:
        return jsonify(_upcoming_cache["data"]), 200

    try:
        import requests
        from datetime import datetime
        from zoneinfo import ZoneInfo

        current_year = datetime.now().year
        aus_tz = ZoneInfo('Australia/Melbourne')
        now = datetime.now(aus_tz)

        # Determine the current/next round from live_games DB to avoid fetching all 200+ games
        from app.data.database import get_data_recency
        recency = get_data_recency()
        live_round = recency.get("live_latest_round")

        # Fetch only the next 2 rounds from Squiggle (much faster than full season)
        all_games = []
        start_round = int(live_round) + 1 if live_round else 1
        for r in range(start_round, start_round + 2):
            try:
                resp = requests.get(
                    f"https://api.squiggle.com.au/?q=games;year={current_year};round={r}",
                    headers={"User-Agent": "AFL-Analytics-App/1.0 (kyllhutchens@gmail.com)"},
                    timeout=10
                )
                if resp.status_code == 200:
                    all_games.extend(resp.json().get('games', []))
            except Exception as round_err:
                logger.warning(f"Failed to fetch round {r} from Squiggle: {round_err}")

        upcoming = []
        for game in all_games:
            date_str = game.get('date')
            if not date_str:
                continue

            try:
                if 'Z' in date_str or '+' in date_str:
                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    naive_date = datetime.fromisoformat(date_str)
                    game_date = naive_date.replace(tzinfo=aus_tz)
            except (ValueError, AttributeError):
                continue

            complete = game.get('complete', 0)
            if complete == 0 and game_date > now:
                upcoming.append({
                    'id': game.get('id'),
                    'round': game.get('round'),
                    'home_team': game.get('hteam'),
                    'away_team': game.get('ateam'),
                    'venue': game.get('venue'),
                    'date': game_date.isoformat(),
                    'complete': complete,
                    'is_final': game.get('is_final', False),
                })

        upcoming.sort(key=lambda x: x['date'])

        # Attach Squiggle predictions
        _attach_predictions(upcoming, current_year)

        # Attach previews from DB
        from app.services.match_preview_service import get_all_previews
        squiggle_ids = [m['id'] for m in upcoming if m.get('id')]
        previews = get_all_previews(squiggle_ids)
        for match in upcoming:
            match['preview'] = previews.get(match['id'])

        result = {'matches': upcoming}
        _upcoming_cache["data"] = result
        _upcoming_cache["expires"] = _time.time() + 120  # 2 min TTL

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error fetching upcoming matches: {e}")
        # Return stale cache if available, otherwise empty
        if _upcoming_cache["data"] is not None:
            return jsonify(_upcoming_cache["data"]), 200
        return jsonify({'matches': [], 'error': 'Squiggle API unavailable'}), 200


@bp.route('/live-games/<int:game_id>/stats', methods=['GET'])
@limiter.exempt
def get_game_stats(game_id):
    """Get top player stats for a game, served from cache."""
    try:
        from app.data.models import LiveGame, QuarterSnapshot
        from sqlalchemy.orm import joinedload
        from sqlalchemy import func

        session = Session()
        try:
            game = session.query(LiveGame).options(
                joinedload(LiveGame.home_team),
                joinedload(LiveGame.away_team)
            ).filter_by(id=game_id).first()

            if not game:
                return jsonify({'error': 'Game not found'}), 404

            # Serve from cache if available
            if game.stats_cache:
                return jsonify(game.stats_cache), 200

            # Cache miss — fetch live and cache the result
            from app.services.api_sports_service import APISportsService
            from sqlalchemy.orm.attributes import flag_modified

            stats = APISportsService.fetch_game_stats(game)

            if stats:
                game.stats_cache = stats
                game.stats_cache_updated_at = datetime.utcnow()
                flag_modified(game, 'stats_cache')
                session.commit()
                return jsonify(stats), 200

            # Fallback: build stats from the most recent QuarterSnapshot
            latest_snapshot = session.query(QuarterSnapshot).filter_by(
                game_id=game_id
            ).order_by(QuarterSnapshot.quarter.desc()).first()

            if latest_snapshot and latest_snapshot.player_stats:
                players = latest_snapshot.player_stats
                top_goals = sorted(players, key=lambda p: p.get('goals', 0), reverse=True)[:3]
                top_disposals = sorted(players, key=lambda p: p.get('disposals', 0), reverse=True)[:3]
                # Fantasy: 3*kicks + 2*handballs + 3*marks + 4*tackles + 6*goals + 1*behinds
                for p in players:
                    p['fantasy_points'] = (
                        3 * p.get('kicks', 0) + 2 * p.get('handballs', 0) +
                        3 * p.get('marks', 0) + 4 * p.get('tackles', 0) +
                        6 * p.get('goals', 0) + p.get('behinds', 0)
                    )
                top_fantasy = sorted(players, key=lambda p: p.get('fantasy_points', 0), reverse=True)[:3]

                return jsonify({
                    'top_goal_kickers': [{'name': p['name'], 'team': p['team'], 'goals': p.get('goals', 0)} for p in top_goals],
                    'top_disposals': [{'name': p['name'], 'team': p['team'], 'disposals': p.get('disposals', 0)} for p in top_disposals],
                    'top_fantasy': [{'name': p['name'], 'team': p['team'], 'points': p.get('fantasy_points', 0)} for p in top_fantasy],
                    'source': 'quarter_snapshot',
                }), 200

            return jsonify({
                'top_goal_kickers': [],
                'top_disposals': [],
                'top_fantasy': [],
                'message': 'Player stats not available for this game'
            }), 200

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error fetching game stats: {e}")
        return jsonify({'error': 'Failed to fetch game stats'}), 500
