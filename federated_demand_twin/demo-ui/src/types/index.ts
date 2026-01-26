// Bayesian Model Types
export interface BayesianPrediction {
  id: string;
  timestamp: string;
  metric: string;
  predictedValue: number;
  confidenceInterval: [number, number];
  probability: number;
  priorMean: number;
  posteriorMean: number;
  uncertainty: number;
}

export interface ModelParameter {
  name: string;
  prior: number;
  posterior: number;
  credibleInterval: [number, number];
}

export interface FederatedNode {
  id: string;
  name: string;
  location: string;
  status: 'active' | 'syncing' | 'offline';
  lastSync: string;
  localSamples: number;
  contribution: number;
}

// Digital Twin Types
export interface Device {
  id: string;
  name: string;
  type: 'compressor' | 'pump' | 'valve' | 'sensor' | 'hvac';
  status: 'normal' | 'warning' | 'critical' | 'offline';
  location: string;
  metrics: DeviceMetric[];
  lastUpdate: string;
}

export interface DeviceMetric {
  name: string;
  value: number;
  unit: string;
  threshold?: { min?: number; max?: number };
  trend: 'up' | 'down' | 'stable';
}

export interface TwinActivity {
  id: string;
  timestamp: string;
  type: 'telemetry' | 'alert' | 'prediction' | 'action';
  deviceId: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
}

// Agent Types
export interface Agent {
  id: string;
  name: string;
  role: string;
  status: 'idle' | 'processing' | 'waiting' | 'completed';
  avatar: string;
  description: string;
}

export interface AgentAction {
  id: string;
  agentId: string;
  agentName: string;
  timestamp: string;
  action: string;
  target: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  duration?: number;
}

export interface OrchestrationStep {
  id: string;
  name: string;
  agents: string[];
  status: 'pending' | 'active' | 'completed' | 'skipped';
  startTime?: string;
  endTime?: string;
}

// Agent Output Types
export interface AgentOutput {
  id: string;
  agentId: string;
  agentName: string;
  timestamp: string;
  outputType: 'analysis' | 'recommendation' | 'decision' | 'action';
  title: string;
  summary: string;
  details: string;
  confidence: number;
  rationale: RationaleStep[];
  evidence: Evidence[];
}

export interface RationaleStep {
  step: number;
  description: string;
  reasoning: string;
  confidence: number;
}

export interface Evidence {
  type: 'data' | 'rule' | 'model' | 'history';
  source: string;
  description: string;
  weight: number;
}

// Case Types
export interface Case {
  id: string;
  title: string;
  status: 'intake' | 'triage' | 'diagnose' | 'plan' | 'authorize' | 'execute' | 'verify' | 'close' | 'learn';
  priority: 'critical' | 'high' | 'medium' | 'low';
  createdAt: string;
  updatedAt: string;
  assignedAgents: string[];
  alerts: number;
  hypotheses: number;
}
