import { useState, useEffect } from 'react';
import { 
  Users, Play, CheckCircle, Clock, 
  RefreshCw, ChevronRight, Shield, AlertCircle
} from 'lucide-react';
import { dpApi, type DPOrchestrationPageData } from '../../services/dpApi';

export function DPOrchestrationPage() {
  const [data, setData] = useState<DPOrchestrationPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const pageData = await dpApi.getOrchestrationPageData();
      setData(pageData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-emerald-600 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
        <div className="flex items-center gap-3">
          <AlertCircle className="w-6 h-6 text-amber-600" />
          <div>
            <h3 className="font-semibold text-amber-800">Data Not Available</h3>
            <p className="text-amber-600 text-sm mt-1">{error}</p>
            <p className="text-amber-600 text-sm">Run the demo first to populate the orchestration data.</p>
          </div>
        </div>
      </div>
    );
  }

  const agents = data?.agents || [];
  const actions = data?.agentActions || [];
  const steps = data?.orchestrationSteps || [];
  const currentCase = data?.currentCase;
  const governance = data?.governance;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'processing': return <Play className="w-5 h-5 text-emerald-500 animate-pulse" />;
      case 'waiting': return <Clock className="w-5 h-5 text-amber-500" />;
      default: return <Clock className="w-5 h-5 text-slate-400" />;
    }
  };

  const getStepStatusClass = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-100 border-green-300 text-green-800';
      case 'active': return 'bg-emerald-100 border-emerald-300 text-emerald-800 animate-pulse';
      default: return 'bg-slate-100 border-slate-300 text-slate-600';
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Procurement Workflow Orchestration</h1>
          <p className="text-slate-500 mt-1">Forecast → Optimize → Risk → Simulate → Plan → Govern → Report</p>
        </div>
        <button 
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Current Case Card */}
      {currentCase && (
        <div className="bg-gradient-to-r from-emerald-500 to-teal-600 rounded-xl p-6 text-white">
          <div className="flex items-start justify-between">
            <div>
              <span className="text-emerald-200 text-sm">Active Decision Pack</span>
              <h2 className="text-xl font-bold mt-1">{currentCase.title}</h2>
              <p className="text-emerald-100 text-sm mt-2">Pack ID: {currentCase.id}</p>
            </div>
            <div className="text-right">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                currentCase.status === 'complete' ? 'bg-green-400/20 text-green-100' :
                currentCase.status === 'in_progress' ? 'bg-white/20' :
                'bg-amber-400/20 text-amber-100'
              }`}>
                {currentCase.status}
              </span>
              <p className="text-emerald-100 text-sm mt-2">
                Confidence: {(currentCase.confidence * 100).toFixed(0)}%
              </p>
            </div>
          </div>
          <div className="grid grid-cols-4 gap-4 mt-6">
            <div className="bg-white/10 rounded-lg p-3">
              <p className="text-emerald-200 text-xs">Agents Active</p>
              <p className="text-xl font-bold">{currentCase.assignedAgents.length}</p>
            </div>
            <div className="bg-white/10 rounded-lg p-3">
              <p className="text-emerald-200 text-xs">Scenarios</p>
              <p className="text-xl font-bold">{currentCase.hypotheses}</p>
            </div>
            <div className="bg-white/10 rounded-lg p-3">
              <p className="text-emerald-200 text-xs">Risk Alerts</p>
              <p className="text-xl font-bold">{currentCase.alerts}</p>
            </div>
            <div className="bg-white/10 rounded-lg p-3">
              <p className="text-emerald-200 text-xs">Working Capital</p>
              <p className="text-xl font-bold">${(currentCase.totalBudget / 1000).toFixed(0)}K</p>
            </div>
          </div>
        </div>
      )}

      {/* Pipeline Steps */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Pipeline Workflow</h2>
        <div className="flex items-center justify-between gap-2 overflow-x-auto pb-2">
          {steps.map((step, idx) => (
            <div key={step.id} className="flex items-center">
              <div className={`px-4 py-2 rounded-lg border ${getStepStatusClass(step.status)} min-w-[100px] text-center`}>
                <span className="text-sm font-medium">{step.name}</span>
                <div className="text-xs mt-1 opacity-75">
                  {step.agents.join(', ')}
                </div>
              </div>
              {idx < steps.length - 1 && (
                <ChevronRight className="w-5 h-5 text-slate-300 mx-1 flex-shrink-0" />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Agents */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Users className="w-5 h-5 text-emerald-600" />
            Supply Chain Agents
          </h2>
          <div className="space-y-3">
            {agents.map((agent) => (
              <div 
                key={agent.id}
                className={`flex items-center gap-4 p-3 rounded-lg border ${
                  agent.status === 'completed' ? 'border-green-200 bg-green-50' :
                  agent.status === 'processing' ? 'border-emerald-200 bg-emerald-50' :
                  'border-slate-200 bg-slate-50'
                }`}
              >
                <span className="text-2xl">{agent.avatar}</span>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-slate-900">{agent.name}</span>
                    {getStatusIcon(agent.status)}
                  </div>
                  <p className="text-xs text-slate-500">{agent.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Agent Actions */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Recent Agent Actions</h2>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {actions.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-4">No actions yet. Run the demo to see agent activity.</p>
            ) : (
              actions.map((action) => (
                <div key={action.id} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg">
                  <div className={`w-2 h-2 rounded-full mt-2 ${
                    action.status === 'completed' ? 'bg-green-500' :
                    action.status === 'in_progress' ? 'bg-emerald-500 animate-pulse' :
                    'bg-slate-400'
                  }`} />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-900">{action.agentName}</span>
                      <span className="text-xs text-slate-400">{action.timestamp}</span>
                    </div>
                    <p className="text-sm text-slate-600 mt-1">{action.action}</p>
                    {action.duration && (
                      <span className="text-xs text-slate-400">{action.duration}ms</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Governance */}
      {governance && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-emerald-600" />
            Governance & Policy Validation
          </h2>
          <div className="grid grid-cols-4 gap-4">
            <div className="p-4 bg-slate-50 rounded-lg">
              <p className="text-sm text-slate-500">Autonomy Level</p>
              <p className="text-lg font-semibold text-slate-900">{governance.autonomyLevel}</p>
            </div>
            <div className="p-4 bg-slate-50 rounded-lg">
              <p className="text-sm text-slate-500">Policy Checks</p>
              <p className="text-lg font-semibold text-slate-900">
                {governance.policyChecks.passed}/{governance.policyChecks.total} passed
              </p>
            </div>
            <div className="p-4 bg-slate-50 rounded-lg">
              <p className="text-sm text-slate-500">Pending Approvals</p>
              <p className="text-lg font-semibold text-slate-900">{governance.pendingApprovals}</p>
            </div>
            <div className="p-4 bg-slate-50 rounded-lg">
              <p className="text-sm text-slate-500">Audit Entries</p>
              <p className="text-lg font-semibold text-slate-900">{governance.auditEntries}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
