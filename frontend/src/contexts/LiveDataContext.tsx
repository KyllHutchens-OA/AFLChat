/**
 * LiveDataContext — Prefetches live games + upcoming matches at app level
 * so the /live tab has data ready immediately. Also caches game detail and
 * stats for completed games to avoid re-fetching on sidebar navigation.
 */
import { createContext, useContext, useState, useEffect, useRef, useCallback, ReactNode } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

// ── Types ────────────────────────────────────────────────────────────────────

interface LiveGame {
  id: number;
  squiggle_id: number;
  season: number;
  round: string;
  home_team: { id: number; name: string; abbreviation: string };
  away_team: { id: number; name: string; abbreviation: string };
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
}

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

interface GameEvent {
  id: number;
  event_type: string;
  team: { id: number; name: string; abbreviation: string } | null;
  home_score_after: number;
  away_score_after: number;
  quarter: number;
  time_str: string;
  timestamp: string;
  player_name?: string;
  player_api_sports_id?: number;
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
    id: number; name: string; abbreviation: string;
    primary_color: string; secondary_color: string;
  };
  away_team: {
    id: number; name: string; abbreviation: string;
    primary_color: string; secondary_color: string;
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
  post_game_analysis?: string | null;
  quarter_scores?: QuarterScores;
  quarter_summaries?: Record<string, string>;
}

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

interface LiveDataContextType {
  // Live games list
  games: LiveGame[];
  gamesLoading: boolean;
  gamesError: string | null;

  // Upcoming matches
  upcomingMatches: UpcomingMatch[];
  upcomingLoading: boolean;
  nextMatch: UpcomingMatch | null;

  // Game detail cache
  getGameDetail: (gameId: number) => LiveGameDetail | null;
  setGameDetail: (gameId: number, game: LiveGameDetail) => void;
  gameDetailLoading: (gameId: number) => boolean;
  fetchGameDetail: (gameId: number) => Promise<void>;

  // Game stats cache
  getGameStats: (gameId: number) => GameStats | null;
  gameStatsLoading: (gameId: number) => boolean;
  fetchGameStats: (gameId: number, gameStatus?: string) => Promise<void>;
}

// ── Context ──────────────────────────────────────────────────────────────────

const LiveDataContext = createContext<LiveDataContextType | undefined>(undefined);

// Polling intervals
const LIVE_POLL_INTERVAL = 15000;   // 15s when live games exist
const IDLE_POLL_INTERVAL = 300000;  // 5 min when no live games
const UPCOMING_POLL_INTERVAL = 300000; // 5 min

// ── Provider ─────────────────────────────────────────────────────────────────

export const LiveDataProvider = ({ children }: { children: ReactNode }) => {
  // ── Live games list ──
  const [games, setGames] = useState<LiveGame[]>([]);
  const [gamesLoading, setGamesLoading] = useState(true);
  const [gamesError, setGamesError] = useState<string | null>(null);

  // ── Upcoming matches ──
  const [upcomingMatches, setUpcomingMatches] = useState<UpcomingMatch[]>([]);
  const [upcomingLoading, setUpcomingLoading] = useState(true);

  // ── Game detail cache (keyed by gameId) ──
  const [detailCache, setDetailCache] = useState<Record<number, LiveGameDetail>>({});
  const [detailLoadingSet, setDetailLoadingSet] = useState<Set<number>>(new Set());

  // ── Game stats cache (keyed by gameId) ──
  const [statsCache, setStatsCache] = useState<Record<number, GameStats>>({});
  const [statsLoadingSet, setStatsLoadingSet] = useState<Set<number>>(new Set());

  // Track in-flight fetches to prevent duplicates
  const detailFetchingRef = useRef<Set<number>>(new Set());
  const statsFetchingRef = useRef<Set<number>>(new Set());

  // ── Fetch live games (prefetched at app level) ──
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
        setGamesError(null);

        const hasLiveGames = fetchedGames.some((g: LiveGame) => g.status === 'live');
        const hasScheduledGames = fetchedGames.some((g: LiveGame) => g.status === 'scheduled');

        if (!hasLiveGames && !hasScheduledGames && fetchedGames.length > 0) {
          if (intervalId) { clearInterval(intervalId); intervalId = null; }
          return;
        }

        const newInterval = hasLiveGames ? LIVE_POLL_INTERVAL : IDLE_POLL_INTERVAL;

        if (isFirstFetch) {
          isFirstFetch = false;
          currentInterval = newInterval;
          intervalId = setInterval(fetchGames, currentInterval);
        } else if (newInterval !== currentInterval) {
          currentInterval = newInterval;
          if (intervalId) clearInterval(intervalId);
          intervalId = setInterval(fetchGames, currentInterval);
        }
      } catch (err) {
        setGamesError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setGamesLoading(false);
      }
    };

    fetchGames();
    return () => { if (intervalId) clearInterval(intervalId); };
  }, []);

  // ── Fetch upcoming matches (prefetched at app level) ──
  useEffect(() => {
    const fetchUpcoming = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/upcoming-matches`);
        if (!response.ok) throw new Error('Failed to fetch upcoming matches');
        const data = await response.json();
        setUpcomingMatches(data.matches || []);
      } catch (err) {
        console.error('Error fetching upcoming matches:', err);
      } finally {
        setUpcomingLoading(false);
      }
    };

    fetchUpcoming();
    const interval = setInterval(fetchUpcoming, UPCOMING_POLL_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  // ── Eagerly prefetch detail + stats for all games once list loads ──
  useEffect(() => {
    if (games.length === 0) return;

    for (const game of games) {
      // Prefetch detail for all games (completed data never changes)
      if (!detailFetchingRef.current.has(game.id)) {
        // Use raw fetch to avoid stale closure issues with the callback
        if (!detailFetchingRef.current.has(game.id)) {
          detailFetchingRef.current.add(game.id);
          fetch(`${BACKEND_URL}/api/live-games/${game.id}`)
            .then(r => r.ok ? r.json() : null)
            .then(data => {
              if (data) setDetailCache(prev => ({ ...prev, [game.id]: data }));
            })
            .catch(() => {})
            .finally(() => detailFetchingRef.current.delete(game.id));
        }
      }

      // Prefetch stats for all games
      if (!statsFetchingRef.current.has(game.id)) {
        statsFetchingRef.current.add(game.id);
        fetch(`${BACKEND_URL}/api/live-games/${game.id}/stats`)
          .then(r => r.ok ? r.json() : null)
          .then(data => {
            if (data) setStatsCache(prev => ({ ...prev, [game.id]: data }));
          })
          .catch(() => {})
          .finally(() => statsFetchingRef.current.delete(game.id));
      }
    }
  }, [games]); // Re-run when games list changes (new games appear)

  // ── Game detail: fetch with caching ──
  const fetchGameDetail = useCallback(async (gameId: number) => {
    // Skip if already fetching this game
    if (detailFetchingRef.current.has(gameId)) return;

    // For completed games, skip if already cached
    const cached = detailCache[gameId];
    if (cached?.status === 'completed' && cached.post_game_analysis) return;

    detailFetchingRef.current.add(gameId);
    setDetailLoadingSet(prev => new Set(prev).add(gameId));

    try {
      const response = await fetch(`${BACKEND_URL}/api/live-games/${gameId}`);
      if (!response.ok) throw new Error('Failed to fetch game');
      const data = await response.json();
      setDetailCache(prev => ({ ...prev, [gameId]: data }));
    } catch (err) {
      console.error(`Error fetching game ${gameId}:`, err);
    } finally {
      detailFetchingRef.current.delete(gameId);
      setDetailLoadingSet(prev => {
        const next = new Set(prev);
        next.delete(gameId);
        return next;
      });
    }
  }, [detailCache]);

  // ── Game stats: fetch with caching ──
  const fetchGameStats = useCallback(async (gameId: number, gameStatus?: string) => {
    if (statsFetchingRef.current.has(gameId)) return;

    // For completed games, skip if already cached
    const cached = statsCache[gameId];
    if (cached && gameStatus === 'completed') return;

    statsFetchingRef.current.add(gameId);
    setStatsLoadingSet(prev => new Set(prev).add(gameId));

    try {
      const response = await fetch(`${BACKEND_URL}/api/live-games/${gameId}/stats`);
      if (!response.ok) throw new Error('Failed to fetch stats');
      const data = await response.json();
      setStatsCache(prev => ({ ...prev, [gameId]: data }));
    } catch (err) {
      console.error(`Error fetching stats for game ${gameId}:`, err);
    } finally {
      statsFetchingRef.current.delete(gameId);
      setStatsLoadingSet(prev => {
        const next = new Set(prev);
        next.delete(gameId);
        return next;
      });
    }
  }, [statsCache]);

  const getGameDetail = useCallback((gameId: number) => detailCache[gameId] || null, [detailCache]);
  const setGameDetail = useCallback((gameId: number, game: LiveGameDetail) => {
    setDetailCache(prev => ({ ...prev, [gameId]: game }));
  }, []);
  const gameDetailLoading = useCallback((gameId: number) => detailLoadingSet.has(gameId), [detailLoadingSet]);

  const getGameStats = useCallback((gameId: number) => statsCache[gameId] || null, [statsCache]);
  const gameStatsLoading = useCallback((gameId: number) => statsLoadingSet.has(gameId), [statsLoadingSet]);

  const nextMatch = upcomingMatches.length > 0 ? upcomingMatches[0] : null;

  return (
    <LiveDataContext.Provider value={{
      games, gamesLoading, gamesError,
      upcomingMatches, upcomingLoading, nextMatch,
      getGameDetail, setGameDetail, gameDetailLoading, fetchGameDetail,
      getGameStats, gameStatsLoading, fetchGameStats,
    }}>
      {children}
    </LiveDataContext.Provider>
  );
};

// ── Hook ─────────────────────────────────────────────────────────────────────

export const useLiveData = () => {
  const context = useContext(LiveDataContext);
  if (!context) {
    throw new Error('useLiveData must be used within LiveDataProvider');
  }
  return context;
};

// Re-export types for consumers
export type { LiveGame, UpcomingMatch, LiveGameDetail, GameEvent, QuarterScores, GameStats, PlayerStat };
