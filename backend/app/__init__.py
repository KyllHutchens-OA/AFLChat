"""
AFL Analytics Agent - Flask Application Factory
"""
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import logging
import sys
import os

__version__ = "0.1.0"

# Get CORS origins from environment (comma-separated list)
# Default allows localhost for development
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5001").split(",")

# Initialize SocketIO with restricted CORS
socketio = SocketIO(cors_allowed_origins=CORS_ORIGINS)

def create_app(config=None):
    """Create and configure the Flask application."""

    app = Flask(__name__)

    # Configuration - SECRET_KEY from environment, required in production
    secret_key = os.getenv("SECRET_KEY")
    flask_env = os.getenv("FLASK_ENV", "development")

    if flask_env == "production" and not secret_key:
        raise ValueError("SECRET_KEY environment variable is required in production")

    app.config['SECRET_KEY'] = secret_key or 'dev-secret-key-for-local-only'

    if config:
        app.config.update(config)

    # Enable CORS with restricted origins
    CORS(app, origins=CORS_ORIGINS)

    # Initialize SocketIO
    socketio.init_app(app)

    # Initialize rate limiter
    from app.middleware.rate_limiter import limiter, ratelimit_error_handler
    limiter.init_app(app)
    app.register_error_handler(429, ratelimit_error_handler)

    # Configure logging for production
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

    # Stream to stdout for Railway/container environments
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S'))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    root_logger.handlers = [handler]

    # Reduce noise from libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)

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

    # Add security headers to all responses
    @app.after_request
    def add_security_headers(response):
        """Add security headers to protect against common attacks."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Content Security Policy for HTML responses
        if response.content_type and 'text/html' in response.content_type:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.plot.ly; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self' wss: ws:; "
                "font-src 'self' data:;"
            )

        return response

    return app
