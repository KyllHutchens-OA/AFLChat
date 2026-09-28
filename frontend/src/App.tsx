import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { SpoilerProvider } from './contexts/SpoilerContext';
import { LiveDataProvider } from './contexts/LiveDataContext';
import Layout from './components/Layout/Layout';
import SpoilerModal from './components/Modal/SpoilerModal';
import AFLAgent from './pages/AFLAgent';
import LiveGames from './pages/LiveGames';
import About from './pages/About';
import Analytics from './pages/Analytics';
import { useAnalytics } from './hooks/useAnalytics';

function AppRoutes() {
  useAnalytics();

  return (
    <Routes>
      <Route path="/" element={<AFLAgent />} />
      <Route path="/afl" element={<AFLAgent />} />
      <Route path="/aflagent/:conversationId?" element={<AFLAgent />} />
      {/* Spoiler preference is asked only on the first visit to /live */}
      <Route path="/live" element={<><SpoilerModal /><LiveGames /></>} />
      <Route path="/about" element={<About />} />
      <Route path="/analytics" element={<Analytics />} />
      {/* Old induction URL; keep bookmarks working */}
      <Route path="/welcome" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <SpoilerProvider>
        <LiveDataProvider>
          <Layout>
            <AppRoutes />
          </Layout>
        </LiveDataProvider>
      </SpoilerProvider>
    </Router>
  );
}

export default App;
