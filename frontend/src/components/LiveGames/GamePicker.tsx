import React from 'react';

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
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {games.map((game) => {
        const isSelected = game.id === selectedGameId;
        const isLive = game.status === 'live';

        return (
          <button
            key={game.id}
            onClick={() => onSelectGame(game.id)}
            className={`
              card-apple p-4 text-left transition-all duration-200 ease-apple
              ${isSelected
                ? 'border-apple-blue-500 bg-apple-blue-50 shadow-apple-md'
                : 'border-apple-gray-200 hover:border-apple-blue-300 hover:shadow-apple'
              }
              active:scale-95
            `}
          >
            {/* Header: Round, Venue, Live Badge */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1">
                <p className="text-sm font-medium text-apple-gray-700">
                  {game.round} • {game.venue}
                </p>
              </div>

              {/* LIVE Badge */}
              {isLive && (
                <div className="flex items-center gap-1.5 px-2 py-1 bg-apple-red/10 border border-apple-red/30 rounded-full">
                  <div className="w-1.5 h-1.5 bg-apple-red rounded-full animate-pulse"></div>
                  <span className="text-xs font-semibold text-apple-red uppercase">Live</span>
                </div>
              )}
            </div>

            {/* Teams and Scores */}
            <div className="space-y-2 mb-3">
              {/* Home Team */}
              <div className="flex items-center justify-between">
                <span className="text-lg font-semibold text-apple-gray-900">
                  {game.home_team.abbreviation}
                </span>
                <span className="text-2xl font-bold text-apple-gray-900">
                  {game.home_score}
                </span>
              </div>

              {/* Away Team */}
              <div className="flex items-center justify-between">
                <span className="text-lg font-semibold text-apple-gray-900">
                  {game.away_team.abbreviation}
                </span>
                <span className="text-2xl font-bold text-apple-gray-900">
                  {game.away_score}
                </span>
              </div>
            </div>

            {/* Time/Status */}
            <div className="text-sm text-apple-gray-500 font-medium">
              {game.status === 'live' && game.time_str
                ? game.time_str
                : game.status === 'completed'
                ? 'Final'
                : 'Scheduled'}
            </div>
          </button>
        );
      })}
    </div>
  );
};

export default GamePicker;
