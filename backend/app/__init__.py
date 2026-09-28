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

    if not secret_key:
        if flask_env != "development":
            raise ValueError("SECRET_KEY environment variable is required outside development")
        secret_key = 'dev-secret-key-for-local-only'

    app.config['SECRET_KEY'] = secret_key

    if config:
        app.config.update(config)

    # Enable CORS with restricted origins
    CORS(app, origins=CORS_ORIGINS)

    # Initialize SocketIO
    socketio.init_app(app)

    # Trust exactly one proxy hop (Railway edge) for client IP / scheme; wraps the
    # SocketIO middleware too, so request.remote_addr is correct in WS handlers.
    # Nothing else may read X-Forwarded-For directly.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

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

    # Register user reports endpoint
    from app.api import reports
    app.register_blueprint(reports.bp)

    # Register teams API (team list + fun stats)
    from app.api import teams_api
    app.register_blueprint(teams_api.bp)

    # Register WebSocket handlers
    from app.api import websocket

    # Fail fast on missing agent DB / unpriced models (both raise outside development)
    from app.data.database import get_agent_engine
    get_agent_engine()
    from app.middleware.usage_tracker import validate_configured_models
    validate_configured_models()

    # Background scheduler + SSE listener only when RUN_SCHEDULER=true (one prod worker).
    # Off by default so local runs and extra web replicas never ingest or poll.
    if os.getenv("RUN_SCHEDULER", "false").lower() == "true":
        from app.services.scheduler import get_scheduler
        from app.services.sse_listener import get_sse_listener

        sse_listener = get_sse_listener(socketio=socketio)
        sse_listener.start()
        logger.info("✓ SSE listener started for live games")

        scheduler = get_scheduler(sse_listener=sse_listener)
        scheduler.start()
        logger.info("✓ Background data scheduler started")
    else:
        logger.info("RUN_SCHEDULER is not true: scheduler and SSE listener not started")

    # Log env var status for scheduler-dependent APIs
    theoddsapi_key = os.getenv("THEODDSAPI_KEY")
    if theoddsapi_key:
        logger.info("THEODDSAPI_KEY: SET")
    else:
        logger.warning("THEODDSAPI_KEY: NOT SET - betting odds updates will be skipped")

    # Add security headers to all responses
    @app.after_request
    def add_security_headers(response):
        """Add security headers to protect against common attacks."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # The API serves JSON only; lock down anything rendered from it
        if response.content_type and 'text/html' in response.content_type:
            response.headers['Content-Security-Policy'] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            )

        return response

    return app
