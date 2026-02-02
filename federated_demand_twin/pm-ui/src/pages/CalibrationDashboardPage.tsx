import { useState, useMemo } from 'react';
import {
  Target, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Clock,
  BarChart3, Activity, Settings, RefreshCw, Download, ChevronRight,
  Gauge, Shield, Zap, Eye, AlertCircle, Info
} from 'lucide-react';

// =============================================================================
// TYPES
// =============================================================================

interface CalibrationModel {
  id: string;
  name: string;
  version: string;
  modelType: 'anomaly_detection' | 'failure_prediction' | 'rul_estimation';
  calibrationMethod: 'platt_scaling' | 'isotonic_regression' | 'temperature_scaling' | 'conformal_prediction';
  lastCalibrated: string;
  status: 'well_calibrated' | 'mild_drift' | 'needs_recalibration';
}

interface CalibrationMetrics {
  ece: number;           // Expected Calibration Error
  mce: number;           // Maximum Calibration Error
  brierScore: number;
  coverage: number;      // Empirical coverage vs target
  coverageTarget: number;
  avgIntervalWidth: number;
}

interface ReliabilityBin {
  binCenter: number;
  predictedProb: number;
  observedFreq: number;
  nSamples: number;
}

interface UncertaintyGatingStats {
  totalPredictions: number;
  autoActioned: number;
  humanReview: number;
  suppressed: number;
  avgConfidence: number;
  avgUncertainty: number;
}

// =============================================================================
// MOCK DATA
// =============================================================================

const mockModels: CalibrationModel[] = [
  { id: 'ad-v2.1', name: 'Anomaly Detection', version: '2.1.0', modelType: 'anomaly_detection', calibrationMethod: 'temperature_scaling', lastCalibrated: '2024-01-20', status: 'well_calibrated' },
  { id: 'fp-v1.3', name: 'Failure Prediction', version: '1.3.0', modelType: 'failure_prediction', calibrationMethod: 'conformal_prediction', lastCalibrated: '2024-01-18', status: 'mild_drift' },
  { id: 'rul-v3.0', name: 'RUL Estimation', version: '3.0.0', modelType: 'rul_estimation', calibrationMethod: 'conformal_prediction', lastCalibrated: '2024-01-15', status: 'needs_recalibration' },
];

const mockMetrics: Record<string, CalibrationMetrics> = {
  'ad-v2.1': { ece: 0.023, mce: 0.08, brierScore: 0.12, coverage: 0.82, coverageTarget: 0.80, avgIntervalWidth: 0.15 },
  'fp-v1.3': { ece: 0.058, mce: 0.15, brierScore: 0.18, coverage: 0.76, coverageTarget: 0.80, avgIntervalWidth: 0.22 },
  'rul-v3.0': { ece: 0.095, mce: 0.25, brierScore: 0.28, coverage: 0.68, coverageTarget: 0.80, avgIntervalWidth: 0.35 },
};

const mockReliabilityDiagram: ReliabilityBin[] = [
  { binCenter: 0.05, predictedProb: 0.05, observedFreq: 0.04, nSamples: 120 },
  { binCenter: 0.15, predictedProb: 0.15, observedFreq: 0.14, nSamples: 85 },
  { binCenter: 0.25, predictedProb: 0.25, observedFreq: 0.28, nSamples: 62 },
  { binCenter: 0.35, predictedProb: 0.35, observedFreq: 0.32, nSamples: 48 },
  { binCenter: 0.45, predictedProb: 0.45, observedFreq: 0.48, nSamples: 35 },
  { binCenter: 0.55, predictedProb: 0.55, observedFreq: 0.52, nSamples: 42 },
  { binCenter: 0.65, predictedProb: 0.65, observedFreq: 0.68, nSamples: 55 },
  { binCenter: 0.75, predictedProb: 0.75, observedFreq: 0.72, nSamples: 78 },
  { binCenter: 0.85, predictedProb: 0.85, observedFreq: 0.88, nSamples: 95 },
  { binCenter: 0.95, predictedProb: 0.95, observedFreq: 0.92, nSamples: 110 },
];

const mockGatingStats: UncertaintyGatingStats = {
  totalPredictions: 1250,
  autoActioned: 890,
  humanReview: 285,
  suppressed: 75,
  avgConfidence: 0.78,
  avgUncertainty: 0.15,
};

const mockDriftHistory = [
  { date: '2024-01-01', ece: 0.025, coverage: 0.81 },
  { date: '2024-01-05', ece: 0.028, coverage: 0.80 },
  { date: '2024-01-10', ece: 0.032, coverage: 0.79 },
  { date: '2024-01-15', ece: 0.045, coverage: 0.77 },
  { date: '2024-01-20', ece: 0.058, coverage: 0.76 },
  { date: '2024-01-25', ece: 0.062, coverage: 0.75 },
];

// =============================================================================
// COMPONENTS
// =============================================================================

function StatusBadge({ status }: { status: CalibrationModel['status'] }) {
  const config = {
    well_calibrated: { bg: 'bg-green-100', text: 'text-green-700', label: 'Well Calibrated', icon: CheckCircle },
    mild_drift: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Mild Drift', icon: AlertTriangle },
    needs_recalibration: { bg: 'bg-red-100', text: 'text-red-700', label: 'Needs Recalibration', icon: AlertCircle },
  };
  const cfg = config[status];
  const Icon = cfg.icon;
  
  return (
    <span className={`flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${cfg.bg} ${cfg.text}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

function MetricCard({ 
  label, 
  value, 
  format, 
  target, 
  threshold,
  icon: Icon 
}: { 
  label: string; 
  value: number; 
  format: 'percent' | 'decimal';
  target?: number;
  threshold?: { warn: number; error: number };
  icon: typeof Target;
}) {
  const formatValue = (v: number) => format === 'percent' ? `${(v * 100).toFixed(1)}%` : v.toFixed(3);
  
  let status: 'good' | 'warn' | 'error' = 'good';
  if (threshold) {
    if (value >= threshold.error) status = 'error';
    else if (value >= threshold.warn) status = 'warn';
  }
  
  const statusColors = {
    good: 'text-green-600',
    warn: 'text-amber-600',
    error: 'text-red-600',
  };

  return (
    <div className="bg-white rounded-xl p-4 border border-slate-200">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-500">{label}</span>
        <Icon className="w-5 h-5 text-slate-400" />
      </div>
      <p className={`text-2xl font-bold ${statusColors[status]}`}>{formatValue(value)}</p>
      {target !== undefined && (
        <p className="text-xs text-slate-500 mt-1">Target: {formatValue(target)}</p>
      )}
    </div>
  );
}

function ReliabilityDiagram({ bins }: { bins: ReliabilityBin[] }) {
  const maxHeight = 150;
  
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <h3 className="font-semibold text-slate-900 mb-4">Reliability Diagram</h3>
      <div className="relative" style={{ height: maxHeight + 40 }}>
        {/* Perfect calibration line */}
        <div 
          className="absolute bg-slate-300 opacity-50"
          style={{
            left: 0,
            bottom: 20,
            width: '100%',
            height: 2,
            transform: 'rotate(-45deg)',
            transformOrigin: 'bottom left',
          }}
        />
        
        {/* Bins */}
        <div className="flex items-end justify-between h-full gap-1 pb-5">
          {bins.map((bin, idx) => {
            const predictedHeight = bin.predictedProb * maxHeight;
            const observedHeight = bin.observedFreq * maxHeight;
            const gap = Math.abs(bin.predictedProb - bin.observedFreq);
            const gapColor = gap < 0.05 ? 'bg-green-500' : gap < 0.1 ? 'bg-amber-500' : 'bg-red-500';
            
            return (
              <div key={idx} className="flex-1 flex flex-col items-center">
                <div className="relative w-full flex justify-center gap-0.5" style={{ height: maxHeight }}>
                  {/* Predicted bar */}
                  <div 
                    className="w-2 bg-blue-300 rounded-t"
                    style={{ height: predictedHeight, marginTop: 'auto' }}
                    title={`Predicted: ${(bin.predictedProb * 100).toFixed(0)}%`}
                  />
                  {/* Observed bar */}
                  <div 
                    className={`w-2 ${gapColor} rounded-t`}
                    style={{ height: observedHeight, marginTop: 'auto' }}
                    title={`Observed: ${(bin.observedFreq * 100).toFixed(0)}%`}
                  />
                </div>
                <span className="text-xs text-slate-500 mt-1">{(bin.binCenter * 100).toFixed(0)}%</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="flex justify-center gap-4 mt-2 pt-2 border-t border-slate-100">
        <span className="flex items-center gap-1 text-xs text-slate-600">
          <div className="w-3 h-3 bg-blue-300 rounded" /> Predicted
        </span>
        <span className="flex items-center gap-1 text-xs text-slate-600">
          <div className="w-3 h-3 bg-green-500 rounded" /> Observed (calibrated)
        </span>
        <span className="flex items-center gap-1 text-xs text-slate-600">
          <div className="w-3 h-3 bg-red-500 rounded" /> Observed (miscalibrated)
        </span>
      </div>
    </div>
  );
}

function UncertaintyDecomposition() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <h3 className="font-semibold text-slate-900 mb-4">Uncertainty Decomposition</h3>
      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm text-slate-600">Aleatoric (Data)</span>
            <span className="text-sm font-medium text-slate-900">62%</span>
          </div>
          <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full" style={{ width: '62%' }} />
          </div>
          <p className="text-xs text-slate-500 mt-1">Inherent noise in sensor data and failure events</p>
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm text-slate-600">Epistemic (Model)</span>
            <span className="text-sm font-medium text-slate-900">38%</span>
          </div>
          <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-purple-500 rounded-full" style={{ width: '38%' }} />
          </div>
          <p className="text-xs text-slate-500 mt-1">Reducible with more training data or better architecture</p>
        </div>
      </div>
      <div className="mt-4 p-3 bg-blue-50 rounded-lg">
        <p className="text-sm text-blue-800">
          <strong>Insight:</strong> High aleatoric uncertainty suggests focusing on sensor quality and 
          failure labeling consistency rather than model complexity.
        </p>
      </div>
    </div>
  );
}

function DriftMonitor({ history }: { history: typeof mockDriftHistory }) {
  const maxEce = Math.max(...history.map(h => h.ece));
  
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-slate-900">Calibration Drift Monitor</h3>
        <span className="text-xs text-amber-600 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" />
          Drift detected
        </span>
      </div>
      
      <div className="h-32 flex items-end gap-2">
        {history.map((point, idx) => {
          const height = (point.ece / (maxEce * 1.2)) * 100;
          const isRecent = idx >= history.length - 2;
          
          return (
            <div key={idx} className="flex-1 flex flex-col items-center">
              <div 
                className={`w-full rounded-t ${
                  point.ece > 0.05 ? 'bg-amber-500' : 'bg-green-500'
                } ${isRecent ? 'opacity-100' : 'opacity-60'}`}
                style={{ height: `${height}%` }}
                title={`ECE: ${point.ece.toFixed(3)}`}
              />
              <span className="text-xs text-slate-500 mt-1 rotate-45 origin-left">
                {point.date.slice(5)}
              </span>
            </div>
          );
        })}
      </div>
      
      <div className="mt-4 p-3 bg-amber-50 rounded-lg flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-amber-900">Recalibration Recommended</p>
          <p className="text-xs text-amber-700 mt-1">
            ECE has increased from 0.025 to 0.062 over the past 25 days. 
            Consider recalibrating with recent data.
          </p>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function CalibrationDashboardPage() {
  const [selectedModel, setSelectedModel] = useState<string>(mockModels[0].id);
  const [view, setView] = useState<'overview' | 'reliability' | 'gating' | 'drift'>('overview');

  const currentModel = mockModels.find(m => m.id === selectedModel)!;
  const currentMetrics = mockMetrics[selectedModel];

  const decisionGrade = useMemo(() => {
    const eceScore = currentMetrics.ece < 0.03 ? 25 : currentMetrics.ece < 0.05 ? 20 : currentMetrics.ece < 0.08 ? 15 : 10;
    const coverageScore = currentMetrics.coverage >= currentMetrics.coverageTarget ? 25 : 
                          currentMetrics.coverage >= currentMetrics.coverageTarget - 0.05 ? 20 : 15;
    const brierScore = currentMetrics.brierScore < 0.15 ? 25 : currentMetrics.brierScore < 0.2 ? 20 : 15;
    const widthScore = currentMetrics.avgIntervalWidth < 0.2 ? 25 : currentMetrics.avgIntervalWidth < 0.3 ? 20 : 15;
    
    const total = eceScore + coverageScore + brierScore + widthScore;
    if (total >= 90) return { grade: 'A', label: 'Decision-Grade', color: 'bg-green-100 text-green-700' };
    if (total >= 75) return { grade: 'B', label: 'Good', color: 'bg-blue-100 text-blue-700' };
    if (total >= 60) return { grade: 'C', label: 'Acceptable', color: 'bg-amber-100 text-amber-700' };
    return { grade: 'D', label: 'Needs Work', color: 'bg-red-100 text-red-700' };
  }, [currentMetrics]);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Uncertainty & Calibration</h1>
          <p className="text-slate-500">Decision-grade uncertainty quantification for PdM predictions</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="px-3 py-2 border border-slate-200 rounded-lg text-sm"
          >
            {mockModels.map(m => (
              <option key={m.id} value={m.id}>{m.name} v{m.version}</option>
            ))}
          </select>
          <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700">
            <RefreshCw className="w-4 h-4" />
            Recalibrate
          </button>
        </div>
      </div>

      {/* Model Summary Card */}
      <div className="bg-gradient-to-r from-slate-50 to-blue-50 rounded-xl border border-slate-200 p-6">
        <div className="flex items-center gap-6">
          <div className={`w-20 h-20 rounded-full flex items-center justify-center text-3xl font-bold ${decisionGrade.color}`}>
            {decisionGrade.grade}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h2 className="text-xl font-bold text-slate-900">{currentModel.name}</h2>
              <StatusBadge status={currentModel.status} />
            </div>
            <p className="text-slate-600">
              {decisionGrade.label} uncertainty - {currentModel.calibrationMethod.replace(/_/g, ' ')} calibration
            </p>
            <p className="text-sm text-slate-500 mt-1">
              Last calibrated: {new Date(currentModel.lastCalibrated).toLocaleDateString()}
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-slate-500">Uncertainty Gating</p>
            <p className="text-2xl font-bold text-green-600">
              {((mockGatingStats.autoActioned / mockGatingStats.totalPredictions) * 100).toFixed(0)}%
            </p>
            <p className="text-xs text-slate-500">Auto-actioned</p>
          </div>
        </div>
      </div>

      {/* View Tabs */}
      <div className="flex gap-2 border-b border-slate-200">
        {[
          { id: 'overview', label: 'Overview', icon: Gauge },
          { id: 'reliability', label: 'Reliability', icon: Target },
          { id: 'gating', label: 'Uncertainty Gating', icon: Shield },
          { id: 'drift', label: 'Drift Monitor', icon: Activity },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setView(tab.id as typeof view)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
              view === tab.id 
                ? 'border-orange-500 text-orange-600' 
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview View */}
      {view === 'overview' && (
        <div className="space-y-6">
          {/* Key Metrics */}
          <div className="grid grid-cols-4 gap-4">
            <MetricCard 
              label="Expected Calibration Error" 
              value={currentMetrics.ece} 
              format="decimal"
              threshold={{ warn: 0.05, error: 0.1 }}
              icon={Target}
            />
            <MetricCard 
              label="Coverage" 
              value={currentMetrics.coverage} 
              format="percent"
              target={currentMetrics.coverageTarget}
              icon={Shield}
            />
            <MetricCard 
              label="Brier Score" 
              value={currentMetrics.brierScore} 
              format="decimal"
              threshold={{ warn: 0.2, error: 0.3 }}
              icon={BarChart3}
            />
            <MetricCard 
              label="Avg Interval Width" 
              value={currentMetrics.avgIntervalWidth} 
              format="percent"
              icon={Activity}
            />
          </div>

          <div className="grid grid-cols-2 gap-6">
            <ReliabilityDiagram bins={mockReliabilityDiagram} />
            <UncertaintyDecomposition />
          </div>

          {/* Conformal Prediction Info */}
          {currentModel.calibrationMethod === 'conformal_prediction' && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <Info className="w-5 h-5 text-blue-600 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-blue-900">Conformal Prediction Active</h3>
                  <p className="text-sm text-blue-700 mt-1">
                    This model uses conformal prediction to provide distribution-free prediction intervals 
                    with guaranteed coverage. The intervals automatically adapt to local difficulty, 
                    becoming wider when the model is less certain.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Reliability View */}
      {view === 'reliability' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-6">
            <ReliabilityDiagram bins={mockReliabilityDiagram} />
            
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-4">Bin-wise Analysis</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50">
                      <th className="text-left px-3 py-2">Bin</th>
                      <th className="text-right px-3 py-2">Predicted</th>
                      <th className="text-right px-3 py-2">Observed</th>
                      <th className="text-right px-3 py-2">Gap</th>
                      <th className="text-right px-3 py-2">n</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {mockReliabilityDiagram.map((bin, idx) => {
                      const gap = Math.abs(bin.predictedProb - bin.observedFreq);
                      return (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="px-3 py-2">{(bin.binCenter * 100).toFixed(0)}%</td>
                          <td className="text-right px-3 py-2">{(bin.predictedProb * 100).toFixed(1)}%</td>
                          <td className="text-right px-3 py-2">{(bin.observedFreq * 100).toFixed(1)}%</td>
                          <td className={`text-right px-3 py-2 font-medium ${
                            gap < 0.05 ? 'text-green-600' : gap < 0.1 ? 'text-amber-600' : 'text-red-600'
                          }`}>
                            {(gap * 100).toFixed(1)}%
                          </td>
                          <td className="text-right px-3 py-2 text-slate-500">{bin.nSamples}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Gating View */}
      {view === 'gating' && (
        <div className="space-y-6">
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-white rounded-xl p-4 border border-green-200 bg-green-50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-green-600">Auto-Actioned</span>
                <Zap className="w-5 h-5 text-green-500" />
              </div>
              <p className="text-2xl font-bold text-green-700">{mockGatingStats.autoActioned}</p>
              <p className="text-xs text-green-600 mt-1">
                {((mockGatingStats.autoActioned / mockGatingStats.totalPredictions) * 100).toFixed(0)}% of predictions
              </p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-amber-200 bg-amber-50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-amber-600">Human Review</span>
                <Eye className="w-5 h-5 text-amber-500" />
              </div>
              <p className="text-2xl font-bold text-amber-700">{mockGatingStats.humanReview}</p>
              <p className="text-xs text-amber-600 mt-1">
                {((mockGatingStats.humanReview / mockGatingStats.totalPredictions) * 100).toFixed(0)}% escalated
              </p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-500">Suppressed</span>
                <AlertCircle className="w-5 h-5 text-slate-400" />
              </div>
              <p className="text-2xl font-bold text-slate-700">{mockGatingStats.suppressed}</p>
              <p className="text-xs text-slate-500 mt-1">
                Low confidence predictions
              </p>
            </div>
            <div className="bg-white rounded-xl p-4 border border-slate-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-500">Avg Confidence</span>
                <Gauge className="w-5 h-5 text-slate-400" />
              </div>
              <p className="text-2xl font-bold text-slate-900">{(mockGatingStats.avgConfidence * 100).toFixed(0)}%</p>
              <p className="text-xs text-slate-500 mt-1">
                ±{(mockGatingStats.avgUncertainty * 100).toFixed(0)}% uncertainty
              </p>
            </div>
          </div>

          {/* Gating Policy */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900 mb-4">Active Gating Policy</h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="p-4 bg-green-50 rounded-lg">
                <h4 className="font-medium text-green-900 mb-2">Auto-Dispatch</h4>
                <ul className="text-sm text-green-700 space-y-1">
                  <li>• Confidence ≥ 85%</li>
                  <li>• Uncertainty ≤ 10%</li>
                  <li>• Coverage validated</li>
                </ul>
              </div>
              <div className="p-4 bg-amber-50 rounded-lg">
                <h4 className="font-medium text-amber-900 mb-2">Human Review</h4>
                <ul className="text-sm text-amber-700 space-y-1">
                  <li>• Confidence 60-85%</li>
                  <li>• OR Uncertainty &gt; 10%</li>
                  <li>• Escalate to operator</li>
                </ul>
              </div>
              <div className="p-4 bg-slate-100 rounded-lg">
                <h4 className="font-medium text-slate-900 mb-2">Suppress</h4>
                <ul className="text-sm text-slate-700 space-y-1">
                  <li>• Confidence &lt; 60%</li>
                  <li>• Flag as uncertain</li>
                  <li>• Log for review</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Drift View */}
      {view === 'drift' && (
        <div className="space-y-6">
          <DriftMonitor history={mockDriftHistory} />
          
          {/* All Models Status */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900 mb-4">All Models Calibration Status</h3>
            <div className="space-y-3">
              {mockModels.map(model => {
                const metrics = mockMetrics[model.id];
                return (
                  <div 
                    key={model.id}
                    className={`flex items-center justify-between p-3 rounded-lg cursor-pointer ${
                      model.id === selectedModel ? 'bg-orange-50 border border-orange-200' : 'bg-slate-50 hover:bg-slate-100'
                    }`}
                    onClick={() => setSelectedModel(model.id)}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-slate-200 rounded-lg flex items-center justify-center">
                        <Activity className="w-5 h-5 text-slate-600" />
                      </div>
                      <div>
                        <p className="font-medium text-slate-900">{model.name}</p>
                        <p className="text-xs text-slate-500">v{model.version} • {model.calibrationMethod.replace(/_/g, ' ')}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-sm font-medium text-slate-900">ECE: {metrics.ece.toFixed(3)}</p>
                        <p className="text-xs text-slate-500">Coverage: {(metrics.coverage * 100).toFixed(0)}%</p>
                      </div>
                      <StatusBadge status={model.status} />
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
