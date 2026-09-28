"""
Bearer-token guard for admin endpoints (analytics dashboard).
Token comes from env ANALYTICS_ADMIN_TOKEN; fails closed when unset.
"""
import hmac
import os
from functools import wraps

from flask import jsonify, request


def check_admin_token():
    """Return a 401 response unless the request carries the admin bearer token, else None."""
    if request.method == 'OPTIONS':
        return None
    expected = os.getenv('ANALYTICS_ADMIN_TOKEN', '')
    header = request.headers.get('Authorization', '')
    provided = header[7:] if header.startswith('Bearer ') else ''
    if not expected or not provided or not hmac.compare_digest(
        provided.encode('utf-8'), expected.encode('utf-8')
    ):
        return jsonify({'error': 'Unauthorized'}), 401
    return None


def require_admin_token(view):
    """Decorator form of check_admin_token for single routes."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        denied = check_admin_token()
        if denied is not None:
            return denied
        return view(*args, **kwargs)
    return wrapper
