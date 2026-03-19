import { useState, useRef, useEffect } from 'react';
import { useWebSocket } from '../../hooks/useWebSocket';
import ChartRenderer from '../Visualization/ChartRenderer';
import FeedbackButton from './FeedbackButton';

const MESSAGE_THRESHOLD = 20; // Suggest new chat after this many messages

const ChatContainer: React.FC = () => {
  const [input, setInput] = useState('');
  const [dismissedNewChatPrompt, setDismissedNewChatPrompt] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { messages, isConnected, isThinking, thinkingStep, isLoadingHistory, currentConversationId, sendMessage, startNewChat } = useWebSocket();

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

  // Handle input focus - scroll to bottom as backup
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
  <>
    <div
      className="flex flex-col h-[calc(100vh-12rem)] bg-white rounded-lg shadow-md border border-gray-200"
      style={{ marginBottom: keyboardHeight > 0 ? `${keyboardHeight}px` : undefined }}
    >
      {/* Connection Status & New Chat Button */}
      <div className="px-4 py-2 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-sm text-gray-600">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          {messages.length > 0 && (
            <button
              onClick={startNewChat}
              className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-200 transition-colors"
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
          <div className="text-center text-gray-500 mt-8">
            <div className="flex items-center justify-center gap-2">
              <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              <span>Loading conversation history...</span>
            </div>
          </div>
        )}

        {!isLoadingHistory && messages.length === 0 && (
          <div className="text-center text-gray-500 mt-8">
            <h2 className="text-xl font-semibold mb-2">Ask me about AFL statistics!</h2>
            <p className="text-sm">Try questions like:</p>
            <ul className="text-sm mt-2 space-y-1">
              <li>"Who won the 2025 grand final?"</li>
              <li>"Show me Richmond's performance in 2024"</li>
              <li>"Which teams had the most wins in 2023?"</li>
            </ul>
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id} className="mb-4">
            {/* Message bubble */}
            <div
              className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-3xl rounded-lg px-4 py-3 ${
                  message.type === 'user'
                    ? 'bg-blue-500 text-white'
                    : message.isError
                    ? 'bg-red-50 border border-red-200 text-gray-900'
                    : 'bg-gray-100 text-gray-900'
                }`}
              >
                {/* Error icon for error messages */}
                {message.isError && (
                  <div className="flex items-center gap-2 mb-2 text-red-600">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span className="text-sm font-medium">Something went wrong</span>
                  </div>
                )}
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
            <div className="max-w-3xl rounded-lg px-4 py-3 bg-gray-100 text-gray-900">
              <div className="flex items-center gap-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
                <span className="text-sm">{thinkingStep}</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* New Chat Suggestion Banner */}
      {showNewChatPrompt && (
        <div className="px-4 py-3 bg-amber-50 border-t border-amber-200 flex items-center justify-between">
          <div className="flex items-center gap-2 text-amber-800">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm">This conversation is getting long. Consider starting a new chat for better responses.</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDismissedNewChatPrompt(true)}
              className="text-sm text-amber-600 hover:text-amber-800 px-2 py-1"
            >
              Dismiss
            </button>
            <button
              onClick={() => {
                startNewChat();
                setDismissedNewChatPrompt(false);
              }}
              className="text-sm bg-amber-600 text-white px-3 py-1 rounded hover:bg-amber-700 transition-colors"
            >
              New Chat
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      <form onSubmit={handleSubmit} className="border-t border-gray-200 p-3 sm:p-4">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onFocus={handleInputFocus}
            placeholder="Ask about AFL statistics..."
            disabled={!isConnected || isThinking}
            className="flex-1 px-3 py-2 sm:px-4 text-sm sm:text-base border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!isConnected || isThinking || !input.trim()}
            className="px-4 py-2 sm:px-6 text-sm sm:text-base bg-blue-500 text-white rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {isThinking ? '...' : 'Send'}
          </button>
        </div>
      </form>
    </div>

    {/* Feedback section - outside main container */}
    {messages.length > 0 && (
      <FeedbackButton
        conversationId={currentConversationId}
        messageText={messages.filter(m => m.type === 'agent' && !m.isError).slice(-1)[0]?.text || ''}
      />
    )}
  </>
  );
};

export default ChatContainer;
