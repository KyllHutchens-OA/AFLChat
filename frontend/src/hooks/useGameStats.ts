import { useState, useEffect } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

interface PlayerStat {
  name: string;
  team: string;
  goals?: number;
  disposals?: number;
  points?: number;
}

interface GameStats {
  top_goal_kickers: PlayerStat[];
  top_disposals: PlayerStat[];
  top_fantasy: PlayerStat[];
}

export const useGameStats = (gameId: number | null, gameStatus?: string) => {
  const [stats, setStats] = useState<GameStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!gameId) {
      setStats(null);
      return;
    }

    let pollInterval: ReturnType<typeof setInterval> | null = null;

    let isInitialFetch = true;

    const fetchStats = async () => {
      if (isInitialFetch) setLoading(true);
      try {
        const response = await fetch(`${BACKEND_URL}/api/live-games/${gameId}/stats`);
        if (!response.ok) {
          throw new Error('Failed to fetch game stats');
        }
        const data = await response.json();
        setStats(data);
        setError(null);
      } catch (err) {
        // Only clear stats on initial fetch failure — keep stale data on refetch errors
        if (isInitialFetch) {
          setError(err instanceof Error ? err.message : 'Unknown error');
          setStats(null);
        }
      } finally {
        if (isInitialFetch) setLoading(false);
        isInitialFetch = false;
      }
    };

    fetchStats();

    // Poll every 30 seconds for live games
    if (gameStatus === 'live') {
      pollInterval = setInterval(fetchStats, 30000);
    }

    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [gameId, gameStatus]);

  return { stats, loading, error };
};
