import { useState, useEffect, useRef } from 'react';
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
  // Player info
  player_name?: string;
  player_api_sports_id?: number;
  // Milestone fields
  description?: string;
  is_milestone?: boolean;
  milestone_type?: string;
}

interface QuarterScores {
  home: (number | null)[];
  away: (number | null)[];
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
  ai_summary?: string | null;
  quarter_scores?: QuarterScores;
  quarter_summaries?: Record<string, string>;
}

export const useLiveGameDetail = (gameId: number) => {
  const [game, setGame] = useState<LiveGameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<Socket | null>(null);

  // Fetch game data (initial and periodic refresh for non-completed games)
  useEffect(() => {
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    const fetchGame = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/live-games/${gameId}`);
        if (!response.ok) throw new Error('Failed to fetch game');

        const data = await response.json();
        setGame(data);
        setError(null);

        // Stop polling if game is completed
        if (data.status === 'completed' && pollInterval) {
          clearInterval(pollInterval);
          pollInterval = null;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchGame();

    // Poll every 15 seconds - will be cleared if game is completed
    pollInterval = setInterval(fetchGame, 15000);

    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [gameId]);

  // WebSocket subscription for real-time updates (only for live games)
  useEffect(() => {
    // Only connect WebSocket if game is loaded AND is live (not completed/scheduled)
    const shouldConnect = game?.status === 'live';

    if (!shouldConnect) {
      // Close any existing connection
      if (socketRef.current) {
        socketRef.current.emit('unsubscribe_live_game', { game_id: gameId });
        socketRef.current.close();
        socketRef.current = null;
      }
      return;
    }

    // Avoid creating duplicate connections (StrictMode double-invoke)
    if (socketRef.current?.connected) {
      return;
    }

    const newSocket = io(BACKEND_URL);
    socketRef.current = newSocket;

    // Subscribe to this game's updates
    newSocket.emit('subscribe_live_game', { game_id: gameId });

    // Listen for live score updates
    newSocket.on('live_game_update', (data) => {
      if (data.game_id === gameId) {
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

    // Listen for new scoring events (goals/behinds/milestones)
    newSocket.on('live_game_event', (data) => {
      if (data.game_id === gameId) {
        // Add new event to the events list
        setGame((prev) => {
          if (!prev) return prev;

          // Create the new event from WebSocket data
          const newEvent: GameEvent = {
            id: Date.now(), // Temporary ID until we refetch
            event_type: data.event_type,
            team: {
              id: 0,
              name: data.team_name,
              abbreviation: data.team_abbreviation,
            },
            home_score_after: data.home_score,
            away_score_after: data.away_score,
            quarter: prev.current_quarter || 0,
            time_str: data.time_str,
            timestamp: data.timestamp,
            player_name: data.player_name,
            description: data.description,
            is_milestone: data.is_milestone,
            milestone_type: data.milestone_type,
          };

          return {
            ...prev,
            home_score: data.home_score,
            away_score: data.away_score,
            events: [newEvent, ...prev.events],
          };
        });
      }
    });

    // Listen for quarter summaries
    newSocket.on('quarter_summary', (data) => {
      if (data.game_id === gameId) {
        setGame((prev) => {
          if (!prev) return prev;
          const summaries = { ...(prev.quarter_summaries || {}) };
          summaries[String(data.quarter)] = data.summary;
          return { ...prev, quarter_summaries: summaries };
        });
      }
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.emit('unsubscribe_live_game', { game_id: gameId });
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [gameId, game?.status]);

  return { game, loading, error };
};
