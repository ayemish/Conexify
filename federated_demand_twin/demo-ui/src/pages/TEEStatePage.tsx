import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  Shield, Activity, Database, History, CheckCircle, XCircle, AlertTriangle,
  Lock, Cpu, FileCheck, Send, ChevronLeft, Server, Container, KeyRound,
  Fingerprint, Binary, Box, FileSignature, Target, Workflow, RefreshCw,
  Building2, ShoppingCart, Globe, Zap, Layers
} from 'lucide-react';

// Types
interface HealthStatus {
  status: string;
  version: string;
  database_healthy: boolean;
  redis_healthy: boolean;
  keylime_enabled: boolean;
  keylime_healthy: boolean | null;
  zk_enabled: boolean;
  zk_healthy: boolean | null;
}

interface BudgetStatus {
  dataset_id: string;
  total_epsilon: number;
  consumed_epsilon: number;
  remaining_epsilon: number;
  release_count: number;
  is_exhausted: boolean;
}

interface ReleaseHistoryItem {
  receipt_id: string;
  job_id: string;
  aggregate_type: string;
  epsilon_consumed: number;
  mechanism: string;
  released_at: string;
  integrity_verified: boolean;
  released_value?: number;
}

interface NormalizationState {
  status: 'idle' | 'discovering' | 'mapping' | 'validating' | 'complete' | 'error';
  currentAgent?: string;
  fieldsDiscovered: number;
  fieldsMapped: number;
  recordsValidated: number;
  errors: string[];
  schemaVersion?: string;
  lastUpdated?: string;
}

interface RetailerTEEState {
  retailerId: string;
  retailerName: string;
  health: HealthStatus;
  budget: BudgetStatus;
  releaseHistory: ReleaseHistoryItem[];
  normalization: NormalizationState;
  capabilities: {
    dpGate: { enabled: boolean; healthy: boolean; budgetEnforced: boolean };
    keylime: { enabled: boolean; healthy: boolean | null };
    zkProofs: { enabled: boolean; healthy: boolean | null };
  };
}

const retailerIcons: Record<string, typeof ShoppingCart> = {
  walmart: ShoppingCart,
  target: Building2,
  amazon: Globe,
  instacart: Zap,
  albertsons: Building2,
};

// Status Badge Component
function StatusBadge({ status, label }: { status: boolean | null; label?: string }) {
  if (status === null) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-600">
        N/A
      </span>
    );
  }
  return status ? (
    <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-700">
      <CheckCircle className="w-3 h-3" /> {label || 'Healthy'}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-700">
      <XCircle className="w-3 h-3" /> {label || 'Unhealthy'}
    </span>
  );
}

// Feature Row Component
function FeatureRow({ id, title, description, status }: { 
  id: string; 
  title: string; 
  description: string; 
  status: 'active' | 'inactive' | 'optional' | 'n/a';
}) {
  const statusColors = {
    active: 'bg-green-100 text-green-700 border-green-200',
    inactive: 'bg-red-100 text-red-700 border-red-200',
    optional: 'bg-amber-100 text-amber-700 border-amber-200',
    'n/a': 'bg-slate-100 text-slate-600 border-slate-200',
  };
  
  return (
    <div className="flex items-start gap-3 py-2 border-b border-slate-100 last:border-0">
      <span className="px-2 py-0.5 text-xs font-mono bg-slate-100 text-slate-600 rounded shrink-0">{id}</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm text-slate-900">{title}</p>
        <p className="text-xs text-slate-500">{description}</p>
      </div>
      <span className={`shrink-0 px-2 py-0.5 text-xs font-medium rounded border ${statusColors[status]}`}>
        {status === 'active' ? 'Active' : status === 'inactive' ? 'Inactive' : status === 'optional' ? 'Optional' : 'N/A'}
      </span>
    </div>
  );
}

// Health Card Component
function HealthCard({ health }: { health: HealthStatus }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="p-4 bg-slate-50 border-b border-slate-200">
        <h3 className="font-semibold text-slate-900 flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          System Health
        </h3>
        <p className="text-xs text-slate-500 mt-1">Release Gate v{health.version}</p>
      </div>
      <div className="p-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
            <span className="text-sm text-slate-600">Database</span>
            <StatusBadge status={health.database_healthy} />
          </div>
          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
            <span className="text-sm text-slate-600">Redis</span>
            <StatusBadge status={health.redis_healthy} />
          </div>
          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
            <span className="text-sm text-slate-600">Keylime</span>
            {health.keylime_enabled ? (
              <StatusBadge status={health.keylime_healthy} />
            ) : (
              <span className="px-2 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-500">Disabled</span>
            )}
          </div>
          <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
            <span className="text-sm text-slate-600">ZK Proofs</span>
            {health.zk_enabled ? (
              <StatusBadge status={health.zk_healthy} />
            ) : (
              <span className="px-2 py-1 text-xs font-medium rounded-full bg-slate-100 text-slate-500">Disabled</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Budget Card Component
function BudgetCard({ budget }: { budget: BudgetStatus }) {
  const usedPercent = (budget.consumed_epsilon / budget.total_epsilon) * 100;
  
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="p-4 bg-emerald-50 border-b border-emerald-200">
        <h3 className="font-semibold text-emerald-900 flex items-center gap-2">
          <Lock className="w-5 h-5 text-emerald-600" />
          Privacy Budget
        </h3>
        <p className="text-xs text-emerald-600 mt-1">Dataset: {budget.dataset_id}</p>
      </div>
      <div className="p-4 space-y-4">
        <div>
          <div className="flex justify-between text-sm mb-2">
            <span className="text-slate-600">Epsilon Used</span>
            <span className="font-semibold text-slate-900">{budget.consumed_epsilon.toFixed(2)} / {budget.total_epsilon.toFixed(2)}</span>
          </div>
          <div className="h-3 bg-slate-200 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all rounded-full ${
                usedPercent > 80 ? 'bg-red-500' : usedPercent > 50 ? 'bg-amber-500' : 'bg-emerald-500'
              }`}
              style={{ width: `${Math.min(usedPercent, 100)}%` }}
            />
          </div>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 bg-slate-50 rounded-lg">
            <p className="text-xs text-slate-500">Remaining ε</p>
            <p className="text-xl font-bold text-slate-900">{budget.remaining_epsilon.toFixed(2)}</p>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <p className="text-xs text-slate-500">Release Count</p>
            <p className="text-xl font-bold text-slate-900">{budget.release_count}</p>
          </div>
        </div>
        
        {budget.is_exhausted && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            <AlertTriangle className="w-4 h-4" />
            Budget exhausted
          </div>
        )}
      </div>
    </div>
  );
}

// Normalization State Card Component
function NormalizationStateCard({ normalization }: { normalization: NormalizationState }) {
  const statusColors: Record<string, string> = {
    idle: 'bg-slate-100 text-slate-700',
    discovering: 'bg-blue-100 text-blue-700',
    mapping: 'bg-amber-100 text-amber-700',
    validating: 'bg-purple-100 text-purple-700',
    complete: 'bg-green-100 text-green-700',
    error: 'bg-red-100 text-red-700',
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="p-4 bg-amber-50 border-b border-amber-200">
        <h3 className="font-semibold text-amber-900 flex items-center gap-2">
          <Layers className="w-5 h-5 text-amber-600" />
          Normalization State
        </h3>
        {normalization.schemaVersion && (
          <p className="text-xs text-amber-600 mt-1">Schema: {normalization.schemaVersion}</p>
        )}
      </div>
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-600">Status</span>
          <span className={`px-3 py-1 text-sm font-medium rounded-full ${statusColors[normalization.status]}`}>
            {normalization.status.charAt(0).toUpperCase() + normalization.status.slice(1)}
          </span>
        </div>
        
        {normalization.currentAgent && (
          <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <Activity className="w-4 h-4 text-amber-600 animate-pulse" />
            <span className="text-sm text-amber-700">{normalization.currentAgent}</span>
          </div>
        )}
        
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 bg-slate-50 rounded-lg text-center">
            <p className="text-xs text-slate-500">Discovered</p>
            <p className="text-lg font-bold text-slate-900">{normalization.fieldsDiscovered}</p>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg text-center">
            <p className="text-xs text-slate-500">Mapped</p>
            <p className="text-lg font-bold text-slate-900">{normalization.fieldsMapped}</p>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg text-center">
            <p className="text-xs text-slate-500">Validated</p>
            <p className="text-lg font-bold text-slate-900">{normalization.recordsValidated}</p>
          </div>
        </div>
        
        {normalization.errors.length > 0 && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-xs font-medium text-red-700 mb-2">Errors ({normalization.errors.length})</p>
            {normalization.errors.slice(0, 3).map((err, i) => (
              <p key={i} className="text-xs text-red-600">{err}</p>
            ))}
          </div>
        )}
        
        {normalization.lastUpdated && (
          <p className="text-xs text-slate-400">Last updated: {normalization.lastUpdated}</p>
        )}
      </div>
    </div>
  );
}

// Release History Table Component
function ReleaseHistoryTable({ history }: { history: ReleaseHistoryItem[] }) {
  if (history.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400">
        <History className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">No release history found</p>
      </div>
    );
  }
  
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            <th className="text-left py-3 px-4 font-medium text-slate-700">Job ID</th>
            <th className="text-left py-3 px-4 font-medium text-slate-700">Type</th>
            <th className="text-left py-3 px-4 font-medium text-slate-700">ε Used</th>
            <th className="text-left py-3 px-4 font-medium text-slate-700">Mechanism</th>
            <th className="text-left py-3 px-4 font-medium text-slate-700">Released Value</th>
            <th className="text-left py-3 px-4 font-medium text-slate-700">Time</th>
            <th className="text-left py-3 px-4 font-medium text-slate-700">Status</th>
          </tr>
        </thead>
        <tbody>
          {history.map((item) => (
            <tr key={item.receipt_id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="py-3 px-4 font-mono text-xs text-slate-600">{item.job_id}</td>
              <td className="py-3 px-4">
                <span className="px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-600 rounded">{item.aggregate_type}</span>
              </td>
              <td className="py-3 px-4 font-medium">{item.epsilon_consumed.toFixed(3)}</td>
              <td className="py-3 px-4 text-slate-600">{item.mechanism}</td>
              <td className="py-3 px-4 font-mono">{item.released_value?.toFixed(2) || '-'}</td>
              <td className="py-3 px-4 text-slate-500 text-xs">
                {new Date(item.released_at).toLocaleString()}
              </td>
              <td className="py-3 px-4">
                {item.integrity_verified ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-700">
                    <CheckCircle className="w-3 h-3" /> Verified
                  </span>
                ) : (
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-100 text-slate-600">Unverified</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// DP Release Form Component
function ReleaseForm({ datasetId, onSubmit }: { datasetId: string; onSubmit: (data: any) => void }) {
  const [formData, setFormData] = useState({
    job_id: '',
    aggregate_type: 'count',
    raw_value: '',
    epsilon: '1.0',
    mechanism: 'laplace',
  });
  
  const aggregates = ['count', 'sum', 'mean', 'variance', 'histogram', 'quantile'];
  const mechanisms = ['laplace', 'gaussian', 'thresholded_laplace'];
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      ...formData,
      dataset_id: datasetId,
      raw_value: parseFloat(formData.raw_value),
      epsilon: parseFloat(formData.epsilon),
    });
  };
  
  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Job ID</label>
          <input 
            type="text"
            placeholder="job-12345"
            value={formData.job_id}
            onChange={(e) => setFormData({ ...formData, job_id: e.target.value })}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Aggregate Type</label>
          <select 
            value={formData.aggregate_type}
            onChange={(e) => setFormData({ ...formData, aggregate_type: e.target.value })}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          >
            {aggregates.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
      </div>
      
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Raw Value</label>
          <input 
            type="number"
            placeholder="1547"
            value={formData.raw_value}
            onChange={(e) => setFormData({ ...formData, raw_value: e.target.value })}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Epsilon (ε)</label>
          <input 
            type="number"
            step="0.1"
            min="0.1"
            placeholder="1.0"
            value={formData.epsilon}
            onChange={(e) => setFormData({ ...formData, epsilon: e.target.value })}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Mechanism</label>
          <select 
            value={formData.mechanism}
            onChange={(e) => setFormData({ ...formData, mechanism: e.target.value })}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          >
            {mechanisms.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>
      
      <button 
        type="submit" 
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white font-medium rounded-lg hover:bg-indigo-700 transition-colors"
      >
        <Send className="w-4 h-4" />
        Submit Release Request
      </button>
    </form>
  );
}

// Capabilities Card Components
function DPGateCard({ capabilities }: { capabilities: RetailerTEEState['capabilities'] }) {
  return (
    <div className="bg-white rounded-xl border-2 border-indigo-200 shadow-sm overflow-hidden">
      <div className="p-4 bg-indigo-50 border-b border-indigo-200">
        <h3 className="font-semibold text-indigo-900 flex items-center gap-2">
          <Lock className="w-5 h-5 text-indigo-600" />
          DP Release Gate (OpenDP)
        </h3>
        <p className="text-xs text-indigo-600 mt-1">Primary exfiltration control</p>
      </div>
      <div className="p-4 space-y-2">
        <div className="flex items-center justify-between p-3 bg-indigo-50 rounded-lg mb-3">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-indigo-600" />
            <span className="font-medium text-slate-900">Release Gate Service</span>
          </div>
          <StatusBadge status={capabilities.dpGate.healthy} />
        </div>
        <FeatureRow id="FR-4.1" title="Output Types" description="Approved aggregates: counts, histograms, means, quantiles" status="active" />
        <FeatureRow id="FR-4.2" title="Single Export Channel" description="All outputs flow through Release Gate" status="active" />
        <FeatureRow id="FR-4.3" title="Contribution Bounds" description="Per-dataset and per-metric bounding" status="active" />
        <FeatureRow id="FR-4.4" title="Budget Accounting" description="ε, δ composition; blocks when exhausted" status={capabilities.dpGate.budgetEnforced ? 'active' : 'inactive'} />
        <FeatureRow id="FR-4.5" title="Mechanism Selection" description="Laplace, Gaussian, thresholded" status="active" />
        <FeatureRow id="FR-4.6" title="Small Cohort Protection" description="Minimum group sizes / DP thresholding" status="active" />
        <FeatureRow id="FR-4.7" title="Release Receipts" description="DP receipt with full audit trail" status="active" />
      </div>
    </div>
  );
}

function IntegrityCard({ capabilities }: { capabilities: RetailerTEEState['capabilities'] }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden ${!capabilities.keylime.enabled ? 'opacity-75' : ''}`}>
      <div className="p-4 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-900 flex items-center gap-2">
            <Fingerprint className="w-5 h-5 text-slate-600" />
            TPM/Keylime Integrity
          </h3>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${capabilities.keylime.enabled ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
            {capabilities.keylime.enabled ? 'Enabled' : 'Optional'}
          </span>
        </div>
      </div>
      <div className="p-4 space-y-2">
        <FeatureRow id="FR-5.1" title="TPM Detection" description="Detect TPM presence" status={capabilities.keylime.enabled ? 'active' : 'optional'} />
        <FeatureRow id="FR-5.2" title="Measured Boot" description="TPM + IMA verification via Keylime" status={capabilities.keylime.enabled ? 'active' : 'optional'} />
        <FeatureRow id="FR-5.3" title="Runtime Policy" description="Fail closed on integrity failure" status={capabilities.keylime.enabled ? 'active' : 'optional'} />
      </div>
    </div>
  );
}

function ZKProofsCard({ capabilities }: { capabilities: RetailerTEEState['capabilities'] }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden ${!capabilities.zkProofs.enabled ? 'opacity-75' : ''}`}>
      <div className="p-4 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-900 flex items-center gap-2">
            <Binary className="w-5 h-5 text-slate-600" />
            ZK Proofs
          </h3>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${capabilities.zkProofs.enabled ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
            {capabilities.zkProofs.enabled ? 'Enabled' : 'Optional'}
          </span>
        </div>
      </div>
      <div className="p-4 space-y-2">
        <FeatureRow id="FR-6.1" title="Supported Queries" description="Crown jewel aggregates" status={capabilities.zkProofs.enabled ? 'active' : 'optional'} />
        <FeatureRow id="FR-6.2" title="ZKSQL Proofs" description="Prove correctness without revealing data" status={capabilities.zkProofs.enabled ? 'active' : 'optional'} />
        <FeatureRow id="FR-6.3" title="Verification" description="Offline verifier tool" status={capabilities.zkProofs.enabled ? 'active' : 'optional'} />
      </div>
    </div>
  );
}

// Main Page Component
export function TEEStatePage() {
  const { retailerId } = useParams<{ retailerId: string }>();
  const navigate = useNavigate();
  const [state, setState] = useState<RetailerTEEState | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'release' | 'history' | 'capabilities'>('overview');
  const [releaseResult, setReleaseResult] = useState<{ success: boolean; message: string; value?: number } | null>(null);

  const fetchState = async () => {
    try {
      const res = await fetch(`/api/tee/state/${retailerId}`);
      if (res.ok) {
        const data = await res.json();
        setState(data);
      }
    } catch (err) {
      console.error('Failed to fetch TEE state:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 5000);
    return () => clearInterval(interval);
  }, [retailerId]);

  const handleRelease = async (data: any) => {
    try {
      const res = await fetch('/api/tee/release', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const result = await res.json();
      setReleaseResult(result);
      if (result.success) fetchState();
    } catch (err) {
      setReleaseResult({ success: false, message: 'Failed to submit release request' });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin" />
        <span className="ml-2 text-slate-600">Loading TEE State...</span>
      </div>
    );
  }

  if (!state) {
    return (
      <div className="text-center py-12">
        <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-slate-700">Unable to load TEE state for {retailerId}</h2>
        <button onClick={() => navigate('/retail-media/data-federation')} className="mt-4 text-indigo-600 hover:underline">
          Back to Data Federation
        </button>
      </div>
    );
  }

  const RetailerIcon = retailerIcons[retailerId || ''] || Building2;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button 
          onClick={() => navigate('/retail-media/data-federation')}
          className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <ChevronLeft className="w-5 h-5 text-slate-600" />
        </button>
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center">
            <RetailerIcon className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{state.retailerName} TEE State</h1>
            <p className="text-slate-500">Data Integration & Normalization Output</p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
          <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
          <span className="text-sm text-green-700 font-medium">Live</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-200">
        {[
          { id: 'overview', label: 'State Overview', icon: Activity },
          { id: 'release', label: 'DP Release', icon: Shield },
          { id: 'history', label: 'Release History', icon: History },
          { id: 'capabilities', label: 'Capabilities', icon: Cpu },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-3 font-medium text-sm border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === tab.id
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-3 gap-6">
          <HealthCard health={state.health} />
          <BudgetCard budget={state.budget} />
          <NormalizationStateCard normalization={state.normalization} />
        </div>
      )}

      {/* Release Tab */}
      {activeTab === 'release' && (
        <div className="max-w-2xl">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-4 bg-slate-50 border-b border-slate-200">
              <h3 className="font-semibold text-slate-900 flex items-center gap-2">
                <Cpu className="w-5 h-5 text-indigo-600" />
                Submit DP Release Request
              </h3>
              <p className="text-xs text-slate-500 mt-1">Submit a raw aggregate value for differential privacy processing</p>
            </div>
            <div className="p-6">
              <ReleaseForm datasetId={state.budget.dataset_id} onSubmit={handleRelease} />
              
              {releaseResult && (
                <div className={`mt-6 p-4 rounded-lg border ${releaseResult.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    {releaseResult.success ? (
                      <CheckCircle className="w-5 h-5 text-green-600" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-600" />
                    )}
                    <span className={`font-medium ${releaseResult.success ? 'text-green-700' : 'text-red-700'}`}>
                      {releaseResult.success ? 'Release Successful' : 'Release Failed'}
                    </span>
                  </div>
                  <p className="text-sm text-slate-600">{releaseResult.message}</p>
                  {releaseResult.value !== undefined && (
                    <p className="mt-2 text-sm">
                      <span className="text-slate-500">Released Value:</span>{' '}
                      <span className="font-mono font-semibold">{releaseResult.value.toFixed(2)}</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 bg-slate-50 border-b border-slate-200">
            <h3 className="font-semibold text-slate-900 flex items-center gap-2">
              <History className="w-5 h-5 text-indigo-600" />
              Release History
            </h3>
            <p className="text-xs text-slate-500 mt-1">Dataset: {state.budget.dataset_id}</p>
          </div>
          <ReleaseHistoryTable history={state.releaseHistory} />
        </div>
      )}

      {/* Capabilities Tab */}
      {activeTab === 'capabilities' && (
        <div className="space-y-6">
          <DPGateCard capabilities={state.capabilities} />
          <div className="grid grid-cols-2 gap-6">
            <IntegrityCard capabilities={state.capabilities} />
            <ZKProofsCard capabilities={state.capabilities} />
          </div>
        </div>
      )}
    </div>
  );
}
