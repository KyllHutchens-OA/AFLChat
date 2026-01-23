"""
AFL Analytics Agent - Context Enrichment

Provides rich contextual insights to enhance statistical analysis.
"""
from typing import Dict, Any, Optional, List
import pandas as pd
import logging
from sqlalchemy import text
from app.data.database import Session

logger = logging.getLogger(__name__)


class ContextEnricher:
    """
    Enriches statistical analysis with contextual information.

    Features:
    - Historical percentiles (all-time performance rankings)
    - Form analysis (recent performance vs historical average)
    - Home vs away splits (venue advantage)
    - Venue-specific performance
    """

    @classmethod
    def enrich_team_context(
        cls,
        team_name: str,
        current_stats: Dict[str, Any],
        data: pd.DataFrame,
        season: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Add rich contextual information for a team.

        Args:
            team_name: Name of the team
            current_stats: Current statistics to enrich
            data: DataFrame with team performance data
            season: Optional specific season to focus on

        Returns:
            Dictionary with enriched context including historical percentiles,
            form analysis, home/away splits, and venue performance
        """
        context = {
            "team": team_name,
            "season": season
        }

        try:
            # Historical percentiles
            historical_percentiles = cls._calculate_historical_percentiles(
                team_name, current_stats, season
            )
            if historical_percentiles:
                context["historical_percentiles"] = historical_percentiles

            # Form analysis (recent vs historical)
            form_analysis = cls._analyze_form(team_name, data, season)
            if form_analysis:
                context["form_analysis"] = form_analysis

            # Home vs away splits
            venue_splits = cls._calculate_venue_splits(team_name, season)
            if venue_splits:
                context["venue_splits"] = venue_splits

            # Venue-specific performance
            venue_performance = cls._analyze_venue_performance(team_name, season)
            if venue_performance:
                context["venue_performance"] = venue_performance

        except Exception as e:
            logger.error(f"Error enriching context for {team_name}: {e}")
            context["error"] = str(e)

        return context

    @classmethod
    def _calculate_historical_percentiles(
        cls,
        team_name: str,
        current_stats: Dict[str, Any],
        season: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate where current performance ranks in team's all-time history.

        Args:
            team_name: Team name
            current_stats: Current season statistics
            season: Season to analyze

        Returns:
            Dictionary with percentile rankings for key metrics
        """
        try:
            session = Session()

            # Get team's all-time season statistics
            query = text("""
                WITH team_seasons AS (
                    SELECT
                        m.season,
                        COUNT(*) as games,
                        SUM(CASE
                            WHEN (m.home_team_id = t.id AND m.home_score > m.away_score)
                                OR (m.away_team_id = t.id AND m.away_score > m.home_score)
                            THEN 1 ELSE 0
                        END) as wins,
                        AVG(CASE
                            WHEN m.home_team_id = t.id THEN m.home_score
                            ELSE m.away_score
                        END) as avg_score,
                        CAST(SUM(CASE
                            WHEN (m.home_team_id = t.id AND m.home_score > m.away_score)
                                OR (m.away_team_id = t.id AND m.away_score > m.home_score)
                            THEN 1 ELSE 0
                        END) AS FLOAT) / COUNT(*) as win_rate
                    FROM matches m
                    JOIN teams t ON t.name = :team_name
                    WHERE (m.home_team_id = t.id OR m.away_team_id = t.id)
                    GROUP BY m.season
                )
                SELECT * FROM team_seasons
                ORDER BY season DESC
            """)

            result = session.execute(query, {"team_name": team_name})
            historical_data = pd.DataFrame(result.fetchall(), columns=result.keys())

            if len(historical_data) == 0:
                return None

            percentiles = {}

            # If we have current season data, calculate percentiles
            if season and "averages" in current_stats:
                current_season_data = historical_data[historical_data['season'] == season]

                if len(current_season_data) > 0:
                    # Calculate percentile for wins
                    if 'wins' in current_stats["averages"]:
                        current_wins = current_stats["averages"]['wins']['mean']
                        wins_percentile = (historical_data['wins'] < current_wins).sum() / len(historical_data) * 100
                        percentiles['wins'] = round(wins_percentile, 1)

                    # Calculate percentile for win_rate
                    if 'win_ratio' in historical_data.columns:
                        current_win_rate = current_season_data.iloc[0]['win_rate']
                        win_rate_percentile = (historical_data['win_rate'] < current_win_rate).sum() / len(historical_data) * 100
                        percentiles['win_rate'] = round(win_rate_percentile, 1)

            # Add historical context
            percentiles['seasons_analyzed'] = len(historical_data)
            percentiles['best_season'] = {
                'year': int(historical_data.loc[historical_data['wins'].idxmax(), 'season']),
                'wins': int(historical_data['wins'].max())
            }
            percentiles['worst_season'] = {
                'year': int(historical_data.loc[historical_data['wins'].idxmin(), 'season']),
                'wins': int(historical_data['wins'].min())
            }

            session.close()
            return percentiles

        except Exception as e:
            logger.error(f"Error calculating historical percentiles: {e}")
            return None

    @classmethod
    def _analyze_form(
        cls,
        team_name: str,
        data: pd.DataFrame,
        season: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze recent form (last 5 games) vs overall average.

        Args:
            team_name: Team name
            data: Performance data
            season: Optional season filter

        Returns:
            Form analysis with momentum indicator
        """
        try:
            # Filter to specific season if provided
            if season and 'season' in data.columns:
                data = data[data['season'] == season]

            if len(data) < 5:
                return None

            # Sort by date/round to get recent games
            if 'match_date' in data.columns:
                data = data.sort_values('match_date')
            elif 'round' in data.columns:
                data = data.sort_values('round')

            # Get numeric columns for analysis
            numeric_cols = data.select_dtypes(include=['number']).columns.tolist()

            form = {}

            # Recent 5 games vs overall average
            recent_5 = data.tail(5)
            overall_avg = data.mean(numeric=True)
            recent_avg = recent_5.mean(numeric=True)

            # Calculate form for key metrics
            for metric in ['wins', 'win_ratio', 'score']:
                if metric in numeric_cols or any(metric in col for col in numeric_cols):
                    # Find the actual column name
                    actual_col = metric if metric in numeric_cols else [col for col in numeric_cols if metric in col][0] if any(metric in col for col in numeric_cols) else None

                    if actual_col:
                        recent_value = recent_avg[actual_col]
                        overall_value = overall_avg[actual_col]

                        if overall_value != 0:
                            diff_pct = ((recent_value - overall_value) / overall_value * 100)
                            form[metric] = {
                                'recent_avg': round(float(recent_value), 2),
                                'season_avg': round(float(overall_value), 2),
                                'difference_percent': round(diff_pct, 2)
                            }

            # Determine momentum
            if form:
                # Average the percentage differences
                avg_diff = sum(f['difference_percent'] for f in form.values()) / len(form)

                if avg_diff > 10:
                    momentum = "hot"
                elif avg_diff < -10:
                    momentum = "cold"
                else:
                    momentum = "neutral"

                form['momentum'] = momentum
                form['recent_games'] = 5

            return form if form else None

        except Exception as e:
            logger.error(f"Error analyzing form: {e}")
            return None

    @classmethod
    def _calculate_venue_splits(
        cls,
        team_name: str,
        season: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate home vs away performance splits.

        Args:
            team_name: Team name
            season: Optional season filter

        Returns:
            Home/away split statistics
        """
        try:
            session = Session()

            query = text("""
                WITH team_games AS (
                    SELECT
                        m.*,
                        CASE
                            WHEN m.home_team_id = t.id THEN 'home'
                            WHEN m.away_team_id = t.id THEN 'away'
                        END as venue_type,
                        CASE
                            WHEN m.home_team_id = t.id THEN m.home_score
                            ELSE m.away_score
                        END as team_score,
                        CASE
                            WHEN m.home_team_id = t.id AND m.home_score > m.away_score THEN 1
                            WHEN m.away_team_id = t.id AND m.away_score > m.home_score THEN 1
                            ELSE 0
                        END as won
                    FROM matches m
                    JOIN teams t ON t.name = :team_name
                    WHERE (m.home_team_id = t.id OR m.away_team_id = t.id)
                        AND (:season IS NULL OR m.season = :season)
                )
                SELECT
                    venue_type,
                    COUNT(*) as games,
                    SUM(won) as wins,
                    AVG(team_score) as avg_score,
                    CAST(SUM(won) AS FLOAT) / COUNT(*) as win_rate
                FROM team_games
                GROUP BY venue_type
            """)

            result = session.execute(query, {"team_name": team_name, "season": season})
            splits_data = pd.DataFrame(result.fetchall(), columns=result.keys())

            if len(splits_data) == 0:
                return None

            splits = {}

            for _, row in splits_data.iterrows():
                venue = row['venue_type']
                splits[venue] = {
                    'games': int(row['games']),
                    'wins': int(row['wins']),
                    'win_rate': round(float(row['win_rate']), 3),
                    'avg_score': round(float(row['avg_score']), 2)
                }

            # Calculate home advantage
            if 'home' in splits and 'away' in splits:
                home_advantage = (splits['home']['win_rate'] - splits['away']['win_rate']) * 100
                splits['home_advantage_pct'] = round(home_advantage, 2)

            session.close()
            return splits

        except Exception as e:
            logger.error(f"Error calculating venue splits: {e}")
            return None

    @classmethod
    def _analyze_venue_performance(
        cls,
        team_name: str,
        season: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze performance at specific venues.

        Args:
            team_name: Team name
            season: Optional season filter

        Returns:
            Venue-specific performance statistics
        """
        try:
            session = Session()

            query = text("""
                SELECT
                    m.venue,
                    COUNT(*) as games,
                    SUM(CASE
                        WHEN (m.home_team_id = t.id AND m.home_score > m.away_score)
                            OR (m.away_team_id = t.id AND m.away_score > m.home_score)
                        THEN 1 ELSE 0
                    END) as wins,
                    AVG(CASE
                        WHEN m.home_team_id = t.id THEN m.home_score
                        ELSE m.away_score
                    END) as avg_score
                FROM matches m
                JOIN teams t ON t.name = :team_name
                WHERE (m.home_team_id = t.id OR m.away_team_id = t.id)
                    AND (:season IS NULL OR m.season = :season)
                    AND m.venue IS NOT NULL
                GROUP BY m.venue
                HAVING COUNT(*) >= 3
                ORDER BY wins DESC
                LIMIT 5
            """)

            result = session.execute(query, {"team_name": team_name, "season": season})
            venue_data = pd.DataFrame(result.fetchall(), columns=result.keys())

            if len(venue_data) == 0:
                return None

            venues = {}

            for _, row in venue_data.iterrows():
                venue = row['venue']
                venues[venue] = {
                    'games': int(row['games']),
                    'wins': int(row['wins']),
                    'win_rate': round(float(row['wins']) / float(row['games']), 3),
                    'avg_score': round(float(row['avg_score']), 2)
                }

            # Identify best and worst venues
            if venues:
                best_venue = max(venues.items(), key=lambda x: x[1]['win_rate'])
                worst_venue = min(venues.items(), key=lambda x: x[1]['win_rate'])

                venues['best'] = {
                    'venue': best_venue[0],
                    'win_rate': best_venue[1]['win_rate']
                }
                venues['worst'] = {
                    'venue': worst_venue[0],
                    'win_rate': worst_venue[1]['win_rate']
                }

            session.close()
            return venues

        except Exception as e:
            logger.error(f"Error analyzing venue performance: {e}")
            return None
