"""
SQLAlchemy models for AFL analytics database.
"""
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    Date,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

from app.data.database import Base


class Team(Base):
    """AFL Team model."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    abbreviation = Column(String(10), nullable=False, unique=True)
    stadium = Column(String(100))
    primary_color = Column(String(7))
    secondary_color = Column(String(7))
    founded_year = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    players = relationship("Player", back_populates="team")
    home_matches = relationship(
        "Match", foreign_keys="Match.home_team_id", back_populates="home_team"
    )
    away_matches = relationship(
        "Match", foreign_keys="Match.away_team_id", back_populates="away_team"
    )
    team_stats = relationship("TeamStat", back_populates="team")

    def __repr__(self):
        return f"<Team {self.name}>"


class Player(Base):
    """AFL Player model."""

    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"))
    position = Column(String(50))
    jersey_number = Column(Integer)
    height_cm = Column(Integer)
    weight_kg = Column(Integer)
    date_of_birth = Column(Date)
    debut_date = Column(Date)
    debut_year = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    team = relationship("Team", back_populates="players")
    player_stats = relationship("PlayerStat", back_populates="player")
    match_lineups = relationship("MatchLineup", back_populates="player")

    def __repr__(self):
        return f"<Player {self.name}>"


class Match(Base):
    """AFL Match model."""

    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    season = Column(Integer, nullable=False)
    round = Column(String(50), nullable=False)  # Changed to String to support finals (e.g., "Qualifying Final")
    match_date = Column(DateTime, nullable=False)
    venue = Column(String(100))
    home_team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    away_team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    home_score = Column(Integer)
    away_score = Column(Integer)

    # Quarter-by-quarter scoring
    home_q1_goals = Column(Integer)
    home_q1_behinds = Column(Integer)
    home_q2_goals = Column(Integer)
    home_q2_behinds = Column(Integer)
    home_q3_goals = Column(Integer)
    home_q3_behinds = Column(Integer)
    home_q4_goals = Column(Integer)
    home_q4_behinds = Column(Integer)
    away_q1_goals = Column(Integer)
    away_q1_behinds = Column(Integer)
    away_q2_goals = Column(Integer)
    away_q2_behinds = Column(Integer)
    away_q3_goals = Column(Integer)
    away_q3_behinds = Column(Integer)
    away_q4_goals = Column(Integer)
    away_q4_behinds = Column(Integer)

    attendance = Column(Integer)
    match_status = Column(String(20), default="completed")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("season", "round", "home_team_id", "away_team_id"),
    )

    # Relationships
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    player_stats = relationship("PlayerStat", back_populates="match")
    team_stats = relationship("TeamStat", back_populates="match")
    lineups = relationship("MatchLineup", back_populates="match")
    weather = relationship("MatchWeather", back_populates="match", uselist=False)

    def __repr__(self):
        return f"<Match {self.season} R{self.round}: {self.home_team_id} vs {self.away_team_id}>"


class PlayerStat(Base):
    """Player Statistics per match."""

    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True)
    match_id = Column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    player_id = Column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )  # Team player was playing FOR in this match (handles trades correctly)
    disposals = Column(Integer, default=0)
    kicks = Column(Integer, default=0)
    handballs = Column(Integer, default=0)
    marks = Column(Integer, default=0)
    tackles = Column(Integer, default=0)
    goals = Column(Integer, default=0)
    behinds = Column(Integer, default=0)
    hitouts = Column(Integer, default=0)
    clearances = Column(Integer, default=0)
    inside_50s = Column(Integer, default=0)
    rebound_50s = Column(Integer, default=0)
    contested_possessions = Column(Integer, default=0)
    uncontested_possessions = Column(Integer, default=0)
    contested_marks = Column(Integer, default=0)
    marks_inside_50 = Column(Integer, default=0)
    one_percenters = Column(Integer, default=0)
    bounces = Column(Integer, default=0)
    goal_assist = Column(Integer, default=0)
    clangers = Column(Integer, default=0)
    free_kicks_for = Column(Integer, default=0)
    free_kicks_against = Column(Integer, default=0)
    fantasy_points = Column(Integer, default=0)
    brownlow_votes = Column(Integer, default=0)
    time_on_ground_pct = Column(Numeric(5, 2))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint
    __table_args__ = (UniqueConstraint("match_id", "player_id"),)

    # Relationships
    match = relationship("Match", back_populates="player_stats")
    player = relationship("Player", back_populates="player_stats")
    team = relationship("Team")  # Team player was on for this specific match

    def __repr__(self):
        return f"<PlayerStat Match:{self.match_id} Player:{self.player_id} Team:{self.team_id}>"


class TeamStat(Base):
    """Team Statistics per match."""

    __tablename__ = "team_stats"

    id = Column(Integer, primary_key=True)
    match_id = Column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    is_home = Column(Boolean, nullable=False)
    score = Column(Integer, nullable=False)
    inside_50s = Column(Integer)
    clearances = Column(Integer)
    contested_possessions = Column(Integer)
    uncontested_possessions = Column(Integer)
    tackles = Column(Integer)
    marks = Column(Integer)
    hitouts = Column(Integer)
    free_kicks_for = Column(Integer)
    free_kicks_against = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint
    __table_args__ = (UniqueConstraint("match_id", "team_id"),)

    # Relationships
    match = relationship("Match", back_populates="team_stats")
    team = relationship("Team", back_populates="team_stats")

    def __repr__(self):
        return f"<TeamStat Match:{self.match_id} Team:{self.team_id}>"


class MatchLineup(Base):
    """Match lineup - which players were selected for each match."""

    __tablename__ = "match_lineups"

    id = Column(Integer, primary_key=True)
    match_id = Column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    player_id = Column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    jersey_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Unique constraint
    __table_args__ = (UniqueConstraint("match_id", "player_id"),)

    # Relationships
    match = relationship("Match", back_populates="lineups")
    team = relationship("Team")
    player = relationship("Player", back_populates="match_lineups")

    def __repr__(self):
        return f"<MatchLineup Match:{self.match_id} Player:{self.player_id}>"


class MatchWeather(Base):
    """Weather conditions during the match."""

    __tablename__ = "match_weather"

    id = Column(Integer, primary_key=True)
    match_id = Column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    temperature_celsius = Column(Numeric(4, 1))
    apparent_temperature_celsius = Column(Numeric(4, 1))
    rainfall_mm = Column(Numeric(5, 1))
    wind_speed_kmh = Column(Numeric(4, 1))
    wind_direction_degrees = Column(Integer)
    humidity_pct = Column(Integer)
    weather_code = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    match = relationship("Match", back_populates="weather")

    def __repr__(self):
        return f"<MatchWeather Match:{self.match_id} Temp:{self.temperature_celsius}°C>"


class Conversation(Base):
    """Agent conversation history."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100))
    chat_type = Column(String(20), nullable=False, default='afl', index=True)  # 'afl' or 'resume'
    messages = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Conversation {self.id}>"


class PageView(Base):
    """Simple analytics - page view tracking."""

    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True)
    visitor_id = Column(String(100), nullable=False, index=True)
    page = Column(String(200), nullable=False)
    referrer = Column(String(500))
    user_agent = Column(String(500))
    ip_address = Column(String(45), index=True)  # IPv6 max length is 45 chars
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<PageView {self.page} by {self.visitor_id}>"


class AdminUser(Base):
    """Admin user for analytics dashboard."""

    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AdminUser {self.username}>"


class APIUsage(Base):
    """Track API usage for cost monitoring and rate limiting."""

    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True)
    visitor_id = Column(String(100), nullable=False, index=True)
    ip_address = Column(String(45), index=True)  # IPv6 max length
    endpoint = Column(String(100))
    model = Column(String(50))
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Numeric(10, 6))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<APIUsage {self.visitor_id} ${self.estimated_cost_usd}>"


class LiveGame(Base):
    """Live game data with real-time updates from Squiggle SSE."""

    __tablename__ = "live_games"

    id = Column(Integer, primary_key=True)
    squiggle_game_id = Column(Integer, nullable=False, unique=True, index=True)
    match_id = Column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=True
    )  # Link to Match when completed

    # Game identification
    season = Column(Integer, nullable=False)
    round = Column(String(50), nullable=False)

    # Teams
    home_team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    away_team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )

    # Live scoring
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    home_goals = Column(Integer, default=0)
    home_behinds = Column(Integer, default=0)
    away_goals = Column(Integer, default=0)
    away_behinds = Column(Integer, default=0)

    # Quarter-by-quarter (for progressive updates)
    home_q1_score = Column(Integer, default=0)
    home_q2_score = Column(Integer, default=0)
    home_q3_score = Column(Integer, default=0)
    home_q4_score = Column(Integer, default=0)
    away_q1_score = Column(Integer, default=0)
    away_q2_score = Column(Integer, default=0)
    away_q3_score = Column(Integer, default=0)
    away_q4_score = Column(Integer, default=0)

    # Game state
    status = Column(
        String(20), nullable=False, default="scheduled", index=True
    )  # scheduled, live, completed
    complete_percent = Column(Integer, default=0)  # 0-100
    time_str = Column(String(50))  # "Q2 15:32", "Half Time", etc.
    current_quarter = Column(Integer)  # 1-4

    # Match details
    venue = Column(String(100))
    match_date = Column(DateTime, nullable=False)

    # Winner (null until game completes)
    winner_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)

    # Metadata
    last_updated = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    # AI-generated summary (created when game completes)
    ai_summary = Column(Text, nullable=True)

    # Relationships
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    winner_team = relationship("Team", foreign_keys=[winner_team_id])
    match = relationship("Match", foreign_keys=[match_id])
    events = relationship(
        "LiveGameEvent", back_populates="game", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<LiveGame {self.season} R{self.round}: {self.home_team_id} vs {self.away_team_id} ({self.status})>"


class LiveGameEvent(Base):
    """Individual scoring events during live games."""

    __tablename__ = "live_game_events"

    id = Column(Integer, primary_key=True)
    game_id = Column(
        Integer,
        ForeignKey("live_games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event details
    event_type = Column(
        String(20), nullable=False
    )  # 'goal', 'behind', 'quarter_end', 'game_start'
    team_id = Column(
        Integer, ForeignKey("teams.id"), nullable=True
    )  # Null for quarter_end events
    player_name = Column(String(200))  # Player who scored (if available from API)
    player_api_sports_id = Column(Integer)  # API-Sports player ID for lookups

    # Scoring context
    home_score_after = Column(Integer)
    away_score_after = Column(Integer)
    quarter = Column(Integer)
    time_str = Column(String(50))

    # Metadata
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    game = relationship("LiveGame", back_populates="events")
    team = relationship("Team")

    def __repr__(self):
        return f"<LiveGameEvent {self.event_type} Game:{self.game_id} Q{self.quarter}>"


class APISportsPlayer(Base):
    """Cached player data from API-Sports for player name lookups."""

    __tablename__ = "api_sports_players"

    id = Column(Integer, primary_key=True)
    api_sports_id = Column(Integer, nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    team_api_sports_id = Column(Integer, index=True)  # API-Sports team ID
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)  # Our team ID
    jersey_number = Column(Integer)

    # Metadata
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    team = relationship("Team")

    def __repr__(self):
        return f"<APISportsPlayer {self.api_sports_id}: {self.name}>"


class APISportsTeamMapping(Base):
    """Mapping between API-Sports team IDs and our team IDs."""

    __tablename__ = "api_sports_team_mappings"

    id = Column(Integer, primary_key=True)
    api_sports_id = Column(Integer, nullable=False, unique=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    api_sports_name = Column(String(200))

    # Relationships
    team = relationship("Team")

    def __repr__(self):
        return f"<APISportsTeamMapping {self.api_sports_id} -> {self.team_id}>"


class NewsArticle(Base):
    """AFL news articles from RSS feeds, enriched by LLM at ingestion."""

    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True)
    source = Column(String(100), nullable=False)  # 'smh', 'theage', 'abc'
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False, unique=True)  # Prevents duplicates
    published_date = Column(DateTime, nullable=False, index=True)
    content = Column(String)  # Raw summary/excerpt from RSS
    author = Column(String(200))

    # LLM-enriched fields (populated at ingestion by GPT-5-nano)
    is_afl = Column(Boolean, default=True, index=True)
    category = Column(String(50), index=True)  # match_result, match_preview, injury, trade, off_field, analysis, other
    summary = Column(String(500))  # LLM-generated one-line summary
    is_injury_related = Column(Boolean, default=False, index=True)
    injury_details = Column(JSONB)  # [{"player": "...", "type": "...", "severity": "..."}]
    related_teams = Column(JSONB)  # ['Collingwood', 'Richmond']
    related_players = Column(JSONB)  # ['Nick Daicos', 'Patrick Cripps']
    enriched_at = Column(DateTime)  # When LLM enrichment ran

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_news_category_published', 'category', 'published_date'),
        Index('idx_news_injury_published', 'is_injury_related', 'published_date'),
    )

    def __repr__(self):
        return f"<NewsArticle {self.source}: {self.title[:50]}>"


class BettingOdds(Base):
    """Betting odds from The Odds API."""

    __tablename__ = "betting_odds"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    bookmaker = Column(String(100), nullable=False)

    # Head-to-head odds (decimal format)
    home_odds = Column(Numeric(6, 2))
    away_odds = Column(Numeric(6, 2))

    odds_fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('match_id', 'bookmaker', 'odds_fetched_at'),
        Index('idx_odds_match_fetched', 'match_id', 'odds_fetched_at'),
    )

    # Relationships
    match = relationship("Match", backref="betting_odds")

    def __repr__(self):
        return f"<BettingOdds Match:{self.match_id} {self.bookmaker}>"


class SquigglePrediction(Base):
    """Match predictions from Squiggle API."""

    __tablename__ = "squiggle_predictions"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)

    predicted_winner_id = Column(Integer, ForeignKey("teams.id"))
    predicted_margin = Column(Numeric(5, 1))
    home_win_probability = Column(Numeric(5, 2))  # 0-100
    away_win_probability = Column(Numeric(5, 2))

    source_model = Column(String(100))  # 'Squiggle', 'ELO'
    prediction_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('match_id', 'source_model', 'prediction_date'),
    )

    # Relationships
    match = relationship("Match", backref="predictions")
    predicted_winner = relationship("Team", foreign_keys=[predicted_winner_id])

    def __repr__(self):
        return f"<SquigglePrediction Match:{self.match_id} Winner:{self.predicted_winner_id}>"


class APIRequestLog(Base):
    """Log API requests for cost monitoring and rate limiting."""

    __tablename__ = "api_request_logs"

    id = Column(Integer, primary_key=True)
    api_name = Column(String(50), nullable=False, index=True)  # 'theoddsapi', 'tavily'
    endpoint = Column(String(200))
    request_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    status_code = Column(Integer)
    success = Column(Boolean, default=False)
    error_message = Column(String)
    response_time_ms = Column(Integer)

    estimated_cost = Column(Numeric(10, 6))  # USD

    __table_args__ = (
        Index('idx_api_name_timestamp', 'api_name', 'request_timestamp'),
    )

    def __repr__(self):
        return f"<APIRequestLog {self.api_name} {self.request_timestamp}>"
