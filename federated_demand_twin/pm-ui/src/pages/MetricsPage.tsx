import { useState, useMemo } from 'react';
import {
  Bell,
  AlertTriangle,
  Clock,
  Plus,
  Filter,
  TrendingUp,
  TrendingDown,
  Activity,
  Loader2
} from 'lucide-react';
import { useAlerts, useAcknowledgeAlert, Alert as APIAlert } from '../services';

// Display types for UI
interface AlertDisplay {
  id: string;
  ruleName: string;
  severity: 'critical' | 'warning' | 'info';
  state: 'firing' | 'pending' | 'resolved';
  message: string;
  metricName: string;
  metricValue: number;
  threshold: number;
  firedAt: string;
  acknowledgedBy?: string;
}

interface MetricSummary {
  name: string;
  namespace: string;
  currentValue: number;
  trend: 'up' | 'down' | 'stable';
  change: number;
  unit: string;
}

// Transform API alert to display format
function transformAlert(apiAlert: APIAlert): AlertDisplay {
  return {
    id: apiAlert.alert_id,
    ruleName: apiAlert.rule_name,
    severity: apiAlert.severity as AlertDisplay['severity'],
    state: apiAlert.state as AlertDisplay['state'],
    message: apiAlert.message,
    metricName: apiAlert.metric_name,
    metricValue: apiAlert.current_value,
    threshold: apiAlert.threshold,
    firedAt: apiAlert.fired_at,
    acknowledgedBy: apiAlert.acknowledged_by,
  };
}

// Metrics would come from a separate metrics endpoint - computed from system state for now
const defaultMetrics: MetricSummary[] = [
  { name: 'Total Predictions', namespace: 'model', currentValue: 0, trend: 'stable', change: 0, unit: '' },
  { name: 'Avg Latency (p50)', namespace: 'model', currentValue: 0, trend: 'stable', change: 0, unit: 'ms' },
  { name: 'Avg Latency (p99)', namespace: 'model', currentValue: 0, trend: 'stable', change: 0, unit: 'ms' },
  { name: 'Error Rate', namespace: 'model', currentValue: 0, trend: 'stable', change: 0, unit: '%' },
  { name: 'Accuracy (Anomaly)', namespace: 'model', currentValue: 0, trend: 'stable', change: 0, unit: '%' },
  { name: 'Accuracy (Failure)', namespace: 'model', currentValue: 0, trend: 'stable', change: 0, unit: '%' },
  { name: 'Active Experiments', namespace: 'experiment', currentValue: 0, trend: 'stable', change: 0, unit: '' },
  { name: 'Pending Approvals', namespace: 'governance', currentValue: 0, trend: 'stable', change: 0, unit: '' },
];

const severityConfig = {
  critical: { color: 'text-red-600', bg: 'bg-red-100', border: 'border-red-200' },
  warning: { color: 'text-amber-600', bg: 'bg-amber-100', border: 'border-amber-200' },
  info: { color: 'text-blue-600', bg: 'bg-blue-100', border: 'border-blue-200' },
};

const stateConfig = {
  firing: { color: 'text-red-600', bg: 'bg-red-100' },
  pending: { color: 'text-amber-600', bg: 'bg-amber-100' },
  resolved: { color: 'text-green-600', bg: 'bg-green-100' },
};

export function MetricsPage() {
  const [alertFilter, setAlertFilter] = useState<string>('all');
  const [activeTab, setActiveTab] = useState<'alerts' | 'metrics'>('alerts');

  // Fetch alerts from API
  const { data: apiAlerts, loading, error, refetch } = useAlerts();
  const { acknowledge, loading: acknowledging } = useAcknowledgeAlert();

  // Transform API alerts to display format
  const alerts: AlertDisplay[] = useMemo(
    () => (apiAlerts || []).map(transformAlert),
    [apiAlerts]
  );

  // Use default metrics for now (would come from metrics API)
  const metrics = defaultMetrics;

  const firingCount = alerts.filter(a => a.state === 'firing').length;

  // Handle acknowledge alert
  const handleAcknowledge = async (alertId: string) => {
    try {
      await acknowledge(alertId, 'current-user');
      refetch();
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Metrics & Alerts</h1>
          <p className="text-slate-500 mt-1">Monitor system metrics and manage alerts</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
          <Plus className="w-4 h-4" />
          Create Alert Rule
        </button>
      </div>

      {/* Alert Summary */}
      {firingCount > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
              <Bell className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <p className="font-medium text-red-900">{firingCount} Active Alert{firingCount > 1 ? 's' : ''}</p>
              <p className="text-sm text-red-700">Immediate attention required</p>
            </div>
          </div>
          <button className="px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700">
            View All
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab('alerts')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'alerts' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          Alerts
          {firingCount > 0 && (
            <span className="ml-2 px-1.5 py-0.5 bg-red-100 text-red-700 text-xs rounded-full">
              {firingCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('metrics')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'metrics' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          Metrics Dashboard
        </button>
      </div>

      {activeTab === 'alerts' ? (
        <>
          {/* Alert Filters */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            {['all', 'firing', 'pending', 'resolved'].map((state) => (
              <button
                key={state}
                onClick={() => setAlertFilter(state)}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors capitalize ${
                  alertFilter === state
                    ? 'bg-orange-100 text-orange-700 font-medium'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {state}
              </button>
            ))}
          </div>

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-orange-600 animate-spin" />
              <span className="ml-2 text-slate-600">Loading alerts...</span>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-red-700">Failed to load alerts: {error.message}</p>
              <button onClick={() => refetch()} className="mt-2 text-sm text-red-600 underline">
                Retry
              </button>
            </div>
          )}

          {/* Alerts List */}
          {!loading && !error && (
          <div className="space-y-3">
            {alerts.filter(a => alertFilter === 'all' || a.state === alertFilter).map((alert: AlertDisplay) => (
              <div 
                key={alert.id} 
                className={`bg-white rounded-xl border p-4 ${
                  alert.state === 'firing' ? severityConfig[alert.severity].border : 'border-slate-200'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${severityConfig[alert.severity].bg}`}>
                      <AlertTriangle className={`w-5 h-5 ${severityConfig[alert.severity].color}`} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-slate-900">{alert.ruleName}</h3>
                        <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${severityConfig[alert.severity].bg} ${severityConfig[alert.severity].color}`}>
                          {alert.severity}
                        </span>
                        <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${stateConfig[alert.state].bg} ${stateConfig[alert.state].color}`}>
                          {alert.state}
                        </span>
                      </div>
                      <p className="text-sm text-slate-600 mt-1">{alert.message}</p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                        <span>Metric: <code className="bg-slate-100 px-1 rounded">{alert.metricName}</code></span>
                        <span>Value: <span className="font-medium text-slate-700">{alert.metricValue}</span></span>
                        <span>Threshold: <span className="font-medium text-slate-700">{alert.threshold}</span></span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    {alert.state === 'firing' && (
                      <button className="px-3 py-1 bg-slate-100 text-slate-700 text-sm rounded-lg hover:bg-slate-200 mb-2">
                        Acknowledge
                      </button>
                    )}
                    <p className="text-xs text-slate-500 flex items-center gap-1 justify-end">
                      <Clock className="w-3 h-3" />
                      {new Date(alert.firedAt).toLocaleString()}
                    </p>
                    {alert.acknowledgedBy && (
                      <p className="text-xs text-slate-500">by {alert.acknowledgedBy}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
          )}
        </>
      ) : (
        /* Metrics Dashboard */
        <div className="space-y-6">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-4 gap-4">
            {metrics.slice(0, 4).map((metric: MetricSummary) => (
              <div key={metric.name} className="bg-white rounded-xl p-4 border border-slate-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-500">{metric.name}</span>
                  {metric.trend === 'up' ? (
                    <TrendingUp className={`w-4 h-4 ${metric.change > 0 && metric.name.includes('Latency') ? 'text-red-500' : 'text-green-500'}`} />
                  ) : metric.trend === 'down' ? (
                    <TrendingDown className={`w-4 h-4 ${metric.change < 0 && metric.name.includes('Error') ? 'text-green-500' : 'text-amber-500'}`} />
                  ) : (
                    <Activity className="w-4 h-4 text-slate-400" />
                  )}
                </div>
                <p className="text-2xl font-bold text-slate-900">
                  {metric.currentValue.toLocaleString()}{metric.unit}
                </p>
                <p className={`text-xs mt-1 ${
                  metric.change > 0 ? 'text-green-600' : metric.change < 0 ? 'text-red-600' : 'text-slate-500'
                }`}>
                  {metric.change > 0 ? '+' : ''}{metric.change}% from yesterday
                </p>
              </div>
            ))}
          </div>

          {/* All Metrics Table */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200">
              <h2 className="font-semibold text-slate-900">All Metrics</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Metric</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Namespace</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Current Value</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Trend</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Change</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {metrics.map((metric: MetricSummary) => (
                    <tr key={metric.name} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <span className="font-medium text-slate-900">{metric.name}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs rounded capitalize">
                          {metric.namespace}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-slate-900">
                        {metric.currentValue.toLocaleString()}{metric.unit}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {metric.trend === 'up' ? (
                          <TrendingUp className="w-4 h-4 text-green-500 inline" />
                        ) : metric.trend === 'down' ? (
                          <TrendingDown className="w-4 h-4 text-red-500 inline" />
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className={`px-4 py-3 text-right text-sm ${
                        metric.change > 0 ? 'text-green-600' : metric.change < 0 ? 'text-red-600' : 'text-slate-500'
                      }`}>
                        {metric.change > 0 ? '+' : ''}{metric.change}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
