import { useState, useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

interface ScoringEvent {
  game_id: number;
  event_type: 'goal' | 'behind';
  team_id: number;
  team_name: string;
  team_abbreviation: string;
  home_score: number;
  away_score: number;
  quarter: number;
  time_str: string;
  timestamp: string;
  // Player info (from API-Sports)
  player_name?: string;
  player_id?: number;
  jersey_number?: number;
  player_total_goals?: number;
}

export const useLiveGameEvents = (enabled: boolean = true) => {
  const [latestEvent, setLatestEvent] = useState<ScoringEvent | null>(null);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    // Don't connect if disabled (no live games)
    if (!enabled) {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      return;
    }

    // Avoid creating duplicate connections (StrictMode double-invoke)
    if (socketRef.current?.connected) {
      return;
    }

    // Create global socket connection
    const newSocket = io(BACKEND_URL);
    socketRef.current = newSocket;

    // Listen for all live game events (not room-specific)
    newSocket.on('live_game_event', (data: ScoringEvent) => {
      setLatestEvent(data);
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [enabled]);

  return { latestEvent, socket: socketRef.current };
};
