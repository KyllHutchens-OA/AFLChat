import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { SpoilerProvider } from './contexts/SpoilerContext';
import { ClubProvider } from './contexts/ClubContext';
import { LiveDataProvider } from './contexts/LiveDataContext';
import Layout from './components/Layout/Layout';
import SpoilerModal from './components/Modal/SpoilerModal';
import { useAnalytics } from './hooks/useAnalytics';

// Every route beyond the landing page is its own chunk, so a first-time
// visitor to "/" never downloads chat (Recharts, react-markdown), live
// games or the admin dashboard.
const Landing = lazy(() => import('./pages/Landing'));
const AFLAgent = lazy(() => import('./pages/AFLAgent'));
const LiveGames = lazy(() => import('./pages/LiveGames'));
const About = lazy(() => import('./pages/About'));
const Demo = lazy(() => import('./pages/Demo'));
const Analytics = lazy(() => import('./pages/Analytics'));

function AppRoutes() {
  useAnalytics();

  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/ask" element={<AFLAgent />} />
        <Route path="/afl" element={<AFLAgent />} />
        <Route path="/aflagent/:conversationId?" element={<AFLAgent />} />
        {/* Spoiler preference is asked only on the first visit to /live */}
        <Route path="/live" element={<><SpoilerModal /><LiveGames /></>} />
        <Route path="/about" element={<About />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/analytics" element={<Analytics />} />
        {/* Old induction URL; keep bookmarks working */}
        <Route path="/welcome" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

function App() {
  return (
    <Router>
      <SpoilerProvider>
        <ClubProvider>
          <LiveDataProvider>
            <Layout>
              <AppRoutes />
            </Layout>
          </LiveDataProvider>
        </ClubProvider>
      </SpoilerProvider>
    </Router>
  );
}

export default App;
