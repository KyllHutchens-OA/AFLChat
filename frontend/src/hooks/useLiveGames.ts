import { useState, useEffect } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

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
  status: string; // 'scheduled', 'live', 'completed'
  complete_percent: number;
  time_str: string;
  current_quarter: number | null;
  venue: string;
  match_date: string;
  last_updated: string;
}

// Polling intervals
const LIVE_POLL_INTERVAL = 15000;    // 15 seconds when live games
const IDLE_POLL_INTERVAL = 300000;   // 5 minutes when no live games

export const useLiveGames = () => {
  const [games, setGames] = useState<LiveGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;
    let currentInterval = LIVE_POLL_INTERVAL;
    let isFirstFetch = true;

    const fetchGames = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/live-games`);
        if (!response.ok) throw new Error('Failed to fetch games');

        const data = await response.json();
        const fetchedGames = data.games || [];
        setGames(fetchedGames);
        setError(null);

        // Adjust polling based on game states
        const hasLiveGames = fetchedGames.some((g: LiveGame) => g.status === 'live');
        const hasScheduledGames = fetchedGames.some((g: LiveGame) => g.status === 'scheduled');

        // If all games are completed, stop polling entirely
        if (!hasLiveGames && !hasScheduledGames && fetchedGames.length > 0) {
          if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
          }
          return;
        }

        // Determine appropriate interval
        const newInterval = hasLiveGames ? LIVE_POLL_INTERVAL : IDLE_POLL_INTERVAL;

        // Start or adjust polling interval
        if (isFirstFetch) {
          // Start polling after first fetch (now we know the game states)
          isFirstFetch = false;
          currentInterval = newInterval;
          intervalId = setInterval(fetchGames, currentInterval);
        } else if (newInterval !== currentInterval) {
          // Adjust interval if it changed
          currentInterval = newInterval;
          if (intervalId) {
            clearInterval(intervalId);
          }
          intervalId = setInterval(fetchGames, currentInterval);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    // Initial fetch only - polling starts after first fetch completes
    fetchGames();

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, []);

  return { games, loading, error };
};
