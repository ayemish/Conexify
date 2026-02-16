/**
 * Work Order API Service
 *
 * Centralizes all AI Work Order Management API calls.
 * Replaces inline fetch calls in WorkOrderModule.jsx.
 */

import { safeRequest } from './apiClient';

const WO_BASE = '/api/v1/workorders';

const WorkOrderApiService = {
  /** Check WO service health and LLM availability. */
  getStatus() {
    return safeRequest(`${WO_BASE}/status`);
  },

  /** Interpret natural-language text into a structured WO draft. */
  interpret(payload) {
    return safeRequest(`${WO_BASE}/interpret`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** Evaluate PdM signals and auto-generate a work order. */
  autoCreate(payload) {
    return safeRequest(`${WO_BASE}/auto-create`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** AI impact assessment and priority scoring. */
  prioritize(payload) {
    return safeRequest(`${WO_BASE}/prioritize`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** Intelligent provider matching and ranking. */
  matchProviders(payload) {
    return safeRequest(`${WO_BASE}/match`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** AI cost and approval recommendation. */
  recommendCost(payload) {
    return safeRequest(`${WO_BASE}/recommend-cost`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** Post-service verification — pre/post metric comparison. */
  verify(payload) {
    return safeRequest(`${WO_BASE}/verify`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** Predictive WO forecast with narrative. */
  forecast(payload) {
    return safeRequest(`${WO_BASE}/forecast`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** A/B test analysis — baseline vs AI-predicted metrics. */
  abTest(payload) {
    return safeRequest(`${WO_BASE}/ab-test`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** Compute A/B baseline metrics from real database records. */
  getAbBaseline(siteId = 'default', timeRange = '30d') {
    return safeRequest(`${WO_BASE}/ab-baseline?site_id=${siteId}&time_range=${timeRange}`);
  },
};

export default WorkOrderApiService;
