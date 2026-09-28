"""
Server-issued visitor identity for quotas.

The server mints a random visitor id and hands the client a token signed with
SECRET_KEY. Quotas key on the verified id (plus the client IP), never on a
client-supplied visitor_id. Minting a fresh token is always possible, so the
per-IP daily cap in UsageTracker is the backstop.
"""
import secrets
from typing import Optional, Tuple

from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

_SALT = "footynac-visitor-v1"
_PREFIX = "v-"


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def issue_visitor_token() -> Tuple[str, str]:
    """Return (visitor_id, signed_token)."""
    visitor_id = _PREFIX + secrets.token_hex(12)
    return visitor_id, _serializer().dumps(visitor_id)


def verify_visitor_token(token: object) -> Optional[str]:
    """Return the visitor id for a valid token, else None."""
    if not isinstance(token, str) or not token or len(token) > 200:
        return None
    try:
        visitor_id = _serializer().loads(token)
    except BadSignature:
        return None
    if isinstance(visitor_id, str) and visitor_id.startswith(_PREFIX):
        return visitor_id
    return None
