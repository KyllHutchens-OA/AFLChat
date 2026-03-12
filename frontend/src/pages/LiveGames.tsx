import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useLiveGames } from '../hooks/useLiveGames';
import { useUpcomingMatches } from '../hooks/useUpcomingMatches';
import GamePicker from '../components/LiveGames/GamePicker';
import LiveDashboard from '../components/LiveGames/LiveDashboard';
import ScoringPopup from '../components/LiveGames/ScoringPopup';
import Countdown from '../components/LiveGames/Countdown';

const LiveGames = () => {
  const { games, loading, error } = useLiveGames();
  const { matches: upcomingMatches, nextMatch } = useUpcomingMatches();
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null);

  // Count of live games for badge
  const liveCount = games.filter(g => g.status === 'live').length;

  // Reusable header component
  const Header = () => (
    <header className="glass border-b border-apple-gray-200/50 sticky top-0 z-20">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-3xl font-semibold text-apple-gray-900">Live Games</h1>
          {liveCount > 0 && (
            <div className="flex items-center gap-2 px-4 py-2 bg-apple-red/10 border border-apple-red/30 rounded-full">
              <div className="w-2 h-2 bg-apple-red rounded-full animate-pulse"></div>
              <span className="text-sm font-medium text-apple-red">
                {liveCount} {liveCount === 1 ? 'Game' : 'Games'} Live
              </span>
            </div>
          )}
        </div>
        <Link
          to="/aflagent"
          className="px-4 py-2 bg-apple-gray-100 text-apple-gray-700 rounded-apple hover:bg-apple-gray-200 transition-colors flex items-center gap-2 text-sm font-medium"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          Chat
        </Link>
      </div>
    </header>
  );

  // Auto-select first live game, or first available game
  useEffect(() => {
    if (games.length > 0 && selectedGameId === null) {
      // Prioritize live games
      const liveGame = games.find(g => g.status === 'live');
      const gameToSelect = liveGame || games[0];
      setSelectedGameId(gameToSelect.id);
    }
  }, [games, selectedGameId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-apple-gray-50">
        <Header />

        {/* Loading shimmer */}
        <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-8">
          <div className="animate-shimmer">
            <div className="h-32 bg-apple-gray-200 rounded-apple mb-6"></div>
            <div className="h-96 bg-apple-gray-200 rounded-apple"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-apple-gray-50">
        <Header />

        {/* Error state */}
        <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-8">
          <div className="card-apple p-8 text-center">
            <div className="text-6xl mb-4">⚠️</div>
            <h2 className="text-2xl font-semibold text-apple-gray-900 mb-2">
              Unable to Load Games
            </h2>
            <p className="text-apple-gray-500">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (games.length === 0) {
    return (
      <div className="min-h-screen bg-apple-gray-50">
        <Header />

        {/* Empty state with schedule */}
        <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-8 space-y-6">
          {/* No live games message */}
          <div className="card-apple p-8 text-center">
            <h2 className="text-3xl font-semibold text-apple-gray-900 mb-2">
              No Live Games
            </h2>
            <p className="text-lg text-apple-gray-500">
              Check back when games are in progress
            </p>
          </div>

          {/* Next game countdown */}
          {nextMatch && (
            <div className="card-apple p-8">
              <div className="text-center mb-6">
                <h3 className="text-xl font-semibold text-apple-gray-900 mb-2">
                  Next Game
                </h3>
                <p className="text-apple-gray-600">
                  Round {nextMatch.round} • {nextMatch.venue}
                </p>
                <p className="text-2xl font-semibold text-apple-gray-900 mt-3">
                  {nextMatch.home_team} vs {nextMatch.away_team}
                </p>
              </div>

              <div className="border-t border-apple-gray-200 pt-6">
                <Countdown targetDate={nextMatch.date} />
              </div>

              <div className="text-center mt-4 text-sm text-apple-gray-500">
                {new Date(nextMatch.date).toLocaleString('en-AU', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                  timeZoneName: 'short',
                })}
              </div>
            </div>
          )}

          {/* Upcoming schedule */}
          {upcomingMatches.length > 1 && (
            <div className="card-apple p-6">
              <h3 className="text-xl font-semibold text-apple-gray-900 mb-4">
                Upcoming Schedule
              </h3>
              <div className="space-y-3">
                {upcomingMatches.slice(1, 6).map((match) => (
                  <div
                    key={match.id}
                    className="flex items-center justify-between p-4 bg-apple-gray-50 rounded-apple hover:bg-apple-gray-100 transition-colors"
                  >
                    <div className="flex-1">
                      <div className="font-medium text-apple-gray-900">
                        {match.home_team} vs {match.away_team}
                      </div>
                      <div className="text-sm text-apple-gray-500 mt-1">
                        Round {match.round} • {match.venue}
                      </div>
                    </div>
                    <div className="text-right ml-4">
                      <div className="text-sm font-medium text-apple-gray-700">
                        {new Date(match.date).toLocaleDateString('en-AU', {
                          weekday: 'short',
                          month: 'short',
                          day: 'numeric',
                        })}
                      </div>
                      <div className="text-sm text-apple-gray-500">
                        {new Date(match.date).toLocaleTimeString('en-AU', {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-apple-gray-50">
      <Header />

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-8 space-y-6">
        {/* Game Picker */}
        <GamePicker
          games={games}
          selectedGameId={selectedGameId}
          onSelectGame={setSelectedGameId}
        />

        {/* Live Dashboard */}
        {selectedGameId && <LiveDashboard gameId={selectedGameId} />}
      </div>

      {/* Scoring Popup Notifications */}
      <ScoringPopup />
    </div>
  );
};

export default LiveGames;
