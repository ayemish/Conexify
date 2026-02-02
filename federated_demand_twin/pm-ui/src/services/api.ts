/**
 * API Service Layer
 * 
 * Provides typed interfaces to the HVACRPdM backend API.
 * Replaces mock data with real backend integration.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

// API Response Types
export interface APIResponse<T> {
  success: boolean;
  message: string;
  data: T;
  timestamp: string;
  status_code?: number;
  details?: unknown;
}

// Model Types (aligned with backend)
export type ModelType = 'anomaly_detection' | 'failure_prediction' | 'rul_estimation' | 'alarm_quality';
export type ModelStage = 'development' | 'staging' | 'production' | 'archived';
export type ExperimentStatus = 'draft' | 'running' | 'completed' | 'stopped';

export interface ModelVersion {
  version_id: string;
  model_name: string;
  model_type: ModelType;
  version_number: string;
  stage: ModelStage;
  created_at: string;
  deployed_at: string | null;
}

export interface ModelDetails extends ModelVersion {
  description?: string;
  metrics?: PerformanceMetrics;
  artifact_path?: string;
  config?: Record<string, unknown>;
}

export interface PerformanceMetrics {
  accuracy?: number;
  precision?: number;
  recall?: number;
  f1_score?: number;
  auc_roc?: number;
  false_positive_rate?: number;
  failure_capture_rate?: number;
  prediction_lead_time_hours?: number;
  estimated_cost_savings?: number;
}

// Experiment Types
export interface Experiment {
  experiment_id: string;
  experiment_name: string;
  description?: string;
  model_type: ModelType;
  status: ExperimentStatus;
  created_at: string;
  n_variants: number;
  winner_variant_id?: string;
  variants?: ExperimentVariant[];
}

export interface ExperimentVariant {
  variant_id: string;
  variant_name: string;
  model_version_id: string;
  traffic_percentage: number;
  is_control: boolean;
  n_predictions: number;
}

// Retraining Types
export type RetrainingTriggerType = 'scheduled' | 'drift_detected' | 'performance_degradation' | 'case_feedback' | 'manual';

export interface RetrainingJob {
  job_id: string;
  model_name: string;
  trigger_type: RetrainingTriggerType;
  status: string;
  created_at: string;
  completed_at: string | null;
  improvement_detected: boolean;
}

export interface RetrainingTrigger {
  trigger_id: string;
  name: string;
  trigger_type: RetrainingTriggerType;
  enabled: boolean;
  config: Record<string, unknown>;
  last_triggered?: string;
}

// Governance Types
export interface PendingApproval {
  approval_id: string;
  action_type: string;
  target_id: string;
  target_type: string;
  requested_by: string;
  requested_at: string;
  risk_level: string;
  expires_at: string | null;
}

// Alert Types
export interface Alert {
  alert_id: string;
  rule_name: string;
  severity: 'critical' | 'warning' | 'info';
  state: 'firing' | 'pending' | 'resolved';
  message: string;
  metric_name: string;
  metric_value: number;
  threshold: number;
  fired_at: string;
  acknowledged_by?: string;
}

// Health Types
export interface HealthStatus {
  status: string;
  site_id: string;
  uptime_seconds: number;
  request_count: number;
}

export interface ComponentHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  message: string;
  response_time_ms: number;
  last_checked: string;
  details?: Record<string, string | number>;
}

export interface SystemHealth {
  components: ComponentHealth[];
  overall_status: string;
  timestamp: string;
  system_resources: {
    cpu_percent: number;
    memory_percent: number;
    disk_percent: number;
  };
}

// Dashboard Types
export interface DashboardSummary {
  models: {
    total: number;
    production: number;
    staging: number;
  };
  experiments: {
    active: number;
    completed: number;
  };
  retraining: {
    pending: number;
    running: number;
  };
  alerts: {
    critical: number;
    warning: number;
  };
  system?: Record<string, unknown>;
}

// API Error class
export class APIError extends Error {
  constructor(
    message: string,
    public statusCode: number = 400,
    public details?: unknown
  ) {
    super(message);
    this.name = 'APIError';
  }
}

// Generic fetch wrapper with error handling
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  // Check content type to ensure we're getting JSON
  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    // If not JSON, the endpoint likely doesn't exist or returned HTML
    if (!response.ok) {
      throw new APIError(
        `API endpoint ${endpoint} returned non-JSON response (${response.status})`,
        response.status
      );
    }
    // Return empty array for list endpoints, null for others
    return (endpoint.includes('list') || endpoint.endsWith('s') ? [] : null) as T;
  }

  // Try to parse JSON, handle empty responses
  const text = await response.text();
  if (!text || text.trim() === '') {
    if (!response.ok) {
      throw new APIError(`API endpoint ${endpoint} returned empty response`, response.status);
    }
    return (endpoint.includes('list') || endpoint.endsWith('s') ? [] : null) as T;
  }

  let data: APIResponse<T>;
  try {
    data = JSON.parse(text);
  } catch {
    throw new APIError(
      `Failed to parse API response from ${endpoint}: Invalid JSON`,
      response.status
    );
  }

  if (!response.ok || !data.success) {
    throw new APIError(
      data.message || 'API request failed',
      data.status_code || response.status,
      data.details
    );
  }

  return data.data;
}

// =========================================================================
// Model API
// =========================================================================

export const modelsAPI = {
  /**
   * List all models with optional filters
   */
  list: async (params?: { model_type?: ModelType; stage?: ModelStage }): Promise<ModelVersion[]> => {
    const queryParams = new URLSearchParams();
    if (params?.model_type) queryParams.set('model_type', params.model_type);
    if (params?.stage) queryParams.set('stage', params.stage);
    const query = queryParams.toString();
    return apiFetch<ModelVersion[]>(`/models${query ? `?${query}` : ''}`);
  },

  /**
   * Get model details by version ID
   */
  get: async (versionId: string): Promise<ModelDetails> => {
    return apiFetch<ModelDetails>(`/models/${versionId}`);
  },

  /**
   * Get current production model for a model name
   */
  getProduction: async (modelName: string): Promise<ModelDetails> => {
    return apiFetch<ModelDetails>(`/models/production/${modelName}`);
  },

  /**
   * Deploy a model to production
   */
  deploy: async (versionId: string, deployedBy: string, skipApproval = false): Promise<{ version_id: string }> => {
    return apiFetch<{ version_id: string }>('/models/deploy', {
      method: 'POST',
      body: JSON.stringify({
        version_id: versionId,
        deployed_by: deployedBy,
        skip_approval: skipApproval,
      }),
    });
  },

  /**
   * Rollback to previous model version
   */
  rollback: async (modelName: string, reason: string, rolledBackBy: string): Promise<void> => {
    await apiFetch('/models/rollback', {
      method: 'POST',
      body: JSON.stringify({
        model_name: modelName,
        reason,
        rolled_back_by: rolledBackBy,
      }),
    });
  },

  /**
   * Get model health status
   */
  getHealth: async (modelName: string): Promise<Record<string, unknown>> => {
    return apiFetch<Record<string, unknown>>(`/models/${modelName}/health`);
  },
};

// =========================================================================
// Experiments API
// =========================================================================

export const experimentsAPI = {
  /**
   * List all experiments
   */
  list: async (status?: ExperimentStatus): Promise<Experiment[]> => {
    const query = status ? `?status=${status}` : '';
    return apiFetch<Experiment[]>(`/experiments${query}`);
  },

  /**
   * Get experiment details
   */
  get: async (experimentId: string): Promise<Experiment> => {
    return apiFetch<Experiment>(`/experiments/${experimentId}`);
  },

  /**
   * Create a new experiment
   */
  create: async (params: {
    name: string;
    description?: string;
    model_type: ModelType;
    control_version_id: string;
    treatment_version_id: string;
    control_traffic_pct?: number;
    created_by: string;
  }): Promise<{ experiment_id: string }> => {
    return apiFetch<{ experiment_id: string }>('/experiments', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /**
   * Start an experiment
   */
  start: async (experimentId: string, startedBy: string): Promise<void> => {
    await apiFetch(`/experiments/${experimentId}/start`, {
      method: 'POST',
      body: JSON.stringify({ started_by: startedBy }),
    });
  },

  /**
   * Conclude an experiment
   */
  conclude: async (experimentId: string, concludedBy: string, promoteWinner = false): Promise<void> => {
    await apiFetch(`/experiments/${experimentId}/conclude`, {
      method: 'POST',
      body: JSON.stringify({
        concluded_by: concludedBy,
        promote_winner: promoteWinner,
      }),
    });
  },

  /**
   * Get experiment statistics
   */
  getStats: async (experimentId: string): Promise<Record<string, unknown>> => {
    return apiFetch<Record<string, unknown>>(`/experiments/${experimentId}/stats`);
  },
};

// =========================================================================
// Retraining API
// =========================================================================

export const retrainingAPI = {
  /**
   * List retraining jobs
   */
  listJobs: async (params?: { model_name?: string; status?: string }): Promise<RetrainingJob[]> => {
    const queryParams = new URLSearchParams();
    if (params?.model_name) queryParams.set('model_name', params.model_name);
    if (params?.status) queryParams.set('status', params.status);
    const query = queryParams.toString();
    return apiFetch<RetrainingJob[]>(`/retraining/jobs${query ? `?${query}` : ''}`);
  },

  /**
   * Trigger manual retraining
   */
  trigger: async (modelName: string, triggeredBy: string): Promise<{ job_id: string }> => {
    return apiFetch<{ job_id: string }>('/retraining/trigger', {
      method: 'POST',
      body: JSON.stringify({
        model_name: modelName,
        triggered_by: triggeredBy,
      }),
    });
  },

  /**
   * Get status of all retraining triggers
   */
  getTriggerStatus: async (): Promise<RetrainingTrigger[]> => {
    return apiFetch<RetrainingTrigger[]>('/retraining/triggers');
  },
};

// =========================================================================
// Governance API
// =========================================================================

export const governanceAPI = {
  /**
   * List pending approvals
   */
  listPendingApprovals: async (): Promise<PendingApproval[]> => {
    return apiFetch<PendingApproval[]>('/governance/approvals/pending');
  },

  /**
   * Process an approval decision
   */
  processApproval: async (
    approvalId: string,
    approved: boolean,
    reviewer: string,
    notes?: string
  ): Promise<void> => {
    await apiFetch(`/governance/approvals/${approvalId}`, {
      method: 'POST',
      body: JSON.stringify({
        approved,
        reviewer,
        notes,
      }),
    });
  },
};

// =========================================================================
// Alerts API
// =========================================================================

export const alertsAPI = {
  /**
   * Get active alerts
   */
  list: async (): Promise<Alert[]> => {
    return apiFetch<Alert[]>('/alerts');
  },

  /**
   * Acknowledge an alert
   */
  acknowledge: async (alertId: string, userId: string): Promise<void> => {
    await apiFetch(`/alerts/${alertId}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    });
  },

  /**
   * Silence an alert
   */
  silence: async (alertId: string, durationMinutes: number): Promise<void> => {
    await apiFetch(`/alerts/${alertId}/silence`, {
      method: 'POST',
      body: JSON.stringify({ duration_minutes: durationMinutes }),
    });
  },
};

// =========================================================================
// Metrics & Health API
// =========================================================================

export const systemAPI = {
  /**
   * Get dashboard summary
   */
  getDashboard: async (): Promise<DashboardSummary> => {
    return apiFetch<DashboardSummary>('/dashboard');
  },

  /**
   * Get metrics as JSON
   */
  getMetrics: async (): Promise<Record<string, unknown>> => {
    return apiFetch<Record<string, unknown>>('/metrics/json');
  },

  /**
   * Health check
   */
  getHealth: async (): Promise<HealthStatus> => {
    return apiFetch<HealthStatus>('/health');
  },

  /**
   * Detailed health check
   */
  getDetailedHealth: async (): Promise<{ components: ComponentHealth[]; overall_status: string }> => {
    return apiFetch<{ components: ComponentHealth[]; overall_status: string }>('/health/detailed');
  },
};

// =========================================================================
// Unified API Export
// =========================================================================

export const api = {
  models: modelsAPI,
  experiments: experimentsAPI,
  retraining: retrainingAPI,
  governance: governanceAPI,
  alerts: alertsAPI,
  system: systemAPI,
};

export default api;
