import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { SpoilerProvider } from './contexts/SpoilerContext';
import { ClubProvider } from './contexts/ClubContext';
import { LiveDataProvider } from './contexts/LiveDataContext';
import Layout from './components/Layout/Layout';
import SpoilerModal from './components/Modal/SpoilerModal';
import AFLAgent from './pages/AFLAgent';
import LiveGames from './pages/LiveGames';
import About from './pages/About';
import { useAnalytics } from './hooks/useAnalytics';

// Landing and admin dashboard stay out of the main bundle.
const Landing = lazy(() => import('./pages/Landing'));
const Analytics = lazy(() => import('./pages/Analytics'));

function AppRoutes() {
  useAnalytics();

  return (
    <Routes>
      <Route path="/" element={<Suspense fallback={null}><Landing /></Suspense>} />
      <Route path="/ask" element={<AFLAgent />} />
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
