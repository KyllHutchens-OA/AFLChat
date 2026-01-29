import { useState, useRef, useEffect } from 'react';
import { useWebSocket } from '../../hooks/useWebSocket';
import ChartRenderer from '../Visualization/ChartRenderer';

const MESSAGE_THRESHOLD = 20; // Suggest new chat after this many messages

const ChatContainer: React.FC = () => {
  const [input, setInput] = useState('');
  const [dismissedNewChatPrompt, setDismissedNewChatPrompt] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { messages, isConnected, isThinking, thinkingStep, isLoadingHistory, sendMessage, startNewChat } = useWebSocket();

  const showNewChatPrompt = messages.length >= MESSAGE_THRESHOLD && !dismissedNewChatPrompt;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isThinking]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!input.trim() || isThinking) {
      return;
    }

    sendMessage(input.trim());
    setInput('');
  };

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)] bg-white rounded-lg shadow-md border border-gray-200">
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
                    : 'bg-gray-100 text-gray-900'
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
      <form onSubmit={handleSubmit} className="border-t border-gray-200 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about AFL statistics..."
            disabled={!isConnected || isThinking}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!isConnected || isThinking || !input.trim()}
            className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {isThinking ? 'Thinking...' : 'Send'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ChatContainer;
