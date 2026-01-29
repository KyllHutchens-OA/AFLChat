import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import AFLChat from './pages/AFLChat';
import ResumeChat from './pages/ResumeChat';
import { useAnalytics } from './hooks/useAnalytics';

function AppRoutes() {
  useAnalytics();

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/afl" element={<AFLChat />} />
      <Route path="/resume" element={<ResumeChat />} />
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <AppRoutes />
    </Router>
  );
}

export default App;
