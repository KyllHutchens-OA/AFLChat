import { useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AgentChatContainer from '../components/Chat/AgentChatContainer';

const AFLAgent: React.FC = () => {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();

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
    <div>
      {/* Page header */}
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pt-8 pb-4">
        <h1 className="text-3xl font-semibold text-apple-gray-900">
          AFL Analytics Agent
        </h1>
        <p className="text-sm text-apple-gray-500 mt-1">
          Ask questions about AFL statistics (1990-2025)
        </p>
      </div>

      <main className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 pb-8">
        <AgentChatContainer
          conversationId={conversationId}
          onConversationCreated={handleConversationCreated}
        />
      </main>
    </div>
  );
};

export default AFLAgent;
