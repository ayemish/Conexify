import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Database, CheckCircle, Clock, Play, Users, 
  AlertTriangle, RefreshCw, Shield, Building2,
  Activity, Zap, Globe, ShoppingCart, ChevronDown, ChevronRight,
  Layers, Lock, FileText, Package, ExternalLink
} from 'lucide-react';

// Retailer Data Source with embedded TEE and Normalization teams
interface RetailerDataSource {
  id: string;
  name: string;
  icon: string;
  connected: boolean;
  lastSync?: string;
  databases: {
    id: string;
    name: string;
    category: string;
    recordCount: number;
    status: 'syncing' | 'ready' | 'error';
  }[];
  teeTeam: {
    status: 'idle' | 'deployed' | 'working' | 'complete';
    agents: {
      id: string;
      name: string;
      status: 'idle' | 'working' | 'complete' | 'error';
      progress?: number;
      lastMessage?: string;
    }[];
    privacyBudgetUsed: number;
    privacyBudgetTotal: number;
    dpReleasesIssued: number;
    proofsGenerated: number;
  };
  normalizationTeam: {
    status: 'idle' | 'discovering' | 'mapping' | 'validating' | 'complete' | 'error';
    currentAgent?: string;
    campaignsNormalized: number;
    performanceRecords: number;
    productsNormalized: number;
    errors: number;
  };
}

interface OrganizationData {
  id: string;
  name: string;
  logo?: string;
  retailerDataSources: RetailerDataSource[];
  totalDatabases: number;
  totalRecords: number;
}

const retailerIcons: Record<string, typeof ShoppingCart> = {
  walmart: ShoppingCart,
  target: Building2,
  amazon: Globe,
  instacart: Zap,
  albertsons: Building2,
};

const retailerColors: Record<string, { bg: string; border: string; text: string }> = {
  walmart: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700' },
  target: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700' },
  amazon: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700' },
  instacart: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700' },
  albertsons: { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700' },
};

export function DataFederationPage() {
  const navigate = useNavigate();
  const [organization, setOrganization] = useState<OrganizationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedRetailer, setExpandedRetailer] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Record<string, 'data' | 'tee' | 'normalization'>>({});

  const fetchData = async () => {
    try {
      const res = await fetch('/api/data-federation/organization');
      if (res.ok) {
        const data = await res.json();
        setOrganization(data);
      }
    } catch (err) {
      console.error('Failed to fetch organization data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  const toggleRetailer = (retailerId: string) => {
    setExpandedRetailer(expandedRetailer === retailerId ? null : retailerId);
    if (!activeTab[retailerId]) {
      setActiveTab(prev => ({ ...prev, [retailerId]: 'data' }));
    }
  };

  const setRetailerTab = (retailerId: string, tab: 'data' | 'tee' | 'normalization') => {
    setActiveTab(prev => ({ ...prev, [retailerId]: tab }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading Data Federation...</span>
      </div>
    );
  }

  if (!organization) {
    return (
      <div className="text-center py-12">
        <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-slate-700">Unable to load organization data</h2>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Organization Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-xl bg-white/20 flex items-center justify-center">
              <Package className="w-8 h-8 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">{organization.name}</h1>
              <p className="text-indigo-200 mt-1">Data Federation Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div className="text-center">
              <p className="text-3xl font-bold">{organization.retailerDataSources.length}</p>
              <p className="text-xs text-indigo-200">Retailer Sources</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold">{organization.totalDatabases}</p>
              <p className="text-xs text-indigo-200">Total Databases</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold">{(organization.totalRecords / 1000000).toFixed(1)}M</p>
              <p className="text-xs text-indigo-200">Total Records</p>
            </div>
            <div className="flex items-center gap-2 text-sm bg-white/20 px-3 py-1.5 rounded-lg">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Live</span>
            </div>
          </div>
        </div>
      </div>

      {/* Retailer Data Sources */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
          <Database className="w-5 h-5 text-indigo-600" />
          Retailer Data Sources
        </h2>

        {organization.retailerDataSources.map((retailer) => {
          const isExpanded = expandedRetailer === retailer.id;
          const RetailerIcon = retailerIcons[retailer.id] || Building2;
          const colors = retailerColors[retailer.id] || retailerColors.walmart;
          const currentTab = activeTab[retailer.id] || 'data';

          // Calculate overall status
          const teeWorking = retailer.teeTeam.status === 'working';
          const normWorking = ['discovering', 'mapping', 'validating'].includes(retailer.normalizationTeam.status);
          const allComplete = retailer.teeTeam.status === 'complete' && retailer.normalizationTeam.status === 'complete';

          return (
            <div key={retailer.id} className={`bg-white rounded-xl border-2 ${colors.border} overflow-hidden transition-all`}>
              {/* Retailer Header - Always Visible */}
              <div
                className={`p-4 cursor-pointer hover:bg-slate-50 transition-colors ${colors.bg}`}
                onClick={() => toggleRetailer(retailer.id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-xl ${colors.bg} border-2 ${colors.border} flex items-center justify-center`}>
                      <RetailerIcon className={`w-6 h-6 ${colors.text}`} />
                    </div>
                    <div>
                      <h3 className="font-bold text-lg text-slate-900">{retailer.name}</h3>
                      <p className="text-sm text-slate-500">
                        {retailer.databases.length} databases • {retailer.databases.reduce((s, d) => s + d.recordCount, 0).toLocaleString()} records
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    {/* Quick Status Indicators */}
                    <div className="flex items-center gap-4">
                      {/* TEE Status */}
                      <div className="flex items-center gap-2">
                        <Shield className={`w-5 h-5 ${teeWorking ? 'text-emerald-500 animate-pulse' : allComplete ? 'text-emerald-500' : 'text-slate-400'}`} />
                        <span className="text-sm text-slate-600">TEE</span>
                        {teeWorking && <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">Working</span>}
                        {retailer.teeTeam.status === 'complete' && <CheckCircle className="w-4 h-4 text-emerald-500" />}
                      </div>

                      {/* Normalization Status */}
                      <div className="flex items-center gap-2">
                        <Layers className={`w-5 h-5 ${normWorking ? 'text-amber-500 animate-pulse' : retailer.normalizationTeam.status === 'complete' ? 'text-emerald-500' : 'text-slate-400'}`} />
                        <span className="text-sm text-slate-600">Normalization</span>
                        {normWorking && <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">{retailer.normalizationTeam.status}</span>}
                        {retailer.normalizationTeam.status === 'complete' && <CheckCircle className="w-4 h-4 text-emerald-500" />}
                      </div>
                    </div>

                    {/* Expand/Collapse */}
                    <div className={`transition-transform ${isExpanded ? 'rotate-0' : ''}`}>
                      {isExpanded ? <ChevronDown className="w-6 h-6 text-slate-400" /> : <ChevronRight className="w-6 h-6 text-slate-400" />}
                    </div>
                  </div>
                </div>
              </div>

              {/* Expanded Content */}
              {isExpanded && (
                <div className="border-t border-slate-200">
                  {/* Tabs */}
                  <div className="flex border-b border-slate-200 bg-slate-50">
                    <button
                      onClick={(e) => { e.stopPropagation(); setRetailerTab(retailer.id, 'data'); }}
                      className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                        currentTab === 'data'
                          ? 'border-indigo-500 text-indigo-600 bg-white'
                          : 'border-transparent text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Database className="w-4 h-4" />
                        Data Sources
                      </div>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setRetailerTab(retailer.id, 'tee'); }}
                      className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                        currentTab === 'tee'
                          ? 'border-emerald-500 text-emerald-600 bg-white'
                          : 'border-transparent text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Shield className="w-4 h-4" />
                        TEE Agent Team
                        {teeWorking && <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />}
                      </div>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setRetailerTab(retailer.id, 'normalization'); }}
                      className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                        currentTab === 'normalization'
                          ? 'border-amber-500 text-amber-600 bg-white'
                          : 'border-transparent text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Layers className="w-4 h-4" />
                        Normalization Team
                        {normWorking && <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />}
                      </div>
                    </button>
                  </div>

                  {/* Tab Content */}
                  <div className="p-6">
                    {/* Data Sources Tab */}
                    {currentTab === 'data' && (
                      <div className="grid grid-cols-3 gap-4">
                        {retailer.databases.map((db) => (
                          <div key={db.id} className="p-4 rounded-lg border border-slate-200 bg-slate-50">
                            <div className="flex items-center gap-3 mb-2">
                              <Database className={`w-5 h-5 ${db.status === 'ready' ? 'text-emerald-500' : db.status === 'syncing' ? 'text-blue-500 animate-pulse' : 'text-red-500'}`} />
                              <div>
                                <h4 className="font-medium text-slate-900">{db.name}</h4>
                                <p className="text-xs text-slate-500">{db.category}</p>
                              </div>
                            </div>
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-slate-600">{db.recordCount.toLocaleString()} records</span>
                              <span className={`px-2 py-0.5 rounded-full text-xs ${
                                db.status === 'ready' ? 'bg-emerald-100 text-emerald-700' :
                                db.status === 'syncing' ? 'bg-blue-100 text-blue-700' :
                                'bg-red-100 text-red-700'
                              }`}>
                                {db.status}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* TEE Agent Team Tab */}
                    {currentTab === 'tee' && (
                      <div className="space-y-6">
                        {/* TEE Status Overview */}
                        <div className="grid grid-cols-4 gap-4">
                          <div className="p-4 rounded-lg bg-emerald-50 border border-emerald-200">
                            <div className="flex items-center gap-2 mb-2">
                              <Shield className="w-5 h-5 text-emerald-600" />
                              <span className="font-medium text-emerald-900">Status</span>
                            </div>
                            <p className="text-lg font-bold text-emerald-700 capitalize">{retailer.teeTeam.status}</p>
                          </div>
                          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                            <div className="flex items-center gap-2 mb-2">
                              <Lock className="w-5 h-5 text-slate-600" />
                              <span className="font-medium text-slate-700">Privacy Budget</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-3 bg-slate-200 rounded-full overflow-hidden">
                                <div 
                                  className="h-full bg-emerald-500 rounded-full"
                                  style={{ width: `${(1 - retailer.teeTeam.privacyBudgetUsed / retailer.teeTeam.privacyBudgetTotal) * 100}%` }}
                                />
                              </div>
                              <span className="font-bold text-slate-700">
                                {Math.round((1 - retailer.teeTeam.privacyBudgetUsed / retailer.teeTeam.privacyBudgetTotal) * 100)}%
                              </span>
                            </div>
                          </div>
                          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                            <p className="text-xs text-slate-500 mb-1">DP Releases</p>
                            <p className="text-2xl font-bold text-slate-900">{retailer.teeTeam.dpReleasesIssued}</p>
                          </div>
                          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                            <p className="text-xs text-slate-500 mb-1">Proofs Generated</p>
                            <p className="text-2xl font-bold text-slate-900">{retailer.teeTeam.proofsGenerated}</p>
                          </div>
                        </div>

                        {/* TEE Agents */}
                        <div>
                          <h4 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                            <Users className="w-5 h-5 text-emerald-600" />
                            Agent Team
                          </h4>
                          <div className="grid grid-cols-4 gap-3">
                            {retailer.teeTeam.agents.map((agent) => (
                              <div key={agent.id} className={`p-3 rounded-lg border ${
                                agent.status === 'working' ? 'bg-emerald-50 border-emerald-200' :
                                agent.status === 'complete' ? 'bg-green-50 border-green-200' :
                                agent.status === 'error' ? 'bg-red-50 border-red-200' :
                                'bg-slate-50 border-slate-200'
                              }`}>
                                <div className="flex items-center gap-2 mb-1">
                                  {agent.status === 'working' && <Activity className="w-4 h-4 text-emerald-600 animate-pulse" />}
                                  {agent.status === 'complete' && <CheckCircle className="w-4 h-4 text-green-600" />}
                                  {agent.status === 'error' && <AlertTriangle className="w-4 h-4 text-red-600" />}
                                  {agent.status === 'idle' && <Clock className="w-4 h-4 text-slate-400" />}
                                  <span className="font-medium text-sm">{agent.name}</span>
                                </div>
                                {agent.progress !== undefined && agent.status === 'working' && (
                                  <div className="mt-2">
                                    <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                      <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${agent.progress}%` }} />
                                    </div>
                                    <p className="text-xs text-slate-500 mt-1">{agent.progress}%</p>
                                  </div>
                                )}
                                {agent.lastMessage && (
                                  <p className="text-xs text-slate-500 mt-1 truncate">{agent.lastMessage}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* View Full TEE State Button */}
                        <div className="pt-4 border-t border-slate-200">
                          <button
                            onClick={(e) => { e.stopPropagation(); navigate(`/retail-media/tee-state/${retailer.id}`); }}
                            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                          >
                            <ExternalLink className="w-4 h-4" />
                            View Full TEE State & DP Release Console
                          </button>
                          <p className="text-xs text-slate-500 mt-2">
                            Access detailed normalization state, release history, DP release form, and capabilities overview
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Normalization Team Tab */}
                    {currentTab === 'normalization' && (
                      <div className="space-y-6">
                        {/* Normalization Status Overview */}
                        <div className="grid grid-cols-5 gap-4">
                          <div className="p-4 rounded-lg bg-amber-50 border border-amber-200">
                            <div className="flex items-center gap-2 mb-2">
                              <Layers className="w-5 h-5 text-amber-600" />
                              <span className="font-medium text-amber-900">Status</span>
                            </div>
                            <p className="text-lg font-bold text-amber-700 capitalize">{retailer.normalizationTeam.status}</p>
                            {retailer.normalizationTeam.currentAgent && (
                              <p className="text-xs text-amber-600 mt-1 flex items-center gap-1">
                                <Activity className="w-3 h-3 animate-pulse" />
                                {retailer.normalizationTeam.currentAgent}
                              </p>
                            )}
                          </div>
                          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                            <p className="text-xs text-slate-500 mb-1">Campaigns</p>
                            <p className="text-2xl font-bold text-slate-900">{retailer.normalizationTeam.campaignsNormalized}</p>
                          </div>
                          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                            <p className="text-xs text-slate-500 mb-1">Performance Records</p>
                            <p className="text-2xl font-bold text-slate-900">{retailer.normalizationTeam.performanceRecords.toLocaleString()}</p>
                          </div>
                          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                            <p className="text-xs text-slate-500 mb-1">Products</p>
                            <p className="text-2xl font-bold text-slate-900">{retailer.normalizationTeam.productsNormalized}</p>
                          </div>
                          <div className={`p-4 rounded-lg border ${retailer.normalizationTeam.errors > 0 ? 'bg-red-50 border-red-200' : 'bg-slate-50 border-slate-200'}`}>
                            <p className="text-xs text-slate-500 mb-1">Errors</p>
                            <p className={`text-2xl font-bold ${retailer.normalizationTeam.errors > 0 ? 'text-red-600' : 'text-slate-900'}`}>
                              {retailer.normalizationTeam.errors}
                            </p>
                          </div>
                        </div>

                        {/* Normalization Crew Agents */}
                        <div>
                          <h4 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                            <Users className="w-5 h-5 text-amber-600" />
                            Normalization Crew
                          </h4>
                          <div className="grid grid-cols-4 gap-3">
                            {[
                              { id: 'discovery', name: 'Schema Discovery', phase: 'discovering' },
                              { id: 'mapper', name: 'Schema Mapper', phase: 'mapping' },
                              { id: 'translator', name: 'Taxonomy Translator', phase: 'mapping' },
                              { id: 'validator', name: 'Data Validator', phase: 'validating' },
                            ].map((agent) => {
                              const isActive = retailer.normalizationTeam.status === agent.phase;
                              const isComplete = ['complete'].includes(retailer.normalizationTeam.status) || 
                                (agent.phase === 'discovering' && ['mapping', 'validating', 'complete'].includes(retailer.normalizationTeam.status)) ||
                                (agent.phase === 'mapping' && ['validating', 'complete'].includes(retailer.normalizationTeam.status));
                              
                              return (
                                <div key={agent.id} className={`p-3 rounded-lg border ${
                                  isActive ? 'bg-amber-50 border-amber-200' :
                                  isComplete ? 'bg-green-50 border-green-200' :
                                  'bg-slate-50 border-slate-200'
                                }`}>
                                  <div className="flex items-center gap-2">
                                    {isActive && <Activity className="w-4 h-4 text-amber-600 animate-pulse" />}
                                    {isComplete && <CheckCircle className="w-4 h-4 text-green-600" />}
                                    {!isActive && !isComplete && <Clock className="w-4 h-4 text-slate-400" />}
                                    <span className="font-medium text-sm">{agent.name}</span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {/* Audit Trail */}
                        <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                          <h4 className="font-semibold text-slate-900 mb-2 flex items-center gap-2">
                            <FileText className="w-4 h-4 text-slate-600" />
                            Normalization Audit Trail
                          </h4>
                          <p className="text-sm text-slate-600">
                            All schema mappings and transformations are logged for compliance and debugging.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
