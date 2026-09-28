"""Unit tests for the admin bearer-token guard (app/api/admin_auth.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask import Flask

from app.api.admin_auth import require_admin_token


@pytest.fixture
def client():
    app = Flask(__name__)

    @app.route('/admin')
    @require_admin_token
    def admin():
        return 'ok'

    return app.test_client()


def test_missing_env_fails_closed(client, monkeypatch):
    monkeypatch.delenv('ANALYTICS_ADMIN_TOKEN', raising=False)
    assert client.get('/admin', headers={'Authorization': 'Bearer '}).status_code == 401
    assert client.get('/admin', headers={'Authorization': 'Bearer x'}).status_code == 401


def test_token_required(client, monkeypatch):
    monkeypatch.setenv('ANALYTICS_ADMIN_TOKEN', 'secret-token')
    assert client.get('/admin').status_code == 401
    assert client.get('/admin', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.get('/admin', headers={'Authorization': 'secret-token'}).status_code == 401
    assert client.get('/admin', headers={'Authorization': 'Bearer secret-token'}).status_code == 200
