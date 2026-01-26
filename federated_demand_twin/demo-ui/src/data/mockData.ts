import type { 
  BayesianPrediction, ModelParameter, FederatedNode,
  Device, TwinActivity, Agent, AgentAction, OrchestrationStep,
  AgentOutput, Case
} from '../types';

// Bayesian Model Data
export const bayesianPredictions: BayesianPrediction[] = [
  {
    id: 'pred-001',
    timestamp: '2026-01-24T15:30:00Z',
    metric: 'Compressor Failure Probability',
    predictedValue: 0.73,
    confidenceInterval: [0.65, 0.81],
    probability: 0.73,
    priorMean: 0.45,
    posteriorMean: 0.73,
    uncertainty: 0.08,
  },
  {
    id: 'pred-002',
    timestamp: '2026-01-24T15:30:00Z',
    metric: 'Discharge Temperature (°F)',
    predictedValue: 185,
    confidenceInterval: [178, 192],
    probability: 0.89,
    priorMean: 165,
    posteriorMean: 185,
    uncertainty: 7,
  },
  {
    id: 'pred-003',
    timestamp: '2026-01-24T15:30:00Z',
    metric: 'Energy Consumption (kWh)',
    predictedValue: 2340,
    confidenceInterval: [2180, 2500],
    probability: 0.92,
    priorMean: 2100,
    posteriorMean: 2340,
    uncertainty: 160,
  },
  {
    id: 'pred-004',
    timestamp: '2026-01-24T15:30:00Z',
    metric: 'Cycle Rate (cycles/hr)',
    predictedValue: 28,
    confidenceInterval: [24, 32],
    probability: 0.85,
    priorMean: 8,
    posteriorMean: 28,
    uncertainty: 4,
  },
];

export const modelParameters: ModelParameter[] = [
  { name: 'α (failure rate)', prior: 0.02, posterior: 0.045, credibleInterval: [0.035, 0.055] },
  { name: 'β (wear coefficient)', prior: 1.5, posterior: 2.1, credibleInterval: [1.8, 2.4] },
  { name: 'σ (noise)', prior: 0.1, posterior: 0.08, credibleInterval: [0.06, 0.10] },
  { name: 'λ (decay rate)', prior: 0.005, posterior: 0.012, credibleInterval: [0.008, 0.016] },
];

export const federatedNodes: FederatedNode[] = [
  { id: 'node-1', name: 'Building A - HVAC', location: 'Floor 1-5', status: 'active', lastSync: '2 min ago', localSamples: 15420, contribution: 0.32 },
  { id: 'node-2', name: 'Building A - Chillers', location: 'Basement', status: 'active', lastSync: '1 min ago', localSamples: 8930, contribution: 0.21 },
  { id: 'node-3', name: 'Building B - HVAC', location: 'Floor 1-8', status: 'syncing', lastSync: '5 min ago', localSamples: 22100, contribution: 0.28 },
  { id: 'node-4', name: 'Building B - Pumps', location: 'Mechanical', status: 'active', lastSync: '30 sec ago', localSamples: 6780, contribution: 0.19 },
];

// Digital Twin Data
export const devices: Device[] = [
  {
    id: 'hvac-001',
    name: 'RTU-01 Compressor',
    type: 'compressor',
    status: 'warning',
    location: 'Building A, Roof',
    lastUpdate: '10 sec ago',
    metrics: [
      { name: 'Discharge Temp', value: 187, unit: '°F', threshold: { max: 180 }, trend: 'up' },
      { name: 'Cycle Rate', value: 26, unit: 'cycles/hr', threshold: { max: 12 }, trend: 'up' },
      { name: 'Suction Pressure', value: 68, unit: 'psi', threshold: { min: 60, max: 80 }, trend: 'stable' },
      { name: 'Runtime', value: 2847, unit: 'hrs', trend: 'up' },
    ],
  },
  {
    id: 'hvac-002',
    name: 'AHU-03 Supply Fan',
    type: 'hvac',
    status: 'normal',
    location: 'Building A, Floor 3',
    lastUpdate: '15 sec ago',
    metrics: [
      { name: 'CFM', value: 4200, unit: 'cfm', threshold: { min: 3800, max: 4500 }, trend: 'stable' },
      { name: 'Static Pressure', value: 1.2, unit: 'in.wc', threshold: { max: 1.5 }, trend: 'stable' },
      { name: 'VFD Speed', value: 72, unit: '%', trend: 'stable' },
    ],
  },
  {
    id: 'pump-001',
    name: 'CHW Pump 1',
    type: 'pump',
    status: 'normal',
    location: 'Building A, Basement',
    lastUpdate: '8 sec ago',
    metrics: [
      { name: 'Flow Rate', value: 450, unit: 'GPM', threshold: { min: 400, max: 500 }, trend: 'stable' },
      { name: 'Head Pressure', value: 45, unit: 'ft', trend: 'stable' },
      { name: 'Power', value: 18.5, unit: 'kW', trend: 'stable' },
    ],
  },
  {
    id: 'valve-001',
    name: 'CHW Valve V-12',
    type: 'valve',
    status: 'normal',
    location: 'Building A, Floor 2',
    lastUpdate: '12 sec ago',
    metrics: [
      { name: 'Position', value: 65, unit: '%', trend: 'stable' },
      { name: 'Delta T', value: 12, unit: '°F', threshold: { min: 10, max: 15 }, trend: 'stable' },
    ],
  },
];

export const twinActivities: TwinActivity[] = [
  { id: 'act-1', timestamp: '15:32:45', type: 'alert', deviceId: 'hvac-001', message: 'Discharge temperature exceeded threshold (187°F > 180°F)', severity: 'warning' },
  { id: 'act-2', timestamp: '15:32:30', type: 'alert', deviceId: 'hvac-001', message: 'Short-cycling detected: 26 cycles/hr (threshold: 12)', severity: 'warning' },
  { id: 'act-3', timestamp: '15:31:15', type: 'prediction', deviceId: 'hvac-001', message: 'Bayesian model predicts 73% failure probability within 48 hours', severity: 'critical' },
  { id: 'act-4', timestamp: '15:30:00', type: 'telemetry', deviceId: 'hvac-002', message: 'Telemetry batch received: 24 readings', severity: 'info' },
  { id: 'act-5', timestamp: '15:29:45', type: 'action', deviceId: 'hvac-001', message: 'Diagnostics agent initiated fault tree analysis', severity: 'info' },
  { id: 'act-6', timestamp: '15:28:30', type: 'telemetry', deviceId: 'pump-001', message: 'Flow rate stable at 450 GPM', severity: 'info' },
];

// Agent Data
export const agents: Agent[] = [
  { id: 'agent-1', name: 'Signal Triage', role: 'Alert Classification', status: 'completed', avatar: '🔍', description: 'Deduplicates, filters, and classifies incoming alerts' },
  { id: 'agent-2', name: 'Correlation', role: 'Pattern Detection', status: 'completed', avatar: '🔗', description: 'Clusters related alerts and detects cascade patterns' },
  { id: 'agent-3', name: 'Diagnostics', role: 'Fault Analysis', status: 'processing', avatar: '🔬', description: 'Runs fault trees and matches failure signatures' },
  { id: 'agent-4', name: 'Root Cause Analyst', role: 'Hypothesis Generation', status: 'waiting', avatar: '🎯', description: 'Proposes root cause hypotheses with confidence scores' },
  { id: 'agent-5', name: 'Remediation Planner', role: 'Action Planning', status: 'idle', avatar: '📋', description: 'Creates ordered remediation action plans' },
  { id: 'agent-6', name: 'Tool Executor', role: 'Action Execution', status: 'idle', avatar: '⚙️', description: 'Executes approved actions with audit logging' },
  { id: 'agent-7', name: 'Verification', role: 'Effectiveness Check', status: 'idle', avatar: '✅', description: 'Confirms remediation effectiveness via telemetry' },
  { id: 'agent-8', name: 'Customer Comms', role: 'Stakeholder Updates', status: 'idle', avatar: '📧', description: 'Drafts status updates and escalation notices' },
  { id: 'agent-9', name: 'Governance', role: 'Policy Enforcement', status: 'processing', avatar: '🛡️', description: 'Enforces RBAC, approvals, and compliance' },
  { id: 'agent-10', name: 'Learning', role: 'Knowledge Extraction', status: 'idle', avatar: '🧠', description: 'Extracts lessons and updates runbooks' },
];

export const agentActions: AgentAction[] = [
  { id: 'action-1', agentId: 'agent-1', agentName: 'Signal Triage', timestamp: '15:30:05', action: 'Classified alert', target: 'hvac-001', status: 'completed', duration: 120 },
  { id: 'action-2', agentId: 'agent-1', agentName: 'Signal Triage', timestamp: '15:30:08', action: 'Created case', target: 'CASE-2026-0124-001', status: 'completed', duration: 85 },
  { id: 'action-3', agentId: 'agent-2', agentName: 'Correlation', timestamp: '15:30:15', action: 'Correlated alerts', target: '3 related alerts', status: 'completed', duration: 340 },
  { id: 'action-4', agentId: 'agent-3', agentName: 'Diagnostics', timestamp: '15:30:45', action: 'Running fault tree', target: 'compressor_short_cycle', status: 'in_progress' },
  { id: 'action-5', agentId: 'agent-9', agentName: 'Governance', timestamp: '15:30:50', action: 'Policy check', target: 'setpoint_adjustment', status: 'in_progress' },
];

export const orchestrationSteps: OrchestrationStep[] = [
  { id: 'step-1', name: 'Intake', agents: ['Signal Triage'], status: 'completed', startTime: '15:30:00', endTime: '15:30:05' },
  { id: 'step-2', name: 'Triage', agents: ['Signal Triage', 'Governance'], status: 'completed', startTime: '15:30:05', endTime: '15:30:12' },
  { id: 'step-3', name: 'Diagnose', agents: ['Correlation', 'Diagnostics', 'Root Cause Analyst'], status: 'active', startTime: '15:30:12' },
  { id: 'step-4', name: 'Plan', agents: ['Remediation Planner', 'Governance'], status: 'pending' },
  { id: 'step-5', name: 'Authorize', agents: ['Governance', 'Customer Comms'], status: 'pending' },
  { id: 'step-6', name: 'Execute', agents: ['Tool Executor', 'Governance'], status: 'pending' },
  { id: 'step-7', name: 'Verify', agents: ['Verification'], status: 'pending' },
  { id: 'step-8', name: 'Close', agents: ['Customer Comms', 'Learning'], status: 'pending' },
];

// Agent Output Data
export const agentOutputs: AgentOutput[] = [
  {
    id: 'output-1',
    agentId: 'agent-1',
    agentName: 'Signal Triage',
    timestamp: '15:30:08',
    outputType: 'analysis',
    title: 'Alert Classification Complete',
    summary: 'Classified 2 alerts as HVAC_MECHANICAL with HIGH priority',
    details: 'Received alerts for discharge temperature (187°F) and cycle rate (26/hr) from RTU-01. Both exceed thresholds and show correlated timing. Classified as potential compressor short-cycling event requiring immediate diagnosis.',
    confidence: 0.94,
    rationale: [
      { step: 1, description: 'Alert Ingestion', reasoning: 'Received 2 alerts from hvac-001 within 15-second window', confidence: 1.0 },
      { step: 2, description: 'Deduplication Check', reasoning: 'No duplicate alerts found in 5-minute window', confidence: 1.0 },
      { step: 3, description: 'Pattern Matching', reasoning: 'Matched signature: compressor_short_cycle (discharge temp + high cycles)', confidence: 0.92 },
      { step: 4, description: 'Priority Assignment', reasoning: 'Equipment criticality HIGH + anomaly severity HIGH = Priority HIGH', confidence: 0.94 },
    ],
    evidence: [
      { type: 'data', source: 'Telemetry Stream', description: 'Discharge temp 187°F (threshold: 180°F)', weight: 0.9 },
      { type: 'data', source: 'Telemetry Stream', description: 'Cycle rate 26/hr (threshold: 12/hr)', weight: 0.95 },
      { type: 'rule', source: 'Alert Rules Engine', description: 'Rule: HVAC_TEMP_HIGH triggered', weight: 0.85 },
      { type: 'history', source: 'Case History', description: 'Similar pattern in CASE-2025-1215-003 led to compressor failure', weight: 0.7 },
    ],
  },
  {
    id: 'output-2',
    agentId: 'agent-2',
    agentName: 'Correlation',
    timestamp: '15:30:22',
    outputType: 'analysis',
    title: 'Cross-Signal Correlation Analysis',
    summary: 'Found strong correlation between discharge temp and cycle rate anomalies',
    details: 'Temporal analysis shows cycle rate increase preceded temperature rise by ~3 minutes. This pattern is consistent with refrigerant flow restriction causing compressor overwork. Cross-referenced with building load data shows no demand spike.',
    confidence: 0.88,
    rationale: [
      { step: 1, description: 'Temporal Clustering', reasoning: 'Both anomalies occurred within 5-minute window, suggesting common cause', confidence: 0.95 },
      { step: 2, description: 'Lead-Lag Analysis', reasoning: 'Cycle rate increase (t=0) preceded temp rise (t+3min) - indicates causal relationship', confidence: 0.85 },
      { step: 3, description: 'External Factor Check', reasoning: 'Building load, ambient temp, and schedule checked - no external triggers found', confidence: 0.9 },
      { step: 4, description: 'Historical Pattern Match', reasoning: 'Pattern matches 3 previous compressor restriction events (2024-2025)', confidence: 0.82 },
    ],
    evidence: [
      { type: 'data', source: 'Time Series Analysis', description: 'Pearson correlation: 0.87 between metrics', weight: 0.9 },
      { type: 'model', source: 'Bayesian Inference', description: 'P(common cause | data) = 0.91', weight: 0.95 },
      { type: 'history', source: 'Pattern Database', description: '3 similar events in past 18 months', weight: 0.75 },
    ],
  },
  {
    id: 'output-3',
    agentId: 'agent-3',
    agentName: 'Diagnostics',
    timestamp: '15:31:45',
    outputType: 'analysis',
    title: 'Fault Tree Analysis Results',
    summary: 'Primary hypothesis: Refrigerant restriction in liquid line',
    details: 'Fault tree analysis evaluated 12 potential failure modes. Top 3 candidates: (1) Liquid line restriction - 68% probability, (2) TXV malfunction - 18% probability, (3) Low refrigerant charge - 9% probability. Recommend sensor verification before remediation.',
    confidence: 0.82,
    rationale: [
      { step: 1, description: 'Symptom Mapping', reasoning: 'High discharge temp + short cycling maps to 4 fault tree branches', confidence: 0.9 },
      { step: 2, description: 'Bayesian Update', reasoning: 'Prior P(restriction) = 0.25, posterior = 0.68 after evidence', confidence: 0.85 },
      { step: 3, description: 'Elimination', reasoning: 'Low charge ruled out - suction pressure normal (68 psi)', confidence: 0.92 },
      { step: 4, description: 'Confidence Aggregation', reasoning: 'Weighted average of evidence streams', confidence: 0.82 },
    ],
    evidence: [
      { type: 'model', source: 'Fault Tree Model', description: 'Branch: RESTRICTION → HIGH_DISCHARGE → SHORT_CYCLE', weight: 0.9 },
      { type: 'data', source: 'Suction Pressure', description: 'Normal range (68 psi) rules out low charge', weight: 0.85 },
      { type: 'rule', source: 'Diagnostic Rules', description: 'Rule: If high discharge AND normal suction THEN restriction', weight: 0.88 },
      { type: 'history', source: 'Maintenance Records', description: 'Last filter change: 8 months ago (recommended: 6 months)', weight: 0.6 },
    ],
  },
];

export const currentCase: Case = {
  id: 'CASE-2026-0124-001',
  title: 'RTU-01 Compressor Short-Cycling',
  status: 'diagnose',
  priority: 'high',
  createdAt: '2026-01-24T15:30:05Z',
  updatedAt: '2026-01-24T15:31:45Z',
  assignedAgents: ['Signal Triage', 'Correlation', 'Diagnostics', 'Root Cause Analyst'],
  alerts: 2,
  hypotheses: 3,
};

// Time series data for charts
export const posteriorConvergenceData = [
  { iteration: 0, prior: 0.45, posterior: 0.45, lower: 0.35, upper: 0.55 },
  { iteration: 100, prior: 0.45, posterior: 0.52, lower: 0.42, upper: 0.62 },
  { iteration: 200, prior: 0.45, posterior: 0.58, lower: 0.48, upper: 0.68 },
  { iteration: 300, prior: 0.45, posterior: 0.63, lower: 0.53, upper: 0.73 },
  { iteration: 400, prior: 0.45, posterior: 0.67, lower: 0.58, upper: 0.76 },
  { iteration: 500, prior: 0.45, posterior: 0.70, lower: 0.62, upper: 0.78 },
  { iteration: 600, prior: 0.45, posterior: 0.72, lower: 0.64, upper: 0.80 },
  { iteration: 700, prior: 0.45, posterior: 0.73, lower: 0.65, upper: 0.81 },
];

export const telemetryHistory = Array.from({ length: 60 }, (_, i) => ({
  time: `${Math.floor(i / 60)}:${(i % 60).toString().padStart(2, '0')}`,
  dischargeTemp: 165 + (i > 30 ? (i - 30) * 0.7 : 0) + Math.random() * 3,
  cycleRate: 8 + (i > 25 ? (i - 25) * 0.6 : 0) + Math.random() * 2,
  threshold_temp: 180,
  threshold_cycles: 12,
}));
