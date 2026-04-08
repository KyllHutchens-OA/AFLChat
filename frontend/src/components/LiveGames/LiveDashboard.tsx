import React, { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { useLiveData } from '../../contexts/LiveDataContext';
import type { GameEvent } from '../../contexts/LiveDataContext';
import { useSpoilerMode } from '../../hooks/useSpoilerMode';
import ProgressBar from './ProgressBar';
import GameStats from './GameStats';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

interface LiveDashboardProps {
  gameId: number;
}

const LiveDashboard: React.FC<LiveDashboardProps> = ({ gameId }) => {
  const { getGameDetail, setGameDetail, gameDetailLoading, fetchGameDetail } = useLiveData();
  const { hideScores } = useSpoilerMode();
  const socketRef = useRef<Socket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const delayedRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const game = getGameDetail(gameId);
  const loading = gameDetailLoading(gameId) && !game;

  // Fetch game detail on mount / gameId change
  useEffect(() => {
    fetchGameDetail(gameId);

    // Poll every 15s for non-completed games, stop for completed
    pollRef.current = setInterval(() => {
      const cached = getGameDetail(gameId);
      if (cached?.status === 'completed') {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }

        // Schedule delayed re-fetch for post-game analysis
        if (!cached.post_game_analysis && !delayedRef.current) {
          delayedRef.current = setTimeout(() => fetchGameDetail(gameId), 3 * 60 * 1000);
        }
        return;
      }
      fetchGameDetail(gameId);
    }, 15000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (delayedRef.current) clearTimeout(delayedRef.current);
    };
  }, [gameId]); // eslint-disable-line react-hooks/exhaustive-deps

  // WebSocket subscription for real-time updates (only for live games)
  useEffect(() => {
    const shouldConnect = game?.status === 'live';

    if (!shouldConnect) {
      if (socketRef.current) {
        socketRef.current.emit('unsubscribe_live_game', { game_id: gameId });
        socketRef.current.close();
        socketRef.current = null;
      }
      return;
    }

    if (socketRef.current?.connected) return;

    const newSocket = io(BACKEND_URL);
    socketRef.current = newSocket;

    newSocket.emit('subscribe_live_game', { game_id: gameId });

    newSocket.on('live_game_update', (data) => {
      if (data.game_id === gameId) {
        const cached = getGameDetail(gameId);
        if (cached) {
          setGameDetail(gameId, {
            ...cached,
            home_score: data.home_score,
            away_score: data.away_score,
            status: data.status,
            complete_percent: data.complete_percent,
            time_str: data.time_str,
            current_quarter: data.current_quarter,
          });
        }
      }
    });

    newSocket.on('live_game_event', (data) => {
      if (data.game_id === gameId) {
        const cached = getGameDetail(gameId);
        if (cached) {
          const newEvent: GameEvent = {
            id: Date.now(),
            event_type: data.event_type,
            team: { id: 0, name: data.team_name, abbreviation: data.team_abbreviation },
            home_score_after: data.home_score,
            away_score_after: data.away_score,
            quarter: cached.current_quarter || 0,
            time_str: data.time_str,
            timestamp: data.timestamp,
            player_name: data.player_name,
            description: data.description,
            is_milestone: data.is_milestone,
            milestone_type: data.milestone_type,
          };
          setGameDetail(gameId, {
            ...cached,
            home_score: data.home_score,
            away_score: data.away_score,
            events: [newEvent, ...cached.events],
          });
        }
      }
    });

    newSocket.on('quarter_summary', (data) => {
      if (data.game_id === gameId) {
        const cached = getGameDetail(gameId);
        if (cached) {
          const summaries = { ...(cached.quarter_summaries || {}) };
          summaries[String(data.quarter)] = data.summary;
          setGameDetail(gameId, { ...cached, quarter_summaries: summaries });
        }
      }
    });

    newSocket.on('post_game_analysis', (data) => {
      if (data.game_id === gameId) {
        const cached = getGameDetail(gameId);
        if (cached) {
          setGameDetail(gameId, { ...cached, post_game_analysis: data.analysis });
        }
      }
    });

    return () => {
      if (socketRef.current) {
        socketRef.current.emit('unsubscribe_live_game', { game_id: gameId });
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [gameId, game?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Helper to display scores based on spoiler mode
  const displayScore = (score: number) => hideScores ? '?' : score;
  const displayBreakdown = (goals: number, behinds: number) => hideScores ? '?.?' : `${goals}.${behinds}`;

  if (loading) {
    return (
      <div className="card-apple p-8 animate-shimmer">
        <div className="h-64 bg-afl-warm-200 rounded-apple"></div>
      </div>
    );
  }

  if (!game) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Scoreboard */}
      <div className="glass rounded-apple-xl p-8 shadow-apple-lg">
        {/* Round and Venue */}
        <div className="text-center mb-6">
          <p className="text-sm font-medium text-afl-warm-500 uppercase tracking-wide">
            Round {game.round} • {game.venue}
          </p>
        </div>

        {/* Teams and Scores */}
        <div className="grid grid-cols-2 gap-8 mb-6">
          {/* Home Team */}
          <div className="text-center">
            <h2 className="text-2xl font-semibold text-afl-warm-900 mb-2">
              {game.home_team.name}
            </h2>
            <p className={`text-6xl font-bold text-afl-warm-900 mb-1 ${hideScores ? 'blur-md select-none' : ''}`}>
              {displayScore(game.home_score)}
            </p>
            <p className={`text-sm text-afl-warm-500 ${hideScores ? 'blur-sm select-none' : ''}`}>
              {displayBreakdown(game.home_goals, game.home_behinds)}
            </p>
          </div>

          {/* Away Team */}
          <div className="text-center">
            <h2 className="text-2xl font-semibold text-afl-warm-900 mb-2">
              {game.away_team.name}
            </h2>
            <p className={`text-6xl font-bold text-afl-warm-900 mb-1 ${hideScores ? 'blur-md select-none' : ''}`}>
              {displayScore(game.away_score)}
            </p>
            <p className={`text-sm text-afl-warm-500 ${hideScores ? 'blur-sm select-none' : ''}`}>
              {displayBreakdown(game.away_goals, game.away_behinds)}
            </p>
          </div>
        </div>

        {/* Game Time */}
        <div className="text-center mb-4">
          <p className="text-xl font-semibold text-afl-warm-700">
            {game.status === 'live' && game.time_str
              ? game.time_str
              : game.status === 'completed'
              ? 'Final'
              : 'Scheduled'}
          </p>
          {game.status === 'live' && game.last_updated && (() => {
            const ageMs = Date.now() - new Date(game.last_updated + 'Z').getTime();
            return ageMs > 3 * 60 * 1000 ? (
              <p className="text-xs text-amber-500 mt-1">Data may be delayed</p>
            ) : null;
          })()}
        </div>

        {/* Progress Bar */}
        <ProgressBar completePercent={game.complete_percent} />

      </div>

      {/* Top Performers - shown for both live and completed games */}
      {!hideScores && (
        <GameStats gameId={game.id} gameStatus={game.status} />
      )}

      {/* Quarter Summaries - temporarily hidden while quality is improved */}
      {/* {!hideScores && hasQuarterSummaries && (
        <QuarterSummaries quarterSummaries={game.quarter_summaries!} quarterScores={game.quarter_scores} />
      )} */}

      {/* AI Summary for completed games - hidden when spoiler mode is on */}
      {!hideScores && game.status === 'completed' && game.ai_summary && (
        <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
          <h3 className="text-xl font-semibold text-afl-warm-900 mb-3">
            Match Summary
          </h3>
          <p className="text-afl-warm-700 leading-relaxed">
            {game.ai_summary}
          </p>
        </div>
      )}

      {/* Post-game stats analysis - hidden when spoiler mode is on */}
      {!hideScores && game.status === 'completed' && game.post_game_analysis && (
        <div className="glass rounded-apple-xl p-6 shadow-apple-lg">
          <h3 className="text-xl font-semibold text-afl-warm-900 mb-3">
            Match Stats Analysis
          </h3>
          <div className="space-y-3">
            {game.post_game_analysis.split('\n\n').map((paragraph, i) => (
              <p key={i} className="text-afl-warm-700 leading-relaxed">
                {paragraph}
              </p>
            ))}
          </div>
        </div>
      )}

    </div>
  );
};

export default LiveDashboard;
