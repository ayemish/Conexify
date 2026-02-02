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
import { DataFederationPage } from './pages/DataFederationPage';
import { TEEStatePage } from './pages/TEEStatePage';
import { AgentsOverviewPage } from './pages/AgentsOverviewPage';
import { BayesianDigitalTwinPage } from './pages/BayesianDigitalTwinPage';
import OptimizationCrewsPage from './pages/OptimizationCrewsPage';
import { OrchestrationPage } from './pages/OrchestrationPage';
import { AgentOutputPage } from './pages/AgentOutputPage';
import { AutonomousOrchestrationPage } from './pages/AutonomousOrchestrationPage';

// Demand & Procurement Pages
import { DemandProcurementLayout } from './components/DemandProcurementLayout';
import { DPDashboardPage } from './pages/dp/DPDashboardPage';
import { DPBayesianModelPage } from './pages/dp/DPBayesianModelPage';
import { DPDigitalTwinPage } from './pages/dp/DPDigitalTwinPage';
import { DPOrchestrationPage } from './pages/dp/DPOrchestrationPage';
import { DPAgentOutputPage } from './pages/dp/DPAgentOutputPage';

// Predictive Maintenance Pages
import { PredictiveMaintenanceLayout } from './components/PredictiveMaintenanceLayout';
import { PMDashboardPage } from './pages/pm/PMDashboardPage';
import { PMModelsPage } from './pages/pm/PMModelsPage';
import { PMExperimentsPage } from './pages/pm/PMExperimentsPage';
import { PMRetrainingPage } from './pages/pm/PMRetrainingPage';
import { PMGovernancePage } from './pages/pm/PMGovernancePage';
import { PMHealthPage } from './pages/pm/PMHealthPage';
import { PMMetricsPage } from './pages/pm/PMMetricsPage';

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
            <Route path="data-federation" element={<DataFederationPage />} />
            <Route path="tee-state/:retailerId" element={<TEEStatePage />} />
            <Route path="agents" element={<AgentsOverviewPage />} />
            <Route path="crews" element={<OptimizationCrewsPage />} />
            <Route path="bayesian-twins" element={<BayesianDigitalTwinPage />} />
            <Route path="orchestration" element={<OrchestrationPage />} />
            <Route path="autonomous" element={<AutonomousOrchestrationPage />} />
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

          {/* Predictive Maintenance Routes */}
          <Route path="/predictive-maintenance" element={
            <ProtectedRoute>
              <PredictiveMaintenanceLayout />
            </ProtectedRoute>
          }>
            <Route index element={<PMDashboardPage />} />
            <Route path="models" element={<PMModelsPage />} />
            <Route path="experiments" element={<PMExperimentsPage />} />
            <Route path="retraining" element={<PMRetrainingPage />} />
            <Route path="governance" element={<PMGovernancePage />} />
            <Route path="health" element={<PMHealthPage />} />
            <Route path="metrics" element={<PMMetricsPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App
