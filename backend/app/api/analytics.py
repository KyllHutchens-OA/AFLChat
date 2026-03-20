"""
Analytics Dashboard - API endpoints for traffic, API usage, and conversation logs.
No authentication - accessible at /api/analytics routes.
"""
from flask import Blueprint, request, jsonify, Response
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from markupsafe import escape
import json
import logging

from app.data.database import Session
from app.data.models import PageView, Conversation, APIUsage, UserReport
from sqlalchemy import func, text

logger = logging.getLogger(__name__)

bp = Blueprint('analytics_dashboard', __name__, url_prefix='/api/analytics')

AEDT = ZoneInfo('Australia/Sydney')


@bp.route('/traffic')
def get_traffic():
    """
    Get page view traffic as a time series.
    Query params:
        hours: int (default 24) - how far back to look
    Returns hourly bucketed page views.
    """
    hours = request.args.get('hours', 24, type=int)
    hours = min(hours, 720)  # Cap at 30 days
    db = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        # Hourly time series
        rows = db.execute(text("""
            SELECT
                date_trunc('hour', timestamp) AS hour,
                COUNT(*) AS views,
                COUNT(DISTINCT visitor_id) AS unique_visitors
            FROM page_views
            WHERE timestamp >= :since
            GROUP BY date_trunc('hour', timestamp)
            ORDER BY hour
        """), {'since': since}).fetchall()

        time_series = [
            {
                'time': row[0].isoformat() + 'Z',
                'views': row[1],
                'unique_visitors': row[2],
            }
            for row in rows
        ]

        # Summary stats
        total_views = sum(r[1] for r in rows)
        total_unique = db.query(func.count(func.distinct(PageView.visitor_id))).filter(
            PageView.timestamp >= since
        ).scalar() or 0
        unique_ips = db.query(func.count(func.distinct(PageView.ip_address))).filter(
            PageView.timestamp >= since,
            PageView.ip_address.isnot(None)
        ).scalar() or 0

        # Views by page
        views_by_page = db.query(
            PageView.page,
            func.count(PageView.id).label('views')
        ).filter(PageView.timestamp >= since).group_by(PageView.page).order_by(
            func.count(PageView.id).desc()
        ).all()

        return jsonify({
            'hours': hours,
            'total_views': total_views,
            'unique_visitors': total_unique,
            'unique_ips': unique_ips,
            'views_by_page': [{'page': p, 'views': v} for p, v in views_by_page],
            'time_series': time_series,
        })

    finally:
        db.close()


@bp.route('/api-usage')
def get_api_usage():
    """
    Get OpenAI API usage stats.
    Query params:
        hours: int (default 24)
    Returns cost, tokens, and time series.
    """
    hours = request.args.get('hours', 24, type=int)
    hours = min(hours, 720)
    db = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        # Summary
        total_requests = db.query(func.count(APIUsage.id)).filter(
            APIUsage.timestamp >= since
        ).scalar() or 0

        total_cost = db.query(func.sum(APIUsage.estimated_cost_usd)).filter(
            APIUsage.timestamp >= since
        ).scalar() or 0

        total_input_tokens = db.query(func.sum(APIUsage.input_tokens)).filter(
            APIUsage.timestamp >= since
        ).scalar() or 0

        total_output_tokens = db.query(func.sum(APIUsage.output_tokens)).filter(
            APIUsage.timestamp >= since
        ).scalar() or 0

        # By model
        by_model = db.query(
            APIUsage.model,
            func.count(APIUsage.id).label('requests'),
            func.sum(APIUsage.estimated_cost_usd).label('cost'),
            func.sum(APIUsage.input_tokens).label('input_tokens'),
            func.sum(APIUsage.output_tokens).label('output_tokens'),
        ).filter(APIUsage.timestamp >= since).group_by(APIUsage.model).all()

        # Hourly time series
        rows = db.execute(text("""
            SELECT
                date_trunc('hour', timestamp) AS hour,
                COUNT(*) AS requests,
                COALESCE(SUM(estimated_cost_usd), 0) AS cost,
                COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens
            FROM api_usage
            WHERE timestamp >= :since
            GROUP BY date_trunc('hour', timestamp)
            ORDER BY hour
        """), {'since': since}).fetchall()

        time_series = [
            {
                'time': row[0].isoformat() + 'Z',
                'requests': row[1],
                'cost': float(row[2]),
                'tokens': int(row[3]),
            }
            for row in rows
        ]

        # Daily limit info
        from app.middleware.usage_tracker import GLOBAL_DAILY_LIMIT_USD, DAILY_LIMIT_PER_VISITOR

        # Today's spend (for limit tracking)
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        today_cost = db.query(func.sum(APIUsage.estimated_cost_usd)).filter(
            APIUsage.timestamp >= today_start
        ).scalar() or 0

        return jsonify({
            'hours': hours,
            'total_requests': total_requests,
            'total_cost_usd': float(total_cost),
            'total_input_tokens': int(total_input_tokens),
            'total_output_tokens': int(total_output_tokens),
            'by_model': [
                {
                    'model': m or 'unknown',
                    'requests': r,
                    'cost': float(c or 0),
                    'input_tokens': int(it or 0),
                    'output_tokens': int(ot or 0),
                }
                for m, r, c, it, ot in by_model
            ],
            'time_series': time_series,
            'limits': {
                'daily_budget_usd': GLOBAL_DAILY_LIMIT_USD,
                'today_spent_usd': float(today_cost),
                'remaining_usd': max(0, GLOBAL_DAILY_LIMIT_USD - float(today_cost)),
                'per_visitor_limit': DAILY_LIMIT_PER_VISITOR,
            },
        })

    finally:
        db.close()


@bp.route('/conversations')
def get_conversations():
    """
    Get conversation logs.
    Query params:
        hours: int (default 24)
        chat_type: str (optional filter: 'afl', 'aflagent', 'resume')
    """
    hours = request.args.get('hours', 24, type=int)
    hours = min(hours, 720)
    chat_type = request.args.get('chat_type')
    db = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        query = "SELECT id, chat_type, messages, created_at, updated_at FROM conversations WHERE updated_at >= :since"
        params = {'since': since}

        if chat_type:
            query += " AND chat_type = :chat_type"
            params['chat_type'] = chat_type

        query += " ORDER BY updated_at DESC"

        result = db.execute(text(query), params)
        rows = result.fetchall()

        conversations = []
        for row in rows:
            conv_id = str(row[0])
            messages = row[2] or []

            # Filter messages to time period
            recent_messages = []
            for msg in messages:
                msg_time = msg.get('timestamp')
                if msg_time:
                    try:
                        msg_dt = datetime.fromisoformat(msg_time.replace('Z', '+00:00'))
                        if msg_dt.replace(tzinfo=None) >= since:
                            recent_messages.append({
                                'role': msg.get('role'),
                                'content': str(escape(msg.get('content', '')[:1000])),
                                'timestamp': msg_time,
                            })
                    except (ValueError, TypeError):
                        pass

            if recent_messages:
                conversations.append({
                    'id': conv_id,
                    'id_short': conv_id[:8],
                    'chat_type': row[1] or 'afl',
                    'messages': recent_messages,
                    'message_count': len(recent_messages),
                    'created_at': row[3].isoformat() if row[3] else None,
                    'updated_at': row[4].isoformat() if row[4] else None,
                })

        # Counts by type
        type_counts = {}
        for conv in conversations:
            ct = conv['chat_type']
            type_counts[ct] = type_counts.get(ct, 0) + conv['message_count']

        return jsonify({
            'hours': hours,
            'conversations': conversations,
            'total_conversations': len(conversations),
            'message_counts_by_type': type_counts,
        })

    finally:
        db.close()


@bp.route('/reports')
def get_reports():
    """
    Get user-submitted issue reports, newest first.
    Includes linked conversation messages for context.
    Query params:
        limit: int (default 50, max 200)
    """
    limit = min(request.args.get('limit', 50, type=int), 200)
    db = Session()

    try:
        reports = (
            db.query(UserReport)
            .order_by(UserReport.created_at.desc())
            .limit(limit)
            .all()
        )

        results = []
        for r in reports:
            conv_messages = []
            if r.conversation_id and r.conversation:
                for msg in (r.conversation.messages or []):
                    conv_messages.append({
                        'role': msg.get('role'),
                        'content': msg.get('content', '')[:2000],
                        'timestamp': msg.get('timestamp'),
                    })

            results.append({
                'id': r.id,
                'conversation_id': str(r.conversation_id) if r.conversation_id else None,
                'message_text': r.message_text,
                'what_happened': r.what_happened,
                'what_expected': r.what_expected,
                'page_url': r.page_url,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'conversation_messages': conv_messages,
            })

        return jsonify({'reports': results, 'total': len(results)})

    finally:
        db.close()


@bp.route('/conversations/download')
def download_conversations():
    """
    Download all conversation logs as JSON file.
    Query params:
        hours: int (default 24)
    """
    hours = request.args.get('hours', 24, type=int)
    hours = min(hours, 720)
    db = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        result = db.execute(text(
            "SELECT id, chat_type, messages, created_at, updated_at "
            "FROM conversations WHERE updated_at >= :since ORDER BY updated_at DESC"
        ), {'since': since})
        rows = result.fetchall()

        conversations = []
        for row in rows:
            messages = row[2] or []
            if messages:
                conversations.append({
                    'id': str(row[0]),
                    'chat_type': row[1] or 'afl',
                    'messages': messages,
                    'created_at': row[3].isoformat() if row[3] else None,
                    'updated_at': row[4].isoformat() if row[4] else None,
                })

        data = json.dumps(conversations, indent=2, default=str)

        return Response(
            data,
            mimetype='application/json',
            headers={
                'Content-Disposition': f'attachment; filename=conversations_{hours}h.json'
            }
        )

    finally:
        db.close()
