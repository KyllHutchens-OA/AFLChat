import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

const CONVERSATION_STORAGE_KEY = 'afl_conversation_id';

interface Message {
  id: string;
  type: 'user' | 'agent';
  text: string;
  timestamp: Date;
  visualization?: any;
  confidence?: number;
  sources?: string[];
}

interface UseWebSocketReturn {
  messages: Message[];
  isConnected: boolean;
  isThinking: boolean;
  thinkingStep: string;
  isLoadingHistory: boolean;
  sendMessage: (message: string) => void;
  clearMessages: () => void;
  startNewChat: () => void;
}

// Singleton socket instance to prevent React StrictMode duplicate connections
let globalSocket: Socket | null = null;

export const useWebSocket = (): UseWebSocketReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState('');
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const socketRef = useRef<Socket | null>(null);
  const currentAgentMessageRef = useRef<Message | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const historyLoadedRef = useRef(false);

  // Load conversation history from backend
  const loadConversationHistory = useCallback(async (conversationId: string) => {
    try {
      setIsLoadingHistory(true);
      console.log('📜 Loading conversation history:', conversationId);

      const response = await fetch(`http://localhost:5001/api/conversations/${conversationId}`);
      if (!response.ok) {
        console.log('No existing conversation found, starting fresh');
        localStorage.removeItem(CONVERSATION_STORAGE_KEY);
        return;
      }

      const data = await response.json();
      if (data.messages && data.messages.length > 0) {
        // Convert stored messages to UI format (including visualizations)
        const loadedMessages: Message[] = data.messages.map((msg: any, index: number) => ({
          id: `history-${index}`,
          type: msg.role === 'user' ? 'user' : 'agent',
          text: msg.content,
          timestamp: new Date(msg.timestamp || Date.now()),
          confidence: msg.metadata?.confidence,
          sources: msg.metadata?.sources,
          visualization: msg.metadata?.visualization,  // Restore charts from history
        }));

        setMessages(loadedMessages);
        conversationIdRef.current = conversationId;
        console.log(`✅ Loaded ${loadedMessages.length} messages from history (with visualizations)`);
      }
    } catch (error) {
      console.error('Failed to load conversation history:', error);
      localStorage.removeItem(CONVERSATION_STORAGE_KEY);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  // Check for existing conversation on mount
  useEffect(() => {
    if (historyLoadedRef.current) return;
    historyLoadedRef.current = true;

    const savedConversationId = localStorage.getItem(CONVERSATION_STORAGE_KEY);
    if (savedConversationId) {
      conversationIdRef.current = savedConversationId;
      loadConversationHistory(savedConversationId);
    }
  }, [loadConversationHistory]);

  useEffect(() => {
    // Use global singleton socket to prevent React StrictMode duplicates
    if (!globalSocket) {
      console.log('🔌 Creating new WebSocket connection');
      globalSocket = io('http://localhost:5001', {
        transports: ['websocket'],
        autoConnect: true,
      });
    } else {
      console.log('♻️ Reusing existing WebSocket connection');
      // If socket is already connected, update state immediately
      if (globalSocket.connected) {
        console.log('✅ Socket already connected, updating state');
        setIsConnected(true);
      }
    }

    const socket = globalSocket;
    socketRef.current = socket;

    // Remove old listeners to prevent duplicates on remount
    socket.removeAllListeners();

    socket.on('connect', () => {
      console.log('✅ Connected to server');
      setIsConnected(true);
    });

    socket.on('disconnect', (reason) => {
      console.log('❌ Disconnected from server. Reason:', reason);
      setIsConnected(false);
    });

    socket.on('thinking', (data: { step: string }) => {
      console.log('💭 Thinking:', data.step);
      setIsThinking(true);
      setThinkingStep(data.step);
    });

    socket.on('visualization', (data: { spec: any }) => {
      console.log('Received visualization');
      // Add visualization to current agent message
      if (currentAgentMessageRef.current) {
        currentAgentMessageRef.current.visualization = data.spec;
      }
    });

    socket.on('response', (data: { text: string; confidence?: number; sources?: string[] }) => {
      console.log('✅ Received response event! Text length:', data.text?.length);
      console.log('Response text preview:', data.text?.substring(0, 100) + '...');
      setIsThinking(false);
      setThinkingStep('');

      // Create or update agent message
      const agentMessage: Message = {
        id: Date.now().toString(),
        type: 'agent',
        text: data.text,
        timestamp: new Date(),
        confidence: data.confidence,
        sources: data.sources,
        visualization: currentAgentMessageRef.current?.visualization,
      };

      console.log('Adding agent message to state:', agentMessage);
      setMessages((prev) => [...prev, agentMessage]);
      currentAgentMessageRef.current = null;
    });

    socket.on('complete', (data: { conversation_id?: string }) => {
      console.log('Request complete');
      setIsThinking(false);
      setThinkingStep('');

      // Store conversation_id for follow-up messages AND persist to localStorage
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
        localStorage.setItem(CONVERSATION_STORAGE_KEY, data.conversation_id);
        console.log('Stored conversation_id:', data.conversation_id);
      }
    });

    socket.on('error', (data: { message: string }) => {
      console.error('Error:', data.message);
      setIsThinking(false);
      setThinkingStep('');

      const errorMessage: Message = {
        id: Date.now().toString(),
        type: 'agent',
        text: `Error: ${data.message}`,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errorMessage]);
    });

    return () => {
      // Don't disconnect the singleton socket on cleanup
      // This prevents React StrictMode from breaking the connection
      console.log('🧹 Cleanup called (not disconnecting singleton socket)');
    };
  }, []);

  const sendMessage = useCallback((message: string) => {
    if (!socketRef.current || !isConnected) {
      console.error('Socket not connected');
      return;
    }

    // Add user message to UI
    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      text: message,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    // Initialize current agent message ref for potential visualization
    currentAgentMessageRef.current = {
      id: (Date.now() + 1).toString(),
      type: 'agent',
      text: '',
      timestamp: new Date(),
    };

    // Send to server with conversation_id (if we have one from previous messages)
    socketRef.current.emit('chat_message', {
      message,
      conversation_id: conversationIdRef.current,
    });
  }, [isConnected]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const startNewChat = useCallback(() => {
    setMessages([]);
    conversationIdRef.current = null;
    localStorage.removeItem(CONVERSATION_STORAGE_KEY);
    console.log('🆕 Started new chat, cleared history');
  }, []);

  return {
    messages,
    isConnected,
    isThinking,
    thinkingStep,
    isLoadingHistory,
    sendMessage,
    clearMessages,
    startNewChat,
  };
};
