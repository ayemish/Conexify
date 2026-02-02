import { useState } from 'react';
import {
  ChevronRight,
  ChevronDown,
  Building2,
  MapPin,
  Cpu,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Activity,
  Clock,
  Wrench,
  FileText,
  TrendingUp,
  TrendingDown,
  Shield,
  Database,
  Wifi,
  WifiOff,
  Gauge
} from 'lucide-react';
import { assets, tenants } from '../data/mockData';
import type { Asset, AssetStatus } from '../types';

// Mock data readiness scores per asset (FR-004)
const dataReadinessScores: Record<string, {
  overall: number;
  sensorCoverage: number;
  dataFreshness: number;
  signalQuality: number;
  missingMetrics: string[];
  staleMetrics: string[];
  driftDetected: boolean;
}> = {
  'asset-001': {
    overall: 94,
    sensorCoverage: 100,
    dataFreshness: 95,
    signalQuality: 87,
    missingMetrics: [],
    staleMetrics: [],
    driftDetected: false,
  },
  'asset-002': {
    overall: 72,
    sensorCoverage: 80,
    dataFreshness: 75,
    signalQuality: 60,
    missingMetrics: ['Oil Pressure'],
    staleMetrics: ['Vibration'],
    driftDetected: true,
  },
  'asset-003': {
    overall: 88,
    sensorCoverage: 95,
    dataFreshness: 90,
    signalQuality: 80,
    missingMetrics: [],
    staleMetrics: ['Suction Temperature'],
    driftDetected: false,
  },
};

const statusConfig: Record<AssetStatus, { color: string; bg: string; icon: typeof CheckCircle2 }> = {
  normal: { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle2 },
  warning: { color: 'text-amber-600', bg: 'bg-amber-100', icon: AlertTriangle },
  critical: { color: 'text-red-600', bg: 'bg-red-100', icon: AlertTriangle },
  offline: { color: 'text-slate-500', bg: 'bg-slate-100', icon: XCircle },
  maintenance: { color: 'text-blue-600', bg: 'bg-blue-100', icon: Wrench },
};

export function AssetExplorerPage() {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(['tenant-001', 'portfolio-001', 'site-001']));
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(assets[0]);

  const toggleNode = (nodeId: string) => {
    const newExpanded = new Set(expandedNodes);
    if (newExpanded.has(nodeId)) {
      newExpanded.delete(nodeId);
    } else {
      newExpanded.add(nodeId);
    }
    setExpandedNodes(newExpanded);
  };

  const getAssetsBysite = (siteId: string) => assets.filter(a => a.siteId === siteId);

  const getStatusCounts = (siteAssets: Asset[]) => {
    return {
      normal: siteAssets.filter(a => a.status === 'normal').length,
      warning: siteAssets.filter(a => a.status === 'warning').length,
      critical: siteAssets.filter(a => a.status === 'critical').length,
    };
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-8rem)]">
      {/* Asset Hierarchy Tree */}
      <div className="w-80 bg-white rounded-xl border border-slate-200 overflow-hidden flex flex-col">
        <div className="p-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-900">Asset Hierarchy</h2>
          <p className="text-xs text-slate-500 mt-1">Navigate portfolios, sites, and equipment</p>
        </div>
        <div className="flex-1 overflow-auto p-2">
          {tenants.map((tenant) => (
            <div key={tenant.id}>
              {/* Tenant Level */}
              <button
                onClick={() => toggleNode(tenant.id)}
                className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-slate-100 text-left"
              >
                {expandedNodes.has(tenant.id) ? (
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-slate-400" />
                )}
                <Building2 className="w-4 h-4 text-orange-500" />
                <span className="text-sm font-medium text-slate-900">{tenant.name}</span>
              </button>

              {expandedNodes.has(tenant.id) && (
                <div className="ml-4">
                  {tenant.portfolios.map((portfolio) => (
                    <div key={portfolio.id}>
                      {/* Portfolio Level */}
                      <button
                        onClick={() => toggleNode(portfolio.id)}
                        className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-slate-100 text-left"
                      >
                        {expandedNodes.has(portfolio.id) ? (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-slate-400" />
                        )}
                        <MapPin className="w-4 h-4 text-blue-500" />
                        <span className="text-sm text-slate-700">{portfolio.name}</span>
                      </button>

                      {expandedNodes.has(portfolio.id) && (
                        <div className="ml-4">
                          {portfolio.sites.map((site) => {
                            const siteAssets = getAssetsBysite(site.id);
                            const counts = getStatusCounts(siteAssets);
                            return (
                              <div key={site.id}>
                                {/* Site Level */}
                                <button
                                  onClick={() => toggleNode(site.id)}
                                  className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-slate-100 text-left"
                                >
                                  {expandedNodes.has(site.id) ? (
                                    <ChevronDown className="w-4 h-4 text-slate-400" />
                                  ) : (
                                    <ChevronRight className="w-4 h-4 text-slate-400" />
                                  )}
                                  <Building2 className="w-4 h-4 text-purple-500" />
                                  <span className="text-sm text-slate-700 flex-1">{site.name}</span>
                                  <div className="flex items-center gap-1">
                                    {counts.critical > 0 && (
                                      <span className="px-1.5 py-0.5 bg-red-100 text-red-700 text-xs rounded">
                                        {counts.critical}
                                      </span>
                                    )}
                                    {counts.warning > 0 && (
                                      <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-xs rounded">
                                        {counts.warning}
                                      </span>
                                    )}
                                  </div>
                                </button>

                                {expandedNodes.has(site.id) && (
                                  <div className="ml-4">
                                    {siteAssets.map((asset) => {
                                      const StatusIcon = statusConfig[asset.status].icon;
                                      return (
                                        <button
                                          key={asset.id}
                                          onClick={() => setSelectedAsset(asset)}
                                          className={`flex items-center gap-2 w-full px-2 py-1.5 rounded text-left ${
                                            selectedAsset?.id === asset.id
                                              ? 'bg-orange-50 border border-orange-200'
                                              : 'hover:bg-slate-100'
                                          }`}
                                        >
                                          <div className="w-4" />
                                          <Cpu className={`w-4 h-4 ${statusConfig[asset.status].color}`} />
                                          <span className="text-sm text-slate-700 truncate flex-1">
                                            {asset.name}
                                          </span>
                                          <StatusIcon className={`w-3 h-3 ${statusConfig[asset.status].color}`} />
                                        </button>
                                      );
                                    })}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Asset Detail Panel */}
      {selectedAsset ? (
        <div className="flex-1 space-y-4 overflow-auto">
          {/* Asset Header */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${statusConfig[selectedAsset.status].bg}`}>
                  <Cpu className={`w-7 h-7 ${statusConfig[selectedAsset.status].color}`} />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-slate-900">{selectedAsset.name}</h1>
                  <p className="text-sm text-slate-500">{selectedAsset.location}</p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${statusConfig[selectedAsset.status].bg} ${statusConfig[selectedAsset.status].color}`}>
                      {selectedAsset.status}
                    </span>
                    <span className="text-xs text-slate-500">{selectedAsset.type}</span>
                    {selectedAsset.autonomyEnabled && (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <Shield className="w-3 h-3" />
                        Autonomy Enabled
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {selectedAsset.openCases > 0 && (
                  <span className="px-2 py-1 bg-red-100 text-red-700 text-xs font-medium rounded">
                    {selectedAsset.openCases} Open Case{selectedAsset.openCases > 1 ? 's' : ''}
                  </span>
                )}
                {selectedAsset.recentAlerts > 0 && (
                  <span className="px-2 py-1 bg-amber-100 text-amber-700 text-xs font-medium rounded">
                    {selectedAsset.recentAlerts} Alert{selectedAsset.recentAlerts > 1 ? 's' : ''}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Data Readiness Score (FR-004) */}
          {(() => {
            const readiness = dataReadinessScores[selectedAsset.id] || {
              overall: 85,
              sensorCoverage: 90,
              dataFreshness: 85,
              signalQuality: 80,
              missingMetrics: [],
              staleMetrics: [],
              driftDetected: false,
            };
            const overallColor = readiness.overall >= 90 ? 'text-green-600' : 
                                 readiness.overall >= 70 ? 'text-amber-600' : 'text-red-600';
            const overallBg = readiness.overall >= 90 ? 'bg-green-50 border-green-200' : 
                              readiness.overall >= 70 ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200';
            return (
              <div className={`rounded-xl p-4 border ${overallBg}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-slate-600" />
                    <h2 className="font-semibold text-slate-900">Data Readiness</h2>
                  </div>
                  <div className="flex items-center gap-2">
                    <Gauge className={`w-5 h-5 ${overallColor}`} />
                    <span className={`text-2xl font-bold ${overallColor}`}>{readiness.overall}%</span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-white/80 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Wifi className="w-4 h-4 text-slate-500" />
                      <span className="text-xs text-slate-500">Sensor Coverage</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${readiness.sensorCoverage >= 90 ? 'bg-green-500' : readiness.sensorCoverage >= 70 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${readiness.sensorCoverage}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-slate-700">{readiness.sensorCoverage}%</span>
                    </div>
                  </div>
                  <div className="bg-white/80 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-4 h-4 text-slate-500" />
                      <span className="text-xs text-slate-500">Data Freshness</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${readiness.dataFreshness >= 90 ? 'bg-green-500' : readiness.dataFreshness >= 70 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${readiness.dataFreshness}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-slate-700">{readiness.dataFreshness}%</span>
                    </div>
                  </div>
                  <div className="bg-white/80 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Activity className="w-4 h-4 text-slate-500" />
                      <span className="text-xs text-slate-500">Signal Quality</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${readiness.signalQuality >= 90 ? 'bg-green-500' : readiness.signalQuality >= 70 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${readiness.signalQuality}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-slate-700">{readiness.signalQuality}%</span>
                    </div>
                  </div>
                </div>
                {(readiness.missingMetrics.length > 0 || readiness.staleMetrics.length > 0 || readiness.driftDetected) && (
                  <div className="mt-3 pt-3 border-t border-slate-200/50 flex items-center gap-4 text-xs">
                    {readiness.missingMetrics.length > 0 && (
                      <span className="flex items-center gap-1 text-red-600">
                        <WifiOff className="w-3 h-3" />
                        Missing: {readiness.missingMetrics.join(', ')}
                      </span>
                    )}
                    {readiness.staleMetrics.length > 0 && (
                      <span className="flex items-center gap-1 text-amber-600">
                        <Clock className="w-3 h-3" />
                        Stale: {readiness.staleMetrics.join(', ')}
                      </span>
                    )}
                    {readiness.driftDetected && (
                      <span className="flex items-center gap-1 text-purple-600">
                        <AlertTriangle className="w-3 h-3" />
                        Sensor Drift Detected
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })()}

          {/* Asset Info Grid */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-xs text-slate-500 mb-1">Manufacturer</p>
              <p className="font-medium text-slate-900">{selectedAsset.manufacturer || '—'}</p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-xs text-slate-500 mb-1">Model</p>
              <p className="font-medium text-slate-900">{selectedAsset.model || '—'}</p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-xs text-slate-500 mb-1">Serial Number</p>
              <p className="font-medium text-slate-900">{selectedAsset.serialNumber || '—'}</p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <p className="text-xs text-slate-500 mb-1">Last Maintenance</p>
              <p className="font-medium text-slate-900">
                {selectedAsset.lastMaintenance
                  ? new Date(selectedAsset.lastMaintenance).toLocaleDateString()
                  : '—'}
              </p>
            </div>
          </div>

          {/* Current Metrics */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <h2 className="font-semibold text-slate-900">Current Readings</h2>
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Updated {selectedAsset.metrics[0]?.timestamp ? new Date(selectedAsset.metrics[0].timestamp).toLocaleTimeString() : '—'}
              </span>
            </div>
            <div className="p-4 grid grid-cols-2 lg:grid-cols-4 gap-4">
              {selectedAsset.metrics.map((metric) => {
                const isOverThreshold = metric.threshold && (
                  (metric.threshold.max && metric.value > metric.threshold.max) ||
                  (metric.threshold.min && metric.value < metric.threshold.min)
                );
                return (
                  <div
                    key={metric.name}
                    className={`p-4 rounded-lg ${isOverThreshold ? 'bg-red-50 border border-red-200' : 'bg-slate-50'}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-slate-500">{metric.name}</span>
                      {metric.trend === 'up' ? (
                        <TrendingUp className={`w-4 h-4 ${isOverThreshold ? 'text-red-500' : 'text-slate-400'}`} />
                      ) : metric.trend === 'down' ? (
                        <TrendingDown className="w-4 h-4 text-slate-400" />
                      ) : (
                        <Activity className="w-4 h-4 text-slate-400" />
                      )}
                    </div>
                    <p className={`text-2xl font-bold ${isOverThreshold ? 'text-red-600' : 'text-slate-900'}`}>
                      {metric.value}
                      <span className="text-sm font-normal text-slate-500 ml-1">{metric.unit}</span>
                    </p>
                    {metric.threshold && (
                      <p className="text-xs text-slate-500 mt-1">
                        {metric.threshold.min && `Min: ${metric.threshold.min}`}
                        {metric.threshold.min && metric.threshold.max && ' | '}
                        {metric.threshold.max && `Max: ${metric.threshold.max}`}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h2 className="font-semibold text-slate-900 mb-4">Quick Actions</h2>
            <div className="flex items-center gap-3">
              <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
                <FileText className="w-4 h-4" />
                View Cases
              </button>
              <button className="flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm">
                <Wrench className="w-4 h-4" />
                Create Work Order
              </button>
              <button className="flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm">
                <Activity className="w-4 h-4" />
                View Telemetry
              </button>
              {selectedAsset.autonomyEnabled && (
                <button className="flex items-center gap-2 px-4 py-2 bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200 text-sm">
                  <Shield className="w-4 h-4" />
                  Safe Mode
                </button>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center bg-white rounded-xl border border-slate-200">
          <p className="text-slate-500">Select an asset to view details</p>
        </div>
      )}
    </div>
  );
}
