"""
User report submission endpoint.
POST /api/reports — submit an issue report from the chat UI.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid
import logging

from app.data.database import Session
from app.data.models import UserReport

logger = logging.getLogger(__name__)

bp = Blueprint('reports', __name__, url_prefix='/api')


@bp.route('/reports', methods=['POST'])
def submit_report():
    """
    Accept an issue report submitted from the chat interface.
    Body (JSON):
        conversation_id: str | null
        message_text: str   — the AI message that triggered the report (truncated to 1000 chars)
        what_happened: str  — user description
        what_expected: str  — what the user expected
        page_url: str       — window.location.href
    """
    data = request.get_json(silent=True) or {}

    what_happened = str(data.get('what_happened', '')).strip()[:2000]
    what_expected = str(data.get('what_expected', '')).strip()[:2000]
    message_text = str(data.get('message_text', '')).strip()[:1000]
    page_url = str(data.get('page_url', '')).strip()[:500]
    raw_conv_id = data.get('conversation_id')

    if not what_happened:
        return jsonify({'error': 'what_happened is required'}), 400

    # Parse conversation UUID if provided
    conv_id = None
    if raw_conv_id:
        try:
            conv_id = uuid.UUID(str(raw_conv_id))
        except ValueError:
            pass

    db = Session()
    try:
        report = UserReport(
            conversation_id=conv_id,
            message_text=message_text or None,
            what_happened=what_happened,
            what_expected=what_expected or None,
            page_url=page_url or None,
        )
        db.add(report)
        db.commit()
        logger.info(f"User report #{report.id} submitted (conv: {conv_id})")
        return jsonify({'id': report.id}), 201
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save user report: {e}")
        return jsonify({'error': 'Failed to save report'}), 500
    finally:
        db.close()
