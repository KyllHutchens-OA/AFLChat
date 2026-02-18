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


# ==================== RESUME ENDPOINTS ====================

@bp.route('/resume/data', methods=['GET'])
def get_resume_data():
    """
    Get resume data for visualizations.
    Returns skills and experience data formatted for charts.
    """
    try:
        from app.resume.data import get_skills_for_visualization, get_experience_for_visualization, RESUME_DATA

        return jsonify({
            'name': RESUME_DATA['name'],
            'title': RESUME_DATA['title'],
            'skills': get_skills_for_visualization(),
            'experience': get_experience_for_visualization()
        }), 200

    except Exception as e:
        logger.error(f"Error getting resume data: {e}")
        return jsonify({'error': 'Failed to load resume data'}), 500


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
