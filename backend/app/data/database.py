"""
Database connection and session management.
"""
import time
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config import get_config
import os

logger = logging.getLogger(__name__)

config = get_config()

# Create database engine
# Convert postgresql:// to postgresql+psycopg:// for psycopg3
database_url = config.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Configurable pool sizes from environment (for Railway tuning)
pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))

engine = create_engine(
    database_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=30,  # Wait max 30s for connection
    pool_recycle=1800,  # Recycle connections every 30 min
    echo=config.DEBUG,  # Log SQL queries in debug mode
    connect_args={
        "prepare_threshold": None,  # Disable prepared statements for Supabase pooler
        # TCP keepalives — prevent Railway from silently dropping idle connections
        "keepalives": 1,
        "keepalives_idle": 30,       # send keepalive after 30s idle
        "keepalives_interval": 10,   # retry every 10s
        "keepalives_count": 5,       # give up after 5 missed keepalives (50s)
        "options": "-c statement_timeout=60000",  # 60s max per statement
    }
)

# Create session factory
# expire_on_commit=False keeps objects usable after commit (needed for live game updates)
session_factory = sessionmaker(bind=engine, expire_on_commit=False)
Session = scoped_session(session_factory)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Get database session (generator-based, for FastAPI/Flask dependency injection).
    Use as: db = next(get_db())
    """
    db = Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_session():
    """
    Get database session as context manager.
    Use as: with get_session() as session:

    This is the preferred way to manage sessions as it ensures
    proper cleanup even if an exception occurs.
    """
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """
    Initialize database (create all tables).
    """
    Base.metadata.create_all(bind=engine)


def close_db():
    """
    Close database connections.
    """
    Session.remove()


# ── Data Recency Cache ────────────────────────────────────────────────────────
_data_recency_cache = {"data": None, "timestamp": 0}
_DATA_RECENCY_TTL = 300  # 5 minutes


def get_data_recency():
    """
    Query the DB for current data availability info.
    Returns dict with earliest_season, historical latest, live latest.
    Cached for 5 minutes.
    """
    now = time.time()
    if _data_recency_cache["data"] and (now - _data_recency_cache["timestamp"]) < _DATA_RECENCY_TTL:
        return _data_recency_cache["data"]

    result = {
        "earliest_season": 1990,
        "historical_latest_season": 2025,
        "historical_latest_round": "unknown",
        "live_latest_season": None,
        "live_latest_round": None,
        "live_latest_date": None,
    }

    try:
        session = Session()
        try:
            # Latest historical match (only completed — exclude future fixtures with no scores)
            row = session.execute(text(
                "SELECT season, round FROM matches "
                "WHERE (home_score > 0 OR away_score > 0) "
                "ORDER BY match_date DESC LIMIT 1"
            )).fetchone()
            if row:
                result["historical_latest_season"] = row[0]
                result["historical_latest_round"] = row[1]

            # Earliest season
            row = session.execute(text("SELECT MIN(season) FROM matches")).fetchone()
            if row and row[0]:
                result["earliest_season"] = row[0]

            # Latest live game
            row = session.execute(text(
                "SELECT season, round, match_date FROM live_games "
                "WHERE status IN ('complete', 'completed', 'post_match') "
                "ORDER BY match_date DESC LIMIT 1"
            )).fetchone()
            if row:
                result["live_latest_season"] = row[0]
                result["live_latest_round"] = row[1]
                result["live_latest_date"] = str(row[2])[:10] if row[2] else None

        finally:
            session.close()

    except Exception as e:
        logger.warning(f"get_data_recency failed, using defaults: {e}")

    _data_recency_cache["data"] = result
    _data_recency_cache["timestamp"] = now
    return result
