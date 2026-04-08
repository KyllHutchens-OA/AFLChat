import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { SpoilerProvider } from './contexts/SpoilerContext';
import { TeamProvider } from './contexts/TeamContext';
import Layout from './components/Layout/Layout';
import SpoilerModal from './components/Modal/SpoilerModal';
import AFLAgent from './pages/AFLAgent';
import LiveGames from './pages/LiveGames';
import About from './pages/About';
import Analytics from './pages/Analytics';
import TeamSelection from './pages/TeamSelection';
import { useAnalytics } from './hooks/useAnalytics';

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
      <Route path="/analytics" element={<Analytics />} />
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <TeamProvider>
        <SpoilerProvider>
          <SpoilerModal />
          <Routes>
            <Route path="/welcome" element={<TeamSelection />} />
            <Route path="*" element={
              <Layout>
                <AppRoutes />
              </Layout>
            } />
          </Routes>
        </SpoilerProvider>
      </TeamProvider>
    </Router>
  );
}

export default App;
