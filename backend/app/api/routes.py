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
        health['checks']['database'] = {'status': 'error', 'message': str(e)}

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


@bp.route('/upcoming-matches', methods=['GET'])
@limiter.exempt  # Exempt from rate limiting (polled frequently)
def get_upcoming_matches():
    """Get upcoming scheduled AFL matches from Squiggle API."""
    try:
        import requests
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # Fetch from Squiggle API
        current_year = datetime.now().year
        response = requests.get(
            f"https://api.squiggle.com.au/?q=games;year={current_year}",
            headers={"User-Agent": "AFL-Analytics-App/1.0"},
            timeout=10
        )

        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch from Squiggle'}), 500

        data = response.json()
        games = data.get('games', [])

        # Filter for upcoming games (not started yet)
        # Get current time in Australian timezone for accurate comparison
        aus_tz = ZoneInfo('Australia/Melbourne')
        now = datetime.now(aus_tz)
        upcoming = []

        for game in games:
            # Parse date
            date_str = game.get('date')
            if not date_str:
                continue

            try:
                # Squiggle returns dates in Australian Eastern time without timezone info
                # Parse as naive datetime, then localize to Australian timezone
                if 'Z' in date_str or '+' in date_str:
                    # Already has timezone info
                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                else:
                    # No timezone info - assume Australian Eastern time
                    naive_date = datetime.fromisoformat(date_str)
                    game_date = naive_date.replace(tzinfo=aus_tz)
            except (ValueError, AttributeError):
                continue

            # Only include games that haven't started yet
            # A game has started if: complete > 0 OR current time > game time
            complete = game.get('complete', 0)
            if complete == 0 and game_date > now:
                upcoming.append({
                    'id': game.get('id'),
                    'round': game.get('round'),
                    'home_team': game.get('hteam'),
                    'away_team': game.get('ateam'),
                    'venue': game.get('venue'),
                    'date': game_date.isoformat(),  # Now includes timezone info
                    'complete': complete,
                    'is_final': game.get('is_final', False),
                })

        # Sort by date (earliest first)
        upcoming.sort(key=lambda x: x['date'])

        # Limit to next 10 games
        upcoming = upcoming[:10]

        return jsonify({'matches': upcoming}), 200

    except Exception as e:
        logger.error(f"Error fetching upcoming matches: {e}")
        return jsonify({'error': 'Failed to fetch upcoming matches'}), 500


@bp.route('/live-games/<int:game_id>/stats', methods=['GET'])
@limiter.exempt
def get_game_stats(game_id):
    """Get top player stats for a completed game."""
    try:
        from app.data.models import LiveGame
        from app.services.api_sports_service import APISportsService

        session = Session()
        game = session.query(LiveGame).filter_by(id=game_id).first()

        if not game:
            session.close()
            return jsonify({'error': 'Game not found'}), 404

        if game.status != 'completed':
            session.close()
            return jsonify({'error': 'Stats only available for completed games'}), 400

        # Get game date for API-Sports query
        game_date = game.match_date.strftime('%Y-%m-%d') if game.match_date else None

        # Find game in API-Sports by teams
        api_game = APISportsService.get_game_by_teams(
            game.home_team.abbreviation,
            game.away_team.abbreviation,
            game_date
        )

        if not api_game:
            session.close()
            return jsonify({
                'top_goal_kickers': [],
                'top_disposals': [],
                'top_fantasy': [],
                'message': 'Player stats not available for this game'
            }), 200

        # Get player stats - note: game ID is nested under 'game'
        api_game_id = api_game.get('game', {}).get('id') or api_game.get('id')
        stats_data = APISportsService.get_game_player_stats(api_game_id)

        if not stats_data:
            session.close()
            return jsonify({
                'top_goal_kickers': [],
                'top_disposals': [],
                'top_fantasy': [],
                'message': 'Player stats not available'
            }), 200

        # Get team names from the api_game response
        home_team_name = api_game.get('teams', {}).get('home', {}).get('name', 'Home')
        away_team_name = api_game.get('teams', {}).get('away', {}).get('name', 'Away')

        # Process player stats
        all_players = []
        for idx, team_data in enumerate(stats_data.get('teams', [])):
            # Team name from api_game since stats_data doesn't include it
            team_name = home_team_name if idx == 0 else away_team_name

            for player in team_data.get('players', []):
                player_info = player.get('player', {})
                player_id = player_info.get('id')

                # Get player name from cached players
                player_name = 'Unknown'
                if player_id:
                    cached_player = APISportsService.get_cached_player(player_id)
                    if cached_player:
                        player_name = cached_player.get('name', 'Unknown')

                # Stats are directly on the player object, not nested
                goals = player.get('goals', {}).get('total', 0) or 0
                disposals = player.get('disposals', 0) or 0
                kicks = player.get('kicks', 0) or 0
                handballs = player.get('handballs', 0) or 0
                marks = player.get('marks', 0) or 0
                tackles = player.get('tackles', 0) or 0

                # Simple fantasy calculation: goals*6 + disposals + marks + tackles
                fantasy = (goals * 6) + disposals + marks + tackles

                all_players.append({
                    'name': player_name,
                    'team': team_name,
                    'goals': goals,
                    'disposals': disposals,
                    'fantasy': fantasy,
                })

        # Sort and get top 3 for each category
        top_goals = sorted(all_players, key=lambda x: x['goals'], reverse=True)[:3]
        top_disposals = sorted(all_players, key=lambda x: x['disposals'], reverse=True)[:3]
        top_fantasy = sorted(all_players, key=lambda x: x['fantasy'], reverse=True)[:3]

        # Filter out zero values
        top_goals = [p for p in top_goals if p['goals'] > 0]
        top_disposals = [p for p in top_disposals if p['disposals'] > 0]
        top_fantasy = [p for p in top_fantasy if p['fantasy'] > 0]

        session.close()

        return jsonify({
            'top_goal_kickers': [{'name': p['name'], 'team': p['team'], 'goals': p['goals']} for p in top_goals],
            'top_disposals': [{'name': p['name'], 'team': p['team'], 'disposals': p['disposals']} for p in top_disposals],
            'top_fantasy': [{'name': p['name'], 'team': p['team'], 'points': p['fantasy']} for p in top_fantasy],
        }), 200

    except Exception as e:
        logger.error(f"Error fetching game stats: {e}")
        return jsonify({'error': 'Failed to fetch game stats'}), 500
