import { useState, useEffect } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, ReferenceLine, BarChart, Bar
} from 'recharts';
import { 
  Box, Cpu, Thermometer, Activity, AlertTriangle, 
  CheckCircle, Clock, RefreshCw, Zap, Search, Mail, 
  Monitor, Store, ShoppingCart, Package, Building2, TrendingUp
} from 'lucide-react';
import { api, type DigitalTwinPageData } from '../services/api';

const statusColors: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  normal: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', dot: 'bg-green-500' },
  warning: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', dot: 'bg-amber-500' },
  critical: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', dot: 'bg-red-500' },
  offline: { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-500', dot: 'bg-slate-400' },
  on_track: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', dot: 'bg-green-500' },
  under_pacing: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', dot: 'bg-amber-500' },
  over_pacing: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', dot: 'bg-red-500' },
};

const deviceIcons: Record<string, typeof Cpu> = {
  retailer: Cpu,
  channel: RefreshCw,
  sku: Activity,
  sensor: Thermometer,
  media: Zap,
  compressor: Cpu,
  pump: RefreshCw,
  valve: Activity,
  hvac: Thermometer,
};

// Channel icons mapping
const channelIcons: Record<string, typeof Search> = {
  sponsored_search: Search,
  sponsored_products: ShoppingCart,
  sponsored_brands: Store,
  display_ad: Monitor,
  website_banner: Monitor,
  digital_endcap: Monitor,
  in_store_display: Store,
  brand_store: Store,
  brand_landing_page: Store,
  email: Mail,
  app_notification: Zap,
  sms: Mail,
  connected_tv: Monitor,
  video_ad: Monitor,
  streaming_audio: Zap,
  social_media: Zap,
  influencer: Zap,
  dsp: Monitor,
  offsite_display: Monitor,
};

type TabType = 'channels' | 'manufacturers' | 'simulation';

interface ChannelTwinState {
  channel: string;
  retailer_id: string;
  week: number;
  impressions: number;
  clicks: number;
  conversions: number;
  spend: number;
  click_through_rate: number;
  conversion_rate: number;
  cost_per_click: number;
  cost_per_acquisition: number;
  attributed_revenue: number;
  roas: number;
  audience_reach: number;
  frequency: number;
  viewability_rate: number;
  budget_utilization: number;
  pacing_status: string;
}

interface ManufacturerProduct {
  manufacturer_id: string;
  manufacturer_name: string;
  products: Array<{
    product_id: string;
    product_name: string;
    brand: string;
    category: string;
    total_media_budget?: number;
  }>;
}

export function DigitalTwinPage() {
  const [data, setData] = useState<DigitalTwinPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('channels');
  const [channelTwins, setChannelTwins] = useState<ChannelTwinState[]>([]);
  const [manufacturers, setManufacturers] = useState<ManufacturerProduct[]>([]);
  const [selectedManufacturer, setSelectedManufacturer] = useState<string | null>(null);

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

  const fetchChannelTwins = async () => {
    try {
      const response = await fetch('/api/digital-twins/channels');
      if (response.ok) {
        const data = await response.json();
        setChannelTwins(data.channels || []);
      }
    } catch (err) {
      console.error('Failed to fetch channel twins:', err);
    }
  };

  const fetchManufacturers = async () => {
    try {
      const response = await fetch('/api/digital-twins/manufacturers');
      if (response.ok) {
        const data = await response.json();
        setManufacturers(data.manufacturers || []);
      }
    } catch (err) {
      console.error('Failed to fetch manufacturers:', err);
    }
  };

  useEffect(() => {
    fetchData();
    fetchChannelTwins();
    fetchManufacturers();
    const interval = setInterval(() => {
      fetchData();
      if (activeTab === 'channels') fetchChannelTwins();
      if (activeTab === 'manufacturers') fetchManufacturers();
    }, 5000);
    return () => clearInterval(interval);
  }, [activeTab]);

  const devices = data?.devices || [];
  const twinActivities = data?.twinActivities || [];
  const telemetryHistory = data?.telemetryHistory || [];

  // Format numbers for display
  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toFixed(0);
  };

  const formatCurrency = (num: number) => {
    if (num >= 1000000) return `$${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `$${(num / 1000).toFixed(1)}K`;
    return `$${num.toFixed(2)}`;
  };

  const formatPercent = (num: number) => `${(num * 100).toFixed(1)}%`;

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
          <h1 className="text-2xl font-bold text-slate-900">Retail Media Digital Twins</h1>
          <p className="text-slate-500 mt-1">Channel performance state and manufacturer product simulation</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>Live updating</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-sm">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              <span className="text-slate-600">{channelTwins.filter(c => c.pacing_status === 'on_track').length} On Track</span>
            </span>
            <span className="flex items-center gap-1.5 text-sm">
              <span className="w-2 h-2 rounded-full bg-amber-500"></span>
              <span className="text-slate-600">{channelTwins.filter(c => c.pacing_status !== 'on_track').length} Attention</span>
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-200">
        <button
          onClick={() => setActiveTab('channels')}
          className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors ${
            activeTab === 'channels'
              ? 'border-indigo-500 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <div className="flex items-center gap-2">
            <Monitor className="w-4 h-4" />
            <span>Channel Digital Twins</span>
          </div>
        </button>
        <button
          onClick={() => setActiveTab('manufacturers')}
          className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors ${
            activeTab === 'manufacturers'
              ? 'border-indigo-500 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4" />
            <span>Manufacturer Products</span>
          </div>
        </button>
        <button
          onClick={() => setActiveTab('simulation')}
          className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors ${
            activeTab === 'simulation'
              ? 'border-indigo-500 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'
          }`}
        >
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4" />
            <span>Simulation</span>
          </div>
        </button>
      </div>

      {/* Channel Digital Twins Tab */}
      {activeTab === 'channels' && (
        <div className="space-y-6">
          {/* Channel Cards Grid */}
          <div className="grid grid-cols-3 gap-4">
            {channelTwins.map((channel) => {
              const colors = statusColors[channel.pacing_status] || statusColors.normal;
              const Icon = channelIcons[channel.channel] || Monitor;
              const isAttention = channel.pacing_status !== 'on_track';
              
              return (
                <div 
                  key={channel.channel}
                  className={`p-5 rounded-xl border-2 ${colors.border} ${colors.bg} transition-all hover:shadow-md`}
                >
                  {/* Channel Header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg ${isAttention ? 'bg-amber-100' : 'bg-white'} border ${colors.border} flex items-center justify-center`}>
                        <Icon className={`w-5 h-5 ${isAttention ? 'text-amber-600' : 'text-indigo-600'}`} />
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-900 text-sm">{channel.channel.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h3>
                        <p className="text-xs text-slate-500">Week {channel.week}</p>
                      </div>
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text} border ${colors.border}`}>
                      {channel.pacing_status.replace(/_/g, ' ').toUpperCase()}
                    </span>
                  </div>

                  {/* Key Metrics */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className="p-2 rounded-lg bg-white border border-slate-200">
                      <span className="text-xs text-slate-500">Impressions</span>
                      <p className="text-lg font-bold text-slate-900">{formatNumber(channel.impressions)}</p>
                    </div>
                    <div className="p-2 rounded-lg bg-white border border-slate-200">
                      <span className="text-xs text-slate-500">Spend</span>
                      <p className="text-lg font-bold text-slate-900">{formatCurrency(channel.spend)}</p>
                    </div>
                    <div className="p-2 rounded-lg bg-white border border-slate-200">
                      <span className="text-xs text-slate-500">ROAS</span>
                      <p className="text-lg font-bold text-emerald-600">{channel.roas.toFixed(1)}x</p>
                    </div>
                    <div className="p-2 rounded-lg bg-white border border-slate-200">
                      <span className="text-xs text-slate-500">CTR</span>
                      <p className="text-lg font-bold text-indigo-600">{formatPercent(channel.click_through_rate)}</p>
                    </div>
                  </div>

                  {/* Budget Utilization */}
                  <div className="mt-3 pt-3 border-t border-slate-200">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-slate-500">Budget Utilization</span>
                      <span className="font-medium text-slate-700">{formatPercent(channel.budget_utilization)}</span>
                    </div>
                    <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                      <div 
                        className={`h-full rounded-full ${channel.budget_utilization > 0.9 ? 'bg-green-500' : channel.budget_utilization > 0.7 ? 'bg-amber-500' : 'bg-red-500'}`}
                        style={{ width: `${channel.budget_utilization * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Channel Performance Summary */}
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Channel Performance Summary</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={channelTwins.slice(0, 8).map(c => ({
                  name: c.channel.replace(/_/g, ' ').slice(0, 12),
                  roas: c.roas,
                  spend: c.spend / 1000,
                }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="#94a3b8" angle={-45} textAnchor="end" height={60} />
                  <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <Tooltip />
                  <Bar dataKey="roas" fill="#6366f1" name="ROAS" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Manufacturer Products Tab */}
      {activeTab === 'manufacturers' && (
        <div className="space-y-6">
          {/* Manufacturer Cards */}
          <div className="grid grid-cols-1 gap-4">
            {manufacturers.map((mfr) => (
              <div 
                key={mfr.manufacturer_id}
                className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-indigo-100 border border-indigo-200 flex items-center justify-center">
                      <Building2 className="w-6 h-6 text-indigo-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-slate-900">{mfr.manufacturer_name}</h3>
                      <p className="text-sm text-slate-500">{mfr.products.length} products</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedManufacturer(selectedManufacturer === mfr.manufacturer_id ? null : mfr.manufacturer_id)}
                    className="px-4 py-2 text-sm font-medium text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                  >
                    {selectedManufacturer === mfr.manufacturer_id ? 'Hide Products' : 'View Products'}
                  </button>
                </div>

                {/* Products Grid */}
                {selectedManufacturer === mfr.manufacturer_id && (
                  <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-slate-200">
                    {mfr.products.map((product) => (
                      <div 
                        key={product.product_id}
                        className="p-4 rounded-lg bg-slate-50 border border-slate-200"
                      >
                        <div className="flex items-start gap-3">
                          <div className="w-10 h-10 rounded-lg bg-white border border-slate-200 flex items-center justify-center">
                            <Package className="w-5 h-5 text-slate-600" />
                          </div>
                          <div className="flex-1">
                            <h4 className="font-medium text-slate-900">{product.product_name}</h4>
                            <p className="text-sm text-slate-500">{product.brand} • {product.category}</p>
                            {product.total_media_budget && (
                              <p className="text-sm font-medium text-indigo-600 mt-1">
                                Budget: {formatCurrency(product.total_media_budget)}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Simulation Tab - Device Cards */}
      {activeTab === 'simulation' && (
        <>
          {/* Device Cards Grid */}
          <div className="grid grid-cols-2 gap-4">
            {devices.map((device) => {
              const colors = statusColors[device.status] || statusColors.normal;
              const Icon = deviceIcons[device.type] || Box;
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
            {/* Marketing Spend Chart */}
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Thermometer className="w-5 h-5 text-indigo-500" />
                  <h2 className="text-lg font-semibold text-slate-900">Marketing Spend</h2>
                </div>
                <span className="text-sm text-indigo-600 font-medium">📊 Spend tracking</span>
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={telemetryHistory}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="time" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <Tooltip />
                    <ReferenceLine y={500} stroke="#6366f1" strokeDasharray="5 5" label={{ value: 'Target', fill: '#6366f1', fontSize: 10 }} />
                    <Line 
                      type="monotone" 
                      dataKey="inventory" 
                      stroke="#6366f1" 
                      strokeWidth={2}
                      dot={false}
                      name="Spend"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Revenue Chart */}
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Activity className="w-5 h-5 text-emerald-500" />
                  <h2 className="text-lg font-semibold text-slate-900">Revenue</h2>
                </div>
                <span className="text-sm text-emerald-600 font-medium">📈 Revenue patterns</span>
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={telemetryHistory}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="time" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <Tooltip />
                    <ReferenceLine y={150} stroke="#10b981" strokeDasharray="5 5" label={{ value: 'Baseline', fill: '#10b981', fontSize: 10 }} />
                    <Line 
                      type="monotone" 
                      dataKey="demand" 
                      stroke="#10b981" 
                      strokeWidth={2}
                      dot={false}
                      name="Revenue"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </>
      )}

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
            const severityColors: Record<string, string> = {
              info: 'bg-blue-100 text-blue-700 border-blue-200',
              warning: 'bg-amber-100 text-amber-700 border-amber-200',
              critical: 'bg-red-100 text-red-700 border-red-200',
            };
            const typeIcons: Record<string, typeof Activity> = {
              telemetry: Activity,
              alert: AlertTriangle,
              prediction: Cpu,
              action: CheckCircle,
            };
            const TypeIcon = typeIcons[activity.type] || Activity;
            
            return (
              <div 
                key={activity.id}
                className={`flex items-start gap-4 p-4 rounded-lg border ${
                  activity.severity === 'critical' ? 'bg-red-50 border-red-200' :
                  activity.severity === 'warning' ? 'bg-amber-50 border-amber-200' :
                  'bg-slate-50 border-slate-200'
                } animate-slide-in`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${severityColors[activity.severity] || severityColors.info}`}>
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
