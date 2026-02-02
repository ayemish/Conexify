import { useState, useMemo } from 'react';
import {
  FlaskConical,
  Plus,
  Play,
  Pause,
  CheckCircle2,
  XCircle,
  Clock,
  Users,
  TrendingUp,
  BarChart3,
  Loader2
} from 'lucide-react';
import { useExperiments, useExperimentActions, Experiment as APIExperiment, ExperimentStatus } from '../services';

// Extended experiment type for UI display
interface ExperimentDisplay {
  id: string;
  name: string;
  description: string;
  status: ExperimentStatus;
  controlModel: string;
  treatmentModel: string;
  trafficSplit: number;
  startDate: string;
  endDate?: string;
  totalPredictions: number;
  controlMetrics: { accuracy: number; latency: number };
  treatmentMetrics: { accuracy: number; latency: number };
  winner?: 'control' | 'treatment' | 'inconclusive';
}

// Transform API experiment to display format
function transformExperiment(apiExp: APIExperiment): ExperimentDisplay {
  const controlVariant = apiExp.variants?.find(v => v.is_control);
  const treatmentVariant = apiExp.variants?.find(v => !v.is_control);
  const totalPredictions = apiExp.variants?.reduce((sum, v) => sum + v.n_predictions, 0) || 0;

  return {
    id: apiExp.experiment_id,
    name: apiExp.experiment_name,
    description: apiExp.description || '',
    status: apiExp.status,
    controlModel: controlVariant?.model_version_id || 'N/A',
    treatmentModel: treatmentVariant?.model_version_id || 'N/A',
    trafficSplit: treatmentVariant?.traffic_percentage || 50,
    startDate: apiExp.created_at,
    totalPredictions,
    controlMetrics: { accuracy: 0.95, latency: 45 }, // Would come from stats endpoint
    treatmentMetrics: { accuracy: 0.96, latency: 42 },
    winner: apiExp.winner_variant_id 
      ? (apiExp.winner_variant_id === controlVariant?.variant_id ? 'control' : 'treatment')
      : undefined,
  };
}

const statusConfig = {
  draft: { color: 'bg-slate-100 text-slate-700', icon: Clock },
  running: { color: 'bg-blue-100 text-blue-700', icon: Play },
  completed: { color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  stopped: { color: 'bg-red-100 text-red-700', icon: XCircle },
};

export function ExperimentsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Fetch experiments from API
  const statusParam = statusFilter !== 'all' ? statusFilter as ExperimentStatus : undefined;
  const { data: apiExperiments, loading, error, refetch } = useExperiments(statusParam);
  
  // Experiment actions
  const { start, conclude, loading: actionLoading } = useExperimentActions();

  // Transform API experiments to display format
  const experiments: ExperimentDisplay[] = useMemo(
    () => (apiExperiments || []).map(transformExperiment),
    [apiExperiments]
  );

  // Compute stats
  const stats = useMemo(() => {
    const running = experiments.filter(e => e.status === 'running').length;
    const completed = experiments.filter(e => e.status === 'completed').length;
    const totalSamples = experiments.reduce((sum, e) => sum + e.totalPredictions, 0);
    return { running, completed, totalSamples };
  }, [experiments]);

  // Handle start experiment
  const handleStart = async (experimentId: string) => {
    try {
      await start(experimentId, 'current-user');
      refetch();
    } catch (err) {
      console.error('Failed to start experiment:', err);
    }
  };

  // Handle conclude experiment
  const handleConclude = async (experimentId: string, promoteWinner = false) => {
    try {
      await conclude(experimentId, 'current-user', promoteWinner);
      refetch();
    } catch (err) {
      console.error('Failed to conclude experiment:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">A/B Experiments</h1>
          <p className="text-slate-500 mt-1">Compare model performance with controlled experiments</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
          <Plus className="w-4 h-4" />
          New Experiment
        </button>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-orange-600 animate-spin" />
          <span className="ml-2 text-slate-600">Loading experiments...</span>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700">Failed to load experiments: {error.message}</p>
          <button onClick={() => refetch()} className="mt-2 text-sm text-red-600 underline">
            Retry
          </button>
        </div>
      )}

      {/* Stats Overview */}
      {!loading && !error && (
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <Play className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{stats.running}</p>
              <p className="text-sm text-slate-500">Running</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{stats.completed}</p>
              <p className="text-sm text-slate-500">Completed</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <Users className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {stats.totalSamples >= 1000 ? `${(stats.totalSamples / 1000).toFixed(0)}K` : stats.totalSamples}
              </p>
              <p className="text-sm text-slate-500">Total Samples</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{experiments.length}</p>
              <p className="text-sm text-slate-500">Total Experiments</p>
            </div>
          </div>
        </div>
      </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-2">
        {['all', 'running', 'completed', 'stopped', 'draft'].map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors capitalize ${
              statusFilter === status
                ? 'bg-orange-100 text-orange-700 font-medium'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {status}
          </button>
        ))}
      </div>

      {/* Experiments List */}
      {!loading && !error && (
      <div className="space-y-4">
        {experiments.map((experiment) => {
          const StatusIcon = statusConfig[experiment.status].icon;
          return (
            <div key={experiment.id} className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center">
                    <FlaskConical className="w-6 h-6 text-purple-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900">{experiment.name}</h3>
                    <p className="text-sm text-slate-500">{experiment.description}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded capitalize ${statusConfig[experiment.status].color}`}>
                    <StatusIcon className="w-3 h-3" />
                    {experiment.status}
                  </span>
                  {experiment.status === 'running' && (
                    <button className="p-2 hover:bg-slate-100 rounded-lg">
                      <Pause className="w-4 h-4 text-slate-500" />
                    </button>
                  )}
                </div>
              </div>

              {/* Experiment Details */}
              <div className="grid grid-cols-2 gap-6 mb-4">
                {/* Control */}
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium text-slate-700">Control</span>
                    <span className="text-xs text-slate-500">{100 - experiment.trafficSplit}% traffic</span>
                  </div>
                  <p className="text-sm text-slate-900 mb-3">{experiment.controlModel}</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-xs text-slate-500">Accuracy</p>
                      <p className="text-lg font-semibold text-slate-900">
                        {(experiment.controlMetrics.accuracy * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Latency</p>
                      <p className="text-lg font-semibold text-slate-900">
                        {experiment.controlMetrics.latency}ms
                      </p>
                    </div>
                  </div>
                </div>

                {/* Treatment */}
                <div className={`rounded-lg p-4 ${
                  experiment.winner === 'treatment' ? 'bg-green-50 border border-green-200' : 'bg-slate-50'
                }`}>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium text-slate-700">Treatment</span>
                    <span className="text-xs text-slate-500">{experiment.trafficSplit}% traffic</span>
                  </div>
                  <p className="text-sm text-slate-900 mb-3">{experiment.treatmentModel}</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-xs text-slate-500">Accuracy</p>
                      <p className={`text-lg font-semibold ${
                        experiment.treatmentMetrics.accuracy > experiment.controlMetrics.accuracy
                          ? 'text-green-600' : 'text-slate-900'
                      }`}>
                        {(experiment.treatmentMetrics.accuracy * 100).toFixed(1)}%
                        {experiment.treatmentMetrics.accuracy > experiment.controlMetrics.accuracy && (
                          <span className="text-xs ml-1">
                            (+{((experiment.treatmentMetrics.accuracy - experiment.controlMetrics.accuracy) * 100).toFixed(1)}%)
                          </span>
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Latency</p>
                      <p className={`text-lg font-semibold ${
                        experiment.treatmentMetrics.latency < experiment.controlMetrics.latency
                          ? 'text-green-600' : 'text-slate-900'
                      }`}>
                        {experiment.treatmentMetrics.latency}ms
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                <div className="flex items-center gap-4 text-sm text-slate-500">
                  <span className="flex items-center gap-1">
                    <Clock className="w-4 h-4" />
                    Started {new Date(experiment.startDate).toLocaleDateString()}
                  </span>
                  <span className="flex items-center gap-1">
                    <BarChart3 className="w-4 h-4" />
                    {experiment.totalPredictions.toLocaleString()} predictions
                  </span>
                </div>
                {experiment.winner && (
                  <span className={`px-2 py-1 text-xs font-medium rounded ${
                    experiment.winner === 'treatment' ? 'bg-green-100 text-green-700' :
                    experiment.winner === 'control' ? 'bg-blue-100 text-blue-700' :
                    'bg-slate-100 text-slate-700'
                  }`}>
                    Winner: {experiment.winner}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
      )}
    </div>
  );
}
