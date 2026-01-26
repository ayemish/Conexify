import { useState, useEffect } from 'react';
import { 
  Box, Activity, AlertTriangle, CheckCircle, RefreshCw, 
  Package, TrendingUp, TrendingDown, Minus, AlertCircle
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { dpApi, type DPDigitalTwinPageData } from '../../services/dpApi';

export function DPDigitalTwinPage() {
  const [data, setData] = useState<DPDigitalTwinPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const pageData = await dpApi.getDigitalTwinPageData();
      setData(pageData);
      if (pageData.devices.length > 0 && !selectedDevice) {
        setSelectedDevice(pageData.devices[0].id);
      }
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
            <p className="text-amber-600 text-sm">Run the demo first to populate the Digital Twin data.</p>
          </div>
        </div>
      </div>
    );
  }

  const devices = data?.devices || [];
  const activities = data?.twinActivities || [];
  const telemetry = data?.telemetryHistory || [];

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'normal': return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'warning': return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      case 'critical': return <AlertTriangle className="w-5 h-5 text-red-500" />;
      default: return <Activity className="w-5 h-5 text-slate-400" />;
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up': return <TrendingUp className="w-4 h-4 text-green-500" />;
      case 'down': return <TrendingDown className="w-4 h-4 text-red-500" />;
      default: return <Minus className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Digital Twin - Inventory State</h1>
          <p className="text-slate-500 mt-1">Real-time inventory simulation and scenario analysis</p>
        </div>
        <button 
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* SKU Cards */}
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
        {devices.map((device) => (
          <div 
            key={device.id}
            onClick={() => setSelectedDevice(device.id)}
            className={`bg-white rounded-xl border p-4 shadow-sm cursor-pointer transition-all ${
              selectedDevice === device.id 
                ? 'border-emerald-500 ring-2 ring-emerald-200' 
                : 'border-slate-200 hover:border-slate-300'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Package className={`w-5 h-5 ${
                  device.status === 'normal' ? 'text-emerald-600' :
                  device.status === 'warning' ? 'text-amber-600' :
                  'text-red-600'
                }`} />
                <span className="font-medium text-slate-900">{device.name}</span>
              </div>
              {getStatusIcon(device.status)}
            </div>
            <p className="text-xs text-slate-500 mb-3">{device.location}</p>
            
            <div className="space-y-2">
              {device.metrics.slice(0, 3).map((metric, idx) => (
                <div key={idx} className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">{metric.name}</span>
                  <div className="flex items-center gap-1">
                    <span className="text-sm font-medium text-slate-900">
                      {typeof metric.value === 'number' ? metric.value.toLocaleString() : metric.value}
                    </span>
                    <span className="text-xs text-slate-400">{metric.unit}</span>
                    {getTrendIcon(metric.trend)}
                  </div>
                </div>
              ))}
            </div>
            
            <div className="mt-3 pt-3 border-t border-slate-100">
              <span className="text-xs text-slate-400">Last update: {device.lastUpdate}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Telemetry Chart */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-emerald-600" />
          Inventory & Demand Trajectory
        </h2>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={telemetry}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="time" tick={{ fontSize: 12 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 12 }} stroke="#94a3b8" />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#fff', 
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px'
                }}
              />
              <ReferenceLine y={500} stroke="#ef4444" strokeDasharray="5 5" label={{ value: 'Safety Stock', fill: '#ef4444', fontSize: 11 }} />
              <Line type="monotone" dataKey="inventory" stroke="#059669" strokeWidth={2} dot={{ fill: '#059669', r: 3 }} name="Inventory" />
              <Line type="monotone" dataKey="demand" stroke="#6366f1" strokeWidth={2} dot={{ fill: '#6366f1', r: 3 }} name="Demand" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Twin Activities */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Box className="w-5 h-5 text-emerald-600" />
          Twin State Updates
        </h2>
        <div className="space-y-3">
          {activities.map((activity) => (
            <div 
              key={activity.id}
              className={`flex items-start gap-3 p-3 rounded-lg ${
                activity.severity === 'critical' ? 'bg-red-50' :
                activity.severity === 'warning' ? 'bg-amber-50' :
                'bg-slate-50'
              }`}
            >
              <div className={`w-2 h-2 rounded-full mt-2 ${
                activity.severity === 'critical' ? 'bg-red-500' :
                activity.severity === 'warning' ? 'bg-amber-500' :
                'bg-emerald-500'
              }`} />
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-900">{activity.message}</span>
                  <span className="text-xs text-slate-400">{activity.timestamp}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs px-2 py-0.5 bg-slate-200 text-slate-600 rounded">{activity.type}</span>
                  <span className="text-xs text-slate-500">{activity.deviceId}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
