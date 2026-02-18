"""
Database connection and session management.
"""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config import get_config
import os

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
        "prepare_threshold": None  # Disable prepared statements for Supabase pooler
    }
)

# Create session factory
session_factory = sessionmaker(bind=engine)
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
