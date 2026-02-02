import { useState } from 'react';
import {
  Database,
  Plus,
  Search,
  Filter,
  MoreVertical,
  Clock,
  AlertTriangle,
  ArrowUpRight,
  GitBranch,
  Tag
} from 'lucide-react';

interface ModelVersion {
  id: string;
  name: string;
  version: string;
  stage: 'development' | 'staging' | 'production' | 'archived';
  modelType: string;
  accuracy: number;
  f1Score: number;
  aucRoc: number;
  createdAt: string;
  createdBy: string;
  description: string;
  canRollbackTo: string[];
}

const mockModels: ModelVersion[] = [
  {
    id: 'ad-v2.1.0',
    name: 'anomaly_detection',
    version: '2.1.0',
    stage: 'production',
    modelType: 'Anomaly Detection',
    accuracy: 0.962,
    f1Score: 0.945,
    aucRoc: 0.978,
    createdAt: '2024-01-15T10:30:00Z',
    createdBy: 'ml-pipeline',
    description: 'Production anomaly detection model with improved feature engineering',
    canRollbackTo: ['ad-v2.0.0', 'ad-v1.9.0'],
  },
  {
    id: 'fp-v1.3.0',
    name: 'failure_prediction',
    version: '1.3.0',
    stage: 'production',
    modelType: 'Failure Prediction',
    accuracy: 0.941,
    f1Score: 0.923,
    aucRoc: 0.956,
    createdAt: '2024-01-10T14:20:00Z',
    createdBy: 'data-science',
    description: 'Equipment failure prediction with 24h horizon',
    canRollbackTo: ['fp-v1.2.0'],
  },
  {
    id: 'rul-v3.0.0',
    name: 'rul_estimation',
    version: '3.0.0-beta',
    stage: 'staging',
    modelType: 'RUL Estimation',
    accuracy: 0.912,
    f1Score: 0.891,
    aucRoc: 0.934,
    createdAt: '2024-01-20T09:15:00Z',
    createdBy: 'ml-pipeline',
    description: 'Remaining useful life estimation using transformer architecture',
    canRollbackTo: [],
  },
  {
    id: 'ad-v2.0.0',
    name: 'anomaly_detection',
    version: '2.0.0',
    stage: 'archived',
    modelType: 'Anomaly Detection',
    accuracy: 0.948,
    f1Score: 0.931,
    aucRoc: 0.962,
    createdAt: '2024-01-05T08:00:00Z',
    createdBy: 'ml-pipeline',
    description: 'Previous production version',
    canRollbackTo: [],
  },
];

const stageColors = {
  development: 'bg-slate-100 text-slate-700',
  staging: 'bg-amber-100 text-amber-700',
  production: 'bg-green-100 text-green-700',
  archived: 'bg-slate-100 text-slate-500',
};

export function PMModelsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [selectedModel, setSelectedModel] = useState<ModelVersion | null>(null);

  const filteredModels = mockModels.filter(model => {
    const matchesSearch = model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         model.version.includes(searchQuery);
    const matchesStage = stageFilter === 'all' || model.stage === stageFilter;
    return matchesSearch && matchesStage;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Model Registry</h1>
          <p className="text-slate-500 mt-1">Manage and track ML model versions</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
          <Plus className="w-4 h-4" />
          Register Model
        </button>
      </div>

      {/* Search and Filters */}
      <div className="flex items-center gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search models by name or version..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-400" />
          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            <option value="all">All Stages</option>
            <option value="production">Production</option>
            <option value="staging">Staging</option>
            <option value="development">Development</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {/* Models Grid */}
      <div className="grid grid-cols-2 gap-4">
        {filteredModels.map((model) => (
          <div
            key={model.id}
            className={`bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md transition-shadow cursor-pointer ${
              selectedModel?.id === model.id ? 'ring-2 ring-orange-500' : ''
            }`}
            onClick={() => setSelectedModel(model)}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                  model.stage === 'production' ? 'bg-green-100' :
                  model.stage === 'staging' ? 'bg-amber-100' : 'bg-slate-100'
                }`}>
                  <Database className={`w-6 h-6 ${
                    model.stage === 'production' ? 'text-green-600' :
                    model.stage === 'staging' ? 'text-amber-600' : 'text-slate-600'
                  }`} />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-900">{model.name}</h3>
                  <div className="flex items-center gap-2 mt-0.5">
                    <Tag className="w-3 h-3 text-slate-400" />
                    <span className="text-sm text-slate-500">v{model.version}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-2 py-1 text-xs font-medium rounded capitalize ${stageColors[model.stage]}`}>
                  {model.stage}
                </span>
                <button className="p-1 hover:bg-slate-100 rounded">
                  <MoreVertical className="w-4 h-4 text-slate-400" />
                </button>
              </div>
            </div>

            <p className="text-sm text-slate-600 mb-4 line-clamp-2">{model.description}</p>

            {/* Metrics */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="bg-slate-50 rounded-lg p-2">
                <p className="text-xs text-slate-500">Accuracy</p>
                <p className="text-sm font-semibold text-slate-900">{(model.accuracy * 100).toFixed(1)}%</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-2">
                <p className="text-xs text-slate-500">F1 Score</p>
                <p className="text-sm font-semibold text-slate-900">{(model.f1Score * 100).toFixed(1)}%</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-2">
                <p className="text-xs text-slate-500">AUC-ROC</p>
                <p className="text-sm font-semibold text-slate-900">{(model.aucRoc * 100).toFixed(1)}%</p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-slate-100">
              <div className="flex items-center gap-4 text-xs text-slate-500">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {new Date(model.createdAt).toLocaleDateString()}
                </span>
                <span className="flex items-center gap-1">
                  <GitBranch className="w-3 h-3" />
                  {model.createdBy}
                </span>
              </div>
              {model.canRollbackTo.length > 0 && (
                <span className="text-xs text-blue-600">
                  {model.canRollbackTo.length} rollback options
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Model Details Panel */}
      {selectedModel && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold text-slate-900">Model Details</h2>
            <div className="flex items-center gap-2">
              {selectedModel.stage === 'staging' && (
                <button className="flex items-center gap-2 px-3 py-1.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700">
                  <ArrowUpRight className="w-4 h-4" />
                  Promote to Production
                </button>
              )}
              {selectedModel.stage === 'production' && selectedModel.canRollbackTo.length > 0 && (
                <button className="flex items-center gap-2 px-3 py-1.5 bg-amber-600 text-white text-sm rounded-lg hover:bg-amber-700">
                  <AlertTriangle className="w-4 h-4" />
                  Rollback
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-4 gap-6">
            <div>
              <p className="text-sm text-slate-500 mb-1">Model Type</p>
              <p className="font-medium text-slate-900">{selectedModel.modelType}</p>
            </div>
            <div>
              <p className="text-sm text-slate-500 mb-1">Version</p>
              <p className="font-medium text-slate-900">v{selectedModel.version}</p>
            </div>
            <div>
              <p className="text-sm text-slate-500 mb-1">Stage</p>
              <span className={`px-2 py-1 text-xs font-medium rounded capitalize ${stageColors[selectedModel.stage]}`}>
                {selectedModel.stage}
              </span>
            </div>
            <div>
              <p className="text-sm text-slate-500 mb-1">Created By</p>
              <p className="font-medium text-slate-900">{selectedModel.createdBy}</p>
            </div>
          </div>

          {selectedModel.canRollbackTo.length > 0 && (
            <div className="mt-6 pt-6 border-t border-slate-100">
              <p className="text-sm text-slate-500 mb-2">Rollback Options</p>
              <div className="flex items-center gap-2">
                {selectedModel.canRollbackTo.map((version) => (
                  <span key={version} className="px-2 py-1 bg-slate-100 text-slate-700 text-xs rounded">
                    {version}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
