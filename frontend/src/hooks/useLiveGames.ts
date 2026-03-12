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

export const useLiveGames = () => {
  const [games, setGames] = useState<LiveGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchGames = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/live-games`);
        if (!response.ok) throw new Error('Failed to fetch games');

        const data = await response.json();
        setGames(data.games || []);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchGames();

    // Poll every 30 seconds for game list updates
    const interval = setInterval(fetchGames, 30000);
    return () => clearInterval(interval);
  }, []);

  return { games, loading, error };
};
