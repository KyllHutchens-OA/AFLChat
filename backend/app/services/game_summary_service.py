"""
Game Summary Service - Generates AI summaries for completed AFL games.
Uses OpenAI to create casual, engaging match summaries with team nicknames.
"""
import logging
import os
from typing import Dict, Any, List, Optional

from openai import OpenAI
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(30.0, connect=10.0)
)

# Team nicknames for casual summaries
TEAM_NICKNAMES = {
    'Adelaide': 'Crows',
    'Brisbane Lions': 'Lions',
    'Carlton': 'Blues',
    'Collingwood': 'Pies',
    'Essendon': 'Bombers',
    'Fremantle': 'Dockers',
    'Geelong': 'Cats',
    'Gold Coast': 'Suns',
    'Greater Western Sydney': 'Giants',
    'Hawthorn': 'Hawks',
    'Melbourne': 'Dees',
    'North Melbourne': 'Roos',
    'Port Adelaide': 'Power',
    'Richmond': 'Tigers',
    'St Kilda': 'Saints',
    'Sydney': 'Swans',
    'West Coast': 'Eagles',
    'Western Bulldogs': 'Dogs',
}


class GameSummaryService:
    """Service for generating AI summaries of completed AFL games."""

    @staticmethod
    def get_nickname(team_name: str) -> str:
        """Get the common nickname for a team."""
        return TEAM_NICKNAMES.get(team_name, team_name)

    @staticmethod
    def calculate_quarter_margins(game) -> List[Dict[str, Any]]:
        """
        Calculate the margin at the end of each quarter.

        Returns:
            List of dicts with quarter info and margin from home team's perspective.
            Positive = home leading, negative = away leading.
        """
        quarters = []

        # Q1
        if game.home_q1_score is not None and game.away_q1_score is not None:
            quarters.append({
                'quarter': 1,
                'home_score': game.home_q1_score,
                'away_score': game.away_q1_score,
                'margin': game.home_q1_score - game.away_q1_score,
            })

        # Q2 (half time)
        if game.home_q2_score is not None and game.away_q2_score is not None:
            quarters.append({
                'quarter': 2,
                'home_score': game.home_q2_score,
                'away_score': game.away_q2_score,
                'margin': game.home_q2_score - game.away_q2_score,
            })

        # Q3 (three quarter time)
        if game.home_q3_score is not None and game.away_q3_score is not None:
            quarters.append({
                'quarter': 3,
                'home_score': game.home_q3_score,
                'away_score': game.away_q3_score,
                'margin': game.home_q3_score - game.away_q3_score,
            })

        # Q4 (final)
        if game.home_q4_score is not None and game.away_q4_score is not None:
            quarters.append({
                'quarter': 4,
                'home_score': game.home_q4_score,
                'away_score': game.away_q4_score,
                'margin': game.home_q4_score - game.away_q4_score,
            })

        return quarters

    @staticmethod
    def identify_momentum_narrative(quarters: List[Dict], home_team: str, away_team: str) -> str:
        """
        Identify any notable momentum shifts in the game.

        Returns a narrative description of how the game played out.
        """
        if len(quarters) < 2:
            return "Limited quarter data available."

        narratives = []
        home_nick = GameSummaryService.get_nickname(home_team)
        away_nick = GameSummaryService.get_nickname(away_team)

        # Check for comebacks
        final_margin = quarters[-1]['margin'] if quarters else 0
        winner_nick = home_nick if final_margin > 0 else away_nick
        loser_nick = away_nick if final_margin > 0 else home_nick

        # Half time margin (if available)
        if len(quarters) >= 2:
            ht_margin = quarters[1]['margin']

            # Check for comeback: team that was behind at half time won
            if (ht_margin < 0 and final_margin > 0) or (ht_margin > 0 and final_margin < 0):
                deficit = abs(ht_margin)
                narratives.append(f"{winner_nick} fought back after being {deficit} points down at half time")

        # Check for big quarter
        if len(quarters) >= 2:
            for i in range(1, len(quarters)):
                prev_margin = quarters[i-1]['margin']
                curr_margin = quarters[i]['margin']
                swing = curr_margin - prev_margin

                if abs(swing) >= 30:  # 30+ point swing
                    quarter_num = quarters[i]['quarter']
                    if swing > 0:
                        narratives.append(f"{home_nick} dominated Q{quarter_num}")
                    else:
                        narratives.append(f"{away_nick} dominated Q{quarter_num}")

        # Check for wire-to-wire
        if quarters:
            all_same_leader = all(
                (q['margin'] > 0) == (quarters[0]['margin'] > 0)
                for q in quarters if q['margin'] != 0
            )
            if all_same_leader and quarters[0]['margin'] != 0:
                leader = home_nick if quarters[0]['margin'] > 0 else away_nick
                narratives.append(f"{leader} led from start to finish")

        return ". ".join(narratives) if narratives else "A competitive contest throughout."

    @staticmethod
    def format_top_performers(player_stats: Dict) -> str:
        """Format top performers for the prompt."""
        lines = []

        if player_stats.get('top_goal_kickers'):
            scorers = player_stats['top_goal_kickers'][:3]
            scorer_str = ", ".join([f"{p['name']} ({p['goals']} goals)" for p in scorers])
            lines.append(f"Top Goal Kickers: {scorer_str}")

        if player_stats.get('top_disposals'):
            disposals = player_stats['top_disposals'][:3]
            disp_str = ", ".join([f"{p['name']} ({p['disposals']} disposals)" for p in disposals])
            lines.append(f"Top Disposals: {disp_str}")

        if player_stats.get('top_fantasy'):
            fantasy = player_stats['top_fantasy'][:3]
            fantasy_str = ", ".join([f"{p['name']} ({p['points']} pts)" for p in fantasy])
            lines.append(f"Top Fantasy: {fantasy_str}")

        return "\n".join(lines) if lines else "Player stats not available."

    @staticmethod
    def generate_summary(game, player_stats: Optional[Dict] = None) -> Optional[str]:
        """
        Generate an AI summary for a completed game.

        Args:
            game: LiveGame model instance
            player_stats: Optional dict with top_goal_kickers, top_disposals, top_fantasy

        Returns:
            Generated summary string or None if generation fails
        """
        try:
            home_team = game.home_team.name
            away_team = game.away_team.name
            home_nick = GameSummaryService.get_nickname(home_team)
            away_nick = GameSummaryService.get_nickname(away_team)

            # Calculate quarter margins
            quarters = GameSummaryService.calculate_quarter_margins(game)
            momentum = GameSummaryService.identify_momentum_narrative(quarters, home_team, away_team)

            # Format quarter scores
            quarter_scores = ""
            if quarters:
                q_parts = []
                for q in quarters:
                    q_parts.append(f"Q{q['quarter']}: {q['home_score']}-{q['away_score']}")
                quarter_scores = ", ".join(q_parts)

            # Determine winner
            if game.home_score > game.away_score:
                winner = home_nick
                loser = away_nick
                margin = game.home_score - game.away_score
            else:
                winner = away_nick
                loser = home_nick
                margin = game.away_score - game.home_score

            # Format performers
            performers_str = ""
            if player_stats:
                performers_str = GameSummaryService.format_top_performers(player_stats)

            prompt = f"""You are a casual AFL commentator. Write a 2-3 sentence summary of this match.

Use these team nicknames where appropriate: {home_nick}, {away_nick}
Be casual and engaging but not over the top. Reference the flow of the game if there was a notable comeback or momentum shift.

Match Details:
- {home_team} ({home_nick}) vs {away_team} ({away_nick})
- Final Score: {game.home_score} - {game.away_score}
- Winner: {winner} by {margin} points
- Venue: {game.venue}
- Quarter Scores: {quarter_scores if quarter_scores else 'Not available'}

Game Flow: {momentum}

{performers_str}

Write a casual, engaging 2-3 sentence summary. Mention a standout performer if the data is available. Don't just list stats - tell the story of the game."""

            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_RESPONSE", "gpt-5-mini"),
                messages=[
                    {"role": "system", "content": "You are an AFL commentator who writes brief, casual match summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200,
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated summary for game {game.id}: {summary[:50]}...")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate summary for game {game.id}: {e}")
            return None


# Singleton instance
game_summary_service = GameSummaryService()
