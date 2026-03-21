"""Add stats_cache columns to live_games table."""
from app.data.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE live_games
            ADD COLUMN IF NOT EXISTS stats_cache JSONB,
            ADD COLUMN IF NOT EXISTS stats_cache_updated_at TIMESTAMP;
        """))
        conn.commit()
        print("✓ Added stats_cache columns to live_games")

if __name__ == "__main__":
    run()
