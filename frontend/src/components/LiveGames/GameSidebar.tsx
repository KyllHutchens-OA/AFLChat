import React from 'react';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';

interface LiveGame {
  id: number;
  squiggle_id: number;
  season: number;
  round: string;
  home_team: {
    id: number;
    name: string;
    abbreviation: string;
  };
  away_team: {
    id: number;
    name: string;
    abbreviation: string;
  };
  home_score: number;
  away_score: number;
  home_goals: number;
  home_behinds: number;
  away_goals: number;
  away_behinds: number;
  status: string;
  complete_percent: number;
  time_str: string;
  current_quarter: number | null;
  venue: string;
  match_date: string;
  last_updated: string;
}

interface UpcomingMatch {
  id: number;
  round: string | number;
  home_team: string;
  away_team: string;
  venue: string;
  date: string;
}

interface GameSidebarProps {
  games: LiveGame[];
  selectedGameId: number | null;
  onSelectGame: (gameId: number) => void;
  upcomingMatches?: UpcomingMatch[];
}

const GameSidebar: React.FC<GameSidebarProps> = ({ games, selectedGameId, onSelectGame, upcomingMatches = [] }) => {
  const { hideScores } = useSpoilerMode();
  const liveGames = games.filter(g => g.status === 'live');
  const completedGames = games.filter(g => g.status === 'completed');

  const displayScore = (score: number) => hideScores ? '?' : score;

  const formatMatchTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return {
      day: date.toLocaleDateString('en-AU', { weekday: 'short', month: 'short', day: 'numeric' }),
      time: date.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' }),
    };
  };

  const GameTile: React.FC<{ game: LiveGame }> = ({ game }) => {
    const isSelected = game.id === selectedGameId;
    const isLive = game.status === 'live';

    return (
      <button
        onClick={() => onSelectGame(game.id)}
        className={`
          w-full text-left transition-all duration-200 ease-apple rounded-apple p-3
          ${isLive ? 'border-l-4 border-l-apple-red' : ''}
          ${isSelected
            ? 'bg-apple-blue-50 border-apple-blue-500 shadow-apple'
            : isLive
              ? 'glass shadow-apple-sm hover:shadow-apple'
              : 'bg-apple-gray-50 opacity-80 hover:opacity-100 hover:bg-apple-gray-100'
          }
          ${!isLive && !isSelected ? 'border-l-4 border-l-transparent' : ''}
          active:scale-[0.98]
        `}
      >
        {/* Home team row */}
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-semibold text-apple-gray-900 truncate">
            {game.home_team.abbreviation}
          </span>
          <span className={`text-sm font-bold text-apple-gray-900 tabular-nums ${hideScores ? 'blur-sm select-none' : ''}`}>
            {displayScore(game.home_score)}
          </span>
        </div>

        {/* Away team row */}
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-sm font-semibold text-apple-gray-900 truncate">
            {game.away_team.abbreviation}
          </span>
          <span className={`text-sm font-bold text-apple-gray-900 tabular-nums ${hideScores ? 'blur-sm select-none' : ''}`}>
            {displayScore(game.away_score)}
          </span>
        </div>

        {/* Status */}
        <div className="flex items-center gap-1.5">
          {isLive && (
            <div className="w-1.5 h-1.5 bg-apple-red rounded-full animate-pulse" />
          )}
          <span className={`text-xs font-medium ${isLive ? 'text-apple-red' : 'text-apple-gray-400'}`}>
            {isLive ? (game.time_str || 'Live') : 'Final'}
          </span>
        </div>
      </button>
    );
  };

  // Only show upcoming matches that aren't already in the live/completed list
  const filteredUpcoming = upcomingMatches.slice(0, 5);

  const UpcomingSection = () => {
    if (filteredUpcoming.length === 0) return null;

    return (
      <div className="mt-4">
        <div className="mb-2 px-1">
          <span className="text-xs font-semibold text-apple-gray-400 uppercase tracking-wide">Upcoming</span>
        </div>
        <div className="space-y-2">
          {filteredUpcoming.map(match => {
            const { day, time } = formatMatchTime(match.date);
            return (
              <div
                key={match.id}
                className="w-full text-left rounded-apple p-3 bg-apple-gray-50 border-l-4 border-l-apple-gray-200 opacity-70"
              >
                {/* Home team */}
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold text-apple-gray-700 truncate">
                    {match.home_team}
                  </span>
                </div>
                {/* Away team */}
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-semibold text-apple-gray-700 truncate">
                    {match.away_team}
                  </span>
                </div>
                {/* Time */}
                <div className="text-xs text-apple-gray-400">
                  {day} • {time}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Desktop: Vertical sidebar */}
      <div className="hidden lg:block">
        <div className="glass rounded-apple-xl p-4 shadow-apple-lg overflow-y-auto max-h-[calc(100vh-12rem)]">
          {/* Live section */}
          {liveGames.length > 0 && (
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-2 px-1">
                <div className="w-2 h-2 bg-apple-red rounded-full animate-pulse" />
                <span className="text-xs font-semibold text-apple-red uppercase tracking-wide">Live</span>
              </div>
              <div className="space-y-2">
                {liveGames.map(game => (
                  <GameTile key={game.id} game={game} />
                ))}
              </div>
            </div>
          )}

          {/* Results section */}
          {completedGames.length > 0 && (
            <div>
              <div className="mb-2 px-1">
                <span className="text-xs font-semibold text-apple-gray-400 uppercase tracking-wide">Results</span>
              </div>
              <div className="space-y-2">
                {completedGames.map(game => (
                  <GameTile key={game.id} game={game} />
                ))}
              </div>
            </div>
          )}

          {/* Upcoming section */}
          <UpcomingSection />
        </div>
      </div>

      {/* Mobile: Horizontal scrolling strip */}
      <div className="lg:hidden">
        <div className="overflow-x-auto -mx-6 px-6">
          <div className="flex flex-row gap-3 pb-2" style={{ minWidth: 'max-content' }}>
            {/* Live games first */}
            {liveGames.map(game => (
              <div key={game.id} className="w-36 flex-shrink-0">
                <GameTile game={game} />
              </div>
            ))}
            {/* Then completed */}
            {completedGames.map(game => (
              <div key={game.id} className="w-36 flex-shrink-0">
                <GameTile game={game} />
              </div>
            ))}
            {/* Then upcoming */}
            {filteredUpcoming.map(match => {
              const { day, time } = formatMatchTime(match.date);
              return (
                <div key={match.id} className="w-36 flex-shrink-0">
                  <div className="rounded-apple p-3 bg-apple-gray-50 border-l-4 border-l-apple-gray-200 opacity-70 h-full">
                    <div className="text-sm font-semibold text-apple-gray-700 truncate mb-1">
                      {match.home_team}
                    </div>
                    <div className="text-sm font-semibold text-apple-gray-700 truncate mb-1.5">
                      {match.away_team}
                    </div>
                    <div className="text-xs text-apple-gray-400">
                      {day} • {time}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
};

export default GameSidebar;
