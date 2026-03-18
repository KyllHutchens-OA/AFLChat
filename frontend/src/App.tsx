import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { SpoilerProvider } from './contexts/SpoilerContext';
import Layout from './components/Layout/Layout';
import SpoilerModal from './components/Modal/SpoilerModal';
import AFLChat from './pages/AFLChat';
import AFLAgent from './pages/AFLAgent';
import LiveGames from './pages/LiveGames';
import About from './pages/About';
import { useAnalytics } from './hooks/useAnalytics';

function AppRoutes() {
  useAnalytics();

  return (
    <Routes>
      <Route path="/" element={<AFLChat />} />
      <Route path="/afl" element={<AFLChat />} />
      <Route path="/aflagent/:conversationId?" element={<AFLAgent />} />
      <Route path="/live" element={<LiveGames />} />
      <Route path="/about" element={<About />} />
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <SpoilerProvider>
        <SpoilerModal />
        <Layout>
          <AppRoutes />
        </Layout>
      </SpoilerProvider>
    </Router>
  );
}

export default App;
