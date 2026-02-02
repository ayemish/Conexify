import { useState, useMemo } from 'react';
import {
  AlertTriangle, Clock, MapPin, Wrench, Filter, Search, ChevronDown,
  ChevronRight, User, Building2, Thermometer, DollarSign, TrendingUp,
  CheckCircle, XCircle, ArrowUpRight, MoreVertical, RefreshCw
} from 'lucide-react';

interface Case {
  id: string;
  caseNumber: string;
  asset: { id: string; name: string; type: string };
  site: { id: string; name: string; address: string; region: string };
  fault: { type: string; description: string; confidence: number };
  severity: 'critical' | 'high' | 'medium' | 'low';
  priority: number;
  status: 'new' | 'triaging' | 'dispatched' | 'in_progress' | 'pending_verification' | 'closed';
  sla: { dueAt: string; status: 'on_track' | 'at_risk' | 'breached' };
  ev: { value: number; components: { savings: number; cost: number } };
  createdAt: string;
  assignedTo?: string;
  uncertainty: number;
}

const mockCases: Case[] = [
  {
    id: 'case-001', caseNumber: 'PDM-2024-0142',
    asset: { id: 'rtu-101', name: 'RTU-101', type: 'rtu' },
    site: { id: 'store-42', name: 'Store #42 - Oakdale', address: '1234 Main St, Oakdale, CA', region: 'West' },
    fault: { type: 'compressor_degradation', description: 'Compressor showing signs of degradation, reduced cooling capacity', confidence: 0.89 },
    severity: 'high', priority: 1, status: 'new',
    sla: { dueAt: '2024-01-28T16:00:00Z', status: 'on_track' },
    ev: { value: 2450, components: { savings: 3200, cost: 750 } },
    createdAt: '2024-01-28T08:15:00Z', uncertainty: 0.15
  },
  {
    id: 'case-002', caseNumber: 'PDM-2024-0143',
    asset: { id: 'rack-205', name: 'Dairy Rack B', type: 'rack' },
    site: { id: 'store-18', name: 'Store #18 - Riverside', address: '567 Oak Ave, Riverside, CA', region: 'West' },
    fault: { type: 'refrigerant_leak', description: 'Suspected refrigerant leak, suction pressure dropping', confidence: 0.94 },
    severity: 'critical', priority: 1, status: 'triaging',
    sla: { dueAt: '2024-01-28T12:00:00Z', status: 'at_risk' },
    ev: { value: 5800, components: { savings: 8500, cost: 2700 } },
    createdAt: '2024-01-28T06:30:00Z', uncertainty: 0.08
  },
  {
    id: 'case-003', caseNumber: 'PDM-2024-0144',
    asset: { id: 'walk-in-03', name: 'Walk-in Freezer #3', type: 'walk_in_freezer' },
    site: { id: 'store-42', name: 'Store #42 - Oakdale', address: '1234 Main St, Oakdale, CA', region: 'West' },
    fault: { type: 'evaporator_frost', description: 'Excessive frost buildup on evaporator coils', confidence: 0.82 },
    severity: 'medium', priority: 2, status: 'dispatched',
    sla: { dueAt: '2024-01-29T10:00:00Z', status: 'on_track' },
    ev: { value: 890, components: { savings: 1200, cost: 310 } },
    createdAt: '2024-01-27T14:20:00Z', assignedTo: 'Mike Johnson', uncertainty: 0.22
  },
];

const severityConfig = {
  critical: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-300', dot: 'bg-red-500' },
  high: { bg: 'bg-orange-100', text: 'text-orange-700', border: 'border-orange-300', dot: 'bg-orange-500' },
  medium: { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-300', dot: 'bg-yellow-500' },
  low: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-300', dot: 'bg-blue-500' },
};

const statusConfig = {
  new: { bg: 'bg-purple-100', text: 'text-purple-700', label: 'New' },
  triaging: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Triaging' },
  dispatched: { bg: 'bg-indigo-100', text: 'text-indigo-700', label: 'Dispatched' },
  in_progress: { bg: 'bg-cyan-100', text: 'text-cyan-700', label: 'In Progress' },
  pending_verification: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Verifying' },
  closed: { bg: 'bg-green-100', text: 'text-green-700', label: 'Closed' },
};

const slaConfig = {
  on_track: { bg: 'bg-green-100', text: 'text-green-700', icon: CheckCircle },
  at_risk: { bg: 'bg-amber-100', text: 'text-amber-700', icon: Clock },
  breached: { bg: 'bg-red-100', text: 'text-red-700', icon: XCircle },
};

export default function OperationsCenterPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'priority' | 'ev' | 'sla' | 'created'>('priority');
  const [expandedCase, setExpandedCase] = useState<string | null>(null);

  const filteredCases = useMemo(() => {
    return mockCases
      .filter(c => {
        if (searchQuery && !c.caseNumber.toLowerCase().includes(searchQuery.toLowerCase()) &&
            !c.site.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
            !c.asset.name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
        if (severityFilter !== 'all' && c.severity !== severityFilter) return false;
        if (statusFilter !== 'all' && c.status !== statusFilter) return false;
        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'priority') return a.priority - b.priority;
        if (sortBy === 'ev') return b.ev.value - a.ev.value;
        if (sortBy === 'sla') return new Date(a.sla.dueAt).getTime() - new Date(b.sla.dueAt).getTime();
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      });
  }, [searchQuery, severityFilter, statusFilter, sortBy]);

  const stats = useMemo(() => ({
    total: mockCases.length,
    critical: mockCases.filter(c => c.severity === 'critical').length,
    atRisk: mockCases.filter(c => c.sla.status === 'at_risk' || c.sla.status === 'breached').length,
    totalEV: mockCases.reduce((sum, c) => sum + c.ev.value, 0),
  }), []);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Operations Center</h1>
          <p className="text-slate-500">Case queue and triage dashboard</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700">
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-500">Open Cases</span>
            <AlertTriangle className="w-5 h-5 text-slate-400" />
          </div>
          <p className="text-3xl font-bold text-slate-900 mt-2">{stats.total}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-red-200 bg-red-50">
          <div className="flex items-center justify-between">
            <span className="text-sm text-red-600">Critical</span>
            <AlertTriangle className="w-5 h-5 text-red-500" />
          </div>
          <p className="text-3xl font-bold text-red-700 mt-2">{stats.critical}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-amber-200 bg-amber-50">
          <div className="flex items-center justify-between">
            <span className="text-sm text-amber-600">SLA At Risk</span>
            <Clock className="w-5 h-5 text-amber-500" />
          </div>
          <p className="text-3xl font-bold text-amber-700 mt-2">{stats.atRisk}</p>
        </div>
        <div className="bg-white rounded-xl p-4 border border-green-200 bg-green-50">
          <div className="flex items-center justify-between">
            <span className="text-sm text-green-600">Total EV</span>
            <DollarSign className="w-5 h-5 text-green-500" />
          </div>
          <p className="text-3xl font-bold text-green-700 mt-2">${stats.totalEV.toLocaleString()}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search cases, sites, assets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500"
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="px-3 py-2 border border-slate-200 rounded-lg text-sm"
            >
              <option value="all">All Severity</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 border border-slate-200 rounded-lg text-sm"
            >
              <option value="all">All Status</option>
              <option value="new">New</option>
              <option value="triaging">Triaging</option>
              <option value="dispatched">Dispatched</option>
              <option value="in_progress">In Progress</option>
            </select>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
              className="px-3 py-2 border border-slate-200 rounded-lg text-sm"
            >
              <option value="priority">Sort: Priority</option>
              <option value="ev">Sort: EV (High→Low)</option>
              <option value="sla">Sort: SLA Due</option>
              <option value="created">Sort: Newest</option>
            </select>
          </div>
        </div>
      </div>

      {/* Case Queue */}
      <div className="space-y-3">
        {filteredCases.map((c) => {
          const SlaIcon = slaConfig[c.sla.status].icon;
          const isExpanded = expandedCase === c.id;
          
          return (
            <div key={c.id} className={`bg-white rounded-xl border ${severityConfig[c.severity].border} overflow-hidden`}>
              {/* Case Header */}
              <div 
                className="p-4 cursor-pointer hover:bg-slate-50"
                onClick={() => setExpandedCase(isExpanded ? null : c.id)}
              >
                <div className="flex items-center gap-4">
                  {/* Priority & Severity */}
                  <div className="flex items-center gap-2">
                    <div className={`w-3 h-3 rounded-full ${severityConfig[c.severity].dot}`} />
                    <span className="text-sm font-medium text-slate-500">#{c.priority}</span>
                  </div>
                  
                  {/* Case Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <span className="font-semibold text-slate-900">{c.caseNumber}</span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${severityConfig[c.severity].bg} ${severityConfig[c.severity].text}`}>
                        {c.severity}
                      </span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${statusConfig[c.status].bg} ${statusConfig[c.status].text}`}>
                        {statusConfig[c.status].label}
                      </span>
                    </div>
                    <p className="text-sm text-slate-600 mt-1 truncate">{c.fault.description}</p>
                  </div>

                  {/* Site & Asset */}
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-sm text-slate-700">
                      <Building2 className="w-4 h-4" />
                      {c.site.name}
                    </div>
                    <div className="flex items-center gap-1 text-sm text-slate-500">
                      <Thermometer className="w-4 h-4" />
                      {c.asset.name}
                    </div>
                  </div>

                  {/* Confidence & EV */}
                  <div className="text-center px-4 border-l border-slate-200">
                    <p className="text-xs text-slate-500">Confidence</p>
                    <p className="text-lg font-bold text-slate-900">{(c.fault.confidence * 100).toFixed(0)}%</p>
                  </div>
                  <div className="text-center px-4 border-l border-slate-200">
                    <p className="text-xs text-slate-500">Expected Value</p>
                    <p className="text-lg font-bold text-green-600">${c.ev.value.toLocaleString()}</p>
                  </div>

                  {/* SLA */}
                  <div className={`flex items-center gap-2 px-3 py-1 rounded-lg ${slaConfig[c.sla.status].bg}`}>
                    <SlaIcon className={`w-4 h-4 ${slaConfig[c.sla.status].text}`} />
                    <span className={`text-sm font-medium ${slaConfig[c.sla.status].text}`}>
                      {new Date(c.sla.dueAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  {/* Expand */}
                  {isExpanded ? <ChevronDown className="w-5 h-5 text-slate-400" /> : <ChevronRight className="w-5 h-5 text-slate-400" />}
                </div>
              </div>

              {/* Expanded Details */}
              {isExpanded && (
                <div className="border-t border-slate-200 p-4 bg-slate-50">
                  <div className="grid grid-cols-3 gap-6">
                    {/* Evidence Summary */}
                    <div>
                      <h4 className="font-medium text-slate-700 mb-2">Evidence Summary</h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-slate-500">Fault Type:</span>
                          <span className="font-medium">{c.fault.type.replace(/_/g, ' ')}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Uncertainty:</span>
                          <span className="font-medium">±{(c.uncertainty * 100).toFixed(0)}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Potential Savings:</span>
                          <span className="font-medium text-green-600">${c.ev.components.savings}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Est. Repair Cost:</span>
                          <span className="font-medium text-red-600">${c.ev.components.cost}</span>
                        </div>
                      </div>
                    </div>

                    {/* Location */}
                    <div>
                      <h4 className="font-medium text-slate-700 mb-2">Location</h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex items-start gap-2">
                          <MapPin className="w-4 h-4 text-slate-400 mt-0.5" />
                          <div>
                            <p className="font-medium">{c.site.name}</p>
                            <p className="text-slate-500">{c.site.address}</p>
                          </div>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-500">Region:</span>
                          <span className="font-medium">{c.site.region}</span>
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div>
                      <h4 className="font-medium text-slate-700 mb-2">Actions</h4>
                      <div className="space-y-2">
                        <button className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700">
                          <Wrench className="w-4 h-4" />
                          Create Work Order
                        </button>
                        <button className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100">
                          <ArrowUpRight className="w-4 h-4" />
                          View Full Case
                        </button>
                        {c.assignedTo ? (
                          <div className="flex items-center gap-2 text-sm text-slate-600">
                            <User className="w-4 h-4" />
                            Assigned to: {c.assignedTo}
                          </div>
                        ) : (
                          <button className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100">
                            <User className="w-4 h-4" />
                            Assign Technician
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {filteredCases.length === 0 && (
        <div className="text-center py-12 bg-white rounded-xl border border-slate-200">
          <AlertTriangle className="w-12 h-12 text-slate-300 mx-auto mb-4" />
          <p className="text-slate-500">No cases match your filters</p>
        </div>
      )}
    </div>
  );
}
