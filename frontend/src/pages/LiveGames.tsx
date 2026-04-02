import { useState, useEffect } from 'react';
import { useLiveGames } from '../hooks/useLiveGames';
import { useUpcomingMatches } from '../hooks/useUpcomingMatches';
import { useSpoilerMode } from '../hooks/useSpoilerMode';
import GameSidebar from '../components/LiveGames/GameSidebar';
import LiveDashboard from '../components/LiveGames/LiveDashboard';
import ScoringPopup from '../components/LiveGames/ScoringPopup';
import Countdown from '../components/LiveGames/Countdown';

const LiveGames = () => {
  const { games, loading, error } = useLiveGames();
  const { matches: upcomingMatches, nextMatch } = useUpcomingMatches();
  // Subscribe to spoiler mode to ensure re-renders when it changes
  useSpoilerMode();
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null);
  const [selectedUpcomingId, setSelectedUpcomingId] = useState<number | null>(null);

  // When selecting an upcoming match, deselect live/completed and vice versa
  const handleSelectGame = (gameId: number) => {
    setSelectedGameId(gameId);
    setSelectedUpcomingId(null);
  };

  const handleSelectUpcoming = (matchId: number) => {
    setSelectedUpcomingId(matchId);
    setSelectedGameId(null);
  };

  const selectedUpcoming = upcomingMatches.find(m => m.id === selectedUpcomingId) || null;

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
    if (games.length > 0 && selectedGameId === null && selectedUpcomingId === null) {
      // Prioritize live games
      const liveGame = games.find(g => g.status === 'live');
      const gameToSelect = liveGame || games[0];
      setSelectedGameId(gameToSelect.id);
    }
  }, [games, selectedGameId, selectedUpcomingId]);

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
  const hasCompletedGames = games.some(g => g.status === 'completed');

  // Show upcoming schedule only when there are no games at all
  // When there are completed games, show them (even without live games)
  if (games.length === 0 || (!hasLiveGames && !hasCompletedGames)) {
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

              {nextMatch.prediction && nextMatch.prediction.margin != null && (
                <div className="text-center mb-4">
                  <span className="inline-flex items-center gap-2 px-4 py-2 bg-apple-blue-50 rounded-full text-sm font-medium text-apple-blue-700">
                    Tipping {nextMatch.prediction.winner} by {Math.round(nextMatch.prediction.margin)} points
                    {nextMatch.prediction.home_prob != null && nextMatch.prediction.away_prob != null && (
                      <span className="text-apple-blue-500">
                        ({nextMatch.prediction.home_prob}% - {nextMatch.prediction.away_prob}%)
                      </span>
                    )}
                  </span>
                </div>
              )}

              {nextMatch.preview && (
                <p className="text-apple-gray-600 text-center mt-2 px-4 leading-relaxed">
                  {nextMatch.preview}
                </p>
              )}

              <div className="border-t border-apple-gray-200 pt-6 mt-4">
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

          {/* Upcoming schedule — current round + next round only */}
          {upcomingMatches.length > 1 && (() => {
            const currentRound = upcomingMatches[0]?.round;
            const nextRound = upcomingMatches.find(m => String(m.round) !== String(currentRound))?.round;
            const relevantMatches = upcomingMatches.slice(1).filter(m =>
              String(m.round) === String(currentRound) || (nextRound && String(m.round) === String(nextRound))
            );
            if (relevantMatches.length === 0) return null;
            return (
            <div className="card-apple p-6">
              <h3 className="text-xl font-semibold text-apple-gray-900 mb-4">
                Upcoming Schedule
              </h3>
              <div className="space-y-3">
                {relevantMatches.map((match) => (
                  <div
                    key={match.id}
                    className="p-4 bg-apple-gray-50 rounded-apple hover:bg-apple-gray-100 transition-colors"
                  >
                    <div className="flex items-center justify-between">
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
                    {match.preview && (
                      <p className="text-sm text-apple-gray-600 italic mt-2 leading-relaxed">
                        {match.preview}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
            );
          })()}
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader />

      {/* Main content - Sidebar + Dashboard layout */}
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pb-8">
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar */}
          <div className="lg:w-72 xl:w-80 flex-shrink-0">
            <GameSidebar
              games={games}
              selectedGameId={selectedGameId}
              onSelectGame={handleSelectGame}
              upcomingMatches={upcomingMatches}
              selectedUpcomingId={selectedUpcomingId}
              onSelectUpcoming={handleSelectUpcoming}
            />
          </div>

          {/* Main Dashboard */}
          <div className="flex-1 min-w-0">
            {selectedGameId && <LiveDashboard gameId={selectedGameId} />}
            {selectedUpcoming && (
              <div className="space-y-6">
                {/* Match header */}
                <div className="glass rounded-apple-xl p-8 shadow-apple-lg">
                  <div className="text-center mb-6">
                    <p className="text-sm font-medium text-apple-gray-500 uppercase tracking-wide">
                      Round {selectedUpcoming.round} • {selectedUpcoming.venue}
                    </p>
                  </div>
                  <div className="text-center mb-6">
                    <p className="text-2xl font-semibold text-apple-gray-900">
                      {selectedUpcoming.home_team} vs {selectedUpcoming.away_team}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-lg font-medium text-apple-gray-700">
                      {new Date(selectedUpcoming.date).toLocaleString('en-AU', {
                        weekday: 'long',
                        day: 'numeric',
                        month: 'long',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                    <Countdown targetDate={selectedUpcoming.date} />
                  </div>
                </div>

                {/* Prediction */}
                {selectedUpcoming.prediction && selectedUpcoming.prediction.margin != null && (
                  <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-apple-gray-900">
                          Match Prediction
                        </h3>
                        <p className="text-apple-gray-700 mt-1">
                          {selectedUpcoming.prediction.winner} by {Math.round(selectedUpcoming.prediction.margin)} points
                        </p>
                      </div>
                      {selectedUpcoming.prediction.home_prob != null && selectedUpcoming.prediction.away_prob != null && (
                        <div className="text-right text-sm text-apple-gray-500">
                          <div>{selectedUpcoming.home_team}: {selectedUpcoming.prediction.home_prob}%</div>
                          <div>{selectedUpcoming.away_team}: {selectedUpcoming.prediction.away_prob}%</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Preview */}
                {selectedUpcoming.preview ? (
                  <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
                    <h3 className="text-xl font-semibold text-apple-gray-900 mb-3">
                      Match Preview
                    </h3>
                    <p className="text-apple-gray-700 leading-relaxed">
                      {selectedUpcoming.preview}
                    </p>
                  </div>
                ) : (
                  <div className="glass rounded-apple-xl p-6 shadow-apple-lg text-center">
                    <p className="text-apple-gray-500">
                      Match preview will be available closer to game time
                    </p>
                  </div>
                )}
              </div>
            )}
            {!selectedGameId && !selectedUpcoming && (
              <div className="card-apple p-8 text-center">
                <p className="text-apple-gray-500">Select a game to view details</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Scoring Popup Notifications - only when live games exist */}
      <ScoringPopup enabled={hasLiveGames} />
    </div>
  );
};

export default LiveGames;
