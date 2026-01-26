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
}

interface UseWebSocketReturn {
  messages: Message[];
  isConnected: boolean;
  isThinking: boolean;
  thinkingStep: string;
  sendMessage: (message: string) => void;
  clearMessages: () => void;
}

export const useWebSocket = (): UseWebSocketReturn => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState('');
  const socketRef = useRef<Socket | null>(null);
  const currentAgentMessageRef = useRef<Message | null>(null);
  const conversationIdRef = useRef<string | null>(null);

  useEffect(() => {
    // Connect to WebSocket
    const socket = io('http://localhost:5001', {
      transports: ['websocket'],
      autoConnect: true,
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('Connected to server');
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('Disconnected from server');
      setIsConnected(false);
    });

    socket.on('thinking', (data: { step: string }) => {
      console.log('Thinking:', data.step);
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
      console.log('Received response');
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

      setMessages((prev) => [...prev, agentMessage]);
      currentAgentMessageRef.current = null;
    });

    socket.on('complete', (data: { conversation_id?: string }) => {
      console.log('Request complete');
      setIsThinking(false);
      setThinkingStep('');

      // Store conversation_id for follow-up messages
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
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
      socket.disconnect();
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
    conversationIdRef.current = null; // Reset conversation for fresh start
  }, []);

  return {
    messages,
    isConnected,
    isThinking,
    thinkingStep,
    sendMessage,
    clearMessages,
  };
};
