import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Clock,
  Filter,
  Search,
  ChevronRight,
  User,
  Building2,
  Cpu,
  CheckCircle2,
  XCircle,
  MoreVertical,
  ArrowUpDown
} from 'lucide-react';
import { cases } from '../data/mockData';
import type { Case, CaseSeverity, CaseStatus } from '../types';

const severityConfig: Record<CaseSeverity, { color: string; bg: string; priority: number }> = {
  critical: { color: 'text-red-600', bg: 'bg-red-100', priority: 1 },
  high: { color: 'text-orange-600', bg: 'bg-orange-100', priority: 2 },
  medium: { color: 'text-amber-600', bg: 'bg-amber-100', priority: 3 },
  low: { color: 'text-blue-600', bg: 'bg-blue-100', priority: 4 },
};

const statusConfig: Record<CaseStatus, { color: string; bg: string; label: string }> = {
  new: { color: 'text-blue-600', bg: 'bg-blue-100', label: 'New' },
  triaging: { color: 'text-purple-600', bg: 'bg-purple-100', label: 'Triaging' },
  diagnosing: { color: 'text-indigo-600', bg: 'bg-indigo-100', label: 'Diagnosing' },
  pending_approval: { color: 'text-amber-600', bg: 'bg-amber-100', label: 'Pending Approval' },
  executing: { color: 'text-cyan-600', bg: 'bg-cyan-100', label: 'Executing' },
  verifying: { color: 'text-teal-600', bg: 'bg-teal-100', label: 'Verifying' },
  resolved: { color: 'text-green-600', bg: 'bg-green-100', label: 'Resolved' },
  closed: { color: 'text-slate-600', bg: 'bg-slate-100', label: 'Closed' },
};

const slaStatusConfig = {
  on_track: { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle2 },
  at_risk: { color: 'text-amber-600', bg: 'bg-amber-100', icon: Clock },
  breached: { color: 'text-red-600', bg: 'bg-red-100', icon: XCircle },
};

export function CaseQueuePage() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'priority' | 'sla' | 'confidence'>('priority');
  const [selectedCases, setSelectedCases] = useState<Set<string>>(new Set());

  const filteredCases = cases
    .filter((c) => {
      const matchesSearch = c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                           c.assetName.toLowerCase().includes(searchQuery.toLowerCase()) ||
                           c.id.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesSeverity = severityFilter === 'all' || c.severity === severityFilter;
      const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
      return matchesSearch && matchesSeverity && matchesStatus;
    })
    .sort((a, b) => {
      if (sortBy === 'priority') {
        return severityConfig[a.severity].priority - severityConfig[b.severity].priority;
      } else if (sortBy === 'sla') {
        return new Date(a.slaDue).getTime() - new Date(b.slaDue).getTime();
      } else {
        return b.confidence - a.confidence;
      }
    });

  const toggleCaseSelection = (caseId: string) => {
    const newSelected = new Set(selectedCases);
    if (newSelected.has(caseId)) {
      newSelected.delete(caseId);
    } else {
      newSelected.add(caseId);
    }
    setSelectedCases(newSelected);
  };

  const stats = {
    critical: cases.filter(c => c.severity === 'critical' && c.status !== 'closed').length,
    high: cases.filter(c => c.severity === 'high' && c.status !== 'closed').length,
    pendingApproval: cases.filter(c => c.status === 'pending_approval').length,
    atRisk: cases.filter(c => c.slaStatus === 'at_risk' || c.slaStatus === 'breached').length,
  };

  const formatTimeRemaining = (slaDue: string) => {
    const diff = new Date(slaDue).getTime() - Date.now();
    if (diff < 0) return 'Overdue';
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
    return `${hours}h ${mins}m`;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Case Queue</h1>
          <p className="text-slate-500 mt-1">Operations Center - Triage and manage active cases</p>
        </div>
        {selectedCases.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-600">{selectedCases.size} selected</span>
            <button className="px-3 py-1.5 bg-slate-100 text-slate-700 text-sm rounded-lg hover:bg-slate-200">
              Bulk Assign
            </button>
            <button className="px-3 py-1.5 bg-slate-100 text-slate-700 text-sm rounded-lg hover:bg-slate-200">
              Acknowledge
            </button>
          </div>
        )}
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-red-200 bg-red-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-red-600">{stats.critical}</p>
              <p className="text-sm text-red-700">Critical</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-orange-200 bg-orange-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-orange-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-orange-600">{stats.high}</p>
              <p className="text-sm text-orange-700">High Priority</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-amber-200 bg-amber-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
              <Clock className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-amber-600">{stats.pendingApproval}</p>
              <p className="text-sm text-amber-700">Pending Approval</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-slate-100 rounded-lg flex items-center justify-center">
              <Clock className="w-5 h-5 text-slate-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">{stats.atRisk}</p>
              <p className="text-sm text-slate-500">SLA At Risk</p>
            </div>
          </div>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex items-center gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search cases by ID, title, or asset..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-400" />
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
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
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            <option value="all">All Status</option>
            <option value="new">New</option>
            <option value="triaging">Triaging</option>
            <option value="diagnosing">Diagnosing</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="executing">Executing</option>
            <option value="verifying">Verifying</option>
          </select>
          <button
            onClick={() => setSortBy(sortBy === 'priority' ? 'sla' : sortBy === 'sla' ? 'confidence' : 'priority')}
            className="flex items-center gap-1 px-3 py-2 border border-slate-200 rounded-lg text-sm hover:bg-slate-50"
          >
            <ArrowUpDown className="w-4 h-4" />
            Sort: {sortBy === 'priority' ? 'Priority' : sortBy === 'sla' ? 'SLA' : 'Confidence'}
          </button>
        </div>
      </div>

      {/* Case List */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="divide-y divide-slate-100">
          {filteredCases.map((caseItem) => {
            const SlaIcon = slaStatusConfig[caseItem.slaStatus].icon;
            return (
              <div
                key={caseItem.id}
                className={`p-4 hover:bg-slate-50 transition-colors cursor-pointer ${
                  selectedCases.has(caseItem.id) ? 'bg-orange-50' : ''
                }`}
                onClick={() => navigate(`/cases/${caseItem.id}`)}
              >
                <div className="flex items-start gap-4">
                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={selectedCases.has(caseItem.id)}
                    onChange={(e) => {
                      e.stopPropagation();
                      toggleCaseSelection(caseItem.id);
                    }}
                    className="mt-1 rounded border-slate-300 text-orange-600 focus:ring-orange-500"
                  />

                  {/* Severity Indicator */}
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${severityConfig[caseItem.severity].bg}`}>
                    <AlertTriangle className={`w-5 h-5 ${severityConfig[caseItem.severity].color}`} />
                  </div>

                  {/* Main Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-slate-500 font-mono">{caseItem.id}</span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${severityConfig[caseItem.severity].bg} ${severityConfig[caseItem.severity].color}`}>
                        {caseItem.severity}
                      </span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${statusConfig[caseItem.status].bg} ${statusConfig[caseItem.status].color}`}>
                        {statusConfig[caseItem.status].label}
                      </span>
                    </div>
                    <h3 className="font-medium text-slate-900 truncate">{caseItem.title}</h3>
                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <Cpu className="w-3 h-3" />
                        {caseItem.assetName}
                      </span>
                      <span className="flex items-center gap-1">
                        <Building2 className="w-3 h-3" />
                        {caseItem.siteName}
                      </span>
                      <span className="flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {caseItem.assigneeName || 'Unassigned'}
                      </span>
                    </div>
                  </div>

                  {/* Right Side Info */}
                  <div className="flex items-center gap-6">
                    {/* Confidence */}
                    <div className="text-right">
                      <p className="text-xs text-slate-500">Confidence</p>
                      <p className="font-semibold text-slate-900">{(caseItem.confidence * 100).toFixed(0)}%</p>
                    </div>

                    {/* SLA */}
                    <div className="text-right">
                      <p className="text-xs text-slate-500">SLA</p>
                      <div className={`flex items-center gap-1 ${slaStatusConfig[caseItem.slaStatus].color}`}>
                        <SlaIcon className="w-4 h-4" />
                        <span className="font-semibold">{formatTimeRemaining(caseItem.slaDue)}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                      <ChevronRight className="w-5 h-5 text-slate-400" />
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                        }}
                        className="p-1 hover:bg-slate-100 rounded"
                      >
                        <MoreVertical className="w-4 h-4 text-slate-400" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {filteredCases.length === 0 && (
        <div className="text-center py-12 bg-white rounded-xl border border-slate-200">
          <p className="text-slate-500">No cases match your filters</p>
        </div>
      )}
    </div>
  );
}
