import { useState } from 'react';
import {
  Heart,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Clock,
  Server,
  Database,
  Cpu,
  HardDrive,
  Activity,
  Wifi
} from 'lucide-react';

interface ComponentHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  message: string;
  responseTimeMs: number;
  lastChecked: string;
  details?: Record<string, string | number>;
}

const mockComponents: ComponentHealth[] = [
  {
    name: 'Model Registry',
    status: 'healthy',
    message: 'All systems operational',
    responseTimeMs: 12,
    lastChecked: '2024-01-26T15:00:00Z',
    details: { models: 4, versions: 12 },
  },
  {
    name: 'A/B Testing Framework',
    status: 'healthy',
    message: '1 active experiment',
    responseTimeMs: 8,
    lastChecked: '2024-01-26T15:00:00Z',
    details: { activeExperiments: 1, totalPredictions: 45231 },
  },
  {
    name: 'Retraining Pipeline',
    status: 'healthy',
    message: '1 job running',
    responseTimeMs: 15,
    lastChecked: '2024-01-26T15:00:00Z',
    details: { queuedJobs: 1, runningJobs: 1 },
  },
  {
    name: 'Governance Controller',
    status: 'degraded',
    message: '2 pending approvals',
    responseTimeMs: 45,
    lastChecked: '2024-01-26T15:00:00Z',
    details: { pendingApprovals: 2, avgReviewTime: '4h' },
  },
  {
    name: 'Metrics Collector',
    status: 'healthy',
    message: 'Collecting metrics normally',
    responseTimeMs: 5,
    lastChecked: '2024-01-26T15:00:00Z',
    details: { metricsPerSecond: 1250, retentionHours: 168 },
  },
  {
    name: 'Notification Service',
    status: 'healthy',
    message: 'All channels operational',
    responseTimeMs: 22,
    lastChecked: '2024-01-26T15:00:00Z',
    details: { activeChannels: 3, deliveryRate: '99.8%' },
  },
];

const systemMetrics = {
  cpu: { value: 34, unit: '%', status: 'healthy' },
  memory: { value: 62, unit: '%', status: 'healthy' },
  disk: { value: 45, unit: '%', status: 'healthy' },
  network: { value: 125, unit: 'ms', status: 'healthy' },
};

const statusConfig = {
  healthy: { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle2 },
  degraded: { color: 'text-amber-600', bg: 'bg-amber-100', icon: AlertTriangle },
  unhealthy: { color: 'text-red-600', bg: 'bg-red-100', icon: XCircle },
};

export function PMHealthPage() {
  const [isRefreshing, setIsRefreshing] = useState(false);

  const overallStatus = mockComponents.some(c => c.status === 'unhealthy') ? 'unhealthy' :
                        mockComponents.some(c => c.status === 'degraded') ? 'degraded' : 'healthy';

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 1500);
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">System Health</h1>
          <p className="text-slate-500 mt-1">Monitor component health and system diagnostics</p>
        </div>
        <button 
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Overall Status */}
      <div className={`rounded-xl p-6 border ${
        overallStatus === 'healthy' ? 'bg-green-50 border-green-200' :
        overallStatus === 'degraded' ? 'bg-amber-50 border-amber-200' :
        'bg-red-50 border-red-200'
      }`}>
        <div className="flex items-center gap-4">
          <div className={`w-16 h-16 rounded-full flex items-center justify-center ${statusConfig[overallStatus].bg}`}>
            <Heart className={`w-8 h-8 ${statusConfig[overallStatus].color}`} />
          </div>
          <div>
            <h2 className={`text-2xl font-bold capitalize ${statusConfig[overallStatus].color}`}>
              System {overallStatus}
            </h2>
            <p className="text-slate-600 mt-1">
              {overallStatus === 'healthy' ? 'All components are operating normally' :
               overallStatus === 'degraded' ? 'Some components require attention' :
               'Critical issues detected'}
            </p>
          </div>
        </div>
      </div>

      {/* System Resources */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">CPU Usage</span>
            <Cpu className="w-5 h-5 text-slate-400" />
          </div>
          <p className="text-2xl font-bold text-slate-900">{systemMetrics.cpu.value}%</p>
          <div className="mt-2 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-green-500 rounded-full" 
              style={{ width: `${systemMetrics.cpu.value}%` }}
            />
          </div>
        </div>

        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">Memory</span>
            <Server className="w-5 h-5 text-slate-400" />
          </div>
          <p className="text-2xl font-bold text-slate-900">{systemMetrics.memory.value}%</p>
          <div className="mt-2 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-blue-500 rounded-full" 
              style={{ width: `${systemMetrics.memory.value}%` }}
            />
          </div>
        </div>

        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">Disk</span>
            <HardDrive className="w-5 h-5 text-slate-400" />
          </div>
          <p className="text-2xl font-bold text-slate-900">{systemMetrics.disk.value}%</p>
          <div className="mt-2 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-purple-500 rounded-full" 
              style={{ width: `${systemMetrics.disk.value}%` }}
            />
          </div>
        </div>

        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm">Network Latency</span>
            <Wifi className="w-5 h-5 text-slate-400" />
          </div>
          <p className="text-2xl font-bold text-slate-900">{systemMetrics.network.value}ms</p>
          <div className="mt-2 flex items-center gap-1">
            <Activity className="w-4 h-4 text-green-500" />
            <span className="text-xs text-green-600">Normal</span>
          </div>
        </div>
      </div>

      {/* Component Health */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">Component Status</h2>
          <span className="text-xs text-slate-500">
            Last checked: {new Date().toLocaleTimeString()}
          </span>
        </div>
        <div className="divide-y divide-slate-100">
          {mockComponents.map((component) => {
            const StatusIcon = statusConfig[component.status].icon;
            return (
              <div key={component.name} className="p-4 hover:bg-slate-50 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${statusConfig[component.status].bg}`}>
                      <StatusIcon className={`w-5 h-5 ${statusConfig[component.status].color}`} />
                    </div>
                    <div>
                      <h3 className="font-medium text-slate-900">{component.name}</h3>
                      <p className="text-sm text-slate-500">{component.message}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <p className="text-sm font-medium text-slate-900">{component.responseTimeMs}ms</p>
                      <p className="text-xs text-slate-500">Response time</p>
                    </div>
                    <span className={`px-2 py-1 text-xs font-medium rounded capitalize ${
                      statusConfig[component.status].bg
                    } ${statusConfig[component.status].color}`}>
                      {component.status}
                    </span>
                  </div>
                </div>
                {component.details && (
                  <div className="mt-3 pl-14 flex items-center gap-4">
                    {Object.entries(component.details).map(([key, value]) => (
                      <span key={key} className="text-xs text-slate-500">
                        {key.replace(/([A-Z])/g, ' $1').trim()}: <span className="font-medium text-slate-700">{value}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Liveness & Readiness */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <Activity className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Liveness Probe</h3>
              <p className="text-sm text-green-600">System is alive</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            <span className="text-sm text-slate-500">Uptime: 14d 6h 32m</span>
          </div>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Readiness Probe</h3>
              <p className="text-sm text-green-600">Ready to accept traffic</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-slate-400" />
            <span className="text-sm text-slate-500">All dependencies connected</span>
          </div>
        </div>
      </div>
    </div>
  );
}
