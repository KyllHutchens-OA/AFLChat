import { useState, useEffect } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

interface UpcomingMatch {
  id: number;
  round: string | number;
  home_team: string;
  away_team: string;
  venue: string;
  date: string;
  complete: number;
  is_final: boolean;
  preview?: string | null;
  prediction?: {
    winner: string;
    margin: number | null;
    home_prob: number | null;
    away_prob: number | null;
  } | null;
}

interface UseUpcomingMatchesResult {
  matches: UpcomingMatch[];
  loading: boolean;
  error: string | null;
  nextMatch: UpcomingMatch | null;
}

export const useUpcomingMatches = (): UseUpcomingMatchesResult => {
  const [matches, setMatches] = useState<UpcomingMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchUpcoming = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/upcoming-matches`);

        if (!response.ok) {
          throw new Error('Failed to fetch upcoming matches');
        }

        const data = await response.json();
        setMatches(data.matches || []);
        setError(null);
      } catch (err) {
        console.error('Error fetching upcoming matches:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchUpcoming();

    // Refresh every 5 minutes
    const interval = setInterval(fetchUpcoming, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  const nextMatch = matches.length > 0 ? matches[0] : null;

  return { matches, loading, error, nextMatch };
};
