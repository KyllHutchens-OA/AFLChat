import React from 'react';
import { useGameStats } from '../../hooks/useGameStats';

interface GameStatsProps {
  gameId: number;
}

const GameStats: React.FC<GameStatsProps> = ({ gameId }) => {
  const { stats, loading, error } = useGameStats(gameId);

  if (loading) {
    return null; // Don't show skeleton to avoid layout shift
  }

  if (error || !stats) {
    return null; // Silently fail - stats aren't critical
  }

  const hasStats =
    stats.top_goal_kickers?.length > 0 ||
    stats.top_disposals?.length > 0 ||
    stats.top_fantasy?.length > 0;

  if (!hasStats) {
    return null;
  }

  return (
    <div className="card-apple p-6">
      <h3 className="text-lg font-semibold text-apple-gray-900 mb-4">
        Top Performers
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Top Goal Kickers */}
        {stats.top_goal_kickers?.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-apple-gray-500 mb-2">
              Goals
            </h4>
            <div className="space-y-1.5">
              {stats.top_goal_kickers.map((player, idx) => (
                <div
                  key={`goal-${idx}`}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-apple-gray-700 truncate flex-1 mr-2">
                    {player.name}
                  </span>
                  <span className="font-semibold text-apple-gray-900 tabular-nums">
                    {player.goals}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top Disposals */}
        {stats.top_disposals?.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-apple-gray-500 mb-2">
              Disposals
            </h4>
            <div className="space-y-1.5">
              {stats.top_disposals.map((player, idx) => (
                <div
                  key={`disp-${idx}`}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-apple-gray-700 truncate flex-1 mr-2">
                    {player.name}
                  </span>
                  <span className="font-semibold text-apple-gray-900 tabular-nums">
                    {player.disposals}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top Fantasy */}
        {stats.top_fantasy?.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-apple-gray-500 mb-2">
              Fantasy
            </h4>
            <div className="space-y-1.5">
              {stats.top_fantasy.map((player, idx) => (
                <div
                  key={`fantasy-${idx}`}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-apple-gray-700 truncate flex-1 mr-2">
                    {player.name}
                  </span>
                  <span className="font-semibold text-apple-gray-900 tabular-nums">
                    {player.points}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default GameStats;
