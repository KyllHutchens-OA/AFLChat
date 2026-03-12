import { Link } from 'react-router-dom';
import ChatContainer from '../components/Chat/ChatContainer';

const AFLChat: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                AFL Analytics Agent
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                Ask questions about AFL statistics (1990-2025)
              </p>
            </div>
            <div className="flex items-center gap-4">
              <Link
                to="/live"
                className="text-sm px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-2"
              >
                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                Live Games
              </Link>
              <Link
                to="/"
                className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                Back to Home
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <ChatContainer />
      </main>
    </div>
  );
};

export default AFLChat;
