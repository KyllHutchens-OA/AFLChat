"""
AFL Analytics Agent - API Routes
"""
from flask import Blueprint, jsonify, request
from app.data.database import Session
from app.data.models import Match, Team, PageView
from datetime import datetime, timedelta
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__, url_prefix='/api')


@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        # Check database connection
        session = Session()
        match_count = session.query(Match).count()
        team_count = session.query(Team).count()
        session.close()

        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'matches': match_count,
            'teams': team_count
        }), 200

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@bp.route('/chat/message', methods=['POST'])
async def chat_message():
    """
    Handle chat messages (REST endpoint for non-streaming).
    For streaming, use WebSocket instead.
    """
    try:
        data = request.get_json()
        message = data.get('message')
        conversation_id = data.get('conversation_id')

        if not message:
            return jsonify({'error': 'Message required'}), 400

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
def track_page_view():
    """Track a page view."""
    try:
        data = request.get_json()
        visitor_id = data.get('visitor_id')
        page = data.get('page')
        referrer = data.get('referrer')
        user_agent = data.get('user_agent')

        if not visitor_id or not page:
            return jsonify({'error': 'visitor_id and page required'}), 400

        session = Session()
        page_view = PageView(
            visitor_id=visitor_id,
            page=page,
            referrer=referrer,
            user_agent=user_agent
        )
        session.add(page_view)
        session.commit()
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
