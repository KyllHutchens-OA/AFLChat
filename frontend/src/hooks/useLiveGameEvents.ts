import { useState, useEffect } from 'react';
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
}

export const useLiveGameEvents = () => {
  const [latestEvent, setLatestEvent] = useState<ScoringEvent | null>(null);
  const [socket, setSocket] = useState<Socket | null>(null);

  useEffect(() => {
    // Create global socket connection
    const newSocket = io(BACKEND_URL);
    setSocket(newSocket);

    console.log('Global event listener connected');

    // Listen for all live game events (not room-specific)
    // These are broadcast by the backend when scoring events occur
    newSocket.on('live_game_event', (data: ScoringEvent) => {
      console.log('Received scoring event:', data);
      setLatestEvent(data);
    });

    newSocket.on('connect_error', (error) => {
      console.error('Socket connection error:', error);
    });

    return () => {
      newSocket.close();
    };
  }, []);

  return { latestEvent, socket };
};
