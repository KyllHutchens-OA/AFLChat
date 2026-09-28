import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { SpoilerProvider } from './contexts/SpoilerContext';
import { TeamProvider } from './contexts/TeamContext';
import { LiveDataProvider } from './contexts/LiveDataContext';
import Layout from './components/Layout/Layout';
import SpoilerModal from './components/Modal/SpoilerModal';
import AFLAgent from './pages/AFLAgent';
import LiveGames from './pages/LiveGames';
import About from './pages/About';
import TeamSelection from './pages/TeamSelection';
import { useAnalytics } from './hooks/useAnalytics';

// Admin dashboard stays out of the main bundle.
const Analytics = lazy(() => import('./pages/Analytics'));

function HomeRedirect() {
  const hasTeam = localStorage.getItem('footy-nac-team');
  return <Navigate to={hasTeam ? '/aflagent' : '/welcome'} replace />;
}

function AppRoutes() {
  useAnalytics();

  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/afl" element={<AFLAgent />} />
      <Route path="/aflagent/:conversationId?" element={<AFLAgent />} />
      <Route path="/live" element={<LiveGames />} />
      <Route path="/about" element={<About />} />
      <Route path="/analytics" element={<Suspense fallback={null}><Analytics /></Suspense>} />
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <TeamProvider>
        <SpoilerProvider>
          <LiveDataProvider>
            <SpoilerModal />
            <Routes>
              <Route path="/welcome" element={<TeamSelection />} />
              <Route path="*" element={
                <Layout>
                  <AppRoutes />
                </Layout>
              } />
            </Routes>
          </LiveDataProvider>
        </SpoilerProvider>
      </TeamProvider>
    </Router>
  );
}

export default App;
