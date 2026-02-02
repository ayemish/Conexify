import { useState, useEffect } from 'react';
import { 
  Users, CheckCircle, ArrowRight, ArrowDown,
  Shield, Zap, RefreshCw, GitBranch, MessageSquare,
  Network, Activity, Link2, Info, Workflow, Share2
} from 'lucide-react';
import { api, type AutonomousOrchestrationPageData } from '../services/api';

const trackColors: Record<string, { bg: string; border: string; text: string }> = {
  data_quality: { bg: 'bg-blue-50', border: 'border-blue-300', text: 'text-blue-700' },
  analytics: { bg: 'bg-purple-50', border: 'border-purple-300', text: 'text-purple-700' },
  simulation: { bg: 'bg-emerald-50', border: 'border-emerald-300', text: 'text-emerald-700' },
  optimization: { bg: 'bg-amber-50', border: 'border-amber-300', text: 'text-amber-700' },
  governance: { bg: 'bg-rose-50', border: 'border-rose-300', text: 'text-rose-700' },
  communication: { bg: 'bg-cyan-50', border: 'border-cyan-300', text: 'text-cyan-700' },
};

const collaborationTypeStyles: Record<string, { bg: string; text: string; icon: string }> = {
  delegation: { bg: 'bg-blue-100', text: 'text-blue-700', icon: '➡️' },
  information_sharing: { bg: 'bg-green-100', text: 'text-green-700', icon: '📤' },
  consensus_request: { bg: 'bg-purple-100', text: 'text-purple-700', icon: '🤝' },
  parallel_execution: { bg: 'bg-amber-100', text: 'text-amber-700', icon: '⚡' },
  feedback_loop: { bg: 'bg-rose-100', text: 'text-rose-700', icon: '🔄' },
  negotiation: { bg: 'bg-indigo-100', text: 'text-indigo-700', icon: '💬' },
};

const statusStyles = {
  idle: { bg: 'bg-slate-100', text: 'text-slate-600', ring: 'ring-slate-200' },
  pending: { bg: 'bg-slate-100', text: 'text-slate-600', ring: 'ring-slate-200' },
  running: { bg: 'bg-blue-100', text: 'text-blue-700', ring: 'ring-blue-300' },
  completed: { bg: 'bg-green-100', text: 'text-green-700', ring: 'ring-green-300' },
};

export function AutonomousOrchestrationPage() {
  const [data, setData] = useState<AutonomousOrchestrationPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const result = await api.getAutonomousOrchestrationPageData();
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
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  const agents = data?.agents || [];
  const parallelTracks = data?.parallelTracks || [];
  const collaborationEvents = data?.collaborationEvents || [];
  const collaborationGraph = data?.collaborationGraph || { nodes: [], edges: [] };
  const currentCase = data?.currentCase || { 
    id: 'PENDING', title: 'Awaiting Demo', status: 'pending', priority: 'medium', 
    assignedAgents: [], collaborations: 0, parallelTracks: 0, totalTracks: 6, totalBudget: 10000000, confidence: 0 
  };
  const governance = data?.governance || { autonomyLevel: 'PENDING', policyChecks: { passed: 0, total: 0 }, pendingApprovals: 0, auditEntries: 0 };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Autonomous Orchestration data...</span>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl">
        <p className="text-red-700">Error: {error}</p>
        <p className="text-sm text-red-600 mt-2">Make sure the backend is running.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header - Process Focus */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center shadow-lg">
            <Workflow className="w-7 h-7 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-900">Agent Collaboration</h1>
              <span className="px-2 py-0.5 text-xs font-semibold bg-purple-100 text-purple-700 rounded-full uppercase tracking-wide">Process View</span>
            </div>
            <p className="text-slate-500 mt-1">How agents coordinate, delegate, and reach consensus during optimization</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-50 border border-purple-200 rounded-full">
            <Share2 className="w-4 h-4 text-purple-600" />
            <span className="text-sm font-medium text-purple-700">Workflow Visualization</span>
          </div>
          {collaborationEvents.length === 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-full">
              <Info className="w-4 h-4 text-amber-600" />
              <span className="text-sm font-medium text-amber-700">Run demo from Dashboard</span>
            </div>
          )}
        </div>
      </div>

      {/* Active Case Banner */}
      <div className="bg-gradient-to-r from-purple-600 to-indigo-600 p-6 rounded-xl text-white">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Network className="w-5 h-5" />
              <span className="text-purple-200 text-sm font-medium">AGENT COLLABORATION</span>
            </div>
            <h2 className="text-2xl font-bold mb-1">{currentCase.title}</h2>
            <p className="text-purple-200">Run ID: {currentCase.id}</p>
          </div>
          <div className="text-right">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-3xl font-bold">{currentCase.collaborations}</p>
                <p className="text-purple-200 text-sm">Collaborations</p>
              </div>
              <div>
                <p className="text-3xl font-bold">{currentCase.parallelTracks}/{currentCase.totalTracks}</p>
                <p className="text-purple-200 text-sm">Tracks Complete</p>
              </div>
              <div>
                <p className="text-3xl font-bold">{agents.filter(a => a.status === 'completed').length}</p>
                <p className="text-purple-200 text-sm">Agents Active</p>
              </div>
            </div>
          </div>
        </div>
        
        {/* Progress Bar */}
        <div className="mt-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-purple-200">Workflow Progress</span>
            <span className="text-sm font-medium">
              {Math.round((currentCase.parallelTracks / currentCase.totalTracks) * 100)}% Complete
            </span>
          </div>
          <div className="h-2 bg-purple-800 rounded-full overflow-hidden">
            <div 
              className="h-full bg-white rounded-full transition-all duration-500" 
              style={{ width: `${(currentCase.parallelTracks / currentCase.totalTracks) * 100}%` }}
            ></div>
          </div>
        </div>
      </div>

      {/* Parallel Work Tracks */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <GitBranch className="w-5 h-5 text-purple-600" />
          <h2 className="text-lg font-semibold text-slate-900">Parallel Work Tracks</h2>
          <span className="text-sm text-slate-500 ml-2">
            {parallelTracks.filter(t => t.status === 'running').length} running in parallel
          </span>
        </div>
        
        <div className="grid grid-cols-3 gap-4">
          {parallelTracks.map((track) => {
            const colors = trackColors[track.type] || trackColors.data_quality;
            const trackStatus = statusStyles[track.status as keyof typeof statusStyles] || statusStyles.pending;
            const trackAgents = agents.filter(a => track.agents.includes(a.id));
            
            return (
              <div 
                key={track.id}
                className={`p-4 rounded-lg border-2 ${colors.border} ${colors.bg} relative overflow-hidden`}
              >
                {/* Progress bar background */}
                <div 
                  className="absolute bottom-0 left-0 h-1 bg-current opacity-30 transition-all duration-500"
                  style={{ width: `${track.progress * 100}%` }}
                ></div>
                
                <div className="flex items-center justify-between mb-3">
                  <h3 className={`font-semibold ${colors.text}`}>{track.name}</h3>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${trackStatus.bg} ${trackStatus.text}`}>
                    {track.status.toUpperCase()}
                  </span>
                </div>
                
                <div className="flex items-center gap-2 mb-2">
                  {trackAgents.map((agent) => (
                    <div 
                      key={agent.id}
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-lg ${
                        agent.status === 'completed' ? 'bg-green-100 ring-2 ring-green-400' :
                        agent.status === 'processing' ? 'bg-blue-100 ring-2 ring-blue-400 animate-pulse' :
                        'bg-slate-100'
                      }`}
                      title={agent.name}
                    >
                      {agent.avatar}
                    </div>
                  ))}
                </div>
                
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">{trackAgents.length} agent{trackAgents.length > 1 ? 's' : ''}</span>
                  <span className={colors.text}>{Math.round(track.progress * 100)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Two Column Layout: Agent Grid & Collaboration Timeline */}
      <div className="grid grid-cols-2 gap-6">
        {/* Agent Collaboration Network */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-indigo-600" />
              <h2 className="text-lg font-semibold text-slate-900">Agent Network</h2>
            </div>
            <span className="text-sm text-slate-500">{agents.length} agents</span>
          </div>
          
          {/* Simple agent grid with collaboration indicators */}
          <div className="grid grid-cols-4 gap-3">
            {agents.map((agent) => {
              const agentEdges = collaborationGraph.edges.filter(
                e => e.source === agent.id || e.target === agent.id
              );
              const collaborationCount = agentEdges.reduce((sum, e) => sum + e.count, 0);
              
              return (
                <div 
                  key={agent.id}
                  className={`p-3 rounded-lg border text-center transition-all ${
                    agent.status === 'completed' ? 'border-green-200 bg-green-50' :
                    agent.status === 'processing' ? 'border-blue-200 bg-blue-50 animate-pulse' :
                    'border-slate-200 bg-slate-50'
                  }`}
                >
                  <div className="text-2xl mb-1">{agent.avatar}</div>
                  <p className="text-xs font-semibold text-slate-900 truncate">{agent.name}</p>
                  <p className="text-xs text-slate-500">{agent.role}</p>
                  {collaborationCount > 0 && (
                    <div className="mt-1 flex items-center justify-center gap-1">
                      <MessageSquare className="w-3 h-3 text-purple-500" />
                      <span className="text-xs text-purple-600">{collaborationCount}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          
          {/* Collaboration Graph Summary */}
          {collaborationGraph.edges.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-200">
              <p className="text-sm font-medium text-slate-700 mb-2">Active Collaboration Links</p>
              <div className="flex flex-wrap gap-2">
                {collaborationGraph.edges.slice(0, 6).map((edge, idx) => (
                  <div 
                    key={idx}
                    className="flex items-center gap-1 px-2 py-1 bg-purple-50 rounded text-xs"
                  >
                    <span className="font-medium text-purple-700">{edge.source}</span>
                    <ArrowRight className="w-3 h-3 text-purple-400" />
                    <span className="font-medium text-purple-700">{edge.target}</span>
                    <span className="text-purple-500">({edge.count})</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Collaboration Timeline */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-emerald-600" />
              <h2 className="text-lg font-semibold text-slate-900">Collaboration Events</h2>
            </div>
            <span className="text-sm text-slate-500">{collaborationEvents.length} events</span>
          </div>
          
          <div className="space-y-3 max-h-80 overflow-y-auto">
            {collaborationEvents.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No collaboration events yet</p>
                <p className="text-sm">Run the demo to see agent collaboration</p>
              </div>
            ) : (
              collaborationEvents.map((event, index) => {
                const style = collaborationTypeStyles[event.type] || collaborationTypeStyles.information_sharing;
                const isLast = index === collaborationEvents.length - 1;
                
                return (
                  <div key={event.id} className="flex gap-3">
                    {/* Timeline indicator */}
                    <div className="flex flex-col items-center">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm ${style.bg}`}>
                        {style.icon}
                      </div>
                      {!isLast && <div className="w-0.5 h-full bg-slate-200 mt-1"></div>}
                    </div>
                    
                    {/* Event content */}
                    <div className={`flex-1 pb-3 ${!isLast ? 'border-b border-slate-100' : ''}`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${style.bg} ${style.text}`}>
                          {event.type.replace('_', ' ').toUpperCase()}
                        </span>
                        <span className="text-xs text-slate-400">{event.timestamp}</span>
                      </div>
                      <p className="text-sm text-slate-700">
                        <span className="font-semibold">{event.initiator}</span>
                        <ArrowRight className="w-3 h-3 inline mx-1 text-slate-400" />
                        <span className="font-semibold">{event.targets.join(', ')}</span>
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5">{event.topic}</p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Governance & Autonomy Section */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-5 h-5 text-violet-600" />
          <h2 className="text-lg font-semibold text-slate-900">Governance & Autonomy</h2>
        </div>
        
        <div className="grid grid-cols-4 gap-4">
          <div className="p-4 bg-gradient-to-br from-violet-50 to-purple-50 rounded-lg border border-violet-200">
            <p className="text-xs font-semibold text-violet-600 uppercase tracking-wide mb-2">Autonomy Level</p>
            <p className="text-xl font-bold text-slate-900">{governance.autonomyLevel}</p>
            <p className="text-sm text-slate-500 mt-1">Agents self-coordinate</p>
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
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Collaboration Audit</p>
            <p className="text-xl font-bold text-slate-900">{governance.auditEntries}</p>
            <p className="text-sm text-slate-500 mt-1">Events recorded</p>
          </div>
        </div>
      </div>

      {/* Workflow Comparison */}
      <div className="bg-gradient-to-br from-slate-50 to-indigo-50 p-6 rounded-xl border border-indigo-200">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center">
            <Zap className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">Autonomous vs Sequential Workflow</h3>
            <p className="text-slate-600 mb-4">
              This autonomous orchestration runs parallel work tracks with dynamic agent collaboration, 
              compared to the sequential pipeline that executes steps one after another.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <p className="text-sm font-semibold text-purple-700 mb-1">Autonomous Mode</p>
                <ul className="text-xs text-slate-600 space-y-1">
                  <li className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-green-500" /> Parallel work tracks</li>
                  <li className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-green-500" /> Agent collaboration</li>
                  <li className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-green-500" /> Dynamic task routing</li>
                  <li className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-green-500" /> Consensus building</li>
                </ul>
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <p className="text-sm font-semibold text-slate-700 mb-1">Sequential Mode</p>
                <ul className="text-xs text-slate-600 space-y-1">
                  <li className="flex items-center gap-1"><ArrowDown className="w-3 h-3 text-slate-400" /> Fixed step order</li>
                  <li className="flex items-center gap-1"><ArrowDown className="w-3 h-3 text-slate-400" /> One agent at a time</li>
                  <li className="flex items-center gap-1"><ArrowDown className="w-3 h-3 text-slate-400" /> Deterministic flow</li>
                  <li className="flex items-center gap-1"><ArrowDown className="w-3 h-3 text-slate-400" /> Simpler debugging</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
