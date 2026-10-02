import { useState, useRef, useEffect } from 'react';
import { useAgentWebSocket } from '../../hooks/useAgentWebSocket';
import ResponseCard from './ResponseCard';
import SuggestedQuestions from './SuggestedQuestions';
import ThinkingCard from './ThinkingCard';
import ChatInput from './ChatInput';
import RecentConversationsDrawer from './RecentConversationsDrawer';
import { getRecentConversations } from '../../utils/recentConversations';

const MESSAGE_THRESHOLD = 20;

interface AgentChatContainerProps {
  conversationId?: string;
  onConversationCreated: (id: string | null) => void;
  onSelectConversation: (id: string) => void;
  // /ask?q=... — sent once on mount, then the caller clears the query param
  initialQuery?: string;
  onInitialQuerySent?: () => void;
}

const AgentChatContainer: React.FC<AgentChatContainerProps> = ({
  conversationId,
  onConversationCreated,
  onSelectConversation,
  initialQuery,
  onInitialQuerySent,
}) => {
  const [input, setInput] = useState('');
  const [dismissedNewChatPrompt, setDismissedNewChatPrompt] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const [showRecent, setShowRecent] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sentInitialQuery = useRef(false);
  const {
    messages, isConnected, isThinking, thinkingStep, thinkingTool, thinkingPhase,
    isLoadingHistory, currentConversationId, sendMessage, startNewChat,
  } = useAgentWebSocket({ conversationId, onConversationCreated });

  useEffect(() => {
    if (!initialQuery || sentInitialQuery.current || !isConnected) return;
    sentInitialQuery.current = true;
    sendMessage(initialQuery);
    onInitialQuerySent?.();
  }, [initialQuery, isConnected, sendMessage, onInitialQuerySent]);

  const showNewChatPrompt = messages.length >= MESSAGE_THRESHOLD && !dismissedNewChatPrompt;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

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

  const handleSubmit = () => {
    if (!input.trim() || isThinking) return;
    sendMessage(input.trim());
    setInput('');
  };

  const handleSuggestedQuestion = (question: string) => {
    sendMessage(question);
  };

  return (
      <div
        className="flex flex-col h-full overflow-hidden"
        style={{
          marginBottom: keyboardHeight > 0 ? `${keyboardHeight}px` : undefined,
        }}
      >
        {/* Present for screen readers/SEO even though the empty-state heading
            below (h2) is the only one usually visible. */}
        <h1 className="sr-only">Ask a footy question</h1>

        {/* Disconnected warning */}
        {!isConnected && (
          <div className="px-4 py-2 bg-sherrin-50 border border-sherrin-200 rounded-lg mb-3 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-sherrin-500" />
            <span className="text-sm text-sherrin-700">Disconnected — reconnecting...</span>
          </div>
        )}

        {/* Messages Area. role="log" + aria-live: screen-reader users hear each
            answer as it arrives, and aria-busy reflects the thinking state. */}
        <div
          role="log"
          aria-live="polite"
          aria-busy={isThinking}
          className="flex-1 overflow-y-auto space-y-4 pb-4 min-h-0"
        >
          {isLoadingHistory && (
            <div className="text-center text-warm-500 mt-8">
              <div className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-sherrin border-t-transparent rounded-full animate-spin" />
                <span>Loading conversation...</span>
              </div>
            </div>
          )}

          {/* Empty state */}
          {!isLoadingHistory && messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center px-4 animate-fade-in">
              <h2 className="text-2xl font-semibold text-warm-900 mb-2">
                Ask me about AFL statistics
              </h2>
              <p className="text-sm text-warm-500 mb-8">
                Stats, records, player comparisons — ask anything
              </p>
              <SuggestedQuestions onSelect={handleSuggestedQuestion} />
            </div>
          )}

          {/* Message list */}
          {messages.map((message) => (
            <div key={message.id} className="animate-fade-in">
              {message.type === 'user' ? (
                /* User bubble — right-aligned, warm accent */
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-br-md px-4 py-3 bg-sherrin text-white shadow-card-sm">
                    <div className="whitespace-pre-wrap text-sm">{message.text}</div>
                  </div>
                </div>
              ) : (
                <ResponseCard
                  text={message.text}
                  visualization={message.visualization}
                  isError={message.isError}
                  dataAsOf={message.isStreaming ? undefined : message.dataAsOf}
                  trace={message.trace}
                  conversationId={currentConversationId}
                />
              )}
            </div>
          ))}

          {/* Thinking */}
          {isThinking && <ThinkingCard step={thinkingStep} tool={thinkingTool} currentStep={thinkingPhase} />}

          <div ref={messagesEndRef} />
        </div>

        {/* New Chat Suggestion Banner */}
        {showNewChatPrompt && (
          <div className="px-4 py-3 bg-nightgame-100 border border-nightgame-300 rounded-lg mb-3 flex items-center justify-between">
            <span className="text-sm text-warm-800">
              This conversation is getting long. Consider starting fresh.
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setDismissedNewChatPrompt(true)}
                className="text-sm text-warm-500 hover:text-warm-700 px-2 py-1"
              >
                Dismiss
              </button>
              <button
                onClick={() => { startNewChat(); setDismissedNewChatPrompt(false); }}
                className="btn-primary text-sm"
              >
                New Chat
              </button>
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="flex items-end gap-2 pt-3 flex-shrink-0">
          <button
            type="button"
            onClick={() => setShowRecent(true)}
            aria-label="Recent chats"
            title="Recent chats"
            className="p-2.5 rounded-lg text-warm-400 hover:text-warm-700 hover:bg-warm-100 transition-colors
                       focus-visible:ring-2 focus-visible:ring-sherrin/50 focus-visible:outline-none"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={startNewChat}
              aria-label="Start a new chat"
              title="New Chat"
              className="p-2.5 rounded-lg text-warm-400 hover:text-warm-700 hover:bg-warm-100 transition-colors
                         focus-visible:ring-2 focus-visible:ring-sherrin/50 focus-visible:outline-none"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          )}
          <div className="flex-1">
            <ChatInput
              value={input}
              onChange={setInput}
              onSubmit={handleSubmit}
              onFocus={handleInputFocus}
              disabled={!isConnected || isThinking}
            />
          </div>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!isConnected || isThinking || !input.trim()}
            aria-label="Send message"
            className="p-2.5 rounded-xl bg-sherrin text-white
                       hover:bg-sherrin-600 disabled:bg-warm-200 disabled:cursor-not-allowed
                       transition-all duration-200 focus-visible:ring-2 focus-visible:ring-sherrin/50 focus-visible:outline-none"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {showRecent && (
          <RecentConversationsDrawer
            conversations={getRecentConversations()}
            currentId={currentConversationId}
            onSelect={(id) => { setShowRecent(false); onSelectConversation(id); }}
            onClose={() => setShowRecent(false)}
          />
        )}
      </div>
  );
};

export default AgentChatContainer;
