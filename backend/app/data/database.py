"""
Database connection and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config import get_config

config = get_config()

# Create database engine
# Convert postgresql:// to postgresql+psycopg:// for psycopg3
database_url = config.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    database_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20,
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
    Get database session.
    Use as context manager: with get_db() as db:
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
