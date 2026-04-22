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

You MUST mention specific players by name. Reference the top goal kicker by name and goals scored. If someone had a standout game in disposals or fantasy, call them out too. Use last names naturally (e.g., 'Daicos was everywhere with 35 disposals'). Tell the story of the game through the players who shaped it.

Match Details:
- {home_team} ({home_nick}) vs {away_team} ({away_nick})
- Final Score: {game.home_score} - {game.away_score}
- Winner: {winner} by {margin} points
- Venue: {game.venue}
- Quarter Scores: {quarter_scores if quarter_scores else 'Not available'}

Game Flow: {momentum}

{performers_str}

Write a casual, engaging 2-3 sentence summary. Don't just list stats - tell the story of the game through the players who shaped it."""

            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_RESPONSE", "gpt-5-mini"),
                messages=[
                    {"role": "system", "content": "You are an AFL commentator who writes brief, casual match summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=1,
                max_completion_tokens=4096,
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated summary for game {game.id}: {summary[:50]}...")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate summary for game {game.id}: {e}")
            return None


    @staticmethod
    def generate_quarter_summary(
        quarter: int,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        quarter_stats: list,
    ) -> Optional[str]:
        """
        Generate a casual 1-2 sentence summary for a completed quarter.

        Args:
            quarter: Quarter number (1-4)
            home_team: Home team full name
            away_team: Away team full name
            home_score: Score at end of quarter
            away_score: Score at end of quarter
            quarter_stats: List of top player stat dicts for the quarter
        """
        try:
            home_nick = GameSummaryService.get_nickname(home_team)
            away_nick = GameSummaryService.get_nickname(away_team)

            # Format top performers
            performers = ""
            if quarter_stats:
                lines = []
                # Top by disposals
                top_disp = sorted(quarter_stats, key=lambda x: x.get("disposals", 0), reverse=True)[:2]
                for p in top_disp:
                    lines.append(f"{p['name']} ({p.get('disposals', 0)} disposals)")
                # Top goalscorers
                top_goals = [p for p in quarter_stats if p.get("goals", 0) > 0]
                top_goals.sort(key=lambda x: x["goals"], reverse=True)
                for p in top_goals[:2]:
                    lines.append(f"{p['name']} ({p['goals']} goals)")
                performers = "; ".join(lines)

            margin = home_score - away_score
            if margin > 0:
                leader = home_nick
            elif margin < 0:
                leader = away_nick
            else:
                leader = "tied"

            prompt = f"""Write a casual 1-2 sentence summary of Q{quarter} of an AFL match.
Use team nicknames: {home_nick}, {away_nick}.
You MUST mention specific players by name. Reference top performers naturally.

Score at end of Q{quarter}: {home_team} {home_score} - {away_team} {away_score} ({"tied" if margin == 0 else f"{leader} by {abs(margin)} pts"})
Top performers so far: {performers if performers else "Data not available"}

Example: "The Pies took control in Q2 with Daicos racking up 12 disposals. De Goey kicked two goals to blow the margin out to 25 points."
Keep it brief and engaging."""

            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_RESPONSE", "gpt-5-mini"),
                messages=[
                    {"role": "system", "content": "You are an AFL commentator writing brief quarter summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=1,
                max_completion_tokens=2000,
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated Q{quarter} summary: {summary[:60]}...")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate quarter summary: {e}")
            return None


    @staticmethod
    def generate_post_game_analysis_from_stats(
        home_team: str,
        away_team: str,
        stats: dict,
    ) -> Optional[str]:
        """
        Generate a 2-paragraph post-game analysis from real Footywire stats.

        Args:
            home_team: Home team full name
            away_team: Away team full name
            stats: Dict from FootywireScraper.get_top_performers() containing
                   top_goal_kickers, top_disposals, top_fantasy, all_players

        Returns:
            Two-paragraph analysis string, or None if generation fails
        """
        try:
            home_nick = GameSummaryService.get_nickname(home_team)
            away_nick = GameSummaryService.get_nickname(away_team)

            top_goals = stats.get('top_goal_kickers', [])
            top_disp = stats.get('top_disposals', [])
            top_fantasy = stats.get('top_fantasy', [])

            goals_str = ', '.join(
                f"{p['name']} ({p['goals']} goals)" for p in top_goals[:4] if p.get('goals', 0) > 0
            ) or 'None recorded'
            disp_str = ', '.join(
                f"{p['name']} ({p['disposals']} disposals)" for p in top_disp[:4]
            ) or 'None recorded'
            fantasy_str = ', '.join(
                f"{p['name']} ({p['points']} pts)" for p in top_fantasy[:3]
            ) or 'None recorded'

            prompt = (
                f"Write exactly 2 short paragraphs about this AFL match between "
                f"{home_team} ({home_nick}) and {away_team} ({away_nick}).\n\n"
                f"Paragraph 1: Highlight the individual standout performers. "
                f"Top goal kickers: {goals_str}. "
                f"Top disposals: {disp_str}. "
                f"Use last names naturally, be casual and engaging.\n\n"
                f"Paragraph 2: Brief overall narrative — mention which team's players "
                f"dominated statistically and what that meant for the game. "
                f"Top fantasy scores: {fantasy_str}.\n\n"
                f"Use team nicknames ({home_nick}, {away_nick}). "
                f"Do NOT include headings or labels. Two plain paragraphs only."
            )

            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_RESPONSE", "gpt-5-mini"),
                messages=[
                    {"role": "system", "content": "You are an AFL commentator writing brief post-game analysis."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_completion_tokens=400,
            )

            analysis = response.choices[0].message.content.strip()
            if analysis:
                logger.info(f"Generated post-game analysis for {home_nick} vs {away_nick}: {analysis[:60]}...")
                return analysis

            logger.warning(f"Empty post-game analysis for {home_nick} vs {away_nick}")
            return None

        except Exception as e:
            logger.error(f"Failed to generate post-game analysis for {home_team} vs {away_team}: {e}")
            return None


# Singleton instance
game_summary_service = GameSummaryService()
