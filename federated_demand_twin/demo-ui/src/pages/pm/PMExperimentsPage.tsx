import { useState } from 'react';
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
  BarChart3
} from 'lucide-react';

interface Experiment {
  id: string;
  name: string;
  description: string;
  status: 'draft' | 'running' | 'completed' | 'stopped';
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

const mockExperiments: Experiment[] = [
  {
    id: 'exp-001',
    name: 'Anomaly Detection v2.1 vs v2.0',
    description: 'Testing improved feature engineering in production',
    status: 'running',
    controlModel: 'anomaly_detection v2.0.0',
    treatmentModel: 'anomaly_detection v2.1.0',
    trafficSplit: 20,
    startDate: '2024-01-20T00:00:00Z',
    totalPredictions: 45231,
    controlMetrics: { accuracy: 0.948, latency: 45 },
    treatmentMetrics: { accuracy: 0.962, latency: 42 },
  },
  {
    id: 'exp-002',
    name: 'RUL Transformer vs LSTM',
    description: 'Comparing transformer architecture for RUL estimation',
    status: 'completed',
    controlModel: 'rul_estimation v2.5.0',
    treatmentModel: 'rul_estimation v3.0.0-beta',
    trafficSplit: 50,
    startDate: '2024-01-10T00:00:00Z',
    endDate: '2024-01-18T00:00:00Z',
    totalPredictions: 128450,
    controlMetrics: { accuracy: 0.891, latency: 52 },
    treatmentMetrics: { accuracy: 0.912, latency: 48 },
    winner: 'treatment',
  },
  {
    id: 'exp-003',
    name: 'Failure Prediction Hyperparameter Tuning',
    description: 'Testing optimized hyperparameters for failure prediction',
    status: 'stopped',
    controlModel: 'failure_prediction v1.2.0',
    treatmentModel: 'failure_prediction v1.3.0-rc1',
    trafficSplit: 10,
    startDate: '2024-01-05T00:00:00Z',
    endDate: '2024-01-08T00:00:00Z',
    totalPredictions: 23100,
    controlMetrics: { accuracy: 0.923, latency: 38 },
    treatmentMetrics: { accuracy: 0.918, latency: 41 },
    winner: 'inconclusive',
  },
];

const statusConfig = {
  draft: { color: 'bg-slate-100 text-slate-700', icon: Clock },
  running: { color: 'bg-blue-100 text-blue-700', icon: Play },
  completed: { color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  stopped: { color: 'bg-red-100 text-red-700', icon: XCircle },
};

export function PMExperimentsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const filteredExperiments = mockExperiments.filter(exp => 
    statusFilter === 'all' || exp.status === statusFilter
  );

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

      {/* Stats Overview */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
              <Play className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">1</p>
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
              <p className="text-2xl font-bold text-slate-900">1</p>
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
              <p className="text-2xl font-bold text-slate-900">196K</p>
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
              <p className="text-2xl font-bold text-slate-900">+1.4%</p>
              <p className="text-sm text-slate-500">Avg Improvement</p>
            </div>
          </div>
        </div>
      </div>

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
      <div className="space-y-4">
        {filteredExperiments.map((experiment) => {
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
    </div>
  );
}
