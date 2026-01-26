import { useState, useEffect } from 'react';
import { 
  Line, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, Area, AreaChart, BarChart, Bar
} from 'recharts';
import { TrendingUp, Target, Layers, GitBranch, AlertTriangle, CheckCircle, RefreshCw } from 'lucide-react';
import { api, type BayesianPageData } from '../services/api';

export function BayesianModelPage() {
  const [data, setData] = useState<BayesianPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const result = await api.getBayesianPageData();
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

  const bayesianPredictions = data?.bayesianPredictions || [];
  const modelParameters = data?.modelParameters || [];
  const federatedNodes = data?.federatedNodes || [];
  const posteriorConvergenceData = data?.posteriorConvergenceData || [];
  const aggregationSummary = data?.aggregationSummary || { totalSamples: 0, activeNodes: 0, syncRounds: 0, modelUncertainty: 0 };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Bayesian model data...</span>
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
          <h1 className="text-2xl font-bold text-slate-900">Media Elasticity Model</h1>
          <p className="text-slate-500 mt-1">Bayesian elasticity estimation with cross-retailer learning</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-500">Last update:</span>
          <span className="font-medium text-slate-700">15:32:45 UTC</span>
        </div>
      </div>

      {/* Key Predictions Grid */}
      <div className="grid grid-cols-4 gap-4">
        {bayesianPredictions.map((pred) => (
          <div 
            key={pred.id} 
            className={`p-5 bg-white rounded-xl border shadow-sm ${
              pred.probability > 0.7 && pred.metric.includes('Failure') 
                ? 'border-red-200 bg-gradient-to-br from-white to-red-50' 
                : 'border-slate-200'
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                {pred.metric.split(' ')[0]}
              </span>
              {pred.probability > 0.7 && pred.metric.includes('Failure') ? (
                <AlertTriangle className="w-4 h-4 text-red-500" />
              ) : (
                <CheckCircle className="w-4 h-4 text-green-500" />
              )}
            </div>
            <p className="text-3xl font-bold text-slate-900 mb-1">
              {pred.metric.includes('Probability') 
                ? `${(pred.predictedValue * 100).toFixed(0)}%`
                : pred.predictedValue.toLocaleString()}
            </p>
            <p className="text-sm text-slate-600 mb-3">{pred.metric}</p>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div 
                  className={`h-full rounded-full ${
                    pred.probability > 0.8 ? 'bg-green-500' : 
                    pred.probability > 0.6 ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${pred.probability * 100}%` }}
                />
              </div>
              <span className="text-xs text-slate-500">{(pred.probability * 100).toFixed(0)}% conf</span>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              CI: [{pred.confidenceInterval[0].toFixed(1)}, {pred.confidenceInterval[1].toFixed(1)}]
            </p>
          </div>
        ))}
      </div>

      {/* Main Charts Row */}
      <div className="grid grid-cols-2 gap-6">
        {/* Posterior Convergence */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-semibold text-slate-900">Posterior Convergence</h2>
          </div>
          <p className="text-sm text-slate-500 mb-4">
            Media elasticity estimates updating as cross-retailer evidence accumulates
          </p>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={posteriorConvergenceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="iteration" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis 
                  domain={[0, 1]} 
                  tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  tick={{ fontSize: 12 }} 
                  stroke="#94a3b8"
                />
                <Tooltip 
                  formatter={(value) => [`${((value as number) * 100).toFixed(1)}%`, '']}
                  labelFormatter={(label) => `Iteration ${label}`}
                />
                <Area 
                  type="monotone" 
                  dataKey="upper" 
                  stroke="transparent" 
                  fill="#dbeafe" 
                  fillOpacity={0.5}
                />
                <Area 
                  type="monotone" 
                  dataKey="lower" 
                  stroke="transparent" 
                  fill="#ffffff" 
                />
                <Line 
                  type="monotone" 
                  dataKey="prior" 
                  stroke="#94a3b8" 
                  strokeDasharray="5 5" 
                  strokeWidth={2}
                  dot={false}
                  name="Prior"
                />
                <Line 
                  type="monotone" 
                  dataKey="posterior" 
                  stroke="#2563eb" 
                  strokeWidth={3}
                  dot={false}
                  name="Posterior"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="flex items-center justify-center gap-6 mt-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-0.5 bg-slate-400" style={{ backgroundImage: 'repeating-linear-gradient(90deg, #94a3b8 0, #94a3b8 5px, transparent 5px, transparent 10px)' }}></div>
              <span className="text-sm text-slate-600">Prior Elasticity</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-1 bg-blue-600 rounded"></div>
              <span className="text-sm text-slate-600">Posterior Elasticity</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-3 bg-blue-100 rounded"></div>
              <span className="text-sm text-slate-600">95% Credible Interval</span>
            </div>
          </div>
        </div>

        {/* Model Parameters */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-5 h-5 text-indigo-600" />
            <h2 className="text-lg font-semibold text-slate-900">Model Parameters</h2>
          </div>
          <p className="text-sm text-slate-500 mb-4">
            ROAS and elasticity parameter estimates with Bayesian updating
          </p>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart 
                data={modelParameters} 
                layout="vertical"
                margin={{ left: 80 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} stroke="#94a3b8" width={75} />
                <Tooltip />
                <Bar dataKey="prior" fill="#cbd5e1" name="Prior" barSize={12} />
                <Bar dataKey="posterior" fill="#3b82f6" name="Posterior" barSize={12} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 space-y-2">
            {modelParameters.slice(0, 2).map((param) => (
              <div key={param.name} className="flex items-center justify-between text-sm">
                <span className="text-slate-600">{param.name}</span>
                <span className="text-slate-500">
                  95% CI: [{param.credibleInterval[0].toFixed(3)}, {param.credibleInterval[1].toFixed(3)}]
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Federated Learning Nodes */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-purple-600" />
            <h2 className="text-lg font-semibold text-slate-900">Federated Learning Nodes</h2>
          </div>
          <div className="flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-slate-400" />
            <span className="text-sm text-slate-500">Privacy-preserving aggregation active</span>
          </div>
        </div>
        
        <div className="grid grid-cols-4 gap-4">
          {federatedNodes.map((node) => (
            <div 
              key={node.id}
              className={`p-4 rounded-lg border ${
                node.status === 'active' ? 'border-green-200 bg-green-50' :
                node.status === 'syncing' ? 'border-blue-200 bg-blue-50' :
                'border-slate-200 bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className={`w-2 h-2 rounded-full ${
                  node.status === 'active' ? 'bg-green-500' :
                  node.status === 'syncing' ? 'bg-blue-500 animate-pulse' :
                  'bg-slate-400'
                }`}></span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                  node.status === 'active' ? 'bg-green-100 text-green-700' :
                  node.status === 'syncing' ? 'bg-blue-100 text-blue-700' :
                  'bg-slate-100 text-slate-600'
                }`}>
                  {node.status.toUpperCase()}
                </span>
              </div>
              <h3 className="font-semibold text-slate-900 mb-1">{node.name}</h3>
              <p className="text-xs text-slate-500 mb-3">{node.location}</p>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Samples</span>
                  <span className="font-medium text-slate-700">{node.localSamples.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Contribution</span>
                  <span className="font-medium text-slate-700">{(node.contribution * 100).toFixed(0)}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Last Sync</span>
                  <span className="text-slate-600">{node.lastSync}</span>
                </div>
              </div>
              {/* Contribution bar */}
              <div className="mt-3 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                <div 
                  className={`h-full rounded-full ${
                    node.status === 'active' ? 'bg-green-500' :
                    node.status === 'syncing' ? 'bg-blue-500' :
                    'bg-slate-400'
                  }`}
                  style={{ width: `${node.contribution * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* Aggregation Summary */}
        <div className="mt-6 p-4 bg-slate-50 rounded-lg">
          <div className="grid grid-cols-4 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-slate-900">{aggregationSummary.totalSamples.toLocaleString()}</p>
              <p className="text-sm text-slate-500">Total Samples</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{aggregationSummary.activeNodes}</p>
              <p className="text-sm text-slate-500">Active Nodes</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{aggregationSummary.syncRounds}</p>
              <p className="text-sm text-slate-500">Sync Rounds</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-green-600">{aggregationSummary.modelUncertainty.toFixed(2)}</p>
              <p className="text-sm text-slate-500">Model Uncertainty</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
