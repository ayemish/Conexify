import { useState } from 'react';
import {
  RefreshCw,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Calendar,
  Database,
  TrendingDown,
  Zap
} from 'lucide-react';

interface RetrainingJob {
  id: string;
  modelName: string;
  trigger: 'scheduled' | 'drift' | 'performance' | 'manual' | 'data_volume';
  status: 'queued' | 'running' | 'completed' | 'failed';
  startedAt?: string;
  completedAt?: string;
  newVersion?: string;
  metrics?: { accuracy: number; f1Score: number };
  triggeredBy: string;
}

interface RetrainingTrigger {
  id: string;
  name: string;
  type: 'scheduled' | 'drift' | 'performance' | 'data_volume';
  enabled: boolean;
  config: Record<string, string | number>;
  lastTriggered?: string;
}

const mockJobs: RetrainingJob[] = [
  {
    id: 'job-001',
    modelName: 'anomaly_detection',
    trigger: 'scheduled',
    status: 'completed',
    startedAt: '2024-01-25T02:00:00Z',
    completedAt: '2024-01-25T02:45:00Z',
    newVersion: '2.1.1',
    metrics: { accuracy: 0.965, f1Score: 0.948 },
    triggeredBy: 'scheduler',
  },
  {
    id: 'job-002',
    modelName: 'failure_prediction',
    trigger: 'drift',
    status: 'running',
    startedAt: '2024-01-26T10:30:00Z',
    triggeredBy: 'drift_detector',
  },
  {
    id: 'job-003',
    modelName: 'rul_estimation',
    trigger: 'performance',
    status: 'failed',
    startedAt: '2024-01-24T14:00:00Z',
    completedAt: '2024-01-24T14:15:00Z',
    triggeredBy: 'performance_monitor',
  },
  {
    id: 'job-004',
    modelName: 'anomaly_detection',
    trigger: 'manual',
    status: 'queued',
    triggeredBy: 'admin@company.com',
  },
];

const mockTriggers: RetrainingTrigger[] = [
  {
    id: 'trigger-001',
    name: 'Weekly Scheduled Retraining',
    type: 'scheduled',
    enabled: true,
    config: { cron: '0 2 * * 0', timezone: 'UTC' },
    lastTriggered: '2024-01-21T02:00:00Z',
  },
  {
    id: 'trigger-002',
    name: 'Data Drift Detection',
    type: 'drift',
    enabled: true,
    config: { threshold: 0.15, windowDays: 7 },
    lastTriggered: '2024-01-26T10:30:00Z',
  },
  {
    id: 'trigger-003',
    name: 'Performance Degradation',
    type: 'performance',
    enabled: true,
    config: { accuracyThreshold: 0.90, checkInterval: '1h' },
    lastTriggered: '2024-01-24T14:00:00Z',
  },
  {
    id: 'trigger-004',
    name: 'Data Volume Trigger',
    type: 'data_volume',
    enabled: false,
    config: { minNewSamples: 10000 },
  },
];

const statusConfig = {
  queued: { color: 'bg-slate-100 text-slate-700', icon: Clock },
  running: { color: 'bg-blue-100 text-blue-700', icon: RefreshCw },
  completed: { color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
  failed: { color: 'bg-red-100 text-red-700', icon: XCircle },
};

const triggerIcons = {
  scheduled: Calendar,
  drift: TrendingDown,
  performance: AlertTriangle,
  data_volume: Database,
  manual: Zap,
};

export function PMRetrainingPage() {
  const [activeTab, setActiveTab] = useState<'jobs' | 'triggers'>('jobs');

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Retraining Pipeline</h1>
          <p className="text-slate-500 mt-1">Automated model retraining and trigger management</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
          <Play className="w-4 h-4" />
          Trigger Manual Retraining
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab('jobs')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'jobs' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          Recent Jobs
        </button>
        <button
          onClick={() => setActiveTab('triggers')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'triggers' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          Triggers
        </button>
      </div>

      {activeTab === 'jobs' ? (
        <>
          {/* Stats */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-sm text-slate-500 mb-1">Queued</p>
              <p className="text-2xl font-bold text-slate-900">1</p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-sm text-slate-500 mb-1">Running</p>
              <p className="text-2xl font-bold text-blue-600">1</p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-sm text-slate-500 mb-1">Completed (24h)</p>
              <p className="text-2xl font-bold text-green-600">1</p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-sm text-slate-500 mb-1">Failed (24h)</p>
              <p className="text-2xl font-bold text-red-600">1</p>
            </div>
          </div>

          {/* Jobs List */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200">
              <h2 className="font-semibold text-slate-900">Retraining Jobs</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {mockJobs.map((job) => {
                const StatusIcon = statusConfig[job.status].icon;
                const TriggerIcon = triggerIcons[job.trigger];
                return (
                  <div key={job.id} className="p-4 hover:bg-slate-50 transition-colors">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                          job.status === 'running' ? 'bg-blue-100' :
                          job.status === 'completed' ? 'bg-green-100' :
                          job.status === 'failed' ? 'bg-red-100' : 'bg-slate-100'
                        }`}>
                          <StatusIcon className={`w-5 h-5 ${
                            job.status === 'running' ? 'text-blue-600 animate-spin' :
                            job.status === 'completed' ? 'text-green-600' :
                            job.status === 'failed' ? 'text-red-600' : 'text-slate-600'
                          }`} />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium text-slate-900">{job.modelName}</h3>
                            {job.newVersion && (
                              <span className="text-xs text-green-600">→ v{job.newVersion}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <TriggerIcon className="w-3 h-3 text-slate-400" />
                            <span className="text-xs text-slate-500 capitalize">{job.trigger.replace('_', ' ')}</span>
                            <span className="text-xs text-slate-400">•</span>
                            <span className="text-xs text-slate-500">{job.triggeredBy}</span>
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded capitalize ${statusConfig[job.status].color}`}>
                          {job.status}
                        </span>
                        {job.startedAt && (
                          <p className="text-xs text-slate-500 mt-1">
                            {new Date(job.startedAt).toLocaleString()}
                          </p>
                        )}
                      </div>
                    </div>
                    {job.metrics && (
                      <div className="mt-3 flex items-center gap-4 pl-14">
                        <span className="text-xs text-slate-500">
                          Accuracy: <span className="font-medium text-slate-700">{(job.metrics.accuracy * 100).toFixed(1)}%</span>
                        </span>
                        <span className="text-xs text-slate-500">
                          F1: <span className="font-medium text-slate-700">{(job.metrics.f1Score * 100).toFixed(1)}%</span>
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      ) : (
        /* Triggers Tab */
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200">
            <h2 className="font-semibold text-slate-900">Retraining Triggers</h2>
          </div>
          <div className="divide-y divide-slate-100">
            {mockTriggers.map((trigger) => {
              const TriggerIcon = triggerIcons[trigger.type];
              return (
                <div key={trigger.id} className="p-4 hover:bg-slate-50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        trigger.enabled ? 'bg-orange-100' : 'bg-slate-100'
                      }`}>
                        <TriggerIcon className={`w-5 h-5 ${
                          trigger.enabled ? 'text-orange-600' : 'text-slate-400'
                        }`} />
                      </div>
                      <div>
                        <h3 className="font-medium text-slate-900">{trigger.name}</h3>
                        <p className="text-xs text-slate-500 capitalize mt-0.5">{trigger.type.replace('_', ' ')} trigger</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      {trigger.lastTriggered && (
                        <span className="text-xs text-slate-500">
                          Last: {new Date(trigger.lastTriggered).toLocaleDateString()}
                        </span>
                      )}
                      <button
                        className={`relative w-11 h-6 rounded-full transition-colors ${
                          trigger.enabled ? 'bg-orange-500' : 'bg-slate-300'
                        }`}
                      >
                        <span className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                          trigger.enabled ? 'left-6' : 'left-1'
                        }`} />
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 pl-14">
                    <div className="flex items-center gap-3 flex-wrap">
                      {Object.entries(trigger.config).map(([key, value]) => (
                        <span key={key} className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded">
                          {key}: {value}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
