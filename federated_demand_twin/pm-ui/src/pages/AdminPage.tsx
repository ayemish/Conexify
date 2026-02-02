import { useState } from 'react';
import {
  Settings,
  Plug,
  Users,
  Bell,
  Shield,
  Database,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  RefreshCw,
  Plus,
  ExternalLink,
  Key,
  DollarSign,
  Save,
  Building2,
  Truck,
  Thermometer,
  Zap
} from 'lucide-react';
import { connectors } from '../data/mockData';
import type { ConnectorStatus, ConnectorType } from '../types';

interface CostModelConfig {
  siteId: string;
  siteName: string;
  truckRollCost: number;
  inspectionCost: number;
  downtimeCostPerHour: number;
  productLossRiskPerHour: number;
  energyWasteCostPerKwh: number;
  slaPenaltyAmount: number;
  criticalityMultiplier: number;
  currency: string;
}

const defaultCostModels: CostModelConfig[] = [
  {
    siteId: 'site-1',
    siteName: 'Galveston Platform A',
    truckRollCost: 350,
    inspectionCost: 150,
    downtimeCostPerHour: 2500,
    productLossRiskPerHour: 1200,
    energyWasteCostPerKwh: 0.12,
    slaPenaltyAmount: 5000,
    criticalityMultiplier: 1.5,
    currency: 'USD',
  },
  {
    siteId: 'site-2',
    siteName: 'Permian Basin Facility',
    truckRollCost: 450,
    inspectionCost: 200,
    downtimeCostPerHour: 3500,
    productLossRiskPerHour: 1800,
    energyWasteCostPerKwh: 0.10,
    slaPenaltyAmount: 7500,
    criticalityMultiplier: 2.0,
    currency: 'USD',
  },
  {
    siteId: 'site-3',
    siteName: 'Houston Data Center',
    truckRollCost: 275,
    inspectionCost: 125,
    downtimeCostPerHour: 5000,
    productLossRiskPerHour: 0,
    energyWasteCostPerKwh: 0.08,
    slaPenaltyAmount: 10000,
    criticalityMultiplier: 3.0,
    currency: 'USD',
  },
];

const statusConfig: Record<ConnectorStatus, { color: string; bg: string; icon: typeof CheckCircle2 }> = {
  connected: { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle2 },
  degraded: { color: 'text-amber-600', bg: 'bg-amber-100', icon: AlertTriangle },
  disconnected: { color: 'text-slate-500', bg: 'bg-slate-100', icon: XCircle },
  error: { color: 'text-red-600', bg: 'bg-red-100', icon: XCircle },
};

const typeConfig: Record<ConnectorType, { label: string; icon: typeof Database }> = {
  bms: { label: 'Building Management System', icon: Settings },
  scada: { label: 'SCADA', icon: Database },
  iot_gateway: { label: 'IoT Gateway', icon: Plug },
  cmms: { label: 'CMMS/EAM', icon: Settings },
  ticketing: { label: 'Ticketing System', icon: Bell },
  messaging: { label: 'Messaging', icon: Bell },
};

type TabType = 'connectors' | 'users' | 'notifications' | 'policies' | 'costmodel';

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<TabType>('connectors');
  const [selectedConnector, setSelectedConnector] = useState<string | null>(connectors[0]?.id);
  const [costModels, setCostModels] = useState<CostModelConfig[]>(defaultCostModels);
  const [selectedCostModelSite, setSelectedCostModelSite] = useState<string>(defaultCostModels[0].siteId);
  const [costModelDirty, setCostModelDirty] = useState(false);

  const selectedConn = connectors.find(c => c.id === selectedConnector);
  const selectedCostModel = costModels.find(c => c.siteId === selectedCostModelSite);

  const updateCostModel = (field: keyof CostModelConfig, value: number) => {
    setCostModels(prev => prev.map(cm => 
      cm.siteId === selectedCostModelSite ? { ...cm, [field]: value } : cm
    ));
    setCostModelDirty(true);
  };

  const saveCostModel = () => {
    setCostModelDirty(false);
    // In a real app, this would save to backend
  };

  const connectorStats = {
    total: connectors.length,
    connected: connectors.filter(c => c.status === 'connected').length,
    degraded: connectors.filter(c => c.status === 'degraded').length,
    writebackEnabled: connectors.filter(c => c.writebackEnabled).length,
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Administration</h1>
          <p className="text-slate-500 mt-1">Manage integrations, users, and system settings</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        {[
          { id: 'connectors', label: 'Connectors', icon: Plug },
          { id: 'costmodel', label: 'Cost Model', icon: DollarSign },
          { id: 'users', label: 'Users', icon: Users },
          { id: 'notifications', label: 'Notifications', icon: Bell },
          { id: 'policies', label: 'Policies', icon: Shield },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as TabType)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab.id ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'connectors' && (
        <>
          {/* Connector Stats */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                  <Plug className="w-5 h-5 text-slate-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-slate-900">{connectorStats.total}</p>
                  <p className="text-sm text-slate-500">Total Connectors</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl p-4 border border-green-200 bg-green-50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                  <CheckCircle2 className="w-5 h-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-green-600">{connectorStats.connected}</p>
                  <p className="text-sm text-green-700">Connected</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl p-4 border border-amber-200 bg-amber-50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-amber-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-amber-600">{connectorStats.degraded}</p>
                  <p className="text-sm text-amber-700">Degraded</p>
                </div>
              </div>
            </div>
            <div className="bg-white rounded-xl p-4 border border-blue-200 bg-blue-50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Shield className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-blue-600">{connectorStats.writebackEnabled}</p>
                  <p className="text-sm text-blue-700">Writeback Enabled</p>
                </div>
              </div>
            </div>
          </div>

          {/* Connectors Grid */}
          <div className="grid grid-cols-3 gap-4">
            {/* Connector List */}
            <div className="col-span-2 bg-white rounded-xl border border-slate-200">
              <div className="p-4 border-b border-slate-200 flex items-center justify-between">
                <h2 className="font-semibold text-slate-900">Integrations</h2>
                <button className="flex items-center gap-2 px-3 py-1.5 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
                  <Plus className="w-4 h-4" />
                  Add Connector
                </button>
              </div>
              <div className="divide-y divide-slate-100">
                {connectors.map((connector) => {
                  const StatusIcon = statusConfig[connector.status].icon;
                  const TypeIcon = typeConfig[connector.type].icon;
                  return (
                    <div
                      key={connector.id}
                      className={`p-4 hover:bg-slate-50 cursor-pointer transition-colors ${
                        selectedConnector === connector.id ? 'bg-orange-50 border-l-4 border-orange-500' : ''
                      }`}
                      onClick={() => setSelectedConnector(connector.id)}
                    >
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${statusConfig[connector.status].bg}`}>
                          <TypeIcon className={`w-5 h-5 ${statusConfig[connector.status].color}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-medium text-slate-900">{connector.name}</h3>
                            <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${statusConfig[connector.status].bg} ${statusConfig[connector.status].color}`}>
                              {connector.status}
                            </span>
                            {connector.writebackEnabled && (
                              <span className="px-2 py-0.5 text-xs font-medium rounded bg-blue-100 text-blue-700">
                                Writeback
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-slate-500">{typeConfig[connector.type].label}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-slate-500">Last Sync</p>
                          <p className="text-sm font-medium text-slate-700">
                            {new Date(connector.lastSync).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Connector Detail */}
            <div className="bg-white rounded-xl border border-slate-200">
              {selectedConn ? (
                <>
                  <div className="p-4 border-b border-slate-200">
                    <h2 className="font-semibold text-slate-900">Connector Details</h2>
                  </div>
                  <div className="p-4 space-y-4">
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Name</p>
                      <p className="font-medium text-slate-900">{selectedConn.name}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Type</p>
                      <p className="text-sm text-slate-700">{typeConfig[selectedConn.type].label}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Endpoint</p>
                      <p className="text-sm text-slate-700 font-mono break-all flex items-center gap-1">
                        {selectedConn.endpoint}
                        <ExternalLink className="w-3 h-3 text-slate-400" />
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-500">Uptime</p>
                        <p className="text-lg font-semibold text-slate-900">{selectedConn.uptime}%</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-500">Latency</p>
                        <p className="text-lg font-semibold text-slate-900">{selectedConn.latency}ms</p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-500">Error Rate</p>
                        <p className={`text-lg font-semibold ${selectedConn.errorRate > 1 ? 'text-amber-600' : 'text-slate-900'}`}>
                          {selectedConn.errorRate}%
                        </p>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-500">Writeback</p>
                        <p className={`text-lg font-semibold ${selectedConn.writebackEnabled ? 'text-green-600' : 'text-slate-500'}`}>
                          {selectedConn.writebackEnabled ? 'Enabled' : 'Disabled'}
                        </p>
                      </div>
                    </div>
                    {selectedConn.credentials && (
                      <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <Key className="w-4 h-4 text-slate-500" />
                          <p className="text-xs text-slate-500 font-medium">Credentials</p>
                        </div>
                        <p className="text-sm text-slate-700">
                          {selectedConn.credentials.configured ? 'Configured' : 'Not configured'}
                        </p>
                        {selectedConn.credentials.lastRotated && (
                          <p className="text-xs text-slate-500 mt-1">
                            Last rotated: {new Date(selectedConn.credentials.lastRotated).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                    )}
                    <div className="flex items-center gap-2 pt-2">
                      <button className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm">
                        <RefreshCw className="w-4 h-4" />
                        Test Connection
                      </button>
                      <button className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
                        <Settings className="w-4 h-4" />
                        Configure
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="p-8 text-center text-slate-500">
                  Select a connector to view details
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {activeTab === 'users' && (
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">User Management</h2>
            <button className="flex items-center gap-2 px-3 py-1.5 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
              <Plus className="w-4 h-4" />
              Invite User
            </button>
          </div>
          <div className="p-6">
            <div className="space-y-4">
              {[
                { name: 'Alex Chen', email: 'alex.chen@arcticpulse.com', role: 'Senior Operator', status: 'active' },
                { name: 'Jordan Martinez', email: 'jordan.m@arcticpulse.com', role: 'Operator', status: 'active' },
                { name: 'Admin User', email: 'admin@arcticpulse.com', role: 'Platform Admin', status: 'active' },
                { name: 'ML Engineer', email: 'ml@arcticpulse.com', role: 'ML Admin', status: 'active' },
              ].map((user) => (
                <div key={user.email} className="flex items-center gap-4 p-4 bg-slate-50 rounded-lg">
                  <div className="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center">
                    <span className="text-orange-600 font-medium">{user.name.split(' ').map(n => n[0]).join('')}</span>
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-slate-900">{user.name}</p>
                    <p className="text-sm text-slate-500">{user.email}</p>
                  </div>
                  <span className="px-2 py-1 bg-slate-200 text-slate-700 text-xs font-medium rounded">
                    {user.role}
                  </span>
                  <span className="px-2 py-1 bg-green-100 text-green-700 text-xs font-medium rounded">
                    {user.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'notifications' && (
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Notification Rules</h2>
            <button className="flex items-center gap-2 px-3 py-1.5 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
              <Plus className="w-4 h-4" />
              Add Rule
            </button>
          </div>
          <div className="p-6">
            <div className="space-y-4">
              {[
                { name: 'Critical Case Alert', trigger: 'Case severity = Critical', channel: 'Email, SMS, Teams', enabled: true },
                { name: 'SLA Breach Warning', trigger: 'SLA < 1 hour remaining', channel: 'Email, Teams', enabled: true },
                { name: 'Model Drift Alert', trigger: 'Accuracy < 90%', channel: 'Email', enabled: true },
                { name: 'Connector Failure', trigger: 'Connector status = Error', channel: 'SMS, Teams', enabled: false },
              ].map((rule) => (
                <div key={rule.name} className="flex items-center gap-4 p-4 bg-slate-50 rounded-lg">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${rule.enabled ? 'bg-green-100' : 'bg-slate-200'}`}>
                    <Bell className={`w-5 h-5 ${rule.enabled ? 'text-green-600' : 'text-slate-400'}`} />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-slate-900">{rule.name}</p>
                    <p className="text-sm text-slate-500">{rule.trigger}</p>
                  </div>
                  <span className="text-xs text-slate-500">{rule.channel}</span>
                  <button
                    className={`relative w-11 h-6 rounded-full transition-colors ${
                      rule.enabled ? 'bg-green-500' : 'bg-slate-300'
                    }`}
                  >
                    <span className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
                      rule.enabled ? 'left-6' : 'left-1'
                    }`} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'policies' && (
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Policy Management</h2>
            <button className="flex items-center gap-2 px-3 py-1.5 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
              <Plus className="w-4 h-4" />
              Create Policy
            </button>
          </div>
          <div className="p-6">
            <div className="space-y-4">
              {[
                { name: 'Default Autonomy Policy', scope: 'Global', actions: 12, approvals: 'Medium+ risk requires approval', version: 3 },
                { name: 'Galveston Platform Policy', scope: 'Site: Galveston Platform A', actions: 8, approvals: 'All actions require approval', version: 2 },
                { name: 'HVAC Control Bounds', scope: 'Asset Type: HVAC', actions: 5, approvals: 'Low risk auto-execute', version: 1 },
              ].map((policy) => (
                <div key={policy.name} className="flex items-center gap-4 p-4 bg-slate-50 rounded-lg">
                  <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                    <Shield className="w-5 h-5 text-purple-600" />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-slate-900">{policy.name}</p>
                    <p className="text-sm text-slate-500">{policy.scope}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-500">{policy.actions} allowed actions</p>
                    <p className="text-xs text-slate-400">v{policy.version}</p>
                  </div>
                  <button className="px-3 py-1.5 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 text-sm">
                    Edit
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'costmodel' && (
        <div className="grid grid-cols-3 gap-6">
          {/* Site Selector */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200">
              <h2 className="font-semibold text-slate-900">Sites</h2>
              <p className="text-xs text-slate-500 mt-1">Select site to configure cost model</p>
            </div>
            <div className="divide-y divide-slate-100">
              {costModels.map((cm) => (
                <button
                  key={cm.siteId}
                  onClick={() => setSelectedCostModelSite(cm.siteId)}
                  className={`w-full p-4 text-left hover:bg-slate-50 transition-colors ${
                    selectedCostModelSite === cm.siteId ? 'bg-orange-50 border-l-4 border-orange-500' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
                      <Building2 className="w-5 h-5 text-slate-600" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-900">{cm.siteName}</p>
                      <p className="text-xs text-slate-500">
                        ${cm.downtimeCostPerHour.toLocaleString()}/hr downtime
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Cost Model Configuration */}
          <div className="col-span-2 bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h2 className="font-semibold text-slate-900">Cost Model Configuration</h2>
                <p className="text-xs text-slate-500 mt-1">
                  {selectedCostModel?.siteName || 'Select a site'}
                </p>
              </div>
              <button
                onClick={saveCostModel}
                disabled={!costModelDirty}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  costModelDirty 
                    ? 'bg-orange-600 text-white hover:bg-orange-700' 
                    : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                }`}
              >
                <Save className="w-4 h-4" />
                Save Changes
              </button>
            </div>

            {selectedCostModel && (
              <div className="p-6">
                <div className="grid grid-cols-2 gap-6">
                  {/* Service Costs */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <Truck className="w-4 h-4 text-slate-500" />
                      Service Costs
                    </h3>
                    
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Truck Roll Cost ($)</label>
                      <input
                        type="number"
                        value={selectedCostModel.truckRollCost}
                        onChange={(e) => updateCostModel('truckRollCost', parseFloat(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                      <p className="text-xs text-slate-400 mt-1">Cost per technician dispatch</p>
                    </div>

                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Inspection Cost ($)</label>
                      <input
                        type="number"
                        value={selectedCostModel.inspectionCost}
                        onChange={(e) => updateCostModel('inspectionCost', parseFloat(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                      <p className="text-xs text-slate-400 mt-1">Cost for routine inspection</p>
                    </div>
                  </div>

                  {/* Downtime & Loss Costs */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <Clock className="w-4 h-4 text-slate-500" />
                      Downtime & Loss Costs
                    </h3>
                    
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Downtime Cost ($/hour)</label>
                      <input
                        type="number"
                        value={selectedCostModel.downtimeCostPerHour}
                        onChange={(e) => updateCostModel('downtimeCostPerHour', parseFloat(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                      <p className="text-xs text-slate-400 mt-1">Cost of unplanned downtime per hour</p>
                    </div>

                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Product Loss Risk ($/hour)</label>
                      <input
                        type="number"
                        value={selectedCostModel.productLossRiskPerHour}
                        onChange={(e) => updateCostModel('productLossRiskPerHour', parseFloat(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                      <p className="text-xs text-slate-400 mt-1">Refrigeration product loss risk</p>
                    </div>
                  </div>

                  {/* Energy Costs */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <Zap className="w-4 h-4 text-slate-500" />
                      Energy Costs
                    </h3>
                    
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Energy Waste Cost ($/kWh)</label>
                      <input
                        type="number"
                        step="0.01"
                        value={selectedCostModel.energyWasteCostPerKwh}
                        onChange={(e) => updateCostModel('energyWasteCostPerKwh', parseFloat(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                      <p className="text-xs text-slate-400 mt-1">Cost per kWh of wasted energy</p>
                    </div>
                  </div>

                  {/* SLA & Penalties */}
                  <div className="space-y-4">
                    <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-slate-500" />
                      SLA & Penalties
                    </h3>
                    
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">SLA Penalty Amount ($)</label>
                      <input
                        type="number"
                        value={selectedCostModel.slaPenaltyAmount}
                        onChange={(e) => updateCostModel('slaPenaltyAmount', parseFloat(e.target.value) || 0)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                      <p className="text-xs text-slate-400 mt-1">Penalty for SLA breach</p>
                    </div>

                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Criticality Multiplier</label>
                      <input
                        type="number"
                        step="0.1"
                        value={selectedCostModel.criticalityMultiplier}
                        onChange={(e) => updateCostModel('criticalityMultiplier', parseFloat(e.target.value) || 1)}
                        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      />
                      <p className="text-xs text-slate-400 mt-1">Multiplier for critical asset costs</p>
                    </div>
                  </div>
                </div>

                {/* Cost Summary */}
                <div className="mt-6 p-4 bg-slate-50 rounded-lg">
                  <h3 className="text-sm font-semibold text-slate-900 mb-3">Expected Value Calculation Preview</h3>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-xs text-slate-500">Action Cost (Dispatch)</p>
                      <p className="font-semibold text-slate-900">
                        ${(selectedCostModel.truckRollCost + selectedCostModel.inspectionCost).toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Avoided Cost (4hr failure)</p>
                      <p className="font-semibold text-green-600">
                        ${((selectedCostModel.downtimeCostPerHour + selectedCostModel.productLossRiskPerHour) * 4).toLocaleString()}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Break-even Confidence</p>
                      <p className="font-semibold text-orange-600">
                        {(((selectedCostModel.truckRollCost + selectedCostModel.inspectionCost) / 
                          ((selectedCostModel.downtimeCostPerHour + selectedCostModel.productLossRiskPerHour) * 4)) * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
