import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/Layout';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { ModelsPage } from './pages/ModelsPage';
import { ExperimentsPage } from './pages/ExperimentsPage';
import { RetrainingPage } from './pages/RetrainingPage';
import { GovernancePage } from './pages/GovernancePage';
import { HealthPage } from './pages/HealthPage';
import { MetricsPage } from './pages/MetricsPage';
import { AssetExplorerPage } from './pages/AssetExplorerPage';
import { CaseQueuePage } from './pages/CaseQueuePage';
import { CaseCockpitPage } from './pages/CaseCockpitPage';
import { WorkOrdersPage } from './pages/WorkOrdersPage';
import { OutcomesPage } from './pages/OutcomesPage';
import { AdminPage } from './pages/AdminPage';
import DispatchOptimizerPage from './pages/DispatchOptimizerPage';
import EvaluationDashboardPage from './pages/EvaluationDashboardPage';
import OperationsCenterPage from './pages/OperationsCenterPage';
import TechnicianCockpitPage from './pages/TechnicianCockpitPage';
import CalibrationDashboardPage from './pages/CalibrationDashboardPage';
import AgentDashboardPage from './pages/AgentDashboardPage';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          
          {/* Protected Routes */}
          <Route element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }>
            {/* Operations */}
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/assets" element={<AssetExplorerPage />} />
            <Route path="/cases" element={<CaseQueuePage />} />
            <Route path="/cases/:caseId" element={<CaseCockpitPage />} />
            <Route path="/work-orders" element={<WorkOrdersPage />} />
            <Route path="/dispatch" element={<DispatchOptimizerPage />} />
            <Route path="/ops-center" element={<OperationsCenterPage />} />
            <Route path="/technician" element={<TechnicianCockpitPage />} />
            <Route path="/outcomes" element={<OutcomesPage />} />
            <Route path="/evaluation" element={<EvaluationDashboardPage />} />
            
            {/* ML Ops */}
            <Route path="/models" element={<ModelsPage />} />
            <Route path="/experiments" element={<ExperimentsPage />} />
            <Route path="/retraining" element={<RetrainingPage />} />
            <Route path="/calibration" element={<CalibrationDashboardPage />} />
            <Route path="/agents" element={<AgentDashboardPage />} />
            
            {/* System */}
            <Route path="/governance" element={<GovernancePage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Route>

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
