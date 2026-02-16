/**
 * Orchestration API Service
 *
 * Centralizes pipeline orchestration and Loweconex platform API calls.
 */

import { request, safeRequest } from './apiClient';

const ORCH_BASE = '/api/v1/orchestration';
const LOWECONEX_BASE = '/api/v1/loweconex';

const OrchestrationApiService = {
  /** List available pipelines with their specs. */
  getPipelines() {
    return safeRequest(`${ORCH_BASE}/pipelines`);
  },

  /** Get run history for all or a specific pipeline type. */
  getHistory(pipelineType = null, limit = 10) {
    if (pipelineType) {
      return safeRequest(`${ORCH_BASE}/pipelines/${pipelineType}/history?limit=${limit}`);
    }
    return safeRequest(`${ORCH_BASE}/history?limit=${limit}`);
  },

  /** Run a specific pipeline type. */
  runPipeline(pipelineType) {
    return safeRequest(`${ORCH_BASE}/pipelines/${pipelineType}/run`, { method: 'POST' });
  },

  /** Run the full Loweconex 7-phase orchestrator pipeline. */
  runLoweconexPipeline(payload = {}) {
    return request(`${LOWECONEX_BASE}/pipeline`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** Check Loweconex pipeline status. */
  getLoweconexStatus() {
    return safeRequest(`${LOWECONEX_BASE}/pipeline/status`);
  },

  /** List available KPI crews. */
  listCrews() {
    return request(`${LOWECONEX_BASE}/crews`);
  },

  /** Run a single KPI crew. */
  runCrew(kpiName, payload = {}) {
    return request(`${LOWECONEX_BASE}/crews/${kpiName}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};

export default OrchestrationApiService;
