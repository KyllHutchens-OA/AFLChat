import { useState, useEffect } from 'react';
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

  // Page header with live badge
  const PageHeader = () => (
    <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pt-8 pb-4">
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
    </div>
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

  // Auto-switch to next live game when current game completes (only if live games exist)
  useEffect(() => {
    if (!selectedGameId || games.length === 0) return;

    const selectedGame = games.find(g => g.id === selectedGameId);
    if (!selectedGame) return;

    // Only auto-switch if there are other live games to watch
    // Don't deselect when all games are completed (let user browse finals)
    const hasOtherLiveGames = games.some(g => g.status === 'live' && g.id !== selectedGameId);

    if (selectedGame.status === 'completed' && hasOtherLiveGames) {
      const timeout = setTimeout(() => {
        const nextLiveGame = games.find(g => g.status === 'live' && g.id !== selectedGameId);
        if (nextLiveGame) {
          setSelectedGameId(nextLiveGame.id);
        }
      }, 15000); // 15 second delay to view final score

      return () => clearTimeout(timeout);
    }
  }, [games, selectedGameId]);

  if (loading) {
    return (
      <div>
        <PageHeader />

        {/* Loading shimmer */}
        <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pb-8">
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
      <div>
        <PageHeader />

        {/* Error state */}
        <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pb-8">
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

  // Check if there are any live (non-completed) games
  const hasLiveGames = games.some(g => g.status === 'live');

  // Show upcoming schedule when no games or no live games and nothing selected
  if (games.length === 0 || (!hasLiveGames && selectedGameId === null)) {
    return (
      <div>
        <PageHeader />

        {/* Empty state with schedule */}
        <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pb-8 space-y-6">
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

              <div className="text-center mt-4 space-y-1">
                <div className="text-sm font-medium text-apple-gray-700">
                  {new Date(nextMatch.date).toLocaleString('en-AU', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </div>
                <div className="text-xs text-apple-gray-500">
                  {new Date(nextMatch.date).toLocaleString('en-AU', {
                    timeZoneName: 'long',
                  }).split(', ').pop()}
                </div>
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
                        })} AEDT
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
    <div>
      <PageHeader />

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pb-8 space-y-6">
        {/* Game Picker */}
        <GamePicker
          games={games}
          selectedGameId={selectedGameId}
          onSelectGame={setSelectedGameId}
        />

        {/* Live Dashboard */}
        {selectedGameId && <LiveDashboard gameId={selectedGameId} />}
      </div>

      {/* Scoring Popup Notifications - only when live games exist */}
      <ScoringPopup enabled={hasLiveGames} />
    </div>
  );
};

export default LiveGames;
