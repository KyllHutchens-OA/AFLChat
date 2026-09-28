import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

interface Message {
  id: string;
  type: 'user' | 'agent';
  text: string;
  timestamp: Date;
  visualization?: any;
  confidence?: number;
  sources?: string[];
  isError?: boolean;
  errorType?: 'rate_limit' | 'usage_limit' | 'processing' | 'network' | 'unknown';
}

interface UseAgentWebSocketOptions {
  conversationId?: string;
  onConversationCreated: (id: string | null) => void;
}

interface UseAgentWebSocketReturn {
  messages: Message[];
  isConnected: boolean;
  isThinking: boolean;
  thinkingStep: string;
  isLoadingHistory: boolean;
  currentConversationId: string | null;
  sendMessage: (message: string) => void;
  clearMessages: () => void;
  startNewChat: () => void;
}

// Singleton socket instance to prevent React StrictMode duplicate connections
let globalSocket: Socket | null = null;

// Use environment variable or default to localhost for development
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5001';

// Server-signed visitor token (quota identity) and per-conversation owner tokens.
// The owner token is issued once in `conversation_started`; the server needs it
// to read or append to that conversation.
const VISITOR_TOKEN_KEY = 'footy-nac-visitor-token';
const CONVERSATION_TOKENS_KEY = 'footy-nac-conversation-tokens';

const readStorage = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const writeStorage = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage unavailable (private mode); the session still works, history won't reload
  }
};

const readConversationTokens = (): Record<string, string> => {
  try {
    const parsed = JSON.parse(readStorage(CONVERSATION_TOKENS_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const getConversationToken = (id: string | null): string | null =>
  id ? readConversationTokens()[id] ?? null : null;

const saveConversationToken = (id: string, token: string) => {
  writeStorage(CONVERSATION_TOKENS_KEY, JSON.stringify({ ...readConversationTokens(), [id]: token }));
};

export const useAgentWebSocket = ({
  conversationId,
  onConversationCreated,
}: UseAgentWebSocketOptions): UseAgentWebSocketReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState('');
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const socketRef = useRef<Socket | null>(null);
  // Holds a visualization spec that arrived before we've attached it to an
  // agent message yet. The `visualization` and `response` socket events are
  // NOT guaranteed to arrive in a fixed order, so we can't rely on mutating a
  // single in-flight message object (that was the old, order-dependent bug).
  const pendingVizRef = useRef<any>(null);
  // Id of the most recently added agent message, so a late-arriving
  // visualization (arrives after `response` already fired) can still be
  // attached via `complete`.
  const lastAgentMessageIdRef = useRef<string | null>(null);
  const conversationIdRef = useRef<string | null>(conversationId || null);
  const historyLoadedRef = useRef(false);
  const hadConversationRef = useRef(!!conversationId);
  const onConversationCreatedRef = useRef(onConversationCreated);

  // Keep callback ref current without triggering re-renders
  useEffect(() => {
    onConversationCreatedRef.current = onConversationCreated;
  }, [onConversationCreated]);

  // Sync conversationId prop into ref
  useEffect(() => {
    conversationIdRef.current = conversationId || null;
  }, [conversationId]);

  // Load conversation history from backend
  const loadConversationHistory = useCallback(async (convId: string) => {
    try {
      setIsLoadingHistory(true);

      const token = getConversationToken(convId);
      if (!token) {
        // Not ours (or storage cleared): the server would refuse it, start fresh
        onConversationCreatedRef.current(null);
        return;
      }
      const response = await fetch(`${BACKEND_URL}/api/conversations/${encodeURIComponent(convId)}`, {
        headers: { 'X-Conversation-Token': token },
      });
      if (!response.ok) {
        // Conversation not found — treat as fresh
        onConversationCreatedRef.current(null);
        return;
      }

      const data = await response.json();
      if (data.messages && data.messages.length > 0) {
        const loadedMessages: Message[] = data.messages.map((msg: any, index: number) => ({
          id: `history-${index}`,
          type: msg.role === 'user' ? 'user' : 'agent',
          text: msg.content,
          timestamp: new Date(msg.timestamp || Date.now()),
          confidence: msg.metadata?.confidence,
          sources: msg.metadata?.sources,
          visualization: msg.metadata?.visualization,
        }));

        setMessages(loadedMessages);
        conversationIdRef.current = convId;
      }
    } catch (error) {
      console.error('Failed to load conversation history:', error);
      onConversationCreatedRef.current(null);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  // Load history when conversationId is provided on mount
  useEffect(() => {
    if (historyLoadedRef.current) return;
    historyLoadedRef.current = true;

    if (conversationId) {
      loadConversationHistory(conversationId);
    }
  }, [conversationId, loadConversationHistory]);

  // Reset state only when user navigates away from an active conversation to bare /aflagent (New Chat).
  // Skip the initial mount where conversationId is undefined (no conversation yet).
  useEffect(() => {
    if (!conversationId && hadConversationRef.current) {
      setMessages([]);
      conversationIdRef.current = null;
      historyLoadedRef.current = true;
    }
    if (conversationId) {
      hadConversationRef.current = true;
    }
  }, [conversationId]);

  useEffect(() => {
    // Use global singleton socket to prevent React StrictMode duplicates
    if (!globalSocket) {
      globalSocket = io(BACKEND_URL, {
        transports: ['websocket', 'polling'],
        autoConnect: true,
        // Re-read on every (re)connect so a freshly issued token is reused
        auth: (cb) => cb({ visitor_token: readStorage(VISITOR_TOKEN_KEY) }),
      });
    } else {
      if (globalSocket.connected) {
        setIsConnected(true);
      }
    }

    const socket = globalSocket;
    socketRef.current = socket;

    // Remove this hook's own listeners to prevent duplicates on remount.
    // (Per-event `off` rather than `removeAllListeners`, since the latter
    // would also strip listeners registered by anyone else sharing the
    // singleton socket.)
    socket.off('connect');
    socket.off('disconnect');
    socket.off('thinking');
    socket.off('visualization');
    socket.off('response');
    socket.off('complete');
    socket.off('error');
    socket.off('visitor_token');
    socket.off('conversation_started');

    socket.on('visitor_token', (data: { token?: string }) => {
      if (data?.token) writeStorage(VISITOR_TOKEN_KEY, data.token);
    });

    socket.on('conversation_started', (data: { conversation_id?: string; owner_token?: string }) => {
      if (data?.conversation_id && data.owner_token) {
        saveConversationToken(data.conversation_id, data.owner_token);
      }
    });

    socket.on('connect', () => {
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      setIsConnected(false);
      setIsThinking(false);
      setThinkingStep('');
    });

    socket.on('thinking', (data: { step: string }) => {
      setIsThinking(true);
      setThinkingStep(data.step);
    });

    socket.on('visualization', (data: { spec: any }) => {
      pendingVizRef.current = data.spec;
    });

    socket.on('response', (data: { text: string; confidence?: number; sources?: string[] }) => {
      setIsThinking(false);
      setThinkingStep('');

      const agentMessage: Message = {
        id: crypto.randomUUID(),
        type: 'agent',
        text: data.text,
        timestamp: new Date(),
        confidence: data.confidence,
        sources: data.sources,
        visualization: pendingVizRef.current ?? undefined,
      };
      pendingVizRef.current = null;
      lastAgentMessageIdRef.current = agentMessage.id;

      setMessages((prev) => [...prev, agentMessage]);
    });

    socket.on('complete', (data: { conversation_id?: string }) => {
      setIsThinking(false);
      setThinkingStep('');

      // If a visualization arrived AFTER `response` already built the agent
      // message (race between the two events), attach it to that message now
      // instead of silently dropping it.
      if (pendingVizRef.current && lastAgentMessageIdRef.current) {
        const viz = pendingVizRef.current;
        const targetId = lastAgentMessageIdRef.current;
        pendingVizRef.current = null;
        setMessages((prev) =>
          prev.map((m) => (m.id === targetId ? { ...m, visualization: viz } : m)),
        );
      }

      if (data.conversation_id) {
        // New when the server started a conversation other than the one we sent
        const isNew = conversationIdRef.current !== data.conversation_id;
        // Update ref BEFORE triggering navigation to prevent reset effect
        conversationIdRef.current = data.conversation_id;
        hadConversationRef.current = true;
        if (isNew) {
          onConversationCreatedRef.current(data.conversation_id);
        }
      }
    });

    socket.on('error', (data: { message: string }) => {
      setIsThinking(false);
      setThinkingStep('');

      // Categorize error type for better UX
      const errorMsg = data.message.toLowerCase();
      let errorType: Message['errorType'] = 'unknown';
      let friendlyMessage = data.message;

      if (errorMsg.includes('rate limit')) {
        errorType = 'rate_limit';
        friendlyMessage = "You're sending messages too quickly. Please wait a moment before trying again.";
      } else if (errorMsg.includes('usage limit') || errorMsg.includes('daily limit')) {
        errorType = 'usage_limit';
        friendlyMessage = "You've reached the daily usage limit. Please try again tomorrow.";
      } else if (errorMsg.includes('timeout') || errorMsg.includes('connection')) {
        errorType = 'network';
        friendlyMessage = "Connection issue - please check your internet and try again.";
      } else if (errorMsg.includes('no message')) {
        errorType = 'processing';
        friendlyMessage = "Please enter a message to send.";
      } else {
        errorType = 'processing';
        friendlyMessage = `Something went wrong processing your request. ${data.message}`;
      }

      const errorMessage: Message = {
        id: crypto.randomUUID(),
        type: 'agent',
        text: friendlyMessage,
        timestamp: new Date(),
        isError: true,
        errorType,
      };

      setMessages((prev) => [...prev, errorMessage]);
    });

    return () => {
      // Don't disconnect the singleton socket on cleanup
    };
  }, []);

  const sendMessage = useCallback((message: string) => {
    if (!socketRef.current || !isConnected) {
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      type: 'user',
      text: message,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    // Clear any leftover pending visualization from a previous turn (e.g. one
    // that never got flushed because that turn ended in an error).
    pendingVizRef.current = null;

    socketRef.current.emit('chat_message', {
      message,
      conversation_id: conversationIdRef.current,
      owner_token: getConversationToken(conversationIdRef.current),
      source: 'aflagent',
    });
  }, [isConnected]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const startNewChat = useCallback(() => {
    setMessages([]);
    conversationIdRef.current = null;
    historyLoadedRef.current = true;
    // Signal page to navigate to bare /aflagent
    onConversationCreatedRef.current(null);
  }, []);

  return {
    messages,
    isConnected,
    isThinking,
    thinkingStep,
    isLoadingHistory,
    currentConversationId: conversationIdRef.current,
    sendMessage,
    clearMessages,
    startNewChat,
  };
};
