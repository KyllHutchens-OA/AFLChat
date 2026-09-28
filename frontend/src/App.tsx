import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { SpoilerProvider } from './contexts/SpoilerContext';
import { LiveDataProvider } from './contexts/LiveDataContext';
import Layout from './components/Layout/Layout';
import SpoilerModal from './components/Modal/SpoilerModal';
import AFLAgent from './pages/AFLAgent';
import LiveGames from './pages/LiveGames';
import About from './pages/About';
import { useAnalytics } from './hooks/useAnalytics';

// Admin dashboard stays out of the main bundle.
const Analytics = lazy(() => import('./pages/Analytics'));

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
      <Route path="/analytics" element={<Suspense fallback={null}><Analytics /></Suspense>} />
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
