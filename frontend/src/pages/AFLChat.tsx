import ChatContainer from '../components/Chat/ChatContainer';
import LiveScoreWidget from '../components/LiveGames/LiveScoreWidget';

const AFLChat: React.FC = () => {
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
        <ChatContainer />
      </main>

      {/* Live score widget */}
      <LiveScoreWidget />
    </div>
  );
};

export default AFLChat;
