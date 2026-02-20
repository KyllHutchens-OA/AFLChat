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
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              AFL Analytics Agent
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Ask questions about AFL statistics (1990-2025)
            </p>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <AgentChatContainer
          conversationId={conversationId}
          onConversationCreated={handleConversationCreated}
        />
      </main>
    </div>
  );
};

export default AFLAgent;
