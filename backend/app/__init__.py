"""
AFL Analytics Agent - Flask Application Factory
"""
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import logging
import os

__version__ = "0.1.0"

# Initialize SocketIO
socketio = SocketIO(cors_allowed_origins="*")

def create_app(config=None):
    """Create and configure the Flask application."""

    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'

    if config:
        app.config.update(config)

    # Enable CORS
    CORS(app)

    # Initialize SocketIO
    socketio.init_app(app)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Startup diagnostics - check environment variables
    logger = logging.getLogger(__name__)
    openai_key = os.getenv("OPENAI_API_KEY")
    db_string = os.getenv("DB_STRING")

    logger.info("=" * 50)
    logger.info("STARTUP DIAGNOSTICS")
    logger.info("=" * 50)
    if openai_key:
        # Mask the key for security, show first 7 and last 4 chars
        masked = f"{openai_key[:7]}...{openai_key[-4:]}" if len(openai_key) > 11 else "***"
        logger.info(f"OPENAI_API_KEY: SET ({masked})")
    else:
        logger.error("OPENAI_API_KEY: NOT SET - OpenAI calls will fail!")

    if db_string:
        logger.info(f"DB_STRING: SET (length={len(db_string)})")
    else:
        logger.error("DB_STRING: NOT SET - Database calls will fail!")
    logger.info("=" * 50)

    # Register blueprints
    from app.api import routes
    app.register_blueprint(routes.bp)

    # Register analytics dashboard
    from app.api import analytics
    app.register_blueprint(analytics.bp)

    # Register WebSocket handlers
    from app.api import websocket

    return app
