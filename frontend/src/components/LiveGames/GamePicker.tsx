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

interface GamePickerProps {
  games: LiveGame[];
  selectedGameId: number | null;
  onSelectGame: (gameId: number) => void;
}

const GamePicker: React.FC<GamePickerProps> = ({ games, selectedGameId, onSelectGame }) => {
  const { hideScores } = useSpoilerMode();
  const liveGames = games.filter(g => g.status === 'live');

  // Get completed games from the current round only
  const allCompletedGames = games.filter(g => g.status === 'completed');
  const currentRound = liveGames.length > 0
    ? liveGames[0].round
    : allCompletedGames.length > 0
      ? allCompletedGames[0].round
      : null;
  const completedGames = currentRound
    ? allCompletedGames.filter(g => g.round === currentRound)
    : allCompletedGames;

  // Helper to display scores based on spoiler mode
  const displayScore = (score: number) => hideScores ? '?' : score;

  return (
    <div className="space-y-4">
      {/* Live Games - Full Cards */}
      {liveGames.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {liveGames.map((game) => {
            const isSelected = game.id === selectedGameId;

            return (
              <button
                key={game.id}
                onClick={() => onSelectGame(game.id)}
                className={`
                  card-apple p-4 text-left transition-all duration-200 ease-apple
                  ${isSelected
                    ? 'border-afl-accent bg-afl-accent-50 shadow-apple-md'
                    : 'border-afl-warm-200 hover:border-afl-accent-300 hover:shadow-apple'
                  }
                  active:scale-95
                `}
              >
                {/* Header: Round, Venue, Live Badge */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-afl-warm-700">
                      Round {game.round} • {game.venue}
                    </p>
                  </div>

                  {/* LIVE Badge */}
                  <div className="flex items-center gap-1.5 px-2 py-1 bg-apple-red/10 border border-apple-red/30 rounded-full">
                    <div className="w-1.5 h-1.5 bg-apple-red rounded-full animate-pulse"></div>
                    <span className="text-xs font-semibold text-apple-red uppercase">Live</span>
                  </div>
                </div>

                {/* Teams and Scores */}
                <div className="space-y-2 mb-3">
                  {/* Home Team */}
                  <div className="flex items-center justify-between">
                    <span className="text-lg font-semibold text-afl-warm-900">
                      {game.home_team.abbreviation}
                    </span>
                    <span className={`text-2xl font-bold text-afl-warm-900 ${hideScores ? 'blur-sm select-none' : ''}`}>
                      {displayScore(game.home_score)}
                    </span>
                  </div>

                  {/* Away Team */}
                  <div className="flex items-center justify-between">
                    <span className="text-lg font-semibold text-afl-warm-900">
                      {game.away_team.abbreviation}
                    </span>
                    <span className={`text-2xl font-bold text-afl-warm-900 ${hideScores ? 'blur-sm select-none' : ''}`}>
                      {displayScore(game.away_score)}
                    </span>
                  </div>
                </div>

                {/* Time/Status */}
                <div className="text-sm text-afl-warm-500 font-medium">
                  {game.time_str || 'Live'}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Completed Games - Compact List (always shown, scores blurred in spoiler mode) */}
      {completedGames.length > 0 && (
        <div>
          {liveGames.length > 0 && (
            <div className="text-sm font-medium text-afl-warm-500 mb-2 px-1">
              Recent Results
            </div>
          )}
          <div className="space-y-2">
            {completedGames.map((game) => {
              const isSelected = game.id === selectedGameId;
              const winner = game.home_score > game.away_score ? 'home' : 'away';

              return (
                <button
                  key={game.id}
                  onClick={() => onSelectGame(game.id)}
                  className={`
                    w-full card-apple px-3 py-2 text-left transition-all duration-200 ease-apple
                    ${isSelected
                      ? 'border-afl-accent bg-afl-accent-50 shadow-apple'
                      : 'border-afl-warm-200 hover:border-afl-warm-300 hover:bg-afl-warm-50'
                    }
                    active:scale-[0.99]
                  `}
                >
                  <div className="flex items-center justify-between gap-4">
                    {/* Teams and Scores - Compact */}
                    <div className="flex-1 flex items-center gap-3">
                      <div className="flex items-center gap-2 min-w-[140px]">
                        <span className={`text-sm font-semibold ${!hideScores && winner === 'home' ? 'text-afl-warm-900' : 'text-afl-warm-500'}`}>
                          {game.home_team.abbreviation}
                        </span>
                        <span className={`text-base font-bold ${!hideScores && winner === 'home' ? 'text-afl-warm-900' : 'text-afl-warm-500'} ${hideScores ? 'blur-sm select-none' : ''}`}>
                          {displayScore(game.home_score)}
                        </span>
                      </div>
                      <span className="text-afl-warm-400 text-sm">vs</span>
                      <div className="flex items-center gap-2 min-w-[140px]">
                        <span className={`text-sm font-semibold ${!hideScores && winner === 'away' ? 'text-afl-warm-900' : 'text-afl-warm-500'}`}>
                          {game.away_team.abbreviation}
                        </span>
                        <span className={`text-base font-bold ${!hideScores && winner === 'away' ? 'text-afl-warm-900' : 'text-afl-warm-500'} ${hideScores ? 'blur-sm select-none' : ''}`}>
                          {displayScore(game.away_score)}
                        </span>
                      </div>
                    </div>

                    {/* Venue - Compact */}
                    <div className="text-xs text-afl-warm-500 hidden sm:block">
                      {game.venue}
                    </div>

                    {/* Final badge */}
                    <div className="text-xs font-medium text-afl-warm-400 px-2 py-0.5 bg-afl-warm-100 rounded">
                      Final
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default GamePicker;
