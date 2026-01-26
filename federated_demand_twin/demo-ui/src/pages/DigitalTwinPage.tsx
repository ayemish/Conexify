import { useState, useEffect } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, ReferenceLine
} from 'recharts';
import { 
  Box, Cpu, Thermometer, Activity, AlertTriangle, 
  CheckCircle, Clock, RefreshCw, Zap
} from 'lucide-react';
import { api, type DigitalTwinPageData } from '../services/api';

const statusColors = {
  normal: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', dot: 'bg-green-500' },
  warning: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', dot: 'bg-amber-500' },
  critical: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', dot: 'bg-red-500' },
  offline: { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-500', dot: 'bg-slate-400' },
};

const deviceIcons: Record<string, typeof Cpu> = {
  retailer: Cpu,
  channel: RefreshCw,
  sku: Activity,
  sensor: Thermometer,
  media: Zap,
};

export function DigitalTwinPage() {
  const [data, setData] = useState<DigitalTwinPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const result = await api.getDigitalTwinPageData();
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

  const devices = data?.devices || [];
  const twinActivities = data?.twinActivities || [];
  const telemetryHistory = data?.telemetryHistory || [];

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Digital Twin data...</span>
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
          <h1 className="text-2xl font-bold text-slate-900">Media Twin Simulation</h1>
          <p className="text-slate-500 mt-1">Retailer-channel inventory state and media-driven demand simulation</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>Live updating</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-sm">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              <span className="text-slate-600">3 Normal</span>
            </span>
            <span className="flex items-center gap-1.5 text-sm">
              <span className="w-2 h-2 rounded-full bg-amber-500"></span>
              <span className="text-slate-600">1 Warning</span>
            </span>
          </div>
        </div>
      </div>

      {/* Device Cards Grid */}
      <div className="grid grid-cols-2 gap-4">
        {devices.map((device) => {
          const colors = statusColors[device.status];
          const Icon = deviceIcons[device.type];
          const hasAlert = device.status === 'warning' || device.status === 'critical';
          
          return (
            <div 
              key={device.id}
              className={`p-5 rounded-xl border-2 ${colors.border} ${colors.bg} transition-all hover:shadow-md`}
            >
              {/* Device Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl ${hasAlert ? 'bg-amber-100' : 'bg-white'} border ${colors.border} flex items-center justify-center`}>
                    <Icon className={`w-6 h-6 ${hasAlert ? 'text-amber-600' : 'text-slate-600'}`} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900">{device.name}</h3>
                    <p className="text-sm text-slate-500">{device.location}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {hasAlert && <AlertTriangle className="w-5 h-5 text-amber-500 animate-pulse" />}
                  <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${colors.bg} ${colors.text} border ${colors.border}`}>
                    {device.status.toUpperCase()}
                  </span>
                </div>
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-2 gap-3">
                {device.metrics.map((metric) => {
                  const isAnomalous = metric.threshold && (
                    (metric.threshold.max && metric.value > metric.threshold.max) ||
                    (metric.threshold.min && metric.value < metric.threshold.min)
                  );
                  
                  return (
                    <div 
                      key={metric.name}
                      className={`p-3 rounded-lg ${isAnomalous ? 'bg-red-50 border border-red-200' : 'bg-white border border-slate-200'}`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-slate-500">{metric.name}</span>
                        {isAnomalous && <AlertTriangle className="w-3 h-3 text-red-500" />}
                      </div>
                      <div className="flex items-baseline gap-1">
                        <span className={`text-xl font-bold ${isAnomalous ? 'text-red-600' : 'text-slate-900'}`}>
                          {metric.value.toLocaleString()}
                        </span>
                        <span className="text-xs text-slate-400">{metric.unit}</span>
                      </div>
                      {metric.threshold && (
                        <p className="text-xs text-slate-400 mt-1">
                          Threshold: {metric.threshold.min ? `${metric.threshold.min}-` : '<'}{metric.threshold.max || '∞'}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Last Update */}
              <div className="mt-4 pt-3 border-t border-slate-200 flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <Clock className="w-4 h-4" />
                  <span>Updated {device.lastUpdate}</span>
                </div>
                <span className={`w-2 h-2 rounded-full ${colors.dot} ${device.status !== 'offline' ? 'animate-pulse' : ''}`}></span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Telemetry Charts */}
      <div className="grid grid-cols-2 gap-6">
        {/* Discharge Temperature Chart */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Thermometer className="w-5 h-5 text-indigo-500" />
              <h2 className="text-lg font-semibold text-slate-900">Media-Driven Demand Lift</h2>
            </div>
            <span className="text-sm text-indigo-600 font-medium">📈 Active campaigns</span>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={telemetryHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <YAxis domain={[150, 200]} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <Tooltip />
                <ReferenceLine y={180} stroke="#6366f1" strokeDasharray="5 5" label={{ value: 'Target Lift', fill: '#6366f1', fontSize: 10 }} />
                <Line 
                  type="monotone" 
                  dataKey="dischargeTemp" 
                  stroke="#6366f1" 
                  strokeWidth={2}
                  dot={false}
                  name="Demand Lift %"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Cycle Rate Chart */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-emerald-500" />
              <h2 className="text-lg font-semibold text-slate-900">ROAS by Channel</h2>
            </div>
            <span className="text-sm text-emerald-600 font-medium">💰 Budget efficiency</span>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={telemetryHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <YAxis domain={[0, 35]} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                <Tooltip />
                <ReferenceLine y={12} stroke="#10b981" strokeDasharray="5 5" label={{ value: 'Target ROAS', fill: '#10b981', fontSize: 10 }} />
                <Line 
                  type="monotone" 
                  dataKey="cycleRate" 
                  stroke="#10b981" 
                  strokeWidth={2}
                  dot={false}
                  name="ROAS"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Activity Feed */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Box className="w-5 h-5 text-indigo-600" />
            <h2 className="text-lg font-semibold text-slate-900">Media Twin Activity</h2>
          </div>
          <span className="text-sm text-slate-500">{twinActivities.length} events</span>
        </div>
        
        <div className="space-y-3">
          {twinActivities.map((activity) => {
            const severityColors = {
              info: 'bg-blue-100 text-blue-700 border-blue-200',
              warning: 'bg-amber-100 text-amber-700 border-amber-200',
              critical: 'bg-red-100 text-red-700 border-red-200',
            };
            const typeIcons = {
              telemetry: Activity,
              alert: AlertTriangle,
              prediction: Cpu,
              action: CheckCircle,
            };
            const TypeIcon = typeIcons[activity.type];
            
            return (
              <div 
                key={activity.id}
                className={`flex items-start gap-4 p-4 rounded-lg border ${
                  activity.severity === 'critical' ? 'bg-red-50 border-red-200' :
                  activity.severity === 'warning' ? 'bg-amber-50 border-amber-200' :
                  'bg-slate-50 border-slate-200'
                } animate-slide-in`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${severityColors[activity.severity]}`}>
                  <TypeIcon className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-slate-500 uppercase">{activity.type}</span>
                    <span className="text-xs text-slate-400">•</span>
                    <span className="text-xs text-slate-500">{activity.deviceId}</span>
                  </div>
                  <p className="text-sm text-slate-700">{activity.message}</p>
                </div>
                <span className="text-xs text-slate-400 whitespace-nowrap">{activity.timestamp}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
