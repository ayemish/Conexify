import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { BayesianModelPage } from './pages/BayesianModelPage';
import { DigitalTwinPage } from './pages/DigitalTwinPage';
import { OrchestrationPage } from './pages/OrchestrationPage';
import { AgentOutputPage } from './pages/AgentOutputPage';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }>
            <Route index element={<DashboardPage />} />
            <Route path="bayesian" element={<BayesianModelPage />} />
            <Route path="digital-twin" element={<DigitalTwinPage />} />
            <Route path="orchestration" element={<OrchestrationPage />} />
            <Route path="output" element={<AgentOutputPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App
