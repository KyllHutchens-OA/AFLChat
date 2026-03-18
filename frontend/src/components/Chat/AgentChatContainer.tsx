import { useState, useRef, useEffect } from 'react';
import { useAgentWebSocket } from '../../hooks/useAgentWebSocket';
import ChartRenderer from '../Visualization/ChartRenderer';

const MESSAGE_THRESHOLD = 20;

interface AgentChatContainerProps {
  conversationId?: string;
  onConversationCreated: (id: string | null) => void;
}

const AgentChatContainer: React.FC<AgentChatContainerProps> = ({
  conversationId,
  onConversationCreated,
}) => {
  const [input, setInput] = useState('');
  const [dismissedNewChatPrompt, setDismissedNewChatPrompt] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { messages, isConnected, isThinking, thinkingStep, isLoadingHistory, sendMessage, startNewChat } =
    useAgentWebSocket({ conversationId, onConversationCreated });

  const showNewChatPrompt = messages.length >= MESSAGE_THRESHOLD && !dismissedNewChatPrompt;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Handle mobile keyboard visibility using visualViewport API
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;

    const handleResize = () => {
      const keyboardH = window.innerHeight - viewport.height;
      setKeyboardHeight(keyboardH > 50 ? keyboardH : 0);
    };

    viewport.addEventListener('resize', handleResize);
    viewport.addEventListener('scroll', handleResize);

    return () => {
      viewport.removeEventListener('resize', handleResize);
      viewport.removeEventListener('scroll', handleResize);
    };
  }, []);

  const handleInputFocus = () => {
    setTimeout(() => scrollToBottom(), 300);
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isThinking, keyboardHeight]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!input.trim() || isThinking) {
      return;
    }

    sendMessage(input.trim());
    setInput('');
  };

  return (
    <div
      className="flex flex-col h-[calc(100vh-12rem)] glass rounded-apple-xl shadow-apple-lg"
      style={{ marginBottom: keyboardHeight > 0 ? `${keyboardHeight}px` : undefined }}
    >
      {/* Connection Status & New Chat Button */}
      <div className="px-4 py-2 glass sticky top-0 z-10 border-b border-apple-gray-200/50 rounded-t-apple-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-apple-green animate-pulse' : 'bg-apple-red'}`} />
            <span className="text-sm text-apple-gray-700">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          {messages.length > 0 && (
            <button
              onClick={startNewChat}
              className="btn-apple-secondary text-sm flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Chat
            </button>
          )}
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {isLoadingHistory && (
          <div className="text-center text-apple-gray-500 mt-8">
            <div className="flex items-center justify-center gap-2">
              <div className="w-4 h-4 border-2 border-apple-blue-500 border-t-transparent rounded-full animate-spin"></div>
              <span>Loading conversation history...</span>
            </div>
          </div>
        )}

        {!isLoadingHistory && messages.length === 0 && (
          <div className="text-center text-apple-gray-500 mt-8 animate-fade-in-up">
            <h2 className="text-xl font-semibold mb-2 text-apple-gray-900">Ask me about AFL statistics!</h2>
            <p className="text-sm">Try questions like:</p>
            <ul className="text-sm mt-2 space-y-1">
              <li>"Who won the 2025 grand final?"</li>
              <li>"Show me Richmond's performance in 2024"</li>
              <li>"Which teams had the most wins in 2023?"</li>
            </ul>
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id} className="mb-4 animate-scale-in">
            {/* Message bubble */}
            <div
              className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-3xl rounded-[18px] px-4 py-3 ${
                  message.type === 'user'
                    ? 'bg-apple-blue-500 text-white shadow-apple'
                    : 'bg-apple-gray-100 text-apple-gray-900'
                }`}
              >
                <div className="whitespace-pre-wrap">{message.text}</div>
              </div>
            </div>

            {/* Chart - full width outside message bubble */}
            {message.type === 'agent' && message.visualization && (
              <div className="w-full mt-3">
                <ChartRenderer spec={message.visualization} />
              </div>
            )}
          </div>
        ))}

        {/* Thinking Indicator */}
        {isThinking && (
          <div className="flex justify-start">
            <div className="max-w-3xl glass rounded-apple px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-apple-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-apple-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-apple-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
                <span className="text-sm text-apple-gray-700">{thinkingStep}</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* New Chat Suggestion Banner */}
      {showNewChatPrompt && (
        <div className="px-4 py-3 glass border-t-2 border-apple-orange bg-apple-orange/10 flex items-center justify-between">
          <div className="flex items-center gap-2 text-apple-orange">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm font-medium">This conversation is getting long. Consider starting a new chat for better responses.</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDismissedNewChatPrompt(true)}
              className="text-sm text-apple-gray-700 hover:text-apple-gray-900 px-2 py-1 transition-colors"
            >
              Dismiss
            </button>
            <button
              onClick={() => {
                startNewChat();
                setDismissedNewChatPrompt(false);
              }}
              className="btn-apple-primary text-sm"
            >
              New Chat
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      <form onSubmit={handleSubmit} className="border-t border-apple-gray-200 p-3 sm:p-4 bg-white/50 rounded-b-apple-xl">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onFocus={handleInputFocus}
            placeholder="Ask about AFL statistics..."
            disabled={!isConnected || isThinking}
            className="input-apple flex-1 text-sm sm:text-base disabled:bg-apple-gray-100 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!isConnected || isThinking || !input.trim()}
            className="btn-apple-primary text-sm sm:text-base disabled:bg-apple-gray-300 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {isThinking ? '...' : 'Send'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AgentChatContainer;
