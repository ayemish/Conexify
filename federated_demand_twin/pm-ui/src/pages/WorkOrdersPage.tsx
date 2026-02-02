import { useState } from 'react';
import {
  Wrench,
  Plus,
  Search,
  Filter,
  Clock,
  User,
  Building2,
  Cpu,
  CheckCircle2,
  XCircle,
  Calendar,
  FileText,
  ExternalLink,
  AlertTriangle
} from 'lucide-react';
import { workOrders } from '../data/mockData';
import type { WorkOrderStatus, WorkOrderPriority } from '../types';

const statusConfig: Record<WorkOrderStatus, { color: string; bg: string; label: string }> = {
  draft: { color: 'text-slate-600', bg: 'bg-slate-100', label: 'Draft' },
  submitted: { color: 'text-blue-600', bg: 'bg-blue-100', label: 'Submitted' },
  assigned: { color: 'text-indigo-600', bg: 'bg-indigo-100', label: 'Assigned' },
  scheduled: { color: 'text-purple-600', bg: 'bg-purple-100', label: 'Scheduled' },
  in_progress: { color: 'text-cyan-600', bg: 'bg-cyan-100', label: 'In Progress' },
  completed: { color: 'text-teal-600', bg: 'bg-teal-100', label: 'Completed' },
  verified: { color: 'text-green-600', bg: 'bg-green-100', label: 'Verified' },
  closed: { color: 'text-slate-500', bg: 'bg-slate-100', label: 'Closed' },
};

const priorityConfig: Record<WorkOrderPriority, { color: string; bg: string; icon: typeof AlertTriangle }> = {
  emergency: { color: 'text-red-600', bg: 'bg-red-100', icon: AlertTriangle },
  urgent: { color: 'text-orange-600', bg: 'bg-orange-100', icon: AlertTriangle },
  standard: { color: 'text-blue-600', bg: 'bg-blue-100', icon: Wrench },
  planned: { color: 'text-slate-600', bg: 'bg-slate-100', icon: Calendar },
};

const verificationConfig = {
  pending: { color: 'text-amber-600', bg: 'bg-amber-100', icon: Clock },
  passed: { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle2 },
  failed: { color: 'text-red-600', bg: 'bg-red-100', icon: XCircle },
};

export function WorkOrdersPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [priorityFilter, setPriorityFilter] = useState<string>('all');
  const [selectedWO, setSelectedWO] = useState<string | null>(null);

  const filteredWorkOrders = workOrders.filter((wo) => {
    const matchesSearch = wo.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         wo.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         wo.assetName.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || wo.status === statusFilter;
    const matchesPriority = priorityFilter === 'all' || wo.priority === priorityFilter;
    return matchesSearch && matchesStatus && matchesPriority;
  });

  const stats = {
    inProgress: workOrders.filter(wo => wo.status === 'in_progress').length,
    scheduled: workOrders.filter(wo => wo.status === 'scheduled' || wo.status === 'assigned').length,
    completed: workOrders.filter(wo => wo.status === 'completed' || wo.status === 'verified').length,
    pendingVerification: workOrders.filter(wo => wo.verificationStatus === 'pending').length,
  };

  const selectedWorkOrder = workOrders.find(wo => wo.id === selectedWO);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Work Orders</h1>
          <p className="text-slate-500 mt-1">Manage maintenance work orders and dispatch</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
          <Plus className="w-4 h-4" />
          Create Work Order
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-xl p-4 border border-cyan-200 bg-cyan-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-cyan-100 rounded-lg flex items-center justify-center">
              <Wrench className="w-5 h-5 text-cyan-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-cyan-600">{stats.inProgress}</p>
              <p className="text-sm text-cyan-700">In Progress</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-purple-200 bg-purple-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
              <Calendar className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-purple-600">{stats.scheduled}</p>
              <p className="text-sm text-purple-700">Scheduled</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-green-200 bg-green-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-green-600">{stats.completed}</p>
              <p className="text-sm text-green-700">Completed</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-xl p-4 border border-amber-200 bg-amber-50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
              <Clock className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-amber-600">{stats.pendingVerification}</p>
              <p className="text-sm text-amber-700">Pending Verification</p>
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
            placeholder="Search work orders..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            <option value="all">All Status</option>
            <option value="assigned">Assigned</option>
            <option value="scheduled">Scheduled</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="verified">Verified</option>
          </select>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            <option value="all">All Priority</option>
            <option value="emergency">Emergency</option>
            <option value="urgent">Urgent</option>
            <option value="standard">Standard</option>
            <option value="planned">Planned</option>
          </select>
        </div>
      </div>

      {/* Work Orders Grid */}
      <div className="grid grid-cols-3 gap-4">
        {/* Work Order List */}
        <div className="col-span-2 bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200">
            <h2 className="font-semibold text-slate-900">Work Orders</h2>
          </div>
          <div className="divide-y divide-slate-100 max-h-[600px] overflow-auto">
            {filteredWorkOrders.map((wo) => {
              const PriorityIcon = priorityConfig[wo.priority].icon;
              return (
                <div
                  key={wo.id}
                  className={`p-4 hover:bg-slate-50 cursor-pointer transition-colors ${
                    selectedWO === wo.id ? 'bg-orange-50 border-l-4 border-orange-500' : ''
                  }`}
                  onClick={() => setSelectedWO(wo.id)}
                >
                  <div className="flex items-start gap-4">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${priorityConfig[wo.priority].bg}`}>
                      <PriorityIcon className={`w-5 h-5 ${priorityConfig[wo.priority].color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-slate-500 font-mono">{wo.id}</span>
                        {wo.externalId && (
                          <span className="text-xs text-blue-600 flex items-center gap-1">
                            <ExternalLink className="w-3 h-3" />
                            {wo.externalId}
                          </span>
                        )}
                      </div>
                      <h3 className="font-medium text-slate-900 truncate">{wo.title}</h3>
                      <div className="flex items-center gap-3 mt-2">
                        <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${priorityConfig[wo.priority].bg} ${priorityConfig[wo.priority].color}`}>
                          {wo.priority}
                        </span>
                        <span className={`px-2 py-0.5 text-xs font-medium rounded ${statusConfig[wo.status].bg} ${statusConfig[wo.status].color}`}>
                          {statusConfig[wo.status].label}
                        </span>
                        {wo.verificationStatus && (
                          <span className={`px-2 py-0.5 text-xs font-medium rounded ${verificationConfig[wo.verificationStatus].bg} ${verificationConfig[wo.verificationStatus].color}`}>
                            Verification: {wo.verificationStatus}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                        <span className="flex items-center gap-1">
                          <Cpu className="w-3 h-3" />
                          {wo.assetName}
                        </span>
                        <span className="flex items-center gap-1">
                          <User className="w-3 h-3" />
                          {wo.assigneeName || 'Unassigned'}
                        </span>
                      </div>
                    </div>
                    {wo.scheduledDate && (
                      <div className="text-right">
                        <p className="text-xs text-slate-500">Scheduled</p>
                        <p className="text-sm font-medium text-slate-700">
                          {new Date(wo.scheduledDate).toLocaleDateString()}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Work Order Detail */}
        <div className="bg-white rounded-xl border border-slate-200">
          {selectedWorkOrder ? (
            <>
              <div className="p-4 border-b border-slate-200">
                <h2 className="font-semibold text-slate-900">Work Order Details</h2>
              </div>
              <div className="p-4 space-y-4 max-h-[600px] overflow-auto">
                <div>
                  <p className="text-xs text-slate-500 mb-1">Title</p>
                  <p className="font-medium text-slate-900">{selectedWorkOrder.title}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Description</p>
                  <p className="text-sm text-slate-700">{selectedWorkOrder.description}</p>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Asset</p>
                    <p className="text-sm font-medium text-slate-900">{selectedWorkOrder.assetName}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Site</p>
                    <p className="text-sm font-medium text-slate-900">{selectedWorkOrder.siteName}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Assignee</p>
                    <p className="text-sm font-medium text-slate-900">{selectedWorkOrder.assigneeName}</p>
                    <p className="text-xs text-slate-500 capitalize">{selectedWorkOrder.assigneeType}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Scheduled</p>
                    <p className="text-sm font-medium text-slate-900">
                      {selectedWorkOrder.scheduledDate 
                        ? new Date(selectedWorkOrder.scheduledDate).toLocaleString() 
                        : '—'}
                    </p>
                  </div>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Diagnostics</p>
                  <p className="text-sm text-slate-700 bg-slate-50 p-3 rounded-lg">{selectedWorkOrder.diagnostics}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-1">Suspected Root Cause</p>
                  <p className="text-sm text-slate-700">{selectedWorkOrder.suspectedRootCause}</p>
                </div>
                {selectedWorkOrder.recommendedParts.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Recommended Parts</p>
                    <ul className="text-sm text-slate-700 list-disc list-inside">
                      {selectedWorkOrder.recommendedParts.map((part, i) => (
                        <li key={i}>{part}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {selectedWorkOrder.technicianNotes && (
                  <div>
                    <p className="text-xs text-slate-500 mb-1">Technician Notes</p>
                    <p className="text-sm text-slate-700 bg-green-50 p-3 rounded-lg">{selectedWorkOrder.technicianNotes}</p>
                  </div>
                )}
                {selectedWorkOrder.caseId && (
                  <button className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm">
                    <FileText className="w-4 h-4" />
                    View Related Case
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="p-8 text-center text-slate-500">
              Select a work order to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
