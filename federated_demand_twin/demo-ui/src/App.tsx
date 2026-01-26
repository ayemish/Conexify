import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { EcosystemSelectPage } from './pages/EcosystemSelectPage';
import { LoginPage } from './pages/LoginPage';

// Retail Media Pages
import { RetailMediaLayout } from './components/RetailMediaLayout';
import { DashboardPage } from './pages/DashboardPage';
import { BayesianModelPage } from './pages/BayesianModelPage';
import { DigitalTwinPage } from './pages/DigitalTwinPage';
import { OrchestrationPage } from './pages/OrchestrationPage';
import { AgentOutputPage } from './pages/AgentOutputPage';

// Demand & Procurement Pages
import { DemandProcurementLayout } from './components/DemandProcurementLayout';
import { DPDashboardPage } from './pages/dp/DPDashboardPage';
import { DPBayesianModelPage } from './pages/dp/DPBayesianModelPage';
import { DPDigitalTwinPage } from './pages/dp/DPDigitalTwinPage';
import { DPOrchestrationPage } from './pages/dp/DPOrchestrationPage';
import { DPAgentOutputPage } from './pages/dp/DPAgentOutputPage';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          
          {/* Ecosystem Selection Landing Page */}
          <Route path="/" element={
            <ProtectedRoute>
              <EcosystemSelectPage />
            </ProtectedRoute>
          } />

          {/* Retail Media Optimization Routes */}
          <Route path="/retail-media" element={
            <ProtectedRoute>
              <RetailMediaLayout />
            </ProtectedRoute>
          }>
            <Route index element={<DashboardPage />} />
            <Route path="bayesian" element={<BayesianModelPage />} />
            <Route path="digital-twin" element={<DigitalTwinPage />} />
            <Route path="orchestration" element={<OrchestrationPage />} />
            <Route path="output" element={<AgentOutputPage />} />
          </Route>

          {/* Demand & Procurement Routes */}
          <Route path="/demand-procurement" element={
            <ProtectedRoute>
              <DemandProcurementLayout />
            </ProtectedRoute>
          }>
            <Route index element={<DPDashboardPage />} />
            <Route path="bayesian" element={<DPBayesianModelPage />} />
            <Route path="digital-twin" element={<DPDigitalTwinPage />} />
            <Route path="orchestration" element={<DPOrchestrationPage />} />
            <Route path="output" element={<DPAgentOutputPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App
