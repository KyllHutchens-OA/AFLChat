import { useEffect, useState, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';

// No localStorage persistence - resume chat resets on page refresh

interface Message {
  id: string;
  type: 'user' | 'agent';
  text: string;
  timestamp: Date;
  confidence?: number;
}

interface UseResumeWebSocketReturn {
  messages: Message[];
  isConnected: boolean;
  isThinking: boolean;
  thinkingStep: string;
  sendMessage: (message: string) => void;
  clearMessages: () => void;
  startNewChat: () => void;
}

// Singleton socket instance
let globalResumeSocket: Socket | null = null;

export const useResumeWebSocket = (): UseResumeWebSocketReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState('');
  const socketRef = useRef<Socket | null>(null);
  const conversationIdRef = useRef<string | null>(null);

  useEffect(() => {
    // Use global singleton socket
    if (!globalResumeSocket) {
      console.log('🔌 Creating new Resume WebSocket connection');
      globalResumeSocket = io('http://localhost:5001', {
        transports: ['websocket'],
        autoConnect: true,
      });
    } else {
      console.log('♻️ Reusing existing Resume WebSocket connection');
      if (globalResumeSocket.connected) {
        setIsConnected(true);
      }
    }

    const socket = globalResumeSocket;
    socketRef.current = socket;

    // Remove old listeners
    socket.removeAllListeners();

    socket.on('connect', () => {
      console.log('Resume chat connected');
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('Resume chat disconnected');
      setIsConnected(false);
    });

    socket.on('resume_thinking', (data: { step: string }) => {
      console.log('Thinking:', data.step);
      setIsThinking(true);
      setThinkingStep(data.step);
    });

    socket.on('resume_response', (data: { text: string; confidence?: number }) => {
      console.log('Received resume response');
      setIsThinking(false);
      setThinkingStep('');

      const agentMessage: Message = {
        id: Date.now().toString(),
        type: 'agent',
        text: data.text,
        timestamp: new Date(),
        confidence: data.confidence,
      };

      setMessages((prev) => [...prev, agentMessage]);
    });

    socket.on('resume_complete', (data: { conversation_id?: string }) => {
      console.log('Resume request complete');
      setIsThinking(false);
      setThinkingStep('');

      // Keep conversation_id in memory for follow-ups within same session
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
      }
    });

    socket.on('resume_error', (data: { message: string }) => {
      console.error('Resume error:', data.message);
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
      // Don't disconnect singleton socket
      console.log('🧹 Resume cleanup called (not disconnecting singleton socket)');
    };
  }, []);

  const sendMessage = useCallback((message: string) => {
    if (!socketRef.current || !isConnected) {
      console.error('Socket not connected');
      return;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      text: message,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    socketRef.current.emit('resume_message', {
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
    console.log('🆕 Started new resume chat');
  }, []);

  return {
    messages,
    isConnected,
    isThinking,
    thinkingStep,
    sendMessage,
    clearMessages,
    startNewChat,
  };
};
