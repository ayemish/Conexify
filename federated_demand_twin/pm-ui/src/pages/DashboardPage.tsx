import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Database,
  FlaskConical,
  RefreshCw,
  Shield,
  TrendingUp,
  Wrench,
  Zap,
  FileText,
  Bot,
  Truck,
  ArrowRight
} from 'lucide-react';

interface ModelSummary {
  name: string;
  version: string;
  stage: string;
  accuracy: number;
  lastUpdated: string;
  predictions24h: number;
}

interface Alert {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  message: string;
  timestamp: string;
  metric: string;
}

const mockModels: ModelSummary[] = [
  { name: 'Anomaly Detection', version: '2.1.0', stage: 'Production', accuracy: 0.96, lastUpdated: '2h ago', predictions24h: 15234 },
  { name: 'Failure Prediction', version: '1.3.0', stage: 'Production', accuracy: 0.94, lastUpdated: '1d ago', predictions24h: 8421 },
  { name: 'RUL Estimation', version: '3.0.0-beta', stage: 'Staging', accuracy: 0.91, lastUpdated: '4h ago', predictions24h: 2156 },
];

const mockAlerts: Alert[] = [
  { id: '1', severity: 'warning', message: 'Model accuracy degraded below threshold (0.92)', timestamp: '15m ago', metric: 'anomaly_detection_accuracy' },
  { id: '2', severity: 'info', message: 'Retraining job completed successfully', timestamp: '1h ago', metric: 'retraining_status' },
  { id: '3', severity: 'critical', message: 'High prediction latency detected (>500ms)', timestamp: '30m ago', metric: 'prediction_latency_p99' },
];

export function DashboardPage() {
  const [timeRange] = useState('24h');
  const navigate = useNavigate();

  const quickActions = [
    { icon: FileText, label: 'Review Cases', description: '3 cases need attention', path: '/cases', color: 'orange' },
    { icon: Bot, label: 'Agent Approvals', description: '2 pending approvals', path: '/agents', color: 'purple' },
    { icon: Truck, label: 'Dispatch Queue', description: '5 ready to dispatch', path: '/dispatch', color: 'blue' },
    { icon: Shield, label: 'Governance', description: '1 model promotion', path: '/governance', color: 'green' },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-slate-500 mt-1">Predictive maintenance overview</p>
        </div>
        <div className="flex items-center gap-3">
          <select 
            value={timeRange}
            className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm"
          >
            <option value="1h">Last 1 hour</option>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
          <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-4 gap-4">
        {quickActions.map((action) => (
          <button
            key={action.path}
            onClick={() => navigate(action.path)}
            className="bg-white rounded-xl p-4 border border-slate-200 hover:border-orange-300 hover:shadow-md transition-all text-left group"
          >
            <div className="flex items-center justify-between mb-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                action.color === 'orange' ? 'bg-orange-100' :
                action.color === 'purple' ? 'bg-purple-100' :
                action.color === 'blue' ? 'bg-blue-100' : 'bg-green-100'
              }`}>
                <action.icon className={`w-5 h-5 ${
                  action.color === 'orange' ? 'text-orange-600' :
                  action.color === 'purple' ? 'text-purple-600' :
                  action.color === 'blue' ? 'text-blue-600' : 'text-green-600'
                }`} />
              </div>
              <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-orange-500 transition-colors" />
            </div>
            <p className="font-medium text-slate-900">{action.label}</p>
            <p className="text-sm text-slate-500">{action.description}</p>
          </button>
        ))}
      </div>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm font-medium">Total Predictions</span>
            <Zap className="w-5 h-5 text-orange-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">25,811</p>
          <p className="text-sm text-green-600 mt-1 flex items-center gap-1">
            <TrendingUp className="w-4 h-4" />
            +12.5% from yesterday
          </p>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm font-medium">Avg Accuracy</span>
            <Activity className="w-5 h-5 text-blue-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">94.2%</p>
          <p className="text-sm text-slate-500 mt-1">Across all models</p>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm font-medium">Active Models</span>
            <Database className="w-5 h-5 text-purple-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">3</p>
          <p className="text-sm text-slate-500 mt-1">2 Production, 1 Staging</p>
        </div>

        <div className="bg-white rounded-xl p-5 border border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-500 text-sm font-medium">Active Alerts</span>
            <AlertTriangle className="w-5 h-5 text-amber-500" />
          </div>
          <p className="text-3xl font-bold text-slate-900">2</p>
          <p className="text-sm text-red-600 mt-1">1 Critical, 1 Warning</p>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Models Overview */}
        <div className="col-span-2 bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Model Registry</h2>
            <span className="text-xs text-slate-500">3 models registered</span>
          </div>
          <div className="divide-y divide-slate-100">
            {mockModels.map((model) => (
              <div key={model.name} className="p-4 hover:bg-slate-50 transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      model.stage === 'Production' ? 'bg-green-100' : 'bg-amber-100'
                    }`}>
                      <Wrench className={`w-5 h-5 ${
                        model.stage === 'Production' ? 'text-green-600' : 'text-amber-600'
                      }`} />
                    </div>
                    <div>
                      <h3 className="font-medium text-slate-900">{model.name}</h3>
                      <p className="text-xs text-slate-500">v{model.version}</p>
                    </div>
                  </div>
                  <span className={`px-2 py-1 text-xs font-medium rounded ${
                    model.stage === 'Production' 
                      ? 'bg-green-100 text-green-700' 
                      : 'bg-amber-100 text-amber-700'
                  }`}>
                    {model.stage}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-4 mt-3">
                  <div>
                    <p className="text-xs text-slate-500">Accuracy</p>
                    <p className="text-sm font-semibold text-slate-900">{(model.accuracy * 100).toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Predictions (24h)</p>
                    <p className="text-sm font-semibold text-slate-900">{model.predictions24h.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Last Updated</p>
                    <p className="text-sm font-semibold text-slate-900">{model.lastUpdated}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Alerts */}
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Recent Alerts</h2>
            <span className="text-xs text-slate-500">{mockAlerts.length} alerts</span>
          </div>
          <div className="divide-y divide-slate-100 max-h-[400px] overflow-auto">
            {mockAlerts.map((alert) => (
              <div key={alert.id} className="p-4 hover:bg-slate-50 transition-colors">
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 ${
                    alert.severity === 'critical' ? 'text-red-500' :
                    alert.severity === 'warning' ? 'text-amber-500' : 'text-blue-500'
                  }`}>
                    {alert.severity === 'critical' ? <AlertTriangle className="w-5 h-5" /> :
                     alert.severity === 'warning' ? <AlertTriangle className="w-5 h-5" /> :
                     <CheckCircle2 className="w-5 h-5" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-900">{alert.message}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`px-1.5 py-0.5 text-xs font-medium rounded ${
                        alert.severity === 'critical' ? 'bg-red-100 text-red-700' :
                        alert.severity === 'warning' ? 'bg-amber-100 text-amber-700' :
                        'bg-blue-100 text-blue-700'
                      }`}>
                        {alert.severity}
                      </span>
                      <span className="text-xs text-slate-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {alert.timestamp}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* System Status */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-slate-200 flex items-center gap-4">
          <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
            <Database className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-900">Model Registry</p>
            <p className="text-xs text-green-600 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> Healthy
            </p>
          </div>
        </div>

        <div className="bg-white rounded-xl p-4 border border-slate-200 flex items-center gap-4">
          <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
            <FlaskConical className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-900">A/B Testing</p>
            <p className="text-xs text-green-600 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> 1 Active Experiment
            </p>
          </div>
        </div>

        <div className="bg-white rounded-xl p-4 border border-slate-200 flex items-center gap-4">
          <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
            <RefreshCw className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-900">Retraining Pipeline</p>
            <p className="text-xs text-green-600 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> Ready
            </p>
          </div>
        </div>

        <div className="bg-white rounded-xl p-4 border border-slate-200 flex items-center gap-4">
          <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
            <Shield className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-900">Governance</p>
            <p className="text-xs text-slate-500 flex items-center gap-1">
              0 Pending Approvals
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
