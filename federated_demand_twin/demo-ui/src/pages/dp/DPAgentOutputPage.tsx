import { useState, useEffect } from 'react';
import { 
  MessageSquare, CheckCircle, AlertTriangle, RefreshCw, 
  ChevronDown, ChevronUp, FileText, Database, Zap, AlertCircle
} from 'lucide-react';
import { dpApi, type DPAgentOutputPageData } from '../../services/dpApi';

export function DPAgentOutputPage() {
  const [data, setData] = useState<DPAgentOutputPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedOutput, setExpandedOutput] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const pageData = await dpApi.getAgentOutputPageData();
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
            <p className="text-amber-600 text-sm">Run the demo first to see agent outputs.</p>
          </div>
        </div>
      </div>
    );
  }

  const outputs = data?.agentOutputs || [];
  const agents = data?.agents || [];

  const getOutputTypeIcon = (type: string) => {
    switch (type) {
      case 'analysis': return <FileText className="w-5 h-5 text-blue-500" />;
      case 'recommendation': return <Zap className="w-5 h-5 text-amber-500" />;
      case 'decision': return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'action': return <AlertTriangle className="w-5 h-5 text-purple-500" />;
      default: return <MessageSquare className="w-5 h-5 text-slate-500" />;
    }
  };

  const getOutputTypeBadge = (type: string) => {
    const styles: Record<string, string> = {
      analysis: 'bg-blue-100 text-blue-700',
      recommendation: 'bg-amber-100 text-amber-700',
      decision: 'bg-green-100 text-green-700',
      action: 'bg-purple-100 text-purple-700',
    };
    return styles[type] || 'bg-slate-100 text-slate-700';
  };

  const getEvidenceIcon = (type: string) => {
    switch (type) {
      case 'data': return <Database className="w-4 h-4" />;
      case 'model': return <Zap className="w-4 h-4" />;
      case 'rule': return <FileText className="w-4 h-4" />;
      default: return <FileText className="w-4 h-4" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Procurement Decisions & Rationale</h1>
          <p className="text-slate-500 mt-1">Order recommendations with full reasoning chains and evidence</p>
        </div>
        <button 
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Agent Status Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
        <div className="flex items-center gap-4 overflow-x-auto pb-2">
          {agents.map((agent) => (
            <div 
              key={agent.id}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border flex-shrink-0 ${
                agent.status === 'completed' ? 'border-green-200 bg-green-50' :
                agent.status === 'processing' ? 'border-emerald-200 bg-emerald-50' :
                'border-slate-200 bg-slate-50'
              }`}
            >
              <span className="text-lg">{agent.avatar}</span>
              <span className="text-sm font-medium text-slate-700">{agent.name}</span>
              {agent.status === 'completed' && <CheckCircle className="w-4 h-4 text-green-500" />}
            </div>
          ))}
        </div>
      </div>

      {/* Agent Outputs */}
      <div className="space-y-4">
        {outputs.map((output) => (
          <div 
            key={output.id}
            className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden"
          >
            {/* Output Header */}
            <div 
              className="p-4 cursor-pointer hover:bg-slate-50 transition-colors"
              onClick={() => setExpandedOutput(expandedOutput === output.id ? null : output.id)}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  {getOutputTypeIcon(output.outputType)}
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-slate-900">{output.title}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${getOutputTypeBadge(output.outputType)}`}>
                        {output.outputType}
                      </span>
                    </div>
                    <p className="text-sm text-slate-500 mt-1">{output.agentName} • {output.timestamp}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <span className="text-sm font-medium text-slate-900">{(output.confidence * 100).toFixed(0)}%</span>
                    <p className="text-xs text-slate-500">confidence</p>
                  </div>
                  {expandedOutput === output.id ? (
                    <ChevronUp className="w-5 h-5 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-slate-400" />
                  )}
                </div>
              </div>
              <p className="text-sm text-slate-600 mt-2">{output.summary}</p>
            </div>

            {/* Expanded Content */}
            {expandedOutput === output.id && (
              <div className="border-t border-slate-200">
                {/* Details */}
                <div className="p-4 bg-slate-50">
                  <h4 className="text-sm font-semibold text-slate-700 mb-2">Details</h4>
                  <p className="text-sm text-slate-600 whitespace-pre-wrap">{output.details}</p>
                </div>

                {/* Reasoning Chain */}
                <div className="p-4 border-t border-slate-200">
                  <h4 className="text-sm font-semibold text-slate-700 mb-3">Reasoning Chain</h4>
                  <div className="space-y-3">
                    {output.rationale.map((step, idx) => (
                      <div key={idx} className="flex gap-3">
                        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-medium">
                          {step.step}
                        </div>
                        <div className="flex-1">
                          <p className="text-sm font-medium text-slate-900">{step.description}</p>
                          <p className="text-sm text-slate-500 mt-0.5">{step.reasoning}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <div className="h-1.5 w-20 bg-slate-200 rounded-full overflow-hidden">
                              <div 
                                className="h-full bg-emerald-500 rounded-full"
                                style={{ width: `${step.confidence * 100}%` }}
                              />
                            </div>
                            <span className="text-xs text-slate-400">{(step.confidence * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Evidence */}
                {output.evidence.length > 0 && (
                  <div className="p-4 border-t border-slate-200 bg-slate-50">
                    <h4 className="text-sm font-semibold text-slate-700 mb-3">Supporting Evidence</h4>
                    <div className="grid md:grid-cols-2 gap-3">
                      {output.evidence.map((ev, idx) => (
                        <div key={idx} className="flex items-start gap-2 p-3 bg-white rounded-lg border border-slate-200">
                          <div className="text-slate-400">
                            {getEvidenceIcon(ev.type)}
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium text-slate-900">{ev.source}</span>
                              <span className="text-xs text-slate-400">{(ev.weight * 100).toFixed(0)}% weight</span>
                            </div>
                            <p className="text-xs text-slate-500 mt-0.5">{ev.description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
