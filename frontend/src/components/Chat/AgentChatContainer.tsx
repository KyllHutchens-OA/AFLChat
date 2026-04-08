import { useState, useRef, useEffect } from 'react';
import { useAgentWebSocket } from '../../hooks/useAgentWebSocket';
import QueryEcho from './QueryEcho';
import ResponseCard from './ResponseCard';
import SuggestedQuestions from './SuggestedQuestions';
import ThinkingCard from './ThinkingCard';
import FeedbackButton from './FeedbackButton';

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
  const { messages, isConnected, isThinking, thinkingStep, isLoadingHistory, currentConversationId, sendMessage, startNewChat } =
    useAgentWebSocket({ conversationId, onConversationCreated });

  // Read team from localStorage (avoid importing TeamContext to keep this self-contained)
  const teamName = localStorage.getItem('footy-nac-team');

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
    if (!input.trim() || isThinking) return;
    sendMessage(input.trim());
    setInput('');
  };

  const handleSuggestedQuestion = (question: string) => {
    sendMessage(question);
  };

  return (
    <>
      <div
        className="flex flex-col h-[calc(100vh-8rem)]"
        style={{ marginBottom: keyboardHeight > 0 ? `${keyboardHeight}px` : undefined }}
      >
        {/* Disconnected warning - only show when disconnected */}
        {!isConnected && (
          <div className="px-4 py-2 bg-red-50 border border-red-200 rounded-lg mb-3 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-sm text-red-700">Disconnected — reconnecting...</span>
          </div>
        )}

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto space-y-4 pb-4">
          {isLoadingHistory && (
            <div className="text-center text-afl-warm-500 mt-8">
              <div className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-afl-accent border-t-transparent rounded-full animate-spin" />
                <span>Loading conversation...</span>
              </div>
            </div>
          )}

          {/* Empty state */}
          {!isLoadingHistory && messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center px-4 animate-fade-in">
              <h2 className="text-2xl font-semibold text-afl-warm-900 mb-2">
                {teamName ? `What do you want to know about the ${teamName}?` : 'Ask me about AFL statistics'}
              </h2>
              <p className="text-sm text-afl-warm-500 mb-8">
                Stats, records, player comparisons — ask anything
              </p>
              <SuggestedQuestions teamName={teamName} onSelect={handleSuggestedQuestion} />
            </div>
          )}

          {/* Message list */}
          {messages.map((message) => (
            <div key={message.id} className="animate-fade-in">
              {message.type === 'user' ? (
                <QueryEcho text={message.text} />
              ) : (
                <ResponseCard
                  text={message.text}
                  visualization={message.visualization}
                  isError={message.isError}
                />
              )}
            </div>
          ))}

          {/* Thinking */}
          {isThinking && <ThinkingCard step={thinkingStep} />}

          <div ref={messagesEndRef} />
        </div>

        {/* New Chat Suggestion Banner */}
        {showNewChatPrompt && (
          <div className="px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg mb-3 flex items-center justify-between">
            <span className="text-sm text-amber-800">
              This conversation is getting long. Consider starting fresh.
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setDismissedNewChatPrompt(true)}
                className="text-sm text-afl-warm-500 hover:text-afl-warm-700 px-2 py-1"
              >
                Dismiss
              </button>
              <button
                onClick={() => { startNewChat(); setDismissedNewChatPrompt(false); }}
                className="btn-apple-primary text-sm"
              >
                New Chat
              </button>
            </div>
          </div>
        )}

        {/* Input Area */}
        <form onSubmit={handleSubmit} className="flex items-center gap-2 pt-3">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={startNewChat}
              className="p-2.5 rounded-lg text-afl-warm-400 hover:text-afl-warm-700 hover:bg-afl-warm-100 transition-colors"
              title="New Chat"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          )}
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={handleInputFocus}
              placeholder={teamName ? `Ask about ${teamName}...` : 'Ask about AFL statistics...'}
              disabled={!isConnected || isThinking}
              className="w-full px-4 py-3 rounded-xl border border-afl-warm-200 bg-white
                         focus:outline-none focus:ring-2 focus:ring-afl-accent/30 focus:border-afl-accent
                         text-sm disabled:bg-afl-warm-50 disabled:cursor-not-allowed
                         placeholder:text-afl-warm-400 transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={!isConnected || isThinking || !input.trim()}
            className="p-2.5 rounded-xl bg-afl-accent text-white
                       hover:bg-afl-accent-600 disabled:bg-afl-warm-200 disabled:cursor-not-allowed
                       transition-all duration-200"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </form>
      </div>

      {/* Feedback section */}
      {messages.length > 0 && (
        <FeedbackButton
          conversationId={currentConversationId}
          messageText={messages.filter(m => m.type === 'agent' && !m.isError).slice(-1)[0]?.text || ''}
        />
      )}
    </>
  );
};

export default AgentChatContainer;
