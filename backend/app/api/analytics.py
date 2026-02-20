"""
Analytics Dashboard - Protected routes for viewing site analytics and chat logs.
"""
from flask import Blueprint, request, session, redirect, url_for, render_template_string
from functools import wraps
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import escape
import logging

from app.data.database import Session
from app.data.models import PageView, Conversation, AdminUser
from sqlalchemy import func, text

logger = logging.getLogger(__name__)

bp = Blueprint('analytics_dashboard', __name__, url_prefix='/api/admin')

AEDT = ZoneInfo('Australia/Sydney')


def hash_password(password):
    """Secure password hashing using PBKDF2."""
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)


def verify_password(password_hash, password):
    """Verify password against stored hash."""
    return check_password_hash(password_hash, password)


def login_required(f):
    """Decorator to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('analytics_dashboard.login'))
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db = Session()
        try:
            user = db.query(AdminUser).filter_by(username=username).first()
            if user and verify_password(user.password_hash, password):
                session['admin_logged_in'] = True
                session['admin_username'] = username
                return redirect(url_for('analytics_dashboard.dashboard'))
            error = 'Invalid credentials'
        finally:
            db.close()

    return render_template_string(LOGIN_TEMPLATE, error=error)


@bp.route('/logout')
def logout():
    """Logout."""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('analytics_dashboard.login'))


@bp.route('/')
@login_required
def dashboard():
    """Analytics dashboard."""
    return render_template_string(DASHBOARD_TEMPLATE)


@bp.route('/data')
@login_required
def get_data():
    """Get analytics data as JSON."""
    from flask import jsonify

    hours = request.args.get('hours', 24, type=int)
    db = Session()

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        # Page views
        total_views = db.query(PageView).filter(PageView.timestamp >= since).count()
        unique_visitors = db.query(func.count(func.distinct(PageView.visitor_id))).filter(
            PageView.timestamp >= since
        ).scalar()
        unique_ips = db.query(func.count(func.distinct(PageView.ip_address))).filter(
            PageView.timestamp >= since,
            PageView.ip_address.isnot(None)
        ).scalar()

        # Views by page
        views_by_page = db.query(
            PageView.page,
            func.count(PageView.id).label('views')
        ).filter(PageView.timestamp >= since).group_by(PageView.page).order_by(
            func.count(PageView.id).desc()
        ).all()

        # Get conversations with messages
        result = db.execute(text(
            "SELECT id, chat_type, messages, updated_at FROM conversations WHERE updated_at >= :since ORDER BY updated_at DESC"
        ), {'since': since})
        rows = result.fetchall()

        afl_chats = []
        aflagent_chats = []
        resume_chats = []

        for row in rows:
            conv_id = str(row[0])
            chat_type = row[1] or 'afl'
            messages = row[2] or []
            updated_at = row[3]

            # Filter messages to only those in the time period
            recent_messages = []
            for msg in messages:
                msg_time = msg.get('timestamp')
                if msg_time:
                    try:
                        msg_dt = datetime.fromisoformat(msg_time.replace('Z', '+00:00'))
                        if msg_dt.replace(tzinfo=None) >= since:
                            # Escape HTML to prevent XSS attacks
                            safe_content = str(escape(msg.get('content', '')[:500]))
                            recent_messages.append({
                                'role': msg.get('role'),
                                'content': safe_content,
                                'timestamp': msg_time
                            })
                    except:
                        pass

            if recent_messages:
                chat_data = {
                    'id': conv_id[:8],
                    'messages': recent_messages,
                    'message_count': len(recent_messages),
                    'updated_at': updated_at.isoformat() if updated_at else None
                }
                if chat_type == 'resume':
                    resume_chats.append(chat_data)
                elif chat_type == 'aflagent':
                    aflagent_chats.append(chat_data)
                else:
                    afl_chats.append(chat_data)

        return jsonify({
            'total_views': total_views,
            'unique_visitors': unique_visitors,
            'unique_ips': unique_ips,
            'views_by_page': [{'page': p, 'views': v} for p, v in views_by_page],
            'afl_chats': afl_chats,
            'aflagent_chats': aflagent_chats,
            'resume_chats': resume_chats,
            'afl_message_count': sum(c['message_count'] for c in afl_chats),
            'aflagent_message_count': sum(c['message_count'] for c in aflagent_chats),
            'resume_message_count': sum(c['message_count'] for c in resume_chats)
        })

    finally:
        db.close()


LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Analytics Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-box {
            background: #1e293b;
            padding: 2rem;
            border-radius: 8px;
            width: 100%;
            max-width: 320px;
        }
        h1 { font-size: 1.5rem; margin-bottom: 1.5rem; text-align: center; }
        input {
            width: 100%;
            padding: 0.75rem;
            margin-bottom: 1rem;
            border: 1px solid #334155;
            border-radius: 4px;
            background: #0f172a;
            color: #e2e8f0;
            font-size: 1rem;
        }
        input:focus { outline: none; border-color: #3b82f6; }
        button {
            width: 100%;
            padding: 0.75rem;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 1rem;
            cursor: pointer;
        }
        button:hover { background: #2563eb; }
        .error { color: #f87171; margin-bottom: 1rem; text-align: center; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Analytics</h1>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="POST">
            <input type="text" name="username" placeholder="Username" required autofocus>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Analytics Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            padding: 1rem;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }
        h1 { font-size: 1.5rem; }
        .controls { display: flex; gap: 0.5rem; align-items: center; }
        select, .btn {
            padding: 0.5rem 1rem;
            border-radius: 4px;
            border: 1px solid #334155;
            background: #1e293b;
            color: #e2e8f0;
            font-size: 0.875rem;
            cursor: pointer;
        }
        .btn { text-decoration: none; }
        .btn:hover { background: #334155; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .stat {
            background: #1e293b;
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value { font-size: 2rem; font-weight: bold; color: #3b82f6; }
        .stat-label { font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem; }
        .tabs {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }
        .tab {
            padding: 0.5rem 1rem;
            background: #1e293b;
            border: none;
            border-radius: 4px;
            color: #94a3b8;
            cursor: pointer;
            font-size: 0.875rem;
        }
        .tab.active { background: #3b82f6; color: white; }
        .chat-section { display: none; }
        .chat-section.active { display: block; }
        .chat-list {
            background: #1e293b;
            border-radius: 8px;
            max-height: 60vh;
            overflow-y: auto;
        }
        .chat-item {
            padding: 1rem;
            border-bottom: 1px solid #334155;
        }
        .chat-item:last-child { border-bottom: none; }
        .chat-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.5rem;
            font-size: 0.75rem;
            color: #94a3b8;
        }
        .message {
            padding: 0.5rem;
            margin: 0.25rem 0;
            border-radius: 4px;
            font-size: 0.875rem;
        }
        .message.user { background: #1e3a5f; }
        .message.assistant { background: #1e293b; border: 1px solid #334155; }
        .message-role { font-weight: bold; font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.25rem; }
        .empty { text-align: center; padding: 2rem; color: #64748b; }
        .pages { background: #1e293b; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; }
        .page-row { display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #334155; }
        .page-row:last-child { border-bottom: none; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Analytics Dashboard</h1>
        <div class="controls">
            <select id="timeRange" onchange="loadData()">
                <option value="24">Last 24 hours</option>
                <option value="168">Last 7 days</option>
            </select>
            <a href="/api/admin/logout" class="btn">Logout</a>
        </div>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="stat-value" id="totalViews">-</div>
            <div class="stat-label">Page Views</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="uniqueVisitors">-</div>
            <div class="stat-label">Unique Visitors</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="resumeMessages">-</div>
            <div class="stat-label">Resume Messages</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="aflMessages">-</div>
            <div class="stat-label">AFL Messages</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="aflagentMessages">-</div>
            <div class="stat-label">AFL Agent Messages</div>
        </div>
    </div>

    <div class="pages" id="pagesSection"></div>

    <div class="tabs">
        <button class="tab active" onclick="showTab('resume')">Resume Chat</button>
        <button class="tab" onclick="showTab('afl')">AFL Chat</button>
        <button class="tab" onclick="showTab('aflagent')">AFL Agent</button>
    </div>

    <div id="resumeSection" class="chat-section active">
        <div class="chat-list" id="resumeChats"></div>
    </div>

    <div id="aflSection" class="chat-section">
        <div class="chat-list" id="aflChats"></div>
    </div>

    <div id="aflagentSection" class="chat-section">
        <div class="chat-list" id="aflagentChats"></div>
    </div>

    <script>
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.chat-section').forEach(s => s.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tab + 'Section').classList.add('active');
        }

        function renderChats(chats, containerId) {
            const container = document.getElementById(containerId);
            if (!chats.length) {
                container.innerHTML = '<div class="empty">No conversations in this period</div>';
                return;
            }
            container.innerHTML = chats.map(chat => `
                <div class="chat-item">
                    <div class="chat-header">
                        <span>ID: ${chat.id}</span>
                        <span>${chat.message_count} messages</span>
                    </div>
                    ${chat.messages.map(m => `
                        <div class="message ${m.role}">
                            <div class="message-role">${m.role}</div>
                            ${m.content}
                        </div>
                    `).join('')}
                </div>
            `).join('');
        }

        async function loadData() {
            const hours = document.getElementById('timeRange').value;
            const res = await fetch('/api/admin/data?hours=' + hours);
            const data = await res.json();

            document.getElementById('totalViews').textContent = data.total_views;
            document.getElementById('uniqueVisitors').textContent = data.unique_visitors;
            document.getElementById('resumeMessages').textContent = data.resume_message_count;
            document.getElementById('aflMessages').textContent = data.afl_message_count;
            document.getElementById('aflagentMessages').textContent = data.aflagent_message_count;

            const pagesHtml = data.views_by_page.map(p =>
                `<div class="page-row"><span>${p.page}</span><span>${p.views} views</span></div>`
            ).join('');
            document.getElementById('pagesSection').innerHTML = pagesHtml || '<div class="empty">No page views</div>';

            renderChats(data.resume_chats, 'resumeChats');
            renderChats(data.afl_chats, 'aflChats');
            renderChats(data.aflagent_chats, 'aflagentChats');
        }

        loadData();
    </script>
</body>
</html>
'''
