/**
 * Fleet & Telemetry API Service
 *
 * Centralizes fleet asset, metrics, alert, and approval API calls.
 */

import { request, safeRequest } from './apiClient';

const FLEET_BASE = '/api/v1/fleet';
const ALERT_BASE = '/api/v1/alerts';
const APPROVAL_BASE = '/api/v1/approvals';

const FleetApiService = {
  /** Fetch all fleet assets. */
  getAssets() {
    return safeRequest(`${FLEET_BASE}/assets`);
  },

  /** Fetch fleet-level metrics. */
  getMetrics() {
    return safeRequest(`${FLEET_BASE}/metrics`);
  },

  /** Fetch asset detail by ID. */
  getAsset(assetId) {
    return request(`${FLEET_BASE}/assets/${assetId}`);
  },

  /** Fetch telemetry for an asset. */
  getTelemetry(assetId, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return request(`${FLEET_BASE}/assets/${assetId}/telemetry${qs ? `?${qs}` : ''}`);
  },

  /** Fetch alerts with optional filters. */
  getAlerts(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return safeRequest(`${ALERT_BASE}${qs ? `?${qs}` : ''}`);
  },

  /** Acknowledge an alert. */
  acknowledgeAlert(alertId, body = {}) {
    return request(`${ALERT_BASE}/${alertId}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  /** Fetch pending approvals. */
  getApprovals(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return safeRequest(`${APPROVAL_BASE}${qs ? `?${qs}` : ''}`);
  },

  /** Approve or reject an approval item. */
  resolveApproval(approvalId, action, notes = '') {
    return request(`${APPROVAL_BASE}/${approvalId}`, {
      method: 'POST',
      body: JSON.stringify({ action, notes }),
    });
  },
};

export default FleetApiService;
