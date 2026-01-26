/**
 * API Service for connecting to the FastAPI backend
 */

const API_BASE_URL = 'http://localhost:8000';

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

export interface DemoStatus {
  status: 'idle' | 'running' | 'completed' | 'error';
  progress: number;
  current_step: string;
  has_results: boolean;
}

export interface Posterior {
  key: string;
  mean: number;
  ci_lower: number;
  ci_upper: number;
  n_observations: number;
  evidence_strength: number;
}

export interface TwinState {
  retailer_id: string;
  sku_id: string;
  inventory: number;
  demand_mean: number;
  demand_std: number;
  weeks_of_supply: number;
}

export interface PipelineStep {
  step_name: string;
  status: string;
  result_summary: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ScenarioResult {
  scenario_id: string;
  scenario_name: string;
  expected_sales: number;
  sales_ci_lower: number;
  sales_ci_upper: number;
  expected_roas: number;
  stockout_rate: number;
}

export interface GovernanceCheck {
  rule_name: string;
  passed: boolean;
  message: string;
}

export interface DemoResults {
  status: string;
  pack_id: string;
  created_at: string | null;
  bayesian: {
    overall_confidence: number;
    data_quality_score: number;
    posteriors: Posterior[];
  };
  digital_twin: {
    summary: Record<string, unknown>;
    states: TwinState[];
  };
  orchestration: {
    steps: PipelineStep[];
  };
  allocation: {
    current: {
      allocation_id: string;
      total_budget: number;
      spend_by_retailer: Record<string, Record<string, number>>;
    };
    recommended: {
      allocation_id: string;
      total_budget: number;
      spend_by_retailer: Record<string, Record<string, number>>;
    };
  };
  scenarios: ScenarioResult[];
  governance: {
    status: string | null;
    approved: boolean | null;
    checks: GovernanceCheck[];
  };
  executive_summary: string;
  uncertainty_acknowledgment: string;
}

export interface Retailer {
  retailer_id: string;
  retailer_name: string;
  tier: string;
  channels: string[];
  min_spend_share: number;
  avg_inventory_weeks: number;
}

export interface Channel {
  channel: string;
  prior_elasticity_mean: number;
  prior_elasticity_std: number;
  adstock_decay: number;
}

export interface SKU {
  sku_id: string;
  sku_name: string;
  category: string;
  brand: string;
  unit_price: number;
  unit_cost: number;
  margin: number;
  weekly_base_demand: number;
}

class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP error ${response.status}`);
    }

    return response.json();
  }

  // Health check
  async healthCheck(): Promise<{ status: string; message: string }> {
    return this.fetch('/');
  }

  // Get demo status
  async getStatus(): Promise<DemoStatus> {
    return this.fetch('/api/status');
  }

  // Get logs
  async getLogs(): Promise<{ logs: LogEntry[] }> {
    return this.fetch('/api/logs');
  }

  // Run the demo
  async runDemo(): Promise<{ status: string; message: string; pack_id: string }> {
    return this.fetch('/api/demo/run', { method: 'POST' });
  }

  // Get demo results
  async getResults(): Promise<DemoResults> {
    return this.fetch('/api/demo/results');
  }

  // Get retailers
  async getRetailers(): Promise<{ retailers: Retailer[] }> {
    return this.fetch('/api/demo/retailers');
  }

  // Get channels
  async getChannels(): Promise<{ channels: Channel[] }> {
    return this.fetch('/api/demo/channels');
  }

  // Get SKUs
  async getSKUs(): Promise<{ skus: SKU[] }> {
    return this.fetch('/api/demo/skus');
  }

  // UI Page Data Endpoints
  async getBayesianPageData(): Promise<BayesianPageData> {
    return this.fetch('/api/ui/bayesian');
  }

  async getDigitalTwinPageData(): Promise<DigitalTwinPageData> {
    return this.fetch('/api/ui/digital-twin');
  }

  async getOrchestrationPageData(): Promise<OrchestrationPageData> {
    return this.fetch('/api/ui/orchestration');
  }

  async getAgentOutputPageData(): Promise<AgentOutputPageData> {
    return this.fetch('/api/ui/agent-output');
  }
}

// UI Page Data Interfaces
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

export interface PosteriorConvergence {
  iteration: number;
  prior: number;
  posterior: number;
  lower: number;
  upper: number;
}

export interface BayesianPageData {
  bayesianPredictions: BayesianPrediction[];
  modelParameters: ModelParameter[];
  federatedNodes: FederatedNode[];
  posteriorConvergenceData: PosteriorConvergence[];
  aggregationSummary: {
    totalSamples: number;
    activeNodes: number;
    syncRounds: number;
    modelUncertainty: number;
  };
}

export interface DeviceMetric {
  name: string;
  value: number;
  unit: string;
  threshold?: { min?: number; max?: number };
  trend: 'up' | 'down' | 'stable';
}

export interface Device {
  id: string;
  name: string;
  type: 'compressor' | 'pump' | 'valve' | 'sensor' | 'hvac';
  status: 'normal' | 'warning' | 'critical' | 'offline';
  location: string;
  lastUpdate: string;
  metrics: DeviceMetric[];
}

export interface TwinActivity {
  id: string;
  timestamp: string;
  type: 'telemetry' | 'alert' | 'prediction' | 'action';
  deviceId: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
}

export interface TelemetryPoint {
  time: string;
  inventory: number;
  demand: number;
  threshold_inventory: number;
}

export interface DigitalTwinPageData {
  devices: Device[];
  twinActivities: TwinActivity[];
  telemetryHistory: TelemetryPoint[];
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  status: 'idle' | 'processing' | 'waiting' | 'completed';
  avatar: string;
  description?: string;
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

export interface CurrentCase {
  id: string;
  title: string;
  status: string;
  priority: string;
  createdAt?: string;
  assignedAgents: string[];
  alerts: number;
  hypotheses: number;
  totalBudget: number;
  confidence: number;
}

export interface OrchestrationPageData {
  agents: Agent[];
  agentActions: AgentAction[];
  orchestrationSteps: OrchestrationStep[];
  currentCase: CurrentCase;
  governance: {
    autonomyLevel: string;
    policyChecks: { passed: number; total: number };
    pendingApprovals: number;
    auditEntries: number;
  };
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

export interface AgentOutputPageData {
  agentOutputs: AgentOutput[];
  agents: Agent[];
}

export const api = new ApiService();
export default api;
