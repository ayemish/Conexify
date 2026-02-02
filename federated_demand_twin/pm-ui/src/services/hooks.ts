/**
 * React Query Hooks for API Integration
 * 
 * Custom hooks that wrap the API service with React Query for
 * caching, loading states, and error handling.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  api,
  ModelVersion,
  ModelDetails,
  ModelType,
  ModelStage,
  Experiment,
  ExperimentStatus,
  RetrainingJob,
  RetrainingTrigger,
  PendingApproval,
  Alert,
  DashboardSummary,
  SystemHealth,
  APIError,
} from './api';

// Generic async state type
interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: APIError | Error | null;
  refetch: () => void;
}

// Generic hook for fetching data
function useAsyncData<T>(
  fetchFn: () => Promise<T>,
  dependencies: unknown[] = []
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<APIError | Error | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchFn();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, dependencies);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

// =========================================================================
// Model Hooks
// =========================================================================

/**
 * Hook to fetch list of models
 */
export function useModels(params?: { model_type?: ModelType; stage?: ModelStage }) {
  return useAsyncData<ModelVersion[]>(
    () => api.models.list(params),
    [params?.model_type, params?.stage]
  );
}

/**
 * Hook to fetch a single model by version ID
 */
export function useModel(versionId: string | null) {
  return useAsyncData<ModelDetails | null>(
    async () => (versionId ? api.models.get(versionId) : null),
    [versionId]
  );
}

/**
 * Hook to fetch production model for a model name
 */
export function useProductionModel(modelName: string | null) {
  return useAsyncData<ModelDetails | null>(
    async () => (modelName ? api.models.getProduction(modelName) : null),
    [modelName]
  );
}

/**
 * Hook for model deployment mutation
 */
export function useDeployModel() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const deploy = useCallback(
    async (versionId: string, deployedBy: string, skipApproval = false) => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.models.deploy(versionId, deployedBy, skipApproval);
        return result;
      } catch (err) {
        const apiError = err instanceof Error ? err : new Error(String(err));
        setError(apiError);
        throw apiError;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { deploy, loading, error };
}

/**
 * Hook for model rollback mutation
 */
export function useRollbackModel() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const rollback = useCallback(
    async (modelName: string, reason: string, rolledBackBy: string) => {
      setLoading(true);
      setError(null);
      try {
        await api.models.rollback(modelName, reason, rolledBackBy);
      } catch (err) {
        const apiError = err instanceof Error ? err : new Error(String(err));
        setError(apiError);
        throw apiError;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { rollback, loading, error };
}

// =========================================================================
// Experiment Hooks
// =========================================================================

/**
 * Hook to fetch list of experiments
 */
export function useExperiments(status?: ExperimentStatus) {
  return useAsyncData<Experiment[]>(
    () => api.experiments.list(status),
    [status]
  );
}

/**
 * Hook to fetch a single experiment
 */
export function useExperiment(experimentId: string | null) {
  return useAsyncData<Experiment | null>(
    async () => (experimentId ? api.experiments.get(experimentId) : null),
    [experimentId]
  );
}

/**
 * Hook for creating an experiment
 */
export function useCreateExperiment() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const create = useCallback(
    async (params: {
      name: string;
      description?: string;
      model_type: ModelType;
      control_version_id: string;
      treatment_version_id: string;
      control_traffic_pct?: number;
      created_by: string;
    }) => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.experiments.create(params);
        return result;
      } catch (err) {
        const apiError = err instanceof Error ? err : new Error(String(err));
        setError(apiError);
        throw apiError;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { create, loading, error };
}

/**
 * Hook for starting/concluding experiments
 */
export function useExperimentActions() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const start = useCallback(async (experimentId: string, startedBy: string) => {
    setLoading(true);
    setError(null);
    try {
      await api.experiments.start(experimentId, startedBy);
    } catch (err) {
      const apiError = err instanceof Error ? err : new Error(String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setLoading(false);
    }
  }, []);

  const conclude = useCallback(
    async (experimentId: string, concludedBy: string, promoteWinner = false) => {
      setLoading(true);
      setError(null);
      try {
        await api.experiments.conclude(experimentId, concludedBy, promoteWinner);
      } catch (err) {
        const apiError = err instanceof Error ? err : new Error(String(err));
        setError(apiError);
        throw apiError;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { start, conclude, loading, error };
}

// =========================================================================
// Retraining Hooks
// =========================================================================

/**
 * Hook to fetch retraining jobs
 */
export function useRetrainingJobs(params?: { model_name?: string; status?: string }) {
  return useAsyncData<RetrainingJob[]>(
    () => api.retraining.listJobs(params),
    [params?.model_name, params?.status]
  );
}

/**
 * Hook to fetch retraining trigger status
 */
export function useRetrainingTriggers() {
  return useAsyncData<RetrainingTrigger[]>(
    () => api.retraining.getTriggerStatus(),
    []
  );
}

/**
 * Hook for triggering retraining
 */
export function useTriggerRetraining() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const trigger = useCallback(async (modelName: string, triggeredBy: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.retraining.trigger(modelName, triggeredBy);
      return result;
    } catch (err) {
      const apiError = err instanceof Error ? err : new Error(String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setLoading(false);
    }
  }, []);

  return { trigger, loading, error };
}

// =========================================================================
// Governance Hooks
// =========================================================================

/**
 * Hook to fetch pending approvals
 */
export function usePendingApprovals() {
  return useAsyncData<PendingApproval[]>(
    () => api.governance.listPendingApprovals(),
    []
  );
}

/**
 * Hook for processing approvals
 */
export function useProcessApproval() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const process = useCallback(
    async (approvalId: string, approved: boolean, reviewer: string, notes?: string) => {
      setLoading(true);
      setError(null);
      try {
        await api.governance.processApproval(approvalId, approved, reviewer, notes);
      } catch (err) {
        const apiError = err instanceof Error ? err : new Error(String(err));
        setError(apiError);
        throw apiError;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { process, loading, error };
}

// =========================================================================
// Alert Hooks
// =========================================================================

/**
 * Hook to fetch active alerts
 */
export function useAlerts() {
  return useAsyncData<Alert[]>(() => api.alerts.list(), []);
}

/**
 * Hook for acknowledging alerts
 */
export function useAcknowledgeAlert() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const acknowledge = useCallback(async (alertId: string, userId: string) => {
    setLoading(true);
    setError(null);
    try {
      await api.alerts.acknowledge(alertId, userId);
    } catch (err) {
      const apiError = err instanceof Error ? err : new Error(String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setLoading(false);
    }
  }, []);

  return { acknowledge, loading, error };
}

/**
 * Hook for alert actions
 */
export function useAlertActions() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<APIError | Error | null>(null);

  const acknowledge = useCallback(async (alertId: string, userId: string) => {
    setLoading(true);
    setError(null);
    try {
      await api.alerts.acknowledge(alertId, userId);
    } catch (err) {
      const apiError = err instanceof Error ? err : new Error(String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setLoading(false);
    }
  }, []);

  const silence = useCallback(async (alertId: string, durationMinutes: number) => {
    setLoading(true);
    setError(null);
    try {
      await api.alerts.silence(alertId, durationMinutes);
    } catch (err) {
      const apiError = err instanceof Error ? err : new Error(String(err));
      setError(apiError);
      throw apiError;
    } finally {
      setLoading(false);
    }
  }, []);

  return { acknowledge, silence, loading, error };
}

// =========================================================================
// System/Dashboard Hooks
// =========================================================================

/**
 * Hook to fetch dashboard summary
 */
export function useDashboard() {
  return useAsyncData<DashboardSummary>(() => api.system.getDashboard(), []);
}

/**
 * Hook to fetch system health
 */
export function useSystemHealth() {
  return useAsyncData<SystemHealth>(
    () => api.system.getDetailedHealth(),
    []
  );
}

/**
 * Hook to fetch metrics
 */
export function useMetrics() {
  return useAsyncData<Record<string, unknown>>(
    () => api.system.getMetrics(),
    []
  );
}

// =========================================================================
// Polling Hook for Real-time Updates
// =========================================================================

/**
 * Hook for polling data at intervals
 */
export function usePolling<T>(
  fetchFn: () => Promise<T>,
  intervalMs: number = 30000,
  enabled: boolean = true
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<APIError | Error | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await fetchFn();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [fetchFn]);

  useEffect(() => {
    if (!enabled) return;

    fetchData();
    const interval = setInterval(fetchData, intervalMs);
    return () => clearInterval(interval);
  }, [fetchData, intervalMs, enabled]);

  return { data, loading, error, refetch: fetchData };
}
