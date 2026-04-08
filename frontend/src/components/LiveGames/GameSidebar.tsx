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
  preview?: string | null;
  prediction?: {
    winner: string;
    margin: number | null;
    home_prob: number | null;
    away_prob: number | null;
  } | null;
}

interface GameSidebarProps {
  games: LiveGame[];
  selectedGameId: number | null;
  onSelectGame: (gameId: number) => void;
  upcomingMatches?: UpcomingMatch[];
  selectedUpcomingId?: number | null;
  onSelectUpcoming?: (matchId: number) => void;
}

const GameSidebar: React.FC<GameSidebarProps> = ({ games, selectedGameId, onSelectGame, upcomingMatches = [], selectedUpcomingId, onSelectUpcoming }) => {
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
            ? 'bg-afl-accent-50 border-afl-accent shadow-apple'
            : isLive
              ? 'glass shadow-apple-sm hover:shadow-apple'
              : 'bg-afl-warm-50 opacity-80 hover:opacity-100 hover:bg-afl-warm-100'
          }
          ${!isLive && !isSelected ? 'border-l-4 border-l-transparent' : ''}
          active:scale-[0.98]
        `}
      >
        {/* Home team row */}
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-semibold text-afl-warm-900 truncate">
            {game.home_team.abbreviation}
          </span>
          <span className={`text-sm font-bold text-afl-warm-900 tabular-nums ${hideScores ? 'blur-sm select-none' : ''}`}>
            {displayScore(game.home_score)}
          </span>
        </div>

        {/* Away team row */}
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-sm font-semibold text-afl-warm-900 truncate">
            {game.away_team.abbreviation}
          </span>
          <span className={`text-sm font-bold text-afl-warm-900 tabular-nums ${hideScores ? 'blur-sm select-none' : ''}`}>
            {displayScore(game.away_score)}
          </span>
        </div>

        {/* Status */}
        <div className="flex items-center gap-1.5">
          {isLive && (
            <div className="w-1.5 h-1.5 bg-apple-red rounded-full animate-pulse" />
          )}
          <span className={`text-xs font-medium ${isLive ? 'text-apple-red' : 'text-afl-warm-400'}`}>
            {isLive ? (game.time_str || 'Live') : 'Final'}
          </span>
          {isLive && game.last_updated && (Date.now() - new Date(game.last_updated + 'Z').getTime() > 3 * 60 * 1000) && (
            <span className="text-[10px] text-amber-500 ml-auto">Delayed</span>
          )}
        </div>
      </button>
    );
  };

  // Games with previews — shown above results regardless of round
  const upcomingWithPreview = upcomingMatches.filter(m => !!m.preview);

  // Remaining upcoming without preview, grouped by round
  const upcomingNoPreview = upcomingMatches.filter(m => !m.preview);
  const firstUpcomingRound = upcomingNoPreview.length > 0 ? String(upcomingNoPreview[0].round) : null;
  const upcomingWithoutPreview = firstUpcomingRound
    ? upcomingNoPreview.filter(m => String(m.round) === firstUpcomingRound)
    : [];

  // Next round (the round after the first upcoming round)
  const nextRound = firstUpcomingRound
    ? upcomingNoPreview.find(m => String(m.round) !== firstUpcomingRound)?.round ?? null
    : (upcomingWithPreview.length > 0
      ? upcomingMatches.find(m => !m.preview && String(m.round) !== String(upcomingWithPreview[0].round))?.round ?? null
      : null);
  const nextRoundUpcoming = nextRound
    ? upcomingMatches.filter(m => String(m.round) === String(nextRound) && !m.preview)
    : [];

  const UpcomingList: React.FC<{ matches: UpcomingMatch[]; label: string }> = ({ matches, label }) => {
    if (matches.length === 0) return null;

    return (
      <div className="mt-4">
        <div className="mb-2 px-1">
          <span className="text-xs font-semibold text-afl-warm-400 uppercase tracking-wide">{label}</span>
        </div>
        <div className="space-y-2">
          {matches.map(match => {
            const { day, time } = formatMatchTime(match.date);
            const isSelected = selectedUpcomingId === match.id;
            const hasPreview = !!match.preview;
            return (
              <button
                key={match.id}
                onClick={() => onSelectUpcoming?.(match.id)}
                className={`
                  w-full text-left rounded-apple p-3 border-l-4 transition-all duration-200 ease-apple
                  ${isSelected
                    ? 'bg-afl-accent-50 border-l-afl-accent shadow-apple opacity-100'
                    : hasPreview
                      ? 'bg-afl-warm-50 border-l-afl-accent-300 opacity-90 hover:opacity-100 hover:bg-afl-warm-100'
                      : 'bg-afl-warm-50 border-l-afl-warm-200 opacity-70 hover:opacity-100 hover:bg-afl-warm-100'
                  }
                  active:scale-[0.98]
                `}
              >
                {/* Home team */}
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold text-afl-warm-700 truncate">
                    {match.home_team}
                  </span>
                </div>
                {/* Away team */}
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-semibold text-afl-warm-700 truncate">
                    {match.away_team}
                  </span>
                </div>
                {/* Time + preview badge */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-afl-warm-400">
                    {day} • {time}
                  </span>
                  {hasPreview && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-afl-accent-50 text-[10px] font-semibold text-afl-accent-600 leading-none">
                      Preview
                    </span>
                  )}
                </div>
                {/* Prediction */}
                {match.prediction && match.prediction.margin != null && (
                  <div className="mt-1.5 text-[11px] text-afl-warm-500">
                    Tipping {match.prediction.winner} by {Math.round(match.prediction.margin)}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  const MobileUpcomingTiles: React.FC<{ matches: UpcomingMatch[] }> = ({ matches }) => (
    <>
      {matches.map(match => {
        const { day, time } = formatMatchTime(match.date);
        const isSelected = selectedUpcomingId === match.id;
        const hasPreview = !!match.preview;
        return (
          <div key={match.id} className="w-36 flex-shrink-0">
            <button
              onClick={() => onSelectUpcoming?.(match.id)}
              className={`
                w-full text-left rounded-apple p-3 border-l-4 h-full transition-all duration-200 ease-apple
                ${isSelected
                  ? 'bg-afl-accent-50 border-l-afl-accent shadow-apple opacity-100'
                  : hasPreview
                    ? 'bg-afl-warm-50 border-l-afl-accent-300 opacity-90'
                    : 'bg-afl-warm-50 border-l-afl-warm-200 opacity-70'
                }
                active:scale-[0.98]
              `}
            >
              <div className="text-sm font-semibold text-afl-warm-700 truncate mb-1">
                {match.home_team}
              </div>
              <div className="text-sm font-semibold text-afl-warm-700 truncate mb-1.5">
                {match.away_team}
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-afl-warm-400">
                  {day} • {time}
                </span>
                {hasPreview && (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-afl-accent-50 text-[10px] font-semibold text-afl-accent-600 leading-none">
                    Preview
                  </span>
                )}
              </div>
              {match.prediction && match.prediction.margin != null && (
                <div className="mt-1.5 text-[11px] text-afl-warm-500 truncate">
                  Tipping {match.prediction.winner} by {Math.round(match.prediction.margin)}
                </div>
              )}
            </button>
          </div>
        );
      })}
    </>
  );

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

          {/* Upcoming with preview - shown above results */}
          {upcomingWithPreview.length > 0 && (
            <UpcomingList matches={upcomingWithPreview} label={`Round ${upcomingWithPreview[0].round} Preview`} />
          )}

          {/* Results this round */}
          {completedGames.length > 0 && (
            <div className={liveGames.length > 0 || upcomingWithPreview.length > 0 ? 'mt-4' : ''}>
              <div className="mb-2 px-1">
                <span className="text-xs font-semibold text-afl-warm-400 uppercase tracking-wide">Results</span>
              </div>
              <div className="space-y-2">
                {completedGames.map(game => (
                  <GameTile key={game.id} game={game} />
                ))}
              </div>
            </div>
          )}

          {/* Upcoming without preview */}
          {upcomingWithoutPreview.length > 0 && (
            <UpcomingList matches={upcomingWithoutPreview} label="Upcoming" />
          )}

          {/* Next round */}
          {nextRoundUpcoming.length > 0 && (
            <UpcomingList
              matches={nextRoundUpcoming}
              label={`Round ${nextRoundUpcoming[0].round}`}
            />
          )}
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
            {/* Then upcoming with preview */}
            <MobileUpcomingTiles matches={upcomingWithPreview} />
            {/* Then completed this round */}
            {completedGames.map(game => (
              <div key={game.id} className="w-36 flex-shrink-0">
                <GameTile game={game} />
              </div>
            ))}
            {/* Then upcoming without preview */}
            <MobileUpcomingTiles matches={upcomingWithoutPreview} />
            {/* Next round */}
            <MobileUpcomingTiles matches={nextRoundUpcoming} />
          </div>
        </div>
      </div>
    </>
  );
};

export default GameSidebar;
