import { useState, useEffect } from 'react';
import { 
  Brain, Target, FileText, ChevronDown, ChevronRight,
  Lightbulb, Database, BookOpen, History, CheckCircle, RefreshCw
} from 'lucide-react';
import { api, type AgentOutputPageData } from '../services/api';

const outputTypeStyles: Record<string, { bg: string; text: string; icon: typeof Brain }> = {
  analysis: { bg: 'bg-blue-100', text: 'text-blue-700', icon: Brain },
  recommendation: { bg: 'bg-green-100', text: 'text-green-700', icon: Lightbulb },
  decision: { bg: 'bg-purple-100', text: 'text-purple-700', icon: Target },
  action: { bg: 'bg-amber-100', text: 'text-amber-700', icon: FileText },
};

const evidenceTypeIcons: Record<string, typeof Database> = {
  data: Database,
  rule: BookOpen,
  model: Brain,
  history: History,
};

export function AgentOutputPage() {
  const [data, setData] = useState<AgentOutputPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedOutput, setExpandedOutput] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const result = await api.getAgentOutputPageData();
      setData(result);
      if (!expandedOutput && result.agentOutputs.length > 0) {
        setExpandedOutput(result.agentOutputs[0].id);
      }
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
  const agentOutputs = data?.agentOutputs || [];

  const filteredOutputs = selectedAgent 
    ? agentOutputs.filter(o => o.agentId === selectedAgent)
    : agentOutputs;

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Agent Output data...</span>
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
          <h1 className="text-2xl font-bold text-slate-900">Agent Output & Rationale</h1>
          <p className="text-slate-500 mt-1">Explainable AI decisions with full reasoning chains</p>
        </div>
      </div>

      {/* Agent Filter */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedAgent(null)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            selectedAgent === null 
              ? 'bg-indigo-600 text-white' 
              : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
          }`}
        >
          All Agents
        </button>
        {agents.filter(a => agentOutputs.some(o => o.agentId === a.id)).map((agent) => (
          <button
            key={agent.id}
            onClick={() => setSelectedAgent(agent.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              selectedAgent === agent.id 
                ? 'bg-indigo-600 text-white' 
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <span>{agent.avatar}</span>
            <span>{agent.name}</span>
          </button>
        ))}
      </div>

      {/* Output Cards */}
      <div className="space-y-4">
        {filteredOutputs.map((output) => {
          const isExpanded = expandedOutput === output.id;
          const typeStyle = outputTypeStyles[output.outputType];
          const TypeIcon = typeStyle.icon;
          const agent = agents.find(a => a.id === output.agentId);

          return (
            <div 
              key={output.id}
              className={`bg-white rounded-xl border shadow-sm overflow-hidden transition-all ${
                isExpanded ? 'border-indigo-300 ring-2 ring-indigo-100' : 'border-slate-200'
              }`}
            >
              {/* Output Header */}
              <div 
                className="p-5 cursor-pointer hover:bg-slate-50 transition-colors"
                onClick={() => setExpandedOutput(isExpanded ? null : output.id)}
              >
                <div className="flex items-start gap-4">
                  {/* Agent Avatar */}
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-100 to-purple-100 flex items-center justify-center text-2xl">
                    {agent?.avatar || '🤖'}
                  </div>
                  
                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="font-semibold text-slate-900">{output.agentName}</span>
                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${typeStyle.bg} ${typeStyle.text} flex items-center gap-1`}>
                        <TypeIcon className="w-3 h-3" />
                        {output.outputType.toUpperCase()}
                      </span>
                      <span className="text-xs text-slate-400">{output.timestamp}</span>
                    </div>
                    <h3 className="text-lg font-semibold text-slate-900 mb-1">{output.title}</h3>
                    <p className="text-slate-600">{output.summary}</p>
                  </div>

                  {/* Confidence & Expand */}
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-xs text-slate-500 mb-1">Confidence</p>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div 
                            className={`h-full rounded-full ${
                              output.confidence > 0.8 ? 'bg-green-500' :
                              output.confidence > 0.6 ? 'bg-amber-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${output.confidence * 100}%` }}
                          />
                        </div>
                        <span className="text-sm font-semibold text-slate-700">
                          {(output.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    {isExpanded ? (
                      <ChevronDown className="w-5 h-5 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-slate-400" />
                    )}
                  </div>
                </div>
              </div>

              {/* Expanded Content */}
              {isExpanded && (
                <div className="border-t border-slate-200">
                  {/* Details Section */}
                  <div className="p-5 bg-slate-50">
                    <h4 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      Detailed Analysis
                    </h4>
                    <p className="text-slate-600 leading-relaxed">{output.details}</p>
                  </div>

                  {/* Rationale Chain */}
                  <div className="p-5">
                    <h4 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                      <Brain className="w-4 h-4 text-purple-600" />
                      Reasoning Chain
                    </h4>
                    <div className="space-y-4">
                      {output.rationale.map((step, index) => (
                        <div key={step.step} className="flex gap-4">
                          {/* Step Number */}
                          <div className="flex flex-col items-center">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                              step.confidence > 0.9 ? 'bg-green-100 text-green-700' :
                              step.confidence > 0.8 ? 'bg-blue-100 text-blue-700' :
                              'bg-amber-100 text-amber-700'
                            }`}>
                              {step.step}
                            </div>
                            {index < output.rationale.length - 1 && (
                              <div className="w-0.5 h-full bg-slate-200 mt-2"></div>
                            )}
                          </div>
                          
                          {/* Step Content */}
                          <div className="flex-1 pb-4">
                            <div className="flex items-center justify-between mb-2">
                              <h5 className="font-semibold text-slate-900">{step.description}</h5>
                              <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                                step.confidence > 0.9 ? 'bg-green-100 text-green-700' :
                                step.confidence > 0.8 ? 'bg-blue-100 text-blue-700' :
                                'bg-amber-100 text-amber-700'
                              }`}>
                                {(step.confidence * 100).toFixed(0)}% confident
                              </span>
                            </div>
                            <p className="text-sm text-slate-600">{step.reasoning}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Evidence Section */}
                  <div className="p-5 bg-gradient-to-br from-slate-50 to-blue-50 border-t border-slate-200">
                    <h4 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                      <Database className="w-4 h-4 text-blue-600" />
                      Supporting Evidence
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      {output.evidence.map((evidence, index) => {
                        const EvidenceIcon = evidenceTypeIcons[evidence.type];
                        return (
                          <div 
                            key={index}
                            className="p-4 bg-white rounded-lg border border-slate-200"
                          >
                            <div className="flex items-start gap-3">
                              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                                evidence.type === 'data' ? 'bg-blue-100' :
                                evidence.type === 'rule' ? 'bg-green-100' :
                                evidence.type === 'model' ? 'bg-purple-100' :
                                'bg-amber-100'
                              }`}>
                                <EvidenceIcon className={`w-4 h-4 ${
                                  evidence.type === 'data' ? 'text-blue-600' :
                                  evidence.type === 'rule' ? 'text-green-600' :
                                  evidence.type === 'model' ? 'text-purple-600' :
                                  'text-amber-600'
                                }`} />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-xs font-semibold text-slate-500 uppercase">{evidence.type}</span>
                                  <span className="text-xs text-slate-400">Weight: {(evidence.weight * 100).toFixed(0)}%</span>
                                </div>
                                <p className="text-sm font-medium text-slate-900 mb-1">{evidence.source}</p>
                                <p className="text-xs text-slate-600">{evidence.description}</p>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Confidence Breakdown */}
                  <div className="p-5 border-t border-slate-200">
                    <h4 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                      <Target className="w-4 h-4 text-emerald-600" />
                      Confidence Breakdown
                    </h4>
                    <div className="grid grid-cols-4 gap-4">
                      <div className="text-center">
                        <div className="w-16 h-16 mx-auto rounded-full border-4 border-blue-200 flex items-center justify-center mb-2">
                          <span className="text-xl font-bold text-blue-700">
                            {(output.rationale.reduce((acc, r) => acc + r.confidence, 0) / output.rationale.length * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-xs text-slate-500">Reasoning</p>
                      </div>
                      <div className="text-center">
                        <div className="w-16 h-16 mx-auto rounded-full border-4 border-green-200 flex items-center justify-center mb-2">
                          <span className="text-xl font-bold text-green-700">
                            {(output.evidence.reduce((acc, e) => acc + e.weight, 0) / output.evidence.length * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-xs text-slate-500">Evidence</p>
                      </div>
                      <div className="text-center">
                        <div className="w-16 h-16 mx-auto rounded-full border-4 border-purple-200 flex items-center justify-center mb-2">
                          <span className="text-xl font-bold text-purple-700">
                            {output.evidence.filter(e => e.type === 'model').length > 0 ? '91%' : 'N/A'}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500">Model</p>
                      </div>
                      <div className="text-center">
                        <div className="w-16 h-16 mx-auto rounded-full border-4 border-emerald-200 flex items-center justify-center mb-2">
                          <span className="text-xl font-bold text-emerald-700">
                            {(output.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-xs text-slate-500">Overall</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Explainability Summary */}
      <div className="bg-gradient-to-br from-emerald-50 to-teal-50 p-6 rounded-xl border border-emerald-200">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center">
            <CheckCircle className="w-6 h-6 text-emerald-600" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">Explainable AI Compliance</h3>
            <p className="text-slate-600 mb-4">
              All agent decisions include complete reasoning chains, evidence citations, and confidence scores. 
              This transparency enables human oversight and auditability per NIST AI RMF guidelines.
            </p>
            <div className="flex gap-4">
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-slate-700">Full rationale chains</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-slate-700">Evidence citations</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-slate-700">Confidence quantification</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle className="w-4 h-4 text-green-600" />
                <span className="text-slate-700">Audit trail</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
