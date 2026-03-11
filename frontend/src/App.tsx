import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import AFLChat from './pages/AFLChat';
import AFLAgent from './pages/AFLAgent';
import { useAnalytics } from './hooks/useAnalytics';

function AppRoutes() {
  useAnalytics();

  return (
    <Routes>
      <Route path="/" element={<AFLChat />} />
      <Route path="/afl" element={<AFLChat />} />
      <Route path="/aflagent/:conversationId?" element={<AFLAgent />} />
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
