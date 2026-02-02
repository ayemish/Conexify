import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  AlertTriangle,
  Clock,
  User,
  Building2,
  Cpu,
  CheckCircle2,
  XCircle,
  Play,
  FileText,
  MessageSquare,
  Download,
  Shield,
  Activity,
  TrendingUp,
  ChevronDown,
  ChevronRight,
  DollarSign,
  Timer,
  Zap,
  BarChart3,
  Cloud,
  Thermometer,
  Users,
  BatteryCharging
} from 'lucide-react';
import { cases } from '../data/mockData';
import type { CaseSeverity, CaseStatus } from '../types';

// Mock EV decision data
const evDecisionData = {
  actionCost: 500,
  avoidedCostPerHour: 2500,
  estimatedDowntimeHours: 4,
  failureProbability: 0.78,
  expectedValue: 7300,
  breakEvenConfidence: 0.05,
  recommendedTiming: 'immediate' as const,
  costOfDelay: 625,
  batchOpportunity: true,
  nearbyIssues: 2,
};

// Mock contributing metrics for explainability
const contributingMetrics = [
  { name: 'Discharge Pressure', value: 312, unit: 'psi', baseline: 285, contribution: 35, trend: 'up' as const },
  { name: 'Suction Temperature', value: 42, unit: '°F', baseline: 38, contribution: 28, trend: 'up' as const },
  { name: 'Compressor Amps', value: 18.5, unit: 'A', baseline: 15.2, contribution: 22, trend: 'up' as const },
  { name: 'Superheat', value: 8, unit: '°F', baseline: 12, contribution: 10, trend: 'down' as const },
  { name: 'Subcooling', value: 6, unit: '°F', baseline: 10, contribution: 5, trend: 'down' as const },
];

// Mock weather and energy context (FR-001)
const contextData = {
  weather: {
    temperature: 92,
    humidity: 78,
    condition: 'Partly Cloudy',
    forecast: 'Heat advisory next 3 days',
  },
  energy: {
    currentRate: 0.14,
    rateTier: 'peak',
    demandCharge: 12.50,
    gridStress: 'high',
  },
  occupancy: {
    current: 85,
    scheduled: 'Open',
    peakHours: true,
  },
};

const severityConfig: Record<CaseSeverity, { color: string; bg: string }> = {
  critical: { color: 'text-red-600', bg: 'bg-red-100' },
  high: { color: 'text-orange-600', bg: 'bg-orange-100' },
  medium: { color: 'text-amber-600', bg: 'bg-amber-100' },
  low: { color: 'text-blue-600', bg: 'bg-blue-100' },
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

const riskConfig = {
  low: { color: 'text-green-600', bg: 'bg-green-100' },
  medium: { color: 'text-amber-600', bg: 'bg-amber-100' },
  high: { color: 'text-orange-600', bg: 'bg-orange-100' },
  critical: { color: 'text-red-600', bg: 'bg-red-100' },
};

const timelineTypeConfig = {
  detection: { color: 'text-blue-600', bg: 'bg-blue-100', icon: Activity },
  recommendation: { color: 'text-purple-600', bg: 'bg-purple-100', icon: FileText },
  approval: { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle2 },
  denial: { color: 'text-red-600', bg: 'bg-red-100', icon: XCircle },
  execution: { color: 'text-cyan-600', bg: 'bg-cyan-100', icon: Play },
  verification: { color: 'text-teal-600', bg: 'bg-teal-100', icon: Shield },
  note: { color: 'text-slate-600', bg: 'bg-slate-100', icon: MessageSquare },
  assignment: { color: 'text-indigo-600', bg: 'bg-indigo-100', icon: User },
};

export function CaseCockpitPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [expandedActions, setExpandedActions] = useState<Set<string>>(new Set());
  const [note, setNote] = useState('');

  const caseData = cases.find(c => c.id === caseId);

  if (!caseData) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-slate-500">Case not found</p>
      </div>
    );
  }

  const toggleAction = (actionId: string) => {
    const newExpanded = new Set(expandedActions);
    if (newExpanded.has(actionId)) {
      newExpanded.delete(actionId);
    } else {
      newExpanded.add(actionId);
    }
    setExpandedActions(newExpanded);
  };

  const formatTimeRemaining = (slaDue: string) => {
    const diff = new Date(slaDue).getTime() - Date.now();
    if (diff < 0) return 'Overdue';
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
    return `${hours}h ${mins}m`;
  };

  const slaRemaining = formatTimeRemaining(caseData.slaDue);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-4 mb-4">
          <button
            onClick={() => navigate('/cases')}
            className="p-2 hover:bg-slate-100 rounded-lg"
          >
            <ArrowLeft className="w-5 h-5 text-slate-600" />
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm text-slate-500 font-mono">{caseData.id}</span>
              <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${severityConfig[caseData.severity].bg} ${severityConfig[caseData.severity].color}`}>
                {caseData.severity}
              </span>
              <span className={`px-2 py-0.5 text-xs font-medium rounded ${statusConfig[caseData.status].bg} ${statusConfig[caseData.status].color}`}>
                {statusConfig[caseData.status].label}
              </span>
            </div>
            <h1 className="text-xl font-bold text-slate-900">{caseData.title}</h1>
          </div>
          <div className={`text-right px-4 py-2 rounded-lg ${
            caseData.slaStatus === 'breached' ? 'bg-red-100' :
            caseData.slaStatus === 'at_risk' ? 'bg-amber-100' : 'bg-green-100'
          }`}>
            <p className="text-xs text-slate-500">SLA</p>
            <p className={`font-bold ${
              caseData.slaStatus === 'breached' ? 'text-red-600' :
              caseData.slaStatus === 'at_risk' ? 'text-amber-600' : 'text-green-600'
            }`}>{slaRemaining}</p>
          </div>
        </div>
        <div className="flex items-center gap-6 text-sm text-slate-600">
          <span className="flex items-center gap-1">
            <Cpu className="w-4 h-4" />
            {caseData.assetName}
          </span>
          <span className="flex items-center gap-1">
            <Building2 className="w-4 h-4" />
            {caseData.siteName}
          </span>
          <span className="flex items-center gap-1">
            <User className="w-4 h-4" />
            {caseData.assigneeName || 'Unassigned'}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-4 h-4" />
            Created {new Date(caseData.createdAt).toLocaleString()}
          </span>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-3 gap-4">
        {/* Left Column: Diagnosis + Evidence */}
        <div className="col-span-2 space-y-4">
          {/* Expected Value Decision Panel (FR-013) */}
          <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl border border-green-200">
            <div className="p-4 border-b border-green-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-green-600" />
                <h2 className="font-semibold text-green-900">Expected Value Analysis</h2>
              </div>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                evDecisionData.recommendedTiming === 'immediate' 
                  ? 'bg-red-100 text-red-700' 
                  : evDecisionData.recommendedTiming === 'next_visit'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-blue-100 text-blue-700'
              }`}>
                <Timer className="w-4 h-4 inline mr-1" />
                {evDecisionData.recommendedTiming === 'immediate' ? 'Act Now' : 
                 evDecisionData.recommendedTiming === 'next_visit' ? 'Next Visit' : 'Monitor'}
              </span>
            </div>
            <div className="p-4">
              <div className="grid grid-cols-4 gap-4 mb-4">
                <div className="bg-white rounded-lg p-3 border border-green-100">
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Zap className="w-3 h-3" /> Action Cost
                  </p>
                  <p className="text-lg font-bold text-slate-900">${evDecisionData.actionCost.toLocaleString()}</p>
                </div>
                <div className="bg-white rounded-lg p-3 border border-green-100">
                  <p className="text-xs text-slate-500">Avoided Cost ({evDecisionData.estimatedDowntimeHours}hr)</p>
                  <p className="text-lg font-bold text-green-600">
                    ${(evDecisionData.avoidedCostPerHour * evDecisionData.estimatedDowntimeHours).toLocaleString()}
                  </p>
                </div>
                <div className="bg-white rounded-lg p-3 border border-green-100">
                  <p className="text-xs text-slate-500">Failure Probability</p>
                  <p className="text-lg font-bold text-orange-600">{(evDecisionData.failureProbability * 100).toFixed(0)}%</p>
                </div>
                <div className="bg-green-100 rounded-lg p-3 border border-green-200">
                  <p className="text-xs text-green-700 font-medium">Expected Value</p>
                  <p className="text-xl font-bold text-green-700">${evDecisionData.expectedValue.toLocaleString()}</p>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-4">
                  <span className="text-slate-600">
                    Break-even confidence: <strong className="text-slate-900">{(evDecisionData.breakEvenConfidence * 100).toFixed(1)}%</strong>
                  </span>
                  <span className="text-slate-600">
                    Cost of 1hr delay: <strong className="text-red-600">${evDecisionData.costOfDelay.toLocaleString()}</strong>
                  </span>
                </div>
                {evDecisionData.batchOpportunity && (
                  <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                    💡 Batch with {evDecisionData.nearbyIssues} nearby issues
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Diagnosis Panel */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200">
              <h2 className="font-semibold text-slate-900">Diagnosis</h2>
            </div>
            <div className="p-4">
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${severityConfig[caseData.severity].bg}`}>
                  <AlertTriangle className={`w-6 h-6 ${severityConfig[caseData.severity].color}`} />
                </div>
                <div className="flex-1">
                  <p className="text-slate-700">{caseData.description}</p>
                  <div className="mt-4 grid grid-cols-3 gap-4">
                    <div className="bg-slate-50 rounded-lg p-3">
                      <p className="text-xs text-slate-500">Fault Type</p>
                      <p className="font-medium text-slate-900">{caseData.faultType}</p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-3">
                      <p className="text-xs text-slate-500">Confidence</p>
                      <p className="font-medium text-slate-900">{(caseData.confidence * 100).toFixed(0)}%</p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-3">
                      <p className="text-xs text-slate-500">Customer Impact</p>
                      <p className={`font-medium capitalize ${
                        caseData.customerImpact === 'high' ? 'text-red-600' :
                        caseData.customerImpact === 'medium' ? 'text-amber-600' : 'text-green-600'
                      }`}>{caseData.customerImpact}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Contributing Metrics Panel (FR-018) */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-slate-600" />
                <h2 className="font-semibold text-slate-900">Contributing Metrics</h2>
              </div>
              <span className="text-xs text-slate-500">Top signals driving this diagnosis</span>
            </div>
            <div className="p-4">
              <div className="space-y-3">
                {contributingMetrics.map((metric) => (
                  <div key={metric.name} className="flex items-center gap-4">
                    <div className="w-40 flex-shrink-0">
                      <p className="text-sm font-medium text-slate-900">{metric.name}</p>
                      <p className="text-xs text-slate-500">
                        {metric.value} {metric.unit} vs {metric.baseline} {metric.unit} baseline
                      </p>
                    </div>
                    <div className="flex-1">
                      <div className="relative h-6 bg-slate-100 rounded-full overflow-hidden">
                        <div 
                          className={`absolute inset-y-0 left-0 rounded-full ${
                            metric.contribution > 25 ? 'bg-red-500' :
                            metric.contribution > 15 ? 'bg-orange-500' : 'bg-amber-500'
                          }`}
                          style={{ width: `${metric.contribution}%` }}
                        />
                        <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-slate-700">
                          {metric.contribution}% contribution
                        </span>
                      </div>
                    </div>
                    <div className="w-16 text-right">
                      <span className={`flex items-center justify-end gap-1 text-sm font-medium ${
                        metric.trend === 'up' ? 'text-red-600' : 'text-blue-600'
                      }`}>
                        <TrendingUp className={`w-4 h-4 ${metric.trend === 'down' ? 'rotate-180' : ''}`} />
                        {metric.trend === 'up' ? '+' : ''}{((metric.value - metric.baseline) / metric.baseline * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-4 border-t border-slate-100">
                <p className="text-xs text-slate-500">
                  <strong>Model explanation:</strong> High discharge pressure combined with elevated suction temperature 
                  indicates potential refrigerant overcharge or condenser fouling. The anomaly pattern matches 
                  87% of historical condenser failure cases.
                </p>
              </div>
            </div>
          </div>

          {/* Recommended Actions Panel */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <h2 className="font-semibold text-slate-900">Recommended Actions</h2>
              <span className="text-xs text-slate-500">{caseData.recommendedActions.length} actions</span>
            </div>
            <div className="divide-y divide-slate-100">
              {caseData.recommendedActions.map((action, index) => (
                <div key={action.id} className="p-4">
                  <button
                    onClick={() => toggleAction(action.id)}
                    className="w-full"
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex items-center justify-center w-8 h-8 bg-slate-100 rounded-full text-sm font-medium text-slate-600">
                        {index + 1}
                      </div>
                      <div className="flex-1 text-left">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-medium text-slate-900">{action.title}</h3>
                          <span className={`px-2 py-0.5 text-xs font-medium rounded capitalize ${riskConfig[action.riskTier].bg} ${riskConfig[action.riskTier].color}`}>
                            {action.riskTier} risk
                          </span>
                          <span className="px-2 py-0.5 text-xs font-medium rounded bg-slate-100 text-slate-600 capitalize">
                            {action.type.replace('_', ' ')}
                          </span>
                          {action.approvalRequired && (
                            <span className="px-2 py-0.5 text-xs font-medium rounded bg-amber-100 text-amber-700">
                              Approval Required
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-slate-600">{action.description}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-700">
                          {(action.confidence * 100).toFixed(0)}%
                        </span>
                        {expandedActions.has(action.id) ? (
                          <ChevronDown className="w-5 h-5 text-slate-400" />
                        ) : (
                          <ChevronRight className="w-5 h-5 text-slate-400" />
                        )}
                      </div>
                    </div>
                  </button>

                  {expandedActions.has(action.id) && (
                    <div className="mt-4 ml-12 space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="bg-green-50 rounded-lg p-3">
                          <p className="text-xs text-green-700 font-medium mb-1">Expected Benefit</p>
                          <p className="text-sm text-green-900">{action.expectedBenefit}</p>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3">
                          <p className="text-xs text-slate-500 font-medium mb-1">Verification Plan</p>
                          <p className="text-sm text-slate-700">{action.verificationPlan}</p>
                        </div>
                      </div>
                      {action.preconditions.length > 0 && (
                        <div className="bg-blue-50 rounded-lg p-3">
                          <p className="text-xs text-blue-700 font-medium mb-1">Preconditions</p>
                          <ul className="text-sm text-blue-900 list-disc list-inside">
                            {action.preconditions.map((p, i) => <li key={i}>{p}</li>)}
                          </ul>
                        </div>
                      )}
                      {action.constraints.length > 0 && (
                        <div className="bg-amber-50 rounded-lg p-3">
                          <p className="text-xs text-amber-700 font-medium mb-1">Constraints</p>
                          <ul className="text-sm text-amber-900 list-disc list-inside">
                            {action.constraints.map((c, i) => <li key={i}>{c}</li>)}
                          </ul>
                        </div>
                      )}
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-xs text-slate-500 font-medium mb-1">Rollback Plan</p>
                        <p className="text-sm text-slate-700">{action.rollbackPlan}</p>
                      </div>
                      <div className="flex items-center gap-2 pt-2">
                        {action.approvalRequired ? (
                          <>
                            <button className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm">
                              <CheckCircle2 className="w-4 h-4" />
                              Approve
                            </button>
                            <button className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm">
                              <XCircle className="w-4 h-4" />
                              Deny
                            </button>
                          </>
                        ) : (
                          <button className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
                            <Play className="w-4 h-4" />
                            Execute
                          </button>
                        )}
                        <button className="flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm">
                          Request More Evidence
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Timeline + Chat */}
        <div className="space-y-4">
          {/* Context Panel (FR-001: Weather, Energy, Occupancy) */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-3 border-b border-slate-200">
              <h2 className="font-semibold text-slate-900 text-sm">Site Context</h2>
            </div>
            <div className="p-3 space-y-3">
              {/* Weather */}
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Cloud className="w-4 h-4 text-blue-600" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Weather</span>
                    <span className="text-xs text-amber-600 font-medium">{contextData.weather.condition}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Thermometer className="w-3 h-3 text-red-500" />
                    <span className="text-sm font-medium text-slate-900">{contextData.weather.temperature}°F</span>
                    <span className="text-xs text-slate-500">/ {contextData.weather.humidity}% RH</span>
                  </div>
                </div>
              </div>

              {/* Energy */}
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                  contextData.energy.gridStress === 'high' ? 'bg-red-100' : 'bg-green-100'
                }`}>
                  <BatteryCharging className={`w-4 h-4 ${
                    contextData.energy.gridStress === 'high' ? 'text-red-600' : 'text-green-600'
                  }`} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Energy</span>
                    <span className={`text-xs font-medium capitalize px-1.5 py-0.5 rounded ${
                      contextData.energy.rateTier === 'peak' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                    }`}>
                      {contextData.energy.rateTier}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-900">${contextData.energy.currentRate}/kWh</span>
                    <span className="text-xs text-slate-500">+ ${contextData.energy.demandCharge}/kW</span>
                  </div>
                </div>
              </div>

              {/* Occupancy */}
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center">
                  <Users className="w-4 h-4 text-purple-600" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Occupancy</span>
                    <span className="text-xs text-green-600 font-medium">{contextData.occupancy.scheduled}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-900">{contextData.occupancy.current}%</span>
                    {contextData.occupancy.peakHours && (
                      <span className="text-xs text-amber-600">Peak hours</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="flex items-center gap-2 flex-wrap">
              <button className="flex items-center gap-1 px-3 py-1.5 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
                <FileText className="w-4 h-4" />
                Create Work Order
              </button>
              <button className="flex items-center gap-1 px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 text-sm">
                <Download className="w-4 h-4" />
                Evidence Packet
              </button>
              <button className="flex items-center gap-1 px-3 py-1.5 bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200 text-sm">
                <Shield className="w-4 h-4" />
                Safe Mode
              </button>
            </div>
          </div>

          {/* Timeline */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <h2 className="font-semibold text-slate-900">Timeline</h2>
              <button className="text-xs text-orange-600 hover:text-orange-700">Export</button>
            </div>
            <div className="p-4 max-h-80 overflow-auto">
              <div className="space-y-4">
                {caseData.timeline.map((event, index) => {
                  const config = timelineTypeConfig[event.type];
                  const Icon = config.icon;
                  return (
                    <div key={event.id} className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${config.bg}`}>
                          <Icon className={`w-4 h-4 ${config.color}`} />
                        </div>
                        {index < caseData.timeline.length - 1 && (
                          <div className="w-px h-full bg-slate-200 mt-2" />
                        )}
                      </div>
                      <div className="flex-1 pb-4">
                        <p className="text-xs text-slate-500">
                          {new Date(event.timestamp).toLocaleString()}
                        </p>
                        <p className="text-sm text-slate-900 mt-0.5">{event.description}</p>
                        <p className="text-xs text-slate-500 mt-1">
                          {event.actorType === 'model' ? '🤖 ' : event.actorType === 'system' ? '⚙️ ' : '👤 '}
                          {event.actor}
                          {event.modelVersion && ` (${event.modelVersion})`}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Notes */}
          <div className="bg-white rounded-xl border border-slate-200">
            <div className="p-4 border-b border-slate-200">
              <h2 className="font-semibold text-slate-900">Add Note</h2>
            </div>
            <div className="p-4">
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add investigation notes..."
                className="w-full p-3 border border-slate-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-500"
                rows={3}
              />
              <button className="mt-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm">
                Add Note
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
