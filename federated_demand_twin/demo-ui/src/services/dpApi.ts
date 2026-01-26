/**
 * API Service for Demand & Procurement Backend
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

export interface DPConfig {
  organization_id: string;
  organization_name: string;
  skus: Array<{ sku_id: string; sku_name: string; category: string; unit_cost: number; lead_time_days: number; current_inventory: number; service_level: string }>;
  suppliers: Array<{ supplier_id: string; supplier_name: string; tier: string; avg_lead_time_days: number; sku_ids: string[] }>;
  forecast_horizon_weeks: number;
  working_capital_limit: number;
}

class DPApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP error ${response.status}`);
    }
    return response.json();
  }

  async healthCheck(): Promise<{ status: string; message: string }> {
    return this.fetch('/');
  }

  async getStatus(): Promise<DemoStatus> {
    return this.fetch('/api/dp/status');
  }

  async getLogs(): Promise<{ logs: LogEntry[] }> {
    return this.fetch('/api/dp/logs');
  }

  async runDemo(): Promise<{ status: string; message: string; pack_id: string }> {
    return this.fetch('/api/dp/demo/run', { method: 'POST' });
  }

  async getConfig(): Promise<DPConfig> {
    return this.fetch('/api/dp/config');
  }

  async getBayesianPageData(): Promise<DPBayesianPageData> {
    return this.fetch('/api/dp/ui/bayesian');
  }

  async getDigitalTwinPageData(): Promise<DPDigitalTwinPageData> {
    return this.fetch('/api/dp/ui/digital-twin');
  }

  async getOrchestrationPageData(): Promise<DPOrchestrationPageData> {
    return this.fetch('/api/dp/ui/orchestration');
  }

  async getAgentOutputPageData(): Promise<DPAgentOutputPageData> {
    return this.fetch('/api/dp/ui/agent-output');
  }
}

// Page Data Interfaces
export interface DPBayesianPageData {
  bayesianPredictions: Array<{ id: string; timestamp: string; metric: string; predictedValue: number; confidenceInterval: [number, number]; probability: number; priorMean: number; posteriorMean: number; uncertainty: number }>;
  modelParameters: Array<{ name: string; prior: number; posterior: number; credibleInterval: [number, number] }>;
  federatedNodes: Array<{ id: string; name: string; location: string; status: string; lastSync: string; localSamples: number; contribution: number }>;
  posteriorConvergenceData: Array<{ iteration: number; prior: number; posterior: number; lower: number; upper: number }>;
  aggregationSummary: { totalSamples: number; activeNodes: number; syncRounds: number; modelUncertainty: number };
}

export interface DPDigitalTwinPageData {
  devices: Array<{ id: string; name: string; type: string; status: string; location: string; lastUpdate: string; metrics: Array<{ name: string; value: number; unit: string; trend: string }> }>;
  twinActivities: Array<{ id: string; timestamp: string; type: string; deviceId: string; message: string; severity: string }>;
  telemetryHistory: Array<{ time: string; inventory: number; demand: number; threshold_inventory: number }>;
}

export interface DPOrchestrationPageData {
  agents: Array<{ id: string; name: string; role: string; status: string; avatar: string; description?: string }>;
  agentActions: Array<{ id: string; agentId: string; agentName: string; timestamp: string; action: string; target: string; status: string; duration?: number }>;
  orchestrationSteps: Array<{ id: string; name: string; agents: string[]; status: string; startTime?: string; endTime?: string }>;
  currentCase: { id: string; title: string; status: string; priority: string; createdAt?: string; assignedAgents: string[]; alerts: number; hypotheses: number; totalBudget: number; confidence: number };
  governance: { autonomyLevel: string; policyChecks: { passed: number; total: number }; pendingApprovals: number; auditEntries: number };
}

export interface DPAgentOutputPageData {
  agentOutputs: Array<{ id: string; agentId: string; agentName: string; timestamp: string; outputType: string; title: string; summary: string; details: string; confidence: number; rationale: Array<{ step: number; description: string; reasoning: string; confidence: number }>; evidence: Array<{ type: string; source: string; description: string; weight: number }> }>;
  agents: Array<{ id: string; name: string; role: string; status: string; avatar: string }>;
}

export const dpApi = new DPApiService();
export default dpApi;
