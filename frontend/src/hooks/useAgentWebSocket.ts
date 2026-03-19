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
  const currentAgentMessageRef = useRef<Message | null>(null);
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

      const response = await fetch(`${BACKEND_URL}/api/conversations/${convId}`);
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
      });
    } else {
      if (globalSocket.connected) {
        setIsConnected(true);
      }
    }

    const socket = globalSocket;
    socketRef.current = socket;

    // Remove old listeners to prevent duplicates on remount
    socket.removeAllListeners();

    socket.on('connect', () => {
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      setIsConnected(false);
    });

    socket.on('thinking', (data: { step: string }) => {
      setIsThinking(true);
      setThinkingStep(data.step);
    });

    socket.on('visualization', (data: { spec: any }) => {
      if (currentAgentMessageRef.current) {
        currentAgentMessageRef.current.visualization = data.spec;
      }
    });

    socket.on('response', (data: { text: string; confidence?: number; sources?: string[] }) => {
      setIsThinking(false);
      setThinkingStep('');

      const agentMessage: Message = {
        id: Date.now().toString(),
        type: 'agent',
        text: data.text,
        timestamp: new Date(),
        confidence: data.confidence,
        sources: data.sources,
        visualization: currentAgentMessageRef.current?.visualization,
      };

      setMessages((prev) => [...prev, agentMessage]);
      currentAgentMessageRef.current = null;
    });

    socket.on('complete', (data: { conversation_id?: string }) => {
      setIsThinking(false);
      setThinkingStep('');

      if (data.conversation_id) {
        const isNew = !conversationIdRef.current;
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
        id: Date.now().toString(),
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
      id: Date.now().toString(),
      type: 'user',
      text: message,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    currentAgentMessageRef.current = {
      id: (Date.now() + 1).toString(),
      type: 'agent',
      text: '',
      timestamp: new Date(),
    };

    socketRef.current.emit('chat_message', {
      message,
      conversation_id: conversationIdRef.current,
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
