import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';

interface LiveGame {
  id: number;
  home_team: { name: string; abbreviation: string };
  away_team: { name: string; abbreviation: string };
  home_score: number;
  away_score: number;
  status: string;
  time_str: string | null;
  round: string;
}

const LiveScoreWidget = () => {
  const { hideScores } = useSpoilerMode();
  const [liveGame, setLiveGame] = useState<LiveGame | null>(null);
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const fetchLiveGames = async () => {
      try {
        const response = await fetch('/api/live-games');
        if (!response.ok) return;

        const data = await response.json();
        const games = data.games || [];

        // Find first live game
        const live = games.find((g: LiveGame) => g.status === 'live');
        setLiveGame(live || null);
      } catch (err) {
        console.error('Error fetching live games:', err);
      }
    };

    // Initial fetch
    fetchLiveGames();

    // Poll every 30 seconds
    const interval = setInterval(fetchLiveGames, 30000);

    return () => clearInterval(interval);
  }, []);

  // Hide widget when spoiler mode is on
  if (!liveGame || !isVisible || hideScores) {
    return null;
  }

  return (
    <Link
      to="/live"
      className="fixed bottom-6 right-6 z-50 glass rounded-md shadow-card-lg border border-warm-200 hover:shadow-card-xl transition-all duration-300 hover:scale-105 group"
    >
      <div className="px-4 py-3 min-w-[280px]">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-sherrin rounded-full animate-pulse"></div>
            <span className="text-xs font-medium text-warm-700">
              LIVE • Round {liveGame.round}
            </span>
          </div>
          <button
            onClick={(e) => {
              e.preventDefault();
              setIsVisible(false);
            }}
            aria-label="Dismiss live score widget"
            className="text-warm-600 hover:text-warm-700 transition-colors
                       focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sherrin"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Score */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-warm-900">
              {liveGame.home_team.abbreviation}
            </span>
            <span className="text-lg font-semibold text-warm-900 tabular-nums">
              {liveGame.home_score}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-warm-900">
              {liveGame.away_team.abbreviation}
            </span>
            <span className="text-lg font-semibold text-warm-900 tabular-nums">
              {liveGame.away_score}
            </span>
          </div>
        </div>

        {/* Time */}
        {liveGame.time_str && (
          <div className="mt-2 pt-2 border-t border-warm-200">
            <span className="text-xs text-warm-600">{liveGame.time_str}</span>
          </div>
        )}

        {/* Hover hint */}
        <div className="mt-2 text-xs text-warm-600 opacity-0 group-hover:opacity-100 transition-opacity">
          Click to view full details →
        </div>
      </div>
    </Link>
  );
};

export default LiveScoreWidget;
