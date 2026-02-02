import { useState } from 'react';
import {
  Shield,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  User,
  FileText,
  ArrowRight,
  History
} from 'lucide-react';

interface ApprovalRequest {
  id: string;
  action: 'model_deploy' | 'model_promote' | 'experiment_start' | 'config_change';
  modelName?: string;
  version?: string;
  targetStage?: string;
  requestedBy: string;
  requestedAt: string;
  status: 'pending' | 'approved' | 'rejected';
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  reviewedBy?: string;
  reviewedAt?: string;
  notes?: string;
}

interface AuditLog {
  id: string;
  action: string;
  actor: string;
  timestamp: string;
  details: string;
  outcome: 'success' | 'failure';
}

const mockApprovals: ApprovalRequest[] = [
  {
    id: 'apr-001',
    action: 'model_deploy',
    modelName: 'rul_estimation',
    version: '3.0.0-beta',
    targetStage: 'production',
    requestedBy: 'ml-pipeline',
    requestedAt: '2024-01-26T14:30:00Z',
    status: 'pending',
    riskLevel: 'high',
  },
  {
    id: 'apr-002',
    action: 'experiment_start',
    modelName: 'failure_prediction',
    requestedBy: 'data-science',
    requestedAt: '2024-01-26T10:00:00Z',
    status: 'pending',
    riskLevel: 'medium',
    notes: 'Testing new feature set for failure prediction',
  },
  {
    id: 'apr-003',
    action: 'model_promote',
    modelName: 'anomaly_detection',
    version: '2.1.0',
    targetStage: 'production',
    requestedBy: 'ml-pipeline',
    requestedAt: '2024-01-25T16:00:00Z',
    status: 'approved',
    riskLevel: 'medium',
    reviewedBy: 'admin@company.com',
    reviewedAt: '2024-01-25T17:30:00Z',
  },
  {
    id: 'apr-004',
    action: 'config_change',
    requestedBy: 'ops-team',
    requestedAt: '2024-01-24T09:00:00Z',
    status: 'rejected',
    riskLevel: 'critical',
    reviewedBy: 'admin@company.com',
    reviewedAt: '2024-01-24T10:00:00Z',
    notes: 'Change would affect production SLAs',
  },
];

const mockAuditLogs: AuditLog[] = [
  { id: 'log-001', action: 'Model deployed to production', actor: 'ml-pipeline', timestamp: '2024-01-26T08:00:00Z', details: 'anomaly_detection v2.1.0', outcome: 'success' },
  { id: 'log-002', action: 'Experiment started', actor: 'data-science', timestamp: '2024-01-26T07:30:00Z', details: 'exp-001: A/B test for anomaly detection', outcome: 'success' },
  { id: 'log-003', action: 'Retraining job completed', actor: 'scheduler', timestamp: '2024-01-25T02:45:00Z', details: 'anomaly_detection → v2.1.1', outcome: 'success' },
  { id: 'log-004', action: 'Model rollback', actor: 'admin@company.com', timestamp: '2024-01-24T15:00:00Z', details: 'failure_prediction v1.3.0 → v1.2.0', outcome: 'success' },
  { id: 'log-005', action: 'Config change rejected', actor: 'admin@company.com', timestamp: '2024-01-24T10:00:00Z', details: 'Threshold change for alerts', outcome: 'failure' },
];

const riskColors = {
  low: 'bg-green-100 text-green-700',
  medium: 'bg-amber-100 text-amber-700',
  high: 'bg-orange-100 text-orange-700',
  critical: 'bg-red-100 text-red-700',
};

const actionLabels = {
  model_deploy: 'Deploy Model',
  model_promote: 'Promote Model',
  experiment_start: 'Start Experiment',
  config_change: 'Config Change',
};

export function PMGovernancePage() {
  const [activeTab, setActiveTab] = useState<'approvals' | 'audit'>('approvals');
  const pendingCount = mockApprovals.filter(a => a.status === 'pending').length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Governance</h1>
          <p className="text-slate-500 mt-1">Approval workflows and audit trails</p>
        </div>
        {pendingCount > 0 && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-full">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span className="text-sm text-amber-700 font-medium">{pendingCount} Pending Approval{pendingCount > 1 ? 's' : ''}</span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab('approvals')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'approvals' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          Approvals
          {pendingCount > 0 && (
            <span className="ml-2 px-1.5 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-full">
              {pendingCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'audit' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          Audit Log
        </button>
      </div>

      {activeTab === 'approvals' ? (
        <div className="space-y-4">
          {/* Pending Approvals */}
          {mockApprovals.filter(a => a.status === 'pending').length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200">
              <div className="p-4 border-b border-slate-200 bg-amber-50">
                <h2 className="font-semibold text-slate-900">Pending Approvals</h2>
              </div>
              <div className="divide-y divide-slate-100">
                {mockApprovals.filter(a => a.status === 'pending').map((approval) => (
                  <div key={approval.id} className="p-4">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">
                          <Shield className="w-5 h-5 text-amber-600" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium text-slate-900">{actionLabels[approval.action]}</h3>
                            <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${riskColors[approval.riskLevel]}`}>
                              {approval.riskLevel} risk
                            </span>
                          </div>
                          {approval.modelName && (
                            <p className="text-sm text-slate-600 mt-0.5">
                              {approval.modelName} {approval.version && `v${approval.version}`}
                              {approval.targetStage && (
                                <span className="text-slate-400"> → {approval.targetStage}</span>
                              )}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700">
                          <CheckCircle2 className="w-4 h-4" />
                          Approve
                        </button>
                        <button className="flex items-center gap-1 px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700">
                          <XCircle className="w-4 h-4" />
                          Reject
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-slate-500 pl-13">
                      <span className="flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {approval.requestedBy}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(approval.requestedAt).toLocaleString()}
                      </span>
                    </div>
                    {approval.notes && (
                      <p className="mt-2 text-sm text-slate-600 pl-13 italic">"{approval.notes}"</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Completed Approvals */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200">
              <h2 className="font-semibold text-slate-900">Recent Decisions</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {mockApprovals.filter(a => a.status !== 'pending').map((approval) => (
                <div key={approval.id} className="p-4 hover:bg-slate-50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        approval.status === 'approved' ? 'bg-green-100' : 'bg-red-100'
                      }`}>
                        {approval.status === 'approved' ? (
                          <CheckCircle2 className="w-5 h-5 text-green-600" />
                        ) : (
                          <XCircle className="w-5 h-5 text-red-600" />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium text-slate-900">{actionLabels[approval.action]}</h3>
                          <ArrowRight className="w-3 h-3 text-slate-400" />
                          <span className={`text-sm font-medium capitalize ${
                            approval.status === 'approved' ? 'text-green-600' : 'text-red-600'
                          }`}>
                            {approval.status}
                          </span>
                        </div>
                        {approval.modelName && (
                          <p className="text-sm text-slate-500">{approval.modelName} {approval.version && `v${approval.version}`}</p>
                        )}
                      </div>
                    </div>
                    <div className="text-right text-xs text-slate-500">
                      <p>by {approval.reviewedBy}</p>
                      <p>{approval.reviewedAt && new Date(approval.reviewedAt).toLocaleString()}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Audit Log Tab */
        <div className="bg-white rounded-xl border border-slate-200">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">Audit Log</h2>
            <button className="text-sm text-orange-600 hover:text-orange-700 flex items-center gap-1">
              <FileText className="w-4 h-4" />
              Export
            </button>
          </div>
          <div className="divide-y divide-slate-100">
            {mockAuditLogs.map((log) => (
              <div key={log.id} className="p-4 hover:bg-slate-50 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      log.outcome === 'success' ? 'bg-green-100' : 'bg-red-100'
                    }`}>
                      <History className={`w-4 h-4 ${
                        log.outcome === 'success' ? 'text-green-600' : 'text-red-600'
                      }`} />
                    </div>
                    <div>
                      <h3 className="font-medium text-slate-900">{log.action}</h3>
                      <p className="text-sm text-slate-500">{log.details}</p>
                    </div>
                  </div>
                  <div className="text-right text-xs text-slate-500">
                    <p>{log.actor}</p>
                    <p>{new Date(log.timestamp).toLocaleString()}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
