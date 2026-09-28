import React from 'react';
import type { Premiers, UpcomingMatch } from '../../contexts/LiveDataContext';
import Countdown from './Countdown';

interface OffSeasonProps {
  premiers: Premiers | null;
  premiersLoading: boolean;
  nextSeasonMatch: UpcomingMatch | null;
  hideScores: boolean;
  onRelive: () => void;
}

// Shown on /live once the season is done and the next one hasn't started -
// a premiers banner, a way back into the Grand Final, and a countdown.
const OffSeason: React.FC<OffSeasonProps> = ({ premiers, premiersLoading, nextSeasonMatch, hideScores, onRelive }) => {
  const nextSeason = premiers ? premiers.season + 1 : null;

  return (
    <div className="space-y-6">
      {/* Premiers banner */}
      <div className="glass rounded-xl p-8 shadow-card-lg text-center">
        {premiersLoading ? (
          <div className="animate-shimmer h-20 bg-warm-200 rounded-md" />
        ) : hideScores ? (
          <>
            <p className="text-sm font-medium text-warm-600 uppercase tracking-wide mb-2">Season done and dusted</p>
            <p className="text-lg text-warm-700">Spoiler mode is on - turn it off to see the premiers.</p>
          </>
        ) : premiers ? (
          <>
            <p className="text-sm font-medium text-warm-600 uppercase tracking-wide mb-2">
              {premiers.season} Premiers
            </p>
            <h2 className="text-3xl font-semibold text-warm-900 mb-3">
              {premiers.winner.name}
            </h2>
            {(() => {
              const homeWon = premiers.home_score >= premiers.away_score;
              const first = homeWon ? premiers.home_team : premiers.away_team;
              const firstGoals = homeWon ? premiers.home_goals : premiers.away_goals;
              const firstBehinds = homeWon ? premiers.home_behinds : premiers.away_behinds;
              const firstScore = homeWon ? premiers.home_score : premiers.away_score;
              const second = homeWon ? premiers.away_team : premiers.home_team;
              const secondGoals = homeWon ? premiers.away_goals : premiers.home_goals;
              const secondBehinds = homeWon ? premiers.away_behinds : premiers.home_behinds;
              const secondScore = homeWon ? premiers.away_score : premiers.home_score;
              return (
                <p className="text-warm-700 tabular-nums">
                  {first.abbreviation} {firstGoals != null ? `${firstGoals}.${firstBehinds}` : ''} ({firstScore})
                  {' d. '}
                  {second.abbreviation} {secondGoals != null ? `${secondGoals}.${secondBehinds}` : ''} ({secondScore})
                </p>
              );
            })()}
          </>
        ) : (
          <>
            <p className="text-3xl font-semibold text-warm-900 mb-2">Season's over</p>
            <p className="text-warm-600">No games on right now</p>
          </>
        )}
      </div>

      {/* Relive the Grand Final */}
      {premiers && premiers.live_game_id != null && (
        <button
          onClick={onRelive}
          className="w-full glass rounded-xl p-6 shadow-card-lg text-left hover:shadow-card-lg transition-shadow active:scale-[0.99]"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-warm-900">Relive the Grand Final</h3>
              <p className="text-sm text-warm-600 mt-1">
                Quarter-by-quarter scores, the scoring worm, stats and the wrap.
              </p>
            </div>
            <span className="text-sherrin text-2xl">&rarr;</span>
          </div>
        </button>
      )}

      {/* Countdown to next season */}
      <div className="glass rounded-xl p-8 shadow-card-lg text-center">
        <h3 className="text-xl font-semibold text-warm-900 mb-4">
          {nextSeasonMatch ? `Season ${nextSeasonMatch.season ?? nextSeason} kicks off` : 'Next season'}
        </h3>
        {nextSeasonMatch ? (
          <>
            <p className="text-warm-700 mb-4">
              {nextSeasonMatch.home_team} vs {nextSeasonMatch.away_team} &middot; {nextSeasonMatch.venue}
            </p>
            <Countdown targetDate={nextSeasonMatch.date} />
          </>
        ) : (
          <p className="text-lg text-warm-600">
            Season {nextSeason ?? new Date().getFullYear() + 1} fixture coming soon
          </p>
        )}
      </div>
    </div>
  );
};

export default OffSeason;
