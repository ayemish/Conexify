import { useState, useEffect } from 'react';
import { 
  Users, Play, CheckCircle, Clock, ArrowRight,
  Workflow, Shield, Zap, RefreshCw
} from 'lucide-react';
import { api, type OrchestrationPageData } from '../services/api';

const statusStyles = {
  idle: { bg: 'bg-slate-100', text: 'text-slate-600', ring: 'ring-slate-200' },
  processing: { bg: 'bg-blue-100', text: 'text-blue-700', ring: 'ring-blue-300' },
  waiting: { bg: 'bg-amber-100', text: 'text-amber-700', ring: 'ring-amber-300' },
  completed: { bg: 'bg-green-100', text: 'text-green-700', ring: 'ring-green-300' },
};

const stepStatusStyles: Record<string, { bg: string; border: string; text: string }> = {
  pending: { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-400' },
  active: { bg: 'bg-blue-50', border: 'border-blue-300', text: 'text-blue-700' },
  completed: { bg: 'bg-green-50', border: 'border-green-300', text: 'text-green-700' },
  skipped: { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-400' },
};

export function OrchestrationPage() {
  const [data, setData] = useState<OrchestrationPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const result = await api.getOrchestrationPageData();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const agents = data?.agents || [];
  const agentActions = data?.agentActions || [];
  const orchestrationSteps = data?.orchestrationSteps || [];
  const currentCase = data?.currentCase || { id: 'PENDING', title: 'Awaiting Demo', status: 'pending', priority: 'medium', assignedAgents: [], alerts: 0, hypotheses: 0, totalBudget: 10000000, confidence: 0 };
  const governance = data?.governance || { autonomyLevel: 'PENDING', policyChecks: { passed: 0, total: 0 }, pendingApprovals: 0, auditEntries: 0 };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Orchestration data...</span>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl">
        <p className="text-red-700">Error: {error}</p>
        <p className="text-sm text-red-600 mt-2">Make sure the backend is running and the demo has been executed.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Agent Orchestration</h1>
          <p className="text-slate-500 mt-1">Multi-agent workflow coordination and case lifecycle</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-full">
            <Play className="w-4 h-4 text-blue-600" />
            <span className="text-sm font-medium text-blue-700">Workflow Active</span>
          </div>
        </div>
      </div>

      {/* Active Case Banner */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-6 rounded-xl text-white">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Workflow className="w-5 h-5" />
              <span className="text-indigo-200 text-sm font-medium">ACTIVE CASE</span>
            </div>
            <h2 className="text-2xl font-bold mb-1">{currentCase.title}</h2>
            <p className="text-indigo-200">Case ID: {currentCase.id}</p>
          </div>
          <div className="text-right">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-3xl font-bold">{currentCase.alerts}</p>
                <p className="text-indigo-200 text-sm">Alerts</p>
              </div>
              <div>
                <p className="text-3xl font-bold">{currentCase.hypotheses}</p>
                <p className="text-indigo-200 text-sm">Hypotheses</p>
              </div>
              <div>
                <p className="text-3xl font-bold">{currentCase.assignedAgents.length}</p>
                <p className="text-indigo-200 text-sm">Agents</p>
              </div>
            </div>
          </div>
        </div>
        
        {/* Progress Bar */}
        <div className="mt-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-indigo-200">Case Progress</span>
            <span className="text-sm font-medium">Stage 3 of 8: {currentCase.status.toUpperCase()}</span>
          </div>
          <div className="h-2 bg-indigo-800 rounded-full overflow-hidden">
            <div className="h-full bg-white rounded-full" style={{ width: '37.5%' }}></div>
          </div>
        </div>
      </div>

      {/* Case Lifecycle Pipeline */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <Zap className="w-5 h-5 text-purple-600" />
          <h2 className="text-lg font-semibold text-slate-900">9-State Case Lifecycle</h2>
        </div>
        
        <div className="flex items-center justify-between">
          {orchestrationSteps.map((step, index) => {
            const styles = stepStatusStyles[step.status];
            const isActive = step.status === 'active';
            
            return (
              <div key={step.id} className="flex items-center">
                <div className={`relative flex flex-col items-center ${isActive ? 'animate-pulse-slow' : ''}`}>
                  {/* Step Circle */}
                  <div className={`w-12 h-12 rounded-full border-2 ${styles.border} ${styles.bg} flex items-center justify-center`}>
                    {step.status === 'completed' ? (
                      <CheckCircle className="w-6 h-6 text-green-600" />
                    ) : step.status === 'active' ? (
                      <Play className="w-5 h-5 text-blue-600" />
                    ) : (
                      <span className={`text-lg font-semibold ${styles.text}`}>{index + 1}</span>
                    )}
                  </div>
                  
                  {/* Step Label */}
                  <div className="mt-2 text-center">
                    <p className={`text-sm font-medium ${step.status === 'active' ? 'text-blue-700' : step.status === 'completed' ? 'text-green-700' : 'text-slate-500'}`}>
                      {step.name}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {step.agents.length} agent{step.agents.length > 1 ? 's' : ''}
                    </p>
                  </div>
                  
                  {/* Active indicator */}
                  {isActive && (
                    <div className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 rounded-full animate-ping"></div>
                  )}
                </div>
                
                {/* Connector Arrow */}
                {index < orchestrationSteps.length - 1 && (
                  <ArrowRight className={`w-6 h-6 mx-2 ${
                    step.status === 'completed' ? 'text-green-400' : 'text-slate-300'
                  }`} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-2 gap-6">
        {/* Agent Status Grid */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-indigo-600" />
              <h2 className="text-lg font-semibold text-slate-900">Agent Status</h2>
            </div>
            <span className="text-sm text-slate-500">10 specialized agents</span>
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            {agents.map((agent) => {
              const styles = statusStyles[agent.status];
              
              return (
                <div 
                  key={agent.id}
                  className={`p-3 rounded-lg border ${
                    agent.status === 'processing' ? 'border-blue-200 bg-blue-50' :
                    agent.status === 'completed' ? 'border-green-200 bg-green-50' :
                    agent.status === 'waiting' ? 'border-amber-200 bg-amber-50' :
                    'border-slate-200 bg-slate-50'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xl">{agent.avatar}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-900 truncate">{agent.name}</p>
                      <p className="text-xs text-slate-500 truncate">{agent.role}</p>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${styles.bg} ${styles.text}`}>
                      {agent.status.toUpperCase()}
                    </span>
                    {agent.status === 'processing' && (
                      <div className="flex gap-0.5">
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                        <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Action Timeline */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-emerald-600" />
              <h2 className="text-lg font-semibold text-slate-900">Action Timeline</h2>
            </div>
            <span className="text-sm text-slate-500">{agentActions.length} actions</span>
          </div>
          
          <div className="space-y-4">
            {agentActions.map((action, index) => {
              const isLast = index === agentActions.length - 1;
              
              return (
                <div key={action.id} className="flex gap-4">
                  {/* Timeline line */}
                  <div className="flex flex-col items-center">
                    <div className={`w-3 h-3 rounded-full ${
                      action.status === 'completed' ? 'bg-green-500' :
                      action.status === 'in_progress' ? 'bg-blue-500 animate-pulse' :
                      action.status === 'failed' ? 'bg-red-500' :
                      'bg-slate-300'
                    }`}></div>
                    {!isLast && <div className="w-0.5 h-full bg-slate-200 mt-1"></div>}
                  </div>
                  
                  {/* Action content */}
                  <div className={`flex-1 pb-4 ${!isLast ? 'border-b border-slate-100' : ''}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-semibold text-slate-900">{action.agentName}</span>
                      <span className="text-xs text-slate-400">{action.timestamp}</span>
                    </div>
                    <p className="text-sm text-slate-600 mb-2">{action.action}</p>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                        {action.target}
                      </span>
                      {action.duration && (
                        <span className="text-xs text-slate-400">{action.duration}ms</span>
                      )}
                      <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                        action.status === 'completed' ? 'bg-green-100 text-green-700' :
                        action.status === 'in_progress' ? 'bg-blue-100 text-blue-700' :
                        action.status === 'failed' ? 'bg-red-100 text-red-700' :
                        'bg-slate-100 text-slate-600'
                      }`}>
                        {action.status.replace('_', ' ').toUpperCase()}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Governance & Policy Section */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-5 h-5 text-violet-600" />
          <h2 className="text-lg font-semibold text-slate-900">Governance & Autonomy</h2>
        </div>
        
        <div className="grid grid-cols-4 gap-4">
          <div className="p-4 bg-gradient-to-br from-violet-50 to-purple-50 rounded-lg border border-violet-200">
            <p className="text-xs font-semibold text-violet-600 uppercase tracking-wide mb-2">Autonomy Level</p>
            <p className="text-xl font-bold text-slate-900">{governance.autonomyLevel}</p>
            <p className="text-sm text-slate-500 mt-1">Safe actions auto-approved</p>
          </div>
          
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Policy Checks</p>
            <p className="text-xl font-bold text-green-600">{governance.policyChecks.passed} / {governance.policyChecks.total}</p>
            <p className="text-sm text-slate-500 mt-1">All policies passed</p>
          </div>
          
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Pending Approvals</p>
            <p className="text-xl font-bold text-amber-600">{governance.pendingApprovals}</p>
            <p className="text-sm text-slate-500 mt-1">Awaiting review</p>
          </div>
          
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Audit Entries</p>
            <p className="text-xl font-bold text-slate-900">{governance.auditEntries}</p>
            <p className="text-sm text-slate-500 mt-1">Full trail recorded</p>
          </div>
        </div>
      </div>
    </div>
  );
}
