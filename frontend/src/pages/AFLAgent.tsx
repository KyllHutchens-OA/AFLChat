import { useCallback, useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import AgentChatContainer from '../components/Chat/AgentChatContainer';
import { getLastConversationId } from '../utils/recentConversations';

const AFLAgent: React.FC = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  // /ask?q=... pre-fills and sends the question (landing page hero/chips/proof cards)
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get('q') ?? undefined;
  const restoreChecked = useRef(false);

  const clearQueryParam = useCallback(() => {
    if (searchParams.has('q')) setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  // Returning to bare /ask (or /afl): restore the last conversation on this
  // device, if any, instead of always starting fresh.
  useEffect(() => {
    if (restoreChecked.current || conversationId || initialQuery) return;
    restoreChecked.current = true;
    const lastId = getLastConversationId();
    if (lastId) navigate(`/aflagent/${lastId}`, { replace: true });
  }, [conversationId, initialQuery, navigate]);

  const handleConversationCreated = useCallback(
    (id: string | null) => {
      if (id) {
        // New conversation created — put ID in URL (replace so back button doesn't stack)
        navigate(`/aflagent/${id}`, { replace: true });
      } else {
        // New chat requested or invalid conversation — go to bare route
        navigate('/aflagent', { replace: true });
      }
    },
    [navigate],
  );

  // Recent-chats drawer: jump to a different, already-existing conversation
  // (a real navigation, so the back button can return to where you were).
  const handleSelectConversation = useCallback(
    (id: string) => navigate(`/aflagent/${id}`),
    [navigate],
  );

  return (
    <main className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-2 h-full">
      {/* Remount on conversation change so history reloads cleanly instead of
          merging with whatever the previous conversation had in state. */}
      <AgentChatContainer
        key={conversationId || 'new'}
        conversationId={conversationId}
        onConversationCreated={handleConversationCreated}
        onSelectConversation={handleSelectConversation}
        initialQuery={initialQuery}
        onInitialQuerySent={clearQueryParam}
      />
    </main>
  );
};

export default AFLAgent;
