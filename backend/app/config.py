"""
Application configuration management.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Base configuration."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    # Database
    DATABASE_URL = os.getenv("DB_STRING")
    if not DATABASE_URL:
        raise ValueError("DB_STRING environment variable is required")

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    NEWS_ENRICHMENT_MODEL = os.getenv("NEWS_ENRICHMENT_MODEL", "gpt-5-nano")

    # Data Sources
    AFL_TABLES_BASE_URL = os.getenv(
        "AFL_TABLES_BASE_URL", "https://afltables.com/afl/stats"
    )
    SQUIGGLE_API_URL = os.getenv("SQUIGGLE_API_URL", "https://api.squiggle.com.au")

    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


# Config dictionary
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Get configuration based on environment."""
    env = os.getenv("FLASK_ENV", "development")
    return config.get(env, config["default"])
