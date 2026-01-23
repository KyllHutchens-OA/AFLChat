"""
AFL Analytics Agent - Advanced Statistics

Provides advanced statistical calculations for deeper insights.
"""
from typing import Dict, Any, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class EfficiencyCalculator:
    """
    Calculates efficiency metrics for deeper performance analysis.

    Features:
    - Shooting accuracy (goals vs behinds)
    - Quarter-by-quarter momentum
    - Margin analysis (close games, blowouts)
    """

    @staticmethod
    def calculate_shooting_accuracy(
        goals: pd.Series,
        behinds: pd.Series
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate shooting accuracy metrics.

        Args:
            goals: Series of goals scored
            behinds: Series of behinds scored

        Returns:
            Dictionary with accuracy metrics
        """
        try:
            total_goals = goals.sum()
            total_behinds = behinds.sum()
            total_shots = total_goals + total_behinds

            if total_shots == 0:
                return None

            accuracy = (total_goals / total_shots * 100)
            points_per_shot = (total_goals * 6 + total_behinds) / total_shots

            return {
                'total_goals': int(total_goals),
                'total_behinds': int(total_behinds),
                'total_shots': int(total_shots),
                'accuracy_percent': round(accuracy, 2),
                'points_per_shot': round(points_per_shot, 2),
                'interpretation': EfficiencyCalculator._interpret_accuracy(accuracy)
            }

        except Exception as e:
            logger.error(f"Error calculating shooting accuracy: {e}")
            return None

    @staticmethod
    def _interpret_accuracy(accuracy: float) -> str:
        """Interpret shooting accuracy percentage."""
        if accuracy >= 65:
            return "Excellent shooting efficiency"
        elif accuracy >= 55:
            return "Good shooting accuracy"
        elif accuracy >= 45:
            return "Average accuracy"
        else:
            return "Below average accuracy - needs improvement"

    @staticmethod
    def calculate_quarter_momentum(
        data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze quarter-by-quarter scoring patterns.

        Args:
            data: DataFrame with quarter scores (q1_score, q2_score, etc.)

        Returns:
            Dictionary with quarter momentum analysis
        """
        try:
            quarter_cols = ['q1_score', 'q2_score', 'q3_score', 'q4_score']

            # Check if quarter columns exist
            available_quarters = [col for col in quarter_cols if col in data.columns]

            if len(available_quarters) < 4:
                return None

            quarter_avgs = {}
            for i, col in enumerate(available_quarters, 1):
                avg = data[col].mean()
                quarter_avgs[f'q{i}'] = round(float(avg), 2)

            # Identify strongest and weakest quarters
            strongest_quarter = max(quarter_avgs.items(), key=lambda x: x[1])
            weakest_quarter = min(quarter_avgs.items(), key=lambda x: x[1])

            # Calculate first half vs second half
            first_half = data[available_quarters[:2]].sum(axis=1).mean()
            second_half = data[available_quarters[2:]].sum(axis=1).mean()

            momentum = {
                'quarter_averages': quarter_avgs,
                'strongest_quarter': {
                    'quarter': strongest_quarter[0].upper(),
                    'avg_score': strongest_quarter[1]
                },
                'weakest_quarter': {
                    'quarter': weakest_quarter[0].upper(),
                    'avg_score': weakest_quarter[1]
                },
                'first_half_avg': round(float(first_half), 2),
                'second_half_avg': round(float(second_half), 2),
                'half_difference': round(float(second_half - first_half), 2),
                'interpretation': EfficiencyCalculator._interpret_quarter_momentum(
                    second_half - first_half
                )
            }

            return momentum

        except Exception as e:
            logger.error(f"Error calculating quarter momentum: {e}")
            return None

    @staticmethod
    def _interpret_quarter_momentum(half_diff: float) -> str:
        """Interpret first vs second half performance."""
        if half_diff > 5:
            return "Strong second half team - improves after halftime"
        elif half_diff < -5:
            return "Better first half team - momentum fades late"
        else:
            return "Consistent across halves"

    @staticmethod
    def calculate_margin_analysis(
        margins: pd.Series
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze winning/losing margins.

        Args:
            margins: Series of score margins (positive = win, negative = loss)

        Returns:
            Dictionary with margin analysis
        """
        try:
            if len(margins) == 0:
                return None

            # Separate wins and losses
            wins = margins[margins > 0]
            losses = margins[margins < 0]

            analysis = {
                'avg_margin': round(float(margins.mean()), 2),
                'biggest_win': int(margins.max()) if len(margins) > 0 else 0,
                'biggest_loss': int(margins.min()) if len(margins) > 0 else 0,
            }

            # Win margin analysis
            if len(wins) > 0:
                analysis['avg_win_margin'] = round(float(wins.mean()), 2)
                analysis['close_wins'] = int((wins <= 12).sum())  # Within 2 goals
                analysis['comfortable_wins'] = int(((wins > 12) & (wins <= 40)).sum())
                analysis['blowout_wins'] = int((wins > 40).sum())  # 40+ points

            # Loss margin analysis
            if len(losses) > 0:
                analysis['avg_loss_margin'] = round(float(abs(losses.mean())), 2)
                analysis['close_losses'] = int((abs(losses) <= 12).sum())
                analysis['heavy_losses'] = int((abs(losses) > 40).sum())

            # Overall game type distribution
            total_games = len(margins)
            close_games = int((abs(margins) <= 12).sum())
            analysis['close_game_pct'] = round((close_games / total_games * 100), 2) if total_games > 0 else 0

            analysis['interpretation'] = EfficiencyCalculator._interpret_margins(analysis)

            return analysis

        except Exception as e:
            logger.error(f"Error calculating margin analysis: {e}")
            return None

    @staticmethod
    def _interpret_margins(analysis: Dict[str, Any]) -> str:
        """Interpret margin patterns."""
        interpretations = []

        close_game_pct = analysis.get('close_game_pct', 0)
        if close_game_pct > 40:
            interpretations.append("Frequently involved in close contests")
        elif close_game_pct < 20:
            interpretations.append("Games tend to be one-sided")

        avg_win_margin = analysis.get('avg_win_margin', 0)
        avg_loss_margin = analysis.get('avg_loss_margin', 0)

        if avg_win_margin > 30:
            interpretations.append("Dominant when winning")
        elif avg_win_margin < 15:
            interpretations.append("Wins tend to be close")

        if avg_loss_margin > 40:
            interpretations.append("Struggles to stay competitive in losses")

        return "; ".join(interpretations) if interpretations else "Mixed margin patterns"

    @staticmethod
    def calculate_all_efficiency_metrics(
        data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Calculate all efficiency metrics from a dataset.

        Args:
            data: DataFrame with match statistics

        Returns:
            Dictionary with all efficiency metrics
        """
        metrics = {}

        # Shooting accuracy
        if 'goals' in data.columns and 'behinds' in data.columns:
            shooting = EfficiencyCalculator.calculate_shooting_accuracy(
                data['goals'], data['behinds']
            )
            if shooting:
                metrics['shooting'] = shooting

        # Quarter momentum
        quarter_momentum = EfficiencyCalculator.calculate_quarter_momentum(data)
        if quarter_momentum:
            metrics['quarter_momentum'] = quarter_momentum

        # Margin analysis
        if 'margin' in data.columns:
            margin_analysis = EfficiencyCalculator.calculate_margin_analysis(
                data['margin']
            )
            if margin_analysis:
                metrics['margins'] = margin_analysis

        return metrics
