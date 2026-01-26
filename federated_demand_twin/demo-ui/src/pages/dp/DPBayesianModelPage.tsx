import { useState, useEffect } from 'react';
import { 
  Brain, TrendingUp, Users, Activity, RefreshCw, 
  ArrowUp, ArrowDown, Minus, AlertCircle 
} from 'lucide-react';
import { Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { dpApi, type DPBayesianPageData } from '../../services/dpApi';

export function DPBayesianModelPage() {
  const [data, setData] = useState<DPBayesianPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const pageData = await dpApi.getBayesianPageData();
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
            <p className="text-amber-600 text-sm">Run the demo first to populate the Bayesian model data.</p>
          </div>
        </div>
      </div>
    );
  }

  const predictions = data?.bayesianPredictions || [];
  const parameters = data?.modelParameters || [];
  const nodes = data?.federatedNodes || [];
  const convergenceData = data?.posteriorConvergenceData || [];
  const summary = data?.aggregationSummary || { totalSamples: 0, activeNodes: 0, syncRounds: 0, modelUncertainty: 0 };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Bayesian Demand Model</h1>
          <p className="text-slate-500 mt-1">Probabilistic demand forecasting with uncertainty quantification</p>
        </div>
        <button 
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Predictions Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {predictions.map((pred) => (
          <div key={pred.id} className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-slate-500">{pred.metric}</span>
              <span className={`text-xs px-2 py-1 rounded-full ${
                pred.probability > 0.8 ? 'bg-green-100 text-green-700' :
                pred.probability > 0.5 ? 'bg-amber-100 text-amber-700' :
                'bg-red-100 text-red-700'
              }`}>
                {(pred.probability * 100).toFixed(0)}% conf.
              </span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{pred.predictedValue.toFixed(0)}</p>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-slate-400">
                CI: [{pred.confidenceInterval[0].toFixed(0)}, {pred.confidenceInterval[1].toFixed(0)}]
              </span>
            </div>
            <div className="mt-3 pt-3 border-t border-slate-100">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400">Prior</span>
                <span className="text-slate-600">{pred.priorMean.toFixed(0)}</span>
              </div>
              <div className="flex justify-between text-xs mt-1">
                <span className="text-slate-400">Posterior</span>
                <span className="text-emerald-600 font-medium">{pred.posteriorMean.toFixed(0)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Model Parameters & Convergence */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Model Parameters */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Brain className="w-5 h-5 text-emerald-600" />
            Demand Model Parameters
          </h2>
          <div className="space-y-4">
            {parameters.map((param, idx) => (
              <div key={idx} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
                <span className="text-sm text-slate-600">{param.name}</span>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span className="text-xs text-slate-400 block">Prior</span>
                    <span className="text-sm text-slate-600">{param.prior.toFixed(0)}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-xs text-slate-400 block">Posterior</span>
                    <span className="text-sm font-medium text-emerald-600">{param.posterior.toFixed(0)}</span>
                  </div>
                  <div className="w-6">
                    {param.posterior > param.prior ? (
                      <ArrowUp className="w-4 h-4 text-green-500" />
                    ) : param.posterior < param.prior ? (
                      <ArrowDown className="w-4 h-4 text-red-500" />
                    ) : (
                      <Minus className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Posterior Convergence */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
            Posterior Convergence
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={convergenceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="iteration" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#fff', 
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px'
                  }}
                />
                <Area type="monotone" dataKey="upper" stroke="none" fill="#d1fae5" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="#fff" />
                <Line type="monotone" dataKey="posterior" stroke="#059669" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="prior" stroke="#94a3b8" strokeWidth={1} strokeDasharray="5 5" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Federated Learning Nodes (SKU/Category Sources) */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Users className="w-5 h-5 text-emerald-600" />
          Data Sources (SKU Categories)
        </h2>
        <div className="grid md:grid-cols-3 lg:grid-cols-5 gap-4">
          {nodes.map((node) => (
            <div 
              key={node.id}
              className={`p-4 rounded-lg border ${
                node.status === 'active' ? 'border-green-200 bg-green-50' :
                node.status === 'syncing' ? 'border-amber-200 bg-amber-50' :
                'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-slate-900">{node.name}</span>
                <span className={`w-2 h-2 rounded-full ${
                  node.status === 'active' ? 'bg-green-500' :
                  node.status === 'syncing' ? 'bg-amber-500 animate-pulse' :
                  'bg-slate-400'
                }`} />
              </div>
              <p className="text-xs text-slate-500 mb-2">{node.location}</p>
              <div className="flex justify-between text-xs">
                <span className="text-slate-400">Samples</span>
                <span className="text-slate-600">{node.localSamples.toLocaleString()}</span>
              </div>
              <div className="flex justify-between text-xs mt-1">
                <span className="text-slate-400">Weight</span>
                <span className="text-slate-600">{(node.contribution * 100).toFixed(0)}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Aggregation Summary */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl p-5 text-white">
          <Activity className="w-6 h-6 mb-2 opacity-80" />
          <p className="text-emerald-100 text-sm">Total Samples</p>
          <p className="text-2xl font-bold">{summary.totalSamples.toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <Users className="w-6 h-6 mb-2 text-emerald-600" />
          <p className="text-slate-500 text-sm">Active Sources</p>
          <p className="text-2xl font-bold text-slate-900">{summary.activeNodes}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <RefreshCw className="w-6 h-6 mb-2 text-emerald-600" />
          <p className="text-slate-500 text-sm">Update Rounds</p>
          <p className="text-2xl font-bold text-slate-900">{summary.syncRounds}</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <Brain className="w-6 h-6 mb-2 text-emerald-600" />
          <p className="text-slate-500 text-sm">Model Confidence</p>
          <p className="text-2xl font-bold text-slate-900">{(summary.modelUncertainty * 100).toFixed(0)}%</p>
        </div>
      </div>
    </div>
  );
}
