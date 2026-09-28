import { useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import AgentChatContainer from '../components/Chat/AgentChatContainer';

const AFLAgent: React.FC = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  // /ask?q=... pre-fills and sends the question (landing page hero/chips/proof cards)
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get('q') ?? undefined;

  const clearQueryParam = useCallback(() => {
    if (searchParams.has('q')) setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

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

  return (
    <main className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-2 h-full">
      <AgentChatContainer
        conversationId={conversationId}
        onConversationCreated={handleConversationCreated}
        initialQuery={initialQuery}
        onInitialQuerySent={clearQueryParam}
      />
    </main>
  );
};

export default AFLAgent;
