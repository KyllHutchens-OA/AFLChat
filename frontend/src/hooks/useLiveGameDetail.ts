import { useState, useEffect } from 'react';
import { io, Socket } from 'socket.io-client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

interface GameEvent {
  id: number;
  event_type: string;
  team: {
    id: number;
    name: string;
    abbreviation: string;
  } | null;
  home_score_after: number;
  away_score_after: number;
  quarter: number;
  time_str: string;
  timestamp: string;
}

interface LiveGameDetail {
  id: number;
  squiggle_id: number;
  season: number;
  round: string;
  home_team: {
    id: number;
    name: string;
    abbreviation: string;
    primary_color: string;
    secondary_color: string;
  };
  away_team: {
    id: number;
    name: string;
    abbreviation: string;
    primary_color: string;
    secondary_color: string;
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
  events: GameEvent[];
}

export const useLiveGameDetail = (gameId: number) => {
  const [game, setGame] = useState<LiveGameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [socket, setSocket] = useState<Socket | null>(null);

  // Fetch initial game data
  useEffect(() => {
    const fetchGame = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/live-games/${gameId}`);
        if (!response.ok) throw new Error('Failed to fetch game');

        const data = await response.json();
        setGame(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchGame();
  }, [gameId]);

  // WebSocket subscription for real-time updates
  useEffect(() => {
    const newSocket = io(BACKEND_URL);
    setSocket(newSocket);

    // Subscribe to this game's updates
    newSocket.emit('subscribe_live_game', { game_id: gameId });

    newSocket.on('subscribed', (data) => {
      console.log('Subscribed to live game:', data.game_id);
    });

    // Listen for live updates
    newSocket.on('live_game_update', (data) => {
      if (data.game_id === gameId) {
        console.log('Live game update:', data);
        // Update game state
        setGame((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            home_score: data.home_score,
            away_score: data.away_score,
            status: data.status,
            complete_percent: data.complete_percent,
            time_str: data.time_str,
            current_quarter: data.current_quarter,
          };
        });
      }
    });

    return () => {
      newSocket.emit('unsubscribe_live_game', { game_id: gameId });
      newSocket.close();
    };
  }, [gameId]);

  return { game, loading, error };
};
