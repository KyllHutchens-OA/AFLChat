import React from 'react';
import { useLiveGameDetail } from '../../hooks/useLiveGameDetail';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';
import ProgressBar from './ProgressBar';
import GameStats from './GameStats';
import QuarterSummaries from './QuarterSummaries';

interface LiveDashboardProps {
  gameId: number;
}

const LiveDashboard: React.FC<LiveDashboardProps> = ({ gameId }) => {
  const { game, loading, error } = useLiveGameDetail(gameId);
  const { hideScores } = useSpoilerMode();

  // Helper to display scores based on spoiler mode
  const displayScore = (score: number) => hideScores ? '?' : score;
  const displayBreakdown = (goals: number, behinds: number) => hideScores ? '?.?' : `${goals}.${behinds}`;

  if (loading) {
    return (
      <div className="card-apple p-8 animate-shimmer">
        <div className="h-64 bg-apple-gray-200 rounded-apple"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card-apple p-8 text-center">
        <div className="text-5xl mb-4">⚠️</div>
        <p className="text-apple-gray-700 font-medium">{error}</p>
      </div>
    );
  }

  if (!game) {
    return null;
  }

  const hasQuarterSummaries = game.quarter_summaries && Object.keys(game.quarter_summaries).length > 0;

  return (
    <div className="space-y-6">
      {/* Scoreboard */}
      <div className="glass rounded-apple-xl p-8 shadow-apple-lg">
        {/* Round and Venue */}
        <div className="text-center mb-6">
          <p className="text-sm font-medium text-apple-gray-500 uppercase tracking-wide">
            Round {game.round} • {game.venue}
          </p>
        </div>

        {/* Teams and Scores */}
        <div className="grid grid-cols-2 gap-8 mb-6">
          {/* Home Team */}
          <div className="text-center">
            <h2 className="text-2xl font-semibold text-apple-gray-900 mb-2">
              {game.home_team.name}
            </h2>
            <p className={`text-6xl font-bold text-apple-gray-900 mb-1 ${hideScores ? 'blur-md select-none' : ''}`}>
              {displayScore(game.home_score)}
            </p>
            <p className={`text-sm text-apple-gray-500 ${hideScores ? 'blur-sm select-none' : ''}`}>
              {displayBreakdown(game.home_goals, game.home_behinds)}
            </p>
          </div>

          {/* Away Team */}
          <div className="text-center">
            <h2 className="text-2xl font-semibold text-apple-gray-900 mb-2">
              {game.away_team.name}
            </h2>
            <p className={`text-6xl font-bold text-apple-gray-900 mb-1 ${hideScores ? 'blur-md select-none' : ''}`}>
              {displayScore(game.away_score)}
            </p>
            <p className={`text-sm text-apple-gray-500 ${hideScores ? 'blur-sm select-none' : ''}`}>
              {displayBreakdown(game.away_goals, game.away_behinds)}
            </p>
          </div>
        </div>

        {/* Game Time */}
        <div className="text-center mb-4">
          <p className="text-xl font-semibold text-apple-gray-700">
            {game.status === 'live' && game.time_str
              ? game.time_str
              : game.status === 'completed'
              ? 'Final'
              : 'Scheduled'}
          </p>
          {game.status === 'live' && game.last_updated && (() => {
            const ageMs = Date.now() - new Date(game.last_updated + 'Z').getTime();
            return ageMs > 3 * 60 * 1000 ? (
              <p className="text-xs text-amber-500 mt-1">Data may be delayed</p>
            ) : null;
          })()}
        </div>

        {/* Progress Bar */}
        <ProgressBar completePercent={game.complete_percent} />

      </div>

      {/* Top Performers - shown for both live and completed games */}
      {!hideScores && (
        <GameStats gameId={game.id} gameStatus={game.status} />
      )}

      {/* Quarter Summaries - shown when available */}
      {!hideScores && hasQuarterSummaries && (
        <QuarterSummaries quarterSummaries={game.quarter_summaries!} quarterScores={game.quarter_scores} />
      )}

      {/* AI Summary for completed games - hidden when spoiler mode is on */}
      {!hideScores && game.status === 'completed' && game.ai_summary && (
        <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
          <h3 className="text-xl font-semibold text-apple-gray-900 mb-3">
            Match Summary
          </h3>
          <p className="text-apple-gray-700 leading-relaxed">
            {game.ai_summary}
          </p>
        </div>
      )}

      {/* Post-game stats analysis - hidden when spoiler mode is on */}
      {!hideScores && game.status === 'completed' && game.post_game_analysis && (
        <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
          <h3 className="text-xl font-semibold text-apple-gray-900 mb-3">
            Match Stats Analysis
          </h3>
          <div className="space-y-3">
            {game.post_game_analysis.split('\n\n').map((paragraph, i) => (
              <p key={i} className="text-apple-gray-700 leading-relaxed">
                {paragraph}
              </p>
            ))}
          </div>
        </div>
      )}

    </div>
  );
};

export default LiveDashboard;
