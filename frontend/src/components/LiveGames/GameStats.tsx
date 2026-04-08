import React, { useEffect, useRef } from 'react';
import { useLiveData } from '../../contexts/LiveDataContext';

// Shorten API-Sports team names (e.g. "Hawthorn Hawks" -> "HAW")
const shortenTeam = (team: string): string => {
  const map: Record<string, string> = {
    'Adelaide Crows': 'ADE',
    'Brisbane Lions': 'BRL',
    'Carlton Blues': 'CAR',
    'Collingwood Magpies': 'COL',
    'Essendon Bombers': 'ESS',
    'Fremantle Dockers': 'FRE',
    'Geelong Cats': 'GEE',
    'Gold Coast Suns': 'GCS',
    'GWS Giants': 'GWS',
    'Hawthorn Hawks': 'HAW',
    'Melbourne Demons': 'MEL',
    'North Melbourne Kangaroos': 'NME',
    'Port Adelaide Power': 'PTA',
    'Richmond Tigers': 'RIC',
    'St Kilda Saints': 'STK',
    'Sydney Swans': 'SYD',
    'West Coast Eagles': 'WCE',
    'Western Bulldogs': 'WBD',
  };
  return map[team] || team.slice(0, 3).toUpperCase();
};

interface GameStatsProps {
  gameId: number;
  gameStatus?: string;
}

const GameStats: React.FC<GameStatsProps> = ({ gameId, gameStatus }) => {
  const { getGameStats, gameStatsLoading, fetchGameStats } = useLiveData();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stats = getGameStats(gameId);
  const loading = gameStatsLoading(gameId) && !stats;

  // Fetch stats on mount, poll for live games
  useEffect(() => {
    fetchGameStats(gameId, gameStatus);

    if (gameStatus === 'live') {
      pollRef.current = setInterval(() => fetchGameStats(gameId, gameStatus), 30000);
    }

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [gameId, gameStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return null; // Don't show skeleton to avoid layout shift
  }

  if (!stats) {
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
      <h3 className="text-lg font-semibold text-afl-warm-900 mb-4">
        Top Performers
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Top Goal Kickers */}
        {stats.top_goal_kickers?.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-afl-warm-500 mb-2">
              Goals
            </h4>
            <div className="space-y-1.5">
              {stats.top_goal_kickers.map((player, idx) => (
                <div
                  key={`goal-${idx}`}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="truncate flex-1 mr-2">
                    <span className="text-afl-warm-700">{player.name}</span>
                    {player.team && (
                      <span className="text-afl-warm-400 text-xs ml-1">{shortenTeam(player.team)}</span>
                    )}
                  </div>
                  <span className="font-semibold text-afl-warm-900 tabular-nums">
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
            <h4 className="text-sm font-medium text-afl-warm-500 mb-2">
              Disposals
            </h4>
            <div className="space-y-1.5">
              {stats.top_disposals.map((player, idx) => (
                <div
                  key={`disp-${idx}`}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="truncate flex-1 mr-2">
                    <span className="text-afl-warm-700">{player.name}</span>
                    {player.team && (
                      <span className="text-afl-warm-400 text-xs ml-1">{shortenTeam(player.team)}</span>
                    )}
                  </div>
                  <span className="font-semibold text-afl-warm-900 tabular-nums">
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
            <h4 className="text-sm font-medium text-afl-warm-500 mb-2">
              Fantasy
            </h4>
            <div className="space-y-1.5">
              {stats.top_fantasy.map((player, idx) => (
                <div
                  key={`fantasy-${idx}`}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="truncate flex-1 mr-2">
                    <span className="text-afl-warm-700">{player.name}</span>
                    {player.team && (
                      <span className="text-afl-warm-400 text-xs ml-1">{shortenTeam(player.team)}</span>
                    )}
                  </div>
                  <span className="font-semibold text-afl-warm-900 tabular-nums">
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
